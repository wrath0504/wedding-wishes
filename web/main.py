import os
import io
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse
from sqlalchemy import Column, Integer, String, DateTime, Table, MetaData, LargeBinary, create_engine
from databases import Database
from datetime import datetime

# Environment variable
DATABASE_URL = os.getenv("DATABASE_URL")

database = Database(DATABASE_URL)
metadata = MetaData()

# Define wishes table with image_data
wishes = Table(
    "wishes",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("text", String),
    Column("status", String, default="approved"),
    Column("image_data", LargeBinary, nullable=False),
    Column("created_at", DateTime, default=datetime.utcnow),
)

# Create table if not exists
engine = create_engine(DATABASE_URL)
metadata.create_all(engine)

app = FastAPI()

@app.on_event("startup")
async def startup():
    await database.connect()

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

@app.get("/api/wishes")
async def get_wishes():
    rows = await database.fetch_all(
        wishes.select().where(wishes.c.status == "approved").order_by(wishes.c.created_at.desc())
    )
    result = []
    for r in rows:
        result.append({
            "id": r.id,
            "text": r.text,
            "image_url": f"/api/wishes/{r.id}/image",
            "created_at": r.created_at.isoformat(),
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
    with open("templates/index.html", "r", encoding="utf-8") as f:
        html = f.read()
    return HTMLResponse(html)
