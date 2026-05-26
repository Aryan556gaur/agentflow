"""
LangGraph-based multi-agent workflow executor.

Each node in the React Flow graph becomes a LangGraph node.
Edges define routing between agents.
Every inter-agent message is persisted to DB and broadcast via WebSocket.

Tools supported (configured per-agent in tools list):
  web_search  – DuckDuckGo search via langchain_community
  calculator  – safe math expression evaluator
  datetime    – returns current UTC datetime
"""

import asyncio
import logging
import math
import operator
import uuid
from datetime import datetime, timezone
from typing import Any, TypedDict, Annotated

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END

from sqlalchemy import select

from models.database import Agent, WorkflowRun, Message, AsyncSessionLocal
from workers.ws_manager import manager as ws_manager
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ── Built-in tools ─────────────────────────────────────────────────────────────

@tool
def web_search(query: str) -> str:
    """Search the web for current information using DuckDuckGo."""
    try:
        from langchain_community.tools import DuckDuckGoSearchRun
        search = DuckDuckGoSearchRun()
        return search.run(query)
    except Exception as e:
        return f"Search error: {e}"


@tool
def calculator(expression: str) -> str:
    """Evaluate a safe mathematical expression. Example: '2 ** 10 + sqrt(144)'"""
    try:
        # Only allow safe math operations
        allowed = {k: v for k, v in math.__dict__.items() if not k.startswith("_")}
        allowed.update({"abs": abs, "round": round, "min": min, "max": max})
        result = eval(expression, {"__builtins__": {}}, allowed)  # noqa: S307
        return str(result)
    except Exception as e:
        return f"Calculator error: {e}"


