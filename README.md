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
| `rounds[]` | per-round *marginal* opponent list (`faceProb`/`beatProb`) — kept for reference |
| `tree` | the **conditional** knockout tree (handoff §6b): a recursive node per match with `condProb`, `reachProb`, `beatProb`, and its true conditional next-round opponents |

The decision tree, pie explorer, and left-panel opponents are all driven by the
**conditional `tree`** — so deeper branches show the real bracket geography (which R16
region you land in depends on *which* R32 opponent you beat), not a repeated marginal set.
Branches are pruned at **0.5% absolute probability**, which also guarantees every displayed
node is well-sampled (≥0.5%·`n_sims` runs). Deep paths for weak teams terminate early by
design — Sweden reaching the final is <0.5%, so its tree honestly stops around the QF.

Default `n_sims` is **200 000** (~75s). More sims don't make the tree *deeper* (the 0.5%
prune is a probability threshold), they make displayed percentages more *stable*.

## Rebuild

```bash
python simulate.py 200000  # writes sim_results.json (default 200k; ~75s)
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
