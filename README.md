# Movie Tracker

A JWT-authenticated watchlist app: search movies via OMDb, save them to your private list, and track watch status and ratings.

Built with Flask + SQLAlchemy on the backend and React (Vite) on the frontend.

## Project Structure

```
movie_tracker/
├── server/         # Flask API (Python 3.13, Pipenv)
└── client/         # React frontend (Vite)
```

## Local Setup

### Backend

```bash
cd server
cp .env.example .env        # then fill in OMDB_API_KEY and JWT_SECRET_KEY
pipenv install
pipenv shell
flask db upgrade            # run migrations
flask run --port 5555
```

The API serves on `http://localhost:5555` under the `/api` prefix.
Health check: `GET /api/health`.

### Frontend

```bash
cd client
npm install
npm run dev
```

The dev server runs on `http://localhost:5173` and proxies `/api` requests to the Flask backend.

## API Routes

All backend routes are prefixed with `/api`. Protected routes require an `Authorization: Bearer <jwt>` header.

| Method | Route                  | Auth | Purpose                       |
| ------ | ---------------------- | ---- | ----------------------------- |
| POST   | /api/signup            | no   | Create account, return JWT    |
| POST   | /api/login             | no   | Authenticate, return JWT      |
| GET    | /api/me                | yes  | Current user                  |
| GET    | /api/movies/search?q=  | no   | Search OMDb by title          |
| GET    | /api/movies/<imdb_id>  | no   | Movie details from OMDb       |
| GET    | /api/watchlist         | yes  | Current user's watchlist      |
| POST   | /api/watchlist         | yes  | Add a movie                   |
| PATCH  | /api/watchlist/<id>    | yes  | Update status / rating / notes |
| DELETE | /api/watchlist/<id>    | yes  | Remove from watchlist         |

## Status

Work in progress. See git log for current state.
