"""
Top 100 TAO holders by total (free + staked) — role and identity analysis.

For each wallet in the top 100:
  - Total TAO (free balance + staked across all hotkeys/subnets)
  - Role: validator / miner / subnet_owner / delegator / pure_holder
    (a wallet can have multiple roles)
  - On-chain identity

Role definitions in bittensor:
  - VALIDATOR: coldkey owns a hotkey that has validator_permit=True on any netuid
  - MINER:     coldkey owns a hotkey registered on any subnet without validator_permit
  - SUBNET_OWNER: coldkey is owner_ss58 of any subnet
  - DELEGATE_VALIDATOR: coldkey appears as owner_ss58 in get_delegates()
    (registered as a delegate even if not personally validated — overlaps with VALIDATOR)
  - DELEGATOR: has staked TAO to hotkeys it doesn't own (i.e. nominating someone else)
  - PURE_HOLDER: none of the above

Output:
  top100_holders.jsonl       — full data per wallet
  top100_holders_report.txt  — human-readable table
"""

import ast
import json
import sys
import time
from pathlib import Path

import bittensor as bt
from scalecodec.utils.ss58 import ss58_encode

ACCOUNTS_FILE  = "finney_accounts.jsonl"
STAKING_FILE   = "finney_staking_cks.txt"
META_FILE      = "finney_meta.json"
OUT_JSONL      = "top100_holders.jsonl"
OUT_REPORT     = "top100_holders_report.txt"
SS58_FORMAT    = 42
TOP_N          = 100

for f in [ACCOUNTS_FILE, META_FILE]:
    if not Path(f).exists():
        print(f"ERROR: {f} not found. Run enumerate_wallets.py first.")
        sys.exit(1)

sub = bt.Subtensor(network="finney")
block = sub.get_current_block()
print(f"Connected at block {block:,}")

# ── Helpers ───────────────────────────────────────────────────────────────────

def tuple_str_to_ss58(s: str) -> str | None:
    try:
        return ss58_encode(bytes(ast.literal_eval(s)[0]), ss58_format=SS58_FORMAT)
    except Exception:
        return None

def get_identity(ss58: str) -> dict:
    try:
        r = sub.query("SubtensorModule", "IdentitiesV2", [ss58])
        if r and r.value:
            v = r.value
            return {"name": v.get("name",""), "url": v.get("url",""),
                    "description": v.get("description",""), "source": "IdentitiesV2"}
    except Exception:
        pass
    try:
        r = sub.query_identity(ss58)
        if r:
            return {"name": r.get("name",""), "url": r.get("web",""),
                    "description": r.get("description",""), "source": "query_identity"}
    except Exception:
        pass
    return {}

# ── Step 1: Load free balances, re-encode SS58 ───────────────────────────────
print("\nLoading free balances from accounts file...")
free_balances = {}   # ss58 -> free_tao
count = 0
failed = 0
with open(ACCOUNTS_FILE) as f:
    for line in f:
        w = json.loads(line)
        ss58 = tuple_str_to_ss58(w["ss58"])
        if ss58:
            free_balances[ss58] = w["free_tao"]
            count += 1
        else:
            failed += 1
print(f"  Loaded {count:,} accounts ({failed} encoding failures)")

# ── Step 2: Get staked amounts via TotalColdkeyStake storage map ──────────────
# In subtensor, TotalColdkeyStake maps coldkey -> u64 (total RAO staked)
print("\nFetching TotalColdkeyStake map...")
RAO = 1_000_000_000
staked_balances = {}   # ss58 -> staked_tao
stake_count = 0
try:
    for ck, amount in sub.query_map("SubtensorModule", "TotalColdkeyStake"):
        ss58 = tuple_str_to_ss58(str(ck)) if isinstance(ck, tuple) else str(ck)
        if ss58:
            staked_balances[ss58] = int(str(amount)) / RAO
            stake_count += 1
        if stake_count % 5000 == 0 and stake_count > 0:
            print(f"  {stake_count:,} staked coldkeys...", flush=True)
    print(f"  Done: {stake_count:,} coldkeys with stake via TotalColdkeyStake")
