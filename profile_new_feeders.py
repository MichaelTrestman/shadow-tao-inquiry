import os
"""
profile_new_feeders.py

Traces one hop upstream of the 5 newly identified high-value senders to
Funder-A, discovered from the upstream_bfs_run.log. These addresses were
NOT in the original known-infrastructure set, and each sent thousands of
TAO to Funder-A (and possibly Funder-B) in recent blocks.

For each address we fetch:
  1. All inbound transfers >= 100 TAO (threshold high enough to skip noise)
  2. All outbound transfers >= 100 TAO
  3. Current nonce + balance (via tao.app API)
  4. Check every sender/receiver against known_holders.json

Addresses:
  EJMGn13   5EJMGn13311deMfe9pwZYd5bPkyMGs1ZmkmNtbpbv7wPcG9C  43.4k TAO -> Funder-A
  Gorfuxev7 5Gorfuxev7QmgDzBK92YrVW2K5PEvfZRW49SQrKm3VXcAGi1  20.3k TAO -> Funder-A, 17k TAO -> Funder-B
  HnhgYXb   5HnhgYXb9pJcAWceju1a5aZttSPpeMqYDNqUbxntGyUNqGxR  12.6k TAO -> Funder-A
  EfXUFMj   5EfXUFMjjc78YKgDrEta3SQFDvwvV7PtPnV2MKBd35SqvhQJ   7.3k TAO -> Funder-A
  FJMfoeUX  5FJMfoeUXsDXQSABaai8CUQvMyAK1a7jXqJvkBMnabfuJCjv   7.3k TAO -> Funder-A, 8.6k -> Funder-B

Output: profile_new_feeders_report.txt
"""

import json
import time
import requests

API_KEY  = os.environ["TAO_APP_API_KEY"]
BASE_URL     = "https://api.tao.app/api/beta/accounting/events"
RAO          = 1_000_000_000
MIN_TAO      = 100.0    # only flows >= 100 TAO; eliminates noise, keeps all meaningful transfers
HEADERS      = {"X-API-Key": API_KEY}
MAX_PAGES    = 500      # safety ceiling

ADDRESSES = {
    "EJMGn13 (round-trip feeder)":  "5EJMGn13311deMfe9pwZYd5bPkyMGs1ZmkmNtbpbv7wPcG9C",
    "Gorfuxev7 (cross-funder hub)": "5Gorfuxev7QmgDzBK92YrVW2K5PEvfZRW49SQrKm3VXcAGi1",
    "HnhgYXb (Funder-A sender)":    "5HnhgYXb9pJcAWceju1a5aZttSPpeMqYDNqUbxntGyUNqGxR",
    "EfXUFMj (Funder-A sender)":    "5EfXUFMjjc78YKgDrEta3SQFDvwvV7PtPnV2MKBd35SqvhQJ",
    "FJMfoeUX (cross-funder hub)":  "5FJMfoeUXsDXQSABaai8CUQvMyAK1a7jXqJvkBMnabfuJCjv",
}

FUNDER_A = "5EiXej3AwjKqb9mjQAf29JG5HJf9Dwtt8CjvDqA8biprWTiN"
FUNDER_B = "5DunDrFV6BPbzsgLZUtMQtCq7w9fcUEbM59BUwx5E7N9Bn5E"

# Load known holders
with open("known_holders.json") as f:
    known_raw = json.load(f)
known_by_ss58 = {}
for entry in known_raw:
    if not isinstance(entry, dict):
        continue
    addr = entry.get("ss58") or entry.get("coldkey") or entry.get("address")
    if not addr:
        continue
    identity = entry.get("identity") or {}
    name = (identity.get("name") if isinstance(identity, dict) else str(identity)) or "(no name)"
    known_by_ss58[addr] = {"name": name, "is_delegate_owner": entry.get("is_delegate_owner"),
                            "is_sn_owner": entry.get("is_sn_owner")}

print(f"Loaded {len(known_by_ss58)} known entities", flush=True)


def fetch_events(address: str, label: str) -> list:
    """Fetch all Transfer events for address; return list of event dicts."""
    all_events, page = [], 1
    while page <= MAX_PAGES:
        try:
            r = requests.get(BASE_URL, headers=HEADERS,
                             params={"coldkey": address, "page": page, "page_size": 100},
                             timeout=30)
        except Exception as e:
            print(f"  API error on page {page}: {e}", flush=True)
            break
        if r.status_code != 200:
            print(f"  HTTP {r.status_code}", flush=True)
            break
        data = r.json()
        rows = data.get("data", [])
        if not rows:
            break
        for row in rows:
            ts, blk, ext_idx, frm, to, amt_rao, fee, alpha, orig_net, dest_net, tx_type = row
            if tx_type == "Transfer" and amt_rao and (amt_rao / RAO) >= MIN_TAO:
                all_events.append({
                    "block": blk,
                    "from": frm or "",
                    "to": to or "",
                    "amount_tao": amt_rao / RAO,
                })
        total   = data.get("total", 0)
        fetched = (page - 1) * 100 + len(rows)
        print(f"  {label}: page {page} ({fetched}/{total})", flush=True)
        if fetched >= total:
            break
        page += 1
        time.sleep(0.2)
    return all_events


