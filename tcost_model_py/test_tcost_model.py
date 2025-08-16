import base64
import json
from uuid import uuid4
from datetime import datetime
from unittest.mock import MagicMock

import pytest

# Use an explicit relative import to get the handler from the correct 'main' module.
from .main import tcost_model_handler
# Pytest should handle the path for 'shared' automatically when run from the root.
from shared.models import RiskEvent, SignalEvent, RiskResult, TCostEvent, EventMeta, InstrumentId

@pytest.fixture
def sample_risk_event() -> RiskEvent:
    """Pytest fixture to create a sample approved RiskEvent for testing."""
    signal = SignalEvent(
        meta=EventMeta(saga_id=uuid4(), event_type="signal...", source="alpha", dedupe_key="..."),
        instrument=InstrumentId(symbol="TEST", sec_type="EQ"),
        signal="long",
        confidence=0.8,
        entry_price=1000.0
    )
    risk_result = RiskResult(
        is_approved=True,
        reason="Symbol is whitelisted.",
        max_order_notional=50000.0,
        max_position_notional=50000.0
    )
    return RiskEvent(
        meta=EventMeta(
            saga_id=signal.meta.saga_id,
            event_type="risk.request.v1",
            source="risk_model_py",
            dedupe_key="...-risk"
        ),
        instrument=signal.instrument,
        signal=signal,
        risk_result=risk_result
    )

def create_mock_cloudevent(payload: dict) -> MagicMock:
    """Helper to construct a valid Pub/Sub push request body."""
    encoded_data = base64.b64encode(json.dumps(payload, default=str).encode("utf-8"))
    event = MagicMock()
    event.data = {"message": {"data": encoded_data, "messageId": "test-message-id"}}
    return event

def test_tcost_calculation_approved(sample_risk_event, capsys):
    """
    Tests the happy path where a risk-approved event is processed and costs are calculated.
    """
    # 1. Arrange
    request_event = create_mock_cloudevent(sample_risk_event.model_dump())

    # 2. Act
    result, status_code = tcost_model_handler(request_event)
    captured = capsys.readouterr()

    # 3. Assert
    assert status_code == 200
    assert "Calculated total estimated cost" in captured.out

    output_after_trigger = captured.out.split("[Pub/Sub MOCK] Publishing event to 'portfolio.construct.v1' topic:")[1]
    published_event_data = json.loads(output_after_trigger.strip())

    tcost_event = TCostEvent.model_validate(published_event_data)
    assert tcost_event.meta.event_type == "portfolio.construct.v1"

    # Verify the cost calculation based on the hardcoded model in main.py
    # trade_value = 50000.0
    # stt = 50000 * 0.001 = 50.0
    # exchange_txn = 50000 * 0.0000345 = 1.725
    # gst = 1.725 * 0.18 = 0.3105
    # total_cost = 50.0 + 1.725 + 0.3105 = 52.0355
    assert tcost_event.tcost_result.total_estimated_cost == pytest.approx(52.0355)
    assert tcost_event.tcost_result.estimated_taxes == pytest.approx(50.3105) # stt + gst

def test_tcost_calculation_denied(sample_risk_event, capsys):
    """
    Tests that if a trade was not approved by risk, cost calculation is skipped.
    """
    # 1. Arrange
    sample_risk_event.risk_result.is_approved = False
    request_event = create_mock_cloudevent(sample_risk_event.model_dump())

    # 2. Act
    result, status_code = tcost_model_handler(request_event)
    captured = capsys.readouterr()

    # 3. Assert
    assert status_code == 200
    assert "Trade was not approved by risk model" in captured.out
    assert "Publishing event to 'portfolio.construct.v1'" not in captured.out
