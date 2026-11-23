# Numai H8: script propriu de oprire, pastrand modulele si programul OEM.
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI:append:h8 = " file://hds-h8-suspend"
PR:append:h8 = ".hds1"

do_install:append:h8() {
    install -m 0755 ${UNPACKDIR}/hds-h8-suspend ${D}${sysconfdir}/init.d/suspend
}
