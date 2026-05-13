import { useState, useEffect } from "react";
import API_URL from "../config";

function DashboardPage() {
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState(null);
  const [selectedMovie, setSelectedMovie] = useState(null);
  const [watchlist, setWatchlist] = useState([]);
  const [error, setError] = useState(null);

  function authFetch(url, options) {
    return fetch(url, options).then((response) => {
      if (response.status === 401) {
        localStorage.removeItem("token");
        window.location.href = "/login";
        return;
      }
      return response.json();
    });
  }

  function fetchWatchlist() {
    const token = localStorage.getItem("token");
    authFetch(`${API_URL}/watchlist/`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((data) => {
        if (data) setWatchlist(data);
      })
      .catch((err) => {
        console.error("Error:", err);
        setError("An error occurred loading your watchlist.");
      });
  }

  useEffect(() => {
    fetchWatchlist();
  }, []);

  // Debounced search-as-you-type
  useEffect(() => {
    if (!query.trim()) {
      setSearchResults(null);
      return;
    }
    const timer = setTimeout(() => {
      const token = localStorage.getItem("token");
      authFetch(`${API_URL}/movies/search?q=${encodeURIComponent(query)}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then((data) => {
          if (data) setSearchResults(data);
        })
        .catch((err) => {
          console.error("Search error:", err);
        });
    }, 350);
    return () => clearTimeout(timer);
  }, [query]);

  const handleSelectSearchResult = (imdbId) => {
    const token = localStorage.getItem("token");
    authFetch(`${API_URL}/movies/${imdbId}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((data) => {
        if (data) {
          setSelectedMovie(data);
          setQuery("");
          setSearchResults(null);
        }
      })
      .catch((err) => {
        console.error("Error:", err);
        setError("An error occurred loading movie details.");
      });
  };

  const handleAddToWatchlist = () => {
    const token = localStorage.getItem("token");
    authFetch(`${API_URL}/watchlist/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        title: selectedMovie.title,
        year: selectedMovie.year,
        imdb_id: selectedMovie.imdb_id,
        movie_type: selectedMovie.movie_type,
        plot: selectedMovie.plot,
        poster: selectedMovie.poster,
      }),
    })
      .then((data) => {
        if (data && data.id) {
          fetchWatchlist();
        } else if (data && data.message) {
          setError(data.message);
        }
      })
      .catch((err) => {
        console.error("Error:", err);
        setError("An error occurred adding to watchlist.");
      });
  };

  const handleUpdateItem = (updates) => {
    const token = localStorage.getItem("token");
    authFetch(`${API_URL}/watchlist/${selectedMovie.id}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(updates),
    })
      .then((data) => {
        if (data && data.id) {
          setSelectedMovie(data);
          fetchWatchlist();
        }
      })
      .catch((err) => {
        console.error("Error:", err);
        setError("An error occurred updating the item.");
      });
  };

  const handleDelete = () => {
    const token = localStorage.getItem("token");
    authFetch(`${API_URL}/watchlist/${selectedMovie.id}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(() => {
        setSelectedMovie(null);
        fetchWatchlist();
      })
      .catch((err) => {
        console.error("Error:", err);
        setError("An error occurred deleting the item.");
      });
  };

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <h1>Reel List</h1>
        <div className="search-container">
          <input
            type="text"
            className="search-input"
            placeholder="Search for a movie..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {searchResults && query.trim() && (
            <ul className="search-dropdown">
              {searchResults.length === 0 ? (
                <li className="dropdown-empty">No movies found</li>
              ) : (
                searchResults.map((movie) => (
                  <li
                    key={movie.imdb_id}
                    className="dropdown-item"
                    onClick={() => handleSelectSearchResult(movie.imdb_id)}
                  >
                    {movie.poster ? (
                      <img
                        src={movie.poster}
                        alt={movie.title}
                        className="dropdown-poster"
                      />
                    ) : (
                      <div className="dropdown-poster placeholder" />
                    )}
                    <span>
                      {movie.title} ({movie.year})
                    </span>
                  </li>
                ))
              )}
            </ul>
          )}
        </div>
      </header>

      {error && (
        <div className="error-modal">
          <p>{error}</p>
          <button onClick={() => setError(null)}>OK</button>
        </div>
      )}

      <div className="dashboard-body">
        <aside className="watchlist-panel">
          <h2>Your Watchlist</h2>
          {watchlist.length === 0 ? (
            <p className="empty-state">
              Your watchlist is empty. Search for a movie to add one.
            </p>
          ) : (
            <ul className="watchlist-list">
              {watchlist.map((item) => (
                <li
                  key={item.id}
                  className={`watchlist-item ${
                    selectedMovie && selectedMovie.id === item.id
                      ? "selected"
                      : ""
                  }`}
                  onClick={() => setSelectedMovie(item)}
                >
                  {item.poster ? (
                    <img
                      src={item.poster}
                      alt={item.title}
                      className="watchlist-poster"
                    />
                  ) : (
                    <div className="watchlist-poster placeholder">No image</div>
                  )}
                  <div className="watchlist-info">
                    <div className="watchlist-title">{item.title}</div>
                    {item.year && (
                      <div className="watchlist-year">{item.year}</div>
                    )}
                    {item.watch_status === "watched" && (
                      <div className="watchlist-status">✓ Watched</div>
                    )}
                    {item.rating && (
                      <div className="watchlist-rating">
                        {"★".repeat(item.rating)}
                      </div>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <main className="detail-panel">
          {selectedMovie ? (
            <div className="movie-detail">
              <div className="detail-actions">
                <button
                  className="btn-secondary"
                  onClick={() => setSelectedMovie(null)}
                >
                  Close
                </button>
                {!selectedMovie.id && (
                  <button
                    className="btn-primary"
                    onClick={handleAddToWatchlist}
                  >
                    + Add to Watchlist
                  </button>
                )}
              </div>
              <div className="detail-body">
                {selectedMovie.poster && (
                  <img
                    src={selectedMovie.poster}
                    alt={selectedMovie.title}
                    className="detail-poster"
                  />
                )}
                <div className="detail-meta">
                  <h2>{selectedMovie.title}</h2>
                  <p className="detail-year">{selectedMovie.year}</p>
                  {selectedMovie.genre && (
                    <p>
                      <strong>Genre:</strong> {selectedMovie.genre}
                    </p>
                  )}
                  {selectedMovie.runtime && (
                    <p>
                      <strong>Runtime:</strong> {selectedMovie.runtime}
                    </p>
                  )}
                  {selectedMovie.plot && (
                    <p className="detail-plot">{selectedMovie.plot}</p>
                  )}

                  {selectedMovie.id && (
                    <div className="detail-controls">
                      <label className="control-row">
                        <span>Status:</span>
                        <select
                          value={selectedMovie.watch_status}
                          onChange={(e) =>
                            handleUpdateItem({ watch_status: e.target.value })
                          }
                        >
                          <option value="want_to_watch">Want to watch</option>
                          <option value="watched">Watched</option>
                        </select>
                      </label>
                      <label className="control-row">
                        <span>Rating:</span>
                        <select
                          value={selectedMovie.rating || ""}
                          onChange={(e) =>
                            handleUpdateItem({
                              rating: e.target.value
                                ? parseInt(e.target.value)
                                : null,
                            })
                          }
                        >
                          <option value="">No rating</option>
                          <option value="1">★</option>
                          <option value="2">★★</option>
                          <option value="3">★★★</option>
                          <option value="4">★★★★</option>
                          <option value="5">★★★★★</option>
                        </select>
                      </label>
                      <button className="btn-danger" onClick={handleDelete}>
                        Delete from Watchlist
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="empty-state-large">
              <p>Search for a movie to get started.</p>
              <p>Click an item in your watchlist to view its details.</p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

export default DashboardPage;
