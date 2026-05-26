import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from models.database import init_db
from api.agents import router as agents_router
from api.workflows import router as workflows_router
from api.monitor import router as monitor_router
from channels.telegram import telegram_channel
from workers.scheduler import start_scheduler, stop_scheduler, sync_schedules

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AgentFlow",
    description="Multi-agent workflow orchestration platform",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agents_router, prefix="/api")
app.include_router(workflows_router, prefix="/api")
app.include_router(monitor_router, prefix="/api")


@app.on_event("startup")
async def startup():
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database ready.")

    # Start cron scheduler
    start_scheduler()
    await sync_schedules()
    logger.info("Scheduler ready.")

    # Start Telegram bot in background if token provided
    await telegram_channel.setup()
    if telegram_channel.app:
        asyncio.create_task(telegram_channel.run_polling())
        logger.info("Telegram bot started.")


@app.on_event("shutdown")
async def shutdown():
    await stop_scheduler()
    await telegram_channel.stop()


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "AgentFlow"}


@app.get("/")
async def root():
    return {"message": "AgentFlow API — see /docs for Swagger UI"}
