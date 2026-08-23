# Worklog — create-spotify-playlist

Narrative of decisions, pivots, and discoveries made building this tool.
Ordered chronologically. Includes dead ends and why they happened.

## Data

Current data used to build playlists — 17 liked songs as of June 2026.

```
┌────────────────────────┬────────────────────────────────────┬───────────────────────────────────┐
│        Track ID        │                Name                │              Artist               │
├────────────────────────┼────────────────────────────────────┼───────────────────────────────────┤
│ 5VXIB8xTvgVPggv1Zmt1KZ │ So Good                            │ Papy Messages                     │
│ 1goiRWxiG3GTlODrdDZ7NR │ Jireh                              │ Elevation Worship / Maverick City │
│ 3JsccmLDh628MBNW17aMBP │ I Looked Up                        │ Sons Of Sunday                    │
│ 1BqBJvGZn8G7buagrQfmJP │ Lead Me On - Live                  │ Chandler Moore                    │
│ 7HAMOncV54OLHqXuKRBXIh │ So Will I (100 Billion X)          │ Hillsong UNITED                   │
│ 1fcytmf4DjBc7ZkhSPnNIP │ Behold (Then Sings My Soul) - Live │ Hillsong Worship                  │
│ 4BuSQyy705aZqKoAiKfqKJ │ Make Room                          │ The Church Will Sing              │
│ 4ElNxglBjcrASiGn58t9Jm │ God Only Knows                     │ for KING & COUNTRY                │
│ 5lwi7XvSzlGsJ6NIGR1qAn │ Love of God (Live)                 │ Brandon Lake / Phil Wickham       │
│ 5xREHZNlYVYoVDkVmrztUS │ Gotham City                        │ DizzyEight                        │
│ 43HieN3qrUrZUgAsyhFTDM │ Always Been You - Live             │ Naomi Raine                       │
│ 6QYz6UacqclzLtzi2QTtol │ Way Maker                          │ Leeland                           │
│ 0KIv0Lho9vsPCj8Sac21IV │ Flowers                            │ Samantha Ebert                    │
│ 59uuKDpLFhHtCWwMudospF │ Goodness Of God - Live             │ CeCe Winans                       │
│ 0Bn1DSXfisvfKjGUwI6rzW │ Oceans (Where Feet May Fail)       │ Hillsong UNITED                   │
│ 3w3FVxMsBMHKaElaJPnkRD │ Way Maker - Live                   │ Leeland                           │
│ 6Up545NUflOiXo8cEraH49 │ You Say                            │ Lauren Daigle                     │
└────────────────────────┴────────────────────────────────────┴───────────────────────────────────┘
```

---

## Phase 1 — Foundation

**Stack**: FastAPI + uv + pydantic-settings. No spotipy — raw HTTP via `requests` against the Spotify Web API. Auth flow manual (PKCE-style code exchange, token refresh, token persisted to `token.json`).

**Core service**: `SpotifyService` — wraps all Spotify API calls, handles token lifecycle. Endpoints: liked songs (paginated), playlists (get/search/remove tracks), delete tracks.

**First real problem**: date filtering on liked songs. Spotify returns `added_at` as ISO 8601 (`"2025-09-16T14:32:00Z"`). Initial implementation tried datetime parsing. Observation: ISO 8601 dates sort lexicographically — `"2025-09-16" < "2025-10-01"` is valid string comparison. Kept it simple, no datetime import needed.

