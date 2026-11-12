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
           "
SRCREV = "485bb98ffc2496f7e313eb5a62fa90c7925ba7b0"
DEPENDS:remove = "enigma2"
DEPENDS:append = " enigma2-hdsatelit"
RDEPENDS:${PN}:remove = "enigma2"
# gstplayer: ServiceApp porneste gstplayer_gst-1.0 pentru 5001 (legatura facuta de pachetul gstplayer la instalare);
# reteta OE-A cere numai gstplayer2, care e alt program
RDEPENDS:${PN}:append = " enigma2-hdsatelit gstplayer"
CXXFLAGS:remove = "-std=c++11"
PACKAGE_ARCH = "${MACHINE_ARCH}"
