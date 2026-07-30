"""HTTP request/response schemas for the Business Intelligence Agent."""
from pydantic import BaseModel , Field 

class BusinessAnalysisRequest(BaseModel):
      """Request received from the frontend."""
      
      question : str = Field(...,min_length=3,
        max_length=500,
        description="Natural language business question.",
        examples=["Why did my profit decrease this month?"], )

      thread_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description=(
            "Conversation id. Send the same value for every turn of a chat to "
            "keep its memory; use a new value to start a fresh conversation."
        ),
        examples=["conv-8f3a1c2b"],
      )

class BusinessAnalysisResponse(BaseModel):
    """Response returned to the frontend."""

    answer: str
    confidence: float
    execution_time_ms: int
    agent_version: str
      
