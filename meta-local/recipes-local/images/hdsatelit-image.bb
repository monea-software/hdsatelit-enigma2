SUMMARY = "Imaginea HDSatelit"
DESCRIPTION = "enigma2 HDSatelit pe baza OE-Alliance. Monea Software pentru HD Satelit."
LICENSE = "MIT"
# versiunea se tine dupa configure.ac din depozitul imaginii (AC_INIT) si dupa DISTRO_VERSION din hdsatelit.conf
PV = "0.6.0"

# hdsatelit-nume-local: numele hdsatelit.local in reteaua de acasa (avahi-publish), pe langa numele receptorului
IMAGE_INSTALL = "hdsatelit-base hdsatelit-ssh hdsatelit-nume-local"

# fara arhiva de localizari si fara limbi in plus: interfata are traducerile ei in enigma2-hdsatelit
IMAGE_LINGUAS = ""
IMAGE_LOCALES_ARCHIVE = ""

# Accesul SSH: root intra numai cu o cheie din /home/root/.ssh/authorized_keys sau cu parola facuta pe receptor la
# prima pornire (pachetul hdsatelit-ssh); fara parola se intra numai prin optiunea „Fără parolă în rețeaua locală”
# (pam_access pe adresa clientului, dropbear_%.bbappend din acest strat), oprita implicit.
# Trasaturile allow-empty-password, empty-root-password si allow-root-login lipsesc dinadins: fara empty-root-password,
# rootfs-postcommands pune `root:*:` (nicio parola pana la prima pornire); fara allow-empty-password dropbear nu
# primeste -B (logarea fara nicio dovada, prin metoda „none”); allow-root-login ar scoate numai un -w pe care
# /etc/default/dropbear din bbappend-ul OE-Alliance nu il are.
IMAGE_FEATURES += "package-management"

# busybox-telnetd si busybox-inetd vin ca RRECOMMENDS ale lui busybox (bbappend-ul OE-Alliance) si ar porni telnet
# (portul 23, fara parola) si inetd; recomandarile se refuza aici, iar paza de mai jos opreste constructia daca intra
# totusi pe alta cale.
BAD_RECOMMENDATIONS += "busybox-telnetd busybox-inetd"

# VPN si exFAT (hdsatelit-base): recomandarile care nu intra. wireguard-tools recomanda modulul WireGuard din afara
# nucleului (nucleul il are deja) si openresolv (ecranul VPN scrie singur DNS-ul); libfuse2 recomanda utilitarele FUSE,
# intre ele fusermount cu setuid (montarea exFAT se face ca root, prin mount.exfat-fuse).
# BAD_RECOMMENDATIONS se potriveste numai pe numele adevarat al pachetului, nu pe ce ofera el (Provides): modulul
# WireGuard din afara nucleului e in pachetul kernel-module-wireguard-4.4.35 (Provides: kernel-module-wireguard), deci
# numele cu versiunea nucleului il tine afara (nucleul 4.4.35 are WireGuard inauntru: modules.builtin are
# kernel/net/wireguard/wireguard.ko).
BAD_RECOMMENDATIONS += "kernel-module-wireguard kernel-module-wireguard-4.4.35 wireguard-module openresolv fuse-utils libulockmgr"

INHIBIT_DEFAULT_DEPS = "1"
PACKAGE_ARCH = "${MACHINE_ARCH}"
PSEUDO_INCLUDE_PATHS .= ",${TMPDIR}/rootfs/${MACHINE}"
SSTATE_ALLOW_OVERLAP_FILES += "${DEPLOY_DIR_IMAGE}"

export IMAGE_BASENAME = "hdsatelit-image"

inherit image

# Lista licentelor din imagine, facuta la construire (classes/hds-licente.bbclass): /usr/share/hdsatelit/licente,
# citita de ecranul „Licențe” si de pagina web /licente
inherit hds-licente

