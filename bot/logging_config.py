import logging
import sys


def configure_logging() -> None:
    """Send logs immediately to stdout, like print()."""
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        force=True,
    )
