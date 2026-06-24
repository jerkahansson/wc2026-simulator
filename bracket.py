"""
WC2026 knockout bracket structure + group/third-place logic.

All slot wiring is the official, pre-published FIFA bracket (source:
en.wikipedia.org/wiki/2026_FIFA_World_Cup_knockout_stage). 48 teams, 12 groups
of 4. Top two of each group + the 8 best third-placed teams = 32 → Round of 32.

Slot tokens used in KO_MATCHES:
    "W<g>"  winner of group <g>           e.g. "WA"
    "R<g>"  runner-up of group <g>        e.g. "RB"
    "T<i>"  third-placed team assigned to the i-th winner-slot (see
            WINNER_SLOTS_FOR_THIRDS); resolved via the combination table
    "<n>W"  winner of match <n>           e.g. "74W"
    "<n>L"  loser of match <n>            e.g. "101L"  (3rd-place playoff)
"""

import json
import os

from copabet_picks import MATCHES

DIR = os.path.dirname(os.path.abspath(__file__))

HOSTS = {"USA", "Mexico", "Canada"}  # full home-advantage in their own country

# --- Groups, derived from the fixtures -------------------------------------
GROUPS = {}          # "A" -> [team, team, team, team] (order of first appearance)
for g, md, home, away, *_ in MATCHES:
    GROUPS.setdefault(g, [])
    for t in (home, away):
        if t not in GROUPS[g]:
            GROUPS[g].append(t)
GROUP_LETTERS = sorted(GROUPS)            # A..L
assert all(len(v) == 4 for v in GROUPS.values()), "every group must have 4 teams"
assert len(GROUP_LETTERS) == 12

# --- Third-place combination table -----------------------------------------
# Column order of the published table: the 8 group winners that face a third.
WINNER_SLOTS_FOR_THIRDS = ["A", "B", "D", "E", "G", "I", "K", "L"]

with open(os.path.join(DIR, "third_place_combinations.json"), encoding="utf-8") as f:
    _comb = json.load(f)
COMBINATIONS = _comb["map"]               # "ABCDEFGH" -> [3rd-group per winner slot]
assert _comb["winnerSlots"] == WINNER_SLOTS_FOR_THIRDS
assert len(COMBINATIONS) == 495


def third_place_assignment(qualified_third_groups):
    """Given the 8 group letters whose third-placed team advanced, return the
    list of third-place group letters in WINNER_SLOTS_FOR_THIRDS order
    (i.e. result[i] is the third-placed group that plays the i-th winner slot)."""
    key = "".join(sorted(qualified_third_groups))
    return COMBINATIONS[key]


# --- The 32 knockout matches (match_no -> (slotA, slotB)) -------------------
# T-index maps to WINNER_SLOTS_FOR_THIRDS: T0->A, T1->B, T2->D, T3->E,
# T4->G, T5->I, T6->K, T7->L.
KO_MATCHES = {
    # Round of 32
    73: ("RA", "RB"),
    74: ("WE", "T3"),
    75: ("WF", "RC"),
    76: ("WC", "RF"),
    77: ("WI", "T5"),
    78: ("RE", "RI"),
    79: ("WA", "T0"),
    80: ("WL", "T7"),
    81: ("WD", "T2"),
    82: ("WG", "T4"),
    83: ("RK", "RL"),
    84: ("WH", "RJ"),
    85: ("WB", "T1"),
    86: ("WJ", "RH"),
    87: ("WK", "T6"),
    88: ("RD", "RG"),
    # Round of 16
    89: ("74W", "77W"),
    90: ("73W", "75W"),
    91: ("76W", "78W"),
    92: ("79W", "80W"),
    93: ("83W", "84W"),
    94: ("81W", "82W"),
    95: ("86W", "88W"),
    96: ("85W", "87W"),
    # Quarter-finals
    97: ("89W", "90W"),
    98: ("93W", "94W"),
    99: ("91W", "92W"),
    100: ("95W", "96W"),
    # Semi-finals
    101: ("97W", "98W"),
    102: ("99W", "100W"),
    # Third-place playoff + Final
    103: ("101L", "102L"),
    104: ("101W", "102W"),
}

# Which match number corresponds to each round (for round-reach bookkeeping).
ROUND_OF = {}
for n in range(73, 89):
    ROUND_OF[n] = "R32"
for n in range(89, 97):
    ROUND_OF[n] = "R16"
for n in range(97, 101):
    ROUND_OF[n] = "QF"
for n in (101, 102):
    ROUND_OF[n] = "SF"
ROUND_OF[103] = "3P"
ROUND_OF[104] = "F"
