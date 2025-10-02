"""
Configuration settings for Medical Data Extraction API
"""
import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # Database
    DATABASE_URL = os.getenv("DATABASE_URL")
    
    # Google Gemini API
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    
    # File storage
    UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
    
    # Processing settings
    BATCH_SIZE = 6  # Process 6 pages in parallel
    MAX_RETRIES = 3
    MAX_PDF_PAGES = 100
    
    # Ensure upload directory exists
    os.makedirs(UPLOAD_DIR, exist_ok=True)

settings = Settings()