# Reteta copiata din openembedded-core, meta/recipes-support/libsoup/libsoup_3.6.5.bb (ramane sub licenta MIT a
# stratului openembedded-core), adusa la libsoup 3.8.0 (singura versiune a ramurii 3.8).
# Repara, dupa NEWS: CVE-2026-3099 si CVE-2026-66337 (3.8.0); CVE-2026-15709, CVE-2026-15711, CVE-2026-66339,
# CVE-2026-12547, CVE-2026-15713, CVE-2026-3633 si CVE-2026-85534 (3.7.3); plus cele din NVD pentru 3.6.5, intre ele
# CVE-2026-2369 si CVE-2026-66338. libsoup 3 il folosesc navigatorul si, de acum, pluginul soup din gstreamer
# (recipes-local/gstreamer/gstreamer1.0-plugins-good_%.bbappend scoate libsoup-2.4 din imagine).
# Arhiva https://download.gnome.org/sources/libsoup/3.8/libsoup-3.8.0.tar.xz, 1609676 octeti; sha256 de mai jos
# calculat pe arhiva si egal cu cel publicat de autori (libsoup-3.8.0.sha256sum pe download.gnome.org).
# Schimbari fata de original: versiunea, suma si PACKAGECONFIG[zstd]: 3.8 are optiunea meson zstd (auto); fara
# rand ar porni sau nu dupa ce se afla in sysroot. zstd nu e in PACKAGECONFIG, deci se trimite -Dzstd=disabled si
# dependintele raman cele de pana acum. bbappend-ul meta-oe-alliance libsoup_3%.bbappend se aplica singur.

SUMMARY = "An HTTP library implementation in C"
DESCRIPTION = "libsoup is an HTTP client/server library for GNOME. It uses GObjects \
and the glib main loop, to integrate well with GNOME applications."
HOMEPAGE = "https://wiki.gnome.org/Projects/libsoup"
BUGTRACKER = "https://bugzilla.gnome.org/"
SECTION = "x11/gnome/libs"
LICENSE = "LGPL-2.0-only"
LIC_FILES_CHKSUM = "file://COPYING;md5=5f30f0716dfdd0d91eb439ebec522ec2"

DEPENDS = "glib-2.0 glib-2.0-native libxml2 sqlite3 libpsl nghttp2"

SHRT_VER = "${@d.getVar('PV').split('.')[0]}.${@d.getVar('PV').split('.')[1]}"

SRC_URI = "${GNOME_MIRROR}/libsoup/${SHRT_VER}/libsoup-${PV}.tar.xz"
SRC_URI[sha256sum] = "bbf08fa3e03a88c31a3d27a0d87cb422e9490f2d08e149211103df6d638a2238"

PROVIDES = "libsoup-3.0"
CVE_PRODUCT = "libsoup"
# Reparate in versiuni de dinainte de 3.8.0, dar fara versiune in NVD (deci socotite nepatchuite); aceleasi randuri
# ca in reteta libsoup_3.8.0.bb din openembedded-core master. CVE-2026-2369 verificat si in sursa: problema 498 din
# amonte, inchisa, iar libsoup/content-sniffer/soup-content-sniffer.c din 3.8.0 iese devreme cand resource_length e 0.
CVE_STATUS[CVE-2026-1467] = "fixed-version: fixed in 3.6.6"
CVE_STATUS[CVE-2026-1536] = "fixed-version: fixed in 3.6.6"
CVE_STATUS[CVE-2026-1801] = "fixed-version: fixed in 3.6.6"
CVE_STATUS[CVE-2026-2369] = "fixed-version: fixed in 3.6.6"
CVE_STATUS[CVE-2026-2436] = "fixed-version: fixed in 3.6.6"
CVE_STATUS[CVE-2026-2443] = "fixed-version: fixed in 3.6.6"
CVE_STATUS[CVE-2026-1539] = "fixed-version: fixed in 3.7.1"
CVE_STATUS[CVE-2026-2708] = "fixed-version: fixed in 3.7.1"
CVE_STATUS[CVE-2026-4271] = "fixed-version: fixed in 3.7.1"
CVE_STATUS[CVE-2026-5119] = "fixed-version: fixed in 3.7.1"

S = "${UNPACKDIR}/libsoup-${PV}"

inherit meson gettext pkgconfig upstream-version-is-even gobject-introspection gi-docgen vala

GIR_MESON_ENABLE_FLAG = 'enabled'
GIR_MESON_DISABLE_FLAG = 'disabled'

PACKAGECONFIG ??= ""
PACKAGECONFIG[brotli] = "-Dbrotli=enabled,-Dbrotli=disabled,brotli"
PACKAGECONFIG[gssapi] = "-Dgssapi=enabled,-Dgssapi=disabled,krb5"
PACKAGECONFIG[ntlm] = "-Dntlm=enabled,-Dntlm=disabled"
PACKAGECONFIG[sysprof] = "-Dsysprof=enabled,-Dsysprof=disabled,sysprof"
PACKAGECONFIG[zstd] = "-Dzstd=enabled,-Dzstd=disabled,zstd"

# Tell libsoup where the target ntlm_auth is installed
do_write_config:append:class-target() {
    cat >${WORKDIR}/soup.cross <<EOF
[binaries]
ntlm_auth = '${bindir}/ntlm_auth'
EOF
}
EXTRA_OEMESON:append:class-target = " --cross-file ${WORKDIR}/soup.cross"

EXTRA_OEMESON += "-Dtls_check=false"
# Disable the test suites
EXTRA_OEMESON += "-Dtests=false -Dautobahn=disabled -Dpkcs11_tests=disabled"

GIDOCGEN_MESON_OPTION = 'docs'
GIDOCGEN_MESON_ENABLE_FLAG = 'enabled'
GIDOCGEN_MESON_DISABLE_FLAG = 'disabled'

# When built without gnome support, libsoup will contain only one shared lib
# and will therefore become subject to renaming by debian.bbclass. Prevent
# renaming in order to keep the package name consistent regardless of whether
# gnome support is enabled or disabled.
DEBIAN_NOAUTONAME:${PN} = "1"

# glib-networking is needed for SSL, proxies, etc.
RRECOMMENDS:${PN} = "glib-networking"

# Numai pentru receptor: varianta native (unealta de constructie) ramane cea din straturile comune; altfel
# python3-native si aproape toate uneltele native s-ar construi din nou, fara niciun folos pentru receptor.
