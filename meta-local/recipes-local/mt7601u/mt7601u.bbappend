# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Driver Wi-Fi USB din feed (hdsatelit-drivere-feed, 11.11.2026, agentul WD), instalat singur cand omul baga stickul.
# Amiko Viper 4K V20, V30, Protek 4K X2 (u57) si V40 (u571): modulul cu -mlong-calls, ca modulele nucleului (motivul in
# dinobot-kernel/linux-dinobot_%.bbappend: zona modulelor e la 32,25 MB de capatul codului nucleului; un modul care
# nimereste la inceputul ei cade cu "relocation out of range"). Driverul e din afara nucleului, deci KCFLAGS (din
# kcflags.inc, dat lui make prin mediu) atinge numai modulul. Pe celelalte masini reteta ramane neschimbata.
KCFLAGS:append:u57 = " -mlong-calls"
KCFLAGS:append:u571 = " -mlong-calls"

# ZER1: driverul furnizorului avea -DDBG si RTDebugLevel=RT_DEBUG_TRACE.
# Se scoate numai optiunea exacta DBG, fara atingerea optiunilor BG_FT.
PR:append = ".hdszer1.hdsbld1.hdsmtd5"

# CPL1: dispecerul nu poate chema functii existente numai cu DBG.
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI += " file://0001-guard-debug-ioctls.patch file://0002-debug-oprit-implicit.patch"
do_configure:append() {
    sed -i 's/ -DDBG$//' ${S}/os/linux/config.mk
    if grep -Eq '[[:space:]]-DDBG([[:space:]]|$)' ${S}/os/linux/config.mk; then
        bbfatal "Depanarea driverului Wi-Fi a ramas activa"
    fi
}

# Modulul trebuie sa aduca profilul si cand e instalat direct, fara metapachet.
PACKAGES =+ "${PN}-config"
FILES:${PN}-config = "${sysconfdir}/Wireless/MT7601U"
CONFFILES:${PN}-config = "${sysconfdir}/Wireless/MT7601U/MT7601U.dat ${sysconfdir}/Wireless/MT7601U/MT7601UCard.dat"
# Permite mutarea numai din versiunile vechi, fara a exclude parintele curent.
# CONFFILES pastreaza profilul modificat la transferul catre pachetul separat.
RREPLACES:${PN}-config = "${PN} (< ${EXTENDPKGV})"
RDEPENDS:${PN}:append = " ${PN}-config"
PACKAGESPLITFUNCS:append = " hds_mt7601_config_depend"

python hds_mt7601_config_depend() {
    for package in (d.getVar('PACKAGES') or '').split():
        if 'kernel-module-mt7601usta' in package:
            d.appendVar('RDEPENDS:' + package, ' ' + d.getVar('PN') + '-config')
}

do_install:append() {
    test -s ${D}${sysconfdir}/Wireless/MT7601U/MT7601U.dat || bbfatal "Lipseste profilul MT7601U"
}
