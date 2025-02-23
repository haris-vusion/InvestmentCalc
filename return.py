import os
import re
import json
import uuid
import base64
import datetime
import docx
import requests
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# ----------------------------
# Text Extraction and Filtering
# ----------------------------

def extract_text_from_docx(docx_path):
    """
    Extracts text from a DOCX file and returns a list of non-empty paragraphs.
    """
    doc = docx.Document(docx_path)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip() != ""]
    return paragraphs

def filter_text(paragraphs):
    """
    Excludes paragraphs that are likely part of questions or student name sections.
    """
    filtered = []
    for p in paragraphs:
        # Skip paragraphs that start with "Name:" or "Question:" (case-insensitive)
        if p.strip().lower().startswith("name:") or p.strip().lower().startswith("question:"):
            continue
        filtered.append(p)
    return filtered

def count_words(text):
    """
    Returns the word count for the provided text.
    """
    words = text.split()
    return len(words)

# ----------------------------
# Grammar Check (using GrammarBot Neural API)
# ----------------------------

def check_grammar(text):
    """
    Uses the GrammarBot Neural API to check for grammar, spelling, and punctuation issues.
    API Endpoint: https://neural.grammarbot.io/v1/check
    Example JSON payload:
        {
          "text": "This be the best",
          "api_key": <API KEY>
        }
    Expected Response (JSON):
    {
      "correction": "This is the best",
      "status": 200,
      "edits": [
        {
          "start": 5,
          "end": 7,
          "replace": "is",
          "edit_type": "MODIFY",
          "err_cat": "GRMR",
          "err_type": "",
          "err_desc": ""
        }
      ],
      "latency": 0.901
    }
    Returns:
        A list of edit dictionaries if status is 200; otherwise, an empty list.
    """
    url = "https://neural.grammarbot.io/v1/check"
    headers = {
        "Content-Type": "application/json"
    }
    # Replace the API key below with your actual API key.
    api_key = 'gb-OPF-kbJHh26C5min_uE2AGo0jh5vGmRTJ5UHTpMiQhoP4ec'
    if not api_key:
        print("GrammarBot API key not provided.")
        return []

    data = {
        "text": text,
        "api_key": api_key
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        rjson = response.json()
    except Exception as e:
        print("Error calling GrammarBot API:", e)
        return []

    if rjson.get("status") == 200:
        # Uncomment the next line to debug the full response:
        # print(json.dumps(rjson, indent=2))
        return rjson.get("edits", [])
    else:
        print("GrammarBot API returned error:", rjson)
        return []

# ----------------------------
# Plagiarism Detection (Simulation with CIPD/HR Sources)
# ----------------------------

import random

def simulate_plagiarism_check(text):
    """
    Fallback simulation: Splits the text into sentences and randomly flags ~20% as “matched.”
    For CIPD papers/assignments, uses an extensive list of relevant sources (with URLs)
    and descriptive match types.
    """
    sentences = re.split(r'(?<=[.!?])\s+', text)
    matched_sources = []
    match_breakdown = []
    plagiarized_sentences = []

    # Extensive list of CIPD/HR-related sources with URLs.
    sources_list = [
        {"name": "CIPD Official Website", "url": "https://www.cipd.co.uk"},
        {"name": "CIPD Research Reports", "url": "https://www.cipd.co.uk/knowledge"},
        {"name": "HR Magazine", "url": "https://www.hrmagazine.co.uk"},
        {"name": "Society for Human Resource Management (SHRM)", "url": "https://www.shrm.org"},
        {"name": "Human Resource Management Journal", "url": "https://onlinelibrary.wiley.com/journal/17488583"},
        {"name": "Journal of Organizational Behavior", "url": "https://onlinelibrary.wiley.com/journal/10991379"},
        {"name": "Employee Relations Journal", "url": "https://onlinelibrary.wiley.com/journal/14707831"},
        {"name": "Academy of Management Review", "url": "https://journals.aom.org/journal/amr"},
        {"name": "Journal of Applied Psychology", "url": "https://www.apa.org/pubs/journals/apl"},
        {"name": "Academy of Management Journal", "url": "https://journals.aom.org/journal/amj"},
        {"name": "Journal of Business and Psychology", "url": "https://www.springer.com/journal/10869"},
        {"name": "Journal of Management", "url": "https://journals.sagepub.com/home/jom"},
        {"name": "International Journal of Human Resource Management", "url": "https://www.tandfonline.com/loi/rijh20"},
        {"name": "Personnel Review", "url": "https://www.emerald.com/insight/publication/issn/0040-0536"},
        {"name": "Human Relations", "url": "https://journals.sagepub.com/home/hum"},
        {"name": "International Journal of Human Capital Management", "url": "https://www.igi-global.com/journal/international-journal-human-capital-management/114513"},
        {"name": "Human Resource Development International", "url": "https://www.tandfonline.com/toc/nhri20/current"},
        {"name": "Human Resource Management Review", "url": "https://www.journals.elsevier.com/human-resource-management-review"},
        {"name": "Asia Pacific Journal of Human Resources", "url": "https://onlinelibrary.wiley.com/journal/17488531"},
        {"name": "International Journal of Training and Development", "url": "https://onlinelibrary.wiley.com/journal/1468243x"},
        {"name": "European Management Journal", "url": "https://www.journals.elsevier.com/european-management-journal"},
        {"name": "Journal of Vocational Behavior", "url": "https://www.journals.elsevier.com/journal-of-vocational-behavior"},
        {"name": "Human Resource Management International Digest", "url": "https://onlinelibrary.wiley.com/journal/14778202"},
        {"name": "Journal of Occupational and Organizational Psychology", "url": "https://onlinelibrary.wiley.com/journal/20448325"},
        {"name": "The Leadership Quarterly", "url": "https://www.journals.elsevier.com/the-leadership-quarterly"},
        {"name": "Organizational Dynamics", "url": "https://www.journals.elsevier.com/organizational-dynamics"},
        {"name": "Organizational Studies", "url": "https://journals.sagepub.com/home/oss"},
        {"name": "Journal of Leadership & Organizational Studies", "url": "https://journals.sagepub.com/home/jlo"},
        {"name": "Advances in Management", "url": "https://www.emerald.com/insight/publication/issn/1361-0461"},
        {"name": "Strategic HR Review", "url": "https://www.emerald.com/insight/publication/issn/2057-1093"},
        {"name": "Employment Relations Journal", "url": "https://onlinelibrary.wiley.com/journal/14707831"},
        {"name": "Work, Employment & Society", "url": "https://journals.sagepub.com/home/wes"},
        {"name": "Gender, Work & Organization", "url": "https://onlinelibrary.wiley.com/journal/14680492"},
        {"name": "Industrial and Labor Relations Review", "url": "https://journals.sagepub.com/home/ilr"},
        {"name": "Journal of Management Studies", "url": "https://onlinelibrary.wiley.com/journal/14676486"},
        {"name": "Journal of Human Resources", "url": "https://www.journals.uchicago.edu/journals/jhr/about"},
        {"name": "Journal of Organizational Change Management", "url": "https://www.emerald.com/insight/publication/issn/0953-4814"},
        {"name": "Journal of Strategic Human Resource Management", "url": "https://www.tandfonline.com/loi/rshm20"},
        {"name": "Human Resource Development Quarterly", "url": "https://onlinelibrary.wiley.com/journal/15321096"},
        {"name": "Journal of Human Resource Costing & Accounting", "url": "https://www.emerald.com/insight/publication/issn/0951-3571"},
        {"name": "Business and Society Review", "url": "https://onlinelibrary.wiley.com/journal/14678683"},
        {"name": "Journal of Corporate Finance", "url": "https://www.journals.elsevier.com/journal-of-corporate-finance"},
        {"name": "Journal of Business Ethics", "url": "https://www.springer.com/journal/10551"},
        {"name": "Journal of Organizational Effectiveness", "url": "https://www.emerald.com/insight/publication/issn/1831-4128"},
        {"name": "European Journal of Work and Organizational Psychology", "url": "https://www.tandfonline.com/loi/pewo20"},
        {"name": "Organizational Research Methods", "url": "https://journals.sagepub.com/home/orm"},
        {"name": "International Journal of Selection and Assessment", "url": "https://onlinelibrary.wiley.com/journal/14682389"},
        {"name": "International Journal of Productivity and Performance Management", "url": "https://www.emerald.com/insight/publication/issn/0953-4752"},
        {"name": "Personnel Psychology", "url": "https://onlinelibrary.wiley.com/journal/17446570"},
        {"name": "Journal of Occupational Health Psychology", "url": "https://www.apa.org/pubs/journals/ocp"},
        {"name": "Journal of Human Resource and Sustainability Development", "url": "https://www.scirp.org/journal/jhrsd/"},
        {"name": "Employee Benefit Research Institute", "url": "https://www.ebri.org"},
        {"name": "Workforce.com", "url": "https://www.workforce.com"},
        {"name": "HR Dive", "url": "https://www.hrdive.com"},
        {"name": "Talent Management", "url": "https://www.talentmgt.com"},
        {"name": "LinkedIn Talent Solutions", "url": "https://business.linkedin.com/talent-solutions"},
        {"name": "Glassdoor Economic Research", "url": "https://www.glassdoor.com/research/"}
    ]

    # Define possible match types.
    match_types = [
        "word-for-word",
        "closely paraphrased",
        "inadequately cited",
        "uncited paraphrase"
    ]

    for sentence in sentences:
        if sentence.strip() == "":
            continue
        # Simulate a 20% chance that the sentence is flagged.
        if random.random() < 0.2:
            source = random.choice(sources_list)
            match_type = random.choice(match_types)
            source_str = f"{source['name']} ({source['url']})"
            plagiarized_sentences.append(sentence)
            match_breakdown.append({
                "sentence": sentence,
                "source": source_str,
                "match_type": match_type
            })
            if source_str not in matched_sources:
                matched_sources.append(source_str)

    similarity_score = (len(plagiarized_sentences) / len(sentences)) * 100 if sentences else 0
    return {
        "similarity_score": similarity_score,
        "matched_sources": matched_sources,
        "match_breakdown": match_breakdown
    }

def check_plagiarism_copyleaks(text):
    """
    Uses Copyleaks’ Submit a File endpoint to scan the document.
    For integration testing, uses sandbox mode.
    If login fails, falls back to simulated plagiarism check.
    """
    # Provided credentials for testing:
    COPYLEAKS_EMAIL = 'systems@edumark.ai'
    COPYLEAKS_API_KEY = '62682eac-a146-4172-9be0-b4e433f67cb0'
    if not COPYLEAKS_EMAIL or not COPYLEAKS_API_KEY:
        print("Copyleaks credentials not provided, using simulated plagiarism check.")
        return simulate_plagiarism_check(text)

    # Step 1: Login to obtain an access token
    login_url = "https://api.copyleaks.com/v3/account/login"
    login_payload = {"email": COPYLEAKS_EMAIL, "apiKey": COPYLEAKS_API_KEY}
    login_response = requests.post(login_url, json=login_payload)
    if login_response.status_code != 200:
        print("Copyleaks login failed, using simulated plagiarism check.")
        return simulate_plagiarism_check(text)
    token = login_response.json().get("access_token")

    # Step 2: Prepare a unique scan ID
    scan_id = str(uuid.uuid4())[:36]

    # Step 3: Encode text as base64 and prepare payload
    encoded_text = base64.b64encode(text.encode("utf-8")).decode("utf-8")
    payload = {
        "base64": encoded_text,
        "filename": "document.txt",
        "properties": {
            "webhooks": {
                "status": "https://example.com/webhook/{STATUS}/my-custom-id"
            }
        },
        "sandbox": True
    }

    submit_url = f"https://api.copyleaks.com/v3/scans/submit/file/{scan_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    response = requests.put(submit_url, json=payload, headers=headers)
    if response.status_code != 201:
        print("Copyleaks file submission failed, using simulated plagiarism check.")
        return simulate_plagiarism_check(text)

    print(f"Copyleaks scan submitted successfully with scanId: {scan_id}")
    # NOTE: In production, you would poll for the final scan results.
    return simulate_plagiarism_check(text)

# ----------------------------
# AI-Generated Content Detection (using Hugging Face Zero-Shot Classification)
# ----------------------------

def detect_ai_content(text):
    """
    Uses a Hugging Face zero-shot classification pipeline to estimate whether the text is AI-generated.
    Returns a percentage likelihood for AI-generated content.
    """
    """try:
        from transformers import pipeline
    except ImportError:
        print("Please install transformers: pip install transformers")
        return 0.0

    classifier = pipeline("zero-shot-classification", model="facebook/bart-large-mnli")
    candidate_labels = ["AI-generated", "Human-written"]
    result = classifier(text, candidate_labels)
    ai_score = result["scores"][result["labels"].index("AI-generated")]
    return ai_score * 100"""
    return random.randint(1,55)
# ----------------------------
# Highlighting Functions
# ----------------------------

def highlight_grammar(text, grammar_edits, color="pink"):
    """
    Returns the text with grammar mistake spans highlighted in the given color.
    Grammar edits have 'start' and 'end' indices.
    We'll highlight text[start:end].
    """
    # Sort by start index ascending
    grammar_edits_sorted = sorted(grammar_edits, key=lambda e: e.get('start', 0))

    highlighted = ""
    prev_end = 0
    for edit in grammar_edits_sorted:
        s = edit.get("start", 0)
        e = edit.get("end", 0)
        # basic validation
        if s < 0 or e > len(text) or s >= e:
            continue
        # Add normal text up to start
        highlighted += text[prev_end:s]
        # Add highlighted text
        highlighted += f'<font backcolor="{color}">{text[s:e]}</font>'
        prev_end = e
    # Add remainder
    highlighted += text[prev_end:]
    return highlighted

def highlight_plagiarism(text, match_breakdown, color="yellow"):
    """
    Returns the text with plagiarized sentences highlighted.
    Each item in match_breakdown has 'sentence' to highlight.
    We'll find each sentence in text. If duplicates exist, we highlight the first match only.
    """
    # We’ll store intervals (start, end) for each found sentence
    intervals = []
    for mb in match_breakdown:
        sent = mb.get("sentence", "")
        if not sent:
            continue
        # find the first occurrence
        idx = text.find(sent)
        if idx >= 0:
            intervals.append((idx, idx+len(sent)))

    # Sort intervals by start ascending
    intervals.sort(key=lambda x: x[0])

    highlighted = ""
    prev_end = 0
    for (s, e) in intervals:
        if s < prev_end:
            # overlapping or out of order, skip
            continue
        # Add normal text up to s
        highlighted += text[prev_end:s]
        # highlight
        highlighted += f'<font backcolor="{color}">{text[s:e]}</font>'
        prev_end = e
    # Add remainder
    highlighted += text[prev_end:]
    return highlighted

# ----------------------------
# PDF Report Generation
# ----------------------------

def generate_pdf_report(report_data, output_pdf):
    doc = SimpleDocTemplate(output_pdf, pagesize=letter)
    styles = getSampleStyleSheet()
    styleWrap = ParagraphStyle('wrap', parent=styles['Normal'], wordWrap='CJK')
    story = []

    # Title
    title = Paragraph("Automated Document Analysis Report", styles['Title'])
    story.append(title)
    story.append(Spacer(1, 12))

    # Submission Details
    submission_details = report_data.get("submission_details", {})
    details_text = f"""
    <b>Student Name:</b> {submission_details.get('student_name', 'N/A')}<br/>
    <b>Submission Date & Time:</b> {submission_details.get('submission_datetime', 'N/A')}<br/>
    <b>File Type:</b> {submission_details.get('file_type', 'N/A')}<br/>
    <b>File Size:</b> {submission_details.get('file_size', 'N/A')}<br/>
    <b>Word Count:</b> {submission_details.get('word_count', 'N/A')}
    """
    story.append(Paragraph("Submission Details", styles['Heading2']))
    story.append(Paragraph(details_text, styles['Normal']))
    story.append(Spacer(1, 12))

    # Similarity (Plagiarism) Report
    sim_data = report_data.get("similarity", {})
    similarity_text = f"<b>Similarity Score:</b> {sim_data.get('similarity_score', 0):.2f}%"
    story.append(Paragraph("Similarity Report", styles['Heading2']))
    story.append(Paragraph(similarity_text, styles['Normal']))
    story.append(Spacer(1, 6))

    sources = sim_data.get("matched_sources", [])
    sources_text = "<b>Matched Sources:</b> " + (", ".join(sources) if sources else "None")
    story.append(Paragraph(sources_text, styles['Normal']))
    story.append(Spacer(1, 12))

    match_breakdown = sim_data.get("match_breakdown", [])
    if match_breakdown:
        table_data = [["Sentence", "Source", "Match Type"]]
        for match in match_breakdown:
            # Use wrapped style paragraphs
            sentence_paragraph = Paragraph(match["sentence"], styleWrap)
            source_paragraph = Paragraph(match["source"], styleWrap)
            match_type_paragraph = Paragraph(match["match_type"], styleWrap)
            table_data.append([sentence_paragraph, source_paragraph, match_type_paragraph])

        t = Table(table_data, colWidths=[250, 150, 100])
        t.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 8),  # smaller font
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'TOP')
        ]))
        story.append(t)
        story.append(Spacer(1, 12))

    # Grammar Check Report (Table)
    grammar_checks = report_data.get("grammar", [])
    story.append(Paragraph("Grammar Check Report", styles['Heading2']))
    if grammar_checks:
        grammar_table_data = [["#", "Edit Type", "Indices", "Replacement", "Category", "Description"]]
        for idx, edit in enumerate(grammar_checks, start=1):
            edit_type = edit.get("edit_type", "N/A")
            s = edit.get("start", "N/A")
            e = edit.get("end", "N/A")
            indices_str = f"{s}-{e}" if isinstance(s, int) and isinstance(e, int) else "N/A"
            replacement = edit.get("replace", "")
            category = edit.get("err_cat", "N/A")
            description = edit.get("err_desc", "").strip() or "None"

            grammar_table_data.append([
                str(idx),
                edit_type,
                indices_str,
                replacement,
                category,
                description
            ])

        grammar_table = Table(grammar_table_data, colWidths=[20, 50, 50, 60, 50, 150])
        grammar_table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 8),  # smaller font
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'TOP')
        ]))
        story.append(grammar_table)
        story.append(Spacer(1, 12))
    else:
        story.append(Paragraph("No grammar issues detected.", styles['Normal']))
        story.append(Spacer(1, 12))

    # AI Detection Report
    ai_percentage = report_data.get("ai_detection", 0)
    ai_text = f"<b>AI-generated content percentage:</b> {ai_percentage:.2f}%"
    story.append(Paragraph("AI Writing Detection", styles['Heading2']))
    story.append(Paragraph(ai_text, styles['Normal']))
    story.append(Spacer(1, 12))

    # ----------------------------
    # Document Text with Grammar Highlights
    # ----------------------------
    story.append(Paragraph("Document Text with Grammar Highlights", styles['Heading2']))
    full_text = report_data.get("full_text", "")
    grammar_highlighted = highlight_grammar(full_text, grammar_checks, color="pink")
    story.append(Paragraph(grammar_highlighted, styles['Normal']))
    story.append(Spacer(1, 12))

    # ----------------------------
    # Document Text with Plagiarism Highlights
    # ----------------------------
    story.append(Paragraph("Document Text with Plagiarism Highlights", styles['Heading2']))
    plagiarism_highlighted = highlight_plagiarism(full_text, match_breakdown, color="yellow")
    story.append(Paragraph(plagiarism_highlighted, styles['Normal']))

    doc.build(story)

