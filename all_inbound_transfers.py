"""
Phase 8: Full inbound transfer history for top 10 shadow wallets.

The archive node has no "find all events for address X" query — we must scan
blocks. This script makes it tractable by using the 14 historical sample points
from shadow_history.json as anchors:

  For each consecutive pair of sample blocks (lo, hi) where balance increased:
    Binary search within [lo, hi] to find the first block where balance rose.
    Record that block's transfer events.
    Advance lo = found_block + 1 and repeat until hi is reached.
    (Multiple transfers can happen within a sample interval.)

This is O(sample_intervals × transfers_per_interval × log2(interval_width))
RPC calls — roughly 50-200 total per wallet, versus scanning millions of blocks.

After finding all sender addresses, cross-references each against known_holders.json
to flag any validators, subnet owners, or identity-registered coldkeys.

Output:
  all_inbound_transfers.json  — all found transfers per wallet
  all_inbound_report.txt      — human-readable report with known-entity flags
"""

import json
import time
from collections import defaultdict

import bittensor as bt

RAO          = 1_000_000_000
OUT_JSON     = "all_inbound_transfers.json"
OUT_REPORT   = "all_inbound_report.txt"
HISTORY_FILE = "shadow_history.json"
KNOWN_JSON   = "known_holders.json"

sub = bt.Subtensor(network="archive")
print(f"Connected to archive at block {sub.get_current_block():,}")

# ── Load shadow history sample points ─────────────────────────────────────
history = json.load(open(HISTORY_FILE))
sample_blocks = history["sample_blocks"]
# shadow_history.json structure: wallets is a dict {ss58: {free_tao_current, history: {str_block: balance}}}
wallet_history_raw = history["wallets"]
# Convert to list of {ss58, history: [(block, balance)] sorted by block}
wallet_history = []
for ss58_addr, wdata in wallet_history_raw.items():
    hist_pairs = sorted(
        [(int(blk), bal) for blk, bal in wdata["history"].items()],
        key=lambda x: x[0]
    )
    wallet_history.append({"ss58": ss58_addr, "history": [{"block": b, "balance": bal} for b, bal in hist_pairs]})
print(f"\nLoaded {len(sample_blocks)} sample blocks, {len(wallet_history)} wallets")

# ── Load known entities for cross-reference ────────────────────────────────
known_raw    = json.load(open(KNOWN_JSON))
known_ss58   = {r["ss58"]: r for r in known_raw}
print(f"Loaded {len(known_ss58)} known coldkeys")

# ── Helpers ────────────────────────────────────────────────────────────────

def get_balance(ss58: str, block: int) -> float:
    bh = sub.substrate.get_block_hash(block_id=block)
    r  = sub.substrate.query("System", "Account", [ss58], block_hash=bh)
    data = r.value if hasattr(r, "value") else r
    return data["data"]["free"] / RAO

def get_transfers_to(ss58: str, block: int) -> list[dict]:
    """All Balances.Transfer events at `block` where to == ss58."""
    bh     = sub.substrate.get_block_hash(block_id=block)
    events = sub.substrate.get_events(block_hash=bh)
    found  = []
    for ev in events:
        if ev["module_id"] == "Balances" and ev["event_id"] == "Transfer":
            attrs = ev["attributes"]
            if isinstance(attrs, dict) and attrs.get("to") == ss58:
                try:
                    amount = int(str(attrs.get("amount", 0)).replace(",", "")) / RAO
                except Exception:
                    amount = 0.0
                found.append({"from": attrs.get("from", "?"), "amount_tao": amount, "block": block})
    return found

def find_next_increase_block(ss58: str, lo: int, hi: int, baseline: float) -> int | None:
    """
    Binary search for the smallest block in (lo, hi] where balance > baseline.
    Returns None if balance never exceeds baseline in this range.
    """
    # Quick check: is hi actually higher?
    hi_bal = get_balance(ss58, hi)
    if hi_bal <= baseline + 0.001:
        return None

    # Binary search
    while lo < hi - 1:
        mid     = (lo + hi) // 2
        mid_bal = get_balance(ss58, mid)
        if mid_bal > baseline + 0.001:
            hi = mid
        else:
            lo = mid
        time.sleep(0.05)
    return hi

# ── Main loop ──────────────────────────────────────────────────────────────
all_results = []

