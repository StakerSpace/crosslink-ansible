# crosslink-check and crosslink-stake

Two scripts land on a node host with `site.yml`. Both are Python 3, standard library only, one file each, and both read the node's own config (`/etc/crosslink/zebrad.toml`), its journal, and the chain's calendar in `/etc/crosslink/chain.env`. Neither needs the playbook once installed: copy the file to any host that runs the node software and point it at the files with the variables under "A node run by hand".

| script | installed on | what it is |
|---|---|---|
| `crosslink-check` (`roles/crosslink_node/files/crosslink-check`) | every node host, `/usr/local/bin/crosslink-check` | is this host working? One screen, read from the host, changing nothing |
| `crosslink-stake` (`roles/crosslink_node/files/crosslink-stake`) | a host with the headless wallet on (`crosslink_disable_wallet: false`), `/usr/local/bin/crosslink-stake`; removed when the wallet goes off | stakes this host's mining rewards to a finalizer, with every check first. The one thing in this repository that spends |

`site.yml --tags stake` updates only the two scripts, the stake timer and `chain.env`: no build, no config, no restart.

## crosslink-check

```bash
sudo crosslink-check              # one screen
sudo crosslink-check --roster     # the same, with every finalizer on the roster
sudo crosslink-check --json       # everything as JSON, for a script
sudo crosslink-check --no-color   # no colour (also: NO_COLOR=1, or not a terminal)
```

Run it as root or as the node's user: it reads the config for the RPC address and the switches. Colour marks what matters: green is fine, yellow is wait or look, red is act. Every figure names its source; a figure it could not read is a dash, never a guess.

What it answers, in order:

| row | what it reads | from |
|---|---|---|
| SERVICES | the node unit and the stake timer, up and for how long | systemd |
| NODE | the height against the node's estimate of the tip; synced, or how far behind and the percentage; the block rate since the last run; the version; the health endpoint's `/ready` answer | `getblockchaininfo`, `getinfo`, `/ready`, one line of state in `/var/tmp` |
| PEERS | p2p peers, and the state network's peers as a count | `getpeerinfo`, the log |
| FINALITY | activated or not, the finalized height, the gap to the tip, whether the finalized block is in this node's chain, the roster's size and total stake and its largest three; "BFT is stopped on this node" when the node dropped BFT after a reorg it could not follow | `get_tfl_final_block_height_and_hash`, `get_tfl_roster_zats`, `getblockhash`, the journal |
| FINALIZER | this host's finalizer address, whether it is on the roster and at what rank, its stake | the log's `finalizer address:` line, the roster |
| STAKING DAY | open or closed, the block in the cycle, blocks until it closes or opens; before the first staking block, how far it is | the height and `chain.env` |
| MINING | on or off, the solver threads, the payout address and where it comes from, that address's balance, the newest reward | the config, the log's `Mining to` line, `getaddressbalance` |
| WALLET | on or off, started or not, how far it has read the payout address against the tip and how fast since the last run, what it can spend (transparent coins and shielded notes, spendable, pending, committed), whether its tree has diverged from the node's | the log, `wallet_spendable_funds` |
| STAKES | the stakes this wallet holds, per finalizer, with the rank; unstaked stakes ready to withdraw; whether `crosslink-stake --all` would go ahead now, in what pieces, with the timer's own `--min`, `--keep` and `--batch`; whether the last timer pass failed | `wallet_staking_positions`, the timer's unit |

Run it twice a minute apart to see the block rate and how fast the wallet reads. `CROSSLINK_CHECK_TIMING=1` says on stderr how long each step took.

`--json` is the same report as a document, for a monitoring hook: every row is a key (`services`, `node`, `finality`, `finalizer`, `staking_day`, `mining`, `wallet`, `stakes`, `stake_timer`), with `read_at` on top.

## crosslink-stake

```bash
sudo crosslink-stake --to ADDRESS --amount 100      # stake 100 cTAZ
sudo crosslink-stake --to ADDRESS --all             # stake every spendable reward but --keep
sudo crosslink-stake --to ADDRESS --all --dry-run   # run every check, send nothing
sudo crosslink-stake --to ADDRESS --all --wait      # wait for Staking Day instead of stopping
sudo crosslink-stake --to ADDRESS --all --yes       # no question, for a script
sudo crosslink-stake --to ADDRESS --all --batch 100 # stakes of at most 100 cTAZ each
sudo crosslink-stake --to ADDRESS --auto            # what the timer runs: --all --yes, and "not now" is not a failure
sudo crosslink-stake --to ADDRESS --timer install   # stake by itself from now on
sudo crosslink-stake --timer status                 # next run, last run, last stake
sudo crosslink-stake --timer show                   # print the two units, change nothing
sudo crosslink-stake --timer remove                 # stop
```

`ADDRESS` is a finalizer address, `zfinv1` and 128 characters: the one a finalizer's node logs at start (`finalizer address:`) and the one `site.yml` records in the key bundle. It is self-describing (the node refuses one that does not verify), and a finalizer need not be on the active roster to be staked to, so the seat is reported, never required.

### The checks

It stops at the first one that fails, and says which and what to do:

