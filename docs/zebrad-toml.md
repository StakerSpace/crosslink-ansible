# zebrad.toml, key by key

Every key the Crosslink node software (`zebrad`, [crosslink_monolith v15](https://github.com/ShieldedLabs/crosslink_monolith/releases/tag/v15)) reads from its config file, what it does, its default, and the playbook variable that writes it. Read against the v15 source: `zebrad/src/config.rs`, `zebra-crosslink/src/lib.rs` (the `config` module), `zebra-network/src/config.rs`, `zebra-state/src/config.rs`, `zebra-rpc/src/config/{rpc,mining}.rs`, `zebra-consensus/src/config.rs`, `zebrad/src/components/{health,metrics,sync,mempool,tracing,notify,zcashd_compat}`.

The playbook writes `/etc/crosslink/zebrad.toml` from `roles/crosslink_node/templates/zebrad.toml.j2`. A key with no variable is written with the value in the "playbook writes" column, or not at all; put anything else in `crosslink_extra_toml`, which goes at the end of the file verbatim. The file is `deny_unknown_fields`: a misspelled key stops the node at start.

Two things to know before any key:

1. **Unset is not "zebra's default" for seven keys.** The loader (`ZebradConfig::load`) fills a key the file does not name from `crosslink_default()`, the Feature Net's own defaults: `network.network` (the chain), `crosslink.bft_peers`, `network.initial_testnet_peers`, `state.network_initial_peers` (the three seed peer lists), `mempool.debug_enable_at_height` (0), **`mining.internal_miner` (true)**, `rpc.listen_addr` (`127.0.0.1:8232`) and `rpc.enable_cookie_auth` (false). So a config without a `[mining]` section **mines**. The playbook writes `internal_miner = false` on every host that is not in the `miner` group.
2. **The season directory.** At every load zebrad appends `crosslink_featurenet_20260929_staking3d` (on v15) to `state.cache_dir`. The state, the BFT store and `secret.seed` live under it. The name is the release's; a release that renames it starts the node on an empty state with a fresh seed unless the seed is carried there first, which the node role does on every run.

`zebrad generate` prints a build's fully resolved defaults as a config file. The node role runs it on the binary it installed; it is also the quickest way to see what a build carries.

## `[consensus]`

| key | default | what it does | playbook writes |
|---|---|---|---|
| `checkpoint_sync` | `true` | follow the checkpoint list while syncing. Required checkpoints are always on; this adds the optional ones | `true` |

## `[crosslink]`

| key | default | what it does | playbook variable |
|---|---|---|---|
| `public_address` | none | `"ip:port"` the BFT overlay binds **and** advertises. zebrad hashes the string into the node's transport key, so changing it changes the node's transport identity. Must be public and stable; behind NAT, the router's address with the UDP port forwarded | `crosslink_public_ip` + `crosslink_bft_overlay_port` (12301) |
| `bft_peers` | the binary's three Feature Net hosts | bootstrap peers for the BFT overlay, same format. A bootstrap list, not a dial set: peers then exchange signed attestations. Positional against the roster | not written: the binary's own are used |
| `explicit_bft_key_seed` | none | a string to derive the finalizer key from instead of `secret.seed` | **never written.** The playbook puts no key on any host |
| `disable_the_headless_wallet` | `false` | the headless wallet off. The wallet is what builds and funds a staking transaction; on it reads the whole chain for the node's own address and prints `USER WALLET ADDRESS:` at start | `crosslink_disable_wallet` (true: the playbook's default is off) |
| `disable_zaino` | `false` | the light wallet server (Zaino) off | `crosslink_disable_zaino` (true) |
| `[[crosslink.hardforks]]` | none | user-led hard fork rules, each `pow_activation_height`, `bft_certificate_height`, `terminated_finalizers` (a list of 64-hex keys). Merged with the shipped rules and validated at load; a bad schedule stops the node | `crosslink_hardforks` |
| `disable_shipped_hardforks` | `false` | ignore the rules compiled into the binary and apply only `hardforks`. For a private test network | `crosslink_disable_shipped_hardforks` |

## `[mining]`

| key | default | what it does | playbook variable |
|---|---|---|---|
| `internal_miner` | `false` in zebra, **`true` for Crosslink when the key is absent** | run the built-in equihash miner. It starts only once the node is synced, uses no port and no pool | `true` in the `miner` group, `false` elsewhere; `crosslink_mining_hold: true` writes `false` on a miner |
| `internal_miner_threads` | `1` | parallel solvers, one core and 144 MB each on its own nonce range; clamped to the host's cores. Blocks arrive about N times as often | `crosslink_miner_threads` |
| `internal_miner_low_priority` | `true` | solvers at the lowest OS priority. On a saturated host a solver then gets what is left over; a test network that wants blocks fast turns it off | `crosslink_miner_low_priority` |
| `miner_address` | none | where the coinbase pays. Any address of the chain: a transparent `t…` address, or a unified address with an Orchard receiver (then the reward is one shielded note a block). Unset, the node derives a transparent address from `secret.seed` and logs `Mining to t…` | `crosslink_miner_address`, or the wallet's own unified address read off the node with `crosslink_miner_shielded: true` |
| `extra_coinbase_data` | none | text appended to every coinbase this node builds, after zebra's marker. Public and permanent; about 95 bytes at most | `crosslink_miner_extra_coinbase_data` |
| `miner_memo` | none | a memo (512 bytes) in the shielded coinbase output; only with a shielded `miner_address` | `crosslink_extra_toml` |

## `[network]`

| key | default | what it does | playbook variable |
|---|---|---|---|
| `listen_addr` | `[::]:8233` | the p2p listener, `address:port` or `address`. `[::]` takes IPv4 and IPv6 | `crosslink_p2p_listen` |
| `external_addr` | none | the p2p address to advertise when the listener is behind NAT or a load balancer | `crosslink_p2p_external_addr` |
| `network` | the binary's chain | which chain. For Crosslink it is a **table** (`[network.network]` with `network_magic`, `genesis_hash`, `activation_heights`, `funding_streams`, `checkpoints`, …), not the string `"Testnet"`. A file that names the network without the whole table is a node on the public testnet | read out of the binary with `zebrad generate` and written whole, with `checkpoints = false`, by `chain-params.py` |
| `initial_testnet_peers` | the binary's three hosts on 8233 | p2p seed peers. Written beside the table, because a chain that is not the public testnet is refused next to the public DNS seeders, and a list left out of the file *is* the public seeders when that check runs | the binary's, by `chain-params.py` |
| `initial_mainnet_peers` | zebra's DNS seeders | unused on a testnet | not written |
| `cache_dir` | the platform cache dir | where the peer address cache lives (`network/testnet.peers`) | `crosslink_data_dir` |
| `peerset_initial_target_size` | 25 | the target number of peers; also bounds inbound and outbound connections and the cached peer list | `crosslink_peerset_target` |
| `crawl_new_peer_interval` | 61 s | how often to ask peers for more addresses | `crosslink_extra_toml` |
| `max_connections_per_ip` | 1 | connections kept per IP. Above 1 weakens the peer set's security | `crosslink_max_connections_per_ip` |

## `[rpc]`

| key | default | what it does | playbook variable |
|---|---|---|---|
| `listen_addr` | none in zebra; `127.0.0.1:8232` for Crosslink when absent | the JSON-RPC server. Bound to a public address, anyone can query the node and send transactions through it. Keep it on loopback | `crosslink_rpc_listen` |
| `enable_cookie_auth` | `true` in zebra; `false` for Crosslink when absent | require the cookie in `cookie_dir` on every call | `crosslink_rpc_cookie_auth` (false) |
| `cookie_dir` | the cache dir | where the auth cookie is written | `crosslink_extra_toml` |
| `indexer_listen_addr` | none | the indexer gRPC, only in a build with the `indexer` feature | `crosslink_extra_toml` |
| `max_response_body_size` | 52 428 800 | the largest reply, in bytes | `crosslink_extra_toml` |
| `parallel_cpu_threads` | 0 | kept for old configs; does nothing | not written |
| `debug_force_finished_sync` | `false` | say the node is at the tip whatever its state. Test only | not written |

The RPC wants the whole envelope: `content-type: application/json`, and `jsonrpc` and `id` in the body. The node's own calls beyond zebra's: `get_tfl_final_block_height_and_hash`, `get_tfl_roster_zats`, `get_tfl_recency_status`, `get_tfl_fat_pointer_to_bft_chain_tip`, `get_wallet_ufvk`, `wallet_spendable_funds`, `wallet_staking_positions`, `wallet_staking_action`. [CALLS.md](CALLS.md) shows them.

## `[state]`

| key | default | what it does | playbook variable |
|---|---|---|---|
| `cache_dir` | the platform cache dir | the root of the chain state. The season directory is appended at load; the state, the BFT store (`pos.chain`) and `secret.seed` are under it | `crosslink_data_dir` (`/var/lib/crosslink`, or `<crosslink_data_root>/node`) |
| `ephemeral` | `false` | a temporary state, deleted on a clean exit | not written |
| `should_backup_non_finalized_state` | `true` | keep the newest, not yet finalized blocks on disk across restarts (`non_finalized_state/`), written every 5 s at most | not written |
| `delete_old_database` | `true` | delete state directories of an older format at start. `secret.seed` is not touched | `true` |
| `network_identity_seed_string` | none (a fresh random key each start) | the string the node derives its **state network** identity from: `blake3(string)` is the keypair's seed (`zebra-state/src/new_network.rs`), so the same string is the same identity on any machine, forever. Make it random and private; keep it once chosen. Not the BFT identity, not the wallet | `crosslink_identity_seed` |
| `network_local_port` | 0 | the state network's port, TCP and UDP | `crosslink_bft_local_port` (12001) |
| `network_initial_peers` | the binary's three hosts on 12001 | state network seed peers, `[::ffff:ip]:port:<id>:<key>` | not written: the binary's own are used |
| `network_checkpoint` | none | a `{ height, hash }` the synced chain must contain; `height = 0` with `hash = ""` means off | `crosslink_extra_toml` |
| `debug_stop_at_height`, `debug_validity_check_interval`, `debug_skip_non_finalized_state_backup_task` | off | test switches | not written |

## `[health]`

The node's own HTTP health server (`zebrad/src/components/health.rs`). `GET /healthy` is 200 with at least `min_connected_peers` live peers; `GET /ready` is 200 at the tip and 503 with a reason (`syncing`, `lag=N blocks`, `tip_age=Ns`). `crosslink-check` reads it.

| key | default | what it does | playbook variable |
|---|---|---|---|
| `listen_addr` | none (off) | where to serve | `crosslink_health_listen` (`127.0.0.1:8234`; empty turns it off) |
| `enforce_on_test_networks` | `false` | without it `/ready` is 200 on any testnet whatever the state | `true` |
| `min_connected_peers` | 1 | peers needed for `/healthy` | `crosslink_extra_toml` |
| `ready_max_blocks_behind` | 2 | the lag `/ready` tolerates | `crosslink_extra_toml` |
| `ready_max_tip_age` | 5 min | the oldest tip `/ready` tolerates | `crosslink_extra_toml` |

## `[metrics]`

| key | default | what it does | playbook variable |
|---|---|---|---|
| `endpoint_addr` | none (off) | zebrad's Prometheus endpoint, `GET /metrics`: tip height, distance to the tip, peers, mempool, RPC latency, value pools, RocksDB. No finality metric | `crosslink_metrics_listen`; `crosslink_metrics_allow_from` opens the port in ufw to those addresses only |

## `[sync]`

| key | default | what it does | playbook variable |
|---|---|---|---|
| `download_concurrency_limit` | 50 | parallel block downloads. Raise it on a fast link | `crosslink_sync_download_concurrency` |
| `checkpoint_verify_concurrency_limit` | 1000 | blocks in flight to the checkpoint verifier. Lower it to save RAM | `crosslink_extra_toml` |
| `full_verify_concurrency_limit` | 20 | blocks in flight to the full verifier. Raise it on many cores | `crosslink_sync_full_verify_concurrency` |
| `parallel_cpu_threads` | 0 (every core) | threads for signature and proof checks | `crosslink_sync_parallel_cpu_threads` |

## `[mempool]`

| key | default | what it does | playbook variable |
|---|---|---|---|
| `tx_cost_limit` | 80 000 000 | the mempool's total size, in cost units (ZIP-401 `mempooltxcostlimit`) | `crosslink_mempool_tx_cost_limit` |
| `eviction_memory_time` | 1 h | how long an evicted transaction id stays rejected | `crosslink_extra_toml` |
| `debug_enable_at_height` | none in zebra; 0 for Crosslink when absent | enable the mempool from this height regardless of sync status | not written (the binary's 0 applies) |
| `max_datacarrier_bytes` | 83 | the largest standard `OP_RETURN` script | `crosslink_extra_toml` |

## `[tracing]`

| key | default | what it does | playbook variable |
|---|---|---|---|
| `filter` | none (`info` with `-v`, else `warn`) | the log filter, `tracing-subscriber` syntax: `"info,zebra_network=debug"` | `crosslink_log_filter` |
| `log_file` | none (stdout, so the journal) | write the log to a file instead | `crosslink_log_file` |
| `use_journald` | `false` | structured journald fields instead of plain lines | `crosslink_log_use_journald` |
| `use_color`, `force_use_color` | `true`, `false` | colour on a terminal; force it | `crosslink_extra_toml` |
| `buffer_limit` | 128 000 | the log buffer, in lines | `crosslink_extra_toml` |
| `endpoint_addr` | none | the `tracing` filter reload endpoint (a build with the `filter-reload` feature) | `crosslink_extra_toml` |
| `flamegraph` | none | write a flamegraph here on exit | `crosslink_extra_toml` |
| `progress_bar` | none | a progress bar on the terminal (`"summary"` or `"detailed"`) | `crosslink_extra_toml` |
| `opentelemetry_endpoint`, `opentelemetry_service_name`, `opentelemetry_sample_percent` | none | OpenTelemetry export | `crosslink_extra_toml` |

## `[notify]`

| key | default | what it does | playbook variable |
|---|---|---|---|
| `block_notify_command` | none | a shell command run on every new best tip, `%s` replaced by the block hash; detached, never blocks validation, not run during initial sync. Like zcashd's `-blocknotify` | `crosslink_block_notify_command` |

## `[zcashd_compat]`

A sidecar `zcashd` that syncs from this node over the legacy p2p protocol. Off by default and not written by the playbook; all of it goes in `crosslink_extra_toml` if you need it: `enabled`, `manage_zcashd`, `zcashd_source`, `zcashd_path`, `zcashd_datadir`, `zcashd_extra_args`, `p2p_connect_addr`, `block_gossip_peer_ips` (a trusted-peer privilege boundary: list only loopback addresses of a host that runs nothing but zebra and its sidecar).

## `[debug_time_dilation]`

A wall-clock multiplier for fast-forwarding a private test network. Off unless `multiplier` is 2 or more; every node on such a network must carry identical settings. Not written.

## What the playbook renders

An RPC node, from the defaults:

```toml
[consensus]
checkpoint_sync = true

[crosslink]
public_address = "203.0.113.20:12301"
disable_the_headless_wallet = true
disable_zaino = true

[mining]
internal_miner = false

[network]
cache_dir = "/var/lib/crosslink"
listen_addr = "[::]:8233"
max_connections_per_ip = 1
peerset_initial_target_size = 25
initial_testnet_peers = [
    "…",                      # the binary's, read by chain-params.py
]

[network.network]             # the binary's chain, copied whole
checkpoints = false
genesis_hash = "…"
network_magic = [67, 108, 84, 49]
…

[health]
listen_addr = "127.0.0.1:8234"
enforce_on_test_networks = true

[rpc]
enable_cookie_auth = false
listen_addr = "127.0.0.1:8232"

[state]
cache_dir = "/var/lib/crosslink"
delete_old_database = true
network_local_port = 12001
network_identity_seed_string = "6b1e0d9c4a7f2e35c8d1b0a9f3e7c642"
```

A miner adds `internal_miner = true`, `internal_miner_threads`, `internal_miner_low_priority` and, when set, `miner_address` and `extra_coinbase_data`. A host with metrics on adds `[metrics]`; one with a sync, mempool, tracing or notify variable set adds that section; `crosslink_extra_toml` goes last. The node starts as `zebrad -c /etc/crosslink/zebrad.toml start --headless` (the flag skips the visualizer window the node otherwise tries to open; the role asks the binary whether it has the flag).

## The ports

| port | protocol | what | config key |
|---|---|---|---|
| 8233 | TCP | Zcash p2p | `[network] listen_addr` |
| 12001 | TCP + UDP | the state network (blocks and BFT data between Crosslink nodes) | `[state] network_local_port` |
| 12301 | UDP | the BFT overlay (Tenderlink votes) | the port in `[crosslink] public_address` |
| 8232 | TCP, loopback | JSON-RPC | `[rpc] listen_addr` |
| 8234 | TCP, loopback | health | `[health] listen_addr` |
| 9999 | TCP, if set | Prometheus | `[metrics] endpoint_addr` |

The first three face the internet and the node role opens them in ufw; the rest never leave the host unless you say so.
