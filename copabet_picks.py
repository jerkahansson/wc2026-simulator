"""
Copabet World Cup 2026 group-stage pick optimizer.

Scoring (Copabet): each group match is worth 100 pts for a correct 1X2 pick.
Points decay LINEARLY with how many people in your league also got it right:
    100 pts if you're the only one correct  ->  10 pts if everyone is correct.
Taking the expectation over the crowd, the expected points for picking outcome o is:

    E[pts | pick o] = 100 * p_o * (1 - 0.9 * q_o)

  p_o = TRUE probability of outcome o   (from de-vigged market odds)
  q_o = fraction of the LEAGUE that picks outcome o   (the crowd)

The edge: pick the outcome that maximizes p_o * (1 - 0.9*q_o), NOT the most
likely outcome. Low-q correct picks (draws especially) pay up to 10x more.

This script: de-vigs the scraped odds -> models the crowd q -> ranks each pick.

Odds source: OddsPortal consensus 1X2, decimal, scraped 2026-06-09.
Re-run with fresh odds by editing MATCHES below (or re-scraping).
"""

import csv

# ---------------------------------------------------------------------------
# TUNABLE CROWD MODEL
# ---------------------------------------------------------------------------
# The ONE bias we're most confident about: the crowd under-picks draws (the
# "orphan outcome" - same fat payoff, zero emotional appeal). draw_damp scales
# the crowd's draw share DOWN relative to the true draw probability.
#   lower  = crowd avoids draws more  -> bigger draw edge   (soft / friend pool)
#   higher = crowd is sharper on draws -> smaller edge       (sharp / work pool)
#
# We stay deliberately NEUTRAL on home/away (gamma=1.0): we discussed that
# "pick the favorite" and "romance the underdog payoff" are competing forces
# that roughly cancel, and we're not confident which dominates. Draw aversion
# is the robust, lopsided bias - so that's the only lever turned on by default.

PROFILES = {
    "friends": dict(draw_damp=0.40, gamma=1.00, sweden_boost=2.0),  # 10 casuals, softer
    "work":    dict(draw_damp=0.62, gamma=1.00, sweden_boost=1.5),  # ~20 quant-ish analysts, sharper
    # Minimax-regret choice from sweep.py: worst-case loss ~34 pts (~2% of card)
    # across the whole plausible draw_damp range 0.35-0.75. Use when the pool's
    # actual draw behavior is unknown - which it is, pre-tournament.
    "mid":     dict(draw_damp=0.50, gamma=1.00, sweden_boost=1.75),
}

SWEDEN = "Sweden"          # over-picked by a Swedish pool (hype after the playoff run)
GROUP_MATCH_VALUE = 100    # Copabet group-stage match value

