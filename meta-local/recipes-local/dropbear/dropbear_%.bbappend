# Accesul SSH al imaginii HDSatelit: /etc/pam.d/dropbear cu regula pam_access a optiunii „Fără parolă în rețeaua
# locală” inaintea verificarii parolei (common-auth), facuta sa ceara parola la orice problema a fisierului de reguli,
# si cu parola primita numai din reteaua de acasa (aceeasi verificare ca la FTP, /etc/pam.d/vsftpd); cheile merg de
# oriunde. Fisierul de reguli si programul parolei sunt in pachetul hdsatelit-ssh; in imagine regulile trimit pe toata
# lumea la parola.
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

# fisierul PAM s-a schimbat (parola numai din reteaua de acasa): versiune noua a pachetului, pentru actualizari
# Scripturile cheii gazdei (mai jos) NU schimba versiunea. Probat pe receptorul de probe (13.11.2026, 0.7.3, opkg 0.10.0): opkg ruleaza
# la actualizare prerm-ul VECHI, postrm-ul VECHI („upgrade”) si abia apoi preinst-ul NOU, deci pe un receptor cu
# pachetul de pana la 0.7.3 cheia RSA e stearsa inainte ca vreun script nou sa ruleze, iar preinst-ul nu are ce copia
# (.hds1 -> .hds2 a dat o cheie RSA noua; ECDSA si ED25519 au ramas). De aceea copia o tine hds-ssh (pachetul
# hdsatelit-ssh r5, la fiecare pornire: /etc/dropbear/.dropbear_rsa_host_key.pastrata), iar postinst-ul de mai jos o pune
# la loc. O versiune noua a lui dropbear se face numai dupa ce hdsatelit-ssh r5 e instalat pe receptoare (postinst-ul
# lui porneste hds-ssh, care face copia; fara r5 copia lipseste). Postrm-ul nou (din 0.7.4) pastreaza cheia la actualizare: probat pe receptorul de probe (.hds2 ->
# .hds1, aceeasi amprenta RSA).
# .hds2: quiet_log pe comutatorul SSH (randul 1 din files/dropbear), fara access denied in syslog la intrarea din casa
# fara parola. Imaginea noua il are de la inceput, iar receptoarele scrise cu 0.7.4 sau mai nou au postrm-ul nou. Pe o
# baza veche (scrisa cu 0.7.3 sau mai vechi, adusa la zi din meniu) pachetul intra in actualizare NUMAI daca
# hdsatelit-ssh r5 a venit intr-o actualizare de dinainte (copia cheii exista); in aceeasi tranzactie cu r5 cheia RSA
# s-ar pierde, deci acolo dropbear asteapta runda urmatoare.
PR:append = ".hds2"

# Cheia gazdei SSH la actualizare. opkg 0.8 ruleaza la actualizare postrm-ul pachetului VECHI cu "upgrade <versiune>",
# iar postrm-ul din openembedded-core (dropbear_2026.94.bb) sterge /etc/dropbear/dropbear_rsa_host_key fara sa se uite
# la $1. Dupa aceea postinst-ul nou porneste dropbear (update-rc.d -s), iar scriptul init face o cheie RSA noua: cine
# intra pe receptor cu SSH vede "host key changed" dupa orice actualizare care aduce dropbear.
# - postrm: cheile se sterg numai la scoaterea pachetului, nu la actualizare;
# - preinst + postinst: pe receptoarele cu pachetul vechi (postrm-ul lui sterge inca cheia la aceasta actualizare),
#   preinst-ul pastreaza o copie inainte, iar postinst-ul o pune la loc inainte ca update-rc.d sa porneasca dropbear
#   (update-rc.d.bbclass adauga pornirea DUPA textul de aici). Nimic la facerea imaginii ($D).
pkg_postrm:${PN} () {
	case "$1" in
	upgrade|failed-upgrade|abort-install|abort-upgrade)
		;;
	*)
		rm -f ${sysconfdir}/dropbear/dropbear_rsa_host_key ${sysconfdir}/dropbear/dropbear_dss_host_key
		;;
	esac
}

pkg_preinst:${PN} () {
	if [ -z "$D" ] && [ "$1" = "upgrade" ] && [ -s ${sysconfdir}/dropbear/dropbear_rsa_host_key ]; then
		cp -p ${sysconfdir}/dropbear/dropbear_rsa_host_key ${sysconfdir}/dropbear/.dropbear_rsa_host_key.pastrata || true
	fi
}

pkg_postinst:${PN} () {
	if [ -z "$D" ] && [ -s ${sysconfdir}/dropbear/.dropbear_rsa_host_key.pastrata ]; then
		if [ -s ${sysconfdir}/dropbear/dropbear_rsa_host_key ]; then
			rm -f ${sysconfdir}/dropbear/.dropbear_rsa_host_key.pastrata
		else
			mv -f ${sysconfdir}/dropbear/.dropbear_rsa_host_key.pastrata ${sysconfdir}/dropbear/dropbear_rsa_host_key
			chmod 0600 ${sysconfdir}/dropbear/dropbear_rsa_host_key
		fi
	fi
}

RDEPENDS:${PN} += "pam-plugin-access pam-plugin-permit"

do_install:append() {
	if ${@bb.utils.contains('DISTRO_FEATURES', 'pam', 'true', 'false', d)}; then
		install -m 0644 ${UNPACKDIR}/dropbear ${D}${sysconfdir}/pam.d/dropbear
		grep -q '^auth.*\[perm_denied=ignore default=2\].*pam_access.so accessfile=/etc/security/hds-ssh-retea-locala.conf' \
			${D}${sysconfdir}/pam.d/dropbear || bbfatal "dropbear: /etc/pam.d/dropbear fara comutatorul pam_access"
		grep -q 'hds-ssh-retea-locala.conf nodefgroup quiet_log' ${D}${sysconfdir}/pam.d/dropbear || \
			bbfatal "dropbear: comutatorul SSH fara quiet_log"
		[ "$(grep -v '^#' ${D}${sysconfdir}/pam.d/dropbear | grep -c 'quiet_log')" = 1 ] || \
			bbfatal "dropbear: quiet_log numai pe comutator, verificarea retelei scrie refuzul"
		grep -q '^auth.*\[success=ignore default=1\].*pam_access.so accessfile=/etc/security/hds-ssh-retele-locale.conf' \
			${D}${sysconfdir}/pam.d/dropbear || bbfatal "dropbear: /etc/pam.d/dropbear fara verificarea retelei"
		# parola numai din reteaua de acasa: randul requisite chiar inaintea lui common-auth
		[ "$(grep -v '^#' ${D}${sysconfdir}/pam.d/dropbear | grep . | grep -B 1 'include[[:space:]]*common-auth' | head -n 1 | tr -s ' \t' ' ')" = \
			"auth requisite pam_access.so accessfile=/etc/security/hds-ssh-retele-locale.conf nodefgroup" ] || \
			bbfatal "dropbear: /etc/pam.d/dropbear primeste parola si din afara retelei de acasa"
	fi
}
