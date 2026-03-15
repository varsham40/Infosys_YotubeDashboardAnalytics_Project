import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Import Base from your model file
from database_operations.db_model import Base

# Load .env variables
load_dotenv()

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")

DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}"

# Create SQLAlchemy engine with connection pooling
engine = create_engine(
    DATABASE_URL, 
    echo=False, # Set to False for production performance
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,
    pool_pre_ping=True
)

# Session creator
SessionLocal = sessionmaker(bind=engine)

# Initialize tables
def init_db():
    Base.metadata.create_all(bind=engine)
