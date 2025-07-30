# telegram_wedding_bot/main.py
# Telegram-бот для приёма фото и пожеланий на свадьбу с локальным хранением и обязательной парой фото+текст
# Требуется: aiogram v3, aiosqlite, python-dotenv

import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile
import aiosqlite
from dotenv import load_dotenv

# Загрузка переменных окружения из .env
load_dotenv()

# Настройки
TOKEN = os.getenv('BOT_TOKEN')  # токен Telegram-бота
DB_PATH = os.getenv('DB_PATH', 'wishes.db')
UPLOAD_DIR = os.getenv('UPLOAD_DIR', 'uploads')
ADMIN_CHAT_ID = int(os.getenv('ADMIN_CHAT_ID', ''))  # chat_id администратора для модерации

# Логи
logging.basicConfig(level=logging.INFO)

# Создаём бот и диспетчер
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Инициализация базы данных и папки для фото
async def init_db():
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            '''
            CREATE TABLE IF NOT EXISTS wishes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                photo_path TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                random_order REAL DEFAULT (RANDOM())
            )
            '''
        )
        await db.commit()

# Сохранение фото локально
async def save_photo_local(file: types.File) -> str:
    ext = os.path.splitext(file.file_path)[1]
    filename = f"{int(asyncio.get_event_loop().time()*1000)}{ext}"
    local_path = os.path.join(UPLOAD_DIR, filename)
    await bot.download_file(file.file_path, destination=local_path)
    return local_path

# Хендлер для текстовых сообщений без фото
@dp.message(F.text & ~F.photo)
async def handle_text_only(message: types.Message):
    await message.reply(
        "Пожелание принимается только вместе с фото и текстом. "
        "Пожалуйста, отправьте фото вместе с подписью к нему."
    )

# Обработчики команд /start и /help
@dp.message(Command("start"))
@dp.message(Command("help"))
async def cmd_start(message: types.Message):
    await message.reply(
        "Привет! Отправь мне фото вместе с подписью — вашим тёплым пожеланием. "
        "Я сохраню его и после модерации оно появится на сайте! ❤️"
    )

# Обработка сообщений с фото
@dp.message(F.photo)
async def handle_photo(message: types.Message):
    caption = message.caption.strip() if message.caption else None
    if not caption:
        await message.reply(
            "Пожелание принимается только вместе с фото и текстом. "
            "Пожалуйста, подпишите фото вашим пожеланием."
        )
        return

    photo = message.photo[-1]
    file_info = await bot.get_file(photo.file_id)

    try:
        photo_path = await save_photo_local(file_info)
    except Exception as e:
        logging.error(f"Ошибка сохранения фото: {e}")
        await message.reply("Не удалось сохранить фото. Попробуйте позже.")
        return

    # Сохраняем запись в базе
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            'INSERT INTO wishes (photo_path, message) VALUES (?, ?)',
            (photo_path, caption)
        )
        await db.commit()
        wish_id = cur.lastrowid

    await message.reply("Спасибо! Ваше пожелание отправлено на модерацию 🎉")

    # Формируем клавиатуру модерации
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve:{wish_id}"),
            types.InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject:{wish_id}")
        ]
    ])

    # Отправляем фото администратору через FSInputFile
    photo_input = FSInputFile(photo_path)
    await bot.send_photo(
        chat_id=ADMIN_CHAT_ID,
        photo=photo_input,
        caption=f"Новое пожелание #{wish_id}:\n{caption}",
        reply_markup=keyboard
    )

# Обработка колбэков для модерации
@dp.callback_query(F.data.startswith("approve:"))
@dp.callback_query(F.data.startswith("reject:"))
async def process_moderation(call: types.CallbackQuery):
    action, id_str = call.data.split(':', 1)
    wish_id = int(id_str)
    status = 'approved' if action == 'approve' else 'rejected'

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE wishes SET status = ? WHERE id = ?', (status, wish_id))
        await db.commit()

    # Обновляем сообщение модератору
    await call.message.edit_caption(
        call.message.caption + f"\n\nСтатус: {status}",
        reply_markup=None
    )
    await call.answer(
        f"Пожелание #{wish_id} {'одобрено' if status=='approved' else 'отклонено'}"
    )

# Точка входа
async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())