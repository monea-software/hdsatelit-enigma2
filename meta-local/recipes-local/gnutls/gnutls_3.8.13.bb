# Reteta copiata din openembedded-core (ramura master), meta/recipes-support/gnutls/gnutls_3.8.13.bb, impreuna cu
# fisierele din gnutls/ (raman sub licenta MIT a stratului openembedded-core); in imagine era gnutls 3.8.10.
# Repara cele 6 CVE nepatchuite ale lui 3.8.10, intre ele cele 2 critice: CVE-2026-42010 (identitatea RSA-PSK pe
# server) si CVE-2026-33845 (reasamblarea DTLS); plus CVE-2026-3833 (nameConstraints, atinge clientul TLS),
# CVE-2026-1584, CVE-2026-42009 si celelalte din NEWS 3.8.13.
# Arhiva https://www.gnupg.org/ftp/gcrypt/gnutls/v3.8/gnutls-3.8.13.tar.xz; semnatura .sig verificata cu gpg (semnaturi
# bune de la doi dintre autorii GnuTLS, cheile din gnutls-release-keyring.gpg: 5D46 CB0F 7634 05A7 0535 56F4 7A75 A648
# B3F9 220C si A6AB 53A0 1D23 7A94 F9EE C4D0 4127 48A4 0AFC C2FB); sha256 de mai jos egal cu cel din openembedded-core.
# Schimbari fata de original: acest antet, LICENSE cu & (OE-ul nostru nu stie inca AND), BBCLASSEXTEND gol (reteta
# numai pentru receptor; gnutls-native ramane cel din openembedded-core, din sstate) si grupul CVE_STATUS pentru
# reparatiile din NEWS 3.8.13. Biblioteca ramane libgnutls.so.30 (pachetul libgnutls30), deci poate veni si prin
# actualizare, impreuna cu libtasn1 4.21.0 (recipes-local/libtasn1), cu care se construieste.

SUMMARY = "GNU Transport Layer Security Library"
DESCRIPTION = "a secure communications library implementing the SSL, \
TLS and DTLS protocols and technologies around them."
HOMEPAGE = "https://gnutls.org/"
BUGTRACKER = "https://savannah.gnu.org/support/?group=gnutls"

LICENSE = "GPL-3.0-or-later & LGPL-2.1-or-later"
LICENSE:${PN} = "LGPL-2.1-or-later"
LICENSE:${PN}-xx = "LGPL-2.1-or-later"
LICENSE:${PN}-bin = "GPL-3.0-or-later"
LICENSE:${PN}-openssl = "GPL-3.0-or-later"

LIC_FILES_CHKSUM = "file://README.md;beginline=181;endline=205;md5=e159ff2a6e9cc95141fb0eaff733bba3 \
                    file://COPYING;md5=1ebbd3e34237af26da5dc08a4e440464 \
                    file://COPYING.LESSERv2;md5=4bf661c1e3793e55c8d1051bc5e0ae21"

DEPENDS = "nettle gmp virtual/libiconv libunistring"

SHRT_VER = "${@d.getVar('PV').split('.')[0]}.${@d.getVar('PV').split('.')[1]}"

SRC_URI = "https://www.gnupg.org/ftp/gcrypt/gnutls/v${SHRT_VER}/gnutls-${PV}.tar.xz \
           file://arm_eabi.patch \
           file://0001-Creating-.hmac-file-should-be-excuted-in-target-envi.patch \
           file://run-ptest \
           file://Add-ptest-support.patch \
           file://0001-tests-pkcs11-trust-list-fault-fix-issues-in-linking.patch \
           file://0001-tests-mini-dtls-framents-link-to-gnulib.patch \
           "

SRC_URI[sha256sum] = "ffed8ec1bf09c2426d4f14aae377de4753b53e537d685e604e99a8b16ca9c97e"

inherit autotools texinfo pkgconfig gettext lib_package gtk-doc ptest

PACKAGECONFIG ??= "libidn libtasn1 ${@bb.utils.filter('DISTRO_FEATURES', 'seccomp', d)}"
PACKAGECONFIG:append:class-native = " p11-kit"

# You must also have CONFIG_SECCOMP enabled in the kernel for
# seccomp to work.
PACKAGECONFIG[seccomp] = "--with-libseccomp-prefix=${STAGING_DIR_HOST},ac_cv_libseccomp=no,libseccomp"
PACKAGECONFIG[libidn] = "--with-idn,--without-idn,libidn2"
PACKAGECONFIG[libtasn1] = "--without-included-libtasn1,--with-included-libtasn1,libtasn1"
PACKAGECONFIG[p11-kit] = "--with-p11-kit,--without-p11-kit,p11-kit"
PACKAGECONFIG[tpm] = "--with-tpm,--without-tpm,trousers"
PACKAGECONFIG[fips] = "--enable-fips140-mode --with-libdl-prefix=${STAGING_DIR_HOST}"
PACKAGECONFIG[dane] = "--enable-libdane,--disable-libdane,unbound"
# Certificate compression
PACKAGECONFIG[brotli] = "--with-brotli,--without-brotli,brotli"
PACKAGECONFIG[zlib] = "--with-zlib,--without-zlib,zlib"
PACKAGECONFIG[zstd] = "--with-zstd,--without-zstd,zstd"

