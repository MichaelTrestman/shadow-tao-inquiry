# Hunt for the Shadow Whales: Exploring Bittensor's Token Ecology

An ongoing forensic analysis of TAO token distribution, ownership concentration, and the phenomenon of "shadow whales", large, invisible token holders, on Bittensor's main chain, Finney.

**Current as of:** Block 7,738,261 (March 13, 2026)

---

## Overview

This project applies blockchain analytics to understand who actually holds TAO, how it moves, and what the concentration of free-balance supply implies about governance risk and network transparency. Data is sourced directly from substrate RPC, an [archive node](https://docs.learnbittensor.org/resources/glossary#archive-node) for historical sampling, and the tao.app indexed event API.

**New to Bittensor?** Key concepts used throughout: [TAO](https://docs.learnbittensor.org/resources/glossary#tao-tau) is the native token; [coldkeys](https://docs.learnbittensor.org/resources/glossary#coldkey) are wallet addresses; [staking](https://docs.learnbittensor.org/staking-and-delegation/delegation) TAO to [validators](https://docs.learnbittensor.org/validators/) is how holders participate in network governance; [Yuma Consensus](https://docs.learnbittensor.org/learn/yuma-consensus) is the on-chain algorithm that converts validator rankings into [emissions](https://docs.learnbittensor.org/learn/emissions).

**Key finding:** ~31.6% of freely circulating TAO sits in "shadow wallets" — addresses with no on-chain identity, no staking activity, and nonce=0 (never sent a transaction). The top 9 shadow wallets alone hold 22.6% of free supply, and all were funded recently and systematically by two unknown intermediate addresses.


## Reports

### [Hunt for the Shadow Whales](./shadow-whale-hunt.md)
An investigative blog and scripting tutorial. Started as a straightforward exercise in mapping Bittensor's whale ecology using the Python SDK — who holds what, how much is staked vs liquid, which validators dominate emissions — and converged on something more interesting: evidence that a single unknown entity controls roughly 20% of all freely circulating TAO across ~7 receive-only "shadow wallets" that have never signed a transaction. Two automated pass-through addresses (each ~23,000 transactions) have been steadily dripping TAO into these cold addresses over months; both pass-throughs were initialized from the same upstream address within 17 minutes of each other. Nothing at any layer connects to a known validator, subnet owner, or registered identity. The document doubles as a practical guide to the substrate RPC and tao.app event API, with all scripts and intermediate data available alongside it.


---

### [Quantifying Shadow TAO on the Finney Chain](./finney-shadow-tao.md)
Quantitative analysis of the shadow wallet phenomenon. Defines "shadow TAO" rigorously, quantifies the supply concentration, and provides historical analysis showing all top shadow wallets had zero balance through block 5,000,000 — they are a recent and ongoing accumulation event.

**Key numbers:**
- 14,032 shadow wallets (nonce=0, no stake, >1 TAO)
- 1,075,903 TAO in shadow wallets = **31.6% of free supply**
- 0 of top 100 shadow wallets have on-chain identity


---

### [Who Holds the Most TAO?](./top-holders.md)
Role and identity analysis of the top 100 free-balance holders. Examines whether large holders are active network participants (validators, subnet owners, delegators) or pure passive holders with no on-chain footprint.

**Key numbers:**
- 98 of top 100 are pure holders — no hotkeys, no delegation, no subnet registration
- Single largest address: 868,020 TAO (~25.5% of free-circulating supply), no identity
- Only 2 addresses in top 100 have active network roles


---

### [Supply Chain Attack Wallet: Tokenomic Investigation](./supply-chain-attack-investigation.md)
Forensic analysis of coldkey `5H9brHhMA1km3Dp3YCx75oaimgxEYScxCfxbzQRZ3gHk9x3L`, publicly implicated in an off-chain supply chain attack (code injection to leak plaintext private keys). Uses the tao.app API and archive node to reconstruct 17 months of transfer history and examine the wallet's relationship to the shadow whale cluster.

**Key findings:**
- Wallet holds ~99k TAO (top-10 by free balance) with zero subnet, staking, or network activity — a large ecosystem-invisible position consistent in posture with the shadow whale cluster, despite being structurally distinct (nonce 111, actively bidirectional)
- 100% of outbound transfers go to a single counterparty (`5FZiux...`, nonce 41,189) — a high-volume automated hub that is the real subject of further investigation
- Four surrounding addresses share statistically impossible base58 suffix pairs, indicating deliberate vanity address generation by a single controlling entity
- No direct on-chain connection to the shadow whale cluster — independent operation


---

### [tao.bot: Profile of Bittensor's #1 Validator](./taobot-profile.md)
Deep profile of the largest validator by stake-weight. Examines the infrastructure of 289 child hotkeys across 68 subnets, 0% take rate, and the governance concentration risk posed by a single anonymous entity controlling this much validation capacity.

---

### [Const: Ecosystem Profile](./const-profile.md)
A profile of Jacob "Const" Steeves — Bittensor co-founder and active builder — examining his known on-chain addresses and tokenomic posture. Included because any rigorous attribution exercise must account for known ecosystem actors: a small founding team managing resources centrally can produce a statistically similar on-chain signature to unknown consolidation, and ruling out that benign explanation is a necessary step before drawing stronger conclusions. The analysis finds no on-chain connection between Const's known addresses and the shadow whale infrastructure.

---

## Investigation Scripts

All analysis is reproducible via Python scripts using the Bittensor SDK and substrate RPC.

| Script | Purpose |
|--------|---------|
| `enumerate_wallets.py` | Stream all accounts from chain; extract balances & nonces |
| `analyze_wallets.py` | Classify shadow wallets (nonce=0, no stake, >1 TAO) |
| `identity_lookup.py` | Query on-chain identity for top shadow wallets |
| `top100_holders.py` | Role + identity analysis for top 100 by free balance |
| `shadow_history.py` | Archive node balance sampling across 14 historical blocks |
| `find_first_transfer.py` | Binary search for first-funded block & sender |
| `all_inbound_transfers.py` | Full inbound transfer history for top shadow whales |
| `investigate_funder.py` | Deep profile of intermediate funder addresses |
| `upstream_bfs.py` | Breadth-first search upstream from funder addresses |
| `validator_stake_weight.py` | Stake-weight for all 5,609 validators |
| `known_holders.py` | Enumerate identity-registered + validator + SN-owner keys |
| `trace_known_to_shadow.py` | Cross-reference known entities vs shadow wallet funders |
| `taoapp_investigation.py` | Full event history via tao.app API for critical addresses |
| `investigate_attacker.py` | Full tokenomic profile of supply chain attack wallet — balance history, transfer network, counterparty nonces, shadow whale cross-reference |
| `investigate_taobot.py` | Profile tao.bot validator infrastructure |
| `const_attribution.py` | Profile Const's known addresses and verify no connection to shadow funding infrastructure |
| `check_childkeys.py` | Check childkey relationships for shadow wallets |

---

## Investigation Status

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Supply enumeration and shadow wallet identification | Complete |
| 2 | Identity lookup on top shadow wallets | Complete |
| 3 | Historical balance analysis via archive node | Complete |
| 4 | First-deposit sender attribution | Complete |
| 5 | Full inbound transfer tracing & funder profiling | In progress |
| 6 | Manual address curation & off-chain identity work | Pending |

---

## Supply Snapshot (Block 7,738,261)

| Metric | Value |
|--------|-------|
| Total free-circulating TAO | ~3.4M |
| Top 10 wallets | 54.4% of free supply |
| Top 100 wallets | 82.6% of free supply |
| Shadow wallets (nonce=0, no stake, >1 TAO) | 14,032 |
| TAO in shadow wallets | 1,075,903 (31.6%) |
| Median non-zero balance | 0.001 TAO |
