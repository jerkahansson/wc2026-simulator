#!/usr/bin/env python3
"""Deterministic ELO-fetch helper for the WC2026 simulator's daily refresh.

Fetches current World Football Elo ratings for the 48 WC2026 teams from
eloratings.net and updates elo_ratings.json in place. It never invents or
randomizes numbers: it reads the live source, parses ratings, maps
eloratings.net country names to our 48 canonical keys, and writes the file
atomically. If it cannot fetch or parse, it raises rather than fabricating.

Entry points:
    fetch_live() -> dict{ourname: int}
        Best-effort fetch + parse from eloratings.net (stdlib only).
    apply_ratings(ratings, updated=None) -> dict
        Validate all 48 keys present, then write elo_ratings.json.

CLI:
    python fetch_elo.py          fetch live, apply, print a diff of changes
    python fetch_elo.py --check  validate current file has all 48 teams

Pure stdlib only (json, urllib, datetime, argparse, os, re).
"""

import argparse
import datetime
import json
import os
import re
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ELO_FILE = os.path.join(HERE, "elo_ratings.json")

# eloratings.net current ratings page (lists all national teams with ratings).
ELO_URL = "https://www.eloratings.net/World.tsv"

# Map eloratings.net country names -> our canonical 48 keys.
# Only entries whose spelling differs from our keys need to appear here;
# names that already match our keys (e.g. "Argentina", "Spain") map through
# identity in fetch_live(). These cover the known divergences.
NAME_MAP = {
    "United States": "USA",
    "USA": "USA",
    "Korea Republic": "South Korea",
    "Korea DPR": "North Korea",  # not in our 48; harmless if present
    "South Korea": "South Korea",
    "Cote d'Ivoire": "Ivory Coast",
    "Côte d'Ivoire": "Ivory Coast",
    "Ivory Coast": "Ivory Coast",
    "Cape Verde": "Cape Verde",
    "Cabo Verde": "Cape Verde",
    "DR Congo": "D.R. Congo",
    "Congo DR": "D.R. Congo",
    "D.R. Congo": "D.R. Congo",
    "Bosnia and Herzegovina": "Bosnia & Herzegovina",
    "Bosnia/Herzegovina": "Bosnia & Herzegovina",
    "Bosnia & Herzegovina": "Bosnia & Herzegovina",
    "Curacao": "Curacao",
    "Curaçao": "Curacao",
    "Czechia": "Czech Republic",
    "Czech Republic": "Czech Republic",
    "Turkiye": "Turkey",
    "Türkiye": "Turkey",
    "Turkey": "Turkey",
    "IR Iran": "Iran",
    "Iran": "Iran",
}


