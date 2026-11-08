# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# GigaBlue UHD TRIO 4K (masina gbmv200): fara modulul NTFS comercial, ca la V20, V10, SF8008 si Ustym
# (octagon-tntfs-3798mv200.bbappend, acolo e intreaga explicatie). Pachetul gigablue-tntfs-3798mv200 (meta-gigablue,
# cerut de masina cu ${HICHIPSET}) are acelasi corp de reteta si aceeasi arhiva ca la Octagon si Uclan
# (3798mv200-tntfs-20200528, sha256 eb64e387): tntfs.ko are license=Commercial si nu se poate redistribui. Scoatem
# tntfs.ko si tntfs.conf; pachetul ramane gol (ALLOW_EMPTY) si cere ntfs-3g (discurile NTFS prin FUSE; nucleul
# linux-gigablue are CONFIG_FUSE_FS=y, defconfig gbmv200).
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
