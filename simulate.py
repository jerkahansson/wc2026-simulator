"""
WC2026 tournament Monte Carlo simulator (football-md.com style).

Method (all standard, off-the-shelf):
  1. Team strength  = World Football Elo (elo_ratings.json, from eloratings.net).
  2. Match goals    = Elo difference -> expected-goal supremacy -> Poisson scorelines.
                      dr = elo_a - elo_b + 100*(a is host) - 100*(b is host)
                      supremacy = dr / B ;  lambda = (T +/- supremacy)/2
                      B and T are calibrated ONCE against the 72 de-vigged market
                      odds in copabet_picks.MATCHES (see calibrate()).
  3. Start "as of today": played results in results.json are fixed; only the
     remaining group matches + the whole knockout bracket are simulated.
  4. Knockouts: 90-min Poisson scoreline; a draw is resolved by a shootout
     (mild Elo tilt). Bracket wiring + best-third logic live in bracket.py.
  5. Monte Carlo: replay N times, aggregate per-team round-reach frequencies.

Run:  python simulate.py [n_sims]      (default 50000)
Writes sim_results.json for sim_dashboard.py and prints a probability table.
"""

import json
import math
import os
import sys
from collections import defaultdict
from itertools import groupby

import numpy as np

from copabet_picks import MATCHES, devig
import bracket as bk

DIR = os.path.dirname(os.path.abspath(__file__))
HA = 100.0            # World Football Elo home-advantage constant
GMAX = 15             # goal grid cap for calibration probabilities
SHOOTOUT_TILT = 0.5   # 0 = pure coin flip; 1 = full Elo expectancy in shootouts

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
with open(os.path.join(DIR, "elo_ratings.json"), encoding="utf-8") as f:
    ELO = json.load(f)["ratings"]

with open(os.path.join(DIR, "results.json"), encoding="utf-8") as f:
    _resdoc = json.load(f)
_res = _resdoc["results"]
FINAL = {(r["home"], r["away"]): (r["score_home"], r["score_away"])
         for r in _res if r["status"] == "final"}
# Played knockout matches, pinned by unordered team pair -> advancing winner.
# Single-elimination => any two teams meet at most once, so the pair is a unique
# key (robust to which bracket slot they happen to meet in). Empty until the
# knockout stage starts; populated by fetch_results.py from the FIFA API.
KO_FINAL = {frozenset((r["home"], r["away"])): r["winner"]
            for r in _resdoc.get("knockout", []) if r.get("winner")}

# sanity: every team referenced in the fixtures has an Elo rating
_teams = {t for _, _, h, a, *_ in MATCHES for t in (h, a)}
_missing = _teams - set(ELO)
assert not _missing, f"teams missing from elo_ratings.json: {_missing}"
assert len(_teams) == 48, f"expected 48 teams, found {len(_teams)}"


def dr_of(a, b):
    """Elo difference for team a vs b, including host home advantage."""
    return ELO[a] - ELO[b] + HA * (a in bk.HOSTS) - HA * (b in bk.HOSTS)


# ---------------------------------------------------------------------------
# Calibration: fit (B, T) so the Elo-Poisson model reproduces the market 1X2
# ---------------------------------------------------------------------------
_FACT = np.array([math.factorial(i) for i in range(GMAX + 1)], dtype=float)


def _outcome_probs(lh, la):
    """1X2 probabilities for two independent Poisson goal counts."""
    k = np.arange(GMAX + 1)
    ph = np.exp(-lh) * lh ** k / _FACT
    pa = np.exp(-la) * la ** k / _FACT
    M = np.outer(ph, pa)                       # M[i,j] = P(home=i, away=j)
    # home win = home goals > away goals = below the diagonal
    return np.tril(M, -1).sum(), np.trace(M), np.triu(M, 1).sum()


