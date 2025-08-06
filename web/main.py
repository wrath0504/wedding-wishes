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
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            photo_path    TEXT NOT NULL,
            message       TEXT NOT NULL,
            status        TEXT NOT NULL DEFAULT 'approved',
            timestamp     TEXT DEFAULT CURRENT_TIMESTAMP,
            random_order  REAL DEFAULT (abs(random()) / 9223372036854775807.0)
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
    # Получаем все одобренные
    rows = await database.fetch_all(
        """
        SELECT id, photo_path, message 
        FROM wishes 
        WHERE status = 'approved' 
        ORDER BY timestamp DESC, random_order
        """
    )

    result = []
    for row in rows:
        # row["photo_path"] — это полный путь на диске, например "/data/uploads/1691023456789.jpg"
        filename = os.path.basename(row["photo_path"])  # "1691023456789.jpg"
        result.append({
            "id":        row["id"],
            "photo_url": f"/uploads/{filename}",
            "message":   row["message"]
        })

    return JSONResponse(result)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
    
@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/debug/wishes")
async def debug_wishes():
    rows = await database.fetch_all("SELECT * FROM wishes")
    return {"count": len(rows), "items": [dict(row) for row in rows]}
