"""
Demo: discover real gospel genre variants on Spotify, then dry-run
build_playlist_from_seed against each one.

Run with:
    uv run python examples/gospel_genre_variants.py

Requires a valid token.json (run the app's /login flow first) since this
hits the real Spotify catalog, no mocks.

Why this exists
----------------
Spotify's artist `genres` field is free text, there is no fixed enum to
enumerate. The only way to find what's actually in use is to search the
catalog and read the tags back off real artists.

That search surfaced a finding worth documenting for anyone demoing or
extending build_playlist_from_seed: the `genre:"..."` search filter does
fuzzy full-text matching against Spotify's search index, it is NOT the
same lookup as an artist's actual tagged `genres` list. Two failure modes
came out of testing this against gospel:

  1. A genre string can be a real, confirmed artist tag (seen directly on
     an artist object) and still return zero tracks from
     `search_tracks('genre:"that string"')`. `funk gospel` is a
     confirmed example, it showed up tagged on an artist returned by a
     broader `genre:gospel` search, but searching for it directly finds
     nothing.

  2. `genre:"..."` search can return a track whose artist isn't tagged
     with that genre at all, sometimes with no genres tagged whatsoever.
     `urban gospel` and `christian gospel` both did this in testing, the
     top hit was an unrelated artist. This is a genuinely useful case
     to keep around for a demo though: it's exactly the input that
     exercises build_playlist_from_seed's fallback paths
     (artist_discography, relaxed_threshold_*) for real, not synthetically.

Confirmed gospel genre variants (as of this writing)
-----------------------------------------------------
Clean — genre:"..." search returns a track whose artist really carries
that (or a closely related gospel) tag, default 0.75 threshold, no
fallback needed:
    gospel, traditional gospel, southern gospel, brazilian gospel,
    contemporary gospel

Fuzzy — genre:"..." search returns a track NOT actually tagged with that
genre, exercises artist_discography / relaxed_threshold_* fallback paths:
    urban gospel, christian gospel, worship gospel

Untestable via search despite being a real artist tag elsewhere:
    funk gospel  (0 tracks for a direct search)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.playlistBuilderService import PlaylistBuilderService
from src.services.spotifyService import SpotifyService
from src.settings import settings

GOSPEL_VARIANTS = [
    "gospel",
    "traditional gospel",
    "southern gospel",
    "funk gospel",
    "brazilian gospel",
    "urban gospel",
    "christian gospel",
    "worship gospel",
    "contemporary gospel",
]


def _search_query(variant: str) -> str:
    return f'genre:"{variant}"' if " " in variant else f"genre:{variant}"


def dry_run_variant(builder: PlaylistBuilderService, spotify: SpotifyService, variant: str) -> dict:
    """Search for a seed track tagged with `variant`, then dry-run build_playlist_from_seed against it."""
    tracks = spotify.search_tracks(_search_query(variant), limit=1)
    if not tracks:
        return {"variant": variant, "seed": None, "note": "no seed track found for this genre string"}

    seed = tracks[0]
    seed_label = f"{seed['name']} — {seed['artists'][0]['name']}" if seed.get("artists") else seed["name"]

    result = builder.build_playlist_from_seed(seed["id"], n=10, dry_run=True, strategy="greedy")

    return {
        "variant": variant,
        "seed": seed_label,
        "seed_genres": result.get("seed_genres"),
        "fallback": result.get("fallback"),
        "threshold_used": result.get("threshold_used"),
        "track_count": result.get("track_count"),
        "error": result.get("error"),
    }


def main() -> None:
    spotify = SpotifyService(
        client_id=settings.spotify_client_id,
        client_secret=settings.spotify_client_secret,
        redirect_uri=settings.spotify_redirect_uri,
    )
    builder = PlaylistBuilderService(spotify)

    print(f"{'variant':<22} {'fallback':<24} {'threshold':<10} {'tracks':<8} seed")
    print("-" * 100)
    empty_variants: list[str] = []
    for variant in GOSPEL_VARIANTS:
        row = dry_run_variant(builder, spotify, variant)
        if row.get("seed") is None:
            empty_variants.append(row["variant"])
            print(f"{row['variant']:<22} {'EMPTY':<24} {'—':<10} {'0':<8} {row['note']}")
            continue
        print(
            f"{row['variant']:<22} "
            f"{str(row['fallback']):<24} "
            f"{str(row['threshold_used']):<10} "
            f"{str(row['track_count']):<8} "
            f"{row['seed']}"
        )

    print()
    if empty_variants:
        print(f"NOT POPULATED ({len(empty_variants)}/{len(GOSPEL_VARIANTS)}):")
        print('genre:"..." search returns zero tracks for these, even though the tag itself')
        print("may show up on artists reached via a broader genre search:")
        for variant in empty_variants:
            print(f"  - {variant}")
    else:
        print(f"All {len(GOSPEL_VARIANTS)} variants returned a seed track.")


if __name__ == "__main__":
    main()
