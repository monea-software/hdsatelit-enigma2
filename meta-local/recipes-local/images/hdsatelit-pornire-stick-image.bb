# HD Satelit: imaginea MICA pentru memoria interna a Dreambox DM8000HD si DM800SE (V21B, 14.11.2026).
# Un .nfi (in _web.zip, image_types_nfi din OE-Alliance) scris de om din modul de salvare Dreambox: loader-ul Dream,
# partitia boot (jffs2: nucleul linux-dreambox 3.2, autoexec.bat, poza de pornire) si radacina jffs2 cu busybox, glibc,
# mke2fs, bzip2 si hdsatelit-pornire-stick. Fara Python, fara enigma2, fara drivere Dream: cativa MB.
# jffs2 pe AMBELE masini: nucleul dm800se nu are UBIFS, iar la dm8000 linia nucleului e fixata pe jffs2
# (recipes-local/linux-dreambox/linux-dreambox_3.2.bbappend), ca sa nu depinda de HDS_VARIANTA.
# Se construieste in ACELASI dosar cu hdsatelit-image (HDS_VARIANTA=usb), imediat dupa el: acelasi nucleu, deci modulele
# din sistemul de pe stick (/lib/modules/3.2-<masina>) se potrivesc cu nucleul din memoria interna. Unealta de unire
# compara kernel-image din cele doua manifeste.
SUMMARY = "HD Satelit: pornirea mica de pe stick (Dreambox DM8000HD, DM800SE)"
LICENSE = "MIT"
PV = "0.1.0"
COMPATIBLE_MACHINE = "^(dm8000|dm800se)$"

inherit image image_types_nfi

# nume propriu: IMAGE_NAME din conf/distro/hdsatelit.conf (hdsatelit-<versiune>-<masina>-<data>) e acelasi pentru orice imagine,
# iar in acelasi dosar de livrare manifestul pornirii mici l-ar inlocui pe cel al sistemului de pe stick
IMAGE_NAME = "${DISTRO_NAME}-pornire-${IMAGE_VERSION}-${MACHINEBUILD}-${DATE}"
IMAGE_NAME[vardepsexclude] += "DATE"

IMAGE_FSTYPES = "jffs2nfi"
IMAGE_INSTALL = "hdsatelit-pornire-stick kernel-image"
IMAGE_FEATURES = ""
IMAGE_LINGUAS = ""
IMAGE_LOCALES_ARCHIVE = ""
# fara recomandari: busybox ar aduce syslog, telnetd, inetd, hwclock; aici nu trebuie nimic din ele
NO_RECOMMENDATIONS = "1"
IMAGE_ROOTFS_MAXSIZE = ""
# suprascrierile variantei usb (classes/hds-usb-image.bbclass) nu se aplica acestei imagini
IMAGE_POSTPROCESS_COMMAND:remove = "hds_usb_transport"
ROOTFS_POSTPROCESS_COMMAND:remove = "hds_usb_marcaj_rootfs"

ROOTFS_POSTPROCESS_COMMAND:append = " hds_pornire_stick_verifica "
hds_pornire_stick_verifica() {
	r=${IMAGE_ROOTFS}
	[ -L $r/sbin/init ] || bbfatal "pornirea mica: /sbin/init nu e legatura (initramfs-ul dm8000 ar refuza radacina)"
	[ "$(readlink $r/sbin/init)" = hds-pornire-stick ] || bbfatal "pornirea mica: /sbin/init nu trimite la hds-pornire-stick"
	for f in bin/busybox usr/sbin/hds-pagina-stare etc/hds-pornire-masina; do
		[ -e $r/$f ] || bbfatal "pornirea mica: lipseste /$f"
	done
	[ -e $r/sbin/mke2fs ] || [ -e $r/usr/sbin/mke2fs ] || bbfatal "pornirea mica: lipseste mke2fs"
	[ "$(cat $r/etc/hds-pornire-masina)" = "${MACHINE}" ] || bbfatal "pornirea mica: hds-pornire-masina gresit"
	ls $r/boot/vmlinux-*.gz > /dev/null 2>&1 || bbfatal "pornirea mica: lipseste nucleul din /boot"
	grep -q 'root=/dev/mtdblock3 rootfstype=jffs2 ro' $r/boot/autoexec.bat || bbfatal "pornirea mica: linia nucleului nu e jffs2 ro"
	grep -q "bootlogo-${MACHINE}.jpg" $r/boot/autoexec.bat || bbfatal "pornirea mica: autoexec.bat nu cheama poza de pornire"
	[ -s $r/boot/bootlogo-${MACHINE}.elf.gz ] && [ -s $r/boot/bootlogo-${MACHINE}.jpg ] || bbfatal "pornirea mica: lipseste poza de pornire"
	# nimic care sa scrie incarcatorul sau memoria interna
	[ ! -e $r/tmp/secondstage-${MACHINE}.bin ] || bbfatal "pornirea mica: secondstage in /tmp (ar rescrie incarcatorul)"
	for p in enigma2 python3 dreambox-dvb-modules-${MACHINE} dreambox-secondstage-${MACHINE} mtd-utils; do
		if [ -d $r/var/lib/opkg/info ] && ls $r/var/lib/opkg/info/$p.control > /dev/null 2>&1; then
			bbfatal "pornirea mica: pachetul $p nu are ce cauta aici"
		fi
	done
	# partitia boot (jffs2) trebuie sa incapa: dm800se 3,75 MiB (cu rezerva), dm8000 7 MiB
	kib=$(du -sk $r/boot | cut -f1)
	lim=7000
	[ "${MACHINE}" = dm800se ] && lim=3500
	[ "$kib" -lt "$lim" ] || bbfatal "pornirea mica: /boot are $kib KiB, peste $lim KiB"
	true
}
