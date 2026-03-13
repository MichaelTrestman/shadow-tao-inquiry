"""
Finney chain wallet enumeration - Phase 1 (streaming)

Writes data to JSONL files immediately as fetched — no memory accumulation.
Safe to kill and resume: checks if output files already exist.

Output files:
  finney_accounts.jsonl     — one {"ss58": ..., "free_tao": ..., "nonce": ...} per line
  finney_staking_cks.txt    — one ss58 per line (coldkeys with any stake)
  finney_meta.json          — block number, chain totals
"""

import json
import os
import sys
import time

import bittensor as bt

RAO = 1_000_000_000

ACCOUNTS_FILE = "finney_accounts.jsonl"
STAKING_FILE  = "finney_staking_cks.txt"
META_FILE     = "finney_meta.json"

sub = bt.Subtensor(network="finney")
block = sub.get_current_block()
print(f"Connected. Block: {block:,}")

# ── 1. Chain totals (fast single queries) ─────────────────────────────────────
print("Fetching chain totals...")
total_issuance_rao = sub.substrate.query("Balances", "TotalIssuance").value
total_stake_rao    = sub.substrate.query("SubtensorModule", "TotalStake").value
meta = {
    "block": block,
    "total_issuance_tao": total_issuance_rao / RAO,
    "total_stake_tao":    total_stake_rao    / RAO,
}
with open(META_FILE, "w") as f:
    json.dump(meta, f, indent=2)
print(f"  Issuance: {meta['total_issuance_tao']:,.2f} TAO")
print(f"  Staked:   {meta['total_stake_tao']:,.2f} TAO")
print(f"  Saved to {META_FILE}")

# ── 2. All accounts → stream to JSONL ─────────────────────────────────────────
if os.path.exists(ACCOUNTS_FILE):
    line_count = sum(1 for _ in open(ACCOUNTS_FILE))
    print(f"\n{ACCOUNTS_FILE} already exists ({line_count:,} lines). Delete to re-fetch.")
else:
    print(f"\nStreaming System.Account map → {ACCOUNTS_FILE} ...")
    print("  (this is the slow part — expect 5-30 min on public RPC)")
    count = 0
    t0 = time.time()
    with open(ACCOUNTS_FILE, "w") as out:
        for ss58, info in sub.query_map("System", "Account"):
            record = {
                "ss58":     str(ss58),
                "free_tao": info["data"]["free"] / RAO,
                "nonce":    info["nonce"],
            }
            out.write(json.dumps(record) + "\n")
            count += 1
            if count % 5000 == 0:
                elapsed = time.time() - t0
                print(f"  {count:,} accounts... ({elapsed:.0f}s)", flush=True)
    elapsed = time.time() - t0
    print(f"  Done: {count:,} accounts in {elapsed:.0f}s → {ACCOUNTS_FILE}")

# ── 3. StakingColdkeys → stream to text file ──────────────────────────────────
if os.path.exists(STAKING_FILE):
    line_count = sum(1 for _ in open(STAKING_FILE))
    print(f"\n{STAKING_FILE} already exists ({line_count:,} lines). Delete to re-fetch.")
else:
    print(f"\nStreaming StakingColdkeys → {STAKING_FILE} ...")
    count = 0
    t0 = time.time()
    with open(STAKING_FILE, "w") as out:
        for ck, _idx in sub.query_map_subtensor("StakingColdkeys"):
            out.write(str(ck) + "\n")
            count += 1
            if count % 1000 == 0:
                print(f"  {count:,} staking coldkeys...", flush=True)
    elapsed = time.time() - t0
    print(f"  Done: {count:,} staking coldkeys in {elapsed:.0f}s → {STAKING_FILE}")

print("\nEnumeration complete. Run analyze_wallets.py to generate summary.")
