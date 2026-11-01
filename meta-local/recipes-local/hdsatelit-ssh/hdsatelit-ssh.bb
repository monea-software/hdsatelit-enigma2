SUMMARY = "HDSatelit: parola receptorului (root, pentru FTP, SSH si SFTP) si regula „Fără parolă în rețeaua locală”"
DESCRIPTION = "La prima pornire receptorul face o parola intamplatoare pentru root (numai hash-ul intra in \
/etc/shadow; textul clar ramane pe receptor si se vede oricand in Setari > Retea > Parola receptorului si in interfata \
web). Programul parolei e folosit si de acel ecran (Schimba parola, Fa o parola noua). Aceeasi parola merge pentru FTP, \
SSH si SFTP, numai din reteaua de acasa (hds-ssh-retele-locale.conf). Optiunea Fara parola in reteaua locala vine \
pornita (din casa root intra direct, din afara casei numai cu cheia sau parola). Telnet pe portul 23, ca la celelalte \
imagini: din casa ca la SSH, din afara casei inchis (busybox inetd + hds-telnet-poarta). Monea Software pentru HD Satelit."
LICENSE = "GPL-2.0-only"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/GPL-2.0-only;md5=801f80980d171dd6425610833a22dbe6"
PV = "0.1.0"
# r3: Telnet din casa (inetd + hds-telnet-poarta) si regula „Fara parola in reteaua locala” pornita implicit (regula
# veche, nealeasa de om, se inlocuieste o data, la pornire, de hds-ssh)
PR = "r3"

