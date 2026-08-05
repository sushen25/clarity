from __future__ import annotations

import argparse
import getpass

from app import create_app
from app.auth import bootstrap_admin


def main():
    parser = argparse.ArgumentParser(description="ADHD report POC administration")
    sub = parser.add_subparsers(dest="command", required=True)
    admin = sub.add_parser("create-admin")
    admin.add_argument("--username", required=True)
    admin.add_argument("--full-name", required=True)
    admin.add_argument("--registration-number", default="")
    args = parser.parse_args()
    if args.command == "create-admin":
        password = getpass.getpass("Password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            raise SystemExit("Passwords do not match")
        app = create_app()
        with app.app_context():
            user_id = bootstrap_admin(args.username, password, args.full_name, args.registration_number)
        print(f"Created admin {args.username} ({user_id})")


if __name__ == "__main__":
    main()

