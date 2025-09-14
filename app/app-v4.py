"""
Medical Data Extraction Tool - Main Application
Streamlit app for extracting medical data from images and PDFs with batch processing
"""

import os
import sys
sys.path.append("./utils")
import io
import streamlit as st
import pdf2image
from PIL import Image
from google.cloud import vision
from google import genai
from google.genai import types
from google.genai.types import GenerateContentConfig
import datetime
import hmac
from dotenv import load_dotenv
import re
from utils.docx_utils import create_docx_report
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# Load environment variables
load_dotenv()

# Constants
MAX_PDF_PAGES = 100
BATCH_SIZE = 8
MAX_RETRIES = 1

# Streamlit App Configuration
st.set_page_config(
    page_title="Medical Data Extraction Tool",
    page_icon="🏥",
    layout="wide"
)
st.write("<h2 style='text-align: center;'>🏥 Medical Data Extraction Tool</h2>", unsafe_allow_html=True)


def check_password():
    """Returns `True` if the user had a correct password."""

    def login_form():
        """Form with widgets to collect user information"""
        with st.form("Credentials"):
            st.text_input("Username", key="username")
            st.text_input("Password", type="password", key="password")
            st.form_submit_button("Log in", on_click=password_entered)

    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if st.session_state["username"] in st.secrets[
            "passwords"
        ] and hmac.compare_digest(
            st.session_state["password"],
            st.secrets.passwords[st.session_state["username"]],
        ):
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Don't store the username or password.
            del st.session_state["username"]
        else:
            st.session_state["password_correct"] = False

    # Return True if the username + password is validated.
    if st.session_state.get("password_correct", False):
        return True

    # Show inputs for username + password.
    login_form()
    if "password_correct" in st.session_state:
        st.error("😕 User not known or password incorrect")
    return False


# if not check_password():
#     st.stop()

# if st.button("Logout"):
#     st.write(
#         """
#         <meta http-equiv="refresh" content="0;url=https://medocr.com">
#         """,
#         unsafe_allow_html=True,
#     )

# UnHide the sidebar Uncomment this markdown code
st.markdown(
    """
    <style>
        section[data-testid="stSidebar"] {display: none !important;}
        div[data-testid="collapsedControl"] {display: none !important;}
    </style>
    """,
    unsafe_allow_html=True
)


@st.cache_resource
def get_vision_client():
    """Initialize and cache Google Vision API client"""
    return vision.ImageAnnotatorClient()


@st.cache_resource
def get_gemini_client():
    """Initialize and cache Gemini API client"""
    return genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


def resize_image(image, max_size=1920):
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


def extract_text_with_ocr(image_bytes, retry_count=0):
    """Extract text using Google Vision OCR with retry logic"""
    try:
        client = get_vision_client()
        image = vision.Image(content=image_bytes)
        response = client.document_text_detection(image=image)
        
        if response.error.message:
            raise Exception(f"OCR Error: {response.error.message}")
            
        return response.full_text_annotation.text if response.full_text_annotation else ""
    except Exception as e:
        if retry_count < MAX_RETRIES:
            time.sleep(1)  # Brief delay before retry
            return extract_text_with_ocr(image_bytes, retry_count + 1)
        else:
            raise Exception(f"OCR extraction failed after {MAX_RETRIES + 1} attempts: {str(e)}")


def process_with_gemini(image_bytes, ocr_text, system_prompt, retry_count=0):
    """Process image and text with Gemini API with retry logic"""
    try:
        client = get_gemini_client()
        
        # Prepare the prompt
        user_prompt = f"""
        DOCUMENT ANALYSIS REQUEST
        -------------------------
        -------------------------
        Please provide a comprehensive markdown extraction of all medical information visible in the image.
        
        You have been provided with:
            1. A medical document image (primary source)
            2. OCR-extracted text from same image by a ocr system.

            YOUR TASK:
            Perform a comprehensive extraction of ALL medical information visible in the image.
            
        OCR REFERENCE TEXT:
        {ocr_text}

        """
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type='image/jpeg',
                ),
                user_prompt
            ],
            config=GenerateContentConfig(
                system_instruction=[system_prompt],
                thinking_config=types.ThinkingConfig(thinking_budget=-1)
            )
        )
        
        return response.text
    except Exception as e:
        if retry_count < MAX_RETRIES:
            time.sleep(1)  # Brief delay before retry
            return process_with_gemini(image_bytes, ocr_text, system_prompt, retry_count + 1)
        else:
            raise Exception(f"Gemini processing failed after {MAX_RETRIES + 1} attempts: {str(e)}")


