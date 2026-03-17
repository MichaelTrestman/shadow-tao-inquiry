"""
Phase 8: Funder address investigation.

5EiXej3AwjKqb9mjQAf29JG5HJf9Dwtt8CjvDqA8biprWTiN made the first deposits
into shadow wallets #1, #3, and #5 — three of the top ten. This script
investigates that address (and optionally others) using only the archive node:

  1. Current balance + nonce (how active is it? still holds TAO?)
  2. Balance history at 14 sample blocks (when did it accumulate, is it
     depleting — i.e. is it being used to fund shadow wallets over time?)
  3. Inbound attribution: binary-search for blocks where its balance
     increased, then read events to find who funded it.
  4. Full transfer events at the known first-deposit blocks: who else did
     it send to in those same blocks?
  5. On-chain identity and role check against known_holders.json.

Limitations: outbound transfer history (who else did it fund beyond the
known blocks) requires an indexer. This script covers inbound flows and
the specific known-deposit blocks.

Output: funder_investigation_report.txt
"""

import json
import time

import bittensor as bt

RAO        = 1_000_000_000
OUT_REPORT = "funder_investigation_report.txt"
KNOWN_JSON = "known_holders.json"

# Target addresses — primary funder and secondary funder for comparison
TARGETS = [
    {
        "ss58":  "5EiXej3AwjKqb9mjQAf29JG5HJf9Dwtt8CjvDqA8biprWTiN",
        "label": "Funder-A",
        "funded_shadow_wallets": [
            ("5FEA1FfUPwT3K4zTsYbQx5X1G9R2ZjYLyFv12xBQxW9QgoCL", 5_946_516),
            ("5Dhf6WgqrfhVyFCGqK4G5utro2jepscwryMhLHtpMfopxweC",  6_581_276),
            ("5C9CxW9355u1sqy6Np85FfGssJAdyA8cAsjjV9YP8aaLvjEY",  6_784_524),
        ],
    },
    {
        "ss58":  "5DunDrFV6BPbzsgLZUtMQtCq7w9fcUEbM59BUwx5E7N9Bn5E",
        "label": "Funder-B",
        "funded_shadow_wallets": [
            ("5ChHTBkaE1VgK5NX59uHuZoK8VQShojKBB1sGfXaZQpxVDCi", 6_084_503),
            ("5Epz8SQ69FuZRLyjCAicn8i71SdyEYaWR5rZ5a1i1bgoxGaQ",  7_061_941),
            ("5GVKorR78gqQCV6mrWMWX95hHG93ZaRAUShZVBNT768dvqv8",  7_066_018),
        ],
    },
]

SAMPLE_BLOCKS = [
    1, 100, 1_000, 10_000, 100_000, 500_000,
    1_000_000, 2_000_000, 3_000_000, 4_000_000,
    5_000_000, 6_000_000, 7_000_000,
]

sub = bt.Subtensor(network="archive")
current_block = sub.get_current_block()
print(f"Connected to archive at block {current_block:,}")
SAMPLE_BLOCKS = SAMPLE_BLOCKS + [current_block]

known_raw  = json.load(open(KNOWN_JSON))
known_by_ss58 = {r["ss58"]: r for r in known_raw}

# ── Helpers ────────────────────────────────────────────────────────────────

def get_balance_and_nonce(ss58: str, block: int) -> tuple[float, int]:
    bh   = sub.substrate.get_block_hash(block_id=block)
    r    = sub.substrate.query("System", "Account", [ss58], block_hash=bh)
    data = r.value if hasattr(r, "value") else r
    return data["data"]["free"] / RAO, data["nonce"]

def get_balance(ss58: str, block: int) -> float:
    return get_balance_and_nonce(ss58, block)[0]

def get_events(block: int) -> list:
    bh = sub.substrate.get_block_hash(block_id=block)
    return sub.substrate.get_events(block_hash=bh)

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

def all_transfers_at(block: int) -> list[dict]:
    events = get_events(block)
    out = []
    for ev in events:
        if ev.get("module_id") == "Balances" and ev.get("event_id") == "Transfer":
            attrs = ev.get("attributes", {})
            if isinstance(attrs, dict):
                out.append({
                    "from":   attrs.get("from", "?"),
                    "to":     attrs.get("to", "?"),
                    "amount": parse_amount(attrs.get("amount", 0)),
                    "block":  block,
                })
    return out

# ── Investigate each target ─────────────────────────────────────────────────

