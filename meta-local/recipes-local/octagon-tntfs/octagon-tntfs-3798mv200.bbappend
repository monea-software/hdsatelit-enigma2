# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Octagon SF8008 (masina sf8008): fara modulul NTFS comercial, ca la V20 si V10
# (dinobot-dvb-modules-u57.bbappend, acolo e intreaga explicatie; amiko-tntfs-3798mv200.bbappend la V10).
#
# Pe SF8008 modulul vine intr-un pachet separat, octagon-tntfs-3798mv200 (meta-octagon, cerut de masina prin
# MACHINE_ESSENTIAL_EXTRA_RDEPENDS cu ${HICHIPSET}), din aceeasi arhiva ca la V10 (3798mv200-tntfs-20200528, sha256
# eb64e387, lotul imagine-060-sf8008): tntfs.ko are license=Commercial (driverul NTFS Tuxera) si nu se poate
# redistribui. Il incarca /etc/modules-load.d/tntfs.conf, nu scriptul `load` al driverelor (acela nu il pomeneste).
# Scoatem amandoua; pachetul ramane gol (ALLOW_EMPTY), ca dependinta ceruta de masina sa fie satisfacuta.
#
# In locul lui, discurile NTFS le monteaza ntfs-3g prin FUSE (nucleul linux-octagon are CONFIG_FUSE_FS=y), ca pe V20;
# de aceea pachetul cere ntfs-3g.
#
# Constructia se opreste cu eroare, nu trece tacut, daca tntfs.ko sau tntfs.conf nu mai sunt unde le stim (alta reteta
# sau alta arhiva: de citit din nou), sau daca dupa schimbare in pachet mai ramane vreun fisier.
# PR cu ".hds1", ca pachetul schimbat sa se vada in manifest si in "opkg list-installed".

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
