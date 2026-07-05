from fastapi import status


class TradingBrainException(Exception):
    """
    Base exception for the TradingBrain application.
    """

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ResourceNotFoundException(TradingBrainException):
    """
    Raised when a requested resource does not exist.
    """

    def __init__(self, message: str = "Resource not found"):
        super().__init__(
            code="RESOURCE_NOT_FOUND",
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
        )


class ValidationException(TradingBrainException):
    """
    Raised for application-level validation errors.
    """

    def __init__(self, message: str):
        super().__init__(
            code="VALIDATION_ERROR",
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
        )