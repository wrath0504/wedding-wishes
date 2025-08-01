import os, sys, asyncio
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).resolve().parent.parent
load_dotenv(project_root/"web"/".env")

DATABASE_URL = os.getenv("DATABASE_URL")
UPLOAD_DIR    = os.getenv("UPLOAD_DIR", str(project_root/"uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)

sys.path.insert(0, str(project_root))
from bot.main import bot, dp, init_db as bot_init_db

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse, HTMLResponse
from databases import Database

app = FastAPI()
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
templates = Jinja2Templates(directory=str(project_root/"web"/"templates"))

database = Database(DATABASE_URL)

@app.on_event("startup")
async def on_startup():
    await database.connect()
    await database.execute("""
    CREATE TABLE IF NOT EXISTS wishes (
      id SERIAL PRIMARY KEY,
      photo_path TEXT NOT NULL,
      message    TEXT NOT NULL,
      status     TEXT NOT NULL DEFAULT 'approved',
      timestamp  TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
      random_order DOUBLE PRECISION DEFAULT RANDOM()
    );
    """)
    await bot_init_db()
    asyncio.create_task(dp.start_polling(bot))

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
    for row in rows:
        fname = os.path.basename(row["photo_path"])
        out.append({
          "id": row["id"],
          "photo_url": f"/uploads/{fname}",
          "message": row["message"]
        })
    return JSONResponse(out)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
