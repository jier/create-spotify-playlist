import uuid
from itertools import islice
from typing import Literal

from src.algorithms.features import build_track_features
from src.algorithms.models import (
    DistanceWeights,
    GreedySelectionConfig,
    SAIterationEvent,
    SimulatedAnnealingConfig,
    ThresholdStepEvent,
    TSPWalkEvent,
)
from src.algorithms.persistence import RunTraceWriter
from src.algorithms.selection import SimulatedAnnealer, select_greedy
from src.algorithms.tsp import TSPOptimizer, order_by_tsp
from src.services.spotifyService import SpotifyService
from src.settings import settings

# ---------------------------------------------------------------------------
# Distance (Jaccard genre similarity + release year proximity)
#
# Spotify deprecated /audio-features in November 2024 — 403 for new apps.
# Distance now uses two remaining signals:
#   1. Genre Jaccard distance  = 1 - (|genres_A ∩ genres_B| / |genres_A ∪ genres_B|)
#   2. Release year distance   = min(|year_A - year_B| / 50, 1.0)  (normalized over 50-year span)
# Weights are tunable via settings.playlist_genre_weight / playlist_year_weight.
# The actual algorithms (distance, feature building, selection, TSP ordering) live in
# ../algorithms/ — pure, no HTTP, no global settings, so they're usable standalone.
# This service is the HTTP-bound orchestration layer around them: fetching from
# Spotify, building the config objects those algorithms need, and (if not a dry
# run) writing the result back to Spotify.
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

    def order_by_release_year(self, track_features: list[list]) -> list[str]:
        """
        Sort tracks chronologically by release year ascending.
        Replaces BPM sort — Spotify deprecated /audio-features (Nov 2024), tempo no longer accessible.
        """
        return [tid for tid, _ in sorted(track_features, key=lambda x: x[1].get("release_year", 0))]

    def _distance_weights(self) -> DistanceWeights:
        return DistanceWeights(
            genre_weight=settings.playlist_genre_weight,
            year_weight=settings.playlist_year_weight,
        )

    def _greedy_config(self, weights: DistanceWeights) -> GreedySelectionConfig:
        return GreedySelectionConfig(
            max_candidate_distance=settings.playlist_max_candidate_distance,
            max_tracks_per_artist=settings.playlist_max_tracks_per_artist,
            weights=weights,
        )

    def _sa_config(self, weights: DistanceWeights) -> SimulatedAnnealingConfig:
        return SimulatedAnnealingConfig(
            max_candidate_distance=settings.playlist_max_candidate_distance,
            diversity_weight=settings.sa_diversity_weight,
            temperature_start=settings.sa_temperature_start,
            temperature_end=settings.sa_temperature_end,
            iterations=settings.sa_iterations,
            weights=weights,
        )

    def _run_selection_strategy(
        self,
        strategy: Literal["greedy", "sa"],
        candidate_features: list[list],
        seed_feat: list,
        candidate_tracks: dict[str, dict],
        n: int,
        weights: DistanceWeights,
    ) -> tuple[list[list], str, float, list[SAIterationEvent], list[ThresholdStepEvent]]:
        """
        Dispatch to the configured strategy. Builds each strategy's config from
        settings here, at the orchestration boundary, so the algorithms
        themselves never read settings directly.

        Returns (top_n, fallback, threshold_used, sa_trace, threshold_trace).
        sa_trace is empty for the greedy strategy, and for the
        "sa_all_candidates" SA shortcut (pool already <= n, nothing to anneal).
        """
        if strategy == "sa":
            annealer = SimulatedAnnealer(self._sa_config(weights), candidate_features, seed_feat, n)
            return annealer.run_to_completion()

        top_n, fallback, threshold_used, threshold_trace = select_greedy(
            candidate_features, seed_feat, candidate_tracks, n, self._greedy_config(weights)
        )
        return top_n, fallback, threshold_used, [], threshold_trace

    def _fetch_seed_and_genres(self, track_id: str) -> tuple[dict, str, str, set[str], dict[str, set[str]]] | None:
        """
        Step 1: fetch the seed track and its primary artist's genres.
        Returns None if the seed track has no artist data (no seed to build from).
        Otherwise (seed_track, seed_artist_id, seed_artist_name, seed_genres, artist_genres).
        """
        seed_track = self._spotify.get_track(track_id)
        seed_artists = seed_track.get("artists", [])
        if not seed_artists:
            return None
        seed_artist_id = seed_artists[0]["id"]
        seed_artist_name = seed_artists[0].get("name", "")

        artist_genres: dict[str, set[str]] = {}
        seed_genres: set[str] = set()
        seed_artist_obj = self._spotify.get_artists([seed_artist_id])
        if seed_artist_obj:
            seed_genres = set(seed_artist_obj[0].get("genres", []))
            artist_genres[seed_artist_id] = seed_genres

        return seed_track, seed_artist_id, seed_artist_name, seed_genres, artist_genres

    def _search_candidates(
        self,
        seed_genres: set[str],
        seed_artist_name: str,
        exclude_track_id: str,
    ) -> dict[str, dict]:
        """
        Step 2: search Spotify for tracks matching up to 3 of the seed's genres.
        Deduplicates by (name, primary_artist_id) — Spotify has single + album versions.
        Caps candidates per artist at settings.playlist_max_tracks_per_artist.
        """
        search_genres = list(seed_genres)[:3] or [seed_artist_name]
        candidate_tracks: dict[str, dict] = {}
        seen_signatures: set[tuple[str, str]] = set()
        artist_track_counts: dict[str, int] = {}
        for genre in search_genres:
            query = f'genre:"{genre}"' if " " in genre else f"genre:{genre}"
            for track in self._spotify.search_tracks(query, limit=50):
                tid = track.get("id")
                if not tid or tid == exclude_track_id:
                    continue
                artists = track.get("artists", [])
                primary_artist_id = artists[0]["id"] if artists else ""
                sig = (track.get("name", "").lower(), primary_artist_id)
                if sig in seen_signatures:
                    continue
                if artist_track_counts.get(primary_artist_id, 0) >= settings.playlist_max_tracks_per_artist:
                    continue
                seen_signatures.add(sig)
                artist_track_counts[primary_artist_id] = artist_track_counts.get(primary_artist_id, 0) + 1
                candidate_tracks[tid] = track
        return candidate_tracks

    def _fetch_candidate_artist_genres(
        self,
        candidate_tracks: dict[str, dict],
        artist_genres: dict[str, set[str]],
    ) -> None:
        """Step 3: batch-fetch genres for every candidate's primary artist. Mutates artist_genres in place."""
        candidate_artist_ids = list({t["artists"][0]["id"] for t in candidate_tracks.values() if t.get("artists")})
        it = iter(candidate_artist_ids)
        while chunk := list(islice(it, 50)):
            for artist in self._spotify.get_artists(chunk):
                if artist:
                    artist_genres[artist["id"]] = set(artist.get("genres", []))

    def _apply_discography_fallback(
        self,
        seed_artist_id: str,
        exclude_track_id: str,
        candidate_tracks: dict[str, dict],
        artist_genres: dict[str, set[str]],
    ) -> list[list]:
        """
        When the selected strategy returns fewer than n tracks (niche or
        untagged artist), pull the seed artist's own discography as
        additional candidates. Mutates candidate_tracks in place with any
        newly found tracks. Returns their built features, or an empty list
        if the discography added nothing new.
        """
        disc_tracks = self._spotify.get_artist_tracks(seed_artist_id)
        new_disc: list[dict] = []
        for t in disc_tracks:
            tid = t.get("id")
            if tid and tid != exclude_track_id and tid not in candidate_tracks:
                candidate_tracks[tid] = t
                new_disc.append(t)
        if not new_disc:
            return []
        return build_track_features(new_disc, artist_genres)

    @staticmethod
    def _assemble_seed_playlist_result(
        *,
        dry_run: bool,
        strategy: str,
        fallback: str,
        threshold_used: float,
        seed_track: dict,
        seed_feat: list,
        seed_genres: set[str],
        candidate_tracks: dict[str, dict],
        final_ids: list[str],
        tsp_score: float,
        initial_score: float,
        all_built_features: list[list],
        track_id: str,
    ) -> dict:
        """Step 7 (response shape): assemble the dry-run/result dict from everything already computed."""
        all_tracks = {track_id: seed_track, **candidate_tracks}
        features_map = {f[0]: f[1] for f in all_built_features}
        improvement = round((1 - tsp_score / initial_score) * 100, 1) if initial_score else 0.0

        return {
            "dry_run": dry_run,
            "selection_strategy": strategy,
            "fallback": fallback,
            "threshold_used": threshold_used,
            "artist_cap": settings.playlist_max_tracks_per_artist,
            "seed": PlaylistBuilderService._track_label(seed_track, seed_feat[1]),
            "seed_genres": sorted(seed_genres),
            "candidates_found": len(candidate_tracks),
            "track_count": len(final_ids),
            "tsp_score": round(tsp_score, 4),
            "initial_score": round(initial_score, 4),
            "improvement_pct": improvement,
            "tracks": [
                {
                    **PlaylistBuilderService._track_label(all_tracks[tid], features_map.get(tid, {})),
                    "seed": tid == track_id,
                }
                for tid in final_ids
                if tid in all_tracks
            ],
        }

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
        track_features = build_track_features(tracks, artist_genres)
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

    def build_playlist_from_seed(
        self,
        track_id: str,
        n: int = 20,
        dry_run: bool = True,
        strategy: Literal["greedy", "sa"] = "greedy",
        run_id: str | None = None,
    ) -> dict:
        """
        Build a playlist seeded from one track using genre-based Spotify search.
        Spotify deprecated /related-artists and /recommendations (Nov 2024).

        Steps:
          1. Fetch seed track + primary artist genres via /artists
          2. Search Spotify for tracks matching each of the seed's genres (up to 3)
             Deduplicate by (name, primary_artist_id) — Spotify has single + album versions
             Artist cap: max playlist_max_tracks_per_artist tracks per artist in candidate pool
          3. Batch-fetch artist genres for all candidate tracks
          4. Build genre+year features for seed and all candidates (../algorithms/features.py)
          5. Select top n via pluggable strategy (../algorithms/selection.py):
               greedy — artist-capped walk in distance order, progressive Jaccard threshold relaxation
               sa     — simulated annealing: minimises avg_relevance − β × avg_pairwise_diversity,
                        returns a full per-iteration trace
             Discography fallback if strategy returns < n (niche/untagged artist)
          6. Run TSP on top n for smooth internal ordering (../algorithms/tsp.py)
          7. Prepend seed track → create playlist or return dry run stats

        Every call writes a JSONL trace to runs/{run_id}.jsonl (see
        ../algorithms/persistence.py for exactly what stages are captured —
        sa_iteration lines only exist when strategy="sa", threshold_step and
        tsp_generation are not implemented yet).
        """
        run_id = run_id or uuid.uuid4().hex
        writer = RunTraceWriter(run_id)
        # Step 1 — seed track + primary artist genres
        fetched = self._fetch_seed_and_genres(track_id)
        if fetched is None:
            return {"error": "Seed track has no artist data"}
        seed_track, seed_artist_id, seed_artist_name, seed_genres, artist_genres = fetched

        # Step 2 — search for candidates by genre
        candidate_tracks = self._search_candidates(seed_genres, seed_artist_name, track_id)

        # Step 3 — batch-fetch artist genres for candidates
        self._fetch_candidate_artist_genres(candidate_tracks, artist_genres)

        # Step 4 — build features
        seed_features = build_track_features([seed_track], artist_genres)
        if not seed_features:
            return {"error": "Could not build features for seed track"}
        seed_feat = seed_features[0]
        writer.write_seed(track_id, sorted(seed_feat[1]["genres"]), seed_feat[1]["release_year"])

        candidate_features = build_track_features(list(candidate_tracks.values()), artist_genres)
        all_built_features = seed_features + candidate_features

        # Step 5 — pluggable selection strategy (see ../algorithms/selection.py)
        weights = self._distance_weights()
        top_n: list[list] = []
        fallback = "genre_search"
        threshold_used = settings.playlist_max_candidate_distance
        sa_trace: list[SAIterationEvent] = []

        if candidate_features:
            top_n, fallback, threshold_used, sa_trace, threshold_trace = self._run_selection_strategy(
                strategy, candidate_features, seed_feat, candidate_tracks, n, weights
            )
            for step in threshold_trace:
                writer.write_threshold_step(step)
            for event in sa_trace:
                writer.write_sa_iteration(event)

        # Discography fallback — strategy-agnostic, triggers when pool is too small
        if len(top_n) < n:
            disc_features = self._apply_discography_fallback(seed_artist_id, track_id, candidate_tracks, artist_genres)
            if disc_features:
                all_built_features += disc_features
                top_n, _, _, sa_trace, threshold_trace = self._run_selection_strategy(
                    strategy, candidate_features + disc_features, seed_feat, candidate_tracks, n, weights
                )
                for step in threshold_trace:
                    writer.write_threshold_step(step)
                for event in sa_trace:
                    writer.write_sa_iteration(event)
                fallback = "artist_discography"
                threshold_used = 1.0

        # candidate_tracks may have grown via the discography fallback (mutated in
        # place) — write it after both attempts so the trace reflects the full pool.
        writer.write_candidates(candidate_tracks, all_built_features[len(seed_features) :])

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
            ordered_ids, tsp_score, initial_score, tsp_trace = TSPOptimizer(top_n, weights).run_to_completion()
            for event in tsp_trace:
                if isinstance(event, TSPWalkEvent):
                    writer.write_tsp_walk(event)
                else:
                    writer.write_tsp_generation(event)
        else:
            ordered_ids = [f[0] for f in top_n]

        # Step 7 — prepend seed, assemble the response
        final_ids = [track_id] + [tid for tid in ordered_ids if tid != track_id]
        writer.write_final(final_ids, tsp_score, initial_score)

        result = self._assemble_seed_playlist_result(
            dry_run=dry_run,
            strategy=strategy,
            fallback=fallback,
            threshold_used=threshold_used,
            seed_track=seed_track,
            seed_feat=seed_feat,
            seed_genres=seed_genres,
            candidate_tracks=candidate_tracks,
            final_ids=final_ids,
            tsp_score=tsp_score,
            initial_score=initial_score,
            all_built_features=all_built_features,
            track_id=track_id,
        )
        result["run_id"] = run_id
        result["trace_path"] = str(writer.path)

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
        track_features = build_track_features(tracks, artist_genres)
        weights = self._distance_weights()
        ordered_ids, final_score, initial_score = order_by_tsp(track_features, weights)

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
