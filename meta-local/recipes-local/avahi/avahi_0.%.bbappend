# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# NUMAI pentru stratul OE-Alliance 6.0 (pregateste-strat-60.sh il pune peste meta-local/recipes-local/avahi): in 6.0
# reteta din openembedded-core e avahi 0.9~rc5 (eticheta v0.9-rc5, 71b640e6), care contine deja cele trei comiteri
# din amonte puse pe 0.8 de bbappend-ul lui 5.6 (CVE-2025-68471 9c6eb53b, CVE-2026-24401 78eab311, CVE-2025-68468
# f66be13d: toate stramosi ai lui v0.9-rc5, verificat cu git merge-base pe clona din DL_DIR). Peticele nu se mai pun
# (al treilea nu se mai aplica, iar primele doua ar fi intrat a doua oara); raman setarile de securitate ale lui
# avahi-daemon.conf, cu aceleasi opriri. PR:append ca la 5.6.
PR:append = ".hds2"

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
