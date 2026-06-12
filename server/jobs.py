"""Background jobs process. Runs alongside gunicorn in the container
(started by entrypoint.sh) so scheduled pushes don't depend on web traffic
and don't double-send across gunicorn workers.

Every CHECK_INTERVAL seconds:
  1. Release reminders: items flagged remind_release whose release date has
     arrived get one push, then release_reminded flips so it never repeats.
  2. Movie Night reminders: scheduled sessions starting within the next
     hour push all participants once.
"""

import time
from datetime import date, datetime, timedelta

from app import app
from models import db, MovieNightSession, MovieNightParticipant, WatchlistItem
from push import notify
from watchlist_routes import _parse_release_date

CHECK_INTERVAL = 10 * 60  # seconds


def _release_reminders():
    candidates = WatchlistItem.query.filter(
        WatchlistItem.remind_release.is_(True),
        WatchlistItem.release_reminded.is_(False),
    ).all()
    today = date.today()
    for item in candidates:
        release = _parse_release_date(item.released)
        if not release or release > today:
            continue
        label = {"movie": "movie", "tv": "show", "book": "book", "song": "song"}
        kind = label.get(item.media_type, "title")
        notify(
            [item.user_id],
            "Out now",
            f"{item.title} is out · the {kind} on your shelf released today",
            app=app,
        )
        item.release_reminded = True
    if candidates:
        db.session.commit()


def _night_reminders():
    now = datetime.utcnow()
    soon = now + timedelta(hours=1)
    sessions = MovieNightSession.query.filter(
        MovieNightSession.status == "scheduled",
        MovieNightSession.reminder_sent.is_(False),
        MovieNightSession.scheduled_for != None,  # noqa: E711
        MovieNightSession.scheduled_for <= soon,
        MovieNightSession.scheduled_for > now - timedelta(hours=6),
    ).all()
    for s in sessions:
        participant_ids = [
            p.user_id
            for p in MovieNightParticipant.query.filter_by(session_id=s.id).all()
        ]
        notify(
            participant_ids,
            "Movie Night soon",
            f"Your movie night starts at {s.scheduled_for.strftime('%-I:%M %p')}",
            app=app,
        )
        s.reminder_sent = True
    if sessions:
        db.session.commit()


def main():
    print("[jobs] reminder loop starting")
    while True:
        try:
            with app.app_context():
                _release_reminders()
                _night_reminders()
        except Exception as e:
            print(f"[jobs] cycle failed: {e}")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