def generate_summary(all_extracted_text, retry_count=0):
    """Generate a comprehensive summary of all extracted medical data"""
    try:
        client = get_gemini_client()
        
        # Combine all extracted text
        combined_text = "\n\n".join(all_extracted_text)
        
        summary_prompt = """
        MEDICAL DOCUMENT SUMMARY GENERATION
        ==================================
        
        You are tasked with creating a comprehensive medical summary from multiple processed documents of same patient.
        
        REQUIREMENTS:
        - Maximum 300 words
        - Focus on key medical insights, diagnoses, treatments, and patient status
        - Identify patterns and trends across documents
        - Highlight critical information and concerns
        - Use clear, professional medical language
        - Structure with appropriate headers and bullet points
        - DO NOT include patient identifiers or sensitive personal information in the summary
        
        OUTPUT FORMAT:
        Use markdown formatting with clear sections such as:
        - ** Patient Overview** Name, age, etc
        - **Executive Summary**
        - **Key Diagnoses & Conditions**  
        - **Treatment Overview**
        - **Critical Findings**
        - **Recommendations & Follow-up**
        
        Keep the summary concise, actionable, and clinically relevant.
        """
        
        user_prompt = f"""
        Please analyze the following extracted medical data from multiple documents and create a comprehensive summary following the requirements above.
        
        EXTRACTED MEDICAL DATA:
        ========================
        {combined_text}
        """
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[user_prompt],
            config=GenerateContentConfig(
                system_instruction=[summary_prompt],
                thinking_config=types.ThinkingConfig(thinking_budget=-1)
            )
        )
        
        return response.text
    except Exception as e:
        if retry_count < MAX_RETRIES:
            time.sleep(1)  # Brief delay before retry
            return generate_summary(all_extracted_text, retry_count + 1)
        else:
            raise Exception(f"Summary generation failed after {MAX_RETRIES + 1} attempts: {str(e)}")


def convert_to_jpeg_bytes(image):
    """Convert PIL image to JPEG bytes"""
    img_byte_arr = io.BytesIO()
    if image.mode in ("RGBA", "P"):
        image = image.convert("RGB")
    image.save(img_byte_arr, format='JPEG', quality=95)
    return img_byte_arr.getvalue()


def process_single_page(image, label, system_prompt):
    """Process a single page with OCR and Gemini"""
    try:
        # Convert to bytes for processing
        img_bytes = convert_to_jpeg_bytes(image)
        
        # OCR extraction
        ocr_text = extract_text_with_ocr(img_bytes)
        
        # Gemini processing
        extracted_data = process_with_gemini(img_bytes, ocr_text, system_prompt)
        
        return {
            'success': True,
            'image': image,
            'label': label,
            'extracted_data': extracted_data
        }
    except Exception as e:
        return {
            'success': False,
            'image': image,
            'label': label,
            'error': str(e)
        }


