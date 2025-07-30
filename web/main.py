import os
from dotenv import load_dotenv

# Загружаем переменные окружения из .env
load_dotenv()
import aiosqlite
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

# Настройки
from dotenv import load_dotenv
load_dotenv()

# Настройки (из .env):
DB_PATH = os.getenv('DB_PATH', 'wishes.db')
UPLOAD_DIR = os.getenv('UPLOAD_DIR', 'uploads')
UPLOAD_DIR = os.getenv('UPLOAD_DIR', 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)
app = FastAPI()

# Подключаем статику для фото
# Монтируем статические файлы из директории UPLOAD_DIR
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Шаблоны для HTML
templates = Jinja2Templates(directory="templates")

# API: получить список одобренных пожеланий
@app.get("/api/wishes")
async def get_wishes():
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, photo_path, message FROM wishes WHERE status = 'approved' ORDER BY timestamp DESC, random_order"
        )
        rows = await cursor.fetchall()
    # Формируем JSON с URL фото
    wishes = []
    for id_, photo_path, message in rows:
        # относительный URL к статике
        url = f"/uploads/{os.path.basename(photo_path)}"
        wishes.append({
            "id": id_,
            "photo_url": url,
            "message": message
        })
    return JSONResponse(wishes)

# Веб-страница: отображение пожеланий
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
