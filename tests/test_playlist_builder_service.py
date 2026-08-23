from src.algorithms.models import DistanceWeights
from src.services.playlistBuilderService import PlaylistBuilderService

# ---------------------------------------------------------------------------
# _track_label
# ---------------------------------------------------------------------------


def test_track_label_extracts_name_artist_year_and_genres():
    track = {"name": "Song Title", "artists": [{"name": "The Artist"}]}
    features = {"genres": {"rock", "indie"}, "release_year": 2018}

    label = PlaylistBuilderService._track_label(track, features)

    assert label == {
        "name": "Song Title",
        "artist": "The Artist",
        "release_year": 2018,
        "genres": ["indie", "rock"],
    }


def test_track_label_defaults_artist_to_unknown_when_missing():
    track = {"name": "Song Title", "artists": []}

    label = PlaylistBuilderService._track_label(track, {})

    assert label["artist"] == "Unknown"
    assert label["release_year"] == 0
    assert label["genres"] == []


# ---------------------------------------------------------------------------
# _fetch_seed_and_genres (Step 1)
# ---------------------------------------------------------------------------


def test_fetch_seed_and_genres_returns_none_when_seed_has_no_artists(fake_playlist_spotify):
    service = PlaylistBuilderService(fake_playlist_spotify)
    fake_playlist_spotify.tracks["seed_track"] = {"id": "seed_track", "artists": []}

    assert service._fetch_seed_and_genres("seed_track") is None


def test_fetch_seed_and_genres_returns_seed_data_and_genres(fake_playlist_spotify):
    service = PlaylistBuilderService(fake_playlist_spotify)
    fake_playlist_spotify.tracks["seed_track"] = {
        "id": "seed_track",
        "artists": [{"id": "artist_1", "name": "Artist One"}],
    }
    fake_playlist_spotify.artists["artist_1"] = {"id": "artist_1", "genres": ["rock", "indie"]}

    result = service._fetch_seed_and_genres("seed_track")

    assert result is not None
    seed_track, seed_artist_id, seed_artist_name, seed_genres, artist_genres = result
    assert seed_track["id"] == "seed_track"
    assert seed_artist_id == "artist_1"
    assert seed_artist_name == "Artist One"
    assert seed_genres == {"rock", "indie"}
    assert artist_genres == {"artist_1": {"rock", "indie"}}


def test_fetch_seed_and_genres_handles_artist_with_no_genre_data(fake_playlist_spotify):
    service = PlaylistBuilderService(fake_playlist_spotify)
    fake_playlist_spotify.tracks["seed_track"] = {
        "id": "seed_track",
        "artists": [{"id": "artist_1", "name": "Artist One"}],
    }
    # artist_1 intentionally not registered -> get_artists([...]) returns []

    result = service._fetch_seed_and_genres("seed_track")

    assert result is not None
    _, seed_artist_id, _, seed_genres, artist_genres = result
    assert seed_artist_id == "artist_1"
    assert seed_genres == set()
    assert artist_genres == {}


# ---------------------------------------------------------------------------
# _search_candidates (Step 2)
# ---------------------------------------------------------------------------


def test_search_candidates_searches_each_seed_genre(fake_playlist_spotify):
    service = PlaylistBuilderService(fake_playlist_spotify)
    fake_playlist_spotify.search_results["genre:rock"] = [
        {"id": "t1", "name": "Song A", "artists": [{"id": "artist_1"}]},
    ]
    fake_playlist_spotify.search_results["genre:pop"] = [
        {"id": "t2", "name": "Song B", "artists": [{"id": "artist_2"}]},
    ]

    result = service._search_candidates({"rock", "pop"}, "Seed Artist", exclude_track_id="seed_track")

    assert set(result) == {"t1", "t2"}


def test_search_candidates_falls_back_to_artist_name_when_no_genres(fake_playlist_spotify):
    service = PlaylistBuilderService(fake_playlist_spotify)
    fake_playlist_spotify.search_results['genre:"Seed Artist"'] = [
        {"id": "t1", "name": "Song A", "artists": [{"id": "artist_1"}]},
    ]

    result = service._search_candidates(set(), "Seed Artist", exclude_track_id="seed_track")

    assert "t1" in result


