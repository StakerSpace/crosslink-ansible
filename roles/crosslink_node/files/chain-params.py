#!/usr/bin/env python3
"""The chain a zebrad build carries, as the `[network]` keys that name it.

Reads `zebrad generate` on stdin — the fully-resolved defaults of that exact
binary, which by its own header behave "exactly like running with no config
file at all" — and prints the part of `[network]` that names the chain: the
PoW seed peers, then the network's table and its sub-tables, copied whole,
with the checkpoint list turned off. The node role pastes the output into
zebrad.toml after the `[network]` table's own keys.

Why anything is written at all. A Crosslink testnet that comes from the binary
keeps zebra's PUBLIC testnet checkpoint list: the builder's default sets it
(`ParametersBuilder::default`, zebra-chain), and `to_network()` only checks
that checkpoint 0 equals the genesis hash, which passes because Crosslink
reuses the testnet genesis. Every later checkpoint belongs to another chain.
At startup zebra-consensus walks that list against this node's state and
asserts each hash (`router.rs`, "invalid block in state"), so the first
restart after the chain passes the first checkpoint aborts the process and
systemd restarts it into the same panic. A chain read from a CONFIG FILE takes
whatever `checkpoints` the file says, and `false` is genesis only — which is
why a Feature Net host never sees this.

What `generate` prints. zebra-network writes the network as the string
"Testnet" only when it IS the public testnet, and as a table when it is not
(`From<Config> for DConfig`). A Crosslink chain never is — its magic differs —
so on a build whose default network is Crosslink's the chain comes out as

    [network]
    ...
    [network.network]
    checkpoints = true
    genesis_hash = "…"
    network_magic = [67, 78, 105, 48]
    ...
    [network.network.activation_heights]
    ...

Reading that table back builds the chain from the file, field by field, on
top of the public testnet's defaults (`build_configured_testnet`), so every
field is copied and only `checkpoints` is changed. The older shape — the
string `network = "Testnet"` with a `[network.testnet_parameters]` table — is
read the same way and is kept the same way, name line included: that pairing
is what selects the table, and a `[network.testnet_parameters]` table under a
file that names no network is read as MAINNET.

Why the PoW seed peers are written with it. Reading the table back,
zebra-network refuses a chain that is not the public testnet next to the
public DNS seeders ("cannot use default initials peers with incompatible
testnet"), and `initial_testnet_peers` left out of the file IS the public
seeders at that point: the deserializer fills the key from zebra's own default
before zebrad's fallback to the binary's list can run. So the list is copied
from the same `generate` output, beside the table it belongs to. The BFT and
state peer lists (`crosslink.bft_peers`, `state.network_initial_peers`) have
no such check and stay out, so the binary's own are used.

What it refuses. `network = "Testnet"` with no table means the binary's own
network is the public testnet; "Mainnet" means mainnet. Neither is a Crosslink
chain, and writing either would make a node on another network that looks
healthy and talks to nobody. It also refuses a table without a magic and a
genesis, because the fields a table leaves out are filled in from the public
testnet — the trap this whole file exists to avoid.

Modes:
  chain-params.py                 print the keys      (stdin: zebrad generate)
  chain-params.py --peers         print the seed peers the binary carries
  chain-params.py --verify FILE   check FILE names the binary's chain, with
                                  checkpoints off, the binary's PoW seed peers
                                  and no other peer list of its own; exit 1
                                  and say what differs
"""
import re
import sys
import tomllib

NATIVE = "network.network"
LEGACY = "network.testnet_parameters"
REQUIRED = ("network_magic", "genesis_hash")
# the PoW seed list is written beside the chain (see above); these two are
# left out so the binary's own are used — zebrad applies its defaults only to
# keys the file does not name
POW_PEERS = ("network", "initial_testnet_peers")
LEFT_OUT = (("crosslink", "bft_peers"), ("state", "network_initial_peers"))
PEER_KEYS = (LEFT_OUT[0], POW_PEERS, LEFT_OUT[1])

