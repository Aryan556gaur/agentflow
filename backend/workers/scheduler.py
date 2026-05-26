"""
Cron-based agent scheduler.

Reads agents with schedule.enabled=True and schedule.cron set,
and fires their linked workflow at the specified interval using
APScheduler (lightweight, no Celery needed).

Schedule config shape (stored in agent.schedule JSON):
  {
    "enabled": true,
    "cron": "0 9 * * 1-5",   // standard 5-field cron
    "timezone": "UTC",
    "workflow_id": "<uuid>",
    "trigger_message": "Run your scheduled task."
  }
"""

import logging
import uuid
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from models.database import Agent, Workflow, WorkflowRun, AsyncSessionLocal
from runtime.executor import run_workflow_async

logger = logging.getLogger(__name__)

_scheduler = AsyncIOScheduler()
_registered_jobs: dict[str, str] = {}  # agent_id -> job_id


async def _fire_workflow(agent_id: str, workflow_id: str, trigger_message: str):
    """Called by APScheduler when a cron fires."""
    try:
        async with AsyncSessionLocal() as db:
            workflow = await db.get(Workflow, workflow_id)
            if not workflow:
                logger.warning("Scheduled workflow %s not found", workflow_id)
                return

            definition = workflow.definition
            nodes = definition.get("nodes", [])
            agent_ids = [n["data"]["agent_id"] for n in nodes]

            result = await db.execute(select(Agent).where(Agent.id.in_(agent_ids)))
            agents = {a.id: a for a in result.scalars().all()}
            agents_map = {
                n["id"]: agents[n["data"]["agent_id"]]
                for n in nodes
                if n["data"]["agent_id"] in agents
            }

            run_id = str(uuid.uuid4())
            run = WorkflowRun(
                id=run_id,
                workflow_id=workflow_id,
                status="pending",
                input_message=trigger_message,
            )
            db.add(run)
            await db.commit()

        logger.info("Scheduler firing workflow %s (agent %s)", workflow_id, agent_id)
        await run_workflow_async(run_id, definition, agents_map, trigger_message)

    except Exception as e:
        logger.error("Scheduled run failed for agent %s: %s", agent_id, e)


async def sync_schedules():
    """Load all agents and register/update their cron jobs."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Agent))
        agents = result.scalars().all()

    current_agent_ids = set()

    for agent in agents:
        sched = agent.schedule or {}
        if not sched.get("enabled") or not sched.get("cron") or not sched.get("workflow_id"):
            continue

        current_agent_ids.add(agent.id)
        cron_expr = sched["cron"]
        workflow_id = sched["workflow_id"]
        timezone = sched.get("timezone", "UTC")
        trigger_message = sched.get("trigger_message", "Scheduled run triggered.")

        existing_job_id = _registered_jobs.get(agent.id)
        if existing_job_id and _scheduler.get_job(existing_job_id):
            # Remove and re-add in case cron changed
            _scheduler.remove_job(existing_job_id)

        parts = cron_expr.strip().split()
        if len(parts) != 5:
            logger.warning("Agent %s has invalid cron '%s'", agent.name, cron_expr)
            continue

        minute, hour, day, month, day_of_week = parts
        trigger = CronTrigger(
            minute=minute, hour=hour, day=day, month=month,
            day_of_week=day_of_week, timezone=timezone
        )

        job = _scheduler.add_job(
            _fire_workflow,
            trigger=trigger,
            args=[agent.id, workflow_id, trigger_message],
            id=f"agent_{agent.id}",
            replace_existing=True,
            misfire_grace_time=60,
        )
        _registered_jobs[agent.id] = job.id
        logger.info("Scheduled agent '%s' with cron '%s'", agent.name, cron_expr)

    # Remove jobs for agents that no longer have schedules
    for agent_id in list(_registered_jobs.keys()):
        if agent_id not in current_agent_ids:
            job_id = _registered_jobs.pop(agent_id)
            if _scheduler.get_job(job_id):
                _scheduler.remove_job(job_id)


def start_scheduler():
    if not _scheduler.running:
        _scheduler.start()
        logger.info("APScheduler started")


async def stop_scheduler():
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
