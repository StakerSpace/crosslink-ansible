# Contributing

Issues and pull requests are welcome. A few things make them land faster.

## Issues

Use the templates. Paste the failing task and the lines around it, or the output of `sudo crosslink-check`, and the host's inventory entry with the addresses replaced. **Strip anything private**: host names, real addresses, seed fingerprints, phrases, anything from the key bundle. A bug in the node software itself (zebrad, the wallet, the BFT engine) belongs with [Shielded Labs](https://github.com/ShieldedLabs/crosslink_monolith/issues); this repository only builds and runs it.

## Pull requests

- Open an issue first for anything bigger than a fix, so the shape is agreed before the work.
- Keep an existing inventory working. A variable that is renamed keeps its old name as an alias.
- A new setting goes to `group_vars/all/main.yml` first, with a default and a comment, then into the template, then into the README's table if people will set it and into `docs/zebrad-toml.md` if it writes a config key.
- A claim about what the node does cites the source file it was read in, at the tag the default row builds.
- Run the gate before pushing:

```bash
ansible-galaxy collection install -r requirements.yml
for p in site.yml reset.yml restore.yml rewards.yml; do
  ansible-playbook -i inventory.example.yml --syntax-check "$p"; done
python3 check-templates.py
ansible-lint
python3 tools/seed-tool.py --selftest
```

CI runs the same on every push and pull request.

## Writing

Plain English, short sentences, say what then why. Task names are verb first, sentence case, no full stop. The terms are in the README's Terms table; use them and no synonyms. `CLAUDE.md` holds the same rules for an AI agent and is a fine summary for a person too.

## What will not be merged

- Anything that writes a key or a seed to a host.
- A way around the preflight's refusals.
- A task that runs `crosslink-stake`.
- A chain's parameters typed into this tree instead of read from the binary.
- Anything identifying a real machine or a real operator.