HEADER = re.compile(r'^\[\[?([A-Za-z0-9_."\-]+)\]\]?\s*(#.*)?$')


def fail(msg: str) -> int:
    print(f"chain-params: {msg}", file=sys.stderr)
    return 1


def parse(text: str, what: str) -> dict | None:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as err:
        fail(f"{what} is not TOML this can read: {err}")
        return None


def chain_of(cfg: dict) -> tuple[str, dict] | None:
    """Where a parsed config names its chain, and the table, or None."""
    net = cfg.get("network", {})
    named = net.get("network")
    if isinstance(named, dict):
        return NATIVE, named
    if named == "Testnet" and isinstance(net.get("testnet_parameters"), dict):
        return LEGACY, net["testnet_parameters"]
    return None


def refuse_non_crosslink(cfg: dict) -> str:
    """Why a config with no chain table cannot be a Crosslink chain."""
    named = cfg.get("network", {}).get("network")
    if named == "Testnet":
        return ("this binary's own network is the PUBLIC testnet (generate prints "
                "`network = \"Testnet\"` and no table). That is not a Crosslink "
                "chain; the deployment only configures Crosslink testnets.")
    if named is None:
        return "generate names no network at all."
    return (f"this binary resolves its network as {named!r}, not a testnet. "
            "The deployment only configures Crosslink testnets.")


def table_lines(lines: list[str], where: str) -> list[str]:
    """The lines of table `where` and its sub-tables, as printed."""
    out: list[str] = []
    inside = False
    for line in lines:
        m = HEADER.match(line.strip())
        if m and line.lstrip().startswith("["):
            name = m.group(1)
            inside = name == where or name.startswith(where + ".")
            if inside:
                out.append(line.rstrip())
            continue
        if inside:
            out.append(line.rstrip())
    return out


def bracket_depth(text: str) -> int:
    """Open minus closed square brackets, outside quoted strings."""
    depth = 0
    quote = ""
    for ch in text:
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "#":
            break
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
    return depth


def checkpoints_off(lines: list[str], where: str) -> list[str]:
    """The same lines with the top table's `checkpoints` set to false.

    The value may span lines and nest — a list of [height, hash] pairs, which
    a build that clears the checkpoints itself prints as `[[0, "…"]]` over
    several lines — so everything up to the bracket that closes the outer list
    goes, counted by depth, not by the first line that starts with `]`. A
    table without the key gets one."""
    out: list[str] = []
    in_top = False
    depth = 0
    found = False
    for line in lines:
        stripped = line.strip()
        if depth > 0:
            depth += bracket_depth(stripped)
            continue
        m = HEADER.match(stripped)
        if m and stripped.startswith("["):
            in_top = m.group(1) == where
            out.append(line)
            if in_top:
                out.append("checkpoints = false")
                found = True
            continue
        if in_top and stripped.split("=", 1)[0].strip() == "checkpoints":
            depth = bracket_depth(stripped.split("=", 1)[1])
            continue
        out.append(line)
    if not found:
        raise ValueError(f"no [{where}] header among the copied lines")
    return out


