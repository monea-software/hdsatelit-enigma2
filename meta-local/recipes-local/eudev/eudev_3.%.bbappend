# Copyright (C) 2026 moneasoftware.com si hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
# Se trimit toate evenimentele. Discurile lente nu tin prima pornire.
HDS_UDEV_FUNDAL = "0"
HDS_UDEV_FUNDAL:vuduo4k = "1"
HDS_UDEV_FUNDAL:vuuno4kse = "1"
HDS_UDEV_FUNDAL:vusolo4k = "1"
HDS_UDEV_FUNDAL:gbtrio4k = "1"
PR:append = "${@'.hds35' if d.getVar('HDS_UDEV_FUNDAL') == '1' else ''}"
PACKAGE_ARCH:vuduo4k = "${MACHINE_ARCH}"
PACKAGE_ARCH:vuuno4kse = "${MACHINE_ARCH}"
PACKAGE_ARCH:vusolo4k = "${MACHINE_ARCH}"
PACKAGE_ARCH:gbtrio4k = "${MACHINE_ARCH}"

python hds_udev_fara_asteptare() {
    if d.getVar('HDS_UDEV_FUNDAL') != '1':
        return
    import pathlib
    cale = pathlib.Path(d.getVar('D') + d.getVar('sysconfdir') + '/init.d/udev')
    text = cale.read_text()
    inceput = '            udevadm settle\n'
    sfarsit = '            fi\n    fi\n    ;;'
    if text.count(inceput) != 1 or text.count(sfarsit) != 1:
        bb.fatal('udev: scriptul s-a schimbat; trebuie verificat din nou')
    text = text.replace(inceput, '            (\n            udevadm settle --timeout=3\n')
    text = text.replace(sfarsit, '            fi\n'
                        '            ) < /dev/null > /dev/null 2>&1 &\n    fi\n    ;;')
    cale.write_text(text)
}
do_install[postfuncs] += " hds_udev_fara_asteptare"
