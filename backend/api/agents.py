from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid

from models.database import Agent, get_db
from models.schemas import AgentCreate, AgentUpdate, AgentResponse
from workers.scheduler import sync_schedules

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("/", response_model=AgentResponse, status_code=201)
async def create_agent(payload: AgentCreate, db: AsyncSession = Depends(get_db)):
    agent = Agent(
        id=str(uuid.uuid4()),
        **payload.model_dump(),
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    await sync_schedules()
    return agent


@router.get("/", response_model=list[AgentResponse])
async def list_agents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Agent).order_by(Agent.created_at.desc()))
    return result.scalars().all()


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(agent_id: str, payload: AgentUpdate, db: AsyncSession = Depends(get_db)):
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(agent, field, value)
    await db.commit()
    await db.refresh(agent)
    await sync_schedules()
    return agent


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    await db.delete(agent)
    await db.commit()
