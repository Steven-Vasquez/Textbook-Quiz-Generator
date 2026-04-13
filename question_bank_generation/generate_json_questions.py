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
import random

load_dotenv()

def shuffle_mcq_options(quiz, seed_prefix="mcq"):
    """
    Deterministically shuffle MCQ options per question to avoid positional bias.
    The shuffle is stable across runs for the same question text.
    """
    for q in quiz.get("mcq", []):
        options = q.get("options", [])
        if len(options) <= 1:
            continue

        # Build a stable seed from question text
        seed = f"{seed_prefix}:{q.get('q','')}"
        rng = random.Random(seed)
        rng.shuffle(options)

        q["options"] = options

    return quiz


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

You are creating questions for a student who has studied the material,
but DOES NOT see the excerpt below during the exam.

IMPORTANT RULES:
- Questions must stand alone.
- DO NOT mention:
  - "the excerpt"
  - "the passage"
  - "the text"
  - "the author"
  - "according to the chapter"
  - "as stated above"
- DO NOT refer to how the information was presented.
- Ask directly about facts, concepts, or principles.

Use the excerpt ONLY as your knowledge source.

Chapter title: {chapter_title}

SOURCE MATERIAL (DO NOT REFER TO THIS IN QUESTIONS):
\"\"\"{chunk_text}\"\"\"


Generate questions ONLY. Do NOT answer them.

Output JSON ONLY:
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

def strip_option_labels(quiz):
    for q in quiz.get("mcq", []):
        new_opts = []
        for opt in q.get("options", []):
            # If opt is a list, flatten it
            if isinstance(opt, list):
                opt = " ".join(map(str, opt))

            # Ensure it's a string
            opt = str(opt)

            cleaned = re.sub(r"^[A-D][\.\)]\s*", "", opt.strip())
            new_opts.append(cleaned)

        q["options"] = new_opts
    return quiz

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

        # --- NEW: set True/False options explicitly ---
        for q in parsed.get("true_false", []):
            q["options"] = ["True", "False"]

        all_chunk_results.append(parsed)
        time.sleep(0.2)

    # Merge chunks
    merged = {"mcq": [], "short": [], "true_false": []}
    for res in all_chunk_results:
        for k in merged.keys():
            merged[k].extend(res.get(k, []))

    merged = strip_option_labels(merged)
    merged = shuffle_mcq_options(merged)

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
