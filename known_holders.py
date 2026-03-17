"""
Phase 6: Known holder mapping.

Enumerates all on-chain IdentitiesV2 entries (validators, subnet owners, and any
other coldkey/hotkey that registered identity), cross-references with delegate
info and subnet ownership, fetches coldkey free balances and per-subnet stake,
and produces:

  known_holders.json          — full data for all identity-registered addresses
  known_holders_report.txt    — human-readable summary + comparison tables

This script is part of the Shadow Whale investigation tutorial and demonstrates:
  - query_map over IdentitiesV2 to enumerate all named entities
  - Decoding byte-tuple encoded string fields (Bittensor's custom encoding)
  - Cross-referencing delegates, subnet owners, and account data
  - Comparing liquid vs staked holdings across entity types
"""

import json
import time
from collections import defaultdict

import bittensor as bt
from scalecodec.utils.ss58 import ss58_encode

RAO = 1_000_000_000
OUT_JSON   = "known_holders.json"
OUT_REPORT = "known_holders_report.txt"


def decode_bytes_field(raw) -> str:
    """Decode a byte-tuple field from IdentitiesV2 to a UTF-8 string."""
    if not raw:
        return ""
    try:
        if isinstance(raw, (list, tuple)) and len(raw) > 0 and isinstance(raw[0], int):
            return bytes(raw).decode("utf-8", errors="replace").strip()
        return str(raw).strip()
    except Exception:
        return ""


def decode_identity(v: dict) -> dict:
    return {
        "name":     decode_bytes_field(v.get("name", ())),
        "url":      decode_bytes_field(v.get("url", ())),
        "github":   decode_bytes_field(v.get("github_repo", ())),
        "discord":  decode_bytes_field(v.get("discord", ())),
        "twitter":  decode_bytes_field(v.get("twitter", ())),
        "image":    decode_bytes_field(v.get("image", ())),
        "description": decode_bytes_field(v.get("description", ())),
    }


sub = bt.Subtensor(network="finney")
print(f"Connected at block {sub.get_current_block():,}")

# ── 1. Stream all IdentitiesV2 ─────────────────────────────────────────────
print("\n[1] Streaming IdentitiesV2...")
identities = {}  # ss58 -> decoded identity dict
for key, val in sub.substrate.query_map("SubtensorModule", "IdentitiesV2"):
    ss58 = ss58_encode(bytes(key[0]).hex(), ss58_format=42)
    v = val.value if hasattr(val, "value") else val
    if isinstance(v, dict):
        idt = decode_identity(v)
        identities[ss58] = idt

print(f"  {len(identities)} IdentitiesV2 entries")
named = {ss58: idt for ss58, idt in identities.items() if idt["name"]}
print(f"  {len(named)} with non-empty name")

# ── 2. Get all delegate info (hotkey -> coldkey + stake) ───────────────────
print("\n[2] Fetching delegates...")
delegates = sub.get_delegates()
hk_to_ck  = {d.hotkey_ss58: d.owner_ss58 for d in delegates}
hk_to_delegate_stake = {}
for d in delegates:
    # total_stake is {netuid: Balance} — sum across all subnets
    total = 0.0
    if isinstance(d.total_stake, dict):
        for bal in d.total_stake.values():
            try:
                total += float(str(bal).replace(",", "").replace("τ", "").strip())
            except Exception:
                pass
    hk_to_delegate_stake[d.hotkey_ss58] = total

# Build set of all delegate coldkeys
delegate_coldkeys = set(hk_to_ck.values())
print(f"  {len(delegates)} delegates, {len(delegate_coldkeys)} unique coldkeys")

# ── 3. Get all subnet owner coldkeys ──────────────────────────────────────
print("\n[3] Fetching subnet info...")
subnets = sub.get_all_subnets_info()
sn_owner_coldkeys = {}  # coldkey -> [netuid, ...]
for sn in subnets:
    if sn and sn.owner_ss58:
        ck = sn.owner_ss58
        sn_owner_coldkeys.setdefault(ck, [])
        sn_owner_coldkeys[ck].append(sn.netuid)
print(f"  {len(subnets)} subnets, {len(sn_owner_coldkeys)} unique owner coldkeys")

# ── 4. Collect all addresses of interest ──────────────────────────────────
# Addresses with identity (named or not), plus delegate coldkeys + subnet owners
all_addresses = set(identities.keys()) | delegate_coldkeys | set(sn_owner_coldkeys.keys())
print(f"\n[4] Total unique addresses to query: {len(all_addresses)}")

# ── 5. Fetch balances for all ─────────────────────────────────────────────
print("[5] Fetching account balances...")
balances = {}  # ss58 -> {free_tao, nonce}
for i, ss58 in enumerate(all_addresses):
    try:
        r = sub.substrate.query("System", "Account", [ss58])
        data = r.value if hasattr(r, "value") else r
        balances[ss58] = {
            "free_tao": data["data"]["free"] / RAO,
            "nonce":    data["nonce"],
        }
    except Exception as e:
        balances[ss58] = {"free_tao": 0.0, "nonce": -1}
    if i % 50 == 0:
        print(f"  {i}/{len(all_addresses)}...", end="\r", flush=True)
    time.sleep(0.01)

print(f"\n  Done. {len(balances)} balance records")

