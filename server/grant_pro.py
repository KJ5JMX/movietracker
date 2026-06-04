"""Grant Pro entitlement to a user (used to comp testers).

Usage on the VM:
    pipenv run python grant_pro.py <username> [--status comp|paid|trial|free]

Defaults to 'comp'. Pass 'free' to revoke.
"""

import argparse
import sys

from app import app
from models import db, User


VALID_STATUSES = {"free", "comp", "paid", "trial"}


def main():
    parser = argparse.ArgumentParser(description="Grant Pro entitlement to a user.")
    parser.add_argument("username")
    parser.add_argument(
        "--status",
        default="comp",
        choices=sorted(VALID_STATUSES),
        help="Pro status to set (default: comp)",
    )
    args = parser.parse_args()

    with app.app_context():
        user = User.query.filter_by(username=args.username).first()
        if not user:
            print(f"No user named {args.username!r}")
            sys.exit(1)
        previous = user.pro_status
        user.pro_status = args.status
        db.session.commit()
        print(
            f"{user.username}: pro_status {previous!r} -> {user.pro_status!r} "
            f"(is_pro: {user.is_pro})"
        )


if __name__ == "__main__":
    main()
