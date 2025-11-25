# app.py
import streamlit as st
from auth import auth_ui
from src.ingestion_store import ingest_and_store_file
from src.embedding_db import EmbedderDB
from src.generator_gemini import Generator
from supabase import create_client
import json
import os
import time
import random



# -----------------------
# CONFIG
# -----------------------
SUPABASE_URL = "https://fvqnabzyhdfqjyiymgkq.supabase.co"
# Replace with your Supabase service role key or a server-side key if writing from server.
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZ2cW5hYnp5aGRmcWp5aXltZ2txIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjM1NTAzNDcsImV4cCI6MjA3OTEyNjM0N30.7ipg_sFgSa0hRIWFX96iv180cL9X54vHVpj4nmmQYnM"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# -----------------------
# SESSION DEFAULTS
# -----------------------
if "user" not in st.session_state:
    st.session_state.user = None
if "current_file_id" not in st.session_state:
    st.session_state.current_file_id = None

# Quiz-related session defaults
if "quiz_index" not in st.session_state:
    st.session_state.quiz_index = None
if "quiz_score" not in st.session_state:
    st.session_state.quiz_score = None
if "quiz_answers" not in st.session_state:
    st.session_state.quiz_answers = None
if "quiz_start_time" not in st.session_state:
    st.session_state.quiz_start_time = None
if "quiz_random_order" not in st.session_state:
    st.session_state.quiz_random_order = None
if "quiz_mcqs" not in st.session_state:
    st.session_state.quiz_mcqs = None
if "quiz_source_file_id" not in st.session_state:
    st.session_state.quiz_source_file_id = None

# Flag to avoid duplicate saves
if "quiz_saved" not in st.session_state:
    st.session_state.quiz_saved = False

# -----------------------
# AUTH UI (external)
# -----------------------

auth_ui()

# -----------------------
# UTIL / HELPERS
# -----------------------
def safe_rerun():
    """Call the appropriate rerun API (works across streamlit versions)."""
    try:
        st.experimental_rerun()
    except Exception:
        try:
            st.rerun()
        except Exception:
            # last resort: do nothing (page will refresh on next interaction)
            pass

def parse_option_letter_and_text(option_str: str, index: int):
    """
    Given an option string as stored in MCQs, return (letter, text)
    Handles formats like:
        "A) Text...", "A. Text...", "A - Text...", "Text only"
    If option has no explicit letter, assign letters by index (A, B, C...).
    """
    if not isinstance(option_str, str):
        option_str = str(option_str or "")
    s = option_str.strip()
    # Leading letter "A)" or "A." or "A -"
    if len(s) >= 2 and s[0].isalpha() and s[1] in [')', '.', '-', ' '] :
        letter = s[0].upper()
        rest = s[2:].strip()
        return letter, rest if rest else s
    # "A)text" without space: treat first char as letter
    if len(s) >= 2 and s[0].isalpha() and not s[1].isalpha() and s[1] not in [')', '.','-',' ']:
        letter = s[0].upper()
        rest = s[1:].strip()
        return letter, rest if rest else s
    # No explicit letter: assign by index
    letters = [chr(ord('A') + i) for i in range(26)]
    letter = letters[index] if index < len(letters) else f"OPT{index}"
    return letter, s

def normalize_answer_from_mcq(mcq: dict, options: list):
    """
    Normalize the stored 'answer' from MCQ entry into (correct_letter, correct_text)
    Accepts answers like "B", "B) text", "B) some text", or full option text.
    """
    raw_ans = mcq.get("answer") or ""
    raw_ans = str(raw_ans).strip()

    # Build mapping letter -> option text and text -> letter
    letter_to_text = {}
    text_to_letter = {}
    for i, opt in enumerate(options):
        letter, text = parse_option_letter_and_text(opt, i)
        letter_to_text[letter] = text
        text_to_letter[text.strip().lower()] = letter

    # Case 1: single letter
    if len(raw_ans) == 1 and raw_ans.isalpha():
        letter = raw_ans.upper()
        text = letter_to_text.get(letter, "")
        return letter, text

    # Case 2: starts with "B)" or "B. "
    if len(raw_ans) >= 2 and raw_ans[0].isalpha() and raw_ans[1] in [')', '.', '-', ' ']:
        letter = raw_ans[0].upper()
        text = letter_to_text.get(letter) or raw_ans[2:].strip()
        return letter, text

    # Case 3: exact option text (case-insensitive)
    for opt_text, letter in text_to_letter.items():
        if opt_text == raw_ans.strip().lower():
            return letter, opt_text

    # Case 4: generator returned something like "B) option text" as answer
    for i, opt in enumerate(options):
        if raw_ans.strip().lower() in opt.strip().lower():
            letter, text = parse_option_letter_and_text(opt, i)
            return letter, text

    # Fallback: unknown, return raw as both
    return raw_ans, raw_ans

