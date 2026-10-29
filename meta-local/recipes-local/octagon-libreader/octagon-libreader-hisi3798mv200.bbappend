# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Octagon SF8008 si SF8008 MINI 4K (familia hisi3798mv200 cu libreader): scriptul de pornire rcS S05 al producatorului
# porneste libreader in prim-plan; pe o placa a carei verificare de autorizare nu trece, libreader nu devine demon
# niciodata si pornirea se opreste acolo, fara retea, fara interfata si fara diagnostic. Scriptul nostru (files/) face
# aceiasi pasi, cu libreader in fundal si asteptat cel mult 60 de secunde.
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
PR:append = ".hds1"
