"""
FastAPI Medical Data Extraction API
"""
import os
import io
import asyncio
import logging
import uuid
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import pdf2image

from config import settings
from database import DatabaseService
from gemini_processor import GeminiProcessor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize services
db_service = DatabaseService(settings.DATABASE_URL)
gemini_processor = GeminiProcessor(settings.GEMINI_API_KEY, settings.MAX_RETRIES)

# Initialize FastAPI app
app = FastAPI(
    title="Medical Data Extraction API",
    description="FastAPI service for extracting medical data from PDF documents using Gemini AI",
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
        async with await db_service.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "error": str(e)}
        )

def resize_image(image: Image.Image, max_size: int = 1920) -> Image.Image:
    """Resize image while preserving aspect ratio"""
    width, height = image.size
    if max(width, height) <= max_size:
        return image
    
    aspect_ratio = width / height
    if width > height:
        new_width = max_size
        new_height = int(max_size / aspect_ratio)
    else:
        new_height = max_size
        new_width = int(max_size * aspect_ratio)
    
    return image.resize((new_width, new_height), Image.LANCZOS)

def convert_to_jpeg_bytes(image: Image.Image) -> bytes:
    """Convert PIL image to JPEG bytes"""
    img_byte_arr = io.BytesIO()
    if image.mode in ("RGBA", "P"):
        image = image.convert("RGB")
    image.save(img_byte_arr, format='JPEG', quality=95)
    return img_byte_arr.getvalue()

def convert_pdf_to_images(file_path: str) -> list:
    """Convert PDF to list of PIL images"""
    try:
        images = pdf2image.convert_from_path(file_path, dpi=200)
        
        if len(images) > settings.MAX_PDF_PAGES:
            logger.warning(f"PDF has {len(images)} pages. Limiting to {settings.MAX_PDF_PAGES}")
            images = images[:settings.MAX_PDF_PAGES]
        
        # Resize images
        resized_images = [resize_image(img) for img in images]
        logger.info(f"Converted PDF to {len(resized_images)} images")
        return resized_images
        
    except Exception as e:
        logger.error(f"Error converting PDF: {str(e)}")
        raise

def process_single_page(image: Image.Image, page_number: int) -> dict:
    """Process a single page with Gemini"""
    try:
        img_bytes = convert_to_jpeg_bytes(image)
        result = gemini_processor.extract_page_data(img_bytes)
        
        return {
            'success': True,
            'page_number': page_number,
            'ocr_text': result['ocr_text'],
            'tags': result['tags']
        }
    except Exception as e:
        logger.error(f"Error processing page {page_number}: {str(e)}")
        return {
            'success': False,
            'page_number': page_number,
            'error': str(e)
        }

