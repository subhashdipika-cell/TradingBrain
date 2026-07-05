from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.exceptions import TradingBrainException
from app.schemas.error import ErrorDetail, ErrorResponse


async def tradingbrain_exception_handler(
    request: Request,
    exc: TradingBrainException,
) -> JSONResponse:
    """
    Handles all TradingBrain custom exceptions.
    """

    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=ErrorDetail(
                code=exc.code,
                message=exc.message,
            )
        ).model_dump(),
    )