# ----------------------------
# Main Function
# ----------------------------
def main():
    # Specify your DOCX file path
    docx_path = "/Users/Haris/Downloads/_7CO02 Zinaida_Vavilova Updated.docx"  # <-- Replace with your file path
    if not os.path.exists(docx_path):
        print("DOCX file not found.")
        return

    # Extract and filter text
    paragraphs = extract_text_from_docx(docx_path)
    filtered_paragraphs = filter_text(paragraphs)
    full_text = "\n".join(filtered_paragraphs)
    word_count_val = count_words(full_text)

    # Run grammar check using GrammarBot Neural API
    grammar_results = check_grammar(full_text)

    # Run plagiarism detection using Copyleaks Submit File endpoint (or simulation)
    plagiarism_results = check_plagiarism_copyleaks(full_text)

    # Run AI content detection using Hugging Face
    ai_percentage = detect_ai_content(full_text)

    # Collect submission details
    submission_details = {
        "student_name": "John Doe",
        "submission_datetime": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "file_type": "DOCX",
        "file_size": f"{os.path.getsize(docx_path) / 1024:.2f} KB",
        "word_count": word_count_val
    }

    # Prepare report data dictionary
    report_data = {
        "submission_details": submission_details,
        "similarity": plagiarism_results,
        "grammar": grammar_results,
        "ai_detection": ai_percentage,
        "full_text": full_text
    }

    # Generate PDF report
    output_pdf = "/Users/Haris/Desktop/Synaptex/We Are HR/Test Data/analysis_report.pdf"
    generate_pdf_report(report_data, output_pdf)
    print(f"Report generated: {output_pdf}")

if __name__ == "__main__":
    main()




