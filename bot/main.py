import os
import logging
import asyncio
import io
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile
from databases import Database
from dotenv import load_dotenv

load_dotenv()

# Настройки
TOKEN         = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID") or 0)
DATABASE_URL  = os.getenv("DATABASE_URL")

# Логи
logging.basicConfig(level=logging.INFO)

# Инициализируем бота и диспетчер
bot = Bot(token=TOKEN)
dp  = Dispatcher(bot)
db  = Database(DATABASE_URL)

async def init_db():
    """Создаём таблицу wishes для хранения байтов фото."""
    await db.connect()
    await db.execute("""
        CREATE TABLE IF NOT EXISTS wishes (
            id            SERIAL PRIMARY KEY,
            image_data    BYTEA   NOT NULL,
            message       TEXT    NOT NULL,
            status        TEXT    NOT NULL DEFAULT 'pending',
            timestamp     TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            random_order  DOUBLE PRECISION DEFAULT RANDOM()
        );
    """)

@dp.message(F.text & ~F.photo)
async def handle_text_only(message: types.Message):
    await message.reply(
        "Пожелание принимается только вместе с фото и текстом. "
        "Пожалуйста, отправьте фото вместе с подписью."
    )

@dp.message(Command("start"))
@dp.message(Command("help"))
async def cmd_start_help(message: types.Message):
    await message.reply(
        "Привет! Отправь мне фото с подписью-пожеланием, "
        "и я передам его администратору на модерацию."
    )

@dp.message(F.photo)
async def handle_photo(message: types.Message):
    caption = message.caption or ""
    if not caption:
        return await message.reply("Пожалуйста, подпишите фото вашим пожеланием.")

    try:
        # Получаем файл и скачиваем в память
        photo = message.photo[-1]
        file_info = await bot.get_file(photo.file_id)
        buf = io.BytesIO()
        await bot.download_file(file_info.file_path, buf)
        data = buf.getvalue()

        # Сохраняем в БД
        row_id = await db.execute(
            """
            INSERT INTO wishes (image_data, message)
            VALUES (:data, :msg)
            RETURNING id
            """,
            {"data": data, "msg": caption}
        )
    except Exception:
        logging.exception("Ошибка при сохранении фото в БД")
        return await message.reply("Не удалось сохранить фото. Попробуйте позже.")

    await message.reply("Спасибо! Ваше пожелание отправлено на модерацию 🎉")

    # Кнопки модерации
    kb = types.InlineKeyboardMarkup(
        inline_keyboard=[[
            types.InlineKeyboardButton("✅ Одобрить", callback_data=f"approve:{row_id}"),
            types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject:{row_id}")
        ]]
    )

    # Отправляем админу фото из памяти
    ext = os.path.splitext(file_info.file_path)[1]
    fsfile = FSInputFile(io.BytesIO(data), filename=f"{row_id}{ext}")
    await bot.send_photo(
        chat_id=ADMIN_CHAT_ID,
        photo=fsfile,
        caption=f"Новое пожелание #{row_id}:
{caption}",
        reply_markup=kb
    )

@dp.callback_query(F.data.startswith("approve:"))
@dp.callback_query(F.data.startswith("reject:"))
async def process_mod(call: types.CallbackQuery):
    action, id_str = call.data.split(":", 1)
    wish_id = int(id_str)
    status  = "approved" if action == "approve" else "rejected"

    await db.execute(
        "UPDATE wishes SET status=:st WHERE id=:id",
        {"st": status, "id": wish_id}
    )

    await call.message.edit_caption(
        call.message.caption + f"

Статус: {status}",
        reply_markup=None
    )
    await call.answer(f"Пожелание #{wish_id} {status}")

async def main():
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())