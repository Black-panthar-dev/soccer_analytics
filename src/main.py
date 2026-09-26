"""Local command-line entry point and logging bootstrap."""

from __future__ import annotations

import logging
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIRECTORY = PROJECT_ROOT / "output"
LOG_PATH = OUTPUT_DIRECTORY / "run.log"


def configure_logging() -> None:
    """Configure console and project-owned file logging."""
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
        ],
    )


def main() -> int:
    """Initialize the local application without processing data yet."""
    configure_logging()
    logging.getLogger(__name__).info(
        "Repository setup is complete; processing is not implemented in this chunk."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
