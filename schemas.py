"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional

# Example schemas (replace with your own):

class User(BaseModel):
    """
    Users collection schema
    Collection name: "user" (lowercase of class name)
    """
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    address: str = Field(..., description="Address")
    age: Optional[int] = Field(None, ge=0, le=120, description="Age in years")
    is_active: bool = Field(True, description="Whether user is active")

class Product(BaseModel):
    """
    Products collection schema
    Collection name: "product" (lowercase of class name)
    """
    title: str = Field(..., description="Product title")
    description: Optional[str] = Field(None, description="Product description")
    price: float = Field(..., ge=0, description="Price in dollars")
    category: str = Field(..., description="Product category")
    in_stock: bool = Field(True, description="Whether product is in stock")

# Crash game schemas
class CrashRound(BaseModel):
    server_seed: str = Field(..., description="Server seed used to generate crash point")
    start_time: float = Field(..., description="Unix timestamp when round starts (seconds)")
    crash_at: float = Field(..., ge=1.0, description="Multiplier where the round crashes")
    k: float = Field(..., gt=0, description="Growth constant for multiplier curve m(t)=exp(k*t)")
    status: str = Field("scheduled", description="scheduled|running|crashed")

class CrashBet(BaseModel):
    round_id: str = Field(..., description="Associated round id")
    player_id: str = Field(..., description="Client generated player id")
    amount: float = Field(..., gt=0, description="Bet amount")
    auto_cashout: Optional[float] = Field(None, ge=1.01, description="Auto cashout multiplier if set")
    cashed_out_at: Optional[float] = Field(None, ge=1.0, description="Multiplier at which player cashed out")
    profit: Optional[float] = Field(None, description="Profit earned on cashout (amount*(m-1))")
