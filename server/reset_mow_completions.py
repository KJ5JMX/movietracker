"""Clear the completion rows attached to the current Movie Week pick.

Why this exists: admin_set_mow reuses the MovieOfWeek row for a given week_key,
so before the 2026-08 fix, replacing the pick inside the same week left the old
week's completions attached to the new film. Everyone then saw the new title as
already watched and already rated, and the card vanished from Lists (which
filters on `completed`). The fix stops it happening again; this script cleans up
rows that already went bad.

Usage (inside the running container):
    docker compose exec api python reset_mow_completions.py            # dry run
    docker compose exec api python reset_mow_completions.py --apply    # do it

Safe to run any time. It only ever touches completions for the ACTIVE pick.
"""

import argparse

from app import app
from models import db, MovieOfWeek, MovieOfWeekCompletion


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply", action="store_true",
        help="actually delete (default is a dry run that only reports)",
    )
    args = parser.parse_args()

    with app.app_context():
        mow = (
            MovieOfWeek.query.filter_by(active=True)
            .order_by(MovieOfWeek.week_key.desc())
            .first()
        )
        if not mow:
            print("No active Movie Week. Nothing to do.")
            return

        rows = MovieOfWeekCompletion.query.filter_by(mow_id=mow.id).all()
        print(f"Active pick: {mow.title!r} ({mow.week_key}, mow_id={mow.id})")
        print(f"Completions attached: {len(rows)}")
        for r in rows:
            print(f"  user_id={r.user_id} rating={r.rating} review={r.review!r}")

        if not rows:
            return
        if not args.apply:
            print("\nDry run. Re-run with --apply to delete these.")
            return

        MovieOfWeekCompletion.query.filter_by(mow_id=mow.id).delete(
            synchronize_session=False
        )
        db.session.commit()
        print(f"\nDeleted {len(rows)} completion row(s) for {mow.title!r}.")


if __name__ == "__main__":
    main()