def calibrate():
    """Grid-search (B, T) minimizing mean abs error vs de-vigged odds."""
    market = []   # (dr, pH, pD, pA)
    for g, md, h, a, oh, od, oa in MATCHES:
        ph, pd, pa = devig(oh, od, oa)
        market.append((dr_of(h, a), ph, pd, pa))

    def mae(B, T):
        err = 0.0
        for dr, ph, pd, pa in market:
            sup = dr / B
            lh = max(0.15, (T + sup) / 2); la = max(0.15, (T - sup) / 2)
            mh, mdr, ma = _outcome_probs(lh, la)
            err += abs(mh - ph) + abs(mdr - pd) + abs(ma - pa)
        return err / (3 * len(market))

    best = (None, None, 1e9)
    # coarse then fine
    for B in np.arange(150, 601, 25):
        for T in np.arange(2.0, 3.21, 0.1):
            e = mae(B, T)
            if e < best[2]:
                best = (B, T, e)
    B0, T0, _ = best
    for B in np.arange(B0 - 25, B0 + 26, 5):
        for T in np.arange(T0 - 0.1, T0 + 0.11, 0.02):
            e = mae(B, T)
            if e < best[2]:
                best = (round(float(B), 2), round(float(T), 3), e)
    return best  # (B, T, mae)


# ---------------------------------------------------------------------------
# One simulation
# ---------------------------------------------------------------------------
# Remaining (unplayed) group fixtures, grouped by group letter.
REMAINING = []   # (idx, group, home, away)
GROUP_FIXTURES = defaultdict(list)   # letter -> list of (home, away, played_score_or_None)
for g, md, h, a, *_ in MATCHES:
    score = FINAL.get((h, a))
    GROUP_FIXTURES[g].append((h, a, score))
    if score is None:
        REMAINING.append((len(REMAINING), g, h, a))


def _rank_group(letter, results, rng):
    """Return teams ordered 1st..4th under FIFA 2026 tiebreakers, plus stats.

    Order: overall points -> head-to-head (pts, GD, GF among tied) ->
    overall GD -> overall GF -> FIFA-ranking proxy (Elo) -> drawing of lots.
    (Fair-play/cards are not modelled; Elo stands in for the FIFA ranking.)
    """
    teams = bk.GROUPS[letter]
    st = {t: {"pts": 0, "gf": 0, "ga": 0} for t in teams}
    for h, a, sh, sa in results:
        st[h]["gf"] += sh; st[h]["ga"] += sa
        st[a]["gf"] += sa; st[a]["ga"] += sh
        if sh > sa:   st[h]["pts"] += 3
        elif sa > sh: st[a]["pts"] += 3
        else:         st[h]["pts"] += 1; st[a]["pts"] += 1
    for t in teams:
        st[t]["gd"] = st[t]["gf"] - st[t]["ga"]

    ordered = []
    for _, grp in groupby(sorted(teams, key=lambda t: -st[t]["pts"]),
                          key=lambda t: -st[t]["pts"]):
        grp = list(grp)
        if len(grp) > 1:
            S = set(grp)
            h2h = {t: {"pts": 0, "gd": 0, "gf": 0} for t in grp}
            for h, a, sh, sa in results:
                if h in S and a in S:
                    h2h[h]["gf"] += sh; h2h[h]["gd"] += sh - sa
                    h2h[a]["gf"] += sa; h2h[a]["gd"] += sa - sh
                    if sh > sa:   h2h[h]["pts"] += 3
                    elif sa > sh: h2h[a]["pts"] += 3
                    else:         h2h[h]["pts"] += 1; h2h[a]["pts"] += 1
            grp.sort(key=lambda t: (h2h[t]["pts"], h2h[t]["gd"], h2h[t]["gf"],
                                    st[t]["gd"], st[t]["gf"], ELO[t], rng.random()),
                     reverse=True)
        ordered.extend(grp)
    return ordered, st


