# data-pipeline/utils/canon_map.py
# Canonicalization helpers for ability keywords / traits.
# - CANON_MAP is the default dictionary used by the scraper's normalizer.
# - KEEP_UPPER contains short acronyms that should remain uppercase.
# - load_canon_map(path) lets you extend/override the map from a JSON file.

from __future__ import annotations
from typing import Dict, Iterable, Tuple, Union
import json

# Keep short acronyms uppercased (e.g., "X", "AI", "ISO")
KEEP_UPPER: set[str] = {"AI", "ISO", "X"}

# Default canonical map.
# Keys MUST be UPPERCASE and COLLAPSED (no spaces/underscores/dashes).
# Values are the canonical human-facing strings you want displayed/stored.
CANON_MAP: Dict[str, str] = {
    # ── Factions / teams ────────────────────────────────────────────────────────
    "HELLFIRECLUB": "Hellfire Club",
    "IMMORTALXMEN": "Immortal X Men",
    "ACCURSED": "Accursed",
    "HYDRA": "Hydra",
    "AIM": "A.I.M.",
    "DARKHOLD": "Darkhold",
    "INHUMANS": "Inhumans",
    "XFORCE": "X-Force",
    "XMEN": "X-Men",
    "UNCANNYXMEN": "Uncanny X-Men",
    "YOUNGAVENGERS": "Young Avengers",

    # ── Modes / contexts ────────────────────────────────────────────────────────
    "CRUCIBLE": "Crucible",
    "CRUCIBLEOFFENSE": "Crucible Offense",
    "CRUCIBLEDEFENSE": "Crucible Defense",
    "WAROFFENSE": "War Offense",
    "WARDEFENSE": "War Defense",
    "ARENA": "Arena",
    "RAIDS": "Raids",

    # ── Roles ──────────────────────────────────────────────────────────────────
    "PROTECTOR": "Protector",
    "SUPPORT": "Support",
    "CONTROLLER": "Controller",
    "BLASTER": "Blaster",
    "BRAWLER": "Brawler",

    # ── Status effects / mechanics ─────────────────────────────────────────────
    "DEFENSEUP": "Defense Up",
    "DEFENSEDOWN": "Defense Down",
    "OFFENSEUP": "Offense Up",
    "OFFENSEDOWN": "Offense Down",
    "HEALBLOCK": "Heal Block",
    "ABILITYBLOCK": "Ability Block",
    "IMMUNITY": "Immunity",
    "SAFEGUARD": "Safeguard",
    "BLEED": "Bleed",
    "BLIND": "Blind",
    "SLOW": "Slow",
    "STUN": "Stun",
    "TAUNT": "Taunt",
    "TRAUMA": "Trauma",
    "DISRUPTED": "Disrupted",
    "VULNERABLE": "Vulnerable",
    "BARRIER": "Barrier",
    "STEALTH": "Stealth",
    "DEATHPROOF": "Deathproof",
    "REGENERATION": "Regeneration",
    "EVADE": "Evade",
    "COUNTER": "Counter",
    "CHARGED": "Charged",

    # ── Turn meter / speed ─────────────────────────────────────────────────────
    "SPEEDUP": "Speed Up",
    "SPEEDDOWN": "Speed Down",
    "SPEEDBAR": "Speed Bar",
}

def _items(data: Union[dict, Iterable[Tuple[str, str]]]) -> Iterable[Tuple[str, str]]:
    """Yield (key, value) pairs from either a dict or a list of 2-tuples."""
    if isinstance(data, dict):
        return data.items()
    return data  # assume list of pairs

def load_canon_map(path: str) -> Dict[str, str]:
    """
    Load a JSON file and return a dict with UPPERCASE, space-collapsed keys.

    Accepted JSON formats:
      1) Object/dict:
         { "HELLFIRECLUB": "Hellfire Club", "DEFENSEUP": "Defense Up" }
      2) Array of pairs:
         [["HELLFIRECLUB","Hellfire Club"], ["DEFENSEUP","Defense Up"]]
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    out: Dict[str, str] = {}
    for k, v in _items(data):
        if not k or v is None:
            continue
        key = str(k).upper().replace(" ", "")
        out[key] = str(v)
    return out
