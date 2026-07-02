# WC2026 Simulator — Road to the Final

An interactive Monte-Carlo visualization of a national team's probabilistic path
through the 2026 FIFA World Cup knockout bracket. For any of the 48 teams it answers,
at a glance and interactively: **how likely are they to reach each round, who might
they face, and how do those odds shift as you walk down a scenario?**

**Live: <https://road-to-the-final-wc26.pages.dev/>** (Cloudflare Pages)
Mirror: <https://jerkahansson.github.io/wc2026-simulator/> (GitHub Pages)
Built as a single self-contained `index.html`.

Three views over a shared stats panel:
1. **Decision tree** — a branching probability tree (node size = probability).
2. **Pie explorer** — one radial match node you drill into, one round at a time.
3. **Bracket** — the full 32-team knockout draw, with the selected team's matches
   highlighted and played results filled in.

## How the numbers are produced

```
elo_ratings.json ──┐
results.json ──────┼──> simulate.py ──> sim_results.json ──> build_site.py ──> index.html
copabet_picks.py ──┘     (Monte Carlo)      (data contract)      (static site)
bracket.py ────────┘
```

- **Strength** = World Football Elo (`elo_ratings.json`, from eloratings.net via
  `fetch_elo.py`).
- **Match model** = Elo difference → expected-goal supremacy → Poisson scorelines.
  The `(B, T)` constants are calibrated once against de-vigged market odds.
- **As-of-today**: played results in `results.json` are fixed. The group stage
  finished for real on 2026-06-26, so `simulate.py` computes winners/runners/best-
  thirds **once** (`_confirmed_group_outcome()`, `bracket.py` wires the official
  FIFA bracket and best-third logic) instead of resampling them every iteration —
  only the still-open part of the knockout bracket is actually simulated.
  `results.json` is auto-filled by `fetch_results.py` from the official FIFA API —
  group scores **and** played knockout winners, which are pinned so eliminated
  teams stop being re-simulated as champions.
- **Monte Carlo**: replay the knockout bracket N times (default 200 000), aggregate
  per-team round-reach frequencies **and** per-round opponent distributions.

### Data contract (`sim_results.json`)

Top-level `bracket[]`: the full 32-team knockout draw (every R32-to-Final match),
with participants filled in from the real group/knockout results wherever they're
already determined, scores/winner once a match has been played, and a `hint`
("TeamA or TeamB") for slots that aren't decided yet — powers the Bracket view.

Per team (the *marginal* shape from the design handoff §6a):

| field | meaning |
|---|---|
| `reach` | P(reach advance / R16 / QF / SF / Final / champion) |
| `championProb`, `predictedFinish` | headline number + most-likely finish (deepest round with P≥0.5) |
| `history[]` | every match the team has actually played (group + knockout), with the real score |
| `rounds[]` | per-round *marginal* opponent list (`faceProb`/`beatProb`) — kept for reference |
| `tree` | the **conditional** knockout tree (handoff §6b): a recursive node per match with `condProb`, `reachProb`, `beatProb`, and its true conditional next-round opponents |

A team's elimination status isn't a separate field — it's read off the tree: a
chain of `condProb≈1` nodes (the *only* possible next opponent) is real, decided
history, not a simulated guess. Walking it to a `beatProb≈0`/`≈1` pin (or to
`reach.advance === 0` for a group exit) tells the UI where/whether a team is out,
letting the tree/pie explorers fast-forward straight to the live frontier match.

The decision tree, pie explorer, and left-panel opponents are all driven by the
**conditional `tree`** — so deeper branches show the real bracket geography (which R16
region you land in depends on *which* R32 opponent you beat), not a repeated marginal set.
Each node keeps its top continuations by sim count, with breadth **tapering by round**
(`TREE_KIDS_BY_DEPTH = [4, 4, 3, 3]`) and **no hard sample floor** — so the tree stays
bushy and every branch with at least one simulated continuation drills all the way to the
Final (no pruning dead-ends; a branch only ends where the team never won that match in any
sim). In the UI, each node's **number and size are its probability given the parent node**;
the current root shows no number. Thin deep branches (few simulations behind them) are
flagged with a trailing `*` — their percentages are statistically noisy, indicative only.

Default `n_sims` is **200 000** (~35 sec, now that the group stage no longer needs
resampling every iteration — see above). More sims make the displayed conditional
percentages more *stable* (deeper nodes get more samples); they don't change the prune rule.

## Rebuild

```bash
python fetch_elo.py        # refresh elo_ratings.json from eloratings.net
python fetch_results.py    # refresh results.json from the FIFA API
python simulate.py 200000  # writes sim_results.json (default 200k; ~35 sec)
python build_site.py       # writes index.html
python verify_sim.py       # green-gate checks (calibration, tiebreakers, bracket, invariants)
```

## Daily refresh (automated — no human in the loop)

`.github/workflows/daily-refresh.yml` runs every morning at **06:30 UTC (08:30
Stockholm)** — and on demand from the Actions tab (**Run workflow**). It:
1. fetches current Elo (`fetch_elo.py`),
2. fetches finished scores + knockout winners (`fetch_results.py`),
3. re-runs `simulate.py 200000` + `build_site.py`,
4. runs `verify_sim.py` as a green-gate, then commits & pushes to `main`
   → Cloudflare Pages auto-deploys.

**No API keys or secrets** — both data sources are public. Each step aborts the run
*before* the commit on any failure, so a bad fetch or a failed check leaves the live
site untouched (it never publishes fabricated or partial data).

Both fetchers are deterministic helpers that validate before writing and **raise rather
than fabricate** on any fetch/parse failure:
- `fetch_elo.py` — `fetch_live()` reads eloratings.net, `apply_ratings()` validates all
  48 team keys. `--check` validates the current file.
- `fetch_results.py` — reads the official FIFA API, maps team names to the 48 canonical
  keys, orients group scores to each fixture, and records knockout winners. `--check`
  validates the current file.

## Hosting

Static site on **Cloudflare Pages**, GitHub-connected, auto-deploys on push to `main`.
No build command; output directory is the repo root (`index.html` + `sim_results.json`
inlined).
