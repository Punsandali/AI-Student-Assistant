import google.generativeai as genai

class Generator:
    def __init__(self, api_key="AIzaSyCfFeW01gjF4ncS13gRlmEpdYhNf9aee7c", model_name="gemini-2.5-flash"):
        self.api_key = api_key
        self.model_name = model_name
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(model_name=self.model_name)

    def generate(self, context, task="summary", n_questions=5):
        # -----------------------------------------
        # 0️⃣ Stop if no relevant content
        # -----------------------------------------
        if not context:
            return (
                "⚠️ No relevant chunks found. Cannot generate summary, flashcards, or MCQs. "
                "Try a different query related to the lecture."
            )

        # Convert list of chunks → one text string
        if isinstance(context, list):
            context = "\n".join(context)

        # -----------------------------------------
        # 1️⃣ Build task-specific prompts
        # -----------------------------------------
        if task == "summary":
            prompt = (
                "Instruction: Using only the CONTEXT, write a concise summary.\n\n"
                f"CONTEXT:\n{context}\n\nSUMMARY:\n"
            )
        elif task == "flashcards":
            prompt = (
                "Instruction: From the CONTEXT, produce flashcards in JSON list with 'question' and 'answer'. "
                "Max 10 cards.\n\n"
                f"CONTEXT:\n{context}\n\nFLASHCARDS:\n"
            )
        elif task == "mcq":
            prompt = f"""
Instruction: Using ONLY the CONTEXT below, create {n_questions} multiple-choice questions.
Each question must have:
- 1 correct answer
- 3 plausible and distinct incorrect options
- A short rationale for the correct answer
Do NOT copy the text verbatim. Distractors must be logically plausible but different from the correct answer.

Output in JSON format:
[
  {{"question":"...","options":["A","B","C","D"],"answer":"A","rationale":"..."}}
]

CONTEXT:
{context}

QUESTIONS:
"""
        else:
            raise ValueError("Invalid task type")

        # -----------------------------------------
        # 2️⃣ Generate Content Safely
        # -----------------------------------------
        response = self.model.generate_content(prompt)

        # -----------------------------------------
        # 3️⃣ Extract text safely
        # -----------------------------------------
        if response and response.candidates:
            try:
                return response.candidates[0].content.parts[0].text
            except:
                return "The model returned an unexpected format."
        else:
            return "No output generated."
