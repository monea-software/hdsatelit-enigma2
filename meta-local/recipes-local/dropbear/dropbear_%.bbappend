# Accesul SSH al imaginii HDSatelit: /etc/pam.d/dropbear cu regula pam_access a optiunii „Fără parolă în rețeaua
# locală” inaintea verificarii parolei (common-auth), facuta sa ceara parola la orice problema a fisierului de reguli.
# Fisierul de reguli si programul parolei sunt in pachetul hdsatelit-ssh; in imagine regulile trimit pe toata lumea la
# parola.
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

RDEPENDS:${PN} += "pam-plugin-access pam-plugin-permit"

do_install:append() {
	if ${@bb.utils.contains('DISTRO_FEATURES', 'pam', 'true', 'false', d)}; then
		install -m 0644 ${UNPACKDIR}/dropbear ${D}${sysconfdir}/pam.d/dropbear
		grep -q '^auth.*\[perm_denied=ignore default=2\].*pam_access.so accessfile=/etc/security/hds-ssh-retea-locala.conf' \
			${D}${sysconfdir}/pam.d/dropbear || bbfatal "dropbear: /etc/pam.d/dropbear fara comutatorul pam_access"
		grep -q '^auth.*\[success=ignore default=1\].*pam_access.so accessfile=/etc/security/hds-ssh-retele-locale.conf' \
			${D}${sysconfdir}/pam.d/dropbear || bbfatal "dropbear: /etc/pam.d/dropbear fara verificarea retelei"
	fi
}
