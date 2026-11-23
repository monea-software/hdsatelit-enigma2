# H8 SE foloseste playerul HDS/GStreamer, nu FFmpeg-ul privat al SDK-ului.
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
inherit python3native
SRC_URI:append:h8se = " file://filtreaza-biblioteci-h8.py"
PR:append:h8se = ".hds1"
RDEPENDS:${PN}:remove:h8se = "libbluray openssl10"

do_install:append:h8se() {
    ${PYTHON} ${UNPACKDIR}/filtreaza-biblioteci-h8.py ${D}${libdir}/hisilicon
}
