SUMMARY = "HDSatelit: IPv6 oprit din fabrica, pornit numai cu semnul /etc/hds-ipv6-pornit"
DESCRIPTION = "Imaginea 0.5.0. Scriptul de pornire hds-ipv6 (rcS S40, inainte de retea si de enigma2) pune \
net.ipv6.conf.all.disable_ipv6 si net.ipv6.conf.default.disable_ipv6 pe 1 cand lipseste fisierul-semn \
/etc/hds-ipv6-pornit (din fabrica lipseste) si pe 0 cand exista. Semnul il pune si il scoate setarea IPv6 din enigma2. \
Clientul DHCPv6 are aceeasi poarta in reteta odhcp6c din acest strat. IPv4 nu se atinge. Monea Software pentru HD Satelit."
LICENSE = "GPL-2.0-only"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/GPL-2.0-only;md5=801f80980d171dd6425610833a22dbe6"
PV = "0.1.0"

SRC_URI = "file://hds-ipv6"
S = "${UNPACKDIR}"

inherit allarch update-rc.d

do_configure[noexec] = "1"
do_compile[noexec] = "1"

INITSCRIPT_NAME = "hds-ipv6"
# rcS S40: dupa S39hostname, inainte de S41hds-netguard; tot rcS se termina inainte de nivelul 3, deci inainte de
# S10networking (rc3) si de enigma2 (gui:3:respawn din inittab). Fara legaturi K: o oprire nu are ce face aici.
INITSCRIPT_PARAMS = "start 40 S ."

do_install() {
    install -d ${D}${sysconfdir}/init.d
    install -m 0755 ${S}/hds-ipv6 ${D}${sysconfdir}/init.d/hds-ipv6
    # paze: fara CRLF, sintaxa sh buna, semnul si cele doua chei exact (altfel IPv6 ar ramane pornit din fabrica)
    if grep -q "$(printf '\r')" ${D}${sysconfdir}/init.d/hds-ipv6; then
        bbfatal "hdsatelit-ipv6: hds-ipv6 are sfarsit de rand CRLF"
    fi
    sh -n ${D}${sysconfdir}/init.d/hds-ipv6 || bbfatal "hdsatelit-ipv6: hds-ipv6 nu e sh valid"
    grep -q '^SEMN=..HDS_IPV6_SEMN:-/etc/hds-ipv6-pornit}$' ${D}${sysconfdir}/init.d/hds-ipv6 || \
        bbfatal "hdsatelit-ipv6: hds-ipv6 nu foloseste semnul /etc/hds-ipv6-pornit"
    grep -q '^P=..HDS_IPV6_PROC:-/proc/sys/net/ipv6/conf}$' ${D}${sysconfdir}/init.d/hds-ipv6 || \
        bbfatal "hdsatelit-ipv6: hds-ipv6 nu scrie in /proc/sys/net/ipv6/conf"
    grep -q 'for c in all default; do' ${D}${sysconfdir}/init.d/hds-ipv6 || \
        bbfatal "hdsatelit-ipv6: hds-ipv6 nu atinge all si default"
    # semnul nu vine niciodata din imagine
    [ ! -e ${D}${sysconfdir}/hds-ipv6-pornit ] || bbfatal "hdsatelit-ipv6: semnul /etc/hds-ipv6-pornit in pachet"
}

FILES:${PN} = "${sysconfdir}/init.d/hds-ipv6"