def _play_ko(a, b, rng):
    """Knockout match -> (winner, loser). 90-min Poisson; draw -> shootout."""
    dr = dr_of(a, b)
    sup = dr / B
    lh = max(0.15, (T + sup) / 2); la = max(0.15, (T - sup) / 2)
    ga, gb = rng.poisson(lh), rng.poisson(la)
    if ga > gb:
        return a, b
    if gb > ga:
        return b, a
    we = 1.0 / (1.0 + 10 ** (-dr / 400))          # Elo win expectancy
    pa = 0.5 + SHOOTOUT_TILT * (we - 0.5)
    return (a, b) if rng.random() < pa else (b, a)


def simulate_once(rng):
    """Play out the remainder of the tournament once.

    Returns (winners, runners, champ, r16, qf, sf, finalists) where the round
    sets contain every team that *reached* that round.
    """
    # --- group stage: fixed scores + sampled remaining ---
    lam = np.array([( (T + dr_of(h, a) / B) / 2, (T - dr_of(h, a) / B) / 2 )
                    for _, _, h, a in REMAINING])
    gh = rng.poisson(np.maximum(0.15, lam[:, 0]))
    ga = rng.poisson(np.maximum(0.15, lam[:, 1]))
    sampled = {}
    for (idx, g, h, a) in REMAINING:
        sampled[(h, a)] = (int(gh[idx]), int(ga[idx]))

    winners, runners = {}, {}
    thirds = []   # (letter, team, stats)
    for letter in bk.GROUP_LETTERS:
        results = []
        for (h, a, score) in GROUP_FIXTURES[letter]:
            sh, sa = score if score is not None else sampled[(h, a)]
            results.append((h, a, sh, sa))
        order, st = _rank_group(letter, results, rng)
        winners[letter] = order[0]
        runners[letter] = order[1]
        thirds.append((letter, order[2], st[order[2]]))

    # --- best 8 third-placed teams ---
    thirds.sort(key=lambda x: (x[2]["pts"], x[2]["gd"], x[2]["gf"],
                               ELO[x[1]], rng.random()), reverse=True)
    best8 = thirds[:8]
    qual_letters = sorted(l for l, _, _ in best8)
    third_team = {l: t for l, t, _ in best8}
    assign = bk.third_place_assignment(qual_letters)   # group letter per winner slot

    def third_for_slot(i):
        return third_team[assign[i]]

    # --- knockouts ---
    win, lose = {}, {}

    def resolve(tok):
        if tok[0] == "W" and tok[1] in bk.GROUPS:
            return winners[tok[1]]
        if tok[0] == "R" and tok[1] in bk.GROUPS:
            return runners[tok[1]]
        if tok[0] == "T":
            return third_for_slot(int(tok[1:]))
        if tok[-1] == "W":
            return win[int(tok[:-1])]
        if tok[-1] == "L":
            return lose[int(tok[:-1])]
        raise ValueError(tok)

    matchup = {}   # match_no -> (teamA, teamB)
    for n in sorted(bk.KO_MATCHES):
        sa, sb = bk.KO_MATCHES[n]
        ta, tb = resolve(sa), resolve(sb)
        matchup[n] = (ta, tb)
        pinned = KO_FINAL.get(frozenset((ta, tb)))
        if pinned in (ta, tb):                 # real played result -> fix it
            w, l = pinned, (tb if pinned == ta else ta)
        else:                                  # not played yet -> simulate
            w, l = _play_ko(ta, tb, rng)
        win[n], lose[n] = w, l

    qualifiers = (set(winners.values()) | set(runners.values())
                  | set(third_team.values()))            # the 32 R32 teams
    r16 = {win[n] for n in range(73, 89)}
    qf = {win[n] for n in range(89, 97)}
    sf = {win[n] for n in range(97, 101)}
    finalists = {win[101], win[102]}
    champ = win[104]

    # Per-team bracket path: for each round a team reached, who it faced and
    # whether it won. The 3rd-place play-off (match 103) is not a "round reached".
    paths = defaultdict(list)   # team -> [(round_label, opponent, won_bool)]
    for n, (ta, tb) in matchup.items():
        rl = bk.ROUND_OF[n]
        if rl == "3P":
            continue
        lab = "Final" if rl == "F" else rl       # R32/R16/QF/SF/Final
        w = win[n]
        paths[ta].append((lab, tb, ta == w))
        paths[tb].append((lab, ta, tb == w))

    return winners, runners, champ, qualifiers, r16, qf, sf, finalists, paths


