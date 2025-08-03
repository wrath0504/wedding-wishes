import os
import io
import logging
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse
from sqlalchemy import Column, Integer, String, DateTime, Table, MetaData, LargeBinary, create_engine
from databases import Database

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variables
DATABASE_URL = os.getenv("DATABASE_URL")

database = Database(DATABASE_URL)
metadata = MetaData()

# Define wishes table matching database schema
wishes = Table(
    "wishes",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("message", String),                  # matches DB column
    Column("status", String, default="approved"),
    Column("timestamp", DateTime, default=datetime.utcnow),  # matches DB column
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
    result = []
    for r in rows:
        result.append({
            "id": r.id,
            "message": r.message,
            "image_url": f"/api/wishes/{r.id}/image",
            "timestamp": r.timestamp.isoformat(),
        })
    return result

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
