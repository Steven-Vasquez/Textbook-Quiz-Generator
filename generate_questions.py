#!/usr/bin/env python3
"""
generate_questions.py
Usage:
    python generate_questions.py chapters_chunked.json output_dir/ --use-index index_dir/   (index optional)
"""

import os, sys, json, time
from dotenv import load_dotenv
from tqdm import tqdm
import argparse
import ujson
import requests
import re

load_dotenv()

# Minimal LLM adapter:
def call_llm(prompt, max_tokens=800, temperature=0.2):
    model = os.getenv("LLM_MODEL")
    url = "http://10.1.3.19:11434/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False
    }

    resp = requests.post(url, json=payload, timeout=1200)

    if resp.status_code != 200:
        raise RuntimeError(f"Local LLM error {resp.status_code}: {resp.text}")

    data = resp.json()

    # Ollama returns {"response":"text", "done":true, ...}
    if "response" in data:
        return data["response"].strip()

    # Fallback for different servers
    return json.dumps(data)

def build_question_prompt(chunk_text, chapter_title, want_mcq=5, want_short=3, want_tf=3):
    return f"""
You are a precise exam generator.

Use ONLY the following excerpt from a textbook chapter.
Chapter title: {chapter_title}

EXCERPT:
\"\"\"{chunk_text}\"\"\"

Generate questions ONLY. Do NOT answer them.

Output JSON:
{{
  "mcq": [ {{ "q": "...", "options": ["A","B","C","D"] }} ],
  "short": [ {{ "q": "..." }} ],
  "true_false": [ {{ "q": "..." }} ]
}}
"""

def merge_chunk_results(chunk_jsons):
    # merge dicts by concatenating lists
    merged = {"mcq": [], "short": [], "true_false": []}
    for res in chunk_jsons:
        for k in ["mcq", "short", "true_false"]:
            merged[k].extend(res.get(k, []))
    return merged

def extract_json(text):
    """
    Safely extract the FIRST valid JSON object from messy LLM output.
    Handles extra commentary, multiple JSON blocks, etc.
    """
    # Find every JSON-like candidate { ... }
    candidates = re.findall(
        r"\{(?:[^{}]|(?:\{[^{}]*\}))*\}",
        text,
        flags=re.DOTALL
    )

    for c in candidates:
        try:
            return json.loads(c)
        except Exception:
            continue

    raise ValueError("No valid JSON object found.")

def normalize_quiz_dict(d):
    """Ensure mcq, short, and true_false arrays contain dicts, not strings or malformed data."""
    fixed = {
        "mcq": [],
        "short": [],
        "true_false": []
    }

    # Normalize MCQ
    for item in d.get("mcq", []):
        if isinstance(item, dict):
            fixed["mcq"].append(item)
        else:
            # fallback if broken
            fixed["mcq"].append({
                "q": str(item),
                "options": [],
                "answer": ""
            })

    # Normalize short answers
    for item in d.get("short", []):
        if isinstance(item, dict):
            fixed["short"].append(item)
        else:
            fixed["short"].append({
                "q": str(item),
                "answer": ""
            })

    # Normalize true/false
    for item in d.get("true_false", []):
        if isinstance(item, dict):
            fixed["true_false"].append(item)

        elif isinstance(item, str):
            # try to split: "Some statement. Answer: True"
            if "answer:" in item.lower():
                parts = re.split(r"(?i)answer:\s*", item, maxsplit=1)
                q = parts[0].strip()
                ans = parts[1].strip()
            else:
                q = item.strip()
                ans = ""
            fixed["true_false"].append({
                "q": q,
                "answer": ans
            })

        else:
            fixed["true_false"].append({
                "q": str(item),
                "answer": ""
            })

    return fixed

def generate_for_chapter(chap_key, chap, use_index=None, index_lookup=None):
    all_chunk_results = []

    for chunk in tqdm(chap["chunks"], desc=f"Generating for {chap_key}", leave=False):
        prompt = build_question_prompt(chunk["text"], chap["title"])

        text = call_llm(prompt)

        # NEW: Robust JSON decoder
        try:
            # Try direct decode
            parsed = json.loads(text)
        except Exception:
            # Try to extract valid JSON block
            try:
                parsed = extract_json(text)
            except Exception:
                # Ultimate fallback with NO crash
                parsed = {
                    "mcq": [],
                    "short": [],
                    "true_false": [
                        {"q": "[PARSE_ERROR] Could not parse model output", "answer": "False"}
                    ]
                }
                
        parsed = normalize_quiz_dict(parsed)
        all_chunk_results.append(parsed)
        time.sleep(0.20)

    return merge_chunk_results(all_chunk_results)

def generate_answers_for_chunk(chunk, questions, chapter_title):
    prompt = build_answer_prompt(chunk["text"], questions, chapter_title)
    text = call_llm(prompt)

    try:
        parsed = extract_json(text)
        return parsed.get("answers", [])
    except Exception:
        return []