1. the wallet is on and has started, and the rewards are this wallet's: no `miner_address`, or `miner_address` is this wallet's own unified address (rewards shielded)
2. the node is synced and on the network's chain: the last finalized block is in this node's chain, read from its own RPC. `--reference URL` also compares the block at an explorer's tip (JSON with `tip` and `tip_hash`), which is the only fork test before finality starts on a chain and the only one that sees a fork younger than the last finalized block
3. no earlier stake from this script is still waiting for a block (it waits 40 blocks, then gives the stake up and stakes again on the next run)
4. the address decodes
5. Staking Day is open with 15 blocks to spare, and the chain is past the first block a stake is valid at
6. the wallet has read the chain up to the tip: its notes (`wallet_spendable_funds`, the wallet's own tip) and the payout address
7. the amount is there: the wallet's spendable shielded notes (its own rule, 3 confirmations) plus the payout address's rewards older than 10 blocks, less `--keep` (1 cTAZ) for fees

While finality is stalled it says so: nothing after the last finalized block is final yet, a stake included.

### What it sends

Every stake is a **power of 10 cTAZ**: 1, 10, 100, 1,000 (0.1 and 0.01 too). The Feature Net asks it from block 55,296 (v15's network upgrade) and the v15 wallet refuses any other amount at every height, so the script stakes no other kind on any build. `--all` goes as such pieces, largest first, none over `--batch` (1,000) and none under `--min` rounded down to a power of 10; what is left under the smallest piece waits for a later pass. An `--amount` that is not a power of 10 is refused.

It stakes one piece at a time: before each stake after the first it waits until the one before is in a block and the wallet has read that block, so no coin is offered twice, and runs every check again. A batch that stops leaves the ones before it staked; run it again for the rest. The cap exists because the wallet pays a stake with the rewards one coin or note each, and a very large stake in thousands of coins is refused by the node's own mempool.

It shows the stake, asks once (`--yes` skips it), sends through `wallet_staking_action` (and falls back to the older `staking_command` on a build that has only that), and then waits up to `--watch` (10) minutes for the stake to be in a block. The wallet answers every refusal with the same words ("failed to create staking transaction from notes") and prints its reason in the node's log; the script reads that line back and says it ("can't afford" means the wallet has not seen the coins yet: wait; "is not a power of 10" means the amount).

### What it writes

The node's reply goes to `/var/lib/crosslink-stake/bond-<time>.json` **before anything reads it**, and every attempt, a failure too, is a line in `/var/lib/crosslink-stake/ledger.jsonl` naming the chain (`NETWORK` from `chain.env`), so a host reset from one network to the next keeps its ledger and ignores the other chain's lines. Copy that directory into the key bundle after a stake. A timeout is not a failure: the stake may still land, so the script never sends again by itself; `wallet_staking_positions` lists it once its block is read.

Exit codes: `0` sent, or nothing to stake · `1` a check stopped it, or the node refused · `3` no reply in time.

### The timer

`--timer install` writes `crosslink-stake.service` and `crosslink-stake.timer`, which run this file with `--auto` every `--every` (30) minutes, restart the timer and start a pass at once, so a changed address, minimum or script is in force in this Staking Day and not at the next tick; a timer already as asked is left alone ("Unchanged"). Run as root it is a system timer, otherwise a user timer (`systemctl --user`). The units carry `--to`, `--min`, `--keep`, `--batch`, `--reference` and `--dry-run` as given at install (install again to change one), and every `CROSSLINK_*` variable set then, so a node run by hand installs it through the same wrapper it stakes with.

With `--auto` every check runs on every pass. A check that passes by itself later ends the pass with exit 0: Staking Day closed, the node syncing, the wallet reading, an earlier stake not in a block yet. Anything else is exit 1, and `systemctl --failed` shows the unit; `crosslink-check` says so too. A pass with nothing to do ends in seconds. A longer `--every` delays the first stake after Staking Day opens, and the last before it closes, by as much. A pass stakes only once `--min` (10 cTAZ) has gathered: each stake is a bond of its own, so a larger minimum means fewer bonds to unstake later. Its output: `journalctl -u crosslink-stake.service`.

The playbook runs the same install on a host whose inventory sets `crosslink_autostake_to` (with `crosslink_autostake_min`, `crosslink_autostake_every_minutes`, `crosslink_autostake_reference`, `crosslink_autostake_dry_run`), removes the timer when the line goes, and never stakes itself. A node restart under a pass loses the stake the wallet is building, so every run holds the timer, waits for a pass in flight to end, restarts the node then, waits for its RPC, and resumes the timer.

## A node run by hand

Both scripts work against a node this playbook did not build. Point them at its files:

| variable | what |
|---|---|
| `CROSSLINK_CHECK_CONFIG` / `CROSSLINK_STAKE_CONFIG` | the node's config file (default `/etc/crosslink/zebrad.toml`) |
| `CROSSLINK_CHECK_LOG` / `CROSSLINK_STAKE_LOG` | the node's log files, joined by `:`, read instead of the journal |
| `CROSSLINK_CHECK_USER_UNIT` / `CROSSLINK_STAKE_USER_UNIT` | set to 1 for a `systemctl --user` unit |
| `CROSSLINK_CHAIN_ENV` | a copy of `chain.env` for the chain (see `roles/crosslink_node/templates/chain.env.j2` for the keys) |
| `CROSSLINK_STAKE_DIR` | where the replies and the ledger go (default `/var/lib/crosslink-stake`) |
| `CROSSLINK_CHECK_STATE` | the block-rate state file (default `/var/tmp/crosslink-check.state`) |

A wrapper that exports them is all such a host needs; `--timer install` keeps them in the unit.
