import base64
import json
from uuid import uuid4

from fastapi import FastAPI, Request, Response, status
from pydantic import BaseModel

# The Dockerfile places the 'shared' directory in the workdir, making it importable.
from shared.models import MarketEvent, SignalEvent, EventMeta

# --- FastAPI App Initialization ---
app = FastAPI(
    title="Alpha Model Service",
    description="Consumes market data events and generates trading signals.",
    version="1.0.0",
)

# --- Pydantic Models for Pub/Sub Message Handling ---
# This models the structure of a push message from Google Pub/Sub
class PubSubMessage(BaseModel):
    data: str
    messageId: str

class PubSubPushRequest(BaseModel):
    message: PubSubMessage
    subscription: str

# --- Health Check Endpoint ---
@app.get("/health", status_code=status.HTTP_200_OK)
def perform_health_check():
    """A simple endpoint to confirm the service is running."""
    return {"status": "ok"}

# --- Main Signal Generation Endpoint ---
@app.post("/", status_code=status.HTTP_204_NO_CONTENT)
async def handle_pubsub_push(request: PubSubPushRequest):
    """
    Handles incoming Pub/Sub push requests. It decodes the market event,
    applies a simple alpha model, and prepares the subsequent signal event.
    """
    try:
        # Decode the inner message data from base64 to a JSON string
        payload_json = base64.b64decode(request.message.data).decode("utf-8")

        # Parse the JSON string into our MarketEvent Pydantic model for validation and use
        market_event = MarketEvent.model_validate_json(payload_json)
        print(f"Received market event for {market_event.instrument.symbol} (Saga: {market_event.meta.saga_id})")

    except Exception as e:
        print(f"ERROR: Could not decode or parse incoming message. Message ID: {request.message.messageId}. Error: {e}")
        # Acknowledge the message with a 204 status to prevent Pub/Sub from redelivering a malformed message.
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # --- Alpha Model Logic (Simple Daily Momentum) ---
    signal = "neutral"
    confidence = 0.5
    if market_event.close > market_event.open:
        signal = "long"
        confidence = 0.75
    elif market_event.close < market_event.open:
        signal = "short"
        confidence = 0.75

    print(f"  - Alpha model generated signal: {signal.upper()} with confidence {confidence}")
    # --- End Alpha Model Logic ---

    # --- Create the SignalEvent ---
    # This event captures the output of our model.
    signal_event = SignalEvent(
        meta=EventMeta(
            saga_id=market_event.meta.saga_id, # Propagate the saga_id for tracing
            event_type="signal.generated.v1",
            source="alpha_model_py",
            dedupe_key=f"{market_event.meta.dedupe_key}-signal" # Create a new dedupe key
        ),
        instrument=market_event.instrument,
        signal=signal,
        confidence=confidence,
        entry_price=market_event.close # Use close price as the potential entry price
    )

    # --- MOCK ACTION: Publish risk.request.v1 event ---
    # We create a new event to trigger the next service in the saga.
    risk_request_event = signal_event.model_copy(deep=True)
    risk_request_event.meta.event_id = uuid4() # This is a new event, so it gets a new ID
    risk_request_event.meta.event_type = "risk.request.v1"

    event_payload_json = risk_request_event.model_dump_json(indent=2)

    print(f"\n[Pub/Sub MOCK] Publishing event to 'risk.request.v1' topic:")
    print(event_payload_json)
    # --- END MOCK ACTION ---

    # Acknowledge the message to Pub/Sub by returning a success status code.
    # 204 No Content is appropriate as we don't need to return a body.
    return Response(status_code=status.HTTP_204_NO_CONTENT)
