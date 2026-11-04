# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Octagon SF8008 MINI 4K (masina sf8008m): scriptul flash-apploader scos din imagine, ca la V20, V10 si SF8008
# (dinobot-partitions-hisi3798mv200.bbappend, acolo e intreaga explicatie; octagon-partitions-sf8008.bbappend la SF8008).
#
# De ce: pachetul octagon-partitions-sf8008m (meta-octagon, adus de masina prin MACHINE_ESSENTIAL_EXTRA_RDEPENDS din
# octagon-hisi.inc) pune /etc/init.d/flash-apploader, pornit la fiecare pornire (S90). Scriptul compara primii 4 MiB din
# partitia "loader" (by-name/loader) cu /usr/share/apploader.bin si, daca difera, rescrie partitia cu dd. Partitia
# loader e plasa de siguranta a receptorului; imaginea noastra nu o scrie niciodata (REGULI-FLASH-RECEPTOR.md).
#
# Ce face acest fisier (acelasi corp ca octagon-partitions-sf8008.bbappend; reteta producatorului e aceeasi, alta arhiva):
#  - INHIBIT_UPDATERCD_BBCLASS: fara postinst/prerm/postrm de update-rc.d, deci fara legatura
#    /etc/rcS.d/S90flash-apploader in imagine;
#  - scriptul se sterge din ${D} dupa instalarea facuta de reteta producatorului (citita doar pentru intelegere);
#  - raman fisierele de date ale pachetului, numai cele trei stiute: /usr/share/bootargs.bin, fastboot.bin si
#    apploader.bin (nu scriu nimic singure; pachetul ramane, ca dependinta ceruta de masina sa fie satisfacuta).
#    do_deploy al retetei (fisierele pentru usb_update.bin, in deploy/images/sf8008m/sf8008m-partitions) nu se atinge;
#  - constructia se opreste cu eroare, nu trece tacut, daca scriptul nu mai e unde il stim (alta reteta: de citit din
#    nou) sau daca in pachet ramane altceva decat cele trei fisiere de date;
#  - PR cu ".hds1", ca pachetul schimbat sa se vada in manifest si in "opkg list-installed" pe receptor.

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
