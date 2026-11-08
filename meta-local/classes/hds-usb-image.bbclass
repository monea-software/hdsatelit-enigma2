# Varianta intreaga pentru chkroot. Numai vusolose, fara reducerea hdsflashmic.
# Tar-ul standard aduce singur dependinta bzip2-native. Ambalarea foloseste
# zipfile din Python-ul de constructie, fara zip-native.
# Forma arhivei (08.11.2026): un singur dosar-frunza smallbox/vusolose/ cu
# kernel_cfe_auto.bin (nucleul acestei constructii, gzip ca la NAND) si
# rootfs.tar.bz2, iar imageversion in radacina zipului. Managerul de imagini
# recunoaste o arhiva numai cu cel putin doua fisiere cunoscute in acelasi
# dosar-frunza (imageversion nu se numara), altfel nici nu o listeaza. Fara
# rootfs.ubi langa tar (managerul ar sterge tar-ul). In modul chkroot se scrie
# numai sistemul: nucleul sta in arhiva doar ca ea sa fie recunoscuta.
IMAGE_FSTYPES:hdsusb = "tar.bz2"
IMAGE_ROOTFS_MAXSIZE:hdsusb = ""
IMAGE_POSTPROCESS_COMMAND:append:hdsusb = " hds_usb_transport "
ROOTFS_POSTPROCESS_COMMAND:append:hdsusb = " hds_usb_marcaj_rootfs "

python () {
    varianta = d.getVar('HDS_VARIANTA') or 'nand'
    if varianta not in ('nand', 'usb'):
        bb.fatal('HDS_VARIANTA poate fi numai nand sau usb')
    if varianta == 'usb' and d.getVar('MACHINE') != 'vusolose':
        bb.fatal('HDS_VARIANTA=usb este pregatita numai pentru vusolose')
    if varianta == 'usb':
        # nucleul (vmlinux-<masina>.bin) trebuie sa fie in DEPLOY_DIR_IMAGE inainte de ambalare
        d.appendVarFlag('do_image_complete', 'depends', ' virtual/kernel:do_deploy')
}

hds_usb_marcaj_rootfs() {
	f="${IMAGE_ROOTFS}${sysconfdir}/hdsatelit-model"
	[ -s "$f" ] || bbfatal "USB: lipseste marcajul modelului"
	printf '%s\n' 'varianta=usb' >> "$f"
}

python hds_usb_transport() {
    import gzip
    import os
    import zipfile

    if (d.getVar('HDS_VARIANTA') != 'usb'
            or d.getVar('MACHINE') != 'vusolose'
            or d.getVar('MACHINEBUILD') != 'vusolose'):
        bb.fatal('Transportul USB este pregatit numai pentru vusolose')
    deploy = d.getVar('IMGDEPLOYDIR')
    nume = d.getVar('IMAGE_NAME')
    asteptat = '%s-%s-vusolose-%s' % (d.getVar('DISTRO_NAME'),
                                     d.getVar('DISTRO_VERSION'), d.getVar('DATE'))
    if nume != asteptat:
        bb.fatal('USB: numele imaginii nu respecta distro-versiune-vusolose-data')
    # OE 6.0 foloseste IMAGE_NAME.tar.bz2. Acceptam si sufixul .rootfs
    # al altor versiuni OE, dar nu alegem in tacere intre doua arhive.
    candidati = [os.path.join(deploy, nume + sufix)
                 for sufix in ('.tar.bz2', '.rootfs.tar.bz2')]
    candidati = [cale for cale in candidati if os.path.isfile(cale)]
    if len(candidati) != 1:
        bb.fatal('USB: trebuie exact un tar.bz2 al imaginii curente')
    # Nucleul din aceeasi constructie, comprimat ca kernel_cfe_auto.bin din arhiva NAND.
    vmlinux = os.path.join(d.getVar('DEPLOY_DIR_IMAGE'), 'vmlinux-%s.bin' % d.getVar('MACHINE'))
    if not os.path.isfile(vmlinux):
        bb.fatal('USB: lipseste nucleul %s' % vmlinux)
    with open(vmlinux, 'rb') as f:
        nucleu = gzip.compress(f.read(), compresslevel=9, mtime=0)
    # Metadatele transportului sunt distincte de /etc/image-version.
    # Formatul propriu comun cu verificatorul de publicare HD Satelit.
    versiune = '%s-%s.%s\n' % (d.getVar('DISTRO_NAME'),
                               d.getVar('DISTRO_VERSION'), d.getVar('DATE'))
    iesire = os.path.join(deploy, nume + '_multiboot.zip')
    temporar = iesire + '.partial'
    try:
        with zipfile.ZipFile(temporar, 'w', compression=zipfile.ZIP_STORED) as arhiva:
            arhiva.writestr('imageversion', versiune)
            arhiva.writestr('smallbox/vusolose/kernel_cfe_auto.bin', nucleu)
            arhiva.write(candidati[0], 'smallbox/vusolose/rootfs.tar.bz2')
        os.replace(temporar, iesire)
    finally:
        if os.path.exists(temporar):
            os.unlink(temporar)
}
