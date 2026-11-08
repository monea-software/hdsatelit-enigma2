# Copyright (C) 2026 moneasoftware.com si hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
# Discul optional nu tine montarea sistemului si pornirea interfetei.
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
HDS_MONTARI_FUNDAL = "0"
HDS_MONTARI_FUNDAL:vuduo4k = "1"
HDS_MONTARI_FUNDAL:vuuno4kse = "1"
HDS_MONTARI_FUNDAL:vusolo4k = "1"
HDS_MONTARI_FUNDAL:gbtrio4k = "1"
SRC_URI:append = " ${@'file://hds-mountall' if d.getVar('HDS_MONTARI_FUNDAL') == '1' else ''}"
PR:append = "${@'.hds35' if d.getVar('HDS_MONTARI_FUNDAL') == '1' else ''}"
PACKAGE_ARCH:vuduo4k = "${MACHINE_ARCH}"
PACKAGE_ARCH:vuuno4kse = "${MACHINE_ARCH}"
PACKAGE_ARCH:vusolo4k = "${MACHINE_ARCH}"
PACKAGE_ARCH:gbtrio4k = "${MACHINE_ARCH}"

do_install:append() {
    if [ "${HDS_MONTARI_FUNDAL}" = 1 ]; then
        install -d ${D}${base_sbindir}
        install -m 0755 ${UNPACKDIR}/hds-mountall ${D}${base_sbindir}/hds-mountall
        sh -n ${D}${base_sbindir}/hds-mountall || bbfatal "montari: sintaxa sh gresita"
    fi
}

python hds_mountall_fara_asteptare() {
    if d.getVar('HDS_MONTARI_FUNDAL') != '1':
        return
    import pathlib
    cale = pathlib.Path(d.getVar('D') + d.getVar('sysconfdir') + '/init.d/mountall.sh')
    text = cale.read_text()
    linii = text.splitlines(keepends=True)
    gasite = [i for i, linie in enumerate(linii)
              if linie.startswith('mount -a ') and '-O no_netdev' in linie]
    if len(gasite) != 1:
        bb.fatal('montari: mountall s-a schimbat; trebuie verificat din nou')
    linii[gasite[0]] = d.getVar('base_sbindir') + '/hds-mountall\n'
    text = ''.join(linii)
    swap = '[ -x /sbin/swapon ] && swapon -a'
    if text.count(swap) != 1:
        bb.fatal('montari: apelul swapon din mountall s-a schimbat')
    text = text.replace(swap, '# Swap este pornit in fundal de hds-mountall.')
    cale.write_text(text)
    cale = pathlib.Path(d.getVar('D') + d.getVar('sysconfdir') + '/init.d/checkroot.sh')
    text = cale.read_text()
    if text.count(swap) != 1:
        bb.fatal('montari: apelul swapon din checkroot s-a schimbat')
    text = text.replace(swap, '# Swap este pornit in fundal de hds-mountall.')
    cale.write_text(text)
}
do_install[postfuncs] += " hds_mountall_fara_asteptare"
FILES:${PN}:append = " ${@d.getVar('base_sbindir') + '/hds-mountall' if d.getVar('HDS_MONTARI_FUNDAL') == '1' else ''}"
