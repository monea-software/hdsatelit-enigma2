# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# busybox-udhcpc: scriptul nostru /etc/udhcpc.d/50default (files/hds-udhcpc-50default) in locul celui din stratul comun.
# Cel din stratul comun sterge TOATE rutele implicite (si pe cele ale celorlalte placi) si pune ruta noua fara
# "dev <placa>": cu cablul scos, Wi-Fi-ul primea adresa, dar ruta implicita ajungea tot pe cablu, deci trecerea singura
# pe Wi-Fi (Components/HdsComutareRetea.py) nu gasea niciodata o ruta prin Wi-Fi. Al nostru lucreaza numai pe placa
# raspunsului DHCP, cu "dev" si cu metrica 10 pentru placile fara fir (0 pentru cablu).
# PR:append schimba versiunea pachetelor (acelasi busybox), ca opkg sa ia busybox-udhcpc din feed.
#
# busybox-syslog (.hds2, imaginea 0.5.0, lotul imagine-050): jurnalul sistemului mai mare. /etc/syslog-startup.conf
# venea cu ROTATESIZE=256 si ROTATEGENS=1 (syslogd -s 256 -b 1: un singur fisier vechi de 256 KB), iar placa Wi-Fi
# scria ~260 KB in primele 2 minute dupa pornire, deci jurnalul de dinainte de o pana de curent se pierdea (TODO
# 17.10.2026 19:14). Acum 1024 KB si 4 fisiere vechi (cel mult ~5 MB in /home/root/logs). Fisierul e conffile, deci
# schimbarea ajunge numai cu o imagine noua (o actualizare nu rescrie un conffile schimbat).
#
# crond si crontab (.hds3, imaginea 0.7.4, 11.11.2026): pluginurile (Cron Manager din AIO Panel, CronTimers si altele)
# scriu sarcini programate, dar busybox venea fara crond (CONFIG_CROND nesetat in defconfig-ul stratului comun) si
# imaginea nu avea alt cron: sarcinile nu rulau niciodata, fara niciun mesaj. files/hds-crond.cfg pune applet-urile
# crond si crontab (fara e-mail; cu @reboot/@daily), cu dosarul /var/spool/cron/crontabs. Pachetul nou busybox-cron
# are /etc/init.d/crond (files/hds-crond, S90), care porneste crond NUMAI cand exista cel putin o sarcina (altfel
# niciun proces in plus), si dosarul /etc/cron/crontabs. Postinst-ul lui face legaturile /var/spool/cron -> /etc/cron
# (ca in stratul comun, tuxbox-links) si /etc/crontabs -> cron/crontabs (unde cauta AIO intai); daca un plugin facuse
# deja un /etc/crontabs adevarat, sarcinile lui trec in /etc/cron/crontabs. busybox cere busybox-cron, deci vine si
# la actualizarea din feed. Scriptul /etc/init.d/busybox-cron al stratului comun (alt dosar, fara conditie) nu intra.
#
# jurnalul sistemului fara nivelul debug (.hds4, imaginea 0.7.4, 12.11.2026, agentul PERF): pe Octagon SF8008 driverul
# video HiSilicon scrie „kern.debug kernel: video pts” la fiecare citire a PTS-ului; verificarea buclei SoftCSA il
# citeste la 0,5 s, deci 2 randuri pe secunda in /home/root/logs/messages, pe memoria interna (masurat pe .114: 83% din
# randuri, ~10 MB pe zi scrisi degeaba pe eMMC, iar cele 600 de randuri puse in raportul unei caderi acopereau numai
# ~5 minute). LOGLEVEL=7 in /etc/syslog-startup.conf da syslogd -l 7: se scrie tot ce e mai urgent decat debug. In
# jurnalele de pe .114 (SF8008) si .122 (Viper 4K V20) singurele randuri debug erau „video pts” si cateva randuri yaffs
# de la pornire. Urma PTS pentru masurarea inghetarilor se ia la cerere din inelul nucleului (dmesg), de pe PC:
# hdsatelit-unelte unelte/stb/urma_pts_receptor.py. Valoarea noua intra la urmatoarea pornire a lui syslogd; ca la
# rotirea de mai sus (acelasi conffile), sigur ajunge cu o imagine noua.
PR:append = ".hds4"

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SRC_URI += "file://hds-udhcpc-50default file://hds-crond.cfg file://hds-crond"

PACKAGES =+ "${PN}-cron"
FILES:${PN}-cron = "${sysconfdir}/init.d/crond ${sysconfdir}/cron"
RDEPENDS:${PN}-cron = "${PN}"
RDEPENDS:${PN} += "${PN}-cron"
INITSCRIPT_PACKAGES += "${PN}-cron"
INITSCRIPT_NAME:${PN}-cron = "crond"
INITSCRIPT_PARAMS:${PN}-cron = "defaults 90 60"

# un singur dosar de sarcini (/etc/cron/crontabs); /var/spool/cron si /etc/crontabs trimit la el. Ruleaza si la
# facerea imaginii ($D) si pe receptor, la instalare sau actualizare; nu atinge o cale care exista deja altfel.
# Numai comenzi pe care receptorul le are (busybox): fara install (nu exista pe receptor), fara stat.
pkg_postinst:${PN}-cron () {
mkdir -p $D${sysconfdir}/cron/crontabs
chmod 0700 $D${sysconfdir}/cron/crontabs
if [ ! -e $D${localstatedir}/spool/cron ] && [ ! -L $D${localstatedir}/spool/cron ]; then
	mkdir -p $D${localstatedir}/spool
	ln -s ${sysconfdir}/cron $D${localstatedir}/spool/cron
fi
v=$D${sysconfdir}/crontabs
if [ -d "$v" ] && [ ! -L "$v" ]; then
	for f in "$v"/*; do
		[ -f "$f" ] || continue
		n=$D${sysconfdir}/cron/crontabs/${f##*/}
		if [ -e "$n" ]; then
			while IFS= read -r r || [ -n "$r" ]; do
				grep -qxF -- "$r" "$n" || printf '%s\n' "$r" >> "$n"
			done < "$f"
			rm -f "$f"
		else
			mv "$f" "$n"
		fi
	done
	rmdir "$v" 2>/dev/null || true
