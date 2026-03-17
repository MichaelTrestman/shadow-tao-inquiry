import os
"""
attacker_network_bfs.py

Expands the transfer graph around the supply-chain attack wallet and its
known network, using the same BFS approach as upstream_bfs.py but:

  - Runs bidirectionally (inbound AND outbound) on the hub wallet
  - Captures subnet-touching events (non-zero netuid) as a separate signal
  - Checks all discovered addresses against known_holders.json
  - Checks nonce + balance for every significant new address found
  - Collects suffix fingerprint matches (addresses ending in ...djib or ...LJsP)

Seed addresses (from investigate_attacker.py findings):
  TARGET   5H9brHhMA1km3Dp3YCx75oaimgxEYScxCfxbzQRZ3gHk9x3L  nonce 111  (the implicated wallet)
  HUB      5FZiuxCBt8p6PFDisJ9ZEbBaKNVKy6TeemVJd1Z6jscsdjib  nonce 41189 (sole counterparty)
  SEED     5DxcqzHjknv1gUReoRVYg1R6XjGgPMRD1ww4koTQND7ZLJsP  nonce 670   (earliest funder)
  DJIB2    5Ff8xfvJpZFv1gkj3UUz2PVS3pb5fzVQtoha7sfQWBn6djib  nonce 2696  (zero-amt prober, djib pair)
  LJSP2    5DJ6DF9ywrVPpdemxGTP1mNBegdexD3UnUy2SAMvdw84LJsP  nonce 180   (zero-amt prober, LJsP pair)

Output:
  attacker_network_bfs_report.txt  — human-readable full report
  attacker_network_bfs.json        — raw graph data
"""

import json
import time
from collections import defaultdict, deque

import requests
import bittensor as bt

# ── Config ────────────────────────────────────────────────────────────────────

API_KEY  = os.environ["TAO_APP_API_KEY"]
BASE_URL      = "https://api.tao.app/api/beta/accounting/events"
RAO           = 1_000_000_000
HEADERS       = {"X-API-Key": API_KEY}
MIN_TAO       = 10.0    # ignore dust transfers in BFS expansion
MAX_HOPS      = 3       # hops beyond the seed layer

# Known vanity suffixes to watch for across the whole graph
VANITY_SUFFIXES = ["djib", "LJsP"]

# Seed network — the addresses we already know about
SEED_ADDRS = {
    "TARGET": "5H9brHhMA1km3Dp3YCx75oaimgxEYScxCfxbzQRZ3gHk9x3L",
    "HUB":    "5FZiuxCBt8p6PFDisJ9ZEbBaKNVKy6TeemVJd1Z6jscsdjib",
    "SEED":   "5DxcqzHjknv1gUReoRVYg1R6XjGgPMRD1ww4koTQND7ZLJsP",
    "DJIB2":  "5Ff8xfvJpZFv1gkj3UUz2PVS3pb5fzVQtoha7sfQWBn6djib",
    "LJSP2":  "5DJ6DF9ywrVPpdemxGTP1mNBegdexD3UnUy2SAMvdw84LJsP",
}
SEED_BY_ADDR = {v: k for k, v in SEED_ADDRS.items()}
ALL_SEEDS    = set(SEED_ADDRS.values())


# ── Load known entities ───────────────────────────────────────────────────────

print("Loading known_holders.json...")
with open("known_holders.json") as f:
    known_holders_raw = json.load(f)

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
    known_entities[addr] = {"name": name, "roles": roles}

print(f"  {len(known_entities)} known entities loaded")


# ── Bittensor substrate connection ────────────────────────────────────────────

