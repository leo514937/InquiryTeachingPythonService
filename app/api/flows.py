from fastapi import APIRouter

from app.workflow.flows import list_flows


router = APIRouter(prefix="/api/flows", tags=["flows"])


@router.get("")
def get_flows():
    return {"code": 0, "message": "success", "data": list_flows()}
