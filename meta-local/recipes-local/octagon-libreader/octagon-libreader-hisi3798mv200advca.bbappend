# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Octagon SX988 4K DUAL OS (masina sx988, V19 14.11.2026; familia hisi3798mv200advca cu libreader): ca pe SF8008 (octagon-libreader-hisi3798mv200.bbappend),
# scriptul rcS S05 al producatorului porneste libreader in prim-plan si pornirea se opreste acolo pe o placa a carei
# verificare de autorizare nu trece. Scriptul nostru (files/) face aceiasi pasi, cu libreader in fundal, asteptat cel mult
# 60 de secunde. Scriptul producatorului pentru mv200advca difera de cel mv200 numai prin resize2fs /dev/mmcblk0p19 (userdata) si
# mount /dev/mmcblk0p7 /boot/ (bootoptions in tabela advca); scriptul nostru are aceleasi doua schimbari.
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
PR:append = ".hds1"
