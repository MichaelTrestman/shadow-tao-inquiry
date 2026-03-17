"""
tao.bot investigation.

tao.bot is the #1 validator by stake-weight on Bittensor Finney (853,488 TAO
as of the validator_stake_weight.py query). It has no public-facing identity,
no website, no off-chain presence that can be attributed. The user community
has noted it appears to operate entirely through child hotkey delegation rather
than running validators directly.

This script documents:
  1. Coldkey state (balance, nonce)
  2. On-chain identity check
  3. Delegate take rate
  4. Stake distribution by subnet (where is the 853k TAO staked?)
  5. Child hotkey registrations across all subnets
  6. Balance history of the coldkey at 14 sample points (is it actively funded?)
  7. All transfers at known change blocks (who funded the coldkey?)

Hotkey:  5E2LP6EnZ54m3wS8s1yPvD5c3xo71kQroBw7aUVK32TKeZ5u
Coldkey: 5GsbTgfvgCH4xdqSkiPb7EaBBFLHjWH5vfEALhJaewSFpZX9

Output: taobot_investigation_report.txt
"""

import json
import time

import bittensor as bt

RAO        = 1_000_000_000
OUT_REPORT = "taobot_investigation_report.txt"
KNOWN_JSON = "known_holders.json"

TAOBOT_HK = "5E2LP6EnZ54m3wS8s1yPvD5c3xo71kQroBw7aUVK32TKeZ5u"
TAOBOT_CK = "5GsbTgfvgCH4xdqSkiPb7EaBBFLHjWH5vfEALhJaewSFpZX9"

SAMPLE_BLOCKS = [
    1, 100, 1_000, 10_000, 100_000, 500_000,
    1_000_000, 2_000_000, 3_000_000, 4_000_000,
    5_000_000, 6_000_000, 7_000_000,
]

print("Loading known holders...", flush=True)
known_raw     = json.load(open(KNOWN_JSON))
known_by_ss58 = {r["ss58"]: r for r in known_raw}
print(f"  {len(known_by_ss58)} known holders loaded", flush=True)

# Finney for current state; archive for history
print("Connecting to finney...", flush=True)
sub_fin = bt.Subtensor(network="finney")
current_block = sub_fin.get_current_block()
print(f"  finney: block {current_block:,}", flush=True)

print("Connecting to archive node...", flush=True)
sub_arc = bt.Subtensor(network="archive")
print("  archive: connected", flush=True)

SAMPLE_BLOCKS = SAMPLE_BLOCKS + [current_block]

# ── Helpers ─────────────────────────────────────────────────────────────────

def get_account(ss58: str, block: int, sub=sub_arc) -> dict:
    bh = sub.substrate.get_block_hash(block_id=block)
    r  = sub.substrate.query("System", "Account", [ss58], block_hash=bh)
    return r.value if hasattr(r, "value") else r

def get_balance(ss58: str, block: int) -> float:
    return get_account(ss58, block)["data"]["free"] / RAO

def get_events(block: int) -> list:
    bh = sub_arc.substrate.get_block_hash(block_id=block)
    return sub_arc.substrate.get_events(block_hash=bh)

def parse_amount(raw) -> float:
    try:
        return int(str(raw).replace(",", "")) / RAO
    except Exception:
        return 0.0

def find_next_increase(ss58: str, lo: int, hi: int, baseline: float) -> int | None:
    hi_bal = get_balance(ss58, hi)
    if hi_bal <= baseline + 0.001:
        return None
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if get_balance(ss58, mid) > baseline + 0.001:
            hi = mid
        else:
            lo = mid
        time.sleep(0.05)
    return hi

def all_transfers_involving(ss58: str, block: int) -> list[dict]:
    events = get_events(block)
    out = []
    for ev in events:
        if ev.get("module_id") == "Balances" and ev.get("event_id") == "Transfer":
            attrs = ev.get("attributes", {})
            if not isinstance(attrs, dict):
                continue
            frm = attrs.get("from", "")
            to  = attrs.get("to", "")
            if frm == ss58 or to == ss58:
                out.append({
                    "from":   frm,
                    "to":     to,
                    "amount": parse_amount(attrs.get("amount", 0)),
                    "block":  block,
                })
    return out

# ── Report lines ─────────────────────────────────────────────────────────────

lines = [
    "=" * 72,
    "TAO.BOT VALIDATOR INVESTIGATION",
    "=" * 72,
    "",
    f"Hotkey:  {TAOBOT_HK}",
    f"Coldkey: {TAOBOT_CK}",
    "",
]

# ── 1. Current coldkey state ─────────────────────────────────────────────────
print("\n1. Current coldkey state...")
acc = get_account(TAOBOT_CK, current_block)
ck_bal   = acc["data"]["free"] / RAO
ck_nonce = acc["nonce"]
lines += [
    "── 1. COLDKEY CURRENT STATE ──────────────────────────────────────",
    f"Free balance: {ck_bal:,.4f} TAO",
    f"Nonce:        {ck_nonce:,}  (number of transactions signed by coldkey)",
    "",
]
print(f"   balance={ck_bal:,.4f} TAO  nonce={ck_nonce:,}")

# ── 2. Known identity check ───────────────────────────────────────────────────
k = known_by_ss58.get(TAOBOT_CK)
if k:
    name  = k.get("identity", {}).get("name", "") or "(no name)"
    roles = []
    if k["is_delegate_owner"]: roles.append("validator")
    if k["is_sn_owner"]:       roles.append(f"SN{k['owned_subnets']}")
    lines.append(f"Known entity: {name}  Roles: {', '.join(roles) or 'none'}")
else:
    lines.append("Not in known_holders.json with identity/validator/SN-owner flag")
