# Arhiva NAND H8 pastreaza recuperarea si pornirea producatorului neatinse.
# Clasa schimba numai cele doua MACHINEBUILD noi. Celelalte modele isi
# pastreaza comenzile imaginii si alegerea pachetelor.
# Se mosteneste inainte de image: anonimul trebuie rulat inainte de copierea
# IMAGE_CMD in do_image_ubi. Verificarea doar a IMAGE_CMD final nu ajunge.

python () {
    if d.getVar('MACHINEBUILD') not in ('zgemmah8se', 'zgemmah82hplus'):
        return
    # USB1 (27.11.2026): imaginea pentru stick (HDS_VARIANTA = usb) nu e arhiva NAND: fara UBI, fara forma compacta, cu
    # recunoasterea textului si driverele din feed in imagine; o face classes/hds-usb-image.bbclass
    if d.getVar('HDS_VARIANTA') == 'usb':
        return
    machine = d.getVar('MACHINE')
    expected = {'zgemmah8se': 'h8se', 'zgemmah82hplus': 'h8'}
    if machine != expected[d.getVar('MACHINEBUILD')]:
        bb.fatal('H8 NAND: modelul si masina nu se potrivesc')
    d.setVar('IMAGEDIR', machine)
    d.setVar('HDS_MARCAJ_ZIP', '${IMAGE_NAME}_nand.zip')
    d.setVar('HDS_NAND_COMPACT', '1')
    # Limita imaginii lasa loc UBI si blocurilor NAND defecte.
    d.setVar('HDS_NAND_UBI_MAX', '377487360' if machine == 'h8' else '419430400')
    # Scoatem append-ul BSP care face recovery ZIP cu fastboot/bootargs.
    # Pastram generarea UBI standard, apoi punem numai arhiva noastra mica.
    d.setVarFlag('IMAGE_CMD:ubi', ':append', [])
    command = d.getVar('IMAGE_CMD:ubi', False)
    if not command or 'multiubi_mkfs' not in command:
        bb.fatal('H8 NAND: nu gasesc generarea UBI standard')
    d.setVar('IMAGE_CMD:ubi', command + '\nhds_zgemma_nand_zip\n')
    d.setVar('IMAGE_FSTYPES', 'ubi')
    d.setVar('MKUBIFS_ARGS', '-m 4096 -e 253952 -c 2048 -x zlib')
    d.appendVar('IMAGE_PREPROCESS_COMMAND', ' hds_copie_sistem_flash_mic ')
    d.appendVarFlag('do_image_ubi', 'depends', ' virtual/kernel:do_deploy zip-native:do_populate_sysroot unzip-native:do_populate_sysroot')
    # Pastram traducerile, fara OCR/modele si grupul mare de drivere din feed.
    d.setVar('HDS_COMPLETARI_PACHETE', ' '.join(p for p in (d.getVar('HDS_COMPLETARI_PACHETE') or '').split()
             if p not in ('hds-ocr', 'hds-ocr-modele', 'hdsatelit-drivere-feed')))
}

hds_zgemma_nand_zip() {
    rootfs="${IMGDEPLOYDIR}/${IMAGE_NAME}.ubi"
    kernel="${DEPLOY_DIR_IMAGE}/uImage"
    [ -s "$rootfs" ] && [ -s "$kernel" ] || bbfatal "H8 NAND: lipsesc nucleul sau sistemul"
    # SE: 400 MiB pentru rootfs 444 MiB; PLUS: 360 MiB pentru rootfs 400 MiB.
    [ "$(stat -c %s "$rootfs")" -le "${HDS_NAND_UBI_MAX}" ] || bbfatal "H8 NAND: sistemul depaseste limita cu rezerva"
    [ "$(stat -c %s "$kernel")" -le 12582912 ] || bbfatal "H8 NAND: nucleul depaseste 12 MiB"
    dest="${WORKDIR}/hds-zgemma-nand"
    rm -rf "$dest"
    install -d "$dest/${IMAGEDIR}"
    install -m 0644 "$kernel" "$dest/${IMAGEDIR}/uImage"
    install -m 0644 "$rootfs" "$dest/${IMAGEDIR}/rootfs.ubi"
    printf '%s\n' "${IMAGE_NAME}" > "$dest/${IMAGEDIR}/imageversion"
    zip_imagine="${DEPLOY_DIR_IMAGE}/${HDS_MARCAJ_ZIP}"
    rm -f "$zip_imagine"
    (cd "$dest" && zip -q -X "$zip_imagine" "${IMAGEDIR}/uImage" "${IMAGEDIR}/rootfs.ubi" "${IMAGEDIR}/imageversion") || bbfatal "H8 NAND: zip nereusit"
    hds_marcaj_model_zip
}
