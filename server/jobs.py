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
from models import (
    db, MovieNightSession, MovieNightParticipant, WatchlistItem,
    Battle, BattleVote, User,
)
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
            category="reminders",
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
            "Your movie night starts within the hour",
            app=app,
            category="movie_nights",
        )
        s.reminder_sent = True
    if sessions:
        db.session.commit()


def _battle_results():
    """When a battle's voting window has closed, announce the winner once to
    everyone, then mark it inactive so it never re-sends. This also nudges the
    curator that it's time to set up the next battle."""
    now = datetime.utcnow()
    battles = Battle.query.filter(
        Battle.active.is_(True),
        Battle.ends_at.isnot(None),
        Battle.ends_at < now,
    ).all()
    if not battles:
        return
    user_ids = [u.id for u in User.query.with_entities(User.id).all()]
    for b in battles:
        a = BattleVote.query.filter_by(battle_id=b.id, choice="a").count()
        bb = BattleVote.query.filter_by(battle_id=b.id, choice="b").count()
        if a == bb:
            msg = f"{b.title}: it's a tie!"
        else:
            winner = b.a_title if a > bb else b.b_title
            msg = f"{winner} won {b.title}"
        notify(
            user_ids, "Battle results", msg,
            app=app, category="festival", data={"type": "battle_result"},
        )
        b.active = False  # announced exactly once
    db.session.commit()


def main():
    print("[jobs] reminder loop starting")
    while True:
        try:
            with app.app_context():
                _release_reminders()
                _night_reminders()
                _battle_results()
        except Exception as e:
            print(f"[jobs] cycle failed: {e}")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