def emit(text: str) -> int:
    cfg = parse(text, "`zebrad generate`")
    if cfg is None:
        return 1
    found = chain_of(cfg)
    if found is None:
        return fail(refuse_non_crosslink(cfg))
    where, table = found
    missing = [k for k in REQUIRED if k not in table]
    if missing:
        return fail(f"the [{where}] table carries no {', '.join(missing)}. A table "
                    f"without them is filled in from the public testnet; read the "
                    f"chain by hand from `zebrad generate`.")

    pow_peers = cfg.get("network", {}).get("initial_testnet_peers")
    if not isinstance(pow_peers, list):
        return fail("generate names no [network] initial_testnet_peers; without "
                    "the list the chain table is refused beside the public "
                    "seeders (see the docstring).")

    lines = checkpoints_off(table_lines(text.splitlines(), where), where)
    if where == LEGACY:
        lines = ['network = "Testnet"', ""] + lines
    peer_lines = ["initial_testnet_peers = ["] + \
        [f'    "{p}",' for p in pow_peers] + ["]", ""]
    out = "\n".join(peer_lines + lines).rstrip()

    # what was printed must read back as the same chain, checkpoints aside
    check = parse("[network]\n" + out, "the output")
    if check is None:
        return 1
    written = chain_of(check)
    if written is None or written[0] != where:
        return fail("the output does not name the chain where the input did")
    if written[1].get("checkpoints") is not False:
        return fail("the output does not turn the checkpoint list off")
    if check["network"].get("initial_testnet_peers") != pow_peers:
        return fail("the output does not carry the binary's PoW seed peers")
    expect = {k: v for k, v in table.items() if k != "checkpoints"}
    got = {k: v for k, v in written[1].items() if k != "checkpoints"}
    if got != expect:
        return fail("the output does not read back as the chain the binary "
                    "printed; the copy is not whole")
    print(out)
    return 0


def peers(text: str) -> int:
    cfg = parse(text, "`zebrad generate`")
    if cfg is None:
        return 1
    for section, key in PEER_KEYS:
        for peer in cfg.get(section, {}).get(key, []) or ["(none)"]:
            print(f"{key} {peer}")
    return 0


def verify(text: str, path: str) -> int:
    """Exit 1 unless the config at `path` names the chain the binary carries,
    with checkpoints off and the peer lists left to the binary."""
    cfg = parse(text, "`zebrad generate`")
    if cfg is None:
        return 1
    try:
        written = parse(open(path, encoding="utf-8").read(), path)
    except OSError as err:
        return fail(f"cannot read {path}: {err}")
    if written is None:
        return 1

    binary = chain_of(cfg)
    if binary is None:
        return fail(refuse_non_crosslink(cfg))
    mine = chain_of(written)
    if mine is None:
        return fail(f"{path} names no chain table. Its `network` is "
                    f"{written.get('network', {}).get('network')!r}: without the "
                    f"binary's table under it this node is on another network.")

    problems = []
    if mine[1].get("checkpoints") is not False:
        problems.append(f"checkpoints: the file says {mine[1].get('checkpoints')!r}, "
                        f"and anything but false keeps the public testnet's list")
    for k, v in binary[1].items():
        if k != "checkpoints" and mine[1].get(k) != v:
            problems.append(f"{k}: the file says {mine[1].get(k)!r}, the binary {v!r}")
    section, key = POW_PEERS
    if written.get(section, {}).get(key) != cfg.get(section, {}).get(key):
        problems.append(f"[{section}] {key}: the file says "
                        f"{written.get(section, {}).get(key)!r}, the binary "
                        f"{cfg.get(section, {}).get(key)!r}. The list has to be "
                        f"the binary's: left out, the public seeders take its "
                        f"place and the chain is refused beside them.")
    for section, key in LEFT_OUT:
        if key in written.get(section, {}):
            problems.append(f"[{section}] {key}: written into the file, so the "
                            f"binary's own list is not used. Leave it out.")
    if problems:
        print(f"chain-params: {path} does not name the chain this binary carries:",
              file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print(f"{path} names the binary's chain: magic {mine[1]['network_magic']}, "
          f"genesis {mine[1]['genesis_hash'][:16]}…, checkpoints off, "
          f"the binary's PoW seed peers, BFT and state peers from the binary.")
    return 0


def main(argv: list[str]) -> int:
    text = sys.stdin.read()
    if argv == []:
        return emit(text)
    if argv == ["--peers"]:
        return peers(text)
    if len(argv) == 2 and argv[0] == "--verify":
        return verify(text, argv[1])
    return fail("usage: chain-params.py [--peers | --verify FILE] < generated.toml")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
