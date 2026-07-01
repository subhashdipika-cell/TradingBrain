from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
)

from app.infrastructure.database.engine import engine

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


async def get_db():
    """
    FastAPI dependency that provides a database session.
    """
    async with AsyncSessionLocal() as session:
        yield session