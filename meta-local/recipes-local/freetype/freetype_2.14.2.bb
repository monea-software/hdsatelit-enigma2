SUMMARY = "Freetype font rendering library"
DESCRIPTION = "FreeType is a software font engine that is designed to be small, efficient, \
highly customizable, and portable while capable of producing high-quality output (glyph \
images). It can be used in graphics libraries, display servers, font conversion tools, text \
image generation tools, and many other products as well."
HOMEPAGE = "http://www.freetype.org/"
BUGTRACKER = "https://savannah.nongnu.org/bugs/?group=freetype"
SECTION = "libs"

LICENSE = "(FTL | GPL-2.0-or-later) & MIT"
# HDSatelit 21.09.2026: LICENSE.TXT si docs/FTL.TXT chiar s-au schimbat intre 2.13.3 si 2.14.2 (verificat
# direct, md5sum pe arhiva reala descarcata, nu presupus identic cu reteta veche) -- hash-uri noi mai jos.
# docs/GPLv2.TXT a ramas neschimbat (boilerplate GPL, md5 identic cu reteta veche).
LIC_FILES_CHKSUM = "file://LICENSE.TXT;md5=eeb073d5fb86d23c52bb9b84aa256307 \
                    file://docs/FTL.TXT;md5=72d844cd2f3bcaf6a85244b508032be7 \
                    file://docs/GPLv2.TXT;md5=8ef380476f642c20ebf40fecb0add2ec \
                    "

# HDSatelit 21.09.2026: bump de versiune, gasit lipsa la auditul de CVE-uri periodic (TODO.md/
# ACTUALIZARI-IMAGINE.md, 20.09.2026) -- 2.13.3 e sub pragul sigur (CVE-2026-23865, CVSS 5.3, reparat in
# 2.14.2). Nicio reteta pentru o versiune mai noua nu exista deja in openembedded-core (verificat).
# Arhiva si sha256 verificate REAL, descarcate si calculate direct (nu doar copiate dintr-o cautare),
# 21.09.2026: https://download.savannah.gnu.org/releases/freetype/freetype-2.14.2.tar.xz, 2667092 octeti
# -- confirmat identic cu valoarea din anuntul oficial de lansare, verificare incrucisata.
SRC_URI = "https://download.savannah.gnu.org/releases/freetype/freetype-2.14.2.tar.xz"
SRC_URI[sha256sum] = "4b62dcab4c920a1a860369933221814362e699e26f55792516d671e6ff55b5e1"

UPSTREAM_CHECK_REGEX = "freetype-(?P<pver>\d+(\.\d+)+)"

inherit autotools pkgconfig multilib_header

# Adapt autotools to work with the minimal autoconf usage in freetype
AUTOTOOLS_SCRIPT_PATH = "${S}/builds/unix"
CONFIGURE_SCRIPT = "${S}/configure"
EXTRA_AUTORECONF += "--exclude=autoheader --exclude=automake -I ."

PACKAGECONFIG ??= "zlib pixmap"

PACKAGECONFIG[brotli] = "--with-brotli,--without-brotli,brotli"
PACKAGECONFIG[bzip2] = "--with-bzip2,--without-bzip2,bzip2"
# harfbuzz results in a circular dependency so enabling is non-trivial
PACKAGECONFIG[harfbuzz] = "--with-harfbuzz,--without-harfbuzz,harfbuzz"
PACKAGECONFIG[pixmap] = "--with-png,--without-png,libpng"
PACKAGECONFIG[zlib] = "--with-zlib,--without-zlib,zlib"
PACKAGECONFIG[freetypeconfig] = "--enable-freetype-config=yes,--enable-freetype-config=no,"

EXTRA_OECONF = "CC_BUILD='${BUILD_CC}'"

TARGET_CPPFLAGS += "-D_FILE_OFFSET_BITS=64"

do_install:append() {
	oe_multilib_header freetype2/freetype/config/ftconfig.h
}

BBCLASSEXTEND = "native nativesdk"