for wallet in wallet_history:
    ss58    = wallet["ss58"]
    history = wallet["history"]  # [{block, balance}] sorted by block

    print(f"\n{'─'*60}")
    print(f"Wallet: {ss58}")

    # Build list of sample points with non-zero start blocks
    samples = [(h["block"], h["balance"]) for h in history if h["balance"] is not None]

    # Find all transfer blocks in each interval where balance increased
    wallet_transfers = []

    for i in range(len(samples) - 1):
        lo_block, lo_bal = samples[i]
        hi_block, hi_bal = samples[i + 1]

        if hi_bal <= lo_bal + 0.001:
            continue  # no increase in this interval

        print(f"  Interval block {lo_block:,}→{hi_block:,}: +{hi_bal - lo_bal:,.1f} TAO")

        # Find all transfer blocks within this interval
        scan_lo   = lo_block
        scan_base = lo_bal

        while True:
            found_block = find_next_increase_block(ss58, scan_lo, hi_block, scan_base)
            if found_block is None:
                break

            bal_at = get_balance(ss58, found_block)
            transfers = get_transfers_to(ss58, found_block)

            if transfers:
                for t in transfers:
                    print(f"    Block {found_block:,}: {t['amount_tao']:,.2f} TAO from {t['from']}")
                    wallet_transfers.append(t)
            else:
                # Balance went up but no Transfer event found — unusual
                print(f"    Block {found_block:,}: balance +{bal_at - scan_base:.2f} TAO but no Transfer event")
                wallet_transfers.append({
                    "from": "(no transfer event)",
                    "amount_tao": bal_at - scan_base,
                    "block": found_block,
                })

            scan_base = bal_at
            scan_lo   = found_block + 1
            if scan_lo >= hi_block:
                break
            time.sleep(0.1)

    print(f"  Total transfers found: {len(wallet_transfers)}")
    total_tao = sum(t["amount_tao"] for t in wallet_transfers)
    print(f"  Total TAO traced: {total_tao:,.2f}")

    all_results.append({
        "ss58":      ss58,
        "transfers": wallet_transfers,
    })
    time.sleep(0.2)

# ── Save JSON ──────────────────────────────────────────────────────────────
with open(OUT_JSON, "w") as f:
    json.dump(all_results, f, indent=2)
print(f"\n\nSaved {len(all_results)} wallet records to {OUT_JSON}")

# ── Cross-reference senders against known entities ─────────────────────────
print("\nCross-referencing senders against known_holders...")

lines = ["=" * 72, "FULL INBOUND TRANSFER ANALYSIS — TOP 10 SHADOW WALLETS", "=" * 72, ""]

global_senders = defaultdict(lambda: {"tao": 0.0, "count": 0, "wallets": set()})

for r in all_results:
    ss58 = r["ss58"]
    xfers = r["transfers"]

    lines.append(f"Wallet: {ss58}")
    lines.append(f"  Transfers: {len(xfers)}")

    by_sender = defaultdict(float)
    for t in xfers:
        by_sender[t["from"]] += t["amount_tao"]
        global_senders[t["from"]]["tao"]    += t["amount_tao"]
        global_senders[t["from"]]["count"]  += 1
        global_senders[t["from"]]["wallets"].add(ss58[:12])

    for sender, total in sorted(by_sender.items(), key=lambda x: -x[1]):
        k = known_ss58.get(sender)
        if k:
            name  = k.get("identity", {}).get("name", "") or "(no name)"
            roles = []
            if k["is_delegate_owner"]: roles.append("validator")
            if k["is_sn_owner"]:       roles.append(f"SN{k['owned_subnets']}")
            label = f"  *** KNOWN: {name} [{','.join(roles)}] ***"
        else:
            label = ""
        lines.append(f"    {total:>10,.2f} TAO  {sender}{label}")
    lines.append("")

# Summary: known entities who sent to shadow wallets
lines.append("=" * 72)
lines.append("KNOWN ENTITIES THAT SENT TO SHADOW WALLETS")
lines.append("=" * 72)
known_found = {s: v for s, v in global_senders.items() if s in known_ss58}
if known_found:
    for sender, v in sorted(known_found.items(), key=lambda x: -x[1]["tao"]):
        k    = known_ss58[sender]
        name = k.get("identity", {}).get("name", "") or "(no name)"
        roles = []
        if k["is_delegate_owner"]: roles.append("validator")
        if k["is_sn_owner"]:       roles.append(f"SN{k['owned_subnets']}")
        lines.append(f"  {sender}")
        lines.append(f"    Name: {name}  Roles: {','.join(roles) or 'none'}")
        lines.append(f"    Total sent to shadow wallets: {v['tao']:,.2f} TAO")
        lines.append(f"    Recipient wallets: {', '.join(v['wallets'])}")
        lines.append("")
else:
    lines.append("  NONE — no known entity (validator/SN owner/identity-registered)")
    lines.append("  appears as a sender to any of the top 10 shadow wallets")
    lines.append("  across their full transfer history.")

# Top senders overall (whether known or not)
lines.append("")
lines.append("TOP SENDERS ACROSS ALL SHADOW WALLETS (by total TAO sent):")
for sender, v in sorted(global_senders.items(), key=lambda x: -x[1]["tao"])[:20]:
    k = known_ss58.get(sender)
    label = f"  [KNOWN: {k.get('identity',{}).get('name','') or '(no name)'}]" if k else ""
    lines.append(f"  {v['tao']:>10,.2f} TAO  {sender}{label}")

report = "\n".join(lines)
print("\n" + report)
with open(OUT_REPORT, "w") as f:
    f.write(report + "\n")
print(f"\nSaved to {OUT_REPORT}")
