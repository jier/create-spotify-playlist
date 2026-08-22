import pytest

from src.services import selectionStrategies as strategies


@pytest.mark.parametrize(
    ("genres_a", "genres_b", "expected"),
    [
        ({"rock"}, {"rock"}, 0.0),
        ({"rock"}, {"pop"}, 1.0),
        ({"rock", "pop"}, {"pop", "jazz"}, 1.0 - 1 / 3),
        (set(), set(), 1.0),
    ],
    ids=["identical", "disjoint", "partial_overlap", "both_empty"],
)
def test_jaccard_distance(genres_a, genres_b, expected):
    assert strategies.jaccard_distance(genres_a, genres_b) == expected


@pytest.fixture
def distance_weights(monkeypatch):
    """Factory: set playlist_genre_weight/playlist_year_weight for one test."""

    def _set(*, genre_weight: float, year_weight: float) -> None:
        monkeypatch.setattr(strategies.settings, "playlist_genre_weight", genre_weight)
        monkeypatch.setattr(strategies.settings, "playlist_year_weight", year_weight)

    return _set


@pytest.mark.parametrize(
    ("genre_weight", "year_weight", "genres_a", "genres_b", "year_a", "year_b", "expected"),
    [
        (1.0, 0.5, {"rock"}, {"pop"}, 2000, 2010, 1.0 * 1.0 + 0.5 * 0.2),
        (0.0, 1.0, {"rock"}, {"rock"}, 1970, 2020, 1.0),
    ],
    ids=["combines_genre_and_year_with_weights", "caps_year_distance_at_one"],
)
def test_get_distance(distance_weights, genre_weight, year_weight, genres_a, genres_b, year_a, year_b, expected):
    distance_weights(genre_weight=genre_weight, year_weight=year_weight)
    track_a = ["a", {"genres": genres_a, "release_year": year_a}]
    track_b = ["b", {"genres": genres_b, "release_year": year_b}]

    assert strategies.get_distance(track_a, track_b) == expected


@pytest.fixture
def greedy_settings(monkeypatch):
    """Factory: configure greedy selection settings for one test."""

    def _set(*, max_candidate_distance: float = 0.75, max_tracks_per_artist: int = 3) -> None:
        monkeypatch.setattr(strategies.settings, "playlist_max_candidate_distance", max_candidate_distance)
        monkeypatch.setattr(strategies.settings, "playlist_max_tracks_per_artist", max_tracks_per_artist)
        monkeypatch.setattr(strategies.settings, "playlist_genre_weight", 1.0)
        monkeypatch.setattr(strategies.settings, "playlist_year_weight", 0.5)

    return _set


def test_select_greedy_enforces_per_artist_cap(greedy_settings):
    greedy_settings(max_tracks_per_artist=2)

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


def test_select_greedy_relaxes_threshold_when_seed_genre_has_no_close_match(greedy_settings):
    greedy_settings()

    seed_feat = ["seed", {"genres": {"metal"}, "release_year": 2000}]
    candidate_features = [["off_genre_track", {"genres": {"jazz"}, "release_year": 2000}]]
    candidate_tracks = {"off_genre_track": {"artists": [{"id": "artist_x"}]}}

    top_n, fallback, threshold_used = strategies.select_greedy(candidate_features, seed_feat, candidate_tracks, n=1)

    assert len(top_n) == 1
    assert threshold_used == 1.0
    assert fallback == "relaxed_threshold_1.0"


@pytest.fixture
def sa_settings(monkeypatch):
    """Factory: configure simulated annealing settings for one test, few iterations for test speed."""

    def _set(*, iterations: int = 30) -> None:
        monkeypatch.setattr(strategies.settings, "playlist_max_candidate_distance", 0.75)
        monkeypatch.setattr(strategies.settings, "playlist_genre_weight", 1.0)
        monkeypatch.setattr(strategies.settings, "playlist_year_weight", 0.5)
        monkeypatch.setattr(strategies.settings, "sa_diversity_weight", 0.5)
        monkeypatch.setattr(strategies.settings, "sa_temperature_start", 1.0)
        monkeypatch.setattr(strategies.settings, "sa_temperature_end", 0.01)
        monkeypatch.setattr(strategies.settings, "sa_iterations", iterations)

    return _set


def test_select_sa_returns_all_candidates_when_pool_at_or_below_n(sa_settings):
    sa_settings()

    seed_feat = ["seed", {"genres": {"rock"}, "release_year": 2000}]
    candidate_features = [[f"track_{i}", {"genres": {"rock"}, "release_year": 2000 + i}] for i in range(3)]
    candidate_tracks = {f"track_{i}": {"artists": [{"id": f"artist_{i}"}]} for i in range(3)}

    top_n, fallback, _ = strategies.select_sa(candidate_features, seed_feat, candidate_tracks, n=5)

    assert len(top_n) == 3
    assert fallback == "sa_all_candidates"


def test_select_sa_returns_exactly_n_distinct_tracks_when_pool_larger_than_n(sa_settings):
    sa_settings()

    seed_feat = ["seed", {"genres": {"rock"}, "release_year": 2000}]
    candidate_features = [[f"track_{i}", {"genres": {"rock"}, "release_year": 2000 + i}] for i in range(10)]
    candidate_tracks = {f"track_{i}": {"artists": [{"id": f"artist_{i}"}]} for i in range(10)}

    top_n, _, _ = strategies.select_sa(candidate_features, seed_feat, candidate_tracks, n=4)

    ids = [tid for tid, _ in top_n]
    assert len(ids) == 4
    assert len(set(ids)) == 4
    assert set(ids).issubset({f"track_{i}" for i in range(10)})
