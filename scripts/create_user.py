"""
create_user.py — Create or update a login in the local credentials file (config/users.yaml).

The password is read without echo (prompted twice) or, for automation, from
standard input with --password-stdin. It is stored only as a bcrypt hash and
is never printed or logged.

Usage:
    python scripts/create_user.py oren --workspace personal
    python scripts/create_user.py demo --workspace demo --password-stdin < pw.txt
    python scripts/create_user.py oren --workspace personal --users-file /path/users.yaml

Docker (the `tools` service mounts ./config read-write):
    docker compose run --rm tools scripts/create_user.py oren --workspace personal
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.auth import AuthError, upsert_user, users_file  # noqa: E402
from app.workspace import KNOWN_WORKSPACES  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or update a local login.")
    parser.add_argument("username")
    parser.add_argument("--workspace", required=True, choices=KNOWN_WORKSPACES,
                        help="Data workspace for this login: personal (owner) or demo (sample data).")
    parser.add_argument("--users-file", default=None, help=f"Credentials file (default: {users_file()})")
    parser.add_argument("--password-stdin", action="store_true", help="Read the password from standard input.")
    args = parser.parse_args()

    if args.password_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    else:
        password = getpass.getpass("New password: ")
        if getpass.getpass("Repeat password: ") != password:
            print("Passwords do not match.", file=sys.stderr)
            return 1

    path = Path(args.users_file) if args.users_file else None
    try:
        upsert_user(args.username, args.workspace, password, path=path)
    except AuthError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"User '{args.username}' saved (workspace: {args.workspace}) in {path or users_file()}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
