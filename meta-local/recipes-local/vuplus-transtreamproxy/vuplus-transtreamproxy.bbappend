# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# transtreamproxy in imaginea HD Satelit (TRC, 15.11.2026; TODO 15.11 01:56): transcodarea unui canal spre telefon sau
# tableta pe receptoarele Vu+ cu codor (Solo 4K, Uno 4K SE, Duo 4K, Duo 4K SE, Ultimo 4K, Uno 4K, Duo 4K Lite), pe
# portul 8002, ca in celelalte imagini Enigma2. Il cere pluginul TransCodingSetup (Extensii, feedul extern).
# Sursa si licenta raman ale autorilor: GPL-3.0-only (COPYING), git github.com/oe-mirrors/filestreamproxy, ramura
# transtreamproxy; reteta de baza e cea OE-Alliance (meta-brands/meta-vuplus si meta-vuplusde,
# recipes-transcode/vuplus-transtreamproxy.bb), deci acest bbappend se aplica pe amandoua.
# Fata de reteta OE-Alliance:
# - SRCREV fix (nu AUTOREV): aceeasi sursa la fiecare constructie; depozitul e in unelte/paznic/depozite-urmarire.json
#   (noutatile se anunta, recompilam din sursa);
# - fara inetd-ul sistemului (virtual-inetd si randul 8002 din /etc/inetd.conf): imaginea nu are inetd
#   (BAD_RECOMMENDATIONS busybox-inetd si paza ssh din hdsatelit-image.bb opresc constructia cu el). Portul il tine
#   serviciul nostru hds-transcodare: `busybox inetd -f /etc/hds-transcodare.conf`, ca Telnet-ul din hdsatelit-ssh;
#   fiecare legatura trece intai prin hds-transcodare-poarta: numai din reteaua de acasa (aceleasi retele ca la SSH,
#   FTP si Telnet), altfel legatura se inchide;
# - transtreamproxy cere canalul de la interfata web a receptorului (GET /web/stream?StreamService=<referinta> pe
#   127.0.0.1:80); raspunsul il da HdsWebControl (flux_transcodare_web.py, din imaginea 0.7.6).
# Pluginul TransCodingSetup schimba portul in /etc/hds-transcodare.conf (peticul lui din meta-pluginuri-externe).
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SRCREV = "7275da4c95a6cd1d805ec8dd82e98617f99e141a"
PR:append = ".hds1"

SRC_URI += "file://hds-transcodare file://hds-transcodare.conf file://hds-transcodare-poarta"

RDEPENDS:${PN}:remove = "virtual-inetd"

inherit update-rc.d
INITSCRIPT_NAME = "hds-transcodare"
INITSCRIPT_PARAMS = "defaults 95"

do_install:append() {
    install -d ${D}${sysconfdir}/init.d ${D}${sbindir}
    install -m 0755 ${UNPACKDIR}/hds-transcodare ${D}${sysconfdir}/init.d/hds-transcodare
    install -m 0644 ${UNPACKDIR}/hds-transcodare.conf ${D}${sysconfdir}/hds-transcodare.conf
    install -m 0755 ${UNPACKDIR}/hds-transcodare-poarta ${D}${sbindir}/hds-transcodare-poarta
    # paza: numai poarta noastra pe port, niciun rand pentru inetd-ul sistemului
    [ "$(grep -v '^#' ${D}${sysconfdir}/hds-transcodare.conf | grep -c .)" = 1 ] || \
        bbfatal "vuplus-transtreamproxy: hds-transcodare.conf porneste si altceva decat poarta"
    grep -q '/usr/sbin/hds-transcodare-poarta' ${D}${sysconfdir}/hds-transcodare.conf || \
        bbfatal "vuplus-transtreamproxy: hds-transcodare.conf nu trece prin hds-transcodare-poarta"
    [ ! -e ${D}${sysconfdir}/inetd.conf ] || bbfatal "vuplus-transtreamproxy: /etc/inetd.conf in pachet"
}

FILES:${PN} += "${sysconfdir}/init.d/hds-transcodare ${sysconfdir}/hds-transcodare.conf ${sbindir}/hds-transcodare-poarta"
CONFFILES:${PN} += "${sysconfdir}/hds-transcodare.conf"

# Scripturile OE-Alliance scriu in /etc/inetd.conf si repornesc inetd.busybox: inlocuite (portul e al serviciului nostru;
# update-rc.d adauga singur, la coada, pornirea si oprirea lui hds-transcodare, deci aici fara exit: numai ":").
pkg_preinst:${PN}() {
#!/bin/sh
:
}

pkg_postinst:${PN}() {
#!/bin/sh
:
}

pkg_prerm:${PN}() {
#!/bin/sh
:
}
