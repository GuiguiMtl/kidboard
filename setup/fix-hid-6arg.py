#!/usr/bin/env python3
"""Patch the packaged OpenRazer driver for the 6-argument hid_report_raw_event.

Linux backported a signature change into stable kernels from 6.18.33:

    hid_report_raw_event(hdev, type, data, size, 0)              # old, 5 args
    hid_report_raw_event(hdev, type, data, size, size, 0)        # new, 6 args

Debian's openrazer-driver-dkms 3.10.2 still emits the 5-argument form, so the
module fails to build and - because DKMS runs from the kernel postinst hook -
takes the kernel packages down with it. Upstream fixed this in PR #2843; this
is the same change applied to the packaged source until Debian catches up.

Idempotent. Keeps a .orig backup. Run with sudo.
"""
import argparse
import glob
import os
import re
import shutil
import sys

# hid_report_raw_event(a, b, c, sizeof(buf), 0)  ->  ..., sizeof(buf), sizeof(buf), 0)
CALL = re.compile(
    r"hid_report_raw_event\(\s*([^,()]+),\s*([^,()]+),\s*([^,()]+),\s*"
    r"sizeof\(\s*([^)]+?)\s*\)\s*,\s*0\s*\)"
)


def patch_text(text):
    def repl(m):
        target, rtype, data, buf = (g.strip() for g in m.groups())
        return ("hid_report_raw_event(%s, %s, %s, sizeof(%s), sizeof(%s), 0)"
                % (target, rtype, data, buf, buf))
    return CALL.subn(repl, text)


def find_sources(explicit=None):
    """Return (c_files, roots).

    Debian ships the DKMS tree in the upstream layout, so the sources are a
    level down in driver/ rather than at the top - hence the recursive walk.
    """
    if explicit:
        return [explicit], []
    roots = sorted(glob.glob("/usr/src/openrazer-driver-*"))
    found = []
    for root in roots:
        found.extend(sorted(glob.glob(os.path.join(root, "**", "*.c"), recursive=True)))
    return found, roots


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="patch this file instead of /usr/src/openrazer-driver-*")
    ap.add_argument("--revert", action="store_true", help="restore the .orig backups")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sources, roots = find_sources(args.file)
    if not sources:
        if not roots:
            print("no /usr/src/openrazer-driver-* directory.")
            print("Is openrazer-driver-dkms installed? Try: dpkg -L openrazer-driver-dkms | grep /usr/src")
        else:
            print("found %s but no .c files under it:" % ", ".join(roots))
            for root in roots:
                for dirpath, _, names in os.walk(root):
                    print("   %s: %s" % (dirpath, ", ".join(sorted(names)[:8]) or "(empty)"))
        return 1
    print("scanning %d source file(s)" % len(sources))

    touched = 0
    for path in sources:
        backup = path + ".orig"

        if args.revert:
            if os.path.exists(backup):
                shutil.copy2(backup, path)
                print("reverted %s" % path)
                touched += 1
            continue

        with open(path) as fh:
            text = fh.read()

        patched, count = patch_text(text)
        if count == 0:
            continue

        print("%s: %d call site(s)" % (path, count))
        for line_no, line in enumerate(text.splitlines(), 1):
            if CALL.search(line):
                print("   %d- %s" % (line_no, line.strip()))
                print("   %d+ %s" % (line_no, patch_text(line)[0].strip()))

        if args.dry_run:
            touched += count
            continue

        if not os.path.exists(backup):
            shutil.copy2(path, backup)
        with open(path, "w") as fh:
            fh.write(patched)
        touched += count

    if args.revert:
        print("reverted %d file(s)" % touched if touched
              else "no .orig backups found - nothing to revert")
        return 0

    if not touched:
        print("nothing to do - already patched, or this source does not need it")
        return 0
    if args.dry_run:
        print("\ndry run: %d change(s) not written" % touched)
    else:
        print("\npatched %d call site(s); backups kept as *.orig" % touched)
    return 0


if __name__ == "__main__":
    sys.exit(main())