EXTRA_OECONF = " \
    --enable-doc \
    --disable-rpath \
    --enable-openssl-compatibility \
    --with-libpthread-prefix=${STAGING_DIR_HOST}${prefix} \
    --with-librt-prefix=${STAGING_DIR_HOST}${prefix} \
    --with-default-trust-store-file=${sysconfdir}/ssl/certs/ca-certificates.crt \
"

# Otherwise the tools try and use HOSTTOOLS_DIR/bash as a shell.
export POSIX_SHELL = "${base_bindir}/sh"

do_configure:prepend() {
	for dir in . lib; do
		rm -f ${dir}/aclocal.m4 ${dir}/m4/libtool.m4 ${dir}/m4/lt*.m4
	done
}

do_compile_ptest() {
    oe_runmake -C tests buildtest-TESTS
}

do_install:append:class-target() {
        if ${@bb.utils.contains('PACKAGECONFIG', 'fips', 'true', 'false', d)}; then
          install -d ${D}${bindir}/bin
          ${B}/libtool --mode=install install -m 0755 ${B}/lib/fipshmac ${D}/${bindir}/
        fi
}

EXTRA_TEST_DISALLOWLIST ?= ""

EXTRA_TEST_DISALLOWLIST:riscv64 = "\
    dtls-rehandshake-anon \
    dtls-rehandshake-cert \
    dtls-rehandshake-cert-2 \
    mini-loss-time \
    mini-record-2 \
    record-retvals \
    rng-op-key \
    rng-op-nonce \
    rng-op-random \
"

do_install_ptest_base:append() {
    sed -i 's:@EXTRA_TEST_DISALLOWLIST@:${EXTRA_TEST_DISALLOWLIST}:g' ${D}${PTEST_PATH}/run-ptest
}

PACKAGES =+ "${PN}-dane ${PN}-openssl ${PN}-xx ${PN}-fips"

FILES:${PN}-dev += "${bindir}/gnutls-cli-debug"

FILES:${PN}-dane = "${libdir}/libgnutls-dane.so.*"
FILES:${PN}-openssl = "${libdir}/libgnutls-openssl.so.*"
FILES:${PN}-xx = "${libdir}/libgnutlsxx.so.*"
FILES:${PN}-fips = "${bindir}/fipshmac"

RDEPENDS:${PN}-ptest += "python3"

BBCLASSEXTEND = ""

pkg_postinst_ontarget:${PN}-fips () {
    if test -x ${bindir}/fipshmac
    then
        mkdir -p ${sysconfdir}/gnutls
        touch ${sysconfdir}/gnutls/config
        ${bindir}/fipshmac ${libdir}/libgnutls.so.30.*.* > ${libdir}/.libgnutls.so.30.hmac
        ${bindir}/fipshmac ${libdir}/libnettle.so.8.* > ${libdir}/.libnettle.so.8.hmac
        ${bindir}/fipshmac ${libdir}/libgmp.so.10.*.* > ${libdir}/.libgmp.so.10.hmac
        ${bindir}/fipshmac ${libdir}/libhogweed.so.6.* > ${libdir}/.libhogweed.so.6.hmac
    fi
}

CVE_STATUS[CVE-2023-0361] = "fixed-version: fixed in version 3.8.0"
CVE_STATUS[CVE-2025-32989] = "fixed-version: fixed in version 3.8.10"
CVE_STATUS[CVE-2025-32990] = "fixed-version: fixed in version 3.8.10"
CVE_STATUS[CVE-2026-1584] = "fixed-version: fixed in version 3.8.12"
CVE_STATUS[CVE-2026-42009] = "fixed-version: fixed in version 3.8.13"
CVE_STATUS[CVE-2026-42010] = "fixed-version: fixed in version 3.8.13"
# toate reparatiile anuntate in NEWS la 3.8.13 (GNUTLS-SA-2026-04-29-1 ... 13); NVD nu da pentru unele versiunea
# reparata (de pilda CVE-2026-33845, verificat si in sursa: lib/buffers.c foloseste frag_length)
CVE_STATUS_GROUPS += "CVE_HDS_GNUTLS_3_8_13"
CVE_HDS_GNUTLS_3_8_13 = "CVE-2026-33846 CVE-2026-33845 CVE-2026-3833 CVE-2026-42011 CVE-2026-42012 CVE-2026-42013 \
    CVE-2026-42014 CVE-2026-5260 CVE-2026-42015 CVE-2026-3832 CVE-2026-5419"
CVE_HDS_GNUTLS_3_8_13[status] = "fixed-version: fixed in version 3.8.13 (NEWS)"
