"""
Gemini service for medical data extraction and classification
Using exact same settings as app-v4.py
"""
import time
from google import genai
from google.genai import types
from google.genai.types import GenerateContentConfig
import logging

logger = logging.getLogger(__name__)

class GeminiService:
    def __init__(self, api_key: str, max_retries: int = 1):
        self.client = genai.Client(api_key=api_key)
        self.max_retries = max_retries
        
        # System prompt for extraction with classification
        self.extraction_prompt = """You are an expert medical data extraction system specialized in oncology department history notes.

Your task is to:
1. Read the provided medical document image and OCR text
2. Extract ALL visible medical information comprehensively
3. Classify the document into appropriate medical categories
4. Structure the information in clean, organized markdown format

CLASSIFICATION CATEGORIES (select all that apply):
- clinical_documentation: Diagnosis reports, prescriptions, progress notes, discharge summaries, referrals
- investigations/lab_reports: Lab tests, imaging reports, pathology, genomic tests
- treatment/procedures: Chemotherapy charts, radiation records, surgery reports, treatment plans
- administrative/legal: Admission forms, insurance documents, consent forms, correspondence
- other/miscellaneous: Follow-up schedules, nursing notes, patient history, anything else

Guidelines:
- Extract ALL visible text comprehensively
- Use clear markdown headers and formatting
- Don't give starter info, just the structured results
- Preserve medical terminology exactly as written
- If information is unclear, mark as "Not clearly visible"
- DO NOT hallucinate or add information not present
- Maintain chronological order when applicable
- Use bullet points and tables where appropriate

Return a structured JSON with:
{
  "ocr_text": "Complete extracted medical information in markdown format",
  "tags": ["applicable", "category", "tags"]
}"""

        # Summary prompt - same as app-v4.py
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
- DO NOT include patient identifiers or sensitive personal information in the summary

OUTPUT FORMAT:
Use markdown formatting with clear sections such as: Add patient name strictly in Summary If available
- **Patient Info**
    - **Name**
    - **Age**
    - **Address**
- **Patient Overview**
- **Executive Summary**
- **Key Diagnoses & Conditions**  
- **Treatment Overview**
- **Critical Findings**
- **Recommendations & Follow-up**

Keep the summary concise, actionable, and clinically relevant."""
    
    def process_with_gemini(self, image_bytes: bytes, ocr_text: str, retry_count: int = 0) -> dict:
        """Process image and text with Gemini API - returns dict with ocr_text and tags"""
        try:
            user_prompt = f"""
DOCUMENT ANALYSIS REQUEST
-------------------------
-------------------------
Please provide a comprehensive markdown extraction of all medical information visible in the image.

You have been provided with:
    1. A medical document image (primary source)
    2. OCR-extracted text from same image by a ocr system.

YOUR TASK:
Perform a comprehensive extraction of ALL medical information visible in the image and classify into appropriate categories.

OCR REFERENCE TEXT:
{ocr_text}

Return JSON with:
- ocr_text: Complete extracted medical information in markdown format
- tags: Array of applicable category tags
"""
            
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[
                    types.Part.from_bytes(
                        data=image_bytes,
                        mime_type='image/jpeg',
                    ),
                    user_prompt
                ],
                config=GenerateContentConfig(
                    system_instruction=[self.extraction_prompt],
                    response_mime_type="application/json",
                    temperature=0.1,
                    thinking_config=types.ThinkingConfig(thinking_budget=-1)
                )
            )
            
            # Parse JSON response
            import json
            result = json.loads(response.text)
            
            # Ensure we have the required fields
            return {
                'ocr_text': result.get('ocr_text', ocr_text),
                'tags': result.get('tags', ['other/miscellaneous'])
            }
            
        except Exception as e:
            if retry_count < self.max_retries:
                time.sleep(1)
                return self.process_with_gemini(image_bytes, ocr_text, retry_count + 1)
            else:
                logger.error(f"Gemini processing failed: {str(e)}")
                # Return OCR text with default tag on failure
                return {
                    'ocr_text': ocr_text,
                    'tags': ['other/miscellaneous']
                }
    
    def generate_summary(self, all_extracted_text: list, retry_count: int = 0) -> str:
        """Generate comprehensive summary from all extracted text - same as app-v4.py"""
        try:
            # Combine all extracted text
            combined_text = "\n\n".join(all_extracted_text)
            
            user_prompt = f"""
Please analyze the following extracted medical data from multiple documents and create a comprehensive summary following the requirements above.

EXTRACTED MEDICAL DATA:
========================
{combined_text}
"""
            
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[user_prompt],
                config=GenerateContentConfig(
                    system_instruction=[self.summary_prompt],
                    thinking_config=types.ThinkingConfig(thinking_budget=-1)
                )
            )
            
            return response.text
            
        except Exception as e:
            if retry_count < self.max_retries:
                time.sleep(1)
                return self.generate_summary(all_extracted_text, retry_count + 1)
            else:
                error_msg = f"Summary generation failed: {str(e)}"
                logger.error(error_msg)
                return "**Summary Generation Failed**\n\nUnable to generate summary due to processing error."