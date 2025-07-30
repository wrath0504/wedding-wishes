import os
import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# ——————————————————————————————————————————————
# 0. Позволяем импортировать пакет bot, пусть web/ знает о корне проекта
#    (предполагаем структуру wedding/{bot,web,uploads,wishes.db})
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
# ——————————————————————————————————————————————

# 1. Загрузить .env из web/.env (и, при необходимости, из корня проекта)
load_dotenv(project_root / "web" / ".env")

# 2. Пути к БД и uploads (относительно корня)
DB_PATH    = os.getenv("DB_PATH", str(project_root / "wishes.db"))
UPLOAD_DIR = os.getenv("UPLOAD_DIR", str(project_root / "uploads"))

# 3. Создать папку uploads, если её нет
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 4. Импорт бота и диспетчера
from bot.main import bot, dp, init_db as bot_init_db

# 5. Импорты FastAPI
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse, HTMLResponse
import aiosqlite

# 6. Инициализация FastAPI
app = FastAPI()

# 7. Монтируем статику: корневая папка uploads на URL /uploads
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# 8. Jinja2-шаблоны (директория web/templates)
templates = Jinja2Templates(directory=str(project_root / "web" / "templates"))

# 9. При старте создаём таблицы для веба и для бота, затем стартуем бота
@app.on_event("startup")
async def on_startup():
    # 9.1 Таблица wishes для сайта
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS wishes (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                photo_path    TEXT    NOT NULL,
                message       TEXT    NOT NULL,
                status        TEXT    NOT NULL DEFAULT 'approved',
                timestamp     DATETIME DEFAULT CURRENT_TIMESTAMP,
                random_order  REAL    DEFAULT (RANDOM())
            );
        """)
        await db.commit()

    # 9.2 Инициализация бота (таблица pending, папка uploads)
    await bot_init_db()

    # 9.3 Запуск бота в фоне
    asyncio.create_task(dp.start_polling(bot))

# 10. API: возвращаем одобренные пожелания
@app.get("/api/wishes")
async def get_wishes():
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, photo_path, message "
            "FROM wishes "
            "WHERE status = 'approved' "
            "ORDER BY timestamp DESC, random_order"
        )
        rows = await cursor.fetchall()

    out = []
    for id_, photo_path, message in rows:
        fname = os.path.basename(photo_path)
        out.append({
            "id": id_,
            "photo_url": f"/uploads/{fname}",
            "message": message
        })
    return JSONResponse(out)

# 11. Главная страница
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
