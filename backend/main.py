from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from database import init_db, get_db, Interaction
from schemas import ChatRequest, ChatResponse
from agent import run_agent

app = FastAPI(title="AI-First HCP CRM — Log Interaction API")

app.add_middleware( 
    CORSMiddleware,
    allow_origins=["*"],  
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """Single entrypoint the ChatPanel calls on every message. Runs the
    LangGraph agent, which routes to one of the five tools and returns a
    patch the frontend merges into Redux state."""
    result = run_agent(req.message, req.current_state.model_dump(), req.is_logged)
    return ChatResponse(
        reply=result.get("reply", ""),
        field_updates=result.get("field_updates", {}),
        suggested_followups=result.get("suggested_followups", []),
        tool_used=result.get("tool_used"),
        is_logged=result.get("is_logged", req.is_logged),
    )


@app.get("/interactions/{interaction_id}")
def get_interaction(interaction_id: str, db: Session = Depends(get_db)):
    record = db.query(Interaction).filter(Interaction.id == interaction_id).first()
    if not record:
        raise HTTPException(404, "Not found")
    return {c.name: getattr(record, c.name) for c in record.__table__.columns}


@app.get("/interactions")
def list_interactions(db: Session = Depends(get_db)):
    records = db.query(Interaction).order_by(Interaction.created_at.desc()).limit(50).all()
    return [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in records]
