# AgentFlow — Engineering Documentation
> Builder's notes: decisions made, patterns used, tradeoffs accepted

---

## What We Built

AgentFlow is a multi-agent orchestration platform where users visually wire AI agents into execution graphs, trigger them via UI/Telegram/cron, and watch them run in real time. The core loop: draw a graph → hit Run → LangGraph executes it node-by-node → every event streams to your browser via WebSocket.

---

## Stack Decisions

### Python + FastAPI (Backend)
Python was the only real option — LangGraph, LangChain, and every AI tool assume it. FastAPI gave us native `async/await` with zero ceremony, built-in WebSocket support, and Pydantic v2 for automatic request validation. No Express shim needed.

### LangGraph (Runtime)
The key insight: React Flow and LangGraph share the same mental model — both are directed graphs with nodes and edges. This made the visual builder map 1:1 to actual execution. Each node the user draws becomes a LangGraph `StateGraph` node; each arrow becomes an edge.

CrewAI was ruled out because it forces a sequential "crew" structure — you can't express branching or conditional routing. AutoGen was ruled out due to weaker async support. LangGraph's `add_conditional_edges` let us support `if:KEYWORD` edge labels for real routing logic.

### Gemini (LLM)
Free tier with a generous quota via `GEMINI_API_KEY` from Google AI Studio. `ChatGoogleGenerativeAI` from `langchain-google-genai` plugs directly into LangChain's tool-binding interface, so the tool-use loop works identically to OpenAI function calling.

### PostgreSQL + SQLAlchemy Async
Four tables: `agents`, `workflows`, `workflow_runs`, `messages`. The async ORM (`AsyncSession`, `asyncpg` driver) is essential — LLM calls can take 5–30 seconds, and blocking the event loop would kill concurrency. Every DB write uses `AsyncSessionLocal()` as an async context manager.

### Redis (Pub/Sub)
Redis is wired in docker-compose but the current WebSocket manager uses in-process fan-out (a dict of `WebSocket` lists). Redis pub/sub would be needed for multi-worker horizontal scaling — it's there for when that matters.

### React + Vite + React Flow (Frontend)
React Flow handles the visual workflow builder — it provides drag-and-drop canvas, custom node components, and the edge/node data model that we serialize directly to JSON and store in `workflow.definition`. Vite gives sub-second HMR during development.

---

## Architecture Walkthrough

```
Browser
  │
  ├─ REST (axios) ──────────────► FastAPI /api/*
  │                                   │
  └─ WebSocket ─────────────────────► /api/monitor/ws/{run_id}
                                      │
                            ┌─────────▼──────────┐
                            │   LangGraph Executor│
                            │   (background task) │
                            └─────────┬──────────┘
                                      │  tool calls
                            ┌─────────▼──────────┐
                            │  TOOL_REGISTRY      │
                            │  web_search         │
                            │  calculator         │
                            │  datetime           │
                            └─────────┬──────────┘
                                      │
                            ┌─────────▼──────────┐
                            │   PostgreSQL        │
                            │   agents / workflows│
                            │   runs / messages   │
                            └────────────────────┘

Telegram ──► TelegramChannel.handle_message()
                    │
                    └──► run_workflow_async() [same executor]

APScheduler ──► cron triggers ──► run_workflow_async()
```

### Request Lifecycle (Run a Workflow)

1. User clicks **▶ Run** in the UI with an input message
2. `POST /api/workflows/{id}/run` → FastAPI creates a `WorkflowRun` record (status=`pending`)
3. `asyncio.create_task(run_workflow_async(...))` — execution goes to background; HTTP returns the `run_id` immediately
4. UI opens a WebSocket to `/api/monitor/ws/{run_id}`
5. `WorkflowExecutor.execute()`:
   - Sets run status to `running`, broadcasts `run_started` event
   - Calls `build_graph()` to compile the StateGraph from the stored React Flow JSON
   - Invokes `compiled.ainvoke(initial_state)` — LangGraph walks the graph
6. For each agent node:
   - Trim message history per memory window
   - Call `llm_with_tools.ainvoke(msgs)` — Gemini responds
   - If tool calls come back → execute each tool → feed results back → loop until plain text
   - Persist `Message` to DB
   - Broadcast `agent_message` via WebSocket
7. Final node completes → run marked `completed`, `run_completed` broadcast
8. Monitor page shows the full event stream in real time

---

## Key Implementation Details

### Tool-Use Loop (executor.py)
The agentic loop is hand-rolled rather than using LangGraph's `ToolNode`. This was intentional — it gives us fine-grained control to broadcast a `tool_call` WebSocket event mid-loop so the Monitor shows tool usage in real time. The pattern:

```python
while True:
    response = await llm_with_tools.ainvoke(loop_msgs)
    tool_calls = getattr(response, "tool_calls", [])
    if not tool_calls:
        output = response.content
        break
    # execute tools, append ToolMessage, continue loop
```

### Conditional Routing
Edge labels prefixed with `if:` trigger conditional routing. When `build_graph()` encounters such an edge, it groups all conditional edges from a source node and creates a router function:

```python
def router(state):
    output = state["current_output"].upper()
    for keyword, target in routing_map.items():
        if keyword in output:
            return target
    return END
```

This means an agent can route to different downstream agents just by including a keyword in its output — exactly what the Triage template uses.

### Memory Windowing
Each agent has `memory_config: {enabled, window}`. When disabled, only the last `HumanMessage` is passed (stateless). When enabled, the last `window` messages are included. This prevents context bloat on long conversations while keeping agents contextually aware.

