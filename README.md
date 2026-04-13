# Textbook Quiz Generator & Autograder

A local, end-to-end pipeline that takes a PDF textbook and produces a randomized, self-grading quiz system. All LLM inference runs on-device via Ollama — no cloud API keys or usage costs required.

---

## Overview

The project has two parts:

1. **Generation pipeline** — A series of Python scripts that extract text from a PDF, chunk it by chapter, generate questions, produce cited answer keys, and export print-ready PDFs.
2. **Web quiz app** — A lightweight browser-based quiz that samples random questions from the generated answer keys and autogrades responses, using an LLM for short answer evaluation.

---

## Requirements

### Python dependencies
```
conda env create -f environment.yml

conda activate TextbookQuizzer
```

### Local LLM (Ollama)
Install [Ollama](https://ollama.com) and pull the model:
```
ollama pull gemma3:12b
```
The generation pipeline and grading server both expect Ollama to be running and reachable. Update the URLs in `generate_json_questions.py`, `generate_json_answer_keys.py`, and `server.py` if your Ollama instance is on a different host.

### Environment variables
Copy `_env` to `.env` and adjust as needed:
```
CHUNK_SIZE=2500          # Max characters per text chunk
CHUNK_OVERLAP=200        # Overlap between chunks
EMBEDDING_MODEL=all-MiniLM-L6-v2
LLM_MODEL=gemma3:12b
```

---

## Generation Pipeline

Run the following scripts in order. All output is written to a directory of your choice.

### Step 0 — Enter the question_bank_generation directory
```
cd question_bank_generation
```

### Step 1 — Extract and split
```
python extract_and_split.py textbook.pdf out/
```
Parses the PDF using PyMuPDF, detects chapter boundaries from the table of contents (or falls back to heading detection), and splits each chapter into text chunks. Each chunk tracks which page numbers it spans. Outputs `out/chapters_chunked.json`.

### Step 2 — (Optional) Embed and index
```
python index_and_embed.py out/chapters_chunked.json out/index/
```
Encodes all chunks using `all-MiniLM-L6-v2` and builds a FAISS vector index. Prepared for semantic retrieval in future versions; not required for the current pipeline.

### Step 3 — Generate questions
```
python generate_json_questions.py out/chapters_chunked.json out/json/questions/
```
Iterates over every chunk in every chapter and prompts the LLM to generate multiple choice, short answer, and true/false questions. The prompt explicitly prohibits questions that reference figures, diagrams, or the source text directly — questions must stand alone as if the student has no access to the book during the exam.

Outputs one JSON and one Markdown file per chapter.

### Step 4 — Generate answer keys
```
python generate_json_answer_keys.py out/chapters_chunked.json out/json/questions/ out/json/answers/
```
For each question, sends the originating chunk back to the LLM and asks it to produce:
- A direct answer
- A verbatim justification quote from the text
- Page number(s) where the quote appears
- A confidence score (1–4)

If the first pass returns a low-confidence or missing answer, a stricter retry prompt is issued. Answers that still fail validation after the retry are dropped. Outputs one JSON and one Markdown file per chapter.

**Confidence scale:**
| Score | Meaning |
|-------|---------|
| 4 | Explicitly stated verbatim |
| 3 | Clearly implied by the text |
| 2 | Weak or indirect support |
| 1 | Not stated — answer dropped |

### Step 4.5 — Manual review ⚠️
Before proceeding, review the Markdown answer key files in `out/json/answers/`. Despite prompt engineering, some questions may slip through that reference figures, tables, or visual elements from the book that a quiz taker wouldn't have access to. Remove these from the JSON answer key files before generating final output.

### Step 5 — Export PDFs
```
python format_quiz_pdf.py out/json/answers/ out/final_output/
```
For each chapter, generates:
- **Student quiz PDF** — clean question sheet with blank answer lines and true/false checkboxes
- **Instructor answer key PDF** — full answers with page citations, justification quotes, and confidence scores
- **4 randomized sample tests** — random subsets of questions across all three types, each with a matching answer key

---

## Web Quiz App

### Step 0 — Enter the textbook_quiz_app directory
```
cd question_bank_generation
```

### Start the grading server
```
python server.py
```
Runs a Flask server on port 5000. Exposes a single `/autograde` endpoint that accepts a question, answer key entry, and student response, then returns a grading result from the local LLM.

### Serve the frontend
Serve the web directory from a local HTTP server. For example:
```
python -m http.server 8080
```
Then open `index.html` in a browser. Place your generated answer key JSON files in an `answer_keys/` subdirectory relative to the HTML files.

The quiz frontend samples a random subset of questions per session (default: 10 per question type) and grades responses on submission. Short answer questions are sent to the grading server; multiple choice and true/false are graded locally by string comparison.

Post-submission feedback includes:
- Correct/incorrect per question
- The correct answer if wrong
- Textbook page references
- Justification citation from the answer key
- Answer key confidence score

---

## Project Structure

```
generation/
├── _env                          # Environment variable template
├── requirements.txt
├── extract_and_split.py          # Step 1: PDF extraction and chunking
├── index_and_embed.py            # Step 2: FAISS embedding (optional)
├── generate_json_questions.py    # Step 3: Question generation
├── generate_json_answer_keys.py  # Step 4: Answer key generation
└── format_quiz_pdf.py            # Step 5: PDF export

web/
├── index.html                    # Chapter selection page
├── quiz.html                     # Quiz page
├── quiz.js                       # Quiz logic and grading
├── styles.css
├── server.py                     # Flask autograding backend
├── chapters.json                 # Chapter list for the frontend
└── answer_keys/
    ├── chapter_5_answer_key.json
    ├── chapter_6_answer_key.json
    └── ...
```

---

## Pipeline Diagram

```
┌─────────────────────┐
│    PDF Textbook     │
└──────────┬──────────┘
           │ extract_and_split.py
           ▼
┌─────────────────────┐
│   Chapter Chunks    │  chapters_chunked.json
└──────────┬──────────┘
           │ generate_json_questions.py
           ▼
┌─────────────────────┐
│  Question Bank      │  {chapter}_quiz.json
└──────────┬──────────┘
           │ generate_json_answer_keys.py
           ▼
┌──────────────────────────────┐
│  Answer Keys + Citations     │  {chapter}_answers.json
│  (manual review recommended) │
└──────────┬───────────────────┘
           │ format_quiz_pdf.py
           ▼
┌─────────────────────────────────────┐
│  Student PDFs + Instructor PDFs     │
│  + Randomized Sample Tests          │
└─────────────────────────────────────┘
```
