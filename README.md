# AgentFlow

**Multi-agent workflow orchestration platform** — build, run, and monitor AI agent pipelines through a visual web UI, with Telegram integration and real-time log streaming.

Built for the Yuno AI Engineer Challenge.

---

## Quick Start (single command)

```bash
# Edit .env — set GEMINI_API_KEY (and optionally TELEGRAM_BOT_TOKEN)

docker compose up --build
```

| Service | URL |
|---|---|
| Web UI | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| Swagger Docs | http://localhost:8000/docs |

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | ✅ | Free key from https://aistudio.google.com/app/apikey |
| `TELEGRAM_BOT_TOKEN` | ❌ | From @BotFather — enables Telegram channel |
| `DATABASE_URL` | auto | Set by docker-compose |
| `REDIS_URL` | auto | Set by docker-compose |
| `SECRET_KEY` | ❌ | App secret (default OK for dev) |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  Frontend · React + Vite                │
│  ┌─────────────┐  ┌──────────────────┐  ┌───────────┐  │
│  │ Agent Builder│  │ Workflow Builder  │  │  Monitor  │  │
│  │  (CRUD UI)  │  │  (React Flow)    │  │ (WS live) │  │
│  └──────┬──────┘  └────────┬─────────┘  └─────┬─────┘  │
└─────────┼──────────────────┼────────────────────┼───────┘
          │ REST /api/*       │                    │ WebSocket
┌─────────┼──────────────────┼────────────────────┼───────┐
│         ▼    Backend · FastAPI                   ▼       │
│  ┌─────────────┐   ┌───────────────┐   ┌──────────────┐ │
│  │  REST API   │   │ LangGraph     │   │  WebSocket   │ │
│  │  agents /   │──▶│ Executor      │──▶│  Manager     │ │
│  │  workflows /│   │ (tool loop,   │   │ (broadcast   │ │
│  │  monitor    │   │  memory,      │   │  per run +   │ │
│  └─────────────┘   │  guardrails)  │   │  global)     │ │
│                    └───────┬───────┘   └──────────────┘ │
│  ┌─────────────┐           │                             │
│  │ Telegram Bot│───────────┘                             │
│  └─────────────┘                                         │
│  ┌─────────────┐   ┌───────────────┐                     │
│  │ APScheduler │──▶│ Cron triggers │                     │
│  └─────────────┘   └───────────────┘                     │
└──────────────────────────┬──────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              │                         │
       ┌──────▼──────┐          ┌───────▼──────┐
       │  PostgreSQL  │          │    Redis     │
       │  agents      │          │  (pub/sub)   │
       │  workflows   │          └──────────────┘
       │  runs        │
       │  messages    │
       └──────────────┘
```

### Request flow

1. User creates agents (name, role, system prompt, model, tools, memory, guardrails, schedule) via the web UI
2. User opens the visual workflow builder — drags agent cards onto the canvas, draws edges for routing
3. A run is triggered (UI **▶ Run** button, or a Telegram message, or a cron schedule)
4. FastAPI creates a `WorkflowRun` record and hands off to the **LangGraph Executor** as a background task
5. The executor builds a `StateGraph` from the React Flow node/edge definition and invokes it asynchronously
6. Each agent node: trims history (memory window), calls Gemini via LangChain, executes any tool calls in a loop, then persists the output message to PostgreSQL
7. Every event (run_started, tool_call, agent_message, run_completed) is broadcast over WebSocket to the Monitor page in real time

---

## Why LangGraph?

| Feature | LangGraph | CrewAI | AutoGen |
|---|---|---|---|
| Arbitrary graph topology | ✅ StateGraph | ❌ sequential only | ⚠️ limited |
| Conditional routing | ✅ add_conditional_edges | ❌ | ⚠️ |
| Stateful execution | ✅ TypedDict state | ❌ | ⚠️ |
| Async-native | ✅ ainvoke | ⚠️ | ⚠️ |
| Tool-use loop | ✅ built-in | ⚠️ | ⚠️ |

LangGraph lets the React Flow visual builder map 1:1 to a real execution graph — any topology the user draws (linear, branching, conditional, cycles) runs as-is. CrewAI forces a sequential crew structure that breaks on complex topologies. AutoGen has weaker async support.

## Why FastAPI + Python?

- Native `async/await` — essential for concurrent LLM calls across multiple agent nodes
- WebSocket support built-in (no extra library needed)
- Pydantic v2 for zero-boilerplate validation
- LangChain, LangGraph, and the broader AI ecosystem all assume Python

---

## Project Structure

```
agentflow/
├── backend/
│   ├── api/
│   │   ├── agents.py        # Agent CRUD — POST/GET/PUT/DELETE /api/agents
│   │   ├── workflows.py     # Workflow CRUD, template instantiation, run execution
│   │   └── monitor.py       # Stats, WebSocket endpoints, recent runs/messages
│   ├── runtime/
│   │   └── executor.py      # LangGraph WorkflowExecutor — tool loop, memory, guardrails
│   ├── channels/
│   │   └── telegram.py      # Telegram bot — routes messages through latest workflow
│   ├── models/
│   │   ├── database.py      # SQLAlchemy async ORM models
│   │   └── schemas.py       # Pydantic request/response schemas
│   ├── workers/
│   │   ├── ws_manager.py    # WebSocket connection manager (per-run + global broadcast)
│   │   └── scheduler.py     # APScheduler cron runner for agent schedules
│   ├── tests/
│   │   └── test_main.py     # Agent CRUD, workflow execution, message delivery, stats
│   ├── main.py              # FastAPI app — startup wires DB, scheduler, Telegram
│   ├── config.py            # Pydantic settings (reads .env)
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── Agents/          # Agent list + create/edit modal (tools, memory, guardrails, schedule)
│       │   ├── Workflows/       # React Flow visual builder + run panel with live log
│       │   └── Monitor/         # Live dashboard — stats, recent runs, WebSocket event stream
│       ├── components/
│       │   └── AgentNode.jsx    # Custom React Flow node
│       ├── api.js               # Axios REST client + WebSocket helper
│       └── styles.css           # Design system (CSS variables, dark theme)
├── docker-compose.yml
└── .env.example
```

---

## Agent Configuration Reference

Each agent supports:

| Field | Description |
|---|---|
| `name` | Display name |
| `role` | Role label shown on canvas nodes |
| `system_prompt` | Full instruction prompt for the LLM |
| `model` | Gemini model: `gemini-2.5-flash`, `gemini-2.0-flash`, `gemini-1.5-flash`, `gemini-1.5-pro` |
| `tools` | Checkboxes: `web_search`, `calculator`, `datetime` |
| `memory_config` | `{ enabled, window }` — how many past messages to include |
| `guardrails` | `{ max_tokens }` — max output tokens per LLM call |
| `schedule` | `{ enabled, cron, timezone, workflow_id, trigger_message }` — APScheduler cron |

---

## Available Tools

| Tool | What it does |
|---|---|
| `web_search` | DuckDuckGo search via langchain-community |
| `calculator` | Safe math expression evaluator (supports all `math` module functions) |
| `datetime` | Returns current UTC date and time |

Tools are executed in a loop — if the LLM returns tool calls, they run and results feed back in; the loop continues until a plain text response is produced.

---

## Pre-built Templates

### Research + Summary
- **Researcher**: given a topic, uses `web_search` to gather information
- **Summarizer**: receives the research output, writes a clean structured summary
- Topology: linear A → B

### Triage + Responder
- **Triage Agent**: classifies the incoming message as FAQ, ESCALATION, or GENERAL
- **FAQ Agent**: handles routine questions
- **Escalation Agent**: handles complex/urgent requests
- Topology: conditional routing A → B (`if:FAQ`) or A → C (`if:ESCALATION`)

---

## Adding a New Workflow Template

1. Open `backend/api/workflows.py`
2. Add an entry to the `TEMPLATES` list:

```python
{
    "name": "My Template",
    "description": "What it does",
    "is_template": True,
    "definition": {"nodes": [], "edges": []},
    "agents": [
        {
            "name": "Agent A",
            "role": "Your Role",
            "system_prompt": "Your instructions...",
            "model": "gemini-2.5-flash",
            "tools": ["web_search"],
            "memory_config": {"enabled": True, "window": 10},
            "guardrails": {"max_tokens": 1000},
            "schedule": {},
        },
    ],
}
```

3. The template appears in **Workflows → Templates** in the UI. Clicking **Instantiate** creates the agents and workflow automatically.

---

## Adding a New Messaging Channel

1. Create `backend/channels/your_channel.py`:

```python
class YourChannel:
    def __init__(self):
        self.app = None

    async def setup(self):
        # Initialize your SDK, register message handler
        # On message: call run_workflow_async(run_id, definition, agents_map, text)
        pass

    async def run_polling(self):
        # Start receiving messages
        pass

    async def stop(self):
        pass

your_channel = YourChannel()
```

2. Wire it in `backend/main.py`:

```python
from channels.your_channel import your_channel

@app.on_event("startup")
async def startup():
    ...
    await your_channel.setup()
    if your_channel.app:
        asyncio.create_task(your_channel.run_polling())
```

3. Add credentials to `.env` and `config.py`.

---

## Running Tests

```bash
cd backend
pip install -r requirements.txt
pip install pytest pytest-asyncio httpx
pytest
```

Tests cover:
- Agent CRUD (create, list, get 404, update, delete)
- Workflow execution with mocked LLM (ChatGoogleGenerativeAI patched)
- Message persistence after a run
- Monitor stats endpoint
- Health check

---

## Demo Script (for the live session)

1. Open http://localhost:3000 → **Workflows** → click **Research + Summary** template → **Instantiate**
2. Select the new workflow → click **▶ Run** → type a research question (e.g. "Latest news on LLM agents")
3. Watch the right panel stream live: `run_started` → `tool_call` (web_search) → `agent_message` → `run_completed`
4. Switch to **Monitor** → see token count, cost estimate, and full message history
5. *(Telegram)* Send the same message to your bot → get the workflow result back in Telegram

---

## Evaluation Criteria Coverage

| Criterion | Weight | Implementation |
|---|---|---|
| Working end-to-end demo | 40% | 2+ agents, real LLM calls, real tool execution, Telegram channel |
| Architecture & code quality | 30% | Clear UI / runtime / persistence separation, async throughout, tests |
| UI/UX & configurability | 20% | Tools, memory, guardrails, schedule all configurable per-agent in UI |
| Documentation | 10% | This README — architecture diagram, setup, runtime justification, extension guides |
