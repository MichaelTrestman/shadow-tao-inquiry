"""
Phase 5: First-transfer sender attribution for top shadow wallets.

For each shadow whale in our top-10 list, this script:
  1. Uses binary search on the archive node to find the exact block where the
     wallet's free balance first became non-zero (~17 RPC calls per wallet).
  2. Reads all Balances.Transfer events at that block and finds any where the
     recipient matches the target address.

This answers: who funded each shadow whale on its first appearance?

Note — this is an *audit*, not a proof. There is no guarantee that the
first deposit to any wallet came via a standard Balances.Transfer. If no
matching event is found, the cause is uncertain (could be a non-standard
extrinsic, a different event type, or a bug in event parsing). Any null
results should be investigated further, not treated as "no sender."

--- Bug history (documented for tutorial transparency) ---

v1 (original): accessed events as ev.value["event"]["module_id"] — wrong,
  events are plain dicts with top-level keys.

v2: added decode_account_id() to parse AccountId byte tuples — also wrong,
  in this bittensor version the attributes["from"/"to"] fields are already
  decoded as SS58 strings by the RPC layer.

v3 (current): uses ev["module_id"], ev["attributes"]["from"/"to"] directly.

From our historical analysis (shadow_history.json) we have known bounds:
  - lo: last block where balance = 0
  - hi: first block where balance > 0
---

Output: first_transfers.json + first_transfers_report.txt
"""

import json
import time
from pathlib import Path

import bittensor as bt
from scalecodec.utils.ss58 import ss58_encode

RAO        = 1_000_000_000
SS58_FORMAT = 42
OUT_JSON   = "first_transfers.json"
OUT_REPORT = "first_transfers_report.txt"

sub = bt.Subtensor(network="archive")
current_block = sub.get_current_block()
print(f"Connected to archive at block {current_block:,}\n")

