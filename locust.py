"""
Locust scenarios for the FastAPI Todo app.

Examples:
- locust -f locust.py --headless -u 10 -r 2 -t 1m -H http://localhost:8000
- TARGET_HOST=https://your-api locust -f locust.py
"""

import os
import random
from io import BytesIO

from locust import HttpUser, between, task


def _random_title() -> str:
    return f"todo-{random.randint(1, 1_000_000)}"


class TodoUser(HttpUser):
    # Pause between tasks to mimic real users
    wait_time = between(1, 4)
    # Hardcoded base URL (update to your deployed endpoint)
    host = "http://136.119.222.179"

    @task(5)
    @task.tags("read")
    def view_homepage(self):
        # Renders current todos (HTML)
        self.client.get("/", name="GET /")

    @task(3)
    @task.tags("write")
    def create_text_todo(self):
        # Uses the form-based route without an image upload
        data = {"title": _random_title()}
        # Avoid downloading the redirect target for cleaner metrics
        self.client.post("/create", data=data, allow_redirects=False, name="POST /create (text)")

    @task(1)
    @task.tags("write")
    def upload_image_api(self):
        # Load-test-friendly route that queues image compression
        files = {"file": ("loadtest.jpg", BytesIO(b"fake image bytes"), "image/jpeg")}
        self.client.post("/api/upload", files=files, name="POST /api/upload")
