# Varianta intreaga pentru stick (HDS_VARIANTA = usb), fara reducerea hdsflashmic.
# Tar-ul standard aduce singur dependinta bzip2-native. Ambalarea foloseste
# zipfile din Python-ul de constructie, fara zip-native.
#
# Vu+ Solo SE (chkroot), forma arhivei (08.11.2026): un singur dosar-frunza smallbox/vusolose/ cu
# kernel_cfe_auto.bin (nucleul acestei constructii, gzip ca la NAND) si
# rootfs.tar.bz2, iar imageversion in radacina zipului. Managerul de imagini
# recunoaste o arhiva numai cu cel putin doua fisiere cunoscute in acelasi
# dosar-frunza (imageversion nu se numara), altfel nici nu o listeaza. Fara
# rootfs.ubi langa tar (managerul ar sterge tar-ul). In modul chkroot se scrie
# numai sistemul: nucleul sta in arhiva doar ca ea sa fie recunoscuta.
#
# USB1 (27.11.2026; Eduard 17:37 si 17:41): ZGEMMA H8.2H Plus (h8) si H8.2H SE (h8se). Nucleul din mtd8 (al OE-Alliance,
# linux-airdigital 4.4.176 / 4.4.35) are un initramfs care, la fiecare pornire, cauta un stick cu partitia 1 FAT si
# partitia 2 ext4 cu eticheta "rootfs", citeste STARTUP de pe partitia 1 (root=, rootsubdir=, rootfstype=) si porneste
# radacina din <partitia 2>/<rootsubdir>; fara stick, fara STARTUP sau cu un subdosar fara sistem porneste memoria
# interna. Nimic nu se scrie pe partitiile de pornire: nucleul ramane cel din mtd8, iar initramfs-ul copiaza in imaginea
# de pe stick modulele lui la prima pornire (/etc/.guest). Arhiva: dosarul <masina>/ cu rootfs.tar.bz2, uImage (nucleul
# acestei constructii, numai pentru recunoastere, NU se scrie), STARTUP_1 si STARTUP_FLASH (sabloanele), imageversion in
# radacina zipului. Pe stick: tools/zgemma-h8-stick/pregateste-stick-h8.sh din depozitul uneltelor (runda-0013/USB1).
HDS_USB_MASINI = "vusolose h8 h8se"
IMAGE_FSTYPES:hdsusb = "tar.bz2"
IMAGE_ROOTFS_MAXSIZE:hdsusb = ""
IMAGE_POSTPROCESS_COMMAND:append:hdsusb = " hds_usb_transport "
ROOTFS_POSTPROCESS_COMMAND:append:hdsusb = " hds_usb_marcaj_rootfs "

python () {
    varianta = d.getVar('HDS_VARIANTA') or 'nand'
    if varianta not in ('nand', 'usb'):
        bb.fatal('HDS_VARIANTA poate fi numai nand sau usb')
    if varianta == 'usb' and d.getVar('MACHINE') not in (d.getVar('HDS_USB_MASINI') or '').split():
        bb.fatal('HDS_VARIANTA=usb este pregatita numai pentru %s' % d.getVar('HDS_USB_MASINI'))
    if varianta == 'usb':
        # nucleul (vmlinux-<masina>.bin, uImage) trebuie sa fie in DEPLOY_DIR_IMAGE inainte de ambalare
        d.appendVarFlag('do_image_complete', 'depends', ' virtual/kernel:do_deploy')
}

hds_usb_marcaj_rootfs() {
	f="${IMAGE_ROOTFS}${sysconfdir}/hdsatelit-model"
	[ -s "$f" ] || bbfatal "USB: lipseste marcajul modelului"
	printf '%s\n' 'varianta=usb' >> "$f"
	case "${MACHINE}" in
	h8|h8se)
		# radacina o monteaza initramfs-ul nucleului (ext4 de pe stick): fstab nu mai spune ubifs
		sed -i 's#^rootfs\([[:space:]]\+\)/\([[:space:]]\+\)ubifs\([[:space:]]\+\)[^[:space:]]\+#rootfs\1/\2auto\3defaults,noatime#' "${IMAGE_ROOTFS}${sysconfdir}/fstab"
		grep -Eq '^rootfs[[:space:]]+/[[:space:]]+auto[[:space:]]' "${IMAGE_ROOTFS}${sysconfdir}/fstab" || bbfatal "USB H8: randul radacinii din fstab nu s-a schimbat"
		# pachetul nucleului are pkg_postinst care sterge si rescrie mtd8; de pe stick o actualizare opkg l-ar scrie in memoria
		# interna. Il tinem pe loc (hold): nucleul se schimba numai din imaginea din memoria interna.
		st="${IMAGE_ROOTFS}/var/lib/opkg/status"
		[ -s "$st" ] || bbfatal "USB H8: lipseste starea opkg"
		awk 'BEGIN{p=""} /^Package:/{p=$2} /^Status:/{ if (p ~ /^kernel-image/) sub(/^Status: install ok /, "Status: install hold ") } {print}' "$st" > "$st.hds" && mv "$st.hds" "$st"
		! grep -A3 -E '^Package: kernel-image' "$st" | grep -q '^Status: install ok ' || bbfatal "USB H8: pachetul nucleului nu e tinut pe loc"
		;;
	esac
}

