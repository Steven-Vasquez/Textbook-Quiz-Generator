#!/usr/bin/env python3
"""
format_quiz_pdf.py

Usage:
    python format_quiz_pdf.py ch01_answers.json output_dir/

Generates:
    - ch01_quiz_student.pdf
    - ch01_quiz_instructor.pdf
    - sample_test_1.pdf
    - sample_test_2.pdf
    - sample_test_3.pdf
    - sample_test_4.pdf
"""

import json
import os
import argparse
import random
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors

# -----------------------------
# Helpers
# -----------------------------
def draw_wrapped_text(c, text, x, y, max_width, leading=14, font="Helvetica", font_size=12):
    """
    Draw multi-line text with wrapping
    """
    from reportlab.pdfbase.pdfmetrics import stringWidth

    c.setFont(font, font_size)
    words = text.split()
    line = ""
    lines = []

    for word in words:
        test_line = f"{line} {word}".strip()
        if stringWidth(test_line, font, font_size) <= max_width:
            line = test_line
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)

    for line in lines:
        c.drawString(x, y, line)
        y -= leading

    return y

def draw_true_false(c, x, y, answer=None, font_size=12, box_size=10, spacing=70):
    """
    Draw aligned open checkboxes for True/False.
    If 'answer' is provided, fill the corresponding box.
    """
    # Calculate vertical offset to align box with text baseline
    text_offset = font_size * 0.25  # tweak if needed

    # True box
    c.rect(x, y - box_size * 0.3, box_size, box_size)  # box outline
    c.setFont("Helvetica", font_size)
    c.drawString(x + box_size + 4, y - box_size * 0.25, "True")
    if answer is not None and answer.lower() == "true":
        # fill True box
        c.setFillColor(colors.black)
        c.rect(x + 1, y - box_size * 0.3 + 1, box_size - 2, box_size - 2, fill=1)
        c.setFillColor(colors.black)

    # False box
    c.rect(x + spacing, y - box_size * 0.3, box_size, box_size)
    c.drawString(x + spacing + box_size + 4, y - box_size * 0.25, "False")
    if answer is not None and answer.lower() == "false":
        # fill False box
        c.setFillColor(colors.black)
        c.rect(x + spacing + 1, y - box_size * 0.3 + 1, box_size - 2, box_size - 2, fill=1)
        c.setFillColor(colors.black)

    return y - box_size - 4

def get_mcq_answer_label(q):
    """
    Returns (letter, answer_text) if MCQ and answer matches an option.
    Otherwise returns (None, answer_text).
    """
    answer = q.get("answer")
    options = q.get("options") or []

    if not options or not answer:
        return None, answer

    for i, opt in enumerate(options):
        if opt.strip() == answer.strip():
            return chr(ord("A") + i), answer

    return None, answer

# -----------------------------
# Use question ID to infer type
# -----------------------------
def infer_type_from_id(qid):
    if "_mcq_" in qid:
        return "mcq"
    if "_true_false_" in qid:
        return "true_false"
    if "_short_" in qid:
        return "short"
    return "unknown"


def draw_question(
    c, q, x, y, max_width, question_number,
    post_question_spacing=-4,
    answer_for_tf=None,
    show_short_answer_lines=True
):
    qtype = infer_type_from_id(q['id'])

    # Draw main question
    question_text = f"{question_number}. {q['question']}"
    y = draw_wrapped_text(c, question_text, x, y, max_width)

    # Space before ID
    y -= post_question_spacing

    # Question ID in small gray text
    c.setFont("Helvetica", 6)
    c.setFillColor(colors.grey)
    c.drawString(x, y, f"(ID: {q['id']})")
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 10)
    y -= 16

    # Draw options / short answer / true-false
    if qtype == "mcq":
        for i, opt in enumerate(q["options"]):
            letter = chr(ord("A") + i)
            y = draw_wrapped_text(c, f"    {letter}.  {opt}", x, y, max_width)
    elif qtype == "short" and show_short_answer_lines:
        for _ in range(3):
            c.line(x, y, x + max_width, y)
            y -= 18
    elif qtype == "true_false":
        y = draw_true_false(c, x, y, answer=answer_for_tf)
        y -= 10

    y -= 10
    return y


