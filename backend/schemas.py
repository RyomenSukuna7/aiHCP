from typing import List, Optional
from pydantic import BaseModel, Field


class InteractionState(BaseModel):
    """Shape of the Redux 'interaction' slice on the frontend. The agent
    reads the current state (so it knows what's already filled) and
    returns a partial patch of the same shape."""

    id: Optional[str] = None
    hcp_name: str = ""
    interaction_type: str = "Meeting"
    date: str = ""
    time: str = ""
    attendees: str = ""
    topics_discussed: str = ""
    materials_shared: List[str] = Field(default_factory=list)
    samples_distributed: List[str] = Field(default_factory=list)
    sentiment: str = "Neutral"
    outcomes: str = ""
    follow_up_actions: List[str] = Field(default_factory=list)
    ai_suggested_followups: List[str] = Field(default_factory=list)


class ChatRequest(BaseModel):
    message: str
    current_state: InteractionState = Field(default_factory=InteractionState)
    # true once a record has been persisted via the Log tool; tells the
    # router whether "update X" should hit edit_interaction vs log_interaction
    is_logged: bool = False


class ChatResponse(BaseModel):
    reply: str
    field_updates: dict = Field(default_factory=dict)
    suggested_followups: List[str] = Field(default_factory=list)
    tool_used: Optional[str] = None
    is_logged: bool = False
