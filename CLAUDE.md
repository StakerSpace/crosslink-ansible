# CLAUDE.md

Guidance for an AI agent working in this repository. Read it before changing anything, then `README.md` and the last ten commits.

## What this is

Ansible playbooks that build and run Crosslink nodes (RPC nodes, miners, finalizers) from the official node software, [ShieldedLabs/crosslink_monolith](https://github.com/ShieldedLabs/crosslink_monolith), on the Crosslink Feature Net, a test network with a test coin (cTAZ). Plus two host scripts: `crosslink-check` (is this host working?) and `crosslink-stake` (stake the host's rewards). Nothing else: no dashboard, no database, no explorer.

Layout, what each piece does and the terms are in `README.md`. Every config key the node reads is in `docs/zebrad-toml.md`; the two scripts are in `docs/scripts.md`; the RPC calls in `docs/CALLS.md`.

## Rules that are not negotiable

- **Never write a key to a host.** No `explicit_bft_key_seed` in any template, task or default, for any group. A node's identity is its own `secret.seed`; the playbook reads it, copies it to the key bundle, carries it across a season rename, and never creates or replaces one.
- **Never target a node the playbook did not install.** The preflight refuses hosts on `forbidden_hostnames` and hosts already running `zebrad`. Do not weaken those checks or add a way around them.
- **Nothing stakes on its own authority.** `crosslink-stake` runs by hand or on the timer the inventory asked for (`crosslink_autostake_to`). The playbook installs it and never runs it. Do not add a task that calls it.
- **A destructive playbook names its host.** `reset.yml` and `restore.yml` need `-e <name>_confirm=<host>` equal to the host. Keep that; a wide limit must stop, not wipe a fleet.
- **The chain comes out of the binary, never from this tree.** Seed peers, magic, genesis, parameters: `zebrad generate` through `roles/crosslink_node/files/chain-params.py`, read on the host at deploy time. Do not type a chain's values into `group_vars`. The chain rows in `crosslink_chains` hold only the ref and the staking calendar the host scripts read.
- **Nothing identifying.** No host names, IP addresses, addresses, keys, seeds, phrases or paths from a real machine in a committed file. `inventory.yml` and the key bundle are gitignored; keep them so. Example addresses are from 203.0.113.0/24 and 198.51.100.0/24.
- **Ground a protocol claim in the source.** When a comment or doc says what the node does, cite the file (`zebrad/src/config.rs`, `zebra-rpc/src/config/mining.rs`, …) at the tag the default row builds. `docs/zebrad-toml.md` was read at v15; re-read it at the next tag before changing a default.

## Before a change ships

```bash
ansible-galaxy collection install -r requirements.yml
for p in site.yml reset.yml restore.yml rewards.yml; do
  ansible-playbook -i inventory.example.yml --syntax-check "$p"; done
python3 check-templates.py       # must print "0 templates with undefined variables"
ansible-lint                     # .ansible-lint holds the skip list, with reasons
python3 -m py_compile roles/crosslink_node/files/crosslink-check \
  roles/crosslink_node/files/crosslink-stake roles/crosslink_node/files/chain-params.py \
  roles/node_identity/files/rewards.py tools/seed-tool.py
python3 tools/seed-tool.py --selftest
grep -rnE '/home/|[0-9a-f]{64}|zfinv1|secret\.seed' --include='*.yml' --include='*.j2' . | grep -v example
```

`.github/workflows/check.yml` runs the same. A template change also wants a rendered `zebrad.toml` read by eye: render it with a throwaway play against `localhost` and the example inventory, or read the file on a host after `--check --diff`.

## How the tree is organised

- `group_vars/all/main.yml` is the one list of settings. Every variable has a default and a comment there; a new variable goes there first, then into the template, then into `README.md`'s table if people will set it and into `docs/zebrad-toml.md`'s table if it writes a config key.
- A setting reaches a host as a line in `zebrad.toml`, `chain.env`, the unit or the two scripts' install. There is no `.env` on a host and nothing is edited in place.
- A renamed variable keeps its old name as an alias (`bulk_data_root`, `crosslink_tag`, `featurenet-v14`), so an inventory written earlier keeps working. Do not rename a variable without keeping the old name.
- The roles: `preflight` (safety and inventory checks, every playbook runs it first), `crosslink_node` (fetch, build, configure, run; the two scripts), `node_identity` (read the node, copy the seed, write the record). `rewards.yml` reuses `node_identity`'s `rewards` task file.
- Every git command on a host runs as the service user, the checkout's owner. Never as root, and never `safe.directory` as a workaround.
- Never load a service's journal into a shell variable: a node writes hundreds of megabytes a run and bash dies holding it. Stream it, bound it (`-n`, `head`), stop at the first hit (`journalctl -r -n 1 --grep`).
- A restart is a handler. A handler notified in a run that then fails is dropped, so the node role also asks the running process which binary it is and restarts on a mismatch. Keep both.
- The stake timer is held across a node restart (hold, wait for a pass to end, `flush_handlers`, wait for the RPC, resume). A restart under a pass loses the stake the wallet is building. Keep the order.

## Writing

Plain English. Short sentences. Say what, then why, one line for why; longer explanations go in `README.md` or `docs/`, once. Task names are verb first, sentence case, no full stop ("Write zebrad.toml"). Every template starts with `# Managed by Ansible (crosslink-ansible). Do not edit by hand.` Use the terms in `README.md`'s Terms table and no synonyms: host, control machine, node, RPC node, miner, finalizer, finalizer address, network, seed, season directory, payout address, own wallet, rewards, ref, key bundle, host summary, hard fork rule, snapshot, Staking Day. Not "validator", not "testnet" (the public Zcash testnet is a different chain; this is the Feature Net, a test network), not "observer".

Commit messages say what changed and why in the first line, in the same voice. No model names or tool names in a commit, a comment or a file.

## Facts worth knowing before touching the node role

- The loader fills seven keys a config leaves out from the Feature Net's defaults, and one of them is `mining.internal_miner = true`. A host that is not a miner must have `internal_miner = false` written, or it mines.
- `public_address` is hashed into the node's transport key. Changing it changes the node's transport identity; a wrong one makes the node unreachable while it looks healthy.
- The seed is at `<data dir>/<season directory>/secret.seed`, never at `<data dir>/secret.seed`. The season directory's name comes from `zebrad/src/config.rs` (`.push("…")`) and changes with a release. Missing, zebrad makes a new random one and never says so.
- One node per identity, ever. Two nodes on one seed are two signers on one key: equivocation. `restore.yml` refuses a finalizer for the same reason.
- A finalizer outside the active roster (the largest N by stake, 12 on the Feature Net) holds stake, signs nothing and earns no commission; a finalizer address is still a valid target for stake. The seat is reported, never required.
- A new stake is a power of 10 zats from block 55,296 (v15's network upgrade), and the v15 wallet refuses any other amount at every height. `crosslink-stake` stakes only such pieces on every build.
- Mining starts only when the node is synced. A syncing miner is not broken.
- `crosslink_identity_seed` is hashed (blake3) into the node's state-network key: the same string is the same identity anywhere. It has no default. Examples carry `CHANGE-ME` or the one documented value `6b1e0d9c4a7f2e35c8d1b0a9f3e7c642`, and the preflight refuses both, an empty value and anything under 16 characters; never put a string anyone really uses in an example.
