// -----------------------------
// quiz.js — Web version with section sampling
// -----------------------------
let quizData;
let allQuestions = [];

// --- URL parameter mapping ---
const params = new URLSearchParams(window.location.search);
const chapterNum = params.get("chapter");

if (!chapterNum) {
    alert("No chapter selected.");
    window.location.href = "index.html";
}

const chapterFile = `answer_keys/chapter_${chapterNum}_answer_key.json`;

// Fetch the JSON
fetch(chapterFile)
    .then(res => {
        if (!res.ok) throw new Error(`Quiz file not found: ${chapterFile}`);
        return res.json();
    })
    .then(data => {
        quizData = data;
        normalizeQuestions();
        renderQuiz({
            mcq: 10,        // Example: pick 5 random MCQs
            true_false: 10,  // pick 5 True/False
            short: 10       // pick 3 Short Answer
        });
    })
    .catch(err => {
        console.error(err);
        alert("Failed to load quiz.");
    });

// -----------------------------
// Helpers
// -----------------------------
function inferTypeFromId(qid) {
    if (qid.includes("_mcq_")) return "mcq";
    if (qid.includes("_true_false_")) return "true_false";
    if (qid.includes("_short_")) return "short";
    return "unknown";
}

function normalizeQuestions() {
    const questions = quizData.answers || [];
    allQuestions = questions.map(q => ({ ...q, type: inferTypeFromId(q.id) }));
}

// Randomly pick `n` items from array
function pickRandom(arr, n) {
    const copy = [...arr];
    const result = [];
    while (copy.length > 0 && result.length < n) {
        const i = Math.floor(Math.random() * copy.length);
        result.push(copy.splice(i, 1)[0]);
    }
    return result;
}

// -----------------------------
// Render Quiz with optional sampling
// config = { mcq: number, true_false: number, short: number }
function renderQuiz(config = {}) {
    document.getElementById("quiz-title").textContent = quizData.title || "Quiz";
    const form = document.getElementById("quiz-form");
    form.innerHTML = "";

    // Group questions by type
    const sections = { mcq: [], true_false: [], short: [] };
    allQuestions.forEach(q => sections[q.type]?.push(q));

    // Pick random subset if config is set
    const finalQuestions = [];
    for (const key of ["mcq", "true_false", "short"]) {
        const pool = sections[key] || [];
        const count = config[key] || pool.length; // default all
        const picked = pickRandom(pool, count);
        finalQuestions.push(...picked);
    }

    // Render in order: MCQ, True/False, Short
    [["Multiple Choice", "mcq"], ["True / False", "true_false"], ["Short Answer", "short"]].forEach(([title, key]) => {
        const qlist = finalQuestions.filter(q => q.type === key);
        if (qlist.length === 0) return;

        const h2 = document.createElement("h2");
        h2.textContent = title;
        form.appendChild(h2);

        qlist.forEach((q, i) => {
            const qnum = form.querySelectorAll(".question").length + 1;
            const div = document.createElement("div");
            div.className = "question";

            let html = `<p><strong>${qnum}. ${q.question}</strong></p>`;

            if (q.type === "mcq") {
                (q.options || []).forEach((opt, idx) => {
                    const letter = String.fromCharCode(65 + idx);
                    html += `<label><input type="radio" name="q${qnum}" value="${opt}"> ${letter}. ${opt}</label><br>`;
                });
            } else if (q.type === "true_false") {
                ["True", "False"].forEach(opt => {
                    html += `<label><input type="radio" name="q${qnum}" value="${opt}"> ${opt}</label><br>`;
                });
            } else if (q.type === "short") {
                html += `<textarea name="q${qnum}" rows="3" cols="50"></textarea>`;
            }

            div.innerHTML = html;
            form.appendChild(div);
        });
    });

    // Store the final questions for grading
    allQuestions = finalQuestions;
}

// -----------------------------
// Grading
// -----------------------------
async function gradeShortAnswerWithLLM(q) {
    // q = { question, answer, studentAnswer, justification }
    const payload = {
        question: q.question,
        answer_key: q.answer,
        student_answer: q.studentAnswer,
        justification: Array.isArray(q.justification)
            ? q.justification
            : []
    };

    const res = await fetch("http://localhost:5000/autograde", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    });

    const json = await res.json();
    //console.log("LLM grading response:", json);
    return json;  // { correct, score, feedback }
}



function normalize(text) {
    return (text || "").trim().toLowerCase();
}

async function gradeQuiz() {
    let score = 0;

    for (let i = 0; i < allQuestions.length; i++) {
        const q = allQuestions[i];
        const qnum = i + 1;

        // Locate the question container
        const questionEl = document.querySelector(`.question:nth-of-type(${qnum})`);
        if (!questionEl) continue;

        // Remove any existing inline feedback
        const oldFeedback = questionEl.querySelector(".inline-feedback");
        if (oldFeedback) oldFeedback.remove();

        // Get user answer
        let userAnswer = null;
        if (q.type === "short") {
            userAnswer = questionEl.querySelector("textarea")?.value || "";
        } else {
            const selected = questionEl.querySelector("input:checked");
            if (selected) userAnswer = selected.value;
        }

        // Grade
        let correct = false;
        let feedback = "";
        let correctAnswerStr = q.answer;

        if (q.type === "short") {
            let aiResult = await gradeShortAnswerWithLLM({
                question: q.question,
                answer: q.answer,
                studentAnswer: userAnswer,
                justification: q.justification
            });

            // Handle potential string output
            if (typeof aiResult === "string") {
                try {
                    aiResult = JSON.parse(aiResult);
                } catch (e) {
                    console.error("Failed to parse AI result for Q" + qnum, aiResult);
                    aiResult = { correct: false, score: 0, feedback: "AI grading failed" };
                }
            }

            correct = aiResult.correct;
            feedback = aiResult.feedback || "";
        } else {
            correct = normalize(userAnswer) === normalize(q.answer);
        }

        if (correct) score++;

        // Add inline feedback element
        const feedbackDiv = document.createElement("div");
        feedbackDiv.className = `inline-feedback ${correct ? "correct" : "incorrect"}`;

        // Include correct answer if user got it wrong
        const correctAnswerHTML = !correct && correctAnswerStr
            ? `<div class="correct-answer"><strong>Correct Answer:</strong> ${correctAnswerStr}</div>`
            : "";

        feedbackDiv.innerHTML = `
            <strong>${correct ? "Correct" : "Incorrect"}</strong>
            ${correctAnswerHTML}
            ${q.type === "short" && feedback ? `<div class="feedback-text"><strong>Feedback:</strong> ${feedback}</div>` : ""}
            <div class="pages"><strong>Pages:</strong> ${q.pages?.join(", ") || "N/A"}</div>
            ${q.justification && q.justification.length
                ? `<div class="justification"><strong>Justification citation:</strong> ${q.justification}</div>`
                : ""}
            <div class="confidence"><strong>Answer Key Confidence:</strong> ${q.confidence ? `${q.confidence}/4` : "N/A"}</div>
        `;
        questionEl.appendChild(feedbackDiv);
    }

    // Update overall score display
    document.getElementById("result").textContent =
        `Score: ${score} / ${allQuestions.length}`;
}
