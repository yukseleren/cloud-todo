from fastapi import FastAPI, Depends, Request, Form, status, UploadFile, File
from starlette.responses import RedirectResponse, JSONResponse
from starlette.templating import Jinja2Templates
from sqlalchemy.orm import Session
from google.cloud import storage, pubsub_v1
import models
from database import SessionLocal, engine
import os
import json
import uuid
import requests

# --- 1. CLOUD CONFIGURATION ---
# These variables come from your Kubernetes Deployment (api-deployment.yaml)
PROJECT_ID = os.environ.get("GCP_PROJECT")
RAW_BUCKET = os.environ.get("RAW_BUCKET")
ENCRYPTION_URL = os.environ.get("ENCODER_URL") # URL of your Serverless Crypto Function
TOPIC_ID = "compression-jobs"

# Initialize Google Clients
storage_client = storage.Client()
publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)

# --- 2. DATABASE SETUP ---
models.Base.metadata.create_all(bind=engine)
templates = Jinja2Templates(directory="templates")

app = FastAPI()

# Dependency for DB Session
def get_db():
    db = SessionLocal()
    try: 
        yield db
    finally:
        db.close()

# --- 3. HELPER: SERVERLESS CRYPTO SERVICE ---
def call_crypto_service(text: str, action: str) -> str:
    """
    Calls the Google Cloud Function to Encrypt or Decrypt text.
    Action: 'encrypt' or 'decrypt'
    """
    if not ENCRYPTION_URL or not text:
        return text # Fallback: return raw text if no service configured
    
    try:
        payload = {"text": text, "action": action}
        # Timeout set to 3s to prevent hanging if function is cold-starting
        response = requests.post(ENCRYPTION_URL, json=payload, timeout=3)
        
        if response.status_code == 200:
            return response.json().get("result")
        else:
            print(f"Crypto Service Error: {response.text}")
            return text
            
    except Exception as e:
        print(f"Failed to connect to Crypto Service: {e}")
        return text

# --- 4. ROUTES ---

@app.get("/")
async def home(req: Request, db: Session = Depends(get_db)):
    """
    READ: Fetches items.
    - DECRYPTS the caption via Serverless Function so user can read it.
    """
    todos = db.query(models.Todo).all()
    
    # Decryption Loop (Demonstration of Inter-Service Communication)
    for todo in todos:
        if todo.caption:
            todo.caption = call_crypto_service(todo.caption, "decrypt")
            
    return templates.TemplateResponse("base.html", { "request": req, "todo_list": todos })

@app.post("/create")
async def create_item(
    title: str = Form(...),          # The Text (e.g., "Secret Plans")
    file: UploadFile = File(None),   # The Image (Optional)
    db: Session = Depends(get_db)
):
    """
    HYBRID WRITE:
    1. Sends Text -> Serverless Function (Encrypt)
    2. Sends Image -> Microservice (Compress)
    """
    
    # A. Encrypt the Text
    secure_caption = call_crypto_service(title, "encrypt")

    # B. Handle Image Upload
    raw_url = None
    status = "text_only"
    filename = None
    
    if file:
        file_id = str(uuid.uuid4())
        filename = f"{file_id}.jpg"
        
        # Upload to GCS Raw Bucket
        bucket = storage_client.bucket(RAW_BUCKET)
        blob = bucket.blob(filename)
        blob.upload_from_file(file.file)
        
        raw_url = f"https://storage.googleapis.com/{RAW_BUCKET}/{filename}"
        status = "processing" # UI shows spinner

    # C. Save to DB (We store the ENCRYPTED text)
    new_todo = models.Todo(
        caption=secure_caption,     # Ciphertext (gAAAA...)
        raw_image_url=raw_url,
        status=status
    )
    db.add(new_todo)
    db.commit()
    db.refresh(new_todo)

    # D. Trigger Microservice Worker via Pub/Sub
    if file:
        message = {"todo_id": new_todo.id, "filename": filename}
        publisher.publish(topic_path, json.dumps(message).encode("utf-8"))

    return RedirectResponse(url=app.url_path_for("home"), status_code=303)

@app.get("/update/{todo_id}")
def update(req: Request, todo_id: int, db: Session = Depends(get_db)):
    todo = db.query(models.Todo).filter(models.Todo.id == todo_id).first()
    todo.complete = not todo.complete
    db.commit()
    return RedirectResponse(url=app.url_path_for("home"), status_code=303)

@app.get("/delete/{todo_id}")
def delete(req: Request, todo_id: int, db: Session = Depends(get_db)):
    todo = db.query(models.Todo).filter(models.Todo.id == todo_id).first()
    db.delete(todo)
    db.commit()
    return RedirectResponse(url=app.url_path_for("home"), status_code=303)

# --- 5. OPTIONAL: API-ONLY ROUTE (For Load Testing) ---
@app.post("/api/upload")
async def api_upload(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Bypasses Encryption/HTML. Used for Locust Load Testing only.
    """
    file_id = str(uuid.uuid4())
    filename = f"{file_id}.jpg"
    
    bucket = storage_client.bucket(RAW_BUCKET)
    blob = bucket.blob(filename)
    blob.upload_from_file(file.file)
    
    new_todo = models.Todo(
        caption=f"LoadTest: {file.filename}", 
        status="processing", 
        raw_image_url=f"https://storage.googleapis.com/{RAW_BUCKET}/{filename}"
    )
    db.add(new_todo)
    db.commit()
    db.refresh(new_todo)
    
    message = {"todo_id": new_todo.id, "filename": filename}
    publisher.publish(topic_path, json.dumps(message).encode("utf-8"))
    
    return JSONResponse(content={"status": "queued", "id": new_todo.id})