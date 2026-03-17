import os
"""
taoapp_investigation.py

Uses the tao.app accounting API to pull complete event histories for the
critical addresses in the shadow whale investigation, and for Const's keys.

API format (per header field order):
  [timestamp, block, extrinsic_idx, from, to, amount_rao, fee, alpha,
   origin_netuid, destination_netuid, transaction_type]

Amount is in rao; divide by 1e9 for TAO.
"""

import json
import time
import requests

API_KEY  = os.environ["TAO_APP_API_KEY"]
BASE_URL = "https://api.tao.app/api/beta/accounting/events"
RAO      = 1_000_000_000

HEADERS = {"X-API-Key": API_KEY}

# ── Addresses under investigation ──────────────────────────────────────────

# Shadow whale infrastructure
FUNDER_A  = "5EiXej3AwjKqb9mjQAf29JG5HJf9Dwtt8CjvDqA8biprWTiN"   # nonce 23,452
FUNDER_B  = "5DunDrFV6BPbzsgLZUtMQtCq7w9fcUEbM59BUwx5E7N9Bn5E"   # nonce 23,089
HB2Q8     = "5HB2Q8H9Rvxr3ejZ1o58FfXk3S3jMij6mB7Vu7b7SPqUdhTQ"   # dominant upstream of Funder-A
FV99mB    = "5FV99mBYw3tYrMTXXe52PDa69an1AE19aTrpnB4kzxW73yUj"   # funded SW#4, seen in SW#1 history
GBnPzv    = "5GBnPzvPghS8AuCoo6bfnK7JUFHuyUhWSFD4woBNsKnPiEUi"   # funded SW#8, feeds HB2Q8
HUPxAs    = "5HUPxAsF52CX7RWAe3vDA7Wu7fiKT78dG3XpxRisfnwKYsn4"   # dust-activated both funders
DfKewdx   = "5DfKewdxchFx7umvw6qcHKXKgvVxEtMFXFXVaXShjf7anzet"   # dominant upstream of Funder-B

# Const's keys
CONST_PUB = "5GH2aUTMRUh1RprCgH4x3tRyCaKeUi5BfmYCfs1NARA8R54n"   # community-attributed key (unverified)
CONST_SN  = "5Fc3ZZQAYB3SPXKcFnd1WJeyQvArSZZeB6LU1rb7zvQ6XvDh"   # SN120 owner

# tao.bot funder keys
TAOBOT_SEED   = "5E2b2DcMd5W8MBhzTCFt63t2ZEN8RsRgL7oDd7BFYL9aMQux"  # funded taobot CK 1,025 TAO at block ~4.85M
TAOBOT_RECENT = "5FqqXKb9zonSNKbZhEuHYjCXnmPbX9tdzMCU2gx8gir8Z8a5"  # sent 9.998 TAO to taobot CK at block 7,632,272
TAOBOT_CK     = "5GsbTgfvgCH4xdqSkiPb7EaBBFLHjWH5vfEALhJaewSFpZX9"  # tao.bot coldkey (nonce 617)

ADDRESSES = {
    "Funder-A":   FUNDER_A,
    "Funder-B":   FUNDER_B,
    "HB2Q8 (upstream hub)": HB2Q8,
    "FV99mB (SW#4 funder)": FV99mB,
    "GBnPzv (SW#8 funder / HB2Q8 feeder)": GBnPzv,
    "HUPxAs (dust activator of both funders)": HUPxAs,
    "DfKewdx (dominant upstream of Funder-B)": DfKewdx,
    "Const_pub": CONST_PUB,
    "Const_SN120": CONST_SN,
    "taobot_seed_funder": TAOBOT_SEED,
    "taobot_recent_funder": TAOBOT_RECENT,
    "taobot_coldkey": TAOBOT_CK,
}


