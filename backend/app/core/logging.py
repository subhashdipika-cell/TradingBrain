from loguru import logger
import sys

logger.remove()

logger.add(
    sys.stdout,
    level="INFO",
    colorize=True,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
)