SUMMARY = "HDSatelit: ruta blackhole spre serverul de autorizare Dinobot (showiframe)"
DESCRIPTION = "Adauga la pornire o ruta blackhole spre 117.78.33.205, ca showiframe (daemonul \
inchis Dinobot) sa nu poata trimite MAC-ul si id-ul cipului la serverul strain de autorizare. \
Adresa e IP fix in binar (nu trece prin DNS), deci blocarea prin ruta (iproute2, deja in imagine) \
e suficienta; filtrul iptables nu exista in nucleul Dinobot (CONFIG_IP_NF_FILTER nesetat). Nu \
afecteaza redarea pe un receptor deja provizionat (calea de retea din showiframe nu se atinge: \
autorizarea trece local, din OTP). Monea Software pentru HD Satelit. Detalii cu dovezi: \
securitate-showiframe/CONCLUZIE-SI-MASURI.md si REPARARE.md."
LICENSE = "CLOSED"
# 0.1.1 (24.09.2026, verificarea adversariala din REPARARE.md, defectul D1): ruta ramane pusa la
# actualizarea pachetului si se pune imediat la instalarea lui pe un receptor pornit
PV = "0.1.1"

SRC_URI = "file://hds-netguard"
S = "${UNPACKDIR}"

inherit allarch update-rc.d

do_configure[noexec] = "1"
do_compile[noexec] = "1"

# iproute2-ip aduce /sbin/ip.iproute2 (stie "blackhole"), deja in imagine prin packagegroup
RDEPENDS:${PN} = "iproute2-ip"

INITSCRIPT_NAME = "hds-netguard"
# S41 in rcS (sysinit): init termina rcS inainte de runlevel 3, deci ruta exista inainte de
# S10networking (rc3.d) si inainte ca gui:3:respawn:/usr/bin/enigma2.sh sa porneasca showiframe
INITSCRIPT_PARAMS = "start 41 S ."

# D1. Clasa update-rc.d pune in prerm "hds-netguard stop" fara sa se uite la $1, iar opkg 0.8.0
# cheama prerm si la ACTUALIZARE ("prerm upgrade <versiune>", libopkg/opkg_install.c r. 232-253):
# ruta ar fi scoasa. Iar postinst-ul clasei ("update-rc.d -s hds-netguard start 41 S .") NU porneste
# scriptul cand receptorul e in runlevel 3 (update-rc.d porneste numai daca nivelul == runlevel-ul
# curent), deci ruta ar lipsi pana la repornire. Aici: prerm opreste numai la dezinstalare, iar
# postinst pune ruta imediat pe un receptor pornit (la facerea imaginii $D e setat si nu face nimic).
updatercd_prerm() {
if ${@use_updatercd(d)} && [ -z "$D" -a -x "${INIT_D_DIR}/${INITSCRIPT_NAME}" ] && [ "$1" != "upgrade" ]; then
	${INIT_D_DIR}/${INITSCRIPT_NAME} stop || :
fi
}

pkg_postinst:${PN}() {
#!/bin/sh
if [ -z "$D" ] && [ -x /etc/init.d/hds-netguard ]; then
	/etc/init.d/hds-netguard start || :
fi
}

do_install() {
    install -d ${D}${sysconfdir}/init.d
    install -m 0755 ${S}/hds-netguard ${D}${sysconfdir}/init.d/hds-netguard
    # paza: scriptul instalat trebuie sa contina adresa si comanda; altfel constructia se opreste
    grep -q '^GUARD_IPS=.*117\.78\.33\.205' ${D}${sysconfdir}/init.d/hds-netguard || \
        bbfatal "hds-netguard: lipseste 117.78.33.205 din GUARD_IPS"
    grep -q 'route replace blackhole' ${D}${sysconfdir}/init.d/hds-netguard || \
        bbfatal "hds-netguard: lipseste 'route replace blackhole'"
    if grep -q "$(printf '\r')" ${D}${sysconfdir}/init.d/hds-netguard; then
        bbfatal "hds-netguard: scriptul are sfarsit de rand CRLF, nu ar porni pe receptor"
    fi
}

FILES:${PN} = "${sysconfdir}/init.d/hds-netguard"
