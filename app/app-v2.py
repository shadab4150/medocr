"""
Medical Data Extraction Tool - Main Application
Streamlit app for extracting medical data from images and PDFs
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
from utils.pdf_utils import create_pdf_report

# Load environment variables
load_dotenv()

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


if not check_password():
    st.stop()

if st.button("Logout"):
    st.write(
        """
        <meta http-equiv="refresh" content="0;url=https://chat1.devnagri.dev/mocr/">
        """,
        unsafe_allow_html=True,
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


def extract_text_with_ocr(image_bytes):
    """Extract text using Google Vision OCR"""
    try:
        client = get_vision_client()
        image = vision.Image(content=image_bytes)
        response = client.document_text_detection(image=image)
        
        if response.error.message:
            raise Exception(f"OCR Error: {response.error.message}")
            
        return response.full_text_annotation.text if response.full_text_annotation else ""
    except Exception as e:
        st.error(f"OCR extraction failed: {str(e)}")
        return ""


def process_with_gemini(image_bytes, ocr_text, system_prompt):
    """Process image and text with Gemini API"""
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
        st.error(f"Image AI Engine processing failed: {str(e)}")
        return f"Error processing with Gemini: {str(e)}"


def convert_to_jpeg_bytes(image):
    """Convert PIL image to JPEG bytes"""
    img_byte_arr = io.BytesIO()
    if image.mode in ("RGBA", "P"):
        image = image.convert("RGB")
    image.save(img_byte_arr, format='JPEG', quality=95)
    return img_byte_arr.getvalue()


def process_uploaded_file(uploaded_file):
    """Process different file types and return list of images"""
    all_images = []
    
    if uploaded_file.type == "application/pdf":
        with st.spinner("Converting PDF pages..."):
            images = pdf2image.convert_from_bytes(uploaded_file.read(), dpi=200)
            for i, img in enumerate(images):
                resized_img = resize_image(img)
                all_images.append((resized_img, f"Page {i+1}"))
    
    elif uploaded_file.type in ["image/tiff", "image/tif"]:
        with st.spinner("Processing TIFF pages..."):
            tiff_image = Image.open(io.BytesIO(uploaded_file.read()))
            for i in range(tiff_image.n_frames):
                tiff_image.seek(i)
                page_image = tiff_image.copy().convert("RGB")
                resized_img = resize_image(page_image)
                all_images.append((resized_img, f"Page {i+1}"))
    
    else:
        # Single image file
        image = Image.open(uploaded_file).convert("RGB")
        resized_img = resize_image(image)
        all_images.append((resized_img, "Image"))
    
    return all_images


def create_page_selection_interface(all_images):
    """Create page selection interface with thumbnails and checkboxes"""
    if len(all_images) >= 1:
        st.header("📑 Page Selection")
        st.write("Select pages to process:")
        
        # Add Select All / Deselect All buttons
        col_btn1, col_btn2, col_spacer = st.columns([1, 1, 2])
        
        with col_btn1:
            if st.button("✅ Select All", use_container_width=True):
                for i in range(len(all_images)):
                    st.session_state[f"page_{i}"] = True
                st.rerun()
        
        with col_btn2:
            if st.button("❌ Deselect All", use_container_width=True):
                for i in range(len(all_images)):
                    st.session_state[f"page_{i}"] = False
                st.rerun()
        
        # Display thumbnails with checkboxes
        cols = st.columns(min(4, len(all_images)))
        selected_pages = []
        
        for i, (img, label) in enumerate(all_images):
            with cols[i % 4]:
                # Create thumbnail
                thumbnail = img.copy()
                thumbnail.thumbnail((100, 100), Image.LANCZOS)
                
                st.image(thumbnail, caption=label, use_container_width=True)
                
                # Use session state to maintain checkbox state
                checkbox_key = f"page_{i}"
                if st.checkbox(f"{label}", key=checkbox_key, value=st.session_state.get(checkbox_key, False)):
                    selected_pages.append(i)
        
        return selected_pages
    
    return []


def process_selected_pages(all_images, selected_pages, system_prompt):
    """Process selected pages with OCR and Gemini"""
    all_extracted_text = []
    processed_pages = []
    
    for page_idx in selected_pages:
        img, label = all_images[page_idx]
        
        with st.status(f"Processing {label}...") as status:
            # Convert to bytes for processing
            img_bytes = convert_to_jpeg_bytes(img)
            
            # OCR extraction
            st.write("🔍 Extracting text with OCR...")
            ocr_text = extract_text_with_ocr(img_bytes)
            
            # Gemini processing
            st.write("🤖 Analysing Image + OCR Text with MedOCR Image Engine...")
            extracted_data = process_with_gemini(img_bytes, ocr_text, system_prompt)
            
            all_extracted_text.append(f"## {label}\n\n{extracted_data}")
            processed_pages.append((img, extracted_data, label))
            status.update(label=f"✅ {label} completed", state="complete")
    
    return all_extracted_text, processed_pages


def create_text_editor_interface(final_output, processed_pages, original_filename):
    """Create text editor and save functionality interface"""
    st.header("✏️ Edit Extracted Data")

    # Preview section
    with st.expander("👁️ Preview Markdown Output", expanded=True):
        st.markdown(final_output)

    with st.expander("👁️ Edit Markdown Output", expanded=False):
        edited_text = st.text_area(
            "Edit the extracted medical data:",
            value=final_output,
            height=400,
            help="You can modify the extracted text before saving"
        )

    # Save functionality
    col_save1, col_save2, col_save3 = st.columns(3)
    
    # Generate base filename and timestamp
    base_name = os.path.splitext(original_filename)[0]
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    with col_save1:
        filename = f"{base_name}_extracted_{timestamp}.md"
        st.download_button(
            label="💾 Save as Markdown",
            data=edited_text,
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
            pdf_data = create_pdf_report(updated_pages, pdf_filename)
            st.download_button(
                label="📄 Download PDF",
                data=pdf_data,
                file_name=pdf_filename,
                mime="application/pdf",
                use_container_width=True
            )
        except Exception as e:
            st.error(f"Error creating PDF: {str(e)}")
    
    with col_save3:
        if st.button("🔄 Reset to Original", use_container_width=True):
            st.session_state['extracted_text'] = st.session_state['extracted_text']
            st.rerun()


def main():
    """Main application function"""
    # Sidebar for system instructions
    with st.sidebar:
        st.header("⚙️ System Configuration")
        
        with st.expander("📋 System Instructions", expanded=True):
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

    # Main interface
    col1, col2 = st.columns([1, 1])

    with col1:
        st.write("<h3 style='text-align: left;'>📄 File Upload</h3>", unsafe_allow_html=True)
        
        uploaded_file = st.file_uploader(
            "Choose a medical document",
            type=["jpg", "jpeg", "png", "pdf", "tiff", "tif"],
            help="Upload PDF or image files containing medical records"
        )
        
        if uploaded_file is not None:
            # Process uploaded file
            all_images = process_uploaded_file(uploaded_file)
            
            # Create page selection interface
            selected_pages = create_page_selection_interface(all_images)

    with col2:
        st.write("<h3 style='text-align: center;'>🔬 Processing & Results</h3>", unsafe_allow_html=True)
        
        if uploaded_file is not None and 'selected_pages' in locals():
            if st.button("🚀 Extract Medical Data", type="primary", use_container_width=True):
                if not selected_pages:
                    st.warning("Please select at least one page to process.")
                else:
                    # Process selected pages
                    all_extracted_text, processed_pages = process_selected_pages(
                        all_images, selected_pages, system_prompt
                    )
                    
                    # Combine all extracted text
                    final_output = "\n\n------88888------\n\n".join(all_extracted_text)
                    
                    # Store in session state for editing
                    st.session_state['extracted_text'] = final_output
                    st.session_state['processed_pages'] = processed_pages
                    st.session_state['original_filename'] = uploaded_file.name
            
            # Text editor section
            if 'extracted_text' in st.session_state:
                create_text_editor_interface(
                    st.session_state['extracted_text'],
                    st.session_state['processed_pages'],
                    st.session_state['original_filename']
                )

    # Footer
    st.markdown("---")
    st.markdown(
        """
        <div style='text-align: center; color: #666; font-size: 0.8em;'>
        🏥 Medical Data Extraction Tool | Built for Oncology Department History Notes
        </div>
        """,
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()