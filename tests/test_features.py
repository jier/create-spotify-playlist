import pytest

from src.algorithms.features import build_track_features


@pytest.mark.parametrize(
    ("tracks", "artist_genres", "expected"),
    [
        (
            [
                {
                    "id": "track1",
                    "artists": [{"id": "artist1"}],
                    "album": {"release_date": "2015-06-01"},
                    "duration_ms": 210000,
                }
            ],
            {"artist1": {"rock", "indie"}},
            [["track1", {"genres": {"rock", "indie"}, "release_year": 2015, "duration_ms": 210000}]],
        ),
        (
            [{"id": "track1", "artists": [], "album": {"release_date": "2020"}, "duration_ms": 0}],
            {},
            [["track1", {"genres": set(), "release_year": 2020, "duration_ms": 0}]],
        ),
        (
            [{"id": "track1", "artists": [{"id": "artist1"}], "album": {"release_date": "unknown"}}],
            {"artist1": set()},
            [["track1", {"genres": set(), "release_year": 0, "duration_ms": 0}]],
        ),
        (
            [{"id": "track1", "artists": [{"id": "artist1"}]}],
            {"artist1": set()},
            [["track1", {"genres": set(), "release_year": 0, "duration_ms": 0}]],
        ),
    ],
    ids=[
        "extracts_genres_and_release_year",
        "defaults_to_empty_genres_when_no_artists",
        "defaults_release_year_to_zero_on_malformed_date",
        "defaults_release_year_to_zero_when_album_missing",
    ],
)
def test_build_track_features(tracks, artist_genres, expected):
    assert build_track_features(tracks, artist_genres) == expected
