import streamlit as st
from agent.ai import generate_response
from sheets import db

# ======================================================
# PLACEHOLDERS (you will implement these)
# ======================================================


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
        # Store selected student in session state for Coach view
        st.session_state["selected_student"] = selected_student
    else:
        # In Coach view, use the previously selected student
        if "selected_student" not in st.session_state:
            selected_student = students[0] if students else None
        else:
            selected_student = st.session_state["selected_student"]

    st.divider()

    if st.button("End Session"):
        st.session_state.pop("messages", None)
        st.rerun()


student_id = selected_student["id"]


# ======================================================
# LOAD CHAT HISTORY
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
        st.title(
            f"{view} View — {selected_student['name']}"
        )

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
    # Append user message to session state
    st.session_state[chat_key].append({
        "role": "user",
        "content": prompt
    })

    # Display user message
    with st.chat_message("user"):
        st.markdown(prompt)

    role_type = (
        "student"
        if view == "Student"
        else "coach"
    )

    response = generate_response(
        student_id=student_id,
        message=prompt,
        type=role_type
    )

    # Append assistant response to session state
    st.session_state[chat_key].append({
        "role": "assistant",
        "content": response
    })

    # Display assistant response
    with st.chat_message("assistant"):
        st.markdown(response)

    # Rerun to update chat history
    st.rerun()