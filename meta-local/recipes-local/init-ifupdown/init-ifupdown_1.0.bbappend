# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Octagon SF8008 si SF8008 MINI: /etc/init.d/networking (rc3 S10) nu mai tine pornirea cat asteapta reteaua. ifup -a
# din busybox cheama "udhcpc -R -b", care trece DHCP in fundal numai dupa 3 runde de cautare (3 x 3 s); fara cablu sau
# numai cu Wi-Fi, pasul S10networking statea astfel 9-15 s (masurat in chroot, lucru-sesiune/pilot-26-09/wifi-sf8008).
# files/hds-networking e scriptul masinii (cel din OE-Alliance, cu check_wol_enable la oprire) cu o singura schimbare la
# pornire: lo indata, restul interfetelor cu ifup -a in fundal. Numai pe sf8008 si sf8008m; pe celelalte masini
# reteta ramane neschimbata. /etc/network/interfaces (conffile) nu se schimba.
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI:append:sf8008 = " file://hds-networking"
SRC_URI:append:sf8008m = " file://hds-networking"
PR:append:sf8008 = ".hds1"
PR:append:sf8008m = ".hds1"
# Uclan Ustym 4K PRO (ustym4kpro): scriptul masinii din OE-Alliance (meta-oe/recipes-core/init-ifupdown/ustym4kpro/init)
# e identic cu cel SF8008, deci acelasi hds-networking.
SRC_URI:append:ustym4kpro = " file://hds-networking"
PR:append:ustym4kpro = ".hds1"
# GigaBlue UHD TRIO 4K (masina gbmv200, MACHINEBUILD gbtrio4k): scriptul masinii din OE-Alliance
# (meta-oe/recipes-core/init-ifupdown/gbmv200/init) e identic cu cel SF8008, deci acelasi hds-networking.
SRC_URI:append:gbtrio4k = " file://hds-networking"
PR:append:gbtrio4k = ".hds1"

do_install:append:sf8008() {
	install -m 0755 ${UNPACKDIR}/hds-networking ${D}${sysconfdir}/init.d/networking
}

do_install:append:sf8008m() {
	install -m 0755 ${UNPACKDIR}/hds-networking ${D}${sysconfdir}/init.d/networking
}

do_install:append:ustym4kpro() {
	install -m 0755 ${UNPACKDIR}/hds-networking ${D}${sysconfdir}/init.d/networking
}

do_install:append:gbtrio4k() {
	install -m 0755 ${UNPACKDIR}/hds-networking ${D}${sysconfdir}/init.d/networking
}

# Fisa 35: aceeasi pornire (lo indata, restul retelei in fundal, ifup cu fluxurile inchise) pentru cele trei Vu+ 4K.
# GigaBlue UHD TRIO 4K (gbtrio4k) o are deja prin randurile lui de mai sus, deci nu intra aici a doua oara.
HDS_RETEA_FUNDAL = "0"
HDS_RETEA_FUNDAL:vuduo4k = "1"
HDS_RETEA_FUNDAL:vuuno4kse = "1"
HDS_RETEA_FUNDAL:vusolo4k = "1"
SRC_URI:append = " ${@'file://hds-networking' if d.getVar('HDS_RETEA_FUNDAL') == '1' else ''}"
PR:append = "${@'.hds35' if d.getVar('HDS_RETEA_FUNDAL') == '1' else ''}"

do_install:append() {
    if [ "${HDS_RETEA_FUNDAL}" = 1 ]; then
        install -m 0755 ${UNPACKDIR}/hds-networking ${D}${sysconfdir}/init.d/networking
    fi
}
