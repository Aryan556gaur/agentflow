import asyncio
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from models.database import Agent, Workflow, WorkflowRun, Message, get_db
from models.schemas import (
    WorkflowCreate, WorkflowUpdate, WorkflowResponse,
    RunWorkflowRequest, WorkflowRunResponse, MessageResponse
)
from runtime.executor import run_workflow_async

router = APIRouter(prefix="/workflows", tags=["workflows"])


# ── Pre-built templates ────────────────────────────────────────────────────────

TEMPLATES = [
    {
        "name": "Research + Summary",
        "description": "Agent A searches the web → Agent B summarizes and replies",
        "is_template": True,
        "definition": {
            "nodes": [],
            "edges": [],
            "template_hint": "research_summary",
        },
        "agents": [
            {
                "name": "Researcher",
                "role": "Research Specialist",
                "system_prompt": "You are a research specialist. Given a topic or question, gather comprehensive information and present it in a structured way with key facts, context, and relevant details. Be thorough and accurate.",
                "model": "gemini-2.5-flash",
                "tools": ["web_search"],
                "memory_config": {"enabled": True, "window": 10},
                "guardrails": {"max_tokens": 1000},
                "schedule": {},
            },
            {
                "name": "Summarizer",
                "role": "Content Summarizer",
                "system_prompt": "You are a content summarizer. Take research findings and produce a clear, concise summary suitable for a general audience. Structure your response with: 1) Key Takeaway, 2) Main Points, 3) Conclusion.",
                "model": "gemini-2.5-flash",
                "tools": [],
                "memory_config": {"enabled": True, "window": 5},
                "guardrails": {"max_tokens": 500},
                "schedule": {},
            },
        ],
    },
    {
        "name": "Triage + Responder",
        "description": "Agent A classifies message → routes to FAQ or Escalation agent",
        "is_template": True,
        "definition": {
            "nodes": [],
            "edges": [],
            "template_hint": "triage_responder",
        },
        "agents": [
            {
                "name": "Triage Agent",
                "role": "Message Classifier",
                "system_prompt": "You are a triage agent. Classify incoming messages into one of: [FAQ, ESCALATION, GENERAL]. Respond ONLY with the classification label and a one-sentence reason. Format: LABEL: reason",
                "model": "gemini-2.5-flash",
                "tools": [],
                "memory_config": {"enabled": False},
                "guardrails": {"max_tokens": 100},
                "schedule": {},
            },
            {
                "name": "FAQ Agent",
                "role": "FAQ Responder",
                "system_prompt": "You are a helpful FAQ agent. Answer common questions clearly and concisely. If you don't know the answer, say so honestly and suggest where the user might find help.",
                "model": "gemini-2.5-flash",
                "tools": [],
                "memory_config": {"enabled": True, "window": 5},
                "guardrails": {"max_tokens": 400},
                "schedule": {},
            },
            {
                "name": "Escalation Agent",
                "role": "Escalation Handler",
                "system_prompt": "You are an escalation agent handling complex or sensitive requests. Acknowledge the issue empathetically, gather key details, and provide a clear escalation path. Always end with next steps for the user.",
                "model": "gemini-2.5-flash",
                "tools": [],
                "memory_config": {"enabled": True, "window": 10},
                "guardrails": {"max_tokens": 600},
                "schedule": {},
            },
        ],
    },
]


@router.get("/templates")
async def get_templates():
    # Return without agents field for clean response
    return [{k: v for k, v in t.items() if k != "agents"} for t in TEMPLATES]


