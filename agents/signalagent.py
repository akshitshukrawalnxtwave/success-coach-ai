import json
from datetime import datetime
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

load_dotenv()

llm = ChatOpenAI(
    model="gpt-5.4-mini-2026-03-17",
    temperature=0.3,
)


def analyze_session_for_signal(student_id, view, messages):
    """
    Analyze session conversation to determine if a signal should be created.
    
    Args:
        student_id: The student's ID
        view: "Student" or "Coach"
        messages: List of session messages [{"role": "user/assistant", "content": "..."}, ...]
    
    Returns:
        dict with signal data if intervention needed, None otherwise
        Signal format: {
            "signal_type": str,
            "severity": str,  # "Low", "Medium", "High"
            "urgency": str,   # "Low", "Medium", "High"
            "reason": str,
            "timestamp": str,
            "actioned": "No"
        }
    """
    if not messages:
        return None
    
    # Format conversation for analysis
    conversation_text = "\n".join(
        [f"{msg.get('role', 'unknown').upper()}: {msg.get('content', '')}" for msg in messages]
    )
    
    system_prompt = """You are an educational signal detection system. Analyze the session conversation and determine if human intervention is needed.

CRITERIA FOR CREATING A SIGNAL:
1. **Academic Distress**: Student struggling with concepts, failing, or requesting help beyond AI capability
2. **Attendance/Engagement Issues**: Low attendance, disengagement, or withdrawal signs
3. **Emotional/Mental Distress**: Student expressing stress, anxiety, depression, or crisis indicators
4. **Behavioral Concerns**: Concerning patterns or issues requiring faculty attention
5. **Knowledge Gaps**: Topics requiring specialized human mentoring or tutoring

RESPOND WITH JSON (no markdown):
{
    "create_signal": true/false,
    "signal_type": "Academic" | "Attendance" | "Mental Health" | "Behavioral" | "Other",
    "severity": "Low" | "Medium" | "High",
    "urgency": "Low" | "Medium" | "High",
    "reason": "Brief, specific reason for the signal"
}

If no signal needed, set create_signal to false."""
    
    human_prompt = f"""Analyze this session for signal creation:

CONVERSATION:
{conversation_text}

VIEW TYPE: {view}
STUDENT ID: {student_id}

Provide your JSON response:"""
    
    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt)
        ])
        
        # Extract JSON from response
        response_text = response.content.strip()
        
        # Try to parse JSON
        signal_data = json.loads(response_text)
        
        if not signal_data.get("create_signal", False):
            return None
        
        # Build signal record
        signal = {
            "signal_type": signal_data.get("signal_type", "Other"),
            "severity": signal_data.get("severity", "Medium"),
            "urgency": signal_data.get("urgency", "Medium"),
            "reason": signal_data.get("reason", "Session analysis flagged for review"),
            "timestamp": datetime.now().isoformat(),
            "actioned": "No"
        }
        
        print(f"Signal created for student {student_id}: {signal_data.get('signal_type')}")
        return signal
        
    except json.JSONDecodeError as e:
        print(f"Error parsing signal agent response: {e}")
        return None
    except Exception as e:
        print(f"Error in signal analysis: {e}")
        return None
