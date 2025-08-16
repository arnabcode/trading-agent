from datetime import datetime, date, timezone
from typing import List, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field
from enum import Enum

# --- Enums for standardized values ---

class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "SL"
    STOP_LOSS_MARKET = "SL-M"

class TransactionType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class ProductType(str, Enum):
    INTRADAY = "MIS"
    DELIVERY = "CNC"
    NORMAL = "NRML" # For F&O

# --- Core Data Structures ---

class EventMeta(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    saga_id: UUID
    event_type: str
    version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str
    dedupe_key: str # Usually hash of content to ensure idempotency
    tags: List[str] = []

class InstrumentId(BaseModel):
    venue: str = "NSE" # Default to National Stock Exchange
    symbol: str # e.g., "RELIANCE", "NIFTY24AUGFUT"
    sec_type: str = "EQ" # EQ, FUT, OPT
    expiry: Optional[date] = None
    strike: Optional[float] = None
    right: Optional[str] = None # "CE" or "PE"
    currency: str = "INR"
    lot_size: int = 1
    tick_size: float = 0.05

# --- Event Payloads ---

class MarketEvent(BaseModel):
    meta: EventMeta
    instrument: InstrumentId
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

class SignalEvent(BaseModel):
    meta: EventMeta
    instrument: InstrumentId
    signal: str # e.g., 'long', 'short', 'neutral'
    confidence: float = Field(..., ge=0.0, le=1.0)
    entry_price: Optional[float] = None
    target_price: Optional[float] = None
    stop_loss_price: Optional[float] = None

class RiskResult(BaseModel):
    is_approved: bool
    reason: Optional[str] = None
    max_position_notional: float
    max_order_notional: float
    stop_loss_price: Optional[float] = None

class RiskEvent(BaseModel):
    meta: EventMeta
    instrument: InstrumentId
    signal: SignalEvent # The original signal
    risk_result: RiskResult

class TCostResult(BaseModel):
    estimated_brokerage: float
    estimated_taxes: float
    estimated_slippage_pct: float
    total_estimated_cost: float
    net_entry_price: float

class TCostEvent(BaseModel):
    meta: EventMeta
    instrument: InstrumentId
    risk_assessment: RiskEvent # The preceding risk event
    tcost_result: TCostResult

class OrderIntent(BaseModel):
    instrument: InstrumentId
    transaction_type: TransactionType
    quantity: int
    order_type: OrderType
    product_type: ProductType
    price: Optional[float] = None # Required for LIMIT orders
    trigger_price: Optional[float] = None # Required for SL/SL-M orders
    tag: Optional[str] = None # Broker-specific tag for tracking

class OrderEvent(BaseModel):
    meta: EventMeta
    order_intent: OrderIntent
    status: str = "pending" # e.g., pending, sent, filled, cancelled
    broker_order_id: Optional[str] = None

class FillEvent(BaseModel):
    meta: EventMeta
    instrument: InstrumentId
    broker_order_id: str
    fill_id: str
    fill_timestamp: datetime
    fill_price: float
    fill_quantity: int
    transaction_type: TransactionType
    exchange_order_id: str
    exchange_timestamp: datetime
