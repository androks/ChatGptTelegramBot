# This is a sample Python script.
import os

import openai as openai

import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import CommandHandler, MessageHandler, ApplicationBuilder, ContextTypes, filters

TELEGRAM_BOT_KEY = os.environ['TELEGRAM_BOT_KEY']
OPEN_AI_KEY = os.environ['OPENAI_KEY']
GPT_PROMPT = os.environ['GPT_PROMPT']

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

openai.api_key = OPEN_AI_KEY


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Hi, what is your question?")


async def message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    loading_message = await context.bot.send_message(chat_id, text="Loading...")
    await context.bot.send_chat_action(chat_id, action=ChatAction.TYPING)
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=get_chat_gpt_answer(chat_id, update.message.text)
        )
    except Exception as e:
        logging.error(e)
        await context.bot.send_message(chat_id=chat_id, text=str(e))
    finally:
        await context.bot.delete_message(chat_id=chat_id, message_id=loading_message.id)


def get_chat_gpt_answer(telegram_id: int, question: str) -> str:
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": GPT_PROMPT},
            {"role": "system", "content": f'user_id: {telegram_id}'},
            {"role": "user", "content": question},
        ]
    )
    return response.choices[0].message.content


if __name__ == '__main__':
    application = ApplicationBuilder().token(TELEGRAM_BOT_KEY).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message))

    application.run_polling()
