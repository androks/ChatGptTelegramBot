import logging
import os

from langchain import ConversationChain, PromptTemplate
from langchain.callbacks import CallbackManager
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


class Callback(CallbackManager):
    whole_text = ''
    last_message_text = ''

    def __init__(self, bot: Bot, chat_id: int, message_id: int):
        super().__init__([])
        self.bot = bot
        self.chat_id = chat_id
        self.message_id = message_id

    # def on_llm_end(self, response: LLMResult, verbose: bool = False, **kwargs: Any) -> None:
    #     asyncio.get_event_loop().run_until_complete(self.update_message(force=True))

    # def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
    #     if token:
    #         self.whole_text += token
    #         nest_asyncio.apply()
    #         asyncio.get_event_loop().run_until_complete(self.update_message())
    #
    # async def update_message(self, force: bool = False):
    #     if force or (self.whole_text and len(self.whole_text) - len(self.last_message_text) > 100):
    #         self.last_message_text = self.whole_text
    #         await update_message_safe(self.bot, self.last_message_text, self.chat_id, self.message_id)


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
    loading_message = await context.bot.send_message(
        chat_id,
        text="Loading...",
        reply_to_message_id=update.message.message_id
        if chat.type == ChatType.GROUP or chat.type == ChatType.SUPERGROUP else None
    )
    await context.bot.send_chat_action(chat_id, action=ChatAction.TYPING)
    try:
        callback = Callback(bot, chat_id, loading_message.message_id)
        await get_chat_gpt_answer(bot, chat_id, update.message.text, loading_message.message_id, callback)
    except Exception as e:
        logging.error(e, exc_info=True)
        await context.bot.send_message(chat_id=chat_id, text=str(e))


async def chat_type_allowed(bot: Bot, chat: Chat, message_text: str) -> bool:
    bot_name = (await bot.get_me()).name
    logging.info(message_text)
    logging.info(bot_name)
    logging.info(chat.type)
    logging.info(str(message_text.__contains__(bot_name)))
    return chat.type == ChatType.PRIVATE or \
        ((chat.type == ChatType.GROUP or chat.type == ChatType.SUPERGROUP) and message_text.__contains__(bot_name))


async def update_message_safe(bot: Bot, text: str, chat_id: int, message_id: int):
    try:
        await bot.edit_message_text(text, chat_id, message_id)
    except BadRequest as e:
        if not e.message.startswith("Message is not modified"):
            raise e


async def get_chat_gpt_answer(bot: Bot, chat_id: int, question: str, message_id: int, callback: Callback) -> str:
    response = get_chain_for_user_with(chat_id, callback).predict(input=question)
    await update_message_safe(bot, response, chat_id, message_id)
    return response


def get_chain_for_user_with(telegram_id: int, callback: Callback) -> ConversationChain:
    open_ai = ChatOpenAI(
        openai_api_key=OPEN_AI_KEY,
        streaming=True,
        verbose=True,
        callback_manager=callback
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
