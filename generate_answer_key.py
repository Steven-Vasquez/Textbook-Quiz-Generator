#!/usr/bin/env python3
"""
generate_answer_key.py
Usage:
    python generate_answer_key.py chapters_chunked.json quiz_dir/ answer_key_dir/
"""

import os, json, time, re
from dotenv import load_dotenv
from tqdm import tqdm
import argparse
import ujson
import requests

load_dotenv()

# -----------------------------
# LLM call
# -----------------------------
def call_llm(prompt, max_tokens=600, temperature=0.0):
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
    return resp.json().get("response", "").strip()


def extract_json(text):
    candidates = re.findall(r"\{(?:[^{}]|(?:\{[^{}]*\}))*\}", text, flags=re.DOTALL)
    for c in candidates:
        try:
            return json.loads(c)
        except Exception:
            continue
    raise ValueError("No valid JSON found")


# -----------------------------
# Answer generation (1 question)
# -----------------------------
def generate_answer_for_question(chunk, question):
    is_mcq = bool(question.get("options"))

    mcq_instruction = ""
    if is_mcq:
        mcq_instruction = """
- Choose EXACTLY ONE of the provided options.
- Answer must MATCH the option text exactly.
"""

    prompt = f"""
You are generating an answer key.

Use ONLY the excerpt below.
Page markers appear as [PAGE X].

Rules:
- Cite the page number(s) where the answer is found.
- If not explicitly stated, answer "Not explicitly stated" and return empty pages.
{mcq_instruction}

Question ID: {question['id']}
Question: {question['q']}
Options: {question.get('options', [])}

EXCERPT:
\"\"\"{chunk['text']}\"\"\"

Return JSON ONLY:
{{
  "id": "{question['id']}",
  "question": "{question['q']}",
  "answer": "...",
  "pages": []
}}
"""

    try:
        parsed = extract_json(call_llm(prompt))
        return {
            "id": parsed.get("id", question["id"]),
            "question": parsed.get("question", question["q"]),
            "answer": parsed.get("answer", "Not explicitly stated"),
            "pages": parsed.get("pages", [])
        }
    except Exception:
        return {
            "id": question["id"],
            "question": question["q"],
            "answer": "Not explicitly stated",
            "pages": []
        }


# -----------------------------
# Save output
# -----------------------------
def save_answer_key(out_dir, chap_key, chap, answers):
    os.makedirs(out_dir, exist_ok=True)

    out_json = os.path.join(out_dir, f"{chap_key}_answers.json")
    with open(out_json, "w", encoding="utf-8") as f:
        ujson.dump(
            {
                "chapter_key": chap_key,
                "chapter_id": chap["chapter_id"],
                "title": chap["title"],
                "answers": answers
            },
            f,
            indent=2
        )

    md = [f"# Answer Key — {chap['title']}\n"]
    for a in answers:
        pages = ", ".join(str(p) for p in a.get("pages", [])) or "N/A"
        md.append(f"**({a['id']}) {a['question']}**")
        md.append(f"Answer: {a['answer']}")
        md.append(f"Pages: {pages}\n")

    md_path = os.path.join(out_dir, f"{chap_key}_answers.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    print("Saved", out_json, md_path)


# -----------------------------
# Main
# -----------------------------
def main(args):
    with open(args.chapters_json, "r", encoding="utf-8") as f:
        chapters = json.load(f)

    for chap_key, chap in chapters.items():
        quiz_file = os.path.join(args.quiz_dir, f"{chap_key}_quiz.json")
        with open(quiz_file, "r", encoding="utf-8") as f:
            quiz = json.load(f)["quiz"]

        # Build chunk lookup
        chunk_map = {c["chunk_id"]: c for c in chap["chunks"]}

        # Flatten questions
        questions = []
        for qtype in ["mcq", "short", "true_false"]:
            questions.extend(quiz.get(qtype, []))

        answers = []

        for q in tqdm(questions, desc=f"Answering {chap_key}"):
            chunk = chunk_map.get(q["chunk_id"])
            if not chunk:
                continue

            ans = generate_answer_for_question(chunk, q)
            answers.append(ans)
            time.sleep(0.1)

        save_answer_key(args.out_dir, chap_key, chap, answers)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("chapters_json")
    parser.add_argument("quiz_dir")
    parser.add_argument("out_dir")
    args = parser.parse_args()
    main(args)