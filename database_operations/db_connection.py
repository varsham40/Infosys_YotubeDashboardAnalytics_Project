import os
import ssl
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
DB_PORT = os.getenv("DB_PORT", "3306")
DB_NAME = os.getenv("DB_NAME")

DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# TiDB Cloud requires SSL connections
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# Create SQLAlchemy engine with connection pooling
engine = create_engine(
    DATABASE_URL, 
    echo=False, # Set to False for production performance
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,
    pool_pre_ping=True,
    connect_args={"ssl": ssl_context}
)

# Session creator
SessionLocal = sessionmaker(bind=engine)

# Initialize tables
def init_db():
    Base.metadata.create_all(bind=engine)
