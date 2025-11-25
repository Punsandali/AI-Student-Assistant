import streamlit as st
from supabase import create_client, Client
import bcrypt
import uuid
from datetime import datetime

# -----------------------
# SUPABASE CONFIG
# -----------------------
SUPABASE_URL = "https://fvqnabzyhdfqjyiymgkq.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZ2cW5hYnp5aGRmcWp5aXltZ2txIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjM1NTAzNDcsImV4cCI6MjA3OTEyNjM0N30.7ipg_sFgSa0hRIWFX96iv180cL9X54vHVpj4nmmQYnM" # Use service key for server-side ops
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# -----------------------
# USER AUTH FUNCTIONS
# -----------------------
def signup_user(email, password):
    # Check if user exists
    resp = supabase.table("app_users_clean").select("id").eq("email", email).execute()
    if resp.data:
        return False, "User already exists"

    # Hash password
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    # Insert user
    user_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    insert_resp = supabase.table("app_users_clean").insert({
        "id": user_id,
        "email": email,
        "password_hash": hashed,
        "created_at": now
    }).execute()

    if insert_resp.data:
        return True, {"id": user_id, "email": email}
    else:
        return False, "Failed to create user"

def login_user(email, password):
    resp = supabase.table("app_users_clean").select("id,email,password_hash").eq("email", email).execute()
    if not resp.data:
        return False, "User not found"

    stored_hash = resp.data[0]["password_hash"]
    if bcrypt.checkpw(password.encode(), stored_hash.encode()):
        return True, resp.data[0]
    else:
        return False, "Incorrect password"

# -----------------------
# STREAMLIT AUTH UI
# -----------------------
def auth_ui():
    if "user" not in st.session_state:
        st.session_state.user = None

    st.markdown("<h1 style='text-align:center;color:#1E90FF'>LearnMate</h1>", unsafe_allow_html=True)

    if not st.session_state.user:
        auth_mode = st.radio("Choose action:", ["Login", "Sign Up"])
        email = st.text_input("📧 Email")
        password = st.text_input("🔒 Password", type="password")

        if st.button(auth_mode):
            if not email or not password:
                st.warning("Please enter both email and password.")
            else:
                if auth_mode == "Sign Up":
                    success, user = signup_user(email, password)
                    if success:
                        st.success("Account created!")
                        st.session_state.user = user
                        st.rerun()
                    else:
                        st.error(user)
                else:
                    success, user_or_msg = login_user(email, password)
                    if success:
                        st.success(f"Login successful! Welcome {email}")
                        st.session_state.user = user_or_msg
                        st.rerun()
                    else:
                        st.error(user_or_msg)
    else:
        st.info(f"Logged in as: {st.session_state.user['email']}")
        if st.button("Logout"):
            st.session_state.user = None
            st.rerun()