# ---------------------------------------------------------------------------
# Monte Carlo driver
# ---------------------------------------------------------------------------
ROUND_SEQ = ["R32", "R16", "QF", "SF", "Final"]   # knockout rounds, in order


def run(n_sims, seed=7, with_opponents=False):
    """Monte-Carlo driver.

    Returns the flat per-team milestone table `out`. If `with_opponents` is
    True, also returns an `agg` dict carrying, per team and per knockout round,
    the empirical opponent-faced distribution and win counts — the extra data
    the path-explorer dashboard needs (see DATA CONTRACT / handoff §6).
    """
    rng = np.random.default_rng(seed)
    teams = sorted(_teams)
    c = {t: defaultdict(int) for t in teams}   # team -> milestone -> count
    # opponent aggregates (only populated when with_opponents)
    reachc = {t: defaultdict(int) for t in teams}          # round -> # sims reached
    face = {t: {r: defaultdict(int) for r in ROUND_SEQ} for t in teams}  # round -> opp -> faced
    winc = {t: {r: defaultdict(int) for r in ROUND_SEQ} for t in teams}  # round -> opp -> won
    # conditional knockout trie per team: root -> kids[oppR32] -> kids[oppR16] -> ...
    # each node {n: #sims that reached this exact path, w: #won that match, kids}.
    trie = {t: {"n": 0, "w": 0, "kids": {}} for t in teams}
    for _ in range(n_sims):
        winners, runners, champ, qualifiers, r16, qf, sf, fin, paths = simulate_once(rng)
        for letter, t in winners.items():
            c[t]["win_group"] += 1
        for letter, t in runners.items():
            c[t]["runner_up"] += 1
        for t in qualifiers:
            c[t]["advance"] += 1            # reached R32 (top-2 or best third)
        for t in r16:
            c[t]["r16"] += 1
        for t in qf:
            c[t]["qf"] += 1
        for t in sf:
            c[t]["sf"] += 1
        for t in fin:
            c[t]["final"] += 1
        c[champ]["winner"] += 1
        if with_opponents:
            for t, steps in paths.items():
                node = trie[t]                      # walk/extend the conditional trie
                for lab, opp, won in steps:          # steps are in round order R32..Final
                    reachc[t][lab] += 1
                    face[t][lab][opp] += 1
                    if won:
                        winc[t][lab][opp] += 1
                    kid = node["kids"].get(opp)
                    if kid is None:
                        kid = {"n": 0, "w": 0, "kids": {}}
                        node["kids"][opp] = kid
                    kid["n"] += 1
                    if won:
                        kid["w"] += 1
                    node = kid

    out = {}
    for t in teams:
        d = c[t]
        out[t] = {
            "elo": ELO[t],
            "win_group": d["win_group"] / n_sims,
            "runner_up": d["runner_up"] / n_sims,
            "advance":   d["advance"] / n_sims,
            "r16":       d["r16"] / n_sims,
            "qf":        d["qf"] / n_sims,
            "sf":        d["sf"] / n_sims,
            "final":     d["final"] / n_sims,
            "winner":    d["winner"] / n_sims,
        }
    if not with_opponents:
        return out
    agg = {"reachc": reachc, "face": face, "winc": winc, "trie": trie}
    return out, agg


ROUND_LABEL = {"advance": "Round of 32", "r16": "Round of 16", "qf": "Quarter-final",
               "sf": "Semi-final", "final": "Final", "winner": "Champion"}


def predicted_finish(d):
    """Most-likely finish = deepest round the team reaches with probability >= 0.5."""
    for key in ("winner", "final", "sf", "qf", "r16", "advance"):
        if d[key] >= 0.5:
            return ROUND_LABEL[key]
    return "Group stage"


