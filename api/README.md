# FastAPI Medical Data Extraction API

A high-performance API for extracting and processing medical data from PDF documents using Google Vision OCR and Gemini AI.

## Features

- **PDF Processing**: Batch processing of multi-page PDF documents
- **OCR Extraction**: Google Vision API for text extraction
- **AI Classification**: Gemini AI for medical data categorization
- **Parallel Processing**: Process 6 pages simultaneously for speed
- **Auto-Summary**: Generate comprehensive medical summaries
- **Database Storage**: PostgreSQL for structured data storage
- **Background Processing**: Non-blocking API with status tracking

## Project Structure

```
fastapi_medical_api/
├── main.py                 # FastAPI application
├── config.py              # Configuration settings
├── models/
│   ├── __init__.py
│   └── schemas.py         # Pydantic models
├── services/
│   ├── __init__.py
│   ├── database_service.py    # PostgreSQL operations
│   ├── gemini_service.py      # Gemini AI integration
│   └── processing_service.py  # Core processing logic
├── uploads/               # PDF storage directory
├── requirements.txt       # Python dependencies
├── .env                  # Environment variables
├── test_api.py           # Testing script
└── README.md            # This file
```

## Setup Instructions

### 1. Prerequisites

- Python 3.9+
- PostgreSQL database
- Google Cloud Vision API credentials
- Google Gemini API key
- Poppler utilities (for PDF processing)

### 2. Install Poppler

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install poppler-utils
```

**macOS:**
```bash
brew install poppler
```

**Windows:**
Download from: https://github.com/oschwartz10612/poppler-windows/releases/

### 3. Clone and Setup

```bash
# Create project directory
mkdir fastapi_medical_api
cd fastapi_medical_api

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create uploads directory
mkdir uploads
```

### 4. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your credentials
nano .env
```

Required environment variables:
- `DATABASE_URL`: PostgreSQL connection string
- `GEMINI_API_KEY`: Your Google Gemini API key
- `GOOGLE_APPLICATION_CREDENTIALS`: Path to Google Cloud service account JSON

### 5. Set Google Cloud Credentials

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account-key.json"
```

### 6. Run the Application

```bash
# Development mode with auto-reload
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Production mode
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

## API Endpoints

### Health Check
```bash
GET /health
```

### Process Document
```bash
POST /process-document
Content-Type: multipart/form-data

Parameters:
- file: PDF file (required)
- patient_id: Patient identifier (required)
- hospital_id: Hospital identifier (required)
```

### Check Document Status
```bash
GET /document-status/{doc_id}
```

### Get Document Summary
```bash
GET /document/{doc_id}/summary
```

### Get Document Pages
```bash
GET /document/{doc_id}/pages
```

### Get Patient Documents
```bash
GET /patient/{patient_id}/documents
```

## Testing

### Basic Test
```bash
# Test health check
curl http://localhost:8000/health

# Process a document
curl -X POST "http://localhost:8000/process-document" \
  -F "file=@sample.pdf" \
  -F "patient_id=PAT123" \
  -F "hospital_id=HOSP456"
```

### Full Test Suite
```bash
# Run test script with a sample PDF
python test_api.py /path/to/sample.pdf
```

## Database Schema

### Tables Created Automatically:
- `patients`: Patient records
- `hospitals`: Hospital information
- `documents`: Uploaded documents metadata
- `pages`: Extracted page data with tags
- `summary_table`: Generated summaries

### Medical Classification Tags:
- `clinical_documentation`: Diagnosis, prescriptions, progress notes
- `investigations/lab_reports`: Lab tests, imaging, pathology
- `treatment/procedures`: Chemotherapy, radiation, surgery records
- `administrative/legal`: Forms, insurance, consent documents
- `other/miscellaneous`: Follow-ups, nursing notes, history

## Processing Flow

1. **Upload**: PDF uploaded via API
2. **Conversion**: PDF converted to images (200 DPI)
3. **Batch Processing**: Pages processed in batches of 6
4. **OCR Extraction**: Google Vision extracts text
5. **AI Classification**: Gemini categorizes medical data
6. **Summary Generation**: Comprehensive summary created
7. **Database Storage**: All data stored in PostgreSQL

## Performance

- **Batch Size**: 6 pages processed simultaneously
- **Processing Time**: ~2 seconds per page
- **Max Pages**: 100 pages per PDF
- **Retry Logic**: 1 retry for failed pages
- **Timeout**: 60 seconds per page

## Error Handling

- Automatic retry for failed OCR/Gemini calls
- Failed pages logged with error messages
- Document status tracking (processing/completed/failed)
- Graceful degradation for partial failures

## Production Deployment

### Using systemd (Linux)

Create service file: `/etc/systemd/system/medical-api.service`
```ini
[Unit]
Description=Medical Data Extraction API
After=network.target

[Service]
Type=exec
User=ubuntu
WorkingDirectory=/path/to/fastapi_medical_api
Environment="PATH=/path/to/venv/bin"
Environment="GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json"
ExecStart=/path/to/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4

[Install]
WantedBy=multi-user.target
```

Start service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable medical-api
sudo systemctl start medical-api
```

### Using Docker

```dockerfile
FROM python:3.9-slim

RUN apt-get update && apt-get install -y poppler-utils

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Using PM2

```bash
pm2 start "uvicorn main:app --host 0.0.0.0 --port 8000" --name medical-api
pm2 save
pm2 startup
```

## Monitoring

Check logs:
```bash
# systemd
sudo journalctl -u medical-api -f

# PM2
pm2 logs medical-api

# Docker
docker logs -f medical-api
```

## Future Enhancements

- [ ] S3/Cloud Storage for PDFs
- [ ] Redis for caching
- [ ] WebSocket for real-time updates
- [ ] MongoDB Atlas for vector search
- [ ] Authentication & API keys
- [ ] Rate limiting
- [ ] Batch upload support
- [ ] Export to DOCX/PDF reports

## Support

For issues or questions, please check the logs and ensure:
1. Database is accessible
2. Google credentials are valid
3. Gemini API key is active
4. Poppler is installed
5. Upload directory has write permissions

## License

Proprietary - Medical Data Extraction Tool