def fetch_all_events(address: str, label: str, max_pages: int = 200) -> list:
    """Fetch all Transfer events for an address, paginated. Returns list of dicts."""
    all_events = []
    page = 1
    while page <= max_pages:
        params = {"coldkey": address, "page": page, "page_size": 100}
        r = requests.get(BASE_URL, headers=HEADERS, params=params, timeout=30)
        if r.status_code != 200:
            print(f"  ERROR {r.status_code}: {r.text[:100]}")
            break
        data = r.json()
        rows = data.get("data", [])
        if not rows:
            break
        for row in rows:
            ts, blk, ext_idx, frm, to, amount_rao, fee, alpha, orig_net, dest_net, tx_type = row
            if tx_type == "Transfer" and amount_rao:
                all_events.append({
                    "timestamp": ts,
                    "block": blk,
                    "from": frm or "",
                    "to": to or "",
                    "amount_tao": (amount_rao or 0) / RAO,
                    "type": tx_type,
                })
        total = data.get("total", 0)
        fetched = (page - 1) * 100 + len(rows)
        print(f"  {label}: page {page} ({fetched}/{total} events)...", flush=True)
        if fetched >= total:
            break
        page += 1
        time.sleep(0.2)
    return all_events


def summarize(label: str, address: str, events: list) -> dict:
    inbound  = [e for e in events if e["to"]   == address]
    outbound = [e for e in events if e["from"] == address]

    in_total  = sum(e["amount_tao"] for e in inbound)
    out_total = sum(e["amount_tao"] for e in outbound)

    # Count senders and receivers
    senders   = {}
    receivers = {}
    for e in inbound:
        senders[e["from"]] = senders.get(e["from"], 0) + e["amount_tao"]
    for e in outbound:
        receivers[e["to"]] = receivers.get(e["to"], 0) + e["amount_tao"]

    top_senders   = sorted(senders.items(),   key=lambda x: -x[1])[:10]
    top_receivers = sorted(receivers.items(), key=lambda x: -x[1])[:10]

    earliest_in  = min(inbound,  key=lambda e: e["block"])["block"] if inbound  else None
    earliest_out = min(outbound, key=lambda e: e["block"])["block"] if outbound else None

    return {
        "label": label,
        "address": address,
        "total_inbound_tao":  in_total,
        "total_outbound_tao": out_total,
        "inbound_tx_count":   len(inbound),
        "outbound_tx_count":  len(outbound),
        "first_inbound_block":  earliest_in,
        "first_outbound_block": earliest_out,
        "top_senders":    top_senders,
        "top_receivers":  top_receivers,
        "all_inbound":    sorted(inbound,  key=lambda e: e["block"]),
        "all_outbound":   sorted(outbound, key=lambda e: e["block"]),
    }


# ── Shadow wallet addresses (for cross-reference) ──────────────────────────
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
ALL_SW = set(SHADOW_WALLETS.values())
SW_BY_ADDR = {v: k for k, v in SHADOW_WALLETS.items()}


# ── Main ───────────────────────────────────────────────────────────────────

print("=" * 72)
print("TAO.APP API INVESTIGATION")
print("=" * 72)

all_summaries = {}
all_events_by_addr = {}

for label, address in ADDRESSES.items():
    print(f"\nFetching: {label} ({address[:12]}...)")
    events = fetch_all_events(address, label)
    summary = summarize(label, address, events)
    all_summaries[label] = summary
    all_events_by_addr[address] = events
    print(f"  → {summary['inbound_tx_count']} in / {summary['outbound_tx_count']} out  "
          f"({summary['total_inbound_tao']:,.1f} TAO in, {summary['total_outbound_tao']:,.1f} TAO out)")


# ── Report ─────────────────────────────────────────────────────────────────

lines = [
    "=" * 72,
    "TAO.APP INVESTIGATION REPORT",
    "=" * 72,
    "",
]

# Cross-reference: which addresses in our investigation set sent to shadow wallets?
lines.append("CROSS-REFERENCE: TRANSFERS TO SHADOW WALLETS")
lines.append("-" * 60)
for label, summary in all_summaries.items():
    sw_sends = [(e["to"], e["amount_tao"], e["block"]) for e in summary["all_outbound"]
                if e["to"] in ALL_SW]
    if sw_sends:
        lines.append(f"\n{label} ({summary['address'][:16]}...):")
        by_sw = {}
        for to_addr, amt, blk in sw_sends:
            sw_name = SW_BY_ADDR.get(to_addr, to_addr[:12])
            if sw_name not in by_sw:
                by_sw[sw_name] = {"count": 0, "total": 0.0, "first": blk}
            by_sw[sw_name]["count"] += 1
            by_sw[sw_name]["total"] += amt
            by_sw[sw_name]["first"]  = min(by_sw[sw_name]["first"], blk)
        for sw_name, info in sorted(by_sw.items()):
            lines.append(f"  → {sw_name}: {info['count']} txs, {info['total']:,.2f} TAO total, first at block {info['first']:,}")
    else:
        lines.append(f"\n{label}: no direct sends to shadow wallets")