def build_answer_prompt(chunk_text, questions, chapter_title):
    return f"""
You are generating an answer key.

Use ONLY the excerpt below. Page markers appear as [PAGE X].
You MUST cite the page number(s) where each answer is found.
If the answer is not explicitly stated, say "Not explicitly stated" and return an empty page list.

EXCERPT:
\"\"\"{chunk_text}\"\"\"

QUESTIONS:
{json.dumps(questions, indent=2)}

Return JSON:
{{
  "answers": [
    {{
      "question": "...",
      "answer": "...",
      "pages": [12]
    }}
  ]
}}
"""

def save_chapter_quiz(out_dir, chap_key, chap, quiz):
    os.makedirs(out_dir, exist_ok=True)

    # JSON output
    out_json = os.path.join(out_dir, f"{chap_key}_quiz.json")
    with open(out_json, "w", encoding="utf-8") as f:
        ujson.dump(
            {"chapter_key": chap_key, "title": chap["title"], "quiz": quiz},
            f,
            indent=2
        )

    # Markdown output
    md_lines = [f"# Quiz — {chap['title']}\n"]

    md_lines.append("## Multiple Choice\n")
    for i, mc in enumerate(quiz["mcq"], 1):
        md_lines.append(f"**{i}. {mc.get('q','')}**")
        opts = mc.get("options", [])
        for letter, opt in zip(['A','B','C','D'], opts):
            md_lines.append(f"- {letter}. {opt}")
        md_lines.append(f"**Answer:** {mc.get('answer','')}\n")

    md_lines.append("## Short Answer\n")
    for i, sa in enumerate(quiz["short"], 1):
        md_lines.append(f"**{i}. {sa.get('q','')}**")
        md_lines.append(f"\nAnswer: {sa.get('answer','')}\n")

    # NEW TRUE/FALSE SECTION
    md_lines.append("## True / False\n")
    for i, tf in enumerate(quiz["true_false"], 1):
        md_lines.append(f"**{i}. {tf.get('q','')}**")
        md_lines.append(f"\nAnswer: {tf.get('answer','')}\n")

    md_path = os.path.join(out_dir, f"{chap_key}_quiz.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print("Saved", out_json, md_path)

def normalize_answer_item(a):
    """
    Ensure answer item is always a dict with question, answer, pages.
    """
    if isinstance(a, dict):
        return {
            "question": a.get("question", ""),
            "answer": a.get("answer", ""),
            "pages": a.get("pages", []) if isinstance(a.get("pages", []), list) else []
        }

    # If LLM returned a raw string
    return {
        "question": "",
        "answer": str(a),
        "pages": []
    }


def save_answer_key(out_dir, chap_key, chap, answers):
    out_json = os.path.join(out_dir, f"{chap_key}_answers.json")
    with open(out_json, "w", encoding="utf-8") as f:
        ujson.dump(
            {
                "chapter_key": chap_key,
                "title": chap["title"],
                "answers": answers
            },
            f,
            indent=2
        )

    md = [f"# Answer Key — {chap['title']}\n"]
    for i, raw in enumerate(answers, 1):
        a = normalize_answer_item(raw)
        
        # TEMP debug
        if not isinstance(a, dict):
            print("[WARN] Non-dict answer item:", type(a), a[:120] if isinstance(a, str) else a)
    
        pages = ", ".join(str(p) for p in a["pages"]) or "N/A"
        md.append(f"**{i}. {a['question']}**")
        md.append(f"Answer: {a['answer']}")
        md.append(f"Pages: {pages}\n")

    md_path = os.path.join(out_dir, f"{chap_key}_answers.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    print("Saved", out_json, md_path)

def main(args):
    
    def extract_all_questions(quiz):
        questions = []
        for mc in quiz.get("mcq", []):
            questions.append(mc.get("q", ""))
        for sa in quiz.get("short", []):
            questions.append(sa.get("q", ""))
        for tf in quiz.get("true_false", []):
            questions.append(tf.get("q", ""))
        return [q for q in questions if q]

    with open(args.chapters_json, "r", encoding="utf-8") as f:
        chapters = json.load(f)

    for chap_key, chap in chapters.items():
        print("Processing chapter:", chap_key)

        # Step B — questions (already implemented)
        quiz = generate_for_chapter(chap_key, chap)
        questions = extract_all_questions(quiz)

        # Step D — answers + citations (NEW)
        answer_key = []
        for chunk in chap["chunks"]:
            answers = generate_answers_for_chunk(
                chunk=chunk,
                questions=questions,
                chapter_title=chap["title"]
            )
            answer_key.extend(answers)

        # Step C — save quiz
        save_chapter_quiz(args.out_dir, chap_key, chap, quiz)

        # Step E — save answer key
        save_answer_key(args.out_dir, chap_key, chap, answer_key)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("chapters_json")
    parser.add_argument("out_dir")
    parser.add_argument("--use-index", default=None, help="index_dir if you want RAG (not used in this base script)")
    args = parser.parse_args()
    main(args)