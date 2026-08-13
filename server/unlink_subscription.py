"""Detach an Apple subscription from a Bardo account (testing utility).

One Apple subscription unlocks exactly one Bardo account: verify-receipt stores
`apple_original_transaction_id` on the user and refuses (409) if another account
presents the same receipt. That guard is correct in production, but it blocks
sandbox testing across several accounts on one Apple ID -- cancelling in Apple
Settings does NOT clear the stored link.

This clears the link (and optionally resets pro status) so the receipt can be
claimed by another account.

Usage (inside the running container):
    docker compose exec api python unlink_subscription.py <username|email|friend-code>
    docker compose exec api python unlink_subscription.py <identifier> --reset-pro
    docker compose exec api python unlink_subscription.py --list

--reset-pro also sets pro_status back to 'free' and clears pro_expires_at, which
is usually what you want when re-testing a purchase from scratch. Comp accounts
are left alone unless you pass --reset-pro explicitly.
"""

import argparse
import sys

from sqlalchemy import func, or_

from app import app
from models import db, User


def find_users(identifier):
    ident = identifier.strip()
    low = ident.lower()
    return User.query.filter(
        or_(
            func.lower(User.username) == low,
            func.lower(User.email) == low,
            func.upper(User.friend_code) == ident.upper(),
        )
    ).all()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("identifier", nargs="?", help="username, email, or friend code")
    parser.add_argument("--reset-pro", action="store_true",
                        help="also set pro_status=free and clear pro_expires_at")
    parser.add_argument("--list", action="store_true",
                        help="show every account that currently holds a subscription link")
    args = parser.parse_args()

    with app.app_context():
        if args.list:
            rows = User.query.filter(
                User.apple_original_transaction_id.isnot(None)
            ).order_by(User.id).all()
            if not rows:
                print("No accounts have an Apple subscription linked.")
                return
            for u in rows:
                print(f"id={u.id} {u.username!r} pro_status={u.pro_status!r} "
                      f"expires={u.pro_expires_at} txn={u.apple_original_transaction_id}")
            return

        if not args.identifier:
            parser.error("give an identifier, or use --list")

        matches = find_users(args.identifier)
        if not matches:
            print(f"No account matches {args.identifier!r}.")
            sys.exit(1)
        if len(matches) > 1:
            print("Ambiguous — matches:", ", ".join(u.username for u in matches))
            sys.exit(2)

        user = matches[0]
        before = user.apple_original_transaction_id
        if before is None and not args.reset_pro:
            print(f"{user.username}: no subscription linked. Nothing to do.")
            return

        user.apple_original_transaction_id = None
        if args.reset_pro:
            user.pro_status = "free"
            user.pro_expires_at = None
        db.session.commit()

        print(f"{user.username} (id={user.id}): unlinked transaction {before!r}")
        if args.reset_pro:
            print(f"  pro_status -> 'free', pro_expires_at cleared")
        print("That receipt can now be claimed by another account.")


if __name__ == "__main__":
    main()
