# Reteta copiata din openembedded-core, meta/recipes-core/dropbear/dropbear_2025.88.bb (ramane sub licenta MIT a
# stratului openembedded-core), adusa la dropbear 2026.94, ultima versiune publicata.
# Repara CVE-2025-14282 (numai cu mai multi utilizatori), CVE-2026-3706 si reparatiile fara CVE din 2026.90-2026.93
# pentru serverul care asculta pe portul 22.
# Arhiva https://matt.ucc.asn.au/dropbear/releases/dropbear-2026.94.tar.bz2, 2386978 octeti; sha256 de mai jos
# calculat pe arhiva si egal cu randul din SHA256SUM.asc publicat de autor; semnaturile gpg pe SHA256SUM.asc si pe
# arhiva sunt bune (cheia de semnare a versiunilor dropbear, F734 7EF2 EE2E 07A2 6762 8CA9 4493 1494 F29C 6773).
# Schimbari fata de original:
# - fara 0001-Fix-proxycmd-without-netcat.patch: reparatia e deja in sursa (peticul iese "Reversed");
# - fisierele cerute de SRC_URI (init, unitatile systemd, dropbear.default, peticele, fisierul PAM dropbear) se iau din
#   dosarul retetei din openembedded-core, prin FILESEXTRAPATHS:append. Fisierul PAM al nostru,
#   recipes-local/dropbear/files/dropbear, castiga in continuare: dropbear_%.bbappend din acest dosar il pune prin
#   FILESEXTRAPATHS:prepend, iar in FILESPATH toate caile din FILESEXTRAPATHS vin in ordinea lor (prepend inaintea
#   lui append), inaintea dosarelor retetei (base_set_filespath din utils.bbclass);
# - ce adauga meta-oe-alliance dropbear_2025.%.bbappend, care nu se aplica pe 2026.94: inherit upx-compress,
#   /etc/default/dropbear cu DROPBEAR_EXTRA_ARGS="-R" si marimile cheilor RSA si ECDSA (in locul lui dropbear.default,
#   care punea -w), stergerea scriptului init.d cand distributia foloseste systemd; CONFFILES e deja acelasi.
#   Nu se pune localoptions.h din acel bbappend: nu avea efect nici pana acum (do_configure:append din reteta
#   rescrie ${B}/localoptions.h dupa ce do_configure:prepend il copia), iar valorile lui (DROPBEAR_X11FWD,
#   DROPBEAR_ENABLE_CBC_MODE, DROPBEAR_SHA1_96_HMAC, DROPBEAR_DH_GROUP1 pe 0) sunt deja cele implicite in
#   src/default_options.h din 2026.94. add-missing-GRND-NONBLOCK-def.patch era numai pentru MACHINE_FEATURES
#   legacykernel, pe care masina noastra nu o are.
# Paza imaginii (hds_paza_ssh_rootfs din recipes-local/images/hdsatelit-image.bb) citeste /etc/default/dropbear si
# DROPBEAR_EXTRA_ARGS din el.

FILESEXTRAPATHS:append := "${COREBASE}/meta/recipes-core/dropbear/dropbear:"

SUMMARY = "A lightweight SSH and SCP implementation"
HOMEPAGE = "http://matt.ucc.asn.au/dropbear/dropbear.html"
DESCRIPTION = "Dropbear is a relatively small SSH server and client. It runs on a variety of POSIX-based platforms. Dropbear is open source software, distributed under a MIT-style license. Dropbear is particularly useful for "embedded"-type Linux (or other Unix) systems, such as wireless routers."
SECTION = "console/network"

# some files are from other projects and have others license terms:
#   public domain, OpenSSH 3.5p1, OpenSSH3.6.1p2, PuTTY
LICENSE = "MIT & BSD-3-Clause & BSD-2-Clause & PD"
LIC_FILES_CHKSUM = "file://LICENSE;md5=25cf44512b7bc8966a48b6b1a9b7605f"

DEPENDS = "zlib virtual/crypt"
RPROVIDES:${PN} = "ssh sshd"
RCONFLICTS:${PN} = "openssh-sshd openssh"

SRC_URI = "http://matt.ucc.asn.au/dropbear/releases/dropbear-${PV}.tar.bz2 \
           file://0001-urandom-xauth-changes-to-options.h.patch \
           file://init \
           file://dropbearkey.service \
           file://dropbear@.service \
           file://dropbear.socket \
           file://dropbear.default \
           ${@bb.utils.contains('DISTRO_FEATURES', 'pam', '${PAM_SRC_URI}', '', d)} \
           "

SRC_URI[sha256sum] = "e098034a843699200c8c977a991fff73159735bf795d5f72ef672c41a6b1ae81"
MIRRORS += "http://matt.ucc.asn.au/dropbear/releases/ https://dropbear.nl/mirror/releases/"

PAM_SRC_URI = "file://0005-dropbear-enable-pam.patch \
               file://0006-dropbear-configuration-file.patch \
               file://dropbear"

PAM_PLUGINS = "libpam-runtime \
	pam-plugin-deny \
	pam-plugin-permit \
	pam-plugin-unix \
	"
inherit autotools update-rc.d systemd
# din bbappend-ul meta-oe-alliance
inherit upx-compress

CVE_PRODUCT = "dropbear_ssh"

