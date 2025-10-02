-- Medical Data Extraction API Database Schema
-- Auto-created by the application, provided here for reference

-- Main documents table: one row per page
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
);

-- Summary table: one row per upload
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
);

-- Indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_documents_upload_id ON api_documents_table(upload_id);
CREATE INDEX IF NOT EXISTS idx_documents_patient_uhid ON api_documents_table(patient_uhid);
CREATE INDEX IF NOT EXISTS idx_documents_irch ON api_documents_table(irch_number);
CREATE INDEX IF NOT EXISTS idx_documents_patient_name ON api_documents_table(patient_name);
CREATE INDEX IF NOT EXISTS idx_documents_status ON api_documents_table(processing_status);
CREATE INDEX IF NOT EXISTS idx_summary_upload_id ON api_summary(upload_id);
CREATE INDEX IF NOT EXISTS idx_summary_patient_uhid ON api_summary(patient_uhid);

-- Useful queries

-- Get all pages for a specific upload
-- SELECT * FROM api_documents_table WHERE upload_id = 'your-upload-id' ORDER BY page_number;

-- Get summary for an upload
-- SELECT * FROM api_summary WHERE upload_id = 'your-upload-id';

-- Check processing status
-- SELECT 
--     upload_id,
--     COUNT(*) as total_pages,
--     SUM(CASE WHEN processing_status = 'success' THEN 1 ELSE 0 END) as successful,
--     SUM(CASE WHEN processing_status = 'failed' THEN 1 ELSE 0 END) as failed,
--     SUM(CASE WHEN processing_status = 'processing' THEN 1 ELSE 0 END) as in_progress
-- FROM api_documents_table
-- WHERE upload_id = 'your-upload-id'
-- GROUP BY upload_id;

-- Get all documents for a patient
-- SELECT * FROM api_documents_table WHERE patient_uhid = 'your-patient-uhid' ORDER BY created_at DESC;

-- Get documents by tag
-- SELECT * FROM api_documents_table WHERE tags @> '["clinical_documentation"]'::jsonb;

-- Get recent uploads
-- SELECT DISTINCT upload_id, patient_uhid, irch, created_at 
-- FROM api_documents_table 
-- ORDER BY created_at DESC 
-- LIMIT 10;

-- Statistics by processing status
-- SELECT processing_status, COUNT(*) 
-- FROM api_documents_table 
-- GROUP BY processing_status;