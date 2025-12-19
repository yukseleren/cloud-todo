import os
import random
from io import BytesIO

# 1. Add 'tag' to the import
from locust import HttpUser, between, task, tag 

def _random_title() -> str:
    return f"todo-{random.randint(1, 1_000_000)}"


class TodoUser(HttpUser):
    # Pause between tasks to mimic real users
    wait_time = between(1, 4)
    # Hardcoded base URL (update to your deployed endpoint)
    host = ""

    @task(5)
    @tag("read") # 2. Use @tag instead of @task.tags
    def view_homepage(self):
        # Renders current todos (HTML)
        self.client.get("/", name="GET /")

    @task(3)
    @tag("write") # 2. Use @tag instead of @task.tags
    def create_text_todo(self):
        # Uses the form-based route without an image upload
        data = {"title": _random_title()}
        # Avoid downloading the redirect target for cleaner metrics
        self.client.post("/create", data=data, allow_redirects=False, name="POST /create (text)")

    @task(1)
    @tag("write") # 2. Use @tag instead of @task.tags
    def upload_image_api(self):
        # Load-test-friendly route that queues image compression
        # Read the file from disk once or per request
        with open("133999647855558691.jpg", "rb") as f:
            file_content = f.read()
            
        files = {"file": ("133999647855558691.jpg", BytesIO(file_content), "image/jpeg")}
        self.client.post("/api/upload", files=files, name="POST /api/upload")