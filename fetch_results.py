#!/usr/bin/env python3
"""Deterministic match-result fetcher for the WC2026 simulator's daily refresh.

Fetches finished WC2026 scores from FIFA's official public API and updates
results.json in place. Like fetch_elo.py, it never invents or randomizes
numbers: it reads the live source, maps FIFA country names to our 48 canonical
keys, orients each group score to our fixture's home/away ordering, and writes
the file atomically. If it cannot fetch or parse, it raises rather than
fabricating, so a bad morning leaves yesterday's good results untouched.

Two arrays are written:
  results[]  -- played group matches (status "final"), keyed to the canonical
                fixtures in copabet_picks.MATCHES (home/away ordering preserved).
  knockout[] -- played knockout matches, each carrying the advancing `winner`
                (from the FIFA `Winner` team id, which already encodes
                extra-time / penalties). simulate.py pins these so eliminated
                teams stop being re-simulated as possible champions.

Entry points:
    fetch_live() -> list[dict]
        Best-effort fetch + parse of finished matches (stdlib only).
    apply(matches, updated=None) -> dict
        Split into group/knockout, validate, write results.json.

CLI:
    python fetch_results.py          fetch live, apply, print a diff of new finals
    python fetch_results.py --check  validate the current results.json shape

Pure stdlib only (json, urllib, datetime, argparse, os).
"""

import argparse
import datetime
import json
import os
import urllib.request

from copabet_picks import MATCHES

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS_FILE = os.path.join(HERE, "results.json")

# FIFA public API: competition 17 = FIFA World Cup, season 285023 = 2026.
# One call returns all 104 matches (group + every knockout round).
API_URL = (
    "https://api.fifa.com/api/v3/calendar/matches"
    "?idCompetition=17&idSeason=285023&count=200&language=en"
)

# A match is considered played/final at this status with non-null scores.
STATUS_FINISHED = 0

# FIFA stage descriptions -> our coarse round label. "First Stage" is the group
# stage; everything else is a knockout round we pin by team pair in simulate.py.
GROUP_STAGE = "First Stage"
KO_ROUND = {
    "Round of 32": "R32",
    "Round of 16": "R16",
    "Quarter-final": "QF",
    "Quarter-finals": "QF",
    "Semi-final": "SF",
    "Semi-finals": "SF",
    "Play-off for third place": "3P",
    "Final": "F",
}

# Map FIFA country names -> our canonical 48 keys (from copabet_picks.MATCHES).
# Only divergent spellings need an entry; everything else maps through identity.
NAME_MAP = {
    "Bosnia and Herzegovina": "Bosnia & Herzegovina",
    "Cabo Verde": "Cape Verde",
    "Congo DR": "D.R. Congo",
    "Curaçao": "Curacao",
    "Czechia": "Czech Republic",
    "Côte d'Ivoire": "Ivory Coast",
    "IR Iran": "Iran",
    "Korea Republic": "South Korea",
    "Türkiye": "Turkey",
}

# Canonical team set + the exact group fixtures (home/away ordering is the
# contract simulate.py reads). Source of truth: the fixtures themselves.
CANON = {t for _, _, h, a, *_ in MATCHES for t in (h, a)}
GROUP_FIXTURES = [(g, md, h, a) for g, md, h, a, *_ in MATCHES]


def _map_name(fifa_name):
    """Map a FIFA country name to our canonical key (or identity)."""
    name = (fifa_name or "").strip()
    return NAME_MAP.get(name, name)


def _team(side):
    """(canonical name, FIFA team id) for a match's Home/Away block."""
    side = side or {}
    nm = (side.get("TeamName") or [{}])[0].get("Description")
    return _map_name(nm), side.get("IdTeam")


