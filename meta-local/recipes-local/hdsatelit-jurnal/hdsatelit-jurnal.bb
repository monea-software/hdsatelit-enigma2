SUMMARY = "HDSatelit: jurnalul sistemului pastrat dupa o oprire necurata, placa Wi-Fi mai tacuta in jurnal"
DESCRIPTION = "Imaginea 0.5.0 (lotul imagine-050). Scriptul de pornire hds-jurnal (rcS S38, rc0 si \
rc6 S39) copiaza la pornire jurnalul de dinainte (messages.0 si messages) in /home/root/logs/messages.cadere numai cand \
ultima oprire n-a fost curata (pana de curent, repornire dura, cadere a nucleului) si scrie semnul opririi curate la \
oprire. Randul din /etc/modprobe.d coboara jurnalul driverului Wi-Fi rtl8188fu la erori (log_level 2) imediat dupa \
incarcarea lui. Rotirea mai mare a jurnalului (1024 KB x 4) e in busybox_%.bbappend. Monea Software pentru HD Satelit."
LICENSE = "GPL-2.0-only"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/GPL-2.0-only;md5=801f80980d171dd6425610833a22dbe6"
PV = "0.1.0"
# r1: hds-jurnal porneste urmarirea pornirii pe pornirile in dubiu (tools/hds-rezerva.sh din enigma2)
PR = "r1"

SRC_URI = "file://hds-jurnal file://hds-wifi-jurnal file://hds-rtl8188fu.conf"
S = "${UNPACKDIR}"

inherit allarch update-rc.d

do_configure[noexec] = "1"
do_compile[noexec] = "1"

INITSCRIPT_NAME = "hds-jurnal"
# rcS S38: dupa S03mountall si S05checkroot (radacina in scriere), inainte de syslogd (rc5 S20syslog), deci inainte ca
# jurnalul sa se schimbe. rc0/rc6 S39: rc cheama scripturile S din 0 si 6 cu "stop"; dupa K20syslog (syslogd oprit) si
# S20sendsigs, inainte de S40umountfs.
INITSCRIPT_PARAMS = "start 38 S . start 39 0 6 ."

do_install() {
    install -d ${D}${sysconfdir}/init.d ${D}${sbindir} ${D}${sysconfdir}/modprobe.d
    install -m 0755 ${S}/hds-jurnal ${D}${sysconfdir}/init.d/hds-jurnal
    install -m 0755 ${S}/hds-wifi-jurnal ${D}${sbindir}/hds-wifi-jurnal
    install -m 0644 ${S}/hds-rtl8188fu.conf ${D}${sysconfdir}/modprobe.d/hds-rtl8188fu.conf
    # paze: fara CRLF, sintaxa sh buna, randul install exact (un rand gresit in modprobe.d ar opri placa Wi-Fi)
    for f in ${D}${sysconfdir}/init.d/hds-jurnal ${D}${sbindir}/hds-wifi-jurnal ${D}${sysconfdir}/modprobe.d/hds-rtl8188fu.conf; do
        if grep -q "$(printf '\r')" "$f"; then
            bbfatal "hdsatelit-jurnal: $(basename $f) are sfarsit de rand CRLF"
        fi
    done
    sh -n ${D}${sysconfdir}/init.d/hds-jurnal || bbfatal "hdsatelit-jurnal: hds-jurnal nu e sh valid"
    sh -n ${D}${sbindir}/hds-wifi-jurnal || bbfatal "hdsatelit-jurnal: hds-wifi-jurnal nu e sh valid"
    [ "$(grep -v '^#' ${D}${sysconfdir}/modprobe.d/hds-rtl8188fu.conf | grep -c .)" = 1 ] || \
        bbfatal "hdsatelit-jurnal: hds-rtl8188fu.conf are alte randuri decat randul install"
    grep -qx 'install rtl8188fu /sbin/modprobe --ignore-install rtl8188fu $CMDLINE_OPTS && /usr/sbin/hds-wifi-jurnal' \
        ${D}${sysconfdir}/modprobe.d/hds-rtl8188fu.conf || bbfatal "hdsatelit-jurnal: randul install schimbat"
    grep -q '^F=/proc/net/rtl8188fu/log_level$' ${D}${sbindir}/hds-wifi-jurnal || \
        bbfatal "hdsatelit-jurnal: hds-wifi-jurnal nu scrie in /proc/net/rtl8188fu/log_level"
    grep -q '^SEMN=$D/.oprire-curata$' ${D}${sysconfdir}/init.d/hds-jurnal || \
        bbfatal "hdsatelit-jurnal: hds-jurnal fara semnul opririi curate"
}

FILES:${PN} = "${sysconfdir}/init.d/hds-jurnal ${sbindir}/hds-wifi-jurnal ${sysconfdir}/modprobe.d/hds-rtl8188fu.conf"
# /sbin/modprobe din kmod (--ignore-install si $CMDLINE_OPTS); kmod e oricum in imagine (0.4.0: kmod 34.2)
RDEPENDS:${PN} = "kmod"
