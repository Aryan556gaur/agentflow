from datetime import datetime
from typing import Any
import uuid

from sqlalchemy import (
    String, Text, JSON, DateTime, ForeignKey, Integer, func
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.dialects.postgresql import UUID

from config import get_settings


settings = get_settings()

engine = create_async_engine(settings.database_url, echo=settings.debug)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(255), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(100), default="gemini-2.5-flash")
    tools: Mapped[list] = mapped_column(JSON, default=list)
    memory_config: Mapped[dict] = mapped_column(JSON, default=dict)
    guardrails: Mapped[dict] = mapped_column(JSON, default=dict)
    schedule: Mapped[dict] = mapped_column(JSON, default=dict)  # {enabled, cron, timezone, workflow_id}
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    definition: Mapped[dict] = mapped_column(JSON, nullable=False)  # nodes + edges from React Flow
    is_template: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    runs: Mapped[list["WorkflowRun"]] = relationship("WorkflowRun", back_populates="workflow")


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_id: Mapped[str] = mapped_column(String, ForeignKey("workflows.id"))
    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending, running, completed, failed
    input_message: Mapped[str] = mapped_column(Text, default="")
    output_message: Mapped[str] = mapped_column(Text, default="")
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    workflow: Mapped["Workflow"] = relationship("Workflow", back_populates="runs")
    messages: Mapped[list["Message"]] = relationship("Message", back_populates="run")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_run_id: Mapped[str] = mapped_column(String, ForeignKey("workflow_runs.id"))
    from_agent: Mapped[str] = mapped_column(String(255))
    to_agent: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[str] = mapped_column(String(50), default="agent_message")  # user_input, agent_message, final_output
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    run: Mapped["WorkflowRun"] = relationship("WorkflowRun", back_populates="messages")


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
