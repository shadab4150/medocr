"""
Database service for PostgreSQL operations
"""
import psycopg
import json
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)

class DatabaseService:
    def __init__(self, connection_string: str):
        self.connection_string = connection_string

    async def get_connection(self):
        """Get database connection"""
        return await psycopg.AsyncConnection.connect(self.connection_string)

    async def create_tables(self):
        """Create required tables if they don't exist"""
        async with await self.get_connection() as conn:
            async with conn.cursor() as cur:
                # Create api_documents_table
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS api_documents_table (
                        upload_id TEXT NOT NULL,
                        page_number INTEGER NOT NULL,
                        patient_uhid TEXT,
                        irch_number TEXT,
                        patient_name TEXT,
                        age TEXT,
                        gender TEXT,
                        ocr_text TEXT,
                        tags JSONB,
                        processing_status TEXT DEFAULT 'processing',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (upload_id, page_number)
                    )
                """)

                # Create api_summary table
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS api_summary (
                        summary_id SERIAL PRIMARY KEY,
                        upload_id TEXT NOT NULL,
                        patient_uhid TEXT,
                        irch_number TEXT,
                        patient_name TEXT,
                        age TEXT,
                        gender TEXT,
                        summary TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                await conn.commit()
                logger.info("Database tables created/verified successfully")

    async def insert_page(
        self, 
        upload_id: str, 
        page_number: int, 
        patient_uhid: str = None, 
        irch_number: str = None,
        patient_name: str = None,
        age: str = None,
        gender: str = None,
        ocr_text: str = None, 
        tags: List[str] = None, 
        status: str = 'processing'
    ):
        """Insert a page record"""
        async with await self.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """INSERT INTO api_documents_table 
                       (upload_id, page_number, patient_uhid, irch_number, patient_name, 
                        age, gender, ocr_text, tags, processing_status)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (upload_id, page_number) 
                       DO UPDATE SET 
                           patient_uhid = EXCLUDED.patient_uhid,
                           irch_number = EXCLUDED.irch_number,
                           patient_name = EXCLUDED.patient_name,
                           age = EXCLUDED.age,
                           gender = EXCLUDED.gender,
                           ocr_text = EXCLUDED.ocr_text,
                           tags = EXCLUDED.tags,
                           processing_status = EXCLUDED.processing_status""",
                    (upload_id, page_number, patient_uhid, irch_number, patient_name,
                     age, gender, ocr_text, json.dumps(tags) if tags else None, status)
                )
                await conn.commit()
                logger.info(f"Inserted/Updated page {page_number} for upload {upload_id}")

    async def update_pages_with_patient_info(
        self, 
        upload_id: str, 
        patient_uhid: str, 
        irch_number: str,
        patient_name: str = None,
        age: str = None,
        gender: str = None
    ):
        """Update all pages with patient and hospital info"""
        async with await self.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """UPDATE api_documents_table 
                       SET patient_uhid = %s, irch_number = %s, patient_name = %s, 
                           age = %s, gender = %s
                       WHERE upload_id = %s""",
                    (patient_uhid, irch_number, patient_name, age, gender, upload_id)
                )
                await conn.commit()
                logger.info(f"Updated all pages with patient info for upload {upload_id}")

    async def insert_summary(
        self, 
        upload_id: str,
        patient_uhid: str, 
        irch_number: str,
        patient_name: str,
        age: str,
        gender: str,
        summary: str
    ):
        """Insert summary record"""
        async with await self.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """INSERT INTO api_summary (upload_id, patient_uhid, irch_number, 
                                                patient_name, age, gender, summary)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (upload_id, patient_uhid, irch_number, patient_name, age, gender, summary)
                )
                await conn.commit()
                logger.info(f"Inserted summary for upload {upload_id}")

    async def get_all_pages_text(self, upload_id: str) -> List[str]:
        """Get all successfully processed pages text for summary generation"""
        async with await self.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """SELECT page_number, ocr_text 
                       FROM api_documents_table 
                       WHERE upload_id = %s AND processing_status = 'success'
                       ORDER BY page_number""",
                    (upload_id,)
                )
                results = await cur.fetchall()
                return [f"## Page {page_num}\n\n{text}" for page_num, text in results if text]