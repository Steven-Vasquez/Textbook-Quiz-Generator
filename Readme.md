
1. python extract_and_split.py textbook.pdf out/
# creates out/chapters_chunked.json

2. python index_and_embed.py out/chapters_chunked.json index/

3. python generate_questions.py out/chapters_chunked.json quizzes/

4. python generate_answer_key.py out/chapters_chunked.json answer_keys/


           ┌─────────────────────┐
           │   PDF Textbook      │
           └─────────┬───────────┘
                     │ Extract text
                     ▼
           ┌─────────────────────┐
           │ Chapter Splitter    │
           └─────────┬───────────┘
                     │ For each chapter
                     ▼
           ┌──────────────────────────────┐
           │ Summarize (Local LLM API)    │
           └─────────┬────────────────────┘
                     │ Send POST request
                     ▼
           ┌──────────────────────────────┐
           │ Generate Questions (LLM API) │
           └─────────┬────────────────────┘
                     │ Format & clean output
                     ▼
           ┌─────────────────────┐
           │ Save Output Files   │
           └─────────────────────┘
