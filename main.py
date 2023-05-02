import asyncio
import logging
import os

from aiogram import Dispatcher, Bot
from aiogram.dispatcher.webhook import WEBHOOK
from aiogram.types import Message, ChatType
from aiogram.utils.exceptions import BadRequest, BotBlocked
from aiogram.utils.executor import set_webhook
from aiohttp.web_app import Application
from langchain import ConversationChain, PromptTemplate
from langchain.chat_models import ChatOpenAI
from langchain.memory import PostgresChatMessageHistory, ConversationBufferWindowMemory
from openai import InvalidRequestError

from set_webhook_job import delete_webhook, set_webhook_url

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
    template=f'Context: {GPT_PROMPT}\n' + '{history}\n' + 'Question: {input}\n' + 'Answer:'
)


async def start(message: Message):
    try:
        await message.bot.send_message(chat_id=message.chat.id, text="Hi, what is your question?")
    except BotBlocked as e:
        logging.error(f'User {message.chat.id}: {message.chat.username} has blocked the bot')


async def clear_context_with(chat_id: int):
    chat_memory = PostgresChatMessageHistory(
        session_id=str(chat_id),
        connection_string=DATABASE_URL
    )
    chat_memory.clear()


async def clear_context(message: Message):
    try:
        await clear_context_with(message.chat.id)
        await message.bot.send_message(chat_id=message.chat.id, text="History Cleared.\nWhat is your next question?")
    except BotBlocked as e:
        logging.error(f'User {message.chat.id}: {message.chat.username} has blocked the bot')


async def message_handle(message: Message):
    bot = message.bot
    chat = message.chat
    chat_id = chat.id
    try:
        loading_message = await bot.send_message(chat_id, text="Loading...")
        await bot.send_chat_action(chat_id, action='typing')
        await get_chat_gpt_answer(bot, chat_id, message.text)
        await bot.delete_message(chat_id, loading_message.message_id)
    except BotBlocked as e:
        logging.error(f'User {message.chat.id}: {message.chat.username} has blocked the bot')
        bot.close_bot
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


async def get_chat_gpt_answer(bot: Bot, chat_id: int, question: str):
    try:
        response = get_chain_for_user_with(chat_id).predict(input=question)
        await bot.send_message(chat_id, response)
    except InvalidRequestError as e:
        logging.error(e, exc_info=True)
        if e.user_message.__contains__("This model's maximum context length"):
            await clear_context_with(chat_id)
            await get_chat_gpt_answer(bot, chat_id, question)
        else:
            await bot.send_message(chat_id, e.user_message)


def get_chain_for_user_with(telegram_id: int) -> ConversationChain:
    open_ai = ChatOpenAI(
        openai_api_key=OPEN_AI_KEY
    )
    memory = ConversationBufferWindowMemory(
        k=12,
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
    asyncio.ensure_future(set_webhook_url(bot_dispatcher.bot))

    set_webhook(
        dispatcher=bot_dispatcher,
        webhook_path=f'/{WEBHOOK}',
        web_app=app
    )
    logging.info('Application created and webhook was set. Returning app instance...')
    return app


if __name__ == '__main__':
    local_init()
else:
    application = heroku_init()
