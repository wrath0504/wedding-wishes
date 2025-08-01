import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile
import aiosqlite
from dotenv import load_dotenv

load_dotenv()

TOKEN          = os.getenv('BOT_TOKEN')
DB_PATH        = os.getenv('DB_PATH', 'wishes.db')
UPLOAD_DIR     = os.getenv('UPLOAD_DIR', 'uploads')
ADMIN_CHAT_ID  = int(os.getenv('ADMIN_CHAT_ID', ''))

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
dp  = Dispatcher()


async def init_db():
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS wishes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                photo_path TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                random_order REAL DEFAULT (RANDOM())
            );
        ''')
        await db.commit()


async def save_photo_local(file: types.File) -> str:
    ext = os.path.splitext(file.file_path)[1]
    fn  = f"{int(asyncio.get_event_loop().time()*1000)}{ext}"
    path = os.path.join(UPLOAD_DIR, fn)
    await bot.download_file(file.file_path, destination=path)
    return path


@dp.message(F.text & ~F.photo)
async def handle_text_only(message: types.Message):
    await message.reply(
        "Пожелание принимается только вместе с фото и текстом. "
        "Пожалуйста, отправьте фото вместе с подписью к нему."
    )


@dp.message(Command("start"))
@dp.message(Command("help"))
async def cmd_start(message: types.Message):
    await message.reply(
        "Привет! Отправь мне фото вместе с подписью — вашим тёплым пожеланием. "
        "Я сохраню его и после модерации оно появится на сайте! ❤️"
    )


@dp.message(F.photo)
async def handle_photo(message: types.Message):
    caption = (message.caption or "").strip()
    if not caption:
        return await message.reply(
            "Пожелание принимается только вместе с фото и текстом. "
            "Пожалуйста, подпишите фото вашим пожеланием."
        )

    photo = message.photo[-1]
    info  = await bot.get_file(photo.file_id)

    try:
        path = await save_photo_local(info)
    except Exception as e:
        logging.error(f"Ошибка сохранения фото: {e}")
        return await message.reply("Не удалось сохранить фото. Попробуйте позже.")

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            'INSERT INTO wishes (photo_path, message) VALUES (?, ?)',
            (path, caption)
        )
        await db.commit()
        wish_id = cur.lastrowid

    await message.reply("Спасибо! Ваше пожелание отправлено на модерацию 🎉")

    kb = types.InlineKeyboardMarkup(
        inline_keyboard=[[
            types.InlineKeyboardButton("✅ Одобрить", callback_data=f"approve:{wish_id}"),
            types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject:{wish_id}")
        ]]
    )
    await bot.send_photo(
        chat_id=ADMIN_CHAT_ID,
        photo=FSInputFile(path),
        caption=f"Новое пожелание #{wish_id}:\n{caption}",
        reply_markup=kb
    )


@dp.callback_query(F.data.startswith("approve:"))
@dp.callback_query(F.data.startswith("reject:"))
async def process_moderation(call: types.CallbackQuery):
    action, id_str = call.data.split(":", 1)
    wish_id = int(id_str)
    status  = "approved" if action == "approve" else "rejected"

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'UPDATE wishes SET status = ? WHERE id = ?',
            (status, wish_id)
        )
        await db.commit()

    await call.message.edit_caption(
        call.message.caption + f"\n\nСтатус: {status}",
        reply_markup=None
    )
    await call.answer(
        f"Пожелание #{wish_id} {'одобрено' if status=='approved' else 'отклонено'}"
    )


async def main():
    await init_db()
    await bot.delete_webhook()
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
