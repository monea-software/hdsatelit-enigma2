# Serverul FTP al imaginii HDSatelit: vsftpd, ca in imaginile OE-Alliance (reteta din meta-networking si bbappend-ul
# OE-Alliance), cu setarile noastre:
# - /etc/vsftpd.conf (files/hds-vsftpd.conf): de sine statator pe portul 21, numai IPv4 (pam_access 1.7.1 nu potriveste
#   retelele IPv6 cu prefix, iar pe un soclu IPv6 clientii IPv4 ar veni ca ::ffff:a.b.c.d), fara anonim, root cu parola
#   receptorului, scriere, pornire in /;
# - /etc/pam.d/vsftpd (files/hds-vsftpd.pam): aceeasi parola ca la SSH si SFTP (parola lui root din /etc/shadow, prin
#   common-auth), numai din reteaua de acasa (pam_access cu /etc/security/hds-ssh-retele-locale.conf din hdsatelit-ssh),
#   comutatorul „Fără parolă în rețeaua locală” ca la /etc/pam.d/dropbear;
# - fara tcp-wrappers: libwrap0 nu intra in imagine (vsftpd.conf are tcp_wrappers=NO; cu YES, vsftpd fara libwrap nu
#   porneste);
# - fara adaosurile bbappend-ului OE-Alliance la scripturile pachetului: utilizatorul „kids” din pkg_postinst (un cont in
#   plus, fara folos aici) si chown-ul din pkg_postinst_ontarget (un postinst amanat la prima pornire; imaginea nu are
#   run-postinsts, deci pachetul ar ramane neconfigurat in opkg). Raman: utilizatorul de sistem „ftp” (useradd, fara
#   parola si fara shell), populate-volatile (dosarul /var/run/vsftpd/empty) si pornirea din init.d.
# Paza imaginii (hds_paza_ssh_rootfs din images/hdsatelit-image.bb) verifica in rootfs aceleasi lucruri.
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SRC_URI += "file://hds-vsftpd.conf \
            file://hds-vsftpd.pam \
"

PACKAGECONFIG:remove = "tcp-wrappers"

# pam_access si pam_permit (regulile din /etc/pam.d/vsftpd), fisierele de reguli din hdsatelit-ssh
RDEPENDS:${PN} += "pam-plugin-access pam-plugin-permit hdsatelit-ssh"

# Adaosurile (:append) puse de alte straturi la pkg_postinst si pkg_postinst_ontarget se scot dupa textul lor: BitBake
# le tine in semnul ":append" al variabilei si le lipeste la citire, deci o functie scrisa din nou aici nu le-ar scoate.
python () {
    pn = d.getVar("PN")
    for nume, semn in (("pkg_postinst", "kids"), ("pkg_postinst_ontarget", "/etc/vsftpd.conf")):
        for var in ("%s:%s" % (nume, pn), "%s:${PN}" % nume):
            adaosuri = d.getVarFlag(var, ":append", False)
            if adaosuri:
                d.setVarFlag(var, ":append", [a for a in adaosuri if semn not in a[0]])
}

do_install:append() {
	install -m 0600 ${UNPACKDIR}/hds-vsftpd.conf ${D}${sysconfdir}/vsftpd.conf
	install -d ${D}${sysconfdir}/pam.d
	install -m 0644 ${UNPACKDIR}/hds-vsftpd.pam ${D}${sysconfdir}/pam.d/vsftpd
	for f in ${D}${sysconfdir}/vsftpd.conf ${D}${sysconfdir}/pam.d/vsftpd; do
		if grep -q "$(printf '\r')" "$f"; then
			bbfatal "vsftpd: $f are sfarsit de rand CRLF"
		fi
	done
	c=${D}${sysconfdir}/vsftpd.conf
	grep -qx 'anonymous_enable=NO' "$c" || bbfatal "vsftpd: vsftpd.conf fara anonymous_enable=NO"
	grep -qx 'local_enable=YES' "$c" || bbfatal "vsftpd: vsftpd.conf fara local_enable=YES"
	grep -qx 'tcp_wrappers=NO' "$c" || bbfatal "vsftpd: vsftpd.conf fara tcp_wrappers=NO"
	grep -qx 'pam_service_name=vsftpd' "$c" || bbfatal "vsftpd: vsftpd.conf fara pam_service_name=vsftpd"
	grep -qx 'listen=YES' "$c" && grep -qx 'listen_ipv6=NO' "$c" || bbfatal "vsftpd: vsftpd.conf trebuie sa asculte numai pe IPv4"
	# primul rand al PAM-ului: reteaua de acasa, altfel logarea se opreste pe loc
	p=${D}${sysconfdir}/pam.d/vsftpd
	[ "$(grep -v '^#' "$p" | grep . | head -n 1 | tr -s ' \t' ' ')" = \
		"auth requisite pam_access.so accessfile=/etc/security/hds-ssh-retele-locale.conf nodefgroup" ] || \
		bbfatal "vsftpd: /etc/pam.d/vsftpd nu incepe cu reteaua de acasa"
	grep -q '^auth[[:space:]]*include[[:space:]]*common-auth' "$p" || bbfatal "vsftpd: /etc/pam.d/vsftpd fara common-auth"
	if grep -q 'nullok' "$p"; then
		bbfatal "vsftpd: /etc/pam.d/vsftpd primeste parola goala (nullok)"
	fi
	# adaosul bbappend-ului OE-Alliance scrie o copie a PAM-ului in ${D}/tmp; nu intra in pachet
	rm -rf ${D}/tmp
}