SRC_URI = "file://hds-ssh-parola \
           file://hds-ssh \
           file://hds-ssh-stick \
           file://hds-ssh-retea-locala.conf \
           file://hds-ssh-retele-locale.conf \
           file://hds-telnet-poarta \
           file://hds-telnet-inetd.conf \
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
	install -d ${D}${sbindir} ${D}${sysconfdir}/init.d ${D}${sysconfdir}/security ${D}${datadir}/hdsatelit-ssh
	install -m 0755 ${S}/hds-ssh-parola ${D}${sbindir}/hds-ssh-parola
	install -m 0755 ${S}/hds-ssh-stick ${D}${sbindir}/hds-ssh-stick
	install -m 0755 ${S}/hds-telnet-poarta ${D}${sbindir}/hds-telnet-poarta
	install -m 0755 ${S}/hds-ssh ${D}${sysconfdir}/init.d/hds-ssh
	install -m 0644 ${S}/hds-ssh-retea-locala.conf ${D}${sysconfdir}/security/hds-ssh-retea-locala.conf
	# copia regulii implicite, pentru inlocuirea o data a regulii vechi, nealese de om (hds-ssh, regula_implicita)
	install -m 0644 ${S}/hds-ssh-retea-locala.conf ${D}${datadir}/hdsatelit-ssh/hds-ssh-retea-locala.conf
	install -m 0644 ${S}/hds-ssh-retele-locale.conf ${D}${sysconfdir}/security/hds-ssh-retele-locale.conf
	install -m 0644 ${S}/hds-telnet-inetd.conf ${D}${sysconfdir}/hds-telnet-inetd.conf
	install -d -m 0700 ${D}${sysconfdir}/hdsatelit-ssh
	for f in ${D}${sbindir}/hds-ssh-parola ${D}${sbindir}/hds-ssh-stick ${D}${sbindir}/hds-telnet-poarta ${D}${sysconfdir}/init.d/hds-ssh \
		${D}${sysconfdir}/security/hds-ssh-retea-locala.conf ${D}${sysconfdir}/security/hds-ssh-retele-locale.conf \
		${D}${sysconfdir}/hds-telnet-inetd.conf; do
		if grep -q "$(printf '\r')" "$f"; then
			bbfatal "hdsatelit-ssh: $f are sfarsit de rand CRLF"
		fi
	done
	# „Fără parolă în rețeaua locală” vine pornita: o singura regula „-”, pentru root, numai cu retelele de acasa (aceleasi
	# ca in hds-ssh-retele-locale.conf, fara ALL), apoi + : ALL : ALL (oricine altcineva: cheia sau parola)
	R=${D}${sysconfdir}/security/hds-ssh-retea-locala.conf
	[ "$(grep -c '^-' $R)" = 1 ] || bbfatal "hdsatelit-ssh: regula implicita trebuie sa aiba o singura regula -"
	grep -q '^- : root : 127.0.0.0/8 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 169.254.0.0/16 ' $R || bbfatal "hdsatelit-ssh: regula - nu e a retelelor de acasa"
	if grep '^-' $R | grep -qw ALL; then
		bbfatal "hdsatelit-ssh: regula - lasa fara parola adrese din afara casei"
	fi
	[ "$(grep -v '^#' $R | grep . | tail -n 1)" = "+ : ALL : ALL" ] || bbfatal "hdsatelit-ssh: regula implicita nu se termina cu + : ALL : ALL"
	# Telnet: numai prin programul de logare care inchide legatura din afara casei; inetd numai pe IPv4, cu limita pe minut
	grep -qE '^23[[:space:]]+stream[[:space:]]+tcp[[:space:]]+nowait\.[0-9]+[[:space:]]+root[[:space:]]+/bin/busybox[[:space:]]+telnetd -i -l /usr/sbin/hds-telnet-poarta$' \
		${D}${sysconfdir}/hds-telnet-inetd.conf || bbfatal "hdsatelit-ssh: hds-telnet-inetd.conf nu are randul telnetd cu hds-telnet-poarta"
	[ "$(grep -v '^#' ${D}${sysconfdir}/hds-telnet-inetd.conf | grep -c .)" = 1 ] || bbfatal "hdsatelit-ssh: hds-telnet-inetd.conf porneste si alte servicii"
	grep -q '\[ "\$loc" = acasa \] || inchide' ${D}${sbindir}/hds-telnet-poarta || bbfatal "hdsatelit-ssh: hds-telnet-poarta nu inchide legaturile din afara casei"
	grep -q 'regula_implicita' ${D}${sysconfdir}/init.d/hds-ssh || bbfatal "hdsatelit-ssh: hds-ssh fara inlocuirea regulii vechi"
	grep -q 'chpasswd -e' ${D}${sbindir}/hds-ssh-parola || bbfatal "hdsatelit-ssh: hds-ssh-parola fara chpasswd -e"
	# parola aleasa de om numai pe stdin (niciodata in linia de comanda), cu hash-ul tinut langa textul clar
	grep -q '^pune)' ${D}${sbindir}/hds-ssh-parola || bbfatal "hdsatelit-ssh: hds-ssh-parola fara comanda pune"
	grep -q 'IFS= read -r p' ${D}${sbindir}/hds-ssh-parola || bbfatal "hdsatelit-ssh: hds-ssh-parola nu citeste parola de pe stdin"
	grep -q '^HASH=\$DOSAR/hash$' ${D}${sbindir}/hds-ssh-parola || bbfatal "hdsatelit-ssh: hds-ssh-parola fara fisierul hash"
	# cheile de pe stick numai la prima pornire dupa flash (semnul stick-citit, pus inainte de citire)
	grep -q 'stick-citit' ${D}${sbindir}/hds-ssh-stick || bbfatal "hdsatelit-ssh: hds-ssh-stick fara semnul primei porniri"
	# a doua verificare din /etc/pam.d/dropbear: numai rețeaua locala, apoi refuz pentru toti
	grep -q '^+ : root : ' ${D}${sysconfdir}/security/hds-ssh-retele-locale.conf || bbfatal "hdsatelit-ssh: lipseste rețeaua locala"
	[ "$(grep -v '^#' ${D}${sysconfdir}/security/hds-ssh-retele-locale.conf | grep . | tail -n 1)" = "- : ALL : ALL" ] || \
		bbfatal "hdsatelit-ssh: hds-ssh-retele-locale.conf nu se termina cu - : ALL : ALL"
}

# fisierul de reguli il schimba ecranul Acces SSH: o actualizare a pachetului nu il pune inapoi
CONFFILES:${PN} = "${sysconfdir}/security/hds-ssh-retea-locala.conf"

FILES:${PN} = "${sbindir}/hds-ssh-parola ${sbindir}/hds-ssh-stick ${sbindir}/hds-telnet-poarta ${sysconfdir}/init.d/hds-ssh \
               ${sysconfdir}/security/hds-ssh-retea-locala.conf ${sysconfdir}/security/hds-ssh-retele-locale.conf \
               ${sysconfdir}/hds-telnet-inetd.conf ${datadir}/hdsatelit-ssh ${sysconfdir}/hdsatelit-ssh"
