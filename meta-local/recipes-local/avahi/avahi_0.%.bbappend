# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# avahi 0.8 (avahi-daemon raspunde pe reteaua locala, pentru numele hdsatelit.local) cu reparatiile din amonte pentru
# trei opriri ale serviciului provocate din retea. avahi 0.9 nu e lansat inca (numai etichete -rc), deci peticele
# celor trei comiteri din ramura master se pun pe 0.8, dupa cele 14 petice ale retetei din openembedded-core:
# - CVE-2025-68471 (assert in lookup_start): 9c6eb53bf2e290aed84b1f207e3ce35c54cc0aa1;
# - CVE-2026-24401 (recursie fara capat in lookup_handle_cname): 78eab31128479f06e30beb8c1cbf99dd921e2524;
# - CVE-2025-68468 (assert gresit in lookup_multicast_callback): f66be13d7f31a3ef806d226bf8b67240179d309a.
# Toate ating numai avahi-core/browse.c; sunt puse in ordinea din amonte. Fisierele din files/ sunt peticele luate de
# la github.com/avahi/avahi/commit/<sha>.patch, cu antetul autorului pastrat si cu Upstream-Status si CVE adaugate.
# bbappend-ul meta-oe-alliance avahi_0.%.bbappend se aplica si el, neschimbat. PR:append schimba versiunea
# pachetelor (aceeasi versiune 0.8, alt continut), ca opkg sa le ia din feed.
PR:append = ".hds2"

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SRC_URI += " \
    file://CVE-2025-68471.patch \
    file://CVE-2026-24401.patch \
    file://CVE-2025-68468.patch \
"

# Configurarea stransa: avahi ramane numai pentru numele hdsatelit.local si anunturile din
# reteaua de acasa. Fata de avahi-daemon.conf din pachet:
# - raspunde numai pe interfetele retelei de acasa (cablu si Wi-Fi), deci nu si pe tun0/wg0 ale VPN-ului;
# - nicio alta stiva mDNS pe acelasi port;
# - fara partea wide-area (DNS unicast spre servere din afara; avizele ramase in 0.8 pentru ea nu mai au pe unde intra);
# - limitele de resurse ale procesului (valorile date ca exemplu in fisierul din amonte), ca o greseala in cod sa nu
#   poata lua memoria sau procesele receptorului.
# Restul (publicarea numelui, avahi-publish din hds-nume-local, anunturile serviciilor) ramane neschimbat.
do_install:append() {
    f=${D}${sysconfdir}/avahi/avahi-daemon.conf
    sed -i \
        -e 's/^#\?allow-interfaces=.*/allow-interfaces=eth0,eth1,wlan0,wlan1/' \
        -e 's/^#\?disallow-other-stacks=.*/disallow-other-stacks=yes/' \
        -e 's/^#\?enable-wide-area=.*/enable-wide-area=no/' \
        -e 's/^#\?rlimit-core=.*/rlimit-core=0/' \
        -e 's/^#\?rlimit-data=.*/rlimit-data=8388608/' \
        -e 's/^#\?rlimit-fsize=.*/rlimit-fsize=0/' \
        -e 's/^#\?rlimit-nofile=.*/rlimit-nofile=768/' \
        -e 's/^#\?rlimit-stack=.*/rlimit-stack=8388608/' \
        -e 's/^#\?rlimit-nproc=.*/rlimit-nproc=3/' \
        "$f"
    for r in 'allow-interfaces=eth0,eth1,wlan0,wlan1' 'disallow-other-stacks=yes' 'enable-wide-area=no' \
             'rlimit-core=0' 'rlimit-nofile=768' 'rlimit-nproc=3'; do
        grep -qx "$r" "$f" || bbfatal "avahi-daemon.conf: lipseste randul $r (fisierul din amonte s-a schimbat?)"
    done
}
