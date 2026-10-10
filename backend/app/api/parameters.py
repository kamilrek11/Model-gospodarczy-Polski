from fastapi import APIRouter

from app.model.params import schema_as_dicts

router = APIRouter(prefix="/parameters", tags=["parameters"])


@router.get("")
def get_parameters() -> list[dict]:
    return schema_as_dicts()
