import base64
import json
from uuid import uuid4

import functions_framework
from pydantic import BaseModel

# Add project root to path to allow importing from 'shared'
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.models import RiskEvent, TCostEvent, TCostResult, EventMeta

# --- Simplified India/Zerodha Fee Model (Equity Delivery) ---
# Note: These are simplified and for demonstration purposes.
# Real-world calculations can be more complex.
STT_CHARGE = 0.001  # 0.1% on buy and sell
EXCHANGE_TXN_CHARGE = 0.0000345  # 0.00345% on NSE
GST = 0.18  # 18% on brokerage and transaction charges
BROKERAGE = 0.0  # Zerodha has zero brokerage for equity delivery

@functions_framework.cloud_event
def tcost_model_handler(cloud_event):
    """
    Cloud Function that calculates transaction costs for a proposed trade.
    """
    try:
        payload_json = base64.b64decode(cloud_event.data["message"]["data"]).decode("utf-8")
        risk_event = RiskEvent.model_validate_json(payload_json)
        print(f"Received risk event for {risk_event.instrument.symbol} (Saga: {risk_event.meta.saga_id})")
    except Exception as e:
        print(f"ERROR: Could not decode or parse incoming message. Error: {e}")
        return "Bad Request: Invalid message format", 400

    # --- TCost Model Logic ---
    # Only calculate costs if the trade was approved by the risk model.
    if not risk_event.risk_result.is_approved:
        print("  - Trade was not approved by risk model. Skipping TCost calculation.")
        # We could publish a "saga failed" event here, but for now we just stop.
        return "OK: Trade not approved", 200

    # Use the max notional value from the risk assessment as the trade value.
    trade_value = risk_event.risk_result.max_order_notional
    entry_price = risk_event.signal.entry_price

    # Calculate individual costs
    stt = trade_value * STT_CHARGE
    exchange_txn_charge = trade_value * EXCHANGE_TXN_CHARGE
    total_brokerage = trade_value * BROKERAGE
    gst_on_charges = (total_brokerage + exchange_txn_charge) * GST

    total_cost = total_brokerage + stt + exchange_txn_charge + gst_on_charges

    # Calculate the adjusted entry price including costs
    quantity = trade_value / entry_price if entry_price else 0
    cost_per_share = total_cost / quantity if quantity else 0
    net_entry_price = entry_price + cost_per_share if entry_price else 0

    tcost_result = TCostResult(
        estimated_brokerage=total_brokerage,
        estimated_taxes=stt + gst_on_charges,
        estimated_slippage_pct=0.0,  # Slippage model would be more complex
        total_estimated_cost=total_cost,
        net_entry_price=net_entry_price
    )
    print(f"  - Calculated total estimated cost: {total_cost:.2f}")

    # --- Create the TCostEvent ---
    tcost_event = TCostEvent(
        meta=EventMeta(
            saga_id=risk_event.meta.saga_id,
            event_type="tcost.calculation.completed.v1",
            source="tcost_model_py",
            dedupe_key=f"{risk_event.meta.dedupe_key}-tcost"
        ),
        instrument=risk_event.instrument,
        risk_assessment=risk_event,
        tcost_result=tcost_result
    )

    # --- MOCK ACTION: Publish portfolio.construct.v1 event ---
    portfolio_request_event = tcost_event.model_copy(deep=True)
    portfolio_request_event.meta.event_id = uuid4()
    portfolio_request_event.meta.event_type = "portfolio.construct.v1"

    event_payload_json = portfolio_request_event.model_dump_json(indent=2)

    print(f"\n[Pub/Sub MOCK] Publishing event to 'portfolio.construct.v1' topic:")
    print(event_payload_json)
    # --- END MOCK ACTION ---

    return "OK", 200
