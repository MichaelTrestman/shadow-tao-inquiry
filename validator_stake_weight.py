"""
Validator stake-weight query.

In Bittensor dTAO, stake lives in per-subnet alpha pools, not in a single
global ledger. TotalColdkeyStake is deprecated/incomplete. The authoritative
source for a validator's stake-weight is DelegateInfo.total_stake, which is
a dict {netuid: stake_amount} returned by the get_delegates() RPC call.

This script:
  1. Fetches all delegates via sub.get_delegates()
  2. For each delegate, sums total_stake across all subnets to get total
     stake-weight for that hotkey
  3. Maps hotkey -> coldkey owner
  4. Cross-references with known_holders.json to attach identity names
  5. Outputs top validators by stake-weight + specific named validators of
     interest (Kraken, OTF, const, etc.)

Output:
  validator_stake_weight.json  — full records
  validator_stake_weight_report.txt  — human-readable

Note on units: DelegateInfo.total_stake values come from the SDK's
Balance objects. We strip formatting and convert to float. If values
appear larger than expected, check whether the SDK is returning rao
(divide by 1e9) or TAO (use as-is). We detect this by checking whether
the top validator stake is plausible (should be hundreds of thousands of
TAO, not billions).
"""

import json
import time

import bittensor as bt

OUT_JSON   = "validator_stake_weight.json"
OUT_REPORT = "validator_stake_weight_report.txt"
KNOWN_JSON = "known_holders.json"

RAO = 1_000_000_000

sub = bt.Subtensor(network="finney")
print(f"Connected at block {sub.get_current_block():,}")

# ── Load known holders for identity lookup ─────────────────────────────────
known_raw  = json.load(open(KNOWN_JSON))
known_by_ss58 = {r["ss58"]: r for r in known_raw}
print(f"Loaded {len(known_by_ss58)} known holders")

# ── Fetch all delegate info ────────────────────────────────────────────────
print("\nFetching delegates...")
delegates = sub.get_delegates()
print(f"  {len(delegates)} delegates")

# ── Build stake-weight per hotkey ─────────────────────────────────────────
# DelegateInfo.total_stake is a dict {netuid: Balance} in dTAO
# Balance objects can be formatted strings like "1,234.567τ" or numeric
def to_float(val) -> float:
    """Convert a Balance or numeric value to float TAO."""
    s = str(val).replace(",", "").replace("τ", "").replace("T", "").strip()
    try:
        return float(s)
    except Exception:
        return 0.0

records = []
for d in delegates:
    total_stake = 0.0
    if isinstance(d.total_stake, dict):
        for bal in d.total_stake.values():
            total_stake += to_float(bal)
    elif d.total_stake:
        total_stake = to_float(d.total_stake)

    hotkey  = d.hotkey_ss58
    coldkey = d.owner_ss58

    # Identity from known_holders (which indexes by coldkey)
    k_info = known_by_ss58.get(coldkey, {})
    identity = k_info.get("identity", {})
    name = identity.get("name", "") if identity else ""

    records.append({
        "hotkey":       hotkey,
        "coldkey":      coldkey,
        "name":         name or "(no identity)",
        "total_stake_tao": total_stake,
    })

records.sort(key=lambda x: -x["total_stake_tao"])

# ── Sanity check on units ──────────────────────────────────────────────────
# If the top validator has stake > 1e9, values are likely in rao, not TAO
top_stake = records[0]["total_stake_tao"] if records else 0
if top_stake > 1_000_000_000:
    print(f"  WARNING: top stake = {top_stake:,.0f} — looks like rao, dividing by 1e9")
    for r in records:
        r["total_stake_tao"] /= RAO
elif top_stake < 1:
    print(f"  WARNING: top stake = {top_stake} — suspiciously low, may be zero/empty")
else:
    print(f"  Top stake: {top_stake:,.2f} TAO — units look correct")

# ── Save JSON ──────────────────────────────────────────────────────────────
with open(OUT_JSON, "w") as f:
    json.dump({"query_block": sub.get_current_block(), "delegates": records}, f, indent=2)
print(f"\nSaved {len(records)} records to {OUT_JSON}")

# ── Generate report ────────────────────────────────────────────────────────
lines = [
    "=" * 72,
    "VALIDATOR STAKE-WEIGHT — Bittensor Finney (dTAO)",
    "Source: DelegateInfo.total_stake (sum across all subnets)",
    "=" * 72,
    "",
]

# Top 30 by stake-weight
lines.append("--- TOP 30 VALIDATORS BY STAKE-WEIGHT ---")
lines.append(f"{'Stake TAO':>14}  {'Name':<30}  Coldkey")
lines.append("-" * 80)
for r in records[:30]:
    lines.append(f"  {r['total_stake_tao']:>12,.2f}  {r['name']:<30}  {r['coldkey']}")

# Specific validators of interest
lines.append("")
lines.append("--- VALIDATORS OF INTEREST ---")
interest = {
    "5FHxxe8ZKYaNmGcSLdG5ekxXeZDhQnk9cbpHdsJW8RunGpSs": "Kraken (coldkey)",
    "5HBtpwxuGNL1gwzwomwR7sjwUt8WXYSuWcLYN6f9KpTZkP4k": "Opentensor Foundation (coldkey)",
    "5Fc3ZZQAYB3SPXKcFnd1WJeyQvArSZZeB6LU1rb7zvQ6XvDh": "const (coldkey)",
    "5GH2aUTMRUh1RprCgH4x3tRyCaKeUi5BfmYCfs1NARA8R54n": "Const public coldkey",
    "5FqACMtcegZxxopgu1g7TgyrnyD8skurr9QDPLPhxNQzsThe": "Owner51",
    "5FCSevLkofmKZRixMawp6jyyjBty1AeSCLa7N5Fv892DYkXX": "Sportstensor",
}
coldkey_lookup = {r["coldkey"]: r for r in records}
for ck, label in interest.items():
    r = coldkey_lookup.get(ck)
    if r:
        lines.append(f"  {r['total_stake_tao']:>12,.2f} TAO  {label}  ({ck})")
    else:
        lines.append(f"  {'(not a delegate)':>12}        {label}  ({ck})")

# Summary stats
total_delegated = sum(r["total_stake_tao"] for r in records)
lines.append("")
lines.append(f"Total delegated stake across all validators: {total_delegated:,.2f} TAO")
lines.append(f"Number of delegates: {len(records)}")

report = "\n".join(lines)
print("\n" + report)
with open(OUT_REPORT, "w") as f:
    f.write(report + "\n")
print(f"\nSaved report to {OUT_REPORT}")
