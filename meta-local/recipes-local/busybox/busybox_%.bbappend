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
PR:append = ".hds2"

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SRC_URI += "file://hds-udhcpc-50default"

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
    true
}
