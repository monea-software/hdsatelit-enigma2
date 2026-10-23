# Reteta copiata din openembedded-core, meta/recipes-core/expat/expat_2.7.3.bb (ramane sub licenta MIT a stratului
# openembedded-core), adusa la expat 2.9.0.
# Repara gaurile din 2.7.3: CVE-2026-66046, CVE-2026-45186, CVE-2026-56132, CVE-2026-56403 pana la CVE-2026-56408
# (depasiri de intregi, mai usor de atins pe 32 de biti) si celelalte reparate pana la 2.8.4; CVE-2026-93990 (2.8.5,
# UTF-16 malformat); CVE-2026-102633 (depasire de intreg pe 32 de biti) si CVE-2026-77214 (XML_ParseBuffer), in 2.9.0.
# Arhiva https://github.com/libexpat/libexpat/releases/download/R_2_9_0/expat-2.9.0.tar.bz2, 685975 octeti; autorii
# nu publica sha256, ci semnatura .asc: verificata cu gpg (semnatura buna, cheia de lansare a autorului expat,
# 3176 EF7D B236 7F1F CA4F 306B 1F9B 0E90 9AF3 7285); sha256 de mai jos calculat pe arhiva verificata.
# Schimbari fata de original: numai versiunea si suma; run-ptest se ia din dosarul retetei din openembedded-core,
# prin FILESEXTRAPATHS:append. Biblioteca ramane libexpat.so.1.

FILESEXTRAPATHS:append := "${COREBASE}/meta/recipes-core/expat/expat:"

SUMMARY = "A stream-oriented XML parser library"
DESCRIPTION = "Expat is an XML parser library written in C. It is a stream-oriented parser in which an application registers handlers for things the parser might find in the XML document (like start tags)"
HOMEPAGE = "https://github.com/libexpat/libexpat"
SECTION = "libs"
LICENSE = "MIT"

LIC_FILES_CHKSUM = "file://COPYING;md5=f4fedd6116da0e171f7cb4d2923d7ac2"

VERSION_TAG = "${@d.getVar('PV').replace('.', '_')}"

SRC_URI = "${GITHUB_BASE_URI}/download/R_${VERSION_TAG}/expat-${PV}.tar.bz2  \
           file://run-ptest \
           "

GITHUB_BASE_URI = "https://github.com/libexpat/libexpat/releases/"
UPSTREAM_CHECK_REGEX = "releases/tag/R_(?P<pver>.+)"

SRC_URI[sha256sum] = "775e8a68f81a748a401dc3168318d4a39484eb4f954726f21517c8f42c0ba984"

EXTRA_OECMAKE:class-native += "-DEXPAT_BUILD_DOCS=OFF"

RDEPENDS:${PN}-ptest += "bash"

inherit cmake lib_package ptest github-releases

do_install_ptest:class-target() {
	install -m 755 ${B}/tests/runtests* ${D}${PTEST_PATH}
	install -m 755 ${B}/tests/benchmark/benchmark ${D}${PTEST_PATH}
}

# Numai pentru receptor: varianta native (unealta de constructie) ramane cea din straturile comune; altfel
# python3-native si aproape toate uneltele native s-ar construi din nou, fara niciun folos pentru receptor.

CVE_PRODUCT = "expat libexpat"
