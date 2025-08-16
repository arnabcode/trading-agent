import base64
import json
import pandas as pd
from datetime import datetime
from unittest.mock import MagicMock
import pytest

# Use an explicit relative import to ensure we get the correct 'main' module.
from .main import data_ingestion_handler

# Pytest should handle the path for 'shared' automatically when run from the root.
from shared.models import MarketEvent

@pytest.fixture
def mock_yfinance(mocker):
    """Pytest fixture to mock the yfinance.download call."""
    # Create a sample DataFrame that yfinance would return
    mock_data = {
        "Open": [100.0],
        "High": [105.0],
        "Low": [99.0],
        "Close": [104.0],
        "Volume": [1000000]
    }
    mock_index = [datetime(2023, 10, 27)]
    mock_df = pd.DataFrame(mock_data, index=pd.to_datetime(mock_index))
    mock_df.index.name = "Date"

    # Patch the yf.download function
    return mocker.patch('yfinance.download', return_value=mock_df)

def create_mock_cloudevent(payload: dict) -> MagicMock:
    """Creates a mock CloudEvent object for a Pub/Sub trigger."""
    encoded_data = base64.b64encode(json.dumps(payload).encode("utf-8"))

    # Mimic the structure of a CloudEvent for Pub/Sub
    event = MagicMock()
    event.data = {
        "message": {
            "data": encoded_data,
            "messageId": "test-message-id"
        },
        "subscription": "test-subscription"
    }
    return event

def test_data_ingestion_handler_success(mock_yfinance, capsys):
    """
    Tests the happy path of the data ingestion handler.
    Verifies that it fetches data, logs mock actions, and prepares the correct event.
    """
    # 1. Arrange
    mock_event = create_mock_cloudevent({"symbol": "TEST.NS"})

    # 2. Act
    result, status_code = data_ingestion_handler(mock_event)
    captured = capsys.readouterr() # Capture printed output

    # 3. Assert
    # Check the function's return value
    assert status_code == 200
    assert result == "OK"

    # Check that yfinance was called correctly
    mock_yfinance.assert_called_once_with("TEST.NS", period="5d", interval="1d")

    # Check the log output for mock actions
    assert "[Firestore MOCK] Writing market_event for TEST.NS" in captured.out
    assert "[Pub/Sub MOCK] Publishing event to 'alpha.request.v1' topic:" in captured.out

    # Verify the structure and content of the published event
    # Isolate the JSON output from the rest of the log messages
    output_after_trigger = captured.out.split("[Pub/Sub MOCK] Publishing event to 'alpha.request.v1' topic:")[1]
    json_string = output_after_trigger.split("Data ingestion process finished successfully.")[0].strip()
    published_event_data = json.loads(json_string)

    # Validate the event using our Pydantic model
    alpha_request = MarketEvent.model_validate(published_event_data)
    assert alpha_request.meta.event_type == "alpha.request.v1"
    assert alpha_request.instrument.symbol == "TEST"
    assert alpha_request.close == 104.0
    assert alpha_request.volume == 1000000

def test_data_ingestion_handler_missing_symbol(capsys):
    """Tests that the function handles a missing 'symbol' in the payload gracefully."""
    # 1. Arrange
    mock_event = create_mock_cloudevent({"wrong_key": "TEST.NS"})

    # 2. Act
    result, status_code = data_ingestion_handler(mock_event)
    captured = capsys.readouterr()

    # 3. Assert
    assert status_code == 400
    assert "Missing 'symbol' in payload" in result
    assert "Error: 'symbol' not found" in captured.out

def test_data_ingestion_handler_yfinance_no_data(mocker, capsys):
    """Tests that the function handles an empty DataFrame from yfinance."""
    # 1. Arrange
    mocker.patch('yfinance.download', return_value=pd.DataFrame()) # Mock empty response
    mock_event = create_mock_cloudevent({"symbol": "FAKE.NS"})

    # 2. Act
    result, status_code = data_ingestion_handler(mock_event)
    captured = capsys.readouterr()

    # 3. Assert
    assert status_code == 404
    assert "No data available" in result
    assert "Error: No data found for symbol FAKE.NS" in captured.out