# ---------------------------------------------------------------------------
# DATA: all 72 group matches  (group, matchday, home, away, odd_H, odd_D, odd_A)
# ---------------------------------------------------------------------------
MATCHES = [
    # Group A
    ("A", 1, "Mexico", "South Africa", 1.42, 4.55, 9.50),
    ("A", 1, "South Korea", "Czech Republic", 2.68, 3.20, 2.92),
    ("A", 2, "Mexico", "South Korea", 1.88, 3.55, 4.90),
    ("A", 2, "Czech Republic", "South Africa", 2.02, 3.35, 4.25),
    ("A", 3, "Czech Republic", "Mexico", 4.50, 3.50, 1.87),
    ("A", 3, "South Africa", "South Korea", 3.97, 3.40, 2.08),
    # Group B
    ("B", 1, "Qatar", "Switzerland", 15.00, 6.60, 1.27),
    ("B", 1, "Canada", "Bosnia & Herzegovina", 1.82, 3.80, 4.90),
    ("B", 2, "Switzerland", "Bosnia & Herzegovina", 1.68, 4.00, 6.25),
    ("B", 2, "Canada", "Qatar", 1.34, 5.00, 12.50),
    ("B", 3, "Bosnia & Herzegovina", "Qatar", 1.58, 4.00, 6.25),
    ("B", 3, "Switzerland", "Canada", 2.18, 3.40, 3.80),
    # Group C  (letters C/D were swapped vs the official draw; corrected)
    ("C", 1, "Brazil", "Morocco", 1.70, 3.85, 5.60),
    ("C", 1, "Haiti", "Scotland", 6.50, 4.75, 1.55),
    ("C", 2, "Scotland", "Morocco", 4.25, 3.35, 2.02),
    ("C", 2, "Brazil", "Haiti", 1.10, 14.00, 46.00),
    ("C", 3, "Scotland", "Brazil", 8.90, 4.80, 1.47),
    ("C", 3, "Morocco", "Haiti", 1.34, 5.25, 12.00),
    # Group D
    ("D", 1, "USA", "Paraguay", 2.02, 3.45, 4.25),
    ("D", 1, "Australia", "Turkey", 5.40, 3.80, 1.75),
    ("D", 2, "USA", "Australia", 1.81, 3.90, 5.05),
    ("D", 2, "Turkey", "Paraguay", 2.30, 3.30, 3.50),
    ("D", 3, "Paraguay", "Australia", 2.23, 3.30, 3.60),
    ("D", 3, "Turkey", "USA", 2.75, 3.50, 2.63),
    # Group E
    ("E", 1, "Germany", "Curacao", 1.04, 23.00, 65.00),
    ("E", 1, "Ivory Coast", "Ecuador", 3.60, 2.90, 2.50),
    ("E", 2, "Germany", "Ivory Coast", 1.60, 4.30, 6.20),
    ("E", 2, "Ecuador", "Curacao", 1.23, 7.00, 18.50),
    ("E", 3, "Ecuador", "Germany", 4.80, 3.80, 1.77),
    ("E", 3, "Curacao", "Ivory Coast", 15.00, 6.25, 1.28),
    # Group F  (Sweden's group)
    ("F", 1, "Netherlands", "Japan", 2.08, 3.75, 3.75),
    ("F", 1, "Sweden", "Tunisia", 1.95, 3.45, 4.50),
    ("F", 2, "Netherlands", "Sweden", 1.66, 4.00, 5.55),
    ("F", 2, "Tunisia", "Japan", 5.25, 3.65, 1.80),
    ("F", 3, "Japan", "Sweden", 2.10, 3.45, 3.70),
    ("F", 3, "Tunisia", "Netherlands", 7.00, 4.40, 1.52),
    # Group G  (letters G/H were swapped vs the official draw; corrected)
    ("G", 1, "Belgium", "Egypt", 1.70, 3.90, 5.75),
    ("G", 1, "Iran", "New Zealand", 1.95, 3.40, 4.60),
    ("G", 2, "Belgium", "Iran", 1.44, 4.80, 8.50),
    ("G", 2, "New Zealand", "Egypt", 5.35, 3.76, 1.75),
    ("G", 3, "Egypt", "Iran", 2.40, 3.05, 3.60),
    ("G", 3, "New Zealand", "Belgium", 11.00, 6.00, 1.34),
    # Group H
    ("H", 1, "Spain", "Cape Verde", 1.11, 13.00, 37.00),
    ("H", 1, "Saudi Arabia", "Uruguay", 8.50, 4.50, 1.45),
    ("H", 2, "Spain", "Saudi Arabia", 1.13, 10.00, 35.00),
    ("H", 2, "Uruguay", "Cape Verde", 1.47, 4.50, 8.10),
    ("H", 3, "Cape Verde", "Saudi Arabia", 2.62, 3.50, 2.72),
    ("H", 3, "Uruguay", "Spain", 5.35, 3.90, 1.70),
    # Group I
    ("I", 1, "France", "Senegal", 1.49, 4.40, 7.70),
    ("I", 1, "Iraq", "Norway", 17.50, 7.00, 1.23),
    ("I", 2, "France", "Iraq", 1.14, 9.00, 35.00),
    ("I", 2, "Norway", "Senegal", 2.17, 3.50, 3.55),
    ("I", 3, "Senegal", "Iraq", 1.52, 4.50, 8.10),
    ("I", 3, "Norway", "France", 4.40, 3.65, 1.85),
    # Group J
    ("J", 1, "Argentina", "Algeria", 1.42, 4.75, 9.10),
    ("J", 1, "Austria", "Jordan", 1.35, 5.50, 11.00),
    ("J", 2, "Argentina", "Austria", 1.70, 3.95, 5.45),
    ("J", 2, "Jordan", "Algeria", 6.50, 4.25, 1.58),
    ("J", 3, "Jordan", "Argentina", 18.50, 6.90, 1.24),
    ("J", 3, "Algeria", "Austria", 3.69, 3.35, 2.20),
    # Group K
    ("K", 1, "Portugal", "D.R. Congo", 1.29, 5.80, 13.50),
    ("K", 1, "Uzbekistan", "Colombia", 9.00, 4.60, 1.44),
    ("K", 2, "Portugal", "Uzbekistan", 1.29, 6.20, 13.00),
    ("K", 2, "Colombia", "D.R. Congo", 1.52, 4.20, 8.30),
    ("K", 3, "Colombia", "Portugal", 3.70, 3.40, 2.15),
    ("K", 3, "D.R. Congo", "Uzbekistan", 2.38, 3.40, 3.25),
    # Group L
    ("L", 1, "England", "Croatia", 1.77, 3.80, 5.00),
    ("L", 1, "Ghana", "Panama", 2.15, 3.50, 3.70),
    ("L", 2, "England", "Ghana", 1.36, 5.30, 12.00),
    ("L", 2, "Panama", "Croatia", 7.30, 4.20, 1.55),
    ("L", 3, "Croatia", "Ghana", 1.66, 3.80, 5.80),
    ("L", 3, "Panama", "England", 10.75, 6.20, 1.33),
]