async def process_pdf_background(upload_id: str, file_path: str):
    """Background processing pipeline for PDF"""
    try:
        logger.info(f"Starting background processing for upload_id: {upload_id}")
        
        # 1. Convert PDF to images
        all_images = convert_pdf_to_images(file_path)
        total_pages = len(all_images)
        
        # 2. Extract patient info from first page
        logger.info("Extracting patient info from first page...")
        first_page_bytes = convert_to_jpeg_bytes(all_images[0])
        patient_info = gemini_processor.extract_patient_info(first_page_bytes)
        patient_uhid = patient_info.get('patient_uhid')
        irch_number = patient_info.get('irch_number')
        patient_name = patient_info.get('patient_name')
        age = patient_info.get('age')
        gender = patient_info.get('gender')
        
        logger.info(f"Extracted - Patient: {patient_name}, UHID: {patient_uhid}, IRCH: {irch_number}, Age: {age}, Gender: {gender}")
        
        # 3. Create placeholder records for all pages
        for page_num in range(1, total_pages + 1):
            await db_service.insert_page(upload_id, page_num, patient_uhid, irch_number, 
                                        patient_name, age, gender)
        
        # 4. Process all pages in batches
        logger.info(f"Processing {total_pages} pages in batches of {settings.BATCH_SIZE}...")
        temp_results = {}  # Store results temporarily
        
        for batch_start in range(0, total_pages, settings.BATCH_SIZE):
            batch_end = min(batch_start + settings.BATCH_SIZE, total_pages)
            batch = all_images[batch_start:batch_end]
            batch_num = (batch_start // settings.BATCH_SIZE) + 1
            total_batches = (total_pages + settings.BATCH_SIZE - 1) // settings.BATCH_SIZE
            
            logger.info(f"Processing Batch {batch_num}/{total_batches} (Pages {batch_start + 1}-{batch_end})")
            
            # Process batch in parallel
            with ThreadPoolExecutor(max_workers=settings.BATCH_SIZE) as executor:
                future_to_page = {
                    executor.submit(process_single_page, img, batch_start + idx + 1): batch_start + idx + 1
                    for idx, img in enumerate(batch)
                }
                
                for future in as_completed(future_to_page):
                    page_num = future_to_page[future]
                    try:
                        result = future.result(timeout=60)
                        temp_results[page_num] = result
                    except Exception as e:
                        logger.error(f"Page {page_num} timeout/error: {str(e)}")
                        temp_results[page_num] = {
                            'success': False,
                            'page_number': page_num,
                            'error': str(e)
                        }
        
        # 5. Update database with all results
        logger.info("Updating database with processed results...")
        for page_num, result in temp_results.items():
            if result['success']:
                await db_service.insert_page(
                    upload_id, page_num, patient_uhid, irch_number, patient_name,
                    age, gender, result['ocr_text'], result['tags'], 'success'
                )
            else:
                await db_service.insert_page(
                    upload_id, page_num, patient_uhid, irch_number, patient_name,
                    age, gender, None, None, 'failed'
                )
        
        # 6. Generate summary from successful pages
        logger.info("Generating summary...")
        all_pages_text = await db_service.get_all_pages_text(upload_id)
        
        if all_pages_text:
            summary = gemini_processor.generate_summary(all_pages_text)
            await db_service.insert_summary(upload_id, patient_uhid, irch_number, 
                                           patient_name, age, gender, summary)
            logger.info(f"Summary generated for upload_id: {upload_id}")
        else:
            logger.warning(f"No successful pages to generate summary for upload_id: {upload_id}")
        
        logger.info(f"Processing completed for upload_id: {upload_id}")
        
    except Exception as e:
        logger.error(f"Background processing failed for upload_id {upload_id}: {str(e)}")

@app.post("/process-document")
async def process_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    """
    Upload PDF and initiate background processing
    
    Returns:
        upload_id and estimated processing time
    """
    # Validate file type
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    try:
        # Generate unique upload_id
        upload_id = str(uuid.uuid4())
        
        # Save PDF to disk
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"medical_doc_{upload_id}_{timestamp}.pdf"
        file_path = os.path.join(settings.UPLOAD_DIR, filename)
        
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        logger.info(f"Saved PDF: {filename} ({len(content) / (1024*1024):.2f} MB)")
        
        # Get page count for time estimation
        try:
            images = convert_pdf_to_images(file_path)
            total_pages = len(images)
        except Exception as e:
            logger.error(f"Failed to get page count: {str(e)}")
            total_pages = 0
        
        # Start background processing
        background_tasks.add_task(process_pdf_background, upload_id, file_path)
        
        # Calculate estimated time (approximately 2 seconds per page)
        estimated_minutes = max(1, (total_pages * 2) // 60)
        
        logger.info(f"Started processing for upload_id: {upload_id}, pages: {total_pages}")
        
        return {
            "message": "Processing started successfully",
            "upload_id": upload_id,
            "total_pages": total_pages,
            "estimated_time_minutes": estimated_minutes,
            "status": "Check database after estimated time for results"
        }
        
    except Exception as e:
        logger.error(f"Error in process_document: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")