def test_search_candidates_excludes_the_seed_track_itself(fake_playlist_spotify):
    service = PlaylistBuilderService(fake_playlist_spotify)
    fake_playlist_spotify.search_results["genre:rock"] = [
        {"id": "seed_track", "name": "Seed Song", "artists": [{"id": "artist_1"}]},
        {"id": "t1", "name": "Other Song", "artists": [{"id": "artist_1"}]},
    ]

    result = service._search_candidates({"rock"}, "Seed Artist", exclude_track_id="seed_track")

    assert "seed_track" not in result
    assert "t1" in result


def test_search_candidates_deduplicates_by_name_and_artist(fake_playlist_spotify):
    service = PlaylistBuilderService(fake_playlist_spotify)
    fake_playlist_spotify.search_results["genre:rock"] = [
        {"id": "t1", "name": "Same Song", "artists": [{"id": "artist_1"}]},
        {"id": "t2", "name": "same song", "artists": [{"id": "artist_1"}]},
    ]

    result = service._search_candidates({"rock"}, "Seed Artist", exclude_track_id="seed_track")

    assert len(result) == 1


def test_search_candidates_respects_per_artist_cap(fake_playlist_spotify, monkeypatch):
    monkeypatch.setattr("src.services.playlistBuilderService.settings.playlist_max_tracks_per_artist", 2)
    service = PlaylistBuilderService(fake_playlist_spotify)
    fake_playlist_spotify.search_results["genre:rock"] = [
        {"id": f"t{i}", "name": f"Song {i}", "artists": [{"id": "artist_1"}]} for i in range(5)
    ]

    result = service._search_candidates({"rock"}, "Seed Artist", exclude_track_id="seed_track")

    assert len(result) == 2


# ---------------------------------------------------------------------------
# _fetch_candidate_artist_genres (Step 3)
# ---------------------------------------------------------------------------


def test_fetch_candidate_artist_genres_populates_artist_genres_in_place(fake_playlist_spotify):
    service = PlaylistBuilderService(fake_playlist_spotify)
    fake_playlist_spotify.artists["artist_1"] = {"id": "artist_1", "genres": ["rock"]}
    fake_playlist_spotify.artists["artist_2"] = {"id": "artist_2", "genres": ["pop", "dance"]}
    candidate_tracks = {
        "t1": {"artists": [{"id": "artist_1"}]},
        "t2": {"artists": [{"id": "artist_2"}]},
    }
    artist_genres: dict[str, set[str]] = {}

    service._fetch_candidate_artist_genres(candidate_tracks, artist_genres)

    assert artist_genres == {"artist_1": {"rock"}, "artist_2": {"pop", "dance"}}


def test_fetch_candidate_artist_genres_skips_tracks_without_artists(fake_playlist_spotify):
    service = PlaylistBuilderService(fake_playlist_spotify)
    candidate_tracks = {"t1": {"artists": []}}
    artist_genres: dict[str, set[str]] = {}

    service._fetch_candidate_artist_genres(candidate_tracks, artist_genres)

    assert artist_genres == {}


# ---------------------------------------------------------------------------
# _apply_discography_fallback
# ---------------------------------------------------------------------------


def test_apply_discography_fallback_adds_new_tracks_and_returns_their_features(fake_playlist_spotify):
    service = PlaylistBuilderService(fake_playlist_spotify)
    fake_playlist_spotify.artist_tracks["artist_1"] = [
        {"id": "disc_track_1", "artists": [{"id": "artist_1"}], "album": {"release_date": "2005"}}
    ]
    candidate_tracks: dict[str, dict] = {}
    artist_genres = {"artist_1": {"rock"}}

    features = service._apply_discography_fallback("artist_1", "seed_track", candidate_tracks, artist_genres)

    assert "disc_track_1" in candidate_tracks
    assert features == [["disc_track_1", {"genres": {"rock"}, "release_year": 2005, "duration_ms": 0}]]


def test_apply_discography_fallback_excludes_seed_and_existing_candidates(fake_playlist_spotify):
    service = PlaylistBuilderService(fake_playlist_spotify)
    fake_playlist_spotify.artist_tracks["artist_1"] = [
        {"id": "seed_track", "artists": [{"id": "artist_1"}]},
        {"id": "already_there", "artists": [{"id": "artist_1"}]},
        {"id": "new_track", "artists": [{"id": "artist_1"}], "album": {"release_date": "2010"}},
    ]
    candidate_tracks = {"already_there": {"artists": [{"id": "artist_1"}]}}
    artist_genres = {"artist_1": set()}

    features = service._apply_discography_fallback("artist_1", "seed_track", candidate_tracks, artist_genres)

    assert set(candidate_tracks) == {"already_there", "new_track"}
    assert [f[0] for f in features] == ["new_track"]


