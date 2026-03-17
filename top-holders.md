# Who Holds the Most TAO? Roles and Identity of the Top 100 Free-Balance Holders

*A role and identity analysis of the largest free-balance addresses on the Finney chain.*

**Block analyzed:** 7,738,826
**Date:** March 13, 2026
**Author:** Head of Documentation, Bittensor
**Status:** Draft — free-balance ranking only; staked-balance ranking pending archive/indexer access

---

## Abstract

We analyzed the top 100 Finney addresses by free TAO balance, querying each for registered hotkeys, validator permits, subnet ownership, and on-chain identity. Of the top 100, **98 are pure holders** — no registered hotkeys, no delegation, no subnet registration, no on-chain identity. Only 2 addresses in the top 100 have any active role in the network. **Zero have on-chain identity.** The single largest free-balance address holds 868,020 TAO — approximately 25.5% of all freely circulating TAO — with no identity and no network participation.

An important limitation shapes this analysis: per-coldkey staked balances could not be retrieved via the available RPC (the `TotalColdkeyStake` storage map is not exposed on the public node). This means the ranking reflects free balances only. Major validators and large delegators, who hold most of their TAO as staked balance, are not represented in this top 100. The picture presented here is of the largest *liquid* holders, not the largest holders overall.

---

## 1. Background and Scope

