# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# GigaBlue UHD TRIO 4K (masina gbmv200, familia hisi3798mv200 cu libreader, ca Octagon SF8008): scriptul de pornire rcS
# S05 al producatorului (gigablue-libreader-gbmv200.sh din meta-gigablue, identic cu cel Octagon) porneste libreader in
# prim-plan; pe o placa a carei verificare de autorizare nu trece, libreader nu devine demon niciodata si pornirea se
# opreste acolo. Scriptul nostru (files/, acelasi ca la octagon-libreader-hisi3798mv200.bbappend si
# uclan-libreader-hisi3798mv200.bbappend) face aceiasi pasi, cu libreader in fundal si asteptat cel mult 60 de secunde.
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
PR:append = ".hds1"
