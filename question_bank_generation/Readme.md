1. python extract_and_split.py textbook.pdf out/
# Divide the text into chapters, and divide each chapter into chunks

# 2. python index_and_embed.py out/chapters_chunked.json out/index/
# (not needed for now)

3. python generate_json_questions.py out/chapters_chunked.json out/json/questions/
# For each chunk in each chapter, generate relavent questions

4. python generate_json_answer_keys.py out/chapters_chunked.json out/json/questions out/json/answers/
# For each question, generate it's associated answer, validate it, and cite the textbook

5. python format_quiz_pdf.py out/json/answers/ out/final_output/
# Create formatted answer key/quiz for each chapter and randomized sample quizzes

           ┌─────────────────────┐
           │   PDF Textbook      │
           └─────────┬───────────┘
                     │ Extract text
                     ▼
           ┌─────────────────────┐
           │ Chapter Splitter    │
           └─────────┬───────────┘
                     │ For each chapter,
                     ▼
           ┌──────────────────────────────┐
           │ Generate Questions (LLM API) │
           └─────────┬────────────────────┘
                     │ Send POST request
                     │ Format & clean output
                     ▼
           ┌────────────────────────────────────────────────┐
           │ Generate answers + citations + validate output │
           └─────────┬──────────────────────────────────────┘
                     │ Send POST request
                     │ Format & clean output
                     ▼
           ┌────────────────────────────────────────────┐
           │ Generate X sample quizzes + answer keys    │
           └────────────────────────────────────────────┘
