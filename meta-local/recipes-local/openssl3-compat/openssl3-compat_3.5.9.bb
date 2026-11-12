# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: MIT
#
# openssl3-compat (IN IMAGINE din 0.7.4; Eduard, 11.11.2026 18:56: „il pui in imagine”, ca omul sa nu faca nimic): numai
# bibliotecile OpenSSL 3 (libssl.so.3, libcrypto.so.3) pentru modulele si pluginurile altora construite pe OpenSSL 3, pe
# imaginea 0.7.x (OE-Alliance 6.0), care are OpenSSL 4 (libssl4/libcrypto4, libssl.so.4). Il cere hdsatelit-base
# (packagegroups/hdsatelit-base.bbappend), deci vine si prin actualizarea din meniu 0.7.3 -> 0.7.4.
# De ce: pachetul altora enigma2-plugin-softcams-oscam-emu-pcsc-levi45 (OSCam 11968) are un preinst care cauta in
# /var/lib/opkg/status „Package: libssl3” si „Package: libcrypto3” (sau /usr/lib/libssl.so.3, libcrypto.so.3), altfel
# le cere din feed si iese cu „The libsslx.x.x file could not be loaded from the repository” (forumul nostru 768 #1564,
# A04 din lucru-sesiune/paralel-1111b; proba pe .122: STADIU-P3-LIBSSL3.md). Binarele lui ssl310 cer libssl.so.3.
#
# Aceeasi reteta (de la SUMMARY in jos, identica) sta si in meta-pluginuri-externe/recipes-compat/openssl3-compat (depozitul
# hdsatelit-unelte, main), pentru feedul extern al receptoarelor ramase pe 0.7.3; acelasi nume, aceeasi versiune 3.5.9-r0.
# NUMAI pentru stratul 6.0 (pregateste-strat-60.sh): pe 5.6 recipes-local/openssl/openssl_3.6.5.bb face deja libssl3 si
# libcrypto3 (doua retete cu aceleasi pachete); pe 6.0 aceea e scoasa (oe-core 6.0 are OpenSSL 4), iar numele
# openssl3-compat nu exista in 6.0, deci pasul 2 al lui pregateste-strat-60.sh o lasa in strat.
#
# Ce NU face (ca sa nu atinga OpenSSL 4 al imaginii): fara programe (openssl), fara openssl.cnf, fara antete si
# fara legaturile de dezvoltare libssl.so/libcrypto.so, fara module (ossl-modules), fara dosarul /usr/lib/ssl-3
# (OpenSSL 4 din oe-core 6.0 il foloseste ca OPENSSLDIR). Dosarul lui OpenSSL 3 e /usr/lib/ssl-3-compat; modulele
# si motoarele s-ar cauta tot acolo (nu sunt in pachet), deci libcrypto.so.3 nu incarca niciodata modulele lui 4.x.
# Fara sysroot (SYSROOT_DIRS gol): nicio reteta a imaginii nu poate lega la OpenSSL 3 in locul lui 4.
#
# Pachetele: libssl3, libcrypto3 (numele cautate de preinst-ul de mai sus) si openssl3-compat (gol, le trage pe
# amandoua; pe el il cere hdsatelit-base). Instalat: ~4,3 MB pe ARM (libcrypto.so.3 3,48 MB, libssl.so.3 0,79 MB).
# Versiunea: 3.5 e ramura LTS (suport pana in 2030); libssl.so.3 are simbolurile OPENSSL_3.0.0 .. OPENSSL_3.5.0.
SUMMARY = "OpenSSL 3 shared libraries only (libssl.so.3, libcrypto.so.3), for third-party binaries"
HOMEPAGE = "https://www.openssl.org/"
# fara numele nostru in control (paza din oscam_actualizare.py), ca la retetele OSCam
MAINTAINER = "OpenSSL Project <https://www.openssl.org/>"
SECTION = "libs/network"
LICENSE = "Apache-2.0"
LIC_FILES_CHKSUM = "file://LICENSE.txt;md5=c75985e733726beaba57bc5253e96d04"

SRC_URI = "https://github.com/openssl/openssl/releases/download/openssl-${PV}/openssl-${PV}.tar.gz"
SRC_URI[sha256sum] = "603f5602e2eef00d77fbd429d34dcd5822bb301757a1bc9cdb24c670f1eb859a"
S = "${UNPACKDIR}/openssl-${PV}"
B = "${WORKDIR}/build"
do_configure[cleandirs] = "${B}"

inherit perlnative

