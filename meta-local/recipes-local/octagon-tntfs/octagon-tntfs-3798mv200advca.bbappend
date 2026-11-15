# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Octagon SX988 4K DUAL OS (masina sx988, V19 14.11.2026): fara modulul NTFS comercial, ca pe SF8008 (octagon-tntfs-3798mv200.bbappend, acolo e
# intreaga explicatie). Masina cere pachetul octagon-tntfs-3798mv200advca (MACHINE_ESSENTIAL_EXTRA_RDEPENDS cu ${HICHIPSET}), alta
# reteta decat cea pentru 3798mv200 (arhiva 3798mv200advca-tntfs-20211220, KV 4.4.176), deci bbappend-ul mv200 nu i se aplica.
# tntfs.ko are license=Commercial (driverul NTFS Tuxera) si nu se poate redistribui; il incarca
# /etc/modules-load.d/tntfs.conf. Scoatem amandoua; pachetul ramane gol (ALLOW_EMPTY). Discurile NTFS le monteaza ntfs-3g
# prin FUSE (defconfig sx988: CONFIG_FUSE_FS=y).
# Constructia se opreste cu eroare daca tntfs.ko sau tntfs.conf nu mai sunt unde le stim, sau daca in pachet ramane ceva.

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
