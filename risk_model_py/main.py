import base64
import json
from uuid import uuid4
from pathlib import Path

from fastapi import FastAPI, Response, status
from pydantic import BaseModel

# The Dockerfile places the 'shared' and 'configs' directories in the workdir.
from shared.models import SignalEvent, RiskEvent, RiskResult, EventMeta

# --- FastAPI App Initialization ---
app = FastAPI(
    title="Risk Model Service",
    description="Consumes trading signals and applies risk policies.",
    version="1.0.0",
)

# --- Load Risk Policy on Startup ---
RISK_POLICY = {}
try:
    policy_path = Path(__file__).parent.parent / "configs" / "risk_policy.json"
    with open(policy_path, "r") as f:
        RISK_POLICY = json.load(f)
    print("Successfully loaded risk policy.")
except Exception as e:
    print(f"FATAL: Could not load risk policy on startup. Error: {e}")
    # In a real app, you might want to prevent startup if the policy is missing.
    RISK_POLICY = {}

# --- Pydantic Models for Pub/Sub Message Handling ---
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
    return {"status": "ok", "risk_policy_version": RISK_POLICY.get("version")}

# --- Main Risk Assessment Endpoint ---
@app.post("/", status_code=status.HTTP_204_NO_CONTENT)
async def handle_pubsub_push(request: PubSubPushRequest):
    """
    Handles incoming Pub/Sub push requests. It decodes the signal event,
    applies the loaded risk policy, and prepares the subsequent risk event.
    """
    try:
        payload_json = base64.b64decode(request.message.data).decode("utf-8")
        signal_event = SignalEvent.model_validate_json(payload_json)
        print(f"Received signal event for {signal_event.instrument.symbol} (Saga: {signal_event.meta.saga_id})")
    except Exception as e:
        print(f"ERROR: Could not decode or parse incoming message. Message ID: {request.message.messageId}. Error: {e}")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # --- Risk Model Logic ---
    symbol = signal_event.instrument.symbol
    is_approved = False
    reason = ""
    max_order_notional = 0.0

    # 1. Check if symbol is in the whitelist
    if symbol not in RISK_POLICY.get("symbol_whitelist", []):
        is_approved = False
        reason = f"Symbol '{symbol}' not in whitelist."
    else:
        is_approved = True
        reason = "Symbol is whitelisted."
        # 2. Determine max order size from policy
        override = RISK_POLICY.get("symbol_specific_overrides", {}).get(symbol)
        if override and "max_order_notional" in override:
            max_order_notional = override["max_order_notional"]
        else:
            max_order_notional = RISK_POLICY.get("default_max_order_notional", 0.0)

    print(f"  - Risk assessment result: {'APPROVED' if is_approved else 'DENIED'}. Reason: {reason}")
    # --- End Risk Model Logic ---

    risk_result = RiskResult(
        is_approved=is_approved,
        reason=reason,
        max_order_notional=max_order_notional,
        max_position_notional=max_order_notional # Assuming same for this simple model
    )

    # --- Create the RiskEvent ---
    risk_event = RiskEvent(
        meta=EventMeta(
            saga_id=signal_event.meta.saga_id,
            event_type="risk.assessment.completed.v1",
            source="risk_model_py",
            dedupe_key=f"{signal_event.meta.dedupe_key}-risk"
        ),
        instrument=signal_event.instrument,
        signal=signal_event,
        risk_result=risk_result
    )

    # --- MOCK ACTION: Publish tcost.request.v1 event ---
    tcost_request_event = risk_event.model_copy(deep=True)
    tcost_request_event.meta.event_id = uuid4()
    tcost_request_event.meta.event_type = "tcost.request.v1"

    event_payload_json = tcost_request_event.model_dump_json(indent=2)

    print(f"\n[Pub/Sub MOCK] Publishing event to 'tcost.request.v1' topic:")
    print(event_payload_json)
    # --- END MOCK ACTION ---

    return Response(status_code=status.HTTP_204_NO_CONTENT)
