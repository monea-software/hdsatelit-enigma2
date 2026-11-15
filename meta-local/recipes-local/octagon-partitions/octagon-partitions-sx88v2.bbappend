# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Octagon SX88V2 4K DUAL OS (masina sx88v2, V19 14.11.2026): scriptul flash-apploader scos din imagine, ca la SF8008
# (octagon-partitions-sf8008.bbappend; intreaga explicatie in dinobot-partitions-hisi3798mv200.bbappend).
# Pachetul octagon-partitions-sx88v2 (arhiva sx88v2-partitions-20221216, adus de masina prin MACHINE_ESSENTIAL_EXTRA_RDEPENDS din
# octagon-hisi.inc) pune /etc/init.d/flash-apploader, pornit la fiecare pornire (S90), care rescrie partitia loader cu dd
# cand primii 4 MiB difera de /usr/share/apploader.bin. Partitia loader e plasa de siguranta a receptorului (si meniul de
# recuperare din care omul alege intre Enigma2 si Define OS); imaginea noastra nu o scrie niciodata (REGULI-FLASH-RECEPTOR.md).
# Reteta are acelasi corp ca octagon-partitions-sf8008 (aceleasi trei fisiere de date in /usr/share).
# Fara legatura rcS (INHIBIT_UPDATERCD_BBCLASS), scriptul sters, raman numai fisierele de date stiute: bootargs.bin, fastboot.bin, apploader.bin.
# Constructia se opreste cu eroare daca scriptul nu mai e unde il stim sau daca in pachet ramane altceva.

PR:append = ".hds1"

INHIBIT_UPDATERCD_BBCLASS = "1"

do_install:append() {
    [ -f ${D}${sysconfdir}/init.d/flash-apploader ] || \
        bbfatal "HDSatelit: reteta ${PN} nu mai instaleaza /etc/init.d/flash-apploader; de revazut bbappend-ul"
    rm -f ${D}${sysconfdir}/init.d/flash-apploader
    rmdir ${D}${sysconfdir}/init.d ${D}${sysconfdir} 2>/dev/null || true
    rest=$(find ${D} ! -type d ! -path ${D}/usr/share/bootargs.bin ! -path ${D}/usr/share/fastboot.bin ! -path ${D}/usr/share/apploader.bin)
    if [ -n "$rest" ]; then
        bbfatal "HDSatelit: in pachetul ${PN} a ramas altceva decat bootargs.bin, fastboot.bin, apploader.bin: $rest"
    fi
    for f in bootargs.bin fastboot.bin apploader.bin; do
        [ -s ${D}/usr/share/$f ] || bbfatal "HDSatelit: lipseste /usr/share/$f din pachetul ${PN}"
    done
}
