# Reteta copiata din openembedded-core, ramura OE-Alliance 6.0 (commit ae5cafacec, „blacksail”),
# meta/recipes-support/ca-certificates/ca-certificates_20260816.bb, cu dosarul ei de petice (ramane sub licenta MIT a
# stratului openembedded-core). Imaginea avea ca-certificates 20250419 (OE-Alliance 5.6), neschimbat de la 19.04.2025
# (Eduard 02.11.2026: „certificatele”; LIPSURI-PLANURI.md L18).
# 20260816 = Mozilla 2.90 (adaugate SECOM TLS ECC/RSA Root CA 2024, Telia EC/RSA TLS Root CA v3; scoase Atos TrustedRoot
# 2011, Entrust Root Certification Authority, SecureSign Root CA12, ePKI Root Certification Authority), plus 20260601
# (Mozilla 2.86) dinaintea ei. Peticul 0001-Blacklist-... scoate emSign ECC Root CA - G3 si Comodo AAA Services root,
# ca Debian 20260816+nmu1 (20.10.2026); arhiva Debian simpla nu mai e in pool, bitbake o ia de pe oglinda Yocto
# (downloads.yoctoproject.org/mirror/sources), 271796 octeti, sha256 de mai jos verificat pe 02.11.2026.
# Schimbare fata de original: LICENSE cu „&” in loc de „AND”, ca la reteta 20250419 a ramurii 5.6.
SUMMARY = "Common CA certificates"
DESCRIPTION = "This package includes PEM files of CA certificates to allow \
SSL-based applications to check for the authenticity of SSL connections. \
This derived from Debian's CA Certificates."
HOMEPAGE = "http://packages.debian.org/sid/ca-certificates"
SECTION = "misc"
LICENSE = "GPL-2.0-or-later & MPL-2.0"
LIC_FILES_CHKSUM = "file://debian/copyright;md5=dab7c7cea776d1a1648deb0052c72647"

# This is needed to ensure we can run the postinst at image creation time
DEPENDS = ""
DEPENDS:class-native = "openssl-native"
DEPENDS:class-nativesdk = "openssl-native"
# Need rehash from openssl and run-parts from debianutils
PACKAGE_WRITE_DEPS += "openssl-native debianutils-native"

SRC_URI[sha256sum] = "d939bcdd0cb058712cf4175bac76997676eb8b68fe9473765e1b40fb3d5b186a"
SRC_URI = "${DEBIAN_MIRROR}/main/c/ca-certificates/${BPN}_${PV}.tar.xz \
           file://0001-update-ca-certificates-don-t-use-Debianisms-in-run-p.patch \
           file://0003-update-ca-certificates-use-relative-symlinks-from-ET.patch \
           file://0001-Revert-mozilla-certdata2pem.py-print-a-warning-for-e.patch \
           file://0001-Blacklist-emSign-ECC-Root-CA-G3-and-Comodo-AAA-Servi.patch \
           "
S = "${UNPACKDIR}/ca-certificates"
inherit allarch

EXTRA_OEMAKE = "\
    'CERTSDIR=${datadir}/ca-certificates' \
    'SBINDIR=${sbindir}' \
"

do_compile:prepend() {
    oe_runmake clean
}

do_install () {
    install -d ${D}${datadir}/ca-certificates \
               ${D}${sysconfdir}/ssl/certs \
               ${D}${sysconfdir}/ca-certificates/update.d
    oe_runmake 'DESTDIR=${D}' install

    install -d ${D}${mandir}/man8
    install -m 0644 sbin/update-ca-certificates.8 ${D}${mandir}/man8/

    install -d ${D}${sysconfdir}
    {
        echo "# Lines starting with # will be ignored"
        echo "# Lines starting with ! will remove certificate on next update"
        echo "#"
        find ${D}${datadir}/ca-certificates -type f -name '*.crt' | \
            sed 's,^${D}${datadir}/ca-certificates/,,' | sort
    } >${D}${sysconfdir}/ca-certificates.conf
}

do_install:append:class-target () {
    sed -i -e 's,/etc/,${sysconfdir}/,' \
           -e 's,/usr/share/,${datadir}/,' \
           -e 's,/usr/local,${prefix}/local,' \
        ${D}${sbindir}/update-ca-certificates \
        ${D}${mandir}/man8/update-ca-certificates.8
}

pkg_postinst:${PN}:class-target () {
    [ -n "$D" ] && sysroot_args="--sysroot $D"
    $D${sbindir}/update-ca-certificates $sysroot_args
}

CONFFILES:${PN} += "${sysconfdir}/ca-certificates.conf"

# Rather than make a postinst script that works for both target and nativesdk,
# we just run update-ca-certificate from do_install() for nativesdk.
CONFFILES:${PN}:append:class-nativesdk = " ${sysconfdir}/ssl/certs/ca-certificates.crt"
do_install:append:class-nativesdk () {
    ${D}${sbindir}/update-ca-certificates --sysroot ${D}${SDKPATHNATIVE}
}

do_install:append:class-native () {
    ${D}${sbindir}/update-ca-certificates --sysroot ${D}${base_prefix}
}

RDEPENDS:${PN}:append:class-target = " openssl-bin openssl"
RDEPENDS:${PN}:append:class-native = " openssl-native"
RDEPENDS:${PN}:append:class-nativesdk = " nativesdk-openssl-bin nativesdk-openssl"

BBCLASSEXTEND = "native nativesdk"
