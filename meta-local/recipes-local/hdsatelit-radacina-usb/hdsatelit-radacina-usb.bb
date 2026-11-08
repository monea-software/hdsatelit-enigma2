SUMMARY = "HD Satelit: pregatirea radacinii USB si a swap-ului"
LICENSE = "CLOSED"
PV = "0.1.0"
SRC_URI = "file://hdsatelit-radacina-usb"
S = "${UNPACKDIR}"
PACKAGE_ARCH = "${MACHINE_ARCH}"
COMPATIBLE_MACHINE = "^(vusolose)$"

inherit update-rc.d

INITSCRIPT_NAME = "hdsatelit-radacina-usb"
# Dupa montarea mediilor din rcS, inainte de partea a doua (S05) si GUI.
INITSCRIPT_PARAMS = "start 04 3 ."
RDEPENDS:${PN} = "enigma2-hdsatelit python3-core python3-json python3-io util-linux-blkid util-linux-swaponoff"

do_configure[noexec] = "1"
do_compile[noexec] = "1"

do_install() {
	install -d ${D}${sysconfdir}/init.d
	install -m 0755 ${S}/hdsatelit-radacina-usb \
		${D}${sysconfdir}/init.d/hdsatelit-radacina-usb
}
