"""
PDF Utilities Module for Medical Data Extraction Tool
Handles PDF creation and formatting for medical reports with summary page
"""

import io
import datetime
import re
from io import BytesIO
from PIL import Image
from reportlab.lib.pagesizes import landscape, A3
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import Paragraph, Frame
from reportlab.lib.units import inch
from reportlab.lib.colors import black, darkblue, gray


def process_markdown_for_pdf(markdown_text):
    """Convert markdown to formatted paragraphs for PDF"""
    lines = markdown_text.split('\n')
    processed_lines = []
    
    for line in lines:
        line = line.strip()
        if not line:
            processed_lines.append('')
            continue
        
        # First, handle bold text formatting throughout the line
        line = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', line)
        
        # Headers
        if line.startswith('#'):
            # Remove markdown header symbols and make it bold
            header_text = re.sub(r'^#{1,6}\s*', '', line)
            processed_lines.append(f"<b>{header_text}</b>")
        
        # Main bullet points
        elif re.match(r'^\s*[-*+]\s+', line):
            bullet_text = re.sub(r'^\s*[-*+]\s+', '', line)
            processed_lines.append(f"• {bullet_text}")
        
        # Sub-bullet points (indented)
        elif re.match(r'^\s*[o°]\s+', line):
            sub_bullet_text = re.sub(r'^\s*[o°]\s+', '', line)
            processed_lines.append(f"    ○ {sub_bullet_text}")
        
        # Numbered lists
        elif re.match(r'^\s*\d+\.\s+', line):
            numbered_text = re.sub(r'^\s*\d+\.\s+', '', line)
            processed_lines.append(f"• {numbered_text}")
        
        # Regular text (already processed for bold)
        else:
            processed_lines.append(line)
    
    return '\n'.join(processed_lines)


def create_paragraph_styles():
    """Create and return paragraph styles for PDF formatting"""
    styles = getSampleStyleSheet()
    
    # Normal text style
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=8,
        leading=10,
        spaceAfter=3,
        fontName='Helvetica',
        leftIndent=0
    )
    
    # Header style
    header_style = ParagraphStyle(
        'CustomHeader',
        parent=styles['Normal'],
        fontSize=10,
        leading=10,
        spaceAfter=6,
        spaceBefore=4,
        fontName='Helvetica-Bold',
        leftIndent=0
    )
    
    # Bullet style
    bullet_style = ParagraphStyle(
        'CustomBullet',
        parent=styles['Normal'],
        fontSize=8,
        leading=8,
        spaceAfter=3,
        fontName='Helvetica',
        leftIndent=10,
        bulletIndent=0
    )
    
    # Sub-bullet style
    sub_bullet_style = ParagraphStyle(
        'CustomSubBullet',
        parent=styles['Normal'],
        fontSize=8,
        leading=8,
        spaceAfter=2,
        fontName='Helvetica',
        leftIndent=25,
        bulletIndent=15
    )
    
    # Summary styles
    summary_title_style = ParagraphStyle(
        'SummaryTitle',
        parent=styles['Normal'],
        fontSize=16,
        leading=20,
        spaceAfter=12,
        fontName='Helvetica-Bold',
        textColor=darkblue,
        alignment=1  # Center alignment
    )
    
    summary_normal_style = ParagraphStyle(
        'SummaryNormal',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        spaceAfter=6,
        fontName='Helvetica',
        leftIndent=0
    )
    
    summary_header_style = ParagraphStyle(
        'SummaryHeader',
        parent=styles['Normal'],
        fontSize=12,
        leading=16,
        spaceAfter=8,
        spaceBefore=8,
        fontName='Helvetica-Bold',
        textColor=darkblue
    )
    
    return {
        'normal': normal_style,
        'header': header_style,
        'bullet': bullet_style,
        'sub_bullet': sub_bullet_style,
        'summary_title': summary_title_style,
        'summary_normal': summary_normal_style,
        'summary_header': summary_header_style
    }


