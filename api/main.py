"""
FastAPI Medical Data Extraction API
Main application entry point
"""
import os
import asyncio
import logging
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# Import models and services
from models.schemas import ProcessingResponse, DocumentStatus
from services.database_service import DatabaseService
from services.gemini_service import GeminiService
from services.processing_service import ProcessingService
from config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize services
db_service = DatabaseService(settings.DATABASE_URL)
gemini_service = GeminiService(settings.GEMINI_API_KEY, settings.MAX_RETRIES)
processing_service = ProcessingService(
    gemini_service,
    settings.BATCH_SIZE,
    settings.MAX_RETRIES,
    settings.MAX_PDF_PAGES
)

# Initialize FastAPI app
app = FastAPI(
    title="Medical Data Extraction API",
    description="FastAPI service for extracting medical data from PDF documents using OCR + Gemini AI",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """Initialize database tables on startup"""
    try:
        await db_service.create_tables()
        logger.info("Database tables initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {str(e)}")
        raise

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "message": "Medical Data Extraction API is running",
        "version": "1.0.0",
        "status": "active"
    }

@app.get("/health")
async def health_check():
    """Health check with database connection test"""
    try:
        # Test database connection
        async with await db_service.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
                result = await cur.fetchone()

        return {
            "status": "healthy",
            "database": "connected",
            "service": "Medical Data Extraction API",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "database": "disconnected",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
        )

def save_uploaded_pdf(file: UploadFile, patient_id: str, hospital_id: str) -> tuple[str, str]:
    """Save uploaded PDF to disk and return filename and filepath"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"medical_doc_{patient_id}_{hospital_id}_{timestamp}.pdf"
    file_path = os.path.join(settings.UPLOAD_DIR, filename)

    # Save file
    with open(file_path, "wb") as buffer:
        content = file.file.read()
        buffer.write(content)

    logger.info(f"Saved PDF: {filename} ({len(content) / (1024*1024):.2f} MB)")
    return filename, file_path

@app.post("/process-document", response_model=ProcessingResponse)
async def process_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    patient_id: str = Form(...),
    hospital_id: str = Form(...)
):
    """
    Upload PDF and initiate background processing

    Args:
        file: PDF file to process
        patient_id: Patient identifier
        hospital_id: Hospital identifier

    Returns:
        ProcessingResponse with doc_id and status
    """

    # Validate file type
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    try:
        # 1. Save PDF to disk
        original_filename, file_path = save_uploaded_pdf(file, patient_id, hospital_id)

        # 2. Get page count for database record
        try:
            images = processing_service.convert_pdf_to_images(file_path)
            total_pages = len(images)
        except Exception as e:
            logger.error(f"Failed to get page count: {str(e)}")
            total_pages = 0
            # Don't fail here, let background processing handle it

        # 3. Create/get patient and hospital records
        await db_service.get_or_create_patient(patient_id)
        await db_service.get_or_create_hospital(hospital_id)

        # 4. Generate doc_id for this batch of pages
        import time
        doc_id = int(time.time() * 1000) % 2147483647  # Generate unique doc_id

        # 5. Start background processing
        background_tasks.add_task(
            processing_service.process_pdf_background,
            doc_id, file_path, patient_id, hospital_id, original_filename, db_service
        )

        logger.info(f"Started processing for doc_id: {doc_id}, pages: {total_pages}")

        # Calculate estimated time (approximately 2 seconds per page)
        estimated_minutes = max(1, (total_pages * 2) // 60)

        return ProcessingResponse(
            message=f"Process has started. It will take approximately {estimated_minutes} minute(s). Please check the database after that.",
            status="processing",
            doc_id=doc_id
        )

    except Exception as e:
        logger.error(f"Error in process_document: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

@app.get("/document-status/{doc_id}", response_model=DocumentStatus)
async def get_document_status(doc_id: int):
    """
    Get processing status of a document

    Args:
        doc_id: Document ID to check

    Returns:
        DocumentStatus with processing details
    """
    result = await db_service.get_document_status(doc_id)

    if not result:
        raise HTTPException(status_code=404, detail="Document not found")

    return DocumentStatus(**result)

@app.get("/patient/{patient_id}/documents")
async def get_patient_documents(patient_id: str):
    """Get all documents for a patient"""
    try:
        async with await db_service.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """SELECT DISTINCT d.doc_id, d.original_filename, d.upload_date,
                              d.processing_status, d.total_pages,
                              h.hospital_name
                       FROM documents d
                       JOIN hospitals h ON d.hospital_uid = h.hospital_uid
                       WHERE d.patient_uid = %s
                       ORDER BY d.upload_date DESC""",
                    (patient_id,)
                )
                results = await cur.fetchall()

                documents = []
                for row in results:
                    doc_id, filename, upload_date, status, total_pages, hospital_name = row
                    documents.append({
                        "doc_id": doc_id,
                        "filename": filename,
                        "upload_date": upload_date.isoformat() if upload_date else None,
                        "status": status,
                        "total_pages": total_pages,
                        "hospital_name": hospital_name
                    })

                return {
                    "patient_id": patient_id,
                    "documents": documents,
                    "total": len(documents)
                }

    except Exception as e:
        logger.error(f"Error getting patient documents: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve documents: {str(e)}")

@app.get("/document/{doc_id}/summary")
async def get_document_summary(doc_id: int):
    """Get summary for a specific document"""
    try:
        async with await db_service.get_connection() as conn:
            async with conn.cursor() as cur:
                # First get the patient_id and hospital_uid from the documents table
                await cur.execute(
                    "SELECT patient_uid, hospital_uid FROM documents WHERE doc_id = %s LIMIT 1",
                    (doc_id,)
                )
                doc_info = await cur.fetchone()
                if not doc_info:
                    raise HTTPException(status_code=404, detail="Document not found")
                patient_id, hospital_uid = doc_info

                await cur.execute(
                    """SELECT summary_text, created_at
                       FROM summary_table
                       WHERE patient_id = %s AND hospital_uid = %s""",
                    (patient_id, hospital_uid)
                )
                result = await cur.fetchone()

                if not result:
                    raise HTTPException(status_code=404, detail="Summary not found for this document")

                summary_text, created_at = result

                return {
                    "doc_id": doc_id,
                    "patient_id": patient_id,
                    "summary": summary_text,
                    "created_at": created_at.isoformat() if created_at else None
                }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting document summary: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve summary: {str(e)}")

@app.get("/document/{doc_id}/pages")
async def get_document_pages(doc_id: int):
    """Get all pages for a specific document with their tags"""
    try:
        async with await db_service.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """SELECT page_id, ocr_text, processing_status
                       FROM documents
                       WHERE doc_id = %s
                       ORDER BY page_id""",
                    (doc_id,)
                )
                results = await cur.fetchall()

                if not results:
                    raise HTTPException(status_code=404, detail="No pages found for this document")

                pages = []
                for row in results:
                    page_id, ocr_text, status = row
                    pages.append({
                        "page_id": page_id,
                        "ocr_text": ocr_text[:500] + "..." if ocr_text and len(ocr_text) > 500 else ocr_text,
                        "status": status,
                    })

                return {
                    "doc_id": doc_id,
                    "pages": pages,
                    "total_pages": len(pages)
                }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting document pages: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve pages: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )