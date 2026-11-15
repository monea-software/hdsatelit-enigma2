# HD Satelit (V21B, 14.11.2026): pe Dreambox DM8000HD nu rescriem niciodata incarcatorul din receptorul pornit.
# dreambox-secondstage-base.inc (OE-Alliance) pune /tmp/secondstage-dm8000.bin in pachet, iar postinst-ul face
# flash_erase + nandwrite pe /dev/mtd1 la ORICE instalare sau actualizare: contra REGULI-FLASH-RECEPTOR. Ramane numai
# do_deploy (secondstage-dm8000.bin in DEPLOY_DIR_IMAGE), folosit de .nfi-ul pornirii mici, pe care il scrie omul din
# modul de salvare Dreambox (acolo incarcatorul se scrie oricum, ca la orice .nfi).
pkg_postinst:${PN}() {
:
}
do_install:append() {
	rm -f ${D}/tmp/secondstage-*.bin
	rmdir ${D}/tmp 2>/dev/null || true
}
FILES:${PN} = ""
ALLOW_EMPTY:${PN} = "1"
RDEPENDS:${PN} = ""