# ── Wallets with known search bounds from historical analysis ─────────────────
# (ss58, lo_block [balance=0], hi_block [balance>0], approx_tao_at_hi)
TARGETS = [
    ("5FEA1FfUPwT3K4zTsYbQx5X1G9R2ZjYLyFv12xBQxW9QgoCL", 5_000_000, 6_000_000,  23_838),
    ("5ChHTBkaE1VgK5NX59uHuZoK8VQShojKBB1sGfXaZQpxVDCi", 6_000_000, 7_000_000,  84_867),
    ("5Dhf6WgqrfhVyFCGqK4G5utro2jepscwryMhLHtpMfopxweC", 6_000_000, 7_000_000,  70_077),
    ("5GUkyA37dHnc1rEijDtvBe5yYNCpaNjaHGqB7DY9Kb2KgSj3", 6_000_000, 7_000_000,  64_939),
    ("5C9CxW9355u1sqy6Np85FfGssJAdyA8cAsjjV9YP8aaLvjEY",  6_000_000, 7_000_000,  18_082),
    ("5Epz8SQ69FuZRLyjCAicn8i71SdyEYaWR5rZ5a1i1bgoxGaQ",  7_000_000, current_block, 90_843),
    ("5GVKorR78gqQCV6mrWMWX95hHG93ZaRAUShZVBNT768dvqv8",  7_000_000, current_block, 56_342),
    ("5HAe1pePzBuPqsF6BpTGN8vCngvKKJaRZ2HkHwFmJgWgAzcf",  7_000_000, current_block, 17_850),
    ("5DwksfKHHG5rURh9jpGaq87m5k3Jn8BJbY9geeX7zTGQD8Pr",  5_000_000, 6_000_000,   9_571),
    ("5CXHJRRk5WAQ8hTkzRDEK89pbsZD2e4Lu7KBTFrHcUQ6GZvz",  3_000_000, 4_000_000,   9_800),
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_free_balance(ss58: str, block_hash: str) -> float:
    result = sub.substrate.query("System", "Account", [ss58], block_hash=block_hash)
    if isinstance(result, dict):
        return result["data"]["free"] / RAO
    if result and hasattr(result, "value") and result.value:
        return result.value["data"]["free"] / RAO
    return 0.0

def get_block_hash(blk: int) -> str:
    return sub.substrate.get_block_hash(block_id=blk)

def find_first_nonzero_block(ss58: str, lo: int, hi: int) -> int:
    """Binary search: return smallest block where free_balance > 0."""
    steps = 0
    while lo < hi - 1:
        mid = (lo + hi) // 2
        bh  = get_block_hash(mid)
        bal = get_free_balance(ss58, bh)
        steps += 1
        if bal > 0:
            hi = mid
        else:
            lo = mid
        time.sleep(0.05)
    return hi, steps

def get_transfers_at_block(ss58: str, block_hash: str) -> list[dict]:
    """
    Read all Balances.Transfer events at a block, return those where 'to' == ss58.

    Note on event format: in this version of bittensor/async_substrate_interface,
    get_events() returns a list of plain dicts. Fields are top-level (not nested
    under .value["event"]). The 'from' and 'to' attributes are already decoded
    as SS58 strings — no further decoding needed.
    """
    transfers = []
    try:
        events = sub.substrate.get_events(block_hash=block_hash)
        for ev in events:
            try:
                # Events are plain dicts with top-level module_id/event_id/attributes
                module   = ev["module_id"]
                event_id = ev["event_id"]
                attrs    = ev["attributes"]

                if module == "Balances" and event_id == "Transfer":
                    # attributes is a dict with string SS58 keys already decoded
                    if isinstance(attrs, dict):
                        from_addr = attrs.get("from", attrs.get("who", "?"))
                        to_addr   = attrs.get("to", "?")
                        try:
                            amount = int(str(attrs.get("amount", 0)).replace(",", "")) / RAO
                        except Exception:
                            amount = 0.0
                    else:
                        continue

                    if to_addr == ss58:
                        transfers.append({
                            "module": module,
                            "event": event_id,
                            "from": from_addr,
                            "to": to_addr,
                            "amount_tao": amount,
                        })
            except Exception:
                continue
    except Exception as e:
        print(f"    Event fetch error: {e}")
    return transfers

# ── Main loop ─────────────────────────────────────────────────────────────────
results = []

for ss58, lo, hi, approx_tao in TARGETS:
    print(f"\n{'─'*60}")
    print(f"Wallet: {ss58}")
    print(f"  Current balance: ~{approx_tao:,} TAO")
    print(f"  Search range: block {lo:,} → {hi:,}")

    first_block, steps = find_first_nonzero_block(ss58, lo, hi)
    first_hash = get_block_hash(first_block)
    first_bal  = get_free_balance(ss58, first_hash)

    print(f"  First non-zero block: {first_block:,}  (found in {steps} steps)")
    print(f"  Balance at first block: {first_bal:,.4f} TAO")

    # Also check one block earlier to confirm it was zero
    prev_hash = get_block_hash(first_block - 1)
    prev_bal  = get_free_balance(ss58, prev_hash)
    print(f"  Balance at block {first_block-1:,}: {prev_bal:,.4f} TAO (should be 0)")

    # Get transfers at the first block
    print(f"  Reading events at block {first_block:,}...")
    transfers = get_transfers_at_block(ss58, first_hash)
    print(f"  Matching transfer events: {len(transfers)}")
    for t in transfers:
        print(f"    FROM: {t['from']}")
        print(f"    AMOUNT: {t['amount_tao']:,.4f} TAO")

    results.append({
        "ss58": ss58,
        "approx_current_tao": approx_tao,
        "first_nonzero_block": first_block,
        "first_balance_tao": first_bal,
        "prev_balance_tao": prev_bal,
        "transfers": transfers,
    })
    time.sleep(0.2)

# ── Save ──────────────────────────────────────────────────────────────────────
with open(OUT_JSON, "w") as f:
    json.dump({"current_block": current_block, "wallets": results}, f, indent=2)
print(f"\n\nFull data saved to {OUT_JSON}")

# ── Report ────────────────────────────────────────────────────────────────────
lines = ["=" * 70, "FIRST TRANSFER ANALYSIS — TOP 10 SHADOW WALLETS", "=" * 70, ""]
for r in results:
    lines.append(f"Wallet: {r['ss58']}")
    lines.append(f"  First funded at block: {r['first_nonzero_block']:,}")
    lines.append(f"  Initial deposit:       {r['first_balance_tao']:,.4f} TAO")
    if r["transfers"]:
        for t in r["transfers"]:
            lines.append(f"  Sender:  {t['from']}")
            lines.append(f"  Amount:  {t['amount_tao']:,.4f} TAO")
    else:
        lines.append("  Sender: (no matching Transfer event found at this block)")
        lines.append("  Note: may have arrived via a non-standard transfer mechanism")
    lines.append("")

report = "\n".join(lines)
print("\n" + report)
with open(OUT_REPORT, "w") as f:
    f.write(report + "\n")
print(f"Report saved to {OUT_REPORT}")