COMPAT_SSLDIR = "${nonarch_libdir}/ssl-3-compat"
# Configure-ul OpenSSL nu stie --disable-static (oe-core: DISABLE_STATIC:pn-openssl = "")
DISABLE_STATIC = ""
EXTRA_OECONF = "no-tests no-docs"
EXTRA_OEMAKE:append:task-compile = ' OPENSSLDIR="${COMPAT_SSLDIR}" ENGINESDIR="${COMPAT_SSLDIR}/engines-3" MODULESDIR="${COMPAT_SSLDIR}/ossl-modules"'

do_configure () {
	os=${HOST_OS}
	case $os in
	linux-gnueabi | linux-gnuspe | linux-musleabi | linux-muslspe | linux-musl) os=linux ;;
	esac
	target="$os-${HOST_ARCH}"
	case $target in
	linux-arm*) target=linux-armv4 ;;
	linux-aarch64*) target=linux-aarch64 ;;
	linux-mips | linux-mipsel) target="linux-mips32 ${TARGET_CC_ARCH}" ;;
	*) bbfatal "openssl3-compat: tinta neprevazuta $target (numai arm, aarch64, mips)" ;;
	esac
	PERLEXTERNAL="$(realpath ${S}/external/perl/Text-Template-*/lib)"
	test -d "$PERLEXTERNAL" || bbfatal "PERLEXTERNAL '$PERLEXTERNAL' not found!"
	HASHBANGPERL="/usr/bin/env perl" PERL=perl PERL5LIB="$PERLEXTERNAL" \
	perl ${S}/Configure ${EXTRA_OECONF} --prefix=${prefix} --openssldir=${COMPAT_SSLDIR} --libdir=${baselib} $target
}

do_compile () {
	oe_runmake build_libs
}

do_install () {
	# numai libssl.so.3 si libcrypto.so.3 (install_runtime_libs nu pune antete, .pc, .a sau legaturile .so)
	oe_runmake DESTDIR="${D}" install_runtime_libs
	rm -rf ${D}${bindir}
	# certificatele imaginii (ca-certificates), pentru SSL_CTX_set_default_verify_paths; o legatura numai a noastra
	install -d ${D}${COMPAT_SSLDIR}
	ln -sf ${@oe.path.relative('${nonarch_libdir}/ssl-3-compat', '${sysconfdir}/ssl/certs')} ${D}${COMPAT_SSLDIR}/certs
	for f in $(find ${D} -type f -o -type l); do
		case "$f" in
		${D}${libdir}/libssl.so.3 | ${D}${libdir}/libcrypto.so.3 | ${D}${COMPAT_SSLDIR}/certs) ;;
		*) bbfatal "openssl3-compat: fisier neasteptat in pachet: ${f#${D}}" ;;
		esac
	done
}

# fara sysroot: nicio reteta nu trebuie sa lege la OpenSSL 3 din greseala in locul lui 4
SYSROOT_DIRS = ""
SYSROOT_DIRS_IGNORE += "${libdir}"

PACKAGES = "${PN}-dbg libssl3 libcrypto3 ${PN}"
FILES:libssl3 = "${libdir}/libssl.so.3"
FILES:libcrypto3 = "${libdir}/libcrypto.so.3 ${COMPAT_SSLDIR}"
FILES:${PN} = ""
ALLOW_EMPTY:${PN} = "1"
RDEPENDS:${PN} = "libssl3 libcrypto3"
RDEPENDS:libssl3 = "libcrypto3"
# numele sunt alese de noi; fara redenumirea automata dupa soname
DEBIAN_NOAUTONAME:libssl3 = "1"
DEBIAN_NOAUTONAME:libcrypto3 = "1"

# Legaturile straine chiar pe numele bibliotecilor noastre (preinst-ul OSCam-ului lui Levi45 face libssl.so.1.1 -> libssl.so.3
# in /usr/lib si /lib cand gaseste libssl3; unele sfaturi de pe forumuri fac libssl.so.3 -> libssl.so.4): opkg 0.10 refuza sa
# instaleze peste un fisier fara pachet („<no package> Please move this file out of the way”, check_data_file_clashes, care
# ruleaza DUPA preinst), iar ld.so, fara ld.so.cache, cauta in /lib inaintea lui /usr/lib. Se sterg numai legaturile (niciodata un
# fisier adevarat), in /usr/lib si /lib; la constructia imaginii ($D) nu e nimic de sters.
pkg_preinst:libssl3 () {
	for f in $D${libdir}/libssl.so.3 $D${base_libdir}/libssl.so.3; do
		if [ -L "$f" ]; then rm -f "$f"; fi
	done
}
pkg_preinst:libcrypto3 () {
	for f in $D${libdir}/libcrypto.so.3 $D${base_libdir}/libcrypto.so.3; do
		if [ -L "$f" ]; then rm -f "$f"; fi
	done
}
