"""Verification suite for the WC2026 simulator. Run: python verify_sim.py"""

import json
import os

import numpy as np

import bracket as bk
import simulate as sim

DIR = os.path.dirname(os.path.abspath(__file__))
ok = lambda msg: print(f"  PASS  {msg}")


def test_calibration():
    print("[1] Calibration sanity")
    B, T, mae = sim.calibrate()
    sim.B, sim.T = B, T
    print(f"      B={B}  T={T}  MAE={mae:.4f}")
    assert mae < 0.07, f"calibration MAE too high: {mae}"
    assert 150 < B < 600 and 2.0 < T < 3.2, "fit hit a grid boundary"

    from copabet_picks import devig
    spots = [("Germany", "Curacao"), ("South Korea", "Czech Republic")]
    for g, md, h, a, oh, od, oa in sim.MATCHES:
        if (h, a) in spots:
            ph, pd, pa = devig(oh, od, oa)
            dr = sim.dr_of(h, a)
            mh, mdpd, ma = sim._outcome_probs(max(.15, (T + dr/B)/2),
                                              max(.15, (T - dr/B)/2))
            print(f"      {h} v {a}: model H/D/A "
                  f"{mh:.2f}/{mdpd:.2f}/{ma:.2f}  market {ph:.2f}/{pd:.2f}/{pa:.2f}")
    ok("calibration within tolerance, not on boundary")


def _results_from(letter, scores):
    """scores: list of (home, away, sh, sa) -> pass straight to _rank_group."""
    return [(h, a, sh, sa) for h, a, sh, sa in scores]


def test_tiebreakers():
    print("[2] Tiebreaker unit tests")
    rng = np.random.default_rng(0)
    a, b, c, d = bk.GROUPS["A"]   # 4 concrete team names

    # (i) head-to-head decides when overall pts/GD/GF are identical.
    #     a & b both 4 pts, GD 0, GF 2; a beat b 1-0.
    res = [(a, b, 1, 0), (a, c, 0, 1), (a, d, 1, 1),
           (b, c, 1, 0), (b, d, 1, 1), (c, d, 2, 0)]
    order, _ = sim._rank_group("A", res, rng)
    assert order.index(a) < order.index(b), f"H2H failed: {order}"
    ok("head-to-head beats equal overall GD/GF")

    # (ii) overall GD decides when points equal and H2H is a draw.
    res = [(a, b, 1, 1), (a, c, 3, 0), (a, d, 0, 1),
           (b, c, 1, 0), (b, d, 0, 1), (c, d, 0, 0)]
    order, st = sim._rank_group("A", res, rng)
    assert st[a]["gd"] > st[b]["gd"]
    assert order.index(a) < order.index(b), f"overall-GD failed: {order}"
    ok("overall goal difference breaks a head-to-head draw")

    # (iii) overall GF decides when points and GD equal (H2H drawn).
    #   a: D a-b 2-2, W a-c 3-1, L a-d 1-2  -> 4 pts, GD 1, GF 6
    #   b: D a-b 2-2, W b-c 2-0, L b-d 0-1  -> 4 pts, GD 1, GF 4
    res = [(a, b, 2, 2), (a, c, 3, 1), (a, d, 1, 2),
           (b, c, 2, 0), (b, d, 0, 1), (c, d, 0, 0)]
    order, st = sim._rank_group("A", res, rng)
    assert st[a]["gd"] == st[b]["gd"] and st[a]["gf"] > st[b]["gf"]
    assert order.index(a) < order.index(b), f"overall-GF failed: {order}"
    ok("overall goals scored breaks a GD tie")


def test_bracket_integrity():
    print("[3] Bracket integrity")
    # (i) the third-place table is a bijection for every one of the 495 combos.
    for key, assign in bk.COMBINATIONS.items():
        assert sorted(assign) == sorted(key), f"combo {key} not a bijection: {assign}"
    ok("all 495 third-place combinations assign each qualifying group exactly once")

    # (ii) R32 references every group winner & runner-up once, and 8 third slots.
    w, r, t = [], [], []
    for n in range(73, 89):
        for tok in bk.KO_MATCHES[n]:
            if tok[0] == "W" and tok[1] in bk.GROUPS: w.append(tok[1])
            elif tok[0] == "R" and tok[1] in bk.GROUPS: r.append(tok[1])
            elif tok[0] == "T": t.append(int(tok[1:]))
    assert sorted(w) == bk.GROUP_LETTERS, w
    assert sorted(r) == bk.GROUP_LETTERS, r
    assert sorted(t) == list(range(8)), t
    ok("R32 uses all 12 winners, all 12 runners-up, and third-slots 0..7 once each")

    # (iii) full sim never places a team in the bracket twice.
    rng = np.random.default_rng(1)
    sim.B, sim.T, _ = sim.calibrate()
    for _ in range(200):
        winners, runners, champ, quals, *_ = sim.simulate_once(rng)
        assert len(quals) == 32, f"expected 32 qualifiers, got {len(quals)}"
    ok("200 simulated brackets each yield exactly 32 distinct qualifiers")


def test_probability_invariants(n=4000):
    print(f"[4] Probability invariants  ({n} sims)")
    sim.B, sim.T, _ = sim.calibrate()
    out = sim.run(n, seed=3)
    # exact expected sums (teams reaching each round, summed over all teams)
    exp = {"winner": 1, "final": 2, "sf": 4, "qf": 8, "r16": 16,
           "advance": 32, "win_group": 12, "runner_up": 12}
    for k, e in exp.items():
        s = sum(out[t][k] for t in out)
        assert abs(s - e) < 0.01, f"sum({k})={s:.3f}, expected {e}"
    ok("round-reach probabilities sum to 1/2/4/8/16/32 and 12/12 group slots")

    for t, d in out.items():
        seq = [d["advance"], d["r16"], d["qf"], d["sf"], d["final"], d["winner"]]
        assert all(seq[i] >= seq[i+1] - 1e-9 for i in range(len(seq)-1)), \
            f"{t} not monotonic: {seq}"
    ok("every team's round-reach chain is monotonically non-increasing")

    # Strong teams should lead the title odds — but only among teams still
    # alive (pinned knockout losses zero out eliminated favourites, so no
    # hardcoded names here). Guard: every top-5 favourite sits in the top-10
    # Elo of the alive teams, i.e. the model never inverts strength.
    alive = [t for t in out if out[t]["winner"] > 0]
    top = sorted(alive, key=lambda t: -out[t]["winner"])[:5]
    elo_top = set(sorted(alive, key=lambda t: -sim.ELO[t])[:10])
    bad = [t for t in top if t not in elo_top]
    assert not bad, f"weak team(s) lead the title odds: {bad} (top5={top})"
    ok(f"strong teams lead the title odds: {top}")

    for host in bk.HOSTS:
        assert out[host]["advance"] > 0.5, f"{host} advance only {out[host]['advance']}"
    ok("all three hosts advance with high probability")


if __name__ == "__main__":
    test_calibration()
    test_tiebreakers()
    test_bracket_integrity()
    test_probability_invariants()
    print("\nAll verification checks passed.")
