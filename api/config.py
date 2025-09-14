"""
Configuration settings for FastAPI Medical Data Extraction API
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Settings:
    # Database
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:VawcGoIcrhqd6l6OSfaK@my-medical-db.cvasumkaopp0.ap-south-1.rds.amazonaws.com:5432/patientdocs"
    )
    
    # Google APIs - using same as app-v4.py
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    
    # File storage
    UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
    
    # Processing settings - same as app-v4.py
    BATCH_SIZE = 6
    MAX_RETRIES = 1  # Using 1 as in app-v4.py
    MAX_PDF_PAGES = 100
    
    # Ensure upload directory exists
    os.makedirs(UPLOAD_DIR, exist_ok=True)

settings = Settings()