# server.py

import json
import os
import re
import logging
from typing import Dict, Any

import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

# ============================================================
# Configuration
# ============================================================

LLM_URL = f"{os.getenv('LLM_ENDPOINT', 'http://localhost:11434')}/api/generate"
LLM_MODEL = os.getenv("LLM_MODEL", "gemma3:12b")
LLM_TIMEOUT_SECONDS = 20
MAX_STUDENT_ANSWER_LENGTH = 2000

# ============================================================
# App Setup
# ============================================================

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)


# ============================================================
# Utility Functions
# ============================================================

def validate_request_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validates and sanitizes incoming grading request.
    Raises ValueError if invalid.
    """
    if not isinstance(data, dict):
        raise ValueError("Invalid JSON payload")

    question = str(data.get("question", "")).strip()
    answer_key = str(data.get("answer_key", "")).strip()
    student_answer = str(data.get("student_answer", "")).strip()
    justification = data.get("justification", [])

    if not question:
        raise ValueError("Missing question")

    if not answer_key:
        raise ValueError("Missing answer_key")

    if len(student_answer) > MAX_STUDENT_ANSWER_LENGTH:
        raise ValueError("Student answer exceeds max length")

    if justification and not isinstance(justification, list):
        raise ValueError("Justification must be a list of strings")

    return {
        "question": question,
        "answer_key": answer_key,
        "student_answer": student_answer,
        "justification": justification or []
    }


def extract_json_from_llm(text: str) -> Dict[str, Any]:
    """
    Extracts the first valid JSON object from LLM output.
    Handles markdown fences and stray text.
    """
    if not text:
        raise ValueError("Empty LLM response")

    # Remove markdown fences
    text = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE).strip()

    # Find first JSON object
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in LLM response")

    json_str = match.group(0)

    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON from LLM: {e}")

    # Validate expected schema
    if not all(k in parsed for k in ("correct", "score", "feedback")):
        raise ValueError("LLM JSON missing required fields")

    return parsed


def build_grading_prompt(question: str, answer_key: str,
                         student_answer: str,
                         justification: list[str]) -> str:
    """
    Constructs a strict, deterministic grading prompt.
    """

    justification_text = " ".join(justification)

    return f"""
You are a STRICT academic grader.

You are grading ONLY the Student Answer.
Do NOT rewrite the reference answer.
Do NOT assume missing content is implied.

Question:
{question}

Reference Answer:
{answer_key}

Additional Justification:
{justification_text}

Student Answer (the only text being graded):
\"\"\"
{student_answer}
\"\"\"

Rules:
- If the student answer is blank or meaningless ? score = 0.0
- If factually incorrect ? score = 0.0
- Partial correctness ? score between 0.1 and 0.9
- Perfect match ? score = 1.0
- Be strict and objective.
- Do not reward vague answers.

Think briefly, then output ONLY valid JSON:

{{"correct": true|false, "score": float, "feedback": "brief feedback"}}
"""


def call_llm(prompt: str) -> Dict[str, Any]:
    """
    Calls the local LLM deterministically.
    """

    payload = {
        "model": LLM_MODEL,
        "prompt": prompt,
        "max_tokens": 400,
        "temperature": 0,
        "stream": False
    }

    try:
        response = requests.post(
            LLM_URL,
            json=payload,
            timeout=LLM_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        data = response.json()

        # Ollama-style response compatibility
        text = data.get("response") or data.get("text") or ""

        return extract_json_from_llm(text)

    except requests.Timeout:
        logging.error("LLM timeout")
        raise RuntimeError("LLM timeout")

    except Exception as e:
        logging.error(f"LLM failure: {e}")
        raise RuntimeError("LLM grading failure")


def pre_llm_guard(student_answer: str) -> Dict[str, Any] | None:
    """
    Hard rule enforcement BEFORE LLM call.
    Returns grading result if blocked, otherwise None.
    """

    if not student_answer or not student_answer.strip():
        return {
            "correct": False,
            "score": 0.0,
            "feedback": "No answer provided."
        }

    # Prevent junk submissions
    if len(student_answer.strip()) < 2:
        return {
            "correct": False,
            "score": 0.0,
            "feedback": "Answer too short to evaluate."
        }

    return None


# ============================================================
# Routes
# ============================================================

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/autograde", methods=["POST"])
def autograde():
    try:
        data = validate_request_payload(request.get_json())

        # Pre-LLM guard
        blocked = pre_llm_guard(data["student_answer"])
        if blocked:
            return jsonify(blocked)

        prompt = build_grading_prompt(
            data["question"],
            data["answer_key"],
            data["student_answer"],
            data["justification"]
        )

        result = call_llm(prompt)

        return jsonify(result)

    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    except RuntimeError as e:
        return jsonify({
            "correct": False,
            "score": 0.0,
            "feedback": str(e)
        }), 500

    except Exception as e:
        logging.exception("Unexpected server error")
        return jsonify({
            "correct": False,
            "score": 0.0,
            "feedback": "Unexpected server error"
        }), 500


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)