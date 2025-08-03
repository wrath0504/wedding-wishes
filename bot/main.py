import os
import io
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from sqlalchemy import Column, Integer, String, DateTime, Table, MetaData, LargeBinary, create_engine
from databases import Database

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))
DATABASE_URL = os.getenv("DATABASE_URL")

# Initialize bot, dispatcher, and database
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
database = Database(DATABASE_URL)
metadata = MetaData()

# Define wishes table matching database schema
wishes = Table(
    "wishes",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("message", String),                  # renamed from text
    Column("status", String, default="pending"),
    Column("timestamp", DateTime, default=datetime.utcnow),  # renamed from created_at
    Column("image_data", LargeBinary, nullable=False),
)

@dp.message_handler(content_types=types.ContentType.PHOTO)
async def handle_photo(message: types.Message):
    logger.info("Received photo from user_id=%s", message.from_user.id)
    try:
        # Download photo into memory buffer
        buf = io.BytesIO()
        await message.photo[-1].download(destination_file=buf)
        data = buf.getvalue()

        # Insert into database
        query = wishes.insert().values(
            message=message.caption or "",
            status="pending",
            image_data=data,
            timestamp=datetime.utcnow(),
        )
        wish_id = await database.execute(query)
        logger.info("Saved wish_id=%s to database", wish_id)

        # Send moderation request to admin
        keyboard = types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("✅ Одобрить", callback_data=f"approve:{wish_id}"),
            types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject:{wish_id}")
        )
        await bot.send_message(
            ADMIN_CHAT_ID,
            f"Новая запись №{wish_id}: {message.caption or '<без текста>'}",
            reply_markup=keyboard
        )
        logger.info("Sent moderation request for wish_id=%s to admin", wish_id)

    except Exception as e:
        logger.error("Error processing photo: %s", e, exc_info=True)
        await message.reply("Произошла ошибка при обработке вашего фото. Попробуйте ещё раз позже.")

@dp.callback_query_handler(lambda c: c.data and c.data.startswith(("approve:", "reject:")))
async def process_callback(callback_query: types.CallbackQuery):
    action, wish_id = callback_query.data.split(":")
    new_status = 'approved' if action == 'approve' else 'rejected'
    await database.execute(
        wishes.update().where(wishes.c.id == int(wish_id)).values(status=new_status)
    )
    await bot.answer_callback_query(callback_query.id, text=f"Статус изменён на {new_status}")
    await bot.edit_message_reply_markup(
        ADMIN_CHAT_ID,
        callback_query.message.message_id,
        reply_markup=None
    )
    logger.info("Updated status for wish_id=%s to %s", wish_id, new_status)

@dp.on_startup
async def on_startup():
    logger.info("Bot startup: connecting to database")
    await database.connect()
    engine = create_engine(DATABASE_URL)
    metadata.create_all(engine)  # ensures table exists
    logger.info("Database schema ensured for bot")

@dp.on_shutdown
async def on_shutdown():
    logger.info("Bot shutdown: disconnecting database")
    await database.disconnect()

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)