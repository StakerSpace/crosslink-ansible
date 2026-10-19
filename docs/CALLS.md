# Operator calls

The calls an operator runs by hand on a node host. Each block is ready to paste. Every call here only reads, except **Stake**, which spends the host's coins. On a host with the wallet on, `sudo crosslink-stake` makes that call with its checks around it.

## Run a call

On the host, define `rpc` once per shell:

```bash
rpc() { curl -s -H 'content-type: application/json' \
  -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$1\",\"params\":${2:-[]}}" \
  http://127.0.0.1:8232/; echo; }
```

The node's RPC listens on loopback only (`crosslink_rpc_listen`). It needs no password.

From the control machine, wrap the same `curl` in an ad-hoc command:

```bash
ansible -i inventory.yml miner-1 -m ansible.builtin.shell -a \
  "curl -s -H 'content-type: application/json' -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"getblockcount\",\"params\":[]}' http://127.0.0.1:8232/"
```

Amounts are zatoshis. 1 cTAZ is 100,000,000.

## Check the host

```bash
sudo crosslink-check                         # one screen: services, sync, peers, finality, miner, wallet, stakes
rpc getblockcount                            # the node's height
rpc get_tfl_final_block_height_and_hash      # the last finalized block
rpc get_tfl_roster_zats                      # every finalizer stake points at, with its stake
rpc get_tfl_recency_status                   # this node's voting status and each finalizer's
curl -s http://127.0.0.1:8234/ready          # "ok" at the tip, or the reason
```

Compare the finalized height with a block explorer. They should be within a few blocks.

## Check for a fork

A node on a fork looks healthy. `crosslink-check` can say "synced" and "the finalized block is in this node's chain" while the node mines its own branch. Blocks mined there earn nothing on the real chain.

The test is the block hash at the network's tip, from an explorer that serves it as JSON with `tip` and `tip_hash`. Run it after the node has synced:

```bash
ref=$(curl -s https://<explorer>/api/tip)
h=$(echo "$ref" | python3 -c 'import json,sys;print(json.load(sys.stdin)["tip"])')
want=$(echo "$ref" | python3 -c 'import json,sys;print(json.load(sys.stdin)["tip_hash"])')
have=$(rpc getblockhash "[$h]" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("result"))')
[ "$have" = "$want" ] && echo "same chain at $h" || echo "different block at $h: forked, or still behind"
```

"Still behind" means the node is below the explorer's height. Wait a minute and run it again. `crosslink-stake --reference <that URL>` makes the same test before every stake.

Two more signs, from the node's log:

```bash
# peers: "key@finalized/tip". A fork falls further behind most of them on every line.
sudo journalctl -u crosslink-node --since -5min | grep "new_network: tip height" | tail -1

# the network finalized a block this node does not have
sudo journalctl -u crosslink-node --since -1h | grep -E \
  "de-facto finalized as below reorg height|couldn't find block in any chain|Didn't have hash available for confirmation"

# the node dropped BFT after a reorg it could not follow and runs on as proof of work
sudo journalctl -u crosslink-node --since -1h | grep "BFT is stopped on this node"
```

The warnings also appear while a node syncs, because it has not received the block yet. They mean a fork only when the node's tip matches its peers.

If the node is forked after it caught up: stop mining (a restart does not help, the node has already made its own blocks final), then resync with `reset.yml` or `restore.yml`. Both keep `secret.seed`, so the payout address and the finalizer identity stay the same.

## Staking Day

