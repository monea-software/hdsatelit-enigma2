# H8 PLUS pastreaza bibliotecile native si codecurile independente ale placii.
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
inherit python3native
SRC_URI:append:h8 = " file://filtreaza-biblioteci-h8.py"
PR:append:h8 = ".hds1"
RDEPENDS:${PN}:remove:h8 = "libbluray openssl10"

do_install:append:h8() {
    ${PYTHON} ${UNPACKDIR}/filtreaza-biblioteci-h8.py ${D}${libdir}/hisilicon
}
