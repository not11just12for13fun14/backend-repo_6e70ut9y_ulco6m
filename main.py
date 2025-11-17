import os
import math
import time
import hmac
import hashlib
from uuid import uuid4
from typing import Optional, List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from database import db, create_document, get_documents
from bson.objectid import ObjectId

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Utility: provably fair crash point from seed
# Using stake-like formula: crash = floor((100 * H) / (H - 1)) / 100 where H from hash
# We'll implement a simpler deterministic mapping using HMAC(server_seed, "crash")

def crash_point_from_seed(server_seed: str) -> float:
    digest = hmac.new(server_seed.encode(), b"crash", hashlib.sha256).hexdigest()
    # take first 13 hex chars -> int -> uniform in [0, 2^52)
    r = int(digest[:13], 16)
    if r == 0:
        r = 1
    # Map to (1.00, 10.00] biasing towards low
    # Use classic formula: 1/(1-x) with cap
    x = (r % (1<<52)) / float(1<<52)
    m = 1.0 / max(1e-9, (1.0 - x))
    m = max(1.01, min(m, 50.0))
    return round(m, 2)

class CreateRoundRequest(BaseModel):
    k: Optional[float] = 0.25  # growth constant for m(t)=exp(k*t)
    delay_seconds: Optional[float] = 2.0

class RoundInfo(BaseModel):
    id: str
    start_time: float
    crash_at: float
    status: str

class PlaceBetRequest(BaseModel):
    player_id: str
    amount: float
    auto_cashout: Optional[float] = None

class CashoutRequest(BaseModel):
    player_id: str

@app.get("/")
def read_root():
    return {"message": "Crash backend ready"}

@app.get("/schema")
def get_schema():
    from schemas import User, Product, CrashRound, CrashBet
    return {
        "schemas": [
            {"name": "user", "fields": list(User.model_fields.keys())},
            {"name": "product", "fields": list(Product.model_fields.keys())},
            {"name": "crashround", "fields": list(CrashRound.model_fields.keys())},
            {"name": "crashbet", "fields": list(CrashBet.model_fields.keys())},
        ]
    }

@app.post("/api/round", response_model=RoundInfo)
def create_round(req: CreateRoundRequest):
    server_seed = uuid4().hex
    crash_at = crash_point_from_seed(server_seed)
    start_time = time.time() + (req.delay_seconds or 0)
    k = float(req.k or 0.25)
    data = {
        "server_seed": server_seed,
        "start_time": start_time,
        "crash_at": float(crash_at),
        "k": k,
        "status": "scheduled",
    }
    try:
        round_id = create_document("crashround", data)
    except Exception:
        # If DB not available, return ephemeral id without persistence
        round_id = uuid4().hex
    return RoundInfo(id=str(round_id), start_time=start_time, crash_at=crash_at, status="scheduled")

@app.get("/api/round/current", response_model=RoundInfo)
def get_current_round():
    # Try to fetch most recent scheduled/running round
    if db is not None:
        try:
            docs = db["crashround"].find({"status": {"$in": ["scheduled", "running"]}}).sort("start_time", -1).limit(1)
            doc = next(iter(docs), None)
            if doc:
                return RoundInfo(id=str(doc.get("_id")), start_time=doc["start_time"], crash_at=float(doc["crash_at"]), status=doc["status"])
        except Exception:
            pass
    # Fallback: create one
    return create_round(CreateRoundRequest())

@app.post("/api/round/{round_id}/status")
def update_round_status(round_id: str, status: str):
    if db is not None:
        try:
            db["crashround"].update_one({"_id": ObjectId(round_id) if len(round_id)==24 else round_id}, {"$set": {"status": status}})
        except Exception:
            pass
    return {"ok": True}

@app.post("/api/round/{round_id}/bet")
def place_bet(round_id: str, req: PlaceBetRequest):
    # Persist bet
    data = {
        "round_id": round_id,
        "player_id": req.player_id,
        "amount": float(req.amount),
        "auto_cashout": req.auto_cashout,
        "cashed_out_at": None,
        "profit": None,
    }
    bet_id = None
    if db is not None:
        try:
            bet_id = create_document("crashbet", data)
        except Exception:
            pass
    return {"bet_id": str(bet_id) if bet_id else uuid4().hex}

@app.post("/api/round/{round_id}/cashout")
def cashout(round_id: str, req: CashoutRequest, at_multiplier: float):
    # Compute profit based on multiplier and user's latest bet on this round
    profit = None
    if db is not None:
        try:
            bet = db["crashbet"].find_one({"round_id": round_id, "player_id": req.player_id}, sort=[("created_at", -1)])
            if bet and bet.get("amount") is not None:
                amount = float(bet["amount"])
                profit = round(amount * max(0.0, at_multiplier - 1.0), 2)
                db["crashbet"].update_one({"_id": bet["_id"]}, {"$set": {"cashed_out_at": at_multiplier, "profit": profit}})
        except Exception:
            pass
    return {"profit": profit}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
