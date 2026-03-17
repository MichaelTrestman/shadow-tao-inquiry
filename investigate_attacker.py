import os
"""
investigate_attacker.py

Tokenomic analysis of coldkey 5H9brHhMA1km3Dp3YCx75oaimgxEYScxCfxbzQRZ3gHk9x3L,
implicated in a supply chain attack on Bittensor (off-chain code injection to leak
plaintext private keys from wallet clients).

Questions answered:
  1. Full transaction history — timing, amounts, counterparties
  2. Balance accumulation curve — when was TAO acquired?
  3. Inbound funding sources — who sent to this wallet?
  4. Outbound distribution — where did TAO go?
  5. Shadow whale cluster connections — any overlap with SW1-SW10 or funder infra?
  6. Temporal patterns — burst activity, pre/post attack behavior
  7. On-chain state — nonce, identity, subnet roles
  8. Archive node balance history — timeline of accumulation

Output:
  attacker_profile_report.txt  — human-readable full report
  attacker_events.json         — raw event data for further analysis
"""

import json
import time
import sys
from datetime import datetime, timezone
from collections import defaultdict

import requests
import bittensor as bt

# ── Config ────────────────────────────────────────────────────────────────────

TARGET        = "5H9brHhMA1km3Dp3YCx75oaimgxEYScxCfxbzQRZ3gHk9x3L"
API_KEY  = os.environ["TAO_APP_API_KEY"]
BASE_URL      = "https://api.tao.app/api/beta/accounting/events"
RAO           = 1_000_000_000
HEADERS       = {"X-API-Key": API_KEY}

# Shadow whale cluster and known infrastructure from shadow-whale-hunt investigation
SHADOW_WHALES = {
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
    "Funder-A":              "5EiXej3AwjKqb9mjQAf29JG5HJf9Dwtt8CjvDqA8biprWTiN",
    "Funder-B":              "5DunDrFV6BPbzsgLZUtMQtCq7w9fcUEbM59BUwx5E7N9Bn5E",
    "HB2Q8 (hub)":           "5HB2Q8H9Rvxr3ejZ1o58FfXk3S3jMij6mB7Vu7b7SPqUdhTQ",
    "FV99mB (SW4-funder)":   "5FV99mBYw3tYrMTXXe52PDa69an1AE19aTrpnB4kzxW73yUj",
    "GBnPzv (SW8-funder)":   "5GBnPzvPghS8AuCoo6bfnK7JUFHuyUhWSFD4woBNsKnPiEUi",
    "HUPxAs (dust-act)":     "5HUPxAsF52CX7RWAe3vDA7Wu7fiKT78dG3XpxRisfnwKYsn4",
    "DfKewdx (FunderB-up)":  "5DfKewdxchFx7umvw6qcHKXKgvVxEtMFXFXVaXShjf7anzet",
    "FXw2v9 (dust-act)":     "5FXw2v9BH1wMCoP4vws27FWMqLGXFK647NwGGRaMHVeSnzKE",
    "ESDyJB (shared-feed)":  "5ESDyJBqh3SRcmboQpHc3761pZqV5C9vrFPFy8qxtAzerktB",
    "Rank#4 (active)":       "5FqBL928choLPmeFz5UVAvonBD5k7K2mZSXVC9RkFzLxoy2s",
}

# Invert for quick lookup
KNOWN_ADDRS = {}
for label, addr in SHADOW_WHALES.items():
    KNOWN_ADDRS[addr] = label
for label, addr in KNOWN_INFRA.items():
    KNOWN_ADDRS[addr] = label

# Archive node sample blocks (same schedule as shadow_history.py for comparability)
SAMPLE_BLOCKS = [
    1, 100, 1_000, 10_000, 100_000, 500_000,
    1_000_000, 2_000_000, 3_000_000, 4_000_000,
    5_000_000, 6_000_000, 7_000_000,
]

