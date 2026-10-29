# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Driverele u571 (Amiko Viper 4K V40) fara modulul NTFS comercial: aceeasi schimbare ca dinobot-dvb-modules-u57.bbappend
# (acolo e explicatia intreaga: tntfs.ko e license=Commercial si nu se poate redistribui; discurile NTFS le monteaza
# ntfs-3g prin FUSE, de aceea pachetul cere ntfs-3g).
#
# Arhiva u571-drivers-4.4.35-20210727 (sha256 484770c7, lotul imagine-060-v40, drivere-v20-v40.md) are tntfs.ko si
# scriptul `load` IDENTICE, octet cu octet, cu cele din arhiva u57 (u57-drivers-4.4.35-20211209), deci pazele de mai jos
# trec la fel. Corpul lui do_install:append e acelasi cu cel din dinobot-dvb-modules-u57.bbappend, in afara numelui
# pachetului din mesaje (${PN}); pregateste-meta-local-060.sh opreste stratul daca cele doua se despart.
# Constructia se opreste cu eroare, nu trece tacut, daca tntfs.ko nu mai e in arhiva (alta arhiva: de citit din nou
# inainte de a schimba ceva), daca `load` nu are exact un rand `insmod tntfs.ko`, sau daca dupa schimbare mai ramane
# tntfs in dosarul modulelor ori in `load`.
# PR cu ".hds1", ca pachetul schimbat sa se vada in manifest si in "opkg list-installed".

PR:append = ".hds1"

RDEPENDS:${PN} += "ntfs-3g"

do_install:append() {
	extra="${D}${nonarch_base_libdir}/modules/${KV}/extra"
	[ -f "$extra/tntfs.ko" ] || bbfatal "tntfs.ko nu mai e in arhiva driverelor ${PN}; arhiva s-a schimbat, de citit din nou"
	[ "$(grep -c -x 'insmod tntfs\.ko' "$extra/load")" = "1" ] || bbfatal "load din ${PN} nu are exact un rand 'insmod tntfs.ko'"
	rm -f "$extra/tntfs.ko"
	sed -i -e '/^insmod tntfs\.ko$/d' "$extra/load"
	[ ! -e "$extra/tntfs.ko" ] || bbfatal "tntfs.ko a ramas in pachetul ${PN}"
	! grep -q tntfs "$extra/load" || bbfatal "load din ${PN} pomeneste inca tntfs"
}
