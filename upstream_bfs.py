import os
"""
upstream_bfs.py

Traces the funding lineage of the shadow whale cluster backward through the
transfer graph, expanding inward hop by hop until either:
  (a) a known entity (validator / SN owner / identity-registered) is reached, or
  (b) a protocol emission source (Deposit event, no transfer sender) is found, or
  (c) the queue is exhausted (untraceable within this API's coverage).

Key insight: the funding supply chain is CONVERGENT. Each hop upstream sees
fewer addresses, not more. Amount thresholds (MIN_AMOUNT_TAO) prune noise.
We only fetch INBOUND transfers — not full bilateral history — so even
high-nonce wallets are processed quickly.

The search is initialized with the full set of known shadow infrastructure
addresses. At each step, we pull the inbound events for the frontier address,
filter by MIN_AMOUNT_TAO, and check each sender against known_holders.json.
Any unknown sender is added to the queue.

Output:
  upstream_bfs_report.txt   — human-readable trace of the full search tree
  upstream_bfs.json         — raw results for further analysis
"""

import json
import time
import requests
from collections import deque

API_KEY  = os.environ["TAO_APP_API_KEY"]
BASE_URL      = "https://api.tao.app/api/beta/accounting/events"
RAO           = 1_000_000_000
MIN_AMOUNT_TAO = 10.0   # ignore sub-threshold transfers — these are dust/noise
MAX_HOPS      = 8       # safety ceiling; search terminates naturally before this
HEADERS       = {"X-API-Key": API_KEY}

# ── Load known entities ─────────────────────────────────────────────────────

with open("known_holders.json") as f:
    known_holders_raw = json.load(f)

# Build a lookup: ss58 → name/role
# Structure: {"ss58": "...", "identity": {"name": "...", ...}, "roles": [...], ...}
known_entities = {}
for entry in known_holders_raw:
    if not isinstance(entry, dict):
        continue
    addr = entry.get("ss58") or entry.get("coldkey") or entry.get("address")
    if not addr:
        continue
    identity = entry.get("identity") or {}
    name = (identity.get("name") if isinstance(identity, dict) else str(identity)) or "(no name)"
    roles = entry.get("roles") or entry.get("role") or []
    known_entities[addr] = {"name": name, "role": roles}

print(f"Loaded {len(known_entities)} known entities from known_holders.json")

# ── Shadow whale infrastructure — initial frontier ──────────────────────────

SHADOW_WALLETS = {
    "SW1":  "5FEA1FfUPwT3K4zTsYbQx5X1G9R2ZjYLyFv12xBQxW9QgoCL",
    "SW2":  "5ChHTBkaE1VgK5NX59uHuZoK8VQShojKBB1sGfXaZQpxVDCi",
    "SW3":  "5Dhf6WgqrfhVyFCGqK4G5utro2jepscwryMhLHtpMfopxweC",
    "SW4":  "5GUkyA37dHnc1rEijDtvBe5yYNCpaNjaHGqB7DY9Kb2KgSj3",
    "SW5":  "5C9CxW9355u1sqy6Np85FfGssJAdyA8cAsjjV9YP8aaLvjEY",
    "SW6":  "5Epz8SQ69FuZRLyjCAicn8i71SdyEYaWR5rZ5a1i1bgoxGaQ",
    "SW7":  "5GVKorR78gqQCV6mrWMWX95hHG93ZaRAUShZVBNT768dvqv8",
    "SW8":  "5HAe1pePzBuPqsF6BpTGN8vCngvKKJaRZ2HkHwFmJgWgAzcf",
    "SW9":  "5DwksfKHHG5rURh9jpGaq87m5k3Jn8BJbY9geeX7zTGQD8Pr",
    "SW10": "5CXHJRRk5WAQ8hTkzRDEK89pbsZD2e4Lu7KBTFrHcUQ6GZvz",
}