except Exception as e:
    print(f"  TotalColdkeyStake map failed ({e}), falling back to staking file...")
    # Fall back: mark all coldkeys from staking file as having stake > 0
    # We won't have exact amounts — flag for manual per-coldkey query later
    with open(STAKING_FILE) as f:
        for line in f:
            ck = line.strip()
            if ck:
                ss58 = tuple_str_to_ss58(ck) if ck.startswith("((") else ck
                if ss58:
                    staked_balances[ss58] = -1   # unknown amount
    print(f"  Fallback: {len(staked_balances):,} coldkeys flagged as stakers (amounts unknown)")

# ── Step 3: Rank by total TAO ─────────────────────────────────────────────────
print("\nRanking by total TAO (free + staked)...")
all_keys = set(free_balances) | set(staked_balances)
ranked = []
for ss58 in all_keys:
    free  = free_balances.get(ss58, 0.0)
    staked = staked_balances.get(ss58, 0.0)
    if staked < 0:
        staked = 0.0   # unknown, treat as 0 for ranking (conservative)
    ranked.append({"ss58": ss58, "free_tao": free, "staked_tao": staked,
                   "total_tao": free + staked})

ranked.sort(key=lambda x: x["total_tao"], reverse=True)
top100 = ranked[:TOP_N]
print(f"  Top 100 range: {top100[0]['total_tao']:,.0f} TAO → {top100[-1]['total_tao']:,.0f} TAO")

# ── Step 4: Build reference data (delegates, subnet owners) ──────────────────
print("\nFetching delegate registry...")
delegates = sub.get_delegates()
# Build: hotkey -> DelegateInfo, coldkey -> DelegateInfo
delegate_by_hotkey  = {d.hotkey_ss58: d for d in delegates}
delegate_by_coldkey = {d.owner_ss58: d  for d in delegates}
print(f"  {len(delegates):,} registered delegates")

print("Fetching all subnet info...")
all_subnets = sub.get_all_subnets_info()
# Build: owner coldkey -> list of netuids
subnet_owner_map = {}
for sn in all_subnets:
    if sn and sn.owner_ss58:
        subnet_owner_map.setdefault(sn.owner_ss58, []).append(sn.netuid)
print(f"  {len(all_subnets):,} subnets, {len(subnet_owner_map):,} unique owners")

# ── Step 5: Per-wallet enrichment ─────────────────────────────────────────────
print(f"\nEnriching top {TOP_N} wallets...")

