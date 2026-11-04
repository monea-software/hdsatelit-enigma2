# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Uclan Ustym 4K PRO (masina ustym4kpro): fara modulul NTFS comercial, ca la V20, V10 si SF8008
# (octagon-tntfs-3798mv200.bbappend, acolo e intreaga explicatie). Pachetul uclan-tntfs-3798mv200 (meta-uclan, cerut de
# masina cu ${HICHIPSET}) are acelasi corp de reteta si aceeasi arhiva ca la Octagon (3798mv200-tntfs-20200528, sha256
# eb64e387): tntfs.ko are license=Commercial si nu se poate redistribui. Scoatem tntfs.ko si tntfs.conf; pachetul
# ramane gol (ALLOW_EMPTY) si cere ntfs-3g (discurile NTFS prin FUSE; nucleul linux-uclan are CONFIG_FUSE_FS=y).
PR:append = ".hds1"

ALLOW_EMPTY:${PN} = "1"

RDEPENDS:${PN} += "ntfs-3g"

do_install:append() {
	[ -f "${D}/lib/modules/${KV}/extra/tntfs.ko" ] || bbfatal "tntfs.ko nu mai e unde il stim in ${PN}; de citit din nou"
	[ -f "${D}${sysconfdir}/modules-load.d/tntfs.conf" ] || bbfatal "tntfs.conf nu mai e unde il stim in ${PN}; de citit din nou"
	rm -f "${D}/lib/modules/${KV}/extra/tntfs.ko" "${D}${sysconfdir}/modules-load.d/tntfs.conf"
	find "${D}" -mindepth 1 -depth -type d -empty -delete
	rest=$(find "${D}" -mindepth 1 ! -type d)
	[ -z "$rest" ] || bbfatal "in pachetul ${PN} a ramas: $rest"
}
