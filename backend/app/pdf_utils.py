import fitz


def extract_text_from_pdf(file_bytes: bytes) -> str:
    pdf = fitz.open(stream=file_bytes, filetype="pdf")

    text = ""

    for page in pdf:
        text += page.get_text()

    pdf.close()

    return text

def extract_pages_from_pdf(file_bytes: bytes):
    document = fitz.open(stream=file_bytes, filetype="pdf")

    pages = []

    for page_index, page in enumerate(document):
        text = page.get_text()

        if text.strip():
            pages.append(
                {
                    "page_number": page_index + 1,
                    "text": text,
                }
            )

    document.close()

    return pages