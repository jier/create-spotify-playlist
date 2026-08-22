from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Credentials (from .env)
    spotify_client_id: str = Field(default="", validation_alias="SPOTIPY_CLIENT_ID")
    spotify_client_secret: str = Field(default="", validation_alias="SPOTIPY_CLIENT_SECRET")
    spotify_redirect_uri: str = Field(default="http://127.0.0.1:8000/callback", validation_alias="SPOTIFY_REDIRECT_URI")

    # Spotify API
    spotify_auth_base: str = "https://accounts.spotify.com"
    spotify_api_base: str = "https://api.spotify.com/v1"
    spotify_scopes: str = (
        "playlist-read-private playlist-modify-private playlist-modify-public "
        "user-library-read user-library-modify user-read-private"
    )

    # TSP playlist ordering distance weights.
    # distance = (genre_weight × jaccard_genre_dist) + (year_weight × normalized_year_dist)
    # Spotify deprecated /audio-features (Nov 2024) — genre + release year are the remaining signals.
    playlist_genre_weight: float = 1.0
    playlist_year_weight: float = 0.5
    # Jaccard genre distance threshold for candidate filtering (applied to genre overlap only, not total distance).
    # 0.75 = candidate must share >25% genre overlap with seed.
    # Prevents off-genre tracks (e.g. afrogospel, kompa) from entering playlist when seed genre is CCM/worship.
    # Progressive fallback relaxes this to 0.85 → 0.95 → 1.0 before trying artist discography.
    playlist_max_candidate_distance: float = 0.75
    # Max tracks per artist in the candidate pool.
    # Prevents popular artists (Elevation Worship, Hillsong) from flooding search results and dominating the playlist.
    playlist_max_tracks_per_artist: int = 3

    # Simulated annealing selection parameters (strategy="sa").
    # Energy = avg_relevance − sa_diversity_weight × avg_pairwise_diversity (both normalised).
    # sa_diversity_weight: 0.0 = pure relevance, 1.0 = equal weight, >1.0 = diversity-first.
    sa_diversity_weight: float = 0.5
    sa_temperature_start: float = 1.0
    sa_temperature_end: float = 0.01
    sa_iterations: int = 1000

    # Local storage
    token_path: Path = Path(__file__).parent.parent / "token.json"

    # Playlist DNA run traces (src/algorithms/persistence.py). Absolute, not
    # relative to cwd — same reasoning as env_file below: a relative "runs"
    # path silently lands wherever the process happens to be started from.
    runs_dir: Path = Path(__file__).parent.parent / "runs"
    # Age-based retention: runs older than this are deleted on app startup
    # (see lifespan in src/app.py) and via `make clean-runs`.
    runs_retention_days: float = 7.0

    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent / ".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
