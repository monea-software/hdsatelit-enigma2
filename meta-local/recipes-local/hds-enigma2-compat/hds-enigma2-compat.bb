# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# hds-enigma2-compat (0.7.4): pachetul REAL „enigma2” 2.7+hds1 al imaginii, gol, cu „Depends: enigma2-hdsatelit”.
# Pluginurile scrise pentru alte imagini cer „Depends: enigma2”, unele cu versiune (EPGImport 2.6: enigma2 >= 2.5). In 0.7.3
# numele venea din „RPROVIDES enigma2” al lui enigma2-hdsatelit, dar opkg-ul imaginii (0.10.0 cu libsolv) nu tine cont de
# versiunea din Provides, deci „enigma2 (>= 2.5)” cadea, iar pachetul de compatibilitate din feedul extern se batea cu
# Provides-ul („implicitly obsoletes enigma2 provided by enigma2-hdsatelit”). Acum Provides-ul e scos
# (strat-60/.../enigma2-hdsatelit.bbappend) si pachetul real vine din feedul imaginii, cerut de hdsatelit-base, deci si prin
# actualizare: proba unelte/stb/proba_opkg_provides.py (.122, 10.11.2026) arata ca fara el in aceeasi tranzactie opkg tine
# pe loc, fara mesaj, furnizorul care pierde Provides-ul (receptoare cu versiuni amestecate). Acelasi continut si nume ca
# pachetul din feedul extern (aio-panel/compatibilitate-enigma2/build_compat_ipk.py), cu revizia r0 in plus (mai nou).
# Reteta enigma2 a OE-Alliance nu se construieste in imagine (nu e in pkgdata), deci numele de pachet e liber.
SUMMARY = "Numele enigma2 pentru pluginurile scrise pentru alte imagini"
DESCRIPTION = "Pachet gol: da numele enigma2 (versiunea 2.7) cerut de pluginuri si trage enigma2-hdsatelit."
LICENSE = "GPL-2.0-only"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/GPL-2.0-only;md5=801f80980d171dd6425610833a22dbe6"

PV = "2.7+hds1"

inherit allarch

PACKAGES = "${PN}"
PKG:${PN} = "enigma2"
ALLOW_EMPTY:${PN} = "1"
RDEPENDS:${PN} = "enigma2-hdsatelit"

do_configure[noexec] = "1"
do_compile[noexec] = "1"
