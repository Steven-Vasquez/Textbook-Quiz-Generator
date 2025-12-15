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

def build_prompt_for_chunk(chunk_text, chapter_title, want_mcq=10, want_short=5, want_tf=5):
    # Use a concise, deterministic prompt template
    return f"""
You are a precise exam generator. Use ONLY the following excerpt from a chapter of a textbook.
Chapter title: {chapter_title}

EXCERPT:
\"\"\"{chunk_text[:6000]}\"\"\"\

Deliver:
1) {want_mcq} multiple-choice questions with 4 options each. Mark the correct answer with [ANSWER: X] on the same line.
2) {want_short} short-answer questions (1-3 sentence answer). Provide the answer.
3) {want_tf} true/false questions. Provide the answer as "True" or "False".

Output format: JSON with keys:
"mcq": [ {{ "q": "...", "options": ["A...", "B...", "C...", "D..."], "answer": "B" }} ],
"short": [ {{ "q":"", "answer":"" }} ],
"true_false": [ {{ "q":"", "answer":"True" }} ]

Be concise and do not add extra commentary.
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
        prompt = build_prompt_for_chunk(chunk, chap["title"])
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

def main(args):
    with open(args.chapters_json, "r", encoding="utf-8") as f:
        chapters = json.load(f)

    for chap_key, chap in chapters.items():
        print("Processing chapter:", chap_key)
        quiz = generate_for_chapter(chap_key, chap)
        save_chapter_quiz(args.out_dir, chap_key, chap, quiz)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("chapters_json")
    parser.add_argument("out_dir")
    parser.add_argument("--use-index", default=None, help="index_dir if you want RAG (not used in this base script)")
    args = parser.parse_args()
    main(args)
