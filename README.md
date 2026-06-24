# WC2026 Simulator — Road to the Final

An interactive Monte-Carlo visualization of a national team's probabilistic path
through the 2026 FIFA World Cup knockout bracket. For any of the 48 teams it answers,
at a glance and interactively: **how likely are they to reach each round, who might
they face, and how do those odds shift as you walk down a scenario?**

Live site: built as a single self-contained `index.html`, deployed on Cloudflare Pages.

Two views over a shared stats panel:
1. **Decision tree** — a branching probability tree (node size = probability).
2. **Pie explorer** — one radial match node you drill into, one round at a time.

## How the numbers are produced

```
elo_ratings.json ──┐
results.json ──────┼──> simulate.py ──> sim_results.json ──> build_site.py ──> index.html
copabet_picks.py ──┘     (Monte Carlo)      (data contract)      (static site)
bracket.py ────────┘
```

- **Strength** = World Football Elo (`elo_ratings.json`, from eloratings.net).
- **Match model** = Elo difference → expected-goal supremacy → Poisson scorelines.
  The `(B, T)` constants are calibrated once against de-vigged market odds.
- **As-of-today**: played results in `results.json` are fixed; only the remaining
  group games + the whole knockout bracket are simulated (`bracket.py` wires the
  official FIFA bracket and best-third logic).
- **Monte Carlo**: replay the tournament N times (default 50 000), aggregate per-team
  round-reach frequencies **and** per-round opponent distributions.

### Data contract (`sim_results.json`)

Per team (the *marginal* shape from the design handoff §6a):

| field | meaning |
|---|---|
| `reach` | P(reach advance / R16 / QF / SF / Final / champion) |
| `championProb`, `predictedFinish` | headline number + most-likely finish (deepest round with P≥0.5) |
| `groupBlock` | real current group standings (Pld/GD/Pts) + remaining group opponent |
| `rounds[]` | for R32→Final: opponents with `faceProb` (P(face them \| reached round)) and `beatProb` (empirical P(win that match)) |

`faceProb` is capped to the **top-8 opponents per round** for file size, so it can sum
slightly below 1 (the dropped tail is the long list of rare opponents). Deep-round
distributions for weak teams are inherently small-sample and noisy — that is honest MC
output, not a bug. The decision tree reuses each round's *marginal* opponent
distribution for levels below the root (the documented approximation).

## Rebuild

```bash
python simulate.py 50000   # writes sim_results.json
python build_site.py       # writes index.html
python verify_sim.py       # green-gate checks (calibration, tiebreakers, bracket, invariants)
```

## Daily refresh (during the tournament)

A scheduled agent runs daily until the final:
1. fetch newly-finished scores into `results.json`,
2. fetch current Elo from eloratings.net (`fetch_elo.py`),
3. re-run `simulate.py` + `build_site.py`,
4. commit & push to `main` → Cloudflare Pages auto-deploys.

`fetch_elo.py` is a deterministic helper: `fetch_live()` scrapes eloratings.net,
`apply_ratings()` validates all 48 team keys before writing. `--check` validates the
current file.

## Hosting

Static site on **Cloudflare Pages**, GitHub-connected, auto-deploys on push to `main`.
No build command; output directory is the repo root (`index.html` + `sim_results.json`
inlined).
