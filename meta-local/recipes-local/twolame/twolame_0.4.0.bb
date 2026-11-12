# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: MIT
#
# twolame (0.7.4): biblioteca de codare MPEG-1/2 Layer II (MP2), LGPL-2.1-or-later, numai libtwolame.so.0 (~0,1 MB).
# De ce: releul DAB+ din satelit (enigma2, lib/python/Hds/DabT2/dab/motor/releu_dab.py) decodeaza AAC-ul DAB+ (cadre de
# 960 de esantioane, HE-AAC) cu faad2 pe placile care nu-l stiu (Broadcom: Vu+; forumul nostru 801 #1562, sunet sacadat
# pe Vu+ Uno 4K SE) si da placii MP2, felul de sunet pe care il reda orice decodor de receptor
# (lib/python/Hds/DabT2/sunet_software.py, prin ctypes: twolame_init, twolame_set_*, twolame_init_params,
# twolame_encode_buffer_interleaved, twolame_close). Nicio reteta twolame in straturile OE-Alliance 6.0 / meta-oe.
# Fara programul twolame (cere libsndfile) si fara documentatie: numai biblioteca, pachetul libtwolame0 (numele dat de
# debian.bbclass dupa soname).
SUMMARY = "TwoLAME MPEG Audio Layer 2 encoder library"
HOMEPAGE = "https://www.twolame.org/"
SECTION = "libs"
LICENSE = "LGPL-2.1-or-later"
LIC_FILES_CHKSUM = "file://COPYING;md5=ade9a053df81f5b9408d2f4f5546df86"

SRC_URI = "https://github.com/njh/twolame/releases/download/${PV}/twolame-${PV}.tar.gz"
SRC_URI[sha256sum] = "cc35424f6019a88c6f52570b63e1baf50f62963a3eac52a03a800bb070d7c87d"

inherit autotools pkgconfig

# fara libsndfile: programul twolame nu se face (configure il sare singur); fara modul de intretinere (asciidoc, doxygen)
EXTRA_OECONF = "--disable-sndfile --disable-maintainer-mode"

do_install:append() {
	rm -rf ${D}${datadir}/doc ${D}${mandir}
	rm -f ${D}${bindir}/twolame
	rmdir --ignore-fail-on-non-empty ${D}${bindir} ${D}${datadir} 2>/dev/null || true
}
