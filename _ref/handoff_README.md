# Handoff: Sweden's Road to the Final — tournament path visualization

## Overview
An interactive web visualization of a national team's probabilistic path through the
2026 World Cup knockout bracket, driven by Monte‑Carlo tournament‑simulation output.
It answers, at a glance and interactively: *how likely is each team to reach each round,
who might they face, and how do those odds change as you walk down a scenario?*

It is the **front‑end / dashboard** half of the WC2026 Monte‑Carlo project. The
back‑end (`elo_ratings.json`, `bracket.py`, `simulate.py`) produces the probabilities;
this design consumes them. See **§6 Data contract** — it is the most important section,
because the reactive views need richer output than a flat per‑team round‑probability table.

There are **two visualization modes** plus a shared left "stats" panel:
1. **Decision tree** — a branching probability tree.
2. **Pie explorer** — a single radial node you drill into one match at a time.

## About the design files
The files in this bundle are **design references created in HTML** — a working prototype
showing the intended look, layout, and interaction behavior. They are **not production
code to copy verbatim**. The task is to **recreate this design in the target codebase's
environment** (e.g. the existing Python dashboard build that emits a self‑contained
`sim_dashboard.html`, or a React/Vue app if you prefer) using its established patterns,
and to **feed it real data from `simulate.py`** instead of the prototype's inline mock
numbers.

The prototype is authored as a "Design Component" (`.dc.html`) that runs via the bundled
`support.js` runtime. To view it: open **`Road to the Final.dc.html`** in a browser
(it loads `support.js` from the same folder). Treat its JavaScript `class Component` as a
**reference implementation of the probability/rendering logic** — the math and layout are
real and correct; only the *source of the numbers* changes in production.

## Fidelity
**High‑fidelity.** Final colors, typography, spacing, sizing rules, and interactions are
all specified below and present in the prototype. Recreate the UI faithfully, then wire
the data contract. The probability model in the prototype is an *illustrative mock*
(Elo→Poisson computed in‑browser); production replaces it with `simulate.py` output.

---

## Screens / views

The whole app is a single full‑viewport screen: a header bar, a fixed‑width left panel
(326 px), and a flexible "stage" on the right that shows the active visualization. The
stage auto‑scales to fit its container via CSS `zoom` (see §5).

### Header bar
- Left: eyebrow `FIFA WORLD CUP 26 · PATH EXPLORER` (IBM Plex Mono, 11px, letter‑spacing
  .32em, uppercase, color `#7b96bf`) above the H1 title
  `{TEAM}'S ROAD TO THE FINAL` (Archivo 900, 30px, uppercase, "FINAL" colored `#FECC00`).
- Right, in order:
  - **Team selector** — a `Team` label + native `<select>` (countries list). Sweden is the
    live demo. Selecting any other country swaps the title and shows a placeholder in the
    stage (see §4). **This is intentionally a stub — the build wires real per‑team data.**
  - **View toggle** — segmented control `Decision tree | Pie explorer`. Active segment:
    bg `#FECC00`, text `#1a1205`. Inactive: transparent, text `#cfe0f5`.
  - **Reset** button — clears the drilled path back to the root (the Japan match).

### Left panel (shared across both views)
Vertical stack, 21px gap, 22px padding, right border `1px solid rgba(140,175,225,.13)`.
1. **Headline card** — "SWEDEN WIN THE WORLD CUP", a huge `championProb` number (Archivo
   900, 54px, `#FECC00`), and a one‑line `predictedFinish` sentence. Card: 1px border
   `rgba(254,204,0,.28)`, radius 16, faint yellow gradient bg.
2. **"Chance to reach round"** — 6 horizontal bars (Advance, Round of 16, Quarter‑final,
   Semi‑final, Final, Champion). Bar track `rgba(140,175,225,.1)`, fill is a blue gradient
   `linear-gradient(90deg,#1f7fc4,#3f9bdc)`, width = probability, right‑aligned % label.
   Animates width over .6s `cubic-bezier(.34,1.3,.5,1)`.