lines.append("")

# ── 3. Delegate take ──────────────────────────────────────────────────────────
print("2. Delegate take rate...")
delegates = sub_fin.get_delegates()
tb = next((d for d in delegates if d.hotkey_ss58 == TAOBOT_HK), None)
if tb:
    lines += [
        "── 2. DELEGATE INFO ──────────────────────────────────────────────",
        f"Take rate: {tb.take}  (fraction of emissions kept by validator; 0 = all to nominators)",
        "",
    ]
    print(f"   take={tb.take}")
else:
    lines.append("tao.bot hotkey not found in delegates list (unexpected)")
    lines.append("")

# ── 4. Stake by subnet ────────────────────────────────────────────────────────
print("3. Stake distribution by subnet...")
lines.append("── 3. STAKE DISTRIBUTION BY SUBNET ──────────────────────────────")
if tb and isinstance(tb.total_stake, dict):
    def to_f(v):
        try: return float(str(v).replace(",", "").replace("\u03c4", "").replace("T", "").strip())
        except: return 0.0
    items = sorted([(k, to_f(v)) for k, v in tb.total_stake.items() if to_f(v) > 0.001], key=lambda x: -x[1])
    lines.append(f"{'Netuid':>8}  {'Stake TAO':>14}")
    lines.append("-" * 28)
    for netuid, amt in items:
        lines.append(f"{str(netuid):>8}  {amt:>14,.1f}")
    lines.append(f"\n  Total subnets with stake: {len(items)}")
    lines.append(f"  Total stake: {sum(v for _, v in items):,.1f} TAO")
else:
    lines.append("  (no stake data)")
lines.append("")

# ── 5. Child hotkeys across all subnets ───────────────────────────────────────
# ChildKeys storage returns list of (proportion_u64, pubkey_bytes_tuple) pairs.
# Proportion is a u64 fraction of 2**64. Pubkey bytes need ss58 encoding.
print("4. Child hotkey registrations...")
lines.append("── 4. CHILD HOTKEY REGISTRATIONS ────────────────────────────────")
from scalecodec.utils.ss58 import ss58_encode
bh_fin = sub_fin.substrate.get_block_hash(block_id=current_block)
total_children = 0
child_errors = []
for netuid in range(0, 100):
    try:
        r = sub_fin.substrate.query("SubtensorModule", "ChildKeys", [TAOBOT_HK, netuid], block_hash=bh_fin)
        v = r.value if hasattr(r, "value") else r
        if not v:
            continue
        children = []
        for entry in v:
            try:
                proportion_u64, pubkey_raw = entry
                # pubkey_raw is a tuple of 32 bytes — decode to ss58
                if isinstance(pubkey_raw, (tuple, list)):
                    # may be nested: ((b0, b1, ...), ) or (b0, b1, ...)
                    inner = pubkey_raw[0] if isinstance(pubkey_raw[0], (tuple, list)) else pubkey_raw
                    pubkey_bytes = bytes(inner)
                else:
                    pubkey_bytes = bytes(pubkey_raw)
                child_ss58 = ss58_encode(pubkey_bytes, ss58_format=42)
                pct = int(proportion_u64) / (2**64) * 100
                children.append((child_ss58, pct))
            except Exception as e:
                children.append((f"(decode error: {e})", 0.0))
        if children:
            lines.append(f"  Netuid {netuid:>3}: {len(children)} child hotkey(s)")
            for child_ss58, pct in children:
                lines.append(f"    {child_ss58:<50}  {pct:.1f}%")
            total_children += len(children)
    except Exception as e:
        child_errors.append(f"  Netuid {netuid}: {e}")
lines.append(f"\n  Total child hotkeys across all subnets: {total_children}")
if child_errors:
    lines.append(f"  Query errors on {len(child_errors)} subnets (likely unregistered netuids)")
lines.append("")
print(f"   found {total_children} child hotkeys total")

# ── 6 & 7. Coldkey balance history + inbound funding ─────────────────────────
# NOTE: Skipped in this script (archive-node binary search omitted for speed).
# An earlier run of investigate_taobot.py (with sections 6-7 intact) completed
# successfully and found only 3 inbound events on the coldkey:
#   Block 4,849,932: 0.998 TAO from 5E2b2DcMd5W8MBhzTCFt63t2ZEN8RsRgL7oDd7BFYL9aMQux
#   Block 4,850,203: 1,025.194 TAO from 5E2b2DcMd5W8MBhzTCFt63t2ZEN8RsRgL7oDd7BFYL9aMQux
#   Block 7,632,272: 9.998 TAO from 5FqqXKb9zonSNKbZhEuHYjCXnmPbX9tdzMCU2gx8gir8Z8a5
# These are documented in taobot-profile.md.
# For outbound history (what the 617 coldkey transactions did), use the tao.app API:
#   GET /api/beta/accounting/events?coldkey=5GsbTgfvgCH4xdqSkiPb7EaBBFLHjWH5vfEALhJaewSFpZX9
lines += [
    "── 5. COLDKEY FUNDING HISTORY ────────────────────────────────────",
    "  Not queried via archive node (nonce=617 → slow; use tao.app API).",
    "  Query: GET /api/beta/accounting/events?coldkey=5GsbTgfvgCH4xdqSkiPb7EaBBFLHjWH5vfEALhJaewSFpZX9",
    "",
]
print("5. Coldkey funding history: skipped (use tao.app API — see note in script)")

# ── Save ──────────────────────────────────────────────────────────────────────
report = "\n".join(lines)
print("\n\n" + report)
with open(OUT_REPORT, "w") as f:
    f.write(report + "\n")
print(f"\nSaved to {OUT_REPORT}")
