
# Supply Chain Attack Wallet: Tokenomic Investigation

**Target coldkey:** `5H9brHhMA1km3Dp3YCx75oaimgxEYScxCfxbzQRZ3gHk9x3L`
**Data collected:** block 7,767,315 (March 17, 2026)
**Script:** `investigate_attacker.py` — output in `attacker_profile_report.txt`, `attacker_events.json`

---

## Key Findings at a Glance

This section summarizes what the blockchain data reveals. The sections that follow contain the full evidence and methodology behind each point.

**1. The wallet is a float account for a single hidden hub.**
Every single outbound transfer this wallet ever made — all 113 of them — went to one address. That same address also sent 98% of all inbound TAO. Total volume through the pair: ~910,000 TAO. This wallet doesn't distribute funds broadly; it moves them back and forth with one controller. See [The Dominant Counterparty](#the-dominant-counterparty).

**2. The hub behind it is a high-volume automated system — and that's the real target to trace.**
The single counterparty (`5FZiux...`) has nonce 41,189, placing it in the same behavioral class as the automated funder wallets in the shadow whale investigation. It has processed enormous TAO volume but currently holds only ~4k TAO — a classic high-throughput routing wallet. If stolen TAO flowed through this operation, it flowed through `5FZiux...`. Tracing *its* inbound senders against victim wallets is the key next step. See [Open Threads](#open-threads).

**3. A cryptographic fingerprint links four surrounding wallets to one actor.**
Two pairs of addresses in this wallet's immediate transfer network share 4-character base58 suffixes — a statistical near-impossibility (~1 in several billion by chance). The most likely explanation is deliberate vanity address generation: the operator generated addresses with matching endings as a coordination or labeling mechanism. This links the main hub wallet, the early seed sender, and two surveillance-style probe addresses to the same controlling entity. See [Address Fingerprinting Observation](#address-fingerprinting-observation).

**4. No connection to the shadow whale cluster.**
The shadow whale investigation identified a cluster of ten large cold-storage wallets funded by two automated pipelines. This wallet has zero on-chain transfers to or from any of those addresses. These are independent operations. See [Shadow Whale Cluster Cross-Reference](#shadow-whale-cluster-cross-reference).

**5. The blockchain data is suggestive but not yet proof of theft.**
The wallet peaked at ~134k TAO in April 2025 following a sharp accumulation phase. Two individual transfers — 65,000 TAO and 31,000 TAO in March–April 2025 — are the largest events and are the most important to contextualize against victim reports. Whether those inflows represent stolen proceeds requires cross-referencing victim addresses against the hub wallet's inbound history. The chain is traceable; it just requires that next step.

---

## Background

This wallet has been publicly implicated in a supply chain attack on Bittensor. The attack was **off-chain**: malicious code was injected into a wallet client (or a dependency of it) that caused plaintext private keys to be exfiltrated from victims' machines. The on-chain record cannot tell us *how* the attack happened — that lives in git history and pip packages — but it can tell us what this wallet was doing before, during, and after: how it accumulated TAO, who it moved funds to, and whether it has any relationship to other suspicious clusters already identified in this investigation. For background on [Bittensor wallets and key security](https://docs.learnbittensor.org/keys/coldkey-hotkey-security), see the official documentation.

**Context from the shadow whale investigation:** This address (`5H9brHhMA1km3Dp3YCx75oaimgxEYScxCfxbzQRZ3gHk9x3L`) appeared in our top-100 free-balance ranking at **position #7** with approximately 98,000 TAO. It was flagged there as *not* a shadow wallet — it has nonce 111, meaning it has originated 111 transactions. The `nonce_check.json` file from that investigation already noted this: *"Nonce 111 on `5H9brHhM...` is also clearly active."* It was left as an open thread. This document picks it up.

### A long-time participant with no participation footprint

The first thing the data reveals — and the thing that frames everything else — is a striking contradiction. This wallet has been active since October 2024, holds roughly 99,000 TAO (top-10 by free balance across the entire chain), and has been party to over 900,000 TAO in total transfer volume over 17 months. By any measure of on-chain financial activity, this is a significant, long-term presence in the ecosystem.

And yet: of 816 total events in its complete history, every single non-transfer event is `TransactionFeePaid` — the bookkeeping record of paying gas on an outbound transfer. There are no staking events. No alpha pool interactions. No subnet registrations. No validator operations. No on-chain identity registration. This address has never, in 17 months, done anything on the Bittensor network except move TAO.

This matters because Bittensor is, nominally, an AI incentive network. The TAO token exists to fund [subnet](https://docs.learnbittensor.org/subnets/understanding-subnets) computation and direct [validator](https://docs.learnbittensor.org/validators/) weight — specifically, staked TAO determines [stake weight](https://docs.learnbittensor.org/resources/glossary#stake-weight), which governs [Yuma Consensus](https://docs.learnbittensor.org/learn/yuma-consensus) and [emissions](https://docs.learnbittensor.org/learn/emissions). A wallet in the top-10 of all liquid TAO holders that has never once interacted with a subnet, staked to a validator, or participated in any network function is not a Bittensor participant in any meaningful sense. It is using the Bittensor blockchain as a financial rail — a place to hold and move a large position — while the network itself runs around it.

That profile — large, long-term, financially active, ecosystem-invisible — is the context in which the supply chain attack allegation should be read. It is consistent with an actor who is present on-chain for financial reasons, not network reasons, and who has no interest in being known.


## On-Chain Profile

From `investigate_attacker.py` at block 7,767,315:

```
Nonce:         111   — 111 signed transactions
Free balance:  98,895 TAO
Identity:      none (no IdentitiesV2 registration)
Subnet owner:  none
Validator:     none (not a delegate owner)
```

**The nonce is key context.** Nonce 111 means this wallet has signed 111 transactions in its lifetime. Compare with:
- Funder-A (`5EiXej3...`): nonce 23,452 — automated distributor
- Funder-B (`5DunDrF...`): nonce 23,089 — automated distributor
- Rank-#4 wallet (`5FqBL928...`): nonce 181,845 — extreme hot wallet
- Shadow whales SW1–SW10: nonce 0 — never signed anything

This wallet is neither a high-volume automated system nor cold storage. 111 transactions places it in a zone of manual or semi-automated use — someone who transacts occasionally, not constantly.

### Comparison to the shadow whale cluster

The behavioral parallel to the shadow whale cluster is worth drawing explicitly, because it is real — and so is the distinction.

**What they share:** Like the shadow whales, this wallet has no subnet activity, no staking, no on-chain identity, and no registered network role. In both cases, a large TAO position sits at the top of the free-balance ranking belonging to an entity with zero legible presence in the Bittensor AI network. The posture is identical: accumulate on-chain, stay invisible off-chain.

**Where they differ structurally:** The shadow whales are nonce-0. They have never signed a transaction. TAO arrives and sits indefinitely — one-directional, passive, inert. This wallet has nonce 111 and has actively returned ~412,000 TAO outbound, all to a single counterparty. It is not cold storage; it is a managed position cycling funds back and forth with a hub. The shadow whales look like a long-term accumulation strategy. This wallet looks like an operational float — a holding address inside a larger active apparatus.

**The unifying implication:** Both patterns are consistent with an actor who wants to hold a large TAO position while leaving no footprint in the network itself. The mechanism differs — passive cold storage versus active float cycling — but the underlying posture is the same. Neither entity is here to run subnets, validate, or participate in Yuma consensus. They are here to hold TAO, and they have structured their on-chain presence to be as opaque as possible while doing so. That the two operations appear to be independent (no direct transfers connect them) makes the parallel more striking, not less: it suggests this kind of ecosystem-invisible large-position holding may be more common than the network's legible participant population implies.


## Balance Accumulation Timeline

Archive node balance history at 14 sample points:

```
       Block   Approx Date        Free TAO
           1   2023-01-03            0.000
   4,000,000   2024-07-11            0.000   ← zero through dTAO launch
   5,000,000   2024-11-27       40,829.267   ← first appearance: ~41k TAO
   6,000,000   2025-04-15      134,324.923   ← peak: ~134k TAO
   7,000,000   2025-09-01      111,190.320   ← declining
   7,767,315   2026-03-17       98,895.052   ← current: ~99k TAO
```

**Three phases are visible:**

1. **Pre-activity (before block ~4.1M, Oct 2024):** Zero balance. The wallet did not exist as an active entity before dTAO launched.

2. **Accumulation phase (Oct 2024 – Apr 2025):** Balance grew from zero to a peak of ~134,000 TAO over roughly six months. The API shows the very first event was at block 4,011,523 (October 10, 2024).

3. **Distribution phase (May 2025 – present):** Balance has been declining. Outbound transfers have exceeded inbound. The wallet went from 134k TAO to ~99k TAO between April 2025 and March 2026 — a net drawdown of ~35,000 TAO over eleven months.

**Comparison to shadow whale cluster:** The shadow whales (SW1–SW9) all had zero balance through block 5,000,000. This wallet already had 40,829 TAO by that point, suggesting it was active in the very early post-dTAO period when the shadow whale infrastructure was just beginning to form. It predates the shadow whale accumulation curve, though neither predates the other by more than a few months.


## Full Transfer History

816 total events across two types:

| Event type | Count |
|---|---|
| Transfer | 703 |
| TransactionFeePaid | 113 |

The 113 fee events correspond exactly to 113 outbound transfers. Every time this wallet signed an outbound transfer, a `TransactionFeePaid` event was recorded — confirming nonce 111 maps precisely to the outbound transfer count.

```
Inbound transfers:   590    total  507,244 TAO   from  5 senders
Outbound transfers:  113    total  412,159 TAO   to    1 recipient
Net accumulation:           +95,085 TAO
```

**The outbound recipient concentration is the most striking single finding: 113 outbound transfers, 100% going to one address.** Every TAO that left this wallet went to the same destination.


## The Dominant Counterparty

The single recipient of all 113 outbound transfers — and the source of 98% of all inbound TAO — is:

**`5FZiuxCBt8p6PFDisJ9ZEbBaKNVKy6TeemVJd1Z6jscsdjib`**

```
Inbound from this address:   498,026 TAO over 363 transfers
Outbound to this address:    412,159 TAO over 113 transfers
Total volume through pair:   910,185 TAO
Current nonce of counterparty: 41,189    ← HOT / automated wallet
Current balance of counterparty: 3,961 TAO
```

Nonce 41,189 on the counterparty tells the same story as Funder-A and Funder-B in the shadow whale investigation: this is a high-velocity automated system, not a human hand-signing transactions. It has passed through enormous volumes of TAO (far more than its current 3,961 TAO balance implies) and is still active.

**The relationship is a two-way channel, not a one-way flow.** TAO moves in both directions between the target and this single counterparty — often in patterns that suggest round-trips: large inbound deposits followed later by large outbound consolidations. This is consistent with the target wallet being used as a **float account or escrow** within a larger operation where the hot wallet (`5FZiux...`) is the operational hub.

The hot wallet's extremely low current balance (3,961 TAO) despite having processed ~500k+ TAO inbound to the target alone suggests it routes large volumes through without retaining them — classic hot wallet behavior.

### Temporal pattern of the dominant pair

```
Block window    Approx date     Inbound TAO    Outbound TAO   Events
  4,000,000     2024-07-11            0.05           0.01        3   ← dust activation
  4,300,000     2024-08-22        4,892.56           0.00        2   ← first real deposits
  4,400,000     2024-09-05        5,885.08           0.00       12
  4,500,000     2024-09-19        7,955.01           0.00       14
  4,600,000     2024-10-02        9,796.57           0.00       10
  4,700,000     2024-10-16        4,300.00           0.00        4
  4,800,000     2024-10-30        8,000.00           0.00        3
  5,100,000     2024-12-11       36,462.83           1.00       16   ← large acceleration
  5,200,000     2024-12-25       80,270.01      18,255.00       13   ← peak inflow window
  5,300,000     2025-01-08        9,570.60       2,608.00        6
  5,400,000     2025-01-22       17,412.32      22,079.00       21
  5,500,000     2025-02-04       23,336.06      22,886.00       20
  ...steady bidirectional traffic through 2025...
  7,700,000     2025-12-07        7,000.00       9,953.00       10   ← still active
```

The early window (blocks 4M–4.8M, roughly July–October 2024) is **inbound-only** — the target is accumulating, not distributing. The first outbound transfer appears in the 5,100,000 window (~December 2024). After that, the pattern shifts to high bidirectional volume suggesting an operational role.

**Largest single inbound transfers:**

```
65,000 TAO  block 5,271,417  (2025-04-03)  from 5FZiux...
31,000 TAO  block 5,105,382  (2025-03-11)  from 5FZiux...
 8,283 TAO  block 5,349,157  (2025-04-14)  from 5FZiux...
 6,821 TAO  block 5,764,334  (2025-06-12)  from 5FZiux...
 6,000 TAO  block 5,682,060  (2025-06-01)  from 5FZiux...
```

The 65,000 TAO single transfer is by far the largest in the dataset. At ~$200–400/TAO (rough range through this period), this is an $13M–26M transfer in a single extrinsic. The 31,000 TAO event three weeks earlier is comparable.

**Largest single outbound transfers:**

```
15,000 TAO  block 5,469,768  (2025-05-01)  to   5FZiux...
12,000 TAO  block 6,805,877  (2025-11-04)  to   5FZiux...
10,000 TAO  block 6,003,639  (2025-07-15)  to   5FZiux...
 8,976 TAO  block 5,227,203  (2025-03-28)  to   5FZiux...
```

The round-number outbound amounts (15k, 12k, 10k) are consistent with deliberate position management rather than automated fractional routing. The 15,000 TAO outbound on block 5,469,768 (May 1, 2025) comes shortly after the 65,000 TAO inbound on April 3 — the pattern suggests the target received a large batch and then returned a portion of it.


## The Early Seed: A Second Sender

The primary counterparty (`5FZiux...`) dominates the history, but it was not the first. The second-largest sender (`5DxcqzHjknv1gUReoRVYg1R6XjGgPMRD1ww4koTQND7ZLJsP`) started earlier:

```
5DxcqzHjknv1gUReoRVYg1R6XjGgPMRD1ww4koTQND7ZLJsP
  Inbound:  9,217 TAO over 11 transfers
  First block: 4,011,523  (October 10, 2024) ← the very first event in the target's history
  Nonce: 670
  Current balance: 2,751 TAO
```

This address made the first transfer into the target at the very earliest block in its history. It is a moderately active wallet (nonce 670) that still holds 2,751 TAO. The relationship is not high-volume but its timing — being the *initiating sender* — makes it structurally important. In the shadow whale investigation, the address that sent the *first* transfer to a wallet was the key to tracing the funding lineage. Here, `5DxcqzH...` is the analogue of Funder-A/Funder-B: the entity that created the initial on-chain relationship.

The address is not in `known_holders.json` — it is not a registered validator, subnet owner, or identity-bearing coldkey.


## Zero-Amount Transfer Anomaly

Two addresses sent Transfer events to the target with **zero (or dust) TAO amounts**:

```
5Ff8xfvJpZFv1gkj3UUz2PVS3pb5fzVQtoha7sfQWBn6djib   211 events  0.000 TAO  (block 6,124,312+)
5DJ6DF9ywrVPpdemxGTP1mNBegdexD3UnUy2SAMvdw84LJsP     4 events  0.000 TAO  (block 6,510,403+)
```

211 zero-TAO Transfer events from a single address is unusual. The most likely interpretations:

- **Blockchain surveillance / wallet mapping**: Some indexers and analytics tools "probe" an address with zero-amount transfers to track when it's active — a kind of on-chain ping
- **Alpha stake movements with zero TAO component**: A dTAO alpha stake operation that routes through zero-TAO extrinsics (unlikely but possible with cross-subnet mechanics)
- **Failed or rejected transactions that the API records as events**

Both sending addresses have non-trivial nonces (2,696 and 180 respectively), suggesting real operational wallets. The sender with 211 events (`5Ff8xfv...`) has nonce 2,696, indicating it does this regularly across many targets. Neither address appears in the known infra or shadow whale set.


## Address Fingerprinting Observation

Examining the 5 counterparty addresses together reveals a statistically remarkable pattern:

```
5FZiuxCBt8p6PFDisJ9ZEbBaKNVKy6TeemVJd1Z6jscsdjib   ← primary (hot wallet)
5Ff8xfvJpZFv1gkj3UUz2PVS3pb5fzVQtoha7sfQWBn6djib   ← zero-amount prober

5DxcqzHjknv1gUReoRVYg1R6XjGgPMRD1ww4koTQND7ZLJsP   ← early seed sender
5DJ6DF9ywrVPpdemxGTP1mNBegdexD3UnUy2SAMvdw84LJsP   ← zero-amount prober
```

Two distinct pairs share a 4-character base58 suffix:
- Pair 1: `...djib` — the high-volume hot wallet and the 211-event zero-amount prober
- Pair 2: `...LJsP` — the early seed sender and the 4-event zero-amount prober

In base58 encoding, each character carries log2(58) ~= 5.86 bits of information. A shared 4-character suffix carries ~23.4 bits of constraint. The probability of this occurring by chance across two independent pairs from a set of five addresses is approximately one in several billion. **This is not coincidence.**

The shared suffix almost certainly indicates one of two things:
1. **Vanity address generation** — the private keys for these addresses were generated using a brute-force search to produce addresses with a desired trailing pattern. This is computationally feasible and is used in blockchain contexts to create visually linkable or memorable addresses.
2. **Common derivation path** — the addresses derive from a shared root key via different derivation paths that happen to produce similar trailing bytes, possibly by design.

Either way, it implies a single entity controls (at minimum) these four addresses: the hot wallet hub, the early seed wallet, and both zero-amount probers. Combined with the single-recipient pattern in the target's outbound history, the evidence points to a coordinated multi-wallet operation under unified control.


## Shadow Whale Cluster Cross-Reference

Direct comparison against the shadow whale cluster (SW1–SW10) and all known infrastructure addresses (Funder-A, Funder-B, HB2Q8, DfKewdx, FV99mB, GBnPzv, HUPxAs, FXw2v9, ESDyJB):

```
Inbound from shadow wallets:  NONE
Outbound to shadow wallets:   NONE
Inbound from known infra:     NONE
Outbound to known infra:      NONE
```

**This wallet is not directly connected to the shadow whale cluster.** There are no on-chain transfers between the target and any of the ten shadow wallets or any of the nine infrastructure addresses identified in the shadow whale investigation. These are separate networks.

This matters for interpreting the attack: if the attacker's wallet was draining victims and routing proceeds into the shadow whale cluster, we would expect to see overlap. We do not. The two operations appear to be independent.


## What the Blockchain Data Shows (and Doesn't Show)

**What we can see:**
- This wallet accumulated ~134k TAO peak (April 2025) entirely through one primary counterparty relationship
- It has been in a net drawdown since April 2025, returning TAO to the same single hot wallet it received from
- 111 outbound transactions, all to one address — a degree of concentration that is unusual even for purpose-built transfer wallets
- A cluster of related addresses (sharing address suffixes) operates around it
- The early seed sender pre-dates the main relationship and has not been identified

**What we cannot see from on-chain data alone:**
- Whether the inbound TAO represents proceeds from private key theft, or legitimate transfers (exchange withdrawals, OTC deals, etc.)
- The identity of the controllers of `5FZiux...` or `5DxcqzH...`
- The downstream use of the 412,159 TAO that was returned outbound to `5FZiux...`
- Whether the off-chain attack code and the on-chain wallet activity are operated by the same party

**What would upgrade this from correlation to attribution:**
- Timing analysis: if large inbound deposits to this wallet correlate with specific victim reports (within a day or two of a reported theft), that would be strong circumstantial evidence
- Tracing `5FZiux...` further — with nonce 41,189, this address has an enormous transaction history; its inbound sources would reveal whether it receives from victim wallets
- IP/exchange attribution for `5FZiux...` — if it is an exchange deposit address, the exchange may have KYC linking it to an identity


## Open Threads

1. **Profile `5FZiuxCBt8p6PFDisJ9ZEbBaKNVKy6TeemVJd1Z6jscsdjib`**: With nonce 41,189 and a complete two-way relationship with the target, this is the most important address in the investigation. It processed >900k TAO total volume with the target alone. What is its full sender set? If victim wallets appear as inbound senders to `5FZiux...`, the chain of custody is established.

2. **Profile `5DxcqzHjknv1gUReoRVYg1R6XjGgPMRD1ww4koTQND7ZLJsP`**: The original seed sender. Nonce 670, still holding 2,751 TAO. Who funded it? What else has it funded?

3. **The suffix-paired addresses**: Script an address scan to find any other wallets sharing `...djib` or `...LJsP` suffixes — if more exist, the vanity address generation pattern becomes a fingerprint for this actor across the broader ecosystem.

4. **Victim wallet cross-reference**: Compile the list of known victim addresses from the attack disclosure, then check each against the inbound transfer list for `5FZiux...`. A match would link the on-chain funds movement to a specific theft event.

5. **Timing correlation**: The largest single inbound transfers (65k TAO on April 3, 31k TAO on March 11) occurred in the blocks 5,105,382–5,271,417 range (March–April 2025). If there is a corresponding surge in victim reports from that period, it brackets the attack window on-chain.

---

*Investigation continues in `investigate_attacker.py`. Raw data: `attacker_events.json`, `attacker_profile_report.txt`.*
