import ollama
from modules.database import log_suggestion


class TeachingAdvisorAgent:
    def __init__(self, model_name: str = "llama3.2:3b"):
        self.model_name = model_name

    def generate_suggestion(self, session_id: str, metrics: dict, present_count: int, total_students: int) -> str:
        """Generates context-aware teaching suggestions locally using Ollama."""
        engagement = metrics.get("total_engagement", 0.0)
        gaze = metrics.get("gaze_score", 0.0)
        movement = metrics.get("movement_score", 0.0)
        audio = metrics.get("audio_score", 0.0)
        inactivity = metrics.get("inactivity_sec", 0.0)

        prompt = (
            f"You are an assistive classroom intelligence coach. Analyze these live anonymous session metrics:\n"
            f"- Attendance: {present_count}/{total_students} learners present\n"
            f"- Overall Engagement: {engagement}%\n"
            f"- Visual Attention (Gaze/Head Alignment): {gaze}%\n"
            f"- Posture/Movement Activity: {movement}% (Inactivity duration: {inactivity}s)\n"
            f"- Vocal/Audio Interaction Level: {audio}%\n\n"
            f"Provide exactly 2 short, practical, non-intrusive teaching suggestions for the instructor right now. "
            f"Keep each suggestion to 1 sentence."
        )

        try:
            response = ollama.chat(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "You give concise, supportive pedagogical suggestions based on classroom analytics."},
                    {"role": "user", "content": prompt},
                ],
                options={"temperature": 0.3, "num_predict": 140},
            )
            suggestion = response["message"]["content"].strip()
        except Exception:
            # Offline rule-based fallback if Ollama background service is paused
            if engagement < 55.0 and audio < 20.0:
                suggestion = (
                    "• Attention and vocal interaction are both low—pause the lecture for a quick 60-second concept check or poll.\n"
                    "• Ask an open-ended question to re-engage learners showing prolonged downward gaze."
                )
            elif gaze < 60.0:
                suggestion = (
                    "• Visual focus is drifting away from the screen—summarize the current slide's key takeaway before advancing.\n"
                    "• Introduce a brief visual example or real-world application to recapture attention."
                )
            elif audio > 70.0 and gaze >= 70.0:
                suggestion = (
                    "• Strong active discussion and visual focus detected—allow 1–2 more minutes for peer Q&A before moving on.\n"
                    "• Capture key student questions on the board to reinforce participation."
                )
            else:
                suggestion = (
                    "• Classroom pacing and attention are steady—maintain current delivery speed.\n"
                    "• Consider a brief comprehension check in the next 5 minutes to sustain momentum."
                )

        log_suggestion(session_id=session_id, engagement_level=engagement, suggestion=suggestion)
        return suggestion


if __name__ == "__main__":
    agent = TeachingAdvisorAgent()
    sample_metrics = {
        "total_engagement": 51.5,
        "gaze_score": 48.0,
        "movement_score": 65.0,
        "audio_score": 12.0,
        "inactivity_sec": 18.0,
    }
    print("Testing Offline AI Teaching Advisor...\n")
    advice = agent.generate_suggestion("TEST_SESSION", sample_metrics, present_count=1, total_students=1)
    print("AI Teaching Suggestions:\n" + advice)