lines.append("")

# Const cross-reference
lines.append("=" * 72)
lines.append("CONST ATTRIBUTION CHECK (via API)")
lines.append("-" * 60)
const_pub_events = all_events_by_addr.get(CONST_PUB, [])
const_sn_events  = all_events_by_addr.get(CONST_SN,  [])

# Direct transfers between the two const keys?
direct = [e for e in const_pub_events if e["to"] == CONST_SN or e["from"] == CONST_SN]
direct += [e for e in const_sn_events if e["to"] == CONST_PUB or e["from"] == CONST_PUB]
# Deduplicate by block+amount
seen = set()
unique_direct = []
for e in direct:
    key = (e["block"], e["from"], e["to"])
    if key not in seen:
        seen.add(key)
        unique_direct.append(e)

if unique_direct:
    lines.append("DIRECT TRANSFERS BETWEEN CONST KEYS: YES")
    for e in sorted(unique_direct, key=lambda x: x["block"]):
        direction = "PUB→SN120" if e["from"] == CONST_PUB else "SN120→PUB"
        lines.append(f"  Block {e['block']:,}: {direction}  {e['amount_tao']:,.4f} TAO")
else:
    lines.append("DIRECT TRANSFERS BETWEEN CONST KEYS: NONE FOUND")

# Do either const key appear in shadow whale infrastructure?
infra_addrs = {FUNDER_A, FUNDER_B, HB2Q8, FV99mB, GBnPzv, HUPxAs, DfKewdx}
infra_labels = {
    FUNDER_A: "Funder-A", FUNDER_B: "Funder-B",
    HB2Q8:    "HB2Q8-hub", FV99mB:   "FV99mB-SW4-funder",
    GBnPzv:   "GBnPzv-SW8-funder", HUPxAs: "HUPxAs-dust-activator",
    DfKewdx:  "DfKewdx-FunderB-upstream",
}

lines.append("")
lines.append("CONST KEYS vs SHADOW INFRASTRUCTURE:")
for const_label, const_addr, const_events in [
    ("Const_pub", CONST_PUB, const_pub_events),
    ("Const_SN120", CONST_SN, const_sn_events),
]:
    hits = [e for e in const_events
            if e["to"] in infra_addrs or e["from"] in infra_addrs]
    if hits:
        lines.append(f"  {const_label}: HITS with shadow infrastructure:")
        for e in sorted(hits, key=lambda x: x["block"]):
            other = e["to"] if e["from"] == const_addr else e["from"]
            direction = "→" if e["from"] == const_addr else "←"
            lines.append(f"    Block {e['block']:,}: {const_label} {direction} {infra_labels.get(other, other[:16])}  {e['amount_tao']:,.4f} TAO")
    else:
        lines.append(f"  {const_label}: No overlap with shadow infrastructure found")

# Also check if Const keys sent to shadow wallets
for const_label, const_addr, const_events in [
    ("Const_pub", CONST_PUB, const_pub_events),
    ("Const_SN120", CONST_SN, const_sn_events),
]:
    sw_hits = [e for e in const_events if e["to"] in ALL_SW]
    if sw_hits:
        lines.append(f"  {const_label}: SENT DIRECTLY TO SHADOW WALLETS:")
        for e in sorted(sw_hits, key=lambda x: x["block"]):
            lines.append(f"    Block {e['block']:,}: → {SW_BY_ADDR[e['to']]}  {e['amount_tao']:,.4f} TAO")
    else:
        lines.append(f"  {const_label}: No direct sends to shadow wallets")

lines.append("")

# tao.bot cross-reference
lines.append("=" * 72)
lines.append("TAOBOT CONNECTION CHECK")
lines.append("-" * 60)
taobot_seed_events   = all_events_by_addr.get(TAOBOT_SEED,   [])
taobot_recent_events = all_events_by_addr.get(TAOBOT_RECENT, [])
taobot_ck_events     = all_events_by_addr.get(TAOBOT_CK,     [])

