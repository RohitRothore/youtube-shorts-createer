#!/usr/bin/env python3
"""Start the YouTube Short Creator web app."""

import uvicorn

from src.config import Settings


def main() -> None:
    settings = Settings.from_env()
    uvicorn.run(
        "app:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )


if __name__ == "__main__":
    main()