A new stake, an unstake and a withdraw are accepted only in the first `STAKING_WINDOW_BLOCKS` blocks of every `STAKING_PERIOD_BLOCKS` (3,456 of every 10,368 on the Feature Net; `/etc/crosslink/chain.env` has the host's values), and not below `STAKING_START_BLOCK`. Moving stake to another finalizer works at any time.

```bash
. /etc/crosslink/chain.env
h=$(rpc getblockcount | python3 -c 'import json,sys;print(json.load(sys.stdin)["result"])')
echo "block $h: position $((h % STAKING_PERIOD_BLOCKS)) of $STAKING_PERIOD_BLOCKS, open below $STAKING_WINDOW_BLOCKS"
```

Stake with blocks to spare. A stake sent near the end of the window can land after it closes.

## The own wallet

The own wallet is the wallet zebrad makes from the seed. It receives the rewards, and it is the only thing on the host that can build a stake. It is off by default. Turn it on in the inventory, under the host:

```yaml
crosslink_disable_wallet: false
```

Then run `site.yml -l <host>`. The node restarts. Keep the line in the inventory: a run without it turns the wallet off again. The same run installs `crosslink-stake`; a run with the wallet off removes it.

After a restart the wallet reads the chain from the start for the node's own address. It cannot stake coins it has not read. `crosslink-check` shows how far it has read.

### Viewing key

```bash
rpc get_wallet_ufvk
```

`result` is the unified full viewing key, a string that starts with `uview`. It is `null` until the wallet has started. What it does: it shows every reward, stake and send of the own wallet, past and future; it cannot spend, stake or sign and does not reveal the seed; it cannot be withdrawn. Publish it on a test network only.

### Stakes the wallet holds

```bash
rpc wallet_staking_positions
```

`active` lists the stakes by finalizer with their amounts and reward-inclusive values; `withdrawable` lists unstaked stakes ready to withdraw. `crosslink-check` prints the same with each finalizer's rank.

```bash
rpc wallet_spendable_funds
```

The wallet's own unified address, its shielded notes it can spend now (3 confirmations), the ones too young, the ones a send of its own has consumed, and the tip it has read to.

## Stake

This spends the host's coins. Run it by hand, alone, never inside a longer command.

### With the script

```bash
sudo crosslink-stake --to <zfinv1…> --all --dry-run     # every check, nothing sent
sudo crosslink-stake --to <zfinv1…> --all               # stake all but 1 cTAZ; asks first
sudo crosslink-stake --to <zfinv1…> --amount 100        # stake 100 cTAZ
sudo crosslink-stake --to <zfinv1…> --all --wait        # wait for Staking Day, then ask
```

[scripts.md](scripts.md) says what it checks, what it writes and how its timer works.

### By hand

This is the call the script makes. The reply names the transaction; the bond key is derived by the wallet from the seed, so it is never lost with a reply. A stake's amount must be a power of 10 zats (1, 10, 100, 1,000 cTAZ and so on) from block 55,296 of the Feature Net, and the v15 wallet refuses any other amount before it too.

```bash
umask 077
out=~/bond-$(date -u +%Y%m%dT%H%M%SZ).json
curl -sS --max-time 300 -o "$out" -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"wallet_staking_action","params":[{"CreateNewDelegationBond":{"amount_zats":10000000000,"target_finalizer":"<zfinv1…>"}}]}' \
  http://127.0.0.1:8232/
cat "$out"
```

The same call moves a stake to another finalizer (`RetargetBond`), starts an unstake (`BeginUnbonding`) or withdraws one (`Withdraw`); withdrawing is two steps, the unstake first and the withdraw once `wallet_staking_positions` lists the position as withdrawable. Each is one object with that one key; the v15 release notes list the fields.

- "failed to create staking transaction from notes": the wallet refused to build the stake. It prints the reason in the node's log just before: `journalctl -u crosslink-node --since '-5min' -o cat | grep -E 'stake_ironwood_to_finalizer|tx build'`. "can't afford" means the wallet has not seen the coins yet: wait and try again. "is not a power of 10" means the amount. Ignore a "can't afford 1000015000" line: that is the shared miner wallet trying to shield 10 cTAZ every 15 seconds.
- A timeout does not mean it failed. Check `rpc wallet_staking_positions` before sending it again.

**Check.** The stake appears in `rpc wallet_staking_positions` once its block is read, and the finalizer's stake in `rpc get_tfl_roster_zats` rises by the amount at the next finalized block.

## Rewards

```bash
ansible-playbook -i inventory.yml rewards.yml -l miner-1     # received, balance, spendable, last 24 hours
```

On the host, the host summary carries a `curl` for `getaddressbalance`: `cat /etc/crosslink/README.md`.
