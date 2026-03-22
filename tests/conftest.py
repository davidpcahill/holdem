"""
Shared fixtures for Playwright E2E tests.

Starts the Flask app in a background thread on a random port,
provides a Playwright browser page pointed at it, and tears
everything down after each test.
"""

import threading
import socket
import time
import pytest
from playwright.sync_api import Page

# Import the Flask app (not started yet)
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import app, socketio


def _find_free_port() -> int:
    """Find a free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def live_server():
    """Start the Flask-SocketIO server in a background thread for the test session."""
    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"

    # Disable Flask debug mode for test stability
    app.config["TESTING"] = True

    thread = threading.Thread(
        target=lambda: socketio.run(
            app, host="127.0.0.1", port=port,
            debug=False, use_reloader=False,
            allow_unsafe_werkzeug=True, log_output=False,
        ),
        daemon=True,
    )
    thread.start()

    # Wait for server to be ready
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.1)
    else:
        raise RuntimeError(f"Server failed to start on port {port}")

    yield base_url


@pytest.fixture()
def app_page(live_server: str, page: Page) -> Page:
    """Navigate to the app and return the Playwright page."""
    page.goto(live_server)
    page.wait_for_selector("#app", state="attached", timeout=5000)
    return page
