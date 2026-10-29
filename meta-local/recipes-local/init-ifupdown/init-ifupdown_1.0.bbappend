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

do_install:append:sf8008() {
	install -m 0755 ${UNPACKDIR}/hds-networking ${D}${sysconfdir}/init.d/networking
}

do_install:append:sf8008m() {
	install -m 0755 ${UNPACKDIR}/hds-networking ${D}${sysconfdir}/init.d/networking
}
