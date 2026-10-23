# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Recodarea DTS -> AC3 la redarea fisierelor: cand /etc/enigma2/hds-dts-ac3 incepe cu "1" (setarea din enigma2),
# dvbaudiosink nu mai primeste audio/x-dts, deci decodebin pune intre dcaparse si sink elementul hdsdtsac3
# (gstreamer1.0-plugin-hds-dts-ac3, alaturi), care da AC3. Fara fisier sau cu alt continut nimic nu se schimba; DTS-ul
# de pe DVD (audio/x-private1-dts) ramane la sink ca pana acum.
# Se aplica impreuna cu bbappend-ul optiunilor sink-urilor (recipes-local/gstreamer/gstreamer1.0-plugin-dvbmediasink
# .bbappend): BitBake le ia pe amandoua; cele doua se pot uni intr-unul la integrare.
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI += "file://0001-dvbaudiosink-dts-recodat-in-ac3.patch"

# Sursa fixata la comiterea din imaginea 0.4.0 (probata pe receptor cu recodarea DTS -> AC3). Stratul comun ia altfel
# varful ramurii (SRCREV:pn-... ?= AUTOREV in unstable-versions.inc), iar comiterea urmatoare din amonte
# (201afd04, DTS nativ pe alte receptoare) schimba exact locul peticului din gstdvbaudiosink.c: peticul intra cu
# "fuzz 2", adica nedovedit (lotul imagine-050). Peticul se aduce la zi pe sursa noua intr-un lot separat, cu proba.
SRCREV:pn-gstreamer1.0-plugin-dvbmediasink = "66ff8288dabe07aa52866544f101138defaff3d1"

# elementul vine in imagine odata cu sink-ul
RRECOMMENDS:${PN} += "gstreamer1.0-plugin-hds-dts-ac3"

do_compile:append() {
	grep -q 'hds-dts-ac3' ${S}/common.c || bbfatal "dvbmediasink: peticul DTS -> AC3 nu e aplicat"
}