3. **Context section — swaps with the focus round:**
   - When the focus is the **group stage**: a standings table for Group H with **real
     points** — columns `Pld | GD | Pts`, Sweden row highlighted gold. Plus a sentence:
     "Final group game: Sweden vs Japan. The result sets where Sweden lands in the bracket."
   - When the focus is a **knockout round** (because you drilled into one): the table is
     replaced by **"{Round} · possible opponents"** — a list of that round's candidate
     opponents, each with `face {%}` (chance of meeting them) and `beat {%}` (Sweden's win
     prob), color dot per team. ← This is the "replace the group with the round's
     opponents" behavior requested by the client.
4. **"Path so far"** — breadcrumb chips of the currently‑drilled path (each clickable to
   jump back to that level); active chip gold. Below it, a line giving the probability of
   the exact run traced so far (or a hint to start exploring).

### View A — Decision tree
A left‑to‑right branching tree of **match nodes** (circles).
- **Root** (far left, x≈100, vertically centered) = the current focus match; starts as the
  group decider "vs Japan", gold ring (`2.5px solid #FECC00`), Sweden blue fill.
- **Children** fan out by column (column width 475px). Each child is a possible opponent in
  the next round. Up to **2 generations** are shown at once (root → R32 → R16 for the base
  root); go deeper by clicking (re‑root, see Interactions).
- **Node size = probability.** Radius `= max(20, 18 + 44·sqrt(p))` where `p` is the node's
  probability *conditional on the current root*. The root is `p = 1`.
- **Node fill = opponent identity** (each team has a fixed color; see §Design tokens →
  team colors), as a radial gradient `radial-gradient(circle at 38% 30%, rgba(255,255,255,.34), {teamColor} 72%)`.
  (Color encodes *who*, not probability — probability is encoded by size only.)
- **Node text:** round tag (R32/R16/QF/SF/FINAL), "vs {Opponent}", and the conditional %.
  Font sizes scale with node radius.
- **Edges:** thin connectors, width `= max(1.5, 1.5 + 9·sqrt(p))`, color `rgba(120,165,220,.5)`.
- **Pruning:** a branch is rendered only if its probability *given its parent* is ≥ the
  `PRUNE` threshold (default **0.05**), and at most the **top 3** opponents per node are
  shown. Both are single constants — see §7.
- A gold **"↑ Back to {parent}"** button sits directly above the root node whenever you're
  drilled below the base.

### View B — Pie explorer
A single large donut (300px) centered in the stage = the current match state.
- **Center hole** shows the round label, "vs {Opponent}" (or "vs Japan" at the start), and
  the advance/win probability for this match.
- **Slices = how this match resolves:** one slice per outcome —
  `{eliminated}` (muted red `#7c3a44`) + one `{advance & face X}` per possible next
  opponent (team color). Slice angle = that outcome's probability; the slices sum to 100%.
  At the Final, the "advance" slice becomes `{Champions}` (gold).
- **Labels** radiate outside the donut: team name + `face {%} · beat {%}` (or the outcome %
  for eliminated/champions), left/right‑aligned by side.
- **Click a team slice (or its label)** → that becomes the new center node and the pie
  repeats for the next round. Eliminated/Champions slices are terminal (not clickable).
- A gold **"↑ Back to {parent}"** button sits above the donut whenever drilled below the
  start.
- Pie slivers below `PRUNE_PIE` (default **0.012**) are hidden.

---

## Interactions & behavior
- **Re‑root (tree):** clicking any non‑root match node makes it the new root; its subtree
  re‑renders to the configured depth, all probabilities re‑expressed *conditional on that
  node*. Implemented as `treeRoot = clickedNode.path`.