def process_files_to_images(uploaded_files):
    """Process multiple uploaded files and convert to list of images"""
    all_images = []
    total_pages = 0
    
    for file_idx, uploaded_file in enumerate(uploaded_files):
        try:
            if uploaded_file.type == "application/pdf":
                # Convert PDF to images
                images = pdf2image.convert_from_bytes(uploaded_file.read(), dpi=200)
                
                # Check page limit
                if total_pages + len(images) > MAX_PDF_PAGES:
                    remaining_allowed = MAX_PDF_PAGES - total_pages
                    st.warning(f"⚠️ PDF '{uploaded_file.name}' has {len(images)} pages. Only processing first {remaining_allowed} pages due to {MAX_PDF_PAGES} page limit.")
                    images = images[:remaining_allowed]
                
                for i, img in enumerate(images):
                    resized_img = resize_image(img)
                    all_images.append((resized_img, f"{uploaded_file.name} - Page {i+1}"))
                    total_pages += 1
                    if total_pages >= MAX_PDF_PAGES:
                        break
            
            elif uploaded_file.type in ["image/tiff", "image/tif"]:
                # Process TIFF pages
                tiff_image = Image.open(io.BytesIO(uploaded_file.read()))
                
                for i in range(tiff_image.n_frames):
                    if total_pages >= MAX_PDF_PAGES:
                        st.warning(f"⚠️ Reached {MAX_PDF_PAGES} page limit. Skipping remaining pages.")
                        break
                        
                    tiff_image.seek(i)
                    page_image = tiff_image.copy().convert("RGB")
                    resized_img = resize_image(page_image)
                    all_images.append((resized_img, f"{uploaded_file.name} - Page {i+1}"))
                    total_pages += 1
            
            else:
                # Single image file
                if total_pages >= MAX_PDF_PAGES:
                    st.warning(f"⚠️ Reached {MAX_PDF_PAGES} page limit. Skipping '{uploaded_file.name}'.")
                    continue
                    
                image = Image.open(uploaded_file).convert("RGB")
                resized_img = resize_image(image)
                all_images.append((resized_img, uploaded_file.name))
                total_pages += 1
                
        except Exception as e:
            st.error(f"❌ Error processing '{uploaded_file.name}': {str(e)}")
            continue
    
    return all_images


