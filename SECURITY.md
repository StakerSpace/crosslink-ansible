# Security

## What this repository is responsible for

How a node is built, configured and run: the systemd sandbox, the firewall rules, what is written to disk and with which permissions, where the seed is copied and how, what the two host scripts read and send. A problem there is this repository's.

## What it is not

The node software, the wallet, the BFT engine and the chain's consensus rules are [Shielded Labs' crosslink_monolith](https://github.com/ShieldedLabs/crosslink_monolith). Its README asks that vulnerability reports in the node go to the Zcash Foundation's zebra repository, not to the monolith; follow their process.

## Reporting

For a problem in this repository that could expose a seed, a key, a wallet, or let a stranger reach a node's RPC: do not open a public issue. Use GitHub's private vulnerability reporting on this repository if it is enabled, or contact the maintainers through the profile of the organisation that owns it. Say which file and which host shape, and what an attacker would get.

For anything else, open an issue.

## Reminders for operators

- The key bundle holds every node's seed. It is one copy on one machine until you back it up and encrypt it.
- `secret.seed` on a host is a finalizer identity and a wallet. The playbook never writes one; zebrad makes a new random one when the file is missing and never says so.
- The RPC is bound to loopback and has no authentication. Do not bind it elsewhere.
- A viewing key (`get_wallet_ufvk`) cannot be withdrawn once shared.
