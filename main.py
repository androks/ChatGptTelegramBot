# This is a sample Python script.
import os

import openai as openai

import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import CommandHandler, MessageHandler, ApplicationBuilder, ContextTypes, filters

TELEGRAM_BOT_KEY = os.environ['TELEGRAM_BOT_KEY']
OPEN_AI_KEY = os.environ['OPENAI_KEY']

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

openai.api_key = OPEN_AI_KEY


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Hi, what is your question?")


async def message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await context.bot.send_chat_action(chat_id, action=ChatAction.TYPING)
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=get_chat_gpt_answer(chat_id, update.message.text)
        )
    except Exception as e:
        logging.error(e)
        await context.bot.send_message(chat_id=chat_id, text=str(e))


def get_chat_gpt_answer(telegram_id: int, question: str) -> str:
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "Welcome to the Buddhist University chat! Our conversation will be focused "
                                          "on Buddhism and related topics. Our goal is to provide you with additional "
                                          "information and clarification on topics you're interested in or didn't "
                                          "fully understand from the course. Please keep in mind that our responses "
                                          "will be based solely on the teachings found at https://studybuddhism.com/. "
                                          "If we cannot find an answer on this website, we will let you know that we "
                                          "don't have an answer for your question. Feel free to ask any questions and "
                                          "we'll do our best to provide helpful and accurate responses."},
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
