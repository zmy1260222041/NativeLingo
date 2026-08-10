#!/usr/bin/env python3
"""Stage the graded-wordlist assets for FR-20 (R-14 / G4).

Fetches the two lists whose primary sources are directly linkable, verifies that
the one behind a click-through licence agreement has been placed by hand, and
prints SHA-256 + byte count for every asset so the numbers in
``docs/reviews/2026-08-08-survival-g4-wordlist.md`` stay reproducible.

Two licences, deliberately kept apart (G4 §2.1 / §2.2):
  * CEFR-J Wordlist v1.6  -- rights-holder's own grant, attribution only.
  * Octanove C1/C2, NGSL  -- CC BY-SA 4.0.
See ``desktop/backend/assets/wordlists/ATTRIBUTION.md``.

Assets are staged **verbatim**. Per G4 §4 the ShareAlike boundary holds only
while we redistribute the data files unmodified; converting them to an in-house
format at build time would be distributing Adapted Material. Derived indices are
built at runtime and never written to disk. The files must also not be encrypted
or obfuscated (CC 4.0 "No downstream restrictions").

Usage:
  python scripts/fetch_game_wordlists.py [--dest DIR] [--check-only]
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DEST = REPO_ROOT / "desktop" / "backend" / "assets" / "wordlists"

USER_AGENT = "NativeLingo-R14-G4/1.0 (wordlist staging; see docs/reviews)"

# Citations and download links deliberately use newgeneralservicelist.COM.
# The .org domain lapsed and was re-registered as gambling-affiliate spam, yet
# the official recommended citations for NAWL and BSL still point at it. A
# Wayback snapshot confirms the old .org stated the identical CC BY-SA 4.0
# terms, so the domain move did not change the licence -- only the safe URL.
FETCHABLE = [
    {
        "name": "Octanove Vocabulary Profile C1/C2 v1.0",
        "filename": "octanove-vocabulary-profile-c1c2-1.0.csv",
        "url": (
            "https://raw.githubusercontent.com/openlanguageprofiles/"
            "olp-en-cefrj/master/octanove-vocabulary-profile-c1c2-1.0.csv"
        ),
        "licence": "CC BY-SA 4.0",
        "expected_bytes": 46462,
    },
    {
        "name": "NGSL 1.2 basic statistics",
        "filename": "NGSL_12_stats.csv",
        "url": "https://www.newgeneralservicelist.com/s/NGSL_12_stats.csv",
        "licence": "CC BY-SA 4.0",
        "expected_bytes": 62566,
    },
]

# Not fetchable: the download page requires agreeing to a 使用許諾 checkbox
# first. Both guessed direct zip URLs return HTTP 404, so this cannot be
# scripted -- a human has to click through once.
MANUAL = {
    "name": "CEFR-J Wordlist v1.6",
    "filename": "CEFRJ_wordlist_ver1.6.zip",
    "page": "https://cefr-j.org/download.html",
    "licence": "rights-holder's own grant (commercial use explicitly permitted, attribution only)",
    "alt_names": [
        "CEFR-J_Wordlist_Ver1.6.zip",
        "CEFRJ_wordlist_ver1.6.xlsx",
        "CEFR-J_Wordlist_Ver1.6.xlsx",
    ],
}

MANUAL_INSTRUCTIONS = """\
CEFR-J Wordlist v1.6 must be downloaded by hand -- this is not a script bug.

  1. Open {page}
  2. Tick the 使用許諾 (terms of use) agreement on the page.
  3. Download the Wordlist Ver.1.6 archive.
  4. Put it here, keeping the original filename:
       {dest}

Why it cannot be automated: the archive sits behind the agree-and-download step,
and both plausible direct URLs return HTTP 404. Guessing more URLs would not
help -- and fetching around a licence gate is exactly what G4 forbids.

The licence itself is fine for our use. The rights holder's own page states the
list "can be used for both research and commercial purposes with a proper
acknowledgement of the source" (Japanese original:
「適切な引用を行っていただければ研究教育および商用においても無償で利用できる」).
Attribution is the only obligation -- no ShareAlike, no NonCommercial, no
NoDerivatives. See docs/reviews/2026-08-08-survival-g4-wordlist.md §2.1.
"""


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(url: str, dest: Path) -> tuple[bool, str]:
    """Download ``url`` to ``dest``. Returns (ok, message)."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            if response.status != 200:
                return False, f"HTTP {response.status}"
            payload = response.read()
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError) as exc:
        return False, f"unreachable: {exc}"
    if not payload:
        return False, "empty response body"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(payload)
    return True, f"{len(payload):,} bytes"


def report(path: Path, expected_bytes: int | None = None) -> None:
    size = path.stat().st_size
    print(f"    bytes   {size:,}")
    print(f"    sha256  {sha256_of(path)}")
    if expected_bytes is not None and size != expected_bytes:
        # Not fatal: upstream may legitimately republish. But it means the size
        # recorded in the G4 review no longer describes this file, and G4's
        # criterion is that the size is on record.
        print(
            f"    NOTE    size differs from the G4-recorded {expected_bytes:,} bytes"
            " -- update docs/reviews/2026-08-08-survival-g4-wordlist.md §7"
        )


def locate_manual(dest_dir: Path) -> Path | None:
    for name in [MANUAL["filename"], *MANUAL["alt_names"]]:
        candidate = dest_dir / name
        if candidate.exists():
            return candidate
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--dest",
        type=Path,
        default=DEFAULT_DEST,
        help=f"asset directory (default: {DEFAULT_DEST.relative_to(REPO_ROOT)})",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="report on what is already staged; download nothing",
    )
    args = parser.parse_args(argv)

    dest_dir: Path = args.dest
    print(f"asset directory: {dest_dir}")
    print()

    missing: list[str] = []

    for spec in FETCHABLE:
        target = dest_dir / spec["filename"]
        print(f"{spec['name']}  [{spec['licence']}]")
        print(f"  {spec['filename']}")
        if target.exists():
            print("    status  already staged")
            report(target, spec["expected_bytes"])
        elif args.check_only:
            print("    status  MISSING (--check-only, not downloading)")
            missing.append(spec["filename"])
        else:
            ok, message = fetch(spec["url"], target)
            if ok:
                print(f"    status  downloaded ({message})")
                report(target, spec["expected_bytes"])
            else:
                print(f"    status  FAILED -- {message}")
                print(f"    url     {spec['url']}")
                missing.append(spec["filename"])
        print()

    print(f"{MANUAL['name']}  [{MANUAL['licence']}]")
    staged = locate_manual(dest_dir)
    if staged is not None:
        print(f"  {staged.name}")
        print("    status  staged by hand")
        report(staged)
    else:
        print("    status  MISSING -- requires a manual download")
        print()
        print(
            MANUAL_INSTRUCTIONS.format(
                page=MANUAL["page"], dest=dest_dir / MANUAL["filename"]
            )
        )
        missing.append(MANUAL["filename"])
    print()

    attribution = dest_dir / "ATTRIBUTION.md"
    if attribution.exists():
        print(f"ATTRIBUTION.md   present ({attribution.stat().st_size:,} bytes)")
    else:
        print("ATTRIBUTION.md   MISSING -- both licences require attribution")
        missing.append("ATTRIBUTION.md")

    print()
    if missing:
        print("INCOMPLETE. Still missing:")
        for name in missing:
            print(f"  - {name}")
        print()
        print(
            "G4's size/latency half cannot be measured until every asset is"
            " staged. Run scripts/game_vocab_gate.py afterwards."
        )
        return 1

    print("All wordlist assets staged. Next: scripts/game_vocab_gate.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
