import os
"""
profile_gbonpzv.py

Profiles GBnPzv (5GBnPzvPghS8AuCoo6bfnK7JUFHuyUhWSFD4woBNsKnPiEUi) — the dominant
upstream source of both Gorfuxev7 and FJMfoeUX, and the direct first funder of SW#8.

GBnPzv showed 0 events in taoapp_investigation.py when queried directly — possibly
because it predates the API's coverage or uses a different index key. This script:

1. Queries the tao.app API directly for GBnPzv (both with page_size and without
   the 100 TAO threshold) to confirm whether the API has any data for it.
2. If data found: reports top senders and receivers.
3. Separately, queries the same addresses that GBnPzv sent to (Gorfuxev7, FJMfoeUX)
   to cross-reference the inbound from GBnPzv — we have that data already.
4. Also profiles the other key upstream address seen in FJMfoeUX's senders:
   5CNChyk2fnVgVSZDLAVVFb4QBTMGm6WfuQvseBG6hj8xWzKP  (9,092 TAO → FJMfoeUX)
   5HbDZ6ULuwZegAMSPaS2kaUfBLMDaht5t48RcDrQATSgGCAR  (6,624 TAO → Gorfuxev7; 2,201 TAO → FJMfoeUX)

Output: profile_gbonpzv_report.txt
"""

import json
import time
import requests

API_KEY  = os.environ["TAO_APP_API_KEY"]
BASE_URL  = "https://api.tao.app/api/beta/accounting/events"
RAO       = 1_000_000_000
HEADERS   = {"X-API-Key": API_KEY}
MAX_PAGES = 500

ADDRESSES = {
    "GBnPzv (dominant upstream)": "5GBnPzvPghS8AuCoo6bfnK7JUFHuyUhWSFD4woBNsKnPiEUi",
    "CNChyk2 (FJMfoeUX sender)":  "5CNChyk2fnVgVSZDLAVVFb4QBTMGm6WfuQvseBG6hj8xWzKP",
    "HbDZ6UL (dual feeder)":      "5HbDZ6ULuwZegAMSPaS2kaUfBLMDaht5t48RcDrQATSgGCAR",
}

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
    known_by_ss58[addr] = name

print(f"Loaded {len(known_by_ss58)} known entities", flush=True)

INFRA_LABELS = {
    "5EiXej3AwjKqb9mjQAf29JG5HJf9Dwtt8CjvDqA8biprWTiN": "Funder-A",
    "5DunDrFV6BPbzsgLZUtMQtCq7w9fcUEbM59BUwx5E7N9Bn5E": "Funder-B",
    "5HB2Q8H9Rvxr3ejZ1o58FfXk3S3jMij6mB7Vu7b7SPqUdhTQ": "HB2Q8-hub",
    "5FV99mBYw3tYrMTXXe52PDa69an1AE19aTrpnB4kzxW73yUj": "FV99mB",
    "5HUPxAsF52CX7RWAe3vDA7Wu7fiKT78dG3XpxRisfnwKYsn4": "HUPxAs",
    "5DfKewdxchFx7umvw6qcHKXKgvVxEtMFXFXVaXShjf7anzet": "DfKewdx",
    "5GBnPzvPghS8AuCoo6bfnK7JUFHuyUhWSFD4woBNsKnPiEUi": "GBnPzv",
    "5Gorfuxev7QmgDzBK92YrVW2K5PEvfZRW49SQrKm3VXcAGi1": "Gorfuxev7",
    "5FJMfoeUXsDXQSABaai8CUQvMyAK1a7jXqJvkBMnabfuJCjv": "FJMfoeUX",
    "5EJMGn13311deMfe9pwZYd5bPkyMGs1ZmkmNtbpbv7wPcG9C": "EJMGn13",
    "5HnhgYXb9pJcAWceju1a5aZttSPpeMqYDNqUbxntGyUNqGxR": "HnhgYXb",
    "5EfXUFMjjc78YKgDrEta3SQFDvwvV7PtPnV2MKBd35SqvhQJ": "EfXUFMj",
    "5FEA1FfUPwT3K4zTsYbQx5X1G9R2ZjYLyFv12xBQxW9QgoCL": "SW1",
    "5ChHTBkaE1VgK5NX59uHuZoK8VQShojKBB1sGfXaZQpxVDCi": "SW2",
    "5Dhf6WgqrfhVyFCGqK4G5utro2jepscwryMhLHtpMfopxweC": "SW3",
    "5GUkyA37dHnc1rEijDtvBe5yYNCpaNjaHGqB7DY9Kb2KgSj3": "SW4",
    "5C9CxW9355u1sqy6Np85FfGssJAdyA8cAsjjV9YP8aaLvjEY": "SW5",
    "5Epz8SQ69FuZRLyjCAicn8i71SdyEYaWR5rZ5a1i1bgoxGaQ": "SW6",
    "5GVKorR78gqQCV6mrWMWX95hHG93ZaRAUShZVBNT768dvqv8": "SW7",
    "5HAe1pePzBuPqsF6BpTGN8vCngvKKJaRZ2HkHwFmJgWgAzcf": "SW8",
}


