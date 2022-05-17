# Copyright 2022 The Chromium OS Authors. All rights reserved.
# Distributed under the terms of the GNU General Public License v2

EAPI=7

LICENSE="GPL-2"
SLOT="0"
KEYWORDS="*"

inherit user

# TODO(b/187790077): this ebuild is just a placeholder (to satisfy Gentoo
# dependencies) while we wait to implement acct-{group,user} properly.
pkg_setup() {
	enewgroup plugdev
}
