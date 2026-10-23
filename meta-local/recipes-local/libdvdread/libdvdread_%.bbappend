# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# libdvdread pentru redarea DVD-urilor copiate necriptate (dosar VIDEO_TS sau fisier .iso). Fara biblioteca de
# decriptare CSS: reteta OE nu o leaga, dar codul original o incarca la rulare (dlopen) daca o gaseste pe sistem.
# Peticul 0001-dvd-input-fara-decriptare.patch scoate incarcarea si functiile care o folosesc; ramane numai citirea
# directa a sectoarelor. Constructia se opreste daca biblioteca ar fi legata la compilare, daca libdvdread.so (curatat
# de simboluri, ca in pachet) mai pomeneste biblioteca de decriptare sau daca mai cere dlopen.

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI += "file://0001-dvd-input-fara-decriptare.patch"

PR:append = ".hds1"

EXTRA_OECONF += "--without-libdvdcss"

do_configure:append() {
	if grep -q '^#define HAVE_DVDCSS_DVDCSS_H' ${B}/config.h; then
		bbfatal "libdvdread: legata de biblioteca de decriptare (HAVE_DVDCSS_DVDCSS_H)"
	fi
}

do_install:append() {
	n=0
	for b in ${D}${libdir}/libdvdread.so.*; do
		[ -L "$b" ] && continue
		n=$(expr $n + 1)
		# fara simboluri, ca in pachet: informatiile de depanare pastreaza numele tipurilor din cod
		${STRIP} --strip-all -o ${T}/hds-verificare.so "$b"
		if grep -aqi "dvdcss" ${T}/hds-verificare.so; then
			bbfatal "libdvdread: $(basename $b) pomeneste biblioteca de decriptare"
		fi
		if ${OBJDUMP} -T "$b" | grep -qw "dlopen"; then
			bbfatal "libdvdread: $(basename $b) cere inca dlopen"
		fi
	done
	[ $n -ge 1 ] || bbfatal "libdvdread: lipseste libdvdread.so"
}
