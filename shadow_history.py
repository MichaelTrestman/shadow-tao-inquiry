"""
Historical balance analysis for the top 10 shadow wallets.

Samples free balance at ~14 points across the full chain history to determine
when each wallet received its TAO and whether balances have been static.

Sample blocks (logarithmic-ish spacing across the chain):
  1, 100, 1_000, 10_000, 100_000, 500_000, 1_000_000, 2_000_000,
  3_000_000, 4_000_000, 5_000_000, 6_000_000, 7_000_000, <current>

NOTE: Requires an archive node. Public Finney RPC nodes are likely pruned
(~256 blocks of state). If historical queries fail, the script will note this
and fall back to what is available.

Input:  finney_shadow_identified.jsonl (sorted by balance, with ss58_encoded)
Output: shadow_history.json + shadow_history_report.txt
"""

import json
import sys
import time
from pathlib import Path

import bittensor as bt

RAO = 1_000_000_000
SHADOW_FILE = "finney_shadow_identified.jsonl"
OUT_JSON    = "shadow_history.json"
OUT_REPORT  = "shadow_history_report.txt"
TOP_N       = 10

if not Path(SHADOW_FILE).exists():
    print(f"ERROR: {SHADOW_FILE} not found.")
    sys.exit(1)

sub = bt.Subtensor(network="archive")
current_block = sub.get_current_block()
print(f"Connected at block {current_block:,}")

# ── Load top 10 shadow wallets ────────────────────────────────────────────────
wallets = []
with open(SHADOW_FILE) as f:
    for line in f:
        w = json.loads(line)
        if w.get("ss58_encoded"):
            wallets.append(w)

wallets.sort(key=lambda x: x["free_tao"], reverse=True)
top_wallets = wallets[:TOP_N]

print(f"\nTop {TOP_N} shadow wallets to analyze:")
for i, w in enumerate(top_wallets):
    print(f"  {i+1:2d}. {w['ss58_encoded']}  {w['free_tao']:>12,.2f} TAO")

# ── Define sample blocks ──────────────────────────────────────────────────────
# Logarithmic spacing across chain history + current
SAMPLE_BLOCKS = [
    1,
    100,
    1_000,
    10_000,
    100_000,
    500_000,
    1_000_000,
    2_000_000,
    3_000_000,
    4_000_000,
    5_000_000,
    6_000_000,
    7_000_000,
    current_block,
]
# Remove any sample points beyond current block
SAMPLE_BLOCKS = [b for b in SAMPLE_BLOCKS if b <= current_block]
print(f"\nSample blocks: {SAMPLE_BLOCKS}")

# ── Get block hashes ──────────────────────────────────────────────────────────
print("\nFetching block hashes...")
block_hashes = {}
for blk in SAMPLE_BLOCKS:
    try:
        h = sub.substrate.get_block_hash(block_id=blk)
        block_hashes[blk] = h
        print(f"  Block {blk:>9,}: {h}")
    except Exception as e:
        print(f"  Block {blk:>9,}: ERROR — {e}")
        block_hashes[blk] = None

# ── Query balance at each block for each wallet ───────────────────────────────
print("\nQuerying historical balances...")
results = {}
archive_available = True

for w in top_wallets:
    ss58 = w["ss58_encoded"]
    print(f"\n  {ss58[:20]}...  (current: {w['free_tao']:,.2f} TAO)")
    history = {}

    for blk in SAMPLE_BLOCKS:
        bh = block_hashes.get(blk)
        if bh is None:
            history[blk] = None
            continue
        try:
            result = sub.substrate.query(
                "System", "Account", [ss58], block_hash=bh
            )
            # archive node returns plain dict, no .value wrapper
            if isinstance(result, dict):
                free_rao = result["data"]["free"]
            elif result and hasattr(result, "value") and result.value:
                free_rao = result.value["data"]["free"]
            else:
                free_rao = 0
            tao = free_rao / RAO
            history[blk] = tao
            print(f"    Block {blk:>9,}: {tao:>12,.4f} TAO")
        except Exception as e:
            err = str(e)
            history[blk] = f"ERROR: {err[:60]}"
            print(f"    Block {blk:>9,}: ERROR — {err[:60]}")
            if "not supported" in err.lower() or "pruned" in err.lower() or "State already" in err.lower():
                archive_available = False

        time.sleep(0.15)

    results[ss58] = {
        "free_tao_current": w["free_tao"],
        "history": history,
    }

# ── Save JSON ─────────────────────────────────────────────────────────────────
out = {
    "current_block": current_block,
    "sample_blocks": SAMPLE_BLOCKS,
    "archive_available": archive_available,
    "wallets": results,
}
with open(OUT_JSON, "w") as f:
    json.dump(out, f, indent=2)
print(f"\nData saved to {OUT_JSON}")

# ── Build report ──────────────────────────────────────────────────────────────
lines = []
lines.append("=" * 90)
lines.append("SHADOW WALLET HISTORICAL BALANCE ANALYSIS — TOP 10")
lines.append(f"Current block: {current_block:,}")
lines.append("=" * 90)

if not archive_available:
    lines.append("")
    lines.append("WARNING: Archive node required for historical queries.")
    lines.append("The public Finney RPC appears to be a pruned node.")
    lines.append("Historical data may be incomplete or unavailable for old blocks.")

lines.append("")

# Header row
hdr = f"{'Block':>10}"
for w in top_wallets:
    hdr += f"  {w['ss58_encoded'][:12]:>14}"
lines.append(hdr)
lines.append("-" * 90)

for blk in SAMPLE_BLOCKS:
    row = f"{blk:>10,}"
    for w in top_wallets:
        ss58 = w["ss58_encoded"]
        val = results[ss58]["history"].get(blk)
        if val is None:
            row += f"  {'N/A':>14}"
        elif isinstance(val, str):  # error
            row += f"  {'ERR':>14}"
        elif val == 0.0:
            row += f"  {'0':>14}"
        else:
            row += f"  {val:>14,.1f}"
    lines.append(row)

lines.append("=" * 90)
lines.append("")
lines.append("Interpretation guide:")
lines.append("  - A balance appearing at an early block means the wallet had TAO that early.")
lines.append("  - A balance that appears suddenly at a specific block indicates when TAO arrived.")
lines.append("  - A static balance across all sampled blocks = no movement since receipt.")
lines.append("  - ERR = block state not available (pruned node)")

report = "\n".join(lines)
print("\n" + report)
with open(OUT_REPORT, "w") as f:
    f.write(report + "\n")
print(f"\nReport saved to {OUT_REPORT}")
