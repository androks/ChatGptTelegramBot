import asyncio
import logging
import os

from aiogram import Dispatcher, Bot
from aiogram.types import Message, ChatType
from aiogram.utils.exceptions import BadRequest
from aiogram.utils.executor import set_webhook
from aiohttp.web_app import Application
from langchain import ConversationChain, PromptTemplate
from langchain.chat_models import ChatOpenAI
from langchain.memory import ConversationSummaryBufferMemory, PostgresChatMessageHistory

from cron import run_cron_jobs
from set_webhook_job import delete_webhook

TELEGRAM_BOT_KEY = os.environ['TELEGRAM_BOT_KEY']
TELEGRAM_BOT_NAME = os.environ['TELEGRAM_BOT_NAME']
OPEN_AI_KEY = os.environ['OPENAI_KEY']
GPT_PROMPT = os.environ['GPT_PROMPT']
HEROKU_APP_NAME = os.environ['HEROKU_APP_NAME']
DATABASE_URL = os.environ['DATABASE_URL']

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

prompt_template = PromptTemplate(
    input_variables=["history", "input"],
    template=f'Context: {GPT_PROMPT}\n' + '<history start>{history}<history end>\n' + 'Question: {input}\n' + 'Answer:'
)


async def start(message: Message):
    await message.bot.send_message(chat_id=message.chat.id, text="Hi, what is your question?")


async def clear_context(message: Message):
    chat_memory = PostgresChatMessageHistory(
        session_id=str(message.chat.id),
        connection_string=DATABASE_URL
    )
    chat_memory.clear()
    await message.bot.send_message(chat_id=message.chat.id, text="History Cleared.\nWhat is your next question?")


async def message_handle(message: Message):
    bot = message.bot
    chat = message.chat
    chat_id = chat.id
    loading_message = await bot.send_message(chat_id, text="Loading...")
    await bot.send_chat_action(chat_id, action='typing')
    try:
        await get_chat_gpt_answer(bot, chat_id, message.text)
        await bot.delete_message(chat_id, loading_message.message_id)
    except Exception as e:
        logging.error(e, exc_info=True)
        await bot.send_message(chat_id=chat_id, text=str(e))


def chat_type_allowed(message: Message) -> bool:
    type = message.chat.type
    text = message.text
    return type == ChatType.PRIVATE or \
        ((type == ChatType.GROUP or type == ChatType.SUPERGROUP) and text.__contains__(TELEGRAM_BOT_NAME))


async def update_message_safe(bot: Bot, text: str, chat_id: int, message_id: int):
    try:
        await bot.edit_message_text(text, chat_id, message_id)
    except BadRequest as e:
        if not e.text.startswith("Message is not modified"):
            raise e


async def get_chat_gpt_answer(bot: Bot, chat_id: int, question: str) -> str:
    response = get_chain_for_user_with(chat_id).predict(input=question)
    await bot.send_message(chat_id, response)
    return response


def get_chain_for_user_with(telegram_id: int) -> ConversationChain:
    open_ai = ChatOpenAI(
        openai_api_key=OPEN_AI_KEY
    )
    memory = ConversationSummaryBufferMemory(
        llm=open_ai,
        chat_memory=PostgresChatMessageHistory(
            session_id=str(telegram_id),
            connection_string=DATABASE_URL
        )
    )
    conversation = ConversationChain(
        llm=open_ai,
        prompt=prompt_template,
        verbose=False,
        memory=memory
    )
    return conversation


def init_app() -> Application:
    # Init application and set config
    app = Application()

    return app


def init_bot_dispatcher(bot: Bot) -> Dispatcher:
    dp = Dispatcher(bot)
    dp.register_message_handler(start, commands=['start'])
    dp.register_message_handler(clear_context, commands=['clear_history'])
    dp.register_message_handler(message_handle, lambda message: chat_type_allowed(message))
    return dp


def init_bot() -> Dispatcher:
    bot = Bot(token=TELEGRAM_BOT_KEY)
    bot_dispatcher = init_bot_dispatcher(bot)
    return bot_dispatcher


def local_init():
    # Init telegram bot
    bot_dispatcher = init_bot()
    asyncio.run(delete_webhook(bot_dispatcher.bot))
    asyncio.run(bot_dispatcher.start_polling())


def heroku_init() -> Application:
    # Init application
    app = init_app()

    # Init telegram bot
    bot_dispatcher = init_bot()
    run_cron_jobs(bot_dispatcher.bot)

    set_webhook(
        dispatcher=bot_dispatcher,
        webhook_path='/webhook',
        web_app=app
    )
    logging.info('Application created and webhook was set. Returning app instance...')
    return app


if __name__ == '__main__':
    local_init()
else:
    application = heroku_init()
