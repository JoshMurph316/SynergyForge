# tests/test_effects_shape.py
import json, pathlib, re

p = pathlib.Path("data-pipeline/output/effect_data.json")
j = json.loads(p.read_text())

names = [e["name"] for e in j["effects"]]
ids   = [e["id"] for e in j["effects"]]

# 1) No junk labels
assert all(not n.lower().startswith(("expires:", "opposite:", "duration:")) for n in names)

# 2) No section headers
assert all(n.upper() not in {"POSITIVE EFFECTS","NEGATIVE EFFECTS","OTHER EFFECTS"} for n in names)

# 3) Opposites present for key pairs
byid = {e["id"]: e for e in j["effects"]}
def opp(a,b): return byid.get(a,{}).get("opposite")==b and byid.get(b,{}).get("opposite")==a
assert opp("DEFENSE_UP","DEFENSE_DOWN")
assert opp("OFFENSE_UP","OFFENSE_DOWN")
assert opp("SPEED_UP","SLOW")

# 4) Must-have modern effects
must = {"SAFEGUARD","TRAUMA","EXPOSED","EXHAUSTED","ISO8_VULNERABLE","REVIVE_ONCE"}
missing = must - set(ids)
# Relax naming difference for ISO-8
missing -= {"ISO8_VULNERABLE"} if any("ISO" in i and "VULNERABLE" in i for i in ids) else set()
assert not missing, f"Missing: {missing}"
print("OK - effects look sane. Total:", len(ids))
