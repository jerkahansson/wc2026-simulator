"""Build the production "Road to the Final" WC2026 path-explorer site.

Reads sim_results.json (the Monte-Carlo output emitted by simulate.py) and emits a
single self-contained index.html: plain HTML + CSS + one vanilla-JS module. The full
DATA object is inlined into a <script> tag so the page has no external runtime
dependency (the .dc prototype's support.js / <x-dc> / DCLogic system is NOT used).

The visualization design, math, layout, animations and tunable constants are ported
faithfully from _ref/prototype.dc.html. The one structural change vs the prototype is
the data source: instead of an in-browser Elo->Poisson mock, every team's real
simulate.py output drives the views (see the JS model()/childrenOf() below).

Usage:
    cd C:\\Users\\erika\\projects\\wc2026-simulator
    python build_site.py
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "sim_results.json")
OUT = os.path.join(HERE, "index.html")


def main():
    with open(SRC, encoding="utf-8") as fh:
        data = json.load(fh)

    # Inline the JSON verbatim. ensure_ascii=False keeps team names like "Curacao"
    # readable; </script> is escaped so the literal can't break out of the tag.
    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")

    html = PAGE_TEMPLATE.replace("__DATA_JSON__", data_json)

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(html)

    n_teams = len(data.get("teams", {}))
    print(f"Wrote {OUT} ({len(html):,} bytes, {n_teams} teams).")


# ---------------------------------------------------------------------------
# The page template. __DATA_JSON__ is substituted with the inlined sim_results.
# Everything below the inlined DATA is a vanilla-JS port of the prototype's
# class Component (model / childrenOf / pathProb / arcPath / nodeLabel / the two
# views / left panel / breadcrumb / back button / zoom animation / fit scaling).
# ---------------------------------------------------------------------------
PAGE_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Road to the Final — WC2026 Path Explorer</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@600;700;800;900&family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  *{box-sizing:border-box;}
  html,body{margin:0;padding:0;background:#06122c;}
  ::-webkit-scrollbar{width:8px;height:8px;}
  ::-webkit-scrollbar-thumb{background:rgba(140,175,225,.22);border-radius:8px;}
  ::-webkit-scrollbar-track{background:transparent;}
  svg path[data-slice]{transition:filter .16s ease;}
  svg path[data-slice]:hover{filter:brightness(1.2);}
  @keyframes navInA{0%{transform:scale(.78)}58%{transform:scale(1.035)}100%{transform:scale(1)}}
  @keyframes navInB{0%{transform:scale(.78)}58%{transform:scale(1.035)}100%{transform:scale(1)}}

  /* ---- layout shell (ported from the prototype's inline styles) ---- */
  #app{position:fixed;inset:0;display:flex;flex-direction:column;
    background:radial-gradient(130% 100% at 70% -10%,#11315f 0%,#0a1f44 42%,#06122c 100%);
    color:#eaf1fb;font-family:'IBM Plex Sans',system-ui,sans-serif;overflow:hidden;}

  .topbar{display:flex;align-items:center;justify-content:space-between;
    padding:18px 30px 16px;border-bottom:1px solid rgba(140,175,225,.13);flex:0 0 auto;}
  .eyebrow{font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:.32em;
    color:#7b96bf;text-transform:uppercase;}
  h1.title{margin:0;font-family:'Archivo',sans-serif;font-weight:900;font-size:30px;
    line-height:1;letter-spacing:-.015em;text-transform:uppercase;}
  h1.title .final{color:#FECC00;}

  .team-label{font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.18em;
    color:#7b96bf;text-transform:uppercase;}
  select.team-select{appearance:none;background:#13294c;color:#eaf1fb;
    border:1px solid rgba(140,175,225,.22);border-radius:9px;padding:9px 30px 9px 12px;
    font-family:'IBM Plex Sans';font-size:13px;font-weight:600;cursor:pointer;
    background-image:linear-gradient(45deg,transparent 50%,#7b96bf 50%),linear-gradient(135deg,#7b96bf 50%,transparent 50%);
    background-position:calc(100% - 16px) 16px,calc(100% - 11px) 16px;
    background-size:5px 5px,5px 5px;background-repeat:no-repeat;}

  .seg-group{display:flex;background:rgba(140,175,225,.1);border:1px solid rgba(140,175,225,.18);
    border-radius:10px;padding:3px;gap:3px;}
  .reset-btn{background:rgba(140,175,225,.1);color:#cfe0f5;border:1px solid rgba(140,175,225,.22);
    border-radius:10px;padding:9px 16px;font-family:'IBM Plex Sans';font-size:13px;font-weight:600;cursor:pointer;}

  .body{display:flex;flex:1 1 auto;min-height:0;}
  .leftpanel{flex:0 0 326px;border-right:1px solid rgba(140,175,225,.13);
    padding:22px 22px 26px;overflow-y:auto;display:flex;flex-direction:column;gap:21px;}

  .headline-card{border:1px solid rgba(254,204,0,.28);border-radius:16px;padding:20px 20px 18px;
    background:linear-gradient(160deg,rgba(254,204,0,.09),rgba(255,255,255,.012));}
  .headline-eyebrow{font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.22em;
    color:#9fb4d6;text-transform:uppercase;margin-bottom:6px;}
  .headline-pct{font-family:'Archivo',sans-serif;font-weight:900;font-size:54px;line-height:.9;
    color:#FECC00;letter-spacing:-.02em;}
  .headline-sub{margin-top:10px;font-size:13px;color:#b9c8e2;line-height:1.4;}

  .section-eyebrow{font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.22em;
    color:#7b96bf;text-transform:uppercase;}

  .bar-row{display:flex;align-items:center;gap:11px;}
  .bar-label{flex:0 0 78px;font-size:12px;color:#b9c8e2;font-weight:500;}
  .bar-track{flex:1 1 auto;height:11px;background:rgba(140,175,225,.1);border-radius:6px;overflow:hidden;}
  .bar-fill{height:100%;background:linear-gradient(90deg,#1f7fc4,#3f9bdc);border-radius:6px;
    transition:width .6s cubic-bezier(.34,1.3,.5,1);}
  .bar-pct{flex:0 0 46px;text-align:right;font-family:'IBM Plex Mono',monospace;font-size:12px;
    color:#eaf1fb;font-weight:500;}

  .stage-hint{padding:14px 30px 4px;flex:0 0 auto;font-size:13px;color:#9fb4d6;}
  .stagearea{flex:1 1 auto;position:relative;display:flex;align-items:center;justify-content:center;overflow:hidden;}

  .crumb{border-radius:18px;padding:5px 11px;font-size:12px;font-weight:600;cursor:pointer;
    font-family:'IBM Plex Sans';}
</style>
</head>
<body>
<div id="app"></div>

<!-- Inlined Monte-Carlo output. No external fetch / runtime. -->
<script>const DATA = __DATA_JSON__;</script>

<script>
"use strict";
(function () {

  // ===================== TUNABLE CONSTANTS =====================
  // Tree breadth is fixed by COUNT, not a probability threshold: the root fans
  // out to LAYER_CAPS[0] opponents (2nd layer), each previewing LAYER_CAPS[1]
  // (3rd layer). 6 then 2 → up to 12 nodes (fits 540px readably). Re-rooting any
  // node re-shows its top-6. Tune here.
  const LAYER_CAPS = [3, 3]; // children shown per node in the TREE → 1/3/9. The left
                             // "possible opponents" list shows the full top-6 (emit cap).
  const PRUNE_PIE = 0.012;   // pie explorer hides slices smaller than this
  const MAXD = 2;            // generations shown before clicking deeper

  // ===================== team colors =====================
  // Names must match the data keys. Fallback #6f86ad for anything unmapped.
  const OPP = {
    Japan:'#1f7fc4', Egypt:'#d6492f', 'Saudi Arabia':'#1f9d5c', Ghana:'#2aa84a',
    Uruguay:'#4ba3e3', Senegal:'#2faf6a', USA:'#3f63c4', Brazil:'#f4c20d',
    France:'#3756b0', Portugal:'#2b9a4c', Croatia:'#d63a3a', Morocco:'#c2402f',
    Mexico:'#2f8a52', England:'#e05656', Netherlands:'#ef8a32', Colombia:'#f0c437',
    Argentina:'#5aa6dd', Germany:'#9aa6bd', Belgium:'#e0b23a', Spain:'#d83b34',
    // extended to cover the remaining qualified teams in the dataset
    Sweden:'#1f7fc4', Norway:'#c8102e', Australia:'#f1c40f', Canada:'#d52b1e',
    Paraguay:'#d2122e', Switzerland:'#d52b1e', Austria:'#d81e3f',
    'Czech Republic':'#11457e', Turkey:'#e30a17', Scotland:'#0b4ea2', Iran:'#239f40',
    Iraq:'#cf142b', Jordan:'#007a3d', Qatar:'#8a1538', 'South Korea':'#0047a0',
    'South Africa':'#007a4d', Tunisia:'#e70013', Algeria:'#2a8a43', 'Ivory Coast':'#f77f00',
    'Cape Verde':'#1c5fae', 'D.R. Congo':'#27a9e0', Curacao:'#0b3d91', Haiti:'#00209f',
    Panama:'#c8102e', Ecuador:'#ffd100', 'Bosnia & Herzegovina':'#1f3a93',
    'New Zealand':'#7b8794', Uzbekistan:'#1eb53a'
  };
  function oppColor(n) { return OPP[n] || '#6f86ad'; }

  // ===================== labels / formatting =====================
  const ROUNDS = ['Round of 32', 'Round of 16', 'Quarter-final', 'Semi-final', 'Final'];
  const RSHORT = ['R32', 'R16', 'QF', 'SF', 'FINAL'];
  // Two vocabularies feed this map: the conditional tree uses "Final" (long
  // form, from simulate.py's ROUND_SEQ); raw results/bracket data use "F"
  // (short form, from bracket.py's ROUND_OF) -- both keys map to the same text.
  const ROUND_FULL = {
    Group: 'Group stage', R32: 'Round of 32', R16: 'Round of 16',
    QF: 'Quarter-final', SF: 'Semi-final', '3P': 'Third-place play-off',
    Final: 'Final', F: 'Final'
  };

  function pct(p) {
    const v = p * 100;
    if (v >= 10) return Math.round(v) + '%';
    if (v >= 1) return v.toFixed(1) + '%';
    return v.toFixed(2) + '%';
  }

  // A branch is "low confidence" when few simulations reached it — its
  // conditional percentages are then statistically noisy. We still SHOW such
  // branches (so the tree drills toward the Final instead of dead-ending) but
  // flag them with a trailing "*" and an explanatory tooltip. reachP is a
  // node's absolute reach probability; reachP * n_sims ≈ the sample count.
  const LOWCONF_SAMPLES = 50;
  function lowConf(reachP) {
    return reachP != null && (reachP * DATA.n_sims) < LOWCONF_SAMPLES;
  }
  function star(reachP) { return lowConf(reachP) ? '*' : ''; }

  // ===================== elimination status =====================
  // The group stage is over, so a team's fate up to its next unplayed match is
  // either a real, decided fact (a played result) or a single certain opponent
  // waiting to be played -- never a simulated guess. Both are visible in the
  // conditional tree as a chain of condProb===1 nodes (the ONLY possible next
  // opponent); a pinned result additionally has beatProb 0 or 1 exactly (every
  // one of the 200k sims agrees). Walking that chain tells us, with zero extra
  // backend data, whether/where/to whom a team has already been eliminated.
  function eliminationInfo(team) {
    if (team.reach.advance <= 0) return { eliminated: true, round: 'Group', opponent: null };
    let node = team.tree;
    while (node.children && node.children.length) {
      const c = node.children.find(k => k.condProb >= 0.999);
      if (!c) return { eliminated: false };                 // >1 live opponent -> still open
      if (c.beatProb <= 0.001) return { eliminated: true, round: c.round, opponent: c.opponent };
      if (c.beatProb >= 0.999) { node = c; continue; }       // pinned win -> keep walking
      return { eliminated: false };                          // confirmed opponent, unplayed
    }
    return { eliminated: false };
  }

  // ===================== state =====================
  const teamNames = Object.keys(DATA.teams).sort();
  const aliveTeamsInit = teamNames.filter(t => !eliminationInfo(DATA.teams[t]).eliminated);
  const defaultTeam = aliveTeamsInit.length
    ? aliveTeamsInit.slice().sort((a, b) => DATA.teams[b].championProb - DATA.teams[a].championProb)[0]
    : teamNames[0];
  const state = {
    scale: 1,
    view: 'tree',
    country: defaultTeam,
    navKey: 0,
    treeRoot: null,   // set by resetPaths()
    piePath: null
  };

  // ===================== model() — swap the data source =====================
  // Returns the per-team derived structure the views consume. Mirrors the
  // prototype's model() output shape ({advance, reach, faceDists, ...}) but the
  // numbers come straight from the selected team's simulate.py record.
  function model() {
    const team = DATA.teams[state.country];
    const reachObj = team.reach;
    // reach[] index: 0=advance,1=r16,2=qf,3=sf,4=final,5=champion
    const reach = [reachObj.advance, reachObj.r16, reachObj.qf, reachObj.sf, reachObj.final, reachObj.champion];

    return {
      team,
      advance: reachObj.advance,
      reach,
      tree: team.tree,        // conditional knockout tree (the real branching)
      champion: reachObj.champion
    };
  }

  // round string ("GROUP"/"R32"/.../"Final") -> our numeric round code (0/1../5).
  function roundNum(s) { return { GROUP: 0, R32: 1, R16: 2, QF: 3, SF: 4, Final: 5 }[s]; }

  // Walk the conditional tree to the node at the end of `path`. Returns the tree
  // node {round, opponent, advanceProb|beatProb, children, ...} or null if the
  // path runs past where the tree was emitted (pruned below 0.5%).
  function nodeAtPath(M, path) {
    let node = M.tree;                 // GROUP root
    for (let i = 1; i < path.length; i++) {
      const want = path[i];
      if (want.round === 6) return node;   // champion terminal sits on the Final node
      const kids = node.children || [];
      node = kids.find(c => roundNum(c.round) === want.round && c.opponent === (want.opp && want.opp.name));
      if (!node) return null;
    }
    return node;
  }

  // Win chance of the match AT the current node: advance for the group/knockout
  // root, beatProb for a knockout match (0 if we've drilled past the emitted tree).
  function nodeBeat(path, M) {
    const last = path[path.length - 1];
    if (last.round === 6) return 0;
    const node = nodeAtPath(M, path);
    if (!node) return 0;
    return (last.round <= 0) ? node.advanceProb : node.beatProb;
  }

  // ===================== childrenOf(path) — CONDITIONAL tree =====================
  // path is an array of {round, opp:{name,elo}|null}. round encoding:
  //   0=group decider, -1=knockout root, 1=R32, 2=R16, 3=QF, 4=SF, 5=Final,
  //   6=champion, 99=eliminated.
  // Children come from the node's true conditional next-opponent distribution
  // (P(face Y | we beat the current opponent)), straight from simulate.py's tree.
  function childrenOf(path, M) {
    const last = path[path.length - 1];
    if (last.round >= 6) return [];
    const node = nodeAtPath(M, path);
    if (!node) return [];
    const isRoot = last.round <= 0;             // group decider / knockout root
    const winP = isRoot ? node.advanceProb : node.beatProb;

    if (last.round === 5) {                     // Final: win => champion, else lose
      return [
        { kind: 'champ', round: 6, condP: node.beatProb },
        { kind: 'lose', round: 99, condP: 1 - node.beatProb, label: 'Lose final' }
      ];
    }

    const out = (node.children || []).map(c => ({
      kind: 'opp', round: roundNum(c.round), opp: { name: c.opponent, elo: c.elo },
      condP: c.condProb, beatProb: c.beatProb, reachP: c.reachProb
    }));
    const label = isRoot ? 'Out in group' : 'Out in ' + RSHORT[last.round - 1];
    out.push({ kind: 'lose', round: 99, condP: 1 - winP, label: label });
    return out;
  }

  // Probability of an exact traced run (product of conditional probs along path).
  function pathProb(path, M) {
    let p = 1;
    for (let i = 1; i < path.length; i++) {
      const par = path.slice(0, i);
      const kids = childrenOf(par, M);
      const want = path[i];
      let hit;
      if (want.round === 6) hit = kids.find(c => c.kind === 'champ');
      else hit = kids.find(c => c.kind === 'opp' && c.round === want.round && c.opp.name === want.opp.name);
      p *= hit ? hit.condP : 0;
    }
    return p;
  }

  // ===================== arcPath / nodeLabel (ported verbatim) =====================
  function arcPath(a0, a1, R, r) {
    const cx = 50, cy = 50;
    const pt = (a, rad) => `${(cx + rad * Math.cos(a)).toFixed(2)} ${(cy + rad * Math.sin(a)).toFixed(2)}`;
    if (a1 - a0 >= 2 * Math.PI - 1e-3) {
      return `M ${pt(0, R)} A ${R} ${R} 0 1 1 ${pt(Math.PI, R)} A ${R} ${R} 0 1 1 ${pt(2 * Math.PI, R)} Z ` +
             `M ${pt(0, r)} A ${r} ${r} 0 1 0 ${pt(Math.PI, r)} A ${r} ${r} 0 1 0 ${pt(2 * Math.PI, r)} Z`;
    }
    const large = (a1 - a0) > Math.PI ? 1 : 0;
    return `M ${pt(a0, R)} A ${R} ${R} 0 ${large} 1 ${pt(a1, R)} L ${pt(a1, r)} A ${r} ${r} 0 ${large} 0 ${pt(a0, r)} Z`;
  }

  function nodeLabel(node, M) {
    if (node.round === -1) return { tag: 'KNOCKOUTS', name: 'Round of 32' };
    if (node.round === 6) return { tag: 'CHAMPION', name: '★' };
    if (node.round === 99) return { tag: 'OUT', name: 'Eliminated' };
    return { tag: RSHORT[node.round - 1], name: 'vs ' + node.opp.name };
  }

  // childrenOf already handles the synthetic knockout root (round -1) via
  // nodeAtPath, so this is just a stable alias.
  function childrenOfRoot(path, M) {
    return childrenOf(path, M);
  }

  // Fast-forward past every match that's already been decided for real (see
  // eliminationInfo for why the condProb/beatProb chain is a reliable signal),
  // so exploration starts at the live frontier instead of replaying history.
  // A group-eliminated team gets a short-circuit straight to the OUT leaf.
  function confirmedPath(M) {
    const path = [{ round: -1, opp: null }];
    if (M.team.reach.advance <= 0) return path.concat([{ round: 99, opp: null }]);
    let node = M.tree;
    while (node.children && node.children.length) {
      const c = node.children.find(k => k.condProb >= 0.999);
      if (!c) break;                                             // >1 live opponent -> this is the frontier
      if (c.beatProb <= 0.001) { path.push({ round: 99, opp: null }); break; }  // pinned loss -> eliminated here, don't leave the lost match as the frontier
      path.push({ round: roundNum(c.round), opp: { name: c.opponent, elo: c.elo } });
      if (c.beatProb >= 0.999) { node = c; continue; }            // pinned win -> keep fast-forwarding
      break;                                                      // confirmed opponent, unplayed -> frontier
    }
    return path;
  }

  function resetPaths() {
    const M = model();
    const p = confirmedPath(M);
    state.treeRoot = p;
    state.piePath = p;
  }

  // ===================== navigation =====================
  function bump(extra) {
    if (extra) Object.assign(state, extra);
    state.navKey += 1;
    render();
  }
  function onCountryChange(v) { state.country = v; resetPaths(); bump(); }
  function showTree() { bump({ view: 'tree' }); }
  function showPie() { bump({ view: 'pie' }); }
  function showBracket() { bump({ view: 'bracket' }); }
  function reset() { resetPaths(); bump(); }
  function rerootTree(path) { bump({ treeRoot: path }); }
  function drillPie(path) { bump({ piePath: path }); }

  // ===================== small DOM helpers =====================
  function el(tag, attrs, children) {
    const e = document.createElement(tag);
    if (attrs) {
      for (const k in attrs) {
        if (k === 'style' && typeof attrs[k] === 'object') Object.assign(e.style, attrs[k]);
        else if (k === 'text') e.textContent = attrs[k];
        else if (k === 'html') e.innerHTML = attrs[k];
        else if (k.slice(0, 2) === 'on' && typeof attrs[k] === 'function') e.addEventListener(k.slice(2), attrs[k]);
        else if (attrs[k] != null) e.setAttribute(k, attrs[k]);
      }
    }
    (children || []).forEach(c => { if (c != null) e.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); });
    return e;
  }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

  // ===================== render =====================
  const app = document.getElementById('app');

  function render() {
    const M = model();
    const st = state;
    clear(app);

    // ---------- header ----------
    const titleWrap = el('div', { style: { display: 'flex', flexDirection: 'column', gap: '5px' } }, [
      el('div', { class: 'eyebrow', text: 'FIFA World Cup 26  ·  Path Explorer' }),
      (function () {
        const h = el('h1', { class: 'title' });
        h.appendChild(document.createTextNode(st.country.toUpperCase() + '’S ROAD TO THE '));
        h.appendChild(el('span', { class: 'final', text: 'FINAL' }));
        return h;
      })()
    ]);

    const aliveTeams = teamNames.filter(t => !eliminationInfo(DATA.teams[t]).eliminated);
    const eliminatedTeams = teamNames.filter(t => eliminationInfo(DATA.teams[t]).eliminated);
    const opt = t => el('option', { value: t, text: t, selected: t === st.country ? 'selected' : null });
    const selectEl = el('select', { class: 'team-select', onchange: function (e) { onCountryChange(e.target.value); } }, [
      el('optgroup', { label: 'Still in the tournament' }, aliveTeams.map(opt)),
      el('optgroup', { label: 'Eliminated' }, eliminatedTeams.map(opt))
    ]);

    const seg = (label, on, handler) => el('button', {
      onclick: handler,
      style: {
        background: on ? '#FECC00' : 'transparent', color: on ? '#1a1205' : '#cfe0f5',
        border: 'none', borderRadius: '8px', padding: '7px 15px',
        fontFamily: "'IBM Plex Sans'", fontSize: '13px', fontWeight: '700', cursor: 'pointer', transition: 'all .2s'
      }, text: label
    });

    const controls = el('div', { style: { display: 'flex', alignItems: 'center', gap: '12px' } }, [
      el('div', { style: { display: 'flex', alignItems: 'center', gap: '8px' } }, [
        el('span', { class: 'team-label', text: 'Team' }), selectEl
      ]),
      el('div', { class: 'seg-group' }, [
        seg('Decision tree', st.view === 'tree', showTree),
        seg('Pie explorer', st.view === 'pie', showPie),
        seg('Bracket', st.view === 'bracket', showBracket)
      ]),
      el('button', { class: 'reset-btn', onclick: reset, text: 'Reset' })
    ]);

    app.appendChild(el('div', { class: 'topbar' }, [titleWrap, controls]));

    // ---------- body ----------
    const body = el('div', { class: 'body' });
    app.appendChild(body);

    // active path depends on view (the bracket is a static global view, not a
    // drilldown, so it just reuses the tree's frontier for the left panel).
    const activePath = st.view === 'pie' ? st.piePath : st.treeRoot;
    const activeLast = activePath[activePath.length - 1];
    const focusRound = activeLast.round;

    body.appendChild(buildLeftPanel(M, activePath, focusRound));

    // ---------- stage ----------
    const stageHint = st.view === 'tree'
      ? 'Each node: green/red ring = chance to win that game · number & size = how likely this matchup is, given the previous one · click a node to make it the root'
      : st.view === 'pie'
      ? 'The pie shows how this match resolves · click a team slice to follow that path into the next round'
      : 'The full knockout draw · gold border = ' + st.country + '’s matches · scores show once a match has been played';

    const stageArea = el('div', { 'data-stagearea': '1', class: 'stagearea' });
    const wrap = el('div', { style: { position: 'relative', width: '1150px', height: '540px', flex: '0 0 auto', zoom: st.scale } });
    const anim = el('div', {
      style: {
        position: 'absolute', inset: '0',
        animation: (st.navKey % 2 === 0 ? 'navInA' : 'navInB') + ' .46s cubic-bezier(.2,.72,.3,1)',
        transformOrigin: st.view === 'tree' ? '13% 50%' : '50% 50%', willChange: 'transform'
      }
    });
    wrap.appendChild(anim);
    stageArea.appendChild(wrap);

    if (st.view === 'tree') buildTree(anim, wrap, M, st);
    else if (st.view === 'pie') buildPie(anim, wrap, M, st, activePath, activeLast);
    else buildBracket(anim, st);

    const right = el('div', { style: { flex: '1 1 auto', minWidth: '0', display: 'flex', flexDirection: 'column' } }, [
      el('div', { class: 'stage-hint', text: stageHint }),
      stageArea
    ]);
    body.appendChild(right);

    requestAnimationFrame(fit);
  }

  // ---------- LEFT PANEL ----------
  function buildLeftPanel(M, activePath, focusRound) {
    const st = state;
    const team = M.team;

    // headline card
    let predictedLabel;
    const elim = eliminationInfo(team);
    if (elim.eliminated) {
      predictedLabel = elim.round === 'Group'
        ? st.country + ' were eliminated in the group stage.'
        : st.country + ' were eliminated in the ' + ROUND_FULL[elim.round] + ' — lost to ' + elim.opponent + '.';
    } else {
      const finish = team.predictedFinish;
      predictedLabel = finish === 'Champion' ? 'Most likely: ' + st.country + ' lift the trophy' : 'Most likely finish: ' + finish;
    }

    const headline = el('div', { class: 'headline-card' }, [
      el('div', { class: 'headline-eyebrow', text: st.country + ' win the World Cup' }),
      el('div', { style: { display: 'flex', alignItems: 'baseline', gap: '9px' } }, [
        el('div', { class: 'headline-pct', text: pct(M.champion) })
      ]),
      el('div', { class: 'headline-sub', text: predictedLabel })
    ]);

    // reach bars
    const barData = [
      ['Round of 32', M.reach[0]], ['Round of 16', M.reach[1]], ['Quarter-final', M.reach[2]],
      ['Semi-final', M.reach[3]], ['Final', M.reach[4]], ['Champion', M.reach[5]]
    ];
    const bars = el('div', { style: { display: 'flex', flexDirection: 'column', gap: '9px' } },
      barData.map(([label, p]) => el('div', { class: 'bar-row' }, [
        el('div', { class: 'bar-label', text: label }),
        el('div', { class: 'bar-track' }, [el('div', { class: 'bar-fill', style: { width: Math.max(p * 100, 1.5) + '%' } })]),
        el('div', { class: 'bar-pct', text: pct(p) })
      ])));
    const barsSection = el('div', {}, [
      el('div', { class: 'section-eyebrow', style: { marginBottom: '12px' }, text: 'Chance to reach round' }),
      bars
    ]);

    // real results so far (group + any played knockout matches)
    const historySection = buildHistorySection(team);

    // context section: possible next opponents, champion/eliminated message,
    // or (round -1 only) a placeholder for the bare knockout root
    const ctx = el('div', { style: { flex: '1 1 auto' } });
    if (focusRound >= 1 && focusRound <= 5) {
      // CONDITIONAL: who could they face NEXT, given the path drilled so far.
      const activeLast = activePath[activePath.length - 1];
      const winP = nodeBeat(activePath, M);
      const kids = childrenOf(activePath, M).filter(c => c.kind === 'opp');
      if (kids.length) {
        const nextRound = ROUNDS[kids[0].round - 1];
        const opps = kids.map(c => {
          const faceCond = winP > 0 ? c.condP / winP : 0;  // P(face them | we get through)
          return el('div', {
            style: {
              display: 'flex', alignItems: 'center', gap: '10px', padding: '8px 11px', borderRadius: '9px',
              background: 'rgba(140,175,225,.05)', border: '1px solid rgba(140,175,225,.1)'
            }
          }, [
            el('div', { style: { width: '10px', height: '10px', borderRadius: '50%', background: oppColor(c.opp.name), flex: '0 0 auto' } }),
            el('div', { style: { flex: '1 1 auto', fontSize: '13px', fontWeight: '600', color: '#eaf1fb' }, text: c.opp.name }),
            el('div', { style: { fontFamily: "'IBM Plex Mono',monospace", fontSize: '11px', color: '#9fb4d6' }, text: 'face ' + pct(faceCond) }),
            el('div', { style: { fontFamily: "'IBM Plex Mono',monospace", fontSize: '11px', color: '#FECC00', width: '58px', textAlign: 'right' }, text: 'beat ' + pct(c.beatProb) })
          ]);
        });
        ctx.appendChild(el('div', {}, [
          el('div', { class: 'section-eyebrow', style: { letterSpacing: '.2em', marginBottom: '4px' }, text: nextRound + ' · possible opponents' }),
          el('div', { style: { fontSize: '12px', color: '#9fb4d6', marginBottom: '11px' }, text: 'If ' + st.country + ' beat ' + activeLast.opp.name + ' — who they could face next.' }),
          el('div', { style: { display: 'flex', flexDirection: 'column', gap: '7px' } }, opps)
        ]));
      } else {
        const msg = winP <= 0.001
          ? st.country + ' lost this one — see Results so far for the score.'
          : focusRound === 5
          ? 'Win the final to lift the trophy — ' + pct(winP) + ' from here.'
          : 'Deeper paths fall below the 0.5% cutoff at this sample size.';
        ctx.appendChild(el('div', {}, [
          el('div', { class: 'section-eyebrow', style: { letterSpacing: '.2em', marginBottom: '4px' }, text: ROUNDS[focusRound - 1] + ' · vs ' + activeLast.opp.name }),
          el('div', { style: { fontSize: '12px', color: '#9fb4d6' }, text: msg })
        ]));
      }
    } else if (focusRound === 6) {
      ctx.appendChild(el('div', {}, [
        el('div', { class: 'section-eyebrow', style: { letterSpacing: '.2em', marginBottom: '4px' }, text: 'Champions of the world' }),
        el('div', { style: { fontSize: '12px', color: '#9fb4d6' }, text: st.country + ' have won the World Cup in this scenario.' })
      ]));
    } else if (focusRound === 99) {
      ctx.appendChild(el('div', {}, [
        el('div', { class: 'section-eyebrow', style: { letterSpacing: '.2em', marginBottom: '4px' }, text: 'Eliminated' }),
        el('div', { style: { fontSize: '12px', color: '#9fb4d6' }, text: 'See Results so far for the full run.' })
      ]));
    } else {
      // round === -1: only reachable by manually navigating back to the
      // synthetic knockout root (a qualified team's real frontier always has
      // a concrete round 1-5 node, so there's nothing more specific to show).
      ctx.appendChild(el('div', {}, [
        el('div', { class: 'section-eyebrow', style: { letterSpacing: '.2em', marginBottom: '4px' }, text: 'Knockout bracket' }),
        el('div', { style: { fontSize: '12px', color: '#9fb4d6' }, text: 'Click into the bracket to explore ' + st.country + ' possible paths.' })
      ]));
    }

    // breadcrumb (path so far)
    const setActive = st.view === 'tree' ? rerootTree : drillPie;
    const crumbs = activePath.map((s, i) => {
      const lab = s.round === -1 ? 'Knockouts' : s.round === 6 ? '★ Champions' : s.round === 99 ? 'Eliminated' : s.opp.name;
      const last = i === activePath.length - 1;
      return el('button', {
        class: 'crumb',
        onclick: function () { setActive(activePath.slice(0, i + 1)); },
        style: {
          background: last ? 'rgba(254,204,0,.16)' : 'rgba(140,175,225,.08)',
          border: '1px solid ' + (last ? 'rgba(254,204,0,.4)' : 'rgba(140,175,225,.16)'),
          color: last ? '#FECC00' : '#cfe0f5'
        }, text: (i > 0 ? '→ ' : '') + lab
      });
    });
    const pathProbLabel = activePath.length > 1
      ? 'Probability of this exact run so far: ' + pct(pathProb(activePath, M))
      : 'Exploring from kickoff — click a node to drill in.';
    const crumbSection = el('div', {}, [
      el('div', { class: 'section-eyebrow', style: { marginBottom: '10px' }, text: 'Path so far' }),
      el('div', { style: { display: 'flex', flexWrap: 'wrap', gap: '7px', alignItems: 'center' } }, crumbs),
      el('div', { style: { marginTop: '10px', fontSize: '12px', color: '#9fb4d6' }, text: pathProbLabel })
    ]);

    const simNote = el('div', {
      style: { marginTop: '4px', fontFamily: "'IBM Plex Mono',monospace", fontSize: '10px', color: '#6f86ad', letterSpacing: '.04em', lineHeight: '1.5' },
      text: 'Based on ' + Number(DATA.n_sims).toLocaleString() + ' Monte-Carlo simulations · updated ' + (DATA.updated || '')
        + ' · strengths: ' + ((DATA.ratings_source || {}).mode === 'market' ? 'market-implied (Polymarket)' : 'Elo')
        + ' · * = few simulations reached this branch (indicative only)'
    });
    return el('div', { class: 'leftpanel' }, [headline, barsSection, historySection, ctx, crumbSection, simNote].filter(Boolean));
  }

  // Real results so far: group matches + any played knockout matches, in
  // chronological order, straight from results.json (never the simulation).
  function buildHistorySection(team) {
    const hist = team.history || [];
    if (!hist.length) return null;
    const rows = hist.map(h => {
      const badge = h.result === 'W' ? '#2ea043' : h.result === 'L' ? '#c0392b' : '#7b96bf';
      return el('div', {
        style: {
          display: 'flex', alignItems: 'center', gap: '9px', padding: '7px 11px', borderRadius: '9px',
          background: 'rgba(140,175,225,.04)', border: '1px solid rgba(140,175,225,.09)'
        }
      }, [
        el('div', {
          style: {
            width: '19px', height: '19px', borderRadius: '50%', background: badge, color: '#fff',
            display: 'flex', alignItems: 'center', justifyContent: 'center', flex: '0 0 auto',
            fontFamily: "'IBM Plex Mono',monospace", fontSize: '10px', fontWeight: '700'
          }, text: h.result
        }),
        el('div', {
          style: {
            flex: '0 0 64px', fontFamily: "'IBM Plex Mono',monospace", fontSize: '9px', color: '#7b96bf',
            textTransform: 'uppercase', letterSpacing: '.05em'
          }, text: ROUND_FULL[h.stage] || h.stage
        }),
        el('div', { style: { flex: '1 1 auto', fontSize: '13px', fontWeight: '600', color: '#eaf1fb', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }, text: 'vs ' + h.opponent }),
        el('div', { style: { fontFamily: "'IBM Plex Mono',monospace", fontSize: '12px', color: '#cfe0f5', fontWeight: '700' }, text: h.teamScore + '–' + h.oppScore })
      ]);
    });
    return el('div', {}, [
      el('div', { class: 'section-eyebrow', style: { marginBottom: '10px' }, text: 'Results so far' }),
      el('div', { style: { display: 'flex', flexDirection: 'column', gap: '6px' } }, rows)
    ]);
  }

  // ---------- DECISION TREE ----------
  function buildTree(anim, wrap, M, st) {
    const X0 = 100, COLW = 475, H = 540;
    let leafCount = 0;
    const flat = [];
    const edges = [];

    const rec = (path, cond, depth, condParent) => {
      const last = path[path.length - 1];
      // condParent = this node's probability GIVEN its parent (null for the root).
      const node = { idx: flat.length, depth, cond, condParent, path, last, kind: last.round === 6 ? 'champ' : (last.round === 99 ? 'lose' : 'opp'), label: last.label, kids: [] };
      flat.push(node);
      if (depth < MAXD && last.round < 6 && last.round !== 99) {
        const cs = childrenOfRoot(path, M)
          .filter(c => c.kind !== 'lose' && c.condP > 0)
          .sort((a, b) => b.condP - a.condP)
          .slice(0, LAYER_CAPS[depth] || 3);
        for (const c of cs) {
          const cp = c.kind === 'champ'
            ? path.concat([{ round: 6, opp: null }])
            : path.concat([{ round: c.round, opp: c.opp }]);
          const ch = rec(cp, cond * c.condP, depth + 1, c.condP);
          edges.push({ from: node.idx, to: ch.idx, prob: cond * c.condP });
          node.kids.push(ch);
        }
      }
      if (node.kids.length === 0) node.y = leafCount++;
      else node.y = node.kids.reduce((s, k) => s + k.y, 0) / node.kids.length;
      return node;
    };
    rec(st.treeRoot, 1, 0, null);

    const rowH = Math.max(42, Math.min(150, (H - 40) / Math.max(leafCount, 1)));
    const yTop = (H - rowH * Math.max(leafCount, 1)) / 2 + rowH / 2;
    const pos = flat.map(n => ({ x: X0 + n.depth * COLW, y: yTop + n.y * rowH }));

    // per-column node count → a radius cap so a crowded column (e.g. 12 in the
    // 3rd layer) shrinks to fit, while the root / early columns stay big.
    const depthCount = {};
    flat.forEach(n => { depthCount[n.depth] = (depthCount[n.depth] || 0) + 1; });
    const maxRForDepth = d => Math.min(72, (H / Math.max(depthCount[d], 1)) * 0.46);

    // edges
    for (const e of edges) {
      const a = pos[e.from], b = pos[e.to];
      const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy), ang = Math.atan2(dy, dx) * 180 / Math.PI;
      const w = Math.max(1.5, 1.5 + 9 * Math.sqrt(e.prob));
      anim.appendChild(el('div', {
        style: {
          position: 'absolute', left: a.x + 'px', top: a.y + 'px', width: len + 'px', height: w + 'px',
          marginTop: (-w / 2) + 'px', transformOrigin: '0 50%', transform: 'rotate(' + ang + 'deg)',
          background: 'rgba(120,165,220,.5)', borderRadius: w + 'px', transition: 'all .4s ease', zIndex: 1
        }
      }));
    }

    // nodes
    for (let i = 0; i < flat.length; i++) {
      const n = flat[i], p = pos[i];
      if (n.kind === 'champ' || n.kind === 'lose') {
        const r = Math.min(Math.max(13, 11 + 26 * Math.sqrt(n.condParent || 0)), maxRForDepth(n.depth));
        const gold = n.kind === 'champ';
        const node = el('div', {
          title: gold ? 'World Cup won' : 'Eliminated',
          style: {
            position: 'absolute', left: p.x + 'px', top: p.y + 'px', width: (r * 2) + 'px', height: (r * 2) + 'px',
            marginLeft: (-r) + 'px', marginTop: (-r) + 'px', borderRadius: '50%',
            display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center',
            cursor: 'default',
            background: gold ? 'radial-gradient(circle at 38% 30%,#fff3c0,#FECC00 62%,#f0a52a)' : 'rgba(150,60,70,.32)',
            color: gold ? '#3a2a00' : '#f0c9cf',
            border: gold ? '2px solid rgba(255,255,255,.5)' : '1px solid rgba(200,90,100,.45)',
            boxShadow: gold ? '0 0 26px rgba(254,204,0,.5)' : 'none',
            transition: 'all .45s cubic-bezier(.34,1.3,.5,1)', zIndex: 3
          }
        }, [
          el('div', { style: { fontFamily: "'IBM Plex Mono',monospace", letterSpacing: '.05em', opacity: '.85', fontSize: (gold ? 12 : 8) + 'px' }, text: gold ? '★' : 'OUT' }),
          el('div', { style: { fontWeight: '700', lineHeight: '1', fontSize: (gold ? 0 : 9) + 'px', marginTop: '1px', display: gold ? 'none' : 'block' }, text: gold ? 'Champions' : (n.label || 'Out') }),
          n.condParent != null
            ? el('div', { style: { fontFamily: "'IBM Plex Mono',monospace", fontWeight: '600', opacity: '.9', fontSize: '11px', marginTop: '2px' }, text: pct(n.condParent) })
            : null
        ]);
        anim.appendChild(node);
      } else {
        // Node = a donut for the match at this state. KNOCKOUT nodes: ring is
        // green = win chance / red = lose; the big number is the chance we REACH
        // this matchup. The GROUP node (vs the last group opponent) is special —
        // qualifying is not a single win/lose match, so its ring is blue =
        // advance / grey = out and its number is the advance chance.
        const isRoot = n.depth === 0;
        // Size = probability of THIS outcome given its parent (condParent).
        // The current root has no parent, so it's drawn at a fixed large size.
        let r = isRoot ? 54 : Math.max(18, 16 + 46 * Math.sqrt(n.condParent || 0));
        r = Math.min(r, maxRForDepth(n.depth));
        const lab = nodeLabel(n.last, M);
        const isGroup = n.last.round <= 0;          // group decider / knockouts root
        const isKORoot = n.last.round === -1;       // synthetic root once groups are done
        const teamCol = isGroup ? '#1f7fc4' : oppColor(n.last.opp.name);
        const clickable = n.depth > 0;
        const oppName = isKORoot ? 'Round of 32' : isGroup ? (M.remainingOpponent || 'group') : n.last.opp.name;
        // ring fraction (green/blue portion). winP = CONDITIONAL win/advance at this node.
        const winP = nodeBeat(n.path, M);
        // Number in the hole = probability vs the PARENT node. The root shows none.
        const lc = !isGroup && lowConf(n.last.reachP);
        const numLabel = isRoot ? '' : pct(n.condParent || 0) + (lc ? '*' : '');
        const deg = Math.round(winP * 360);
        const ring = isGroup
          ? 'conic-gradient(#1f7fc4 0deg ' + deg + 'deg, rgba(140,175,225,.20) ' + deg + 'deg 360deg)'
          : 'conic-gradient(#2ea043 0deg ' + deg + 'deg, #7c3a44 ' + deg + 'deg 360deg)';
        const tip = (isKORoot
          ? (M.advance > 0
             ? state.country + ' in the knockout bracket — click a node to explore the possible paths'
             : state.country + ' were eliminated in the group stage')
          : isGroup
          ? (state.country + ' advance from ' + (M.groupName || 'the group') + ': ' + pct(M.advance) + ' (out ' + pct(1 - M.advance) + ') — final game vs ' + oppName)
          : (state.country + ' vs ' + oppName + ' — win ' + pct(winP) + ', lose ' + pct(1 - winP)
             + (n.condParent != null ? ' · ' + pct(n.condParent) + ' chance from the previous match' : '')))
          + (lc ? ' · * few simulations reached here — indicative only' : '');
        const hole = r * 0.62;            // donut hole radius
        const wfs = Math.max(9, hole * 0.7);   // number font
        const showName = r >= 27;         // only big nodes have room for the name
        const holeKids = [
          el('div', { style: { fontFamily: "'IBM Plex Mono',monospace", letterSpacing: '.04em', fontSize: Math.max(7, hole * 0.34) + 'px', color: '#9fb4d6', lineHeight: '1' }, text: lab.tag })
        ];
        if (showName) holeKids.push(el('div', { style: { fontWeight: '700', lineHeight: '1', fontSize: Math.max(8, hole * 0.42) + 'px', marginTop: '1px', color: teamCol, maxWidth: (hole * 1.8) + 'px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }, text: oppName }));
        if (numLabel) holeKids.push(el('div', { style: { fontFamily: "'Archivo',sans-serif", fontWeight: '800', fontSize: wfs + 'px', marginTop: '1px', color: '#eaf1fb', lineHeight: '1' }, text: numLabel }));
        const node = el('div', {
          title: tip,
          onclick: clickable ? function () { rerootTree(n.path); } : null,
          style: {
            position: 'absolute', left: p.x + 'px', top: p.y + 'px', width: (r * 2) + 'px', height: (r * 2) + 'px',
            marginLeft: (-r) + 'px', marginTop: (-r) + 'px', borderRadius: '50%',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            cursor: clickable ? 'pointer' : 'default',
            background: ring,
            border: isRoot ? '2.5px solid #FECC00' : '1px solid ' + teamCol,
            boxShadow: isRoot ? '0 0 24px rgba(254,204,0,.4)' : '0 10px 26px -10px ' + teamCol,
            transition: 'all .45s cubic-bezier(.34,1.3,.5,1)', zIndex: isRoot ? 5 : 3, userSelect: 'none'
          }
        }, [
          el('div', {
            style: {
              position: 'absolute', width: (hole * 2) + 'px', height: (hole * 2) + 'px', borderRadius: '50%',
              background: '#0b1d3c', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center'
            }
          }, holeKids)
        ]);
        anim.appendChild(node);
      }
    }

    // back button above the root
    if (st.treeRoot.length > 1) {
      const rr = 62, rx = pos[0].x, ry = pos[0].y;
      addBackButton(wrap, M, st.treeRoot, rx, ry - rr - 46, function () { rerootTree(st.treeRoot.slice(0, -1)); });
    }
  }

  // ---------- PIE EXPLORER ----------
  function buildPie(anim, wrap, M, st, activePath, activeLast) {
    const cx = 575, cy = 270, D = 300, Rpx = D / 2;
    const last = activeLast;
    const lab = nodeLabel(last, M);

    const donutWrap = el('div', { style: { position: 'absolute', left: (cx - Rpx) + 'px', top: (cy - Rpx) + 'px', width: D + 'px', height: D + 'px', transition: 'all .4s ease' } });
    const svgNS = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(svgNS, 'svg');
    svg.setAttribute('viewBox', '0 0 100 100');
    svg.setAttribute('style', 'width:100%;height:100%;overflow:visible;display:block;');
    donutWrap.appendChild(svg);

    const labels = [];

    if (last.round < 6) {
      const kids = childrenOfRoot(activePath, M).filter(c => c.condP >= PRUNE_PIE);
      let a0 = -Math.PI / 2;
      for (const c of kids) {
        const a1 = a0 + 2 * Math.PI * c.condP;
        const mid = (a0 + a1) / 2;
        const isOpp = c.kind === 'opp' || c.kind === 'champ';
        const col = c.kind === 'champ' ? '#FECC00' : c.kind === 'lose' ? '#7c3a44' : oppColor(c.opp.name);
        const onSlice = isOpp ? function () {
          if (c.kind === 'champ') drillPie(activePath.concat([{ round: 6, opp: null }]));
          else drillPie(activePath.concat([{ round: c.round, opp: c.opp }]));
        } : null;

        const path = document.createElementNS(svgNS, 'path');
        path.setAttribute('data-slice', '1');
        path.setAttribute('d', arcPath(a0, a1, 46, 27));
        path.setAttribute('style', 'fill:' + col + ';stroke:#06122c;stroke-width:1.4px;stroke-linejoin:round;cursor:' + (isOpp ? 'pointer' : 'default') + ';opacity:' + (isOpp ? 0.95 : 0.7) + ';');
        if (onSlice) path.addEventListener('click', onSlice);
        svg.appendChild(path);

        // outside label
        const lr = Rpx + 58, lx = cx + lr * Math.cos(mid), ly = cy + lr * Math.sin(mid);
        const rightSide = Math.cos(mid) >= 0;
        const nm = c.kind === 'champ' ? 'Champions ★' : c.kind === 'lose' ? (c.label || 'Eliminated') : c.opp.name;
        const beat = c.kind === 'opp' ? (c.beatProb || 0) : 0;
        const lc = c.kind === 'opp' && lowConf(c.reachP);
        const sub = (c.kind === 'opp' ? ('face ' + pct(c.condP) + ' · beat ' + pct(beat)) : pct(c.condP)) + (lc ? '*' : '');
        // hover tooltip on the slice (shows the legend / team name)
        const titleEl = document.createElementNS(svgNS, 'title');
        titleEl.textContent = (c.kind === 'opp' ? (nm + ' — face ' + pct(c.condP) + ' · beat ' + pct(beat)) : (nm + ' — ' + pct(c.condP)))
          + (lc ? ' · * few simulations reached here — indicative only' : '');
        path.appendChild(titleEl);
        // For small slices the face/beat line just clutters — drop it below 2.5%
        // (still available on hover via the slice tooltip). Keep the team name.
        const labelKids = [
          el('div', { style: { display: 'flex', alignItems: 'center', gap: '7px', justifyContent: rightSide ? 'flex-start' : 'flex-end' } }, [
            el('div', { style: { width: '9px', height: '9px', borderRadius: '50%', background: col } }),
            el('div', { style: { fontSize: '13px', fontWeight: '700', color: '#eaf1fb' }, text: nm })
          ])
        ];
        if (c.condP >= 0.025) {
          labelKids.push(el('div', { style: { fontFamily: "'IBM Plex Mono',monospace", fontSize: '11px', color: '#9fb4d6', marginTop: '2px' }, text: sub }));
        }
        labels.push(el('div', {
          onclick: onSlice,
          style: {
            position: 'absolute', left: lx + 'px', top: ly + 'px',
            transform: 'translate(' + (rightSide ? '0' : '-100%') + ', -50%)',
            width: '150px', textAlign: rightSide ? 'left' : 'right', cursor: isOpp ? 'pointer' : 'default'
          }
        }, labelKids));
        a0 = a1;
      }
    } else {
      // champion terminal node — full gold donut
      const path = document.createElementNS(svgNS, 'path');
      path.setAttribute('data-slice', '1');
      path.setAttribute('d', arcPath(-Math.PI / 2, 1.5 * Math.PI, 46, 27));
      path.setAttribute('style', 'fill:#FECC00;stroke:#06122c;stroke-width:1.4px;cursor:default;fill-rule:evenodd;');
      svg.appendChild(path);
    }

    // center hole
    let centerTag, centerName, centerSub = '';
    if (last.round === -1) { centerTag = 'Knockouts'; centerName = 'Round of 32'; centerSub = 'Advance ' + pct(M.advance); }
    else if (last.round === 0) { centerTag = 'Final group game'; centerName = 'vs ' + (M.remainingOpponent || '?'); centerSub = 'Advance ' + pct(M.advance); }
    else if (last.round === 6) { centerTag = 'World Cup'; centerName = 'Champions ★'; centerSub = state.country + ' are world champions'; }
    else {
      centerTag = ROUNDS[last.round - 1];
      centerName = 'vs ' + last.opp.name;
      centerSub = 'Win ' + pct(nodeBeat(activePath, M));
    }
    const center = el('div', {
      style: { position: 'absolute', inset: '0', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center', pointerEvents: 'none', padding: '0 18px' }
    }, [
      el('div', { style: { fontFamily: "'IBM Plex Mono',monospace", fontSize: '11px', letterSpacing: '.1em', color: '#9fb4d6', textTransform: 'uppercase' }, text: centerTag }),
      el('div', { style: { fontFamily: "'Archivo',sans-serif", fontWeight: '800', fontSize: '22px', lineHeight: '1.05', marginTop: '3px' }, text: centerName }),
      el('div', { style: { fontFamily: "'IBM Plex Mono',monospace", fontSize: '12px', color: '#FECC00', marginTop: '4px' }, text: centerSub })
    ]);
    donutWrap.appendChild(center);

    anim.appendChild(donutWrap);
    labels.forEach(l => anim.appendChild(l));

    if (st.piePath.length > 1) {
      addBackButton(wrap, M, st.piePath, cx, cy - Rpx - 50, function () { drillPie(st.piePath.slice(0, -1)); });
    }
  }

  // ---------- BRACKET ----------
  // The full 32-team knockout draw (R32 -> Final), a global static view (not a
  // drilldown). Row (y) position is computed bottom-up the same way the tree
  // does: R32 matches get sequential slots, every later match's slot is the
  // average of the two matches that feed it (DATA.bracket[].feedsFrom).
  const BRACKET_ROUNDS = ['R32', 'R16', 'QF', 'SF', 'F'];

  function buildBracket(anim, st) {
    const byNo = {};
    DATA.bracket.forEach(m => { byNo[m.no] = m; });
    const rounds = BRACKET_ROUNDS.map(r => DATA.bracket.filter(m => m.round === r).sort((a, b) => a.no - b.no));

    const H = 540, colW = 224, HEADER_H = 26;
    const slot = {};
    let leafCount = 0;
    function slotOf(m) {
      if (slot[m.no] != null) return slot[m.no];
      const feeds = m.feedsFrom.filter(n => n != null).map(n => byNo[n]).filter(Boolean);
      slot[m.no] = feeds.length ? feeds.reduce((sum, f) => sum + slotOf(f), 0) / feeds.length : leafCount++;
      return slot[m.no];
    }
    DATA.bracket.forEach(slotOf);

    // Fit ALL leaf rows (16, fixed) inside the stage's fixed height exactly —
    // .stagearea clips overflow, so the card height must shrink to the grid,
    // not the other way around.
    const rowH = (H - HEADER_H) / Math.max(leafCount, 1);
    const cardH = Math.max(20, rowH - 5);
    const xFor = ri => 16 + ri * colW;
    const yFor = m => HEADER_H + slot[m.no] * rowH + rowH / 2;
    const pos = {};
    rounds.forEach((ms, ri) => ms.forEach(m => { pos[m.no] = { x: xFor(ri), y: yFor(m) }; }));

    // connector lines: each match -> its (up to two) feeder matches
    DATA.bracket.forEach(m => {
      const p = pos[m.no]; if (!p) return;
      m.feedsFrom.forEach(n => {
        if (n == null || !pos[n]) return;
        const q = pos[n];
        const dx = p.x - q.x, dy = p.y - q.y, len = Math.hypot(dx, dy), ang = Math.atan2(dy, dx) * 180 / Math.PI;
        anim.appendChild(el('div', {
          style: {
            position: 'absolute', left: q.x + 'px', top: q.y + 'px', width: len + 'px', height: '1.5px',
            transformOrigin: '0 50%', transform: 'rotate(' + ang + 'deg)', background: 'rgba(120,165,220,.35)', zIndex: 1
          }
        }));
      });
    });

    // round headers
    rounds.forEach((ms, ri) => {
      if (!ms.length) return;
      anim.appendChild(el('div', {
        style: {
          position: 'absolute', left: xFor(ri) + 'px', top: '0px', width: (colW - 34) + 'px',
          fontFamily: "'IBM Plex Mono',monospace", fontSize: '10px', letterSpacing: '.14em',
          color: '#7b96bf', textTransform: 'uppercase'
        }, text: ROUND_FULL[BRACKET_ROUNDS[ri]]
      }));
    });

    // match cards — row height is half of cardH (two rows per card), so both
    // padding and font shrink with it to stay legible without overflowing.
    const rowPx = cardH / 2;
    const fontPx = Math.max(8, Math.min(11, rowPx * 0.42));
    const padY = Math.max(0, (rowPx - fontPx) / 2 - 1);
    const row = (name, score, isWinner, hint, isMe) => el('div', {
      style: {
        display: 'flex', alignItems: 'center', gap: '5px', padding: padY + 'px 7px', fontSize: fontPx + 'px',
        lineHeight: '1.1', fontWeight: isWinner ? '700' : '500',
        color: isWinner ? '#eaf1fb' : (name ? '#9fb4d6' : '#5c7093'),
        background: isMe ? 'rgba(254,204,0,.14)' : 'transparent'
      }
    }, [
      el('div', { style: { width: '6px', height: '6px', borderRadius: '50%', background: name ? oppColor(name) : 'transparent', flex: '0 0 auto' } }),
      el('div', { style: { flex: '1 1 auto', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }, text: name || hint || 'TBD' }),
      el('div', { style: { fontFamily: "'IBM Plex Mono',monospace", flex: '0 0 auto' }, text: score != null ? String(score) : '' })
    ]);

    DATA.bracket.forEach(m => {
      const p = pos[m.no]; if (!p) return;
      const involvesTeam = m.teamA === st.country || m.teamB === st.country;
      const card = el('div', {
        title: ROUND_FULL[m.round] + (m.teamA && m.teamB ? ': ' + m.teamA + ' vs ' + m.teamB : ''),
        style: {
          position: 'absolute', left: p.x + 'px', top: (p.y - cardH) + 'px', width: (colW - 34) + 'px',
          borderRadius: '8px', overflow: 'hidden', background: '#0e2044',
          border: '1px solid ' + (involvesTeam ? 'rgba(254,204,0,.55)' : 'rgba(140,175,225,.16)'),
          boxShadow: involvesTeam ? '0 0 14px rgba(254,204,0,.25)' : 'none', zIndex: 3
        }
      }, [
        row(m.teamA, m.scoreA, m.winner === m.teamA, m.hintA, m.teamA === st.country),
        el('div', { style: { height: '1px', background: 'rgba(140,175,225,.14)' } }),
        row(m.teamB, m.scoreB, m.winner === m.teamB, m.hintB, m.teamB === st.country)
      ]);
      anim.appendChild(card);
    });
  }

  // gold "Back to {parent}" button
  function addBackButton(wrap, M, path, x, y, handler) {
    const parent = path[path.length - 2];
    const pl = parent.round === -1 ? 'Knockouts' : parent.round === 0 ? (M.remainingOpponent || 'Group') : parent.round === 6 ? 'Champions' : parent.opp.name;
    const btn = el('button', {
      onclick: handler,
      style: {
        position: 'absolute', left: x + 'px', top: y + 'px', marginLeft: '-84px',
        width: '168px', height: '40px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '7px',
        background: '#FECC00', color: '#1a1205', border: 'none', borderRadius: '21px',
        fontFamily: "'IBM Plex Sans'", fontSize: '13px', fontWeight: '700', cursor: 'pointer',
        boxShadow: '0 8px 20px -5px rgba(0,0,0,.55)', zIndex: 40
      }
    }, [
      el('span', { style: { fontSize: '15px', lineHeight: '1' }, text: '↑' }),
      document.createTextNode(' Back to ' + pl)
    ]);
    wrap.appendChild(btn);
  }

  // ===================== fit-to-container scaling =====================
  function fit() {
    const elv = document.querySelector('[data-stagearea]');
    if (!elv) return;
    const s = Math.min((elv.clientWidth - 30) / 1150, (elv.clientHeight - 26) / 540);
    const v = Math.max(0.42, Math.min(s, 1.3));
    if (Math.abs(v - state.scale) > 0.004) {
      state.scale = v;
      const w = elv.querySelector('div[style*="zoom"]') || elv.firstElementChild;
      if (w) w.style.zoom = v; // adjust in place to avoid a full re-render loop
    }
  }
  window.addEventListener('resize', fit);

  // ResizeObserver on the stage area (re-attached after each render via the
  // observer below, which watches #app's subtree implicitly through resize).
  let ro = null;
  function attachObserver() {
    const elv = document.querySelector('[data-stagearea]');
    if (elv && window.ResizeObserver) {
      if (ro) ro.disconnect();
      ro = new ResizeObserver(fit);
      ro.observe(elv);
    }
  }
  const _origRender = render;
  render = function () { _origRender(); attachObserver(); };

  // ===================== boot =====================
  resetPaths();
  render();
  setTimeout(fit, 60);
  requestAnimationFrame(function () { fit(); requestAnimationFrame(fit); });

})();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
