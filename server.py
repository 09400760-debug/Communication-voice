from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response, JSONResponse
from fastapi.templating import Jinja2Templates
import httpx
import os
import json
from pathlib import Path
from datetime import datetime, timezone

app = FastAPI()
templates = Jinja2Templates(directory="templates")

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"].strip()

TRANSCRIPTS_DIR = Path("transcripts")
TRANSCRIPTS_DIR.mkdir(exist_ok=True)

FINAL_FEEDBACK_QUESTION = "Would you like to receive your assessment now?"

FEMALE_VOICE = "marin"
MALE_VOICE = "cedar"


def now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_session_id(session_id: str) -> str:
    return "".join(c for c in str(session_id).strip() if c.isalnum() or c in "-_")


def parse_iso_datetime(value: str | None):
    if not value:
        return None
    try:
        cleaned = str(value).strip()
        if cleaned.endswith("Z"):
            cleaned = cleaned.replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned)
    except Exception:
        return None


def compute_duration_seconds(started_at: str | None, ended_at: str | None):
    start_dt = parse_iso_datetime(started_at)
    end_dt = parse_iso_datetime(ended_at)
    if not start_dt or not end_dt:
        return None
    try:
        return max(0, int((end_dt - start_dt).total_seconds()))
    except Exception:
        return None


def choose_voice(caregiver_gender: str, caregiver_role: str) -> str:
    gender = str(caregiver_gender or "").strip().lower()
    role = str(caregiver_role or "").strip().lower()

    if gender == "male":
        return MALE_VOICE
    if gender == "female":
        return FEMALE_VOICE
    if any(word in role for word in ["father", "grandfather", "uncle", "male"]):
        return MALE_VOICE
    return FEMALE_VOICE


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.head("/")
async def home_head():
    return Response(status_code=200)


@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)


