# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# AB-COM PULSe 4K si PULSe 4K MINI (MPU, 12.11.2026; masinile pulse4k, pulse4kmini): fara modulul NTFS comercial, ca la
# SF8008 (octagon-tntfs-3798mv200.bbappend, acolo e intreaga explicatie).
#
# Pe masinile AB-COM modulul vine in pachetul abcom-tntfs-3798mv200 (meta-abcom, cerut de masina prin
# MACHINE_ESSENTIAL_EXTRA_RDEPENDS din abcom-hisil-3798mv200.inc), din aceeasi arhiva ca la SF8008 si H9 COMBO
# (3798mv200-tntfs-20200528, sha256 eb64e387): tntfs.ko are license=Commercial (driverul NTFS Tuxera) si nu se poate
# redistribui. Il incarca /etc/modules-load.d/tntfs.conf. Scoatem amandoua; pachetul ramane gol (ALLOW_EMPTY), ca
# dependinta ceruta de masina sa fie satisfacuta. Discurile NTFS le monteaza ntfs-3g prin FUSE (CONFIG_FUSE_FS=y in
# defconfig pulse4k).
#
# Constructia se opreste cu eroare daca tntfs.ko sau tntfs.conf nu mai sunt unde le stim, sau daca in pachet mai ramane
# vreun fisier. PR cu ".hds1", ca pachetul schimbat sa se vada in manifest.

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
