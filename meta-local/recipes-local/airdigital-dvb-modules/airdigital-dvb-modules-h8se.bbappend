# Numai H8 SE: script propriu de oprire, pastrand modulele si programul OEM.
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI:append:h8se = " file://hds-h8-suspend"
PR:append:h8se = ".hds1"

do_install:append:h8se() {
    install -m 0755 ${UNPACKDIR}/hds-h8-suspend ${D}${sysconfdir}/init.d/suspend
}
