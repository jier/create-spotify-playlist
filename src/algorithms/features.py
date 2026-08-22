"""Build the genre/year genome for a track. Pure: takes already-fetched data, no HTTP."""


def build_track_features(tracks: list[dict], artist_genres: dict[str, set[str]]) -> list[list]:
    """
    Build [[track_id, {genres, release_year, duration_ms}], ...] for distance computation.
    Spotify /audio-features is deprecated (Nov 2024) — genre + release year are used instead.
    """
    result = []
    for track in tracks:
        artists = track.get("artists", [])
        artist_id = artists[0]["id"] if artists else None
        genres = artist_genres.get(artist_id, set()) if artist_id else set()

        release_date = track.get("album", {}).get("release_date", "0")
        try:
            release_year = int(release_date[:4])
        except ValueError:
            release_year = 0

        result.append(
            [
                track["id"],
                {"genres": genres, "release_year": release_year, "duration_ms": track.get("duration_ms", 0)},
            ]
        )
    return result
