# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Octagon SX88V2 4K DUAL OS (masina sx88v2, V19 14.11.2026; familia hisi3798mv300 cu libreader): ca pe SF8008 (octagon-libreader-hisi3798mv200.bbappend),
# scriptul rcS S05 al producatorului porneste libreader in prim-plan si pornirea se opreste acolo pe o placa a carei
# verificare de autorizare nu trece. Scriptul nostru (files/) face aceiasi pasi, cu libreader in fundal, asteptat cel mult
# 60 de secunde. Scriptul producatorului pentru mv300 e IDENTIC cu cel mv200 (md5 7db27a86...), deci acelasi script al nostru.
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
PR:append = ".hds1"
