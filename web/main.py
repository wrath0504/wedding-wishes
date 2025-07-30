import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

DB_PATH    = os.getenv("DB_PATH", "../wishes.db")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "../uploads")

os.makedirs(UPLOAD_DIR, exist_ok=True)

from bot.main import bot, dp, init_db as bot_init_db

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse, HTMLResponse
import aiosqlite

app = FastAPI()

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

templates = Jinja2Templates(directory="templates")

@app.on_event("startup")
async def on_startup():
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

    await bot_init_db()

    asyncio.create_task(dp.start_polling(bot))


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

    result = []
    for id_, photo_path, message in rows:
        filename = os.path.basename(photo_path)
        result.append({
            "id": id_,
            "photo_url": f"/uploads/{filename}",
            "message": message
        })
    return JSONResponse(result)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
