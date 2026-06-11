"""Grant (or revoke) Pro entitlement for a tester.

Looks the account up by username, email, OR friend code — whichever the tester
gives you — and sets their pro_status.

Usage (inside the running container):
    docker compose exec api python grant_pro.py <username|email|friend-code>
    docker compose exec api python grant_pro.py <identifier> --status free   # revoke
    docker compose exec api python grant_pro.py --list                        # see everyone

Defaults to 'comp' (the tester status). Pass '--status free' to revoke.

Heads up: email and friend code only match if the tester actually has them set.
Username is always present; friend code is shown in the app; email is optional
profile data that is NOT collected at signup — so don't rely on email alone.
"""

import argparse
import sys

from sqlalchemy import func, or_

from app import app
from models import db, User


VALID_STATUSES = {"free", "comp", "paid", "trial"}


def find_users(identifier):
    """Users matching identifier on username, email, or friend_code (all
    case-insensitive). Normally 0 or 1; more than 1 means it's ambiguous (e.g. a
    shared email) and the caller should refuse rather than comp the wrong person."""
    ident = identifier.strip()
    low = ident.lower()
    return (
        User.query.filter(
            or_(
                func.lower(User.username) == low,
                func.lower(User.email) == low,
                func.upper(User.friend_code) == ident.upper(),
            )
        )
        .all()
    )


def list_users():
    rows = User.query.order_by(User.id).all()
    if not rows:
        print("No users yet.")
        return
    print(f"{'id':>3}  {'username':<20} {'email':<28} {'friend':<11} pro_status")
    print("-" * 80)
    for u in rows:
        print(
            f"{u.id:>3}  {u.username:<20} {(u.email or '-'):<28} "
            f"{(u.friend_code or '-'):<11} {u.pro_status}"
        )


def main():
    parser = argparse.ArgumentParser(
        description="Grant or revoke Pro entitlement for a tester."
    )
    parser.add_argument(
        "identifier",
        nargs="?",
        help="username, email, or friend code of the tester",
    )
    parser.add_argument(
        "--status",
        default="comp",
        choices=sorted(VALID_STATUSES),
        help="Pro status to set (default: comp; use 'free' to revoke)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all users (id, username, email, friend code, pro_status) and exit",
    )
    args = parser.parse_args()

    with app.app_context():
        if args.list:
            list_users()
            return

        if not args.identifier:
            parser.error("provide a username / email / friend-code, or use --list")

        matches = find_users(args.identifier)
        if not matches:
            print(
                f"No user matches {args.identifier!r} "
                f"(tried username, email, and friend code)."
            )
            sys.exit(1)
        if len(matches) > 1:
            print(f"{args.identifier!r} is ambiguous — it matches several accounts:")
            for u in matches:
                print(f"  id={u.id}  username={u.username!r}  email={u.email!r}")
            print("Re-run with the exact username to pick one.")
            sys.exit(2)

        user = matches[0]
        previous = user.pro_status
        user.pro_status = args.status
        db.session.commit()
        print(
            f"{user.username} (id={user.id}): pro_status {previous!r} -> "
            f"{user.pro_status!r} (is_pro: {user.is_pro})"
        )


if __name__ == "__main__":
    main()
