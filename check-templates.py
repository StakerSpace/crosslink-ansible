#!/usr/bin/env python3
"""Every variable a template reads must be defined somewhere: group_vars, the
example inventory, or a fact a task registers or sets. Every list a template
loops over must be a list in group_vars. Run from the repository root; exit
code is the number of templates that fail either rule.

`ansible-playbook --syntax-check` cannot see an undefined template variable;
this does. A bare key in an inventory (`crosslink_hardforks:` with nothing
under it) overrides a group_vars list with null, which this cannot see; the
node role's hard fork check names it at run time.
"""
import glob
import re
import sys

import yaml

BUILTIN = {"range", "item", "inventory_hostname", "groups", "hostvars", "lookup",
           "ansible_facts", "play_hosts", "loop", "now", "omit", "true", "false", "none"}


def main() -> int:
    defined: set[str] = set()
    values: dict = {}
    for f in glob.glob("group_vars/*/*.yml") + glob.glob("group_vars/*.yml"):
        loaded = yaml.safe_load(open(f))
        if isinstance(loaded, dict):
            values.update(loaded)
    defined |= set(values)

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, dict):
                    walk(v)
                else:
                    defined.add(k)
    walk(yaml.safe_load(open("inventory.example.yml")))

    def facts(tasks):
        for t in tasks or []:
            if not isinstance(t, dict):
                continue
            if isinstance(t.get("register"), str):
                defined.add(t["register"])
            for k in ("ansible.builtin.set_fact", "set_fact"):
                if isinstance(t.get(k), dict):
                    defined.update(t[k])
            if isinstance(t.get("vars"), dict):
                defined.update(t["vars"])
            for k in ("block", "rescue", "always"):    # facts set inside a block
                facts(t.get(k))
    for f in glob.glob("roles/*/tasks/*.yml"):
        facts(yaml.safe_load(open(f)))
    for f in glob.glob("*.yml"):
        for play in yaml.safe_load(open(f)) or []:
            if isinstance(play, dict):
                if isinstance(play.get("vars"), dict):
                    defined.update(play["vars"])
                facts(play.get("tasks"))

    bad = 0
    for f in sorted(glob.glob("roles/*/templates/*.j2")):
        tpl = open(f).read()
        used = set(re.findall(r"{{\s*([a-z_][a-z0-9_]*)", tpl))
        used |= set(re.findall(r"{%\s*for\s+\w+\s+in\s+([a-z_][a-z0-9_]*)", tpl))
        used |= set(re.findall(r"{%\s*(?:if|elif)\s+(?:not\s*\(?\s*)?([a-z_][a-z0-9_]*)", tpl))
        # names the template makes itself: loop variables and {% set %}
        local = set(re.findall(r"{%\s*for\s+(\w+)\s+in", tpl))
        local |= set(re.findall(r"{%\s*set\s+(\w+)", tpl))
        undefined = sorted(u for u in used
                           if u not in defined and u not in BUILTIN
                           and u not in local and not u.startswith("ansible_"))
        # a loop over null or a string renders a traceback or garbage, not a config
        looped = set(re.findall(r"{%\s*for\s+\w+\s+in\s+([a-z_][a-z0-9_]*)", tpl))
        empty = sorted(v for v in looped if v in values and not isinstance(values[v], list))
        if undefined or empty:
            bad += 1
        if undefined:
            print(f"{f}: undefined {undefined}")
        if empty:
            print(f"{f}: looped but not a list in group_vars {empty}")
    print(f"{bad} templates with undefined variables")
    return bad


if __name__ == "__main__":
    sys.exit(main())
