# Reteta copiata din openembedded-core, meta/recipes-support/gnutls/libtasn1_4.20.0.bb, impreuna cu libtasn1/ (raman
# sub licenta MIT a stratului openembedded-core), adusa la libtasn1 4.21.0 (ca in openembedded-core master).
# Repara CVE-2025-13151 (depasire de stiva in asn1_expend_octet_string, certificate citite de gnutls si de navigator).
# Arhiva https://ftp.gnu.org/gnu/libtasn1/libtasn1-4.21.0.tar.gz; semnatura .sig verificata cu gpg (semnatura buna,
# Simon Josefsson, subcheia A3CC 9C87 0B9D 310A BAD4 CF2F 5172 2B08 FE47 45A2 din gnu-keyring.gpg); sha256 de mai jos
# egal cu cel din openembedded-core master. Sumele licentelor neschimbate (verificate), peticul OE se aplica la fel.
# Schimbari fata de original: acest antet, versiunea, suma si BBCLASSEXTEND gol (reteta numai pentru receptor).
# Biblioteca ramane libtasn1.so.6 (pachetul libtasn1-6), deci poate veni si prin actualizare.

SUMMARY = "Library for ASN.1 and DER manipulation"
DESCRIPTION = "A highly portable C library that encodes and decodes \
DER/BER data following an ASN.1 schema. "
HOMEPAGE = "http://www.gnu.org/software/libtasn1/"

LICENSE = "GPL-3.0-or-later & LGPL-2.1-or-later"
LICENSE:${PN}-bin = "GPL-3.0-or-later"
LICENSE:${PN} = "LGPL-2.1-or-later"
LIC_FILES_CHKSUM = "file://COPYING;md5=1ebbd3e34237af26da5dc08a4e440464 \
                    file://COPYING.LESSERv2;md5=4bf661c1e3793e55c8d1051bc5e0ae21"

SRC_URI = "${GNU_MIRROR}/libtasn1/libtasn1-${PV}.tar.gz \
           file://dont-depend-on-help2man.patch \
           "

DEPENDS = "bison-native"

SRC_URI[sha256sum] = "1d8a444a223cc5464240777346e125de51d8e6abf0b8bac742ac84609167dc87"

inherit autotools texinfo lib_package gtk-doc

BBCLASSEXTEND = ""
