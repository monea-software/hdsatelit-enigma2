# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# odhcp6c (clientul DHCPv6: ruleaza ca root si primeste pachete din reteaua locala) adus la comiterea
# 10a52220aec9d45803518d8cc4d63e552484ed61, capul ramurii master din depozitul OpenWrt. Fata de SRCREV-ul retetei din
# meta-oe-alliance (f2521b29) are reparatiile din amonte b6f0c70f (citire peste capatul optiunii IA din Advertise) si
# 0a4e51db (Reconfigure primit de la un server necunoscut), plus celelalte reparatii de dupa ea. La o comitere git nu
# exista suma publicata; identitatea sursei o da SHA-ul intreg.
# Reteta (meta-oe-alliance odhcp6c.bb, fara versiune in nume, deci bbappend fara %) nu merge numai cu SRCREV nou:
# - libubox e obligatoriu in amonte (src/dhcpv6.c include libubox/md5.h): DEPENDS libubox (libubox_git.bb din
#   meta-openembedded/meta-oe); sed-ul retetei pe LIBUBOX nu mai are pe ce sa se aplice;
# - configurarea trece pe cmake.bbclass (fisierul de toolchain si sysroot-ul tintei) in locul lui `cmake .` din
#   reteta, care ar cauta libubox pe gazda; UBUS=OFF, receptorul nu are ubus (codul ubus e numai sub WITH_UBUS).
#   do_configure se scrie din nou aici pentru ca reteta il defineste, iar inherit cmake nu inlocuieste o functie deja
#   definita de reteta (EXPORT_FUNCTIONS); do_compile vine din cmake.bbclass;
# - programul se construieste in ${B}, nu in ${S}; se instaleaza tot in ${bindir}, ca pana acum (instalarea cmake
#   l-ar pune in ${sbindir});
# - scriptul implicit al programului s-a mutat in /lib/netifd/dhcpv6.script; files/ifup (ifup-ul retetei cu o
#   singura schimbare) ii da explicit -s /usr/sbin/odhcp6c-update. Variabilele si starile trimise scriptului sunt
#   aceleasi ca la comiterea veche. files/ifup vine inaintea celui din meta-oe-alliance prin FILESEXTRAPATHS:prepend.
# Constructia se opreste daca ifup-ul instalat nu are -s cu scriptul retetei.
#
# IPv6 oprit din fabrica: clientul porneste numai cand exista fisierul-semn /etc/hds-ipv6-pornit. Il pornesc doua cai,
# amandoua prin numele odhcp6c din PATH: ifup-ul din busybox pentru randul "iface ... inet6 dhcp" (peticul
# 0002-Extended-network-interfaces-support din meta-oe-alliance; asa e eth0 in /etc/network/interfaces din fabrica, iar
# files/ifup iese atunci devreme) si files/ifup pentru interfetele fara rand inet6. De aceea poarta e /usr/bin/odhcp6c
# (files/hds-odhcp6c, un script sh), iar programul sta in /usr/libexec/hds-odhcp6c/odhcp6c, cu acelasi nume de proces.
# files/ifup are si el poarta. sysctl-ul IPv6 e in reteta hdsatelit-ipv6. PR .hds1: continutul pachetului s-a schimbat
# la aceeasi versiune.

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SRCREV = "10a52220aec9d45803518d8cc4d63e552484ed61"

PR:append = ".hds1"

SRC_URI += "file://hds-odhcp6c"

DEPENDS += "libubox"

inherit cmake

EXTRA_OECMAKE = "-DUBUS=OFF"

do_configure() {
	cmake_do_configure
}

do_install() {
	install -d ${D}${bindir} ${D}${libexecdir}/hds-odhcp6c
	install -m 755 ${B}/odhcp6c ${D}${libexecdir}/hds-odhcp6c/odhcp6c
	install -m 755 ${UNPACKDIR}/hds-odhcp6c ${D}${bindir}/odhcp6c
	install -d ${D}${sysconfdir}/network/if-up.d
	install -m 755 ${UNPACKDIR}/ifup ${D}${sysconfdir}/network/if-up.d/odhcp6c
	grep -q "^odhcp6c -s ${sbindir}/odhcp6c-update " ${D}${sysconfdir}/network/if-up.d/odhcp6c || \
		bbfatal "odhcp6c: ifup nu da -s ${sbindir}/odhcp6c-update"
	# poarta semnului: in ifup si in /usr/bin/odhcp6c (script sh fara CRLF, cu semnul si cu calea programului, care
	# e ELF si sta exact unde il cauta poarta)
	grep -qx '\[ -e /etc/hds-ipv6-pornit \] || exit 0' ${D}${sysconfdir}/network/if-up.d/odhcp6c || \
		bbfatal "odhcp6c: ifup fara poarta semnului /etc/hds-ipv6-pornit"
	if grep -q "$(printf '\r')" ${D}${bindir}/odhcp6c ${D}${sysconfdir}/network/if-up.d/odhcp6c; then
		bbfatal "odhcp6c: poarta sau ifup cu sfarsit de rand CRLF"
	fi
	sh -n ${D}${bindir}/odhcp6c || bbfatal "odhcp6c: poarta nu e sh valid"
	grep -q 'HDS_IPV6_SEMN:-/etc/hds-ipv6-pornit}" \] || exit 0$' ${D}${bindir}/odhcp6c || \
		bbfatal "odhcp6c: poarta nu cere semnul /etc/hds-ipv6-pornit"
	grep -qx 'exec /usr/libexec/hds-odhcp6c/odhcp6c "$@"' ${D}${bindir}/odhcp6c || \
		bbfatal "odhcp6c: poarta nu porneste /usr/libexec/hds-odhcp6c/odhcp6c"
	[ "${libexecdir}" = /usr/libexec ] || bbfatal "odhcp6c: libexecdir nu e /usr/libexec (calea din poarta)"
	head -c 4 ${D}${libexecdir}/hds-odhcp6c/odhcp6c | grep -q 'ELF' || bbfatal "odhcp6c: programul nu e ELF"
	install -d ${D}${sysconfdir}/network/if-down.d
	install -m 755 ${UNPACKDIR}/ifdown ${D}${sysconfdir}/network/if-down.d/odhcp6c
	install -d ${D}${sbindir}
	install -m 755 ${UNPACKDIR}/odhcp6c-update ${D}${sbindir}/odhcp6c-update
}

FILES:${PN} += "${libexecdir}/hds-odhcp6c"
