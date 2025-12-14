from sqlalchemy import Boolean, Column, Integer, String
from database import Base

class Todo(Base):
    __tablename__ = "todos"

    id = Column(Integer, primary_key=True, index=True)
    caption = Column(String)  # <--- Make sure this is 'caption', not 'title'
    raw_image_url = Column(String, nullable=True)
    compressed_image_url = Column(String, nullable=True)
    status = Column(String, default="text_only")
    complete = Column(Boolean, default=False)