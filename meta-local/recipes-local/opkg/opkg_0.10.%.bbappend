# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# opkg (0.7.5, LIB 13.11.2026): wget-ul cu care opkg descarca pachetele primeste --read-timeout=60 si --tries=3 (peste
# --dns-timeout/--connect-timeout din timeout.patch al OE-Alliance). Pe 13.11.2026 doua descarcari din feedul extern s-au agatat
# pe receptorul de probe dupa conectare si au tinut opkg (si instalarea din Extensii) 12 minute, fara sfarsit. Tabloul de argumente marit de la 8
# la 12 (era deja plin). Opkg-ul din imagine foloseste wget-ul GNU (pachetul wget, in toate imaginile 0.7.x), care are optiunile.
FILESEXTRAPATHS:prepend := "${THISDIR}/opkg:"
SRC_URI += "file://hds-wget-read-timeout.patch"
PR:append = ".hds1"
