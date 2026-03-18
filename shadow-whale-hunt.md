
# Hunt for the Shadow Whales: Mapping Bittensor's Unknown Holders

*An investigative blog and scripting tutorial. All scripts referenced are available in this repository.*

**Data collected:** block 7,738,261 (March 13, 2026); tao.app API queries at block ~7,767,000 (March 17, 2026)
**Archive history:** 14 sample points from block 1 through block 7,739,373
**Status:** Active investigation — cross-funder network mapped via tao.app API; upstream BFS to next layer pending


## Intro

As a tutorial exercise in getting to know Bittensor's blockchain architecture, this page uses the [Bittensor Python SDK](https://docs.learnbittensor.org/sdk/index) and blockchain queries to investigate the 'ecology' of Bittensor's population of 'whales', that is, the ecosystem's largest token holders.
<!-- Use this current framing in the intro throughout, not the prior more aggressive idea of a 'hunt' which implies almost that shadow wallets are bad actors, which there is no evidence of at all; they do represent a kind of tokenomic risk but they do not imply bad intent or action, and in fact many of them likely represent good security practices of keeping TAO in deep storage; although this does imply that they are not staking, even into root, which is strange... -->

We began with general questions such as, how much of the total TAO and total overall [stake-weight](https://docs.learnbittensor.org/resources/glossary#stake-weight) is held by validators, subnet owners, miners, etc.

One quesiton of particular interest at the start was, how much of the TAO in the ecosystem is held by what we might call 'shadow whales', large holders who have no known identity whatsoever. I here mean 'identity' in any of the following senses: 1) an on-chain identity, as in a website and company name held in the 'identity field' on the bittensor blockchain. unfortunately, it's usually only validators and sn owners that do this at all, and many of them don't even do it. 2) a public off-chain identity, which could mean tweeting or sharing on your website what your key is. Startups that run multiple subnets may do this, for example [https://latent.to/](https://latent.to/). 3) An implicit behavioral identity defined by the transactions that the wallet has signed, which can be publicly viewed on the public chain.

We define shadow wallets here as having nonce=0 (meaning the next transaction they sign will be their first, implying they have never signed a transaction), and having no stake. 

Because shadow wallets by definition have never signed a transaction, meaning they have never transferred TAO or alpha stake, or staked TAO into a subnet's alpha, nor registered a hotkey on a subnet. Shadow wallets may be the recipients of transfers of TAO, and can have owner permissions for a subnet if someone creates a subnet with one wallet and then does a coldkey-swap to the shadow wallet, since this does not require it to sign a transaction. However, it would not then be able to sign any transactions (although proxy ownership could solve this problem, since proxy relationship are transferred with coldkey-swaps along with subnet ownership).

We set out simply to map who holds what — but the investigation had a surprise: it converged on evidence that a single unknown entity controls around 20% of all freely circulating (non-staked) TAO, spread across roughly seven "shadow wallets" — addresses that have never signed a transaction. Two automated pass-through wallets, each with ~23,000 transactions, have been steadily dripping TAO into these cold addresses over months. The link between the two pass-through wallets: the same upstream address initialized both within 17 minutes of each other. Nothing at any layer connects to a known validator, subnet owner, or any registered on-chain identity. The operator could be an exchange, an institution, or a single large investor — it isn't public information. But it represents an unknown concentration of power in the ecosystem that bears consideration.

In Bittensor, [staking TAO](https://docs.learnbittensor.org/staking-and-delegation/delegation) to validators is how large holders actively direct the network. Validators with more delegated [stake weight](https://docs.learnbittensor.org/resources/glossary#stake-weight) carry more influence in [Yuma Consensus](https://docs.learnbittensor.org/learn/yuma-consensus) — the on-chain algorithm that converts validators' rankings of miners into [emission](https://docs.learnbittensor.org/learn/emissions) allocations, distributing newly minted TAO and subnet alpha tokens to miners, validators, stakers, and subnet creators each [epoch](https://docs.learnbittensor.org/resources/glossary#epoch). Stake also determines which subnets attract new TAO liquidity: under Bittensor's current [flow-based emissions model](https://docs.learnbittensor.org/learn/emissions#tao-reserve-injection), a subnet's share of the network's 0.5 TAO/block emission is proportional to net staking inflows into that subnet's pool. Shadow TAO, by definition, participates in none of this — it is not staked, it earns no emissions, and it exerts no weight in consensus. The proportion of free supply that is actively deployed is one signal of network participation; 31.6% sitting in nonce-0 wallets is a meaningful gap.



## The Shadow Wallet Census

Before querying anything, we need a precise definition of what we're looking for. A **shadow wallet** is an address that holds a meaningful balance but has never acted on-chain as a sender. More precisely, three conditions must all hold:

1. **Nonce = 0** — has never originated a transaction
2. **No stake** — does not appear in `StakingColdkeys`
3. **Free balance > 1 TAO** — above the dust threshold

The classification logic is in `analyze_wallets.py`:

```python
# analyze_wallets.py — shadow wallet classification
for ss58, free_tao, nonce in accounts:
    has_stake = ss58 in staking_coldkeys
    if nonce == 0 and not has_stake and free_tao > 1.0:
        shadow_wallets.append(...)
```

**Why nonce?** In Substrate, every account's nonce increments each time it signs and submits an extrinsic. Nonce = 0 means the address has never sent, staked, registered, or done anything as a sender. It may have *received* TAO — but it has left no footprint on the chain as an actor.

**Why no stake?** A wallet could be nonce = 0 yet still have a network relationship if someone staked TAO to a hotkey it owns — that operation is signed by the staker, not the coldkey being staked to. Excluding `StakingColdkeys` keeps the definition tight: no outbound transactions and no network role of any kind.

**Why free balance only?** [Staked TAO](https://docs.learnbittensor.org/staking-and-delegation/delegation) is *not* included in `TotalIssuance`. When TAO is staked, it moves out of the Balances pallet entirely — `Currency::withdraw` removes it from free balance, and it is tracked separately in `SubtensorModule`. This has a direct implication: **a wallet with nonce = 0 and a non-zero free balance cannot have earned that balance through staking rewards.** Staking rewards land in the stake ledger, not in free balance. To convert staked TAO to free balance requires an unstaking transaction — which increments the nonce. A nonce-0 wallet with free balance received that TAO via a direct `Balances.Transfer`. Full stop.

### Enumerating the chain

The measurement is a full scan of `System.Account` — the Substrate storage map that holds every account's balance and nonce, keyed by `AccountId`:

```python
# enumerate_wallets.py — core loop
for key, data in sub.substrate.query_map("System", "Account"):
    free_tao = data.value["data"]["free"] / 1_000_000_000  # rao to TAO
    nonce    = data.value["nonce"]
    ss58 = ss58_encode(bytes(key[0]).hex(), ss58_format=42)
```

We also pull the staking ledger and chain totals:

```python
# Who has any stake at all
for key, _ in sub.substrate.query_map("SubtensorModule", "StakingColdkeys"):
    staking_coldkeys.add(ss58_encode(bytes(key[0]).hex(), 42))

liquid_supply = sub.substrate.query("Balances", "TotalIssuance").value / 1e9
total_stake   = sub.substrate.query("SubtensorModule", "TotalStake").value / 1e9
```

Then `analyze_wallets.py` applies the classification:

```python
for ss58, free_tao, nonce in accounts:
    has_stake = ss58 in staking_coldkeys
    if nonce == 0 and not has_stake and free_tao > 1.0:
        shadow_wallets.append(...)
```

### Results

**Supply split at block 7,738,261** (`finney_summary.txt`):

```
Block:                      7,738,261
Total issuance:             3,401,428.01 TAO
Total free balances (sum):  3,400,473.40 TAO
Total staked (chain total): 7,337,639.83 TAO
Accounted for:              10,738,113.23 TAO

Total accounts:                  446,835
  With stake:                     47,255
  No stake:                      399,580
  Ever sent a tx (nonce>0):      406,424
  Never sent a tx:                40,411
```

The near-exact match between `TotalIssuance` and the sum of all free balances (~955 TAO difference, attributable to reserved/frozen balances) confirms the accounting is sound.

**Shadow wallet totals at the same block:**

```
Shadow wallets (>1 TAO, nonce=0, no stake):
  Count:                          14,032
  TAO held:                 1,075,902.89 TAO
  % of free supply:                31.6%

Large shadow (>1000 TAO, nonce=0, no stake):
  Count:                              50
  TAO held:                   850,237.96 TAO
```

The 50 largest shadow wallets hold 850,000 TAO, over 30% of all freely circulating TAO and more than the entire validator and subnet owner ecosystem combined, as we will see.


## Sunny Whales vs. Shadow Whales

Not all large holders are opaque. Bittensor has real **sunny whales** — large holders who are publicly attributable. Understanding them establishes the baseline that makes shadow wallets anomalous.

### Sources of attribution

**On-chain identity** is the most direct: any [coldkey](https://docs.learnbittensor.org/resources/glossary#coldkey) can register a name, URL, GitHub, Discord, and Twitter via `SubtensorModule.IdentitiesV2`. Querying it is straightforward:

```python
# identity_lookup.py
result = sub.substrate.query("SubtensorModule", "IdentitiesV2", [ss58])
if result and result.value:
    name = result.value.get("name", "")
```

Registering an identity requires signing a transaction. By definition, no shadow wallet can have on-chain identity — it would immediately disqualify them (nonce would be > 0).

**Validator and delegate identity.** Every [validator](https://docs.learnbittensor.org/validators/) registers a [hotkey](https://docs.learnbittensor.org/resources/glossary#hotkey) and associates it with a [coldkey](https://docs.learnbittensor.org/resources/glossary#coldkey). Named validators can register delegate identities — human-readable names attached to their hotkey. Query all delegates:

```python
delegates = sub.get_delegates()
# Each DelegateInfo has: hotkey_ss58, owner_ss58 (coldkey), validator_permits, etc.
delegate_identities = sub.get_delegate_identities()  # queries IdentitiesV2 for all delegates
```

**Validators are structurally excluded from being shadow whales.** This is not an assumption — it follows directly from the definition. To be an active validator on Bittensor, a coldkey must have (a) signed transactions to register and configure a hotkey, setting nonce > 0, and (b) staked TAO to receive [validator permits](https://docs.learnbittensor.org/resources/glossary#validator-permit). Both conditions immediately disqualify a wallet from shadow status. `known_holders.py` confirms this empirically: across all 1,966 validator coldkeys, not a single one appears in the shadow wallet list. Average free balance is 7 TAO; every one has a nonce > 0.

**Subnet ownership.** Every subnet has an owner coldkey, queryable from `get_all_subnets_info()`. Subnet owners frequently self-identify through websites, GitHub repositories, and community channels, even if they haven't registered on-chain identity.

**Do subnet owners hold whale-scale liquid TAO?** The top subnet owners by free balance from `known_holders_report.txt`:

```
--- TOP SUBNET OWNERS BY COLDKEY FREE BALANCE ---
   1,941 TAO free  SNs=[51]   Owner51           5FqACMtceg...
   1,403 TAO free  SNs=[41]   Sportstensor      5FCSevLkof...
   1,341 TAO free  SNs=[97]   (no identity)     5G9ZvMXQEe...
   1,126 TAO free  SNs=[125]  (no identity)     5DTzv2rL6Y...
     273 TAO free  SNs=[83]   CliqueAI          5DqEjRLyNN...
     206 TAO free  SNs=[3]    Owner3            5G26HqQg8M...
```

No subnet owner holds whale-scale free balance. The entire 129-coldkey subnet owner population holds 7,309 TAO combined — less than a single mid-tier shadow wallet. Subnet owners, like validators, hold most of their wealth in stake (alpha pool positions in their own subnets), not in freely deployable TAO. The free-balance top of chain is not the subnet owner or validator population.

**Off-chain attribution.** Some wallets are attributable through public disclosure: a founder sharing their address in Discord, an exchange publishing cold wallet addresses for audit purposes, or community-maintained labels on explorers like [taostats.io](https://taostats.io).

### Known sunny whales

**Binance** (`5Hd2ze5ug8n1bo3UCAcQsf66VNjKqGos8u6apNfzcU86pg4N`) is the largest single TAO holder by free balance with **868,020 TAO**. It is an exchange custody cold wallet. Binance has on-chain identity registered (visible on taostats), making it the clearest sunny whale: large, known, and traceable. Exchange cold wallets are identifiable as sunny for behavioral reasons too — they grow *and* shrink as customers deposit and withdraw, and they're publicly documented. This is categorically different from the monotonically growing shadow wallets examined below.

**Jacob Steeves (Const)**, Bittensor co-founder, is attributable through two coldkeys with different confidence levels. The stronger attribution is `5Fc3ZZQAYB3SPXKcFnd1WJeyQvArSZZeB6LU1rb7zvQ6XvDh` — the SN120 (Affine) owner key, which has on-chain identity registered as "const" in `IdentitiesV2` and is associated with a validator hotkey. A second key, `5GH2aUTMRUh1RprCgH4x3tRyCaKeUi5BfmYCfs1NARA8R54n`, is rumored in community discourse to be his personal coldkey but this attribution is unverified. In the free-balance ranking, the attributed personal key appears at **position #66 with 3,270 TAO free balance** — a number that would be misleading without context. Const reportedly ranks near #2 on taostats by total holdings; the discrepancy is because the vast majority of his TAO is staked. The small free balance is itself informative: his stake is deployed, not sitting in a liquid cold hoard.

**Kraken** validates on the Finney network. Its coldkey holds only **10 TAO free** but **723,400 TAO in stake-weight** across 95 hotkeys — the #2 largest validator. The path from hotkey → `DelegateInfo` → `owner_ss58` (coldkey) is fully on-chain queryable. Registered validators with public brand identities represent the highest-confidence sunny whales: their stake, activity, and identity all corroborate each other.

**The Opentensor Foundation** (`5HBtpwxuGNL1gwzwomwR7sjwUt8WXYSuWcLYN6f9KpTZkP4k`) holds 23 TAO free but **413,881 TAO in stake-weight** across 106 hotkeys — the #5 validator by stake and the anchor of Bittensor's institutional governance layer.

**The free-balance view of known entities is deeply misleading.** `known_holders_by_stakeweight.py` corrects this by combining each coldkey's free balance with its validator stake (summing `DelegateInfo.total_stake` across all owned hotkeys). From `known_holders_stakeweight_report.txt`:

```
Name                           Free TAO    Stake TAO    Combined  HKs
  tao.bot                             3      853,488     853,491    1
  Kraken                             10      723,400     723,410   95
  Taostats                            2      583,924     583,925    2
  Yuma, a DCG Company                10      567,258     567,268  128
  Openτensor Foundaτion              23      413,881     413,904  106
  General Tensor (RoundTable21)      44      293,751     293,796  134
  Crucible Labs                     486      276,705     277,190    3
  Polychain                           7      223,286     223,292    2
  TAO.com                             8      206,364     206,372  112
  tao5                                6      196,277     196,283    1
```

Two significant entities absent from the free-balance ranking appear here: **Taostats** (583,924 TAO stake, #3 by combined weight) and **Yuma, a DCG Company** (567,258 TAO stake, #4). Both hold negligible free balances but are among the largest economic actors on the network — completely invisible from the free-balance lens. The known operator class is larger and more concentrated than the free-balance top 100 would suggest.

Total delegated stake across all 5,609 validators: **5,407,513 TAO**. The top 10 validators by combined weight account for roughly 3.5M TAO — a supermajority of active network governance weight held by approximately 10 known entities.

### The contrast

| Attribute | Sunny whale | Shadow whale |
|---|---|---|
| Nonce | > 0 | = 0 |
| Stake | Present (usually) | Absent |
| On-chain identity | Registered | None |
| Hotkey / subnet ownership | Common | None |
| Balance pattern | Dynamic — grows and shrinks | Monotonic — only grows |
| Governance legibility | Reasonably high | Zero |

The balance pattern row deserves emphasis. Exchange cold wallets, validator coldkeys, and active ecosystem participants all show bidirectional balance changes — funds come in and go out. Every shadow whale in the top 10 shows a monotonically increasing balance from its first appearance to the analysis date. This rules out exchange custody for the largest wallets and is inconsistent with active operational use.



## The Top 100 Free-Balance Holders

`top100_holders.py` was designed to rank all wallets by total TAO (free + staked), but the staked balance query — `SubtensorModule.TotalColdkeyStake` — returned zero for every wallet. With dTAO, stake lives in per-subnet alpha pools rather than a single global ledger, so `TotalColdkeyStake` appears to be incomplete or deprecated in the current model. All 100 wallets show `staked = 0`. The report is therefore a ranking by **free balance only**, not total holdings. This matters: the free-balance top 100 and the total-holdings top 100 are different populations. Here is what the data shows for the top holders ranked by **free balance**:

The first 15 rows of `top100_holders_report.txt` (full file in the repo):

```
#    SS58 Address                                           Free     Staked      Total  Roles / Identity
------------------------------------------------------------------------------------------
1    5Hd2ze5ug8n1bo3UCAcQsf66VNjKqGos8u6apNfzcU86pg4N    868,020          0    868,020  [pure_holder]
2    5FEA1FfUPwT3K4zTsYbQx5X1G9R2ZjYLyFv12xBQxW9QgoCL    141,003          0    141,003  [pure_holder]
3    5ChHTBkaE1VgK5NX59uHuZoK8VQShojKBB1sGfXaZQpxVDCi    129,499          0    129,499  [pure_holder]
4    5FqBL928choLPmeFz5UVAvonBD5k7K2mZSXVC9RkFzLxoy2s    122,232          0    122,232  [pure_holder]
5    5Dhf6WgqrfhVyFCGqK4G5utro2jepscwryMhLHtpMfopxweC    117,065          0    117,065  [pure_holder]
6    5GUkyA37dHnc1rEijDtvBe5yYNCpaNjaHGqB7DY9Kb2KgSj3    108,064          0    108,064  [pure_holder]
7    5H9brHhMA1km3Dp3YCx75oaimgxEYScxCfxbzQRZ3gHk9x3L     98,102          0     98,102  [pure_holder]
8    5C9CxW9355u1sqy6Np85FfGssJAdyA8cAsjjV9YP8aaLvjEY     93,908          0     93,908  [pure_holder]
9    5Epz8SQ69FuZRLyjCAicn8i71SdyEYaWR5rZ5a1i1bgoxGaQ     90,843          0     90,843  [pure_holder]
10   5ELWnR5A7DUmmqHsYPA3iZMFu1BX3gceruEqFPtsmTkCqR7J     81,996          0     81,996  [pure_holder]
...
35   5GhjixW4b6S8MxC4hb2W8xud3U4gw4rUGrqEjTgfSsa2pvPN     12,003          0     12,003  [pure_holder]
36   5EE7eFjdM5tPjizRywj25rK82GH4eDQCxh3PT4BZgkaWBuvn     12,003          0     12,003  [pure_holder]
37   5GEQHK4XnfJAzqVJQ1twRiNdfTEBTPmCMcmmLpRY3qrJkMzJ     12,003          0     12,003  [pure_holder]
38   5GgeiyNgHu7dL961ZDFVpStm53VeqQVoSCZmM4Xt4T1p27ta     12,003          0     12,003  [pure_holder]
39   5HAZamWxtVYNkukfc8cEWDrk64JLRncuG1rC7t4Pcm3BVVAt     12,003          0     12,003  [pure_holder]
...
66   5GH2aUTMRUh1RprCgH4x3tRyCaKeUi5BfmYCfs1NARA8R54n      3,270          0      3,270  [pure_holder]
...
83   5GmHcpW2tQ4HfRqCfFCEkjfCnnAFQB29AeKhBYMhqWk5e2Xw      2,171          0      2,171  [validator+subnet_owner] SN[...]
...
91   5FqACMtcegZxxopgu1g7TgyrnyD8skurr9QDPLPhxNQzsThe       1,885          0      1,885  [validator+miner+subnet_owner] SN[51]
```

Role summary from the same file:
```
ROLE SUMMARY (top 100 wallets):
  pure_holder         98 wallets     2,805,077 TAO  (26.1% of supply)
  validator            2 wallets         4,038 TAO  (0.0% of supply)
  subnet_owner         2 wallets         4,038 TAO  (0.0% of supply)
  miner                1 wallets         1,885 TAO  (0.0% of supply)

Identity coverage (top 100): 0/100 have on-chain identity
```

**On-chain identity: expected result.** Very few of the top 100 free-balance holders have on-chain coldkey identity registered. This is not a surprising finding: the identity pallet is primarily used by validators and subnet owners as a signaling mechanism for their hotkey-linked coldkeys. There is no norm or expectation that regular holders register identity, and the script queries coldkey identity specifically — hotkey delegate identity is a separate registration. The absence of registered identity in this list means nothing by itself.

Two wallets are attributable from off-chain sources (Binance and Const). The remaining 98 are unknown, but that is the normal state for large holders on a permissionless chain.

**The real top-line finding: role distribution.** 98 out of 100 of the largest free-balance holders are `pure_holder` — no stake, no validator role, no subnet ownership. Only 2 are active network participants (positions #83 and #91 with a combined 4,038 TAO in free balance). The free-balance top of the chain is passive holders, not operators, by an overwhelming margin.

**Positions #4 and #7 are not shadow wallets.** Position #4 (`5FqBL928...`, 122k TAO) and position #7 (`5H9brHhM...`, 98k TAO) were not in our original top-10 shadow wallet analysis. A direct nonce query (`nonce_check.json`, block 7,760,196) confirms why:

```json
{
  "query_block": 7760196,
  "wallets": [
    {
      "ss58": "5FqBL928choLPmeFz5UVAvonBD5k7K2mZSXVC9RkFzLxoy2s",
      "free_balance_rank": 4,
      "nonce": 181845,
      "free_tao": 122886.979737487
    },
    {
      "ss58": "5H9brHhMA1km3Dp3YCx75oaimgxEYScxCfxbzQRZ3gHk9x3L",
      "free_balance_rank": 7,
      "nonce": 111,
      "free_tao": 95895.052102143
    }
  ]
}
```

Nonce 181,845 on `5FqBL928...` is extraordinarily high — this is a very active wallet, possibly a hot wallet or automated exchange address. Nonce 111 on `5H9brHhM...` is also clearly active. Neither qualifies as a shadow wallet. Both are large free-balance holders who transact on-chain but hold no stake and have no registered network role — a different category from shadow wallets, and not a governance concern of the same kind.

**The 12,003 TAO cluster.** Positions 36–39 in the top 100 show four wallets each holding exactly **12,003 TAO**:

- `5EE7eFjdM5...`
- `5GEQHK4Xn...`
- `5GgeiyNgH...`
- `5HAZamWxt...`

Four wallets with an identical, non-round balance is not coincidence. This is almost certainly one entity distributing TAO across multiple addresses in equal tranches. A single $12,003 TAO event divided four ways would explain it. Combined: 48,012 TAO under coordinated single-entity control, invisible on-chain because the addresses have never interacted with each other.

**Role distribution among top 100:**

| Role | Count | TAO held |
|---|---|---|
| pure_holder | 98 | 2,805,077 |
| validator + subnet_owner | 2 | 4,038 |

The two validators appear at positions #83 and #91 — near the bottom of the top 100 by free balance. This makes structural sense: active validators hold most of their wealth as *staked* TAO, not free balance. The free-balance top 100 is dominated by passive holders, not network operators.



## Liquidity Asymmetry

The free-balance framing surfaces a structural dynamic that matters more than the headline number alone.

Shadow whales dominating the **liquid supply** is a different kind of threat than dominating total holdings. The distinction hinges on speed of deployment.

**Sunny whales are effectively locked in.** Const, OTF, and active validators hold most of their TAO as **staked balance** — deployed in the network earning [emissions](https://docs.learnbittensor.org/learn/emissions) and directing validator weights. Unstaking takes effect next block, but deploying staked capital at the scale required to match the shadow whales is structurally self-destructive. Validators and subnet owners hold stake inside per-subnet alpha pools; withdrawing large positions causes immediate slippage against those pools, with the unstaker absorbing the price impact while collapsing the subnet's liquidity behind them. A validator who unstakes loses emission weight, and coordinated mass unstaking across the validator set would destabilize the consensus layer — harming precisely the entities doing the unstaking. The sunny whales' stake is effectively illiquid not by rule but by incentive structure: the cost of liquidating it to match shadow whale firepower is losses that the actors themselves could not absorb. A large unstaking event would be visible on-chain as it happened, but there would be no advance signal — and the damage to subnets and emission weights would be immediate.

**Shadow whales are already liquid.** Their holdings are entirely **free balance**. No prior on-chain action is required to deploy them. In a governance dispute — a token vote, a parameter change, a hostile validator election — shadow whales could act in the same block the vote opens. No warning, no preparatory on-chain footprint.

The 31.6% shadow wallet figure — over 1,075,000 TAO in liquid, nonce-0 addresses — should be read in this light. It is not just a curiosity about cold storage habits. It is a measure of how much consensus power could materialize with zero prior on-chain signal.


## Historical Investigation

`shadow_history.py` connects to the Finney **archive node** and queries each shadow whale's balance at 14 sample points across the full chain history:

```python
sub = bt.Subtensor(network="archive")

sample_blocks = [1, 100, 1_000, 10_000, 100_000, 500_000,
                 1_000_000, 2_000_000, 3_000_000, 4_000_000,
                 5_000_000, 6_000_000, 7_000_000, current_block]

for blk in sample_blocks:
    block_hash = sub.substrate.get_block_hash(block_id=blk)
    result = sub.substrate.query("System", "Account", [ss58], block_hash=block_hash)
    free_tao = result.value["data"]["free"] / 1e9
```

Block timing reference (at ~12 seconds/block):

| Block | Approx. date |
|---|---|
| 4,000,000 | September 2024 — just before dTAO launch |
| 6,000,000 | ~July 2025 |
| 7,000,000 | ~December 2025 |
| 7,739,373 | March 2026 (analysis date) |

**Key finding: every top shadow whale had zero balance through block 5,000,000.**

None of these wallets are legacy artifacts from Bittensor's genesis era or the original mining period. The shadow whale phenomenon is post-dTAO. Something about the network's transformation in late 2024 — or the attention and liquidity it brought — appears to have triggered large-scale accumulation into nonce-0 addresses.

Full output from `shadow_history_report.txt` (block 7,739,373):

```
     Block    5FEA1FfUPwT3    5ChHTBkaE1Vg    5Dhf6WgqrfhV    5GUkyA37dHnc    5C9CxW9355u1    5Epz8SQ69FuZ    5GVKorR78gqQ    5HAe1pePzBuP    5DwksfKHHG5r    5CXHJRRk5WAQ
         1               0               0               0               0               0               0               0               0               0               0
       100               0               0               0               0               0               0               0               0               0               0
     1,000               0               0               0               0               0               0               0               0               0               0
    10,000               0               0               0               0               0               0               0               0               0               0
   100,000               0               0               0               0               0               0               0               0               0               0
   500,000               0               0               0               0               0               0               0               0               0               0
 1,000,000               0               0               0               0               0               0               0               0               0               0
 2,000,000               0               0               0               0               0               0               0               0               0               0
 3,000,000               0               0               0               0               0               0               0               0               0               0
 4,000,000               0               0               0               0               0               0               0               0               0         9,800.0
 5,000,000               0               0               0               0               0               0               0               0               0         9,800.0
 6,000,000        23,837.8               0               0               0               0               0               0               0         9,570.6         9,800.0
 7,000,000        86,216.5        84,866.8        70,077.0        64,938.7        18,082.1               0               0               0        14,555.4         9,800.0
 7,739,373       141,002.5       129,499.3       117,065.0       108,063.8        96,009.4        90,843.5        56,342.0        17,850.0        15,131.8         9,800.0
```

Nine of the ten wallets show zero balance at block 4,000,000 (September 2024, just before dTAO launch) and zero at block 5,000,000. The exception is `5CXHJRRk...`, which had exactly 9,800 TAO at block 4,000,000 and has not changed since — the profile of a pre-dTAO cold storage position. The other nine are post-dTAO accumulations.



## The Funding Investigation

Knowing *when* each wallet was first funded is useful. Knowing *who* funded it is the prize.

`find_first_transfer.py` uses binary search against the archive node to narrow down the exact first-funded block for each wallet, then reads the block's events to find the sending address:

```python
def find_first_nonzero_block(ss58, lo, hi):
    """Binary search: return smallest block where free_balance > 0."""
    while lo < hi - 1:
        mid = (lo + hi) // 2
        bh  = sub.substrate.get_block_hash(block_id=mid)
        bal = get_free_balance(ss58, bh)
        if bal > 0:
            hi = mid
        else:
            lo = mid
    return hi
```

This is efficient — it takes ~17 RPC calls to narrow a 1,000,000-block range to a single block.

**First-funded blocks confirmed for all 10 wallets:** the binary search worked. Exact block numbers are in `first_transfers.json`.

**The event lookup required three debugging iterations.** This is documented here because it demonstrates a real pitfall when reading Substrate events via the bittensor SDK — the kind of thing that isn't obvious from the docs.

**Bug v1:** The original script accessed events as `ev.value["event"]["module_id"]`. This was wrong — `get_events()` in this version of bittensor returns plain dicts with top-level fields: `ev["module_id"]`, `ev["event_id"]`, `ev["attributes"]`.

**Bug v2:** After fixing the access pattern, the script tried to decode `attributes["to"]` with `decode_account_id()`, assuming the field would be raw bytes. Also wrong — the RPC layer already decodes `AccountId` fields to SS58 strings. `attributes["from"]` and `attributes["to"]` are ready to use directly.

**v3 (current `find_first_transfer.py`):** Uses `ev["module_id"]` and `attrs["to"]` directly. The complete bug history is in the script's docstring.

```python
# v1 — wrong nesting
module = ev.value["event"]["module_id"]   # AttributeError

# v2 — unnecessary decode
to_addr = decode_account_id(attrs["to"])  # TypeError: string without encoding

# v3 — correct
module  = ev["module_id"]
to_addr = attrs["to"]                      # already an SS58 string
```

**Complete results** (`first_transfers_report.txt`, `first_transfers.json`):

```
Wallet: 5FEA1FfUPwT3K4zTsYbQx5X1G9R2ZjYLyFv12xBQxW9QgoCL
  First funded at block: 5,946,516    Initial deposit: 1,615.857 TAO
  Sender:  5EiXej3AwjKqb9mjQAf29JG5HJf9Dwtt8CjvDqA8biprWTiN  (2 txs: 923.44 + 692.42)

Wallet: 5ChHTBkaE1VgK5NX59uHuZoK8VQShojKBB1sGfXaZQpxVDCi
  First funded at block: 6,084,503    Initial deposit: 196.358 TAO
  Sender:  5DunDrFV6BPbzsgLZUtMQtCq7w9fcUEbM59BUwx5E7N9Bn5E

Wallet: 5Dhf6WgqrfhVyFCGqK4G5utro2jepscwryMhLHtpMfopxweC
  First funded at block: 6,581,276    Initial deposit: 256.505 TAO
  Sender:  5EiXej3AwjKqb9mjQAf29JG5HJf9Dwtt8CjvDqA8biprWTiN   ← same as wallet 1

Wallet: 5GUkyA37dHnc1rEijDtvBe5yYNCpaNjaHGqB7DY9Kb2KgSj3
  First funded at block: 6,659,270    Initial deposit: 247.821 TAO
  Sender:  5FV99mBYw3tYrMTXXe52PDa69an1AE19aTrpnB4kzxW73yUj

Wallet: 5C9CxW9355u1sqy6Np85FfGssJAdyA8cAsjjV9YP8aaLvjEY
  First funded at block: 6,784,524    Initial deposit: 632.937 TAO
  Sender:  5EiXej3AwjKqb9mjQAf29JG5HJf9Dwtt8CjvDqA8biprWTiN   ← same as wallets 1, 3

Wallet: 5Epz8SQ69FuZRLyjCAicn8i71SdyEYaWR5rZ5a1i1bgoxGaQ
  First funded at block: 7,061,941    Initial deposit: 1,026.481 TAO
  Sender:  5DunDrFV6BPbzsgLZUtMQtCq7w9fcUEbM59BUwx5E7N9Bn5E   ← same as wallet 2

Wallet: 5GVKorR78gqQCV6mrWMWX95hHG93ZaRAUShZVBNT768dvqv8
  First funded at block: 7,066,018    Initial deposit: 8,968.653 TAO
  Sender:  5DunDrFV6BPbzsgLZUtMQtCq7w9fcUEbM59BUwx5E7N9Bn5E   ← same as wallets 2, 6
  (9 transfers of exactly 996.517 TAO each — same block)

Wallet: 5HAe1pePzBuPqsF6BpTGN8vCngvKKJaRZ2HkHwFmJgWgAzcf
  First funded at block: 7,563,740    Initial deposit: 850.000 TAO
  Sender:  5GBnPzvPghS8AuCoo6bfnK7JUFHuyUhWSFD4woBNsKnPiEUi

Wallet: 5DwksfKHHG5rURh9jpGaq87m5k3Jn8BJbY9geeX7zTGQD8Pr
  First funded at block: 5,217,006    Initial deposit: 0.220 TAO
  Sender:  5DaH7esryhVaKThgrT2d4BhNdkqoomK2m5Gpkr52nUmYm72n

Wallet: 5CXHJRRk5WAQ8hTkzRDEK89pbsZD2e4Lu7KBTFrHcUQ6GZvz
  First funded at block: 3,766,862    Initial deposit: 0.025 TAO
  Sender:  5FqBL928choLPmeFz5UVAvonBD5k7K2mZSXVC9RkFzLxoy2s   ← free-balance rank #4, nonce 181,845
```

**Sender clustering:** two addresses account for 6 of the 10 first deposits:

| Sender | Funded wallets (first deposit) |
|---|---|
| `5EiXej3...` | #1, #3, #5 |
| `5DunDrF...` | #2, #6, #7 |
| `5FqBL928...` (rank #4) | #10 |
| `5FV99mB...` | #4 |
| `5GBnPzv...` | #8 |
| `5DaH7es...` | #9 |

This establishes that at minimum two distinct entities (those controlling `5EiXej3` and `5DunDrF`) each seeded multiple shadow wallets. Whether a single controller operates both sender addresses is not yet determinable from first-deposit data alone. The next step is tracing the full inbound transfer history of each shadow wallet and the outbound history of the two dominant sender addresses.



## Known Holders — Validators and Subnet Owners

`known_holders.py` enumerates every address that is either (a) registered in `IdentitiesV2`, (b) a delegate validator coldkey, or (c) a subnet owner coldkey — then fetches free balance and `TotalColdkeyStake` for each. This builds the population of "known" TAO holders against which shadow wallets can be compared.

Results from `known_holders_report.txt` (block 7,760,166):

```
Addresses with on-chain identity or network role: 2,369

VALIDATORS vs SUBNET OWNERS COMPARISON
Group                 Count   Total Free TAO  Total Stake TAO     Avg Free
  Validators           1966           14,426                0            7
  SN Owners             129            7,309                0           57
  Both (overlap)        124            7,087                0           57

Note: stake figures from TotalColdkeyStake — may undercount dTAO alpha pool stake.
```

**Key structural finding:** The entire population of 1,966 validator coldkeys holds a combined **14,426 TAO in free balance** — an average of 7 TAO each. The 129 subnet owner coldkeys hold 7,309 TAO total. Combined, the entire attributable network operator class holds less than 22,000 TAO in freely deployable balance.

For comparison: shadow wallets hold **1,075,903 TAO** in free balance. That is **75× the entire validator/subnet-owner ecosystem combined**, in liquid, unattributed capital.

**The overlap is near-total:** 124 of 129 subnet owners are also validators. Subnet ownership and validation are effectively the same population.

**Stake shows zero across the board** — confirming that `TotalColdkeyStake` does not capture dTAO alpha-pool stake. The real staked TAO for validators (which accounts for the bulk of the 7.3M staked on chain) is held in per-subnet pools, not in this legacy ledger. This means the "Stake TAO" column in `known_holders_report.txt` is not usable for total-holdings comparison and should be ignored.

**Top named validators by free balance** (from `known_holders_report.txt`):

```
Name                               Free TAO    Coldkey
  Owner51                             1,941    5FqACMtcegZxxopgu1g7TgyrnyD8skurr9QDPLPhxNQzsThe
  Sportstensor                        1,403    5FCSevLkofmKZRixMawp6jyyjBty1AeSCLa7N5Fv892DYkXX
  FlameWire | SN97                      600    5EXSiTySWQiuzowhogXzfCr4Xn45CW3oMELWGTxFEfQCTy86
  Tao Bridge                            540    5HiveMEoWPmQmBAb8v63bKPcFhgTGCmST1TVZNvPHSTKFLCv
  Crucible Labs                         486    5Eq8b9p6zJMjEXyH9sX4DRMYspnUyorEKq3Zmha1WN6AC4sf
  CliqueAI                              273    5DqEjRLyNN8k3WbEXhA36tyGG4YpWyPEcVSTa47XxspNHhc3
  Kraken                                 10    5FHxxe8ZKYaNmGcSLdG5ekxXeZDhQnk9cbpHdsJW8RunGpSs
  Opentensor Foundation                  23    5HBtpwxuGNL1gwzwomwR7sjwUt8WXYSuWcLYN6f9KpTZkP4k
  const (SN120 owner)                    91    5Fc3ZZQAYB3SPXKcFnd1WJeyQvArSZZeB6LU1rb7zvQ6XvDh
```

Notable: **Kraken** (`5FHxxe8ZKYaNmGcSLdG5ekxXeZDhQnk9cbpHdsJW8RunGpSs`) holds only 10 TAO in free balance. **OTF** (`Opentensor Foundation`) holds 23 TAO free. What matters for these entities is not their free balance but their **[stake-weight](https://docs.learnbittensor.org/resources/glossary#stake-weight)** — the total TAO staked to their validator hotkeys by nominators, which determines their influence over emissions and subnet weights. Free balance for active validators is essentially operational float.

`validator_stake_weight.py` fills this gap. The authoritative source is `DelegateInfo.total_stake`, a dict `{netuid: stake_amount}` returned by `sub.get_delegates()`. Summing across all subnets gives total [stake-weight](https://docs.learnbittensor.org/resources/glossary#stake-weight) per validator — the metric that determines their influence in [Yuma Consensus](https://docs.learnbittensor.org/learn/yuma-consensus) and their share of [emissions](https://docs.learnbittensor.org/learn/emissions). From `validator_stake_weight_report.txt` (block 7,760,965):

```
--- TOP 30 VALIDATORS BY STAKE-WEIGHT ---
     Stake TAO  Name                            Coldkey
  853,488.01  tao.bot                         5GsbTgf...
  723,397.30  Kraken                          5FHxxe8...
  583,923.82  Taostats                        5GcCZ2B...
  566,959.20  Yuma, a DCG Company             5E9fVY1...
  413,410.73  Opentensor Foundation           5HBtpwx...
  293,457.75  General Tensor (RoundTable21)   5DywxdtE...
  276,703.11  Crucible Labs                   5Eq8b9p...
  223,285.57  Polychain                       5GP8N57...
  ...
Total delegated stake across all validators: 5,407,513.43 TAO
Number of delegates: 5,609
```

**Kraken holds 723,397 TAO in stake-weight (#2 overall)** and 10 TAO in free balance. **OTF holds 413,411 TAO in stake-weight (#5 overall)** and 23 TAO free. These numbers are independently confirmed by [tao.app/validators](https://tao.app/validators), which shows the same stake totals and also breaks down each validator's Root vs Alpha stake split — Kraken is 99.1% Root stake, tao.bot is 91.2% Alpha.

The disparity between free balance (tens of TAO) and stake-weight (hundreds of thousands of TAO) is precisely the point: these are not liquid holdings. To deploy that capital, either entity must unstake from their validator — an on-chain, time-delayed action that is publicly visible before it settles. Shadow whales face no such constraint.

The total delegated stake across all 5,609 validators is **5,407,513 TAO** — this is the portion of the 7.3M total staked TAO that is in active validator delegation. The largest 5 validators collectively hold about 3.4M TAO in stake-weight, representing the concentrated core of network governance by the known operator class.

**Combined view: free + stake per coldkey.** `known_holders_by_stakeweight.py` joins `known_holders.json` with `validator_stake_weight.json`, aggregating all hotkey stakes per coldkey to produce a complete economic weight per known entity. The ordering is unrecognizable compared to the free-balance ranking — named holders with large free balances (Owner51 at 1,941 TAO, Sportstensor at 1,403 TAO) don't appear until position ~40. From `known_holders_stakeweight_report.txt`:

```
--- NAMED HOLDERS BY COMBINED WEIGHT ---
Name                           Free TAO    Stake TAO    Combined  HKs  Role
  tao.bot                             3      853,488     853,491    1  validator
  Kraken                             10      723,400     723,410   95  validator
  Taostats                            2      583,924     583,925    2  validator
  Yuma, a DCG Company                10      567,258     567,268  128  validator
  Openτensor Foundaτion              23      413,881     413,904  106  validator
  General Tensor (RoundTable21)      44      293,751     293,796  134  validator
  Crucible Labs                     486      276,705     277,190    3  validator
  Polychain                           7      223,286     223,292    2  validator
  TAO.com                             8      206,364     206,372  112  validator
  tao5                                6      196,277     196,283    1  validator
  Rizzo (Insured)                     7       98,894      98,901  136  validator,sn_owner([20])
  Datura                              0       68,519      68,519    1  validator
  xTAO                                1       60,195      60,196    1  validator
  1T1B.AI                            55       56,801      56,855    2  validator
  Neuralteq.com                      12       54,245      54,256    2  validator
  FirstTensor.com                     0       48,807      48,807    1  validator
  Tatsu                               0       44,971      44,971    2  validator
  Firepool                            1       40,971      40,971    1  validator
  PRvalidator                         0       36,013      36,013    1  validator
  TAO.app                             0       32,951      32,951   22  validator
  NorthTensor                         7       28,695      28,702    1  validator
  Tensorplex Labs                     2       19,690      19,693    1  validator
  Ary van der Touw                   11       19,633      19,644    7  validator
```

This is the definitive ranking of known sunny whale economic weight. The top of the combined list is structurally inaccessible as a governance attack vector — staked capital is illiquid by incentive (see Liquidity Asymmetry below). The shadow whale advantage is not size relative to any single known actor, but liquidity: 1,075,903 TAO deployable in one block vs. the validators' stake that requires unstaking first.


## Full Transfer History — Why It's Hard and How We Approach It

`find_first_transfer.py` tells us who made the *first* deposit into each shadow wallet. But wallets like `5FEA1FfUPwT3...` have grown from a ~1,600 TAO opening balance to over 141,000 TAO. The first deposit is a single data point — all the subsequent transfers, totaling ~139,000 TAO, are unknown.

**The core architectural constraint.** Substrate does not index events by address. The chain's state trie is keyed by `(module, storage_function, params)` — you can query the balance of an address at any block, but there is no built-in way to ask "give me all events involving address X." To find every inbound transfer, the naive approach is to fetch every block and scan its events:

```python
# This is infeasible — millions of RPC calls
for block in range(1, current_block):
    events = sub.substrate.get_events(block_hash=get_block_hash(block))
    for ev in events:
        if ev["module_id"] == "Balances" and ev["event_id"] == "Transfer":
            if ev["attributes"]["to"] == target_ss58:
                record(ev)
```

For a wallet like `5FEA1FfUPwT3...` whose first deposit was at block 5,946,516, a full scan would require ~1.8 million RPC calls. At ~50ms each that is 25 hours per wallet. With 10 wallets, it is not tractable.

**The right approach: binary search on balance checkpoints.** We already have `shadow_history.json` — balance samples at 14 known blocks spanning the full chain history. For any interval `[lo_block, hi_block]` where the balance increased, we know at least one transfer happened somewhere inside. Binary search narrows it to the exact block in O(log_2(interval_width)) calls — roughly 17 for a 1M-block interval. Once we have the block, we fetch that block's events to get the sender and amount. If balance increases again after that block, repeat within `[found_block+1, hi_block]`.

```python
# all_inbound_transfers.py — core loop (simplified)
for lo_block, hi_block in increasing_intervals(sample_points):
    scan_lo, baseline = lo_block, balance_at(lo_block)
    while True:
        found = binary_search_for_increase(ss58, scan_lo, hi_block, baseline)
        if found is None:
            break
        transfers = get_transfers_to(ss58, found)   # fetch that block's events
        scan_lo  = found + 1
        baseline = balance_at(found)
```

This reduces the problem from O(millions of blocks) to O(sample_intervals × transfers × log_2(interval_width)) — roughly 50–200 RPC calls per wallet instead of millions. It misses transfers that happened between two sample points where balance later *decreased* (which can't happen for shadow wallets, since their balance is monotonically increasing), and it misses transfers that are smaller than the 0.001 TAO tolerance used in the binary search — but for large accumulation events both of these edge cases are negligible.

**The alternative: an off-chain indexer.** The ideal solution is an indexed event store. The `taoapp` tool in this workspace provides a ClickHouse-backed API: `GET /api/beta/accounting/events?coldkey=<ss58>` returns the full event history for any address in milliseconds. This would make the binary search approach unnecessary. However, `taoapp` is not always running and its coverage depends on when it was last synced. The archive node binary search approach is fully reproducible from the public chain with no additional infrastructure.

###  Known Entities at First-Funded Blocks

`trace_known_to_shadow.py` runs a targeted check: for each shadow wallet's first-funded block, fetch all `Balances.Transfer` events at that block and flag any sender that appears in `known_holders.json`.

Complete output (`known_to_shadow_report.txt`):

```
========================================================================
KNOWN-ENTITY → SHADOW WALLET TRANSFER SCAN
========================================================================

Wallet: 5FEA1FfUPwT3K4zTsYbQx5X1G9R2ZjYLyFv12xBQxW9QgoCL
  First-funded block: 5,946,516
  All senders at that block: 2
    FROM 5EiXej3AwjKqb9mjQAf29JG5HJf9Dwtt8CjvDqA8biprWTiN  923.4418 TAO
    FROM 5EiXej3AwjKqb9mjQAf29JG5HJf9Dwtt8CjvDqA8biprWTiN  692.4152 TAO

Wallet: 5ChHTBkaE1VgK5NX59uHuZoK8VQShojKBB1sGfXaZQpxVDCi
  First-funded block: 6,084,503
    FROM 5DunDrFV6BPbzsgLZUtMQtCq7w9fcUEbM59BUwx5E7N9Bn5E  196.3578 TAO

Wallet: 5Dhf6WgqrfhVyFCGqK4G5utro2jepscwryMhLHtpMfopxweC
  First-funded block: 6,581,276
    FROM 5EiXej3AwjKqb9mjQAf29JG5HJf9Dwtt8CjvDqA8biprWTiN  256.5047 TAO

Wallet: 5GUkyA37dHnc1rEijDtvBe5yYNCpaNjaHGqB7DY9Kb2KgSj3
  First-funded block: 6,659,270
    FROM 5FV99mBYw3tYrMTXXe52PDa69an1AE19aTrpnB4kzxW73yUj  247.8207 TAO

Wallet: 5C9CxW9355u1sqy6Np85FfGssJAdyA8cAsjjV9YP8aaLvjEY
  First-funded block: 6,784,524
    FROM 5EiXej3AwjKqb9mjQAf29JG5HJf9Dwtt8CjvDqA8biprWTiN  632.9372 TAO

Wallet: 5Epz8SQ69FuZRLyjCAicn8i71SdyEYaWR5rZ5a1i1bgoxGaQ
  First-funded block: 7,061,941
    FROM 5DunDrFV6BPbzsgLZUtMQtCq7w9fcUEbM59BUwx5E7N9Bn5E  1,026.4809 TAO

Wallet: 5GVKorR78gqQCV6mrWMWX95hHG93ZaRAUShZVBNT768dvqv8
  First-funded block: 7,066,018
  All senders at that block: 9
    FROM 5DunDrFV6BPbzsgLZUtMQtCq7w9fcUEbM59BUwx5E7N9Bn5E  996.5170 TAO (×9)

Wallet: 5HAe1pePzBuPqsF6BpTGN8vCngvKKJaRZ2HkHwFmJgWgAzcf
  First-funded block: 7,563,740
    FROM 5GBnPzvPghS8AuCoo6bfnK7JUFHuyUhWSFD4woBNsKnPiEUi  849.9997 TAO

Wallet: 5DwksfKHHG5rURh9jpGaq87m5k3Jn8BJbY9geeX7zTGQD8Pr
  First-funded block: 5,217,006
    FROM 5DaH7esryhVaKThgrT2d4BhNdkqoomK2m5Gpkr52nUmYm72n  0.2200 TAO

Wallet: 5CXHJRRk5WAQ8hTkzRDEK89pbsZD2e4Lu7KBTFrHcUQ6GZvz
  First-funded block: 3,766,862
    FROM 5FqBL928choLPmeFz5UVAvonBD5k7K2mZSXVC9RkFzLxoy2s  0.0250 TAO

RESULT: No known entity (validator/SN owner/identity-registered) appears
as a first-deposit sender for any of the top 10 shadow wallets.
```

**Interpretation.** None of the 2,369 known entities (validators, subnet owners, identity-registered coldkeys) made a first deposit to any shadow wallet. The first-deposit senders are all unregistered addresses — consistent with the shadow wallets being funded by private parties who have deliberately maintained no on-chain identity. This does not rule out known entities appearing in *subsequent* transfers, which is what `all_inbound_transfers.py` investigates.



## Patterns and What They Suggest

With sender attribution now in hand, the pattern picture is much clearer.

**Two funders, six wallets.** `5EiXej3...` made the first deposits into wallets 1, 3, and 5. `5DunDrF...` made the first deposits into wallets 2, 6, and 7. These are the two dominant players in the shadow whale ecosystem's creation — at least at the founding-deposit level. The four remaining wallets each have a distinct first-deposit sender.

**Wallet 7's first deposit was 9 mechanical tranches.** `5DunDrF...` sent exactly 9 transfers of 996.517 TAO each — 8,968.65 TAO total — into wallet 7 in the same block (7,066,018). Nine transfers of identical amounts in a single block is automated behavior, not a human clicking "send." This is a script methodically batching a large position into a cold address.

**Wallets 6 and 7 were funded fourteen hours apart.** `5Epz8SQ6...` (wallet 6, first deposit at block 7,061,941) and `5GVKorR7...` (wallet 7, first deposit at block 7,066,018) are 4,077 blocks apart — roughly 14 hours — and share the same initial funder. This is confirmed, not inferred.

**The rank-#4 wallet seeded wallet #10.** `5FqBL928...` — the extremely active free-balance holder at position #4 in our ranking, with nonce 181,845 — sent 0.025 TAO to `5CXHJRRk...` at block 3,766,862. The 0.025 TAO amount is consistent with a wallet "dusting" — sending a tiny amount to activate or label a cold address. Wallet #10 subsequently received 9,800 TAO and has been static since block 4M. The connection between the most active address in the top 10 and one of the shadow wallets is notable.

**Wallets 2, 3, and 4 grew at similar rates.** Between block 7M and the analysis date (~103 days):
- `5ChHTBka...`: +44,632 TAO
- `5Dhf6Wgq...`: +46,988 TAO
- `5GUkyA37...`: +43,125 TAO

Similar growth rates over the same period suggest similar inbound transfer schedules — possibly from shared source addresses, or addresses owned by the same entity.

**The 12,003 TAO cluster.** Four wallets at identical balances. One entity, four addresses. This is the clearest evidence of deliberate multi-wallet strategy in the dataset.

**Wallet #10 is different.** `5CXHJRRk...` received 9,800 TAO before dTAO (block ~3.8M) and has not been touched since. Eighteen months of total inactivity on a round-number position is consistent with genuine cold storage: a one-time transfer, a secured key, indefinite hold. This is the profile of a cold storage wallet that belongs in the discussion but isn't part of the active-accumulation phenomenon.

**The cold storage interpretation.** Nonce = 0 is architecturally consistent with intentional cold storage — a key generated offline, funded once, and held. This is legitimate practice. For static wallets like #10, it is probably the right explanation. For the nine actively growing wallets, it strains: cold storage addresses are funded once and left alone. Sending ongoing transfers to the same nonce-0 address over months is unusual — it reduces anonymity (the address is known) without providing the operational utility of an active wallet. The more natural explanation for ongoing accumulation into nonce-0 addresses is that these are receive-only addresses held by an entity that has no need to sign outgoing transactions from them: a custodian, a long-term accumulator, or someone building a position they don't intend to deploy soon.



## Childkey Investigation

Bittensor supports [childkey delegation](https://docs.learnbittensor.org/validators/child-hotkeys) — a hotkey can designate child hotkeys that inherit some of its network permissions. `check_childkeys.py` checked whether any shadow whale addresses appear as parent or child in the childkey registry:

```python
# check_childkeys.py
for parent_hk, children in sub.substrate.query_map("SubtensorModule", "ChildKeys"):
    for child_hk, proportion in children:
        # check if any shadow address appears as parent or child
```

**Result: zero matches.** None of the top shadow wallet addresses appear in any childkey relationship. This result is largely expected — childkey maps store hotkey-to-hotkey relationships, and shadow wallets are coldkeys; the two registries don't intersect by design. The check would only surface an anomaly if someone had reused the same address as both a hotkey and a coldkey, which would itself be a notable finding. No such overlap exists here.



## Funder Address Investigation

`investigate_funder.py` profiles the two dominant shadow wallet funders using only the archive node: current balance and nonce, balance history at 14 sample points, inbound attribution (who funded them via binary search), and all transfers from them at the known shadow-funding blocks.

### Funder-A: `5EiXej3AwjKqb9mjQAf29JG5HJf9Dwtt8CjvDqA8biprWTiN`

From `funder_investigation_report.txt` (in progress — partial findings recorded here):

**Current state:** 242.51 TAO remaining, **nonce 23,452**.

Nonce 23,452 is the most important single data point. This address has signed over 23,000 transactions. That is not a human wallet — it is an automated system. Combined with the fact that it has been nearly completely depleted (down from a peak balance to 242 TAO), the behavioral profile is clear: **Funder-A is a hot wallet used to programmatically distribute TAO**, not to hold it.

**Not a registered entity.** `5EiXej3...` does not appear in `known_holders.json` — it is not a validator, not a subnet owner, and has no on-chain identity registered. It is not tao.bot's coldkey (`5GsbTgfv...`) or hotkey (`5E2LP6En...`), ruling out the most obvious high-activity candidate.

**Balance history:** zero through block 4,000,000. First activity in the 4M–5M interval, with tiny dust deposits (0.02–0.3 TAO) from several addresses activating the wallet before serious accumulation:

```
Block 4,813,834: received 0.0211 TAO from 5FXw2v9BH1wMCoP4vws27FWMqLGXFK647NwGGRaMHVeSnzKE
Block 4,844,283: received 0.0221 TAO from 5FXw2v9BH1wMCoP4vws27FWMqLGXFK647NwGGRaMHVeSnzKE
Block 4,844,293: received 0.0143 TAO from 5F2BLayFnkn9bPUwZju1UQHqaZY8qqWQBRhuRhtU4Vu6yK2m
Block 4,877,017: received 0.1984 TAO from 5HmzvWPJi2qjqA3guPN8aimUpD9eME6aqzXtpPah9N7AwUia
Block 4,962,438: received 0.2969 TAO from 5HUPxAsF52CX7RWAe3vDA7Wu7fiKT78dG3XpxRisfnwKYsn4
```

None of these dust-senders appear in `known_holders.json`. The dust-activation pattern (tiny amounts from multiple addresses before a wallet begins operating) is consistent with automated wallet provisioning infrastructure — someone initializing a new hot wallet in a managed system.

**Funder-A is a pass-through distribution wallet, not a holder.** Live transaction data (from a block explorer, verified against block numbers matching our archive queries) confirms the pattern: Funder-A receives periodic refills from upstream addresses, then immediately dispatches to shadow wallets and other destinations. As of block ~7,761,000 it holds ~158 TAO — nearly depleted — but is being continuously refilled:

```
Block 7,760,936: received  99.9997 TAO from 5HUPxAs...
Block 7,760,936: received  64.3000 TAO from 5HB2Q8...
Block 7,760,936: received   5.0000 TAO from 5GMsaZ...
Block 7,760,875: received   8.9997 TAO from 5DMAbJ...
```

**`5HUPxAs...` is a confirmed long-term upstream funder.** This address sent Funder-A a 0.2969 TAO dust activation at block 4,962,438 (pre-dTAO, ~early 2025) and is still sending it large amounts today. The same address, the same relationship, spanning over a year. `5HUPxAs...` is almost certainly part of the same operational entity as Funder-A — a feeder wallet in the same infrastructure.

Funder-A's behavioral profile:
- Receives batches of TAO from upstream sources (`5HUPxAs...`, `5HB2Q8...`, `5GMsaZ...`, `5DMAbJ...`, and others)
- Immediately dispatches to many destination addresses — including shadow wallets and numerous other addresses not yet identified
- Maintains near-zero balance between refills (consistent with an automated treasury/distribution system)
- Has been operating continuously since block ~4.96M (pre-dTAO) through at least block 7,761,000

**The upstream feeder `5HUPxAs...` is itself fully depleted.**

`5HUPxAsF52CX7RWAe3vDA7Wu7fiKT78dG3XpxRisfnwKYsn4` — the address that dust-activated Funder-A at block 4,962,438 and is still sending it TAO today — has a current free balance of **0.000018 TAO** and a nonce of **689**. It is not in `known_holders.json`. It is not a delegate or subnet owner. Like Funder-A, it has been fully deployed. The pattern: `5HUPxAs...` received TAO from somewhere upstream, forwarded it to Funder-A (and possibly others), and is now empty. Nonce 689 with full depletion suggests a purposeful, finite deployment — not an ongoing operational wallet.

**`investigate_funder.py` results — who funded Funder-A with large amounts:**

The archive-node binary search across all balance intervals is now complete. The dominant upstream funders of Funder-A are:

```
Block 5,629,888:   734.9999 TAO  from 5HB2Q8H9Rvxr3ejZ1o58FfXk3S3jMij6mB7Vu7b7SPqUdhTQ
Block 5,860,339: 1,373.9999 TAO  from 5HB2Q8H9Rvxr3ejZ1o58FfXk3S3jMij6mB7Vu7b7SPqUdhTQ
Block 7,196,237:    78.0022 TAO  from 5ESDyJBqh3SRcmboQpHc3761pZqV5C9vrFPFy8qxtAzerktB
Block 7,336,427:   471.7707 TAO  from 5GYLRjVVUz3GzcXWjrgYRp4FLaVBb2y5McUfkQNAKqT9d82a
```

Plus earlier smaller refills in the 4M–5M interval from ~10 addresses (mostly under 25 TAO each).

**`5HB2Q8H9...` is the single dominant upstream funder of Funder-A**, providing at least 2,109 TAO across two large transfers in the 5M–6M block range. That is far above any other single source in our data. `5HB2Q8H9...` does not appear in `known_holders.json` — it is not a registered validator, SN owner, or identity-registered address.

Querying its current state:

```
5HB2Q8H9Rvxr3ejZ1o58FfXk3S3jMij6mB7Vu7b7SPqUdhTQ: balance=0.0000 TAO  nonce=2,293
```

The same pattern — **fully depleted, high nonce, anonymous**. Nonce 2,293 means this wallet signed 2,293 transactions. It is not `5HUPxAs...` (nonce 689), not Funder-A (nonce 23,452) — it is a distinct node in the same infrastructure, now completely empty. It received a large amount of TAO, forwarded most of it to Funder-A and likely other addresses, and is now dry. The layer structure is:

```
[Unknown upstream source]
       ↓
  5HB2Q8H9... (nonce 2,293, balance 0.00)  ← dominant funder of Funder-A
  5HUPxAs...  (nonce   689, balance 0.00)  ← long-term feeder of Funder-A
       ↓
  Funder-A: 5EiXej3... (nonce 23,452, balance ~158 TAO)
       ↓
  Shadow wallets (nonce 0, large free balances)
```

This is a **multi-layer automated treasury system**. Every layer is anonymous, every feeder is depleted or near-depleted, and each layer has progressively higher nonce counts. The entity at the top of this chain — the source of `5HB2Q8H9...`'s 2,109+ TAO — is the critical unknown. Tracing it requires either the tao.app API or further archive node work.

### Funder-A's ongoing funding of shadow wallet #1

`all_inbound_transfers.py` reveals that Funder-A did not just make the *first* deposit into shadow wallet #1 — it has been sending large, frequent transfers continuously (partial results, still running):

```
Block 6,018,759: 161.81 TAO from Funder-A
Block 6,018,759: 696.46 TAO from Funder-A
Block 6,018,772: 696.46 TAO from Funder-A
Block 6,018,939: 657.13 TAO from Funder-A
Block 6,020,975: 210.83 TAO from Funder-A
Block 6,021,335: 145.19 TAO from Funder-A
Block 6,021,774: 702.45 TAO from Funder-A
Block 6,028,540: 385.64 TAO from Funder-A
Block 6,036,787: 262.42 TAO from Funder-A
Block 6,039,088: 151.17 TAO from Funder-A
Block 6,039,088: 711.39 TAO from Funder-A
Block 6,040,993: 153.25 TAO from Funder-A
Block 6,041,026: 142.42 TAO from 5FV99mBYw3tYrMTXXe52PDa69an1AE19aTrpnB4kzxW73yUj  ← different sender
Block 6,041,053: 771.86 TAO from Funder-A
Block 6,041,192: 379.33 TAO from Funder-A
```

Two things stand out. First: the transfer pattern is automated — amounts vary, blocks are close together, the pace is consistent with a script dripping TAO into a cold address. Second: **`5FV99mBYw3tYrMTXXe52PDa69an1AE19aTrpnB4kzxW73yUj` appears at block 6,041,026 sending 142 TAO to shadow wallet #1** — the same address that made the *first* deposit into shadow wallet #4. The same sender appearing in the ongoing inbound history of a different shadow wallet, sending amounts comparable to Funder-A's transfers, strongly suggests these are coordinated. `5FV99mB...` is either the same operator as Funder-A or part of the same funding infrastructure.

Full results pending completion of `all_inbound_transfers.py`.

### Funder-B: `5DunDrFV6BPbzsgLZUtMQtCq7w9fcUEbM59BUwx5E7N9Bn5E`

From `funder_investigation_report.txt`:

**Current state:** 115.17 TAO remaining, **nonce 23,089**.

Nonce 23,089 is indistinguishable from Funder-A's 23,452 in behavioral terms: both are automated high-throughput pass-through wallets. Funder-B is not in `known_holders.json`.

**Balance history:**

```
Block 5,000,000:     67.46 TAO
Block 6,000,000:    126.43 TAO
Block 7,000,000:    169.30 TAO
Block 7,761,208:    115.17 TAO
```

The same pattern as Funder-A: receives TAO, dispatches it, maintains a small working balance. The 7M→current decrease confirms it is depleting its balance into shadow wallets.

**Funder-B's upstream funders:**

```
Block 4,963,873: received 877.3709 TAO from 5DfKewdxchFx7umvw6qcHKXKgvVxEtMFXFXVaXShjf7anzet
Block 5,250,203: received  57.3696 TAO from 5DC8Uq5wy1M4m9XRJaEFFt2PtV8zdKUUVQemEe5whZ2bguq6
Block 5,783,692: received  97.0052 TAO from 5ESDyJBqh3SRcmboQpHc3761pZqV5C9vrFPFy8qxtAzerktB
Block 6,135,677: received  95.7881 TAO from 5Gorfuxev7QmgDzBK92YrVW2K5PEvfZRW49SQrKm3VXcAGi1
```

Plus dust activations from `5FXw2v9B...` (blocks 4,869,772 and 4,905,153), `5CZyR91W...` (0.0019 TAO), `5HUPxAs...` (0.0887 TAO), and others.

**`5DfKewdx...` is Funder-B's dominant upstream funder** — 877 TAO in a single transfer at block 4,963,873. It first sent a 0.0890 TAO dust activation just 70 blocks earlier (4,963,788), then sent 877 TAO. The same dust-then-fund pattern. `5DfKewdx...` is not in `known_holders.json`.

### Shared-operator evidence: Funder-A and Funder-B are the same entity

`investigate_funder.py` reveals that the same addresses appear in the activation and funding history of **both** funders:

| Address | Funder-A | Funder-B |
|---|---|---|
| `5FXw2v9B...` | Dust activation blocks 4,813,834 + 4,844,283 | Dust activation blocks 4,869,772 + 4,905,153 |
| `5HUPxAs...` | Dust activation block 4,962,438 (0.297 TAO) | Dust activation block 4,962,353 (0.089 TAO) — **85 blocks earlier** |
| `5ESDyJBq...` | 78.00 TAO at block 7,196,237 | 97.01 TAO at block 5,783,692 |
| `5EQjSevJ...` | 3.70 TAO at block 4,964,113 | 0.977 TAO at block 4,962,718 |

`5HUPxAs...` dust-activated Funder-A at block 4,962,438 and Funder-B at block 4,962,353. **Those are 85 blocks apart — roughly 17 minutes.** The same address, activating two separate funder wallets in the same ~20 minute window, with the same small amounts. This is not coincidence. The entity controlling `5HUPxAs...` owns both Funder-A and Funder-B.

Combined with the evidence that both funders send to the same shadow wallets in overlapping time windows (block 6,054,831: both send to shadow wallet #1), the picture is unambiguous: **a single entity operates Funder-A, Funder-B, `5FV99mB...`, and at minimum 7 of the top 10 shadow wallets.**



## Who Is Behind the Shadow Wallets? Hypotheses

The evidence assembled so far establishes a layered, automated funding infrastructure operating since pre-dTAO, with no registered identity at any level. What it does not establish is who controls it. This section frames the candidate hypotheses honestly and identifies what evidence would move us toward or away from each.

### What the evidence does support

A single operator — or tightly coordinated group — almost certainly controls the core infrastructure. The signals:

- `5HUPxAs...` dust-activated **both** Funder-A (block 4,962,438) and Funder-B (block 4,962,353) — 85 blocks apart. The same address, activating two separate funder wallets in ~17 minutes. One operator controls both funders.
- `5FXw2v9B...`, `5ESDyJBq...`, and `5EQjSevJ...` all appear in the funding history of both Funder-A and Funder-B. Multiple shared upstream sources, not one coincidence.
- `5FV99mB...` appears as first-depositor for shadow wallet #4 *and* as an ongoing sender to shadow wallet #1 — connecting what initially appeared to be separate funders
- Funder-A (nonce 23,452) and Funder-B (nonce 23,089) have nearly identical activity levels — approximately equal transaction counts, operating since the same pre-dTAO period, currently holding similar small balances while depleting
- The entire infrastructure has zero registered identity at every level (shadow wallets, funders, feeders) — a consistent operational posture, not random omission
- All top shadow wallets (except the pre-dTAO outlier #10) appeared after block 4M — a coordinated entry around dTAO launch

### Candidate hypotheses

**1. Exchange custody or large institutional holder**

Some validators operating large-scale infrastructure on the Bittensor network have professional custody operations and a pattern of separating cold storage from validator operations. An exchange or institutional holder managing ~850k TAO in cold storage would naturally use automated, identity-free wallets — exactly what we observe. The timing is consistent: all top shadow wallets post-date block 4M, around the dTAO transition, when the economics of holding TAO changed significantly.

What would support it:
- A chain-of-custody link from `5HUPxAs...` or another feeder wallet back to any known exchange or institutional custody address
- The total shadow wallet TAO (~850k in the top 10 alone) is plausible as a large exchange cold reserve
- The receive-only (nonce-0) posture is consistent with dedicated cold storage

What would weigh against it:
- Exchanges typically hold custody in wallets that can sign (for withdrawals); nonce-0 receive-only wallets are harder to operate for an exchange — unless these are specifically designed as long-term cold storage
- If `5HUPxAs...`'s upstream source is a retail OTC desk rather than an exchange withdrawal, it points more toward hypothesis 3

**2. Founders / early team accumulation**

The Bittensor founders (Const, Ala Shaabana, and other early participants) received token allocations and have been building since genesis. This would be an entirely unremarkable explanation: a small team with a multi-year vision managing large positions across layered cold storage is standard operational security, not malfeasance. Post-dTAO, the emission structure changed significantly, creating real incentives to restructure holdings — consolidating into clean receive-only addresses while staked positions live elsewhere is exactly how a sophisticated long-term holder would behave. If the shadow whale infrastructure turns out to be founder treasury management, that closes the investigation, not opens a new one.

What would support it:
- A link from any feeder wallet to OTF addresses or Const's known keys
- Total shadow wallet TAO proportionate to known founder allocations
- The pre-dTAO dust activations being traceable to addresses in the early block history of the chain

What would weigh against it:
- No direct on-chain connection to any known founder address found so far
- The scale (~1M+ TAO) is large even for combined founder holdings
- Const's on-chain profile (see [Const: Ecosystem Profile](./const-profile.md)) is structurally opposite to the shadow whale pattern — his wealth is stake-dominant, his addresses have nonce > 0, and he has registered identity — so if founders are involved, it is through addresses not yet attributed to them

**3. Institutional investor / OTC buyer**

A hedge fund, VC, or high-net-worth individual entering Bittensor via OTC at or around dTAO launch, receiving TAO directly into managed cold storage infrastructure. The professional layering (feeder wallets → distribution wallets → cold addresses), automated dispatch, and deliberate identity avoidance is consistent with an institutional party that values privacy and has the tooling to implement it.

What would support it:
- `5HUPxAs...`'s upstream source being an OTC desk or known broker address
- The entry timing matching a known institutional TAO purchase event

What would weigh against it:
- Institutional OTC buyers typically receive in one large transfer; the gradual, batched accumulation over months looks more like ongoing programmatic buying than a one-time settlement
- The pre-dTAO activation (block ~4.96M) suggests this infrastructure was being set up *before* dTAO launched, which implies the operator already had conviction about Bittensor's direction — more consistent with insiders than outside investors

**4. Bittensor protocol / OTF secondary treasury**

OTF holds treasury TAO and has operational needs for managing ecosystem grants, subnet funding, and development resources. A secondary cold treasury, deliberately kept unattributed for operational security reasons, would explain the scale and posture.

What would support it:
- `5HUPxAs...` linking back to any OTF-adjacent address
- The shadow wallets never deploying (consistent with a reserve, not an operational float)

What would weigh against it:
- OTF's known address (`5HBtpwxu...`) holds only 23 TAO free and 413k in stake — a second large treasury of 850k+ TAO would represent a very substantial undisclosed OTF reserve

### Updated Infrastructure Map: The Cross-Funder Network

`taoapp_investigation.py` (block ~7,767,000) reveals that Funder-A and Funder-B share **six upstream addresses** in their respective top-10 sender lists:

| Sender | → Funder-A (TAO) | → Funder-B (TAO) | Notes |
|---|---|---|---|
| `5HB2Q8H9...` | 69,328 (#1) | 14,754 (#2) | Previously identified as HB2Q8 hub |
| `5Gorfuxev7...` | 21,942 (#3) | 17,047 (#1) | **NEW — dominant cross-funder hub** |
| `5FJMfoeUXsDXQSABaai8CUQvMyAK1a7jXqJvkBMnabfuJCjv` | 10,548 (#6) | 8,578 (#3) | NEW |
| `5HUPxAs...` | 9,920 (#7) | 8,437 (#4) | Dust activator; now sending large amounts |
| `5EJMGn13311deMfe9pwZYd5bPkyMGs1ZmkmNtbpbv7wPcG9C` | 55,672 (#2) | 7,530 (#5) | Sends AND receives large amounts from Funder-A — round-trip pattern |
| `5ESDyJBqh3SRcmboQpHc3761pZqV5C9vrFPFy8qxtAzerktB` | 8,786 (#9) | 2,060 (#7) | Appeared in both funder histories |

Six of the ten top-senders are shared between both funders. This is not a coincidence — it is a coordinated upstream feeding network, likely all operated by the same entity as the funders themselves. Each of these addresses deserves its own event-history query for further upstream tracing.

**`5EJMGn13...` is notable**: it is the #2 sender *to* Funder-A (55,672 TAO in) AND also the #1 receiver *from* Funder-A (42,598 TAO out). It is simultaneously feeding the distribution system and receiving from it. This could indicate a recycling/laundering pattern — TAO flowing in a loop through multiple addresses — or it could be the operator's consolidation account that both funds the system and collects processing fees. Either way, it is a high-priority address for deeper investigation.

**The scale is larger than previously estimated.** The 738k TAO currently in the top-10 shadow wallets represents the *accumulated balance* as of the analysis date. The tao.app API reveals that Funder-A alone processed **282,914 TAO** in the most recent 20,000 events (covering roughly the last several weeks of activity), and Funder-B processed **83,046 TAO** in its most recent 20,000 events. The total throughput of this operation far exceeds the current shadow wallet balances — much of the TAO in transit has been distributed to addresses beyond the top-10.

**The operation is active right now.** Funder-B sent to shadow wallets as recently as blocks 7.73–7.75M (blocks before the analysis date). This is not a historical archive of past cold-storage loading — it is an active, ongoing accumulation program.

### Feeder Profile Investigation: The Recycling Layer and GBnPzv

`profile_new_feeders.py` (March 17, block ~7,767,000) traced the five high-value senders to Funder-A identified in the BFS log. The results fundamentally revised the picture of what these "upstream senders" are.

**EJMGn13, HnhgYXb, and EfXUFMj are not upstream sources — they are internal recyclers.** All three show the same top senders AND receivers: Funder-A, Funder-B, and `5FV99mBYw3tYrMTXXe52PDa69an1AE19aTrpnB4kzxW73yUj`. TAO is flowing in a closed loop within the infrastructure. More tellingly: all three activated on the **same block, 6,421,401** — automated provisioning of three wallets simultaneously by the same operator. `FV99mB` (`5FV99mBYw3tYrMTXXe52PDa69an1AE19aTrpnB4kzxW73yUj`) is the central recycling hub, with hundreds of thousands of TAO cycling through it and back. This appears to be deliberate obfuscation: TAO bouncing between infrastructure addresses to make the chain of custody harder to trace linearly.

**`5GBnPzv...` is confirmed as the dominant source for both Gorfuxev7 and FJMfoeUX:**

| Address | TAO from GBnPzv | % of inbound |
|---|---|---|
| Gorfuxev7 (`5Gorfuxev7...`) | 70,803 TAO | ~91% |
| FJMfoeUX (`5FJMfoeUXs...`) | 57,034 TAO | ~70% |

GBnPzv feeds these two addresses, which then feed Funder-A, Funder-B, and FV99mB. GBnPzv is also the direct first funder of shadow wallet #8. It is the most strategically central address in the infrastructure: touching four different layers simultaneously.

**tao.bot's funders appear in the shadow infrastructure:**

`5FJMfoeUXs...`'s top senders include:
- `5E2b2DcMd5W8MBhzTCFt63t2ZEN8RsRgL7oDd7BFYL9aMQux` — tao.bot's seed funder (6,036 TAO to FJMfoeUX)
- `5FqqXKb9...` — tao.bot's recent funder (2,363 TAO to FJMfoeUX)
- `5FqBL928...` — rank #4 free-balance holder, nonce 181,845, previously seeded shadow wallet #10 (4,465 TAO to FJMfoeUX)

The addresses funding tao.bot's coldkey are also funding the shadow whale distribution machinery through FJMfoeUX. This is the shared intermediary signal: the same addresses that bootstrapped tao.bot also contributed to the shadow whale supply chain — but both connected through FJMfoeUX, not directly. Whether this reflects a single entity operating both tao.bot and the shadow infrastructure, or two unrelated parties using the same aggregation service, cannot be determined from these on-chain flows alone. The critical open question — what else did `5E2b2DcMd5W8...` fund, and where did it receive its TAO from — is addressed in `taobot-profile.md`.

The updated infrastructure map:

```
[Unknown ultimate source]
         ↓
  5GBnPzv... (direct SW#8 funder; also feeds Gorfuxev7 and FJMfoeUX)
         ↓
  5Gorfuxev7...  5FJMfoeUXs...  (feeders of Funder-A/B/FV99mB)
                 ↑ also receives from 5E2b2DcM... and 5FqqXKb9... (tao.bot funders)
         ↓
  [Recycling layer: FV99mB, EJMGn13, HnhgYXb, EfXUFMj — internal circulation]
         ↓
  Funder-A (5EiXej3..., nonce 23,452) + Funder-B (5DunDrF..., nonce 23,089)
         ↓
  Shadow wallets SW1–SW10 (nonce 0, ~738k TAO free balance)
```

### Address Cross-Reference: Who Is (and Isn't) Registered

`crosscheck_addresses.py` cross-referenced every known shadow whale and infrastructure address against `known_holders.json` (2,369 validators, SN owners, and identity-registered coldkeys) and the top-100 free-balance rankings. The full output is in `crosscheck_report.txt`. Summary of findings:

**Shadow wallets in the top-100 free-balance ranking:**

| Shadow wallet | Rank | Free balance |
|---|---|---|
| SW1 (`5FEA1FfU...`) | #2 | 141,003 TAO |
| SW2 (`5ChHTBka...`) | #3 | 129,499 TAO |
| SW3 (`5Dhf6Wgq...`) | #5 | 117,065 TAO |
| SW4 (`5GUkyA37...`) | #6 | 108,064 TAO |
| SW5 (`5C9CxW93...`) | #8 | 93,908 TAO |
| SW6 (`5Epz8SQ6...`) | #9 | 90,843 TAO |
| SW7 (`5GVKorR7...`) | #13 | 56,342 TAO |
| SW8 (`5HAe1peP...`) | #29 | 17,850 TAO |

All eight are in the top 30 by free balance. None appear in `known_holders.json` — zero are validators, subnet owners, or identity-registered.

**Infrastructure addresses in the top-100:**

| Address | Role | Rank | Free balance |
|---|---|---|---|
| `5GBnPzv...` | GBnPzv (dominant upstream source) | #18 | 23,696 TAO |
| `5FqBL928...` | FqBL928 (active trader, shadow-adjacent) | #4 | 122,232 TAO |
| `5EfXUFMj...` | EfXUFMj (recycler) | #46 | 7,901 TAO |
| `5EJMGn13...` | EJMGn13 (recycler) | #52 | 5,834 TAO |
| `5HbDZ6UL...` | HbDZ6UL (FJMfoeUX feeder) | #56 | 5,213 TAO |
| `5CNChyk2...` | CNChyk2 (FJMfoeUX feeder) | #75 | 2,507 TAO |
| `5DunDrF...` (Funder-B) | — | #93 | 1,809 TAO |

None appear in `known_holders.json`. The active infrastructure addresses (Funder-A, HB2Q8, FJMfoeUX, Gorfuxev7, FV99mB) do **not** appear in the top 100 by free balance — confirming their role as pass-through wallets that cycle and forward TAO rather than holding it.

**tao.bot addresses:**

| Address | Role | In known_holders | Top-100 rank |
|---|---|---|---|
| `5GsbTgfv...` | tao.bot coldkey | ✅ as validator ("tao.bot") | not in top 100 (2.24 TAO free) |
| `5E2LP6En...` | tao.bot hotkey | not present | not in top 100 |
| `5E2b2DcM...` | tao.bot seed funder | not present | not in top 100 |
| `5FqqXKb9...` | tao.bot recent funder | not present | **#34 (12,248 TAO)** |

**No direct address overlap** exists between the shadow cluster set and the tao.bot address set. The tao.bot recent funder at rank #34 is a significant free-balance holder that is not a validator, SN owner, or identity-registered entity.

**The `5FqBL928...` shadow-adjacent finding.** Rank #4 with 122,232 TAO free balance and nonce 181,845. This address first appeared as the dust-sender who activated shadow wallet #10 (block 3,766,862) and also appears in `profile_new_feeders_report.txt` as a sender to FJMfoeUX (4,465 TAO). An extremely active address (nonce 181,845 means over 181,000 on-chain transactions) with a 122k TAO free balance that is not registered anywhere — and connected to both the earliest shadow wallet in the dataset and the shadow infrastructure feeder network. It is likely an exchange hot wallet or an OTC platform.

### How to resolve it

The chain of custody now extends to at least four layers deep. The immediate critical data points are the upstream sources of **`5HB2Q8H9...`** (nonce 2,293, depleted) — the dominant funder of Funder-A with 2,109+ TAO. `5HUPxAs...` (nonce 689, depleted) is the secondary feeder and is also worth tracing. If either of those upstream histories shows:

- Exchange or institutional custody addresses → supports hypothesis 1
- OTF or founder-adjacent addresses → supports hypotheses 2 or 4
- Another layer of anonymous wallets → the structure goes deeper still

Specifically: `5HB2Q8H9...` received two large round-number amounts (734.9999 and 1,373.9999 TAO). Round numbers strongly suggest these were deliberate, human-authorized transfers rather than automated micro-dispatch. That origin block could be especially revealing.

With the tao.app API now complete (`taoapp_investigation.py`), the full event history of the visible infrastructure is mapped. Six cross-funder addresses are confirmed; their upstream origins are the next layer to resolve. See the Updated Infrastructure Map section above for details.

---

## Open Research Questions

**1. [RESOLVED] Who made the first deposits?** `find_first_transfer.py` identified the first-deposit sender for all 10 wallets. Two addresses (`5EiXej3...` and `5DunDrF...`) account for 6 of 10 first deposits. Full attribution is in `first_transfers.json`.

**2. [RESOLVED] What are the two dominant sender addresses?** Both are automated pass-through wallets. Funder-A (`5EiXej3...`, nonce 23,452) dominant upstream: `5HB2Q8H9...` (2,109 TAO). Funder-B (`5DunDrF...`, nonce 23,089) dominant upstream: `5DfKewdx...` (877 TAO). Neither is a registered validator or SN owner.

**3. [RESOLVED] Does a single entity control both `5EiXej3` and `5DunDrF`?** Yes. `5HUPxAs...` dust-activated both within 85 blocks. `5FXw2v9B...`, `5ESDyJBq...`, and `5EQjSevJ...` all appear in the funding history of both. Multiple shared upstream sources. Funder-A and Funder-B are the same operator.

**4. [RESOLVED] Where does the ongoing TAO come from?** `taoapp_investigation.py` completed with the tao.app API. The operation is **ongoing and very recent**. Funder-A sent to shadow wallets SW1–SW7 starting at block ~7.14M; Funder-B sent to SW1–SW7 starting at block ~7.56M (current block ~7.77M). This is not archival cold-storage funding — the shadow wallets are being actively loaded right now. Funder-A processed **282,914 TAO** in the most recent 20,000 events alone, and Funder-B processed **83,046 TAO**. The shadow wallets are not near their final state; they appear to be mid-accumulation. Six addresses appear in the top-10 sender lists of **both** Funder-A and Funder-B simultaneously, forming a coordinated upstream feeding network.

**5. What is `5FqBL928...`?** This wallet (rank #4 by free balance, nonce 181,845) seeded the pre-dTAO shadow wallet `5CXHJRRk...` with 0.025 TAO at block 3.8M. With nonce ~182k it is one of the most active addresses on the chain. Its identity is unknown — it does not appear in `known_holders_report.txt`. What is it?

**6. [RESOLVED] Are 5FqBL928... and 5H9brHhM... shadow wallets? No.** Nonce 181,845 and 111 respectively. Neither qualifies. See `nonce_check.json`.

**7. Correlation with protocol events.** Does the appearance of new shadow wallets (July 2025, October 2025, December 2025, February 2026) correlate with specific network events — subnet launches, price movements, governance milestones?

**8. [RESOLVED — see section below] Who are the upstream funders of Funder-A and Funder-B?** `taoapp_investigation.py` is complete. The API confirms `5HB2Q8H9...` is the #1 sender to Funder-A (69,328 TAO in recent events) and #2 to Funder-B (14,754 TAO). `5Gorfuxev7...` is #3 to Funder-A (21,942 TAO) and #1 to Funder-B (17,047 TAO) — a new cross-funder hub address. Five additional addresses appear in the top-10 sender lists of both funders. The full cross-funder network analysis is in the Updated Infrastructure Map section.

**9. [RESOLVED — negative] Is Const connected to the shadow whale infrastructure?** `const_attribution.py` completed a full binary-search scan across all balance-change blocks for both of Const's known keys (`5GH2aUTMRUh1RprCgH4x3tRyCaKeUi5BfmYCfs1NARA8R54n` and `5Fc3ZZQAYB3SPXKcFnd1WJeyQvArSZZeB6LU1rb7zvQ6XvDh`). Result: no direct transfers between the two keys, no transfers involving either key and any shadow whale address or known funder address at any balance-change block. Neither Const key has any on-chain connection to the shadow whale infrastructure. See `const_attribution_report.txt` and `const-profile.md` for the full profile.

**10. [REVISED — SUSPICIOUS PROXIMITY VIA SHARED INTERMEDIARY] Is tao.bot connected to the shadow whale infrastructure?** Initial `taoapp_investigation.py` found no direct transfers between tao.bot's addresses and shadow wallet addresses. `profile_new_feeders.py` (March 17) reveals a **shared intermediary signal**: the addresses that funded tao.bot's coldkey — `5E2b2DcMd5W8MBhzTCFt63t2ZEN8RsRgL7oDd7BFYL9aMQux` (6,036 TAO) and `5FqqXKb9...` (2,363 TAO) — both sent TAO to `5FJMfoeUXsDXQSABaai8CUQvMyAK1a7jXqJvkBMnabfuJCjv` (FJMfoeUX), a confirmed feeder of Funder-A, Funder-B, and FV99mB. **The evidence establishes suspicious proximity, not shared control.** The connection is: [tao.bot funder] → FJMfoeUX → Funder-A/B → Shadow wallets — two hops from shadow infrastructure, always through FJMfoeUX as an intermediary. FJMfoeUX received from at least 8 distinct senders (344 inbound transactions); if it operates as an aggregation service, tao.bot's funders' presence is not conclusive. The critical open question is whether `5E2b2DcMd5W8...` (tao.bot's seed funder) funded *only* tao.bot and shadow-adjacent infrastructure, or whether it funded unrelated parties as well — the former strengthens the shared-operator hypothesis, the latter weakens it. See `taobot-profile.md` for a detailed critical evaluation of this evidence.

---


## The tao.bot Signal: A False Lead and What It Teaches

This section documents a lead that emerged from the feeder profile investigation and briefly looked like the most significant finding of the entire inquiry. It did not survive scrutiny. The full sequence — signal, interpretation, resolution — is worth writing up because the reasoning pattern is common in chain analysis and the failure mode is instructive.

### The initial finding

When `profile_new_feeders.py` traced the top senders to FJMfoeUX — a confirmed shadow infrastructure feeder whose entire outbound flow goes to Funder-A, Funder-B, and FV99mB — two addresses in its sender list had also funded **tao.bot**, Bittensor's largest validator by stake-weight (855,736 TAO delegated, roughly 1.5× the next-largest). See `taobot-profile.md` for a full tao.bot profile.

| Address | Funded tao.bot's coldkey | Also sent to FJMfoeUX (shadow feeder) |
|---|---|---|
| `5E2b2DcMd5W8MBhzTCFt63t2ZEN8RsRgL7oDd7BFYL9aMQux` | 1,025 TAO at block ~4,850,000 (seed) | 6,036 TAO |
| `5FqqXKb9zonSNKbZhEuHYjCXnmPbX9tdzMCU2gx8gir8Z8a5` | 9.998 TAO at block 7,632,272 (top-up) | 2,363 TAO |

`FJMfoeUX` (`5FJMfoeUXsDXQSABaai8CUQvMyAK1a7jXqJvkBMnabfuJCjv`) is a confirmed shadow infrastructure feeder: its entire outbound flow goes to Funder-A, Funder-B, and FV99mB — the addresses that loaded the shadow wallets.

**There is no direct transfer between tao.bot and any shadow wallet.** The connection runs: [tao.bot funder] → FJMfoeUX → Funder-A/B → Shadow wallets. Two hops, always through FJMfoeUX.

### Why it seemed significant

If FJMfoeUX is a controlled node in the shadow whale infrastructure (not a neutral service), then every address that sent to it was knowingly participating in the operation. Under that reading, the entity that seeded tao.bot would be the same entity accumulating shadow TAO — a single operator controlling both the network's largest validator and the network's largest liquid TAO position.

If FJMfoeUX is a general aggregation service used by multiple parties, the two tao.bot funders may have simply used the same intermediary as unrelated shadow-adjacent parties. The co-presence in its sender list would then be coincidental.

The distinction hangs on what else FJMfoeUX's senders did with their money, and whether `5E2b2DcMd5W8...` funded anything beyond tao.bot and shadow infrastructure.

The stakes of the shared-operator reading were enormous. The shadow whale investigation established a single unknown operator controlling ~20% of liquid TAO. That by itself is notable but not immediately actionable — it is an unknown holder in cold storage. A confirmed tao.bot connection would change the character of the finding entirely: the same operator would also hold the largest validator stake on the network, giving them simultaneous influence over:

- **Liquid TAO** (~738k TAO in shadow wallets, deployable immediately with no on-chain warning)
- **Consensus weight** (~856k TAO stake, affecting Yuma Consensus rankings for every subnet)
- **Child-hotkey market power** (289 child hotkeys across 68 subnets — the ability to favour or defund subnet teams at will)

That combination — opaque liquid capital plus opaque consensus weight plus opaque operational leverage over subnet teams — would constitute a concentration of influence in the Bittensor ecosystem that has no parallel in any known entity.

**tao.bot is already unusual in the validator community.** Unlike every other major validator — Kraken, OTF, Taostats, Yuma/DCG, Crucible Labs, Polychain — tao.bot has no public presence, no known team, and does not participate in validator community discussions. It is not personally known to other validators. That community isolation is not evidence of wrongdoing, but it meant that if the funding signal held, there would be no established accountability channel the community could even use to raise the question.

The resolution plan was:
1. **Profile `5E2b2DcMd5W8...` fully.** Does it fund anything beyond tao.bot + shadow infra? What funded it? One hop further upstream might converge with GBnPzv or another known shadow address — or lead to an exchange withdrawal that closes the question.
2. **Profile all 344 senders to FJMfoeUX.** If they are all shadow-adjacent, FJMfoeUX is a controlled node; if many are unrelated, it is a service.
3. **Check the upstream of GBnPzv.** GBnPzv is the dominant source of both Gorfuxev7 and FJMfoeUX. If GBnPzv's upstream converges with `5E2b2DcMd5W8...`, the shared-operator signal strengthens significantly.

### Resolution: a Kraken hot wallet

Step 1 closes the question. Pulling the full transfer history for `5E2b2DcMd5W8MBhzTCFt63t2ZEN8RsRgL7oDd7BFYL9aMQux` from taostats.io returns **71,869 entries** and the label **Kraken Hot** — it is Kraken's TAO withdrawal hot wallet, the address from which all Kraken customer withdrawals originate.

Both rows in the table above are simply Kraken withdrawal transactions by different customers:
- One customer withdrew TAO from Kraken to tao.bot's coldkey.
- A different customer withdrew TAO from Kraken to FJMfoeUX.

They share a common upstream address because they both used the same exchange. There is no shared-operator inference to make.

The second address, `5FqqXKb9...`, is confirmed by the same transfer log: it appears as a *recipient* of large Kraken withdrawals — 10,413 TAO at block 6523301 and 7,014 TAO at block 6521895. It is a Kraken customer, not a shadow-adjacent actor by relation to tao.bot.

The same log also reveals something minor but worth noting: shadow infrastructure addresses received small direct Kraken withdrawals — FJMfoeUX received 152.998 TAO from Kraken Hot at block 6519147, and HB2Q8 received 418.998 TAO at block 6520193. This confirms the shadow whale operator has a Kraken account and occasionally uses it to top up the infrastructure. It does not identify the operator; Kraken is a minor source relative to total flows (FJMfoeUX received 57,000+ TAO from GBnPzv alone).

**Status: closed. False positive via exchange routing.**

### The lesson: exchange hot wallets as false-positive generators

Exchange hot wallets are a natural convergence point in blockchain analysis. A busy hot wallet sends to thousands of destinations every day — validators, shadow infrastructure, random holders — all as separate customer withdrawals. Any two of those destinations will share the hot wallet as a "common upstream funder." Finding this pattern and inferring shared ownership is a mistake analogous to concluding that two people are related because they both withdrew cash from the same ATM.

The correct check is to profile the shared address immediately: nonce, transaction count, balance behavior, and block explorer label. A high-nonce address with tens of thousands of entries and bidirectional flow to many counterparties is almost certainly a service, not a controlled node. In this case the check cost one taostats.io lookup.

The tao.bot and shadow whale operators are, as far as this evidence goes, separate entities who both happen to use Kraken.

---


## Future Directions: Completing the Hunt

The central finding of this investigation emerged without prior expectation: what started as a survey of large holders converged on evidence that a single unknown entity controls roughly 20% of all freely circulating TAO, accumulated across seven shadow wallets through a layered, automated funding infrastructure that has been operating continuously since before dTAO launched. This was not a hypothesis we began with. It is what the chain data shows.

That finding changes the nature of the remaining work. The question is no longer "are there shadow whales?" — it is "who is the single operator behind this specific infrastructure?" The investigative method that follows from this is targeted: trace the funding chain upstream from the identified cluster until it terminates at a known entity, a dead end, or an explanation.

### Why the Funding Chain Is the Right Thread to Pull

Every TAO in the shadow wallets arrived via a `Balances.Transfer` extrinsic signed by an address with a non-zero nonce. This is not just a fact about these specific wallets — it is a structural guarantee of the Substrate account model. There is no mechanism in Substrate to credit an account without a corresponding signed extrinsic from the sending side. New TAO does not materialize in an account; it is always transferred from a prior holder. This means the funding lineage is complete by construction: every satoshi in shadow wallet #1's 141,003 TAO balance is traceable, block by block, back through the transfer graph until it reaches either an original emission event (validator reward, staking reward converted to free balance) or a source wallet that itself received from an identifiable entity.

The chain of custody we've established so far is four layers deep:

```
Shadow wallets (nonce 0)
    ↑ funded by
Funder-A (5EiXej3..., nonce 23,452) + Funder-B (5DunDrF..., nonce 23,089)
    ↑ funded by
5HB2Q8H9... (nonce 2,293) → dominant upstream of Funder-A
5DfKewdx... (877 TAO)     → dominant upstream of Funder-B
    ↑ funded by
5GBnPzv... (also direct funder of SW#8)
5CNChyk2...
5FZiuxCB...
5DS3BcDq...
    ↑ funded by (unknown)
```

The tao.app API confirms that `5HB2Q8H9...` is sending large amounts to both Funder-A (69,328 TAO) and Funder-B (14,754 TAO) in recent events. Five other addresses are also confirmed sending large amounts to both funders simultaneously. The network is tighter than previously understood: `5GBnPzv...` feeds `5HB2Q8H9...` AND directly funded shadow wallet #8 — the same operator touching the infrastructure at multiple layers simultaneously.

The funding tree is **convergent**, not divergent. This is the key structural insight that makes the upstream search tractable.

### Upstream BFS: A Different Problem Than General Graph Search

It is worth distinguishing the specific search we want from the broader graph-analysis problem, because they have very different complexity profiles.

A general graph BFS — asking "is there any path between address A and address B across the whole network?" — is susceptible to combinatorial explosion. The branching factor (unique counterparties per address) can reach thousands for high-traffic nodes like exchanges, and at depth *d* the frontier grows as O(b^d). Finding that OTF connects to Binance connects to some pass-through connects to Funder-A is a path, but it tells you nothing about the shadow whale operator.

**Upstream BFS from a known cluster is different.** We are not asking "is there any path?". We are asking: "what address first received the TAO that eventually arrived in these specific shadow wallets, via these specific intermediate addresses?" This is a directed funding-lineage query. Several properties make it much more tractable:

**The supply chain converges.** A layered distribution system — the kind the shadow whale operator has built — is designed to disperse TAO from a central source out to many destinations. Traced forward, it fans out. Traced backward, it converges. At each layer upstream, there are *fewer* addresses, not more. We have nine shadow wallets, two primary funders, and roughly four feeders visible so far. The next layer is likely two to four addresses. The layer after that may be one. The tree does not explode — it tapers toward a root.

**Shadow wallets constrain the search direction.** Shadow wallets have nonce = 0, so they have no outbound edges. The BFS can only go inward (following inbound transfers). This means we never "wander" through the shadow wallet set; we always move upstream toward the source.

**Amount thresholds are highly effective here.** The transactions we care about are large — hundreds to thousands of TAO. Filtering to transfers above 10 TAO (for upstream tracing) eliminates the vast majority of noise transfers (dust activations, gas-equivalents, micro-payments) while retaining all meaningful funding events. At each feeder address in the chain, the number of *large-amount* inbound transfers is small — typically two to ten sources per address. This keeps the effective branching factor low even as the search goes deeper.

**Hub contamination is a terminal problem, not a transit problem.** The main concern with general graph BFS is "six degrees of separation" — paths through high-traffic hub addresses (exchanges, validators) that connect unrelated entities. In upstream BFS, this matters only at the *root* of the funding tree: if the TAO ultimately came from a Binance withdrawal, the chain terminates at Binance's hot wallet and attribution stops (the exchange knows their customer; we don't). In transit — through the anonymous feeder wallets — hub contamination isn't relevant because we're tracing backward through causal funding events, not forward through arbitrary transfer possibilities. An address in the funding chain is there because it *actually participated* in the funding, not because it shares a counterparty at some remove.

### What the Upstream Search Looks Like in Code

The algorithm is straightforward: a BFS queue initialized with the known funder addresses, expanding inward by fetching each address's inbound events from the tao.app API and checking whether any sender is a known entity.

```python
import requests
from collections import deque

API_KEY   = "<redacted>"
BASE_URL  = "https://api.tao.app/api/beta/accounting/events"
MIN_AMOUNT_TAO = 10.0   # ignore dust
RAO        = 1_000_000_000

KNOWN_ENTITIES = load_known_holders()  # the 2,369 validator/SN-owner/identity keys
SHADOW_INFRA   = {FUNDER_A, FUNDER_B, HB2Q8, FV99mB, GBnPzv, HUPxAs, DfKewdx}

def get_inbound(address):
    """Fetch all inbound transfers above threshold via tao.app."""
    page, results = 1, []
    while True:
        r = requests.get(BASE_URL,
                         headers={"X-API-Key": API_KEY},
                         params={"coldkey": address, "page": page, "page_size": 100})
        rows = r.json().get("data", [])
        for ts, blk, _, frm, to, amt_rao, *_ , tx_type in rows:
            if tx_type == "Transfer" and to == address and amt_rao and amt_rao / RAO >= MIN_AMOUNT_TAO:
                results.append({"from": frm, "block": blk, "amount_tao": amt_rao / RAO})
        if not r.json().get("next_page"):
            break
        page += 1
    return results

visited = set(SHADOW_INFRA)
queue   = deque(SHADOW_INFRA)

while queue:
    addr = queue.popleft()
    for event in get_inbound(addr):
        sender = event["from"]
        if sender in visited:
            continue
        visited.add(sender)

        # The payoff: did we reach a known entity?
        if sender in KNOWN_ENTITIES:
            print(f"KNOWN ENTITY REACHED: {KNOWN_ENTITIES[sender]['name']}")
            print(f"  Path: ... → {addr[:12]} ← {sender[:12]}")
            print(f"  Amount: {event['amount_tao']:,.2f} TAO at block {event['block']:,}")
        else:
            # Unknown address: add to queue for next hop
            queue.append(sender)
```

The `visited` set prevents revisiting addresses, keeping the search from cycling. The amount threshold is the primary complexity control: at 10 TAO, the queue expands only when a new upstream funder has made a meaningful transfer. The check against `KNOWN_ENTITIES` fires immediately when any layer of the funding chain touches an identifiable address. Each address in the queue requires one to N paginated API calls (N = ceil(nonce / 100)), but for feeder wallets with nonces in the hundreds, this is fast.

The search terminates naturally when the queue is exhausted — either because every upstream path reached a dead end (fully anonymous or originated from an emission event), a known entity, or a source with no recorded inbound transfers above threshold (suggesting off-chain origin, such as an OTC purchase).

### The Architecture Makes the Funding Lineage Complete

A critical point for readers learning Bittensor's chain architecture: **emission is the only way new TAO enters free balance without a Transfer event.** Validator rewards and other protocol emissions are credited directly as free balance via the `pallet-balances` credit mechanism. These show up in the `Balances.Deposit` event (not `Transfer`). When a validator earns emissions, the TAO appears in their free balance without any corresponding transfer sender.

This matters because it defines what "the chain terminates" means in the upstream search:

- **Transfer event found:** the TAO came from another address. Follow it upstream.
- **Deposit event found (no Transfer sender):** the TAO entered this address as a protocol emission. This is the root. The address that received this emission *earned* this TAO by running a validator or miner — and that activity required signing transactions. Validators are registered and enumerable. If the emission root is a validator, it is identifiable.
- **No event found above threshold:** the source is either a very small original deposit or a gap in the indexer. For large amounts (>100 TAO), this should not happen — large amounts leave large events.

The implication: the funding lineage of the shadow whales must eventually terminate at either (a) an original emission to a validator or miner, (b) an OTC or exchange withdrawal where the TAO entered the chain from fiat purchase and the counterparty is an exchange rather than a traceable address, or (c) a known actor who has simply not been identified yet because the chain hasn't been traced far enough. Option (a) would be the most forensically significant: finding the validator that originally earned this TAO, even through four layers of pass-throughs, would constitute strong evidence about the operator's identity. Option (b) is the likely outcome for a large institutional position — TAO purchased via OTC or exchange, withdrawn to a private wallet — and would leave the trail at an exchange withdrawal address without further attribution.

### Honest Limits of This Approach

**The exchange terminus problem.** If the funding lineage terminates at a major exchange withdrawal address (Binance, OKX, Kraken, or a smaller crypto-fiat broker), attribution requires the exchange's KYC records — which are off-chain and not publicly available. The chain evidence would confirm which exchange was used, and the block timing of the withdrawal would help narrow the purchaser, but it would not identify the person without exchange cooperation. This is the dominant termination case for large institutional positions.

**Depth and API volume.** At four layers deep, we've already accumulated roughly a dozen unique feeder addresses. If the tree extends two to three layers further (plausible for a well-designed system), we might encounter O(50–200) unique addresses to query. At the current API rate, that is ten to forty minutes of calls — entirely feasible on a laptop. The search becomes expensive only if the tree is deliberately designed to be wide (many parallel feeders), which would itself be a forensically meaningful observation about operational sophistication.

**Emission tracing as a different tool.** Following the funding chain backward to emission events, if possible, requires the Bittensor archive node — the tao.app API indexes Transfer events, but emission (Deposit) events may or may not be covered. The archive node's `get_events()` at each relevant block covers all event types including Deposit, so emission tracing remains feasible via the archive approach for the terminal blocks. This is where the two-tool approach (tao.app for broad transfer history, archive node for precise block-level event analysis) remains relevant even in v2.

**The human at the top.** Even a complete technical attribution — establishing that a specific known address sent the original TAO — does not necessarily identify the human operator. An OTF multisig, a DAO treasury, or an exchange custody wallet are institutional actors; their on-chain identity is clear but their human decision-makers are not public. The forensic graph tells you what the chain shows; it cannot compel disclosure of who controls a private key.

### The Immediate Next Steps

`taoapp_investigation.py` is complete. The known infrastructure has been fully mapped at the current depth. The next layer of the upstream search involves the **six newly identified cross-funder hub addresses** (especially `5Gorfuxev7...`, `5FJMfoeUXsDXQSABaai8CUQvMyAK1a7jXqJvkBMnabfuJCjv`, and `5EJMGn13...`) plus the remaining feeders of `5HB2Q8H9...`.

The concrete next steps:

1. **Run the upstream BFS (`upstream_bfs.py`)** — initialized from the full set of known infrastructure addresses, expanding inward via the tao.app API, checking each new sender against the 2,369 known entities. The six cross-funder hubs are high-priority starting points.
2. **Profile `5EJMGn13...` specifically** — its round-trip pattern (top sender to Funder-A AND top receiver from Funder-A) warrants a dedicated event history query to understand whether it is a consolidation account, a recycling layer, or something else.
3. **Profile `5Gorfuxev7...`** — the single address most deeply connected to the visible infrastructure, sending 17-22k TAO to each funder. If this address has a known upstream, it could be the penultimate layer.
4. **Cross-reference at each new layer against the 2,369 known entities** — if any upstream address has an on-chain identity or is a registered validator/SN owner, the hunt is over.
5. **Repeat until termination** — exchange hot wallet (attribution stops at exchange), emission event (validator identity revealed), or complete anonymity (genuinely untraceable).

This is a tractable search on a laptop. The funding tree converges by design. The architecture of the chain guarantees the trail exists. What remains is to follow it.

## The Toolkit

The investigation uses two data sources: the Bittensor Python SDK against Finney [archive node](https://docs.learnbittensor.org/resources/glossary#archive-node) RPC, and the `tao.app` indexed event API.

### Archive node (RPC)

```python
import bittensor as bt

# Public node — current state
sub = bt.Subtensor(network="finney")

# Archive node — full block history
sub_archive = bt.Subtensor(network="archive")
# or: bt.Subtensor(network="wss://archive.chain.opentensor.ai")
```

The substrate interface under the hood is `async_substrate_interface`, which wraps standard Substrate JSON-RPC methods. Storage maps are queried with `sub.substrate.query_map(module, storage_function)` and single values with `sub.substrate.query(module, storage_function, params)`. Historical queries use `block_hash` parameters: every RPC method accepts a block hash, and the archive node keeps the full state at every block.

### tao.app event API

Substrate does not index events by address — there is no built-in way to ask "give me all transfers involving address X." The archive-node approach uses binary search on balance checkpoints to locate individual transfer blocks (O(log N) calls per interval), but this is slow for addresses with thousands of events spread across millions of blocks.

The `tao.app` ClickHouse-backed API solves this directly:

```python
import requests

API_KEY  = "<redacted>"
BASE_URL = "https://api.tao.app/api/beta/accounting/events"

r = requests.get(
    BASE_URL,
    headers={"X-API-Key": API_KEY},
    params={"coldkey": ss58_address, "page": 1, "page_size": 100}
)
# Returns: [timestamp, block, extrinsic_idx, from, to, amount_rao, fee,
#           alpha, origin_netuid, destination_netuid, transaction_type]
```

The response is paginated JSON with `total`, `page`, `next_page` fields. Amount is in rao (divide by 1e9 for TAO). This returns the full event history for any address in milliseconds — replacing hours of archive-node binary search for high-nonce wallets.

**Coverage note:** The tao.app index coverage depends on when the indexer was last synced. For addresses active through the current chain head, coverage is complete. For addresses whose entire activity predates the indexer's earliest indexed block, coverage may be partial. In practice, for the addresses in this investigation (all active after block 4M), coverage is confirmed complete by cross-checking total inbound amounts against known binary-search results.

All raw data is stored as JSONL or plain text files for reproducibility. The full pipeline:

| Script | What it does | Output |
|---|---|---|
| `enumerate_wallets.py` | Streams all accounts + staking coldkeys from chain | `finney_accounts.jsonl`, `finney_staking_cks.txt`, `finney_meta.json` |
| `analyze_wallets.py` | Classifies shadow wallets | `finney_shadow_wallets.jsonl`, `finney_summary.txt` |
| `identity_lookup.py` | On-chain identity for top 100 shadow wallets | `finney_shadow_identified.jsonl`, `finney_shadow_top_report.txt` |
| `top100_holders.py` | Role + identity analysis for top 100 by free balance | `top100_holders.jsonl`, `top100_holders_report.txt` |
| `shadow_history.py` | Archive node balance sampling across 14 blocks | `shadow_history.json`, `shadow_history_report.txt` |
| `find_first_transfer.py` | Binary search for first-funded block + sender attribution | `first_transfers.json`, `first_transfers_report.txt` |
| `check_childkeys.py` | Childkey relationship check for shadow wallets | `childkey_check.json` |
| `known_holders.py` | Enumerate all identity-registered + validator + SN-owner coldkeys with balances | `known_holders.json`, `known_holders_report.txt` |
| `known_holders_by_stakeweight.py` | Join `known_holders.json` with `validator_stake_weight.json` to rank known entities by combined free + validator stake | `known_holders_stakeweight_report.txt` |
| `nonce_check.json` | Ad-hoc nonce query for positions #4 and #7 (not a script — raw JSON) | `nonce_check.json` |
| `validator_stake_weight.py` | Query actual stake-weight for all 5,609 validators via `DelegateInfo.total_stake` | `validator_stake_weight.json`, `validator_stake_weight_report.txt` |
| `trace_known_to_shadow.py` | Cross-reference known entities against first-funded block events for each shadow wallet | `known_to_shadow_report.txt` |
| `all_inbound_transfers.py` | Binary-search full inbound transfer history for all 10 shadow wallets; cross-reference all senders against known entities | `all_inbound_transfers.json`, `all_inbound_report.txt` |
| `investigate_funder.py` | Deep profile of Funder-A (`5EiXej3...`) and Funder-B (`5DunDrF...`): balance history, inbound attribution, all transfers at known shadow-funding blocks | `funder_investigation_report.txt` |
| `const_attribution.py` | Check for on-chain transfers between Const's public key and SN120 owner key; balance history and inbound funding for both | `const_attribution_report.txt` |
| `taoapp_investigation.py` | Full event history (via tao.app API) for all critical addresses: Funder-A, Funder-B, upstream feeders, Const's keys, tao.bot addresses; cross-reference all against shadow wallets | `taoapp_investigation_report.txt`, `taoapp_investigation.json` |
| `investigate_taobot.py` | Profile tao.bot validator: coldkey state, take rate, stake by subnet, 289 child hotkeys across 68 subnets, coldkey funding history | `taobot_investigation_report.txt` |
| `upstream_bfs.py` | BFS upstream from shadow whale infrastructure through the tao.app API; checks every new sender against known entities; expands hop by hop until chain terminates | `upstream_bfs_report.txt`, `upstream_bfs.json` |
| `profile_new_feeders.py` | Profile the top-5 new senders to Funder-A identified from BFS log; reveals internal recycling layer and GBnPzv dominance; tao.bot shared-upstream finding | `profile_new_feeders_report.txt` |
| `profile_gbonpzv.py` | Profile GBnPzv upstream and its co-feeders (CNChyk2, HbDZ6UL); GBnPzv has 522k events (may be exchange/large-trader); traces who funded the dominant source address | `profile_gbonpzv_report.txt` |
| `crosscheck_addresses.py` | Cross-references all shadow whale, infrastructure, and tao.bot addresses against known_holders.json (validators/SN-owners) and the top-100 free-balance ranking; identifies who is NOT registered anywhere | `crosscheck_report.txt` |