print("Connecting to Finney...")
sub = bt.Subtensor(network="finney")
print(f"  Connected at block {sub.get_current_block():,}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def fetch_all_events(address: str, label: str = "") -> list:
    """
    Fetch complete event history for address via tao.app API.
    Returns all events regardless of type or direction.
    Retries on 429 with exponential backoff.
    """
    all_events = []
    page = 1
    while True:
        params = {"coldkey": address, "page": page, "page_size": 100}
        try:
            r = requests.get(BASE_URL, headers=HEADERS, params=params, timeout=30)
        except Exception as e:
            print(f"    [network error: {e}]")
            break
        if r.status_code == 429:
            wait = 30
            print(f"    [429 rate limit — waiting {wait}s]", flush=True)
            time.sleep(wait)
            continue
        if r.status_code != 200:
            print(f"    [HTTP {r.status_code}]")
            break
        data = r.json()
        rows = data.get("data", [])
        if not rows:
            break
        for row in rows:
            ts, blk, ext_idx, frm, to, amount_rao, fee, alpha, orig_net, dest_net, tx_type = row
            all_events.append({
                "timestamp":   ts,
                "block":       blk,
                "from":        frm or "",
                "to":          to  or "",
                "amount_tao":  (amount_rao or 0) / RAO,
                "alpha":       alpha,
                "orig_netuid": orig_net,
                "dest_netuid": dest_net,
                "tx_type":     tx_type,
            })
        total   = data.get("total", 0)
        fetched = (page - 1) * 100 + len(rows)
        if label:
            print(f"    {label}: page {page} ({fetched}/{total})", flush=True)
        if fetched >= total:
            break
        page += 1
        time.sleep(0.2)
    return all_events


def get_nonce_balance(address: str) -> tuple:
    try:
        result = sub.substrate.query("System", "Account", [address])
        val = result if isinstance(result, dict) else (result.value if hasattr(result, "value") else None)
        if val:
            return val["nonce"], val["data"]["free"] / RAO
    except Exception:
        pass
    return None, None


def get_identity(address: str) -> str:
    try:
        result = sub.substrate.query("SubtensorModule", "IdentitiesV2", [address])
        val = result if isinstance(result, dict) else (result.value if hasattr(result, "value") else None)
        if val:
            return val.get("name", "") or str(val)
    except Exception:
        pass
    return ""


def check_vanity_suffix(address: str) -> list:
    return [s for s in VANITY_SUFFIXES if address.endswith(s)]


def summarise_events(events: list, address: str) -> dict:
    """Aggregate events by counterparty, split inbound/outbound."""
    inbound  = defaultdict(lambda: {"tao": 0.0, "count": 0, "first": 9e18, "last": 0})
    outbound = defaultdict(lambda: {"tao": 0.0, "count": 0, "first": 9e18, "last": 0})
    subnet_events = []

    for e in events:
        if e["tx_type"] not in ("Transfer", "transfer"):
            continue
        blk = e["block"] or 0
        amt = e["amount_tao"]

        # Subnet-touching: non-zero netuid on either side
        if e["orig_netuid"] or e["dest_netuid"]:
            subnet_events.append(e)

        if e["to"] == address:
            bucket = inbound[e["from"]]
        elif e["from"] == address:
            bucket = outbound[e["to"]]
        else:
            continue

        bucket["tao"]   += amt
        bucket["count"] += 1
        bucket["first"]  = min(bucket["first"], blk)
        bucket["last"]   = max(bucket["last"],  blk)

    return {
        "inbound":       dict(inbound),
        "outbound":      dict(outbound),
        "subnet_events": subnet_events,
    }


lines = []
raw   = {"seeds": {}, "discovered": {}, "known_hits": [], "subnet_events": [], "vanity_hits": []}

def p(s=""):
    lines.append(s)
    print(s)


# ── Phase 1: Profile all seed addresses ───────────────────────────────────────

p("=" * 72)
p("ATTACKER NETWORK BFS — Phase 1: Seed Address Profiles")
p("=" * 72)

seed_summaries = {}

for label, addr in SEED_ADDRS.items():
    p()
    p(f"{'─'*72}")
    p(f"[{label}] {addr}")
    p(f"{'─'*72}")

    nonce, bal = get_nonce_balance(addr)
    identity   = get_identity(addr)
    vanity     = check_vanity_suffix(addr)

    p(f"  Nonce:    {nonce:,}" if nonce is not None else "  Nonce:    [error]")
    p(f"  Balance:  {bal:,.3f} TAO" if bal is not None else "  Balance:  [error]")
    p(f"  Identity: {identity}" if identity else "  Identity: [none]")
    if vanity:
        p(f"  VANITY SUFFIX MATCH: {vanity}")
    if addr in known_entities:
        p(f"  KNOWN ENTITY: {known_entities[addr]}")

    p(f"  Fetching full event history...")
    events = fetch_all_events(addr, label=label)
    p(f"  Total events: {len(events)}")

    summary = summarise_events(events, addr)
    seed_summaries[addr] = summary

    in_total  = sum(v["tao"] for v in summary["inbound"].values())
    out_total = sum(v["tao"] for v in summary["outbound"].values())
    p(f"  Inbound:  {len(summary['inbound'])} counterparties  {in_total:>12,.2f} TAO")
    p(f"  Outbound: {len(summary['outbound'])} counterparties  {out_total:>12,.2f} TAO")

    if summary["subnet_events"]:
        p(f"  *** SUBNET-TOUCHING EVENTS: {len(summary['subnet_events'])} ***")
        for se in summary["subnet_events"][:20]:
            p(f"    block {se['block']:>10,}  {se['tx_type']:<20}  "
              f"{se['amount_tao']:>10,.3f} TAO  "
              f"netuid {se['orig_netuid']} -> {se['dest_netuid']}  "
              f"from {se['from'][:16]}... to {se['to'][:16]}...")
        raw["subnet_events"].extend(summary["subnet_events"])

    # Top counterparties
    p()
    p("  Top inbound senders:")
    for sender, st in sorted(summary["inbound"].items(), key=lambda x: -x[1]["tao"])[:10]:
        known = known_entities.get(sender, {})
        vsuffix = check_vanity_suffix(sender)
        flag = f" [KNOWN: {known['name']}]" if known else ""
        flag += f" [VANITY: {vsuffix}]" if vsuffix else ""
        in_seed = f" [{SEED_BY_ADDR[sender]}]" if sender in SEED_BY_ADDR else ""
        p(f"    {sender}  {st['tao']:>12,.2f} TAO  {st['count']:>5}x  blk {int(st['first']):,}{flag}{in_seed}")

    p()
    p("  Top outbound recipients:")
    for recip, st in sorted(summary["outbound"].items(), key=lambda x: -x[1]["tao"])[:10]:
        known = known_entities.get(recip, {})
        vsuffix = check_vanity_suffix(recip)
        flag = f" [KNOWN: {known['name']}]" if known else ""
        flag += f" [VANITY: {vsuffix}]" if vsuffix else ""
        in_seed = f" [{SEED_BY_ADDR[recip]}]" if recip in SEED_BY_ADDR else ""
        p(f"    {recip}  {st['tao']:>12,.2f} TAO  {st['count']:>5}x  blk {int(st['first']):,}{flag}{in_seed}")

    raw["seeds"][addr] = {
        "label": label, "nonce": nonce, "balance": bal, "identity": identity,
        "vanity": vanity,
        "inbound_count": len(summary["inbound"]),
        "outbound_count": len(summary["outbound"]),
        "subnet_event_count": len(summary["subnet_events"]),
    }

    time.sleep(0.3)


# ── Phase 2: BFS expansion ────────────────────────────────────────────────────

p()
p("=" * 72)
p("ATTACKER NETWORK BFS — Phase 2: Graph Expansion")
p("=" * 72)

# Build initial frontier: all counterparties of all seeds above MIN_TAO
# that are not already in the seed set
visited = dict(SEED_BY_ADDR)   # addr -> label
queue   = deque()

for addr, summary in seed_summaries.items():
    seed_label = SEED_BY_ADDR[addr]
    all_parties = {}
    for cp, st in summary["inbound"].items():
        all_parties[cp] = max(all_parties.get(cp, 0), st["tao"])
    for cp, st in summary["outbound"].items():
        all_parties[cp] = max(all_parties.get(cp, 0), st["tao"])

    for cp, tao in all_parties.items():
        if cp in visited or tao < MIN_TAO:
            continue
        visited[cp] = f"hop1-via-{seed_label}"
        queue.append((cp, 1, seed_label, tao))

p(f"Initial BFS frontier: {len(queue)} addresses from seed counterparties")

known_hits   = []
vanity_hits  = []
discoveries  = []

while queue:
    addr, hop, via_label, via_tao = queue.popleft()

    if hop > MAX_HOPS:
        continue

    # Check known entity first — if hit, record and don't expand further
    if addr in known_entities:
        entity = known_entities[addr]
        p(f"\n  *** KNOWN ENTITY at hop {hop} ***")
        p(f"      {entity['name']} | roles: {entity['roles']}")
        p(f"      Address: {addr}")
        p(f"      Via: {via_label}  ({via_tao:,.2f} TAO)")
        known_hits.append({
            "address": addr, "hop": hop, "via": via_label,
            "tao": via_tao, "name": entity["name"], "roles": str(entity["roles"])
        })
        continue

    # Quick nonce check
    nonce, bal = get_nonce_balance(addr)
    identity   = get_identity(addr)
    vanity     = check_vanity_suffix(addr)

    # Flag vanity suffix matches
    if vanity:
        p(f"\n  *** VANITY SUFFIX MATCH at hop {hop}: {vanity} ***")
        p(f"      {addr}")
        p(f"      Nonce {nonce}  Balance {bal:,.2f} TAO  Via {via_label}")
        vanity_hits.append({"address": addr, "suffix": vanity, "hop": hop,
                             "nonce": nonce, "balance": bal, "via": via_label})
        raw["vanity_hits"].append({"address": addr, "suffix": vanity, "hop": hop})

    discovery = {
        "address": addr, "hop": hop, "via": via_label, "tao": via_tao,
        "nonce": nonce, "balance": bal, "identity": identity, "vanity": vanity,
    }

    # Decide whether to expand this address (fetch its events)
    # Only expand if: high-value (>500 TAO) OR high-nonce (>100) OR identity present
    should_expand = (via_tao >= 500 or (nonce or 0) > 100 or bool(identity)) and hop < MAX_HOPS

    if should_expand:
        p(f"\n  [hop {hop}] Expanding {addr[:20]}...  "
          f"nonce={nonce}  bal={bal:,.0f}  via={via_label}  {via_tao:,.0f} TAO")

        events  = fetch_all_events(addr)
        summary = summarise_events(events, addr)

        if summary["subnet_events"]:
            p(f"    *** SUBNET EVENTS: {len(summary['subnet_events'])} ***")
            for se in summary["subnet_events"][:10]:
                p(f"      block {se['block']:>10,}  netuid {se['orig_netuid']} -> {se['dest_netuid']}  "
                  f"{se['amount_tao']:>10,.3f} TAO")
            raw["subnet_events"].extend(summary["subnet_events"])

        # Enqueue new counterparties
        all_parties = {}
        for cp, st in summary["inbound"].items():
            all_parties[cp] = max(all_parties.get(cp, 0), st["tao"])
        for cp, st in summary["outbound"].items():
            all_parties[cp] = max(all_parties.get(cp, 0), st["tao"])

        for cp, tao in all_parties.items():
            if cp in visited or tao < MIN_TAO:
                continue
            vsuffix = check_vanity_suffix(cp)
            if vsuffix:
                p(f"    [VANITY SUFFIX FOUND in counterparties: {cp} -> {vsuffix}]")
                raw["vanity_hits"].append({"address": cp, "suffix": vsuffix, "hop": hop + 1})
            visited[cp] = f"hop{hop+1}-via-{addr[:10]}"
            queue.append((cp, hop + 1, addr[:16], tao))

        discovery["inbound_count"]  = len(summary["inbound"])
        discovery["outbound_count"] = len(summary["outbound"])
        discovery["subnet_events"]  = len(summary["subnet_events"])

        time.sleep(0.3)
    else:
        p(f"  [hop {hop}] Skip expand {addr[:20]}...  "
          f"nonce={nonce}  bal={bal:,.0f}  {via_tao:,.0f} TAO  (below threshold)", flush=True)

    discoveries.append(discovery)
    raw["discovered"][addr] = discovery


# ── Phase 3: Report ───────────────────────────────────────────────────────────

p()
p("=" * 72)
p("ATTACKER NETWORK BFS — Summary")
p("=" * 72)

p()
p("KNOWN ENTITIES REACHED:")
p("─" * 72)
if known_hits:
    for h in sorted(known_hits, key=lambda x: x["hop"]):
        p(f"  Hop {h['hop']}  {h['name']}")
        p(f"          roles:   {h['roles']}")
        p(f"          address: {h['address']}")
        p(f"          via:     {h['via']}  ({h['tao']:,.2f} TAO)")
else:
    p("  None found within search depth and amount threshold.")

p()
p("SUBNET-TOUCHING EVENTS:")
p("─" * 72)
subnet_all = raw["subnet_events"]
if subnet_all:
    # Deduplicate by block+from+to
    seen = set()
    unique_subnet = []
    for se in subnet_all:
        key = (se["block"], se["from"], se["to"])
        if key not in seen:
            seen.add(key)
            unique_subnet.append(se)
    p(f"  {len(unique_subnet)} unique subnet-touching events found across the network:")
    for se in sorted(unique_subnet, key=lambda x: x["block"] or 0):
        p(f"  block {se['block']:>10,}  netuid {str(se['orig_netuid']):>4} -> {str(se['dest_netuid']):<4}  "
          f"{se['amount_tao']:>12,.3f} TAO  "
          f"from {se['from'][:16]}...  to {se['to'][:16]}...")
else:
    p("  No subnet-touching events found in the attacker network.")

p()
p("VANITY SUFFIX MATCHES (beyond seeds):")
p("─" * 72)
if vanity_hits:
    for v in vanity_hits:
        p(f"  {v['address']}  suffix={v['suffix']}  hop={v['hop']}  "
          f"nonce={v.get('nonce')}  bal={v.get('balance', 0):,.2f} TAO  via={v['via']}")
else:
    p("  No additional vanity-suffix addresses found beyond seed set.")

p()
p("FULL DISCOVERY TREE:")
p("─" * 72)
for d in sorted(discoveries, key=lambda x: (x["hop"], -(x.get("tao") or 0))):
    known_flag  = " [KNOWN]"  if d["address"] in known_entities else ""
    vanity_flag = f" [VANITY:{d['vanity']}]" if d.get("vanity") else ""
    subnet_flag = f" [SUBNET:{d.get('subnet_events',0)}]" if d.get("subnet_events") else ""
    p(f"  hop {d['hop']}  {d['address']}  "
      f"nonce={d['nonce']}  bal={d.get('balance',0) or 0:>10,.0f} TAO  "
      f"via={d['via'][:16]}  {d.get('tao',0):>10,.0f} TAO{known_flag}{vanity_flag}{subnet_flag}")

p()
p(f"Total addresses visited: {len(visited)}")
p(f"Known entities reached:  {len(known_hits)}")
p(f"Subnet events found:     {len(raw['subnet_events'])}")
p(f"Vanity suffix hits:      {len(raw['vanity_hits'])}")


# ── Write output ──────────────────────────────────────────────────────────────

report = "\n".join(lines)
with open("attacker_network_bfs_report.txt", "w") as f:
    f.write(report + "\n")
print("\nSaved: attacker_network_bfs_report.txt")

raw["known_hits"]  = known_hits
raw["discoveries"] = discoveries
with open("attacker_network_bfs.json", "w") as f:
    json.dump(raw, f, indent=2, default=str)
print("Saved: attacker_network_bfs.json")