KNOWN_INFRA = {
    "Funder-A":             "5EiXej3AwjKqb9mjQAf29JG5HJf9Dwtt8CjvDqA8biprWTiN",
    "Funder-B":             "5DunDrFV6BPbzsgLZUtMQtCq7w9fcUEbM59BUwx5E7N9Bn5E",
    "HB2Q8 (hub)":          "5HB2Q8H9Rvxr3ejZ1o58FfXk3S3jMij6mB7Vu7b7SPqUdhTQ",
    "FV99mB (SW4 funder)":  "5FV99mBYw3tYrMTXXe52PDa69an1AE19aTrpnB4kzxW73yUj",
    "GBnPzv (SW8 funder)":  "5GBnPzvPghS8AuCoo6bfnK7JUFHuyUhWSFD4woBNsKnPiEUi",
    "HUPxAs (dust-act)":    "5HUPxAsF52CX7RWAe3vDA7Wu7fiKT78dG3XpxRisfnwKYsn4",
    "DfKewdx (FunderB-up)": "5DfKewdxchFx7umvw6qcHKXKgvVxEtMFXFXVaXShjf7anzet",
    "FXw2v9 (dust-act)":    "5FXw2v9BH1wMCoP4vws27FWMqLGXFK647NwGGRaMHVeSnzKE",
    "ESDyJB (shared feed)": "5ESDyJBqh3SRcmboQpHc3761pZqV5C9vrFPFy8qxtAzerktB",
}

# Layer 2 feeders of HB2Q8 — revealed by tao.app first-page inspection.
# We skip Funder-A and Funder-B as BFS seeds because:
#   - We already know their primary upstream is HB2Q8 / DfKewdx
#   - They have 67k+ events each; paginating them adds no new information
# Starting from layer 2 finds the same unknown territory faster.
LAYER2_FEEDERS = {
    "GBnPzv (feeds HB2Q8, funded SW8)": "5GBnPzvPghS8AuCoo6bfnK7JUFHuyUhWSFD4woBNsKnPiEUi",
    "CNChyk2 (feeds HB2Q8)":            "5CNChyk2fnVgVSZDLAVVFb4QBTMGm6WfuQvseBG6hj8xWzKP",
    "FZiuxCB (feeds HB2Q8)":            "5FZiuxCBt8p6PFDisJ9ZEbBaKNVKy6TeemVJd1Z6jscsdjib",
    "DS3BcDq (feeds HB2Q8)":            "5DS3BcDqhkBpn8gD1Es8BAMTTXSs76gTKuUQxDNNeBQ6WjGe",
    "DfKewdx (FunderB-up)":             "5DfKewdxchFx7umvw6qcHKXKgvVxEtMFXFXVaXShjf7anzet",
    "HUPxAs (dust-act both funders)":   "5HUPxAsF52CX7RWAe3vDA7Wu7fiKT78dG3XpxRisfnwKYsn4",
    "FXw2v9 (dust-act)":                "5FXw2v9BH1wMCoP4vws27FWMqLGXFK647NwGGRaMHVeSnzKE",
    "ESDyJB (shared feed A+B)":         "5ESDyJBqh3SRcmboQpHc3761pZqV5C9vrFPFy8qxtAzerktB",
    "HB2Q8 (hub itself)":               "5HB2Q8H9Rvxr3ejZ1o58FfXk3S3jMij6mB7Vu7b7SPqUdhTQ",
    "FV99mB (SW4 funder)":              "5FV99mBYw3tYrMTXXe52PDa69an1AE19aTrpnB4kzxW73yUj",
}

INFRA_BY_ADDR = {v: k for k, v in KNOWN_INFRA.items()}
ALL_SW        = set(SHADOW_WALLETS.values())
ALL_INFRA     = set(KNOWN_INFRA.values())

# ── State ───────────────────────────────────────────────────────────────────

# visited: addr → {"label": str, "hop": int, "via": addr, "amount": float, "block": int}
visited = {}

# Hop 0: shadow wallets (dead ends for BFS — no outbound)
for label, addr in SHADOW_WALLETS.items():
    visited[addr] = {"label": label, "hop": 0, "via": None, "amount": None, "block": None}

# Hop 1: Funder-A and Funder-B — mark visited but DO NOT queue (we know their upstream)
visited["5EiXej3AwjKqb9mjQAf29JG5HJf9Dwtt8CjvDqA8biprWTiN"] = {
    "label": "Funder-A (skip — upstream known)", "hop": 1, "via": "shadow-wallets", "amount": None, "block": None}
