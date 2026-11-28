# PCS1 (25.11.2026): pcsc_scan pentru cititoarele de carduri USB, in feedul extern (feed-070), pe toate arhitecturile.
# Reteta OE-Alliance (meta-oe-alliance pcsc-tools_git.bb) are SRCREV = AUTOREV: fixam eticheta 1.7.5 (aceeasi comitere
# ca reteta pcsc-tools_1.7.5 din meta-openembedded), ca pachetul sa iasa la fel la fiecare constructie.
# Scripturile perl (ATR_analysis, scriptor, gscriptor) cer perl si Chipcard::PCSC (libpcsc-perl), care nu sunt in feedurile
# noastre si n-au reteta in straturi; le scoatem, deci pachetul cere numai pcsc-lite (ca reteta OE-Alliance).
# pcsc_scan chema ATR_analysis la fiecare card introdus: --disable-ATRparser il compileaza fara el (ca pcsc_scan -n),
# altfel omul ar vedea "ATR_analysis: not found" la fiecare card. Lipseste numai descrierea cardului dupa ATR.
SRCREV = "fbd5649502ebcc2d4d0ad1a88c5ae2cde7ecc39f"
PR = "r0.hds3"
EXTRA_OECONF += "--disable-ATRparser"

do_install:append() {
	for f in ATR_analysis scriptor gscriptor; do
		rm -f ${D}${bindir}/$f ${D}${mandir}/man1/$f.1 ${D}${mandir}/man1/$f.1p
	done
	rm -f ${D}${datadir}/pcsc/gscriptor.png ${D}${datadir}/pcsc/smartcard_list.txt ${D}${datadir}/applications/gscriptor.desktop
	rmdir --ignore-fail-on-non-empty ${D}${datadir}/pcsc ${D}${datadir}/applications 2>/dev/null || true
}
