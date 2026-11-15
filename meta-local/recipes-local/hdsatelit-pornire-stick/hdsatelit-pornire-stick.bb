# HD Satelit: pornirea mica din memoria interna a Dreambox DM8000HD si DM800SE (V21B, 14.11.2026).
# Incarcatorul Dreambox nu porneste din memoria interna un sistem de peste ~96-100 MB (OE-Alliance f6d48f5768, d24bcf6ba8),
# iar sistemul nostru MIPS are ~140 MiB; pe DM800SE partitia root are 60 MiB. De aceea in memoria interna sta numai acest
# pachet (cu busybox si nucleul, in hdsatelit-pornire-stick-image), iar sistemul intreg sta pe un stick FAT32:
# files/hds-pornire-stick (= /sbin/init) cauta hdsatelit-<masina>/ pe stick, face la prima pornire radacina.ext4 si swap.img,
# apoi intra in sistem prin loop si pivot_root. files/hds-pagina-stare = pagina web (portul 80, prin nc).
# Poza de pornire: elf-ul Dream (dreambox-bootlogo_1.3_<masina>, aceleasi sume ca reteta de bootlogo OE-Alliance) deseneaza
# /boot/bootlogo-<masina>.jpg (linia din autoexec.bat a nucleului); jpg-ul nostru (files/pornire-stick.jpg, facut de
# unealta noastra de poze) spune omului ce sa faca. Driverul video nu se incarca, deci poza
# ramane pe televizor pana porneste sistemul de pe stick.
SUMMARY = "HD Satelit: pornirea de pe stick din memoria interna (Dreambox DM8000HD, DM800SE)"
LICENSE = "CLOSED"
PV = "0.1.0"
COMPATIBLE_MACHINE = "^(dm8000|dm800se)$"
PACKAGE_ARCH = "${MACHINE_ARCH}"

BOOTLOGO_DREAM = "1.3"
SRC_URI = " \
    file://hds-pornire-stick \
    file://hds-pagina-stare \
    file://pornire-stick.jpg \
    https://source.mynonpublic.com/dreambox/dreambox-bootlogo_${BOOTLOGO_DREAM}_${MACHINE}.tar.bz2;name=${MACHINE} \
    "
SRC_URI[dm8000.sha256sum] = "91e4402190fe88cf394ae780141d968a1ebecd8db7b23c1f0ca3f4bfa9c9512a"
SRC_URI[dm800se.sha256sum] = "8a283442c231e82ee1a2093e53dc5bf52c478e12d22c79af7e7026b52711fc9c"
S = "${UNPACKDIR}"

# busybox: sh, mount, losetup, pivot_root, swapon, mkswap, udhcpc, nc, tar, awk; mke2fs face ext4 (busybox numai ext2)
RDEPENDS:${PN} = "busybox busybox-udhcpc bzip2 e2fsprogs-mke2fs"

do_configure[noexec] = "1"
do_compile[noexec] = "1"

do_install() {
	for f in hds-pornire-stick hds-pagina-stare; do
		if grep -q "$(printf '\r')" ${S}/$f; then
			bbfatal "hdsatelit-pornire-stick: $f are sfarsit de rand CRLF"
		fi
	done
	install -d ${D}${base_sbindir} ${D}${sbindir} ${D}${sysconfdir} ${D}/boot
	install -m 0755 ${S}/hds-pornire-stick ${D}${base_sbindir}/hds-pornire-stick
	# initramfs-ul OE-Alliance al nucleului dm8000 primeste radacina numai daca /sbin/init e o LEGATURA (sau are /sbin/ldconfig)
	ln -sf hds-pornire-stick ${D}${base_sbindir}/init
	install -m 0755 ${S}/hds-pagina-stare ${D}${sbindir}/hds-pagina-stare
	echo "${MACHINE}" > ${D}${sysconfdir}/hds-pornire-masina
	elf=$(find ${S} -name "bootlogo-${MACHINE}.elf.gz" | head -1)
	[ -n "$elf" ] || bbfatal "hdsatelit-pornire-stick: lipseste bootlogo-${MACHINE}.elf.gz din arhiva Dream"
	install -m 0644 "$elf" ${D}/boot/bootlogo-${MACHINE}.elf.gz
	install -m 0644 ${S}/pornire-stick.jpg ${D}/boot/bootlogo-${MACHINE}.jpg
	install -d ${D}/media/stick ${D}/mnt/rad ${D}/run ${D}/tmp ${D}/proc ${D}/sys ${D}/dev
}

FILES:${PN} = "${base_sbindir} ${sbindir} ${sysconfdir}/hds-pornire-masina /boot /media /mnt /run /tmp /proc /sys /dev"
INSANE_SKIP:${PN} += "already-stripped arch"
