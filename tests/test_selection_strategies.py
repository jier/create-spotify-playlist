from src.services import selectionStrategies as strategies


def test_jaccard_distance_identical_genre_sets_is_zero():
    assert strategies.jaccard_distance({"rock"}, {"rock"}) == 0.0


def test_jaccard_distance_disjoint_genre_sets_is_one():
    assert strategies.jaccard_distance({"rock"}, {"pop"}) == 1.0


def test_jaccard_distance_partial_overlap():
    result = strategies.jaccard_distance({"rock", "pop"}, {"pop", "jazz"})
    assert result == 1.0 - 1 / 3


def test_jaccard_distance_both_empty_is_one():
    assert strategies.jaccard_distance(set(), set()) == 1.0


def test_get_distance_combines_genre_and_year_with_configured_weights(monkeypatch):
    monkeypatch.setattr(strategies.settings, "playlist_genre_weight", 1.0)
    monkeypatch.setattr(strategies.settings, "playlist_year_weight", 0.5)

    track_a = ["a", {"genres": {"rock"}, "release_year": 2000}]
    track_b = ["b", {"genres": {"pop"}, "release_year": 2010}]

    result = strategies.get_distance(track_a, track_b)

    assert result == 1.0 * 1.0 + 0.5 * 0.2


def test_get_distance_caps_year_distance_at_one(monkeypatch):
    monkeypatch.setattr(strategies.settings, "playlist_genre_weight", 0.0)
    monkeypatch.setattr(strategies.settings, "playlist_year_weight", 1.0)

    track_a = ["a", {"genres": {"rock"}, "release_year": 1970}]
    track_b = ["b", {"genres": {"rock"}, "release_year": 2020}]

    result = strategies.get_distance(track_a, track_b)

    assert result == 1.0


def _greedy_settings(monkeypatch, max_candidate_distance: float = 0.75, max_tracks_per_artist: int = 3) -> None:
    monkeypatch.setattr(strategies.settings, "playlist_max_candidate_distance", max_candidate_distance)
    monkeypatch.setattr(strategies.settings, "playlist_max_tracks_per_artist", max_tracks_per_artist)
    monkeypatch.setattr(strategies.settings, "playlist_genre_weight", 1.0)
    monkeypatch.setattr(strategies.settings, "playlist_year_weight", 0.5)


def test_select_greedy_enforces_per_artist_cap(monkeypatch):
    _greedy_settings(monkeypatch, max_tracks_per_artist=2)

    seed_feat = ["seed", {"genres": {"rock"}, "release_year": 2000}]
    candidate_features = [[f"artist_a_track_{i}", {"genres": {"rock"}, "release_year": 2000 + i}] for i in range(4)] + [
        ["artist_b_track_0", {"genres": {"rock"}, "release_year": 2000}]
    ]
    candidate_tracks = {
        **{f"artist_a_track_{i}": {"artists": [{"id": "artist_a"}]} for i in range(4)},
        "artist_b_track_0": {"artists": [{"id": "artist_b"}]},
    }

    top_n, fallback, threshold_used = strategies.select_greedy(candidate_features, seed_feat, candidate_tracks, n=3)

    assert len(top_n) == 3
    artist_a_count = sum(1 for tid, _ in top_n if tid.startswith("artist_a"))
    assert artist_a_count <= 2
    assert fallback == "genre_search"
    assert threshold_used == 0.75


def test_select_greedy_relaxes_threshold_when_seed_genre_has_no_close_match(monkeypatch):
    _greedy_settings(monkeypatch)

    seed_feat = ["seed", {"genres": {"metal"}, "release_year": 2000}]
    candidate_features = [["off_genre_track", {"genres": {"jazz"}, "release_year": 2000}]]
    candidate_tracks = {"off_genre_track": {"artists": [{"id": "artist_x"}]}}

    top_n, fallback, threshold_used = strategies.select_greedy(candidate_features, seed_feat, candidate_tracks, n=1)

    assert len(top_n) == 1
    assert threshold_used == 1.0
    assert fallback == "relaxed_threshold_1.0"


def _sa_settings(monkeypatch, iterations: int = 30) -> None:
    monkeypatch.setattr(strategies.settings, "playlist_max_candidate_distance", 0.75)
    monkeypatch.setattr(strategies.settings, "playlist_genre_weight", 1.0)
    monkeypatch.setattr(strategies.settings, "playlist_year_weight", 0.5)
    monkeypatch.setattr(strategies.settings, "sa_diversity_weight", 0.5)
    monkeypatch.setattr(strategies.settings, "sa_temperature_start", 1.0)
    monkeypatch.setattr(strategies.settings, "sa_temperature_end", 0.01)
    monkeypatch.setattr(strategies.settings, "sa_iterations", iterations)


def test_select_sa_returns_all_candidates_when_pool_at_or_below_n(monkeypatch):
    _sa_settings(monkeypatch)

    seed_feat = ["seed", {"genres": {"rock"}, "release_year": 2000}]
    candidate_features = [[f"track_{i}", {"genres": {"rock"}, "release_year": 2000 + i}] for i in range(3)]
    candidate_tracks = {f"track_{i}": {"artists": [{"id": f"artist_{i}"}]} for i in range(3)}

    top_n, fallback, _ = strategies.select_sa(candidate_features, seed_feat, candidate_tracks, n=5)

    assert len(top_n) == 3
    assert fallback == "sa_all_candidates"


def test_select_sa_returns_exactly_n_distinct_tracks_when_pool_larger_than_n(monkeypatch):
    _sa_settings(monkeypatch)

    seed_feat = ["seed", {"genres": {"rock"}, "release_year": 2000}]
    candidate_features = [[f"track_{i}", {"genres": {"rock"}, "release_year": 2000 + i}] for i in range(10)]
    candidate_tracks = {f"track_{i}": {"artists": [{"id": f"artist_{i}"}]} for i in range(10)}

    top_n, _, _ = strategies.select_sa(candidate_features, seed_feat, candidate_tracks, n=4)

    ids = [tid for tid, _ in top_n]
    assert len(ids) == 4
    assert len(set(ids)) == 4
    assert set(ids).issubset({f"track_{i}" for i in range(10)})
