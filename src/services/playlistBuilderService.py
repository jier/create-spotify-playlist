import random
from itertools import islice

from ..settings import settings
from .spotifyService import SpotifyService

# Graph type: track_id → {other_track_id → distance}
Graph = dict[str, dict[str, float]]


# ---------------------------------------------------------------------------
# Distance (Jaccard genre similarity + release year proximity)
#
# Spotify deprecated /audio-features in November 2024 — 403 for new apps.
# Distance now uses two remaining signals:
#   1. Genre Jaccard distance  = 1 - (|genres_A ∩ genres_B| / |genres_A ∪ genres_B|)
#   2. Release year distance   = min(|year_A - year_B| / 50, 1.0)  (normalized over 50-year span)
# Weights are tunable via settings.playlist_genre_weight / playlist_year_weight.
# ---------------------------------------------------------------------------


def _jaccard_distance(genres_a: set[str], genres_b: set[str]) -> float:
    union = genres_a | genres_b
    if not union:
        return 1.0  # no genre info on either — treat as maximally distant
    return 1.0 - len(genres_a & genres_b) / len(union)


def _get_distance(a: list, b: list) -> float:
    genre_dist = _jaccard_distance(a[1].get("genres", set()), b[1].get("genres", set()))
    year_dist = min(abs(a[1].get("release_year", 0) - b[1].get("release_year", 0)) / 50.0, 1.0)
    return settings.playlist_genre_weight * genre_dist + settings.playlist_year_weight * year_dist


# ---------------------------------------------------------------------------
# Graph helpers (ported + updated from legacy/graph.py)
# ---------------------------------------------------------------------------


def _make_graph(data: list[list]) -> Graph:
    """Build adjacency graph where edge weight = distance between two tracks."""
    return {
        track[0]: {other[0]: _get_distance(track, other) for other in data if other[0] != track[0]} for track in data
    }


def _evaluate_walk(walk: list, graph: Graph) -> float:
    """Sum of distances between all adjacent track pairs in walk. O(n) dict lookup."""
    dist = 0.0
    for i in range(1, len(walk)):
        dist += graph[walk[i]][walk[i - 1]]
    return dist


def _get_walk(graph: Graph) -> list:
    """Random ordering of all tracks with distance score appended."""
    walk: list = list(graph.keys())
    random.shuffle(walk)
    walk.append(_evaluate_walk(walk, graph))
    return walk


# ---------------------------------------------------------------------------
# Genetics helpers (ported + updated from legacy/genetics.py)
# ---------------------------------------------------------------------------


def _sort_walks(walks: list[list]) -> list[list]:
    return sorted(walks, key=lambda w: w[-1])