def test_apply_discography_fallback_returns_empty_when_nothing_new(fake_playlist_spotify):
    service = PlaylistBuilderService(fake_playlist_spotify)
    fake_playlist_spotify.artist_tracks["artist_1"] = []
    candidate_tracks: dict[str, dict] = {}

    features = service._apply_discography_fallback("artist_1", "seed_track", candidate_tracks, {})

    assert features == []


# ---------------------------------------------------------------------------
# _assemble_seed_playlist_result (Step 7 shape)
# ---------------------------------------------------------------------------


def test_assemble_seed_playlist_result_builds_expected_shape():
    seed_track = {"name": "Seed Song", "artists": [{"name": "Seed Artist"}]}
    seed_feat = ["seed_track", {"genres": {"rock"}, "release_year": 2000}]
    candidate_tracks = {"t1": {"name": "Other Song", "artists": [{"name": "Other Artist"}]}}
    all_built_features = [seed_feat, ["t1", {"genres": {"pop"}, "release_year": 2010}]]

    result = PlaylistBuilderService._assemble_seed_playlist_result(
        dry_run=True,
        strategy="greedy",
        fallback="genre_search",
        threshold_used=0.75,
        seed_track=seed_track,
        seed_feat=seed_feat,
        seed_genres={"rock"},
        candidate_tracks=candidate_tracks,
        final_ids=["seed_track", "t1"],
        tsp_score=1.5,
        initial_score=3.0,
        all_built_features=all_built_features,
        track_id="seed_track",
    )

    assert result["dry_run"] is True
    assert result["selection_strategy"] == "greedy"
    assert result["fallback"] == "genre_search"
    assert result["threshold_used"] == 0.75
    assert result["seed_genres"] == ["rock"]
    assert result["candidates_found"] == 1
    assert result["track_count"] == 2
    assert result["tsp_score"] == 1.5
    assert result["initial_score"] == 3.0
    assert result["improvement_pct"] == 50.0
    assert result["tracks"] == [
        {"name": "Seed Song", "artist": "Seed Artist", "release_year": 2000, "genres": ["rock"], "seed": True},
        {"name": "Other Song", "artist": "Other Artist", "release_year": 2010, "genres": ["pop"], "seed": False},
    ]


def test_assemble_seed_playlist_result_improvement_is_zero_when_initial_score_is_zero():
    seed_track = {"name": "Seed", "artists": []}
    seed_feat = ["seed_track", {"genres": set(), "release_year": 0}]

    result = PlaylistBuilderService._assemble_seed_playlist_result(
        dry_run=True,
        strategy="greedy",
        fallback="genre_search",
        threshold_used=0.75,
        seed_track=seed_track,
        seed_feat=seed_feat,
        seed_genres=set(),
        candidate_tracks={},
        final_ids=["seed_track"],
        tsp_score=0.0,
        initial_score=0.0,
        all_built_features=[seed_feat],
        track_id="seed_track",
    )

    assert result["improvement_pct"] == 0.0


# ---------------------------------------------------------------------------
# _distance_weights / _greedy_config / _sa_config
# ---------------------------------------------------------------------------


def test_distance_weights_reads_from_settings(fake_playlist_spotify, monkeypatch):
    monkeypatch.setattr("src.services.playlistBuilderService.settings.playlist_genre_weight", 2.0)
    monkeypatch.setattr("src.services.playlistBuilderService.settings.playlist_year_weight", 0.25)
    service = PlaylistBuilderService(fake_playlist_spotify)

    weights = service._distance_weights()

    assert weights.genre_weight == 2.0
    assert weights.year_weight == 0.25


def test_greedy_config_reads_from_settings(fake_playlist_spotify, monkeypatch):
    monkeypatch.setattr("src.services.playlistBuilderService.settings.playlist_max_candidate_distance", 0.6)
    monkeypatch.setattr("src.services.playlistBuilderService.settings.playlist_max_tracks_per_artist", 5)
    service = PlaylistBuilderService(fake_playlist_spotify)
    weights = DistanceWeights()

    config = service._greedy_config(weights)

    assert config.max_candidate_distance == 0.6
    assert config.max_tracks_per_artist == 5
    assert config.weights is weights


