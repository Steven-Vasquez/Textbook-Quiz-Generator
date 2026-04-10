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
# Helper functions
# -----------------------------
def is_invalid_answer(ans):
    if not ans or not isinstance(ans, dict):
        return True

    answer_text = ans.get("answer", "").strip().lower()
    confidence = ans.get("confidence", None)
    pages = str(ans.get("pages", "")).strip().lower()

    return (
        not answer_text
        or answer_text in {"not explicitly stated", "..."}
        or confidence == 1
        or confidence == 1.0
        or pages in {"n/a", "na", ""}
    )



# -----------------------------
# LLM call
# -----------------------------
def call_llm(prompt, max_tokens=600, temperature=0.2):
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
    """
    Second-pass retry with stricter evidence discipline.
    Uses the same confidence scale as the primary pass.
    """

    is_mcq = bool(question.get("options"))

    mcq_instruction = ""
    if is_mcq:
        mcq_instruction = """
MCQ RULES:
- Choose EXACTLY ONE of the provided options.
- The chosen option MUST be semantically equivalent to the meaning of the justification quote(s).
- If none of the options match the meaning of the quote(s):
  - answer = "Not explicitly stated"
  - pages = []
  - justification = []
  - confidence = 1
"""

    prompt = f"""
You are retrying answer generation after a failed first attempt.

Retry ONLY if the excerpt provides sufficient textual support.
Do NOT lower the evidentiary standard to force an answer.

ABSOLUTE RULES:
- Do NOT guess.
- Do NOT introduce outside knowledge.
- Do NOT merge unrelated statements.
- If support is ambiguous or contradictory, return "Not explicitly stated".

FIELD DEFINITIONS:
- answer:
  - Must exactly reflect what the excerpt states or implies
  - Use "Not explicitly stated" if the excerpt does not support a single clear answer
- pages:
  - Page numbers where the justification quote(s) appear
  - Empty list if answer is "Not explicitly stated"
- justification:
  - Exact quote(s) copied verbatim from the excerpt
  - Quote(s) must logically support the answer
- confidence (use ONLY these values):
  - 4 = explicitly stated verbatim
  - 3 = clearly implied by the text
  - 2 = weak or indirect textual support
  - 1 = not stated or contradictory

If the justification quote(s) contradict the answer:
- answer = "Not explicitly stated"
- pages = []
- justification = []
- confidence = 1

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
  "pages": [],
  "confidence": 1,
  "justification": []
}}
"""

    try:
        parsed = extract_json(call_llm(prompt))
        return {
            "id": parsed.get("id", question["id"]),
            "question": parsed.get("question", question["q"]),
            "options": question.get("options"),  # ← PRESERVE EXACT OPTIONS
            "answer": parsed.get("answer", "Not explicitly stated"),
            "pages": parsed.get("pages", []),
            "confidence": float(parsed.get("confidence", 1)),
            "justification": parsed.get("justification", [])
        }
    except Exception:
        return {
            "id": question["id"],
            "question": question["q"],
            "options": question.get("options"),
            "answer": "Not explicitly stated",
            "pages": [],
            "confidence": 1,
            "justification": []
        }

def generate_answer_retry(chunk, question):
    """
    Second-pass retry with STRICTER, high-precision instructions.
    Only answer if explicitly stated.
    """

    is_mcq = bool(question.get("options"))

    mcq_instruction = ""
    if is_mcq:
        mcq_instruction = """
MCQ RULES:
- Choose EXACTLY ONE option ONLY IF it is explicitly stated in the excerpt.
- The option text MUST match the meaning of the quote verbatim.
- If no option is explicitly stated:
  - answer = "Not explicitly stated"
  - pages = []
  - justification = []
  - confidence = 1
"""

    prompt = f"""
You are retrying answer generation after a failed first pass.

Retry ONLY if the excerpt EXPLICITLY states the answer.
If the answer is not stated verbatim, return "Not explicitly stated".

ABSOLUTE RULES:
- Do NOT guess.
- Do NOT infer.
- Do NOT paraphrase.
- Do NOT combine multiple weak signals.
- If there is any ambiguity, return "Not explicitly stated".

FIELD DEFINITIONS:
- answer:
  - The exact fact stated in the excerpt
  - Or "Not explicitly stated"
- pages:
  - List ONLY page numbers that contain the justification quote(s)
  - Empty list if answer is "Not explicitly stated"
- justification:
  - Exact quote(s) copied verbatim from the excerpt
  - Each quote must independently support the answer
- confidence (use ONLY these values):
  - 4 = explicitly stated verbatim
  - 1 = not stated, ambiguous, or contradictory
  - NEVER use 2 or 3 in this retry pass

If the quote(s) contradict the answer:
- answer = "Not explicitly stated"
- pages = []
- justification = []
- confidence = 1

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
  "pages": [],
  "confidence": 1,
  "justification": []
}}
"""


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
        md.append(f"Pages: {pages}")
        md.append(f"Confidence: {a.get('confidence', 1):.2f}")

        if a.get("justification"):
            md.append("Justification:")
            for j in a["justification"]:
                md.append(f"> {j}")
        else:
            md.append("Justification: N/A")

        md.append("")

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

            # Retry once if answer is missing or explicitly not stated
            if is_invalid_answer(ans):
                ans = generate_answer_retry(chunk, q)

            # Only keep questions with a valid answer
            if not is_invalid_answer(ans):
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