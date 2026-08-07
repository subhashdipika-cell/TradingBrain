from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends

from app.infrastructure.database.session import get_db

router = APIRouter(tags=["Database"])


@router.get("/database")
async def database_health(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(text("SELECT 1"))

    return {
        "database": "connected",
        "result": result.scalar_one(),
    }