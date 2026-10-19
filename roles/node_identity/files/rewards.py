#!/usr/bin/env python3
"""What a miner has earned, read from a node's public RPCs.

Asks a node about one transparent address: a miner's payout address. Every
block the miner finds pays its coinbase there, so the address's history is
the mining record. Standard library only. Read-only. Works against the node
on the miner host (RPC on loopback) or against any other synced node.

    rewards.py [--rpc URL] [--maturity N] [--json] ADDRESS

Prints what the address received in total, its balance now and how much of
that is spendable, the last 24 hours by block time, and the newest reward.

Facts this rests on, read in the node's source:

- getaddressbalance returns `balance` and `received` in zatoshis
  (1 cTAZ = 10^8), and `received` is the lifetime total.
- getaddresstxids returns txids in chain order (zebra-state builds a
  BTreeMap keyed by transaction location), so the last one is the newest.
- A coinbase output is spendable MIN_TRANSPARENT_COINBASE_MATURITY blocks
  after its block. zebra-chain/src/transparent.rs sets it to 2 on the
  feature-net (Zcash: 100); zebra-state/src/service/check/utxo.rs reads it.
- A transaction paying this address is a coinbase unless someone sent to
  it. The script checks the ones it opens and counts any that is not.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

ZAT = 10 ** 8
DAY = 86400


class Rpc:
    def __init__(self, url, timeout=30):
        self.url = url
        self.timeout = timeout

    def __call__(self, method, params=None):
        body = json.dumps({"jsonrpc": "1.0", "id": "rewards", "method": method,
                           "params": params or []}).encode()
        req = urllib.request.Request(self.url, data=body,
                                     headers={"content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            reply = json.loads(r.read().decode())
        if reply.get("error"):
            raise RuntimeError(f"{method}: {reply['error']}")
        return reply["result"]


def ctaz(zats):
    return f"{zats / ZAT:,.2f}"


def iso(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def paid_to(tx, address):
    """Zatoshis this transaction pays to the address."""
    total = 0
    for out in tx.get("vout") or []:
        if address in (out.get("scriptPubKey", {}).get("addresses") or []):
            total += out.get("valueZat", 0)
    return total


def is_coinbase(tx):
    vin = tx.get("vin") or []
    return len(vin) == 1 and "coinbase" in vin[0]


def blocks_per_second(rpc, tip):
    """From two headers. Bounds the height range for the 24-hour window."""
    span = min(1000, tip)
    if span < 10:
        return 1 / 75
    newer = rpc("getblockheader", [str(tip), True])["time"]
    older = rpc("getblockheader", [str(tip - span), True])["time"]
    return span / max(newer - older, 1)


def read(rpc, address, maturity, day_max):
    tip = rpc("getblockcount")
    balance = rpc("getaddressbalance", [{"addresses": [address]}])
    utxos = rpc("getaddressutxos", [{"addresses": [address]}])
    txids = rpc("getaddresstxids", [{"addresses": [address]}])

    # A coinbase at height h can be spent from height h + maturity. The next
    # block is tip + 1.
    immature = [u for u in utxos if u["height"] + maturity > tip + 1]
    immature_zats = sum(u["satoshis"] for u in immature)

    out = {
        "address": address,
        "read_at": iso(time.time()),
        "tip": tip,
        "received_zats": balance["received"],
        "balance_zats": balance["balance"],
        "spendable_zats": balance["balance"] - immature_zats,
        "immature_zats": immature_zats,
        "immature_outputs": len(immature),
        "unspent_outputs": len(utxos),
        "transactions": len(txids),
        "maturity_blocks": maturity,
        "newest": None,
        "day": None,
    }

    if txids:
        newest = rpc("getrawtransaction", [txids[-1], 1])
        height = newest.get("height")
        out["newest"] = {
            "height": height,
            "time_utc": iso(newest["blocktime"]) if newest.get("blocktime") else "",
            "blocks_ago": (tip - height) if isinstance(height, int) else None,
            "zats": paid_to(newest, address),
            "coinbase": is_coinbase(newest),
        }

        # The last 24 hours by block time. Ask for a height range wide enough
        # to hold a day at the measured block rate, open the newest first and
        # stop at the first one older than a day.
        since = time.time() - DAY
        rate = blocks_per_second(rpc, tip)
        start = max(0, tip - int(DAY * rate * 1.5) - 10)
        recent = rpc("getaddresstxids", [{"addresses": [address], "start": start, "end": tip}])
        blocks = 0
        zats = 0
        other = 0
        other_zats = 0
        opened = 0
        capped = False
        for txid in reversed(recent):
            if opened >= day_max:
                capped = True
                break
            tx = rpc("getrawtransaction", [txid, 1])
            opened += 1
            if tx.get("blocktime", 0) < since:
                break
            if is_coinbase(tx):
                blocks += 1
                zats += paid_to(tx, address)
            else:
                other += 1
                other_zats += paid_to(tx, address)
        out["day"] = {
            "blocks": blocks,
            "zats": zats,
            "other_payments": other,
            "other_zats": other_zats,
            "opened": opened,
            "capped": capped,
            "range_start": start,
        }

    out["text"] = text(out)
    out["summary"] = summary(out)
    return out


def text(o):
    """Formatted figures for the record templates."""
    t = {
        "tip": f"{o['tip']:,}",
        "received": ctaz(o["received_zats"]),
        "balance": ctaz(o["balance_zats"]),
        "spendable": ctaz(o["spendable_zats"]),
        "immature": ctaz(o["immature_zats"]),
        "transactions": f"{o['transactions']:,}",
    }
    n = o["newest"]
    if n:
        t["newest"] = (f"block {n['height']:,}, {n['time_utc']}, {n['blocks_ago']:,} blocks ago, "
                       f"{ctaz(n['zats'])} cTAZ" + ("" if n["coinbase"] else " (not a coinbase)"))
    else:
        t["newest"] = "none yet"
    d = o["day"]
    if d:
        t["day"] = (("at least " if d["capped"] else "") + f"{d['blocks']:,} blocks, {ctaz(d['zats'])} cTAZ"
                    + (f" (and {d['other_payments']} other transactions: spends from the address, "
                       f"or {ctaz(d['other_zats'])} cTAZ paid in)"
                       if d["other_payments"] else ""))
    else:
        t["day"] = "none"
    return t


def summary(o):
    t = o["text"]
    return (f"received {t['received']} cTAZ in {t['transactions']} transactions; "
            f"balance {t['balance']} (spendable {t['spendable']}); "
            f"last 24h {t['day']}; newest {t['newest']}")


def print_plain(o):
    t = o["text"]
    print(f"{o['address']}  tip {o['tip']:,}  read {o['read_at']}")
    print(f"received   {t['received']:>16} cTAZ  in {t['transactions']} transactions")
    print(f"balance    {t['balance']:>16} cTAZ  spendable {t['spendable']}, immature {t['immature']} "
          f"({o['immature_outputs']} outputs; maturity {o['maturity_blocks']} blocks)")
    print(f"last 24h   {t['day']}")
    print(f"newest     {t['newest']}")
    print("A transaction paying this address is a coinbase unless someone sent to it.")


def main(argv):
    p = argparse.ArgumentParser(description="What a miner has earned, from a node's public RPCs.")
    p.add_argument("address", help="the payout address (t…)")
    p.add_argument("--rpc", default="http://127.0.0.1:8232/", help="node RPC URL (default: loopback)")
    p.add_argument("--maturity", type=int, default=2,
                   help="blocks before a coinbase can be spent (feature-net 2, Zcash 100)")
    p.add_argument("--day-max", type=int, default=5000,
                   help="most transactions to open for the 24-hour figure")
    p.add_argument("--json", action="store_true", help="print JSON")
    a = p.parse_args(argv)

    if not a.address.startswith("t"):
        print(f"{a.address} is not a transparent (t…) address", file=sys.stderr)
        return 2
    try:
        out = read(Rpc(a.rpc), a.address, a.maturity, a.day_max)
    except (urllib.error.URLError, OSError) as e:
        print(f"cannot reach the node at {a.rpc}: {e}", file=sys.stderr)
        return 2
    except RuntimeError as e:
        print(f"the node refused: {e}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(out))
    else:
        print_plain(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
