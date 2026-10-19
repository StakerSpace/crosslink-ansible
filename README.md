# crosslink-ansible

Ansible playbooks that build and run [Crosslink](https://shieldedlabs.net/crosslink/) nodes from the official node software, [ShieldedLabs/crosslink_monolith](https://github.com/ShieldedLabs/crosslink_monolith) ([v15](https://github.com/ShieldedLabs/crosslink_monolith/releases/tag/v15) today). One inventory line makes a host an **RPC node**, a **miner** or a **finalizer** on the Crosslink Feature Net, and two scripts land on every host: `crosslink-check`, one screen that says whether the host is working, and `crosslink-stake`, which stakes a host's mining rewards to a finalizer, by hand or on a timer.

Crosslink is Shielded Labs' finality upgrade for Zcash. The Feature Net is a test network with a test coin, cTAZ. Nothing here touches Zcash mainnet.

## Quick start

Six commands from an empty host to a running node. Debian or Ubuntu host, root over SSH, a public IPv4 address.

```bash
git clone https://github.com/StakerSpace/crosslink-ansible.git && cd crosslink-ansible
ansible-galaxy collection install -r requirements.yml
cp inventory.example.yml inventory.yml      # put your host's address under miner-1 (or rpc-1)
openssl rand -hex 16                        # the host's identity string: paste it over CHANGE-ME
ansible-playbook -i inventory.yml site.yml  # builds zebrad (about 20 min), configures, starts
ssh root@<host> crosslink-check             # one screen: synced? peers? mining? finality?
```

The smallest inventory, one miner, is three lines under a host. The identity string is yours to make, one per host; the run refuses the placeholder:

```yaml
all:
  vars:
    ansible_user: root
  children:
    miner:
      hosts:
        miner-1:
          ansible_host: 203.0.113.30
          crosslink_identity_seed: "CHANGE-ME"           # the output of: openssl rand -hex 16
          crosslink_miner_threads: 6                 # cores minus two
```

Change `miner` to `node` for an RPC node, or add the host to `finalizer` as well to run a finalizer. The run ends with one line per host (role, ref, payout address, where its key bundle is) and the node syncs and starts mining by itself once it reaches the tip. The 24-word phrase for the miner's wallet is in `~/crosslink-node-keys/miner-1/mnemonic.txt`: back it up.

## Find what you need

| I want to… | read |
|---|---|
| run an RPC node, a miner or a finalizer | [Roles](#roles) |
| know which settings matter and see examples (threads, data disk, public IP, pinned ref, logging) | [Settings](#settings) |
| change anything in `zebrad.toml` | [docs/zebrad-toml.md](docs/zebrad-toml.md): every key, its default and the variable that writes it |
| mine, and choose where the rewards go | [Mining](#mining), [Rewards shielded](#rewards-shielded) |
| see what a miner has earned | [The miner's rewards](#the-miners-rewards) |
| run a finalizer and get the address stake goes to | [Finalizer](#finalizer) |
| stake the host's rewards, by hand or on a timer | [crosslink-stake](#crosslink-stake), [docs/scripts.md](docs/scripts.md) |
| check whether a host is working | [crosslink-check](#crosslink-check), [After the run](#after-the-run) |
| find the seed, the phrase and the host records | [Key bundle](#key-bundle) |
| build a tag, a branch or one commit, or upload a binary | [Which code runs](#which-code-runs) |
| join the Nightly Network, or follow a release that replaces the chain | [Networks](#networks) |
| wipe a node's state and resync, keeping its identity | [The playbooks](#the-playbooks): `reset.yml` |
| rebuild a node from a snapshot | [Restore](#restore) |
| load a hard fork rule | [Hard fork rules](#hard-fork-rules) |
| scrape the node with Prometheus | [Metrics](#metrics) |
| run the RPC calls by hand: fork test, Staking Day, viewing key, a stake | [docs/CALLS.md](docs/CALLS.md) |
| know what the playbook will never do | [Safety rules](#safety-rules) |
| contribute, or report a problem | [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md) |
| point an AI agent at this repository | [CLAUDE.md](CLAUDE.md) |

## What it does

- **Builds zebrad from source** at any tag, branch or commit, or uploads a binary you built elsewhere. A moved branch is rebuilt; an unmoved tag is left alone. Old binaries stay for rollback.
- **Reads the chain out of the binary.** The release carries the Feature Net's magic, genesis, parameters and seed peers. The playbook reads them back out of the binary it just built and writes them into `zebrad.toml`, so nothing about the chain is typed into this repository and a newer release brings its own values.
- **Writes `zebrad.toml`** from variables: ports, the public address, mining and its solver threads, the wallet switch, the health and metrics endpoints, hard fork rules, sync, mempool and logging tunables, and a verbatim escape hatch for the rest. [docs/zebrad-toml.md](docs/zebrad-toml.md) explains every key the node software reads.
- **Runs the node under systemd** as its own user, least privilege, restart on failure, and opens only the p2p and BFT ports in ufw. RPC stays on loopback.
- **Keeps the node's identity safe.** The node's seed file is its finalizer key and its wallet. The playbook never writes one, carries the existing one across a release that renames the state directory, refuses to pick between two different seeds, and copies a miner's or finalizer's seed to a **key bundle** on your machine as a 24-word phrase.
- **Mines** with as many solver threads as you give it, to the node's own wallet, to an address you set, or shielded to the wallet's unified address.
- **Stakes rewards** from the host with `crosslink-stake`, with every check first, or by itself on a systemd timer.
- **Reports** what each miner has earned (`rewards.yml`), **resets** a node's state while keeping its seed (`reset.yml`), **restores** a node from a published snapshot (`restore.yml`), and loads **hard fork rules** safely.
- **Checks itself** before it touches anything: hosts already running a node are refused, a key bundle inside the repository is refused, a payout address or a hard fork rule that zebrad would reject is refused before anything is written.

What it does not do: run a dashboard, an explorer or a database. It is the node software and nothing else.

## Requirements

| where | what |
|---|---|
| control machine | Linux or macOS, with Python 3, `ansible-core` 2.15 or newer, the `community.general` collection (`ansible-galaxy collection install -r requirements.yml`) and SSH to every host. On a Mac, `brew install ansible` or `pip3 install ansible-core`; if a run with several hosts dies with an Objective-C fork-safety error, `export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` first. Windows is not an Ansible control node: run it from WSL2 (Ubuntu), with the clone and the SSH keys inside WSL |
| each host | Linux only: Debian 12 or Ubuntu 22.04 or newer, systemd, root or a sudo user, a public IPv4 address (or a forwarded UDP port, see `crosslink_public_ip`), outbound internet to GitHub and crates.io for the build. A Mac or a Windows machine cannot be a target |
| sizing | the build takes about 20 minutes cold and wants a few GB of RAM; the chain state is small today and grows; a restore wants 25 GB free. One mining solver thread is one core and 144 MB |

## Roles

A host's role is its inventory group. Groups combine.

| group | the host runs | what the group adds |
|---|---|---|
| `node` | a full node with its RPC on loopback: an RPC endpoint, a seed peer | nothing else. Its seed stays on the host: no stake points at it and it earns nothing |
| `miner` | a full node with the internal miner on | solver threads, a payout address, the seed copied to the key bundle (it is the wallet), `rewards.yml` |
| `finalizer` | a full node whose BFT key is meant to carry stake | the seed copied to the key bundle (it is the identity), the finalizer address read off the node and recorded, a host record that says so |

- `miner` + `finalizer`: one node that mines and finalizes. Fine on a test network. On a network that matters, keep them on separate hosts: one machine holding both loses both at once.
- `node` alone: an RPC endpoint for your own tools, or a seed peer.
- One inventory file is one network. A second network gets its own file.

A finalizer is not a kind of node. **Every** node derives a BFT key from its seed file and becomes a finalizer when stake points at that key. The `finalizer` group changes no setting the node reads; it tells the playbook what the host is for, so the seed is backed up and the address stake goes to is written down. The playbook never writes `explicit_bft_key_seed`, on any host.

## Settings

Every setting is a variable in `group_vars/all/main.yml`, with its default and a comment. Override it per host in `inventory.yml`, under the host. Nothing is edited on a host: the playbook renders `zebrad.toml` from the variables, and a changed file restarts the node.

The ones most people set:

| variable | default | what it does |
|---|---|---|
| `crosslink_network` | `featurenet` | which chain: `featurenet` (the Feature Net, v15) or `nightly`. Picks the code and the staking calendar. `featurenet-v14` is another name for `featurenet` |
| `crosslink_ref` | the network's (`v15`) | the git ref to build: a tag, a branch or a commit |
| `zebrad_install_mode` | `build` | `build` on the host, or `copy` the binary at `zebrad_local_binary` from your machine |
| `crosslink_data_root` | empty | a volume for the chain state, for example `/mnt/ssd/crosslink`. Empty uses `/var/lib/crosslink`. `bulk_data_root` is another name for it |
| `crosslink_public_ip` | the host's first IPv4 | the address BFT peers dial. Must be public and stable; zebrad hashes it into the node's transport key. Set it when the host is behind NAT, and forward UDP 12301 |
| `crosslink_identity_seed` | none, required | the string the node's state-network identity is derived from (blake3 of it is the key seed). The same string is the same identity on any machine, so make it random and private, one per host: `openssl rand -hex 16`. Keep it once chosen. The run refuses an empty value, the placeholder and the example below. Not the BFT identity, not the wallet |
| `crosslink_miner_threads` | 1 | parallel equihash solvers on a miner. Each is one core and 144 MB. Leave two cores to the node |
| `crosslink_miner_low_priority` | true | solvers at the lowest OS priority, so mining never starves the node |
| `crosslink_miner_address` | empty | where rewards go. Empty pays the node's own wallet (its seed) |
| `crosslink_miner_shielded` | false | pay rewards as shielded notes to the wallet's own unified address. Needs the wallet on |
| `crosslink_disable_wallet` | true | the headless wallet. Turn it on (`false`) only to stake from the host |
| `crosslink_autostake_to` | empty | a finalizer address (`zfinv1…`): install the stake timer and stake the host's rewards there by itself |
| `crosslink_metrics_listen` | empty | zebrad's Prometheus endpoint, for example `0.0.0.0:9999`; `crosslink_metrics_allow_from` lists who may scrape it |
| `crosslink_keys_dir` | `~/crosslink-node-keys` | where the key bundle is written on your machine. Must be outside the repository |

Examples, each under a host in the inventory:

```yaml
# A fast miner on a 8-core box with a dedicated disk
miner-1:
  ansible_host: 203.0.113.30
  crosslink_identity_seed: "6b1e0d9c4a7f2e35c8d1b0a9f3e7c642"   # openssl rand -hex 16; this one is refused, make your own
  crosslink_miner_threads: 6
  crosslink_data_root: /mnt/nvme/crosslink

# A node behind NAT: tell peers the router's address, forward UDP 12301 and 12001, TCP 8233 and 12001
rpc-1:
  ansible_host: 10.0.0.5
  crosslink_public_ip: 198.51.100.7

# Pin a finalizer to one commit so a moved branch never restarts it
finalizer-1:
  ansible_host: 203.0.113.40
  crosslink_ref: "68a076cf0a2b…"

# A binary built elsewhere
miner-2:
  ansible_host: 203.0.113.31
  zebrad_install_mode: copy
  zebrad_local_binary: /home/me/builds/zebrad-v15

# Louder logs, a custom mempool limit, and a block hook
rpc-2:
  ansible_host: 203.0.113.21
  crosslink_log_filter: "info,zebra_network=debug"
  crosslink_mempool_tx_cost_limit: 160000000
  crosslink_block_notify_command: "/usr/local/bin/on-block %s"
```

The full list, with the `zebrad.toml` key each one writes, is in [docs/zebrad-toml.md](docs/zebrad-toml.md). Anything the template does not write goes in `crosslink_extra_toml`, verbatim.

Never leave a key bare in the inventory. `crosslink_hardforks:` with nothing under it overrides the default list with null and the node role stops. Delete the key to get the default back.

## The playbooks

| playbook | what it does | run it |
|---|---|---|
| `site.yml` | build or upload the binary, write the config and the unit, open the ports, carry the seed, start the node, install the two scripts, write the key bundle | on every change; it is idempotent |
| `rewards.yml` | what each miner has earned, read from the node: received in total, balance, spendable, the last 24 hours. Writes `rewards.json` to the key bundle. Read-only | whenever you want to know |
| `reset.yml` | wipe a node's chain state and resync, keeping its seed. For a replaced network, a corrupt state or a fork of the node's own | `-l <host> -e reset_confirm=<host>` |
| `restore.yml` | replace a node's chain state with a published snapshot, keeping its seed. For a node that left the network, or to skip a sync from genesis. Refuses a finalizer | `-l <host> -e restore_confirm=<host> -e restore_url=… -e restore_sha256=…` |

Limits and tags on `site.yml`:

```bash
ansible-playbook -i inventory.yml site.yml -l miner             # only the miners
ansible-playbook -i inventory.yml site.yml -l miner-1           # one host
ansible-playbook -i inventory.yml site.yml --tags identity      # only the key bundle and the records
ansible-playbook -i inventory.yml site.yml --tags stake         # only the two scripts, the timer and chain.env: no build, no restart
ansible-playbook -i inventory.yml site.yml --check --diff       # what would change
```

The preflight always runs. `python3 check-templates.py` from the repository root must print `0 templates with undefined variables` before a change to a template ships; `ansible-lint` is the other gate.

## Which code runs

`crosslink_ref` is any git ref. Unset, it follows the network: `v15` on the Feature Net, `dev` on the Nightly.

```yaml
crosslink_ref: "v15"            # tag
crosslink_ref: "main"           # branch: rebuilt when its head moves
crosslink_ref: "68a076cf…"      # commit: never changes
crosslink_update_source: false  # keep the current checkout; never fetch
```

The ref is resolved to a commit before the build and the binary is named after it (`zebrad-v15-68a076cf0a2b`). A moved branch gets a new name, a rebuild and a restart; an unmoved tag does nothing. The commit is recorded in the host's card. A finalizer holding a seat should be pinned to a commit: the restart that follows a rebuild costs it the votes it would have cast.

## Networks

| `crosslink_network` | the chain |
|---|---|
| `featurenet` (default) | the Feature Net: Shielded Labs' public test network, v15 since 2026-10-13, with a network upgrade at block 55,296 that every node needs |
| `nightly` | the Nightly Network: Shielded Labs' fast-moving test chain, built from `dev`, no binaries, replaced whenever they want a new one |

The binary carries the chain in both cases, so switching is one line. What a row holds is the ref and the staking calendar the two host scripts read (the period, the Staking Day window, the first block a stake is valid at, the block finality starts at, the active roster cap); the comments in `group_vars/all/main.yml` say where each value is read in the source.

**The chain's table is read from the binary and written whole.** A chain read from a config file is built field by field on top of zebra's public testnet defaults, so a config that names the network without the whole table is a node on the **public** testnet: wrong magic, wrong genesis, a healthy-looking log, no peer that answers. So the node role runs `zebrad generate` on the binary it installed, copies the network table and the PoW seed peers it prints into `zebrad.toml` with the checkpoint list turned off, prints the three seed-peer lists the binary carries, and reads the written file back against the binary before the node starts. The BFT and state seed peers are left out of the file so the binary's own are used. `roles/crosslink_node/files/chain-params.py` is that reader.

**A replaced network needs a reset.** The Nightly is replaced, not upgraded: a new genesis, a new magic, a renamed state directory. Run `site.yml` first (the new build and its parameters), then `reset.yml` (the old chain's state out). `reset.yml` keeps the seed and puts it back under the new season directory before the node starts, because zebrad replaces a missing seed at random and never says so.

**A release may rename the state directory.** zebrad keeps its state and its seed under a season-named directory it appends to `cache_dir` at config load (`crosslink_featurenet_20260929_staking3d` on v15). A release that renames it would start the node with a fresh seed, a new identity and a new wallet. The node role reads the name out of the source it is about to build and copies the seed there first, on every run. With `zebrad_install_mode: copy` there is no source to read; the run says so, and the copy is yours to make.

## Mining

Add the host to the `miner` group. That is all. `crosslink_miner_threads` sets how many equihash solvers run in parallel: each is one core and 144 MB on its own nonce range, so blocks arrive about that many times as often. One is upstream's default; a host with cores to spare sets it to the cores minus two. `crosslink_miner_low_priority` (true) keeps the solvers from starving the node.

```yaml
miner:
  hosts:
    miner-1:
      ansible_host: 203.0.113.30
      crosslink_identity_seed: "6b1e0d9c4a7f2e35c8d1b0a9f3e7c642"   # openssl rand -hex 16; this one is refused, make your own
      crosslink_miner_threads: 6
      # crosslink_miner_address: "tm…"      # optional. Default: the miner's own wallet
      # crosslink_miner_extra_coinbase_data: "example.org"
```

Facts about the internal miner, from the source:

| fact | source |
|---|---|
| Solvers run at low priority, 144 MB each | `ThreadPriority::Min`, `zebrad/src/components/miner.rs` |
| Mining starts only when the node is synced | `getblocktemplate` fails until `check_synced_to_tip` |
| No port, no pool | the miner calls the RPC in-process |
| Rewards spendable 2 blocks later (Zcash: 100) | `MIN_TRANSPARENT_COINBASE_MATURITY = 2`, `zebra-chain/src/transparent.rs`; `crosslink_coinbase_maturity` |
| The binary's own default turns the miner on | `crosslink_default()`, `zebrad/src/config.rs`. The playbook writes `internal_miner = false` on a host that is not a miner |
| A build without the miner runs but never mines | the role checks the binary for a miner marker |

### The miner's own wallet

A miner mines to a wallet of its own. On the first start zebrad creates `secret.seed` at random in the season directory and derives the payout address from it. The playbook takes the path from the node's log and never computes it. It writes no seed and picks no address: the host makes its own. The key bundle copies the seed off every miner on every run and writes it as 24 words. Those words are the wallet: restore them in any wallet to spend the rewards.

The seed is the only key. zebrad creates a new random one whenever the file is missing, so a resync that removes it changes the payout address and strands earlier rewards. Keep the bundle. To pay rewards somewhere else instead, set `crosslink_miner_address`; then the host holds no money.

### Rewards shielded

zebrad takes any address of the chain as `miner_address`. A unified address with an Orchard receiver is paid its reward as one shielded note a block. The headless wallet has a unified address of its own, derived from the same seed, printed at start. Set, under the host:

```yaml
crosslink_disable_wallet: false
crosslink_miner_shielded: true
```

The run reads that address off the node and writes it as `miner_address`; on a host whose node has never run it writes the config once without it, starts the node, reads the address the wallet prints and writes the config again. Nothing is derived on your machine: only what the node said is written. A stake from such a wallet spends those notes, so the chain shows no address it was paid from. What the wallet received in total is then not on the chain to read; `rewards.yml` reports what it holds now.

### The miner's rewards

```bash
ansible-playbook -i inventory.yml rewards.yml              # every miner
ansible-playbook -i inventory.yml rewards.yml -l miner-1   # one
```

Read-only. One line per host: received in total, balance now and how much of it is spendable, the last 24 hours, the newest reward. The script behind it, `roles/node_identity/files/rewards.py`, is standard library only and works from any synced node:

```bash
python3 roles/node_identity/files/rewards.py --rpc http://127.0.0.1:8232/ tm…
```

## Finalizer

Add the host to the `finalizer` group and run `site.yml`. Then read the address stake goes to:

```bash
grep finalizer_address ~/crosslink-node-keys/finalizer-1/identity.json
```

That address, `zfinv1` and 128 characters, is the whole capability a delegator stakes to: the node's BFT key and its signature over that key. Stake to it from any Crosslink wallet, and the node takes a seat at the next height it qualifies for. Three things to know:

- **The active roster is capped.** Only the largest few finalizers by stake vote at any height (12 on the Feature Net); the rest hold stake, sign nothing and earn no commission.
- **One node per identity.** Two nodes started from one seed are two signers on one key: that is equivocation. Restore a seed onto a second host only after the first is stopped. `restore.yml` refuses a finalizer for the same reason.
- **The seed is the payout wallet too** when the host also mines and no payout address is set. One file, two jobs. Back it up.

**To stake from the host itself, the headless wallet has to be on.** It is off by default, and the staking RPC funnels through it. Set `crosslink_disable_wallet: false` under the host **in the inventory**, not in the config file on the host: the next run rewrites that file. The wallet derives from the same seed the rewards are paid to, so on a mining host the miner funds the staker. Staking from a wallet elsewhere needs none of this.

With the wallet on, the run installs `crosslink-stake` (below). To stake by itself, set `crosslink_autostake_to` to the finalizer address: the run installs the script's own timer, a pass every `crosslink_autostake_every_minutes` (30) that stakes everything but 1 cTAZ once `crosslink_autostake_min` (10) has gathered. `crosslink_autostake_dry_run: true` runs every check and sends nothing. An empty address removes the timer. The playbook never stakes; the timer on the host does.

A node restart under a stake pass loses the stake the wallet is building. So on every run the node role holds the timer, waits for a pass in flight to end, restarts the node then, waits for its RPC, and resumes the timer.

`WALLET TREE ROOT MISMATCH` in the log is expected with the wallet on, one line per sync pass. It compares the wrong tree and means nothing. `WALLET TREE DESYNC` is the real one: restart the node once it is synced.

## The two scripts on every host

Both are Python, standard library only, installed by `site.yml`. `crosslink-check` goes on every node host; `crosslink-stake` on a host with the wallet on, and is removed when the wallet goes off. Both read the node's own config (`/etc/crosslink/zebrad.toml`), its journal and `/etc/crosslink/chain.env`, and both also run against a node this playbook did not build: `CROSSLINK_CHECK_CONFIG` / `CROSSLINK_STAKE_CONFIG` name the config, `CROSSLINK_CHECK_LOG` / `CROSSLINK_STAKE_LOG` the log files (joined by `:`, read instead of the journal), `CROSSLINK_CHECK_USER_UNIT` / `CROSSLINK_STAKE_USER_UNIT` a `systemctl --user` unit, `CROSSLINK_CHAIN_ENV` a copy of `chain.env`. [docs/scripts.md](docs/scripts.md) has the whole story.

### crosslink-check

```bash
sudo crosslink-check              # one screen
sudo crosslink-check --roster     # the same, with every finalizer on the roster
sudo crosslink-check --json       # everything as JSON, for a script
sudo crosslink-check --no-color   # no colour (also NO_COLOR=1, or not a terminal)
```

Is this host working? One screen, read from the host, changing nothing. In order: the services and how long they have been up · the node's height against its estimate of the tip, synced or how far behind, and the block rate since the last run · peers · finality: activated, the finalized height, the gap, the roster and its stake · whether this host's finalizer address is on the roster and at what rank · the miner, its payout address and that address's balance · whether the headless wallet has started and read the payout address to the tip, what it can spend, and whether its tree has diverged · the stakes this wallet holds, per finalizer, and whether `crosslink-stake --all` would go ahead now, in what pieces · whether the stake timer's last pass failed. Green is fine, yellow is wait or look, red is act. Run it twice a minute apart to see the block rate.

### crosslink-stake

```bash
sudo crosslink-stake --to <zfinv1…> --all --dry-run     # every check, nothing sent
sudo crosslink-stake --to <zfinv1…> --all               # stake all but 1 cTAZ; asks first
sudo crosslink-stake --to <zfinv1…> --amount 100        # stake 100 cTAZ
sudo crosslink-stake --to <zfinv1…> --all --wait        # wait for Staking Day, then ask
sudo crosslink-stake --to <zfinv1…> --timer install     # stake by itself from now on
sudo crosslink-stake --timer status                     # next run, last run, last stake
sudo crosslink-stake --timer remove                     # stop
```

Stakes this host's mining rewards to a finalizer. The one thing in this repository that spends. It stops at the first check that fails: the wallet is off or has not started · the node is not synced or not on the network's chain · an earlier stake of its own is not in a block yet · the address does not decode · Staking Day is closed or closing (15 blocks to spare) · the wallet has not read the chain to the tip · the amount is not there. It shows the stake, asks once, sends, writes the node's reply to `/var/lib/crosslink-stake/` before reading it, and ledgers every attempt. Every stake is a power of 10 cTAZ, the only amount the v15 wallet takes: `--all` goes as pieces of 1, 10, 100, 1,000 cTAZ, largest first, none over `--batch` (1,000) and none under `--min`. When the wallet refuses, the script reads the wallet's reason back from the node's log and prints it. Exit 0: sent, or nothing to stake. Exit 1: a check stopped it. Exit 3: no reply in time; the stake may still land, and the script never sends again by itself.

`--timer install` writes a systemd service and timer that run it with `--auto` every 30 minutes (`--every`): every check on every pass, a closed Staking Day ends the pass quietly, `--min` keeps the bonds few. The playbook runs the same install when the inventory sets `crosslink_autostake_to`.

## Key bundle

After each run the `node_identity` role writes one directory per node on your machine, under `crosslink_keys_dir` (`~/crosslink-node-keys`, mode 0700, outside the repository):

```
~/crosslink-node-keys/
  README.md          what to do with these files
  FLEET.md           every host with a directory here, in one table
  miner-1/
    secret.seed      the seed, 32 bytes, as on the host     PRIVATE
    seed.hex         the seed as hex                        PRIVATE
    mnemonic.txt     the seed as 24 BIP-39 words            PRIVATE
    identity.json    ref, commit, ports, payout address, finalizer address, seed fingerprint
    NODE-CARD.md     the same in prose, with restore steps
    rewards.json     what the payout address had received, written by rewards.yml
  rpc-1/
    identity.json    the record only
    NODE-CARD.md
```

A miner's and a finalizer's seed is copied; an RPC node's is not. The role never overwrites a bundled seed with a different one: a different seed on the host means the node was started without its seed and now has a new identity, and the run stops and says which seed is which. Everything in the record is read from the host: the payout address, the advertised address, the finalizer address and the seed path from the node's log, the commit from git.

Every node host also gets `/etc/crosslink/README.md`: its role, every file the playbook put there, the payout address, the seed's fingerprint, the ports, the checks and the rebuild steps. No secrets.

`tools/seed-tool.py` converts a seed offline (`mnemonic`, `hex`, `fingerprint`; `--selftest` checks it against the BIP-39 vectors). **Back the bundle up somewhere else and encrypt it.**

## Hard fork rules

A user-led hard fork rule terminates finalizers: at its PoW height every bond pointing at them is burned, and from its BFT height votes are signed under a new namespace. **Every node on the network needs the rule**, RPC nodes and miners too. A node without it leaves the network at the PoW height and carries on alone; its tip still climbs, so it looks healthy.

```yaml
crosslink_hardforks:
  - pow_activation_height: 228096
    bft_certificate_height: 2158
    terminated_finalizers:
      - "b8c5272fe6d34980ba6e8aa88d65a6cbf3daabaabea80bdd51a5a5d3bce30c9e"
```

Copy a published rule exactly, keys in the order the rule writes them, and run `site.yml` on every node host **well before the PoW height**: the node reads the rule only at start. The node role refuses a malformed rule and a rule whose PoW height is within `crosslink_hardfork_margin` (600) blocks of the node's tip; a node that is already past the height is on its own branch and needs `restore.yml`. The rules the binary ships are applied by zebrad itself and are not written; `crosslink_disable_shipped_hardforks: true` ignores them, for a private test network that writes its whole schedule by hand.

## Restore

```bash
ansible-playbook -i inventory.yml restore.yml -l rpc-1 \
  -e restore_confirm=rpc-1 \
  -e restore_url=https://<explorer>/snapshots/<file>.tar.zst \
  -e restore_sha256=<sha256>                                   # 1. the state in
ansible-playbook -i inventory.yml site.yml -l rpc-1            # 2. the node started (a miner: -e crosslink_mining_hold=true)
sudo crosslink-check                                           # 3. on the host: wait for the tip
ansible-playbook -i inventory.yml site.yml -l rpc-1            # 4. a miner: mining on again
```

It checks the seed and the free space, downloads and verifies the snapshot, unpacks it, checks it holds this build's season directory, stops the node, moves the old `state/`, `pos.chain` and `non_finalized_state/` aside and the snapshot's pair in. The seed and every other file stay where they are. The node stays stopped. Community explorers publish snapshots with a sha256 and the height they were taken at; the snapshot must be from before the block the node went wrong at.

## Metrics

zebrad serves its own Prometheus metrics when `[metrics] endpoint_addr` is set: tip height, distance to the tip, peers, mempool, RPC latency, value pools, RocksDB. The scraper and the dashboards are not part of this playbook. Switch it on per host:

```yaml
miner-1:
  crosslink_metrics_listen: "0.0.0.0:9999"
  crosslink_metrics_allow_from: ["203.0.113.5"]   # the scraper; a CIDR range works too
```

The port opens in ufw to the listed addresses and to nobody else. With no address listed, or without ufw, the bind address is the only guard: bind loopback or a private interface then.

## After the run

```bash
sudo crosslink-check                                            # is it working? one screen
cat /etc/crosslink/README.md                                    # what this host runs
cat /etc/crosslink/zebrad.toml                                  # the config the playbook wrote
systemctl status crosslink-node
journalctl -u crosslink-node -f                                  # sync
journalctl -u crosslink-node -f | grep -E 'mining|template'      # mining
curl -s -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"getblockcount","params":[]}' \
  http://127.0.0.1:8232/                                         # RPC
curl -s http://127.0.0.1:8234/ready                              # "ok" at the tip, or the reason
ansible-playbook -i inventory.yml rewards.yml                    # what the miners earned
```

The RPC needs the whole envelope: without `content-type: application/json` the node answers "Supplied content type is not allowed", and without `jsonrpc` and `id` it answers a parse error. [docs/CALLS.md](docs/CALLS.md) has the calls an operator runs by hand: the fork test, Staking Day, the viewing key, staking positions, a stake.

## Safety rules

- **A node this playbook did not install is never a target.** The preflight refuses hosts on `forbidden_hostnames` and hosts already running `zebrad`. List every hand-built finalizer on `forbidden_hostnames`, by inventory name or hostname, and keep it out of the inventory.
- **No key is ever written to a host.** No `explicit_bft_key_seed`, on any host, in any group. A node's identity is its own seed file.
- **Nothing here stakes on its own authority.** `crosslink-stake` runs by hand or on the timer the inventory asked for. The playbook installs it and never runs it.
- **A destructive playbook names its host.** `reset.yml` and `restore.yml` need `-e <playbook>_confirm=<host>` equal to the host, so a wide limit stops instead of wiping a fleet.
- **The key bundle stays outside the repository**, and the real inventory is gitignored.

## Layout

```
site.yml                    plays: preflight, node, identity
rewards.yml                 what each miner has earned; read-only
reset.yml                   wipes a node's chain state, keeps its seed
restore.yml                 rebuilds a node's chain state from a snapshot, keeps its seed
inventory.example.yml       copy to inventory.yml
group_vars/all/main.yml     every setting, with its default
requirements.yml            the collections (community.general)
check-templates.py          every template variable is defined; run before a change ships
roles/preflight             safety and inventory checks
roles/crosslink_node        fetch, build, configure, run the node; the two scripts
roles/crosslink_node/files/chain-params.py   the chain's parameters, read out of the binary
roles/crosslink_node/files/crosslink-check   is this host working?
roles/crosslink_node/files/crosslink-stake   stake the host's rewards
roles/crosslink_node/tasks/hardforks.yml     the hard fork rules, checked before zebrad.toml is written
roles/node_identity         read the node, copy its seed, read the rewards, write the record and the host summary
roles/node_identity/files/rewards.py         the rewards read, from any node's RPC
tools/seed-tool.py          secret.seed as its BIP-39 phrase; stdlib, offline, self-testing
docs/zebrad-toml.md         every key the node software reads, and the variable that writes it
docs/scripts.md             crosslink-check and crosslink-stake in full
docs/CALLS.md               the RPC calls an operator runs by hand
CLAUDE.md                   for an AI agent working in this repository
CONTRIBUTING.md             issues, pull requests, the gate, what will not be merged
SECURITY.md                 what this repository is responsible for, and how to report
```

## Terms

| term | meaning |
|---|---|
| host | a machine the playbook targets |
| control machine | the machine that runs `ansible-playbook` |
| node | a Crosslink full node (`zebrad`) installed by this playbook |
| RPC node | a node in the `node` group and no other: its RPC on loopback, no mining, no stake |
| miner | a node in the `miner` group; the internal miner is on |
| finalizer | a node whose BFT key carries stake. In the `finalizer` group it is one this playbook installed; on `forbidden_hostnames` it is one the playbook must never touch |
| finalizer address | the `zfinv1…` string stake is sent to: a node's BFT key and its signature over that key. Public. Read from the node's log |
| network | the chain a host joins: `featurenet` or `nightly`. One inventory file, one network |
| seed | `secret.seed` in the season directory under the data dir, 32 bytes; the node's identity. Its path is read from the node's log |
| season directory | the directory zebrad appends to `cache_dir` at config load; named by the release |
| payout address | the address mining rewards are paid to |
| own wallet | the wallet zebrad makes from a node's seed at first start; where rewards go unless a payout address is set |
| rewards | the coinbase outputs paid to the payout address. "received" is the lifetime total, "balance" what is still unspent |
| ref | a git tag, branch or commit |
| key bundle | the per-host directory written on the control machine |
| host summary | `/etc/crosslink/README.md` on a node host: what it runs and where every file is. No secrets |
| hard fork rule | a `[[crosslink.hardforks]]` entry: a PoW height, a BFT height and the keys it terminates |
| snapshot | a published archive of a node's chain state (`state/` and `pos.chain`), without a seed |
| Staking Day | the blocks of each staking period in which a stake, an unstake or a withdraw is accepted |

## License

MIT. Crosslink and zebrad are Shielded Labs' and the Zcash Foundation's work under their own licenses; this repository only builds and runs them.
