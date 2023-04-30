import asyncio
import logging
import os

from aiogram import Bot
from aiogram.dispatcher.webhook import WEBHOOK

SET_WEBHOOK_JOB_DELAY = 60 * 5


async def delete_webhook(bot: Bot):
    await bot.delete_webhook(drop_pending_updates=False)


async def set_webhook_url(bot: Bot):
    try:
        webhook = f'{os.environ["HEROKU_APP_NAME"]}{WEBHOOK}'
        await bot.set_webhook(webhook, max_connections=50)
        logging.info(f'Webhook was set to {webhook}')
    except Exception as e:
        logging.info(e, exc_info=True)


async def set_telegram_webhook_job(bot: Bot):
    while True:
        try:
            await asyncio.sleep(SET_WEBHOOK_JOB_DELAY)
            webhook_info = await bot.get_webhook_info()
            if not webhook_info or not webhook_info.url:
                logging.info('Webhook is not set. Setting')
                await set_webhook_url(bot)
            elif webhook_info.url is not f'{os.environ["HEROKU_APP_NAME"]}{WEBHOOK}':
                await bot.delete_webhook(drop_pending_updates=False)
                await set_webhook_url(bot)
            else:
                logging.info('Webhook is already set')
        except Exception as e:
            logging.critical("Exception while trying to check webhook status")
            logging.critical(e, exc_info=True)