def create_paragraphs_from_text(formatted_text, styles, is_summary=False):
    """Convert formatted text to ReportLab paragraphs with appropriate styles"""
    paragraphs = []
    lines = formatted_text.split('\n')
    
    # Choose appropriate styles based on whether this is summary or detail
    if is_summary:
        normal_style = styles['summary_normal']
        header_style = styles['summary_header']
        bullet_style = styles['summary_normal']
        sub_bullet_style = styles['summary_normal']
    else:
        normal_style = styles['normal']
        header_style = styles['header']
        bullet_style = styles['bullet']
        sub_bullet_style = styles['sub_bullet']
    
    for line in lines:
        line = line.strip()
        if not line:
            # Add small space for empty lines
            paragraphs.append(Paragraph('<br/>', normal_style))
            continue
        
        # Determine style based on content
        if line.startswith('<b>') and line.endswith('</b>'):
            # Header
            paragraphs.append(Paragraph(line, header_style))
        elif line.startswith('    ○'):
            # Sub-bullet
            clean_line = line.replace('    ○ ', '')
            paragraphs.append(Paragraph(f"○ {clean_line}", sub_bullet_style))
        elif line.startswith('• '):
            # Main bullet
            paragraphs.append(Paragraph(line, bullet_style))
        else:
            # Regular text
            paragraphs.append(Paragraph(line, normal_style))
    
    return paragraphs


def create_summary_page(canvas_obj, page_width, page_height, margin, summary_text, styles):
    """Create a dedicated summary page"""
    # Page title
    canvas_obj.setFont("Helvetica-Bold", 20)
    canvas_obj.setFillColor(darkblue)
    title_y = page_height - margin - 30
    canvas_obj.drawCentredText(page_width/2, title_y, "MEDICAL DOCUMENT SUMMARY")
    canvas_obj.setFillColor(black)
    
    # Add decorative line under title
    canvas_obj.setStrokeColor(darkblue)
    canvas_obj.setLineWidth(2)
    canvas_obj.line(margin + 100, title_y - 10, page_width - margin - 100, title_y - 10)
    
    # Process summary text for PDF formatting
    formatted_summary = process_markdown_for_pdf(summary_text)
    summary_paragraphs = create_paragraphs_from_text(formatted_summary, styles, is_summary=True)
    
    # Create full-width frame for summary
    summary_frame = Frame(
        margin + 50,  # Extra margin for better appearance
        margin + 60,  # Leave space for footer
        page_width - (2 * margin) - 100,  # Full width minus margins
        page_height - margin - 120,  # Account for title and footer space
        leftPadding=20,
        rightPadding=20,
        topPadding=20,
        bottomPadding=20,
        showBoundary=1  # Show border around summary
    )
    
    # Add summary paragraphs to frame
    try:
        remaining = summary_frame.addFromList(summary_paragraphs, canvas_obj)
        if remaining:
            # If summary is too long, add continuation note
            canvas_obj.setFont("Helvetica-Italic", 8)
            canvas_obj.setFillColor(gray)
            canvas_obj.drawString(margin + 60, margin + 40, "Summary truncated to fit page. See detailed extraction for complete information.")
            canvas_obj.setFillColor(black)
    except Exception as e:
        # Fallback to simple text if frame fails
        canvas_obj.setFont("Helvetica", 10)
        y_pos = title_y - 60
        lines = formatted_summary.split('\n')
        
        for line in lines[:30]:  # Limit to prevent overflow
            if y_pos < margin + 80:
                break
            canvas_obj.drawString(margin + 60, y_pos, line[:100])  # Truncate long lines
            y_pos -= 14
    
    # Add generation timestamp at bottom
    canvas_obj.setFont("Helvetica-Italic", 8)
    canvas_obj.setFillColor(gray)
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    canvas_obj.drawCentredText(page_width/2, margin + 20, f"Summary generated on {timestamp}")
    canvas_obj.setFillColor(black)


