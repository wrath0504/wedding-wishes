import os
import io
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from sqlalchemy import Column, Integer, String, DateTime, Table, MetaData, LargeBinary, create_engine
from databases import Database

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))
DATABASE_URL = os.getenv("DATABASE_URL")

# Initialize bot, dispatcher, and database
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
database = Database(DATABASE_URL)
metadata = MetaData()

# Define wishes table with image_data as bytea
wishes = Table(
    "wishes",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("text", String),
    Column("status", String, default="pending"),
    Column("image_data", LargeBinary, nullable=False),
    Column("created_at", DateTime, default=datetime.utcnow),
)

@dp.message_handler(content_types=['photo'])
async def handle_photo(message: types.Message):
    # Download photo into memory
    photo = message.photo[-1]
    buf = io.BytesIO()
    await photo.download(destination=buf)
    data = buf.getvalue()

    # Insert into database
    query = wishes.insert().values(
        text=message.caption or "",
        status="pending",
        image_data=data,
        created_at=datetime.utcnow(),
    )
    wish_id = await database.execute(query)

    # Send for moderation
    approve_btn = types.InlineKeyboardButton("✅ Одобрить", callback_data=f"approve:{wish_id}")
    reject_btn = types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject:{wish_id}")
    keyboard = types.InlineKeyboardMarkup().add(approve_btn, reject_btn)
    await bot.send_message(
        ADMIN_CHAT_ID,
        f"Новая запись #{wish_id}: {message.caption or ''}",
        reply_markup=keyboard
    )

@dp.callback_query_handler(lambda c: c.data and c.data.startswith(('approve:','reject:')))
async def process_callback(callback_query: types.CallbackQuery):
    action, wish_id = callback_query.data.split(":")
    new_status = 'approved' if action == 'approve' else 'rejected'
    query = wishes.update().where(wishes.c.id == int(wish_id)).values(status=new_status)
    await database.execute(query)
    await bot.answer_callback_query(callback_query.id, text=f"Статус изменён на {new_status}")
    await bot.edit_message_reply_markup(
        ADMIN_CHAT_ID,
        callback_query.message.message_id,
        reply_markup=None
    )

@dp.on_startup
async def on_startup():
    await database.connect()
    # Ensure table exists
    engine = create_engine(DATABASE_URL)
    metadata.create_all(engine)

@dp.on_shutdown
async def on_shutdown():
    await database.disconnect()

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