INITSCRIPT_NAME = "dropbear"
INITSCRIPT_PARAMS = "defaults 10"

SYSTEMD_SERVICE:${PN} = "dropbear.socket"

SBINCOMMANDS = "dropbear dropbearkey dropbearconvert"
BINCOMMANDS = "dbclient ssh scp"
EXTRA_OEMAKE = 'MULTI=1 SCPPROGRESS=1 PROGRAMS="${SBINCOMMANDS} ${BINCOMMANDS}"'

PACKAGECONFIG ?= "${@bb.utils.filter('DISTRO_FEATURES', 'pam x11', d)}"
PACKAGECONFIG[pam] = "--enable-pam,--disable-pam,libpam,${PAM_PLUGINS}"
PACKAGECONFIG[system-libtom] = "--disable-bundled-libtom,--enable-bundled-libtom,libtommath libtomcrypt"
PACKAGECONFIG[x11] = ",,,,xauth"

# This option appends to CFLAGS and LDFLAGS from OE
# This is causing [textrel] QA warning
EXTRA_OECONF += "--disable-harden"

# musl does not implement wtmp/logwtmp APIs
EXTRA_OECONF:append:libc-musl = " --disable-wtmp --disable-lastlog"

do_configure:append() {
	echo "/* Dropbear features */" > ${B}/localoptions.h
	if ${@bb.utils.contains('PACKAGECONFIG', 'x11', 'true', 'false', d)}; then
		echo "#define DROPBEAR_X11FWD 1" >> ${B}/localoptions.h
	fi
}

do_install() {
	install -d ${D}${sysconfdir} \
		${D}${sysconfdir}/init.d \
		${D}${sysconfdir}/default \
		${D}${sysconfdir}/dropbear \
		${D}${bindir} \
		${D}${sbindir} \
		${D}${localstatedir}

	install -m 0644 ${UNPACKDIR}/dropbear.default ${D}${sysconfdir}/default/dropbear

	install -m 0755 dropbearmulti ${D}${sbindir}/

	for i in ${BINCOMMANDS}
	do
		# ssh and scp symlinks are created by update-alternatives
		if [ $i = ssh ] || [ $i = scp ]; then continue; fi
		ln -s ${sbindir}/dropbearmulti ${D}${bindir}/$i
	done
	for i in ${SBINCOMMANDS}
	do
		ln -s ./dropbearmulti ${D}${sbindir}/$i
	done
	sed -e 's,/etc,${sysconfdir},g' \
		-e 's,/usr/sbin,${sbindir},g' \
		-e 's,/var,${localstatedir},g' \
		-e 's,/usr/bin,${bindir},g' \
		-e 's,/usr,${prefix},g' ${UNPACKDIR}/init > ${D}${sysconfdir}/init.d/dropbear
	chmod 755 ${D}${sysconfdir}/init.d/dropbear
	if [ "${@bb.utils.filter('DISTRO_FEATURES', 'pam', d)}" ]; then
		install -d ${D}${sysconfdir}/pam.d
		install -m 0644 ${UNPACKDIR}/dropbear  ${D}${sysconfdir}/pam.d/
	fi

	# deal with systemd unit files
	install -d ${D}${systemd_system_unitdir}
	install -m 0644 ${UNPACKDIR}/dropbearkey.service ${D}${systemd_system_unitdir}
	install -m 0644 ${UNPACKDIR}/dropbear@.service ${D}${systemd_system_unitdir}
	install -m 0644 ${UNPACKDIR}/dropbear.socket ${D}${systemd_system_unitdir}
	sed -i -e 's,@BASE_BINDIR@,${base_bindir},g' \
		-e 's,@BINDIR@,${bindir},g' \
		-e 's,@SBINDIR@,${sbindir},g' \
		${D}${systemd_system_unitdir}/dropbear.socket ${D}${systemd_system_unitdir}/*.service
}

# din bbappend-ul meta-oe-alliance: /etc/default/dropbear al imaginii
do_install:append() {
	printf '%s\n' 'DROPBEAR_EXTRA_ARGS="-R"' 'DROPBEAR_RSAKEY_ARGS="-s 2048"' 'DROPBEAR_ECDSAKEY_ARGS="-s 521"' \
		> ${D}${sysconfdir}/default/dropbear
	chmod 0644 ${D}${sysconfdir}/default/dropbear
	if ${@bb.utils.contains('DISTRO_FEATURES', 'systemd', 'true', 'false', d)}; then
		rm -f ${D}${sysconfdir}/init.d/dropbear
	fi
}

inherit update-alternatives

ALTERNATIVE_PRIORITY = "20"
ALTERNATIVE:${PN} = "${@bb.utils.filter('BINCOMMANDS', 'scp ssh', d)}"

ALTERNATIVE_TARGET = "${sbindir}/dropbearmulti"

pkg_postrm:${PN} () {
  if [ -f "${sysconfdir}/dropbear/dropbear_rsa_host_key" ]; then
        rm ${sysconfdir}/dropbear/dropbear_rsa_host_key
  fi
  if [ -f "${sysconfdir}/dropbear/dropbear_dss_host_key" ]; then
        rm ${sysconfdir}/dropbear/dropbear_dss_host_key
  fi
}

CONFFILES:${PN} = "${sysconfdir}/default/dropbear"

FILES:${PN} += "${systemd_system_unitdir}/dropbearkey.service"
