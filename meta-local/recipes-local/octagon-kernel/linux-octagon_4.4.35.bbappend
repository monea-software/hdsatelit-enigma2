# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Octagon SF8008 si SF8008 MINI 4K (masinile sf8008 si sf8008m, nucleul linux-octagon 4.4.35): initramfs-ul din
# nucleu citeste STARTUP-ul activ, asteapta radacina pana la 10 s, primeste root=UUID=..., verifica /sbin/init si cade
# pe locul 1 daca imaginea locului ales lipseste. Cel din stratul producatorului (varianta veche, un "init" static de
# 10 KB) nu stie nimic din acestea, deci pe un receptor ale carui locuri (memorie interna, SSD, stick, card) sunt scrise
# in forma noua radacina nu se monteaza si pornirea ramane la sigla de dinainte. Imaginile facute pentru aceste masini
# au in nucleu initramfs-ul nou (1 754 365 o, md5 d5d83a5003d0fdd83461d63f4f9b32c5) si, in defconfig, driverul AHCI
# platform compilat in nucleu (fara modul) si controlerele de joc: acelasi initramfs si aceleasi randuri aici.
# Fisierele din files/ sunt cele ale acelor imagini, neschimbate: initramfs-subdirboot.cpio.gz si defconfig-ul fiecarei
# masini (fata de cel din stratul producatorului difera numai SATA_AHCI_PLATFORM=y, JOYSTICK_XPAD*, HID_SONY, iar la
# sf8008m si HIDRAW, UHID). Paze: md5-ul initramfs-ului inainte de configurare si, dupa configurare, in .config.
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
# PR-ul unui nucleu vine din MACHINE_KERNEL_PR (machine_kernel_pr.bbclass il pune la parsare peste orice PR)
MACHINE_KERNEL_PR:append = ".hds1"
HDS_INITRAMFS_MD5 = "d5d83a5003d0fdd83461d63f4f9b32c5"

kernel_do_configure:prepend() {
	hds_md5=$(md5sum ${UNPACKDIR}/initramfs-subdirboot.cpio.gz | cut -d' ' -f1)
	if [ "$hds_md5" != "${HDS_INITRAMFS_MD5}" ]; then
		bbfatal "initramfs-subdirboot.cpio.gz: md5 $hds_md5, astept ${HDS_INITRAMFS_MD5} (alt initramfs decat cel al imaginilor)"
	fi
}

kernel_do_configure:append() {
	grep -q '^CONFIG_SATA_AHCI_PLATFORM=y$' ${B}/.config || bbfatal "defconfig: lipseste CONFIG_SATA_AHCI_PLATFORM=y"
	grep -q '^CONFIG_INITRAMFS_SOURCE=.*initramfs-subdirboot.cpio.gz' ${B}/.config || bbfatal "defconfig: initramfs-ul nu e cel din nucleu"
}