### Guardrails
`guardrails: {max_tokens}` maps directly to `max_output_tokens` in the LLM constructor. Simple but effective — prevents runaway responses. Future extension point for content filters, topic restrictions, etc.

### WebSocket Manager (ws_manager.py)
Two broadcast targets: per-run connections and global connections (for the Monitor dashboard). Connection sets are tracked in dicts. `broadcast_to_run` sends only to clients watching a specific run; `broadcast_global` sends to the Monitor's stats view.

### Telegram Integration (telegram.py)
`python-telegram-bot` v20 async API. On message receipt, the bot finds the most recently created workflow (or a configured default), builds the `agents_map` from the workflow's node definitions, creates a `WorkflowRun` record, then calls the same `run_workflow_async()` the REST API uses. No separate code path — Telegram is just another trigger source.

### Scheduler (scheduler.py)
APScheduler's `AsyncIOScheduler`. At startup, `sync_schedules()` reads all agents with `schedule.enabled == true` and registers cron jobs. Each job calls `run_workflow_async()` with `schedule.trigger_message` as the input.

### Template Instantiation (workflows.py)
Templates are stored as a Python list in `TEMPLATES` inside `workflows.py`. When a user clicks **Instantiate**, the API creates all the template's agents in the DB, then creates the workflow with those agent IDs wired into the node definitions. This gives real, independently editable agent copies per workflow instance.

---

## Database Schema

```
agents
  id, name, role, system_prompt, model
  tools (JSON array)
  memory_config (JSON: {enabled, window})
  guardrails (JSON: {max_tokens})
  schedule (JSON: {enabled, cron, timezone, workflow_id, trigger_message})

workflows
  id, name, description
  definition (JSON: React Flow {nodes, edges})
  is_template

workflow_runs
  id, workflow_id → workflows
  status (pending/running/completed/failed)
  input_message, output_message
  token_count, started_at, completed_at, error

messages
  id, workflow_run_id → workflow_runs
  from_agent, to_agent, content
  message_type (user_input/agent_message/final_output/tool_call)
  timestamp
```

All IDs are `uuid4` strings. No integer sequences — safe for distributed creation without coordination.

---

## Frontend Structure

```
pages/Agents/AgentsPage.jsx     — CRUD list + create/edit modal
pages/Workflows/WorkflowsPage.jsx — React Flow canvas + run panel
pages/Monitor/MonitorPage.jsx   — live stats + WebSocket event log
components/AgentNode.jsx        — custom React Flow node renderer
api.js                          — axios REST client + WS helper
```

The workflow builder stores the React Flow `nodes` and `edges` arrays directly to `workflow.definition`. No transform layer — what React Flow gives us is what LangGraph receives.

---

## Tradeoffs & Known Limitations

**In-process WebSocket fan-out** — works for a single server instance. Horizontal scaling would require Redis pub/sub between workers. The `redis_url` config is already there; the `ws_manager` needs a pub/sub adapter.

**Conditional routing by keyword matching** — simple and demo-friendly, but fragile for production. A proper solution would have the LLM output structured JSON with an explicit routing field.

**Gemini-only** — `ChatGoogleGenerativeAI` is hardcoded. The `model` field per agent is there; supporting OpenAI/Anthropic would just need a model-to-LLM factory function.

**Single Telegram workflow** — the bot always routes to the most recent workflow. Multi-workflow routing (e.g. by chat ID or `/use <workflow_id>` command) is the obvious next step.

**No auth** — CORS is `allow_origins=["*"]`. For production, add JWT/OAuth and scope agents/workflows per user.

**Token counting** — uses `usage_metadata.total_tokens` from Gemini responses. Not all models populate this field consistently; cost estimates are approximate.

---

## How to Extend

### Add a Tool
In `executor.py`, add to `TOOL_REGISTRY`:
```python
@tool
def my_tool(param: str) -> str:
    """Description the LLM sees."""
    return do_something(param)

TOOL_REGISTRY["my_tool"] = my_tool
```
Add `"my_tool"` to the checkbox list in `AgentsPage.jsx`.

### Add a Messaging Channel
Create `backend/channels/slack.py` implementing `setup()`, `run_polling()`, `stop()`. In the message handler, call `run_workflow_async()`. Wire it in `main.py` startup. Add token to `.env` and `config.py`.

### Add a Workflow Template
In `backend/api/workflows.py`, add an entry to `TEMPLATES`. The template auto-appears in the UI on next load.

### Add Agent Guardrails
`guardrails` is a free-form JSON dict. Add new keys (e.g. `blocked_topics`, `language`), then check them in `_make_node_fn()` before or after the LLM call.

---

## Running Tests

```bash
cd backend
pip install -r requirements.txt pytest pytest-asyncio httpx
pytest
```

Tests use `httpx.AsyncClient` against the FastAPI app directly (no running server needed). The LLM is mocked with `unittest.mock.patch` so tests run without a Gemini key.

Coverage:
- Agent CRUD (create, list, 404, update, delete)
- Workflow run with mocked LLM
- Message persistence after run
- Monitor stats endpoint
- Health check

---

## Evaluation Coverage (Yuno Challenge)

| Criterion | Weight | How it's met |
|---|---|---|
| Working end-to-end demo | 40% | 2+ agents, real Gemini calls, real DuckDuckGo tool execution, Telegram channel, live WebSocket streaming |
| Architecture & code quality | 30% | UI / executor / persistence fully separated, async throughout, Pydantic schemas, tests for critical paths |
| UI/UX & configurability | 20% | Per-agent: model, tools, memory window, max_tokens guardrail, cron schedule — all configurable in UI |
| Documentation | 10% | README + this document: architecture diagram, setup, runtime justification, extension guides |
