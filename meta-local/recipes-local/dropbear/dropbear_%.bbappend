# Accesul SSH al imaginii HDSatelit: /etc/pam.d/dropbear cu regula pam_access a optiunii „Fără parolă în rețeaua
# locală” inaintea verificarii parolei (common-auth), facuta sa ceara parola la orice problema a fisierului de reguli,
# si cu parola primita numai din reteaua de acasa (aceeasi verificare ca la FTP, /etc/pam.d/vsftpd); cheile merg de
# oriunde. Fisierul de reguli si programul parolei sunt in pachetul hdsatelit-ssh; in imagine regulile trimit pe toata
# lumea la parola.
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

# fisierul PAM s-a schimbat (parola numai din reteaua de acasa): versiune noua a pachetului, pentru actualizari
# Scripturile cheii gazdei (mai jos) NU schimba versiunea: intra in imaginile noi si pleaca spre receptoarele de acum
# odata cu urmatoarea schimbare adevarata a pachetului dropbear (atunci preinst/postinst de mai jos o pazesc). O
# versiune noua numai pentru ele ar aduce dropbear tuturor la actualizare: se face numai dupa o actualizare
# adevarata .hds1 -> .hds2 probata pe un receptor, cu aceeasi amprenta RSA inainte si dupa.
PR:append = ".hds1"

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
		grep -q '^auth.*\[success=ignore default=1\].*pam_access.so accessfile=/etc/security/hds-ssh-retele-locale.conf' \
			${D}${sysconfdir}/pam.d/dropbear || bbfatal "dropbear: /etc/pam.d/dropbear fara verificarea retelei"
		# parola numai din reteaua de acasa: randul requisite chiar inaintea lui common-auth
		[ "$(grep -v '^#' ${D}${sysconfdir}/pam.d/dropbear | grep . | grep -B 1 'include[[:space:]]*common-auth' | head -n 1 | tr -s ' \t' ' ')" = \
			"auth requisite pam_access.so accessfile=/etc/security/hds-ssh-retele-locale.conf nodefgroup" ] || \
			bbfatal "dropbear: /etc/pam.d/dropbear primeste parola si din afara retelei de acasa"
	fi
}
