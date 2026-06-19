import streamlit as st
from agents.ai import generate_response
from agents.signalagent import analyze_session_for_signal
from utils.prevChat import end_session
from utils.sheets import db

# ======================================================
# APP CONFIG
# ======================================================

st.set_page_config(
    page_title="Success Coach",
    layout="wide"
)

# ======================================================
# SAMPLE STUDENTS
# ======================================================

students = db.get_all_students()

# ======================================================
# SIDEBAR
# ======================================================

with st.sidebar:
    st.title("Success Coach")

    view = st.radio(
        "View",
        ["Student", "Coach"]
    )

    if view == "Student":
        selected_student = st.selectbox(
            "Select Student",
            students,
            format_func=lambda x: x["name"]
        )
        st.session_state["selected_student"] = selected_student
    else:
        if "selected_student" not in st.session_state:
            selected_student = students[0] if students else None
        else:
            selected_student = st.session_state["selected_student"]

    st.divider()

    if st.button("🔴 End Session", use_container_width=True):
        student_id = selected_student["id"]
        session_key = f"messages_{student_id}_{view}"
        
        # Get current session messages
        session_messages = st.session_state.get(session_key, [])
        
        # Analyze session for signals (requires human intervention)
        signal_data = analyze_session_for_signal(student_id, view, session_messages)
        
        # Create signal if needed
        if signal_data:
            db.save_signal(
                student_id=student_id,
                signal_type=signal_data["signal_type"],
                severity=signal_data["severity"],
                urgency=signal_data["urgency"],
                reason=signal_data["reason"],
                timestamp=signal_data["timestamp"],
                actioned=signal_data["actioned"]
            )

        # Save current session to Mem0
        end_session(
            session_key=session_key,
            student_id=student_id
        )

        # Clear Streamlit chat history for this session
        st.session_state.pop(session_key, None)

        st.success("Session saved!")
        st.rerun()


student_id = selected_student["id"]

# ======================================================
# CHAT KEY — unique per student + view
# ======================================================

chat_key = f"messages_{student_id}_{view}"

if chat_key not in st.session_state:
    st.session_state[chat_key] = []

# ======================================================
# HEADER
# ======================================================

left, right = st.columns([3, 1])

with left:
    if view == "Coach":
        st.title("Coach View")
    else:
        st.title(f"{view} View — {selected_student['name']}")

with right:
    st.metric(
        "Messages",
        len(st.session_state[chat_key])
    )

# ======================================================
# CHAT HISTORY
# ======================================================

chat_container = st.container()

with chat_container:
    for msg in st.session_state[chat_key]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

# ======================================================
# CHAT INPUT
# ======================================================

placeholder = (
    "Ask as student..."
    if view == "Student"
    else "Coach action..."
)

prompt = st.chat_input(placeholder)

if prompt:
    st.session_state[chat_key].append({
        "role": "user",
        "content": prompt
    })

    with st.chat_message("user"):
        st.markdown(prompt)

    role_type = "student" if view == "Student" else "coach"

    # Pass session_key so ai.py tracks the right session
    response = generate_response(
        student_id=student_id,
        message=prompt,
        type=role_type,
        session_key=chat_key        # <-- new param
    )

    st.session_state[chat_key].append({
        "role": "assistant",
        "content": response
    })

    with st.chat_message("assistant"):
        st.markdown(response)

    st.rerun()