def draw_image_on_canvas(canvas_obj, image, image_width, content_height, margin):
    """Draw image on the left side of the canvas"""
    try:
        # Convert PIL image to bytes for ReportLab
        img_buffer = BytesIO()
        if image.mode in ("RGBA", "P"):
            image = image.convert("RGB")
        image.save(img_buffer, format='JPEG', quality=85)
        img_buffer.seek(0)
        
        # Calculate image dimensions to fit in left half
        img_width, img_height = image.size
        aspect_ratio = img_width / img_height
        
        # A3 gives us more space, so we can make image larger
        max_img_height = content_height - 20
        max_img_width = image_width - 20
        
        if aspect_ratio > (max_img_width / max_img_height):
            # Image is wider - fit to width
            display_width = max_img_width
            display_height = max_img_width / aspect_ratio
        else:
            # Image is taller - fit to height
            display_height = max_img_height
            display_width = max_img_height * aspect_ratio
        
        # Center the image in left half
        img_x = margin + (image_width - display_width) / 2
        img_y = margin + (content_height - display_height) / 2
        
        canvas_obj.drawImage(ImageReader(img_buffer), img_x, img_y, 
                           width=display_width, height=display_height)
        
        # Add border around image for clarity
        canvas_obj.setStrokeColor('gray')
        canvas_obj.setLineWidth(0.5)
        canvas_obj.rect(img_x, img_y, display_width, display_height)
        
        return True
        
    except Exception as e:
        # If image fails, draw error message
        canvas_obj.setFont("Helvetica", 12)
        canvas_obj.drawString(margin + 10, content_height/2 + margin, f"Image loading error: {str(e)}")
        return False


def draw_page_header(canvas_obj, page_width, page_height, margin, title_text):
    """Draw page header"""
    # Add page title
    canvas_obj.setFont("Helvetica-Bold", 16)
    canvas_obj.drawString(margin, page_height - margin + 10, title_text)
    
    # Add A3 size indicator
    canvas_obj.setFont("Helvetica", 8)
    canvas_obj.drawString(page_width - 100, page_height - margin + 10, "[A3 Format]")


def draw_page_footer(canvas_obj, page_width, margin, page_label, page_num, is_continuation=False, continuation_num=0):
    """Draw page footer"""
    canvas_obj.setFont("Helvetica", 8)
    canvas_obj.setFillColor('gray')
    footer_text = f"Generated on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {page_label}"
    if is_continuation:
        footer_text += f" (continuation {continuation_num + 1})"
    footer_text += " | A3 Landscape Format"
    canvas_obj.drawString(margin, margin - 5, footer_text)
    canvas_obj.setFillColor('black')
    
    # Add page number on right
    canvas_obj.drawRightString(page_width - margin, margin - 5, f"Page {page_num}")


