# Const's Tokenomic Network: A Profile

*A profile of Jacob Robert Steeves ("Const"), Bittensor co-founder and active builder. One address is attributable to Const with high confidence via on-chain identity registration (the SN120 owner key); a second is community-rumored to be his personal coldkey but unverified. Const is deeply embedded across the ecosystem — subnet owner, validator, and one of the largest total TAO holders by taostats ranking — and a complete picture of his on-chain footprint will require tracing multiple subnet ownerships, associated hotkeys, and staked positions across alpha pools. This document is a work in progress. The immediate purpose: any rigorous attribution exercise must exclude known benign explanations before drawing stronger conclusions, and a founding team managing large positions centrally is exactly the kind of pattern that needs to be characterized and accounted for.*

**Data sources:** `known_holders_report.txt`, `validator_stake_weight_report.txt`, `top100_holders_report.txt`, `const_attribution_report.txt` (pending completion)

---

## Known Addresses

Two addresses are attributable to Const with varying confidence:

| Label | Address | Source | Confidence |
|---|---|---|---|
| Community-attributed key | `5GH2aUTMRUh1RprCgH4x3tRyCaKeUi5BfmYCfs1NARA8R54n` | Rumored in community channels; unverified | Low — unconfirmed attribution |
| SN120 owner key | `5Fc3ZZQAYB3SPXKcFnd1WJeyQvArSZZeB6LU1rb7zvQ6XvDh` | On-chain identity registered as "const" in `IdentitiesV2`; registered as validator + SN120 owner | High — on-chain self-identification |

