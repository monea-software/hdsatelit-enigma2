# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Driverele u57 fara modulul NTFS comercial.
#
# Arhiva driverelor (u57-drivers-4.4.35-20211209) aduce 41 de module de nucleu; tntfs.ko e singurul cu
# license=Commercial (driverul NTFS Tuxera) si nu se poate redistribui. Il scoatem din pachet, impreuna cu randul care
# il incarca din scriptul `load` al arhivei (rulat de /etc/init.d/loadmodules la S05). Restul scriptului ramane
# neschimbat.
#
# In locul lui, discurile NTFS le monteaza ntfs-3g prin FUSE: nucleul 4.4.35 are CONFIG_FUSE_FS=y, driverul ntfs al
# nucleului e numai citire (si nu e in imagine), iar ntfs3 apare abia in 5.15. Busybox `mount -t auto` incearca
# tipurile din /etc/filesystems (base-files OE-A: ... btrfs ntfs-3g exfat-fuse *) si, dupa mount(2) cazut, cheama
# ajutorul mount.<tip> (CONFIG_FEATURE_MOUNT_HELPERS=y), deci ajunge la mount.ntfs-3g. De aceea pachetul cere ntfs-3g:
# scoaterea lui tntfs si inlocuirea lui intra impreuna in imagine. Ajutorul e descris in ntfs-3g-ntfsprogs_%.bbappend.
#
# Constructia se opreste cu eroare, nu trece tacut, daca tntfs.ko nu mai e in arhiva (alta arhiva: de citit din nou
# inainte de a schimba ceva), daca `load` nu are exact un rand `insmod tntfs.ko`, sau daca dupa schimbare mai ramane
# tntfs in dosarul modulelor ori in `load`.
# PR cu ".hds1", ca pachetul schimbat sa se vada in manifest si in "opkg list-installed".

PR:append = ".hds1"

RDEPENDS:${PN} += "ntfs-3g"

do_install:append() {
	extra="${D}${nonarch_base_libdir}/modules/${KV}/extra"
	[ -f "$extra/tntfs.ko" ] || bbfatal "tntfs.ko nu mai e in arhiva driverelor; arhiva s-a schimbat, de citit din nou"
	[ "$(grep -c -x 'insmod tntfs\.ko' "$extra/load")" = "1" ] || bbfatal "load nu are exact un rand 'insmod tntfs.ko'"
	rm -f "$extra/tntfs.ko"
	sed -i -e '/^insmod tntfs\.ko$/d' "$extra/load"
	[ ! -e "$extra/tntfs.ko" ] || bbfatal "tntfs.ko a ramas in pachet"
	! grep -q tntfs "$extra/load" || bbfatal "load pomeneste inca tntfs"
}