fi
if [ ! -e "$v" ] && [ ! -L "$v" ]; then
	ln -s cron/crontabs "$v"
fi
}

do_install:append() {
    install -d ${D}${sysconfdir}/udhcpc.d
    install -m 0755 ${UNPACKDIR}/hds-udhcpc-50default ${D}${sysconfdir}/udhcpc.d/50default
    f=${D}${sysconfdir}/udhcpc.d/50default
    if grep -q "$(printf '\r')" "$f"; then
        bbfatal "busybox: 50default are sfarsit de rand CRLF"
    fi
    grep -q 'ip route del default dev "$interface"' "$f" || bbfatal "busybox: 50default sterge alte rute decat ale placii"
    grep -q 'dev "$interface" metric' "$f" || bbfatal "busybox: 50default pune ruta implicita fara dev"
    # jurnalul sistemului (0.5.0): rotirea la 1024 KB, 4 fisiere vechi; fisierul trebuie sa fie cel stiut (jurnalul in
    # /home/root/logs/messages, 256 x 1), altfel constructia se opreste in loc sa scrie peste altceva
    c=${D}${sysconfdir}/syslog-startup.conf
    [ -f "$c" ] || bbfatal "busybox: lipseste /etc/syslog-startup.conf (busybox-syslog)"
    grep -q '^LOGFILE=/home/root/logs/messages[[:space:]]' "$c" || bbfatal "busybox: syslog-startup.conf nu scrie in /home/root/logs/messages"
    grep -q '^ROTATESIZE=256[[:space:]]' "$c" || bbfatal "busybox: syslog-startup.conf fara ROTATESIZE=256 (s-a schimbat fisierul stratului comun)"
    grep -q '^ROTATEGENS=1[[:space:]]' "$c" || bbfatal "busybox: syslog-startup.conf fara ROTATEGENS=1 (s-a schimbat fisierul stratului comun)"
    sed -i -e 's/^ROTATESIZE=256\([[:space:]]\)/ROTATESIZE=1024\1/' -e 's/^ROTATEGENS=1\([[:space:]]\)/ROTATEGENS=4\1/' "$c"
    [ "$(grep -c '^ROTATESIZE=1024[[:space:]]' "$c")" = 1 ] || bbfatal "busybox: ROTATESIZE=1024 nu e pus o singura data"
    [ "$(grep -c '^ROTATEGENS=4[[:space:]]' "$c")" = 1 ] || bbfatal "busybox: ROTATEGENS=4 nu e pus o singura data"
    grep -q '^ROTATE\(SIZE\|GENS\)=\(256\|1\)[[:space:]]' "$c" && bbfatal "busybox: a ramas o valoare veche de rotire"
    # 0.7.4: fara nivelul debug in jurnalul de pe memoria interna (randul comentat al stratului comun devine LOGLEVEL=7)
    grep -q '^LOGLEVEL=' "$c" && bbfatal "busybox: syslog-startup.conf are deja LOGLEVEL (s-a schimbat fisierul stratului comun)"
    grep -q '^#LOGLEVEL=5[[:space:]]' "$c" || bbfatal "busybox: syslog-startup.conf fara randul #LOGLEVEL=5 (s-a schimbat fisierul stratului comun)"
    sed -i -e 's/^#LOGLEVEL=5\([[:space:]]\)/LOGLEVEL=7\1/' "$c"
    [ "$(grep -c '^LOGLEVEL=7[[:space:]]' "$c")" = 1 ] || bbfatal "busybox: LOGLEVEL=7 nu e pus o singura data"
    # crond (0.7.4): applet-urile in binar, cu dosarul stiut, si scriptul nostru in locul celui din stratul comun
    grep -q '^CONFIG_CROND=y$' ${B}/.config || bbfatal "busybox: CONFIG_CROND nu e pus (hds-crond.cfg)"
    grep -q '^CONFIG_CRONTAB=y$' ${B}/.config || bbfatal "busybox: CONFIG_CRONTAB nu e pus (hds-crond.cfg)"
    grep -q '^CONFIG_FEATURE_CROND_DIR="/var/spool/cron"$' ${B}/.config || bbfatal "busybox: dosarul crond nu e /var/spool/cron"
    cat ${D}${sysconfdir}/busybox.links* | grep -qx '/usr/sbin/crond' || bbfatal "busybox: crond lipseste din busybox.links"
    cat ${D}${sysconfdir}/busybox.links* | grep -qx '/usr/bin/crontab' || bbfatal "busybox: crontab lipseste din busybox.links"
    rm -f ${D}${sysconfdir}/init.d/busybox-cron
    install -m 0755 ${UNPACKDIR}/hds-crond ${D}${sysconfdir}/init.d/crond
    if grep -q "$(printf '\r')" ${D}${sysconfdir}/init.d/crond; then
        bbfatal "busybox: /etc/init.d/crond are sfarsit de rand CRLF"
    fi
    grep -q 'are_sarcini || return 0\|if ! are_sarcini' ${D}${sysconfdir}/init.d/crond || bbfatal "busybox: /etc/init.d/crond porneste fara sa caute sarcini"
    install -d -m 0700 ${D}${sysconfdir}/cron/crontabs
    true
}
