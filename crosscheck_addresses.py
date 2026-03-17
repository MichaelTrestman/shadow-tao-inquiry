"""
crosscheck_addresses.py

Cross-references all shadow whale and tao.bot infrastructure addresses against:
  1. known_holders.json — validators, SN owners, delegates with on-chain identity
  2. top100_holders_report.txt — free-balance rankings (parsed from text)

Produces a clear table of what each address is or is NOT registered as.
Output: crosscheck_report.txt
"""

import json
import re

# ── Address registries ─────────────────────────────────────────────────────────

SHADOW_WALLETS = {
    "SW1":  "5FEA1FfUPwT3K4zTsYbQx5X1G9R2ZjYLyFv12xBQxW9QgoCL",
    "SW2":  "5ChHTBkaE1VgK5NX59uHuZoK8VQShojKBB1sGfXaZQpxVDCi",
    "SW3":  "5Dhf6WgqrfhVyFCGqK4G5utro2jepscwryMhLHtpMfopxweC",
    "SW4":  "5GUkyA37dHnc1rEijDtvBe5yYNCpaNjaHGqB7DY9Kb2KgSj3",
    "SW5":  "5C9CxW9355u1sqy6Np85FfGssJAdyA8cAsjjV9YP8aaLvjEY",
    "SW6":  "5Epz8SQ69FuZRLyjCAicn8i71SdyEYaWR5rZ5a1i1bgoxGaQ",
    "SW7":  "5GVKorR78gqQCV6mrWMWX95hHG93ZaRAUShZVBNT768dvqv8",
    "SW8":  "5HAe1pePzBuPqsF6BpTGN8vCngvKKJaRZ2HkHwFmJgWgAzcf",
}

INFRA_FEEDERS = {
    "Funder-A":    "5EiXej3AwjKqb9mjQAf29JG5HJf9Dwtt8CjvDqA8biprWTiN",
    "Funder-B":    "5DunDrFV6BPbzsgLZUtMQtCq7w9fcUEbM59BUwx5E7N9Bn5E",
    "HB2Q8-hub":   "5HB2Q8H9Rvxr3ejZ1o58FfXk3S3jMij6mB7Vu7b7SPqUdhTQ",
    "FV99mB":      "5FV99mBYw3tYrMTXXe52PDa69an1AE19aTrpnB4kzxW73yUj",
    "HUPxAs":      "5HUPxAsF52CX7RWAe3vDA7Wu7fiKT78dG3XpxRisfnwKYsn4",
    "DfKewdx":     "5DfKewdxchFx7umvw6qcHKXKgvVxEtMFXFXVaXShjf7anzet",
    "GBnPzv":      "5GBnPzvPghS8AuCoo6bfnK7JUFHuyUhWSFD4woBNsKnPiEUi",
    "Gorfuxev7":   "5Gorfuxev7QmgDzBK92YrVW2K5PEvfZRW49SQrKm3VXcAGi1",
    "FJMfoeUX":    "5FJMfoeUXsDXQSABaai8CUQvMyAK1a7jXqJvkBMnabfuJCjv",
    "EJMGn13":     "5EJMGn13311deMfe9pwZYd5bPkyMGs1ZmkmNtbpbv7wPcG9C",
    "HnhgYXb":     "5HnhgYXb9pJcAWceju1a5aZttSPpeMqYDNqUbxntGyUNqGxR",
    "EfXUFMj":     "5EfXUFMjjc78YKgDrEta3SQFDvwvV7PtPnV2MKBd35SqvhQJ",
    "CNChyk2":     "5CNChyk2fnVgVSZDLAVVFb4QBTMGm6WfuQvseBG6hj8xWzKP",
    "HbDZ6UL":     "5HbDZ6ULuwZegAMSPaS2kaUfBLMDaht5t48RcDrQATSgGCAR",
    "FqBL928":     "5FqBL928choLPmeFz5UVAvonBD5k7K2mZSXVC9RkFzLxoy2s",
}

TAOBOT_ADDRS = {
    "taobot-coldkey":       "5GsbTgfvgCH4xdqSkiPb7EaBBFLHjWH5vfEALhJaewSFpZX9",
    "taobot-hotkey":        "5E2LP6EnZ54m3wS8s1yPvD5c3xo71kQroBw7aUVK32TKeZ5u",
    "taobot-seed-funder":   "5E2b2DcMd5W8MBhzTCFt63t2ZEN8RsRgL7oDd7BFYL9aMQux",
    "taobot-recent-funder": "5FqqXKb9zonSNKbZhEuHYjCXnmPbX9tdzMCU2gx8gir8Z8a5",
}

# ── Load known_holders.json ────────────────────────────────────────────────────

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
    known_by_ss58[addr] = {
        "name": name,
        "is_delegate_owner": bool(entry.get("is_delegate_owner")),
        "is_sn_owner": bool(entry.get("is_sn_owner")),
        "free_tao": entry.get("free_tao", 0),
        "stake_tao": entry.get("stake_tao", 0),
        "nonce": entry.get("nonce"),
        "owned_subnets": entry.get("owned_subnets", []),
    }

