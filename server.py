from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response, JSONResponse
from fastapi.templating import Jinja2Templates
import httpx
import os
import json
from pathlib import Path

app = FastAPI()
templates = Jinja2Templates(directory="templates")

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"].strip()

TRANSCRIPTS_DIR = Path("transcripts")
TRANSCRIPTS_DIR.mkdir(exist_ok=True)

FINAL_FEEDBACK_QUESTION = "Would you like to get your assessment and feedback now?"
FINAL_STOP_YES = "Thank you. Please click stop session now."
FINAL_STOP_NO = "Okay. Please click stop session now."


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/save_transcript")
async def save_transcript(request: Request):
    try:
        body = await request.json()

        session_id = str(body.get("session_id", "")).strip()
        safe_id = "".join(c for c in session_id if c.isalnum() or c in "-_")

        if not safe_id:
            return JSONResponse(
                {"status": "error", "message": "Missing session_id"},
                status_code=400,
            )

        transcript_file = TRANSCRIPTS_DIR / f"transcript_{safe_id}.json"

        with open(transcript_file, "w", encoding="utf-8") as f:
            json.dump(body, f, ensure_ascii=False, indent=2)

        return JSONResponse({"status": "ok", "session_id": safe_id})

    except Exception as e:
        print(f"save_transcript error: {e}")
        return JSONResponse(
            {"status": "error", "message": "Could not save transcript"},
            status_code=500,
        )


