"""Start the browser company diagram (API + built frontend).

Usage:
  python src/backend/server.py [--host 127.0.0.1] [--port 8765] [--open]

Settings default to WEB_HOST / WEB_PORT (environment or .env); see src/backend/config.py.
"""

import argparse
import sys
import threading
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import db  # noqa: E402
from backend.app import create_app  # noqa: E402
from backend.config import FRONTEND_DIST, load_settings  # noqa: E402


def main() -> int:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Serve the browser company diagram.")
    parser.add_argument("--host", default=settings.web_host, help=f"default {settings.web_host}")
    parser.add_argument("--port", type=int, default=settings.web_port, help=f"default {settings.web_port}")
    parser.add_argument("--open", action="store_true", help="Open the diagram in the default browser.")
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        print("Missing packages. Run: bash scripts/setup_web.sh", file=sys.stderr)
        return 1

    db.init_pool(settings)
    try:
        db.check_connection()
    except db.Error as exc:
        print(f"Cannot connect to the database: {exc}", file=sys.stderr)
        print("Run scripts/setup_database.sh to set it up, or check .env.", file=sys.stderr)
        return 1

    shown_host = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
    url = (settings.public_url if (args.host, args.port) == (settings.web_host, settings.web_port)
           else f"http://{shown_host}:{args.port}")
    print(f"Company diagram: {url}")
    print(f"API docs:        {url}/api/docs")
    if not (FRONTEND_DIST / "index.html").is_file():
        print("The frontend is not built yet; run: bash scripts/setup_web.sh", file=sys.stderr)
    print("Press Ctrl+C to stop.")
    if args.open:
        threading.Timer(1.0, webbrowser.open, (url,)).start()

    uvicorn.run(create_app(settings), host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
