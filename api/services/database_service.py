"""
Database service using psycopg for PostgreSQL operations
"""
import psycopg
import json
from typing import Optional, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class DatabaseService:
    def __init__(self, connection_string: str):
        self.connection_string = connection_string

    async def get_connection(self):
        """Get database connection"""
        return await psycopg.AsyncConnection.connect(self.connection_string)

    async def create_tables(self):
        """Create all required tables if they don't exist"""
        async with await self.get_connection() as conn:
            async with conn.cursor() as cur:
                # Create patients table
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS patients (
                        patient_uid VARCHAR(255) PRIMARY KEY,
                        patient_age INTEGER,
                        patient_name VARCHAR(255),
                        demographics JSONB,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Create hospitals table
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS hospitals (
                        hospital_uid VARCHAR(255) PRIMARY KEY,
                        hospital_name VARCHAR(255),
                        location VARCHAR(255),
                        state VARCHAR(255),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Create documents table
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS documents (
                        doc_id SERIAL,
                        page_id INTEGER,
                        hospital_uid VARCHAR(255) REFERENCES hospitals(hospital_uid),
                        patient_uid VARCHAR(255) REFERENCES patients(patient_uid),
                        upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        ocr_text TEXT,
                        doc_image_path VARCHAR(500),
                        original_filename VARCHAR(255),
                        file_path VARCHAR(500), -- ADD THIS LINE
                        total_pages INTEGER,
                        processing_status VARCHAR(50) DEFAULT 'processing',
                        PRIMARY KEY (doc_id, page_id)
                    )
                """)

                # Create summary table
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS summary_table (
                        summary_id SERIAL PRIMARY KEY,
                        patient_id VARCHAR(255) REFERENCES patients(patient_uid),
                        hospital_uid VARCHAR(255) REFERENCES hospitals(hospital_uid),
                        summary_text TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                await conn.commit()
                logger.info("All tables created/verified successfully")

    async def get_or_create_patient(self, patient_id: str) -> bool:
        """Get or create patient record"""
        async with await self.get_connection() as conn:
            async with conn.cursor() as cur:
                # Check if patient exists
                await cur.execute(
                    "SELECT patient_uid FROM patients WHERE patient_uid = %s",
                    (patient_id,)
                )
                result = await cur.fetchone()

                if not result:
                    # Create new patient
                    await cur.execute(
                        """INSERT INTO patients (patient_uid, demographics)
                           VALUES (%s, %s)
                           ON CONFLICT (patient_uid) DO NOTHING""",
                        (patient_id, json.dumps({}))
                    )
                    await conn.commit()
                    logger.info(f"Created new patient: {patient_id}")

                return True

    async def get_or_create_hospital(self, hospital_id: str) -> bool:
        """Get or create hospital record"""
        async with await self.get_connection() as conn:
            async with conn.cursor() as cur:
                # Check if hospital exists
                await cur.execute(
                    "SELECT hospital_uid FROM hospitals WHERE hospital_uid = %s",
                    (hospital_id,)
                )
                result = await cur.fetchone()

                if not result:
                    # Create new hospital
                    await cur.execute(
                        """INSERT INTO hospitals (hospital_uid, hospital_name)
                           VALUES (%s, %s)
                           ON CONFLICT (hospital_uid) DO NOTHING""",
                        (hospital_id, f"Hospital_{hospital_id}")
                    )
                    await conn.commit()
                    logger.info(f"Created new hospital: {hospital_id}")

                return True

    async def create_document_record(
        self, doc_id: int, page_id: int, patient_id: str, hospital_id: str,
        filename: str, file_path: str, total_pages: int, ocr_text: str = '', doc_image_path: str = ''
    ) -> int:
        """Create document record and return doc_id"""
        async with await self.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """INSERT INTO documents (doc_id, page_id, patient_uid, hospital_uid, original_filename,
                       file_path, total_pages, ocr_text, doc_image_path, processing_status)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING doc_id""",
                    (doc_id, page_id, patient_id, hospital_id, filename, file_path, total_pages, ocr_text, doc_image_path, 'processing')
                )
                result = await cur.fetchone()
                await conn.commit()
                doc_id = result[0]
                logger.info(f"Created document record: {doc_id}, page: {page_id}")
                return doc_id

    async def create_summary_record(self, patient_id: str, hospital_uid: str, summary_text: str) -> int:
        """Create summary record"""
        async with await self.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """INSERT INTO summary_table (patient_id, hospital_uid, summary_text)
                       VALUES (%s, %s, %s) RETURNING summary_id""",
                    (patient_id, hospital_uid, summary_text)
                )
                result = await cur.fetchone()
                await conn.commit()
                return result[0]

    async def update_document_status(self, doc_id: int, status: str):
        """Update document processing status"""
        async with await self.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE documents SET processing_status = %s WHERE doc_id = %s",
                    (status, doc_id)
                )
                await conn.commit()
                logger.info(f"Updated document {doc_id} status to {status}")

    async def get_document_status(self, doc_id: int) -> Optional[Dict]:
        """Get document processing status with details"""
        async with await self.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """SELECT
                       total_pages,
                       COUNT(CASE WHEN processing_status = 'success' THEN 1 END) as processed_pages,
                       COUNT(CASE WHEN processing_status = 'failed' THEN 1 END) as failed_pages
                       FROM documents WHERE doc_id = %s
                       GROUP BY total_pages""",
                    (doc_id,)
                )
                result = await cur.fetchone()

                if result:
                    total_pages, processed_pages, failed_pages = result
                    status = 'completed' if (processed_pages + failed_pages) == total_pages else 'processing'
                    return {
                        "doc_id": doc_id,
                        "status": status,
                        "total_pages": total_pages or 0,
                        "processed_pages": processed_pages or 0,
                        "failed_pages": failed_pages or 0,
                        "progress_percentage": ((processed_pages or 0) + (failed_pages or 0)) / (total_pages or 1) * 100
                    }
                return None