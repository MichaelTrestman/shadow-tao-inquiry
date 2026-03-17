"""
known_holders_by_stakeweight.py

Combines known_holders.json (free balances, identities, roles) with
validator_stake_weight.json (per-hotkey stake) to rank known entities by
total economic weight: free_tao + validator_stake_tao.

Uses existing JSON data — no RPC or API calls required.

Outputs:
  known_holders_stakeweight_report.txt
"""

import json
from collections import defaultdict

KNOWN_JSON     = "known_holders.json"
STAKE_JSON     = "validator_stake_weight.json"
OUT_REPORT     = "known_holders_stakeweight_report.txt"


# ── Load known holders ──────────────────────────────────────────────────────
known = json.load(open(KNOWN_JSON))
known_by_ck = {r["ss58"]: r for r in known}
print(f"Loaded {len(known)} known holder records")

# ── Load validator stake-weight and aggregate per coldkey ───────────────────
stake_data = json.load(open(STAKE_JSON))
delegates  = stake_data["delegates"]
print(f"Loaded {len(delegates)} delegate (hotkey) records")

# Sum all hotkey stakes per coldkey
ck_stake = defaultdict(float)
ck_hotkey_count = defaultdict(int)
for d in delegates:
    ck = d["coldkey"]
    ck_stake[ck]        += d["total_stake_tao"]
    ck_hotkey_count[ck] += 1

print(f"  {len(ck_stake)} unique validator coldkeys with stake")

# ── Build combined records ───────────────────────────────────────────────────
records = []
for r in known:
    ck          = r["ss58"]
    free_tao    = r["free_tao"]
    stake_tao   = ck_stake.get(ck, 0.0)
    combined    = free_tao + stake_tao
    name        = r["identity"].get("name", "") if r.get("identity") else ""

    roles = []
    if r.get("is_delegate_owner"): roles.append("validator")
    if r.get("is_sn_owner"):       roles.append(f"sn_owner({r['owned_subnets']})")
    role_str = ",".join(roles) if roles else ("identity_only" if r.get("has_identity") else "role_only")

    records.append({
        "ss58":         ck,
        "name":         name,
        "free_tao":     free_tao,
        "stake_tao":    stake_tao,
        "combined_tao": combined,
        "role":         role_str,
        "hotkey_count": ck_hotkey_count.get(ck, 0),
        "has_identity": r.get("has_identity", False),
        "is_validator": r.get("is_delegate_owner", False),
        "is_sn_owner":  r.get("is_sn_owner", False),
    })

records.sort(key=lambda x: -x["combined_tao"])

# ── Report ───────────────────────────────────────────────────────────────────
lines = []
lines.append("=" * 80)
lines.append("KNOWN HOLDER ANALYSIS — By Combined Stakeweight (Free + Validator Stake)")
lines.append(f"Known entities: {len(records)}  |  Source: known_holders.json + validator_stake_weight.json")
lines.append("=" * 80)
lines.append("")

# All known entities ranked by combined weight
lines.append(f"--- TOP 100 KNOWN HOLDERS BY COMBINED WEIGHT (n={len(records)} total) ---")
lines.append(f"{'Name':<30} {'Free TAO':>12} {'Stake TAO':>13} {'Combined':>13} {'HKs':>4}  Role")
lines.append("-" * 100)
for r in records[:100]:
    name = (r["name"] or "(no identity)")[:28]
    lines.append(
        f"  {name:<28} {r['free_tao']:>12,.0f} {r['stake_tao']:>13,.0f} "
        f"{r['combined_tao']:>13,.0f} {r['hotkey_count']:>4}  {r['role']}"
    )

# Named holders only, by combined weight
named = [r for r in records if r["has_identity"]]
lines.append("")
lines.append(f"--- NAMED HOLDERS BY COMBINED WEIGHT (n={len(named)} total) ---")
lines.append(f"{'Name':<30} {'Free TAO':>12} {'Stake TAO':>13} {'Combined':>13} {'HKs':>4}  Role")
lines.append("-" * 100)
for r in named[:80]:
    name = r["name"][:28]
    lines.append(
        f"  {name:<28} {r['free_tao']:>12,.0f} {r['stake_tao']:>13,.0f} "
        f"{r['combined_tao']:>13,.0f} {r['hotkey_count']:>4}  {r['role']}"
    )

# Validators only, by stake-weight
validators = [r for r in records if r["is_validator"]]
validators.sort(key=lambda x: -x["stake_tao"])
lines.append("")
lines.append(f"--- VALIDATORS BY STAKE-WEIGHT (n={len(validators)}) ---")
lines.append(f"{'Name':<30} {'Free TAO':>12} {'Stake TAO':>13} {'Combined':>13} {'HKs':>4}")
lines.append("-" * 80)
for r in validators[:40]:
    name = (r["name"] or "(no identity)")[:28]
    lines.append(
        f"  {name:<28} {r['free_tao']:>12,.0f} {r['stake_tao']:>13,.0f} "
        f"{r['combined_tao']:>13,.0f} {r['hotkey_count']:>4}"
    )

# SN owners by combined weight
sn_owners = [r for r in records if r["is_sn_owner"]]
sn_owners.sort(key=lambda x: -x["combined_tao"])
lines.append("")
lines.append(f"--- SUBNET OWNERS BY COMBINED WEIGHT (n={len(sn_owners)}) ---")
lines.append(f"{'Name':<30} {'Free TAO':>12} {'Stake TAO':>13} {'Combined':>13}  Role")
lines.append("-" * 85)
for r in sn_owners[:30]:
    name = (r["name"] or "(no identity)")[:28]
    lines.append(
        f"  {name:<28} {r['free_tao']:>12,.0f} {r['stake_tao']:>13,.0f} "
        f"{r['combined_tao']:>13,.0f}  {r['role']}"
    )

# Summary
total_free    = sum(r["free_tao"]    for r in records)
total_stake   = sum(r["stake_tao"]   for r in records)
total_combined = sum(r["combined_tao"] for r in records)
lines.append("")
lines.append("--- TOTALS ---")
lines.append(f"  Total free TAO (known entities):     {total_free:>14,.0f}")
lines.append(f"  Total stake TAO (known entities):    {total_stake:>14,.0f}")
lines.append(f"  Total combined (known entities):     {total_combined:>14,.0f}")
lines.append("")
lines.append("Note: stake_tao = sum of DelegateInfo.total_stake across all owned hotkeys.")
lines.append("      free_tao from System.Account.data.free at block ~7,738,261.")

report = "\n".join(lines)
print(report)
with open(OUT_REPORT, "w") as f:
    f.write(report + "\n")
print(f"\nSaved to {OUT_REPORT}")
