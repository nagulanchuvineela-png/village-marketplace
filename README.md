# Village Marketplace — Full Stack Setup Guide

## Project Structure

```
village_marketplace/
├── backend/
│   ├── server.py          ← FastAPI + Socket.io (THE MISSING PIECE ✅)
│   └── requirements.txt
├── scraper/
│   ├── main.py            ← Price scraper microservice (upgraded ✅)
│   └── requirements.txt
├── farmer_app/
│   └── index.html         ← React PWA for farmers (upgraded ✅)
├── buyer_app/
│   └── index.html         ← Vue web app for buyers (upgraded ✅)
└── README.md
```

---

## Prerequisites

Install these before starting:

| Tool | Download |
|------|----------|
| Python 3.10+ | https://python.org |
| Redis | https://redis.io/docs/install/ |
| VS Code | https://code.visualstudio.com |
| Live Server (VS Code ext) | Search in Extensions panel |

---

## Step 1 — Install Redis (Windows)

### Option A: Using Docker (easiest)
```bash
docker run -d -p 6379:6379 redis
```

### Option B: Download Redis for Windows
Download from: https://github.com/microsoftarchive/redis/releases
Run: `redis-server.exe`

---

## Step 2 — Install Backend Dependencies

Open VS Code terminal, navigate to `backend/` folder:

```bash
cd backend
pip install -r requirements.txt
```

---

## Step 3 — Install Scraper Dependencies

```bash
cd scraper
pip install -r requirements.txt
```

---

## Step 4 — Run Everything (3 Terminals)

### Terminal 1 — Start Redis
```bash
redis-server
```

### Terminal 2 — Start Backend (FastAPI + Socket.io)
```bash
cd backend
python server.py
```
→ API runs at: http://localhost:8000
→ API docs at: http://localhost:8000/docs

### Terminal 3 — Start Price Scraper
```bash
cd scraper
python main.py
```
→ Sends price updates every 1 minute

---

## Step 5 — Open the Frontends

In VS Code, right-click each HTML file → **"Open with Live Server"**

| App | File | Purpose |
|-----|------|---------|
| Farmer App | `farmer_app/index.html` | Post listings, see prices |
| Buyer App  | `buyer_app/index.html`  | Browse listings, negotiate |

Or just double-click the HTML files to open in browser.

---

## API Endpoints

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/` | Health check |
| GET | `/docs` | Swagger API docs |
| POST | `/price-updates` | Scraper sends prices here |
| GET | `/prices` | Get all latest prices |
| GET | `/prices/{crop}/history` | Price history |
| POST | `/listings` | Farmer posts a listing |
| GET | `/listings?crop=tomato` | Browse listings |
| POST | `/negotiate` | Buyer sends offer |

---

## WebSocket Events

| Event | Direction | Payload |
|-------|-----------|---------|
| `price:update` | Server → All clients | `{crop_name, price}` |
| `listing:new` | Server → All clients | Full listing object |
| `negotiation:offer` | Server → All clients | Offer details |

---

## VS Code Extensions to Install

- **Python** (Microsoft)
- **Pylance**
- **Live Server** (Ritwick Dey)
- **REST Client** (optional, for testing API)
