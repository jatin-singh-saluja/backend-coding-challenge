"""
Exposes a simple HTTP API to search a users Gists via a regular expression.

Github provides the Gist service as a pastebin analog for sharing code and
other develpment artifacts.  See http://gist.github.com for details.  This
module implements a Flask server exposing two endpoints: a simple ping
endpoint to verify the server is up and responding and a search endpoint
providing a search across all public Gists for a given Github account.
"""

import json
import os
import re

import requests
from dotenv import load_dotenv
from flask import Flask, Response, abort, jsonify, request, stream_with_context
from jsonschema import ValidationError, validate

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Load GitHub token from environment variable
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    raise RuntimeError("GITHUB_TOKEN is not set")

HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"}

search_input_schema = {
    "type": "object",
    "properties": {
        "username": {"type": "string"},
        "pattern": {"type": "string"},
        "page": {"type": "integer", "minimum": 1},
        "per_page": {"type": "integer", "minimum": 1, "maximum": 100},
    },
    "required": ["username", "pattern"],
}

search_output_schema = {
    "type": "object",
    "properties": {
        "status": {"type": "string"},
        "username": {"type": "string"},
        "pattern": {"type": "string"},
        "matches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "gist_id": {"type": "string"},
                    "filename": {"type": "string"},
                    "url": {"type": "string"},
                },
                "required": ["gist_id", "filename", "url"],
            },
        },
        "page": {"type": "integer"},
        "more_pages": {"type": "boolean"},
    },
    "required": ["status", "username", "pattern", "matches", "page", "more_pages"],
}


@app.route("/ping")
def ping():
    """Provide a static response to a simple GET request."""
    return "pong"


@app.route("/api/v1/search", methods=["POST"])
def search():
    """Provides matches for a single pattern across a single user's gists with pagination.

    Pulls down a list of all gists for a given user and then searches
    each gist for a given regular expression.

    Returns:
        A Flask Response object of type application/json.  The result
        object contains the list of matches along with a 'status' key
        indicating any failure conditions.
    """
    post_data = request.get_json()
    if post_data is None:
        abort(400, description="Invalid JSON data")

    try:
        validate(instance=post_data, schema=search_input_schema)
    except ValidationError as e:
        abort(400, description=f"JSON validation error: {e.message}")

    username = post_data.get("username")
    pattern = post_data.get("pattern")
    page = post_data.get("page", 1)
    per_page = post_data.get("per_page", 10)

    try:
        re.compile(pattern)
    except re.error:
        abort(400, description="Invalid regular expression pattern")

    def generate():
        try:
            gists, more_pages = gists_for_user(username, page, per_page)
        except RuntimeError as e:
            abort(500, description=str(e))

        matches = []

        for gist in gists:
            gist_files = gist_files_content(gist["url"])
            for filename, content in gist_files.items():
                if re.search(pattern, content):
                    match = {
                        "gist_id": gist["id"],
                        "filename": filename,
                        "url": gist["html_url"],
                    }
                    matches.append(match)
                    # Validate the match against the schema before yielding
                    response_part = {
                        "status": "success",
                        "username": username,
                        "pattern": pattern,
                        "matches": [match],
                        "page": page,
                        "more_pages": more_pages,
                    }
                    try:
                        validate(instance=response_part,
                                 schema=search_output_schema)
                    except ValidationError as e:
                        abort(
                            500, description=f"Response validation error: {e.message}"
                        )
                    # Stream new match to the client immediately
                    yield (json.dumps(response_part) + "\n").encode("utf-8")

        if not matches:
            response_part = {
                "status": "no matches",
                "username": username,
                "pattern": pattern,
                "matches": [],
                "page": page,
                "more_pages": more_pages,
            }
            yield (json.dumps(response_part) + "\n").encode("utf-8")

    return Response(stream_with_context(generate()), content_type="application/json")


@app.errorhandler(400)
def bad_request(error):
    response = jsonify({"status": "error", "message": error.description})
    response.status_code = 400
    return response


@app.errorhandler(500)
def internal_error(error):
    response = jsonify({"status": "error", "message": error.description})
    response.status_code = 500
    return response


def gists_for_user(
    username: str, page: int = 1, per_page: int = 10
) -> tuple[list[dict], bool]:
    """Provides the list of gist metadata for a given user with pagination.

    This abstracts the /users/:username/gist endpoint from the Github API.
    See https://developer.github.com/v3/gists/#list-a-users-gists for
    more information.

    Args:
        username (string): the user to query gists for
        page (int): the page number to retrieve
        per_page (int): the number of gists per page

    Returns:
        The dict parsed from the json response from the Github API.  See
        the above URL for details of the expected structure.
    """
    gists_url = f"https://api.github.com/users/{username}/gists"
    params = {"page": page, "per_page": per_page}

    try:
        response = requests.get(gists_url, headers=HEADERS, params=params)
        response.raise_for_status()  # Raise an HTTPError for bad responses (4xx and 5xx)
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Error fetching gists: {e}")

    gists = response.json()
    # Check if there are more pages by looking at the Link header
    more_pages = "next" in response.links

    return gists, more_pages


def gist_files_content(gist_url: str) -> dict[str, str]:
    """Fetches the content of the files in a Gist.

    Args:
        gist_url (string): the URL of the Gist.

    Returns:
        A dict where keys are filenames and values are file contents.
    """
    try:
        response = requests.get(gist_url, headers=HEADERS)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        abort(500, description=f"Error fetching gist files: {e}")

    gist_data = response.json()
    files_content = {}

    for filename, file_info in gist_data["files"].items():
        try:
            file_response = requests.get(file_info["raw_url"], headers=HEADERS)
            file_response.raise_for_status()
            files_content[filename] = file_response.text
        except requests.exceptions.RequestException as e:
            abort(500, description=f"Error fetching file {filename}: {e}")

    return files_content


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=9876)
