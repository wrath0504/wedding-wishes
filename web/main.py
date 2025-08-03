import os
import io
import sys
import logging
import threading
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse
from sqlalchemy import Column, Integer, String, DateTime, Table, MetaData, LargeBinary, create_engine
from databases import Database

# Extend Python path to import bot package
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

# Now import telegram bot dispatcher
from bot.main import dp

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variable
DATABASE_URL = os.getenv("DATABASE_URL")

database = Database(DATABASE_URL)
metadata = MetaData()

# Define wishes table matching database schema
wishes = Table(
    "wishes",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("message", String),
    Column("status", String, default="approved"),
    Column("timestamp", DateTime, default=datetime.utcnow),
    Column("image_data", LargeBinary, nullable=False),
)

# Ensure table exists
engine = create_engine(DATABASE_URL)
metadata.create_all(engine)

app = FastAPI()

@app.on_event("startup")
async def startup():
    logger.info("API startup: connecting to database")
    await database.connect()
    # Start Telegram bot polling in background thread
    def start_bot():
        from aiogram import executor
        executor.start_polling(dp, skip_updates=True)
    threading.Thread(target=start_bot, daemon=True).start()
    logger.info("Telegram bot polling started in background")

@app.on_event("shutdown")
async def shutdown():
    logger.info("API shutdown: disconnecting database")
    await database.disconnect()

@app.get("/api/wishes")
async def get_wishes():
    rows = await database.fetch_all(
        wishes.select()
              .where(wishes.c.status == "approved")
              .order_by(wishes.c.timestamp.desc())
    )
    return [
        {
            "id": r.id,
            "message": r.message,
            "image_url": f"/api/wishes/{r.id}/image",
            "timestamp": r.timestamp.isoformat(),
        }
        for r in rows
    ]

@app.get("/api/wishes/{wish_id}/image")
async def wish_image(wish_id: int):
    r = await database.fetch_one(wishes.select().where(wishes.c.id == wish_id))
    if not r:
        raise HTTPException(status_code=404, detail="Wish not found")
    return StreamingResponse(io.BytesIO(r.image_data), media_type="image/jpeg")

@app.get("/")
async def read_index():
    try:
        with open("templates/index.html", "r", encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        logger.error("index.html not found in templates folder")
        raise HTTPException(status_code=500, detail="Template not found")
    return HTMLResponse(html)