visited["5DunDrFV6BPbzsgLZUtMQtCq7w9fcUEbM59BUwx5E7N9Bn5E"] = {
    "label": "Funder-B (skip — upstream known)", "hop": 1, "via": "shadow-wallets", "amount": None, "block": None}

# Hop 2: start BFS from Layer 2 feeders — these are where we don't yet have upstream
for label, addr in LAYER2_FEEDERS.items():
    visited[addr] = {"label": label, "hop": 2, "via": "Funder-A/B or HB2Q8", "amount": None, "block": None}

# BFS queue: only layer 2 feeders
queue = deque()
for label, addr in LAYER2_FEEDERS.items():
    queue.append(addr)

hits        = []   # known entities found upstream
discoveries = []   # new unknown addresses found at each layer

print(f"\nStarting upstream BFS from {len(KNOWN_INFRA)} known infrastructure addresses")
print(f"Minimum transfer amount: {MIN_AMOUNT_TAO} TAO")
print(f"Known entities to check against: {len(known_entities)}")
print("=" * 72)


# ── Helpers ─────────────────────────────────────────────────────────────────

def get_inbound_above_threshold(address: str) -> list:
    """
    Fetch all inbound Transfer events >= MIN_AMOUNT_TAO for address.
    Only pulls transfers TO this address (inbound), ignoring outbound.
    Uses page_size=100; paginates until all events retrieved.
    """
    results, page = [], 1
    while True:
        try:
            r = requests.get(
                BASE_URL,
                headers=HEADERS,
                params={"coldkey": address, "page": page, "page_size": 100},
                timeout=30,
            )
        except Exception as e:
            print(f"  [API error: {e}]")
            break

        if r.status_code != 200:
            print(f"  [HTTP {r.status_code}: {r.text[:60]}]")
            break

        data = r.json()
        rows = data.get("data", [])
        if not rows:
            break

        for row in rows:
            ts, blk, ext_idx, frm, to, amt_rao, fee, alpha, orig_net, dest_net, tx_type = row
            if tx_type == "Transfer" and to == address and amt_rao and (amt_rao / RAO) >= MIN_AMOUNT_TAO:
                results.append({
                    "from": frm or "",
                    "amount_tao": amt_rao / RAO,
                    "block": blk,
                })

        total   = data.get("total", 0)
        fetched = (page - 1) * 100 + len(rows)
        if fetched >= total:
            break
        page += 1
        time.sleep(0.15)

    return results


# ── BFS ─────────────────────────────────────────────────────────────────────

current_hop = 1

