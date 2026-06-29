#!/usr/bin/env python3
"""bestiary target: the world_update parse boundary as a one-file CLI.

bestiary writes each adversarial specimen to a file and runs us as
``python world_update_parse_cli.py <path>`` (a CliTarget). We feed the
specimen bytes to the Fact-Extractor exactly as if the DM had emitted them
as a raw response, then print a STRUCTURED verdict and exit 0.

The contract under test (the malformed-LLM-output boundary, CLAUDE.md hunt
list): a hostile input must degrade to a structured refusal — never crash,
hang, over-allocate, or silently misparse garbage into an accepted payload.

We intentionally do NOT wrap ``extract()`` in a catch-all: if it raises, the
non-zero exit IS the NEVER-CRASH finding we want bestiary to surface.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# The session_id the schema validates as format:uuid — fixed so the parse is
# deterministic (DETERMINISTIC property) and the only variable is the specimen.
_FIXED_SESSION = "00000000-0000-4000-8000-000000000000"


# bestiary runs us as a subprocess from an arbitrary cwd, so put the repo root
# (this file is tests/bestiary/<name>.py → parents[2]) on the path before
# importing engine. Done at module load so an import failure surfaces as the
# harness fault it is, not a per-specimen parse crash.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from engine.agents.fact_extractor import extract  # noqa: E402


def main(argv: list[str]) -> int:
    path = Path(argv[1])
    # The real boundary is LLM *text*; decode hostile bytes the lossless way so
    # arbitrary byte specimens reach the parser as a string it must tolerate.
    text = path.read_bytes().decode("utf-8", errors="surrogateescape")

    result = extract(text, session_id=_FIXED_SESSION, turn_number=0)

    # Structured verdict on stdout — survived_check reads this. A hostile
    # specimen should yield payload_present=false (refused), not a smuggled
    # payload.
    print(
        json.dumps(
            {
                "payload_present": result.payload is not None,
                "error_count": len(result.errors),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