- **Drill (pie):** clicking a team slice pushes that match onto `piePath`.
- **Back button:** steps up one level (`path.slice(0, -1)`).
- **Breadcrumb chips:** jump to any ancestor (`path.slice(0, i+1)`).
- **Reset:** returns both paths to the base `[{round:0, opponent:"Japan"}]`.
- **Zoom transition:** every navigation (re‑root, drill, back, breadcrumb, view switch,
  team change) replays a **scale‑in animation** on the content layer so it's clear you've
  moved. Keyframe: `scale(.78) → scale(1.035) at 58% → scale(1)`, duration **.46s**,
  easing `cubic-bezier(.2,.72,.3,1)`, `transform-origin` ≈ `13% 50%` (tree) / `50% 50%`
  (pie). **Important:** the animation is *scale‑only* (no opacity fade) on purpose — so
  content is never stuck invisible if the animation doesn't run.
  > Implementation note: the prototype runs this on a **nested inner content layer**, not
  > the outer stage element, because that host environment disabled CSS `transform` on the
  > top‑level frame. In a normal codebase you can animate the container directly; just keep
  > it scale‑only and re‑trigger it on each navigation (the prototype toggles between two
  > identical keyframe names `navInA`/`navInB` to force a restart without remounting).
- **Hover:** pie slices brighten (`filter: brightness(1.2)`); tree nodes show a `title`
  tooltip.
- **Responsiveness:** desktop‑first, single fixed 1150×540 stage that scales to fit. Not
  designed for mobile in this prototype.

## State management
State variables (prototype names):
- `view`: `'tree' | 'pie'`.
- `country`: selected team (only `'Sweden'` has real data in the prototype).
- `treeRoot`: array of `{round, opponent}` steps; the tree's current root path.
- `piePath`: array of `{round, opponent}` steps; the pie's current drill path.
- `navKey`: integer bumped on every navigation to retrigger the zoom animation.
- `scale`: fit‑to‑container zoom factor (set from a ResizeObserver on the stage area).

`round` encoding used throughout: `0`=group/Japan decider, `1`=R32, `2`=R16, `3`=QF,
`4`=SF, `5`=Final, `6`=Champions(terminal), `99`=eliminated(terminal).

Data fetching: in production, fetch/inline one `sim_results.json` (see §6) and select the
focal team's object; everything else is derived client‑side.

---

## 6. DATA CONTRACT  ← read this before building the back end

A sample file, **`sim_results.sample.json`**, ships in this bundle with both shapes filled
in using the prototype's mock numbers.

> **Critical:** the project plan's original `sim_results.json` (per‑team probabilities of
> winning group / advancing / reaching each round / winning) is **not sufficient** for the
> reactive views. The tree and pie need, additionally, the **opponent distribution at each
> round** (who Sweden could face and with what probability) and **Sweden's win probability
> vs each of those opponents**. Have `simulate.py` aggregate these from the Monte‑Carlo
> runs (e.g. across all sims in which Sweden reaches round *r*, tally the opponent faced and
> the win/loss outcome).

Pick **one** of these output shapes:

**(a) Marginal (minimum viable — drives the views exactly as built).**
Per focal team: `championProb`, `predictedFinish`, the `group` block (standings with real
`pld/gd/pts` + `remainingOpponent`), a `reach` block (advance/r16/qf/sf/final/champion),
and a `rounds[]` array (R32→Final) where each round lists its `opponents[]` with
`faceProb` (conditional on reaching that round; sums to ~1) and `beatProb`. With this shape
the decision tree's deeper levels are *approximated* by reusing each round's marginal
opponent distribution (i.e. the R16 distribution is assumed independent of which R32
opponent you actually beat) — which is exactly what the prototype does today.

**(b) Conditional tree (recommended for fidelity).**
A recursive node: `{ match:{round,opponent,opponentElo}, outcomes:[ {type, ...,
condProb, next} ] }` where `condProb` values at a node sum to 1, and `next` recurses. This
lets re‑rooting/drilling show *true* conditional distributions (P(face Y in R16 | beat
Uruguay in R32)). Prune at emit time by absolute probability (~0.5%) to bound file size.
This shape maps 1:1 onto the prototype's `childrenOf(path)` function.

Whichever you choose, also emit the `group.standings` with real points and the headline
`championProb` so the left panel is correct.

**Team‑name normalization** (flagged in the project plan) matters here too: opponent names
in `rounds`/`outcomes` must match the keys used elsewhere (`"USA"`, `"Korea Rep."`, etc.)
and the dashboard's team‑color map.