# Paza accesului SSH, dupa ce toate pachetele sunt puse si dupa zap_empty_root_password (rootfs-postcommands vine prin
# inherit_defer din image.bbclass, deci un „+=” de aici ar pune paza inaintea ei, iar paza ar gasi inca root:: si ar
# opri constructia; :append o pune la sfarsitul listei): DROPBEAR_EXTRA_ARGS fara -B (logare fara dovada) si fara -w
# (fara root, singurul cont al receptorului), scris din nou numai cu celelalte argumente; apoi constructia se opreste
# daca root are parola goala, daca a ramas -B sau -w, daca telnetd ori inetd sunt in imagine sau daca lipsesc piesele
# pachetului hdsatelit-ssh si regula pam_access.
hds_paza_ssh_rootfs() {
	implicit=${IMAGE_ROOTFS}${sysconfdir}/default/dropbear
	[ -f "$implicit" ] || bbfatal "paza ssh: lipseste /etc/default/dropbear"
	argumente=$(sed -n 's/^DROPBEAR_EXTRA_ARGS=//p' "$implicit" | tail -n 1 | tr -d '"')
	pastrate=
	for a in $argumente; do
		case "$a" in
		-B|-w) ;;
		*) pastrate="$pastrate $a" ;;
		esac
	done
	pastrate=$(echo $pastrate)
	sed -i '/^DROPBEAR_EXTRA_ARGS=/d' "$implicit"
	printf 'DROPBEAR_EXTRA_ARGS="%s"\n' "$pastrate" >> "$implicit"
	for a in $(sed -n 's/^DROPBEAR_EXTRA_ARGS=//p' "$implicit" | tr -d '"'); do
		case "$a" in
		--*) ;;
		-*B*|-*w*) bbfatal "paza ssh: DROPBEAR_EXTRA_ARGS are inca $a" ;;
		esac
	done
	if grep -q '^root::' ${IMAGE_ROOTFS}${sysconfdir}/shadow; then
		bbfatal "paza ssh: root are parola goala in /etc/shadow"
	fi
	if grep -q '^root::' ${IMAGE_ROOTFS}${sysconfdir}/passwd; then
		bbfatal "paza ssh: root are parola goala in /etc/passwd"
	fi
	for s in ${IMAGE_ROOTFS}${sysconfdir}/init.d/telnetd.busybox ${IMAGE_ROOTFS}${sysconfdir}/init.d/inetd.busybox \
		${IMAGE_ROOTFS}${sysconfdir}/rc*.d/*telnetd* ${IMAGE_ROOTFS}${sysconfdir}/rc*.d/*inetd*; do
		if [ -e "$s" ] || [ -L "$s" ]; then
			bbfatal "paza ssh: $s este in imagine (telnet sau inetd)"
		fi
	done
	[ -x ${IMAGE_ROOTFS}${sbindir}/hds-ssh-parola ] || bbfatal "paza ssh: lipseste /usr/sbin/hds-ssh-parola (hdsatelit-ssh)"
	[ -x ${IMAGE_ROOTFS}${sysconfdir}/init.d/hds-ssh ] || bbfatal "paza ssh: lipseste /etc/init.d/hds-ssh (hdsatelit-ssh)"
	ls ${IMAGE_ROOTFS}${sysconfdir}/rc3.d/S*hds-ssh > /dev/null 2>&1 || bbfatal "paza ssh: hds-ssh nu porneste in rc3"
	# regulile pam_access: numai o regula „-” potrivita lasa root fara parola; in imagine nu e niciuna
	regula=${IMAGE_ROOTFS}${sysconfdir}/security/hds-ssh-retea-locala.conf
	grep -q '^+ : ALL : ALL' "$regula" || bbfatal "paza ssh: $regula nu trimite pe toata lumea la parola"
	if grep -q '^-' "$regula"; then
		bbfatal "paza ssh: „Fără parolă în rețeaua locală” e pornita in imagine"
	fi
	# PAM: pam_permit numai dupa „refuzat” de la comutator SI „reusit” de la rețeaua locala; altfel parola
	grep -q '^auth.*\[perm_denied=ignore default=2\].*pam_access.so.*hds-ssh-retea-locala.conf' \
		${IMAGE_ROOTFS}${sysconfdir}/pam.d/dropbear || bbfatal "paza ssh: /etc/pam.d/dropbear nu are comutatorul pam_access"
	grep -q '^auth.*\[success=ignore default=1\].*pam_access.so.*hds-ssh-retele-locale.conf' \
		${IMAGE_ROOTFS}${sysconfdir}/pam.d/dropbear || bbfatal "paza ssh: /etc/pam.d/dropbear nu are verificarea retelei"
	retele=${IMAGE_ROOTFS}${sysconfdir}/security/hds-ssh-retele-locale.conf
	grep -q '^+ : root : ' "$retele" || bbfatal "paza ssh: $retele nu are rețeaua locala"
	[ "$(grep -v '^#' "$retele" | grep . | tail -n 1)" = "- : ALL : ALL" ] || bbfatal "paza ssh: $retele nu se termina cu - : ALL : ALL"
	[ "$(grep -c 'pam_permit.so' ${IMAGE_ROOTFS}${sysconfdir}/pam.d/dropbear)" = 1 ] || \
		bbfatal "paza ssh: /etc/pam.d/dropbear trebuie sa aiba exact un pam_permit"
	[ -f ${IMAGE_ROOTFS}${base_libdir}/security/pam_access.so ] || bbfatal "paza ssh: lipseste pam_access.so"
	[ -f ${IMAGE_ROOTFS}${base_libdir}/security/pam_permit.so ] || bbfatal "paza ssh: lipseste pam_permit.so"
	# common-auth (libpam-runtime): randul pam_unix fara nullok si nullok_secure. nullok_secure nu e cunoscut de pam_unix
	# 1.7.1 (fiecare logare cu parola ar scrie „unrecognized option” in jurnal), iar nullok ar primi o parola goala; fara
	# ele, un camp gol in /etc/shadow nu deschide nimic
	comun=${IMAGE_ROOTFS}${sysconfdir}/pam.d/common-auth
	[ -f "$comun" ] || bbfatal "paza ssh: lipseste /etc/pam.d/common-auth"
	sed -i -E '/pam_unix\.so/ s/[[:space:]]+nullok(_secure)?([[:space:]]|$)/\2/g' "$comun"
	if grep -Eq '^[^#]*pam_unix\.so.*[[:space:]]nullok' "$comun"; then
		bbfatal "paza ssh: /etc/pam.d/common-auth primeste inca parola goala (nullok)"
	fi
	bbnote "paza ssh: DROPBEAR_EXTRA_ARGS=\"$pastrate\", root fara parola goala, fara nullok, fara telnet si inetd"
}
ROOTFS_POSTPROCESS_COMMAND:append = " hds_paza_ssh_rootfs"

# Paza de model: receptorul pentru care e construita imaginea. Din aceste valori se scriu:
# - /etc/hdsatelit-model in imagine: regulile citite la pornire de garda din enigma2.sh si de
#   Components/HdsPazaModel.py (pe alt receptor nimic nu scrie pe partitii si interfata arata numai mesajul);
# - e2/update/hdsatelit-model in zip: aceleasi randuri plus imageversion si sumele SHA-256 ale lui kernel.bin si
#   rootfs.tar.bz2, verificat inainte de orice scriere facuta de imagine (actualizarea din meniu) si de scripturile
#   pregateste-imagine si urca-pe-stick.
# Amprenta: cipul (CHIP_VERSION din /proc/msp/sys), antetul de fabrica al partitiei deviceinfo (HW=), tabela
# partitiilor data de bootloader (numele si marimile pana la nucleu; marimea sistemului depinde de eMMC, deci nu se
# cere), marimea partitiei nucleului si tipul placii din driver. Fisierul de reguli e cheie=valoare, fara spatii in
# lista partitiilor (garda din enigma2.sh o citeste cu awk).
HDS_MODEL_NUME = "Amiko Viper 4K V20"
HDS_MODEL_MACHINEBUILD = "viper4kv20"
HDS_MODEL_CIP = "Hi3798MV200"
HDS_MODEL_BOXTYPE = "u57"
HDS_MODEL_HW = "U5SLIM"
HDS_MODEL_PARTITII = "boot:1M,bootargs:1M,baseparam:4M,pqparam:4M,logo:4M,deviceinfo:4M,loader:32M,trustedcore:8M,kernel:32M,rootfs"
HDS_MODEL_KERNEL_PART = "mmcblk0p9"
HDS_MODEL_KERNEL_KIB = "32768"
HDS_MODEL_ROOTFS_PART = "mmcblk0p10"

# the rules as key=value lines on stdout; a build for another machine stops here instead of marking a wrong receiver
hds_reguli_model() {
	[ "${MACHINEBUILD}" = "${HDS_MODEL_MACHINEBUILD}" ] || bbfatal "paza de model: regulile sunt pentru ${HDS_MODEL_MACHINEBUILD}, constructia e pentru ${MACHINEBUILD}"
	[ "${MTD_KERNEL}" = "${HDS_MODEL_KERNEL_PART}" ] || bbfatal "paza de model: nucleul masinii e pe ${MTD_KERNEL}, regulile spun ${HDS_MODEL_KERNEL_PART}"
	[ "${MTD_ROOTFS}" = "${HDS_MODEL_ROOTFS_PART}" ] || bbfatal "paza de model: sistemul masinii e pe ${MTD_ROOTFS}, regulile spun ${HDS_MODEL_ROOTFS_PART}"
	printf '%s\n' \
		"# HD Satelit: receptorul pentru care e construita imaginea (paza de model)" \
		"format=1" \
		"distro=${DISTRO_NAME}" \
		"version=${DISTRO_VERSION}" \
		"model=${HDS_MODEL_NUME}" \
		"machine=${MACHINE}" \
		"machinebuild=${MACHINEBUILD}" \
		"chip=${HDS_MODEL_CIP}" \
		"boxtype=${HDS_MODEL_BOXTYPE}" \
		"hw=${HDS_MODEL_HW}" \
		"partitions=${HDS_MODEL_PARTITII}" \
		"kernel_part=${HDS_MODEL_KERNEL_PART}" \
		"kernel_kib=${HDS_MODEL_KERNEL_KIB}" \
		"rootfs_part=${HDS_MODEL_ROOTFS_PART}"
}

hds_marcaj_model_rootfs() {
	install -d ${IMAGE_ROOTFS}${sysconfdir}
	hds_reguli_model > ${IMAGE_ROOTFS}${sysconfdir}/hdsatelit-model
	chmod 0644 ${IMAGE_ROOTFS}${sysconfdir}/hdsatelit-model
}
ROOTFS_POSTPROCESS_COMMAND += "hds_marcaj_model_rootfs "

# Runs at the end of IMAGE_CMD of dinobotemmcmultiboot, after the machine code has closed the zip and removed
# ${IMAGEDIR}: the sums are taken from the files inside the zip (what gets written), then the marker is added to it.
hds_marcaj_model_zip() {
	zip_imagine="${DEPLOY_DIR_IMAGE}/${IMAGE_NAME}_mmc.zip"
	dosar="${WORKDIR}/hds-marcaj-model"
	gol=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
	[ -f "$zip_imagine" ] || bbfatal "paza de model: lipseste $zip_imagine"
	for f in ${KERNEL_FILE} ${ROOTFS_FILE} imageversion; do
		unzip -l "$zip_imagine" "${IMAGEDIR}/$f" > /dev/null || bbfatal "paza de model: lipseste ${IMAGEDIR}/$f din zip"
	done
	kernel_sha=$(unzip -p "$zip_imagine" "${IMAGEDIR}/${KERNEL_FILE}" | sha256sum | cut -d' ' -f1)
	rootfs_sha=$(unzip -p "$zip_imagine" "${IMAGEDIR}/${ROOTFS_FILE}" | sha256sum | cut -d' ' -f1)
	versiune=$(unzip -p "$zip_imagine" "${IMAGEDIR}/imageversion" | head -n 1 | tr -cd 'A-Za-z0-9_.+-')
	[ -n "$kernel_sha" ] && [ "$kernel_sha" != "$gol" ] || bbfatal "paza de model: ${KERNEL_FILE} din zip e gol"
	[ -n "$rootfs_sha" ] && [ "$rootfs_sha" != "$gol" ] || bbfatal "paza de model: ${ROOTFS_FILE} din zip e gol"
	[ -n "$versiune" ] || bbfatal "paza de model: imageversion din zip e gol"
	rm -rf "$dosar"
	mkdir -p "$dosar/${IMAGEDIR}"
	hds_reguli_model > "$dosar/${IMAGEDIR}/hdsatelit-model"
	printf '%s\n' "imageversion=$versiune" "kernel_sha256=$kernel_sha" "rootfs_sha256=$rootfs_sha" \
		>> "$dosar/${IMAGEDIR}/hdsatelit-model"
	(cd "$dosar" && zip -q -X "$zip_imagine" "${IMAGEDIR}/hdsatelit-model") || bbfatal "paza de model: marcajul nu a intrat in zip"
	unzip -p "$zip_imagine" "${IMAGEDIR}/hdsatelit-model" | cmp -s - "$dosar/${IMAGEDIR}/hdsatelit-model" || \
		bbfatal "paza de model: marcajul din zip difera de cel scris"
	bbnote "paza de model: ${IMAGEDIR}/hdsatelit-model in $zip_imagine (kernel $kernel_sha, rootfs $rootfs_sha)"
}
IMAGE_CMD:dinobotemmcmultiboot:append = " hds_marcaj_model_zip; "
