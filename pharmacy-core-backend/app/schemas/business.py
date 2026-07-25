"""HTTP request/response schemas for the Business Intelligence Agent."""
from pydantic import BaseModel , Field 

class BusinessAnalysisRequest(BaseModel):
      """Request received from the frontend."""
      
      question : str = Field(...,min_length=3,
        max_length=500,
        description="Natural language business question.",
        examples=["Why did my profit decrease this month?"], )
      
class BusinessAnalysisResponse(BaseModel):
    """Response returned to the frontend."""

    answer: str
    confidence: float
    execution_time_ms: int
    agent_version: str
      
