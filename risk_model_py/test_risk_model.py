import base64
import json
from uuid import uuid4
from datetime import datetime

from fastapi.testclient import TestClient
import pytest

# Use an explicit relative import to get the 'app' from the correct 'main' module.
from .main import app
# Pytest should handle the path for 'shared' automatically when run from the root.
from shared.models import SignalEvent, RiskEvent, EventMeta, InstrumentId

client = TestClient(app)

@pytest.fixture
def sample_signal_event() -> SignalEvent:
    """Pytest fixture to create a sample SignalEvent for testing."""
    return SignalEvent(
        meta=EventMeta(
            saga_id=uuid4(),
            event_type="risk.request.v1",
            source="alpha_model_py",
            dedupe_key="TEST-2023-10-27-signal"
        ),
        instrument=InstrumentId(symbol="TEST", sec_type="EQ"),
        signal="long",
        confidence=0.8,
        entry_price=100.0
    )

def create_pubsub_push_request(payload: dict) -> dict:
    """Helper to construct a valid Pub/Sub push request body."""
    payload_json = json.dumps(payload, default=str)
    encoded_data = base64.b64encode(payload_json.encode("utf-8")).decode("utf-8")
    return {
        "message": {"data": encoded_data, "messageId": "test-message-id"},
        "subscription": "test-subscription"
    }

def test_health_check():
    """Tests the /health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["risk_policy_version"] == 1

def test_risk_check_approved(sample_signal_event, capsys):
    """
    Tests a signal for a whitelisted symbol ('TEST') which should be approved.
    """
    # 1. Arrange
    request_body = create_pubsub_push_request(sample_signal_event.model_dump())

    # 2. Act
    response = client.post("/", json=request_body)
    captured = capsys.readouterr()

    # 3. Assert
    assert response.status_code == 204
    assert "Risk assessment result: APPROVED" in captured.out

    output_after_trigger = captured.out.split("[Pub/Sub MOCK] Publishing event to 'tcost.request.v1' topic:")[1]
    published_event_data = json.loads(output_after_trigger.strip())

    risk_event = RiskEvent.model_validate(published_event_data)
    assert risk_event.meta.event_type == "tcost.request.v1"
    assert risk_event.risk_result.is_approved is True
    # From risk_policy.json: "TEST" has a specific override
    assert risk_event.risk_result.max_order_notional == 50000.0

def test_risk_check_denied(sample_signal_event, capsys):
    """
    Tests a signal for a non-whitelisted symbol which should be denied.
    """
    # 1. Arrange
    # Change the symbol to one not in the policy
    sample_signal_event.instrument.symbol = "UNKNOWN"
    request_body = create_pubsub_push_request(sample_signal_event.model_dump())

    # 2. Act
    response = client.post("/", json=request_body)
    captured = capsys.readouterr()

    # 3. Assert
    assert response.status_code == 204
    assert "Risk assessment result: DENIED" in captured.out
    assert "Symbol 'UNKNOWN' not in whitelist" in captured.out

    output_after_trigger = captured.out.split("[Pub/Sub MOCK] Publishing event to 'tcost.request.v1' topic:")[1]
    published_event_data = json.loads(output_after_trigger.strip())

    risk_event = RiskEvent.model_validate(published_event_data)
    assert risk_event.risk_result.is_approved is False
    assert risk_event.risk_result.max_order_notional == 0.0
