# AI-First HCP CRM — Log Interaction Screen

A "Log Interaction" screen for a pharma field-rep CRM that can be filled
either by hand (structured form) or by typing/dictating a note to an AI
assistant that fills — and later edits — the same form in real time.

```
hcp-crm/
├── backend/           FastAPI + LangGraph + Groq agent
│   ├── agent.py        the LangGraph graph and 5 tools
│   ├── main.py          FastAPI app, /chat endpoint
│   ├── database.py      SQLAlchemy models (Postgres/MySQL)
│   ├── schemas.py        Pydantic I/O contracts
│   └── requirements.txt
└── frontend/          React + Redux Toolkit
    └── src/
        ├── store/          interactionSlice.js (single source of truth)
        └── components/     LogInteractionForm.jsx, ChatPanel.jsx
```

## Why this shape

The structured form and the chat panel both read/write the **same Redux
slice** (`interaction`). The chat panel never renders its own copy of the
data — it calls `POST /chat`, gets back a small JSON *patch*
(`field_updates`), and dispatches `patchApplied(patch)`. That's what makes
"fill this in for me" and "no, change the date to next Tuesday" work
identically: every AI action is just a patch to the one form.

## Role of the LangGraph agent

The agent is the layer between "what the rep typed" and "what changed on
the form." On every message it:

1. **Routes** the message to one of five tools using an LLM intent
   classifier (`classify_intent` node) — it doesn't try to do everything
   in one giant prompt, which keeps each tool's prompt small, testable,
   and cheap to run on `llama-3.1-8b-instant`.
2. **Extracts / reasons** using the LLM, scoped to that tool's job only.
3. **Reconciles** the result against the interaction already on screen
   (via `current_state` sent with every request) so it never blanks out
   fields the new message didn't mention.
4. **Persists** the change (log/edit tools upsert a row in `interactions`)
   and **returns a patch + a short natural-language reply**, so the rep
   sees both the updated form and a confirmation in chat.

Field reps are often on the move, so the agent is intentionally
conservative: it only writes fields it's confident about, echoes back what
it changed, and lets a one-line follow-up message ("no, negative") correct
it — rather than trying to be right in one shot.

## The five tools

| # | Tool | Purpose |
|---|------|---------|
| 1 | **`log_interaction`** | Extracts HCP name, interaction type, date/time, attendees, topics, materials/samples, sentiment, outcomes, and follow-ups from a free-text note via the LLM, merges them with whatever's already on the form, and upserts the `interactions` row. This is what fires the first time a rep describes a visit. |
| 2 | **`edit_interaction`** | Diffs a correction instruction ("change sentiment to positive", "move the meeting to 3pm") against the currently logged record and returns *only* the changed field(s), so unrelated fields are never touched. |
| 3 | **`search_materials_and_samples`** | Extracts product/keyword intent ("share the OncoBoost Phase III PDF") and matches it against a materials/samples catalogue table, appending matches to `materials_shared` / `samples_distributed`. |
| 4 | **`sentiment_analysis`** | Infers Positive / Neutral / Negative HCP sentiment from the discussion/outcome text with a short rationale — usable standalone ("what do you think their sentiment was?") or as part of tool 1's extraction. |
| 5 | **`suggest_followups`** | Given topics, outcomes and sentiment so far, proposes up to four concrete next steps (schedule a follow-up, send a document, add to an advisory board list) that render as tappable chips under "AI Suggested Follow-ups", matching tool 2's job of *editing* the record when the rep accepts one. |

All five are plain Python functions operating on a shared `AgentState`
TypedDict inside a `langgraph.graph.StateGraph` — a router node picks the
tool, the tool node updates state, and every tool node edges straight to
`END`.

## Tech stack (as required)

- **Frontend:** React + Redux Toolkit, Google Inter font
- **Backend:** Python, FastAPI
- **Agent framework:** LangGraph (`StateGraph`)
- **LLM:** Groq `llama-3.1-8b-instant` for extraction/routing (fast + cheap),
  `llama-3.3-70b-versatile` as a fallback for open-ended chat
- **DB:** Postgres or MySQL via SQLAlchemy (swap the `DATABASE_URL` DSN)

## Running it

**Backend**
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your Groq key from console.groq.com/keys
uvicorn main:app --reload --port 8000
```

**Frontend**
```bash
cd frontend
npm install
echo "REACT_APP_API_BASE=http://localhost:8000" > .env
npm start
```

Open the app, type something like:

> "Met Dr. Sharma, discussed OncoBoost Phase III efficacy, she was
> positive, shared the brochure and left a sample"

and watch HCP name, topics, sentiment, materials, and samples fill in on
the left. Follow up with "actually make that neutral sentiment" to see the
`edit_interaction` tool at work.
