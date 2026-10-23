# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# ntfs-3g pentru discurile NTFS, in locul modulului comercial tntfs (scos in dinobot-dvb-modules-u57.bbappend, care
# cere si pachetul ntfs-3g). Din pachete intra numai ntfs-3g si libntfs-3g, nu ntfsprogs (mkntfs, ntfsfix...).
#
# 1. mount.ntfs-3g: reteta il face legatura spre ntfs-3g; aici e scriptul files/mount.ntfs-3g, care cheama ntfs-3g cu
#    big_writes si noatime. Fara big_writes, FUSE pe nucleul 4.4 trimite scrierile in bucati de 4 KB (nucleele de la
#    4.20 incolo il ignora); ntfs-3g il aplica numai pe volume de cel putin 4 GiB (SAFE_CAPACITY_FOR_BIG_WRITES).
#    mount.ntfs (legatura din reteta) duce tot la script.
# 2. /usr/bin/mount.ntfs-3g -> /sbin/mount.ntfs-3g: eudev porneste programele RUN numai cu proprietatile
#    dispozitivului ca mediu, fara PATH (udev-event.c, udev_device_get_properties_envp), ash nu exporta PATH-ul lui
#    implicit, iar busybox cauta ajutorul cu execvp, deci in calea implicita a glibc (/bin:/usr/bin), nu in /sbin.
#    Fara legatura, montarea automata din /etc/udev/scripts/mount.sh nu ar gasi ajutorul.
# 3. Fara util-linux-mount (RRECOMMENDS in reteta): ar lua locul lui /bin/mount (busybox) prin update-alternatives si
#    ar schimba toate montarile imaginii; busybox cheama singur ajutoarele mount.<tip>.
# 4. Fara pachetul fuse (RDEPENDS in reteta): ntfs-3g se construieste cu FUSE-ul lui intern (fuse-lite, implicit in
#    configure), deci nu incarca libfuse (NEEDED verificat cu readelf pe pachetul construit); fuse ar aduce si
#    fusermount (setuid) prin RRECOMMENDS.
# Constructia se opreste cu eroare daca reteta nu mai face mount.ntfs-3g ca legatura sau daca lipseste ntfs-3g.

PR:append = ".hds1"

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI += "file://mount.ntfs-3g"

FILES:ntfs-3g += "${bindir}/mount.ntfs-3g"
RDEPENDS:ntfs-3g:remove = "fuse"
RRECOMMENDS:ntfs-3g:remove = "util-linux-mount"

do_install:append() {
	[ -L "${D}${base_sbindir}/mount.ntfs-3g" ] || bbfatal "mount.ntfs-3g nu mai e legatura in reteta; de citit din nou"
	[ -f "${D}${bindir}/ntfs-3g" ] || bbfatal "lipseste ${bindir}/ntfs-3g"
	rm -f "${D}${base_sbindir}/mount.ntfs-3g"
	sed -e 's#@BINDIR@#${bindir}#g' "${UNPACKDIR}/mount.ntfs-3g" > "${D}${base_sbindir}/mount.ntfs-3g"
	chmod 0755 "${D}${base_sbindir}/mount.ntfs-3g"
	! grep -q '@BINDIR@' "${D}${base_sbindir}/mount.ntfs-3g" || bbfatal "mount.ntfs-3g: @BINDIR@ neinlocuit"
	ln -rsf "${D}${base_sbindir}/mount.ntfs-3g" "${D}${bindir}/mount.ntfs-3g"
}