report_lines = [
    "=" * 72,
    "FUNDER ADDRESS INVESTIGATION",
    "=" * 72,
    "",
]

for target in TARGETS:
    ss58  = target["ss58"]
    label = target["label"]

    print(f"\n{'='*60}")
    print(f"Investigating {label}: {ss58}")

    report_lines += [
        f"{'─'*72}",
        f"{label}: {ss58}",
        f"{'─'*72}",
    ]

    # ── 1. Current state ─────────────────────────────────────────────────
    bal, nonce = get_balance_and_nonce(ss58, current_block)
    print(f"  Balance: {bal:,.4f} TAO  Nonce: {nonce:,}")
    report_lines.append(f"Current balance: {bal:,.4f} TAO")
    report_lines.append(f"Nonce: {nonce:,}  (number of transactions signed)")

    # ── 2. Known identity / role ─────────────────────────────────────────
    k = known_by_ss58.get(ss58)
    if k:
        name  = k.get("identity", {}).get("name", "") or "(no name)"
        roles = []
        if k["is_delegate_owner"]: roles.append("validator")
        if k["is_sn_owner"]:       roles.append(f"SN{k['owned_subnets']}")
        report_lines.append(f"Known entity: {name}  Roles: {', '.join(roles) or 'none'}")
    else:
        report_lines.append("Not in known_holders.json (no registered identity, not a validator or SN owner)")

    # ── 3. Balance history ───────────────────────────────────────────────
    print("  Sampling balance history...")
    report_lines.append("\nBalance history (14 sample points):")
    hist = []
    for blk in SAMPLE_BLOCKS:
        b = get_balance(ss58, blk)
        hist.append((blk, b))
        if b > 0:
            report_lines.append(f"  Block {blk:>10,}: {b:>14,.4f} TAO")
        time.sleep(0.05)

    # ── 4. Who funded it? (binary search on increase intervals) ─────────
    print("  Finding inbound funding blocks...")
    report_lines.append("\nInbound funding (blocks where balance increased):")

    for i in range(len(hist) - 1):
        lo_blk, lo_bal = hist[i]
        hi_blk, hi_bal = hist[i+1]
        if hi_bal <= lo_bal + 0.001:
            continue
        print(f"  Interval {lo_blk:,}→{hi_blk:,}: +{hi_bal-lo_bal:,.1f} TAO")

        scan_lo, scan_base = lo_blk, lo_bal
        while True:
            found = find_next_increase(ss58, scan_lo, hi_blk, scan_base)
            if found is None:
                break
            new_bal = get_balance(ss58, found)
            transfers = all_transfers_at(found)
            inbound = [t for t in transfers if t["to"] == ss58]

            if inbound:
                for t in inbound:
                    k_sender = known_by_ss58.get(t["from"])
                    k_label  = f"  [KNOWN: {k_sender['identity'].get('name','')}]" if k_sender else ""
                    line = f"  Block {found:,}: received {t['amount']:,.4f} TAO from {t['from']}{k_label}"
                    print("   ", line.strip())
                    report_lines.append(line)
            else:
                report_lines.append(f"  Block {found:,}: balance +{new_bal-scan_base:.4f} TAO (no Transfer event found)")

            scan_base = new_bal
            scan_lo   = found + 1
            if scan_lo >= hi_blk:
                break
            time.sleep(0.1)

    # ── 5. All transfers at the known shadow-funding blocks ──────────────
    print("  Checking all transfers at known shadow-funding blocks...")
    report_lines.append(f"\nAll transfers at blocks where {label} funded shadow wallets:")

    for (shadow_ss58, deposit_block) in target["funded_shadow_wallets"]:
        report_lines.append(f"\n  Block {deposit_block:,} (first deposit to {shadow_ss58[:16]}...):")
        transfers = all_transfers_at(deposit_block)
        from_this = [t for t in transfers if t["from"] == ss58]
        for t in from_this:
            k_recv = known_by_ss58.get(t["to"])
            k_label = f"  [KNOWN: {k_recv['identity'].get('name','')}]" if k_recv else ""
            report_lines.append(f"    → {t['to']}  {t['amount']:,.4f} TAO{k_label}")
        if not from_this:
            report_lines.append(f"    (no outbound transfers from {label} found at this block)")
        time.sleep(0.1)

    report_lines.append("")

# ── Save report ─────────────────────────────────────────────────────────────
report = "\n".join(report_lines)
print("\n\n" + report)
with open(OUT_REPORT, "w") as f:
    f.write(report + "\n")
print(f"\nSaved to {OUT_REPORT}")
