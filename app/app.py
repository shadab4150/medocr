import os
import io
import streamlit as st
import pdf2image
from PIL import Image
from google.cloud import vision
from google import genai
from google.genai import types
from google.genai.types import GenerateContentConfig, HttpOptions
import datetime
import hmac
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

#st.title("🏥 Medical Data Extraction Tool")
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

# Initialize clients
@st.cache_resource
def get_vision_client():
    return vision.ImageAnnotatorClient()

@st.cache_resource
def get_gemini_client():
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
            config=GenerateContentConfig(system_instruction=[system_prompt],
                thinking_config=types.ThinkingConfig(thinking_budget=-1))
        )
        
        return response.text
    except Exception as e:
        st.error(f"Image AI Enginer processing failed: {str(e)}")
        return f"Error processing with Gemini: {str(e)}"

def convert_to_jpeg_bytes(image):
    """Convert PIL image to JPEG bytes"""
    img_byte_arr = io.BytesIO()
    if image.mode in ("RGBA", "P"):
        image = image.convert("RGB")
    image.save(img_byte_arr, format='JPEG', quality=95)
    return img_byte_arr.getvalue()


#st.header("Oncology History Notes Processor")

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
- Don't give Starter info like 'Here is the comprehensive medical information extracted from the provided document:', etc. Just The structred results.
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
    #st.header("")
    st.write("<h3 style='text-align: left;'>📄 File Upload</h3>", unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader(
        "Choose a medical document",
        type=["jpg", "jpeg", "png", "pdf", "tiff", "tif"],
        help="Upload PDF or image files containing medical records"
    )
    
    if uploaded_file is not None:
        all_images = []
        
        # Handle different file types
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
        
        # Page selection interface
        if len(all_images) > 1:
            st.header("📑 Page Selection")
            st.write("Select pages to process:")
            
            # Display thumbnails with checkboxes
            cols = st.columns(min(4, len(all_images)))
            selected_pages = []
            
            for i, (img, label) in enumerate(all_images):
                with cols[i % 4]:
                    # Create thumbnail
                    thumbnail = img.copy()
                    thumbnail.thumbnail((100, 100), Image.LANCZOS)
                    
                    st.image(thumbnail, caption=label, use_container_width=True)
                    if st.checkbox(f"{label}", key=f"page_{i}"):
                        selected_pages.append(i)
        
        else:
            selected_pages = [0]  # Single image/page
            st.image(all_images[0][0], caption="Uploaded Document", use_container_width=True)

with col2:
    #st.header("")
    st.write("<h3 style='text-align: center;'>🔬 Processing & Results</h3>", unsafe_allow_html=True)
    
    if uploaded_file is not None and 'selected_pages' in locals():
        if st.button("🚀 Extract Medical Data", type="primary", use_container_width=True):
            if not selected_pages:
                st.warning("Please select at least one page to process.")
            else:
                all_extracted_text = []
                
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
                        status.update(label=f"✅ {label} completed", state="complete")
                
                # Combine all extracted text
                final_output = "\n\n---\n\n".join(all_extracted_text)
                
                # Store in session state for editing
                st.session_state['extracted_text'] = final_output
                st.session_state['original_filename'] = uploaded_file.name
        
        # Text editor section
        if 'extracted_text' in st.session_state:
            st.header("✏️ Edit Extracted Data")

            # Preview section
            with st.expander("👁️ Preview Markdown Output", expanded=True):
                st.markdown(st.session_state['extracted_text'])

            
            with st.expander("👁️ Edit Markdown Output", expanded=False):
                edited_text = st.text_area(
                    "Edit the extracted medical data:",
                    value=st.session_state['extracted_text'],
                    height=400,
                    help="You can modify the extracted text before saving"
                )
            
            # Save functionality
            col_save1, col_save2 = st.columns(2)
            
            with col_save1:
                # Generate filename
                base_name = os.path.splitext(st.session_state['original_filename'])[0]
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{base_name}_extracted_{timestamp}.md"
                
                st.download_button(
                    label="💾 Save as Markdown",
                    data=edited_text,
                    file_name=filename,
                    mime="text/markdown",
                    use_container_width=True
                )
            
            with col_save2:
                if st.button("🔄 Reset to Original", use_container_width=True):
                    st.session_state['extracted_text'] = st.session_state['extracted_text']
                    st.rerun()
            
            # # Preview section
            # with st.expander("👁️ Preview Markdown Output", expanded=True):
            #     st.markdown(edited_text)

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
 