def group_standings():
    """Current real group tables from played (final) results in results.json.

    Returns (standings, remaining): standings[letter] is a points-sorted list of
    {name, pld, gd, pts}; remaining[team] is that team's not-yet-played group
    opponent (or absent if the group stage is complete for them)."""
    # earliest not-yet-played matchday per group, for a "before MDn" stage label
    next_md = {}
    for g, md, h, a, *_ in MATCHES:
        if FINAL.get((h, a)) is None and (g not in next_md or md < next_md[g]):
            next_md[g] = md
    standings, remaining, stage = {}, {}, {}
    for letter in bk.GROUP_LETTERS:
        stage[letter] = f"before MD{next_md[letter]}" if letter in next_md else "group complete"
        st = {t: {"pld": 0, "gf": 0, "ga": 0, "pts": 0} for t in bk.GROUPS[letter]}
        for (h, a, score) in GROUP_FIXTURES[letter]:
            if score is None:
                remaining[h] = a
                remaining[a] = h
                continue
            sh, sa = score
            st[h]["pld"] += 1; st[a]["pld"] += 1
            st[h]["gf"] += sh; st[h]["ga"] += sa
            st[a]["gf"] += sa; st[a]["ga"] += sh
            if sh > sa:   st[h]["pts"] += 3
            elif sa > sh: st[a]["pts"] += 3
            else:         st[h]["pts"] += 1; st[a]["pts"] += 1
        for t in st:
            st[t]["gd"] = st[t]["gf"] - st[t]["ga"]
        order = sorted(bk.GROUPS[letter],
                       key=lambda t: (st[t]["pts"], st[t]["gd"], st[t]["gf"], ELO[t]),
                       reverse=True)
        standings[letter] = [{"name": t, "pld": st[t]["pld"], "gd": st[t]["gd"],
                              "pts": st[t]["pts"]} for t in order]
    return standings, remaining, stage


TREE_ROOT_MIN = 0.005    # keep an R32 opponent reached >= 0.5% of the time overall
# Max children per node, BY the node's round-depth (0=R32 .. 3=SF). We keep the
# top-K most-likely continuations by sim count with NO hard sample floor, so the
# tree branches as far as the data allows and always reaches the Final. Tapering
# (wide early, a touch narrower deep) keeps it bushy without exploding the file:
# breadth is the expensive axis (K wide ^ 5 deep x 48 teams). Thin deep branches
# are kept but flagged with "*" in the UI (few sims behind them).
TREE_KIDS_BY_DEPTH = [4, 4, 3, 3]


def build_conditional_tree(root, remaining_opp, n_sims):
    """Emit the recursive conditional knockout tree (handoff §6b) from a team's
    trie. Each node: the match (round, opponent), condProb (vs its parent),
    reachProb (absolute), beatProb (chance to win that match), and children =
    the conditional next-round opponents.

    Breadth tapers with depth (TREE_KIDS_BY_DEPTH): each node keeps its top-K
    most-likely continuations by sim count with no hard floor, so the tree stays
    bushy and every node with >=1 simulated continuation drills all the way to the
    Final — no pruning dead-ends. A branch only ends early at a node where the team
    never won that match in any sim (then there is genuinely nowhere to go)."""
    def emit(node, depth, opp, n_parent):
        n, w = node["n"], node["w"]
        out = {
            "round": ROUND_SEQ[depth],
            "opponent": opp,
            "elo": ELO[opp],
            "condProb": round(n / n_parent, 5) if n_parent else 0.0,
            "reachProb": round(n / n_sims, 5),
            "beatProb": round(w / n, 5) if n else 0.0,
            "children": [],
        }
        if depth < len(ROUND_SEQ) - 1 and n > 0:   # not the Final → may have kids
            ranked = sorted(node["kids"].items(), key=lambda kv: -kv[1]["n"])
            for o2, sub in ranked[:TREE_KIDS_BY_DEPTH[depth]]:
                out["children"].append(emit(sub, depth + 1, o2, n))
        return out

    adv = sum(s["n"] for s in root["kids"].values())
    children = []
    for opp, sub in sorted(root["kids"].items(), key=lambda kv: -kv[1]["n"]):
        if sub["n"] / n_sims >= TREE_ROOT_MIN:
            children.append(emit(sub, 0, opp, n_sims))
    return {
        "round": "GROUP",
        "opponent": remaining_opp,
        "advanceProb": round(adv / n_sims, 5),
        "children": children,
    }


