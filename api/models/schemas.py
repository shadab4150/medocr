"""
Pydantic models for FastAPI Medical Data Extraction API
"""
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class ProcessingResponse(BaseModel):
    """Response model for document processing initiation"""
    message: str
    status: str
    doc_id: Optional[int] = None

class MedicalPageExtraction(BaseModel):
    """Structured extraction for each medical document page"""
    ocr_text: str
    tags: List[str]  # clinical_documentation, investigations/lab_reports, etc.

class DocumentStatus(BaseModel):
    """Document processing status response"""
    doc_id: int
    status: str
    total_pages: int
    processed_pages: int
    failed_pages: int
    progress_percentage: float