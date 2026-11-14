# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Novaler Multibox 4K PRO si 4K SE (MNP si MNS, 12.11.2026; masinile multiboxpro si multiboxse din meta-maxytec): fara
# modulul NTFS comercial, ca la SF8008 (octagon-tntfs-3798mv200.bbappend, acolo e intreaga explicatie) si H9
# (airdigital-tntfs-3798mv200.bbappend).
#
# Pe masinile maxytec modulul vine in pachetul maxytec-tntfs-3798mv200 (cerut de masina prin MACHINE_ESSENTIAL_EXTRA_RDEPENDS
# din maxytec-hisil-3798mv200.inc), din aceeasi arhiva ca la SF8008, V10 si H9 (3798mv200-tntfs-20200528, sha256
# eb64e387): tntfs.ko are license=Commercial (driverul NTFS Tuxera) si nu se poate redistribui. Il incarca
# /etc/modules-load.d/tntfs.conf. Scoatem amandoua; pachetul ramane gol (ALLOW_EMPTY), ca dependinta ceruta de masina sa
# fie satisfacuta. Discurile NTFS le monteaza ntfs-3g prin FUSE (CONFIG_FUSE_FS=y in defconfig multiboxpro si multiboxse).
#
# Constructia se opreste cu eroare daca tntfs.ko sau tntfs.conf nu mai sunt unde le stim, sau daca in pachet mai ramane
# vreun fisier. PR cu ".hds1", ca pachetul schimbat sa se vada in manifest.
# ATENTIE: cu acest bbappend in strat, randurile celorlalte masini din model-60.sh au nevoie de „maxytec” in HDS_60_ALTI
# (stratul lor nu are reteta maxytec-tntfs; peticul MNP/petic_main_multiboxpro.py il pune).

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
