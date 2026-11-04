# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Uclan Ustym 4K PRO (masina ustym4kpro): scriptul flash-apploader scos din imagine, ca la V20, V10 si SF8008
# (dinobot-partitions-hisi3798mv200.bbappend, acolo e intreaga explicatie; octagon-partitions-sf8008.bbappend la SF8008).
#
# De ce: pachetul uclan-partitions-ustym4kpro (meta-uclan, adus de masina prin MACHINE_ESSENTIAL_EXTRA_RDEPENDS din
# uclan-hisi.inc; reteta are acelasi corp ca octagon-partitions-sf8008, alta arhiva) pune /etc/init.d/flash-apploader,
# pornit la fiecare pornire (S90), care rescrie partitia loader daca difera de /usr/share/apploader.bin. Partitia
# loader e plasa de siguranta a receptorului; imaginea noastra nu o scrie niciodata (REGULI-FLASH-RECEPTOR.md).
# Ce face: acelasi corp ca octagon-partitions-sf8008.bbappend (fara update-rc.d, scriptul sters, raman numai
# bootargs.bin, fastboot.bin si apploader.bin, constructia se opreste daca reteta s-a schimbat), PR cu ".hds1".
PR:append = ".hds1"

INHIBIT_UPDATERCD_BBCLASS = "1"

do_install:append() {
    [ -f ${D}${sysconfdir}/init.d/flash-apploader ] || \
        bbfatal "HDSatelit: reteta ${PN} nu mai instaleaza /etc/init.d/flash-apploader; de revazut bbappend-ul"
    rm -f ${D}${sysconfdir}/init.d/flash-apploader
    rmdir ${D}${sysconfdir}/init.d ${D}${sysconfdir} 2>/dev/null || true
    # Paza: in pachet raman numai cele trei fisiere de date din /usr/share.
    rest=$(find ${D} ! -type d ! -path ${D}/usr/share/bootargs.bin ! -path ${D}/usr/share/fastboot.bin \
        ! -path ${D}/usr/share/apploader.bin)
    if [ -n "$rest" ]; then
        bbfatal "HDSatelit: in pachetul ${PN} a ramas altceva decat bootargs.bin, fastboot.bin si apploader.bin: $rest"
    fi
    for f in bootargs.bin fastboot.bin apploader.bin; do
        [ -s ${D}/usr/share/$f ] || bbfatal "HDSatelit: lipseste /usr/share/$f din pachetul ${PN}"
    done
}
