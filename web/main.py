import os
from dotenv import load_dotenv

# 1. Загрузка переменных окружения
load_dotenv()

# 2. Пути к БД и папке с картинками
# Если wishes.db лежит в корне репозитория рядом с папками bot/ и web/,
# то относительно web/ это "../wishes.db"
DB_PATH    = os.getenv("DB_PATH", "../wishes.db")
# Аналогично uploads в корне проекта
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "../uploads")

# 3. Гарантированно создаём папку для статики
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 4. Импорты FastAPI после os.makedirs (чтобы UPLOAD_DIR уже гарантированно был)
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse, HTMLResponse
import aiosqlite

app = FastAPI()

# 5. Монтируем каталог с картинками на маршрут /uploads
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# 6. Настраиваем Jinja2-шаблоны (папка web/templates)
templates = Jinja2Templates(directory="templates")

# 7. При старте создаём таблицу, если её нет
@app.on_event("startup")
async def ensure_tables():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS wishes (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                photo_path    TEXT    NOT NULL,
                message       TEXT    NOT NULL,
                timestamp     DATETIME DEFAULT CURRENT_TIMESTAMP,
                random_order  REAL,
                status        TEXT    DEFAULT 'approved'
            );
        """)
        await db.commit()

# 8. API для выдачи списка одобренных пожеланий
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

# 9. Главная страница с рендером шаблона
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
