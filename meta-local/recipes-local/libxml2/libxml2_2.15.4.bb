SUMMARY = "XML C Parser Library and Toolkit"
DESCRIPTION = "The XML Parser Library allows for manipulation of XML files. Libxml2 exports Push and Pull type parser interfaces for both XML and HTML. It also has a SAX like interface, which is designed to be compatible with Expat."
HOMEPAGE = "https://gitlab.gnome.org/GNOME/libxml2"
BUGTRACKER = "https://gitlab.gnome.org/GNOME/libxml2/-/issues"
SECTION = "libs"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://Copyright;md5=5873615e8a9ecbf5c8857c4312ee05d6 \
                    file://dict.c;beginline=6;endline=15;md5=2b4b7b827d2d8b080372433c4c9c85b6 \
                    file://list.c;beginline=4;endline=13;md5=b9c25b021ccaf287e50060602d20f3a7 \
                    "

# HDSatelit 21.09.2026: bump de versiune deliberat, gasit lipsa la auditul de CVE-uri periodic
# (TODO.md/ACTUALIZARI-IMAGINE.md, 20.09.2026) -- 2.14.6 e sub pragul sigur (CVE-2026-86140, CVSS 8.0,
# reparat in 2.15.4). Nicio reteta pentru o versiune mai noua nu exista deja in openembedded-core
# (verificat cu grep/find inainte de a scrie asta) -- reteta noua, proprie, in loc de un simplu
# PREFERRED_VERSION/bbappend, ca sa nu depinda de fisierele de reteta veche (patch-uri specifice
# versiunii 2.14.x care nu se stie daca s-ar mai aplica curat).
#
# Simplificata deliberat fata de reteta stock din openembedded-core: am scos suportul ptest (fisierele
# lui insotitoare, run-ptest/install-tests.patch, nu sunt folosite de imaginea asta -- niciun ptest
# rulat pe acest receptor) si patch-ul de revenire CMake (irelevant, aceasta reteta foloseste autotools,
# nu cmake) si CVE-2025-6021.patch (CVE pentru o versiune mult mai veche, deja acoperit de reparatiile
# reale incluse in sursa 2.15.4 descarcata direct de la upstream).
#
# Arhiva si sha256 verificate REAL, descarcate si calculate direct (nu doar copiate dintr-o cautare),
# 21.09.2026: https://download.gnome.org/sources/libxml2/2.15/libxml2-2.15.4.tar.xz, 3177444 octeti.
DEPENDS = "zlib virtual/libiconv"

SRC_URI = "https://download.gnome.org/sources/libxml2/2.15/libxml2-2.15.4.tar.xz"
SRC_URI[sha256sum] = "98087fd181d9070724f3fbc65c7377db03038eb92bd882374daff44940138821"

# HDSatelit 21.09.2026: fara `S = ...` explicit -- bitbake deriva automat "${UNPACKDIR}/${BPN}-${PV}",
# exact numele folderului din arhiva. Prima incercare cu `S = "${WORKDIR}/..."` a picat la `do_unpack`
# cu eroare directa de la bitbake ("S should be set relative to UNPACKDIR") -- gasita real, la rulare,
# nu presupusa; reparata prin eliminarea liniei, nu prin inlocuirea WORKDIR cu UNPACKDIR (mai simplu,
# acelasi rezultat, fara sa mai fie nevoie sa tina pasul manual cu numele exact al folderului).

BINCONFIG = "${bindir}/xml2-config"

PACKAGECONFIG ??= "python"
PACKAGECONFIG[python] = "--with-python=${PYTHON},--without-python,python3"

inherit autotools pkgconfig binconfig-disabled

inherit_defer ${@bb.utils.contains('PACKAGECONFIG', 'python', 'python3targetconfig', '', d)}

RDEPENDS:${PN}-python += "${@bb.utils.contains('PACKAGECONFIG', 'python', 'python3-core', '', d)}"

# HDSatelit 21.09.2026: --without-lzma scos deliberat -- verificat direct cu `./configure --help` pe
# sursa reala 2.15.4, optiunea nu mai exista deloc (suport lzma scos upstream intre 2.14 si 2.15); restul
# fanioanelor (debug/legacy/catalog/c14n) confirmate inca valabile, neschimbate fata de reteta veche.
EXTRA_OECONF = "--without-debug --without-legacy --with-catalog --with-c14n"
EXTRA_OECONF:class-native = "--without-legacy --with-c14n --with-zlib"
EXTRA_OECONF:class-nativesdk = "--without-legacy --with-c14n --with-zlib"
EXTRA_OECONF:linuxstdbase = "--with-debug --with-legacy --with-c14n --with-zlib"

python populate_packages:prepend () {
    # autonamer would call this libxml2-2, but we don't want that
    if d.getVar('DEBIAN_NAMES'):
        d.setVar('PKG:libxml2', '${MLPREFIX}libxml2')
}

PACKAGE_BEFORE_PN += "${PN}-utils"
PACKAGES += "${PN}-python"

FILES:${PN}-staticdev += "${PYTHON_SITEPACKAGES_DIR}/*.a"
FILES:${PN}-utils = "${bindir}/*"
FILES:${PN}-python = "${PYTHON_SITEPACKAGES_DIR}"

do_install:append:class-native () {
	# Docs are not needed in the native case
	rm ${D}${datadir}/gtk-doc -rf

	create_wrapper ${D}${bindir}/xmllint 'XML_CATALOG_FILES=${XML_CATALOG_FILES:-${sysconfdir}/xml/catalog}'
}
do_install[vardepsexclude] += "XML_CATALOG_FILES:-${sysconfdir}/xml/catalog"

BBCLASSEXTEND = "native nativesdk"