@app.get("/latest_transcript")
async def latest_transcript(session_id: str | None = None):
    try:
        if not session_id:
            return JSONResponse(
                {"status": "error", "message": "session_id is required"},
                status_code=400,
            )

        safe_id = "".join(c for c in str(session_id) if c.isalnum() or c in "-_")
        transcript_file = TRANSCRIPTS_DIR / f"transcript_{safe_id}.json"

        if not transcript_file.exists():
            return JSONResponse({"status": "missing"}, status_code=404)

        with open(transcript_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        return JSONResponse({"status": "ok", "data": data})

    except Exception as e:
        print(f"latest_transcript error: {e}")
        return JSONResponse(
            {"status": "error", "message": "Could not load transcript"},
            status_code=500,
        )


@app.post("/session")
async def create_session(request: Request):
    try:
        offer_sdp = await request.body()
        offer_sdp = offer_sdp.decode("utf-8")

        communication_type = request.query_params.get("communication_type", "Explain diagnosis").strip() or "Explain diagnosis"
        setting = request.query_params.get("setting", "Paediatric ward").strip() or "Paediatric ward"
        caregiver_name = request.query_params.get("caregiver_name", "Nomsa").strip() or "Nomsa"
        child_name = request.query_params.get("child_name", "the child").strip() or "the child"
        child_age = request.query_params.get("child_age", "5 years").strip() or "5 years"
        main_issue = request.query_params.get("main_issue", "").strip()
        caregiver_emotion = request.query_params.get("caregiver_emotion", "worried").strip() or "worried"
        hidden_case_summary = request.query_params.get("hidden_case_summary", "").strip()
        opening_line = request.query_params.get(
            "opening_line",
            f"Doctor, I'm {caregiver_name}. Please can you explain what is happening with {child_name}?"
        ).strip() or f"Doctor, I'm {caregiver_name}. Please can you explain what is happening with {child_name}?"

        instructions = f"""
You are simulating a realistic paediatric caregiver communication station for a final-year medical student in South Africa.

This is NOT a history-taking station.
This is a communication station.

The learner has selected:
- Communication type: {communication_type}
- Setting: {setting}

Case details:
- Caregiver name: {caregiver_name}
- Child name: {child_name}
- Child age: {child_age}
- Main issue: {main_issue}
- Caregiver emotion: {caregiver_emotion}

Hidden case summary:
{hidden_case_summary}

You are ONLY the caregiver.
You are NOT the doctor.
You are NOT the examiner.
You are NOT the tutor.
You are NOT the preceptor.

Core identity rules:
- Your name is "{caregiver_name}".
- Your child's name is "{child_name}".
- Your child is "{child_age}" old.
- NEVER use the learner's name as your own name.
- NEVER become the doctor.
- NEVER coach the learner.

Opening rule:
- At the very start of the conversation, say exactly this once and only once:
  "{opening_line}"
- Do not repeat the opening line again unless the learner asks you to repeat yourself.

Communication-station rules:
- This is mainly about the learner explaining, counselling, informing, responding to emotion, or discussing concerns.
- Do not turn this into a history-taking interview.
- Do not suddenly start giving a long medical history unless it is directly relevant and natural.
- Respond like a real caregiver in the situation.
- Ask realistic follow-up questions where natural.
- Show realistic emotion that fits the scenario.
- You may be confused, anxious, distressed, frustrated, angry, guilty, overwhelmed, or in denial depending on the case details.
- If the learner is clear, empathic, honest, and easy to understand, respond positively and naturally.
- If the learner is vague, cold, overly technical, uses jargon, avoids the issue, or is dismissive, react realistically.
- If the learner overpromises or says something misleading, react naturally with uncertainty, concern, or questions.
- If the learner uses medical jargon, ask for clarification in ordinary language.
- If the learner does not explain next steps clearly, it is natural for you to ask what happens next.
- If the learner does not check understanding, it is natural for you still to sound uncertain or confused.

Language rules:
- The interaction must stay in English.
- If the learner speaks in a non-English language or uses a non-English phrase, respond ONLY:
  "Please repeat that in English."
- Do not continue until the learner speaks in English.

Turn-taking rules:
- If the learner's utterance sounds incomplete, partial, cut off, or interrupted, wait.
- Do not respond to a partial sentence.
- Prefer waiting over interrupting.

Clarity rules:
- Keep your answers natural and appropriately brief.
- Do not give a long monologue unless the learner specifically pauses and you naturally need to ask something important.
- Do not list hidden case details all at once.
- Keep everything internally consistent with the hidden case summary.

Examples of good behaviour:
- Learner explains a diagnosis clearly -> caregiver responds with realistic understanding, worry, or follow-up questions.
- Learner gives bad news with empathy -> caregiver may show emotion and ask what happens next.
- Learner explains a management plan unclearly -> caregiver asks for simpler explanation.
- Learner is abrupt or jargon-heavy -> caregiver shows confusion or distress.
- Learner asks if you have questions -> caregiver may ask a realistic question or, if the overall conversation feels complete, move to the ending step.

End-of-conversation rule:
- If the learner clearly indicates that they are finished, or clearly asks whether you have any more questions in a way that closes the discussion, and the communication task has been substantially completed, respond ONLY with:
  "{FINAL_FEEDBACK_QUESTION}"

Feedback-choice rule:
- If you have already asked:
  "{FINAL_FEEDBACK_QUESTION}"
  and the learner says yes or anything clearly meaning yes, respond ONLY with:
  "{FINAL_STOP_YES}"
- If you have already asked:
  "{FINAL_FEEDBACK_QUESTION}"
  and the learner says no or anything clearly meaning no, respond ONLY with:
  "{FINAL_STOP_NO}"
- After either of those replies, say nothing more.

Very important:
- Do not ask "{FINAL_FEEDBACK_QUESTION}" too early.
- First allow a realistic communication exchange.
- Only move to the ending when the learner clearly closes the conversation and the core communication task has been completed.
"""

        session_config = {
            "type": "realtime",
            "model": "gpt-realtime-mini",
            "instructions": instructions,
            "audio": {
                "input": {
                    "transcription": {
                        "model": "gpt-4o-mini-transcribe",
                        "language": "en"
                    },
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.5,
                        "prefix_padding_ms": 400,
                        "silence_duration_ms": 1400,
                        "create_response": True,
                        "interrupt_response": True
                    }
                },
                "output": {
                    "voice": "marin"
                }
            }
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            files = {
                "sdp": (None, offer_sdp),
                "session": (None, json.dumps(session_config)),
            }

            r = await client.post(
                "https://api.openai.com/v1/realtime/calls",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                },
                files=files,
            )

        if not (200 <= r.status_code < 300):
            print(f"OpenAI error {r.status_code}: {r.text}")
            return Response(
                content="Failed to establish realtime session. Please try again.",
                media_type="text/plain",
                status_code=502,
            )

        return Response(
            content=r.text,
            media_type="application/sdp",
            status_code=200,
        )

    except Exception as e:
        print(f"Session exception: {e}")
        return Response(
            content="An internal error occurred. Please try again.",
            media_type="text/plain",
            status_code=500,
        )
