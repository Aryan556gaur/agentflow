from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from models.database import WorkflowRun, Message, Workflow, Agent, get_db
from models.schemas import WorkflowRunResponse, MessageResponse
from workers.ws_manager import manager

router = APIRouter(prefix="/monitor", tags=["monitor"])


# ── WebSocket ──────────────────────────────────────────────────────────────────

@router.websocket("/ws")
async def websocket_all(websocket: WebSocket):
    """Global monitor — receives all workflow events."""
    await manager.connect(websocket, "all")
    try:
        while True:
            await websocket.receive_text()  # keep connection alive
    except WebSocketDisconnect:
        manager.disconnect(websocket, "all")


@router.websocket("/ws/{run_id}")
async def websocket_run(websocket: WebSocket, run_id: str):
    """Per-run monitor."""
    await manager.connect(websocket, run_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, run_id)


# ── Dashboard Stats ────────────────────────────────────────────────────────────

@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    total_agents = await db.scalar(select(func.count(Agent.id)))
    total_workflows = await db.scalar(select(func.count(Workflow.id)))
    total_runs = await db.scalar(select(func.count(WorkflowRun.id)))
    total_messages = await db.scalar(select(func.count(Message.id)))
    total_tokens = await db.scalar(select(func.sum(WorkflowRun.token_count))) or 0

    # Runs by status
    runs_by_status = {}
    for status in ["pending", "running", "completed", "failed"]:
        count = await db.scalar(
            select(func.count(WorkflowRun.id)).where(WorkflowRun.status == status)
        )
        runs_by_status[status] = count or 0

    return {
        "total_agents": total_agents or 0,
        "total_workflows": total_workflows or 0,
        "total_runs": total_runs or 0,
        "total_messages": total_messages or 0,
        "total_tokens": total_tokens,
        "runs_by_status": runs_by_status,
    }


@router.get("/runs/recent", response_model=list[WorkflowRunResponse])
async def recent_runs(limit: int = 20, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(WorkflowRun)
        .options(selectinload(WorkflowRun.messages))
        .order_by(WorkflowRun.started_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/messages/recent", response_model=list[MessageResponse])
async def recent_messages(limit: int = 50, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Message)
        .order_by(Message.timestamp.desc())
        .limit(limit)
    )
    return result.scalars().all()
