"""
Generate web/src/generated/models.ts from src/algorithms/models.py.

The backend is the source of truth for the wire protocol (the JSONL trace
RunTraceWriter produces, see src/algorithms/persistence.py). Run this after
changing any trace event model so the frontend's types can't drift from
what the backend actually emits:

    uv run python web/scripts/generate_ts_models.py

Deliberately ignores DistanceWeights / GreedySelectionConfig /
SimulatedAnnealingConfig: these are backend algorithm tuning config, never
serialized into the JSONL trace or any HTTP response, so the frontend has
no business knowing about them. Excluding them isn't just tidiness — left
in, pydantic2zod can't translate GreedySelectionConfig.weights's default
(an instantiated DistanceWeights()) and silently emits invalid Zod
(`DistanceWeights.default(null)`, which would reject any valid input).
Scoping codegen to only the actual wire-protocol types avoids generating
broken schemas for models that were never part of the wire protocol.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

import pydantic2zod  # noqa: E402

OUTPUT_PATH = Path(__file__).parent.parent / "src" / "generated" / "models.ts"


class Compiler(pydantic2zod.Compiler):
    IGNORE_TYPES = {
        "src.algorithms.models.DistanceWeights",
        "src.algorithms.models.GreedySelectionConfig",
        "src.algorithms.models.SimulatedAnnealingConfig",
    }


def main() -> None:
    ts_src = Compiler().parse("src.algorithms.models").to_zod()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(ts_src)
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