def build_rich_payload(out, agg, group, n_sims):
    """Assemble the path-explorer data contract (marginal shape, handoff §6a):
    per team a reach block, real group standings, championProb/predictedFinish,
    and rounds[] of opponent face/beat distributions."""
    standings, remaining, stage = group_standings()
    reachc, face, winc, trie = agg["reachc"], agg["face"], agg["winc"], agg["trie"]
    teams = {}
    for t, d in out.items():
        letter = group[t]
        rounds = []
        for lab in ROUND_SEQ:
            rc = reachc[t][lab]
            opps = []
            if rc > 0:
                ranked = sorted(face[t][lab].items(), key=lambda kv: -kv[1])
                for opp, fc in ranked[:8]:        # top-8 opponents per round (file size)
                    opps.append({
                        "name": opp,
                        "elo": ELO[opp],
                        "faceProb": round(fc / rc, 5),          # P(face opp | reached round)
                        "beatProb": round(winc[t][lab][opp] / fc, 5) if fc else 0.0,
                    })
            rounds.append({"round": lab, "opponents": opps})
        std = [{**s, **({"self": True} if s["name"] == t else {})}
               for s in standings[letter]]
        teams[t] = {
            **out[t],
            "group": letter,
            "championProb": d["winner"],
            "predictedFinish": predicted_finish(d),
            "reach": {"advance": d["advance"], "r16": d["r16"], "qf": d["qf"],
                      "sf": d["sf"], "final": d["final"], "champion": d["winner"]},
            "groupBlock": {
                "name": f"Group {letter}",
                "stageLabel": stage[letter],
                "remainingOpponent": remaining.get(t),
                "standings": std,
            },
            "rounds": rounds,
            "tree": build_conditional_tree(trie[t], remaining.get(t), n_sims),
        }
    return teams


def main():
    global B, T
    n_sims = int(sys.argv[1]) if len(sys.argv) > 1 else 500000
    B, T, mae = calibrate()
    print(f"Calibrated: B={B}  T={T}  (1X2 mean abs error vs market = {mae:.4f})")

    out, agg = run(n_sims, with_opponents=True)
    group = {t: next(l for l in bk.GROUP_LETTERS if t in bk.GROUPS[l]) for t in out}
    payload = {
        "updated": _json_today(),
        "n_sims": n_sims,
        "calibration": {"B": B, "T": T, "mae": round(mae, 4)},
        "teams": build_rich_payload(out, agg, group, n_sims),
    }
    with open(os.path.join(DIR, "sim_results.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    rows = sorted(out.items(), key=lambda kv: -kv[1]["winner"])
    print(f"\n{'Team':<22}{'Grp':<4}{'Win%':>6}{'Final':>7}{'SF':>6}{'QF':>6}"
          f"{'R16':>6}{'Adv':>6}")
    print("-" * 63)
    for t, d in rows:
        print(f"{t:<22}{group[t]:<4}{d['winner']*100:>5.1f}{d['final']*100:>7.1f}"
              f"{d['sf']*100:>6.1f}{d['qf']*100:>6.1f}{d['r16']*100:>6.1f}"
              f"{d['advance']*100:>6.1f}")
    print(f"\nWrote sim_results.json  ({n_sims} sims)")


def _json_today():
    with open(os.path.join(DIR, "elo_ratings.json"), encoding="utf-8") as f:
        return json.load(f).get("updated", "")


if __name__ == "__main__":
    main()
