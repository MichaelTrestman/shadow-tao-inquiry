"""
Attribution check: Const's public key vs SN120 owner key.

Const (Jacob Robert Steeves, Bittensor co-founder) has publicly claimed
coldkey 5GH2aUTMRUh1RprCgH4x3tRyCaKeUi5BfmYCfs1NARA8R54n. The SN120
(Affine) owner on-chain is a different key:
  5Fc3ZZQAYB3SPXKcFnd1WJeyQvArSZZeB6LU1rb7zvQ6XvDh

known_holders.py labels this SN120 owner as "const". This script checks
whether there are any on-chain Balances.Transfer events between these two
addresses — which would constitute on-chain evidence that they are
controlled by the same person.

Strategy:
  1. Sample both addresses' balances at 14 historical blocks.
  2. For every interval where either address' balance changed, binary-search
     to find the exact block of the change.
  3. At each such block, fetch all Balances.Transfer events and check whether
     either address appears as sender AND the other as recipient.
  4. Also check any coldkey-swap (SubtensorModule.ColdkeySwapped) events at
     those blocks as a secondary signal.

Output:
  const_attribution_report.txt
"""

import json
import time

import bittensor as bt

RAO = 1_000_000_000
OUT_REPORT = "const_attribution_report.txt"

# The two keys under investigation
KEY_A = "5GH2aUTMRUh1RprCgH4x3tRyCaKeUi5BfmYCfs1NARA8R54n"  # Const's public claim
KEY_B = "5Fc3ZZQAYB3SPXKcFnd1WJeyQvArSZZeB6LU1rb7zvQ6XvDh"  # SN120 owner ("const")
LABEL_A = "Const_claimed"
LABEL_B = "SN120_owner"

SAMPLE_BLOCKS = [
    1, 100, 1_000, 10_000, 100_000, 500_000,
    1_000_000, 2_000_000, 3_000_000, 4_000_000,
    5_000_000, 6_000_000, 7_000_000,
]

sub = bt.Subtensor(network="archive")
current_block = sub.get_current_block()
print(f"Connected to archive at block {current_block:,}")

SAMPLE_BLOCKS = SAMPLE_BLOCKS + [current_block]

# ── Helpers ────────────────────────────────────────────────────────────────

def get_balance(ss58: str, block: int) -> float:
    bh = sub.substrate.get_block_hash(block_id=block)
    r  = sub.substrate.query("System", "Account", [ss58], block_hash=bh)
    data = r.value if hasattr(r, "value") else r
    return data["data"]["free"] / RAO

def get_events_at(block: int) -> list:
    bh = sub.substrate.get_block_hash(block_id=block)
    return sub.substrate.get_events(block_hash=bh)

def find_change_block(ss58: str, lo: int, hi: int, lo_bal: float) -> int | None:
    """Binary search for first block in (lo, hi] where balance != lo_bal."""
    hi_bal = get_balance(ss58, hi)
    if abs(hi_bal - lo_bal) < 0.001:
        return None
    while lo < hi - 1:
        mid = (lo + hi) // 2
        mid_bal = get_balance(ss58, mid)
        if abs(mid_bal - lo_bal) >= 0.001:
            hi = mid
        else:
            lo = mid
        time.sleep(0.05)
    return hi

def check_transfers_between(events: list, addr_a: str, addr_b: str, block: int) -> list:
    """Return Transfer events where one address sends to the other."""
    found = []
    for ev in events:
        if ev.get("module_id") == "Balances" and ev.get("event_id") == "Transfer":
            attrs = ev.get("attributes", {})
            if not isinstance(attrs, dict):
                continue
            frm = attrs.get("from", "")
            to  = attrs.get("to", "")
            try:
                amount = int(str(attrs.get("amount", 0)).replace(",", "")) / RAO
            except Exception:
                amount = 0.0
            if (frm == addr_a and to == addr_b) or (frm == addr_b and to == addr_a):
                found.append({"from": frm, "to": to, "amount_tao": amount, "block": block})
    return found

def check_coldkey_swaps(events: list, addr_a: str, addr_b: str) -> list:
    """Return any ColdkeySwapped events involving either address."""
    found = []
    for ev in events:
        module = ev.get("module_id", "")
        event_id = ev.get("event_id", "")
        if module == "SubtensorModule" and "swap" in event_id.lower():
            attrs = ev.get("attributes", {})
            found.append({"event": event_id, "attrs": str(attrs)})
    return found

# ── Step 1: Sample balance history for both keys ───────────────────────────
print(f"\nSampling balance history for both keys across {len(SAMPLE_BLOCKS)} blocks...")

def sample_history(ss58: str, label: str) -> list:
    hist = []
    for blk in SAMPLE_BLOCKS:
        bal = get_balance(ss58, blk)
        hist.append({"block": blk, "balance": bal})
        time.sleep(0.05)
    return hist

hist_a = sample_history(KEY_A, LABEL_A)
print(f"  {LABEL_A}: first nonzero at block {next((h['block'] for h in hist_a if h['balance'] > 0), 'never')}")
print(f"  {LABEL_A}: current balance {hist_a[-1]['balance']:,.2f} TAO")

hist_b = sample_history(KEY_B, LABEL_B)
print(f"  {LABEL_B}: first nonzero at block {next((h['block'] for h in hist_b if h['balance'] > 0), 'never')}")
print(f"  {LABEL_B}: current balance {hist_b[-1]['balance']:,.2f} TAO")