@router.post("/templates/{template_name}/instantiate", status_code=201)
async def instantiate_template(template_name: str, db: AsyncSession = Depends(get_db)):
    """Create agents + workflow from a pre-built template."""
    tmpl = next((t for t in TEMPLATES if t["name"] == template_name), None)
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")

    # Create agents
    created_agents = []
    for a in tmpl.get("agents", []):
        agent = Agent(id=str(uuid.uuid4()), **a)
        db.add(agent)
        created_agents.append(agent)
    await db.flush()  # get IDs

    # Build nodes + edges from agents
    nodes = []
    edges = []
    x = 100
    for i, agent in enumerate(created_agents):
        nodes.append({
            "id": f"node_{agent.id}",
            "type": "agentNode",
            "position": {"x": x + i * 260, "y": 200},
            "data": {"agent_id": agent.id, "label": agent.name, "role": agent.role, "model": agent.model},
        })
        if i > 0:
            edges.append({
                "id": f"edge_{i}",
                "source": f"node_{created_agents[i-1].id}",
                "target": f"node_{agent.id}",
                "animated": True,
            })

    wf = Workflow(
        id=str(uuid.uuid4()),
        name=tmpl["name"],
        description=tmpl["description"],
        definition={"nodes": nodes, "edges": edges},
        is_template=False,
    )
    db.add(wf)
    await db.commit()
    await db.refresh(wf)
    return wf


# ── CRUD ───────────────────────────────────────────────────────────────────────

@router.post("/", response_model=WorkflowResponse, status_code=201)
async def create_workflow(payload: WorkflowCreate, db: AsyncSession = Depends(get_db)):
    wf = Workflow(id=str(uuid.uuid4()), **payload.model_dump())
    db.add(wf)
    await db.commit()
    await db.refresh(wf)
    return wf


@router.get("/", response_model=list[WorkflowResponse])
async def list_workflows(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Workflow).order_by(Workflow.created_at.desc()))
    return result.scalars().all()


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow_id: str, db: AsyncSession = Depends(get_db)):
    wf = await db.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf


@router.put("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(workflow_id: str, payload: WorkflowUpdate, db: AsyncSession = Depends(get_db)):
    wf = await db.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(wf, field, value)
    await db.commit()
    await db.refresh(wf)
    return wf


@router.delete("/{workflow_id}", status_code=204)
async def delete_workflow(workflow_id: str, db: AsyncSession = Depends(get_db)):
    wf = await db.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    await db.delete(wf)
    await db.commit()


# ── Execution ──────────────────────────────────────────────────────────────────

@router.post("/{workflow_id}/run", response_model=WorkflowRunResponse)
async def run_workflow(
    workflow_id: str,
    payload: RunWorkflowRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    wf = await db.get(Workflow, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    definition = wf.definition
    nodes = definition.get("nodes", [])
    if not nodes:
        raise HTTPException(status_code=400, detail="Workflow has no nodes")

    # Collect all agent IDs from nodes
    agent_ids = [n["data"]["agent_id"] for n in nodes]
    result = await db.execute(select(Agent).where(Agent.id.in_(agent_ids)))
    agents = {a.id: a for a in result.scalars().all()}

    # Build the node_id -> agent map
    agents_map = {n["id"]: agents[n["data"]["agent_id"]] for n in nodes if n["data"]["agent_id"] in agents}

    # Create run record
    run_id = str(uuid.uuid4())
    run = WorkflowRun(
        id=run_id,
        workflow_id=workflow_id,
        status="pending",
        input_message=payload.input_message,
    )
    db.add(run)
    await db.commit()

    # Run async in background
    background_tasks.add_task(
        run_workflow_async,
        run_id,
        definition,
        agents_map,
        payload.input_message,
    )

    result = await db.execute(
        select(WorkflowRun)
        .where(WorkflowRun.id == run_id)
        .options(selectinload(WorkflowRun.messages))
    )
    return result.scalar_one()


# ── Run history ────────────────────────────────────────────────────────────────

@router.get("/{workflow_id}/runs", response_model=list[WorkflowRunResponse])
async def list_runs(workflow_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(WorkflowRun)
        .where(WorkflowRun.workflow_id == workflow_id)
        .options(selectinload(WorkflowRun.messages))
        .order_by(WorkflowRun.started_at.desc())
    )
    return result.scalars().all()


@router.get("/runs/{run_id}", response_model=WorkflowRunResponse)
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(WorkflowRun)
        .where(WorkflowRun.id == run_id)
        .options(selectinload(WorkflowRun.messages))
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/runs/{run_id}/messages", response_model=list[MessageResponse])
async def get_run_messages(run_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Message)
        .where(Message.workflow_run_id == run_id)
        .order_by(Message.timestamp.asc())
    )
    return result.scalars().all()
