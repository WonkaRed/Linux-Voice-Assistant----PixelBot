#!/usr/bin/env python3
"""Nova Server — Entry point."""
import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from nova_server.config import ServerConfig
from nova_server.server import NovaServer


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    config = ServerConfig()

    if not config.auth_token:
        logging.warning(
            "No auth_token in config.yaml! Generate one with: "
            "python3 -c \"import secrets; print(secrets.token_urlsafe(32))\""
        )

    server = NovaServer(config)

    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        logging.info("Server stopped")


if __name__ == "__main__":
    main()