# Check: do taobot's funders appear anywhere in shadow infrastructure?
ALL_INFRA = infra_addrs | ALL_SW
infra_all_labels = dict(infra_labels)
infra_all_labels.update(SW_BY_ADDR)

for tb_label, tb_addr, tb_events in [
    ("taobot_seed_funder",   TAOBOT_SEED,   taobot_seed_events),
    ("taobot_recent_funder", TAOBOT_RECENT, taobot_recent_events),
    ("taobot_coldkey",       TAOBOT_CK,     taobot_ck_events),
]:
    hits = [e for e in tb_events if e["to"] in ALL_INFRA or e["from"] in ALL_INFRA]
    if hits:
        lines.append(f"\n{tb_label}: HITS WITH SHADOW INFRASTRUCTURE OR SHADOW WALLETS:")
        for e in sorted(hits, key=lambda x: x["block"]):
            other = e["to"] if e["from"] == tb_addr else e["from"]
            direction = "→" if e["from"] == tb_addr else "←"
            lbl = infra_all_labels.get(other, other[:20])
            lines.append(f"  Block {e['block']:,}: {tb_label} {direction} {lbl}  {e['amount_tao']:,.4f} TAO")
    else:
        lines.append(f"\n{tb_label}: NO overlap with shadow infrastructure or shadow wallets")

# Also check if the shadow infra funders sent to or received from taobot's addresses
TAOBOT_ADDRS = {TAOBOT_SEED, TAOBOT_RECENT, TAOBOT_CK}
TAOBOT_LABELS = {TAOBOT_SEED: "taobot_seed_funder", TAOBOT_RECENT: "taobot_recent_funder", TAOBOT_CK: "taobot_coldkey"}
lines.append("\nSHADOW INFRA NODES → taobot addresses (reverse check):")
found_reverse = False
for lbl2, addr2 in list(ADDRESSES.items())[:9]:  # only original shadow/const addresses
    ev2 = all_events_by_addr.get(addr2, [])
    hits2 = [e for e in ev2 if e["to"] in TAOBOT_ADDRS or e["from"] in TAOBOT_ADDRS]
    if hits2:
        found_reverse = True
        for e in sorted(hits2, key=lambda x: x["block"]):
            other = e["to"] if e["from"] == addr2 else e["from"]
            direction = "→" if e["from"] == addr2 else "←"
            lbl3 = TAOBOT_LABELS.get(other, other[:20])
            lines.append(f"  {lbl2} {direction} {lbl3}  {e['amount_tao']:,.4f} TAO  (block {e['block']:,})")
if not found_reverse:
    lines.append("  None found.")

lines.append("")

# Per-address summaries
lines.append("=" * 72)
lines.append("PER-ADDRESS SUMMARIES")
lines.append("=" * 72)

for label, summary in all_summaries.items():
    lines.append(f"\n{'─'*60}")
    lines.append(f"{label}")
    lines.append(f"  Address: {summary['address']}")
    lines.append(f"  Inbound:  {summary['inbound_tx_count']:,} txs, {summary['total_inbound_tao']:,.2f} TAO total")
    lines.append(f"  Outbound: {summary['outbound_tx_count']:,} txs, {summary['total_outbound_tao']:,.2f} TAO total")
    lines.append(f"  First inbound block:  {summary['first_inbound_block']}")
    lines.append(f"  First outbound block: {summary['first_outbound_block']}")

    lines.append("  Top senders:")
    for addr, amt in summary["top_senders"]:
        lines.append(f"    {addr}  {amt:,.2f} TAO")

    lines.append("  Top receivers:")
    for addr, amt in summary["top_receivers"]:
        lines.append(f"    {addr}  {amt:,.2f} TAO")

report = "\n".join(lines)
print("\n\n" + report)

with open("taoapp_investigation_report.txt", "w") as f:
    f.write(report + "\n")
print("\nSaved to taoapp_investigation_report.txt")

# Also save raw summaries (without full event lists) as JSON
json_out = {}
for label, s in all_summaries.items():
    json_out[label] = {k: v for k, v in s.items() if k not in ("all_inbound", "all_outbound")}
with open("taoapp_investigation.json", "w") as f:
    json.dump(json_out, f, indent=2)
print("Saved to taoapp_investigation.json")