def summarize_events(address: str, events: list) -> dict:
    inbound  = [e for e in events if e["to"]   == address]
    outbound = [e for e in events if e["from"] == address]

    # Aggregate by counterparty
    senders   = {}
    receivers = {}
    for e in inbound:
        s = e["from"]
        senders[s] = senders.get(s, 0) + e["amount_tao"]
    for e in outbound:
        r = e["to"]
        receivers[r] = receivers.get(r, 0) + e["amount_tao"]

    top_senders   = sorted(senders.items(),   key=lambda x: -x[1])
    top_receivers = sorted(receivers.items(), key=lambda x: -x[1])

    return {
        "inbound_count":  len(inbound),
        "outbound_count": len(outbound),
        "in_total":  sum(e["amount_tao"] for e in inbound),
        "out_total": sum(e["amount_tao"] for e in outbound),
        "top_senders":   top_senders[:20],
        "top_receivers": top_receivers[:20],
        "first_in_block":  min((e["block"] for e in inbound),  default=None),
        "first_out_block": min((e["block"] for e in outbound), default=None),
    }


print("=" * 72, flush=True)
print("NEW FEEDER PROFILE INVESTIGATION", flush=True)
print("=" * 72, flush=True)

all_results = {}
for label, address in ADDRESSES.items():
    print(f"\nFetching: {label} ({address[:16]}...)", flush=True)
    events  = fetch_events(address, label)
    summary = summarize_events(address, events)
    all_results[label] = {"address": address, "summary": summary}
    print(f"  → {summary['inbound_count']} in ({summary['in_total']:,.1f} TAO) / "
          f"{summary['outbound_count']} out ({summary['out_total']:,.1f} TAO)", flush=True)


# ── Report ─────────────────────────────────────────────────────────────────

lines = [
    "=" * 72,
    "NEW FEEDER PROFILE REPORT",
    f"Min transfer threshold: {MIN_TAO} TAO",
    "=" * 72,
    "",
]

INFRA_ALL = {
    FUNDER_A: "Funder-A", FUNDER_B: "Funder-B",
    "5HB2Q8H9Rvxr3ejZ1o58FfXk3S3jMij6mB7Vu7b7SPqUdhTQ": "HB2Q8-hub",
    "5HUPxAsF52CX7RWAe3vDA7Wu7fiKT78dG3XpxRisfnwKYsn4": "HUPxAs",
    "5DfKewdxchFx7umvw6qcHKXKgvVxEtMFXFXVaXShjf7anzet": "DfKewdx",
    "5GBnPzvPghS8AuCoo6bfnK7JUFHuyUhWSFD4woBNsKnPiEUi": "GBnPzv",
}
ADDR_SET = set(ADDRESSES.values())

for label, result in all_results.items():
    addr = result["address"]
    s    = result["summary"]
    lines.append(f"{'─'*72}")
    lines.append(f"{label}")
    lines.append(f"  Address: {addr}")
    lines.append(f"  Inbound (>={MIN_TAO:.0f} TAO):  {s['inbound_count']:,} txs, {s['in_total']:>12,.2f} TAO")
    lines.append(f"  Outbound (>={MIN_TAO:.0f} TAO): {s['outbound_count']:,} txs, {s['out_total']:>12,.2f} TAO")
    if s["first_in_block"]:
        lines.append(f"  First inbound block:  {s['first_in_block']:,}")
    if s["first_out_block"]:
        lines.append(f"  First outbound block: {s['first_out_block']:,}")
    lines.append("")

    lines.append("  TOP SENDERS (upstream sources):")
    for counterparty, amt in s["top_senders"]:
        flag = ""
        if counterparty in known_by_ss58:
            flag = f"  *** KNOWN: {known_by_ss58[counterparty]['name']} ***"
        elif counterparty in INFRA_ALL:
            flag = f"  [infra: {INFRA_ALL[counterparty]}]"
        elif counterparty in ADDR_SET:
            flag = "  [other feeder in this set]"
        lines.append(f"    {counterparty}  {amt:>12,.2f} TAO{flag}")

    lines.append("")
    lines.append("  TOP RECEIVERS (downstream destinations):")
    for counterparty, amt in s["top_receivers"]:
        flag = ""
        if counterparty in known_by_ss58:
            flag = f"  *** KNOWN: {known_by_ss58[counterparty]['name']} ***"
        elif counterparty in INFRA_ALL:
            flag = f"  [infra: {INFRA_ALL[counterparty]}]"
        elif counterparty in ADDR_SET:
            flag = "  [other feeder in this set]"
        lines.append(f"    {counterparty}  {amt:>12,.2f} TAO{flag}")
    lines.append("")

report = "\n".join(lines)
print("\n\n" + report)
with open("profile_new_feeders_report.txt", "w") as f:
    f.write(report + "\n")
print("Saved to profile_new_feeders_report.txt")