print(f"Loaded {len(known_by_ss58)} known entities from known_holders.json")

# ── Parse top100 report for rank and free balance ──────────────────────────────

top100_by_addr = {}
with open("top100_holders_report.txt") as f:
    for line in f:
        # Lines like: "  2    5FEA1Ff...    141,003          0    141,003  [pure_holder]"
        m = re.match(r'\s*(\d+)\s+(5[A-Za-z0-9]{47})\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+(.*)', line)
        if m:
            rank = int(m.group(1))
            addr = m.group(2)
            free = int(m.group(3).replace(",", ""))
            staked = int(m.group(4).replace(",", ""))
            total = int(m.group(5).replace(",", ""))
            roles = m.group(6).strip()
            top100_by_addr[addr] = {"rank": rank, "free": free, "staked": staked, "roles": roles}

print(f"Parsed {len(top100_by_addr)} addresses from top100_holders_report.txt")


# ── Cross-reference function ───────────────────────────────────────────────────

def check(label, addr):
    in_known = addr in known_by_ss58
    in_top100 = addr in top100_by_addr

    known_str = ""
    if in_known:
        k = known_by_ss58[addr]
        roles = []
        if k["is_delegate_owner"]: roles.append("validator")
        if k["is_sn_owner"]:       roles.append(f"SN-owner[{','.join(str(s) for s in k['owned_subnets'])}]")
        known_str = f"  KNOWN: name='{k['name']}' roles={roles or ['registered-only']}"

    top100_str = ""
    if in_top100:
        t = top100_by_addr[addr]
        top100_str = f"  top100 rank=#{t['rank']}  free={t['free']:,} TAO"

    return {
        "label": label,
        "addr": addr,
        "in_known": in_known,
        "in_top100": in_top100,
        "known_str": known_str,
        "top100_str": top100_str,
    }


# ── Build report ──────────────────────────────────────────────────────────────

lines = [
    "=" * 80,
    "ADDRESS CROSS-REFERENCE: SHADOW WHALE CLUSTER vs TAOBOT vs KNOWN ENTITIES",
    "Sources: known_holders.json (2,369 entities)  |  top100_holders_report.txt",
    "=" * 80,
    "",
]

for section_label, addr_dict in [
    ("SHADOW WALLETS (SW1–SW8)", SHADOW_WALLETS),
    ("SHADOW INFRASTRUCTURE — FEEDERS / HUBS", INFRA_FEEDERS),
    ("TAO.BOT ADDRESSES", TAOBOT_ADDRS),
]:
    lines.append(f"{'─' * 80}")
    lines.append(section_label)
    lines.append(f"{'─' * 80}")
    for label, addr in addr_dict.items():
        r = check(label, addr)
        status_parts = []
        if r["in_known"]:
            status_parts.append(f"IN known_holders{r['known_str']}")
        else:
            status_parts.append("NOT in known_holders")
        if r["in_top100"]:
            status_parts.append(f"IN top100{r['top100_str']}")
        else:
            status_parts.append("NOT in top100")
        lines.append(f"  {label:<22}  {addr}")
        for part in status_parts:
            lines.append(f"      → {part}")
    lines.append("")

# ── Addresses that appear in BOTH shadow cluster AND tao.bot sets ─────────────
lines.append("─" * 80)
lines.append("OVERLAP: addresses appearing in multiple sets")
lines.append("─" * 80)
all_shadow = set(SHADOW_WALLETS.values()) | set(INFRA_FEEDERS.values())
all_taobot = set(TAOBOT_ADDRS.values())
overlap = all_shadow & all_taobot
if overlap:
    for addr in overlap:
        lines.append(f"  !! DIRECT OVERLAP: {addr}")
else:
    lines.append("  No direct address overlap between shadow cluster and tao.bot address sets.")
lines.append("")

# ── Addresses in neither set that appear in top 100 ───────────────────────────
lines.append("─" * 80)
lines.append("TOP 100 ADDRESSES NOT IN ANY KNOWN SET (candidates for further profiling)")
lines.append("─" * 80)
known_addrs = set(SHADOW_WALLETS.values()) | set(INFRA_FEEDERS.values()) | set(TAOBOT_ADDRS.values())
for addr, t in sorted(top100_by_addr.items(), key=lambda x: x[1]["rank"]):
    if addr not in known_addrs and addr not in known_by_ss58:
        lines.append(f"  #{t['rank']:>3}  {addr}  {t['free']:>12,} TAO  {t['roles']}")
lines.append("")

report = "\n".join(lines)
print("\n\n" + report)

with open("crosscheck_report.txt", "w") as f:
    f.write(report + "\n")
print("Saved to crosscheck_report.txt")