# Approximate block → date mapping (12s/block, genesis ~Jan 2023)
# Block 7,738,261 = March 13, 2026
# Block 7,000,000 ≈ Dec 2025, Block 6,000,000 ≈ Jul 2025, Block 5,000,000 ≈ Jan 2025
BLOCK_DATES = {
    1:         "2023-01",
    100:       "2023-01",
    1_000_000: "2023-08",
    2_000_000: "2024-01",
    3_000_000: "2024-06",
    4_000_000: "2024-09",
    5_000_000: "2025-01",
    6_000_000: "2025-07",
    7_000_000: "2025-12",
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def fetch_all_events(address: str, label: str = "") -> list:
    """
    Fetch all accounting events for an address via tao.app API.
    Returns list of parsed event dicts.
    """
    all_events = []
    page = 1
    while True:
        params = {"coldkey": address, "page": page, "page_size": 100}
        try:
            r = requests.get(BASE_URL, headers=HEADERS, params=params, timeout=30)
        except Exception as e:
            print(f"  [network error: {e}]")
            break

        if r.status_code != 200:
            print(f"  [HTTP {r.status_code}: {r.text[:80]}]")
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
                "ext_idx":     ext_idx,
                "from":        frm or "",
                "to":          to  or "",
                "amount_tao":  (amount_rao or 0) / RAO,
                "fee_tao":     (fee        or 0) / RAO,
                "alpha":       alpha,
                "orig_netuid": orig_net,
                "dest_netuid": dest_net,
                "tx_type":     tx_type,
            })

        total   = data.get("total", 0)
        fetched = (page - 1) * 100 + len(rows)
        if label:
            print(f"  page {page} — {fetched}/{total} events", flush=True)
        if fetched >= total:
            break
        page += 1
        time.sleep(0.2)

    return all_events


def _extract_value(result):
    """Normalize query result — handles both object-with-.value and plain dict."""
    if result is None:
        return None
    if isinstance(result, dict):
        return result
    if hasattr(result, "value"):
        return result.value
    return None


def get_nonce_and_balance(sub, address: str) -> tuple:
    """Return (nonce, free_tao) from current chain state."""
    result = sub.substrate.query("System", "Account", [address])
    val = _extract_value(result)
    if val:
        nonce    = val["nonce"]
        free_tao = val["data"]["free"] / RAO
        return nonce, free_tao
    return 0, 0.0


def get_balance_at_block(sub, address: str, block_hash: str) -> float:
    """Free balance in TAO at a specific block hash."""
    try:
        result = sub.substrate.query("System", "Account", [address], block_hash=block_hash)
        val = _extract_value(result)
        if val:
            return val["data"]["free"] / RAO
    except Exception:
        pass
    return 0.0


def get_identity(sub, address: str) -> dict:
    """Query IdentitiesV2 for an address."""
    try:
        result = sub.substrate.query("SubtensorModule", "IdentitiesV2", [address])
        val = _extract_value(result)
        if val:
            return val
    except Exception:
        pass
    return {}


def get_subnet_roles(sub, address: str) -> dict:
    """Check if address is a subnet owner for any subnet."""
    owned_subnets = []
    try:
        subnets = sub.get_all_subnets_info()
        if subnets:
            for sn in subnets:
                if hasattr(sn, 'owner_ss58') and sn.owner_ss58 == address:
                    owned_subnets.append(sn.netuid)
    except Exception:
        pass

    is_validator = False
    try:
        delegates = sub.get_delegates()
        if delegates:
            for d in delegates:
                if hasattr(d, 'owner_ss58') and d.owner_ss58 == address:
                    is_validator = True
                    break
    except Exception:
        pass

    return {"owned_subnets": owned_subnets, "is_delegate_owner": is_validator}


def ts_to_date(ts) -> str:
    """Convert Unix timestamp to ISO date string."""
    if ts:
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        except Exception:
            return str(ts)
    return "unknown"


def block_to_approx_date(block: int) -> str:
    """Very rough block → date estimate."""
    # Genesis ~Jan 3, 2023. 12s/block.
    genesis_ts = 1672704000  # Jan 3, 2023 00:00 UTC (approximate)
    approx_ts  = genesis_ts + block * 12
    return datetime.fromtimestamp(approx_ts, tz=timezone.utc).strftime("%Y-%m-%d")


