# Quantifying Shadow TAO on the Finney Chain

*An empirical analysis of latent supply, ownership concentration, and on-chain identity coverage in Bittensor's TAO distribution.*

**Block analyzed:** 7,738,261
**Date:** March 13, 2026


---

## Abstract

Using direct substrate storage queries against the Finney chain, we enumerated all 446,835 accounts and 50,268 staking coldkeys to characterize Bittensor's TAO ownership distribution. We find that **31.6% of freely circulating TAO** — approximately 1,075,903 TAO — sits in wallets that have never sent a transaction, hold no stake, and carry no on-chain identity. We term these **shadow wallets**. The top 9 shadow wallets alone hold 769,705 TAO (~22.6% of all free supply). The free supply is highly concentrated: the top 10 wallets hold 54.4%; the median non-zero balance is 0.001 TAO.

We then queried on-chain identity records (`IdentitiesV2`, `query_identity`) for the top 100 shadow wallets by balance — wallets holding between 418 TAO and 141,003 TAO. **Zero of the top 100 returned any identity information.**

---

## 1. Background

Since launch, the Finney chain has accumulated a large number of accounts — some actively participating in staking, validation, and subnet operation, others receiving TAO early and never interacting since. This analysis attempts to quantify that second category: wallets holding material TAO with no observable on-chain activity.

Understanding how much TAO is held in inactive, unidentified wallets is relevant to governance design, emission modeling, and any future discussions about supply distribution.

---

## 2. Methodology

### Data collection

Data was collected via direct substrate RPC queries against the Finney public node at block **7,738,261** (March 13, 2026). The enumeration streamed two storage maps:

- **`System.Account`** — all 446,835 accounts with free balances and nonce values
- **`SubtensorModule.StakingColdkeys`** — all 50,268 coldkeys with any staked TAO

Chain-level totals were fetched via single queries:
- **`Balances.TotalIssuance`** — total issued liquid TAO
- **`SubtensorModule.TotalStake`** — total staked TAO across all subnets

### Supply accounting

TAO supply is partitioned across two pallets on-chain:

| Component | Value |
|---|---|
| `Balances.TotalIssuance` (liquid supply) | 3,401,428 TAO |
| Sum of all free balances (cross-check) | 3,400,473 TAO |
| Difference (reserved/frozen balances) | ~955 TAO |
| `SubtensorModule.TotalStake` | 7,337,640 TAO |
| **Total supply (liquid + staked)** | **~10,739,068 TAO** |

Staked TAO is **not** included in `Balances.TotalIssuance`. When TAO is staked in Bittensor, it moves out of the Balances pallet and is tracked within `SubtensorModule`. This is confirmed by the near-perfect match between `TotalIssuance` and the sum of individual free balances (~955 TAO difference, attributable to reserved/frozen balances). The total supply of ~10.7M TAO is consistent with Finney's emission schedule at this block height.

### Shadow wallet definition

A wallet is classified as a **shadow wallet** if it meets all three conditions:

1. **Nonce = 0** — the account has never originated a transaction
2. **No stake** — the coldkey does not appear in `StakingColdkeys`
3. **Free balance > 1 TAO** — above dust threshold

Nonce = 0 is the strongest available proxy for "no outgoing on-chain activity." A nonce-0 wallet may have received TAO via mining rewards, transfers, or OTC, but has never sent a transaction, staked, or interacted with any pallet as a sender. Cold storage is a valid use case for this pattern; the analysis makes no claim about intent.

### Identity lookup

On-chain identity was queried for the top 100 shadow wallets by balance using:
- `SubtensorModule.IdentitiesV2` storage
- `query_identity` RPC fallback

SS58 addresses were re-encoded from raw substrate key bytes using `ss58_encode(..., ss58_format=42)`.

### Limitations

- **Manual address curation incomplete.** On-chain identity queries returned zero results for the top 100 shadow wallets, but some may be identifiable via off-chain labeling — exchange cold wallets, OTF reserve addresses, or community-curated lists. This curation is not yet complete.
- **No historical activity data.** Without an archive node or Subquery indexer, we cannot determine when these wallets last moved. Nonce = 0 means no outgoing transactions ever; it does not indicate when the wallet was created or when TAO was received.
- **Nonce does not capture inbound-only activity.** A wallet that received TAO but never sent will show nonce = 0 regardless of how it acquired funds.

---

## 3. Supply Overview

### 3.1 Account counts

| Category | Count | Notes |
|---|---|---|
| Total accounts | 446,835 | All addresses with any on-chain state |
| With any stake | 47,255 | Appear in `StakingColdkeys` |
| No stake | 399,580 | Free balance only |
| Ever sent a tx (nonce > 0) | 406,424 | 90.9% of all accounts |
| Never sent a tx (nonce = 0) | 40,411 | 9.1% of all accounts |
| Non-zero free balance | 291,769 | |

### 3.2 Free supply concentration

| Cohort | TAO held | % of free supply |
|---|---|---|
| Top 10 wallets | 1,850,732 TAO | 54.4% |
| Top 100 wallets | 2,809,116 TAO | 82.6% |
| Top 1,000 wallets | 3,113,175 TAO | 91.6% |
| Median non-zero wallet | 0.001 TAO | — |

Free supply is highly concentrated in a small number of addresses. The median non-zero balance of 0.001 TAO reflects a large tail of dust accounts.

---

