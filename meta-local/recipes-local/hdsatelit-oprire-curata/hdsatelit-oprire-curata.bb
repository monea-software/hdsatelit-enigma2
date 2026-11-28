# hdsatelit-oprire-curata (0.8.0, RBT0): /sbin/reboot, /sbin/halt si /sbin/poweroff care, cu enigma2 pornit, ii cer intai
# lui enigma2 sa se opreasca curat (SIGUSR2, Screens/Standby.py), iar repornirea sau oprirea o face apoi tools/enigma2.sh.
# De ce: pe Vu+ Duo 4K Lite un plugin chema reboot direct cat enigma2 mergea; driverul Vu+ elibera CEC-ul si video-ul de
# sub enigma2 (Oops in nexus) si receptorul ramanea blocat (STADIU-CEC9, STADIU-RBT0). Fara enigma2 (enigma2.sh dupa
# iesire, rc0/rc6, paznicul inaintea interfetei) scriptul trece direct la binarul adevarat din sysvinit
# (/usr/lib/hdsatelit-oprire/<nume> -> /sbin/halt.sysvinit, cu numele exact: halt se poarta dupa argv[0]). update-alternatives, prioritatea peste sysvinit (200) si busybox (50).
SUMMARY = "reboot, halt si poweroff care opresc intai enigma2 curat (HD Satelit)"
LICENSE = "GPL-2.0-only"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/GPL-2.0-only;md5=801f80980d171dd6425610833a22dbe6"
PV = "1.0"
PR = "r0"

SRC_URI = "file://hds-oprire-curata"
S = "${UNPACKDIR}"

inherit allarch update-alternatives

do_configure[noexec] = "1"
do_compile[noexec] = "1"

do_install() {
    install -d ${D}${base_sbindir}
    install -m 0755 ${S}/hds-oprire-curata ${D}${base_sbindir}/hds-oprire-curata
    # paza: sfarsit de rand LF si sintaxa sh buna, altfel reboot nu ar mai merge deloc
    if grep -q "$(printf '\r')" ${D}${base_sbindir}/hds-oprire-curata; then
        bbfatal "hds-oprire-curata: sfarsit de rand CRLF"
    fi
    sh -n ${D}${base_sbindir}/hds-oprire-curata || bbfatal "hds-oprire-curata: eroare de sintaxa sh"
    # binarul adevarat cu numele exact (halt din sysvinit se poarta dupa argv[0]): reboot, halt, poweroff -> halt.sysvinit
    install -d ${D}${libdir}/hdsatelit-oprire
    for n in reboot halt poweroff; do
        ln -sf ${base_sbindir}/halt.sysvinit ${D}${libdir}/hdsatelit-oprire/$n
    done
}

ALTERNATIVE:${PN} = "reboot halt poweroff"
ALTERNATIVE_LINK_NAME[reboot] = "${base_sbindir}/reboot"
ALTERNATIVE_LINK_NAME[halt] = "${base_sbindir}/halt"
ALTERNATIVE_LINK_NAME[poweroff] = "${base_sbindir}/poweroff"
ALTERNATIVE_TARGET = "${base_sbindir}/hds-oprire-curata"
ALTERNATIVE_PRIORITY = "300"

RDEPENDS:${PN} = "sysvinit"
FILES:${PN} = "${base_sbindir}/hds-oprire-curata ${libdir}/hdsatelit-oprire"
