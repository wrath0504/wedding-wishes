import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile
from databases import Database
from dotenv import load_dotenv

load_dotenv()

# Настройки
TOKEN         = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID") or 0)
UPLOAD_DIR    = os.getenv("UPLOAD_DIR", "uploads")
DATABASE_URL  = os.getenv("DATABASE_URL")

# Логи
logging.basicConfig(level=logging.INFO)

# Инициализируем бота и диспетчер
bot = Bot(token=TOKEN)
dp  = Dispatcher()

# Инициализируем объект для работы с Postgres
db = Database(DATABASE_URL)

async def init_db():
    """Создаём папку uploads и таблицу wishes, если они ещё не созданы."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    await db.connect()
    await db.execute("""
        CREATE TABLE IF NOT EXISTS wishes (
            id           SERIAL PRIMARY KEY,
            photo_path   TEXT   NOT NULL,
            message      TEXT   NOT NULL,
            status       TEXT   NOT NULL DEFAULT 'pending',
            timestamp    TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            random_order DOUBLE PRECISION DEFAULT RANDOM()
        );
    """)

async def save_photo_local(file: types.File) -> str:
    ext = os.path.splitext(file.file_path)[1]
    fn  = f"{int(asyncio.get_event_loop().time()*1000)}{ext}"
    dst = os.path.join(UPLOAD_DIR, fn)
    await bot.download_file(file.file_path, destination=dst)
    return dst

@dp.message(F.text & ~F.photo)
async def handle_text_only(message: types.Message):
    await message.reply(
        "Пожелание принимается только вместе с фото и текстом. "
        "Пожалуйста, отправьте фото вместе с подписью."
    )

@dp.message(Command("start"))
@dp.message(Command("help"))
async def cmd_start(message: types.Message):
    await message.reply(
        "Привет! Отправь фото с подписью — я сохраню пожелание, "
        "а после модерации оно появится на сайте! ❤️"
    )

@dp.message(F.photo)
async def handle_photo(message: types.Message):
    caption = (message.caption or "").strip()
    if not caption:
        return await message.reply(
            "Пожалуйста, подпишите фото вашим пожеланием."
        )

    # Сохраняем файл локально
    photo = message.photo[-1]
    info  = await bot.get_file(photo.file_id)
    try:
        path = await save_photo_local(info)
    except Exception as e:
        logging.exception("Ошибка сохранения фото")
        return await message.reply("Не удалось сохранить фото. Попробуйте позже.")

    # Вставляем запись в Postgres и получаем ID
    row_id = await db.execute(
        """
        INSERT INTO wishes (photo_path, message)
        VALUES (:path, :msg)
        RETURNING id
        """,
        {"path": path, "msg": caption}
    )

    await message.reply("Спасибо! Ваше пожелание отправлено на модерацию 🎉")

    # Кнопки модерации
    kb = types.InlineKeyboardMarkup(
        inline_keyboard=[[
            types.InlineKeyboardButton(
                text="✅ Одобрить", 
                callback_data=f"approve:{row_id}"
            ),
            types.InlineKeyboardButton(
                text="❌ Отклонить", 
                callback_data=f"reject:{row_id}"
            )
        ]]
    )

    # Отправляем админу
    await bot.send_photo(
        chat_id=ADMIN_CHAT_ID,
        photo=FSInputFile(path),
        caption=f"Новое пожелание #{row_id}:\n{caption}",
        reply_markup=kb
    )

@dp.callback_query(F.data.startswith("approve:"))
@dp.callback_query(F.data.startswith("reject:"))
async def process_mod(call: types.CallbackQuery):
    action, id_str = call.data.split(":", 1)
    wish_id = int(id_str)
    status  = "approved" if action=="approve" else "rejected"

    await db.execute(
        "UPDATE wishes SET status=:st WHERE id=:id",
        {"st": status, "id": wish_id}
    )

    await call.message.edit_caption(
        call.message.caption + f"\n\nСтатус: {status}",
        reply_markup=None
    )
    await call.answer(f"Пожелание #{wish_id} {status}")

async def main():
    await init_db()
    # Удаляем старые update, чтобы не было конфликта
    await bot.delete_webhook()
    # Запускаем polling, пропуская старые
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
