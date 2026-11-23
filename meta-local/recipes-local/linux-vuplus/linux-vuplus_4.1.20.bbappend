# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Vu+ Uno 4K SE si Vu+ Zero 4K (nucleul Vu+ 4.1.20, stblinux-4.1-1.9, meta-vuplus; Vu+ Duo 4K Lite are reteta ei in
# meta-vuplusde si bbappend-ul ei in recipes-local/linux-vuplusde): demodulatorul mn88472 (tunerul USB Xbox One
# DVB-T2, cu tda18250) da puterea, raportul semnal/zgomot (CNR) si erorile de pachete prin statisticile DVBv5
# (DTV_STAT_*), ca in Linux 4.12 (XBS8, 22.11.2026; forumul 801, Uno 4K SE 0.7.7: bara de semnal 0 % cu imagine buna).
# Driverul din staging de acum (seria oe-alliance 0013-0017, "mn88472: finalize driver", mai 2016) nu le da pe nicio
# cale; enigma2 le citeste prin FE_GET_PROPERTY cand citirile vechi dau eroare (lib/dvb/hdsstatdvb5.h).
#
# Numai modulul mn88472.ko se schimba (CONFIG_DVB_MN88472=m): vmlinux si zImage raman la fel, vermagic la fel
# ("4.1.20-1.9 SMP mod_unload ARMv7 p2v8"). Versiunea noua o primeste numai pachetul modulului (numele lui poarta
# versiunea nucleului: kernel-module-mn88472-4.1.20-1.9; PKGR cu ".hds1"), ca Actualizarea software sa aduca modulul fara
# sa atinga kernel-image (al carui postinst scrie nucleul).
# Driverul dupa 0013-0017 e IDENTIC in toate trei sursele 4.1 (stblinux-4.1-1.9, stblinux-4.1-1.17 a lui Duo 4K si
# Duo 4K SE, vuplus-linux-4.1.20-20250410 a lui Duo 4K Lite; diff -r, XBS8), deci acelasi petic si in
# linux-vuplus_4.1.45.bbappend. Vu+ Solo4K, Ultimo4K, Uno4K (3.14.28) nu au mn88472.

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI += "file://mn88472-dvbv5-statistici.patch"
# CST8 (22.11.2026): PKGR pe un pachet facut abia la impachetare (kernel-module-*, din PACKAGES_DYNAMIC) nu intra in
# semnatura sarcinilor, deci un sstate mai vechi cu acelasi petic (constructia de proba XBS8) da pachetul fara .hds1
# (masurat: kernel-module-mn88472-4.1.20-1.9_4.1.20-r12.rginput1). Variabila de mai jos il pune in semnatura lui do_package.
HDS_MN88472_PKGR = "hds1"
do_package[vardeps] += "HDS_MN88472_PKGR"
PKGR:kernel-module-mn88472-4.1.20-1.9 = "${PR}.${HDS_MN88472_PKGR}"