def fetch_live(url=API_URL, timeout=30):
    """Fetch + parse finished WC2026 matches from the FIFA API.

    Returns a list of normalized dicts (one per finished match):
        {stage, round, group, home, away, score_home, score_away,
         winner, date}
    where `home`/`away` are the FIFA home/away teams (canonical names),
    `winner` is the canonical name of the advancing team (knockouts) or None
    (group/draws), and `date` is YYYY-MM-DD.

    Raises RuntimeError on fetch/parse failure or if it ends up with zero
    finished matches (so callers never silently wipe results.json).
    """
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (wc2026-simulator daily refresh)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        doc = json.loads(raw)
    except Exception as exc:  # network / HTTP / decode / JSON failures
        raise RuntimeError("fetch_live: could not fetch %s (%s)" % (url, exc)) from exc

    rows = doc.get("Results")
    if not isinstance(rows, list) or not rows:
        raise RuntimeError(
            "fetch_live: no match list in API response; format may have changed. "
            "Not fabricating values."
        )

    out = []
    for m in rows:
        if m.get("MatchStatus") != STATUS_FINISHED:
            continue
        sh, sa = m.get("HomeTeamScore"), m.get("AwayTeamScore")
        if sh is None or sa is None:
            continue  # not actually completed; never record a partial score
        (hn, hid), (an, aid) = _team(m.get("Home")), _team(m.get("Away"))
        if not hn or not an:
            continue  # placeholder/TBD fixture
        stage = (m.get("StageName") or [{}])[0].get("Description", "")
        grp = (m.get("GroupName") or [{}])[0].get("Description", "") if m.get("GroupName") else ""
        date = (m.get("Date") or "")[:10]

        winner = None
        wid = m.get("Winner")
        if wid is not None:
            if wid == hid:
                winner = hn
            elif wid == aid:
                winner = an

        out.append({
            "stage": stage,
            "round": KO_ROUND.get(stage, "GROUP" if stage == GROUP_STAGE else stage),
            "group": grp,
            "home": hn, "away": an,
            "score_home": int(sh), "score_away": int(sa),
            "winner": winner,
            "date": date,
        })

    if not out:
        raise RuntimeError(
            "fetch_live: parsed zero finished matches from the FIFA API; format "
            "may have changed. Not fabricating values."
        )
    return out


def _split(matches):
    """Turn raw fetched matches into (group_results, knockout_results).

    group_results follow the canonical fixture home/away ordering and only
    cover First Stage games; knockout_results carry the advancing winner.
    Raises if a played team is unknown (unmapped name) so we never write
    half-mapped data.
    """
    # index finished matches by the unordered team pair
    by_pair = {}
    for m in matches:
        # every played team must be one of our 48
        for t in (m["home"], m["away"]):
            if t not in CANON:
                raise RuntimeError(
                    "unmapped team name from FIFA API: %r (add it to NAME_MAP)" % t
                )
        by_pair.setdefault(frozenset((m["home"], m["away"])), []).append(m)

    group_results = []
    for g, md, h, a in GROUP_FIXTURES:
        cands = [m for m in by_pair.get(frozenset((h, a)), []) if m["stage"] == GROUP_STAGE]
        if not cands:
            continue  # not played yet
        if len(cands) > 1:
            raise RuntimeError("ambiguous group match for fixture %s v %s" % (h, a))
        m = cands[0]
        # orient the score to OUR home team h
        if m["home"] == h:
            score_home, score_away = m["score_home"], m["score_away"]
        else:
            score_home, score_away = m["score_away"], m["score_home"]
        group_results.append({
            "home": h, "away": a, "status": "final",
            "score_home": score_home, "score_away": score_away, "date": m["date"],
        })

    knockout_results = []
    for m in matches:
        if m["stage"] == GROUP_STAGE:
            continue
        knockout_results.append({
            "round": m["round"], "home": m["home"], "away": m["away"],
            "score_home": m["score_home"], "score_away": m["score_away"],
            "winner": m["winner"], "date": m["date"],
        })

    group_results.sort(key=lambda r: (r["date"], r["home"], r["away"]))
    knockout_results.sort(key=lambda r: (r["date"], r["home"], r["away"]))
    return group_results, knockout_results


# Order of keys when writing a results row, for a stable, readable file.
_RESULT_KEYS = ["home", "away", "status", "score_home", "score_away", "date"]
_KO_KEYS = ["round", "home", "away", "score_home", "score_away", "winner", "date"]


def _row(d, keys):
    """Compact one-line JSON object with a fixed key order."""
    return json.dumps({k: d[k] for k in keys}, ensure_ascii=False)


