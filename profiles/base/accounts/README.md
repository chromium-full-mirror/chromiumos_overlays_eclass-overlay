# Introduction

In accordance with [Gentoo's GLEP 27](https://wiki.gentoo.org/wiki/GLEP:27),
Chromium OS has implemented a mechanism that allows users and groups
to be managed stably and centrally for a given build profile. Each
user and group is defined in a file underneath the appropriate
`profiles/base/accounts/` subdirectory.

For example, the `chronos` user is defined as follows in a file at
[`profiles/base/accounts/user/chronos`](./user/chronos):
```
user:chronos
password:*
uid:1000
gid:1000
gecos:system_user
home:/home/chronos/user
shell:/bin/bash
```

The `cras` group is defined in a similarly constructed file at
[`profiles/base/accounts/group/cras`](./group/cras):
```
group:cras
password:!
gid:220
users:chronos,power
```

Notice how the membership of the group is provided in the group
definition, even though traditionally this is done at user-creation
time.

The password field can be set to one of the following:

*   `!` - The account is locked and may not be logged into (this is the
    default).
*   `*` - No password yet, but the account has the ability to have one added,
    so this should be used for accounts that people expect to have a password
    set for, or want to otherwise login as remotely.
*   `x` - The password is shadowed but the account is for an internal feature;
    people should not set a password themselves.
*   An encrypted password as per
    [crypt(3)](http://man7.org/linux/man-pages/man3/crypt.3.html#NOTES).


# Choosing UIDs and GIDs

Every UID on CrOS has an associated GID with the same value. The
opposite does not hold true, however.

CrOS system daemon UIDs (and associated GIDs) range from 200-299 and
from 20100-29999. If you're creating a new user, pick the first UID in
the range 20100-29999 that is not currently used, and create both a user
and a group with this ID.  To find the next available UID, invoke
`./display-accts.py --show-free`.

FUSE-based filesystem daemons have UID/GIDs that range from 300-399.
If you're adding a daemon that will be talking to `cros-disks` and
managing some kind of volumes (archives mounted as volumes, external
disks, network-mounted storage, etc.) then you should create a user
and group with IDs in this range.

Groups that have no associated user should be given GIDs in the 400 range.

Groups and users that are shared with programs running in different user
namespaces should be in the 600-699 range.

The `chronos` user, which all user-facing processes in CrOS run as, is
UID/GID 1000.  There is also a special user/group that has access to
many resources owned by `chronos`, called `chronos-access`, which has
the UID/GID 1001.

# Testing

If a newly added group has users, it is necessary to also add matching
information to [`cros/test/usergroup_baseline.py`](https://chromium.googlesource.com/chromiumos/chromite/+/HEAD/cros/test/usergroup_baseline.py):
```
GroupEntry(group='cras', gid=220, users={'chronos', 'power'}),
```

## Board/project-specific accounts

For boards creating their own users, the 2000-4999 range is reserved for that.
Boards must take care that they don't create conflicts amongst themselves or
any project overlays they inherit.

This space is not intended for mainline CrOS use.  Such projects should be
integrated directly into this overlay instead.  This is only for boards/projects
that are maintained by partners.

# Creating users and groups in ebuilds

The API implemented by the CrOS-specific [user.eclass](/eclass/user.eclass)
is compatible with that provided by the upstream
[user.eclass](https://gitweb.gentoo.org/repo/gentoo.git/tree/eclass/user.eclass).

```sh
enewuser cras   # Creates a user called 'cras' with the pre-specified UID.
enewgroup cras  # Ditto for the group.
```

You can choose to specify other fields when calling the functions to create
new users and groups, but the eclass will bail if the values you choose conflict
with those in the DB.

Calls to `enewuser` and `enewgroup` are allowed ONLY in three ebuild stanzas:

*   `pkg_setup()`: Make the calls here if you need to chown/chgrp files using
    the accounts you're creating.
*   `pkg_preinst()`: Make the calls here if you just need the accounts to exist
    at runtime.
*   `pkg_postinst()`: Try to avoid making the calls here. If you need a failed
    account creation to be non-fatal, then you can add them here.

Bear in mind that when creating a new user, simply using `cros deploy` to
install the new pacakge on the test system will **not** install the new user.
This is currently being tracked in [crbug.com/402673]. You can build a new
image (by using `emerge-$BOARD <package>` and `build_image`) to get the new
user/group to show up in `/etc/passwd` and `/etc/group`.

Alternatively you can `emerge-$BOARD` the package with the new user/group and
then copy `/build/$BOARD/etc/{passwd,group}` over the device's
`/etc/{passwd,group}`, via `scp` or some other mechanism.

[crbug.com/402673]: https://bugs.chromium.org/p/chromium/issues/detail?id=402673