def draw_answer_question(c, q, x, y, max_width, question_number):
    # Draw question with filled TF if applicable
    answer = q.get("answer", None)
    y = draw_question(
        c, q, x, y, max_width, question_number,
        answer_for_tf=answer if infer_type_from_id(q['id']) == "true_false" else None,
        show_short_answer_lines=False
    )

    qtype = infer_type_from_id(q['id'])
    confidence = q.get("confidence", 1)
    pages = ", ".join(str(p) for p in q.get("pages", [])) or "N/A"
    justification = q.get("justification", [])

    # Bold main answer info
    c.setFont("Helvetica-Bold", 11)
    if qtype == "mcq":
        letter, answer_text = get_mcq_answer_label(q)
        if letter:
            answer_line = f"Answer: ({letter}). {answer_text}"
        else:
            answer_line = f"Answer: {answer_text}"
    else:
        answer_line = f"Answer: {answer}"

    y = draw_wrapped_text(
        c,
        answer_line,
        x + 10,
        y,
        max_width - 10,
        font="Helvetica-Bold",
        font_size=11
    )
    y = draw_wrapped_text(c, f"Confidence: {confidence:.2f}", x + 10, y, max_width - 10, font="Helvetica-Bold", font_size=11)
    y = draw_wrapped_text(c, f"Pages: {pages}", x + 10, y, max_width - 10, font="Helvetica-Bold", font_size=11)

    # Justification
    if justification:
        y = draw_wrapped_text(c, "Justification:", x + 10, y, max_width - 10, font="Helvetica-Bold", font_size=11)
        for j in justification:
            y = draw_wrapped_text(c, f"> {j}", x + 20, y, max_width - 20, font="Helvetica", font_size=11)

    c.setFont("Helvetica", 12)
    y -= 10
    return y




# -----------------------------
# PDF Generators
# -----------------------------
def create_student_pdf(data, out_path):
    c = canvas.Canvas(out_path, pagesize=letter)
    width, height = letter
    x_margin = 50
    y = height - 50
    max_width = width - 2 * x_margin

    # Title with wrapping
    y = draw_wrapped_text(c, f"Quiz — {data['title']}", x_margin, y, max_width, leading=16, font_size=16, font="Helvetica-Bold")
    y -= 10
    c.setFont("Helvetica", 12)
    y = draw_wrapped_text(c, "Answer all questions. Choose the best answer where applicable.", x_margin, y, max_width)
    y -= 20

    questions = data.get("answers", [])
    sections = {"mcq": [], "short": [], "true_false": []}
    for q in questions:
        sections[infer_type_from_id(q["id"])].append(q)

    for section_name, qlist in [("Multiple Choice", sections["mcq"]),
                                ("Short Answer", sections["short"]),
                                ("True / False", sections["true_false"])]:
        if not qlist:
            continue
        y -= 20
        y = draw_wrapped_text(c, section_name, x_margin, y, max_width, leading=14, font="Helvetica-Bold", font_size=14)
        y -= 10
        c.setFont("Helvetica", 12)
        for i, q in enumerate(qlist, 1):
            if y < 100:
                c.showPage()
                y = height - 50
                c.setFont("Helvetica", 12)
            y = draw_question(c, q, x_margin, y, max_width, i)

    c.save()
    print(f"Saved {out_path}")