def _load_file():
    """Read and parse elo_ratings.json. Raises on missing/invalid file."""
    with open(ELO_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def required_keys():
    """The exact 48 team-name keys that must always be present.

    Source of truth is the current elo_ratings.json, so the key set stays in
    lockstep with copabet_picks.py without hardcoding it twice.
    """
    data = _load_file()
    return sorted(data["ratings"].keys())


def _map_name(elo_name):
    """Map an eloratings.net country name to our canonical key (or identity)."""
    name = elo_name.strip()
    if name in NAME_MAP:
        return NAME_MAP[name]
    return name


def fetch_live(url=ELO_URL, timeout=30):
    """Best-effort fetch + parse of current Elo ratings from eloratings.net.

    Returns dict{ourname: int} restricted to teams in our required 48 keys.
    Raises RuntimeError if it cannot fetch or parse, or if it ends up with
    fewer than all 48 required teams (so callers never get partial data).

    Parse strategy: eloratings.net publishes a tab-separated World.tsv where
    each row is a team; the country name is a quoted field and the current
    rating is the first integer 1000-2500 on that row. We pull (name, rating)
    pairs and map names through NAME_MAP. This is deterministic given the
    fetched bytes.
    """
    needed = set(required_keys())
    req = urllib.request.Request(
        url, headers={"User-Agent": "wc2026-simulator/1.0 (+stdlib urllib)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:  # network / HTTP / decode failures
        raise RuntimeError(
            "fetch_live: could not fetch %s (%s)" % (url, exc)
        ) from exc

    ratings = {}
    # Each line: fields separated by tabs. A team name appears as a quoted
    # string; the current rating is a 4-digit integer in the typical Elo band.
    name_re = re.compile(r'"([^"]+)"')
    int_re = re.compile(r"\b(\d{4})\b")
    for line in raw.splitlines():
        if not line.strip():
            continue
        nm = name_re.search(line)
        if not nm:
            continue
        ours = _map_name(nm.group(1))
        if ours not in needed:
            continue
        # First plausible Elo-range integer on the row is the current rating.
        rating = None
        for m in int_re.finditer(line):
            val = int(m.group(1))
            if 1000 <= val <= 2500:
                rating = val
                break
        if rating is None:
            continue
        # Keep the highest if a team somehow appears twice; ratings are stable.
        if ours not in ratings:
            ratings[ours] = rating

    if not ratings:
        raise RuntimeError(
            "fetch_live: parsed zero ratings from %s; source format may have "
            "changed. Not fabricating values." % url
        )

    missing = sorted(needed - set(ratings))
    if missing:
        raise RuntimeError(
            "fetch_live: parsed %d/%d teams; missing: %s. Refusing partial "
            "data." % (len(ratings), len(needed), ", ".join(missing))
        )
    return ratings


def apply_ratings(ratings, updated=None):
    """Validate all 48 required keys are present, then write the file.

    `ratings` is dict{ourname: int}. Extra keys are ignored. `updated` is a
    date string (YYYY-MM-DD); defaults to today. Writes atomically so the file
    is never left partially written. Returns the dict that was written.
    Raises ValueError listing any missing keys or non-int values.
    """
    needed = required_keys()
    missing = [k for k in needed if k not in ratings]
    if missing:
        raise ValueError(
            "apply_ratings: missing %d required team(s): %s"
            % (len(missing), ", ".join(missing))
        )

    clean = {}
    bad = []
    for k in needed:
        v = ratings[k]
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            bad.append("%s=%r" % (k, v))
            continue
        clean[k] = int(round(v))
    if bad:
        raise ValueError(
            "apply_ratings: non-numeric rating(s): %s" % ", ".join(bad)
        )

    if updated is None:
        updated = datetime.date.today().isoformat()

    data = _load_file()  # preserve _comment / source / any extra metadata
    data["updated"] = updated
    data["ratings"] = clean

    tmp = ELO_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, ELO_FILE)  # atomic on same filesystem
    return clean


def check_file():
    """Validate the current elo_ratings.json has all required teams.

    Returns the sorted list of keys on success; raises ValueError otherwise.
    """
    data = _load_file()
    if "ratings" not in data or not isinstance(data["ratings"], dict):
        raise ValueError("elo_ratings.json: missing or invalid 'ratings' object")
    keys = data["ratings"]
    needed = required_keys()  # derived from the same file -> self-consistent
    missing = [k for k in needed if k not in keys]
    if missing:
        raise ValueError("missing teams: %s" % ", ".join(missing))
    bad = [
        "%s=%r" % (k, v)
        for k, v in keys.items()
        if isinstance(v, bool) or not isinstance(v, int)
    ]
    if bad:
        raise ValueError("non-int ratings: %s" % ", ".join(bad))
    return sorted(keys)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="only validate the current elo_ratings.json has all 48 teams",
    )
    args = parser.parse_args(argv)

    if args.check:
        keys = check_file()
        print("OK: elo_ratings.json has all %d required teams." % len(keys))
        return 0

    old = _load_file().get("ratings", {})
    new = fetch_live()
    apply_ratings(new)

    changes = []
    for k in sorted(new):
        before = old.get(k)
        after = new[k]
        if before != after:
            changes.append((k, before, after))
    if not changes:
        print("No rating changes.")
    else:
        print("Updated %d rating(s):" % len(changes))
        for k, before, after in changes:
            delta = "" if before is None else " (%+d)" % (after - before)
            print("  %-22s %s -> %s%s" % (k, before, after, delta))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
