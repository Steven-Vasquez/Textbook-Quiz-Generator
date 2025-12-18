#!/usr/bin/env python3
"""
generate_questions.py
Usage:
    python generate_questions.py chapters_chunked.json output_dir/
"""

import os, json, time, re
from dotenv import load_dotenv
from tqdm import tqdm
import argparse
import ujson
import requests

load_dotenv()

# LLM call
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
    return data.get("response", "").strip() if "response" in data else json.dumps(data)

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

def extract_json(text):
    candidates = re.findall(r"\{(?:[^{}]|(?:\{[^{}]*\}))*\}", text, flags=re.DOTALL)
    for c in candidates:
        try:
            return json.loads(c)
        except Exception:
            continue
    raise ValueError("No valid JSON object found.")

def normalize_quiz_dict(d):
    fixed = {"mcq": [], "short": [], "true_false": []}
    for k in ["mcq", "short", "true_false"]:
        for item in d.get(k, []):
            if isinstance(item, dict):
                fixed[k].append(item)
            else:
                fixed[k].append({"q": str(item), "options": [] if k=="mcq" else [], "answer": ""})
    return fixed

def generate_for_chapter(chap_key, chap):
    all_chunk_results = []

    for chunk in tqdm(chap["chunks"], desc=f"Generating for {chap_key}", leave=False):
        chunk_id = chunk["chunk_id"]

        prompt = build_question_prompt(chunk["text"], chap["title"])
        text = call_llm(prompt)

        try:
            parsed = json.loads(text)
        except:
            try:
                parsed = extract_json(text)
            except:
                parsed = {"mcq": [], "short": [], "true_false": []}

        parsed = normalize_quiz_dict(parsed)

        # attach chunk_id to every question
        for qtype in ["mcq", "short", "true_false"]:
            for q in parsed.get(qtype, []):
                q["chunk_id"] = chunk_id

        all_chunk_results.append(parsed)
        time.sleep(0.2)

    # Merge chunks
    merged = {"mcq": [], "short": [], "true_false": []}
    for res in all_chunk_results:
        for k in merged.keys():
            merged[k].extend(res.get(k, []))

    return merged


def assign_question_ids(quiz, chapter_id):
    counters = {
        "mcq": 1,
        "short": 1,
        "true_false": 1
    }

    for qtype in ["mcq", "short", "true_false"]:
        for q in quiz.get(qtype, []):
            q["id"] = f"{chapter_id}_{qtype}_{counters[qtype]:03d}"
            counters[qtype] += 1

    return quiz


def save_chapter_quiz(out_dir, chap_key, chap, quiz):
    os.makedirs(out_dir, exist_ok=True)
    out_json = os.path.join(out_dir, f"{chap_key}_quiz.json")
    with open(out_json, "w", encoding="utf-8") as f:
        ujson.dump({"chapter_key": chap_key, "title": chap["title"], "quiz": quiz}, f, indent=2)

    md_lines = [f"# Quiz — {chap['title']}\n"]
    for section, items in [("Multiple Choice", quiz["mcq"]), ("Short Answer", quiz["short"]), ("True / False", quiz["true_false"])]:
        md_lines.append(f"## {section}\n")
        for i, q in enumerate(items, 1):
            md_lines.append(f"**{i}. ({q['id']}) {q['q']}**")
            if section=="Multiple Choice":
                for letter, opt in zip(['A','B','C','D'], q.get("options", [])):
                    md_lines.append(f"- {letter}. {opt}")
    md_path = os.path.join(out_dir, f"{chap_key}_quiz.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
    print("Saved", out_json, md_path)

def main(args):
    with open(args.chapters_json, "r", encoding="utf-8") as f:
        chapters = json.load(f)
    for chap_key, chap in chapters.items():
        quiz = generate_for_chapter(chap_key, chap)
        quiz = assign_question_ids(quiz, chap["chapter_id"])
        save_chapter_quiz(args.out_dir, chap_key, chap, quiz)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("chapters_json")
    parser.add_argument("out_dir")
    args = parser.parse_args()
    main(args)