def _array_block(name, rows, keys, trailing_comma):
    """Render a JSON array, one object per line; inline `[]` when empty."""
    tail = "," if trailing_comma else ""
    if not rows:
        return ["  %s: []%s" % (json.dumps(name), tail)]
    out = ["  %s: [" % json.dumps(name)]
    for i, r in enumerate(rows):
        sep = "," if i < len(rows) - 1 else ""
        out.append("    " + _row(r, keys) + sep)
    out.append("  ]" + tail)
    return out


def _write(group_results, knockout_results, updated):
    """Write results.json atomically, one match per line (matches prior style)."""
    comment = (
        "Final scores for played WC2026 matches. results[] = group stage keyed by "
        "fixture home/away; knockout[] carries the advancing winner. Auto-updated "
        "daily from the FIFA public API (api.fifa.com) by fetch_results.py."
    )
    lines = ["{"]
    lines.append("  \"_comment\": %s," % json.dumps(comment, ensure_ascii=False))
    lines.append("  \"updated\": %s," % json.dumps(updated))
    lines += _array_block("results", group_results, _RESULT_KEYS, trailing_comma=True)
    lines += _array_block("knockout", knockout_results, _KO_KEYS, trailing_comma=False)
    lines.append("}")
    blob = "\n".join(lines) + "\n"

    tmp = RESULTS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(blob)
    os.replace(tmp, RESULTS_FILE)


def apply(matches, updated=None):
    """Validate fetched matches and write results.json. Returns a summary dict."""
    group_results, knockout_results = _split(matches)
    if not group_results:
        raise RuntimeError("apply: zero group results parsed; refusing to write.")
    if updated is None:
        updated = datetime.date.today().isoformat()
    _write(group_results, knockout_results, updated)
    return {"group": group_results, "knockout": knockout_results, "updated": updated}


def _load_current():
    with open(RESULTS_FILE, encoding="utf-8") as f:
        return json.load(f)


def check_file():
    """Validate the current results.json shape. Returns (n_group, n_ko)."""
    data = _load_current()
    res = data.get("results")
    if not isinstance(res, list):
        raise ValueError("results.json: missing or invalid 'results' array")
    for r in res:
        for k in ("home", "away", "status", "score_home", "score_away"):
            if k not in r:
                raise ValueError("results.json: row missing %r: %r" % (k, r))
        for t in (r["home"], r["away"]):
            if t not in CANON:
                raise ValueError("results.json: unknown team %r" % t)
    ko = data.get("knockout", [])
    if not isinstance(ko, list):
        raise ValueError("results.json: 'knockout' must be an array if present")
    return len(res), len(ko)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true",
        help="only validate the current results.json shape",
    )
    args = parser.parse_args(argv)

    if args.check:
        ng, nk = check_file()
        print("OK: results.json has %d group result(s), %d knockout result(s)." % (ng, nk))
        return 0

    # snapshot current group scores for a diff
    old = {}
    if os.path.exists(RESULTS_FILE):
        for r in _load_current().get("results", []):
            old[(r["home"], r["away"])] = (r["score_home"], r["score_away"])

    summary = apply(fetch_live())
    new = {(r["home"], r["away"]): (r["score_home"], r["score_away"])
           for r in summary["group"]}

    added = [k for k in new if k not in old]
    changed = [k for k in new if k in old and old[k] != new[k]]
    print("results.json updated (%s): %d group, %d knockout."
          % (summary["updated"], len(summary["group"]), len(summary["knockout"])))
    if added:
        print("  + %d new final(s):" % len(added))
        for h, a in sorted(added, key=lambda k: k):
            print("      %s %d-%d %s" % (h, new[(h, a)][0], new[(h, a)][1], a))
    if changed:
        print("  ! %d corrected score(s):" % len(changed))
        for h, a in changed:
            print("      %s %s -> %s %s" % (h, old[(h, a)], new[(h, a)], a))
    if not added and not changed:
        print("  no group-score changes.")
    if summary["knockout"]:
        print("  knockout pinned: " + ", ".join(
            "%s>%s" % (k["round"], k["winner"]) for k in summary["knockout"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