---

## 7. Tunable thresholds (kept as single constants for the build)
In the prototype's `class Component`, near the top:
- `PRUNE = 0.05` — **the client asked that this be easy to change.** A decision‑tree branch
  is shown only if its probability *given its parent* ≥ this value (0.05 = 5%).
- `PRUNE_PIE = 0.012` — pie explorer hides slices smaller than this.
- Tree breadth/depth also live in one spot: `MAXD = 2` (generations shown before you must
  click to go deeper) and the `.slice(0, 3)` cap (top‑3 opponents per node). Adjust these
  together if you want a fuller or sparser tree.

## Design tokens
**Colors**
- App background: radial gradient `radial-gradient(130% 100% at 70% -10%, #11315f 0%, #0a1f44 42%, #06122c 100%)`; base `#06122c`.
- Panel borders / hairlines: `rgba(140,175,225,.13)`.
- Text: primary `#eaf1fb`, secondary `#b9c8e2`, muted `#9fb4d6`, faint `#7b96bf`.
- **Sweden accent yellow** `#FECC00` (titles' "FINAL", headline number, active toggle, gold
  rings, back button, traced path / breadcrumb active).
- **Sweden blue** `#1f7fc4` (root/Japan node, reach‑bar gradient `#1f7fc4`→`#3f9bdc`).
- Eliminated red: node `rgba(150,60,70,.32)`, pie slice `#7c3a44`.
- Champions gold gradient: `radial-gradient(circle at 38% 30%, #fff3c0, #FECC00 62%, #f0a52a)`.
- **Team colors** (used for node fills, pie slices, dots) — extend this map as teams are
  added; names must match the data:
  `Japan #1f7fc4, Egypt #d6492f, Saudi Arabia #1f9d5c, Ghana #2aa84a, Uruguay #4ba3e3,
  Senegal #2faf6a, USA #3f63c4, Brazil #f4c20d, France #3756b0, Portugal #2b9a4c,
  Croatia #d63a3a, Morocco #c2402f, Mexico #2f8a52, England #e05656, Netherlands #ef8a32,
  Colombia #f0c437, Argentina #5aa6dd, Germany #9aa6bd, Belgium #e0b23a, Spain #d83b34`.
  Fallback for unmapped teams: `#6f86ad`.

**Typography** (Google Fonts)
- Display/headlines: **Archivo**, weights 800–900.
- Body/UI: **IBM Plex Sans**, 400–700.
- Numbers, tags, mono labels: **IBM Plex Mono**, 400–600.

**Sizing rules**
- Tree node radius: `max(20, 18 + 44·sqrt(p))`; edge width `max(1.5, 1.5 + 9·sqrt(p))`.
- Pie donut: 300px outer, viewBox `0 0 100 100` with outer R=46 / inner r=27.
- Stage design size: 1150 × 540, scaled with CSS `zoom` to fit (clamped 0.42–1.3).

**Radii / shadows**
- Cards/panels radius 16–18; buttons 9–11; chips/pills 18–21.
- Node shadow `0 10px 26px -10px {teamColor}`; back button `0 8px 20px -5px rgba(0,0,0,.55)`.

## Assets
None external. No images/icons — the trophy is the `★` glyph; donuts/edges are SVG/CSS
drawn at runtime. Fonts load from Google Fonts. If your codebase has a brand/icon system,
substitute as appropriate.

## Files in this bundle
- **`Road to the Final.dc.html`** — the current design (both views + panel + selector).
  Reference implementation of all math (`model()`, `childrenOf()`, `arcPath()`), layout,
  and the tunable constants.
- **`support.js`** — runtime needed to open the `.dc.html` in a browser. Not part of your
  production app; only for viewing the prototype.
- **`sim_results.sample.json`** — sample data in both contract shapes (§6).
- **`alt - Road to the Final v1 (linear spine).dc.html`** — an earlier exploration (a fixed
  R32→Final spine instead of a branching tree). Kept for reference only; the branching
  tree + pie explorer is the chosen direction.
