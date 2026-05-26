"""
Telegram Bot integration for AgentFlow.
Listens for messages and routes them through a designated workflow.
"""

import asyncio
import logging
import uuid
from typing import Optional

from sqlalchemy import select

from models.database import Agent, Workflow, WorkflowRun, AsyncSessionLocal
from runtime.executor import run_workflow_async
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class TelegramChannel:
    """Handles Telegram bot events and routes to AgentFlow."""

    def __init__(self, default_workflow_id: Optional[str] = None):
        self.default_workflow_id = default_workflow_id
        self.app = None

    async def setup(self):
        if not settings.telegram_bot_token:
            logger.warning("No TELEGRAM_BOT_TOKEN set — Telegram integration disabled")
            return

        try:
            from telegram import Update
            from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

            app = Application.builder().token(settings.telegram_bot_token).build()

            async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
                await update.message.reply_text(
                    "🤖 AgentFlow Bot ready!\n"
                    "Send any message to trigger the active workflow.\n"
                    "Use /workflows to list available workflows."
                )

            async def workflows_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
                async with AsyncSessionLocal() as db:
                    result = await db.execute(select(Workflow))
                    workflows = result.scalars().all()
                if not workflows:
                    await update.message.reply_text("No workflows found. Create one in the web UI first.")
                    return
                text = "📋 *Available Workflows:*\n\n"
                for wf in workflows:
                    text += f"• `{wf.id[:8]}...` — {wf.name}\n"
                await update.message.reply_text(text, parse_mode="Markdown")

            async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
                user_msg = update.message.text
                chat_id = update.effective_chat.id

                await update.message.reply_text("⚙️ Processing your message through the workflow...")

                # Find the workflow to use
                workflow_id = self.default_workflow_id
                if not workflow_id:
                    async with AsyncSessionLocal() as db:
                        result = await db.execute(
                            select(Workflow).order_by(Workflow.created_at.desc()).limit(1)
                        )
                        wf = result.scalar_one_or_none()
                        if wf:
                            workflow_id = wf.id

                if not workflow_id:
                    await update.message.reply_text("❌ No workflows configured. Create one in the web UI.")
                    return

                try:
                    async with AsyncSessionLocal() as db:
                        workflow = await db.get(Workflow, workflow_id)
                        if not workflow:
                            await update.message.reply_text("❌ Workflow not found.")
                            return

                        definition = workflow.definition
                        nodes = definition.get("nodes", [])
                        agent_ids = [n["data"]["agent_id"] for n in nodes]

                        from sqlalchemy import select as sel
                        result = await db.execute(select(Agent).where(Agent.id.in_(agent_ids)))
                        agents = {a.id: a for a in result.scalars().all()}
                        agents_map = {
                            n["id"]: agents[n["data"]["agent_id"]]
                            for n in nodes
                            if n["data"]["agent_id"] in agents
                        }

                    run_id = str(uuid.uuid4())
                    async with AsyncSessionLocal() as db:
                        run = WorkflowRun(
                            id=run_id,
                            workflow_id=workflow_id,
                            status="pending",
                            input_message=user_msg,
                        )
                        db.add(run)
                        await db.commit()

                    output = await run_workflow_async(run_id, definition, agents_map, user_msg)
                    await update.message.reply_text(f"✅ *Result:*\n\n{output}", parse_mode="Markdown")

                except Exception as e:
                    logger.error(f"Telegram workflow error: {e}")
                    await update.message.reply_text(f"❌ Error: {str(e)[:200]}")

            app.add_handler(CommandHandler("start", start_cmd))
            app.add_handler(CommandHandler("workflows", workflows_cmd))
            app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

            self.app = app
            logger.info("Telegram bot configured successfully")

        except ImportError:
            logger.error("python-telegram-bot not installed")
        except Exception as e:
            logger.error(f"Telegram setup error: {e}")

    async def run_polling(self):
        if self.app:
            logger.info("Starting Telegram bot polling...")
            await self.app.initialize()
            await self.app.start()
            await self.app.updater.start_polling()

    async def stop(self):
        if self.app:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()


# Singleton
telegram_channel = TelegramChannel()