# ── 6. Fetch stake per coldkey via TotalColdkeyStake ─────────────────────
# Note: In dTAO, this may undercount stake in subnet alpha pools.
# We record it but flag it as potentially incomplete.
print("[6] Fetching coldkey stake (TotalColdkeyStake — may be incomplete in dTAO)...")
coldkey_stake = {}
for i, ss58 in enumerate(all_addresses):
    try:
        r = sub.substrate.query("SubtensorModule", "TotalColdkeyStake", [ss58])
        val = r.value if hasattr(r, "value") else r
        if val and isinstance(val, (int, float)):
            coldkey_stake[ss58] = float(val) / RAO
        else:
            coldkey_stake[ss58] = 0.0
    except Exception:
        coldkey_stake[ss58] = 0.0
    if i % 50 == 0:
        print(f"  {i}/{len(all_addresses)}...", end="\r", flush=True)
    time.sleep(0.01)

print(f"\n  Done.")

# ── 7. Build enriched records ─────────────────────────────────────────────
print("\n[7] Building enriched records...")
records = []
for ss58 in all_addresses:
    bal  = balances.get(ss58, {"free_tao": 0.0, "nonce": -1})
    idt  = identities.get(ss58, {})
    stake = coldkey_stake.get(ss58, 0.0)

    # Roles
    is_delegate_owner = ss58 in delegate_coldkeys
    is_sn_owner       = ss58 in sn_owner_coldkeys
    has_identity      = bool(idt.get("name", ""))

    # Hotkeys for this coldkey
    owned_hotkeys = [hk for hk, ck in hk_to_ck.items() if ck == ss58]

    records.append({
        "ss58":             ss58,
        "identity":         idt,
        "has_identity":     has_identity,
        "free_tao":         bal["free_tao"],
        "stake_tao":        stake,
        "nonce":            bal["nonce"],
        "is_delegate_owner": is_delegate_owner,
        "is_sn_owner":      is_sn_owner,
        "owned_subnets":    sn_owner_coldkeys.get(ss58, []),
        "owned_hotkeys":    owned_hotkeys,
    })

records.sort(key=lambda x: x["free_tao"], reverse=True)

# ── 8. Save JSON ───────────────────────────────────────────────────────────
with open(OUT_JSON, "w") as f:
    json.dump(records, f, indent=2)
print(f"Saved {len(records)} records to {OUT_JSON}")

# ── 9. Generate report ─────────────────────────────────────────────────────
lines = []
lines.append("=" * 72)
lines.append("KNOWN HOLDER ANALYSIS — Bittensor Finney chain")
lines.append(f"Addresses with on-chain identity or network role: {len(records)}")
lines.append("=" * 72)

# Named holders sorted by free balance
named_records = [r for r in records if r["has_identity"]]
named_records.sort(key=lambda x: x["free_tao"], reverse=True)

lines.append(f"\n--- TOP NAMED HOLDERS BY FREE BALANCE (n={len(named_records)}) ---")
lines.append(f"{'Name':<30} {'Free TAO':>12} {'Stake TAO':>12} {'Role':<20} {'SS58'}")
lines.append("-" * 90)
for r in named_records[:50]:
    name = r["identity"].get("name", "")[:28]
    roles = []
    if r["is_delegate_owner"]: roles.append("validator")
    if r["is_sn_owner"]:       roles.append(f"sn_owner({r['owned_subnets']})")
    role_str = ",".join(roles) if roles else "identity_only"
    lines.append(f"  {name:<28} {r['free_tao']:>12,.0f} {r['stake_tao']:>12,.0f}  {role_str:<20} {r['ss58']}")

# Validators vs SN owners comparison
validators = [r for r in records if r["is_delegate_owner"]]
sn_owners  = [r for r in records if r["is_sn_owner"]]
overlap    = [r for r in records if r["is_delegate_owner"] and r["is_sn_owner"]]

lines.append(f"\n--- VALIDATORS vs SUBNET OWNERS COMPARISON ---")
lines.append(f"{'Group':<20} {'Count':>6} {'Total Free TAO':>16} {'Total Stake TAO':>16} {'Avg Free':>12}")
lines.append("-" * 76)
for label, group in [("Validators", validators), ("SN Owners", sn_owners), ("Both (overlap)", overlap)]:
    n    = len(group)
    tot_free  = sum(r["free_tao"]  for r in group)
    tot_stake = sum(r["stake_tao"] for r in group)
    avg_free  = tot_free / n if n else 0
    lines.append(f"  {label:<18} {n:>6} {tot_free:>16,.0f} {tot_stake:>16,.0f} {avg_free:>12,.0f}")

lines.append(f"\nNote: stake figures from TotalColdkeyStake — may undercount dTAO alpha pool stake.")

# Top validators by free balance
lines.append(f"\n--- TOP VALIDATORS BY COLDKEY FREE BALANCE ---")
validators.sort(key=lambda x: x["free_tao"], reverse=True)
for r in validators[:20]:
    name  = r["identity"].get("name", "(no identity)")[:28]
    lines.append(f"  {r['free_tao']:>10,.0f} TAO free  {name:<28} {r['ss58']}")

# Top SN owners by free balance
lines.append(f"\n--- TOP SUBNET OWNERS BY COLDKEY FREE BALANCE ---")
sn_owners.sort(key=lambda x: x["free_tao"], reverse=True)
for r in sn_owners[:20]:
    name = r["identity"].get("name", "(no identity)")[:28]
    lines.append(f"  {r['free_tao']:>10,.0f} TAO free  SNs={r['owned_subnets']}  {name:<28} {r['ss58']}")

report = "\n".join(lines)
print(report)
with open(OUT_REPORT, "w") as f:
    f.write(report + "\n")
print(f"\nSaved report to {OUT_REPORT}")