def fetch_all_events(address: str, label: str, min_tao: float = 0.0) -> list:
    all_events, page = [], 1
    while page <= MAX_PAGES:
        try:
            r = requests.get(BASE_URL, headers=HEADERS,
                             params={"coldkey": address, "page": page, "page_size": 100},
                             timeout=30)
        except Exception as e:
            print(f"  [API error page {page}: {e}]", flush=True)
            break
        if r.status_code != 200:
            print(f"  [HTTP {r.status_code}]", flush=True)
            break
        data = r.json()
        rows = data.get("data", [])
        if not rows:
            break
        for row in rows:
            ts, blk, ext_idx, frm, to, amt_rao, fee, alpha, orig_net, dest_net, tx_type = row
            if tx_type == "Transfer" and amt_rao and (amt_rao / RAO) >= min_tao:
                all_events.append({"block": blk, "from": frm or "", "to": to or "",
                                   "amount_tao": amt_rao / RAO})
        total   = data.get("total", 0)
        fetched = (page - 1) * 100 + len(rows)
        print(f"  {label}: page {page} ({fetched}/{total})", flush=True)
        if fetched >= total:
            break
        page += 1
        time.sleep(0.2)
    return all_events


def summarize(address: str, events: list, min_tao: float) -> dict:
    inbound  = [e for e in events if e["to"]   == address]
    outbound = [e for e in events if e["from"] == address]
    senders, receivers = {}, {}
    for e in inbound:
        s = e["from"]
        senders[s] = senders.get(s, 0) + e["amount_tao"]
    for e in outbound:
        r = e["to"]
        receivers[r] = receivers.get(r, 0) + e["amount_tao"]
    return {
        "in_count": len(inbound), "out_count": len(outbound),
        "in_total":  sum(e["amount_tao"] for e in inbound),
        "out_total": sum(e["amount_tao"] for e in outbound),
        "top_senders":   sorted(senders.items(),   key=lambda x: -x[1])[:20],
        "top_receivers": sorted(receivers.items(), key=lambda x: -x[1])[:20],
        "first_in":  min((e["block"] for e in inbound),  default=None),
        "first_out": min((e["block"] for e in outbound), default=None),
    }


def flag(addr: str) -> str:
    if addr in known_by_ss58:
        return f"  *** KNOWN: {known_by_ss58[addr]} ***"
    if addr in INFRA_LABELS:
        return f"  [infra: {INFRA_LABELS[addr]}]"
    return ""


print("=" * 72, flush=True)
print("GBONPZV UPSTREAM INVESTIGATION", flush=True)
print("=" * 72, flush=True)

all_results = {}
for label, address in ADDRESSES.items():
    # Try with no threshold first to see if API has data at all
    print(f"\nFetching: {label} ({address[:16]}...)", flush=True)
    events  = fetch_all_events(address, label, min_tao=0.0)
    summary = summarize(address, events, min_tao=0.0)
    all_results[label] = {"address": address, "summary": summary, "events": events}
    print(f"  → {summary['in_count']} in ({summary['in_total']:,.1f} TAO) / "
          f"{summary['out_count']} out ({summary['out_total']:,.1f} TAO)", flush=True)


# ── Report ──────────────────────────────────────────────────────────────────

lines = ["=" * 72, "GBONPZV UPSTREAM INVESTIGATION REPORT", "=" * 72, ""]

for label, result in all_results.items():
    addr = result["address"]
    s    = result["summary"]
    lines.append(f"{'─'*72}")
    lines.append(f"{label}")
    lines.append(f"  Address: {addr}")
    if s["in_count"] == 0 and s["out_count"] == 0:
        lines.append("  NO EVENTS FOUND via tao.app API (address not indexed or pre-coverage)")
        lines.append("")
        continue
    lines.append(f"  Inbound:  {s['in_count']:,} txs, {s['in_total']:>12,.2f} TAO  "
                 f"(first block {s['first_in']})")
    lines.append(f"  Outbound: {s['out_count']:,} txs, {s['out_total']:>12,.2f} TAO  "
                 f"(first block {s['first_out']})")
    lines.append("")
    lines.append("  TOP SENDERS (upstream sources):")
    for counterparty, amt in s["top_senders"]:
        lines.append(f"    {counterparty}  {amt:>12,.2f} TAO{flag(counterparty)}")
    lines.append("")
    lines.append("  TOP RECEIVERS (downstream destinations):")
    for counterparty, amt in s["top_receivers"]:
        lines.append(f"    {counterparty}  {amt:>12,.2f} TAO{flag(counterparty)}")
    lines.append("")

report = "\n".join(lines)
print("\n\n" + report)
with open("profile_gbonpzv_report.txt", "w") as f:
    f.write(report + "\n")
print("Saved to profile_gbonpzv_report.txt")
