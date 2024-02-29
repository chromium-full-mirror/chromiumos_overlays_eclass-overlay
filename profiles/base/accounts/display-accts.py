#!/usr/bin/env python3
# Copyright 2014 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Pretty print (and check) a set of group/user accounts"""

import argparse
import collections
import os
from pathlib import Path
import re
import sys
from typing import Dict, List, NamedTuple, Optional, Tuple, TypeVar


assert sys.version_info >= (
    3,
    6,
), f"Python 3.6+ required, but found {sys.version_info}"


# Regex to match valid account names.
VALID_ACCT_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]*[a-z0-9]$")


class Group(NamedTuple):
    """A group account."""

    # NB: Order is not the same as /etc/group.  Don't rely on it.
    group: str
    gid: str
    password: str = "!"
    users: str = ""
    defunct: str = ""


class User(NamedTuple):
    """A user account."""

    # NB: Order is not the same as /etc/passwd.  Don't rely on it.
    user: str
    uid: str
    gid: str
    password: str = "!"
    gecos: str = ""
    home: str = "/dev/null"
    shell: str = "/bin/false"
    defunct: str = ""


GroupOrUser = TypeVar("GroupOrUser", Group, User)


def _ParseAccount(
    name: str, name_key: str, content: str, obj: GroupOrUser
) -> GroupOrUser:
    """Parse the raw data in |content| and return a new |obj|."""
    # Make sure files all have a trailing newline.
    if not content.endswith("\n"):
        raise ValueError("File needs a trailing newline")

    # Disallow leading & trailing blank lines.
    if content.startswith("\n"):
        raise ValueError("Delete leading blank lines")
    if content.endswith("\n\n"):
        raise ValueError("Delete trailing blank lines")

    d = {}
    for line in content.splitlines():
        if not line or line.startswith("#"):
            continue

        # Disallow leading & trailing whitespace.
        if line != line.strip():
            raise ValueError(f'Trim leading/trailing whitespace: "{line}"')

        key, val = line.split(":")
        if key not in obj._fields:
            raise ValueError(f"unknown key: {key}")
        d[key] = val

    unknown_keys = set(d.keys()) - set(obj._fields)
    if unknown_keys:
        raise ValueError(f'unknown keys: {" ".join(unknown_keys)}')

    if d[name_key] != name:
        raise ValueError(
            f'account "{name}" has "{name_key}" field set to "{d[name_key]}"'
        )

    return obj(**d)


def ParseGroup(name: str, content: str) -> Group:
    """Parse |content| as a Group object."""
    return _ParseAccount(name, "group", content, Group)


def ParseUser(name: str, content: str) -> User:
    """Parse |content| as a User object."""
    return _ParseAccount(name, "user", content, User)


def AlignWidths(arr: List[NamedTuple]) -> Dict[NamedTuple, int]:
    """Calculate a set of widths for alignment.

    Args:
        arr: An array of accounts.

    Returns:
        A dict whose fields have the max length.
    """
    d = {}
    for f in arr[0]._fields:
        d[f] = 0

    for a in arr:
        for f in a._fields:
            d[f] = max(d[f], len(getattr(a, f)))

    return d


def DisplayAccounts(accts: List[NamedTuple], order: Tuple[Tuple[str]]) -> None:
    """Display |accts| as a table using |order| for field ordering.

    Args:
        accts: An array of accounts.
        order: The order in which to display the members.
    """
    obj = type(accts[0])
    header_obj = obj(**dict((k, (v if v else k).upper()) for k, v in order))
    keys = [k for k, _ in order]
    sorter = lambda x: int(getattr(x, keys[0]))

    widths = AlignWidths([header_obj] + accts)

    def p(obj):
        for k in keys:
            print(f"{getattr(obj, k):<{widths[k] + 1}}", end="")
        print()

    for a in [header_obj] + sorted(accts, key=sorter):
        p(a)