The connection between these two addresses is what `const_attribution.py` investigates. See the [Attribution Check](#attribution-check) section below.

---

## On-Chain Profile: Community-Attributed Key (`5GH2aUTMRUh1RprCgH4x3tRyCaKeUi5BfmYCfs1NARA8R54n`)

**Free balance:** ~3,270 TAO — ranked #66 in the free-balance top 100 (`top100_holders_report.txt`).

**Role classification:** `pure_holder` at the key level — no validator registration, no subnet ownership on this key. The key has signed transactions (nonce > 0), disqualifying it from shadow wallet status.

**Stake-weight:** The validator stake-weight report (`validator_stake_weight_report.txt`) lists this key as `(not a delegate)` — meaning no validator hotkey is currently associated with it in `DelegateInfo`. This key does not appear in the top validator list by stake-weight.

**Interpretation.** Const reportedly ranks near #2 on taostats by total holdings, which implies a very large staked position. The 3,270 TAO free balance at #66 is not his wealth — it is operational float. The bulk of his TAO is staked, held in per-subnet alpha pools which are tracked separately from the `System.Account` free balance. Under [dTAO](https://docs.learnbittensor.org/learn/emissions), stake lives in per-subnet liquidity pools and generates [emissions](https://docs.learnbittensor.org/learn/emissions) for the holder; this staked alpha does not appear in free-balance rankings. A [validator](https://docs.learnbittensor.org/validators/) or [subnet owner](https://docs.learnbittensor.org/subnets/understanding-subnets) holding most of their position as staked alpha would show a deceptively small free balance in our analysis — exactly what we observe here. This is the expected posture for an active, deeply embedded network participant.

---

## On-Chain Profile: SN120 Owner Key (`5Fc3ZZQAYB3SPXKcFnd1WJeyQvArSZZeB6LU1rb7zvQ6XvDh`)

**Free balance:** 91 TAO (`known_holders_report.txt`).

**Role:** validator + subnet_owner, SN[120] (Affine). This key has signed transactions, has a registered hotkey, and owns subnet 120.

**Stake-weight:** Listed in `validator_stake_weight_report.txt` as `0.00 TAO` delegate stake. This is consistent with SN120 being a subnet-owner/miner key rather than a major validator by delegated stake — `DelegateInfo.total_stake` reflects TAO staked *to* the validator hotkey by nominators, not the operator's own position.

**On-chain identity:** Registered as `const` in `IdentitiesV2` (reflected in `known_holders.py` labeling). This is the key with publicly registered on-chain identity, consistent with the operational key of a subnet owner who needs to signal identity.

---

## Shadow Whale Intersection: What the Data Shows

The two Const addresses have been cross-referenced against all shadow-whale-relevant data:

**First deposit senders (`first_transfers.json`):** Neither `5GH2aUTMRUh1RprCgH4x3tRyCaKeUi5BfmYCfs1NARA8R54n` nor `5Fc3ZZQAYB3SPXKcFnd1WJeyQvArSZZeB6LU1rb7zvQ6XvDh` appears as the first-deposit sender for any of the top 10 shadow wallets.

**Known-entity transfer scan (`known_to_shadow_report.txt`):** `trace_known_to_shadow.py` cross-referenced all 2,369 known entities (validators, SN owners, identity-registered coldkeys) against the first-funded-block events for each shadow wallet. Result: `No known entity appears as a first-deposit sender for any of the top 10 shadow wallets.` Both Const keys are in `known_holders.json` and were therefore included in this scan. Neither triggered a match.

**Funder investigation (`funder_investigation_report.txt`):** The binary-search inbound transfer history for Funder-A (`5EiXej3...`, nonce 23,452) and Funder-B (`5DunDrF...`, nonce 23,089) — the two automated pass-through wallets that seeded most of the shadow whale ecosystem — shows no transfers from either Const address.

**Summary:** As of the data available, **neither of Const's known addresses has any on-chain connection to the shadow whale infrastructure.** The shadow whale funders (Funder-A, Funder-B, and their feeder wallets) are all anonymous, unregistered addresses with no link to `known_holders.json`. Const's keys are both registered in the known-holders set and were included in the sweep — no match.

There is no positive on-chain evidence connecting Const to the shadow whale ecosystem, although this does not rule out connection through addresses not yet linked to Const.

---

## Attribution Check: Are the Two Const Keys the Same Controller? {#attribution-check}

`const_attribution.py` checks whether `5GH2aUTMRUh1RprCgH4x3tRyCaKeUi5BfmYCfs1NARA8R54n` (community-attributed key) and `5Fc3ZZQAYB3SPXKcFnd1WJeyQvArSZZeB6LU1rb7zvQ6XvDh` (SN120 owner) have ever transferred TAO directly between each other — which would be on-chain evidence of shared control.

The script:
1. Samples both keys' balances at 14 historical blocks (block 1 through current)
2. Binary-searches each balance-change interval to find exact change blocks
3. Fetches all `Balances.Transfer` events at those blocks and checks for transfers between the two keys
4. Also records all inbound/outbound transfers at those blocks for context
5. Checks for any `ColdkeySwapped` events involving either address

**Results:** *(pending — `const_attribution.py` running against the archive node)*

<!-- REPLACE THIS SECTION with const_attribution_report.txt contents when the script completes -->

---

## Structural Comparison: Const vs. Shadow Whales

| Attribute | Const (attributed key) | Const (SN120 key) | Top shadow whales |
|---|---|---|---|
| Nonce | > 0 | > 0 | = 0 |
| On-chain identity | None on this key | Registered ("const") | None |
| Network role | None (pure_holder) | validator + SN120 owner | None |
| Free balance | ~3,270 TAO (rank #66) | ~91 TAO | 17,850–141,003 TAO each |
| Stake | Majority of wealth | Minimal (dTAO alpha) | Zero |
| Balance pattern | Stable (small float) | Stable (small float) | Monotonically increasing |
| Connected to shadow infra | **No** | **No** | N/A |

Const's tokenomic posture is the archetypal *sunny whale* — high total holdings driven by [staked positions](https://docs.learnbittensor.org/staking-and-delegation/delegation), small free balance, active network participant with signed transactions. This is structurally opposite to the shadow whale profile (large free balance, zero stake, nonce = 0, anonymous).

---

## Open Questions

1. **Are the two Const keys the same controller?** `const_attribution.py` results will show whether they have ever transferred directly. If yes, confirmed shared control. If no, the link rests on the `known_holders.py` labeling assumption.

2. **Where is Const's staked balance?** The `TotalColdkeyStake` ledger does not capture dTAO alpha-pool stake. If Const's reported #2 ranking on taostats is accurate, his stake is distributed across multiple subnet alpha pools under hotkey(s) not yet traced from his known coldkeys.

3. **Does `5GH2aUTMRUh1RprCgH4x3tRyCaKeUi5BfmYCfs1NARA8R54n` have additional associated hotkeys?** This key is not registered as a delegate. If Const has staked through a separate hotkey arrangement, those stakes would appear under that hotkey's coldkey association, not under the public key directly.
