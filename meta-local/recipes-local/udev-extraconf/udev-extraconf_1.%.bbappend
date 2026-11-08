# Copyright (C) 2026 moneasoftware.com si hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
HDS_MEDIA_FUNDAL = "0"
HDS_MEDIA_FUNDAL:vuduo4k = "1"
HDS_MEDIA_FUNDAL:vuuno4kse = "1"
HDS_MEDIA_FUNDAL:vusolo4k = "1"
HDS_MEDIA_FUNDAL:gbtrio4k = "1"
SRC_URI:append = " ${@'file://hds-mount-udev' if d.getVar('HDS_MEDIA_FUNDAL') == '1' else ''}"
PR:append = "${@'.hds35' if d.getVar('HDS_MEDIA_FUNDAL') == '1' else ''}"
PACKAGE_ARCH:vuduo4k = "${MACHINE_ARCH}"
PACKAGE_ARCH:vuuno4kse = "${MACHINE_ARCH}"
PACKAGE_ARCH:vusolo4k = "${MACHINE_ARCH}"
PACKAGE_ARCH:gbtrio4k = "${MACHINE_ARCH}"

do_install:append() {
    if [ "${HDS_MEDIA_FUNDAL}" = 1 ]; then
        test -f ${D}${sysconfdir}/udev/scripts/mount.sh || bbfatal "media: lipseste mount.sh"
        mv ${D}${sysconfdir}/udev/scripts/mount.sh ${D}${sysconfdir}/udev/scripts/mount-sistem.sh
        install -m 0755 ${UNPACKDIR}/hds-mount-udev ${D}${sysconfdir}/udev/scripts/mount.sh
        sh -n ${D}${sysconfdir}/udev/scripts/mount.sh || bbfatal "media: sintaxa sh gresita"
    fi
}
FILES:${PN}-automount:append = " ${@d.getVar('sysconfdir') + '/udev/scripts/mount-sistem.sh' if d.getVar('HDS_MEDIA_FUNDAL') == '1' else ''}"
