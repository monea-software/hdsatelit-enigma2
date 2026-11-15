# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# NUMAI pentru stratul OE-Alliance 6.0 (pregateste-strat-60.sh il pune peste meta-local). ServiceApp (fluxurile 5001 si
# 5002) se face pentru FEEDUL imaginii, nu intra in imagine: se instaleaza din meniu. Reteta din meta-oe-alliance
# cere pachetul "enigma2", pe care stratul nostru il scoate din citire (BBMASK in conf/distro/hdsatelit.conf); aici se
# leaga de enigma2-hdsatelit, care pune in sysroot enigma2.pc si antetele (sigc++-3.0). Fara -std=c++11: reteta il
# adauga pentru orice distributie pe care nu o stie, iar antetele noastre cer C++17. Pachetul depinde de enigma2-ul
# modelului (PACKAGE_ARCH de masina, ca enigma2-hdsatelit), deci tine de masina, nu numai de procesor.
#
# 11.11.2026 (Sarcina A): sursa e ramura sig3 (sigc++ 3 fara macro-uri vechi), fixata, nu AUTOREV, plus peticul care o
# leaga de interfata enigma2-ului nostru (subtitrarile cu eWidget si tuplu Python, fara iTapService, iStreamBufferInfo,
# eConfigManager, alternativeurl). Peticul se face din nou cu lucru-sesiune/paralel-1111/unelte-a/porteaza_serviceapp.py
# daca se schimba SRCREV.
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI = "git://github.com/oe-mirrors/serviceapp.git;branch=sig3;protocol=https \
           file://0001-serviceapp-enigma2-hdsatelit.patch \
           file://0002-serviceapp-hds-exteplayer3-solose.patch \
           file://0003-serviceapp-hds-fara-listdir-pe-flux.patch \
           file://0004-serviceapp-hds-exteplayer3-reconectare.patch \
           "
# 15.11.2026 (SSE, TODO 14.11 22:37): 0002 = pe Vu+ Solo SE IPTV implicit prin exteplayer3 ("inlocuieste servicemp3" si
# playerul exteplayer3, o singura data, numai daca omul nu a ales nimic in ServiceApp); se face din nou cu
# lucru-sesiune/paralel-1111b/runda-0013/SSE/fa_petic_0002.py daca se schimba SRCREV. PR r9 (dupa r8).
# 15.11.2026 (SAL, TODO 14.11 22:37): 0003 = getSubtitleList nu mai cauta subtitrari externe (access, listDir) pe adresa
# unui flux, numai pe caile de pe disc: fara "listDir(<adresa>) - error in opendir" in jurnal la fiecare cerere. Sursa
# pentru proba: lucru-sesiune/paralel-1111b/runda-0013/SAL/sursa-485bb98 (teste/test_sal_serviceapp_075.py). PR r10.
# 15.11.2026 (IRC, TODO 15.11 05:35): 0004 = exteplayer3 reface singur legatura unui flux viu de pe internet (http, https):
# "-f reconnect_streamed=1 -f reconnect_on_network_error=1 -f reconnect_delay_max=15", fiecare ca doua argumente (exteplayer3
# pune singur numai timeout si reconnect; reconnect_streamed numai cu -v). Sursa pentru proba:
# lucru-sesiune/paralel-1111b/runda-0013/IRC/sursa-485bb98 (teste/test_irc_serviceapp_reconectare_075.py). PR r11.
SRCREV = "485bb98ffc2496f7e313eb5a62fa90c7925ba7b0"
DEPENDS:remove = "enigma2"
DEPENDS:append = " enigma2-hdsatelit"
RDEPENDS:${PN}:remove = "enigma2"
# gstplayer: ServiceApp porneste gstplayer_gst-1.0 pentru 5001 (legatura facuta de pachetul gstplayer la instalare);
# reteta OE-A cere numai gstplayer2, care e alt program
# 14.11.2026 (SAP): enigma2-hdsatelit cel putin versiunea imaginii pentru care se construieste (serviceapp.so foloseste
# simbolurile binarului enigma2: pe o baza mai veche opkg aduce intai enigma2-hdsatelit din feed), dar NU exact o
# constructie: o republicare a lui enigma2-hdsatelit fara schimbari C++ (C74, c56b96f3f5) nu mai lasa ServiceApp
# neinstalabil. Reteta OE-A cere "enigma2" fara versiune; `=` din feedul 0.7.4 (r7) l-a pus de mana pregateste_sva.py,
# nu reteta. In feed e acum r7.1 (fa_feed_sap.py, `>=`), deci PR r8: o constructie noua trebuie sa fie mai noua pentru opkg.
# Daca enigma2-hdsatelit se schimba in C++ in aceeasi versiune, ServiceApp se reconstruieste odata cu el (PR + 1).
# 15.11.2026 (SVA, poarta 0.7.6): versiunea ramane (serviceapp.so pe un enigma2 mai vechi nu s-ar incarca), dar
# enigma2-hdsatelit tras de aici din Extensii (si cu "Actualizeaza toate") nu mai ramane pe jumatate: pkg_postinst-ul lui
# (meta-local/recipes-local/enigma2-hdsatelit, blocul NVK/SVA) cere interfetei pornite actualizarea rapida (tema si restul
# setului din feedul semnat, apoi repornirea interfetei). Orice reteta care cere enigma2-hdsatelit cu versiune se sprijina
# pe acelasi bloc (proba teste/test_sva_extensii_trag_imaginea_075.py).
PR = "r11"
RDEPENDS:${PN}:append = " enigma2-hdsatelit (>= ${DISTRO_VERSION}) gstplayer"
CXXFLAGS:remove = "-std=c++11"
PACKAGE_ARCH = "${MACHINE_ARCH}"
