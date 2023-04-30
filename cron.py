import asyncio
import logging

from aiogram import Bot

from set_webhook_job import set_telegram_webhook_job


def run_cron_jobs(bot: Bot):
    try:
        asyncio.ensure_future(set_telegram_webhook_job(bot))
    except Exception as e:
        logging.error(e, exc_info=True)