**Batch delete by date**: `delete_liked_songs_on_or_before(before, dry_run=True)`. Key insight — Spotify returns liked songs newest-first, so we can stream and stop early for "after date" queries, but "before date" requires scanning everything. Used `itertools.islice` + walrus operator for clean 50-track batching (Spotify's API max per delete request). `dry_run=True` as default on all destructive operations — never deletes without explicit opt-in.

---

## Phase 2 — Tooling

Replaced `black` + `isort` + `flake8` with `ruff` (lint + format in one tool). Added `pyright` for type checking. Updated `Makefile` (`lint`, `format`, `typecheck`, `check`). Updated `.pre-commit-config.yaml`. Both tools configured to exclude `src/legacy/` (legacy code kept for reference, not linted).

---

## Phase 3 — Playlist Builder (first attempt)

Goal: build playlists from liked songs by genre, ordered by BPM — so listening flows naturally without shuffle.

**Design decision**: new `PlaylistBuilderService` class (not inheriting `SpotifyService` — composition over inheritance). Singleton pattern: `services/__init__.py` exports `spotify` and `playlist_builder` instances. Both consumed by `app.py` via import.

**Travelling Sales Man (TSP) genetic algorithm** ported from `src/legacy/` with fixes:
- Graph changed from `list[list]` (O(n²) lookups) to `dict[str, dict[str, float]]` (O(1))
- Walk score stored as last element of walk list
- Selection via tournament (3 random candidates, keep best)
- Crossover splices two parent orderings
- Mutation rotates walk by one position

**BPM ordering**: called `GET /audio-features` to get tempo, energy, danceability per track. Plan was to sort by BPM so playlist flows from slow → fast or clusters by energy.

---

## Phase 4 — Spotify November 2024 Deprecations (Major Pivot)

**Discovery**: `GET /audio-features` returns 403 for apps registered after November 2024. Also deprecated: `/recommendations`, `popularity`, `preview_url`.

This broke the entire BPM/energy ordering strategy. Three signals gone at once.

**Redesign**: replaced audio features with two remaining signals:
1. **Jaccard genre distance** — `1 - |A∩B| / |A∪B|` on artist genre tag sets
2. **Release year distance** — `min(|year_A - year_B| / 50, 1.0)` normalized over 50-year span

Both weights tunable in `settings.py` (`playlist_genre_weight=1.0`, `playlist_year_weight=0.5`).

**Endpoint rename**: `/bpm` → `/chronological` (now sorts by release year since tempo is gone). Two endpoints kept: chronological (simple sort) and TSP (genetic algorithm ordering by genre+year distance).

**Distance is now clean**: `Jaccard × genre_weight + year_dist × year_weight`. Max possible = 1.5.

---

## Phase 5 — Seed-Based Discovery

**Problem**: with only 17 liked songs, genre-based endpoints return too few tracks to be useful. Need to search Spotify's full catalog.

**First attempt**: `GET /artists/{id}/related-artists` → get top tracks from related artists → rank by Jaccard distance to seed. Clean design.

**Second hit from Spotify deprecations**: `/related-artists` returns 404 (also deprecated November 2024). `/recommendations` also gone.

**Second redesign**: `GET /search?q=genre:{genre}&type=track` — still available. Search by each of the seed's genre tags (up to 3), collect candidates, rank by Jaccard distance, run TSP.

New endpoint: `POST /me/playlists/seed/{track_id}?n=20&dry_run=true`

Steps documented in code:
1. Fetch seed track + primary artist genres via `/artists`
2. Search Spotify for tracks matching each of the seed's genres (up to 3)
3. Batch-fetch artist genres for all candidates
4. Build genre+year features for seed and all candidates
5. Rank candidates by Jaccard distance to seed — take top n
6. Run TSP on those n for smooth internal ordering
7. Prepend seed track → create playlist or return dry run stats

Old genre-based endpoints (`/chronological`, `/tsp`) marked deprecated in FastAPI — they only search your own liked songs, seed endpoint searches the full catalog.

---

## Phase 6 — Deduplication Bug

**Problem found**: Spotify has multiple versions of the same song (single release, album version, deluxe edition) — each with a different track ID. Naive dedup by track ID misses these. Result: "Jesus Be The Name" appearing twice, "SO BE IT" appearing twice in the same playlist.

**Fix**: dedup candidates by `(track_name.lower(), primary_artist_id)` — first version seen wins. Removed 51 duplicates from a 150-candidate pool for Jireh seed.

---

## Phase 7 — Genre Pollution & Threshold Filter

**Problem**: `genre:gospel` is a massive bucket. Brazilian gospel, Haitian kompa gospel, afrogospel, traditional gospel all share the "gospel" tag but are stylistically unrelated to CCM/worship. On non-deterministic search runs, Spotify returns different tracks — sometimes the good CCM results, sometimes the obscure international gospel.

**First fix (wrong)**: added `playlist_max_candidate_distance = 0.6` applied to **total distance** (Jaccard + year_dist). Too strict — tracks with 2 of 5 shared genres (Jaccard=0.6) plus any year gap exceeded 0.6 total. Legitimately similar CCM tracks filtered out.

**Second problem found**: max possible total distance = 1.5 (not 1.0). Tracks with empty genres (Jaccard=1.0) + any year gap have total > 1.0. Using 1.0 as the "no filter" fallback silently blocked candidates.

**Correct fix**: threshold applied to **Jaccard distance only** (genre relevance), not total distance. Total distance still used for TSP ranking. Default threshold raised to 0.75.

Progressive fallback chain:
- `0.75` (strict, >25% genre overlap required)
- `0.85` → `0.95` → `1.0` (relax if < 3 candidates pass)
- Artist discography fallback (`/artists/{id}/albums` → track list) for niche/untagged artists

---

## Phase 8 — Niche Artist Fallback

**Problem**: low-popularity artists (e.g. Papy Messages, popularity=0) have no genre tags on Spotify. Genre search for `genre:Papy Messages` returns nothing. Endpoint returned a generic error.

**Fix**: three-stage error handling:
1. No genres → fall through to genre search with artist name (returns 0 → continue)
2. All thresholds exhausted → fetch artist's own discography via `/artists/{id}/albums`
3. Discography also empty → return descriptive error with `seed_genres` and `candidates_searched`

Response now includes `fallback` (which strategy ran) and `threshold_used` (what Jaccard cutoff was applied) so you can see exactly what happened.

---

## Phase 9 — Artist Popularity Bias & Cap

**Problem**: popular artists (Elevation Worship, Hillsong, Bethel Music) dominated every playlist. Two compounding reasons:
1. Spotify search returns popular artists first — so they flood the candidate pool across all genre queries
2. Jaccard correctly identifies them as most similar to each other — they all share identical tag sets (`ccm, christian, gospel, pop worship, worship`), so they rank first regardless of artist cap on the pool

**First fix (wrong)**: capped tracks per artist in the *candidate pool* only. Did nothing to the final playlist — top 20 by Jaccard distance were still all Elevation/Hillsong/Bethel because they share exact genre tags and all have low distance from each other.

**Correct fix**: cap applied at *selection* — walk candidates in distance order, skip an artist once it contributes `playlist_max_tracks_per_artist` tracks to `top_n`. Cap on candidates still kept to reduce API round-trips (fewer artist genre fetches).

```python
# settings.py
playlist_max_tracks_per_artist: int = 3

# Step 5 — selection with artist cap enforced
for c in sorted(genre_relevant, key=lambda c: _get_distance(seed_feat, c)):
    artists = candidate_tracks.get(c[0], {}).get("artists", [])
    aid = artists[0]["id"] if artists else ""
    if artist_final_counts.get(aid, 0) >= settings.playlist_max_tracks_per_artist:
        continue
    artist_final_counts[aid] = artist_final_counts.get(aid, 0) + 1
    top_n.append(c)
    if len(top_n) >= n:
        break
```

**Also fixed**: threshold relaxation previously stopped at `>= 3` candidates — stopped too early when n=20 was requested. Changed to `>= n` so thresholds keep relaxing until the playlist can actually be filled.

**Result with Jireh seed**: 125 candidates, 31 tracks, `improvement_pct` 59.4% — playlist now spans Charity Gayle, Mozaiek Worship, Gateway Worship, CeCe Winans, Leeland, Matt Redman, All Sons & Daughters alongside the popular artists, each capped at 3.

**Considered but rejected**: containment/overlap coefficient instead of Jaccard. Rejected because containment has no upper bound on genre drift — a track with 50 tags containing all seed genres gets similarity=1.0 regardless of the other 45 tags.

```
┌────────────────────┬──────────────────────┬───────────────────────────────────────┐
│       Metric       │       Formula        │               Behavior                │
├────────────────────┼──────────────────────┼───────────────────────────────────────┤
│ Jaccard (current)  │ |A∩B| / |A∪B|        │ Penalizes BOTH sides for extra tags   │
│ Containment (left) │ |A∩B| / |seed|       │ "Does candidate cover seed's genres?" │
│ Overlap coeff      │ |A∩B| / min(|A|,|B|) │ Rewards being a subset of seed        │
└────────────────────┴──────────────────────┴───────────────────────────────────────┘
```

---

## Phase 10 — Understanding TSP Scores

**What the numbers mean**:

- `initial_score` — total path length of a *random* ordering before the algorithm runs. Sum of distances between every adjacent track pair. With 30 tracks = 29 edges, max per edge = 1.5 (Jaccard × 1.0 + year_dist × 0.5).
- `tsp_score` — same sum after the genetic algorithm finishes. Lower = smoother transitions between adjacent tracks.
- `improvement_pct = (1 - tsp_score / initial_score) × 100`

**Reading the Jireh result** (`initial: 11.69`, `tsp: 4.75`, `improvement: 59.4%`):

```
Average transition before: 11.69 / 29 = 0.40 per edge  (out of max 1.5)
Average transition after:   4.75 / 29 = 0.16 per edge
```

59.4% improvement means real genre/year variance existed in the pool and the algorithm successfully clustered similar tracks together — `{christian, worship}` tracks group before bridging into `{ccm, christian, pop worship, worship}` and so on, rather than jumping randomly.

**Interpreting the scale**:
- `0%` — nothing to optimize (all tracks identical genre+year, initial already near 0) or algorithm too small (population/generations)
- `20–40%` — moderate variance, tracks fairly similar
- `40–60%` — strong improvement, meaningful genre/year spread in pool
- `>60%` — large variance, algorithm had lots of room to find a better route

**Tag density and edge weights — the nuance**:

Tag count doesn't change *which* nodes TSP visits (it visits all of them). It changes *edge weights*, which affects ordering.

```
Within 5-tag cluster:   EW {ccm, christian, gospel, pop worship, worship}
                     Hillsong {ccm, christian, gospel, pop worship, worship}
                     → Jaccard = 1 - 5/5 = 0.0  (zero-cost edge)

Cross-cluster:             EW {ccm, christian, gospel, pop worship, worship}
                      Charity {christian, worship}
                     → |A∩B|=2, |A∪B|=5 → Jaccard = 1 - 2/5 = 0.6

Within 2-tag cluster:  Charity {christian, worship}
                       Gateway {christian, worship}
                     → Jaccard = 1 - 2/2 = 0.0  (also zero-cost)
```

Both clusters are internally tight (0.0 edges). But crossing between them costs 0.6. TSP minimises total path — it groups each cluster as a consecutive block with one expensive jump between them. What you actually hear: `EW → Hillsong → Bethel → [0.6 jump] → Charity Gayle → Gateway → The Belonging Co`.

Tag density itself isn't the bias. The bias is **asymmetry**: a 5-tag artist is always 0.6 away from a 2-tag artist, but two 5-tag artists with identical tags are 0.0 from each other.

The *selection-stage* bias (Step 5) is separate: 5-tag artists always rank first in the distance sort (Jaccard 0.0 to a 5-tag seed) so they fill their `artist_cap` slots before lesser-known artists are even considered. That's a ranking problem, not a TSP problem.

**Duration signal**: `duration_ms` available on all track objects, could proxy "live vs studio" (live tracks typically longer). Not yet wired into distance computation.

---

## Phase 11 — Pluggable Selection Strategies (SA vs Greedy)

**Root problem**: greedy artist-cap selection collapses the selected set onto a single cluster in genre space. Even with cap=3, all 20 picks come from artists sharing near-identical tag sets. The set has near-zero variance across genre dimensions.

**What was discussed**: three classes of solution exist in literature for this type of constrained diverse subset selection problem.

| Method | Mechanism | Stochastic | Multi-dim | Complexity |
|---|---|---|---|---|
| Greedy cap (current) | hard per-artist limit | no | no | O(n) |
| MMR | λ × relevance − (1−λ) × similarity-to-selected | no | soft | O(n × C) |
| Simulated Annealing | energy minimisation with temperature | yes | yes | tunable |
| DPP + MCMC | det(L_S) kernel, sample diverse subsets | yes | yes | O(n²) per step |
| Multi-aspect (Agrawal) | cover multiple intent axes | no | yes | O(n × intents) |

**Key insight from discussion**: MMR, DPPs, and SA all solve the same question — "find n picks where the selected set doesn't collapse to a single point in genre space." They differ in how they enforce it:
- Artist cap: hard discrete constraint, doesn't understand feature space
- MMR λ: greedy soft penalty, can't undo early bad picks
- SA: stochastic, can escape local optima by accepting worse moves with probability `e^(-ΔE/T)`
- DPP: `det = 0` when two items identical, maximised when items span feature space — zero-variance subsets have zero probability

**Why DPP is overkill here**: DPPs are a probabilistic *sampler*, not a deterministic ranker. Requires computing/approximating det(L) for a similarity kernel matrix. Mathematically elegant but complex. SA gives most of the benefit without the kernel math.

**Decision**: implement SA as a pluggable strategy alongside greedy cap. Single `strategy` query param on the API (`greedy` or `sa`) so both can be compared on the same seed.

**SA energy function**:
```
E(S) = avg_relevance(S) − β × avg_pairwise_diversity(S)
     = (Σ dist(seed, sᵢ) / n) − β × (Σ dist(sᵢ, sⱼ) / C(n,2))
```
β = `sa_diversity_weight` (default 0.5). At β=0: pure relevance. As β→∞: pure diversity. Normalised so β=1.0 means equal average weight on relevance and pairwise spread.

**Architecture**: Step 5 extracted from `build_playlist_from_seed` into `src/services/selectionStrategies.py`. Distance functions moved there too. Both `select_greedy` and `select_sa` share the same signature → pluggable without changing orchestrator logic.

**Papers cited**:
- Carbonell & Goldstein (1998) — MMR: https://dl.acm.org/doi/10.1145/290941.291025
- Agrawal et al. (2009) — Multi-aspect diversification: https://dl.acm.org/doi/10.1145/1498759.1498766
- Kulesza & Taskar (2012) — DPPs for machine learning: https://arxiv.org/abs/1207.6083
- Kirkpatrick et al. (1983) — Simulated annealing: https://www.science.org/doi/10.1126/science.220.4598.671

---

**Empirical comparison — Jireh seed, n=20, β=0.5:**

| | Greedy | SA |
|---|---|---|
| tsp_score | 2.73 | 3.94 |
| initial_score | 5.30 | 7.88 |
| improvement_pct | 48.5% | 50% |
| EW tracks | 3 | 1 |
| Bethel tracks | 3 | 1 |
| New artists (vs greedy) | — | Charity Gayle, Gateway Worship, Josiah Queen, ELEVATION RHYTHM |

**Reading the tradeoff**: SA's `initial_score` is higher (7.88 vs 5.30) because the selected pool IS more diverse — adjacent tracks have larger genre jumps. TSP minimises those, landing at 3.94 vs greedy's 2.73. The playlist flows slightly less smoothly but no longer sounds like a single artist's extended set.

`improvement_pct` is higher for SA (50% vs 48.5%) even though absolute `tsp_score` is worse — more room to optimise = more diverse pool. TSP doing the same relative job on harder material.

**β sensitivity**: β=0.5 delivers clear diversity gains. Raise β → 1.0: SA pushes further into niche territory. Lower β → 0: SA converges toward greedy behaviour. The knob is meaningful and interpretable.

---

**Empirical comparison — CeCe Winans seed `{christian, gospel, worship}`, n=20, β=0.5:**

| | Greedy | SA |
|---|---|---|
| tsp_score | 2.15 | 7.16 |
| initial_score | 6.34 | 9.03 |
| improvement_pct | 66.1% | 20.7% |
| Notable artists | Leeland, Mozaiek, Charity Gayle, SEU, Gateway | Mary Mary, Bebe Winans, Piano Prayer, All Sons & Daughters |

**Greedy wins here.** 3-tag seed creates a wider Jaccard gate — more artists naturally pass the 0.75 threshold, so greedy already finds genuine variety without diversity forcing. SA's energy function then overshoots, pulling in gospel R&B (Mary Mary, 2000), gospel-only (Bebe Winans), and instrumental worship (Piano Prayer) — all technically pass the threshold:

```
{gospel} vs {christian, gospel, worship}       → Jaccard = 1 - 1/3 = 0.667 ≤ 0.75 ✓
{christian r&b, gospel} vs {christian, gospel, worship} → Jaccard = 1 - 1/4 = 0.75 ✓ (boundary)
```

SA rewards these because they're maximally diverse from everything else already selected. Stylistically coherent as "gospel broadly" — not coherent as a listening experience. tsp_score 7.16 confirms TSP couldn't bridge those genre gaps.

**Key finding — β is not seed-agnostic:**

| Seed tag count | Greedy behaviour | SA behaviour | Winner |
|---|---|---|---|
| 5 tags (Jireh) | popular-artist flood, homogeneous | diverse CCM, new artists | SA |
| 3 tags (CeCe) | naturally diverse, all cohesive | genre drift into R&B/instrumental | Greedy |

SA's diversity pressure scales with how many candidates pass the threshold. A 3-tag seed admits a wider candidate pool, giving SA more "exotic" material to explore. β=0.5 that works for Jireh overshoots for CeCe.

**Open question**: β should probably scale with seed tag density — high-tag seeds need more diversity forcing, low-tag seeds need less. Alternatively, expose β as a per-request API parameter and let the user tune it.

---

## Phase 12 — Tags Are the Search Space proxy of  deprecated /audio-features

**The deeper problem**: β adjustment is a symptom fix. The CeCe result forced a more fundamental question — the entire system's search space is defined by genre tags, and that definition is flawed in two structural ways.

**Problem 1 — tag count changes metric resolution.** Jaccard 0.667 means different things depending on tag density:
```
{gospel} vs {christian, gospel, worship}            → 0.667  (1 shared / 3 union)
{christian, gospel} vs {christian, gospel, worship} → 0.333  (2 shared / 3 union)
```
Same numerical distance, completely different musical meaning. The metric is not comparable across artists with different tag counts. A 1-tag artist at distance 0.667 from the seed is NOT musically equivalent to a 2-tag artist at 0.667. The Jaccard score conflates "few shared tags" with "many tags but few overlapping".

**Problem 2 — tags are not atomic or orthogonal.** `gospel` spans CCM, gospel R&B, afrogospel, kompa gospel — disconnected musical regions sharing one label. SA sees tracks with `gospel` as occupying the same genre dimension and maximises spread across them. Mary Mary (`christian r&b, gospel`) and Maverick City (`christian, gospel, worship`) both have `gospel` → SA treats them as covering different corners of that dimension → rewards selecting both. Musically, they are from different worlds.

SA is doing exactly what it was designed to do. The search space it is exploring is just not what we want it to be. Every component — Jaccard threshold, `get_distance`, SA energy, TSP graph edges — inherits this assumption: **genre tags ≈ musical similarity**.

**What genre tags actually are:**

> genre tags = vocabulary words in a bag-of-words model, unweighted — where the most frequent terms (`worship`, `christian`, `gospel`) dominate every distance calculation despite carrying the least discriminating information, and rare terms (`christian r&b`, `christian folk`, `country christian`) that mark real stylistic boundaries contribute almost nothing because they appear in fewer intersection sets.

The common tags are stop words. The rare tags are the actual signal. Jaccard treats them equally.

**What the search space actually means — signal vs noise:**

The real search space we want: *"would a listener naturally move from track A to track B without noticing a jarring shift."* Its true dimensions are tempo feel, emotional weight, production density, lyrical intimacy, cultural/regional sound, era. That is what `/audio-features` partially gave us. Spotify deprecated it.

Genre tags are Spotify editorial labels assigned to *artists*, not tracks. They cluster by cultural scene (`ccm` = white American evangelical radio), production era (`pop worship` = post-Hillsong 2010s), and genre lineage (`gospel` = Black church tradition). They partially capture the real dimensions but conflate several at once:

| Signal (real dimension) | Tag proxy | Noise introduced |
|---|---|---|
| Cultural/scene alignment | `ccm`, `christian folk`, `christian r&b` | `christian`, `worship` overlap everything |
| Production era | `pop worship` (2010s) | `gospel` spans 1960–2026 |
| Regional origin | `afrogospel`, `kompa gospel` | `gospel` swallows them |
| Emotional register | — | no tag exists for this |

> **genre tags = coordinates in a space where the axes are unevenly informative.** The axes everyone shares (`worship`, `christian`) have near-zero resolution because they separate nothing. The axes few share (`christian r&b`, `christian folk`, `country christian`) have the highest resolution because they mark real boundaries. Jaccard treats all axes as equal — the metric is dominated by noise, blind to signal.

Weighted Jaccard doesn't redefine the search space. It suppresses the loudest noise so weaker but meaningful tags can be heard. We are fixing a broken proxy through a better proxy. The honest limit: tags don't span the real search space. They are noisy projections of it. The actual dimensions — tempo feel, emotional weight, production density — were what `/audio-features` gave us. We are approximating with what Spotify left available.

**The principled fix — weighted Jaccard with IDF-style tag weights:**
```
w(tag) = log(total_candidates / candidates_with_tag)

weighted_jaccard(A, B) = Σ min(w(t)) for t in A∩B
                         ─────────────────────────────
                         Σ max(w(t)) for t in A∪B
```
`worship` (80% of candidates) → weight ≈ 0.22 → near-zero contribution.
`christian r&b` (2% of candidates) → weight ≈ 3.9 → high contribution.

Now distance between seed and Mary Mary reflects the true signal (`christian r&b` is high-information divergence from `{christian, gospel, worship}`), not a reward. SA's search space becomes "variation in specific, rare genre dimensions" — which is the actual musical variation we want.

**Ongoing / Next:**

**Weighted Jaccard**: compute tag IDF over the candidate pool per request (cheap, O(candidates × tags)), replace `jaccard_distance` in `selectionStrategies.py` with weighted version.

**β per request**: expose `sa_diversity_weight` as a query param for per-seed tuning in the meantime.

**Duration distance**: `duration_ms` as third signal — proxy for live vs studio without needing deprecated audio features.

## Phase 13 — Dry Run: `build_playlist_from_seed` Against Real Gospel Variants

First real-catalog run of the extracted `src/algorithms/` package end to end, no mocks. Nine gospel genre variants confirmed against Spotify's actual search index (`genre:gospel`, `traditional gospel`, `southern gospel`, `funk gospel`, `brazilian gospel`, `urban gospel`, `christian gospel`, `worship gospel`, `contemporary gospel`), then each one dry-run through `build_playlist_from_seed`. Script and full writeup live in `examples/gospel_genre_variants.py`.

**Finding: `genre:"..."` search and an artist's actual `genres` tag list are two different things.** Spotify's search filter does fuzzy full-text matching against its search index; it is not a lookup into the tag list itself.

- `funk gospel` is a confirmed real artist tag (seen directly on an artist returned by a broader `genre:gospel` search) but a direct `genre:"funk gospel"` search returns zero tracks.
- `urban gospel` and `christian gospel` searches returned tracks whose artists aren't actually tagged with those genres at all — one had no genres tagged whatsoever. Not a bug in our code, but it usefully exercised the `artist_discography` and `relaxed_threshold_1.0` fallback paths for real, not synthetically.

Clean variants (default 0.75 threshold, no fallback): `gospel`, `traditional gospel`, `southern gospel`, `brazilian gospel`, `contemporary gospel`.

**Ongoing / Next:**

**Frontend visualization idea (parking here so it isn't lost)**: for the lava-lamp-style playlist DNA visualization, pull each track's artist image (Spotify returns this on the artist object we already fetch for genres) and use it inside the blob/particle representing that track, so a viewer can visually see which artists are actually in the mix as the SA trace animates, not just abstract color/energy blobs.

## Phase 14 — JSONL Persistence for the SA Trace (DNA Visualization Data Source)

Called out directly: the Phase 13 dry run tested search/selection/fallback correctness, it did not produce any visualization data — `sa_trace` was computed in `build_playlist_from_seed` and then discarded, no sink existed. Built the actual sink.

`src/algorithms/persistence.py` — `RunTraceWriter(run_id, runs_dir="runs")`. One file per run at `runs/{run_id}.jsonl`, one JSON object per line, four methods: `write_seed`, `write_candidates`, `write_sa_iteration`, `write_final`. Three new Pydantic models in `models.py` (`SeedTraceEvent`, `CandidateTraceEvent`, `FinalTraceEvent`) alongside the existing `SAIterationEvent`, which was missing a `stage` field entirely — caught this by actually reading the file back and hitting a `KeyError: 'stage'` on line one, not by review.

Wired into `build_playlist_from_seed`: generates a `run_id` (uuid4 hex, or accepts one), writes seed once, sa_iteration per SA loop iteration (both the main selection attempt and the discography fallback re-run, if it happens), candidates once after both attempts (`candidate_tracks` is mutated in place by the discography fallback, so writing after captures the full final pool), final once. Response now carries `run_id` and `trace_path`.

Verified against a real run, not just unit tests: `genre:gospel` seed, `strategy="sa"`, n=10 → 1060 real lines (1 seed, 58 candidate, 1000 sa_iteration, 1 final), read back and inspected line by line.

9 new tests in `tests/test_persistence.py` — the module was untested before this, now every method plus the zero-initial-score guard and multi-writer isolation are covered directly, not just indirectly through `build_playlist_from_seed`.

**Ongoing / Next:**

**Not yet captured, real gaps not silently skipped**: threshold-relaxation steps inside `select_greedy` / the discography fallback path aren't emitted as events. Per-generation TSP trace doesn't exist — `order_by_tsp` returns only `(ordered_ids, final_score, initial_score)`, would need turning into a generator the same way `SimulatedAnnealer.run()` already is.

**HTTP exposure**: nothing serves a run's JSONL file over HTTP yet. Needed before the item 6 web interface can consume it from a browser instead of reading the local file directly.

## Phase 15 — threshold_step, TSP as a Generator, HTTP Exposure

Closed out the three gaps Phase 14 ended on.

**threshold_step**: both `select_greedy` and `SimulatedAnnealer.__init__` already looped over `[max_candidate_distance, 0.85, 0.95, 1.0]` relaxing the Jaccard threshold until enough candidates passed — that loop just never recorded what it tried. Both now build a `list[ThresholdStepEvent]` (threshold, candidates_passing, accepted) as they loop; `select_greedy`'s return signature grew a 4th element, `SimulatedAnnealer` exposes it as `self.threshold_trace` and `run_to_completion()` grew a 5th return value. Every call site and every existing test that unpacked these tuples needed updating — a real ripple, not just additive.

**TSP as a generator — first attempt was wrong.** Initial version yielded one aggregate event per generation (best/worst/mean score only). Called out directly: that throws away the population diversity the visualization is supposed to show, an aggregate is a regression from "trace" to "summary."

Fixed with a content-addressed walk cache instead of truncating anything. The insight: `_apply_selection` carries tournament-winning survivors forward as the literal same walk, and `_apply_mutation` leaves ~half the population untouched each generation — so most of a generation's "population" is content that already appeared in an earlier generation. `TSPOptimizer` now assigns each distinct track ordering an incrementing `walk_id` the first time it's seen (`generation=0` = initial random population included), writes a `TSPWalkEvent(walk_id, track_ids)` once per distinct ordering ever, and a `TSPGenerationEvent(generation, members=[{walk_id, score}, ...])` once per generation with the *entire* population, every member, referencing walks by id instead of repeating track ids. Full diversity, no 80% cutoff, affordable because the expensive payload (track ids) is deduplicated by content rather than repeated per generation.

Verified the cache is doing real work, not just correct: a real run (n=10, generations=50, population_size=20) produced 334 `tsp_walk` events against 1020 total population slots across 51 generation events (generation 0 + 50 evolved) — 32.7% cache-miss rate, meaning two-thirds of every generation's population was already-known content reused from an earlier generation.

`order_by_tsp` kept its existing 3-tuple return signature (unaffected callers: `build_genre_playlist_tsp`, all of `test_tsp.py`) by becoming a thin wrapper that constructs a `TSPOptimizer` and drains `run_to_completion()`, discarding the trace. Only `build_playlist_from_seed` was changed to use `TSPOptimizer` directly and write both event types.

**HTTP exposure**: `GET /runs/{run_id}` (`src/app.py`), backed by `read_run_trace()` in `persistence.py`. Returns the JSONL file verbatim as `application/x-ndjson`, not re-parsed into a JSON array — matches the on-disk format exactly in case a future version streams a run's lines while it's still in progress. Guards against path traversal (`run_id` becomes part of a file path): resolves the path and rejects anything that would land outside `runs_dir`, tested with `../secret`, `../../etc/passwd`, and an embedded `/`.

Verified against a running server, not just TestClient: started uvicorn for real, `POST /me/playlists/seed/{track_id}?strategy=sa` against a live gospel seed, then `GET /runs/{run_id}` against that same server — 1446 real lines, every stage present (1 seed, 58 candidate, 1 threshold_step, 1000 sa_iteration, 334 tsp_walk, 51 tsp_generation, 1 final), inspected line by line. Left the resulting `runs/{run_id}.jsonl` on disk this time instead of cleaning it up, so it can be opened and inspected directly.

16 new/updated tests: `ThresholdStepEvent` coverage in `test_selection.py`, a new TSPOptimizer section in `test_tsp.py` (generation numbering, full-population-per-generation, walk dedup by content, every population member resolves to an already-written walk_id), `read_run_trace` coverage and a new `test_run_trace_endpoint.py` in `test_persistence.py`/`tests/`.

**Ongoing / Next:** TSP walk lineage (which parent produced which child via crossover/mutation) isn't recorded — only content + score. Would let a frontend animate an actual parent-to-child morph instead of just "this walk_id appeared." Item 6 (the actual web interface) is next.

## Phase 16 — Retention Policy, TSP Walk Lineage

Two asks. Found a real bug chasing down the first one.

**Retention policy**: `settings.runs_dir` (absolute — `RunTraceWriter`/`read_run_trace` still default internally to the cwd-relative `"runs"` literal, same bug class as the earlier `.env` fix, a relative path silently lands wherever the process started from) and `settings.runs_retention_days` (default 7). `cleanup_old_runs(runs_dir, max_age_days)` in `persistence.py` deletes `*.jsonl` files by mtime, kept settings-free like the rest of the module (explicit params, no `from src.settings import settings` inside `src/algorithms/`) — `PlaylistBuilderService` and `app.py`'s lifespan pass `settings.runs_dir`/`settings.runs_retention_days` in explicitly, same convention as `GreedySelectionConfig`. Runs on every app startup (FastAPI `lifespan`) and on demand via `make clean-runs`.

While wiring this up, checked whether the test suite itself was polluting `runs/` — it was. `test_playlist_builder_service.py`'s `build_playlist_from_seed` calls go through the real `RunTraceWriter` with no isolation, so every `pytest` run had been silently writing real files into the actual project `runs/` directory (confirmed: ran the suite, watched new files appear). Fixed with an autouse `isolated_runs_dir` fixture in `conftest.py` that monkeypatches `settings.runs_dir` to a per-test `tmp_path` — verified fixed by running the full suite twice and confirming `runs/` didn't grow.

**TSP walk lineage** — the harder one. Needed `parent_walk_ids` on every `TSPWalkEvent`: `[]` for the initial random population, `[p]` for a mutation, `[a, b]` for a crossover. The obvious approach (diff each generation's population against the last to infer who mutated from what) doesn't work: a crossover child can get mutated in the *same* `_apply_genetics()` call, before TSPOptimizer ever sees a generation boundary to diff against — there's no "previous generation" to compare that intermediate child to.

Fixed by inverting where identity gets assigned: instead of `TSPOptimizer` scanning the finished population after the fact, the genetic operators (`_apply_crossover`, `_mutate`) now call an injected `register(track_ids, score, parent_walk_ids)` callback at the exact moment they create a new walk, and get back a `Walk` with its content-addressed `walk_id` already resolved — immediately, not after the generation completes. `_apply_selection`, `_apply_crossover`, `_apply_mutation` all stay stateless functions themselves; the actual mutable registry (`_walk_registry: dict[tuple[str,...], int]`) lives solely in `TSPOptimizer`, threaded in as a bound method. This is why the population representation changed from a raw `list[str | float]` (track ids + trailing score) to a small `Walk` dataclass (`track_ids`, `score`, `walk_id`, `parent_walk_ids`) — needed named fields to carry lineage through the pipeline cleanly.

Verified against a real run (not just unit tests): parent-count distribution across 510 real `tsp_walk` events was `{0: 20, 2: 260, 1: 230}` (20 initial-population walks, 260 crossover children, 230 mutations), a DAG-ordering check over the whole trace confirmed every parent_walk_id was already emitted before anything referenced it (0 violations), and explicitly pulled out the hard case — a mutation whose parent is itself a same-generation crossover child (2 parents) — and confirmed it resolves correctly.

5 new lineage tests in `test_tsp.py`: no-parents for generation 0, parents-always-precede-children (DAG validity), parent count is always 0/1/2, both crossover (2-parent) and mutation (1-parent) lineage actually occur over enough generations (not just structurally possible), and the same-generation crossover-then-mutation case specifically. Ran the probabilistic ones 10x to rule out flakiness before trusting them.

6 new tests for `cleanup_old_runs` (age cutoff, mixed old/recent, missing dir, non-jsonl files ignored).

**Ongoing / Next:** item 6, the actual web interface, is next — the trace format is now feature-complete for what's been asked of it (all 7 stages, full untruncated population, lineage).

## Phase 17 — Rendering Approach Research, TS Codegen, web/ Scaffold

Two things before writing any actual UI: pick a rendering approach with real justification (not vibes), and stop hand-maintaining a second copy of the wire protocol in TypeScript.

**Rendering approach**, grounded in primary sources, not aggregator "X vs Y" sites (several search hits for this were caught looking like AI-generated SEO content farms — generic titles, no author, near-identical marketing-speak snippets across "different" domains — and set aside rather than cited):
- [MDN's WebGL page](https://developer.mozilla.org/en-US/docs/Web/API/WebGL_API): raw OpenGL-ES-conforming API, shader programs, buffers, matrix math from scratch. Even MDN's own docs point to three.js/PixiJS as the practical on-ramp, i.e. nobody really uses it raw. Ruled out: our actual on-screen element count per frame (candidate pool ~50-60, SA/TSP populations ~10-20) never needs GPU-shader-scale performance, and the total event count (1000+ SA iterations, 50+ TSP generations) is animation depth over time, not simultaneous elements.
- [D3's official "What is D3?" doc](https://d3js.org/what-is-d3): explicitly not a renderer, 30 independent modules, its headline feature (DOM enter/update/exit data join) is SVG/DOM-specific. But several modules are completely renderer-agnostic — `d3-interpolate`, `d3-ease`, `d3-force` — pure math, usable standalone with Canvas, no DOM, no "framework."
- [MDN's Canvas API page](https://developer.mozilla.org/en-US/docs/Web/API/Canvas_API): the actual renderer. Trivial to embed images (`drawImage()`, for the artist-picture idea), no DOM/style-recalc overhead, simplest mental model for a first build.
- [CSS-Tricks' Gooey Effect article](https://css-tricks.com/gooey-effect/) (Lucas Bebber): the real lava-lamp/metaball technique — an SVG `<filter>` (`feGaussianBlur` -> `feColorMatrix` alpha-contrast boost -> `feBlend`) applied via plain CSS `filter: url(#goo)`. Crucially, that CSS property works on *any* DOM element, not just SVG shapes — including a `<canvas>`. Article itself flags it can get resource-intensive on large areas.

Decision: Canvas 2D (native, no rendering library) + `d3-interpolate`/`d3-ease`/`d3-force` as pure math imports + the CSS/SVG gooey filter on the canvas element. No framework anywhere in the stack.

**Validated, not just decided**: delegated a subagent to build a throwaway prototype (`prototype/gooey-canvas/`, gitignored — not meant to be committed) applying `filter: url(#goo)` to a `<canvas>` with ~18 animated circles. Real gotcha it found and fixed: `<script type="module">` fails over `file://` (Chromium rejects ES module fetches from a `null` origin) — switched to a classic script tag. It verified the result without any visual/screenshot tooling by driving a second, disposable browser instance over the Chrome DevTools Protocol: confirmed the CSS filter resolved (`getComputedStyle(canvas).filter === 'url("#goo")'`), confirmed pixels were actually drawn (`ctx.getImageData()` non-zero-alpha count), and confirmed animation was live (canvas pixel-buffer hash changed between two timestamps). Left the actual visual judgment to a human — opened it in the real browser for that.

**TypeScript codegen**: added `pydantic2zod` (argyle-engineering) as a dev dependency. Verified it was a real, maintained project *before* trusting it — a search result for a similarly-named but different package ("pydantic-zod-codegen") had the exact same red flags as the rendering-comparison spam (word-for-word identical description across a "PyPI" listing and a "GitHub" listing under a company name that doesn't check out), caught by fetching the real GitHub repo directly instead of citing the snippet.

`web/scripts/generate_ts_models.py` compiles `src/algorithms/models.py` into `web/src/generated/models.ts` (Zod schemas + inferred TS types). Explicitly `IGNORE_TYPES`s `DistanceWeights`/`GreedySelectionConfig`/`SimulatedAnnealingConfig` — backend tuning config, never serialized into the trace or any HTTP response, no reason for the frontend to know about them. This wasn't just tidiness: left in, the tool couldn't translate `GreedySelectionConfig.weights`'s default (an instantiated `DistanceWeights()`) and silently emitted broken Zod (`DistanceWeights.default(null)`, which would reject valid input) — excluding them avoided shipping that bug.

Changed every `*TraceEvent.stage` field in `models.py` from `str = "..."` to `Literal["..."] = "..."` — a real backend correctness fix on its own (nothing previously stopped constructing e.g. a `SeedTraceEvent` with the wrong stage string), and required for the generated Zod to emit `z.literal(...)` instead of a loose `z.string()`, which a discriminated union needs.

`web/src/traceEvent.ts` is hand-written, deliberately kept separate from the generated file: builds `z.discriminatedUnion("stage", [...])` over all 7 trace event schemas, plus `parseTraceLine`/`parseTrace`/`fetchTrace`. "The union of every event type" isn't a Pydantic-side concept pydantic2zod could derive — it's a TypeScript consumption decision, so it doesn't belong in generated output that gets overwritten on every regen.

Verified against a real backend-produced trace, not a fixture: `web/scripts/verify_against_real_trace.ts` parsed an actual `runs/{run_id}.jsonl` from an earlier live server run — 1622 events, all validated, stage counts matched exactly, and independently re-ran the `tsp_walk` DAG-lineage check in TypeScript (0 violations), matching the Python-side check from Phase 16.

`web/` is its own npm package (zod runtime dep; typescript 7.0.2 + tsx dev deps — TS 7 is real, confirmed by what npm actually resolved, not assumed), strict `tsconfig`, no frontend framework. `make generate-ts-models` and `make web-typecheck` added.

**Ongoing / Next:** no actual UI or rendering code exists yet — this phase was the data/type layer only. Next: the event-log -> view-model projector (resolving `walk_id` references, building a playback timeline), then the Canvas renderer itself.

## Phase 18 — Event-Log -> View-Model Projector

`web/src/projector.ts`, `buildViewModel(events) -> PlaylistDNAViewModel`. Pure, no DOM/Canvas — the "reducer" half of the split from Phase 17 (a future renderer only ever touches this output, never `TraceEvent` directly).

Two things this is more than a relabel of the trace:

**Resolves `tsp_walk`/`tsp_generation` references.** Straightforward — the backend already guarantees a walk's `TSPWalkEvent` appears before any generation event that references it (verified back in Phase 16), so a single forward pass builds a `Map<walk_id, TSPWalk>` and resolves each generation's members against it, throwing if a reference is ever unresolved (this is a real invariant check, not defensive noise — if it ever fires, the backend's ordering guarantee broke).

**Reconstructs the SA-selected track set at every iteration — the harder one.** A `sa_iteration` event only records what swapped (`out_track_id` -> `in_track_id`), never the full selection at that point. The only anchor available anywhere in the trace is the *final* result. Realized this is soundly reconstructable, not guesswork: TSP only reorders the SA-selected set, it never changes membership, and the seed is prepended afterward, entirely outside the SA selection. So `final.track_ids` minus the seed is exactly what the SA converged to — walking the iteration list backward from there, undoing each *accepted* swap in reverse, recovers the exact selection after every iteration, all the way back to the true initial random selection before iteration 0.

Real complication caught before it became a silent bug: if the discography fallback triggers, the trace can contain a *second*, independent anneal over a larger candidate pool — and its `sa_iteration` events restart from iteration 0. Naively treating the whole `sa_iteration` stream as one continuous sequence would silently corrupt the backward reconstruction for that case (undoing swaps from an abandoned first attempt as if they were part of the real one). `splitIntoSAEpisodes` detects the restart (iteration failing to strictly increase is only possible at an episode boundary, since `SimulatedAnnealer.run()` always increments by exactly 1) and only reconstructs the *last* episode — the one actually anchored to the final result. Earlier, abandoned episodes are still exposed (iteration/temperature/energy/swap), just without a selection trajectory, since there's nothing sound to anchor one to.

15 tests in `web/src/projector.test.ts` (Node's built-in `node:test`, zero extra test framework dependency): resolution/error-path unit tests, a hand-traced multi-step backward-reconstruction case verified by hand, the episode-split behavior, and — same discipline as the Python side — two tests that run `buildViewModel` against actual `runs/*.jsonl` files produced by a real server, not just synthetic fixtures, checking the reconstructed selection size stays consistent with the final result throughout. `make web-test`/`make web-check` added.

**Ongoing / Next:** the Canvas renderer itself — nothing draws anything yet. The view model is playback-ready; next is turning it into `requestAnimationFrame` frames.

## Phase 19 — Fixed a Test Suite That Scaled With Local `runs/` Growth

Caught immediately, before it became a real problem: Phase 18's real-trace tests scanned the ambient `runs/` directory (`readdirSync(runsDir).filter(...)`, one test per file found) rather than testing against something fixed. Two real problems with that, not just one:

1. **Non-deterministic across environments.** `runs/` is gitignored. On a fresh clone or CI, it doesn't exist at all — `realRunFiles` would be empty, and the "at least one real trace file was found" assertion would fail outright. The suite silently depended on the local machine's dev history.
2. **Unbounded runtime.** Every `build_playlist_from_seed` call mints a fresh `run_id`; nothing prunes `runs/` except age-based cleanup on app startup (7-day default). Under normal local development the directory only grows, and the test suite's runtime would grow with it — scaling with how much the app had been used, not with the size of the test suite.

Fixed by committing one real trace as a fixture instead: `web/src/fixtures/sample-run.jsonl`, copied verbatim from an actual server run (not synthetic, not hand-written) — a strategy=sa run with every stage type present. Test count went from "however many files happen to be in runs/ today" to a fixed 1, bounded regardless of local usage, and identical on every machine including a fresh clone. To refresh the fixture against current backend behavior: regenerate a run and copy it in (documented in a comment at the top of that test section).

## Phase 20 — First Working Visualization

A real, running, playable visualization exists now — `web/index.html`, `web/src/main.ts`, `web/src/renderer.ts`, `web/src/playback.ts`, `web/src/colors.ts`.

**`colors.ts`** — deterministic genre -> HSL hue hashing, no lookup table (Spotify's genre vocabulary is open-ended, confirmed back in the gospel-variant dry run — a maintained table would inevitably miss genres it hasn't seen). Same genre set (any order) always gets the same color.

**`playback.ts`** — the pure simulation layer under the renderer, same reducer/renderer split as `projector.ts` one level deeper: blob positions, organic drift (damped random-walk velocity, bounce off canvas edges), and a `selected` flag that grows/highlights whichever blobs are currently part of the SA/final selection. Randomness is injectable (`random: () => number`, defaults to `Math.random`) specifically so tests can supply a fixed sequence instead of asserting on non-deterministic output — same pattern used for testable randomness elsewhere. 12 tests: bounds, bounce-off-each-edge, "zero jitter moves exactly velocity × dt" (a real deterministic physics check, not just "it changed"), immutability (never mutates the map passed in), and selection toggling both directions.

**`renderer.ts`** — the one file in the pipeline that isn't unit tested, and said so directly in its own docstring rather than silently having a coverage gap: Canvas 2D drawing isn't meaningfully testable without a browser or a jsdom+canvas mock this project isn't pulling in for one file. Drives a `requestAnimationFrame` loop through three phases: `candidates` (intro drift, ~2s) -> `sa` (steps through the last SA episode's reconstructed `selectionsAfter` trajectory from Phase 18, one iteration per `msPerIteration` of simulated time — skipped entirely if the trace has no SA episode, e.g. `strategy=greedy`) -> `final` (highlights the actual result, stays there). Reports phase/iteration progress via an `onStatusChange` callback for the DOM status line.

**Vite added** (`web/vite.config.ts`) — no framework plugins, just a dev server + static build. Its dev-server proxy forwards `/runs` and `/me` to the real FastAPI backend rather than adding `CORSMiddleware` to `src/app.py`, which already locks itself to loopback-only via `LoopbackOnlyMiddleware` — not worth widening backend security config for what's purely a frontend dev-server concern.

**Verified end to end, not just "it compiles"**: started the real backend (`uvicorn`) and the real Vite dev server side by side, generated a genuine `strategy=sa` run against a live gospel seed via the actual `/me/playlists/seed/{track_id}` endpoint, then drove a disposable Brave instance over the Chrome DevTools Protocol (same technique as the gooey-canvas prototype) to: confirm the DOM has the canvas + resolved gooey filter, load that real 1836-event run through the actual UI, confirm pixels were drawn before playback even started (the constructor's initial draw), confirm the pixel buffer's hash changed after clicking Play (proving live animation, not a static frame), and polled status text over ~18 real seconds watching it progress `phase: candidates (intro)` -> `iteration 66/1000` -> ... -> `iteration 866/1000` -> `phase: final playlist`. Zero console/runtime errors throughout. Left the servers running and opened the real page in the default browser afterward for a human to actually look at it.

**Ongoing / Next:** TSP generation playback (population of orderings evolving via parent lineage) isn't built — this version only animates the SA trajectory and the final result. Artist pictures inside blobs (the earlier parked idea) also not wired in yet.

## Phase 21 — Actionable Load Errors, Real Convergence Instead of Random Jitter

Two real problems reported directly from actually using it: an unhelpful error when the backend wasn't running, and — the more important one — the animation "just randomly staying in the same place" instead of showing anything converging.

**Unhelpful load error.** `fetchTrace` (`web/src/traceEvent.ts`) had no handling for `fetch()` itself throwing (the backend not listening at all — a real case, nothing auto-starts uvicorn) or for a response that comes back `ok` but isn't actually JSONL (Vite's dev proxy can answer with its own error page, still `response.ok`, when the backend it's supposed to forward to is unreachable). Both failure modes now get a specific, actionable message instead of a cryptic downstream parse error — including telling the user directly to check `uv run uvicorn src.app:app`. 6 new tests in a new `web/src/traceEvent.test.ts` (parsing basics, fetch throwing, non-ok status, wrong content-type, and the real happy path), using a mocked `globalThis.fetch`.

**No real convergence — the actual bug.** Looked at `playback.ts`: `applySelection` only ever changed a blob's `radius`. Position was driven entirely by `stepPhysics`'s random-walk drift, completely independent of whether a blob was selected. So selection state was cosmetically visible (bigger circle) but nothing ever moved toward anything — exactly "randomly staying in the same place," an accurate description of what the code actually did, not a rendering glitch.

Fixed with two real, tested additions to `playback.ts`:
- `applyAttraction(blobs, target, strength, dtMs)` — pulls every *selected* blob a fraction of the remaining distance toward a target point each step; unselected blobs untouched. Wired in `renderer.ts` to pull toward the seed blob's own current position every frame — selected tracks now visibly gather around the seed as the anneal proceeds, unselected ones stay scattered.
- `stepPhysics` gained a `jitterScale` parameter (default 1, only scales the *new* per-step perturbation, not existing velocity) — the renderer passes the current SA iteration's `temperature` (already cooling from 1.0 to 0.01 by construction, see `SimulatedAnnealingConfig`) as that scale, floored at 0.08 so it settles rather than fully freezing. Blobs now visibly calm down as the anneal cools, instead of jittering at a constant chaotic rate for the entire 1000-iteration run regardless of how close it is to converging.

Verified quantitatively, not just by eye: `web/scripts/verify_convergence.ts` replays the exact same phase logic `Renderer` uses — headless, no browser, driving the real `playback.ts` functions directly against the real `sample-run.jsonl` fixture — and measures the average distance of selected blobs to the seed over the course of the anneal. Result: 313px at iteration 0 (the initial random selection, scattered across the canvas) down to 10-17px by iteration ~300, staying settled in that range through iteration 1000 and into the final phase. That is what "converging" is supposed to look like, now actually happening, not asserted.

6 new tests in `playback.test.ts` for `applyAttraction` (untouched when unselected, closes the gap over repeated steps, `strength=0` is a no-op, never mutates) and `jitterScale` (0 means no new perturbation at all, default 1 does perturb).

37 web tests total, all Python tests still passing, `tsc`/`vite build` clean.
