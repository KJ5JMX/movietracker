# Reel List

A JWT-authenticated movie watchlist app. Search movies via the OMDb API, save them to your private list, and track your watch status and ratings.

## Features

- Sign up / log in with JWT authentication
- Live search-as-you-type powered by the OMDb API
- Save movies to a personal, private watchlist
- Mark movies as "Want to watch" or "Watched"
- Rate watched movies on a 5-star scale
- Per-user data isolation — every watchlist item belongs to exactly one user
- Persistent storage so your watchlist survives logouts and page refreshes

## Tech Stack

**Backend**
- Python 3.13 with Flask
- SQLAlchemy (ORM) and Flask-Migrate (Alembic) for the database
- Flask-JWT-Extended for token-based auth
- Werkzeug for password hashing
- SQLite locally, ready for Postgres in production

**Frontend**
- React (Create React App)
- React Router for navigation
- React Icons for UI iconography
- Plain CSS for styling

**External**
- [OMDb API](https://www.omdbapi.com/) for movie search and details

## Project Structure

```
movie_tracker/
├── server/                  # Flask backend
│   ├── app.py               # Flask app + blueprint registration
│   ├── config.py            # Reads .env into the Flask config
│   ├── models.py            # User and WatchlistItem SQLAlchemy models
│   ├── auth_routes.py       # /auth/register, /auth/login, /auth/me
│   ├── watchlist_routes.py  # CRUD on the user's watchlist
│   ├── movie_routes.py      # OMDb search + detail proxy
│   └── migrations/          # Flask-Migrate migration history
└── client/                  # React frontend
    └── src/
        ├── App.js           # Router setup
        ├── App.css          # All styles
        ├── components/
        │   └── Navbar.js
        └── pages/
            ├── LoginPage.js
            ├── SignupPage.js
            └── DashboardPage.js
```

## Local Setup

### Prerequisites

- Python 3.13+ and [Pipenv](https://pipenv.pypa.io/)
- Node.js 20+ and npm
- A free [OMDb API key](https://www.omdbapi.com/apikey.aspx) (the verification email must be confirmed before the key is active)

### Backend

```bash
cd server
pipenv install
pipenv shell
```

Create a `.env` file in `server/` with:

```
FLASK_APP=app.py
DATABASE_URL=sqlite:///watchlist.db
SECRET_KEY=<a long random string>
JWT_SECRET_KEY=<another long random string>
OMDB_API_KEY=<your OMDb key>
```

Run migrations and start the server:

```bash
flask db upgrade
python app.py
```

Backend serves at `http://localhost:5555`.

### Frontend

```bash
cd client
npm install
npm start
```

Frontend serves at `http://localhost:3000` and talks to the Flask backend on port 5555.

## API Routes

| Method | Route                       | Auth | Purpose                                     |
| ------ | --------------------------- | ---- | ------------------------------------------- |
| GET    | `/`                         | no   | Health check                                |
| POST   | `/auth/register`            | no   | Create account, returns JWT and user        |
| POST   | `/auth/login`               | no   | Authenticate, returns JWT and user          |
| GET    | `/auth/me`                  | yes  | Current user info                           |
| GET    | `/movies/search?q=<title>`  | yes  | Search OMDb by title                        |
| GET    | `/movies/<imdb_id>`         | yes  | Full movie details from OMDb                |
| GET    | `/watchlist/`               | yes  | Current user's watchlist                    |
| POST   | `/watchlist/`               | yes  | Add a movie to the watchlist                |
| PATCH  | `/watchlist/<id>`           | yes  | Update watch_status, rating, or notes       |
| DELETE | `/watchlist/<id>`           | yes  | Remove from watchlist                       |

Protected routes require an `Authorization: Bearer <jwt>` header.

## Data Model

```
users                       watchlist_items
─────────                   ──────────────────
id          PK              id              PK
username    UNIQUE          title
password_hash               year
                            imdb_id
                            movie_type
                            plot
                            poster
                            watch_status    (default: want_to_watch)
                            rating          (1–5, nullable)
                            notes
                            user_id         FK → users.id
```

A user has many watchlist items. Each watchlist item belongs to exactly one user. Deleting a user cascades to delete their watchlist items.

## Authentication Flow

1. User registers or logs in via the React frontend
2. Backend validates credentials and returns a JWT signed with the server's `JWT_SECRET_KEY`
3. Frontend stores the token in `localStorage`
4. Every protected request sends the token in the `Authorization: Bearer <token>` header
5. Backend's `@jwt_required()` decorator validates the token and exposes the user's ID via `get_jwt_identity()`
6. Every watchlist query filters by the JWT's user ID, so users can never read or modify each other's data
