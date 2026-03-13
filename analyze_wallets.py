"""
Finney wallet analysis - Phase 2

Reads from files produced by enumerate_wallets.py:
  finney_accounts.jsonl
  finney_staking_cks.txt
  finney_meta.json

Produces:
  finney_summary.txt         — human-readable summary
  finney_shadow_wallets.jsonl — shadow wallet details (nonce=0, no stake, >1 TAO)
"""

import json
import statistics
import sys
from pathlib import Path

ACCOUNTS_FILE = "finney_accounts.jsonl"
STAKING_FILE  = "finney_staking_cks.txt"
META_FILE     = "finney_meta.json"
SUMMARY_FILE  = "finney_summary.txt"
SHADOW_FILE   = "finney_shadow_wallets.jsonl"

for f in [ACCOUNTS_FILE, STAKING_FILE, META_FILE]:
    if not Path(f).exists():
        print(f"ERROR: {f} not found. Run enumerate_wallets.py first.")
        sys.exit(1)

# ── Load meta ─────────────────────────────────────────────────────────────────
with open(META_FILE) as f:
    meta = json.load(f)
block             = meta["block"]
total_issuance    = meta["total_issuance_tao"]
total_stake       = meta["total_stake_tao"]

# ── Load staking coldkeys into a set ──────────────────────────────────────────
print("Loading staking coldkeys...")
staking_cks = set()
with open(STAKING_FILE) as f:
    for line in f:
        staking_cks.add(line.strip())
print(f"  {len(staking_cks):,} staking coldkeys")

# ── Stream accounts, compute stats, write shadow file ─────────────────────────
print("Analyzing accounts...")

total_free   = 0.0
wallet_count = 0
stake_count  = 0
never_sent   = 0
has_sent     = 0

free_balances = []   # for distribution stats; loaded into memory (list of floats, manageable)

shadow_count = 0
shadow_tao   = 0.0
large_shadow_count = 0
large_shadow_tao   = 0.0

with open(ACCOUNTS_FILE) as accounts_in, open(SHADOW_FILE, "w") as shadow_out:
    for line in accounts_in:
        w = json.loads(line)
        ss58     = w["ss58"]
        free_tao = w["free_tao"]
        nonce    = w["nonce"]
        has_stake = ss58 in staking_cks

        wallet_count += 1
        total_free   += free_tao
        if has_stake:
            stake_count += 1
        if nonce == 0:
            never_sent += 1
        else:
            has_sent += 1

        if free_tao > 0:
            free_balances.append(free_tao)

        # Shadow: nonce=0, no stake, >1 TAO
        if nonce == 0 and not has_stake and free_tao > 1.0:
            shadow_count += 1
            shadow_tao   += free_tao
            shadow_out.write(json.dumps({"ss58": ss58, "free_tao": free_tao}) + "\n")
            if free_tao > 1000:
                large_shadow_count += 1
                large_shadow_tao   += free_tao

# Also count staking coldkeys not in System.Account (pure stakers with no free balance)
# They are already represented in stake_count via the set, but wallet_count may miss them
extra_stakers = staking_cks - set()  # we'd need to track seen ss58s; skip for now

# ── Distribution stats ────────────────────────────────────────────────────────
free_balances.sort(reverse=True)
n = len(free_balances)

def top_n_share(lst, n):
    s = sum(lst[:n])
    return s, s / total_free * 100 if total_free else 0

# ── Build summary ─────────────────────────────────────────────────────────────
lines = []
lines.append("=" * 60)
lines.append("FINNEY WALLET SUMMARY")
lines.append("=" * 60)
lines.append(f"Block:                      {block:,}")
lines.append(f"Total issuance:             {total_issuance:>12,.2f} TAO")
lines.append(f"Total free balances (sum):  {total_free:>12,.2f} TAO")
lines.append(f"Total staked (chain total): {total_stake:>12,.2f} TAO")
lines.append(f"Accounted for:              {total_free + total_stake:>12,.2f} TAO")
lines.append("")
lines.append(f"Total accounts:             {wallet_count:>12,}")
lines.append(f"  With stake:               {stake_count:>12,}")
lines.append(f"  No stake:                 {wallet_count - stake_count:>12,}")
lines.append("")
lines.append(f"  Ever sent a tx (nonce>0): {has_sent:>12,}")
lines.append(f"  Never sent a tx:          {never_sent:>12,}")
lines.append("")
lines.append(f"Shadow wallets (>1 TAO, nonce=0, no stake):")
lines.append(f"  Count:                    {shadow_count:>12,}")
lines.append(f"  TAO held:                 {shadow_tao:>12,.2f} TAO")
pct = shadow_tao / total_free * 100 if total_free else 0
lines.append(f"  % of free supply:         {pct:>11.1f}%")
lines.append("")
lines.append(f"Large shadow (>1000 TAO, nonce=0, no stake):")
lines.append(f"  Count:                    {large_shadow_count:>12,}")
lines.append(f"  TAO held:                 {large_shadow_tao:>12,.2f} TAO")
lines.append("")
lines.append(f"Free balance distribution (non-zero wallets):")
lines.append(f"  Count:    {n:,}")
if n >= 10:
    tao, pct = top_n_share(free_balances, 10)
    lines.append(f"  Top 10 hold:   {tao:>12,.2f} TAO  ({pct:.1f}%)")
if n >= 100:
    tao, pct = top_n_share(free_balances, 100)
    lines.append(f"  Top 100 hold:  {tao:>12,.2f} TAO  ({pct:.1f}%)")
if n >= 1000:
    tao, pct = top_n_share(free_balances, 1000)
    lines.append(f"  Top 1000 hold: {tao:>12,.2f} TAO  ({pct:.1f}%)")
if n > 0:
    lines.append(f"  Median:        {statistics.median(free_balances):.4f} TAO")
lines.append("=" * 60)

summary = "\n".join(lines)
print("\n" + summary)

with open(SUMMARY_FILE, "w") as f:
    f.write(summary + "\n")
print(f"\nSummary saved to {SUMMARY_FILE}")
print(f"Shadow wallet details saved to {SHADOW_FILE}")
