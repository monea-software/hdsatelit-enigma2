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

PR:append = ".hds2"

RDEPENDS:${PN} += "ntfs-3g"

# R2K (0.7.5, Wlad, forum 948): interfata 2560x1440 pentru temele 2K (Fury-FHD cu „Skin Resolution” 2K). Driverul hi_fb.ko
# refuza orice latime peste 1920; clasa OE-Alliance hisi-hifb-wqhd (meta-oe/classes, commitul 67bc3f2a90, mostenita deja de
# reteta) ridica limitele la 2560x1440 in hifb_set_par si hifb_disp_setdispsize; o pornim aici si fara e2egl. Memoria video
# ramane cea din fabrica a driverului (clasa ar pune vram0_size=43200): enigma2 al nostru cere 2 pagini, 2560x1440x2 = 28800 KB,
# care incap (40500 KB pe Viper 4K V20, 49152 KB pe V10). Probat pe receptorul de probe (V20) cu Fury-FHD 9.0 pe 2K, 13.11.2026
# (paralel-1111b/STADIU-R2K.md). Unde n-ar incapea, enigma2 refuza curat rezolutia si tema ramane pe HD Satelit (R2K, skin.py).
HISI_HIFB_WQHD_PATCH = "1"

do_install:append() {
	extra="${D}${nonarch_base_libdir}/modules/${KV}/extra"
	[ -f "$extra/tntfs.ko" ] || bbfatal "tntfs.ko nu mai e in arhiva driverelor; arhiva s-a schimbat, de citit din nou"
	[ "$(grep -c -x 'insmod tntfs\.ko' "$extra/load")" = "1" ] || bbfatal "load nu are exact un rand 'insmod tntfs.ko'"
	rm -f "$extra/tntfs.ko"
	sed -i -e '/^insmod tntfs\.ko$/d' "$extra/load"
	[ ! -e "$extra/tntfs.ko" ] || bbfatal "tntfs.ko a ramas in pachet"
	! grep -q tntfs "$extra/load" || bbfatal "load pomeneste inca tntfs"
	# R2K: hi_fb.ko peticit de clasa hisi-hifb-wqhd (mai sus); memoria video ramane cea din fabrica (load fara vram0_size)
	ldhds="$(find ${D} -path '*/modules/*/extra/load' | head -1)"
	kohds="$(find ${D} -path '*/modules/*/extra/hi_fb.ko' | head -1)"
	[ -n "$kohds" ] && [ -n "$ldhds" ] || bbfatal "R2K: hi_fb.ko sau load lipsesc din ${PN}"
	sed -i -e 's/^insmod hi_fb\.ko video="hi_fb:vram0_size:${HISI_HIFB_WQHD_VRAM0_SIZE}"$/insmod hi_fb.ko/' "$ldhds"
	[ "$(grep -c -x 'insmod hi_fb\.ko' "$ldhds")" = "1" ] || bbfatal "R2K: load din ${PN} nu are exact un rand 'insmod hi_fb.ko'"
	python3 -c 'import sys; d = open(sys.argv[1], "rb").read(); sys.exit(0 if any(bytes.fromhex(n) in d for n in sys.argv[2:]) else 1)' \
		"$kohds" a03500e30a0c52e3 0a0c52e33e0000ca041091e5a03500e3 a03500e3030058e10a0c5793 \
		|| bbfatal "R2K: hi_fb.ko din ${PN} nu e peticit pentru 2560x1440 (alta arhiva a producatorului: de citit din nou)"
}
