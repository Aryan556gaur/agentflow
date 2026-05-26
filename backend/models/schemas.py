from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field


# ── Agent Schemas ──────────────────────────────────────────────────────────────

class AgentCreate(BaseModel):
    name: str
    role: str
    system_prompt: str
    model: str = "gemini-2.5-flash"
    tools: list[str] = []
    memory_config: dict[str, Any] = {}
    guardrails: dict[str, Any] = {}
    schedule: dict[str, Any] = {}  # {enabled, cron, timezone, workflow_id}


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    system_prompt: Optional[str] = None
    model: Optional[str] = None
    tools: Optional[list[str]] = None
    memory_config: Optional[dict[str, Any]] = None
    guardrails: Optional[dict[str, Any]] = None


class AgentResponse(BaseModel):
    id: str
    name: str
    role: str
    system_prompt: str
    model: str
    tools: list[str]
    memory_config: dict[str, Any]
    guardrails: dict[str, Any]
    schedule: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── Workflow Schemas ────────────────────────────────────────────────────────────

class NodeData(BaseModel):
    agent_id: str
    label: str


class FlowNode(BaseModel):
    id: str
    type: str = "agentNode"
    position: dict[str, float]
    data: NodeData


class FlowEdge(BaseModel):
    id: str
    source: str
    target: str
    label: Optional[str] = None


class WorkflowDefinition(BaseModel):
    nodes: list[FlowNode]
    edges: list[FlowEdge]


class WorkflowCreate(BaseModel):
    name: str
    description: str = ""
    definition: dict[str, Any]  # raw React Flow graph
    is_template: bool = False


class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    definition: Optional[dict[str, Any]] = None
    is_template: Optional[bool] = None


class WorkflowResponse(BaseModel):
    id: str
    name: str
    description: str
    definition: dict[str, Any]
    is_template: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── Run & Message Schemas ───────────────────────────────────────────────────────

class RunWorkflowRequest(BaseModel):
    input_message: str
    source: str = "api"  # api, telegram


class MessageResponse(BaseModel):
    id: str
    workflow_run_id: str
    from_agent: str
    to_agent: str
    content: str
    message_type: str
    timestamp: datetime

    class Config:
        from_attributes = True


class WorkflowRunResponse(BaseModel):
    id: str
    workflow_id: str
    status: str
    input_message: str
    output_message: str
    token_count: int
    started_at: datetime
    completed_at: Optional[datetime]
    error: Optional[str]
    messages: list[MessageResponse] = []

    class Config:
        from_attributes = True


# ── WebSocket Event ─────────────────────────────────────────────────────────────

class WSEvent(BaseModel):
    event: str  # agent_message, run_started, run_completed, run_failed
    run_id: str
    data: dict[str, Any]
    timestamp: str
