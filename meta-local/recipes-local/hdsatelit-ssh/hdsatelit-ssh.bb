SUMMARY = "HDSatelit: parola lui root facuta pe receptor si regula „Fără parolă în rețeaua locală”"
DESCRIPTION = "La prima pornire receptorul face o parola intamplatoare pentru root (numai hash-ul intra in \
/etc/shadow; textul clar ramane cat trebuie ca sa fie aratat in Setari > Retea > Acces SSH si in interfata web). \
Programul parolei e folosit si de ecranul Acces SSH (Fa o parola noua). Fisierul de reguli pam_access al optiunii \
Fara parola in reteaua locala vine oprit. Monea Software pentru HD Satelit."
LICENSE = "GPL-2.0-only"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/GPL-2.0-only;md5=801f80980d171dd6425610833a22dbe6"
PV = "0.1.0"
PR = "r1"

SRC_URI = "file://hds-ssh-parola \
           file://hds-ssh \
           file://hds-ssh-stick \
           file://hds-ssh-retea-locala.conf \
           file://hds-ssh-retele-locale.conf \
"
S = "${UNPACKDIR}"

inherit allarch update-rc.d

do_configure[noexec] = "1"
do_compile[noexec] = "1"

# openssl (rand, passwd -6), chpasswd din shadow (-e: hash-ul gata facut), flock (zavorul comenzilor), awk/od/nice din
# busybox
RDEPENDS:${PN} = "openssl-bin shadow util-linux-flock busybox"

INITSCRIPT_NAME = "hds-ssh"
# S09 in rc2-5: inaintea lui dropbear (S10), ca drepturile cheilor sa fie bune cand porneste serverul
INITSCRIPT_PARAMS = "start 09 2 3 4 5 ."

# pachetul nu opreste nimic la actualizare sau dezinstalare (scriptul nu tine niciun proces)
updatercd_prerm() {
:
}

do_install() {
	install -d ${D}${sbindir} ${D}${sysconfdir}/init.d ${D}${sysconfdir}/security
	install -m 0755 ${S}/hds-ssh-parola ${D}${sbindir}/hds-ssh-parola
	install -m 0755 ${S}/hds-ssh-stick ${D}${sbindir}/hds-ssh-stick
	install -m 0755 ${S}/hds-ssh ${D}${sysconfdir}/init.d/hds-ssh
	install -m 0644 ${S}/hds-ssh-retea-locala.conf ${D}${sysconfdir}/security/hds-ssh-retea-locala.conf
	install -m 0644 ${S}/hds-ssh-retele-locale.conf ${D}${sysconfdir}/security/hds-ssh-retele-locale.conf
	install -d -m 0700 ${D}${sysconfdir}/hdsatelit-ssh
	for f in ${D}${sbindir}/hds-ssh-parola ${D}${sbindir}/hds-ssh-stick ${D}${sysconfdir}/init.d/hds-ssh ${D}${sysconfdir}/security/hds-ssh-retea-locala.conf \
		${D}${sysconfdir}/security/hds-ssh-retele-locale.conf; do
		if grep -q "$(printf '\r')" "$f"; then
			bbfatal "hdsatelit-ssh: $f are sfarsit de rand CRLF"
		fi
	done
	# regulile din imagine trimit pe toata lumea la parola (nicio regula „-”): „Fără parolă în rețeaua locală” porneste
	# numai din ecranul Acces SSH
	grep -q '^+ : ALL : ALL' ${D}${sysconfdir}/security/hds-ssh-retea-locala.conf || bbfatal "hdsatelit-ssh: lipseste + : ALL : ALL"
	if grep -q '^-' ${D}${sysconfdir}/security/hds-ssh-retea-locala.conf; then
		bbfatal "hdsatelit-ssh: regulile din imagine lasa pe cineva fara parola"
	fi
	grep -q 'chpasswd -e' ${D}${sbindir}/hds-ssh-parola || bbfatal "hdsatelit-ssh: hds-ssh-parola fara chpasswd -e"
	# cheile de pe stick numai la prima pornire dupa flash (semnul stick-citit, pus inainte de citire)
	grep -q 'stick-citit' ${D}${sbindir}/hds-ssh-stick || bbfatal "hdsatelit-ssh: hds-ssh-stick fara semnul primei porniri"
	# a doua verificare din /etc/pam.d/dropbear: numai rețeaua locala, apoi refuz pentru toti
	grep -q '^+ : root : ' ${D}${sysconfdir}/security/hds-ssh-retele-locale.conf || bbfatal "hdsatelit-ssh: lipseste rețeaua locala"
	[ "$(grep -v '^#' ${D}${sysconfdir}/security/hds-ssh-retele-locale.conf | grep . | tail -n 1)" = "- : ALL : ALL" ] || \
		bbfatal "hdsatelit-ssh: hds-ssh-retele-locale.conf nu se termina cu - : ALL : ALL"
}

# fisierul de reguli il schimba ecranul Acces SSH: o actualizare a pachetului nu il pune inapoi
CONFFILES:${PN} = "${sysconfdir}/security/hds-ssh-retea-locala.conf"

FILES:${PN} = "${sbindir}/hds-ssh-parola ${sbindir}/hds-ssh-stick ${sysconfdir}/init.d/hds-ssh ${sysconfdir}/security/hds-ssh-retea-locala.conf \
               ${sysconfdir}/security/hds-ssh-retele-locale.conf \
               ${sysconfdir}/hdsatelit-ssh"