for i, w in enumerate(top100):
    ss58 = w["ss58"]

    # Owned hotkeys
    try:
        hotkeys = sub.get_owned_hotkeys(ss58)
    except Exception:
        hotkeys = []
    w["owned_hotkeys"] = hotkeys

    # Subnet ownership
    w["owned_subnets"] = subnet_owner_map.get(ss58, [])

    # Delegate status
    if ss58 in delegate_by_coldkey:
        d = delegate_by_coldkey[ss58]
        w["is_delegate_owner"] = True
        w["delegate_hotkey"]   = d.hotkey_ss58
        w["delegate_permits"]  = d.validator_permits
        w["delegate_regs"]     = d.registrations
    else:
        w["is_delegate_owner"] = False
        w["delegate_hotkey"]   = None
        w["delegate_permits"]  = []
        w["delegate_regs"]     = []

    # For owned hotkeys, check validator_permit on each registered netuid
    is_validator = False
    is_miner     = False
    for hk in hotkeys:
        if hk in delegate_by_hotkey:
            d = delegate_by_hotkey[hk]
            if d.validator_permits:
                is_validator = True
            if d.registrations:
                is_miner = True   # registered anywhere (miner or validator)
        # Also check if the hotkey is in the delegate registry at all
        # If delegate + permits -> validator; if delegate + no permits -> registered miner/validator without permit

    # Fallback: if coldkey is_delegate_owner, it's a validator by definition
    if w["is_delegate_owner"] and w["delegate_permits"]:
        is_validator = True

    w["is_validator"] = is_validator
    w["is_miner"]     = is_miner and not is_validator   # pure miner only if no validator permit

    # Delegator: has stake but none of the hotkeys belong to them
    # i.e. staked_tao > 0 and no owned hotkeys with stake
    w["is_delegator"] = (w["staked_tao"] > 0 and not hotkeys
                         and not w["is_delegate_owner"])

    # Derive role label
    roles = []
    if is_validator or w["is_delegate_owner"]:
        roles.append("validator")
    if w["is_miner"]:
        roles.append("miner")
    if w["owned_subnets"]:
        roles.append("subnet_owner")
    if w["is_delegator"]:
        roles.append("delegator")
    if not roles:
        roles.append("pure_holder")
    w["roles"] = roles

    # Identity
    w["identity"] = get_identity(ss58)
    identity_name = w["identity"].get("name","") or "(no identity)"

    role_str = "+".join(roles)
    print(f"  {i+1:3d}. {ss58[:20]}...  {w['total_tao']:>12,.0f} TAO  [{role_str}]  {identity_name}")
    time.sleep(0.1)

# ── Step 6: Write output ──────────────────────────────────────────────────────
with open(OUT_JSONL, "w") as f:
    for w in top100:
        f.write(json.dumps(w) + "\n")
print(f"\nFull data saved to {OUT_JSONL}")

# ── Step 7: Report ────────────────────────────────────────────────────────────
role_totals = {}
for w in top100:
    for r in w["roles"]:
        role_totals[r] = role_totals.get(r, {"count": 0, "tao": 0.0})
        role_totals[r]["count"] += 1
        role_totals[r]["tao"]   += w["total_tao"]

with open(META_FILE) as f:
    meta = json.load(f)
total_supply = meta["total_issuance_tao"] + meta["total_stake_tao"]

lines = []
lines.append("=" * 90)
lines.append(f"TOP {TOP_N} TAO HOLDERS — ROLE AND IDENTITY ANALYSIS")
lines.append(f"Block: {block:,}    Total supply: {total_supply:,.0f} TAO")
lines.append("=" * 90)
lines.append(f"{'#':<4} {'SS58 Address':<48} {'Free':>10} {'Staked':>10} {'Total':>10}  Roles / Identity")
lines.append("-" * 90)

for i, w in enumerate(top100):
    ss58       = w["ss58"]
    role_str   = "+".join(w["roles"])
    ident      = w["identity"].get("name","") or ""
    subnets    = f" SN{w['owned_subnets']}" if w["owned_subnets"] else ""
    label      = f"[{role_str}]{subnets}  {ident}" if ident else f"[{role_str}]{subnets}"
    lines.append(f"{i+1:<4} {ss58:<48} {w['free_tao']:>10,.0f} {w['staked_tao']:>10,.0f} {w['total_tao']:>10,.0f}  {label}")

lines.append("=" * 90)
lines.append("")
lines.append("ROLE SUMMARY (top 100 wallets, wallets may have multiple roles):")
for role, d in sorted(role_totals.items(), key=lambda x: -x[1]["tao"]):
    pct = d["tao"] / total_supply * 100
    lines.append(f"  {role:<18} {d['count']:3d} wallets  {d['tao']:>12,.0f} TAO  ({pct:.1f}% of supply)")

identified = sum(1 for w in top100 if w["identity"].get("name"))
lines.append("")
lines.append(f"Identity coverage (top 100): {identified}/100 have on-chain identity")

report = "\n".join(lines)
print("\n" + report)
with open(OUT_REPORT, "w") as f:
    f.write(report + "\n")
print(f"\nReport saved to {OUT_REPORT}")
