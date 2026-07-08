import json
import os
from datetime import datetime, date as date_cls
from typing import Any, Dict, List, Optional, TypedDict

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from sqlalchemy.orm import Session

from database import Interaction, MaterialSample, SessionLocal

try:
    from langgraph.graph import StateGraph, END
except ImportError:  # pragma: no cover
    raise RuntimeError("pip install langgraph langchain-groq")

load_dotenv()

GROQ_MODEL = os.getenv("GROQ_MODEL", "gemma2-9b-it")
GROQ_FALLBACK_MODEL = os.getenv("GROQ_FALLBACK_MODEL", "llama-3.3-70b-versatile")

llm = ChatGroq(model=GROQ_MODEL, temperature=0, api_key=os.getenv("GROQ_API_KEY"))
llm_fallback = ChatGroq(model=GROQ_FALLBACK_MODEL, temperature=0.2, api_key=os.getenv("GROQ_API_KEY"))


class AgentState(TypedDict, total=False):
    message: str
    current_state: Dict[str, Any]
    is_logged: bool
    intent: str
    field_updates: Dict[str, Any]
    suggested_followups: List[str]
    reply: str
    tool_used: str


def _safe_json(raw: str) -> Dict[str, Any]:
    """Groq's JSON mode is reliable but we still guard against a stray
    code fence or preamble the model occasionally adds."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.split("\n", 1)[-1] if raw.lower().startswith("json") else raw
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end != -1:
        raw = raw[start : end + 1]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}

# node 1 -> intent router

def classify_intent(state: AgentState) -> AgentState:
    prompt = f"""You route messages from a pharma sales rep to the correct tool.
Reply with ONLY one word, no punctuation, from this list:
- log_interaction      (rep is describing a new/ongoing HCP interaction to capture for the first time)
- edit_interaction      (rep wants to change/update/correct/set a specific field, e.g. "change sentiment to positive", "update the date to tomorrow", "make it a Call", "change type to email")
- query_field          (rep is ASKING for the current value of a specific field, e.g. "what is the name?", "what time is it set to?", "show me the sentiment", "what is the date?", "tell me the attendees")
- search_materials      (rep wants to find/attach a brochure, leave-behind, or drug sample)
- sentiment_analysis    (rep explicitly asks you to judge/re-judge HCP sentiment from a description)
- suggest_followups     (rep asks "what should I do next" / "suggest follow ups")
- general               (anything else, e.g. greetings, help requests)

IMPORTANT:
- If the message uses words like "change", "update", "set", "correct", "fix", "make it", "switch to", choose edit_interaction.
- If the message uses words like "what is", "what's", "show me", "tell me", "what", "which" about a specific form field, choose query_field.

Currently logged already: {state.get("is_logged", False)}
Message: "{state['message']}"
One word answer:"""
    resp = llm.invoke(prompt).content.strip().lower()
    valid = {
        "log_interaction",
        "edit_interaction",
        "search_materials",
        "sentiment_analysis",
        "suggest_followups",
        "general",
    }
    state["intent"] = resp if resp in valid else "log_interaction"
    return state

# tool 1 -> Log Interaction
def log_interaction_tool(state: AgentState) -> AgentState:
    """Extracts structured fields (HCP, type, date/time, attendees, topics,
    materials, samples, sentiment, outcomes, follow-ups) from free text via
    the LLM, then upserts a row in `interactions` and returns the same
    fields as a patch for the Redux form."""
    today = date_cls.today().isoformat()
    prompt = f"""Extract structured HCP-interaction data from the rep's note below.
