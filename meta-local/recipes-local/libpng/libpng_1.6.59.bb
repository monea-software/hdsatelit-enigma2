# Reteta copiata din openembedded-core, meta/recipes-multimedia/libpng/libpng_1.6.50.bb (ramane sub licenta MIT a
# stratului openembedded-core), adusa la libpng 1.6.59.
# Repara gaurile din 1.6.50: CVE-2026-25646, CVE-2026-22801, CVE-2026-33636, CVE-2026-33416, CVE-2025-64720 si
# CVE-2025-66293 (reparate pana la 1.6.57) si CVE-2026-46675 (use-after-free in png_read_end, in 1.6.59); 1.6.58
# repara o regresie din 1.6.56 la png_get_PLTE.
# Arhiva libpng16/1.6.59/libpng-1.6.59.tar.xz de pe SourceForge, 1074540 octeti; autorii nu publica sha256 sau
# semnatura langa arhiva; sha1 si md5 afisate de SourceForge in dosarul versiunii se potrivesc cu arhiva; sha256 de mai
# jos calculat pe ea.
# Schimbari fata de original: versiunea, suma si md5-ul lui LICENSE (in LICENSE s-au schimbat numai anii de
# copyright, 2025 in 2026; licenta e aceeasi); run-ptest se ia din dosarul retetei din openembedded-core, prin
# FILESEXTRAPATHS:append.
# bbappend-ul meta-oe-alliance libpng_1.6.%.bbappend se aplica singur si pe 1.6.59 (disable-srgb-profile-checks.patch).

FILESEXTRAPATHS:append := "${COREBASE}/meta/recipes-multimedia/libpng/files:"

SUMMARY = "PNG image format decoding library"
DESCRIPTION = "An open source project to develop and maintain the reference \
library for use in applications that read, create, and manipulate PNG \
(Portable Network Graphics) raster image files. "
HOMEPAGE = "http://www.libpng.org/"
SECTION = "libs"
LICENSE = "Libpng"
LIC_FILES_CHKSUM = "file://LICENSE;md5=9dc350edbbbee660c7d9af79487168f2"
DEPENDS = "zlib"

LIBV = "16"

SRC_URI = "${SOURCEFORGE_MIRROR}/${BPN}/${BPN}${LIBV}/${BP}.tar.xz \
           file://run-ptest \
"

SRC_URI[sha256sum] = "d80dd2a38a37f803cb9b6ac7b14bd6e74ddc3b654780a8380bdf93523fdb4389"

MIRRORS += "${SOURCEFORGE_MIRROR}/project/${BPN}/${BPN}${LIBV}/ ${SOURCEFORGE_MIRROR}/project/${BPN}/${BPN}${LIBV}/older-releases/"

UPSTREAM_CHECK_URI = "http://libpng.org/pub/png/libpng.html"

BINCONFIG = "${bindir}/libpng-config ${bindir}/libpng16-config"

inherit autotools binconfig-disabled pkgconfig ptest

# Work around missing symbols
ARMNEON = "${@bb.utils.contains("TUNE_FEATURES", "neon", "--enable-arm-neon=on", "--enable-arm-neon=off", d)}"
ARMNEON:aarch64 = "--enable-hardware-optimizations=on"
EXTRA_OECONF += "${ARMNEON}"

PACKAGES =+ "${PN}-tools"

FILES:${PN}-tools = "${bindir}/png-fix-itxt ${bindir}/pngfix ${bindir}/pngcp"

RDEPENDS:${PN}-ptest += "make bash gawk"

do_install_ptest() {
    # Install test scripts to ptest path
    install -d ${D}${PTEST_PATH}/src/tests
    install -m 755 ${S}/tests/* ${D}${PTEST_PATH}/src/tests
    install -m 755 ${S}/test-driver ${D}${PTEST_PATH}
    install -d ${D}${PTEST_PATH}/src/tests/scripts
    install -m 755 ${S}/scripts/*.awk ${D}${PTEST_PATH}/src/tests/scripts
    install -m 644 ${S}/scripts/pnglib* ${S}/scripts/*.c ${S}/scripts/*.def ${S}/scripts/macro.lst ${D}${PTEST_PATH}/src/tests/scripts
    install -m 644 ${S}/scripts/pnglibconf.h.prebuilt ${D}${PTEST_PATH}/src/tests/scripts/pnglibconf.h
    install -d ${D}${PTEST_PATH}/src/contrib/tools
    install -m 755 ${S}/contrib/tools/*.sh ${D}${PTEST_PATH}/src/contrib/tools
    install -m 644 ${S}/contrib/tools/*.c ${S}/contrib/tools/*.h ${D}${PTEST_PATH}/src/contrib/tools

    # Install .libs directory binaries to ptest path
    install -m 755 ${B}/.libs/pngtest ${B}/.libs/pngstest ${B}/.libs/pngimage ${B}/.libs/pngunknown ${B}/.libs/pngvalid ${D}${PTEST_PATH}/src

    # Copy png files to ptest path
    cd ${S} && find contrib -name '*.png' | cpio -pd ${D}${PTEST_PATH}/src

    # Install Makefile and png files
    install -m 644 ${S}/pngtest.png ${D}${PTEST_PATH}/src
    install -m 644 ${S}/*.png ${S}/*.h ${S}/*.c ${S}/*.dfa ${B}/pnglibconf.out ${S}/Makefile.am ${S}/Makefile.in ${D}${PTEST_PATH}/src/tests

    sed -e 's/^abs_srcdir = ..*/abs_srcdir = \.\./'          \
        -e 's/^top_srcdir = ..*/top_srcdir = \.\./'          \
        -e 's/^srcdir = ..*/srcdir = \./'                    \
        -e 's/^Makefile: ..*/Makefile: /'                    \
        -e 's/check-TESTS: $(check_PROGRAMS)/check-TESTS:/g' \
        ${B}/Makefile > ${D}${PTEST_PATH}/src/Makefile

    sed -e 's|#!/bin/awk|#!/usr/bin/awk|g' -i ${D}${PTEST_PATH}/src/tests/scripts/*.awk
}

# Numai pentru receptor: varianta native (unealta de constructie) ramane cea din straturile comune; altfel
# python3-native si aproape toate uneltele native s-ar construi din nou, fara niciun folos pentru receptor.