def create_pdf_report(images_and_texts, filename, summary_text=None):
    """Create a PDF report with optional summary page and images on left and text on right using A3 size"""
    buffer = BytesIO()
    
    # Create PDF with A3 landscape orientation - much more space!
    page_width, page_height = landscape(A3)
    c = canvas.Canvas(buffer, pagesize=landscape(A3))
    
    # Define layout dimensions - adjusted for A3
    margin = 0.5 * inch
    image_width = (page_width / 2) - (1.5 * margin)
    text_width = (page_width / 2) - (1.5 * margin)
    content_height = page_height - (2 * margin)
    
    # Get paragraph styles
    styles = create_paragraph_styles()
    
    current_page_num = 1
    
    # Create summary page if summary text is provided
    if summary_text and summary_text.strip():
        create_summary_page(c, page_width, page_height, margin, summary_text, styles)
        
        # Draw footer for summary page
        c.setFont("Helvetica", 8)
        c.setFillColor('gray')
        footer_text = f"Generated on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Document Summary | A3 Landscape Format"
        c.drawString(margin, margin - 5, footer_text)
        c.drawRightString(page_width - margin, margin - 5, f"Page {current_page_num}")
        c.setFillColor('black')
        
        # Start new page for detailed content
        c.showPage()
        current_page_num += 1
    
    # Process each document page
    for item_num, (image, extracted_text, page_label) in enumerate(images_and_texts, 1):
        # Process markdown for PDF
        formatted_text = process_markdown_for_pdf(extracted_text)
        
        # Create paragraphs with appropriate styles
        paragraphs = create_paragraphs_from_text(formatted_text, styles)
        
        # Track if this is the first page of this item
        is_first_page = True
        remaining_paragraphs = paragraphs.copy()
        continuation_page_num = 0
        
        while remaining_paragraphs:
            # Add new page if needed (for continuation pages or new items)
            if not is_first_page or (current_page_num > 1 and is_first_page and not summary_text):
                c.showPage()
                current_page_num += 1
            elif current_page_num > 1 and is_first_page and summary_text:
                # Already on a new page after summary
                pass
            
            # Draw page header
            if is_first_page:
                title_text = f"Medical Data Extraction - {page_label}"
            else:
                continuation_page_num += 1
                title_text = f"Medical Data Extraction - {page_label} (continued - page {continuation_page_num + 1})"
            
            draw_page_header(c, page_width, page_height, margin, title_text)
            
            # Left side - Image (only on first page of this item)
            if is_first_page:
                draw_image_on_canvas(c, image, image_width, content_height, margin)
            else:
                # On continuation pages, add a note in the left column
                c.setFont("Helvetica-Italic", 10)
                c.setFillColor('gray')
                c.drawString(image_width/2, page_height/2, "[Image shown on first page]")
                c.setFillColor('black')
            
            # Draw vertical separator line
            c.setStrokeColor('gray')
            c.setLineWidth(0.5)
            c.line(page_width/2, margin, page_width/2, page_height - margin - 20)
            
            # Right side - Text
            text_x = (page_width / 2) + margin
            
            # Create text frame for right half - with more space on A3
            text_frame = Frame(
                text_x, 
                margin + 30,  # Leave space for footer
                text_width, 
                content_height - 50,  # Adjusted for header and footer
                leftPadding=15, 
                rightPadding=15, 
                topPadding=10, 
                bottomPadding=10
            )
            
            # Add paragraphs to frame and get any that don't fit
            try:
                remaining_paragraphs = text_frame.addFromList(remaining_paragraphs, c)
                
                # If there are remaining paragraphs, we'll need another page
                if remaining_paragraphs:
                    is_first_page = False
                    # Add continuation indicator at bottom
                    c.setFont("Helvetica-Italic", 8)
                    c.setFillColor('gray')
                    c.drawString(text_x + 10, margin + 15, "... continued on next page")
                    c.setFillColor('black')
                else:
                    # All paragraphs fit, move to next item
                    break
                    
            except Exception as frame_error:
                # Fallback: simple text drawing if frame fails
                print(f"Frame error: {frame_error}")  # Debug info
                
                c.setFont("Helvetica", 9)
                text_y_start = page_height - margin - 40
                y_position = text_y_start
                line_height = 12
                max_lines_per_page = int((content_height - 60) / line_height)
                
                lines_drawn = 0
                remaining_lines = []
                
                # Convert paragraphs to plain text lines
                for para in remaining_paragraphs:
                    if hasattr(para, 'text'):
                        # Clean HTML tags
                        text = para.text.replace('<b>', '').replace('</b>', '').replace('<br/>', '')
                        if text.strip():
                            remaining_lines.append(text)
                
                for i, line in enumerate(remaining_lines):
                    if lines_drawn >= max_lines_per_page:
                        # Need a new page for remaining text
                        remaining_paragraphs = [Paragraph(l, styles['normal']) for l in remaining_lines[i:]]
                        is_first_page = False
                        c.setFont("Helvetica-Italic", 8)
                        c.setFillColor('gray')
                        c.drawString(text_x + 10, margin + 15, "... continued on next page")
                        c.setFillColor('black')
                        break
                    
                    # Truncate very long lines to fit in A3 width
                    max_chars = 120  # More space on A3
                    if len(line) > max_chars:
                        line = line[:max_chars-3] + "..."
                    
                    c.drawString(text_x + 15, y_position, line)
                    y_position -= line_height
                    lines_drawn += 1
                else:
                    # All lines drawn
                    remaining_paragraphs = []
            
            # Draw page footer
            draw_page_footer(c, page_width, margin, page_label, current_page_num, 
                           not is_first_page, continuation_page_num)
            
            # If no more paragraphs remain, we're done with this item
            if not remaining_paragraphs:
                break
            
            current_page_num += 1
    
    # Save PDF
    c.save()
    buffer.seek(0)
    return buffer.getvalue()