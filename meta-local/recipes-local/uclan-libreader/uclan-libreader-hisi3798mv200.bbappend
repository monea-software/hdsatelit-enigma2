# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Uclan Ustym 4K PRO (familia hisi3798mv200 cu libreader, ca Octagon SF8008): scriptul de pornire rcS S05 al
# producatorului (identic cu cel Octagon, afara de nume) porneste libreader in prim-plan; pe o placa a carei verificare
# de autorizare nu trece, libreader nu devine demon niciodata si pornirea se opreste acolo. Scriptul nostru (files/,
# acelasi ca la octagon-libreader-hisi3798mv200.bbappend) face aceiasi pasi, cu libreader in fundal si asteptat cel
# mult 60 de secunde.
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
PR:append = ".hds1"
