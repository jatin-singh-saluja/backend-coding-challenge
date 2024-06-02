import pytest
from unittest.mock import patch, Mock

from gistapi import app, gists_for_user, gist_files_content, HEADERS


@pytest.fixture
def client():
    with app.test_client() as client:
        yield client


def test_ping(client):
    """Test the /ping endpoint."""
    rv = client.get("/ping")
    assert rv.data == b"pong"
    assert rv.status_code == 200


@patch("gistapi.requests.get")
def test_gists_for_user(mock_get):
    """Test the gists_for_user function."""
    mock_response = mock_get.return_value
    mock_response.json.return_value = [
        {"id": "1", "url": "http://example.com", "html_url": "http://example.com"}
    ]
    mock_response.links = {}
    mock_response.raise_for_status.return_value = None

    gists, more_pages = gists_for_user("testuser")

    assert len(gists) == 1
    assert gists[0]["id"] == "1"
    assert more_pages is False


@patch("gistapi.requests.get")
def test_gist_files_content(mock_get):
    """Test the gist_files_content function."""
    # Mock the initial gist response
    mock_gist_response = Mock()
    mock_gist_response.json.return_value = {
        "files": {
            "gistfile1.txt": {"raw_url": "http://example.com/raw/gistfile1.txt"},
            "gistfile2.txt": {"raw_url": "http://example.com/raw/gistfile2.txt"},
        }
    }
    mock_gist_response.raise_for_status.return_value = None

    # Mock the file content responses
    mock_file_response_1 = Mock()
    mock_file_response_1.text = "content of gistfile1"
    mock_file_response_1.raise_for_status.return_value = None

    mock_file_response_2 = Mock()
    mock_file_response_2.text = "content of gistfile2"
    mock_file_response_2.raise_for_status.return_value = None

    def side_effect(url, headers):
        if url == "http://example.com/raw/gistfile1.txt":
            return mock_file_response_1
        elif url == "http://example.com/raw/gistfile2.txt":
            return mock_file_response_2
        return mock_gist_response

    mock_get.side_effect = side_effect

    files_content = gist_files_content("http://example.com")

    assert "gistfile1.txt" in files_content
    assert files_content["gistfile1.txt"] == "content of gistfile1"
    assert "gistfile2.txt" in files_content
    assert files_content["gistfile2.txt"] == "content of gistfile2"

    mock_get.assert_any_call("http://example.com/raw/gistfile1.txt", headers=HEADERS)
    mock_get.assert_any_call("http://example.com/raw/gistfile2.txt", headers=HEADERS)
    assert mock_get.call_count == 3


def test_search_missing_pattern(client):
    data = {"username": "testuser"}
    response = client.post("/api/v1/search", json=data)
    json_data = response.get_json()

    assert response.status_code == 400
    assert json_data["status"] == "error"
    assert json_data["message"] == "Pattern is required"


def test_search_missing_username(client):
    """Test the /api/v1/search endpoint without a username."""
    data = {"pattern": "test"}

    response = client.post("/api/v1/search", json=data)
    json_data = response.get_json()

    assert response.status_code == 400
    assert json_data["status"] == "error"
    assert json_data["message"] == "Username is required"