python hds_usb_transport() {
    import gzip
    import os
    import zipfile

    masina = d.getVar('MACHINE')
    mb = d.getVar('MACHINEBUILD')
    perechi = {'vusolose': 'vusolose', 'h8': 'zgemmah82hplus', 'h8se': 'zgemmah8se'}
    if d.getVar('HDS_VARIANTA') != 'usb' or perechi.get(masina) != mb:
        bb.fatal('Transportul USB este pregatit numai pentru vusolose, zgemmah82hplus (h8) si zgemmah8se (h8se)')
    deploy = d.getVar('IMGDEPLOYDIR')
    nume = d.getVar('IMAGE_NAME')
    asteptat = '%s-%s-%s-%s' % (d.getVar('DISTRO_NAME'), d.getVar('DISTRO_VERSION'), mb, d.getVar('DATE'))
    if nume != asteptat:
        bb.fatal('USB: numele imaginii nu respecta distro-versiune-model-data')
    # OE 6.0 foloseste IMAGE_NAME.tar.bz2. Acceptam si sufixul .rootfs
    # al altor versiuni OE, dar nu alegem in tacere intre doua arhive.
    candidati = [os.path.join(deploy, nume + sufix)
                 for sufix in ('.tar.bz2', '.rootfs.tar.bz2')]
    candidati = [cale for cale in candidati if os.path.isfile(cale)]
    if len(candidati) != 1:
        bb.fatal('USB: trebuie exact un tar.bz2 al imaginii curente')
    # Metadatele transportului sunt distincte de /etc/image-version.
    # Formatul propriu comun cu verificatorul de publicare HD Satelit.
    versiune = '%s-%s.%s\n' % (d.getVar('DISTRO_NAME'),
                               d.getVar('DISTRO_VERSION'), d.getVar('DATE'))
    iesire = os.path.join(deploy, nume + '_multiboot.zip')
    temporar = iesire + '.partial'
    if masina == 'vusolose':
        # Nucleul din aceeasi constructie, comprimat ca kernel_cfe_auto.bin din arhiva NAND.
        vmlinux = os.path.join(d.getVar('DEPLOY_DIR_IMAGE'), 'vmlinux-%s.bin' % masina)
        if not os.path.isfile(vmlinux):
            bb.fatal('USB: lipseste nucleul %s' % vmlinux)
        with open(vmlinux, 'rb') as f:
            nucleu = gzip.compress(f.read(), compresslevel=9, mtime=0)
        fisiere = [('smallbox/vusolose/kernel_cfe_auto.bin', nucleu)]
        tar = 'smallbox/vusolose/rootfs.tar.bz2'
    else:
        uimage = os.path.join(d.getVar('DEPLOY_DIR_IMAGE'), 'uImage')
        if not os.path.isfile(uimage):
            bb.fatal('USB: lipseste nucleul %s' % uimage)
        with open(uimage, 'rb') as f:
            nucleu = f.read()
        if nucleu[:4] != b'\x27\x05\x19\x56' or len(nucleu) > 12582912:
            bb.fatal('USB H8: uImage fara antet sau peste 12 MiB')
        mtd = d.getVar('MTD_KERNEL') or 'mtd8'
        fisiere = [
            ('%s/uImage' % masina, nucleu),
            # sabloanele OE-Alliance (MultiBootManager, UBISlotManager); pe receptor pregateste-stick-h8.sh pune
            # root=UUID=<uuid-ul partitiei 2>; LABEL=rootfs merge si el (busybox-ul initramfs-ului, probat pe .129)
            ('%s/STARTUP_1' % masina, 'kernel=/dev/%s root=LABEL=rootfs rootsubdir=linuxrootfs1 rootfstype=ext4\n' % mtd),
            ('%s/STARTUP_FLASH' % masina, 'kernel=/dev/%s ubi.mtd=rootfs root=ubi0:rootfs flash=1 rootfstype=ubifs\n' % mtd),
        ]
        tar = '%s/rootfs.tar.bz2' % masina
    try:
        with zipfile.ZipFile(temporar, 'w', compression=zipfile.ZIP_STORED) as arhiva:
            arhiva.writestr('imageversion', versiune)
            for cale, date in fisiere:
                arhiva.writestr(cale, date)
            arhiva.write(candidati[0], tar)
        os.replace(temporar, iesire)
    finally:
        if os.path.exists(temporar):
            os.unlink(temporar)
}
