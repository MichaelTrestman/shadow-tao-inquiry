"""
Check whether top shadow wallets are involved in the child hotkey system.

The childkey system allows a parent validator hotkey to designate child hotkeys
that receive a proportion of the parent's validator take. Take flows as free
balance to the child hotkey — which would explain: growing balances, nonce=0,
no stake in StakingColdkeys.

Two things to check for each shadow wallet address:
  1. Is it listed as a CHILD HOTKEY in the ChildKeys map?
     (parent_hotkey, netuid) -> Vec<(proportion, child_hotkey)>
  2. Does it appear as a PARENT HOTKEY with children?
     i.e. is it itself a parent validator routing take to others?

We enumerate ChildKeys and ParentKeys maps and cross-reference against
the top shadow wallet addresses.
"""

import ast
import json
from pathlib import Path

import bittensor as bt
from scalecodec.utils.ss58 import ss58_encode

SHADOW_FILE = "finney_shadow_identified.jsonl"
OUT_FILE    = "childkey_check.json"
SS58_FORMAT = 42
TOP_N       = 50   # check top 50 shadow wallets

sub = bt.Subtensor(network="archive")
block = sub.get_current_block()
print(f"Connected to archive at block {block:,}")

# ── Load top shadow wallets ───────────────────────────────────────────────────
wallets = []
with open(SHADOW_FILE) as f:
    for line in f:
        w = json.loads(line)
        if w.get("ss58_encoded"):
            wallets.append(w)
wallets.sort(key=lambda x: x["free_tao"], reverse=True)
top = wallets[:TOP_N]
shadow_addresses = {w["ss58_encoded"] for w in top}
print(f"Loaded {len(shadow_addresses)} shadow wallet addresses to check")

# ── Enumerate ChildKeys map ───────────────────────────────────────────────────
# ChildKeys: (parent_hotkey, netuid) -> Vec<(proportion, child_hotkey)>
print("\nEnumerating ChildKeys map (parent_hotkey, netuid -> child_hotkeys)...")
child_key_relationships = []   # list of {parent, netuid, proportion, child}
shadow_as_child = []           # shadow wallets found as child hotkeys
shadow_as_parent = []          # shadow wallets found as parent hotkeys

try:
    count = 0
    for (parent_hk, netuid), children in sub.query_map("SubtensorModule", "ChildKeys"):
        parent_str = str(parent_hk)
        # Try to encode parent as ss58 if it's a byte tuple
        try:
            if isinstance(parent_hk, tuple):
                parent_ss58 = ss58_encode(bytes(parent_hk[0]), ss58_format=SS58_FORMAT)
            else:
                parent_ss58 = parent_str
        except Exception:
            parent_ss58 = parent_str

        netuid_int = int(str(netuid))

        # children is Vec<(u64, AccountId)> = list of (proportion, child_hotkey)
        children_val = children.value if hasattr(children, 'value') else children
        if not children_val:
            continue

        for proportion, child_hk in children_val:
            try:
                if isinstance(child_hk, (list, tuple)):
                    child_ss58 = ss58_encode(bytes(child_hk), ss58_format=SS58_FORMAT)
                else:
                    child_ss58 = str(child_hk)
            except Exception:
                child_ss58 = str(child_hk)

            rel = {
                "parent": parent_ss58,
                "netuid": netuid_int,
                "proportion": int(str(proportion)),
                "child": child_ss58,
            }
            child_key_relationships.append(rel)

            if child_ss58 in shadow_addresses:
                shadow_as_child.append(rel)
                print(f"  !! SHADOW WALLET IS CHILD: {child_ss58[:20]}... "
                      f"netuid={netuid_int} parent={parent_ss58[:20]}...")

            if parent_ss58 in shadow_addresses:
                shadow_as_parent.append(rel)
                print(f"  !! SHADOW WALLET IS PARENT: {parent_ss58[:20]}... "
                      f"-> child={child_ss58[:20]}... netuid={netuid_int}")

        count += 1
        if count % 500 == 0:
            print(f"  {count:,} parent hotkeys processed...", flush=True)

    print(f"\nTotal child key relationships found: {len(child_key_relationships):,}")
    print(f"Shadow wallets appearing as CHILD hotkey: {len(shadow_as_child)}")
    print(f"Shadow wallets appearing as PARENT hotkey: {len(shadow_as_parent)}")

except Exception as e:
    print(f"ChildKeys enumeration failed: {e}")

# ── Save results ──────────────────────────────────────────────────────────────
out = {
    "block": block,
    "shadow_addresses_checked": list(shadow_addresses),
    "total_child_relationships": len(child_key_relationships),
    "shadow_as_child": shadow_as_child,
    "shadow_as_parent": shadow_as_parent,
}
with open(OUT_FILE, "w") as f:
    json.dump(out, f, indent=2)
print(f"\nResults saved to {OUT_FILE}")

if not shadow_as_child and not shadow_as_parent:
    print("\nNo shadow wallets found in the child key system.")
    print("The growing balances have a different source.")