def process_pages_in_batches(all_images, system_prompt):
    """Process pages in batches with parallel execution"""
    all_extracted_text = []
    processed_pages = []
    failed_pages = []
    
    total_pages = len(all_images)
    
    # Create progress containers
    progress_bar = st.progress(0)
    status_text = st.empty()
    progress_details = st.empty()
    
    processed_count = 0
    
    # Process in batches
    for batch_start in range(0, total_pages, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, total_pages)
        batch = all_images[batch_start:batch_end]
        batch_num = (batch_start // BATCH_SIZE) + 1
        total_batches = (total_pages + BATCH_SIZE - 1) // BATCH_SIZE
        
        status_text.text(f"📊 Processing Batch {batch_num}/{total_batches} (Pages {batch_start + 1}-{batch_end}/{total_pages})")
        
        # Process batch in parallel
        with ThreadPoolExecutor(max_workers=BATCH_SIZE) as executor:
            # Submit all tasks in the batch
            future_to_page = {
                executor.submit(process_single_page, img, label, system_prompt): (idx + batch_start, img, label)
                for idx, (img, label) in enumerate(batch)
            }
            
            # Process completed tasks as they finish
            for future in as_completed(future_to_page):
                page_idx, img, label = future_to_page[future]
                
                try:
                    result = future.result(timeout=60)  # 60 second timeout per page
                    
                    if result['success']:
                        extracted_data = result['extracted_data']
                        all_extracted_text.append((page_idx, f"## {label}\n\n{extracted_data}"))
                        processed_pages.append((page_idx, img, extracted_data, label))
                        processed_count += 1
                    else:
                        failed_pages.append(f"{label}: {result.get('error', 'Unknown error')}")
                        processed_count += 1
                        
                except Exception as e:
                    failed_pages.append(f"{label}: Timeout or processing error - {str(e)}")
                    processed_count += 1
                
                # Update progress
                progress = processed_count / total_pages
                progress_bar.progress(progress)
                progress_details.text(f"✅ Completed: {processed_count}/{total_pages} pages | ❌ Failed: {len(failed_pages)}")
    
    # Sort results by original page index to maintain order
    all_extracted_text.sort(key=lambda x: x[0])
    processed_pages.sort(key=lambda x: x[0])
    
    # Remove index from sorted results
    all_extracted_text = [text for _, text in all_extracted_text]
    processed_pages = [(img, data, label) for _, img, data, label in processed_pages]
    
    # Clear progress indicators
    progress_bar.empty()
    status_text.empty()
    progress_details.empty()
    
    # Show summary
    if failed_pages:
        with st.expander(f"⚠️ Failed Pages ({len(failed_pages)})", expanded=False):
            for error in failed_pages:
                st.error(error)
    
    st.success(f"✅ Successfully processed {len(processed_pages)}/{total_pages} pages")
    
    return all_extracted_text, processed_pages


def create_text_editor_interface(final_output, processed_pages, original_filenames, summary_text):
    """Create text editor and save functionality interface"""
    st.header("✏️ Edit Extracted Data")

    # Summary section
    st.subheader("📋 Document Summary")
    with st.expander("👁️ View Summary", expanded=True):
        st.markdown(summary_text)
    
    with st.expander("✏️ Edit Summary", expanded=False):
        edited_summary = st.text_area(
            "Edit the document summary:",
            value=summary_text,
            height=300,
            key="summary_editor",
            help="Modify the summary before saving"
        )
        # Update session state if summary is edited
        if edited_summary != summary_text:
            st.session_state['summary_text'] = edited_summary

    st.markdown("---")

    # Full document preview section
    with st.expander("👁️ Preview Full Document", expanded=False):
        st.markdown(final_output)

    with st.expander("✏️ Edit Full Document", expanded=False):
        edited_text = st.text_area(
            "Edit the extracted medical data:",
            value=final_output,
            height=400,
            help="You can modify the extracted text before saving"
        )

    # Save functionality
    col_save1, col_save2, col_save3 = st.columns(3)
    
    # Generate base filename and timestamp
    if len(original_filenames) == 1:
        base_name = os.path.splitext(original_filenames[0])[0]
    else:
        base_name = "combined_documents"
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Get current summary (edited or original)
    current_summary = st.session_state.get('summary_text', summary_text)
    
    with col_save1:
        # Combine summary and full document for markdown download
        full_markdown = f"""# Medical Document Summary

{current_summary}

---

# Detailed Extraction

{edited_text}"""
        
        filename = f"{base_name}_extracted_{timestamp}.md"
        st.download_button(
            label="💾 Save as Markdown",
            data=full_markdown,
            file_name=filename,
            mime="text/markdown",
            use_container_width=True
        )
    
    with col_save2:
        # PDF download button
        pdf_filename = f"{base_name}_report_{timestamp}.pdf"
        
        # Update processed_pages with edited text if needed
        page_texts = edited_text.split("------88888------")
        updated_pages = []
        
        for i, (img, original_text, label) in enumerate(processed_pages):
            if i < len(page_texts):
                # Remove the page header from the text
                page_text = page_texts[i].strip()
                page_text = re.sub(r'^##\s+.*?\n\n', '', page_text)
                updated_pages.append((img, page_text, label))
            else:
                updated_pages.append((img, original_text, label))
        
        try:
            docx_filename = f"{base_name}_report_{timestamp}.docx"
            docx_data = create_docx_report(processed_pages, docx_filename, current_summary)
            st.download_button(
                label="📄 Download Report",
                data=docx_data,
                file_name=docx_filename,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True
            )
        except Exception as e:
            st.error(f"Error creating DOCX: {str(e)}")
    
    with col_save3:
        if st.button("🔄 Reset to Original", use_container_width=True):
            st.session_state['extracted_text'] = st.session_state['original_extracted_text']
            st.session_state['summary_text'] = st.session_state['original_summary_text']
            st.rerun()


def main():
    """Main application function"""
    # Sidebar for system instructions
    with st.sidebar:
        st.header("⚙️ System Configuration")
        
        with st.expander("📋 System Instructions", expanded=False):
            default_system_prompt = """You are an expert medical data extraction system specialized in oncology department history notes.

Your task is to:
1. Read the provided medical document image and OCR text
2. Extract ALL visible medical information comprehensively
3. Structure the information in clean, organized markdown format
4. Maintain all important medical details including:
   - Patient demographics and identifiers
   - Medical history and diagnoses
   - Treatment plans and medications
   - Laboratory results and vital signs
   - Doctor's observations and notes
   - Follow-up instructions
   - Dates and medical facility information

Guidelines:
- Use clear markdown headers and formatting
- Don't give Starter info like 'Here is the comprehensive medical information extracted from the provided document:', etc. Just The structured results.
- Preserve medical terminology exactly as written
- If information is unclear or missing, mark as "Not clearly visible" or "Not provided"
- DO NOT hallucinate or add information not present in the document
- Maintain chronological order when applicable
- Use bullet points and tables where appropriate for clarity

Output the complete medical information in well-structured markdown format."""
            
            system_prompt = st.text_area(
                "System Prompt:",
                value=default_system_prompt,
                height=400,
                help="Instructions for the Gemini model on how to extract medical data"
            )
        
        st.markdown("---")
        st.markdown("### ⚡ Processing Settings")
        st.info(f"""
        • **Batch Size:** {BATCH_SIZE} pages
        • **Max Pages:** {MAX_PDF_PAGES}
        • **Retry on Failure:** {MAX_RETRIES} attempt(s)
        • **Parallel Processing:** Enabled
        • **Summary Generation:** Enabled
        """)

    # Main interface
    st.write("<h3>📄 Upload Medical Documents</h3>", unsafe_allow_html=True)
    
    uploaded_files = st.file_uploader(
        "Choose medical documents (multiple files supported)",
        type=["jpg", "jpeg", "png", "pdf", "tiff", "tif"],
        accept_multiple_files=True,
        help="Upload PDF or image files containing medical records. Multiple files will be combined into one document with an auto-generated summary."
    )
    
    if uploaded_files:
        # Show uploaded files info
        with st.expander("📁 Uploaded Files", expanded=True):
            for file in uploaded_files:
                file_size = len(file.getvalue()) / (1024 * 1024)  # Size in MB
                st.text(f"• {file.name} ({file_size:.2f} MB)")
        
        # Extract button
        if st.button("🚀 Extract Medical Data", type="primary", use_container_width=True):
            try:
                # Process all uploaded files to images
                with st.spinner("📑 Converting files to images..."):
                    all_images = process_files_to_images(uploaded_files)
                
                if not all_images:
                    st.error("❌ No valid images found in uploaded files.")
                else:
                    st.info(f"📊 Total pages to process: {len(all_images)}")
                    
                    # Process pages in batches with parallel execution
                    all_extracted_text, processed_pages = process_pages_in_batches(
                        all_images, system_prompt
                    )
                    
                    if processed_pages:
                        # Generate summary after all pages are processed
                        with st.spinner("📝 Generating comprehensive summary..."):
                            try:
                                summary_text = generate_summary(all_extracted_text)
                                st.success("✅ Summary generated successfully!")
                            except Exception as e:
                                st.error(f"⚠️ Summary generation failed: {str(e)}")
                                summary_text = "**Summary Generation Failed**\n\nUnable to generate summary due to processing error."
                        
                        # Combine all extracted text
                        final_output = "\n\n------88888------\n\n".join(all_extracted_text)
                        
                        # Store in session state for editing
                        st.session_state['extracted_text'] = final_output
                        st.session_state['original_extracted_text'] = final_output
                        st.session_state['summary_text'] = summary_text
                        st.session_state['original_summary_text'] = summary_text
                        st.session_state['processed_pages'] = processed_pages
                        st.session_state['original_filenames'] = [f.name for f in uploaded_files]
                    else:
                        st.error("❌ No pages were successfully processed.")
                        
            except Exception as e:
                st.error(f"❌ Processing error: {str(e)}")
    
    # Text editor section
    if 'extracted_text' in st.session_state and 'summary_text' in st.session_state:
        create_text_editor_interface(
            st.session_state['extracted_text'],
            st.session_state['processed_pages'],
            st.session_state['original_filenames'],
            st.session_state['summary_text']
        )

    # Footer
    st.markdown("---")
    st.markdown(
        """
        <div style='text-align: center; color: #666; font-size: 0.8em;'>
        🏥 Medical Data Extraction Tool | Built for Oncology Department History Notes
        <br>⚡ Batch Processing Enabled | 🔄 Parallel Execution | 📋 Auto Summary Generation
        </div>
        """,
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()