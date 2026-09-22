from __future__ import annotations

import argparse
import json

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description="Create, command, and inspect Granted genie sessions.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("new")
    create.add_argument("level", choices=["closed_door", "three_enemies", "whispering_gate"])
    create.add_argument("--id")

    wish = subparsers.add_parser("wish")
    wish.add_argument("session_id")
    wish.add_argument("text")

    show = subparsers.add_parser("show")
    show.add_argument("session_id")

    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=180) as client:
        if args.command == "new":
            response = client.post(
                "/agent/sessions", json={"level_id": args.level, "session_id": args.id}
            )
        elif args.command == "wish":
            response = client.post(
                f"/agent/sessions/{args.session_id}/wish",
                json={"wish_text": args.text, "debug": True},
            )
        else:
            response = client.get(f"/agent/sessions/{args.session_id}")
        response.raise_for_status()
        print(json.dumps(response.json(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
