from fastapi import APIRouter, Depends

from api.feedback.schemas import FeedbackCreate, FeedbackListQuery
from api.feedback.service import feedback_service
from settings.dependencies import CommonQueryParams

router = APIRouter()


@router.post("/feedback")
def create_feedback(request_body: FeedbackCreate, common: CommonQueryParams = Depends()):
    return feedback_service.create(request_body, common)


@router.post("/feedback/list")
def list_feedback(request_body: FeedbackListQuery, common: CommonQueryParams = Depends()):
    return feedback_service.list_public(request_body, common)