@app.post("/save_transcript")
async def save_transcript(request: Request):
    try:
        body = await request.json()

        session_id = str(body.get("session_id", "")).strip()
        safe_id = safe_session_id(session_id)

        if not safe_id:
            return JSONResponse(
                {"status": "error", "message": "Missing session_id"},
                status_code=400,
            )

        transcript_file = TRANSCRIPTS_DIR / f"transcript_{safe_id}.json"

        started_at = body.get("started_at")
        ended_at = body.get("ended_at") or now_iso_utc()
        duration_seconds = body.get("duration_seconds")

        if duration_seconds is None:
            duration_seconds = compute_duration_seconds(started_at, ended_at)

        transcript_payload = {
            "session_id": safe_id,
            "study_number": body.get("study_number"),
            "interaction_mode": body.get("interaction_mode"),
            "communication_type": body.get("communication_type"),
            "setting": body.get("setting"),
            "caregiver_name": body.get("caregiver_name"),
            "caregiver_gender": body.get("caregiver_gender"),
            "caregiver_role": body.get("caregiver_role"),
            "child_name": body.get("child_name"),
            "child_age": body.get("child_age"),
            "child_sex": body.get("child_sex"),
            "main_issue": body.get("main_issue"),
            "caregiver_emotion": body.get("caregiver_emotion"),
            "student_context": body.get("student_context"),
            "hidden_case_summary": body.get("hidden_case_summary"),
            "opening_line": body.get("opening_line"),
            "siblings": body.get("siblings"),
            "residence": body.get("residence"),
            "household_structure": body.get("household_structure"),
            "school_or_daycare": body.get("school_or_daycare"),
            "caregiver_occupation": body.get("caregiver_occupation"),
            "caregiver_understanding": body.get("caregiver_understanding"),
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_seconds": duration_seconds,
            "session_completed": body.get("session_completed", False),
            "timeout_reason": body.get("timeout_reason"),
            "transcript_lines": body.get("transcript_lines", []),
            "transcript_text": body.get("transcript_text", ""),
            "saved_at": now_iso_utc(),
        }

        with open(transcript_file, "w", encoding="utf-8") as f:
            json.dump(transcript_payload, f, ensure_ascii=False, indent=2)

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

        safe_id = safe_session_id(session_id)
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
        caregiver_gender = request.query_params.get("caregiver_gender", "female").strip() or "female"
        caregiver_role = request.query_params.get("caregiver_role", "mother").strip() or "mother"
        child_name = request.query_params.get("child_name", "the child").strip() or "the child"
        child_age = request.query_params.get("child_age", "5 years").strip() or "5 years"
        child_sex = request.query_params.get("child_sex", "male").strip() or "male"
        main_issue = request.query_params.get("main_issue", "").strip()
        caregiver_emotion = request.query_params.get("caregiver_emotion", "worried").strip() or "worried"
        student_context = request.query_params.get("student_context", "").strip()
        hidden_case_summary = request.query_params.get("hidden_case_summary", "").strip()
        opening_line = request.query_params.get(
            "opening_line",
            f"Doctor, I'm {caregiver_name}, {child_name}'s {caregiver_role}. Please can you explain what is happening?"
        ).strip() or f"Doctor, I'm {caregiver_name}, {child_name}'s {caregiver_role}. Please can you explain what is happening?"

        siblings = request.query_params.get("siblings", "").strip()
        residence = request.query_params.get("residence", "").strip()
        household_structure = request.query_params.get("household_structure", "").strip()
        school_or_daycare = request.query_params.get("school_or_daycare", "").strip()
        caregiver_occupation = request.query_params.get("caregiver_occupation", "").strip()
        caregiver_understanding = request.query_params.get("caregiver_understanding", "").strip()

        session_id = request.query_params.get("session_id", "").strip()
        study_number = request.query_params.get("study_number", "").strip()
        interaction_mode = request.query_params.get("interaction_mode", "").strip()

        selected_voice = choose_voice(caregiver_gender, caregiver_role)

        instructions = f"""
You are simulating a realistic paediatric caregiver communication station for a final-year medical student in South Africa.

This is NOT a history-taking station.
This is a communication station.

The learner has selected:
- Communication type: {communication_type}
- Setting: {setting}

Case details:
- Caregiver name: {caregiver_name}
- Caregiver gender: {caregiver_gender}
- Caregiver role: {caregiver_role}
- Caregiver occupation: {caregiver_occupation or "Not specified"}
- Child name: {child_name}
- Child age: {child_age}
- Child sex: {child_sex}
- Main issue: {main_issue}
- Caregiver emotion: {caregiver_emotion}
- Current caregiver understanding: {caregiver_understanding or "Not specified"}
- Siblings: {siblings or "Not specified"}
- Residence: {residence or "Not specified"}
- Household structure: {household_structure or "Not specified"}
- School/daycare: {school_or_daycare or "Not specified"}

Visible student context:
{student_context or "Not provided"}

Session metadata:
- Study number: {study_number or "Not provided"}
- Interaction mode: {interaction_mode or "Not provided"}
- Session ID: {session_id or "Not provided"}

Hidden case summary:
{hidden_case_summary}

You are ONLY the caregiver.
You are NOT the doctor.
You are NOT the examiner.
You are NOT the tutor.
You are NOT the preceptor.

Core identity rules:
- Your name is "{caregiver_name}".
- Your role is "{caregiver_role}".
- Your child's name is "{child_name}".
- Your child is "{child_age}" old.
- NEVER use the learner's name as your own name.
- NEVER become the doctor.
- NEVER coach the learner.

Opening rule:
- At the very start of the conversation, say exactly this once and only once:
  "{opening_line}"
- Do not repeat the opening line again unless the learner asks you to repeat yourself.
- If the learner gives only a brief greeting after that, reply briefly and naturally without repeating the full opening line.

Communication-station rules:
- This is mainly about the learner explaining, counselling, informing, responding to emotion, or discussing concerns.
- Do not turn this into a history-taking interview.
- Do not suddenly start giving a long medical history unless it is directly relevant and natural.
- Respond like a real caregiver in the situation.
- Ask realistic follow-up questions where natural.
- Show realistic emotion that fits the scenario.

Dynamic emotional response:
- Your emotional state should change realistically during the conversation.
- At the start, your emotional tone should match the case details.
- If the learner is clear, empathic, honest, checks understanding, and explains things in simple language, you may gradually become calmer, more trusting, more reassured, and easier to engage.
- If the learner is vague, cold, dismissive, misleading, avoids the core issue, or uses too much jargon, you should become more confused, frustrated, distressed, doubtful, or upset.
- Do not keep exactly the same emotional tone throughout if the learner's communication changes.
- Let your reactions feel dynamic and realistic rather than fixed.

Caregiver question behaviour:
- If the learner explains clearly, it is natural for you to ask fewer anxious follow-up questions.
- If the learner leaves gaps, it is natural for you to ask more questions such as what this means, how serious it is, what happens next, whether the child will be okay, or what you should do.
- If the learner uses medical jargon, ask for clarification in ordinary language.
- If the learner does not explain next steps clearly, it is natural for you to ask what happens next.
- If the learner does not check understanding, it is natural for you still to sound uncertain or confused.

Realism rules:
- You should know obvious background facts about your child, home, and family comfortably and naturally.
- If asked about siblings, where you live, who stays at home, daycare/school, or your work, answer confidently and directly using the known facts above.
- Do NOT say "I'm not sure" to ordinary non-medical facts that a normal caregiver would know.
- Uncertainty should mainly relate to:
  - the diagnosis
  - seriousness of the condition
  - prognosis
  - next steps
  - treatment plan
  - implications for the child
  - difficult communication issues

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

End-of-conversation rule:
- If the learner clearly indicates that they are finished, or clearly asks whether you have any more questions in a way that closes the discussion, and the communication task has been substantially completed, respond ONLY with:
  "{FINAL_FEEDBACK_QUESTION}"

After asking "{FINAL_FEEDBACK_QUESTION}":
- Wait for the learner's answer.
- Do not say anything else unless the learner asks a simple clarification.
- Do not say "click stop session".
- Do not give feedback.
- Do not score.
- Do not coach.

Very important:
- Do not ask "{FINAL_FEEDBACK_QUESTION}" too early.
- First allow a realistic communication exchange.
- Only move to the ending when the learner clearly closes the conversation and the core communication task has been completed.
""".strip()

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
                        "threshold": 0.6,
                        "prefix_padding_ms": 400,
                        "silence_duration_ms": 900,
                        "create_response": True,
                        "interrupt_response": True
                    }
                },
                "output": {
                    "voice": selected_voice
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
