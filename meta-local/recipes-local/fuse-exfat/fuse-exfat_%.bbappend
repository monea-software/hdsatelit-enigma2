# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# exFAT pe stick-uri si discuri, prin FUSE (nucleul receptorului nu are driver exFAT); exfatprogs da mkfs.exfat si
# fsck.exfat.
# 1. Montarea automata (/etc/udev/scripts/mount.sh) cheama busybox mount -t auto, care incearca tipurile din
#    /etc/filesystems (acolo e deja exfat-fuse) si apoi ajutorul mount.exfat-fuse cu execvp, in calea implicita a glibc
#    (/bin:/usr/bin): eudev nu da PATH programelor RUN. Reteta il pune in /sbin, deci aici se adauga legatura
#    /usr/bin/mount.exfat-fuse, ca la mount.ntfs-3g.
# 2. Fara util-linux-mount (RRECOMMENDS in reteta): ar lua locul lui /bin/mount (busybox) prin update-alternatives si
#    ar schimba toate montarile imaginii.
# Constructia se opreste daca reteta nu mai pune mount.exfat-fuse in /sbin.

PR:append = ".hds1"

RRECOMMENDS:${PN}:remove = "util-linux-mount"
FILES:${PN} += "${bindir}/mount.exfat-fuse"

do_install:append() {
	[ -x "${D}${base_sbindir}/mount.exfat-fuse" ] || bbfatal "fuse-exfat: lipseste ${base_sbindir}/mount.exfat-fuse"
	install -d ${D}${bindir}
	ln -rsf "${D}${base_sbindir}/mount.exfat-fuse" "${D}${bindir}/mount.exfat-fuse"
}