def test_sa_config_reads_from_settings(fake_playlist_spotify, monkeypatch):
    monkeypatch.setattr("src.services.playlistBuilderService.settings.playlist_max_candidate_distance", 0.6)
    monkeypatch.setattr("src.services.playlistBuilderService.settings.sa_diversity_weight", 0.8)
    monkeypatch.setattr("src.services.playlistBuilderService.settings.sa_temperature_start", 2.0)
    monkeypatch.setattr("src.services.playlistBuilderService.settings.sa_temperature_end", 0.05)
    monkeypatch.setattr("src.services.playlistBuilderService.settings.sa_iterations", 50)
    service = PlaylistBuilderService(fake_playlist_spotify)
    weights = DistanceWeights()

    config = service._sa_config(weights)

    assert config.max_candidate_distance == 0.6
    assert config.diversity_weight == 0.8
    assert config.temperature_start == 2.0
    assert config.temperature_end == 0.05
    assert config.iterations == 50
    assert config.weights is weights


# ---------------------------------------------------------------------------
# _run_selection_strategy
# ---------------------------------------------------------------------------


def test_run_selection_strategy_dispatches_to_greedy(fake_playlist_spotify):
    service = PlaylistBuilderService(fake_playlist_spotify)
    seed_feat = ["seed", {"genres": {"rock"}, "release_year": 2000}]
    candidate_features = [["t1", {"genres": {"rock"}, "release_year": 2000}]]
    candidate_tracks = {"t1": {"artists": [{"id": "artist_1"}]}}

    top_n, fallback, _, trace, threshold_trace = service._run_selection_strategy(
        "greedy", candidate_features, seed_feat, candidate_tracks, n=1, weights=DistanceWeights()
    )

    assert len(top_n) == 1
    assert fallback == "genre_search"
    assert trace == []
    assert len(threshold_trace) == 1


def test_run_selection_strategy_dispatches_to_sa(fake_playlist_spotify, monkeypatch):
    monkeypatch.setattr("src.services.playlistBuilderService.settings.sa_iterations", 10)
    service = PlaylistBuilderService(fake_playlist_spotify)
    seed_feat = ["seed", {"genres": {"rock"}, "release_year": 2000}]
    candidate_features = [[f"t{i}", {"genres": {"rock"}, "release_year": 2000 + i}] for i in range(10)]
    candidate_tracks = {f"t{i}": {"artists": [{"id": f"artist_{i}"}]} for i in range(10)}

    top_n, fallback, _, trace, threshold_trace = service._run_selection_strategy(
        "sa", candidate_features, seed_feat, candidate_tracks, n=4, weights=DistanceWeights()
    )

    assert len(top_n) == 4
    assert fallback.startswith("sa_")
    assert len(trace) == 10
    assert len(threshold_trace) == 1


# ---------------------------------------------------------------------------
# build_playlist_from_seed — end-to-end regression, proving the decomposition
# into the helpers above didn't change observable behavior.
# ---------------------------------------------------------------------------


def test_build_playlist_from_seed_returns_error_when_seed_has_no_artists(fake_playlist_spotify):
    fake_playlist_spotify.tracks["seed_track"] = {"id": "seed_track", "artists": []}
    service = PlaylistBuilderService(fake_playlist_spotify)

    result = service.build_playlist_from_seed("seed_track")

    assert result == {"error": "Seed track has no artist data"}


