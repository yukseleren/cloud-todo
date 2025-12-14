import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Get password from environment, crash if missing (safe!)
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_URL = f"postgresql://app_user:{DB_PASSWORD}@127.0.0.1:5432/todo_app"

engine = create_engine(DB_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()