def _apply_selection(population: list[list]) -> list[list]:
    selected = []
    for _ in range(len(population) // 2):
        tournament = random.sample(population, 3)
        selected.append(min(tournament, key=lambda w: w[-1]))
    return selected


def _apply_crossover(population: list[list], graph: Graph) -> list[list]:
    offspring = []
    for _ in range(len(population)):
        a = list(random.choice(population)[:-1])
        b = list(random.choice(population)[:-1])
        mid = max(len(a) // 2, 1)
        start = random.randrange(mid)
        child = a[start : start + mid]
        child += [x for x in b if x not in child]
        child.append(_evaluate_walk(child, graph))
        offspring.append(child)
    return offspring


def _mutate(walk: list, graph: Graph) -> list:
    body = walk[:-1]
    rotated = body[1:] + [body[0]]
    rotated.append(_evaluate_walk(rotated, graph))
    return rotated


def _apply_mutation(population: list[list], graph: Graph) -> list[list]:
    return [_mutate(w, graph) if random.random() < 0.5 else w for w in population]


def _apply_genetics(population: list[list], graph: Graph) -> list[list]:
    selected = _apply_selection(population)
    offspring = _apply_crossover(selected, graph)
    return _apply_mutation(selected + offspring, graph)


def _init_population(graph: Graph, size: int) -> list[list]:
    return _sort_walks([_get_walk(graph) for _ in range(size)])


# ---------------------------------------------------------------------------
# PlaylistBuilderService
# ---------------------------------------------------------------------------


class PlaylistBuilderService:
    def __init__(self, spotify: SpotifyService) -> None:
        self._spotify = spotify

    def _fetch_genre_tracks(self, genre: str) -> tuple[list[dict], dict[str, set[str]]]:
        """
        Paginate liked songs, batch-fetch artist genres, filter by genre.
        Returns (matching_tracks, {artist_id: genres_set}) for matched artists.
        Keeps genre data in memory to reuse for distance computation — avoids second API round-trip.
        """
        all_items = list(self._spotify.iter_liked_songs())

        artist_to_tracks: dict[str, list[dict]] = {}
        for item in all_items:
            artists = item["track"].get("artists", [])
            if not artists:
                continue
            artist_to_tracks.setdefault(artists[0]["id"], []).append(item["track"])

        artist_genres: dict[str, set[str]] = {}
        matching_artist_ids: set[str] = set()
        it = iter(list(artist_to_tracks.keys()))
        while chunk := list(islice(it, 50)):
            for artist in self._spotify.get_artists(chunk):
                if not artist:
                    continue
                genres: set[str] = set(artist.get("genres", []))
                artist_genres[artist["id"]] = genres
                if any(genre.lower() in g.lower() for g in genres):
                    matching_artist_ids.add(artist["id"])

        matching_tracks = [
            item["track"]
            for item in all_items
            if item["track"].get("artists") and item["track"]["artists"][0]["id"] in matching_artist_ids
        ]
        matched_genres = {aid: g for aid, g in artist_genres.items() if aid in matching_artist_ids}
        return matching_tracks, matched_genres

    def _build_track_features(self, tracks: list[dict], artist_genres: dict[str, set[str]]) -> list[list]:
        """
        Build [[track_id, {genres, release_year, duration_ms}], ...] for TSP distance computation.
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

    def order_by_release_year(self, track_features: list[list]) -> list[str]:
        """
        Sort tracks chronologically by release year ascending.
        Replaces BPM sort — Spotify deprecated /audio-features (Nov 2024), tempo no longer accessible.
        """
        return [tid for tid, _ in sorted(track_features, key=lambda x: x[1].get("release_year", 0))]

    def order_by_tsp(
        self,
        track_features: list[list],
        population_size: int = 20,
        generations: int = 50,
    ) -> tuple[list[str], float, float]:
        """
        Order tracks via genetic TSP to minimize total distance between adjacent tracks.
        Distance = Jaccard genre distance + normalized release year distance.
        (Replaces audio-feature distance — Spotify deprecated /audio-features Nov 2024.)
        Returns (ordered_track_ids, final_score, initial_score).

        improvement_pct = (1 - final_score / initial_score) * 100
          0%            → algorithm made no progress; either population_size/generations too small,
                          or all tracks share identical genre+year (initial_score=0, guarded separately)
          20–40%        → moderate improvement, tracks fairly similar
          40–60%        → strong improvement, meaningful genre/year variance in pool
          >60%          → large variance, algorithm had lots of room to optimize

        generations: each generation runs one cycle of selection → crossover → mutation.
          More generations = more evolution cycles = closer to the optimal route, diminishing returns.
          Default 50 balances speed vs quality. Increase for larger track pools or higher accuracy.
        """
        graph = _make_graph(track_features)
        population = _init_population(graph, population_size)
        initial_score = float(population[0][-1])
        for _ in range(generations):
            population = _apply_genetics(population, graph)
            population = _sort_walks(population)
        best = population[0]
        return best[:-1], float(best[-1]), initial_score

    def _build_playlist(self, name: str, track_ids: list[str]) -> dict:
        me = self._spotify.get_me()
        playlist = self._spotify.create_playlist(me["id"], name)
        uris = [f"spotify:track:{tid}" for tid in track_ids]
        self._spotify.add_tracks_to_playlist(playlist["id"], uris)
        return playlist

    @staticmethod
    def _track_label(track: dict, features: dict) -> dict:
        artist = track["artists"][0]["name"] if track.get("artists") else "Unknown"
        return {
            "name": track["name"],
            "artist": artist,
            "release_year": features.get("release_year", 0),
            "genres": sorted(features.get("genres", set())),
        }

    def build_genre_playlist_chronological(self, genre: str, dry_run: bool = True) -> dict:
        """
        Find liked songs matching genre → sort by release year ascending.
        Replaces BPM sort — Spotify /audio-features deprecated Nov 2024.
        dry_run=True (default): return stats without creating playlist.
        """
        tracks, artist_genres = self._fetch_genre_tracks(genre)
        track_features = self._build_track_features(tracks, artist_genres)
        ordered_ids = self.order_by_release_year(track_features)

        features_map = {tf[0]: tf[1] for tf in track_features}
        track_map = {t["id"]: t for t in tracks}
        years = [features_map[tid].get("release_year", 0) for tid in ordered_ids]

        result: dict = {
            "dry_run": dry_run,
            "genre": genre,
            "track_count": len(ordered_ids),
            "year_range": {"oldest": min(years) if years else 0, "newest": max(years) if years else 0},
            "tracks": [self._track_label(track_map[tid], features_map[tid]) for tid in ordered_ids],
        }

        if not dry_run:
            playlist = self._build_playlist(f"{genre.title()} – Chronological", ordered_ids)
            result["playlist_id"] = playlist["id"]

        return result

    def build_playlist_from_seed(self, track_id: str, n: int = 20, dry_run: bool = True) -> dict:
        """
        Build a playlist seeded from one track using genre-based Spotify search.
        Spotify deprecated /related-artists and /recommendations (Nov 2024).

        Steps:
          1. Fetch seed track + primary artist genres via /artists
          2. Search Spotify for tracks matching each of the seed's genres (up to 3)
             Deduplicate by (name, primary_artist_id) — Spotify has single + album versions
          3. Batch-fetch artist genres for all candidate tracks
          4. Build genre+year features for seed and all candidates
          5. Rank candidates by Jaccard distance to seed, progressive threshold fallback:
               a. playlist_max_candidate_distance (default 0.6) — strict, genre-accurate
               b. Relax to 0.7 → 0.8 → 1.0 if < 3 candidates pass (niche genre)
               c. Fetch artist's own discography if still < 3 candidates (no genre tags / unknown artist)
          6. Run TSP on top n for smooth internal ordering
          7. Prepend seed track → create playlist or return dry run stats
        """
        # Step 1 — seed track + primary artist genres
        seed_track = self._spotify.get_track(track_id)
        seed_artists = seed_track.get("artists", [])
        if not seed_artists:
            return {"error": "Seed track has no artist data"}
        seed_artist_id = seed_artists[0]["id"]
        seed_artist_name = seed_artists[0].get("name", "")

        artist_genres: dict[str, set[str]] = {}
        seed_genres: set[str] = set()
        seed_artist_obj = self._spotify.get_artists([seed_artist_id])
        if seed_artist_obj:
            seed_genres = set(seed_artist_obj[0].get("genres", []))
            artist_genres[seed_artist_id] = seed_genres

        # Step 2 — search for candidates by genre
        search_genres = list(seed_genres)[:3] or [seed_artist_name]
        candidate_tracks: dict[str, dict] = {}
        seen_signatures: set[tuple[str, str]] = set()
        for genre in search_genres:
            query = f'genre:"{genre}"' if " " in genre else f"genre:{genre}"
            for track in self._spotify.search_tracks(query, limit=50):
                tid = track.get("id")
                if not tid or tid == track_id:
                    continue
                artists = track.get("artists", [])
                sig = (track.get("name", "").lower(), artists[0]["id"] if artists else "")
                if sig in seen_signatures:
                    continue
                seen_signatures.add(sig)
                candidate_tracks[tid] = track

        # Step 3 — batch-fetch artist genres for candidates
        candidate_artist_ids = list({t["artists"][0]["id"] for t in candidate_tracks.values() if t.get("artists")})
        it = iter(candidate_artist_ids)
        while chunk := list(islice(it, 50)):
            for artist in self._spotify.get_artists(chunk):
                if artist:
                    artist_genres[artist["id"]] = set(artist.get("genres", []))

        # Step 4 — build features
        seed_features = self._build_track_features([seed_track], artist_genres)
        if not seed_features:
            return {"error": "Could not build features for seed track"}
        seed_feat = seed_features[0]

        candidate_features = self._build_track_features(list(candidate_tracks.values()), artist_genres)
        all_built_features = seed_features + candidate_features

        # Step 5 — rank + progressive threshold fallback
        fallback = "genre_search"
        threshold_used = settings.playlist_max_candidate_distance
        top_n: list[list] = []

        if candidate_features:
            scored = sorted(
                [(c, _get_distance(seed_feat, c)) for c in candidate_features],
                key=lambda x: x[1],
            )
            for threshold in [settings.playlist_max_candidate_distance, 0.7, 0.8, 1.0]:
                top_n = [c for c, d in scored if d <= threshold][:n]
                if len(top_n) >= 3:
                    threshold_used = threshold
                    if threshold > settings.playlist_max_candidate_distance:
                        fallback = f"relaxed_threshold_{threshold}"
                    break

        # Fallback — artist discography (niche/untagged artist)
        if len(top_n) < 3:
            disc_tracks = self._spotify.get_artist_tracks(seed_artist_id)
            new_disc: list[dict] = []
            for t in disc_tracks:
                tid = t.get("id")
                if tid and tid != track_id and tid not in candidate_tracks:
                    candidate_tracks[tid] = t
                    new_disc.append(t)
            if new_disc:
                disc_features = self._build_track_features(new_disc, artist_genres)
                all_built_features += disc_features
                all_scored = sorted(
                    [(c, _get_distance(seed_feat, c)) for c in candidate_features + disc_features],
                    key=lambda x: x[1],
                )
                top_n = [c for c, _ in all_scored][:n]
                fallback = "artist_discography"
                threshold_used = 1.0

        if not top_n:
            return {
                "error": "No candidates found — artist may be too niche or not indexed by Spotify",
                "seed_genres": sorted(seed_genres),
                "candidates_searched": len(candidate_tracks),
            }

        # Step 6 — TSP
        ordered_ids: list[str]
        tsp_score = 0.0
        initial_score = 0.0
        if len(top_n) >= 3:
            ordered_ids, tsp_score, initial_score = self.order_by_tsp(top_n)
        else:
            ordered_ids = [f[0] for f in top_n]

        # Step 7 — prepend seed
        final_ids = [track_id] + [tid for tid in ordered_ids if tid != track_id]

        all_tracks = {track_id: seed_track, **candidate_tracks}
        features_map = {f[0]: f[1] for f in all_built_features}
        improvement = round((1 - tsp_score / initial_score) * 100, 1) if initial_score else 0.0

        result: dict = {
            "dry_run": dry_run,
            "fallback": fallback,
            "threshold_used": threshold_used,
            "seed": self._track_label(seed_track, seed_feat[1]),
            "seed_genres": sorted(seed_genres),
            "candidates_found": len(candidate_tracks),
            "track_count": len(final_ids),
            "tsp_score": round(tsp_score, 4),
            "initial_score": round(initial_score, 4),
            "improvement_pct": improvement,
            "tracks": [
                {**self._track_label(all_tracks[tid], features_map.get(tid, {})), "seed": tid == track_id}
                for tid in final_ids
                if tid in all_tracks
            ],
        }

        if not dry_run:
            seed_name = seed_track.get("name", track_id)
            playlist = self._build_playlist(f"From: {seed_name}", final_ids)
            result["playlist_id"] = playlist["id"]

        return result

    def build_genre_playlist_tsp(self, genre: str, dry_run: bool = True) -> dict:
        """
        Find liked songs matching genre → TSP order by Jaccard genre + release year distance.
        dry_run=True (default): return stats without creating playlist.
        """
        tracks, artist_genres = self._fetch_genre_tracks(genre)
        track_features = self._build_track_features(tracks, artist_genres)
        ordered_ids, final_score, initial_score = self.order_by_tsp(track_features)

        features_map = {tf[0]: tf[1] for tf in track_features}
        track_map = {t["id"]: t for t in tracks}
        improvement = round((1 - final_score / initial_score) * 100, 1) if initial_score else 0.0

        result: dict = {
            "dry_run": dry_run,
            "genre": genre,
            "track_count": len(ordered_ids),
            "tsp_score": round(final_score, 4),
            "initial_score": round(initial_score, 4),
            "improvement_pct": improvement,
            "distance_signals": ["jaccard_genre", "release_year"],
            "tracks": [self._track_label(track_map[tid], features_map[tid]) for tid in ordered_ids],
        }

        if not dry_run:
            playlist = self._build_playlist(f"{genre.title()} – TSP", ordered_ids)
            result["playlist_id"] = playlist["id"]

        return result
