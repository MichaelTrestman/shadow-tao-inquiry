"""
Phase 3: Identity overlay for shadow wallets.

Reads finney_shadow_wallets.jsonl (which has byte-tuple address strings from the
Phase 1 encoding bug), re-encodes them as proper SS58, then queries on-chain
identity for each wallet.

Output:
  finney_shadow_identified.jsonl  — all shadow wallets with ss58 + identity fields
  finney_shadow_top_report.txt    — human-readable report on top wallets
"""

import ast
import json
import sys
import time
from pathlib import Path

import bittensor as bt
from scalecodec.utils.ss58 import ss58_encode

SHADOW_FILE   = "finney_shadow_wallets.jsonl"
OUT_JSONL     = "finney_shadow_identified.jsonl"
OUT_REPORT    = "finney_shadow_top_report.txt"
SS58_FORMAT   = 42
TOP_N         = 100   # query identities for top N by balance

if not Path(SHADOW_FILE).exists():
    print(f"ERROR: {SHADOW_FILE} not found. Run enumerate_wallets.py first.")
    sys.exit(1)

sub = bt.Subtensor(network="finney")
print(f"Connected at block {sub.get_current_block():,}")

# ── Helper: parse byte-tuple string → SS58 ────────────────────────────────────
def tuple_str_to_ss58(s: str) -> str | None:
    """Convert '((14, 157, ...),)' style string to an SS58 address."""
    try:
        parsed = ast.literal_eval(s)
        raw = bytes(parsed[0])
        return ss58_encode(raw, ss58_format=SS58_FORMAT)
    except Exception as e:
        return None

# ── Helper: query on-chain identity ───────────────────────────────────────────
def get_identity(ss58: str) -> dict:
    """
    Returns a dict with identity fields, or empty dict if none.
    Tries IdentitiesV2 first (bittensor custom), falls back to query_identity.
    """
    try:
        result = sub.query("SubtensorModule", "IdentitiesV2", [ss58])
        if result and result.value:
            v = result.value
            return {
                "name":        v.get("name", ""),
                "description": v.get("description", ""),
                "url":         v.get("url", ""),
                "github":      v.get("github_repo", ""),
                "discord":     v.get("discord", ""),
                "twitter":     v.get("twitter", ""),
                "image":       v.get("image", ""),
                "source":      "IdentitiesV2",
            }
    except Exception:
        pass

    try:
        result = sub.query_identity(ss58)
        if result:
            return {
                "name":        result.get("name", ""),
                "description": result.get("description", ""),
                "url":         result.get("web", ""),
                "github":      result.get("github_repo", ""),
                "discord":     result.get("discord", ""),
                "twitter":     result.get("twitter", ""),
                "image":       "",
                "source":      "query_identity",
            }
    except Exception:
        pass

    return {}

# ── Load and sort shadow wallets ──────────────────────────────────────────────
print(f"Loading {SHADOW_FILE}...")
wallets = []
with open(SHADOW_FILE) as f:
    for line in f:
        w = json.loads(line)
        wallets.append(w)

wallets.sort(key=lambda x: x["free_tao"], reverse=True)
print(f"  {len(wallets):,} shadow wallets loaded")

# ── Fix SS58 encoding for all wallets ─────────────────────────────────────────
print("Re-encoding SS58 addresses...")
fixed = 0
failed = 0
for w in wallets:
    ss58 = tuple_str_to_ss58(w["ss58"])
    if ss58:
        w["ss58_encoded"] = ss58
        fixed += 1
    else:
        w["ss58_encoded"] = None
        failed += 1

print(f"  Encoded: {fixed:,}  Failed: {failed:,}")

# ── Identity lookups for top N ────────────────────────────────────────────────
top = [w for w in wallets if w["ss58_encoded"] is not None][:TOP_N]
print(f"\nQuerying on-chain identity for top {len(top)} shadow wallets...")

for i, w in enumerate(top):
    identity = get_identity(w["ss58_encoded"])
    w["identity"] = identity
    has_id = bool(identity.get("name") or identity.get("description"))
    label = identity.get("name", "") if has_id else "(no identity)"
    print(f"  {i+1:3d}. {w['ss58_encoded'][:20]}...  {w['free_tao']:>12,.2f} TAO  {label}")
    time.sleep(0.1)   # be gentle on public RPC

# Fill identity = {} for wallets outside top N
for w in wallets[TOP_N:]:
    if "identity" not in w:
        w["identity"] = None   # not queried

# ── Write full JSONL with ss58_encoded ────────────────────────────────────────
with open(OUT_JSONL, "w") as f:
    for w in wallets:
        f.write(json.dumps(w) + "\n")
print(f"\nFull identified dataset saved to {OUT_JSONL}")

# ── Build top report ──────────────────────────────────────────────────────────
total_shadow_tao = sum(w["free_tao"] for w in wallets)
lines = []
lines.append("=" * 80)
lines.append(f"TOP {TOP_N} SHADOW WALLETS — IDENTITY REPORT")
lines.append(f"Block: {sub.get_current_block():,}   Total shadow TAO: {total_shadow_tao:,.2f}")
lines.append("=" * 80)
lines.append(f"{'Rank':<5} {'SS58 Address':<48} {'TAO':>12}  Identity")
lines.append("-" * 80)

for i, w in enumerate(top):
    ss58 = w.get("ss58_encoded") or "ENCODING_ERROR"
    tao  = w["free_tao"]
    ident = w.get("identity", {}) or {}
    name  = ident.get("name", "") or ""
    desc  = ident.get("description", "") or ""
    label = name or desc[:40] or "(no identity)"
    lines.append(f"{i+1:<5} {ss58:<48} {tao:>12,.2f}  {label}")

lines.append("=" * 80)

# Summary: how many of top N have any identity
has_identity = sum(1 for w in top if w.get("identity", {}) and (w["identity"].get("name") or w["identity"].get("description")))
lines.append(f"\nOf top {TOP_N}: {has_identity} have on-chain identity, {TOP_N - has_identity} have none.")

report = "\n".join(lines)
print("\n" + report)

with open(OUT_REPORT, "w") as f:
    f.write(report + "\n")
print(f"\nReport saved to {OUT_REPORT}")
