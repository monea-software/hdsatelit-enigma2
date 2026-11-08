# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# NUMAI pentru stratul OE-Alliance 6.0 (pregateste-strat-60.sh il pune peste meta-local). ServiceApp (fluxurile 5001 si
# 5002) se face pentru FEEDUL imaginii 0.7.1, nu intra in imagine: se instaleaza din meniu. Reteta din meta-oe-alliance
# cere pachetul "enigma2", pe care stratul nostru il scoate din citire (BBMASK in conf/distro/hdsatelit.conf); aici se
# leaga de enigma2-hdsatelit, care pune in sysroot enigma2.pc si antetele (sigc++-3.0; ramura develop a pluginului stie
# si 2, si 3). Fara -std=c++11: reteta il adauga pentru orice distributie pe care nu o stie, iar antetele noastre cer
# C++17 (configure.ac, MM_AX_CXX_COMPILE_STDCXX 17). Pachetul depinde de enigma2-ul modelului (PACKAGE_ARCH de masina,
# ca enigma2-hdsatelit), deci tine de masina, nu numai de procesor.
DEPENDS:remove = "enigma2"
DEPENDS:append = " enigma2-hdsatelit"
RDEPENDS:${PN}:remove = "enigma2"
RDEPENDS:${PN}:append = " enigma2-hdsatelit"
CXXFLAGS:remove = "-std=c++11"
PACKAGE_ARCH = "${MACHINE_ARCH}"
