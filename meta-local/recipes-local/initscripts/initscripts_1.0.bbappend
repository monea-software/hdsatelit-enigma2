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

# HDSatelit 0.7.4 (M2, 12.11.2026): umountfs (oprirea, rc0 si rc6, din OE-Alliance) citea locul montarii din /proc/mounts
# cu `read` fara -r si il dadea nedecodat lui umount. mount.sh pune eticheta stickului in loc (/run/media/<ETICHETA>-sdb1);
# o eticheta cu spatiu ("USB DISK") apare in /proc/mounts ca \040, umount nu gaseste locul si stickul ramane montat pentru
# scriere pana la oprire: la pornire FAT spune "Volume was not properly unmounted" (wlad-sat, stickul FAT32). Masurat pe
# .122 (FAT prin loop in /tmp, paralel-1111b/M2/proba_umountfs_spatiu.sh): inainte cod 1 si stickul ramas "rw"; cu
# read -r si printf %b: demontat, FAT curat. Pentru toate modelele.
PR:append = ".hdsu1"

python hds_umountfs_locuri_cu_spatiu() {
    import pathlib
    cale = pathlib.Path(d.getVar('D') + d.getVar('sysconfdir') + '/init.d/umountfs')
    text = cale.read_text()
    vechi = '\tif read dev mp type opts\n\tthen\n'
    if text.count(vechi) != 1 or text.count('umount -f -r "$mp"') != 1:
        bb.fatal('umountfs s-a schimbat; trebuie verificat din nou (locurile cu spatiu)')
    nou = ('\tif read -r dev mp type opts\n\tthen\n'
           '\t\t# HDSatelit: /proc/mounts scrie spatiul ca \\040 (eticheta stickului e in locul montarii)\n'
           '\t\tmp=$(printf \'%b\' "$mp")\n')
    cale.write_text(text.replace(vechi, nou))
}
do_install[postfuncs] += " hds_umountfs_locuri_cu_spatiu"