Return STRICT JSON only, matching this schema (omit a key if not mentioned,
never invent values that aren't implied by the text):

{{
  "hcp_name": string,
  "interaction_type": one of ["Meeting","Call","Email","Conference"],
  "date": "YYYY-MM-DD",
  "time": "HH:MM" (24h),
  "attendees": string (comma separated names),
  "topics_discussed": string,
  "materials_shared": [string],
  "samples_distributed": [string],
  "sentiment": one of ["Positive","Neutral","Negative"],
  "outcomes": string,
  "follow_up_actions": [string]
}}

Today's date is {today} if the rep says "today"/"just now".
Existing form values (merge/override intelligently, don't blank out fields
the new note doesn't mention): {json.dumps(state.get("current_state", {}))}

Rep's note: "{state['message']}"
JSON:"""
    raw = llm.invoke(prompt).content
    extracted = _safe_json(raw)

    # never let the LLM null-out something the rep already had on screen
    current = state.get("current_state", {})
    patch = {k: v for k, v in extracted.items() if v not in (None, "", [])}

    # Don't overwrite date, time, or interaction_type with LLM defaults
    # unless the rep explicitly mentioned them in their message.
    msg_lower = state["message"].lower()
    date_keywords = ["date", "today", "yesterday", "tomorrow", "monday", "tuesday",
                     "wednesday", "thursday", "friday", "saturday", "sunday",
                     "january", "february", "march", "april", "may", "june",
                     "july", "august", "september", "october", "november", "december"]
    time_keywords = ["time", "am", "pm", "hour", "minute", "o'clock", ":"]
    type_keywords = ["meeting", "call", "email", "conference"]

    if current.get("date") and not any(kw in msg_lower for kw in date_keywords):
        patch.pop("date", None)
    if current.get("time") and not any(kw in msg_lower for kw in time_keywords):
        patch.pop("time", None)
    if current.get("interaction_type") and not any(kw in msg_lower for kw in type_keywords):
        patch.pop("interaction_type", None)

    db: Session = SessionLocal()
    try:
        interaction_id = current.get("id")
        record = None
        if interaction_id:
            record = db.query(Interaction).filter(Interaction.id == interaction_id).first()
        if record is None:
            record = Interaction()
            db.add(record)
        for k, v in {**current, **patch}.items():
            if hasattr(record, k) and k != "id":
                setattr(record, k, v)
        db.commit()
        db.refresh(record)
        patch["id"] = record.id
    finally:
        db.close()

    state["field_updates"] = patch
    state["tool_used"] = "log_interaction"
    state["is_logged"] = True
    filled = ", ".join(k.replace("_", " ") for k in patch if k != "id")
    state["reply"] = f"Logged it — I filled in: {filled or 'the details you gave me'}. Anything to add or correct?"
    return state


# tool 2 -> Edit Interaction
def edit_interaction_tool(state: AgentState) -> AgentState:
    """Diffs the rep's correction instruction against the currently
    logged record and returns only the changed field(s)."""
    current = state.get("current_state", {})
    prompt = f"""The rep wants to CORRECT one or more fields of an already-logged
HCP interaction. Current values: {json.dumps(current)}

Instruction: "{state['message']}"

Return STRICT JSON containing ONLY the fields that should change, using the
same field names as the current values (hcp_name, interaction_type, date,
time, attendees, topics_discussed, materials_shared, samples_distributed,
sentiment, outcomes, follow_up_actions). Do not include unchanged fields.
JSON:"""
    raw = llm.invoke(prompt).content
    patch = _safe_json(raw)

    if patch:
        db: Session = SessionLocal()
        try:
            interaction_id = current.get("id")
            record = (
                db.query(Interaction).filter(Interaction.id == interaction_id).first()
                if interaction_id
                else None
            )
            if record:
                for k, v in patch.items():
                    if hasattr(record, k):
                        setattr(record, k, v)
                db.commit()
        finally:
            db.close()

    state["field_updates"] = patch
    state["tool_used"] = "edit_interaction"
    if patch:
        changed = ", ".join(f"{k.replace('_',' ')} → {v}" for k, v in patch.items())
        state["reply"] = f"Updated: {changed}."
    else:
        state["reply"] = "I couldn't tell which field to change — could you rephrase, e.g. \"set sentiment to positive\"?"
    return state

# tool 3 -> Search Materials & Samples
def search_materials_tool(state: AgentState) -> AgentState:
    """Keyword-matches the rep's request against the materials/samples
    catalogue and appends matches to the appropriate list."""
    prompt = f"""Extract search keywords (drug/product names, topic words) the rep
wants to find a brochure or sample for. Message: "{state['message']}"
Return STRICT JSON: {{"keywords": [string], "kind": "material" | "sample" | "both"}}
JSON:"""
    raw = llm.invoke(prompt).content
    parsed = _safe_json(raw)
    keywords = [k.lower() for k in parsed.get("keywords", [])]
    kind = parsed.get("kind", "both")

    db: Session = SessionLocal()
    try:
        query = db.query(MaterialSample)
        if kind in ("material", "sample"):
            query = query.filter(MaterialSample.kind == kind)
        candidates = query.all()
    finally:
        db.close()

    matches = [
        c.name
        for c in candidates
        if not keywords or any(kw in (c.tags or "").lower() or kw in c.name.lower() for kw in keywords)
    ]

    current = state.get("current_state", {})
    patch: Dict[str, Any] = {}
    if matches:
        mats = [m for m in candidates if m.name in matches and m.kind == "material"]
        samps = [m for m in candidates if m.name in matches and m.kind == "sample"]
        if mats:
            patch["materials_shared"] = list(
                dict.fromkeys(current.get("materials_shared", []) + [m.name for m in mats])
            )
        if samps:
            patch["samples_distributed"] = list(
                dict.fromkeys(current.get("samples_distributed", []) + [m.name for m in samps])
            )

    state["field_updates"] = patch
    state["tool_used"] = "search_materials"
    state["reply"] = (
        f"Found and attached: {', '.join(matches)}." if matches else "No matching materials or samples in the catalogue — try a different product name."
    )
    return state


#  tool 4 -> Sentiment Analysis
def sentiment_analysis_tool(state: AgentState) -> AgentState:
    """Infers Positive / Neutral / Negative HCP sentiment from the topics
    discussed / outcomes / raw message, with a one-line rationale."""
    current = state.get("current_state", {})
    text = " ".join(
        filter(
            None,
            [
                state["message"],
                current.get("topics_discussed", ""),
                current.get("outcomes", ""),
            ],
        )
    )
    prompt = f"""Infer the HCP's sentiment toward the product/visit from this text.
Return STRICT JSON: {{"sentiment": "Positive"|"Neutral"|"Negative", "reason": string (<=15 words)}}
Text: "{text}"
JSON:"""
    raw = llm.invoke(prompt).content
    parsed = _safe_json(raw)
    sentiment = parsed.get("sentiment", "Neutral")
    reason = parsed.get("reason", "")

    state["field_updates"] = {"sentiment": sentiment}
    state["tool_used"] = "sentiment_analysis"
    state["reply"] = f"Sentiment set to {sentiment}{f' — {reason}' if reason else ''}."
    return state


# tool 5 -> Suggest Follow-ups
def suggest_followups_tool(state: AgentState) -> AgentState:
    """Given topics/outcomes/sentiment so far, proposes next-step actions
    the rep can accept with one tap (mirrors the 'AI Suggested Follow-ups'
    checklist under the form)."""
    current = state.get("current_state", {})
    prompt = f"""Based on this HCP interaction so far, suggest up to 4 concrete
follow-up actions a pharma rep could take (e.g. schedule a follow-up call,
send a specific document, add the HCP to an advisory board, sample
replenishment). Be specific and short (<=8 words each).
Interaction: {json.dumps(current)}
Latest message: "{state['message']}"
Return STRICT JSON: {{"followups": [string]}}
JSON:"""
    raw = llm.invoke(prompt).content
    parsed = _safe_json(raw)
    followups = parsed.get("followups", [])[:4]

    state["field_updates"] = {"ai_suggested_followups": followups}
    state["suggested_followups"] = followups
    state["tool_used"] = "suggest_followups"
    state["reply"] = "Here are some suggested next steps — tap any to add them." if followups else "Not enough detail yet to suggest follow-ups."
    return state

# tool 6 -> Query Field
def query_field_tool(state: AgentState) -> AgentState:
    """Reads the current form state and returns ONLY the value of the
    specific field the rep is asking about — nothing else."""
    current = state.get("current_state", {})

    # Map of natural-language aliases → actual state keys
    FIELD_ALIASES = {
        "hcp_name":           ["name", "hcp", "hcp name", "doctor", "doctor name", "physician"],
        "interaction_type":   ["type", "interaction type", "kind", "meeting type"],
        "date":               ["date", "day", "when"],
        "time":               ["time", "hour", "when"],
        "attendees":          ["attendees", "attendee", "who", "people", "participants"],
        "topics_discussed":   ["topics", "topic", "discussed", "discussion", "what was discussed"],
        "materials_shared":   ["materials", "material", "brochure", "brochures", "documents"],
        "samples_distributed":["samples", "sample", "distributed"],
        "sentiment":          ["sentiment", "feeling", "mood", "how did it go"],
        "outcomes":           ["outcomes", "outcome", "result", "results", "what happened"],
        "follow_up_actions":  ["follow up", "follow-up", "followup", "next steps", "actions"],
    }

    msg_lower = state["message"].lower()

    # Find which field the rep is asking about
    matched_field = None
    for field, aliases in FIELD_ALIASES.items():
        if any(alias in msg_lower for alias in aliases):
            matched_field = field
            break

    if matched_field is None:
        # Ask LLM to identify the field if keyword match fails
        prompt = f"""The rep is asking about a specific field of the current interaction form.
Current form fields: {list(current.keys())}
Rep's question: "{state['message']}"
Reply with ONLY the exact field name from the list above (e.g. hcp_name, date, time, sentiment).
One word or snake_case answer:"""
        matched_field = llm.invoke(prompt).content.strip().lower().replace(" ", "_")
        if matched_field not in current:
            matched_field = None

    state["field_updates"] = {}
    state["tool_used"] = "query_field"

    if matched_field and matched_field in current:
        value = current[matched_field]
        # Format the value nicely
        if isinstance(value, list):
            if value:
                formatted = ", ".join(str(v) for v in value)
            else:
                formatted = "nothing set yet"
        elif value in (None, ""):
            formatted = "not set yet"
        else:
            formatted = str(value)
        label = matched_field.replace("_", " ").title()
        state["reply"] = f"{label}: {formatted}"
    else:
        state["reply"] = "I'm not sure which field you're asking about. Try asking like: \"what is the HCP name?\" or \"what is the date?\""

    return state


# Fallback — general help
def general_node(state: AgentState) -> AgentState:
    prompt = f"""You are a concise assistant embedded in a pharma CRM "Log HCP
Interaction" screen. Answer briefly and steer the rep back to logging an
interaction if relevant. Message: "{state['message']}" """
    state["reply"] = llm_fallback.invoke(prompt).content.strip()
    state["field_updates"] = {}
    state["tool_used"] = "general"
    return state


#   Build the graph
def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("classify_intent", classify_intent)
    graph.add_node("log_interaction", log_interaction_tool)
    graph.add_node("edit_interaction", edit_interaction_tool)
    graph.add_node("query_field", query_field_tool)
    graph.add_node("search_materials", search_materials_tool)
    graph.add_node("sentiment_analysis", sentiment_analysis_tool)
    graph.add_node("suggest_followups", suggest_followups_tool)
    graph.add_node("general", general_node)

    graph.set_entry_point("classify_intent")
    graph.add_conditional_edges(
        "classify_intent",
        lambda s: s["intent"],
        {
            "log_interaction": "log_interaction",
            "edit_interaction": "edit_interaction",
            "query_field": "query_field",
            "search_materials": "search_materials",
            "sentiment_analysis": "sentiment_analysis",
            "suggest_followups": "suggest_followups",
            "general": "general",
        },
    )
    for node in [
        "log_interaction",
        "edit_interaction",
        "query_field",
        "search_materials",
        "sentiment_analysis",
        "suggest_followups",
        "general",
    ]:
        graph.add_edge(node, END)

    return graph.compile()


agent_graph = build_graph()


def run_agent(message: str, current_state: Dict[str, Any], is_logged: bool) -> AgentState:
    initial: AgentState = {
        "message": message,
        "current_state": current_state,
        "is_logged": is_logged,
    }
    return agent_graph.invoke(initial)