## 4. Shadow TAO

### 4.1 Scale

| Metric | Value |
|---|---|
| Shadow wallets (nonce=0, no stake, >1 TAO) | 14,032 |
| TAO held by shadow wallets | 1,075,903 TAO |
| As % of free supply | **31.6%** |
| As % of total supply (free + staked) | 10.0% |

31.6% of freely circulating TAO sits in wallets that have never originated a transaction and hold no stake. These wallets have not delegated, registered a hotkey, or participated in any subnet.

### 4.2 Distribution by size

Shadow TAO is concentrated in a small number of large wallets:

| Balance range | Wallet count | TAO held | % of shadow TAO |
|---|---|---|---|
| > 10,000 TAO | 9 | 769,705 TAO | 71.5% |
| 1,000 – 10,000 TAO | 43 | 82,532 TAO | 7.7% |
| 100 – 1,000 TAO | 383 | 89,483 TAO | 8.3% |
| 10 – 100 TAO | 3,766 | 98,635 TAO | 9.2% |
| 1 – 10 TAO | 9,831 | 35,548 TAO | 3.3% |

Nine wallets account for 71.5% of all shadow TAO. The largest single shadow wallet holds 141,003 TAO (~4.1% of free supply). The top 6 each hold between 90,000 and 141,000 TAO.

The top 50 shadow wallets hold 850,238 TAO — **79.0% of all shadow TAO**, representing ~25% of all freely circulating TAO.

### 4.3 On-chain identity

On-chain identity records were queried for the top 100 shadow wallets by balance, covering the range from 141,003 TAO down to 418 TAO. Both `SubtensorModule.IdentitiesV2` and the `query_identity` RPC were used.

**Zero of the top 100 returned any identity data** — no name, description, URL, GitHub, Discord, or Twitter handle.

This includes the six wallets each holding more than 90,000 TAO. None have registered any on-chain identity. Whether these are cold storage addresses that predate the identity system, exchange custody wallets, OTF reserves, or other entities cannot be determined from on-chain data alone. The full SS58 address list is documented in `finney_shadow_top_report.txt`.

### 4.4 What shadow wallets are not

By definition these wallets have:
- No registered stake
- No registered hotkeys (validators and miners require hotkey registration, which is an on-chain transaction)
- No subnet registration (also an on-chain transaction)
- No on-chain identity

They cannot be active validators, delegators, or subnet operators. They may be exchange custody addresses, OTC recipients, cold storage, or OTF reserves — these cases are indistinguishable without a manually curated address registry.

---

## 5. Implications

### 5.1 Governance

As Bittensor's governance mechanisms develop, shadow TAO becomes a relevant design input. If voting weight is proportional to TAO holdings, the shadow wallet cohort — 14,032 wallets holding 31.6% of free supply — represents a meaningful block of unattributed voting weight. The 52 wallets holding more than 1,000 TAO each with nonce=0 and no stake are the most concentrated part of this: collectively ~852,000 TAO with no on-chain identity.

Governance designs that weight active stake (staked TAO) differently from dormant free balances would reduce the influence of this cohort. This is an open design question for the community.

### 5.2 Supply modeling

Shadow TAO affects how circulating supply should be interpreted. Of the 3.4M TAO in liquid balances, ~1.08M (31.6%) has never moved as a sender. This is relevant for emissions modeling, market depth analysis, and any assessment of how much TAO is actually available for circulation versus effectively dormant.

### 5.3 Open research gaps

The primary gaps in this analysis:

- **Manual address curation.** Cross-referencing the top shadow wallet addresses against known exchange cold wallets, OTF addresses, and other labeled wallets is the most actionable next step. Some fraction of shadow TAO may be attributable to known entities.
- **Historical depth.** An archive node or Subquery indexer would allow us to determine when these wallets last received TAO and correlate activity with Finney epochs (Nakamoto period, pre-dtao, post-dtao).
- **Staked shadow TAO.** This analysis covers only free-balance shadow wallets (nonce=0, no stake). A parallel category exists: wallets that staked but have otherwise been inactive. That cohort is not characterized here.

---

## Appendix: Raw Data Summary

```
Block:                      7,738,261
Total issuance (liquid):    3,401,428 TAO
Total staked:               7,337,640 TAO
Total supply:              10,739,068 TAO

Total accounts:               446,835
  With stake:                  47,255
  No stake:                   399,580
  Ever sent tx (nonce>0):     406,424
  Never sent tx (nonce=0):     40,411

Shadow wallets (>1 TAO, nonce=0, no stake):
  Count:                       14,032
  TAO held:               1,075,903 TAO
  % of free supply:             31.6%

Large shadow (>1,000 TAO):
  Count:                           52
  TAO held:                 852,238 TAO

Free balance distribution:
  Top 10 wallets:        1,850,732 TAO  (54.4%)
  Top 100 wallets:       2,809,116 TAO  (82.6%)
  Top 1,000 wallets:     3,113,175 TAO  (91.6%)
  Median (non-zero):         0.001 TAO

Identity lookup (top 100 shadow wallets):
  Queried:                        100
  With any on-chain identity:       0
```

*Data collected via substrate RPC against Finney public node. Scripts and raw data available at `finney-investigation/` in the Bittensor workspace.*

---

*Document version: 0.2 (Phase 1 + Phase 3 identity overlay complete)*
*Next version: after manual address curation and historical activity analysis*
