from dotenv import load_dotenv
from agent.prevChat import fetch_previous_chat

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

load_dotenv()   # Loads OPENAI_API_KEY from .env


llm = ChatOpenAI(
    model="gpt-5.4-mini-2026-03-17",
    temperature=0.7
)


def generate_response(student_id, message, type):
    """
    type = 'student' or 'coach'
    Returns assistant response string
    """

    # Fetch previous conversation
    previous_chat = fetch_previous_chat(student_id)

    if not previous_chat:
        previous_chat = "No previous conversation."

    if isinstance(previous_chat, list):
        previous_chat = "\n".join(previous_chat)

    # Dynamic role prompt
    role_instruction = {
        "student": """
Explain concepts simply.
Use examples when useful.
Act like a helpful tutor.
""",

        "coach": """
Provide mentoring.
Give actionable guidance.
Encourage progress and accountability.
"""
    }.get(type, "Be helpful.")

    system_prompt = f"""
You are an educational AI assistant.

Rules:
- Use previous chat when relevant.
- Give concise and useful responses.
- Maintain context across conversations.

Role:
{role_instruction}
"""

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        (
            "human",
            """
Previous Chat:
{history}

User Message:
{message}
"""
        )
    ])

    chain = prompt | llm

    response = chain.invoke({
        "history": previous_chat,
        "message": message
    })

    return response.content