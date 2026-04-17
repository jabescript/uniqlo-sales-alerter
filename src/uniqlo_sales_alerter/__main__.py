"""CLI entry-point: ``python -m uniqlo_sales_alerter [--preview-cli|--preview-html]``."""

from __future__ import annotations

import argparse
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Uniqlo Sales Alerter",
    )
    preview_group = parser.add_mutually_exclusive_group()
    preview_group.add_argument(
        "--preview-cli",
        action="store_true",
        help="Enable CLI preview and start the server.",
    )
    preview_group.add_argument(
        "--preview-html",
        action="store_true",
        help="Enable HTML preview and start the server.",
    )
    preview_group.add_argument(
        "--preview",
        action="store_true",
        help=argparse.SUPPRESS,  # backward compat alias for --preview-cli
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to config.yaml (default: config.yaml in project root).",
    )
    args = parser.parse_args()

    if args.preview or args.preview_cli:
        os.environ.setdefault("PREVIEW_CLI", "true")
    elif args.preview_html:
        os.environ.setdefault("PREVIEW_HTML", "true")

    _run_server()


def _run_server() -> None:
    try:
        import uvicorn
    except ImportError:
        print("uvicorn is required to run the server. Install it with:")
        print("  pip install uvicorn[standard]")
        sys.exit(1)

    logging.getLogger(__name__).info(
        "Settings UI: http://localhost:8000/settings",
    )

    uvicorn.run(
        "uniqlo_sales_alerter.main:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )


if __name__ == "__main__":
    main()
