## What changed, and why

<!-- One paragraph. Say what the host ends up with that it did not before. -->

## Checked

- [ ] `ansible-playbook -i inventory.example.yml --syntax-check site.yml` (and the other playbooks a change touches)
- [ ] `python3 check-templates.py` prints `0 templates with undefined variables`
- [ ] `ansible-lint` passes
- [ ] A template change: the rendered `zebrad.toml` read by eye
- [ ] A protocol claim in a comment or doc names the source file it was read in
- [ ] Nothing identifying: no host names, addresses, keys, seeds or real paths

## Old inventories

<!-- Does an inventory written before this change still work unchanged? A renamed variable keeps its old name as an alias. -->