@tool
def get_datetime() -> str:
    """Returns the current UTC date and time."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


TOOL_REGISTRY: dict[str, Any] = {
    "web_search": web_search,
    "calculator": calculator,
    "datetime": get_datetime,
}


# ── State ──────────────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    messages: Annotated[list, operator.add]
    current_output: str
    run_id: str
    token_count: int


# ── Executor ───────────────────────────────────────────────────────────────────

class WorkflowExecutor:
    """Executes a workflow definition using LangGraph."""

    def __init__(self, workflow_run_id: str, workflow_definition: dict, agents_map: dict[str, Agent]):
        self.run_id = workflow_run_id
        self.definition = workflow_definition
        self.agents_map = agents_map  # node_id -> Agent ORM object

    def _build_llm(self, agent: Agent) -> ChatGoogleGenerativeAI:
        # Honour max_tokens guardrail if set
        guardrails = agent.guardrails or {}
        max_tokens = guardrails.get("max_tokens") or 1024

        return ChatGoogleGenerativeAI(
            model=agent.model,
            google_api_key=settings.gemini_api_key,
            temperature=0.7,
            max_output_tokens=int(max_tokens),
        )

    def _get_agent_tools(self, agent: Agent) -> list:
        """Return bound LangChain tool objects for this agent's tool list."""
        tools = []
        for name in (agent.tools or []):
            t = TOOL_REGISTRY.get(name)
            if t:
                tools.append(t)
            else:
                logger.warning("Agent %s requested unknown tool '%s' — skipping", agent.name, name)
        return tools

    def _trim_history(self, messages: list, agent: Agent) -> list:
        """Apply memory window from memory_config."""
        memory_config = agent.memory_config or {}
        if not memory_config.get("enabled", False):
            # Memory disabled — only pass the very last user message
            user_msgs = [m for m in messages if isinstance(m, HumanMessage)]
            return user_msgs[-1:] if user_msgs else messages[-1:]
        window = int(memory_config.get("window", 10))
        return messages[-window:]

    def _make_node_fn(self, node_id: str, agent: Agent, next_agent_name: str = "Next Agent"):
        """Creates a LangGraph node function for a given agent."""
        llm = self._build_llm(agent)
        agent_tools = self._get_agent_tools(agent)

        # Bind tools to LLM if any
        llm_with_tools = llm.bind_tools(agent_tools) if agent_tools else llm

        async def node_fn(state: AgentState) -> dict:
            run_id = state["run_id"]
            system_msg = SystemMessage(content=agent.system_prompt)
            history = self._trim_history(state["messages"], agent)
            msgs = [system_msg] + history

            # --- Agentic tool-use loop ---
            total_tokens = 0
            output = ""
            loop_msgs = list(msgs)

            while True:
                response = await llm_with_tools.ainvoke(loop_msgs)
                token_usage = getattr(response, "usage_metadata", {}) or {}
                total_tokens += token_usage.get("total_tokens", 0)

                # Check if LLM wants to call tools
                tool_calls = getattr(response, "tool_calls", [])
                if not tool_calls:
                    # Final text response
                    output = response.content
                    break

                # Execute each tool call
                loop_msgs.append(response)
                for tc in tool_calls:
                    t_name = tc["name"]
                    t_args = tc["args"]
                    t_id = tc.get("id", str(uuid.uuid4()))

                    t_obj = TOOL_REGISTRY.get(t_name)
                    if t_obj:
                        try:
                            t_result = t_obj.invoke(t_args)
                        except Exception as e:
                            t_result = f"Tool error: {e}"
                    else:
                        t_result = f"Unknown tool: {t_name}"

                    logger.info("Agent '%s' used tool '%s' → %s…", agent.name, t_name, str(t_result)[:80])

                    # Broadcast tool usage to monitor
                    await ws_manager.broadcast_to_run(run_id, {
                        "event": "tool_call",
                        "run_id": run_id,
                        "data": {
                            "agent": agent.name,
                            "tool": t_name,
                            "args": t_args,
                            "result_preview": str(t_result)[:200],
                        },
                        "timestamp": datetime.utcnow().isoformat(),
                    })

                    loop_msgs.append(ToolMessage(content=str(t_result), tool_call_id=t_id))

            # Persist message to DB
            async with AsyncSessionLocal() as db:
                msg = Message(
                    id=str(uuid.uuid4()),
                    workflow_run_id=run_id,
                    from_agent=agent.name,
                    to_agent=next_agent_name,
                    content=output,
                    message_type="agent_message",
                )
                db.add(msg)
                await db.commit()

            # Broadcast via WebSocket
            await ws_manager.broadcast_to_run(run_id, {
                "event": "agent_message",
                "run_id": run_id,
                "data": {
                    "from_agent": agent.name,
                    "to_agent": next_agent_name,
                    "content": output,
                    "agent_id": node_id,
                    "message_id": msg.id,
                },
                "timestamp": datetime.utcnow().isoformat(),
            })

            return {
                "messages": [AIMessage(content=output)],
                "current_output": output,
                "token_count": state["token_count"] + total_tokens,
            }

        node_fn.__name__ = f"agent_{node_id}"
        return node_fn

    def build_graph(self) -> Any:
        """Parse the React Flow definition and build a LangGraph StateGraph."""
        nodes = self.definition.get("nodes", [])
        edges = self.definition.get("edges", [])

        if not nodes:
            raise ValueError("Workflow has no nodes")

        # Build edge map: source -> list of targets (for next_agent_name lookup)
        edge_targets: dict[str, list[str]] = {}
        for e in edges:
            edge_targets.setdefault(e["source"], []).append(e["target"])

        # node_id -> agent name of first downstream agent
        def next_name(node_id: str) -> str:
            targets = edge_targets.get(node_id, [])
            if not targets:
                return "Output"
            target_node = next((n for n in nodes if n["id"] == targets[0]), None)
            if not target_node:
                return "Output"
            agent = self.agents_map.get(target_node["id"])
            return agent.name if agent else "Output"

        graph = StateGraph(AgentState)

        # Add nodes
        for node in nodes:
            node_id = node["id"]
            agent = self.agents_map.get(node_id)
            if not agent:
                raise ValueError(f"Agent not found for node {node_id}")
            graph.add_node(node_id, self._make_node_fn(node_id, agent, next_name(node_id)))

        # Determine entry point (node with no incoming edges)
        target_ids = {e["target"] for e in edges}
        source_ids = {e["source"] for e in edges}
        entry_nodes = [n["id"] for n in nodes if n["id"] not in target_ids]
        entry = entry_nodes[0] if entry_nodes else nodes[0]["id"]
        graph.set_entry_point(entry)

        # Add edges — support conditional routing via edge label "if:KEYWORD"
        conditional_sources: dict[str, list] = {}
        for edge in edges:
            label = edge.get("label", "") or ""
            if label.startswith("if:"):
                conditional_sources.setdefault(edge["source"], []).append(edge)
            else:
                graph.add_edge(edge["source"], edge["target"])

        for src, cond_edges in conditional_sources.items():
            routing_map: dict[str, str] = {}
            for ce in cond_edges:
                keyword = ce["label"][3:].strip().upper()
                routing_map[keyword] = ce["target"]
            routing_map["__default__"] = END

            def make_router(rmap):
                def router(state: AgentState):
                    output = state.get("current_output", "").upper()
                    for keyword, target in rmap.items():
                        if keyword != "__default__" and keyword in output:
                            return target
                    return rmap["__default__"]
                return router

            graph.add_conditional_edges(src, make_router(routing_map))

        # Terminal nodes -> END
        for node in nodes:
            nid = node["id"]
            if nid not in source_ids and nid not in conditional_sources:
                graph.add_edge(nid, END)

        return graph.compile()

    async def execute(self, input_message: str) -> str:
        """Run the workflow and return the final output."""
        async with AsyncSessionLocal() as db:
            run = await db.get(WorkflowRun, self.run_id)
            if run:
                run.status = "running"
                await db.commit()

        await ws_manager.broadcast_to_run(self.run_id, {
            "event": "run_started",
            "run_id": self.run_id,
            "data": {"input": input_message},
            "timestamp": datetime.utcnow().isoformat(),
        })

        try:
            async with AsyncSessionLocal() as db:
                msg = Message(
                    id=str(uuid.uuid4()),
                    workflow_run_id=self.run_id,
                    from_agent="User",
                    to_agent="Workflow",
                    content=input_message,
                    message_type="user_input",
                )
                db.add(msg)
                await db.commit()

            compiled = self.build_graph()

            initial_state: AgentState = {
                "messages": [HumanMessage(content=input_message)],
                "current_output": "",
                "run_id": self.run_id,
                "token_count": 0,
            }

            final_state = await compiled.ainvoke(initial_state)
            output = final_state.get("current_output", "")
            token_count = final_state.get("token_count", 0)

            async with AsyncSessionLocal() as db:
                run = await db.get(WorkflowRun, self.run_id)
                if run:
                    run.status = "completed"
                    run.output_message = output
                    run.token_count = token_count
                    run.completed_at = datetime.utcnow()
                    await db.commit()

            await ws_manager.broadcast_to_run(self.run_id, {
                "event": "run_completed",
                "run_id": self.run_id,
                "data": {"output": output, "token_count": token_count},
                "timestamp": datetime.utcnow().isoformat(),
            })

            return output

        except Exception as e:
            logger.error("Workflow run %s failed: %s", self.run_id, e)
            async with AsyncSessionLocal() as db:
                run = await db.get(WorkflowRun, self.run_id)
                if run:
                    run.status = "failed"
                    run.error = str(e)
                    run.completed_at = datetime.utcnow()
                    await db.commit()

            await ws_manager.broadcast_to_run(self.run_id, {
                "event": "run_failed",
                "run_id": self.run_id,
                "data": {"error": str(e)},
                "timestamp": datetime.utcnow().isoformat(),
            })
            raise


async def run_workflow_async(
    workflow_run_id: str,
    workflow_definition: dict,
    agents_map: dict[str, Any],
    input_message: str,
) -> str:
    executor = WorkflowExecutor(workflow_run_id, workflow_definition, agents_map)
    return await executor.execute(input_message)
