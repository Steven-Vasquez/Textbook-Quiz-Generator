
1. python extract_and_split.py textbook.pdf out/
# creates out/chapters_chunked.json

2. python index_and_embed.py out/chapters_chunked.json out/index/

3. python generate_json_questions.py out/chapters_chunked.json out/json/questions/

4. python generate_json_answer_keys.py out/chapters_chunked.json out/json/answers/

python format_quiz_pdf.py out/json/answers/Chapter_5_The_Electrical_System_Your_Cars_Spark_of_Life_answers.json out/final_output/

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
