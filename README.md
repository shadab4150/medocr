# 🏥 Medical Data Extraction Tool

A Streamlit-based application for extracting structured medical data from images and PDF documents using Google Vision OCR and Gemini AI.

---

## Features

- **Upload & Process Medical Records:**  
  Upload PDF, JPG, PNG, or TIFF files containing medical records, including multi-page PDFs and scanned images.

- **OCR & AI-Powered Extraction:**  
  Uses Google Vision API for OCR and Gemini AI for comprehensive, structured extraction of medical information.

- **Interactive Page Selection:**  
  Preview and select specific pages from uploaded documents for processing.

- **Editable Results:**  
  Review and edit extracted data in markdown format before saving or exporting.

- **Export as Markdown or PDF:**  
  Download the extracted data as a markdown file or a professionally formatted A3 landscape PDF report (with original document image and extracted text side-by-side).

- **Secure Access:**  
  Password-protected login for authorized use.

---

## Quick Start

### Prerequisites

- Python 3.8+
- Google Cloud Vision API credentials
- Gemini AI API key
- [Streamlit](https://streamlit.io/)
- Required Python packages (see below)

### Installation

1. **Clone the Repository**

    ```bash
    git clone https://github.com/yourusername/medical-data-extraction-tool.git
    cd medical-data-extraction-tool
    ```

2. **Install Dependencies**

    ```bash
    pip install -r requirements.txt
    ```

3. **Environment Setup**

    - Copy `.env.example` to `.env` and add your API keys:

      ```
      GEMINI_API_KEY=your-gemini-api-key
      GOOGLE_APPLICATION_CREDENTIALS=path/to/your/google/vision/credentials.json
      ```

    - Add your user credentials to `.streamlit/secrets.toml`:

      ```toml
      [passwords]
      your_username = "your_password"
      ```

4. **Run the App**

    ```bash
    streamlit run app-v2.py
    ```

    The app will launch in your default browser.

---

## File Structure

```
.
├── app-v2.py            # Streamlit main application
├── utils/
│   └── pdf_utils.py     # PDF creation and formatting utilities
├── requirements.txt     # Python dependencies
├── .env                 # API keys and environment variables
├── .streamlit/
│   └── secrets.toml     # User credentials for authentication
└── README.md
```

---

## Usage

1. **Login:**  
   Enter your username and password.

2. **Upload Document:**  
   Select a PDF or image file. Multi-page PDFs and TIFFs are supported.

3. **Select Pages:**  
   Preview and choose which pages to process.

4. **Extract Data:**  
   Click "Extract Medical Data" to run OCR and AI extraction.

5. **Review & Edit:**  
   Edit the markdown result as needed.

6. **Download:**  
   Save the extracted data as either a markdown file or a formatted PDF report.

---

## Customization

- **System Prompt:**  
  Customize the extraction instructions for Gemini AI via the sidebar to target specific medical domains or report styles.

- **PDF Layout:**  
  Modify `utils/pdf_utils.py` to adjust PDF formatting, fonts, or page size.

---

## Dependencies

- [Streamlit](https://streamlit.io/)
- [Google Cloud Vision](https://cloud.google.com/vision)
- [Google Gemini AI](https://ai.google.dev/)
- [pdf2image](https://github.com/Belval/pdf2image)
- [Pillow](https://python-pillow.org/)
- [ReportLab](https://www.reportlab.com/)
- [python-dotenv](https://github.com/theskumar/python-dotenv)

See `requirements.txt` for the full list.

---

## Security

- User authentication via credentials in `.streamlit/secrets.toml`.
- **Do not share your API keys or credentials publicly.**

---

## License

This project is for internal.
---

## Acknowledgments

- Built for oncology department history notes and general medical records extraction.

---

## Contact

For questions or support, please open an issue or contact [your email/contact here].
