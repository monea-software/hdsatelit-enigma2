# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# opkg (0.7.5, LIB 13.11.2026): wget-ul cu care opkg descarca pachetele primeste --read-timeout=60 si --tries=3 (peste
# --dns-timeout/--connect-timeout din timeout.patch al OE-Alliance). Pe 13.11.2026 doua descarcari din feedul extern s-au agatat
# pe receptorul de probe dupa conectare si au tinut opkg (si instalarea din Extensii) 12 minute, fara sfarsit. Tabloul de argumente marit de la 8
# la 12 (era deja plin). Opkg-ul din imagine foloseste wget-ul GNU (pachetul wget, in toate imaginile 0.7.x), care are optiunile.
# UPD1 (25.11.2026): si antetul --user-agent=hdsatelit-receptor/1 (opkg); cu antetul implicit Wget/1.25.0 protectia
# anti-roboti din fata feedului oprea uneori cererile (actualizarea si Extensii nu mergeau). Tabloul argv la 14.
FILESEXTRAPATHS:prepend := "${THISDIR}/opkg:"
SRC_URI += "file://hds-wget-read-timeout.patch file://hds-wget-user-agent.patch"
PR:append = ".hds2"