# ── Main ──────────────────────────────────────────────────────────────────────

lines = []
raw_output = {}

def p(s=""):
    lines.append(s)
    print(s)


p("=" * 72)
p("SUPPLY CHAIN ATTACK — COLDKEY INVESTIGATION")
p("=" * 72)
p(f"Target:  {TARGET}")
p(f"Run at:  {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
p()


# ── Section 1: On-chain state ─────────────────────────────────────────────────

p("─" * 72)
p("1. ON-CHAIN STATE (current Finney)")
p("─" * 72)

sub = bt.Subtensor(network="finney")
current_block = sub.get_current_block()
p(f"Current block: {current_block:,}  ({block_to_approx_date(current_block)})")

nonce, free_tao = get_nonce_and_balance(sub, TARGET)
p(f"Nonce:         {nonce:,}  (number of signed transactions)")
p(f"Free balance:  {free_tao:,.3f} TAO")

identity = get_identity(sub, TARGET)
if identity:
    p(f"Identity:      {identity}")
else:
    p("Identity:      [none registered in IdentitiesV2]")

roles = get_subnet_roles(sub, TARGET)
if roles["owned_subnets"]:
    p(f"Subnet owner:  subnets {roles['owned_subnets']}")
else:
    p("Subnet owner:  [none]")
if roles["is_delegate_owner"]:
    p("Validator:     [YES — owns a delegate hotkey]")
else:
    p("Validator:     [none]")

raw_output["on_chain"] = {
    "block":        current_block,
    "nonce":        nonce,
    "free_tao":     free_tao,
    "identity":     identity,
    "roles":        roles,
}
p()


# ── Section 2: Archive node balance history ───────────────────────────────────

p("─" * 72)
p("2. BALANCE HISTORY (archive node, 14 sample blocks)")
p("─" * 72)

try:
    sub_archive = bt.Subtensor(network="archive")
    p("Connected to archive node.")
except Exception as e:
    sub_archive = None
    p(f"WARNING: could not connect to archive node: {e}")
    p("Skipping balance history — API-only analysis follows.")

balance_history = {}
if sub_archive:
    blocks_to_sample = SAMPLE_BLOCKS + [current_block]
    p(f"{'Block':>12}  {'Approx Date':>12}  {'Free TAO':>16}")
    p("-" * 46)
    for blk in blocks_to_sample:
        try:
            bh  = sub_archive.substrate.get_block_hash(block_id=blk)
            bal = get_balance_at_block(sub_archive, TARGET, bh)
            date_str = block_to_approx_date(blk)
            balance_history[blk] = bal
            p(f"{blk:>12,}  {date_str:>12}  {bal:>16,.3f}")
        except Exception as ex:
            p(f"{blk:>12,}  [error: {ex}]")
        time.sleep(0.1)

raw_output["balance_history"] = balance_history
p()


# ── Section 3: Full event history via tao.app ─────────────────────────────────

p("─" * 72)
p("3. FULL EVENT HISTORY (tao.app API)")
p("─" * 72)
p(f"Fetching all events for {TARGET}...")

events = fetch_all_events(TARGET, label=TARGET[:12])
p(f"Total events fetched: {len(events)}")

if not events:
    p("No events found. Check API key or address.")
    sys.exit(1)

raw_output["events"] = events

# Partition by direction
inbound  = [e for e in events if e["to"]   == TARGET and e["tx_type"] in ("Transfer", "transfer")]
outbound = [e for e in events if e["from"] == TARGET and e["tx_type"] in ("Transfer", "transfer")]
other    = [e for e in events if e not in inbound and e not in outbound]

# Also capture non-Transfer events (staking, subnet ops, etc.)
by_type = defaultdict(list)
for e in events:
    by_type[e["tx_type"]].append(e)

p()
p(f"Transaction breakdown:")
for tx_type, evs in sorted(by_type.items()):
    p(f"  {tx_type:<30} {len(evs):>5} events")
p()

in_total  = sum(e["amount_tao"] for e in inbound)
out_total = sum(e["amount_tao"] for e in outbound)
p(f"Inbound transfers:   {len(inbound):>5}  total {in_total:>14,.3f} TAO")
p(f"Outbound transfers:  {len(outbound):>5}  total {out_total:>14,.3f} TAO")
p(f"Net flow:            {in_total - out_total:>+21,.3f} TAO")
p()

if inbound:
    dates = [e["timestamp"] for e in inbound if e["timestamp"]]
    if dates:
        p(f"Inbound activity: {ts_to_date(min(dates))} → {ts_to_date(max(dates))}")
if outbound:
    dates = [e["timestamp"] for e in outbound if e["timestamp"]]
    if dates:
        p(f"Outbound activity: {ts_to_date(min(dates))} → {ts_to_date(max(dates))}")
p()


# ── Section 4: Inbound sender analysis ────────────────────────────────────────

p("─" * 72)
p("4. INBOUND SENDER ANALYSIS")
p("─" * 72)

sender_stats = defaultdict(lambda: {"total": 0.0, "count": 0, "first_block": 9e18, "last_block": 0})
for e in inbound:
    s = e["from"]
    sender_stats[s]["total"]      += e["amount_tao"]
    sender_stats[s]["count"]      += 1
    sender_stats[s]["first_block"] = min(sender_stats[s]["first_block"], e["block"] or 9e18)
    sender_stats[s]["last_block"]  = max(sender_stats[s]["last_block"],  e["block"] or 0)

p(f"Unique senders: {len(sender_stats)}")
p()
p(f"{'Sender':<52}  {'TAO':>12}  {'#':>5}  {'First blk':>10}  {'Label'}")
p("-" * 100)

shadow_hit_senders = {}
known_hit_senders  = {}

for sender, stats in sorted(sender_stats.items(), key=lambda x: -x[1]["total"]):
    label = KNOWN_ADDRS.get(sender, "")
    flag  = ""
    if sender in SHADOW_WHALES.values():
        flag = " *** SHADOW WHALE ***"
        shadow_hit_senders[sender] = stats
    elif sender in KNOWN_INFRA.values():
        flag = " *** KNOWN INFRA ***"
        known_hit_senders[sender] = stats

    p(f"  {sender}  {stats['total']:>12,.3f}  {stats['count']:>5}  "
      f"{int(stats['first_block'] if stats['first_block'] < 9e18 else 0):>10,}  {label}{flag}")

raw_output["sender_stats"] = {k: v for k, v in sender_stats.items()}
p()


# ── Section 5: Outbound recipient analysis ────────────────────────────────────

p("─" * 72)
p("5. OUTBOUND RECIPIENT ANALYSIS")
p("─" * 72)

recip_stats = defaultdict(lambda: {"total": 0.0, "count": 0, "first_block": 9e18, "last_block": 0})
for e in outbound:
    r = e["to"]
    recip_stats[r]["total"]      += e["amount_tao"]
    recip_stats[r]["count"]      += 1
    recip_stats[r]["first_block"] = min(recip_stats[r]["first_block"], e["block"] or 9e18)
    recip_stats[r]["last_block"]  = max(recip_stats[r]["last_block"],  e["block"] or 0)

p(f"Unique recipients: {len(recip_stats)}")
p()
p(f"{'Recipient':<52}  {'TAO':>12}  {'#':>5}  {'First blk':>10}  {'Label'}")
p("-" * 100)

shadow_hit_recips = {}
known_hit_recips  = {}

for recip, stats in sorted(recip_stats.items(), key=lambda x: -x[1]["total"]):
    label = KNOWN_ADDRS.get(recip, "")
    flag  = ""
    if recip in SHADOW_WHALES.values():
        flag = " *** SHADOW WHALE ***"
        shadow_hit_recips[recip] = stats
    elif recip in KNOWN_INFRA.values():
        flag = " *** KNOWN INFRA ***"
        known_hit_recips[recip] = stats

    p(f"  {recip}  {stats['total']:>12,.3f}  {stats['count']:>5}  "
      f"{int(stats['first_block'] if stats['first_block'] < 9e18 else 0):>10,}  {label}{flag}")

raw_output["recip_stats"] = {k: v for k, v in recip_stats.items()}
p()


# ── Section 6: Shadow whale / known infra overlap summary ─────────────────────

p("─" * 72)
p("6. SHADOW WHALE CLUSTER OVERLAP")
p("─" * 72)

any_hit = False
for addr, stats in {**shadow_hit_senders, **shadow_hit_recips,
                    **known_hit_senders,  **known_hit_recips}.items():
    label     = KNOWN_ADDRS.get(addr, addr)
    direction = []
    if addr in shadow_hit_senders or addr in known_hit_senders:
        direction.append(f"SENT {shadow_hit_senders.get(addr, known_hit_senders.get(addr))['total']:,.2f} TAO to target")
    if addr in shadow_hit_recips or addr in known_hit_recips:
        direction.append(f"RECEIVED {shadow_hit_recips.get(addr, known_hit_recips.get(addr))['total']:,.2f} TAO from target")
    p(f"  {label} ({addr[:16]}...):")
    for d in direction:
        p(f"    → {d}")
    any_hit = True

if not any_hit:
    p("  No direct transfers to/from any shadow whale or known infrastructure address.")
p()


# ── Section 7: Temporal pattern analysis ──────────────────────────────────────

p("─" * 72)
p("7. TEMPORAL PATTERNS")
p("─" * 72)

# Sort all events by block
all_sorted = sorted([e for e in events if e["block"]], key=lambda x: x["block"])

if all_sorted:
    p(f"First event: block {all_sorted[0]['block']:,}  ({ts_to_date(all_sorted[0]['timestamp'])})")
    p(f"Last event:  block {all_sorted[-1]['block']:,}  ({ts_to_date(all_sorted[-1]['timestamp'])})")
    p()

    # Bucket by 100k-block windows (~14 days each)
    buckets = defaultdict(lambda: {"in": 0.0, "out": 0.0, "count": 0})
    for e in all_sorted:
        w = (e["block"] // 100_000) * 100_000
        if e["to"] == TARGET:
            buckets[w]["in"]  += e["amount_tao"]
        elif e["from"] == TARGET:
            buckets[w]["out"] += e["amount_tao"]
        buckets[w]["count"] += 1

    p(f"{'Block window':>14}  {'Approx date':>12}  {'In TAO':>14}  {'Out TAO':>14}  {'Events':>6}")
    p("-" * 70)
    for w in sorted(buckets):
        b = buckets[w]
        p(f"  {w:>12,}  {block_to_approx_date(w):>12}  {b['in']:>14,.2f}  {b['out']:>14,.2f}  {b['count']:>6}")
    p()

# Largest single transfers
p("Largest inbound transfers:")
for e in sorted(inbound, key=lambda x: -x["amount_tao"])[:10]:
    p(f"  {e['amount_tao']:>12,.3f} TAO  block {e['block']:>10,}  ({ts_to_date(e['timestamp'])})  from {e['from'][:20]}...")

p()
p("Largest outbound transfers:")
for e in sorted(outbound, key=lambda x: -x["amount_tao"])[:10]:
    p(f"  {e['amount_tao']:>12,.3f} TAO  block {e['block']:>10,}  ({ts_to_date(e['timestamp'])})  to   {e['to'][:20]}...")

p()


# ── Section 8: Non-transfer events (staking, subnet, alpha) ───────────────────

p("─" * 72)
p("8. NON-TRANSFER EVENTS (staking, subnet operations, alpha)")
p("─" * 72)

non_transfer = [e for e in events if e["tx_type"] not in ("Transfer", "transfer")]
if non_transfer:
    for e in sorted(non_transfer, key=lambda x: x["block"] or 0):
        p(f"  block {e['block']:>10,}  {e['tx_type']:<30}  "
          f"amount {e['amount_tao']:>12,.3f} TAO  "
          f"netuid {e['orig_netuid']} → {e['dest_netuid']}")
else:
    p("  No non-Transfer events found for this address.")
p()


# ── Section 9: Counterparty nonce check ───────────────────────────────────────

p("─" * 72)
p("9. COUNTERPARTY NONCE SPOT-CHECK")
p("─" * 72)
p("Checking nonce and balance for top 5 inbound senders + top 5 outbound recipients...")
p("(High nonce = automated/hot wallet; nonce=0 = shadow/cold storage)")
p()

top_senders   = sorted(sender_stats.items(), key=lambda x: -x[1]["total"])[:5]
top_recips    = sorted(recip_stats.items(), key=lambda x: -x[1]["total"])[:5]
check_addrs   = [(a, "sender", s) for a, s in top_senders] + \
                [(a, "recipient", s) for a, s in top_recips]

nonce_results = {}
p(f"  {'Address':<52}  {'Role':<10}  {'Nonce':>8}  {'Free TAO':>14}  {'Note'}")
p("  " + "-" * 100)

for addr, role, stats in check_addrs:
    try:
        n, bal = get_nonce_and_balance(sub, addr)
        label  = KNOWN_ADDRS.get(addr, "")
        note   = ""
        if n == 0:
            note = "← shadow / cold"
        elif n > 10_000:
            note = "← HOT / automated"
        elif n > 1_000:
            note = "← highly active"
        if label:
            note += f"  [{label}]"
        nonce_results[addr] = {"nonce": n, "free_tao": bal, "role": role}
        p(f"  {addr}  {role:<10}  {n:>8,}  {bal:>14,.3f}  {note}")
    except Exception as ex:
        p(f"  {addr}  [error: {ex}]")
    time.sleep(0.15)

raw_output["nonce_checks"] = nonce_results
p()


# ── Section 10: Summary and findings ─────────────────────────────────────────

p("=" * 72)
p("10. SUMMARY OF FINDINGS")
p("=" * 72)
p()
p(f"TARGET: {TARGET}")
p()
p(f"  Nonce:        {nonce:,}  (this wallet has signed {nonce} transactions)")
p(f"  Balance:      {free_tao:,.2f} TAO (free; no registered stake)")
p(f"  Identity:     {'registered' if identity else 'none'}")
p(f"  Roles:        {'subnet owner of ' + str(roles['owned_subnets']) if roles['owned_subnets'] else 'none'}; "
  f"{'delegate owner' if roles['is_delegate_owner'] else 'not a delegate'}")
p()
p(f"  Transfer history:")
p(f"    Total inbound  {in_total:>14,.3f} TAO over {len(inbound)} transfers from {len(sender_stats)} senders")
p(f"    Total outbound {out_total:>14,.3f} TAO over {len(outbound)} transfers to {len(recip_stats)} recipients")
p(f"    Net accumulation: {in_total - out_total:>+,.2f} TAO")
p()
p(f"  Shadow whale cluster connections:")
if shadow_hit_senders:
    p(f"    INBOUND from shadow wallets:  {len(shadow_hit_senders)} addresses")
else:
    p(f"    INBOUND from shadow wallets:  none")
if shadow_hit_recips:
    p(f"    OUTBOUND to shadow wallets:   {len(shadow_hit_recips)} addresses")
else:
    p(f"    OUTBOUND to shadow wallets:   none")
if known_hit_senders:
    p(f"    INBOUND from known infra:     {len(known_hit_senders)} addresses")
else:
    p(f"    INBOUND from known infra:     none")
if known_hit_recips:
    p(f"    OUTBOUND to known infra:      {len(known_hit_recips)} addresses")
else:
    p(f"    OUTBOUND to known infra:      none")
p()


# ── Write outputs ─────────────────────────────────────────────────────────────

report_text = "\n".join(lines)
with open("attacker_profile_report.txt", "w") as f:
    f.write(report_text + "\n")
print("\nSaved: attacker_profile_report.txt")

with open("attacker_events.json", "w") as f:
    json.dump(raw_output, f, indent=2, default=str)
print("Saved: attacker_events.json")
