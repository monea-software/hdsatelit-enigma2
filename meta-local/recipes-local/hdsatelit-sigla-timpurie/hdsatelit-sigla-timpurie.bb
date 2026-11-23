SUMMARY = "Sigla HD Satelit inaintea interfetei pe H8"
LICENSE = "GPL-2.0-only"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/GPL-2.0-only;md5=801f80980d171dd6425610833a22dbe6"
SRC_URI = "file://hds-sigla-timpurie file://hds-sigla-paznic.py"
S = "${UNPACKDIR}"
COMPATIBLE_MACHINE = "^(h8|h8se)$"
RDEPENDS:${PN} = "busybox showiframe hdsatelit-bootlogo python3-core python3-ctypes python3-fcntl"

inherit update-rc.d
INITSCRIPT_NAME = "hds-sigla-timpurie"
INITSCRIPT_PARAMS = "start 06 S ."

do_configure[noexec] = "1"
do_compile[noexec] = "1"
do_install() {
    install -d ${D}${sysconfdir}/init.d
    install -m 0755 ${S}/hds-sigla-timpurie ${D}${sysconfdir}/init.d/hds-sigla-timpurie
    install -d ${D}${libexecdir}
    install -m 0755 ${S}/hds-sigla-paznic.py ${D}${libexecdir}/hds-sigla-paznic.py
}