def devig(oh, od, oa):
    """Decimal odds -> true probabilities (proportional de-vig)."""
    ih, idr, ia = 1 / oh, 1 / od, 1 / oa
    s = ih + idr + ia
    return ih / s, idr / s, ia / s


def crowd_q(ph, pd, pa, home, away, cfg):
    """Estimate the league's pick shares (q_H, q_D, q_A)."""
    wh = ph ** cfg["gamma"]
    wa = pa ** cfg["gamma"]
    wd = pd * cfg["draw_damp"]              # draws are the orphan outcome
    if home == SWEDEN:
        wh *= cfg["sweden_boost"]           # Swedish pool over-picks Sweden
    if away == SWEDEN:
        wa *= cfg["sweden_boost"]
    s = wh + wd + wa
    return wh / s, wd / s, wa / s


def ev(p, q):
    return GROUP_MATCH_VALUE * p * (1 - 0.9 * q)


def analyze(cfg):
    rows = []
    for group, md, home, away, oh, od, oa in MATCHES:
        ph, pd, pa = devig(oh, od, oa)
        qh, qd, qa = crowd_q(ph, pd, pa, home, away, cfg)
        evs = {"H": ev(ph, qh), "D": ev(pd, qd), "A": ev(pa, qa)}
        pick = max(evs, key=evs.get)
        fav = max({"H": ph, "D": pd, "A": pa}.items(), key=lambda kv: kv[1])[0]
        rows.append(dict(
            group=group, md=md, home=home, away=away,
            pH=ph, pD=pd, pA=pa, qH=qh, qD=qd, qA=qa,
            evH=evs["H"], evD=evs["D"], evA=evs["A"],
            pick=pick, pick_ev=evs[pick],
            fav=fav, contrarian=(pick != fav),
        ))
    return rows


def label(code, home, away):
    return {"H": home, "D": "Draw", "A": away}[code]


def main():
    import sys
    profile = sys.argv[1] if len(sys.argv) > 1 else "friends"
    cfg = PROFILES[profile]

    rows = analyze(cfg)

    # console report
    print(f"\n=== Copabet WC2026 group picks  |  profile: {profile}  "
          f"(draw_damp={cfg['draw_damp']}, sweden_boost={cfg['sweden_boost']}) ===\n")
    hdr = f"{'Gr':<2} {'MD':<2} {'Match':<34} {'pick':<22} {'EV':>5} {'p%':>4} {'q%':>4}  flag"
    print(hdr)
    print("-" * len(hdr))
    n_draw = n_contra = 0
    total_ev = 0.0
    for r in sorted(rows, key=lambda x: (x["group"], x["md"])):
        pk = label(r["pick"], r["home"], r["away"])
        p = {"H": r["pH"], "D": r["pD"], "A": r["pA"]}[r["pick"]]
        q = {"H": r["qH"], "D": r["qD"], "A": r["qA"]}[r["pick"]]
        flag = []
        if r["pick"] == "D":
            n_draw += 1
            flag.append("DRAW")
        if r["contrarian"]:
            n_contra += 1
            flag.append("contrarian")
        if r["md"] == 3:
            flag.append("MD3*")
        total_ev += r["pick_ev"]
        match = f"{r['home']} v {r['away']}"
        print(f"{r['group']:<2} {r['md']:<2} {match:<34} {pk:<22} "
              f"{r['pick_ev']:>5.1f} {p*100:>3.0f} {q*100:>3.0f}  {' '.join(flag)}")

    print("-" * len(hdr))
    print(f"\nDraws picked:        {n_draw} / 72")
    print(f"Contrarian picks:    {n_contra} / 72   (pick != most-likely outcome)")
    print(f"Total expected pts:  {total_ev:.0f}")
    print("\n* MD3 = matchday-3 games. The 'both teams safe with a draw' boost is "
          "NOT yet modeled here\n  (needs the group Monte Carlo) - treat MD3 draws "
          "as candidates for an extra manual nudge.\n")

    # CSV output
    out = f"copabet_picks_{profile}.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["group", "matchday", "home", "away",
                    "p_H", "p_D", "p_A", "q_H", "q_D", "q_A",
                    "EV_H", "EV_D", "EV_A", "PICK", "pick_label",
                    "pick_EV", "most_likely", "contrarian"])
        for r in rows:
            w.writerow([r["group"], r["md"], r["home"], r["away"],
                        f"{r['pH']:.3f}", f"{r['pD']:.3f}", f"{r['pA']:.3f}",
                        f"{r['qH']:.3f}", f"{r['qD']:.3f}", f"{r['qA']:.3f}",
                        f"{r['evH']:.1f}", f"{r['evD']:.1f}", f"{r['evA']:.1f}",
                        r["pick"], label(r["pick"], r["home"], r["away"]),
                        f"{r['pick_ev']:.1f}", r["fav"], r["contrarian"]])
    print(f"Wrote {out}\n")


if __name__ == "__main__":
    main()