# -----------------------
# LAYOUT: Sidebar navigation (pretty)
# -----------------------
if st.session_state.user:
    # small CSS tweaks
    st.markdown(
        """
        <style>
        .sidebar .sidebar-content { padding-top: 10px; }
        .card {
            border-radius: 10px;
            padding: 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
            margin-bottom: 12px;
            background: linear-gradient(180deg, #ffffff, #fbfbff);
        }
        .section-title { font-weight:700; font-size:18px; margin: 6px 0; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Sidebar menu
    st.sidebar.title("Study Assistant")
    st.sidebar.markdown("### Navigation")
    menu = st.sidebar.radio(
        "",
        ("📤 Upload & Generate", "📝 Quiz Mode", "📂 Output History", "📊 Quiz History", "⚙️ Settings"),
        index=0
    )

    # show logged in user in sidebar
    user = st.session_state.user
    st.sidebar.write(f"**{user.get('email','unknown')}**")
    st.sidebar.caption("Logged in")

    # Main page title
    st.title("📚 Study Assistant — Upload / Generate / Quiz / History")

    # ----------------------------------------------------------
    # UPLOAD & GENERATE
    # ----------------------------------------------------------
    if menu == "📤 Upload & Generate":
        st.header("📤 Upload & Generate")
        col1, col2 = st.columns([2,1])

        with col1:
            st.subheader("Upload a Lecture File (PDF / DOCX / TXT)")
            uploaded_file = st.file_uploader("Choose file", type=["pdf", "docx", "txt"])

            if uploaded_file:
                tmp_dir = "temp_uploads"
                os.makedirs(tmp_dir, exist_ok=True)
                tmp_path = os.path.join(tmp_dir, uploaded_file.name)
                with open(tmp_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())

                st.info("Processing file — extracting text, chunking, embedding and storing...")
                try:
                    file_id = ingest_and_store_file(tmp_path, user_id=user.get("id"))
                    st.success("Uploaded and indexed.")
                    st.session_state.current_file_id = file_id
                except Exception as e:
                    st.error(f"Error ingesting file: {e}")

            st.write("---")
            st.subheader("Generate Content from Lecture")
            files_resp = (
                supabase.table("user_files")
                .select("*")
                .eq("user_id", user.get("id"))
                .order("uploaded_at", desc=True)
                .execute()
            )
            files = files_resp.data or []
            file_options = {f.get("file_name", "unknown"): f.get("id") for f in files}

            selected_file_id = None
            if file_options:
                selected_name = st.selectbox("Choose file (for generation)", list(file_options.keys()))
                selected_file_id = file_options[selected_name]
                st.session_state.current_file_id = selected_file_id
            else:
                st.info("No files uploaded yet. Upload above to index a lecture.")

            query = st.text_input("Enter topic / question (leave empty for full document):")
            task = st.selectbox("Output type", ["summary", "flashcards", "mcq"])
            n_qs = st.slider("Number of MCQs", 1, 20, 5, disabled=(task != "mcq"))

            if st.button("Generate"):
                if not selected_file_id:
                    st.warning("Select or upload a file first.")
                else:
                    embedder = EmbedderDB()
                    # Build context
                    if not query.strip():
                        st.info("No query entered → using FULL DOCUMENT.")
                        all_chunks_resp = (
                            supabase.table("file_chunks")
                            .select("chunk_text")
                            .eq("file_id", selected_file_id)
                            .execute()
                        )
                        all_chunks = [c.get("chunk_text", "") for c in all_chunks_resp.data or []]
                        context = "\n\n".join(all_chunks[:50])
                        st.write(f"### Using FULL document context ({len(all_chunks)} chunks).")
                    else:
                        st.info("Using query-based retrieval (RAG).")
                        top_chunks = embedder.search(file_id=selected_file_id, query=query, top_k=5)
                        context = "\n\n".join(top_chunks)
                        if top_chunks:
                            print("Successful")
                            # st.write("### Retrieved Chunks Preview:")
                            # for i, c in enumerate(top_chunks, 1):
                            #      st.markdown(f"**Chunk {i}:** {c[:400]}{'...' if len(c) > 400 else ''}")
                        else:
                            st.warning("⚠️ No relevant chunks found for that query. Generation stopped.")
                            st.stop()
                        

                    # Generate
                    gen = Generator()
                    try:
                        output = gen.generate(context=context, task=task, n_questions=n_qs)
                    except Exception as e:
                        st.error(f"Generator error: {e}")
                        output = ""

                    st.session_state.generated_output = output
                    st.session_state.generated_task = task
                    st.session_state.generated_query = query
                    st.session_state.generated_file_id = selected_file_id

                    # Display generated output
                    if task == "flashcards":
                        cleaned = output.replace("```json", "").replace("```", "").strip()
                        try:
                            cards = json.loads(cleaned)
                            st.write("### Generated Flashcards")
                            for i, fc in enumerate(cards, 1):
                                st.markdown(f"**Flashcard {i}**")
                                st.write(f"- **Q:** {fc.get('question')}")
            
                                st.write(f"- **A:** {fc.get('answer')}")
                                st.write("---")
                        except Exception:
                            st.text_area("Raw Flashcards Output", output, height=300)

                    elif task == "mcq":
                        cleaned = output.replace("```json", "").replace("```", "").strip()
                        try:
                            mcqs_list = json.loads(cleaned)
                            st.write("### Generated MCQs (answers hidden)")
                            for i, mcq in enumerate(mcqs_list, 1):
                                st.markdown(f"**Q{i}: {mcq.get('question')}**")
                                options = mcq.get("options", [])
                                for opt in options:
                                    st.write(f"- {opt}")
                                st.write("---")
                        except Exception:
                            st.text_area("Raw MCQs Output", output, height=300)

                    else:
                        st.text_area("Summary", output, height=300)
                    # -----------------------------
# SAVE GENERATED OUTPUT SECTION
# -----------------------------
                st.write("### Save This Output")

            if st.button("Save to My Notes"):
                    try:
                            supabase.table("generated_outputs").insert({
            "user_id": user.get("id"),
            "file_id": st.session_state.get("generated_file_id"),
            "task": st.session_state.get("generated_task"),
            "query": st.session_state.get("generated_query"),
            "output_text": st.session_state.get("generated_output")
        }).execute()

                            st.success("Saved successfully! You can view it in '📚 My Saved Notes'")
                    except Exception as e:
                            st.error(f"Failed to save: {e}")


        with col2:
            st.markdown("<div class='card'>", unsafe_allow_html=True)
            st.markdown("<div class='section-title'>Quick Actions</div>", unsafe_allow_html=True)

            if st.button("Start Quiz (most recent MCQs)"):
                # start a quiz from most recently generated (in session) MCQs
                if st.session_state.get("generated_task") == "mcq" and st.session_state.get("generated_output"):
                    try:
                        mcqs_text = st.session_state.generated_output.replace("```json", "").replace("```", "").strip()
                        mcqs_list = json.loads(mcqs_text)
                    except Exception:
                        st.error("Recent MCQs could not be parsed - cannot start quiz.")
                        mcqs_list = []
                    if mcqs_list:
                        st.session_state.quiz_mcqs = mcqs_list
                        st.session_state.quiz_index = 0
                        st.session_state.quiz_score = 0
                        st.session_state.quiz_answers = []
                        st.session_state.quiz_start_time = time.time()
                        st.session_state.quiz_random_order = random.sample(range(len(mcqs_list)), len(mcqs_list))
                        st.session_state.quiz_source_file_id = st.session_state.get("generated_file_id")
                        safe_rerun()
                else:
                    st.info("No recent MCQs available to start a quiz from.")


            st.markdown("</div>", unsafe_allow_html=True)

    # ----------------------------------------------------------
    # QUIZ MODE
    # ----------------------------------------------------------
    elif menu == "📝 Quiz Mode":
        st.header("📝 Quiz Mode")
        

        st.write("Run a quiz using previously saved MCQs or the most recently generated MCQs.")

        # show quick controls
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Start Quiz from Most Recent MCQs"):
                if st.session_state.get("generated_task") == "mcq" and st.session_state.get("generated_output"):
                    try:
                        mcqs_text = st.session_state.generated_output.replace("```json", "").replace("```", "").strip()
                        mcqs_list = json.loads(mcqs_text)
                    except Exception:
                        st.error("Recent MCQs could not be parsed - cannot start quiz.")
                        mcqs_list = []
                    if mcqs_list:
                        st.session_state.quiz_mcqs = mcqs_list
                        st.session_state.quiz_index = 0
                        st.session_state.quiz_score = 0
                        st.session_state.quiz_answers = []
                        st.session_state.quiz_start_time = time.time()
                        st.session_state.quiz_random_order = random.sample(range(len(mcqs_list)), len(mcqs_list))
                        st.session_state.quiz_source_file_id = st.session_state.get("generated_file_id")
                        safe_rerun()
                else:
                    st.info("No recent MCQs to start from.")
        with col2:
            if st.button("Clear Quiz State"):
                st.session_state.quiz_index = None
                st.session_state.quiz_score = None
                st.session_state.quiz_answers = None
                st.session_state.quiz_start_time = None
                st.session_state.quiz_random_order = None
                st.session_state.quiz_mcqs = None
                st.session_state.quiz_source_file_id = None
                st.session_state.quiz_saved = False
                safe_rerun()

        st.write("---")

        # Show active quiz UI (if set)
        if st.session_state.get("quiz_mcqs"):
            mcqs = st.session_state.quiz_mcqs
            idx = st.session_state.quiz_index or 0

            if idx < len(mcqs):
                # ensure random order exists
                if not st.session_state.get("quiz_random_order"):
                    st.session_state.quiz_random_order = random.sample(range(len(mcqs)), len(mcqs))
                current_q_idx = st.session_state.quiz_random_order[idx]
                current_q = mcqs[current_q_idx]
              
                options = current_q.get("options", [])
                selected = st.radio(f"Q {idx+1}/{len(mcqs)}: {current_q.get('question')}", options, key=f"quiz_radio_{idx}")
                

                if st.button("Submit Answer", key=f"quiz_submit_{idx}"):
                    # parse selected option into (letter, text)
                    sel_letter = None
                    sel_text = None
                    for i, opt in enumerate(options):
                        if selected.strip() == opt.strip():
                            sel_letter, sel_text = parse_option_letter_and_text(opt, i)
                            break

                    if not sel_letter:
                        # fallback to first char letter
                        if isinstance(selected, str) and len(selected.strip()) >= 1 and selected.strip()[0].isalpha():
                            sel_letter = selected.strip()[0].upper()
                            sel_text = selected.strip()
                        else:
                            sel_letter = "?"
                            sel_text = str(selected)

                    # Normalize correct answer
                    correct_letter, correct_text = normalize_answer_from_mcq(current_q, options)

                    # store richer answer info
                    st.session_state.quiz_answers = st.session_state.quiz_answers or []
                    st.session_state.quiz_answers.append({
                        "question": current_q.get("question"),
                        "selected_letter": sel_letter,
                        "selected_text": sel_text,
                        "correct_letter": correct_letter,
                        "correct_text": correct_text
                    })

                    # compare
                    match = False
                    if isinstance(correct_letter, str) and len(correct_letter) == 1 and isinstance(sel_letter, str) and len(sel_letter) == 1:
                        match = (sel_letter.upper() == correct_letter.upper())
                    else:
                        match = (str(sel_text).strip().lower() == str(correct_text).strip().lower())

                    if match:
                        st.success("✅ Correct!")
                        if st.session_state.quiz_score is None:
                            st.session_state.quiz_score = 0
                        st.session_state.quiz_score += 1
                    else:
                        st.error(f"❌ Incorrect — Correct: {correct_letter}) {correct_text}")
                    

                    # increment index
                    
             
                    st.session_state.quiz_index += 1
                 
                    safe_rerun()


                st.progress((idx) / max(1, len(mcqs)))

            else:
                # Quiz finished
                duration = int(time.time() - (st.session_state.quiz_start_time or time.time()))
                score = st.session_state.quiz_score if st.session_state.quiz_score is not None else 0
                total = len(mcqs)
                st.balloons()
                st.markdown(f"### 🎉 Quiz Finished — Score: {score}/{total}")
                st.markdown(f"⏱ Duration: {duration} seconds")

                for i, ans in enumerate(st.session_state.quiz_answers or [], 1):
                    st.markdown(f"**Q{i}: {ans.get('question')}**")
                    st.write(f"- Your answer: {ans.get('selected_letter')} ) {ans.get('selected_text')}")
                    st.write(f"- Correct answer: {ans.get('correct_letter')} ) {ans.get('correct_text')}")
                    st.write("---")

                # Save attempt once
                if not st.session_state.quiz_saved:
                    try:
                        insert_resp = supabase.table("quiz_attempts").insert({
                            "user_id": user.get("id"),
                            "file_id": st.session_state.get("quiz_source_file_id"),
                            "score": score,
                            "total_questions": total,
                            "answers": json.dumps(st.session_state.quiz_answers or []),
                            "duration_sec": duration,
                            "attempted_at": int(time.time())
                        }).execute()

                        if insert_resp.data:
                            st.success("✅ Quiz attempt saved to history.")
                            st.session_state.quiz_saved = True
                        else:
                            st.error("❌ Failed to save quiz attempt.")
                    except Exception as e:
                        st.error(f"Error saving quiz attempt: {e}")

                if st.button("Restart Quiz (same MCQs)"):
                    st.session_state.quiz_index = 0
                    st.session_state.quiz_score = 0
                    st.session_state.quiz_answers = []
                    st.session_state.quiz_start_time = time.time()
                    st.session_state.quiz_random_order = random.sample(range(len(mcqs)), len(mcqs))
                    st.session_state.quiz_saved = False
                    safe_rerun()

    # ----------------------------------------------------------
    # OUTPUT HISTORY
    # ----------------------------------------------------------
    elif menu == "📂 Output History":
        st.header("📂 Generated Outputs (History)")

        files_map_resp = (
            supabase.table("user_files")
            .select("id, file_name")
            .eq("user_id", user.get("id"))
            .execute()
        )
        files_map = {f.get("id"): f.get("file_name", "unknown") for f in (files_map_resp.data or [])}

        history_resp = (
            supabase.table("generated_outputs")
            .select("*")
            .eq("user_id", user.get("id"))
            .order("id", desc=True)
            .execute()
        )
        history = history_resp.data or []

        if not history:
            st.info("No saved generated outputs yet.")
        else:
            for row in history:
                file_id = row.get("file_id")
                fname = files_map.get(file_id, "Unknown File")
                q = row.get("query") or "(Full document)"
                task_name = row.get("task") or "unknown"
                text = row.get("output_text") or ""
                created_at = row.get("created_at")
                if created_at:
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                        created_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        created_str = created_at
                else:
                    created_str = "unknown"

                exp_title = f"📁 {fname} — {task_name.upper()} — {q} — {created_str}"
                # single-level expander (no nested expanders inside)
                with st.expander(exp_title):
                    if task_name == "flashcards":
                        try:
                            cards = json.loads(text)
                            for i, fc in enumerate(cards, 1):
                                st.markdown(f"**Flashcard {i}**")
                                st.write(f"• **Q:** {fc.get('question')}")
                                st.write(f"• **A:** {fc.get('answer')}")
                                st.write("---")
                        except Exception:
                            st.text(text)

                    elif task_name == "mcq":
                        try:
                            mcqs = json.loads(text)
                            for i, mcq in enumerate(mcqs, 1):
                                st.markdown(f"**MCQ {i}:** {mcq.get('question')}")
                                for opt in mcq.get("options", []):
                                    st.write(f"- {opt}")
                                st.write(f"**Correct Answer:** {mcq.get('answer')}")
                                st.write("---")
                        except Exception:
                            st.text(text)
                    else:
                        st.text_area("Summary", text, height=250)

                    # Start quiz button for this MCQ entry
                    if task_name == "mcq":
                        if st.button("Start Quiz from this MCQs", key=f"start_quiz_{row.get('id')}"):
                            try:
                                mcqs_text = text.replace("```json", "").replace("```", "").strip()
                                mcqs_list = json.loads(mcqs_text)
                            except Exception:
                                st.error("Saved MCQs are invalid JSON and cannot start quiz.")
                                mcqs_list = []

                            if mcqs_list:
                                st.session_state.quiz_mcqs = mcqs_list
                                st.session_state.quiz_index = 0
                                st.session_state.quiz_score = 0
                                st.session_state.quiz_answers = []
                                st.session_state.quiz_start_time = time.time()
                                st.session_state.quiz_random_order = random.sample(range(len(mcqs_list)), len(mcqs_list))
                                st.session_state.quiz_source_file_id = file_id
                                safe_rerun()

    # ----------------------------------------------------------
    # QUIZ HISTORY
    # ----------------------------------------------------------
    elif menu == "📊 Quiz History":
        st.header("📊 Quiz History")

        quiz_resp = (
            supabase.table("quiz_attempts")
            .select("*")
            .eq("user_id", user.get("id"))
            .order("attempted_at", desc=True)
            .execute()
        )
        quiz_history = quiz_resp.data or []

        if not quiz_history:
            st.info("No quiz attempts yet.")
        else:
            # map file_id -> filename
            files_map_resp = (
                supabase.table("user_files")
                .select("id, file_name")
                .eq("user_id", user.get("id"))
                .execute()
            )
            files_map = {f.get("id"): f.get("file_name", "unknown") for f in (files_map_resp.data or [])}

            # group by file
            grouped_quiz = {}
            for attempt in quiz_history:
                file_id = attempt.get("file_id")
                fname = files_map.get(file_id, "Unknown File")
                grouped_quiz.setdefault(fname, []).append(attempt)

            for fname, attempts in grouped_quiz.items():
                with st.expander(f"📁 {fname} — {len(attempts)} attempt(s)"):
                    for att in attempts:
                        score = att.get("score", 0)
                        total_q = att.get("total_questions", 0)
                        duration = att.get("duration_sec", 0)
                        attempted_at = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(att.get("attempted_at", 0)))
                        st.markdown(f"**Score: {score}/{total_q} | Duration: {duration}s | Date: {attempted_at}**")

                        answers = []
                        try:
                            answers = json.loads(att.get("answers", "[]"))
                        except Exception:
                            answers = []

                        for i, ans in enumerate(answers, 1):
                            st.markdown(f"**Q{i}: {ans.get('question')}**")
                            st.write(f"- Your answer: {ans.get('selected_letter')} ) {ans.get('selected_text')}")
                            st.write(f"- Correct answer: {ans.get('correct_letter')} ) {ans.get('correct_text')}")
                            st.write("---")
                        st.markdown("---")

    # ----------------------------------------------------------
    # SETTINGS
    # ----------------------------------------------------------
    elif menu == "⚙️ Settings":
        st.header("⚙️ Settings")
        st.write("Some useful settings and debug controls.")
        st.write("• Current file id:", st.session_state.get("current_file_id"))
        if st.button("Reset quiz session state"):
            st.session_state.quiz_index = None
            st.session_state.quiz_score = None
            st.session_state.quiz_answers = None
            st.session_state.quiz_start_time = None
            st.session_state.quiz_random_order = None
            st.session_state.quiz_mcqs = None
            st.session_state.quiz_source_file_id = None
            st.session_state.quiz_saved = False
            safe_rerun()

        st.write("---")
        st.subheader("Developer (debug) tools")
        if st.checkbox("Show raw session_state"):
            st.json({k: v for k, v in st.session_state.items() if k.startswith("quiz") or k in ("current_file_id","generated_task")})
        st.write("---")
        st.subheader("Change Password")

        with st.form("change_password_form"):
            current_password = st.text_input("Current Password", type="password")
            new_password = st.text_input("New Password", type="password")
            confirm_password = st.text_input("Confirm New Password", type="password")
    
            submitted = st.form_submit_button("Update Password")
    
            if submitted:
                if not current_password or not new_password or not confirm_password:
                    st.error("Please fill in all fields.")
                elif new_password != confirm_password:
                    st.error("New password and confirmation do not match.")
                else:
            # ✅ Check current password from Supabase
                    user_id = st.session_state.user.get("id")
                    resp = supabase.table("users").select("password_hash").eq("id", user_id).single().execute()
                    if not resp.data:
                        st.error("User not found!")
                    else:
                        stored_hash = resp.data.get("password_hash")
                        import bcrypt
                        
                
                        if not bcrypt.checkpw(current_password.encode(), stored_hash.encode()):
                            st.error("Current password is incorrect!")
                        else:
                    # ✅ Update password in Supabase
                            new_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
                            update_resp = supabase.table("users").update({"password_hash": new_hash}).eq("id", user_id).execute()
                            if update_resp.data:
                                st.success("Password updated successfully!")
                            else:
                                st.error("Failed to update password. Please try again.")


    # Footer tips (common)
    st.markdown("---")
    st.markdown("**Tips:** Save generated MCQs if you want to re-run quizzes from them. Use the Output History to start quizzes later.")
else:
    st.info("Please sign in to use the Study Assistant.")
