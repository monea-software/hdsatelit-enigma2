# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Vu+ Duo 4K Lite (vuduo4klite): reteta linux-vuplus_4.1.20 din meta-vuplusde (vuplus-linux-4.1.20-20250410, aceleasi
# petice mn88472 0013-0017 din meta-oe). Acelasi petic ca la Uno 4K SE / Zero 4K (recipes-local/linux-vuplus, acolo
# explicatia): mn88472 da puterea, CNR si erorile prin DTV_STAT_*, ca in Linux 4.12 (XBS8, 22.11.2026). Driverul de
# dupa 0013-0017 e identic cu cel din stblinux-4.1-1.9 (diff -r), peticul trece.
# Dosar separat de recipes-local/linux-vuplus, fiindca acela se citeste numai cu vuplus-layer (BBMASK in
# conf/distro/hdsatelit.conf: linux-vuplus_4.1.45.bbappend n-are reteta in meta-vuplusde); acesta numai cu vuplusde-layer.
# Numai modulul mn88472.ko se schimba; versiunea noua numai pe pachetul modulului (kernel-image ramane cum e).

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI += "file://mn88472-dvbv5-statistici.patch"
# CST8 (22.11.2026): PKGR pe un pachet facut abia la impachetare (kernel-module-*, din PACKAGES_DYNAMIC) nu intra in
# semnatura sarcinilor, deci un sstate mai vechi cu acelasi petic (constructia de proba XBS8) da pachetul fara .hds1
# (masurat: kernel-module-mn88472-4.1.20-1.9_4.1.20-r12.rginput1). Variabila de mai jos il pune in semnatura lui do_package.
HDS_MN88472_PKGR = "hds1"
do_package[vardeps] += "HDS_MN88472_PKGR"
PKGR:kernel-module-mn88472-4.1.20-1.9 = "${PR}.${HDS_MN88472_PKGR}"