while queue:
    addr = queue.popleft()
    info = visited[addr]
    hop  = info["hop"]

    if hop != current_hop:
        current_hop = hop
        print(f"\n{'='*60}")
        print(f"HOP {current_hop}: expanding {1 + sum(1 for q in queue if visited.get(q, {}).get('hop') == hop)} addresses")
        print(f"{'='*60}")

    label = info["label"]
    print(f"\n  [{label}] {addr[:16]}...", flush=True)

    inbound = get_inbound_above_threshold(addr)
    if not inbound:
        print(f"    No inbound transfers >= {MIN_AMOUNT_TAO} TAO found")
        continue

    # Aggregate by sender
    senders = {}
    for ev in inbound:
        frm = ev["from"]
        if frm not in senders:
            senders[frm] = {"total": 0.0, "count": 0, "first_block": ev["block"], "last_block": ev["block"]}
        senders[frm]["total"]      += ev["amount_tao"]
        senders[frm]["count"]      += 1
        senders[frm]["first_block"] = min(senders[frm]["first_block"], ev["block"])
        senders[frm]["last_block"]  = max(senders[frm]["last_block"],  ev["block"])

    # Sort by total descending
    for sender, stats in sorted(senders.items(), key=lambda x: -x[1]["total"]):
        print(f"    ← {sender[:16]}...  {stats['total']:>12,.2f} TAO  "
              f"({stats['count']} txs, blocks {stats['first_block']:,}–{stats['last_block']:,})")

        if sender in visited:
            print(f"       [already visited: {visited[sender]['label']}]")
            continue

        # Check known entities
        if sender in known_entities:
            entity = known_entities[sender]
            print(f"    *** KNOWN ENTITY REACHED ***")
            print(f"        Name:   {entity['name']}")
            print(f"        Role:   {entity['role']}")
            print(f"        Amount: {stats['total']:,.2f} TAO")
            print(f"        Via:    {label}")
            hits.append({
                "known_entity":   sender,
                "entity_name":    entity["name"],
                "entity_role":    str(entity["role"]),
                "funded":         addr,
                "funded_label":   label,
                "amount_tao":     stats["total"],
                "tx_count":       stats["count"],
                "first_block":    stats["first_block"],
                "last_block":     stats["last_block"],
                "hop_depth":      hop + 1,
            })
            visited[sender] = {
                "label":  f"KNOWN:{entity['name']}",
                "hop":    hop + 1,
                "via":    addr,
                "amount": stats["total"],
                "block":  stats["first_block"],
            }
            continue

        # Also check if it's a shadow wallet we already know
        if sender in ALL_SW:
            print(f"       [shadow wallet — circular, skip]")
            continue

        # New unknown address — add to frontier
        new_label = f"unknown-hop{hop+1}"
        visited[sender] = {
            "label":  new_label,
            "hop":    hop + 1,
            "via":    addr,
            "amount": stats["total"],
            "block":  stats["first_block"],
        }
        discoveries.append({
            "address":  sender,
            "hop":      hop + 1,
            "via":      addr,
            "via_label": label,
            "amount_tao": stats["total"],
            "first_block": stats["first_block"],
        })

        if hop + 1 <= MAX_HOPS:
            queue.append(sender)
            print(f"       [queued for hop {hop+1}]")

    time.sleep(0.1)


# ── Report ───────────────────────────────────────────────────────────────────

lines = [
    "=" * 72,
    "UPSTREAM BFS REPORT — Shadow Whale Funding Chain",
    "=" * 72,
    f"Min transfer threshold: {MIN_AMOUNT_TAO} TAO",
    f"Max hops: {MAX_HOPS}",
    f"Known entities checked: {len(known_entities)}",
    f"Total addresses visited: {len(visited)}",
    "",
]

lines.append("=" * 72)
lines.append("KNOWN ENTITIES REACHED IN UPSTREAM CHAIN")
lines.append("=" * 72)
if hits:
    for h in sorted(hits, key=lambda x: x["hop_depth"]):
        lines.append(f"\nHop {h['hop_depth']}: {h['entity_name']} ({h['entity_role']})")
        lines.append(f"  Address: {h['known_entity']}")
        lines.append(f"  Funded:  {h['funded_label']} ({h['funded'][:16]}...)")
        lines.append(f"  Amount:  {h['amount_tao']:,.2f} TAO over {h['tx_count']} txs")
        lines.append(f"  Blocks:  {h['first_block']:,} – {h['last_block']:,}")
else:
    lines.append("\nNone found within the search depth and amount threshold.")

lines.append("")
lines.append("=" * 72)
lines.append("FULL DISCOVERY TREE (unknown addresses found at each hop)")
lines.append("=" * 72)
for d in sorted(discoveries, key=lambda x: (x["hop"], -x["amount_tao"])):
    lines.append(f"  Hop {d['hop']}: {d['address']}")
    lines.append(f"    Via:    {d['via_label']}")
    lines.append(f"    Amount: {d['amount_tao']:,.2f} TAO  first block {d['first_block']:,}")

report = "\n".join(lines)
print("\n\n" + report)

with open("upstream_bfs_report.txt", "w") as f:
    f.write(report + "\n")
print("\nSaved to upstream_bfs_report.txt")

with open("upstream_bfs.json", "w") as f:
    json.dump({
        "hits":        hits,
        "discoveries": discoveries,
        "visited":     {k: v for k, v in visited.items() if v["hop"] > 0},
    }, f, indent=2)
print("Saved to upstream_bfs.json")