def CheckConsistency(groups: List[Group], users: List[User]) -> bool:
    """Run various consistency checks on the lists of groups/users.

    This does not check for syntax/etc... errors on a per-account basis as the
    main _ParseAccount function above took care of that.

    Args:
        groups: A list of Group objects.
        users: A list of User objects.

    Returns:
        True if everything is consistent.
    """
    ret = True

    gid_counts = collections.Counter(x.gid for x in groups)
    for gid in (k for k, v in gid_counts.items() if v > 1):
        ret = False
        dupes = ", ".join(x.group for x in groups if x.gid == gid)
        print(f"error: duplicate gid found: {gid}: {dupes}", file=sys.stderr)

    uid_counts = collections.Counter(x.uid for x in users)
    for uid in (k for k, v in uid_counts.items() if v > 1):
        ret = False
        dupes = ", ".join(x.user for x in users if x.uid == uid)
        print(f"error: duplicate uid found: {uid}: {dupes}", file=sys.stderr)

    for group in groups:
        if not VALID_ACCT_NAME_RE.match(group.group):
            print(f"error: invalid group account name: {group.group}")
    for user in users:
        if not VALID_ACCT_NAME_RE.match(user.user):
            print(f"error: invalid user account name: {user.user}")

    found_users = set(x.user for x in users)
    want_users = set()
    for group in groups:
        if group.users:
            want_users.update(group.users.split(","))

    missing_users = want_users - found_users
    if missing_users:
        ret = False
        print("error: group lists unknown users", file=sys.stderr)
        for group in groups:
            for user in missing_users:
                if user in group.users.split(","):
                    print(
                        f'error: group "{group.group}" wants missing user '
                        f'"{user}"',
                        file=sys.stderr,
                    )

    return ret


def _FindFreeIds(
    accts: GroupOrUser, key: int, low_id: int, high_id: int
) -> List[int]:
    """Find all free ids in |accts| between |low_id| and |high_id| (inclusive).

    Args:
        accts: An iterable of account objects.
        key: The member of the account object holding the id.
        low_id: The first id to look for.
        high_id: The last id to look for.

    Returns:
        A sorted list of free ids.
    """
    free_accts = set(range(low_id, high_id + 1))
    used_accts = set(int(getattr(x, key)) for x in accts)
    return sorted(free_accts - used_accts)


def ShowNextFree(groups: List[Group], users: List[User]) -> None:
    """Display next set of free groups/users."""
    RANGES = (
        ("CrOS daemons", 20100, 29999),
        ("FUSE daemons", 300, 399),
        ("Standalone", 400, 499),
        ("Namespaces", 600, 699),
    )
    for name, low_id, high_id in RANGES:
        print(f"{name}:")
        for accts, key in ((groups, "gid"), (users, "uid")):
            if accts:
                free_accts = _FindFreeIds(accts, key, low_id, high_id)
                if len(free_accts) > 10:
                    free_accts = free_accts[0:10] + ["..."]
                print(f"  {key}: {free_accts}")
        print()


def GetParser() -> argparse.ArgumentParser:
    """Creates the argparse parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--show-free",
        default=False,
        action="store_true",
        help="Find next available UID/GID",
    )
    parser.add_argument(
        "--lint",
        default=False,
        action="store_true",
        help="Validate all the user accounts",
    )
    parser.add_argument(
        "account", nargs="*", type=Path, help="Display these account files only"
    )
    return parser


def main(argv: Optional[List[str]] = None) -> Optional[int]:
    parser = GetParser()
    opts = parser.parse_args(argv)

    accounts = opts.account
    consistency_check = False
    if not accounts:
        accounts_dir = Path(__file__).resolve().parent
        accounts = list((accounts_dir / "group").glob("*")) + list(
            (accounts_dir / "user").glob("*")
        )
        consistency_check = True

    groups: List[Group] = []
    users: List[User] = []
    for f in accounts:
        try:
            content = f.read_text(encoding="utf-8")
            if not content:
                raise ValueError("empty file")
            if content[-1] != "\n":
                raise ValueError("missing trailing newline")

            if "group:" in content:
                groups.append(ParseGroup(f.name, content))
            else:
                users.append(ParseUser(f.name, content))
        except ValueError as e:
            print(f"error: {f}: {e}", file=sys.stderr)
            return os.EX_DATAERR

    if opts.show_free:
        ShowNextFree(groups, users)
        return

    if not opts.lint:
        if groups:
            order = (
                ("gid", ""),
                ("group", ""),
                ("password", "pass"),
                ("users", ""),
                ("defunct", ""),
            )
            DisplayAccounts(groups, order)

        if users:
            if groups:
                print()
            order = (
                ("uid", ""),
                ("gid", ""),
                ("user", ""),
                ("shell", ""),
                ("home", ""),
                ("password", "pass"),
                ("gecos", ""),
                ("defunct", ""),
            )
            DisplayAccounts(users, order)

    if consistency_check and not CheckConsistency(groups, users):
        return os.EX_DATAERR


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
