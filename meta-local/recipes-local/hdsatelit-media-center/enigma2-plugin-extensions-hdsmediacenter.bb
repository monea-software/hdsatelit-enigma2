# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Media Center (Kodi 22 din OE-Alliance, redenumit) din feedul nostru, NU din imagine (Eduard, 13.11.2026 08:54): pachetul pe care il
# instaleaza cardul din meniul Aplicatii (magazinul, Components/HdsAplicatii.py). E pluginul de pornire
# (Plugins/Extensions/HdsMediaCenter/plugin.py: porneste(session)) si trage cu el Kodi-ul masinii prin RDEPENDS virtual-kodi
# (PREFERRED_PROVIDER_virtual/kodi = stb-kodi-${MACHINE} in configurarea masinii OE-Alliance; pe u57: stb-kodi-u57).
#   instalare:    opkg install enigma2-plugin-extensions-hdsmediacenter      (aduce si stb-kodi-<masina> cu dependintele)
#   dezinstalare: opkg remove --autoremove enigma2-plugin-extensions-hdsmediacenter
#                 (scoate si Kodi si dependintele aduse odata cu el; un Kodi instalat altfel, de mana, ramane)
# Profilul Kodi (/media/hdd/.kodi, pe stick sau disc) e al omului: nu se sterge la dezinstalare.
# Pornirea: iesirea enigma2 cu codul 15, cazul 15 din tools/enigma2.sh.in al imaginii (0.7.5 si mai noi); pe o imagine
# fara el, enigma2 doar reporneste. Culegerea feedului: --cu enigma2-plugin-extensions-hdsmediacenter (dosarul masinii).
# Numele fara „kodi” (Eduard, 13.11 09:12: redenumire completa); pachetele OE-Alliance stb-kodi-<masina> raman, nu se vad.
# Modulul Widevine nu e aici: il aduce omul (Components/HdsWidevine.py din imagine), pluginul doar il leaga in profil.
# Numele aratat omului e neutru („Media Center”, „Powered by Kodi”): politica marcii Kodi, vezi plugin.py.
SUMMARY = "Media Center (Powered by Kodi) pentru imaginea HD Satelit"
DESCRIPTION = "Porneste centrul media pe tot ecranul, in locul interfetei, si intoarce in interfata la iesire. \
Profilul sta pe un stick USB sau pe un disc. Versiune modificata pentru receptoare, nu e un produs XBMC Foundation."
HOMEPAGE = "https://moneasoftware.com"
SECTION = "extra"
LICENSE = "GPL-2.0-only"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/GPL-2.0-only;md5=801f80980d171dd6425610833a22dbe6"
PV = "0.1.0"
PR = "r1"

SRC_URI = "file://plugin.py file://__init__.py"
S = "${UNPACKDIR}"

INHIBIT_DEFAULT_DEPS = "1"
PACKAGE_ARCH = "all"
do_configure[noexec] = "1"
do_compile[noexec] = "1"

PLUGINDIR = "${libdir}/enigma2/python/Plugins/Extensions/HdsMediaCenter"

do_install() {
    install -d ${D}${PLUGINDIR}
    install -m 0644 ${S}/__init__.py ${S}/plugin.py ${D}${PLUGINDIR}/
}

RDEPENDS:${PN} = "virtual-kodi"

# gzip, ca celelalte retete ale noastre din feed: opkg-urile vechi nu despacheteaza zstd
OPKGBUILDCMD = 'opkg-build -Z gzip -a "-9n"'

PACKAGES = "${PN}"
FILES:${PN} = "${PLUGINDIR}"

pkg_postrm:${PN}() {
#!/bin/sh
[ -n "$D" ] && exit 0
case "$1" in
    upgrade) exit 0 ;;
esac
rm -rf /usr/lib/enigma2/python/Plugins/Extensions/HdsMediaCenter /tmp/hds-kodi.stare /tmp/hds-kodi.stare.citit /tmp/hds-kodi.videomode
exit 0
}
