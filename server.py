"""
Village Marketplace - Backend Server
FastAPI + Socket.io + Redis
Port: 8000
"""

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import redis.asyncio as aioredis
import socketio
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ─────────────────────────────────────────
# Redis Setup
# ─────────────────────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

redis_client: Optional[aioredis.Redis] = None

async def get_redis():
    global redis_client
    if redis_client is None:
        redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
    return redis_client


# ─────────────────────────────────────────
# Socket.io Server
# ─────────────────────────────────────────
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",   # Allow all origins in dev
    logger=True,
    engineio_logger=False,
)

@sio.event
async def connect(sid, environ):
    print(f"[WS] Client connected: {sid}")

@sio.event
async def disconnect(sid):
    print(f"[WS] Client disconnected: {sid}")

@sio.event
async def negotiate(sid, data):
    """Buyer sends a negotiation offer — broadcast to all farmers."""
    print(f"[WS] Negotiation from {sid}: {data}")
    await sio.emit("negotiation:offer", data, skip_sid=sid)


# ─────────────────────────────────────────
# FastAPI App
# ─────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: connect Redis
    global redis_client
    redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
    print("[DB] Redis connected")
    yield
    # Shutdown: close Redis
    await redis_client.aclose()
    print("[DB] Redis closed")


app = FastAPI(
    title="Village Marketplace API",
    version="1.0.0",
    description="Backend for Farmer PWA & Buyer Web App",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────
# Pydantic Schemas
# ─────────────────────────────────────────
class PriceUpdate(BaseModel):
    crop_name: str
    price: float

class Listing(BaseModel):
    farmer_name: str
    village: str
    crop_name: str
    quantity_kg: float
    price_per_kg: float
    phone: Optional[str] = ""
    transport_available: bool = False
    transport_details: Optional[str] = ""
    address: Optional[str] = ""

class NegotiationOffer(BaseModel):
    listing_id: str
    buyer_name: str
    offered_price: float
    quantity_kg: float


# ─────────────────────────────────────────
# Routes
# ─────────────────────────────────────────

@app.get("/")
async def root():
    return {"message": "Village Marketplace API is running ✅", "docs": "/docs"}


# ── Price Updates (called by scraper microservice) ──────────────────────────

@app.post("/price-updates")
async def receive_price_update(data: PriceUpdate):
    """
    Scraper microservice POSTs here every minute.
    We save to Redis and broadcast to all WebSocket clients.
    """
    r = await get_redis()

    # Persist latest price in Redis
    price_key = f"price:{data.crop_name}"
    price_record = {
        "crop_name": data.crop_name,
        "price": data.price,
        "updated_at": datetime.utcnow().isoformat(),
    }
    await r.set(price_key, json.dumps(price_record))
    # Also keep a time-series (last 100 entries)
    await r.lpush(f"price_history:{data.crop_name}", json.dumps(price_record))
    await r.ltrim(f"price_history:{data.crop_name}", 0, 99)

    # Broadcast to all connected WebSocket clients
    await sio.emit("price:update", {"crop_name": data.crop_name, "price": data.price})

    print(f"[PRICE] {data.crop_name}: ₹{data.price}/kg  → broadcasted")
    return {"status": "ok", "broadcasted": True}


@app.get("/prices")
async def get_all_prices():
    """Get latest cached prices for all crops from Redis."""
    r = await get_redis()
    crops = ["tomato", "onion", "potato", "wheat", "rice", "brinjal", "carrot"]
    prices = {}
    for crop in crops:
        raw = await r.get(f"price:{crop}")
        if raw:
            prices[crop] = json.loads(raw)
    return {"prices": prices}


@app.get("/prices/{crop_name}/history")
async def get_price_history(crop_name: str):
    """Get last 20 price updates for a crop."""
    r = await get_redis()
    raw_list = await r.lrange(f"price_history:{crop_name}", 0, 19)
    history = [json.loads(item) for item in raw_list]
    return {"crop_name": crop_name, "history": history}


# ── Listings ────────────────────────────────────────────────────────────────

@app.post("/listings")
async def create_listing(listing: Listing):
    """Farmer posts a new crop listing."""
    r = await get_redis()

    listing_id = f"listing:{datetime.utcnow().timestamp()}"
    listing_data = {
        **listing.model_dump(),
        "id": listing_id,
        "status": "active",
        "created_at": datetime.utcnow().isoformat(),
    }

    await r.set(listing_id, json.dumps(listing_data))
    await r.lpush("listings:active", json.dumps(listing_data))
    await r.ltrim("listings:active", 0, 499)  # keep latest 500

    # Notify all buyers via WebSocket
    await sio.emit("listing:new", listing_data)

    print(f"[LISTING] New listing: {listing.crop_name} by {listing.farmer_name}")
    return {"status": "created", "listing_id": listing_id, "data": listing_data}


@app.get("/listings")
async def get_listings(crop: Optional[str] = None):
    """Get active listings, optionally filtered by crop."""
    r = await get_redis()
    raw_list = await r.lrange("listings:active", 0, 49)
    listings = [json.loads(item) for item in raw_list]

    if crop:
        listings = [l for l in listings if l.get("crop_name", "").lower() == crop.lower()]

    return {"listings": listings, "count": len(listings)}


# ── Negotiation ─────────────────────────────────────────────────────────────

@app.post("/negotiate")
async def send_negotiation(offer: NegotiationOffer):
    """Buyer sends a negotiation offer. Saved + broadcasted."""
    r = await get_redis()

    offer_data = {
        **offer.model_dump(),
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
    }

    offer_key = f"offer:{offer.listing_id}:{datetime.utcnow().timestamp()}"
    offer_data["offer_key"] = offer_key  # CRITICAL: include so farmer can respond
    await r.set(offer_key, json.dumps(offer_data))

    # Broadcast to farmer (offer_key included)
    await sio.emit("negotiation:offer", offer_data)

    return {"status": "offer_sent", "data": offer_data}


class OfferResponse(BaseModel):
    offer_key: str
    action: str  # "accepted" or "declined"
    farmer_note: Optional[str] = ""


@app.post("/negotiate/respond")
async def respond_to_offer(response: OfferResponse):
    """Farmer accepts or declines a buyer's offer."""
    r = await get_redis()

    raw = await r.get(response.offer_key)
    if not raw:
        raise HTTPException(status_code=404, detail="Offer not found")

    offer_data = json.loads(raw)
    offer_data["status"] = response.action
    offer_data["farmer_note"] = response.farmer_note
    offer_data["responded_at"] = datetime.utcnow().isoformat()

    await r.set(response.offer_key, json.dumps(offer_data))

    # Notify buyer via WebSocket
    await sio.emit("offer:response", offer_data)

    print(f"[OFFER] {response.action.upper()}: {response.offer_key}")
    return {"status": response.action, "data": offer_data}


# ─────────────────────────────────────────
# Mount Socket.io → ASGI
# ─────────────────────────────────────────
# This wraps FastAPI with Socket.io so both HTTP and WS run on port 8000
socket_app = socketio.ASGIApp(sio, app)


# ─────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(
        "server:socket_app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
