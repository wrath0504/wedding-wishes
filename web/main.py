import os
import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# Делаем пакет bot доступным для импорта
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# Загрузка .env из web/.env
load_dotenv(project_root / "web" / ".env")

# Настройки
DATABASE_URL = os.getenv("DATABASE_URL")
UPLOAD_DIR   = os.getenv("UPLOAD_DIR", str(project_root / "uploads"))

# Создаём папку uploads, если её нет
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Импорт бота
from bot.main import bot, dp, init_db as bot_init_db

# FastAPI и Web
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse, HTMLResponse
from databases import Database

app = FastAPI()

# Монтируем статику
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Jinja2-шаблоны
templates = Jinja2Templates(directory=str(project_root / "web" / "templates"))

# Подключение к базе
database = Database(DATABASE_URL)

@app.on_event("startup")
async def on_startup():
    # Подключаемся к базе Postgres и создаём таблицу
    await database.connect()
    await database.execute("""
        CREATE TABLE IF NOT EXISTS wishes (
            id            SERIAL PRIMARY KEY,
            photo_path    TEXT NOT NULL,
            message       TEXT NOT NULL,
            status        TEXT NOT NULL DEFAULT 'approved',
            timestamp     TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            random_order  DOUBLE PRECISION DEFAULT RANDOM()
        );
    """)
    # Инициализация бота (создание SQLite-таблицы, если нужно)
    await bot_init_db()
    # Запуск polling в фоне (игнорируем старые апдейты)
    asyncio.create_task(dp.start_polling(bot, skip_updates=True))

@app.on_event("shutdown")
async def on_shutdown():
    await database.disconnect()

@app.get("/api/wishes")
async def get_wishes():
    rows = await database.fetch_all(
        "SELECT id, photo_path, message "
        "FROM wishes WHERE status='approved' "
        "ORDER BY timestamp DESC, random_order"
    )
    out = []
    for id_, photo_path, message in rows:
        # Правильные отступы внутри цикла
        filename = os.path.basename(photo_path)
        url = f"/uploads/{filename}"
        out.append({
            "id": id_,
            "photo_url": url,
            "message": message
        })
    return JSONResponse(out)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
