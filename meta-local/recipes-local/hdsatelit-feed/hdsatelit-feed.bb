# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
SUMMARY = "HDSatelit: sursele opkg ale actualizarilor prin pachete"
DESCRIPTION = "Fisierul /etc/opkg/hdsatelit-feed.conf: canalul public al feedului de actualizari de pe \
stb.hdsatelit.com, legat de versiunea imaginii (DISTRO_VERSION). Monea Software pentru HD Satelit."
LICENSE = "GPL-2.0-only"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/GPL-2.0-only;md5=801f80980d171dd6425610833a22dbe6"
PV = "0.1.0"

# Cate o sursa src/gz pe fiecare arhitectura a imaginii (all, procesorul, masina, numele receptorului), toate sub
#   ${DISTRO_FEED_URI}/<arh>   = https://stb.hdsatelit.com/feed/public/<versiunea imaginii>/<arh>
# Feedul e legat de baza imaginii: o imagine noua nu ia niciodata pachetele facute pentru alta imagine. Canalul de proba
# (numai receptoarele noastre) NU vine din imagine: /etc/opkg/hdsatelit-proba-feed.conf si parola il pune trusa
# (scripturi/pune-feed-proba.sh). Inainte de lansarea unei imagini cu o baza noua, pe server trebuie sa existe feedul ei
# public (macar gol: unelte/stb/publica_feed.py public-gol <baza>), altfel opkg update da eroare.
# Pachetul tine de masina (arhitecturile ei), nu numai de procesor. Fisierul e CONFFILES: o actualizare nu il calca daca
# omul l-a schimbat.
PACKAGE_ARCH = "${MACHINE_ARCH}"
INHIBIT_DEFAULT_DEPS = "1"
S = "${UNPACKDIR}"

do_configure[noexec] = "1"

HDS_FEED_ARHITECTURI = "all ${TUNE_PKGARCH} ${MACHINE_ARCH} ${MACHINEBUILD}"
do_compile[vardeps] += "DISTRO_FEED_URI HDS_FEED_ARHITECTURI"

do_compile() {
	case "${DISTRO_FEED_URI}" in
	https://stb.hdsatelit.com/feed/public/${DISTRO_VERSION}) ;;
	*) bbfatal "hdsatelit-feed: DISTRO_FEED_URI trebuie sa fie https://stb.hdsatelit.com/feed/public/${DISTRO_VERSION}, nu '${DISTRO_FEED_URI}'" ;;
	esac
	f=${B}/hdsatelit-feed.conf
	printf '%s\n' "# HD Satelit: actualizarile prin pachete (Meniu > Setari > Software & Firmware > Actualizare software)." \
		"# Feedul e legat de imaginea ${DISTRO_VERSION}; imaginea urmatoare are feedul ei." > "$f"
	vazute=" "
	for arh in ${HDS_FEED_ARHITECTURI}; do
		case "$vazute" in *" $arh "*) continue ;; esac
		vazute="$vazute$arh "
		echo "src/gz hdsatelit-$arh ${DISTRO_FEED_URI}/$arh" >> "$f"
	done
	grep -q '@' "$f" && bbfatal "hdsatelit-feed: o adresa are nume sau parola"
	true
}

do_install() {
	install -d ${D}${sysconfdir}/opkg
	install -m 0644 ${B}/hdsatelit-feed.conf ${D}${sysconfdir}/opkg/hdsatelit-feed.conf
}

FILES:${PN} = "${sysconfdir}/opkg/hdsatelit-feed.conf"
CONFFILES:${PN} = "${sysconfdir}/opkg/hdsatelit-feed.conf"