In Bittensor, TAO can exist in two states for a given [coldkey](https://docs.learnbittensor.org/resources/glossary#coldkey) address:

- **Free balance** — liquid TAO held directly in the account, transferable immediately
- **Staked balance** — TAO committed to one or more [hotkeys](https://docs.learnbittensor.org/resources/glossary#hotkey) across one or more subnets, earning [emissions](https://docs.learnbittensor.org/learn/emissions) but not immediately liquid

This analysis covers the top 100 addresses by free balance. A complementary analysis of staked balances — and therefore of the validator and delegator cohort — requires per-coldkey stake data that is not currently retrievable via the public RPC endpoint. That analysis is noted as a next step.

### Role taxonomy

In Bittensor, the relationship between [coldkeys](https://docs.learnbittensor.org/resources/glossary#coldkey) and [hotkeys](https://docs.learnbittensor.org/resources/glossary#hotkey) determines network role:

- **[Validator](https://docs.learnbittensor.org/validators/)**: the coldkey owns a hotkey that holds a [validator permit](https://docs.learnbittensor.org/resources/glossary#validator-permit) on at least one subnet. Validators set weights on miners via [Yuma Consensus](https://docs.learnbittensor.org/learn/yuma-consensus) and earn dividends based on [stake weight](https://docs.learnbittensor.org/resources/glossary#stake-weight).
- **[Miner](https://docs.learnbittensor.org/miners/)**: the coldkey owns a hotkey registered on a subnet without validator permit. Miners serve inference or other subnet-specific tasks and earn [emissions](https://docs.learnbittensor.org/learn/emissions) based on validators' rankings of their work.
- **[Subnet owner](https://docs.learnbittensor.org/subnets/understanding-subnets)**: the coldkey is `owner_ss58` on one or more subnets. Subnet owners set the incentive rules and earn a share of subnet emissions.
- **[Delegator](https://docs.learnbittensor.org/staking-and-delegation/delegation)**: the coldkey has staked TAO to hotkeys it does not own — nominating a validator to earn emissions on its behalf.
- **Pure holder**: none of the above. Holds free TAO with no registered network participation.

A single coldkey can hold multiple roles.

---

## 2. Methodology

For each of the top 100 addresses by free balance:

1. **Free balance** — sourced from the Phase 1 `System.Account` enumeration (block 7,738,261)
2. **Owned hotkeys** — queried via `SubtensorModule.OwnedHotkeys` storage map
3. **Validator status** — determined by cross-referencing owned hotkeys against `get_delegates()`, checking `validator_permits` on the returned `DelegateInfo`
4. **Subnet ownership** — from `get_all_subnets_info()`, matching `owner_ss58` against each address
5. **Delegator status** — inferred: staked balance > 0 with no owned hotkeys
6. **On-chain identity** — queried via `SubtensorModule.IdentitiesV2` with fallback to `query_identity`

Staked balances are shown as 0 throughout because `TotalColdkeyStake` is not available on the public node and per-coldkey stake queries were not run for all 100 addresses. The ranking is therefore free-balance only.

---

## 3. Results

### 3.1 Role distribution

| Role | Wallet count | Notes |
|---|---|---|
| Pure holder | 98 | No hotkeys, no subnet ownership, no delegation |
| Validator | 2 | Both also subnet owners |
| Subnet owner | 2 | Same 2 as above |
| Miner | 1 | One of the 2 validators also has miner registrations |
| Delegator | 0 | Cannot determine without staked balance data |

The 2 active addresses appear at ranks 83 and 91 — near the bottom of the top 100, each holding approximately 2,000 TAO in free balance. Both own subnets (SN41 and SN51 respectively) and have validator permits. Neither has on-chain identity.

### 3.2 Identity coverage

**0 of the top 100 have any on-chain identity** — no name, description, URL, or social handle registered via `IdentitiesV2` or `query_identity`. This holds across the full range, from the 868,020 TAO address at rank 1 down to the 1,629 TAO address at rank 100.

### 3.3 Top 20 by free balance

| Rank | SS58 Address | Free TAO | Role |
|---|---|---|---|
| 1 | 5Hd2ze5ug8n1bo3UCAcQsf66VNjKqGos8u6apNfzcU86pg4N | 868,020 | pure_holder |
| 2 | 5FEA1FfUPwT3K4zTsYbQx5X1G9R2ZjYLyFv12xBQxW9QgoCL | 141,003 | pure_holder |
| 3 | 5ChHTBkaE1VgK5NX59uHuZoK8VQShojKBB1sGfXaZQpxVDCi | 129,499 | pure_holder |
| 4 | 5FqBL928choLPmeFz5UVAvonBD5k7K2mZSXVC9RkFzLxoy2s | 122,232 | pure_holder |
| 5 | 5Dhf6WgqrfhVyFCGqK4G5utro2jepscwryMhLHtpMfopxweC | 117,065 | pure_holder |
| 6 | 5GUkyA37dHnc1rEijDtvBe5yYNCpaNjaHGqB7DY9Kb2KgSj3 | 108,064 | pure_holder |
| 7 | 5H9brHhMA1km3Dp3YCx75oaimgxEYScxCfxbzQRZ3gHk9x3L | 98,102 | pure_holder |
| 8 | 5C9CxW9355u1sqy6Np85FfGssJAdyA8cAsjjV9YP8aaLvjEY | 93,908 | pure_holder |
| 9 | 5Epz8SQ69FuZRLyjCAicn8i71SdyEYaWR5rZ5a1i1bgoxGaQ | 90,843 | pure_holder |
| 10 | 5ELWnR5A7DUmmqHsYPA3iZMFu1BX3gceruEqFPtsmTkCqR7J | 81,996 | pure_holder |
| 11 | 5GzGtUFNxufJoa5mASaC8pJjaz8WynzVZ4KBLzpGbXyJpmGm | 72,563 | pure_holder |
| 12 | 5Ho71YYpmq6VsxxYdfzAmiYRoQVT5VmPWojK46LUHdzad1Gh | 70,929 | pure_holder |
| 13 | 5GVKorR78gqQCV6mrWMWX95hHG93ZaRAUShZVBNT768dvqv8 | 56,342 | pure_holder |
| 14 | 5CsLYxFomrfxLgPpsLGyg2cDrDQwZQVuMQZULHDL6NTiSCda | 38,315 | pure_holder |
| 15 | 5DdfV4KJgkrwyNKPCML87KceNj3in9py2HGiwiGF7KSiJNP9 | 35,556 | pure_holder |
| 16 | 5FsWP1GxpzT11xyFBojKpE75pzp54ESDA6BYbRMPJ2nsCZE5 | 33,579 | pure_holder |
| 17 | 5E2DRjhMy8BQ1XRQsfjH2FSL9PwqVfBbkn2PL5ELSY6rFo3h | 30,173 | pure_holder |
| 18 | 5GBnPzvPghS8AuCoo6bfnK7JUFHuyUhWSFD4woBNsKnPiEUi | 23,696 | pure_holder |
| 19 | 5DsqKdVuoz8i8uLHqe71EMbLtJ7mSY8NbRb7LHbtFC2V9xbP | 23,408 | pure_holder |
| 20 | 5DohFrx7u4HFuBYgncNY4FivhjpNLnuYtLu9gKJDU1zBx5EW | 21,811 | pure_holder |

The top address alone holds 868,020 TAO — more than all addresses ranked 2 through approximately 30 combined, and roughly 25.5% of all freely circulating TAO.

### 3.4 Notable pattern: uniform balances at ranks 35–39

Five consecutive addresses (ranks 35–39) each hold exactly 12,003 TAO:

| Rank | SS58 |
|---|---|
| 35 | 5GhjixW4b6S8MxC4hb2W8xud3U4gw4rUGrqEjTgfSsa2pvPN |
| 36 | 5EE7eFjdM5tPjizRywj25rK82GH4eDQCxh3PT4BZgkaWBuvn |
| 37 | 5GEQHK4XnfJAzqVJQ1twRiNdfTEBTPmCMcmmLpRY3qrJkMzJ |
| 38 | 5GgeiyNgHu7dL961ZDFVpStm53VeqQVoSCZmM4Xt4T1p27ta |
| 39 | 5HAZamWxtVYNkukfc8cEWDrk64JLRncuG1rC7t4Pcm3BVVAt |

Identical balances across five distinct addresses is consistent with a single originating distribution event — an OTC transaction split across multiple wallets, a protocol distribution, or an exchange custody arrangement. None carry identity. This cluster warrants further investigation.

---

## 4. Interpretation

### 4.1 Active network participants are not the largest free-balance holders

The two addresses with any active role (validator, subnet owner) appear at ranks 83 and 91, each with ~2,000 TAO in free balance. This is consistent with how active participants behave: validators and subnet owners typically commit TAO as stake rather than holding it liquid. Their TAO is staked, earning emissions, and therefore does not show up in free-balance rankings.

This means the top 100 free-balance list is not a list of Bittensor's most engaged actors. It is a list of addresses that hold large amounts of liquid TAO without committing it to network activity.

### 4.2 The largest holder

The address at rank 1 — `5Hd2ze5ug8n1bo3UCAcQsf66VNjKqGos8u6apNfzcU86pg4N` — holds 868,020 TAO in free balance. This is:

- ~25.5% of all freely circulating TAO
- ~8.1% of total supply (free + staked)
- More than twice the balance of the second-largest address

It has no on-chain identity, no registered hotkeys, no subnet ownership. It is purely a holding address. The origin and holder of this address are unknown from on-chain data alone.

### 4.3 Concentration of unidentified liquid supply

The top 100 free-balance holders collectively hold approximately 2,809,000 TAO — 82.6% of all freely circulating TAO (this matches the Phase 1 concentration analysis). Every single one is unidentified by on-chain data. The two with active roles are among the smallest in the cohort.

This is not a finding about misconduct or intent. It is a statement about the current state of on-chain transparency: the addresses controlling the overwhelming majority of liquid TAO supply have no verifiable on-chain identity.

---

## 5. What This Analysis Cannot Tell Us

### 5.1 Total TAO rankings

Because per-coldkey staked balances are not available via the public RPC (`TotalColdkeyStake` storage map not exposed), this analysis cannot rank holders by total TAO (free + staked). The major validators and large delegators — who hold most of their TAO staked — are absent from this top 100. A complete picture of the largest TAO holders requires either:

- Access to a Subquery indexer with stake data
- A private/archive node that exposes `TotalColdkeyStake`
- Individual per-coldkey stake queries across all 50,268 staking coldkeys (feasible but slow)

### 5.2 Off-chain identity

On-chain identity queries cover only what has been voluntarily registered via `IdentitiesV2`. Large custodial addresses (exchange cold wallets, OTC desk wallets, foundation reserves) may be identifiable through off-chain sources — community knowledge, exchange disclosure, or foundation transparency reports — but this cannot be determined from the chain alone.

### 5.3 Historical context

We do not know when these balances were accumulated, from what source, or how long they have been at current levels. Archive node access would allow correlating balances with specific block epochs and transaction patterns.

---

## 6. Next Steps

- **Per-coldkey stake queries**: run `get_stake_info_for_coldkey` for all 50,268 staking coldkeys to get true total TAO rankings. This is the highest-priority gap.
- **Manual address curation**: cross-reference top addresses against known exchange, OTF, and validator cold wallet lists.
- **Cluster analysis**: investigate the 5-wallet 12,003 TAO cluster and any other groups with identical or near-identical balances that may indicate a common origin.
- **Archive/indexer access**: historical depth on when these balances were set and from what transactions.

---

## Appendix: Full Top 100

Full address list, balances, and role classifications are available in `top100_holders.jsonl` and `top100_holders_report.txt`.

```
Top 100 free-balance range: 868,020 TAO → 1,629 TAO
Role distribution:
  pure_holder    98 wallets   2,805,077 TAO  (26.1% of total supply)
  validator       2 wallets       4,038 TAO
  subnet_owner    2 wallets       4,038 TAO
  miner           1 wallet        1,885 TAO

Identity coverage: 0 / 100
```

*Data collected via substrate RPC against Finney public node. Analysis scripts in `finney-investigation/`.*

---

*Document version: 0.1*
*Companion to: Quantifying Shadow TAO on the Finney Chain (v0.2)*