def test_build_playlist_from_seed_end_to_end_dry_run(fake_playlist_spotify, monkeypatch):
    monkeypatch.setattr("src.services.playlistBuilderService.settings.playlist_max_tracks_per_artist", 3)
    monkeypatch.setattr("src.services.playlistBuilderService.settings.playlist_max_candidate_distance", 0.75)

    fake_playlist_spotify.tracks["seed_track"] = {
        "id": "seed_track",
        "name": "Seed Song",
        "artists": [{"id": "seed_artist", "name": "Seed Artist"}],
        "album": {"release_date": "2000"},
    }
    fake_playlist_spotify.artists["seed_artist"] = {"id": "seed_artist", "genres": ["rock"]}
    fake_playlist_spotify.search_results["genre:rock"] = [
        {
            "id": f"cand_{i}",
            "name": f"Candidate {i}",
            "artists": [{"id": f"cand_artist_{i}", "name": f"Candidate Artist {i}"}],
            "album": {"release_date": f"{2001 + i}"},
        }
        for i in range(3)
    ]
    for i in range(3):
        fake_playlist_spotify.artists[f"cand_artist_{i}"] = {"id": f"cand_artist_{i}", "genres": ["rock"]}

    service = PlaylistBuilderService(fake_playlist_spotify)

    result = service.build_playlist_from_seed("seed_track", n=3, dry_run=True, strategy="greedy")

    assert result["dry_run"] is True
    assert result["selection_strategy"] == "greedy"
    assert result["track_count"] == 4
    assert result["tracks"][0]["seed"] is True
    assert result["tracks"][0]["name"] == "Seed Song"
    assert {t["name"] for t in result["tracks"][1:]} == {"Candidate 0", "Candidate 1", "Candidate 2"}
    assert "playlist_id" not in result
    assert fake_playlist_spotify.created_playlists == []


def test_build_playlist_from_seed_creates_playlist_when_not_dry_run(fake_playlist_spotify, monkeypatch):
    monkeypatch.setattr("src.services.playlistBuilderService.settings.playlist_max_tracks_per_artist", 3)
    monkeypatch.setattr("src.services.playlistBuilderService.settings.playlist_max_candidate_distance", 0.75)

    fake_playlist_spotify.tracks["seed_track"] = {
        "id": "seed_track",
        "name": "Seed Song",
        "artists": [{"id": "seed_artist", "name": "Seed Artist"}],
        "album": {"release_date": "2000"},
    }
    fake_playlist_spotify.artists["seed_artist"] = {"id": "seed_artist", "genres": ["rock"]}
    fake_playlist_spotify.search_results["genre:rock"] = [
        {
            "id": "cand_0",
            "name": "Candidate",
            "artists": [{"id": "cand_artist_0", "name": "Candidate Artist"}],
            "album": {"release_date": "2005"},
        },
    ]
    fake_playlist_spotify.artists["cand_artist_0"] = {"id": "cand_artist_0", "genres": ["rock"]}

    service = PlaylistBuilderService(fake_playlist_spotify)

    result = service.build_playlist_from_seed("seed_track", n=1, dry_run=False, strategy="greedy")

    assert "playlist_id" in result
    assert len(fake_playlist_spotify.created_playlists) == 1
    assert fake_playlist_spotify.created_playlists[0]["name"] == "From: Seed Song"
    assert len(fake_playlist_spotify.added_tracks) == 1


def test_build_playlist_from_seed_falls_back_to_discography_when_genre_search_finds_nothing(
    fake_playlist_spotify, monkeypatch
):
    monkeypatch.setattr("src.services.playlistBuilderService.settings.playlist_max_tracks_per_artist", 3)
    monkeypatch.setattr("src.services.playlistBuilderService.settings.playlist_max_candidate_distance", 0.75)

    fake_playlist_spotify.tracks["seed_track"] = {
        "id": "seed_track",
        "name": "Seed Song",
        "artists": [{"id": "seed_artist", "name": "Seed Artist"}],
        "album": {"release_date": "2000"},
    }
    fake_playlist_spotify.artists["seed_artist"] = {"id": "seed_artist", "genres": ["rock"]}
    # No search results registered at all -> genre search finds zero candidates.
    fake_playlist_spotify.artist_tracks["seed_artist"] = [
        {
            "id": f"disc_{i}",
            "name": f"Discography {i}",
            "artists": [{"id": "seed_artist", "name": "Seed Artist"}],
            "album": {"release_date": f"{2001 + i}"},
        }
        for i in range(3)
    ]

    service = PlaylistBuilderService(fake_playlist_spotify)

    result = service.build_playlist_from_seed("seed_track", n=2, dry_run=True, strategy="greedy")

    assert result["fallback"] == "artist_discography"
    assert result["track_count"] == 3
    assert result["tracks"][0]["seed"] is True
    assert {t["name"] for t in result["tracks"][1:]}.issubset({"Discography 0", "Discography 1", "Discography 2"})
