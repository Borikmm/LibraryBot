import logging
import sys
import os


def configure_logging() -> None:
    """Send logs immediately to stdout, like print()."""
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        stream=sys.stdout,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        force=True,
    )
    # HTTP client INFO messages contain the Bot API URL, including its token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
