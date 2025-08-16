import base64
import json
import os
import sys
from datetime import datetime
from uuid import uuid4

import functions_framework
import yfinance as yf

# Add project root to path to allow importing from 'shared'
# This allows the function to find the 'shared' module in a monorepo-like structure.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.models import EventMeta, InstrumentId, MarketEvent

@functions_framework.cloud_event
def data_ingestion_handler(cloud_event):
    """
    Cloud Function triggered by Pub/Sub to ingest market data.

    Args:
        cloud_event (object): The CloudEvent for the Pub/Sub message.
                              The message data is expected to be a base64-encoded
                              JSON string, e.g., {"symbol": "RELIANCE.NS"}.
    """
    # Decode the Pub/Sub message to get the target symbol
    try:
        message_data = base64.b64decode(cloud_event.data["message"]["data"]).decode("utf-8")
        payload = json.loads(message_data)
        symbol = payload.get("symbol")
        if not symbol:
            print("Error: 'symbol' not found in Pub/Sub message payload.")
            return "Bad Request: Missing 'symbol' in payload", 400
    except Exception as e:
        print(f"Error decoding message: {e}")
        return "Bad Request: Invalid message format", 400

    print(f"Received request to ingest data for symbol: {symbol}")

    # Fetch data using yfinance for the last day
    try:
        # We fetch for 5 days to ensure we get the last trading day if run on a weekend/holiday
        data = yf.download(symbol, period="5d", interval="1d")
        if data.empty:
            print(f"Error: No data found for symbol {symbol}")
            return "Not Found: No data available for the symbol", 404

        latest_data = data.iloc[-1]
        data_timestamp = latest_data.name.to_pydatetime()
        print(f"Successfully fetched data for {symbol} for date {data_timestamp.date()}")

    except Exception as e:
        print(f"Error fetching data from yfinance for {symbol}: {e}")
        return "Internal Server Error: yfinance query failed", 500

    # Create the MarketEvent using our shared Pydantic models
    saga_id = uuid4()
    dedupe_key = f"{symbol}-{data_timestamp.date()}"

    instrument = InstrumentId(
        symbol=symbol.replace(".NS", ""), # Use a clean version of the symbol
        sec_type="EQ",
        venue="NSE",
        lot_size=1,
        tick_size=0.05
    )

    market_event = MarketEvent(
        meta=EventMeta(
            saga_id=saga_id,
            event_type="market.data.ingested.v1",
            source="data_ingestion_py",
            dedupe_key=dedupe_key,
        ),
        instrument=instrument,
        timestamp=data_timestamp,
        open=latest_data["Open"],
        high=latest_data["High"],
        low=latest_data["Low"],
        close=latest_data["Close"],
        volume=int(latest_data["Volume"])
    )

    # --- MOCK ACTIONS ---
    # In a real application, you would use client libraries for Firestore and Pub/Sub.
    # Here, we simulate the actions by printing to the log.

    # 1. Mock: Write the market_event to a 'market_events' collection in Firestore.
    print(f"\n[Firestore MOCK] Writing market_event for {symbol} to collection 'market_events'.")
    print(f"  - Saga ID: {saga_id}")
    print(f"  - Document ID (Dedupe Key): {dedupe_key}")

    # 2. Mock: Prepare and "publish" the event that triggers the next service.
    # The original event is repackaged as an 'alpha.request.v1' event.
    alpha_request_event = market_event.model_copy(deep=True)
    alpha_request_event.meta.event_id = uuid4() # New event, new ID
    alpha_request_event.meta.event_type = "alpha.request.v1"

    event_payload_json = alpha_request_event.model_dump_json(indent=2)

    print(f"\n[Pub/Sub MOCK] Publishing event to 'alpha.request.v1' topic:")
    print(event_payload_json)
    # --- END MOCK ACTIONS ---

    print("\nData ingestion process finished successfully.")
    return "OK", 200