def create_instructor_pdf(data, out_path):
    c = canvas.Canvas(out_path, pagesize=letter)
    width, height = letter
    x_margin = 50
    y = height - 50
    max_width = width - 2 * x_margin

    # Title
    y = draw_wrapped_text(
        c,
        f"Answer Key — {data['title']}",
        x_margin,
        y,
        max_width,
        leading=16,
        font="Helvetica-Bold",
        font_size=16
    )
    y -= 30

    # Group questions by inferred type
    questions = data.get("answers", [])
    sections = {
        "mcq": [],
        "short": [],
        "true_false": []
    }

    for q in questions:
        sections[infer_type_from_id(q["id"])].append(q)

    section_order = [
        ("Multiple Choice", "mcq"),
        ("Short Answer", "short"),
        ("True / False", "true_false"),
    ]

    for section_title, key in section_order:
        qlist = sections[key]
        if not qlist:
            continue

        # Page break if needed
        if y < 200:
            c.showPage()
            y = height - 50

        # Section header
        y -= 10
        y = draw_wrapped_text(
            c,
            section_title,
            x_margin,
            y,
            max_width,
            leading=14,
            font="Helvetica-Bold",
            font_size=14
        )
        y -= 10

        # Reset numbering within section
        for i, q in enumerate(qlist, 1):
            if y < 150:
                c.showPage()
                y = height - 50

            y = draw_answer_question(
                c,
                q,
                x_margin,
                y,
                max_width,
                i
            )

    c.save()
    print(f"Saved {out_path}")

def create_sample_tests(data, out_dir, n_samples=4, num_each=10):
    questions = data.get("answers", [])
    q_by_type = {"mcq": [], "short": [], "true_false": []}

    for q in questions:
        q_by_type[infer_type_from_id(q["id"])].append(q)

    for s in range(1, n_samples + 1):
        sample_qs = []

        for qtype in ["mcq", "short", "true_false"]:
            selected = random.sample(
                q_by_type[qtype],
                min(num_each, len(q_by_type[qtype]))
            )
            sample_qs.extend(selected)

        random.shuffle(sample_qs)

        sample_data = {
            "title": f"{data['title']} — Sample Test {s}",
            "answers": sample_qs
        }

        chapter_id = data.get("chapter_id")
        # Student version
        student_dir = os.path.join(out_dir, "quizzes")
        os.makedirs(student_dir, exist_ok=True)

        student_pdf = os.path.join(
            student_dir,
            f"{chapter_id}_sample_test_{s}.pdf"
        )
        create_student_pdf(sample_data, student_pdf)

        # Instructor / answer key version
        answer_key_dir = os.path.join(out_dir, "ans_keys")
        os.makedirs(answer_key_dir, exist_ok=True)

        answer_key_pdf = os.path.join(
            answer_key_dir,
            f"{chapter_id}_sample_test_{s}_answer_key.pdf"
        )
        create_instructor_pdf(sample_data, answer_key_pdf)


# -----------------------------
# Main
# -----------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("answer_key_dir", help="Directory containing answer key JSON files")
    parser.add_argument("out_dir", help="Base output directory")
    args = parser.parse_args()

    # Loop over all JSON files in the input directory
    for fname in sorted(os.listdir(args.answer_key_dir)):
        if not fname.lower().endswith(".json"):
            continue

        answer_key_path = os.path.join(args.answer_key_dir, fname)

        with open(answer_key_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        chapter_id = data.get("chapter_id")
        if not chapter_id:
            print(f"Skipping {fname}: no chapter_id found")
            continue

        # Create chapter-specific output directory
        chapter_out_dir = os.path.join(args.out_dir, chapter_id)
        os.makedirs(chapter_out_dir, exist_ok=True)

        print(f"\nProcessing chapter {chapter_id}")

        # Output filenames (include chapter_id explicitly)
        student_pdf = os.path.join(
            chapter_out_dir, f"{chapter_id}_quiz_student.pdf"
        )
        instructor_pdf = os.path.join(
            chapter_out_dir, f"{chapter_id}_quiz_instructor.pdf"
        )

        create_student_pdf(data, student_pdf)
        create_instructor_pdf(data, instructor_pdf)

        # Sample tests (also chapter-scoped)
        create_sample_tests(
            data,
            chapter_out_dir,
            n_samples=4,
            num_each=10
        )


if __name__ == "__main__":
    main()
