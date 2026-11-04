# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# NUMAI pentru stratul OE-Alliance 6.0. Pe 5.6 reteta noastra wpa-supplicant_2.12.bb punea /etc/wpa_supplicant.conf
# fara nicio retea (files/wpa_supplicant.conf-sane al nostru). In 6.0 openembedded-core are aceeasi versiune 2.12,
# deci pregateste-strat-60.sh scoate reteta noastra, iar fisierul din openembedded-core pune din fabrica o retea
# deschisa straina (network={ key_mgmt=NONE }): receptorul s-ar lega singur de orice Wi-Fi deschis. Aici fisierul
# nostru il inlocuieste pe acela (acelasi nume, cautat intai aici); constructia se opreste daca imaginea ar avea totusi
# o retea in fisier.
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
PR:append = ".hds1"

do_install:append() {
	if grep -q 'network=' ${D}${sysconfdir}/wpa_supplicant.conf; then
		bbfatal "wpa-supplicant: /etc/wpa_supplicant.conf are o retea pusa din fabrica"
	fi
}
