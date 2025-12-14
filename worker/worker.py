import os
import json
import time
import tempfile
import sqlalchemy
from google.cloud import pubsub_v1, storage
from PIL import Image

# --- CONFIGURATION ---
PROJECT_ID = os.environ['GCP_PROJECT']
SUB_ID = "compression-sub" # Must match your Terraform/PubSub Subscription name
RAW_BUCKET = os.environ['RAW_BUCKET'] 
PUBLIC_BUCKET = os.environ['PUBLIC_BUCKET'] # You need a separate bucket for processed images
DB_URL = "postgresql://app_user:securepassword@127.0.0.1:5432/todo_app" # Connects via Sidecar

# --- SETUP CLIENTS ---
subscriber = pubsub_v1.SubscriberClient()
sub_path = subscriber.subscription_path(PROJECT_ID, SUB_ID)
storage_client = storage.Client()
db_engine = sqlalchemy.create_engine(DB_URL)

def process_message(message):
    try:
        print(f"Received message: {message.data}")
        data = json.loads(message.data.decode("utf-8"))
        
        todo_id = data['todo_id']
        filename = data['filename']
        
        print(f"Processing Task {todo_id} (File: {filename})...")

        # 1. Download from Raw Bucket
        raw_bucket = storage_client.bucket(RAW_BUCKET)
        blob = raw_bucket.blob(filename)
        _, temp_local = tempfile.mkstemp()
        blob.download_to_filename(temp_local)

        # 2. Compress Image
        with Image.open(temp_local) as img:
            out_filename = temp_local + "_compressed.jpg"
            # Resize and Lower Quality
            img.save(out_filename, "JPEG", quality=40, optimize=True)

        # 3. Upload to Public Bucket
        dest_bucket = storage_client.bucket(PUBLIC_BUCKET)
        new_blob_name = f"compressed_{filename}"
        new_blob = dest_bucket.blob(new_blob_name)
        new_blob.upload_from_filename(out_filename)
        
        # Make it public so the HTML tag <img src="..."> can read it
        # (Alternatively, use Signed URLs if you want better security)
        # Note: If bucket has "Uniform Bucket Level Access", you skip this line 
        # and just ensure the bucket itself is public.
        # new_blob.make_public() 

        public_url = f"https://storage.googleapis.com/{PUBLIC_BUCKET}/{new_blob_name}"

        # 4. Update Database
        # We update 'compressed_image_url' and set status to 'completed'
        with db_engine.connect() as conn:
            stmt = sqlalchemy.text("""
                UPDATE todos 
                SET compressed_image_url = :url, status = 'completed' 
                WHERE id = :uid
            """)
            conn.execute(stmt, {"url": public_url, "uid": todo_id})
            conn.commit()

        print(f"Task {todo_id} Completed!")
        message.ack() # Tell Google "I'm done, don't send this again"
        
        # Cleanup
        os.remove(temp_local)
        os.remove(out_filename)

    except Exception as e:
        print(f"Error: {e}")
        message.nack() # Tell Google "I failed, retry later"

if __name__ == "__main__":
    print(f"Listening for messages on {sub_path}...")
    future = subscriber.subscribe(sub_path, callback=process_message)
    with subscriber:
        try:
            future.result()
        except KeyboardInterrupt:
            future.cancel()