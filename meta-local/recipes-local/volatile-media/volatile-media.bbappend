# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# volatile-media (scriptul de pornire care pune un tmpfs peste /media) fara numele altei echipe in metadatele
# pachetului (regula: nimic din ce iese nu poarta numele altor imagini, interfete, pluginuri sau skinuri; notitele de
# licenta si de autor raman).
#
# MAINTAINER: reteta din care vine pachetul pune numele echipei ei in campul Maintainer (control in
# /var/lib/opkg/info, Packages din feed). Campul spune cine intretine pachetul in distributie; nu e o notita de
# copyright sau de licenta. Licenta ramane cea a retetei (GPL-2.0-or-later, license-gplv2.inc), cu textul ei in lista
# licentelor; scriptul volatile-media.sh nu are antet de autor. Valoarea e cea a distributiei (MAINTAINER din
# conf/distro/hdsatelit.conf), ca la toate retetele fara MAINTAINER propriu.
# PR ".hds1": alte metadate la aceeasi versiune, ca opkg sa ia pachetul din feed.
MAINTAINER = "Monea Software pentru HD Satelit"
PR:append = ".hds1"

# RUN1 (0.8.0, TODO 23.11 22:40, toate modelele): /run curat la fiecare pornire, ca in OE-core (fstab-ul lor are tmpfs pe /run;
# fstab-ul OE-Alliance nu, deci /run ramanea un dosar pe disc). De la o pornire la alta ramaneau pid-uri si socluri (dbus, avahi,
# udhcpc, ifstate, starea siglei timpurii); dupa o oprire brusca /run/dbus/pid gol oprea pornirea dbus, avahi cadea si
# hdsatelit.local nu raspundea ore intregi. Montarea sta aici, nu in fstab: fstab e fisier de configurare (opkg nu-l inlocuieste
# daca omul are discuri trecute in el), iar scriptul acesta ruleaza la S02, dupa sysfs.sh si inainte de mountall (S03), udev (S05)
# si orice alt script care scrie in /run. Teava lui sysvinit (/run/initctl) ramane sub montare: o facem din nou si init o
# redeschide la USR1, ca mountall.sh din OE-core; USR1 numai cand init e sysvinit (la init-ul din busybox USR1 inseamna oprire).
PR:append = ".hdsrun1"

python hds_run_tmpfs() {
    import pathlib
    import subprocess
    cale = pathlib.Path(d.getVar('D') + d.getVar('sysconfdir') + '/init.d/volatile-media.sh')
    text = cale.read_text()
    antet = '#!/bin/sh\n'
    if not text.startswith(antet) or text.count('mountpoint -q "/media"') != 1 or ' /run' in text:
        bb.fatal('volatile-media.sh s-a schimbat; trebuie vazut din nou (RUN1, tmpfs pe /run)')
    bloc = '\n'.join([
        '',
        '# HDSatelit: /run curat la fiecare pornire (tmpfs, ca in OE-core); pid-urile si soclurile vechi pacaleau scripturile de pornire.',
        'if ! mountpoint -q /run && mount -t tmpfs -o mode=0755,nodev,nosuid,strictatime tmpfs /run; then',
        '\t# teava lui sysvinit a ramas sub montare: o facem din nou, iar init o redeschide la USR1 (numai sysvinit)',
        '\tif [ "$(readlink -f /sbin/init)" = /sbin/init.sysvinit ]; then',
        '\t\tmknod -m 600 /run/initctl p 2>/dev/null',
        '\t\tkill -USR1 1 2>/dev/null',
        '\tfi',
        'fi',
        ''])
    cale.write_text(antet + bloc + text[len(antet):])
    if subprocess.run(['sh', '-n', str(cale)]).returncode != 0:
        bb.fatal('volatile-media.sh nu e sh valid dupa RUN1')
}
do_install[postfuncs] += "hds_run_tmpfs"
