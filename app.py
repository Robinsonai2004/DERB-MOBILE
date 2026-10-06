#!/usr/bin/env python3
"""
DERB MOBILE - local server entry point.

Run from the project folder:

    python app.py

Then open http://localhost:8080 in the Android browser (same phone).
No internet connection is required.
"""

from __future__ import annotations

import socket
import sys

import config
from web import create_app

app = create_app()


def _lan_ip() -> str:
    """Best-effort local network address so a PC on the same Wi-Fi can connect."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # no packets sent; just picks the route
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def banner() -> None:
    line = "=" * 52
    print(line)
    print(f"  {config.BRAND_COMPANY}")
    print(f"  {config.BRAND_PRODUCT}  v{config.BRAND_VERSION}")
    print(f"  {config.BRAND_PHASE}")
    print(line)
    print(f"  Phone (this device):  http://localhost:{config.PORT}")
    print(f"  Same Wi-Fi network:   http://{_lan_ip()}:{config.PORT}")
    print(f"  Documents folder:     {config.DERB_ROOT}")
    print(f"  Database:             {config.DB_PATH}")
    print(line)
    print("  Press CTRL+C to stop the server.")
    print(line)


if __name__ == "__main__":
    banner()
    try:
        app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG,
                use_reloader=False, threaded=True)
    except KeyboardInterrupt:
        print("\nDERB MOBILE stopped.")
        sys.exit(0)
