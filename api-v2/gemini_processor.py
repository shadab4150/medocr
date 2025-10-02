"""
Gemini service for medical data extraction
"""
import time
import json
from google import genai
from google.genai import types
from google.genai.types import GenerateContentConfig
import logging
from pydantic import BaseModel

class GeminiOutput(BaseModel):
    ocr_text: str
    tags: list[str]

class PatientOutput(BaseModel):
    patient_uhid: str
    irch_number: str
    age: str 
    gender: str
    patient_name: str

logger = logging.getLogger(__name__)

class GeminiProcessor:
    def __init__(self, api_key: str, max_retries: int = 3):
        self.client = genai.Client(api_key=api_key)
        self.max_retries = max_retries
        
        # Prompt for extracting patient info from first page
        self.patient_info_prompt = """You are a medical data extraction system.

TASK: Extract patient and hospital identification information from the first page of a medical document.

Extract the following information:
1. Patient UHID (Unique Hospital Identification Number)
2. IRCH Number (Hospital ID / Registration Number)
3. Patient Name (if available)
4. Age (if available)
5. Sex (if available Male/Female)

Look for labels like:
- UHID, Patient ID, Registration No, MR No, Hospital No
- IRCH, Hospital ID, Facility Code
- Name, Patient Name
- Age, Years, DOB (Date of Birth)
- Sex Male or Female

Return JSON format:
{
  "patient_uhid": "extracted UHID or null",
  "irch": "extracted IRCH/Hospital ID or null"
  "patient_name": "extracted Patient Name or null"
  "age": "extracted Age or null",
  "sex": "extracted Male/Female"
}

If information is not clearly visible, return null for that field.
DO NOT hallucinate information."""

        # Prompt for extracting medical data from all pages
        self.extraction_prompt = """You are an expert medical data extraction system specialized in oncology department history notes.

Your task is to:
1. Read the provided medical document image
2. Extract ALL visible medical information comprehensively
3. Classify the document into appropriate medical categories
4. Structure the information in clean, organized markdown format

CLASSIFICATION CATEGORIES (select all that apply):
- clinical_documentation: Diagnosis reports, prescriptions, progress notes, discharge summaries, referrals
- investigations: Lab tests, imaging reports, pathology, genomic tests
- treatment: Chemotherapy charts, radiation records, surgery reports, treatment plans
- administrative: Admission forms, insurance documents, consent forms, correspondence
- other: Follow-up schedules, nursing notes, patient history, anything else

Guidelines:
- Extract ALL visible text comprehensively
- Use clear markdown headers and formatting
- Preserve medical terminology exactly as written
- If information is unclear, mark as "Not clearly visible"
- DO NOT hallucinate or add information not present
- Maintain chronological order when applicable
- Use bullet points and tables where appropriate

Return JSON format:
{
  "ocr_text": "Complete extracted medical information in markdown format",
  "tags": ["applicable", "category", "tags"]
}"""

        # Summary generation prompt
        self.summary_prompt = """MEDICAL DOCUMENT SUMMARY GENERATION
==================================

You are tasked with creating a comprehensive medical summary from multiple processed documents of same patient.

REQUIREMENTS:
- Maximum 250-300 words
- Focus on key medical insights, diagnoses, treatments, and patient status
- Identify patterns and trends across documents
- Highlight critical information and concerns
- Use clear, professional medical language
- Structure with appropriate headers and bullet points
- DO NOT include sensitive personal information in the summary

OUTPUT FORMAT:
Use markdown formatting with clear sections such as:
- **Patient Info** (Name, Age, Address if available)
- **Executive Summary**
- **Key Diagnoses & Conditions**
- **Treatment Overview**
- **Critical Findings**
- **Recommendations & Follow-up**

Keep the summary concise, actionable, and clinically relevant."""

    def extract_patient_info(self, image_bytes: bytes, retry_count: int = 0) -> dict:
        """Extract patient UHID and IRCH from first page"""
        try:
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[
                    types.Part.from_bytes(
                        data=image_bytes,
                        mime_type='image/jpeg',
                    ),
                    "Extract patient UHID and IRCH (hospital ID) from this medical document."
                ],
                config=GenerateContentConfig(
                    system_instruction=[self.patient_info_prompt],
                    response_mime_type="application/json",
                    temperature=0.1,
                    response_schema=PatientOutput
                    
                )
            )
            
            result = json.loads(response.text)
            return result
            
        except Exception as e:
            if retry_count < self.max_retries:
                time.sleep(1)
                return self.extract_patient_info(image_bytes, retry_count + 1)
            else:
                logger.error(f"Patient info extraction failed: {str(e)}")
                return {'patient_uhid': None, 'irch': None}

    def extract_page_data(self, image_bytes: bytes, retry_count: int = 0) -> dict:
        """Extract OCR text and tags from a page"""
        try:
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[
                    types.Part.from_bytes(
                        data=image_bytes,
                        mime_type='image/jpeg',
                    ),
                    "Extract all medical information from this document page and classify it."
                ],
                config=GenerateContentConfig(
                    system_instruction=[self.extraction_prompt],
                    response_mime_type="application/json",
                    temperature=0.1,
                    response_schema=GeminiOutput
                )
            )
            
            result = json.loads(response.text)
            return result
            
        except Exception as e:
            if retry_count < self.max_retries:
                time.sleep(1)
                return self.extract_page_data(image_bytes, retry_count + 1)
            else:
                logger.error(f"Page extraction failed: {str(e)}")
                raise Exception(f"Failed after {self.max_retries} retries: {str(e)}")

    def generate_summary(self, all_pages_text: list, retry_count: int = 0) -> str:
        """Generate comprehensive summary from all extracted text"""
        try:
            combined_text = "\n\n".join(all_pages_text)
            
            user_prompt = f"""
Please analyze the following extracted medical data from multiple documents and create a comprehensive summary.

EXTRACTED MEDICAL DATA:
========================
{combined_text}
"""
            
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[user_prompt],
                config=GenerateContentConfig(
                    system_instruction=[self.summary_prompt],
                    temperature=0.1,
                )
            )
            
            return response.text
            
        except Exception as e:
            if retry_count < self.max_retries:
                time.sleep(1)
                return self.generate_summary(all_pages_text, retry_count + 1)
            else:
                logger.error(f"Summary generation failed: {str(e)}")
                return "**Summary Generation Failed**\n\nUnable to generate summary due to processing error."