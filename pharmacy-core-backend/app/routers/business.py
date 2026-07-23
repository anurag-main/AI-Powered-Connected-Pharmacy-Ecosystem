"""HTTP layer for the Business Intelligence Agent.

Receives a business question from the frontend and delegates
the request to the BusinessService.
"""

from fastapi import APIRouter , Depends , status
from app.schemas.business import (
  BusinessAnalysisRequest,
  BusinessAnalysisResponse
)

from app.services import BusinessService 

def get_business_service() -> BusinessService :
      """Dependency provider for BusinessService."""
      return BusinessService
    
router = APIRouter(
    prefix="/api/v1/business",
    tags=["Business Intelligence"],
)

@router.post("/analyze", response_model=BusinessAnalysisResponse,
             status_code=status.HTTP_200_OK,
                 summary="Analyze pharmacy business performance using AI",)
def analyze_business(
  request: BusinessAnalysisRequest,
  service: BusinessService=Depends(get_business_service), 
)-> BusinessAnalysisResponse:
  """
    Analyze the pharmacy business and return AI-generated insights.
    """
    
  return service.analyze(request)
  
  