# ── Step 2: Find blocks where either key's balance changed ─────────────────
print("\nFinding balance-change blocks via binary search...")

change_blocks = set()

def find_all_changes(hist: list, ss58: str, label: str):
    for i in range(len(hist) - 1):
        lo_blk, lo_bal = hist[i]["block"], hist[i]["balance"]
        hi_blk, hi_bal = hist[i+1]["block"], hist[i+1]["balance"]
        if abs(hi_bal - lo_bal) < 0.001:
            continue
        print(f"  {label}: balance changed in [{lo_blk:,}, {hi_blk:,}]: {lo_bal:.2f} → {hi_bal:.2f}")
        # Find the change block
        scan_lo, scan_base = lo_blk, lo_bal
        while True:
            found = find_change_block(ss58, scan_lo, hi_blk, scan_base)
            if found is None:
                break
            change_blocks.add(found)
            new_bal = get_balance(ss58, found)
            print(f"    Change at block {found:,}: {scan_base:.4f} → {new_bal:.4f} TAO")
            scan_base = new_bal
            scan_lo = found + 1
            if scan_lo >= hi_blk:
                break
            time.sleep(0.1)

find_all_changes(hist_a, KEY_A, LABEL_A)
find_all_changes(hist_b, KEY_B, LABEL_B)

print(f"\nTotal unique balance-change blocks found: {len(change_blocks)}")

# ── Step 3: Check events at each change block ──────────────────────────────
print("\nChecking events at change blocks for transfers between the two keys...")

direct_transfers = []
coldkey_swap_events = []
all_transfers_involving = []  # any transfer to/from either key

for blk in sorted(change_blocks):
    print(f"  Block {blk:,}...", end=" ", flush=True)
    events = get_events_at(blk)

    # Direct transfers between the two keys
    between = check_transfers_between(events, KEY_A, KEY_B, blk)
    if between:
        direct_transfers.extend(between)
        print(f"MATCH: {len(between)} transfer(s) between the two keys!")
    else:
        print("no direct transfer")

    # Any coldkey swap events (secondary signal)
    swaps = check_coldkey_swaps(events, KEY_A, KEY_B)
    coldkey_swap_events.extend(swaps)

    # Also record any transfer TO either key (for context)
    for ev in events:
        if ev.get("module_id") == "Balances" and ev.get("event_id") == "Transfer":
            attrs = ev.get("attributes", {})
            if not isinstance(attrs, dict):
                continue
            frm = attrs.get("from", "")
            to  = attrs.get("to", "")
            try:
                amount = int(str(attrs.get("amount", 0)).replace(",", "")) / RAO
            except Exception:
                amount = 0.0
            if to in (KEY_A, KEY_B) or frm in (KEY_A, KEY_B):
                all_transfers_involving.append({
                    "block": blk, "from": frm, "to": to, "amount_tao": amount
                })
    time.sleep(0.1)

# ── Step 4: Report ─────────────────────────────────────────────────────────
lines = [
    "=" * 72,
    "CONST ATTRIBUTION CHECK",
    "Checking for on-chain connections between two keys:",
    f"  A ({LABEL_A}): {KEY_A}",
    f"  B ({LABEL_B}): {KEY_B}",
    "=" * 72,
    "",
    f"Key A balance at current block: {hist_a[-1]['balance']:,.4f} TAO",
    f"Key B balance at current block: {hist_b[-1]['balance']:,.4f} TAO",
    "",
]

lines.append("DIRECT TRANSFERS BETWEEN A AND B:")
if direct_transfers:
    for t in direct_transfers:
        frm_label = LABEL_A if t["from"] == KEY_A else LABEL_B
        to_label  = LABEL_B if t["to"] == KEY_B else LABEL_A
        lines.append(f"  Block {t['block']:,}: {frm_label} → {to_label}  {t['amount_tao']:,.4f} TAO")
else:
    lines.append("  NONE found across all balance-change blocks.")

lines.append("")
lines.append("ALL TRANSFERS INVOLVING EITHER KEY (context):")
for t in all_transfers_involving:
    frm_label = LABEL_A if t["from"] == KEY_A else (LABEL_B if t["from"] == KEY_B else t["from"][:16])
    to_label  = LABEL_A if t["to"] == KEY_A else (LABEL_B if t["to"] == KEY_B else t["to"][:16])
    lines.append(f"  Block {t['block']:,}: {frm_label} → {to_label}  {t['amount_tao']:,.4f} TAO")

if coldkey_swap_events:
    lines.append("")
    lines.append("COLDKEY SWAP EVENTS AT CHANGE BLOCKS:")
    for s in coldkey_swap_events:
        lines.append(f"  {s['event']}: {s['attrs']}")

lines.append("")
if direct_transfers:
    lines.append("CONCLUSION: On-chain transfers found between the two keys.")
    lines.append("This is on-chain evidence consistent with shared control.")
else:
    lines.append("CONCLUSION: No direct transfers found between the two keys")
    lines.append("at blocks where either key's balance changed.")
    lines.append("This does not rule out shared control — they may simply never")
    lines.append("have transferred directly between each other. Alternative")
    lines.append("signals: shared upstream funder, coldkey swap history,")
    lines.append("or off-chain disclosure.")

report = "\n".join(lines)
print("\n\n" + report)
with open(OUT_REPORT, "w") as f:
    f.write(report + "\n")
print(f"\nSaved to {OUT_REPORT}")
