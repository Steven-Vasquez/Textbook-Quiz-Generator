#!/usr/bin/env python3
"""
extract_and_split.py
Usage:
    python extract_and_split.py textbook.pdf output_dir/
"""

import os, sys, re, json
import fitz  # PyMuPDF
from tqdm import tqdm
from dotenv import load_dotenv

load_dotenv()

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "2500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))

def get_toc_chapters(doc):
    toc = doc.get_toc(simple=True)
    chapters = []
    for entry in toc:
        # entry: (level, title, page)
        level, title, page = entry
        if re.search(r"\bchapter\b", title, re.I):
            chapters.append((title.strip(), page))
    return chapters

def find_heading_pages(doc):
    # fallback: find pages with "Chapter" heading
    chapters = []
    for pageno in range(len(doc)):
        text = doc[pageno].get_text("text")
        if re.search(r"^\s*chapter\s+\d+", text, re.I | re.M):
            # take first line as title
            first_line = text.strip().splitlines()[0][:120]
            chapters.append((first_line.strip(), pageno+1))
    return chapters

def extract_page_text(doc, start_page, end_page_inclusive):
    text = []
    for p in range(start_page-1, end_page_inclusive):
        text.append(doc[p].get_text("text"))
    return "\n".join(text)

def chunk_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    chunks = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + chunk_size, length)
        chunks.append(text[start:end].strip())
        start = max(end - overlap, end)
        if start >= length:
            break
    return chunks

def extract_pages(doc, start_page, end_page_inclusive):
    pages = []
    for p in range(start_page - 1, end_page_inclusive):
        text = doc[p].get_text("text").strip()
        pages.append({
            "page": p + 1,
            "text": text
        })
    return pages

def chunk_pages(pages, max_chars=CHUNK_SIZE):
    chunks = []
    current_text = ""
    current_pages = set()

    for page in pages:
        page_block = f"\n[PAGE {page['page']}]\n{page['text']}\n"
        if len(current_text) + len(page_block) > max_chars:
            chunks.append({
                "text": current_text.strip(),
                "pages": sorted(current_pages)
            })
            current_text = ""
            current_pages = set()

        current_text += page_block
        current_pages.add(page["page"])

    if current_text.strip():
        chunks.append({
            "text": current_text.strip(),
            "pages": sorted(current_pages)
        })

    return chunks

def main(pdf_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    doc = fitz.open(pdf_path)

    chapters = get_toc_chapters(doc)
    if not chapters:
        chapters = find_heading_pages(doc)
    if not chapters:
        # fallback: single chapter = whole doc
        chapters = [("Full_Book", 1)]

    # sort by page
    chapters = sorted(chapters, key=lambda x: x[1])
    chapter_texts = {}
    for i, (title, start_page) in enumerate(chapters):
        end_page = chapters[i+1][1]-1 if i+1 < len(chapters) else len(doc)
        pages = extract_pages(doc, start_page, end_page)
        chunks = chunk_pages(pages)
        title_safe = re.sub(r"[^\w\-_ ]", "", title).strip().replace(" ", "_")[:80]
        chapter_texts[title_safe] = {
            "title": title,
            "start_page": start_page,
            "end_page": end_page,
            "chunks": chunks
        }

    # save a JSON
    out_path = os.path.join(out_dir, "chapters_chunked.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(chapter_texts, f, indent=2, ensure_ascii=False)
    print("Saved", out_path)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python extract_and_split.py textbook.pdf out_dir")
        sys.exit(1)
    pdf_path = sys.argv[1]
    out_dir = sys.argv[2]
    main(pdf_path, out_dir)
