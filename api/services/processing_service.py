"""
Core processing service - maintains exact logic from app-v4.py
"""
import io
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from google.cloud import vision
from PIL import Image
import pdf2image
import logging

logger = logging.getLogger(__name__)

class ProcessingService:
    def __init__(self, gemini_service, batch_size=6, max_retries=1, max_pdf_pages=100):
        self.vision_client = vision.ImageAnnotatorClient()
        self.gemini_service = gemini_service
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.max_pdf_pages = max_pdf_pages

    def resize_image(self, image: Image.Image, max_size: int = 1920) -> Image.Image:
        """Resize image while preserving aspect ratio - same as app-v4.py"""
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

    def convert_to_jpeg_bytes(self, image: Image.Image) -> bytes:
        """Convert PIL image to JPEG bytes - same as app-v4.py"""
        img_byte_arr = io.BytesIO()
        if image.mode in ("RGBA", "P"):
            image = image.convert("RGB")
        image.save(img_byte_arr, format='JPEG', quality=95)
        return img_byte_arr.getvalue()

    def extract_text_with_ocr(self, image_bytes: bytes, retry_count: int = 0) -> str:
        """Extract text using Google Vision OCR with retry logic - same as app-v4.py"""
        try:
            image = vision.Image(content=image_bytes)
            response = self.vision_client.document_text_detection(image=image)

            if response.error.message:
                raise Exception(f"OCR Error: {response.error.message}")

            return response.full_text_annotation.text if response.full_text_annotation else ""

        except Exception as e:
            if retry_count < self.max_retries:
                time.sleep(1)
                return self.extract_text_with_ocr(image_bytes, retry_count + 1)
            else:
                raise Exception(f"OCR extraction failed after {self.max_retries + 1} attempts: {str(e)}")

    def convert_pdf_to_images(self, file_path: str) -> list:
        """Convert PDF to list of PIL images with labels"""
        try:
            images = pdf2image.convert_from_path(file_path, dpi=200)

            # Check page limit - same as app-v4.py
            if len(images) > self.max_pdf_pages:
                logger.warning(f"PDF has {len(images)} pages. Limiting to {self.max_pdf_pages}")
                images = images[:self.max_pdf_pages]

            # Create labeled images
            labeled_images = []
            for i, img in enumerate(images):
                resized_img = self.resize_image(img)
                label = f"Page {i+1}"
                labeled_images.append((resized_img, label))

            logger.info(f"Converted PDF to {len(labeled_images)} images")
            return labeled_images

        except Exception as e:
            logger.error(f"Error converting PDF: {str(e)}")
            raise

    def process_single_page(self, image: Image.Image, label: str) -> dict:
        """Process a single page with OCR and Gemini - same logic as app-v4.py"""
        try:
            # Convert to bytes for processing
            img_bytes = self.convert_to_jpeg_bytes(image)

            # OCR extraction
            ocr_text = self.extract_text_with_ocr(img_bytes)

            # Gemini processing with classification
            result = self.gemini_service.process_with_gemini(img_bytes, ocr_text)

            return {
                'success': True,
                'label': label,
                'ocr_text': result['ocr_text'],
                'tags': result['tags'],
                'extracted_data': result['ocr_text']  # For summary generation
            }

        except Exception as e:
            logger.error(f"Error processing page {label}: {str(e)}")
            return {
                'success': False,
                'label': label,
                'error': str(e)
            }

    async def process_pages_in_batches(self, all_images: list, doc_id: int, patient_id: str,
                                      hospital_id: str, filename: str, file_path: str, db_service) -> tuple:
        """Process pages in batches with parallel execution - same as app-v4.py"""
        all_extracted_text = []
        processed_count = 0
        failed_count = 0
        total_pages = len(all_images)

        logger.info(f"Starting batch processing for {total_pages} pages")

        # Process in batches - same logic as app-v4.py
        for batch_start in range(0, total_pages, self.batch_size):
            batch_end = min(batch_start + self.batch_size, total_pages)
            batch = all_images[batch_start:batch_end]
            batch_num = (batch_start // self.batch_size) + 1
            total_batches = (total_pages + self.batch_size - 1) // self.batch_size

            logger.info(f"Processing Batch {batch_num}/{total_batches} (Pages {batch_start + 1}-{batch_end}/{total_pages})")

            # Process batch in parallel - same as app-v4.py
            with ThreadPoolExecutor(max_workers=self.batch_size) as executor:
                # Submit all tasks in the batch
                future_to_page = {
                    executor.submit(self.process_single_page, img, label): (idx + batch_start, img, label)
                    for idx, (img, label) in enumerate(batch)
                }

                # Process completed tasks as they finish
                for future in as_completed(future_to_page):
                    page_idx, img, label = future_to_page[future]

                    try:
                        result = future.result(timeout=60)  # 60 second timeout per page

                        if result['success']:
                            # Store successful page in documents table
                            await db_service.create_document_record(
                                doc_id, page_idx + 1, patient_id, hospital_id, filename, "PLACEHOLDER", total_pages,
                                result['ocr_text']
                            )
                            # Add to extracted text for summary generation (no page-level summary)
                            all_extracted_text.append((page_idx, f"## {label}\n\n{result['extracted_data']}"))
                            processed_count += 1

                        else:
                            # Store failed page in documents table
                            await db_service.create_document_record(
                                doc_id, page_idx + 1, patient_id, hospital_id, filename, "PLACEHOLDER", total_pages
                            )
                            failed_count += 1

                    except Exception as e:
                        # Store timeout/error page in documents table
                        await db_service.create_document_record(
                            doc_id, page_idx + 1, patient_id, hospital_id, filename, "PLACEHOLDER", total_pages
                        )
                        failed_count += 1

        # Sort results by original page index to maintain order - same as app-v4.py
        all_extracted_text.sort(key=lambda x: x[0])

        # Remove index from sorted results
        all_extracted_text = [text for _, text in all_extracted_text]

        logger.info(f"Batch processing completed: {processed_count} successful, {failed_count} failed")
        return all_extracted_text, processed_count

    async def process_pdf_background(self, doc_id: int, file_path: str, patient_id: str,
                                    hospital_id: str, filename: str, db_service):
        """Background processing pipeline for PDF"""
        try:
            logger.info(f"Starting background processing for doc_id: {doc_id}")

            # 1. Convert PDF to images
            all_images = self.convert_pdf_to_images(file_path)

            # 2. Process pages in batches
            all_extracted_text, processed_count = await self.process_pages_in_batches(
                all_images, doc_id, patient_id, hospital_id, filename, file_path, db_service
            )

            # 3. Generate summary ONLY after all pages are processed
            if all_extracted_text:
                try:
                    summary_text = self.gemini_service.generate_summary(all_extracted_text)
                    await db_service.create_summary_record(patient_id, hospital_id, summary_text)
                    logger.info(f"Summary generated for doc_id: {doc_id}")
                except Exception as e:
                    logger.error(f"Summary generation failed for doc_id {doc_id}: {str(e)}")

            # 4. Update document status
            if processed_count > 0:
                await db_service.update_document_status(doc_id, 'completed')
                logger.info(f"Document {doc_id} processing completed successfully")
            else:
                await db_service.update_document_status(doc_id, 'failed')
                logger.error(f"Document {doc_id} processing failed - no pages processed")

        except Exception as e:
            logger.error(f"Background processing failed for doc_id {doc_id}: {str(e)}")
            await db_service.update_document_status(doc_id, 'failed')