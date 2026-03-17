"""
Phase 7: Known-entity → shadow-wallet transfer tracing.

For each top shadow wallet, checks whether any known entity (subnet owner,
validator, or identity-registered coldkey from known_holders.json) appears
as a sender in that wallet's first-deposit block.

This is a lightweight first pass: it checks the first-funded block per wallet
(already established by find_first_transfer.py) and also performs a targeted
query for each known entity: do any of the known coldkeys appear in the
transfer events at the shadow wallet's first-funded block?

For a full multi-block scan (all inbound transfers, not just the first one),
a denser approach using the archive node event scanner is needed.

Output: known_to_shadow_report.txt
"""

import json
import time

import bittensor as bt
from scalecodec.utils.ss58 import ss58_encode

RAO          = 1_000_000_000
OUT_REPORT   = "known_to_shadow_report.txt"
FIRST_XFERS  = "first_transfers.json"
KNOWN_JSON   = "known_holders.json"

sub = bt.Subtensor(network="archive")
print(f"Connected to archive at block {sub.get_current_block():,}")

# ── Load known entities ────────────────────────────────────────────────────
print("\nLoading known holders...")
known = json.load(open(KNOWN_JSON))
known_coldkeys = {r["ss58"] for r in known}
known_by_ss58  = {r["ss58"]: r for r in known}
print(f"  {len(known_coldkeys)} known coldkeys (validators, SN owners, identity-registered)")

# ── Load first-transfer data ───────────────────────────────────────────────
print("Loading first transfer data...")
ft = json.load(open(FIRST_XFERS))
wallets = ft["wallets"]
print(f"  {len(wallets)} shadow wallets with first-funded blocks")

# ── For each shadow wallet, get ALL transfer events at its first-funded block
# and check if any sender is a known entity ────────────────────────────────
print("\nScanning first-funded blocks for known-entity senders...")

lines = ["=" * 72, "KNOWN-ENTITY → SHADOW WALLET TRANSFER SCAN", "=" * 72, ""]
lines.append("Methodology: checks all Balances.Transfer events at each shadow wallet's")
lines.append("first-funded block. If the sender appears in known_holders.json")
lines.append("(validators, subnet owners, or identity-registered coldkeys), it is flagged.")
lines.append("")

any_match = False
for w in wallets:
    ss58       = w["ss58"]
    block      = w["first_nonzero_block"]
    bh         = sub.substrate.get_block_hash(block_id=block)
    events     = sub.substrate.get_events(block_hash=bh)

    known_senders = []
    all_senders   = []

    for ev in events:
        if ev["module_id"] == "Balances" and ev["event_id"] == "Transfer":
            attrs = ev["attributes"]
            if not isinstance(attrs, dict):
                continue
            to_addr   = attrs.get("to", "")
            from_addr = attrs.get("from", "")
            amount    = int(str(attrs.get("amount", 0)).replace(",", "")) / RAO

            if to_addr == ss58:
                all_senders.append((from_addr, amount))
                if from_addr in known_coldkeys:
                    known_senders.append((from_addr, amount, known_by_ss58[from_addr]))

    tag = " *** KNOWN ENTITY ***" if known_senders else ""
    lines.append(f"Wallet: {ss58}")
    lines.append(f"  First-funded block: {block:,}")
    lines.append(f"  All senders at that block: {len(all_senders)}{tag}")
    for sender, amt in all_senders:
        k_info = known_by_ss58.get(sender)
        label = ""
        if k_info:
            name  = k_info.get("identity", {}).get("name", "")
            roles = []
            if k_info.get("is_delegate_owner"): roles.append("validator")
            if k_info.get("is_sn_owner"):       roles.append(f"SN{k_info['owned_subnets']}")
            label = f"  [KNOWN: {name or '(no name)'} {','.join(roles)}]"
        lines.append(f"    FROM {sender}  {amt:,.4f} TAO{label}")
    if known_senders:
        any_match = True
    lines.append("")
    time.sleep(0.1)

if not any_match:
    lines.append("RESULT: No known entity (validator/SN owner/identity-registered) appears")
    lines.append("as a first-deposit sender for any of the top 10 shadow wallets.")
    lines.append("")
    lines.append("Note: this checks only the first-funded block per wallet. Known entities")
    lines.append("may appear in subsequent inbound transfers, which requires a full block scan.")

report = "\n".join(lines)
print("\n" + report)
with open(OUT_REPORT, "w") as f:
    f.write(report + "\n")
print(f"\nSaved to {OUT_REPORT}")
