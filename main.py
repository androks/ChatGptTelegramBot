import logging
import os

from langchain import ConversationChain, PromptTemplate
from langchain.chat_models import ChatOpenAI
from langchain.memory import ConversationSummaryBufferMemory, PostgresChatMessageHistory
from telegram import Update, Bot, Chat
from telegram.constants import ChatAction, ChatType
from telegram.error import BadRequest
from telegram.ext import CommandHandler, MessageHandler, ApplicationBuilder, ContextTypes, filters

TELEGRAM_BOT_KEY = os.environ['TELEGRAM_BOT_KEY']
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Hi, what is your question?")


async def clear_context(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_memory = PostgresChatMessageHistory(
        session_id=str(update.effective_chat.id),
        connection_string=DATABASE_URL
    )
    chat_memory.clear()
    await context.bot.send_message(chat_id=update.effective_chat.id, text="History Cleared.\nWhat is your next "
                                                                          "question?")


async def message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot = context.bot
    chat = update.effective_chat
    chat_id = chat.id
    if not await chat_type_allowed(bot, chat, update.message.text):
        return
    loading_message = await context.bot.send_message(chat_id, text="Loading...")
    await context.bot.send_chat_action(chat_id, action=ChatAction.TYPING)
    try:
        await get_chat_gpt_answer(bot, chat_id, update.message.text, loading_message.message_id)
        await bot.delete_message(chat_id, loading_message.message_id)
    except Exception as e:
        logging.error(e, exc_info=True)
        await context.bot.send_message(chat_id=chat_id, text=str(e))


async def chat_type_allowed(bot: Bot, chat: Chat, message_text: str) -> bool:
    bot_name = (await bot.get_me()).name
    logging.info(message_text)
    logging.info(chat.type)
    return chat.type == ChatType.PRIVATE or \
        ((chat.type == ChatType.GROUP or chat.type == ChatType.SUPERGROUP) and message_text.__contains__(bot_name))


async def update_message_safe(bot: Bot, text: str, chat_id: int, message_id: int):
    try:
        await bot.edit_message_text(text, chat_id, message_id)
    except BadRequest as e:
        if not e.message.startswith("Message is not modified"):
            raise e


async def get_chat_gpt_answer(bot: Bot, chat_id: int, question: str, message_id: int) -> str:
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


if __name__ == '__main__':
    application = ApplicationBuilder().token(TELEGRAM_BOT_KEY).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('clear_history', clear_context))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message))

    application.run_webhook(
        listen='0.0.0.0',
        port=int(os.environ.get('PORT', 5000)),
        url_path=TELEGRAM_BOT_KEY,
        webhook_url=HEROKU_APP_NAME + TELEGRAM_BOT_KEY,
    )
