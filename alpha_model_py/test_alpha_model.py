import base64
import json
from uuid import uuid4
from datetime import datetime

from fastapi.testclient import TestClient
import pytest

# Use an explicit relative import to get the 'app' from the correct 'main' module.
from .main import app

# Pytest should handle the path for 'shared' automatically when run from the root.
from shared.models import MarketEvent, SignalEvent, EventMeta, InstrumentId

# Create a TestClient instance for our FastAPI app
client = TestClient(app)

@pytest.fixture
def sample_market_event() -> MarketEvent:
    """Pytest fixture to create a sample MarketEvent for testing."""
    return MarketEvent(
        meta=EventMeta(
            saga_id=uuid4(),
            event_type="alpha.request.v1",
            source="data_ingestion_py",
            dedupe_key="TEST-2023-10-27"
        ),
        instrument=InstrumentId(
            symbol="TEST",
            sec_type="EQ"
        ),
        timestamp=datetime.now(),
        open=100.0,
        high=110.0,
        low=95.0,
        close=105.0, # A positive-momentum day
        volume=1000000
    )

def create_pubsub_push_request(payload: dict) -> dict:
    """Helper to construct a valid Pub/Sub push request body."""
    # Pydantic v2 .model_dump() returns dicts with enums, uuids, etc.
    # We need to convert them to JSON-compatible types.
    payload_json = json.dumps(payload, default=str)
    encoded_data = base64.b64encode(payload_json.encode("utf-8")).decode("utf-8")
    return {
        "message": {
            "data": encoded_data,
            "messageId": "test-message-id"
        },
        "subscription": "test-subscription"
    }

def test_health_check():
    """Tests the /health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_handle_pubsub_push_success_long_signal(sample_market_event, capsys):
    """
    Tests the main handler with a positive momentum MarketEvent.
    Expects a 'long' signal to be generated and published.
    """
    # 1. Arrange
    # Event where close > open
    request_body = create_pubsub_push_request(sample_market_event.model_dump())

    # 2. Act
    response = client.post("/", json=request_body)
    captured = capsys.readouterr()

    # 3. Assert
    assert response.status_code == 204 # No Content

    # Check log output for the mock publication
    assert "[Pub/Sub MOCK] Publishing event to 'risk.request.v1' topic:" in captured.out

    # Verify the content of the published event
    output_after_trigger = captured.out.split("[Pub/Sub MOCK] Publishing event to 'risk.request.v1' topic:")[1]
    published_event_data = json.loads(output_after_trigger.strip())

    signal_event = SignalEvent.model_validate(published_event_data)
    assert signal_event.meta.event_type == "risk.request.v1"
    assert signal_event.meta.saga_id == sample_market_event.meta.saga_id # Saga ID is propagated
    assert signal_event.instrument.symbol == "TEST"
    assert signal_event.signal == "long"
    assert signal_event.confidence == 0.75

def test_handle_pubsub_push_malformed_message(capsys):
    """
    Tests that the handler gracefully handles a message with bad data
    and returns a success status code to prevent Pub/Sub redelivery.
    """
    # 1. Arrange
    bad_request_body = {
        "message": {"data": "this is not valid base64", "messageId": "bad-message"},
        "subscription": "test-subscription"
    }

    # 2. Act
    response = client.post("/", json=bad_request_body)
    captured = capsys.readouterr()

    # 3. Assert
    assert response.status_code == 204 # Should still ack the message
    assert "ERROR: Could not decode or parse incoming message" in captured.out
