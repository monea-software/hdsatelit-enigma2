SUMMARY = "Imaginea HDSatelit"
DESCRIPTION = "enigma2 HDSatelit pe baza OE-Alliance. Monea Software pentru HD Satelit."
LICENSE = "MIT"
# versiunea se tine dupa configure.ac din depozitul imaginii (AC_INIT) si dupa DISTRO_VERSION din hdsatelit.conf
PV = "0.6.13"

# hdsatelit-nume-local: numele hdsatelit.local in reteaua de acasa (avahi-publish), pe langa numele receptorului
IMAGE_INSTALL = "hdsatelit-base hdsatelit-ssh hdsatelit-nume-local"

# fara arhiva de localizari si fara limbi in plus: interfata are traducerile ei in enigma2-hdsatelit
IMAGE_LINGUAS = ""
IMAGE_LOCALES_ARCHIVE = ""

# Accesul SSH: root intra numai cu o cheie din /home/root/.ssh/authorized_keys sau cu parola receptorului (pachetul
# hdsatelit-ssh: la prima pornire o parola la intamplare, apoi cea aleasa de om in Setari > Retea > Parola receptorului),
# cu parola numai din reteaua de acasa; fara parola se intra numai prin optiunea „Fără parolă în rețeaua locală”
# (pam_access pe adresa clientului, dropbear_%.bbappend din acest strat), oprita implicit.
# Accesul FTP (vsftpd din hdsatelit-base, recipes-local/vsftpd): portul 21, root cu aceeasi parola, numai din reteaua de
# acasa, fara anonim.
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
# Primul Amiko Viper 4K (V10, masina viper4k, lotul imagine-060-v10): nucleul lui (linux-amiko 4.4.35, defconfig
# viper4k) NU are WireGuard inauntru (fara CONFIG_WIREGUARD; V20 il are =y), deci acolo modulul din afara nucleului
# (wireguard-module, pachetul kernel-module-wireguard, recomandat de wireguard-tools prin bbappend-ul OE-Alliance) intra
# in imagine, iar ecranul VPN il gaseste sub /lib/modules (Components/HdsVpn.py, de la 0.6.3). openresolv ramane afara.
# Numai pe viper4k: pe celelalte masini lista de mai sus ramane neschimbata.
BAD_RECOMMENDATIONS:remove:viper4k = "kernel-module-wireguard kernel-module-wireguard-4.4.35 wireguard-module"
# Octagon SF8008 (masina sf8008, lotul imagine-060-sf8008): nucleul lui (linux-octagon 4.4.35, defconfig sf8008) NU are
# nici el WireGuard inauntru, deci modulul din afara nucleului intra si aici, ca pe viper4k.
# oem-info (recomandat de masina prin MACHINE_EXTRA_RRECOMMENDS, trasatura oem-info din sf8008.conf) rescrie la fiecare
# pornire /usr/lib/enigma.info dupa /proc/stb/info/type; imaginea noastra nu are acel fisier (numele vin din
# /etc/hdsatelit-model), iar scriptul l-ar face din nou, numai cu un rand checksum=. Nu intra.
BAD_RECOMMENDATIONS:remove:sf8008 = "kernel-module-wireguard kernel-module-wireguard-4.4.35 wireguard-module"
BAD_RECOMMENDATIONS:append:sf8008 = " oem-info"
# Octagon SF8008 MINI 4K (masina sf8008m, lotul imagine-060-sf8008m): nucleul lui (linux-octagon 4.4.35, defconfig
# sf8008m) NU are nici el WireGuard inauntru, deci modulul din afara nucleului intra si aici, ca pe sf8008. oem-info nu
# e recomandat pe sf8008m (masina nu are trasatura oem-info, iar reteta lui e numai pentru sf8008, sfx6008 si sx88v2),
# deci nu e nevoie de el in BAD_RECOMMENDATIONS; verifica-pachete-060.sh il cere oricum lipsa din manifest.
BAD_RECOMMENDATIONS:remove:sf8008m = "kernel-module-wireguard kernel-module-wireguard-4.4.35 wireguard-module"

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
# daca root are parola goala, daca a ramas -B sau -w, daca telnetd ori inetd sunt in imagine, daca lipsesc piesele
# pachetului hdsatelit-ssh si regula pam_access, daca parola SSH se primeste si din afara retelei de acasa sau daca
# serverul FTP nu e cel al imaginii (vsftpd pornit in rc3, fara anonim, PAM-ul cu reteaua de acasa intai, fara contul
# kids, configurat de opkg: imaginea nu are run-postinsts pentru postinst-uri amanate).
# Ultimele doua paze se leaga de ce pune stratul in imagine: parola numai din reteaua de acasa cand omul isi alege parola
# (hds-ssh-parola are comanda pune) sau cand imaginea are FTP; paza FTP cand vsftpd e in dependintele lui hdsatelit-base
# sau in imagine pe alta cale. Reviziile 0.6.8 pentru alte receptoare (strat-<masina>.txt) iau reteta asta peste stratul
# actualizarii 8, care n-are nici vsftpd, nici parola aleasa: acolo raman celelalte paze.
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
	# ce pune stratul: FTP (vsftpd in dependintele lui hdsatelit-base sau in imagine) si parola aleasa de om (pune)
	cu_ftp=0
	if [ -e ${IMAGE_ROOTFS}${sbindir}/vsftpd ] || [ -L ${IMAGE_ROOTFS}${sbindir}/vsftpd ]; then
		cu_ftp=1
	elif awk '/^Package: / { p = $2 } /^Depends: / && p == "hdsatelit-base" { print }' ${IMAGE_ROOTFS}/var/lib/opkg/status | \
		sed 's/^Depends://' | tr ',' '\n' | grep -Eq '^[[:space:]]*vsftpd([[:space:]]|$)'; then
		cu_ftp=1
	fi
	cu_parola_aleasa=0
	if grep -q '^pune)' ${IMAGE_ROOTFS}${sbindir}/hds-ssh-parola; then
		cu_parola_aleasa=1
	fi
	acasa="auth requisite pam_access.so accessfile=/etc/security/hds-ssh-retele-locale.conf nodefgroup"
	mai_mult=
	if [ "$cu_parola_aleasa" = 1 ] || [ "$cu_ftp" = 1 ]; then
		# parola SSH numai din reteaua de acasa: randul requisite cu reteaua chiar inaintea lui common-auth
		[ "$(grep -v '^#' ${IMAGE_ROOTFS}${sysconfdir}/pam.d/dropbear | grep . | grep -B 1 'include[[:space:]]*common-auth' | \
			head -n 1 | tr -s ' \t' ' ')" = "$acasa" ] || bbfatal "paza ssh: parola SSH se primeste si din afara retelei de acasa"
		mai_mult="$mai_mult, parola numai din reteaua de acasa"
	fi
	if [ "$cu_ftp" = 1 ]; then
		# FTP: vsftpd pornit in rc3, fara anonim, root prin PAM; PAM-ul incepe cu reteaua de acasa si cere parola
		[ -x ${IMAGE_ROOTFS}${sbindir}/vsftpd ] || bbfatal "paza ftp: lipseste /usr/sbin/vsftpd"
		ls ${IMAGE_ROOTFS}${sysconfdir}/rc3.d/S*vsftpd > /dev/null 2>&1 || bbfatal "paza ftp: vsftpd nu porneste in rc3"
		ftp=${IMAGE_ROOTFS}${sysconfdir}/vsftpd.conf
		[ -f "$ftp" ] || bbfatal "paza ftp: lipseste /etc/vsftpd.conf"
		grep -qx 'anonymous_enable=NO' "$ftp" || bbfatal "paza ftp: vsftpd.conf fara anonymous_enable=NO"
		grep -qx 'local_enable=YES' "$ftp" || bbfatal "paza ftp: vsftpd.conf fara local_enable=YES"
		grep -qx 'pam_service_name=vsftpd' "$ftp" || bbfatal "paza ftp: vsftpd.conf fara pam_service_name=vsftpd"
		# numai IPv4: pam_access 1.7.1 nu potriveste retelele IPv6 cu prefix (::ffff:a.b.c.d ar fi refuzat)
		grep -qx 'listen=YES' "$ftp" && grep -qx 'listen_ipv6=NO' "$ftp" || bbfatal "paza ftp: vsftpd.conf trebuie sa asculte numai pe IPv4"
		pamftp=${IMAGE_ROOTFS}${sysconfdir}/pam.d/vsftpd
		[ -f "$pamftp" ] || bbfatal "paza ftp: lipseste /etc/pam.d/vsftpd"
		[ "$(grep -v '^#' "$pamftp" | grep . | head -n 1 | tr -s ' \t' ' ')" = "$acasa" ] || \
			bbfatal "paza ftp: /etc/pam.d/vsftpd nu incepe cu reteaua de acasa"
		grep -q '^auth[[:space:]]*include[[:space:]]*common-auth' "$pamftp" || bbfatal "paza ftp: /etc/pam.d/vsftpd fara common-auth"
		if grep -q 'nullok' "$pamftp"; then
			bbfatal "paza ftp: /etc/pam.d/vsftpd primeste parola goala (nullok)"
		fi
		[ "$(grep -c 'pam_permit.so' "$pamftp")" = 1 ] || bbfatal "paza ftp: /etc/pam.d/vsftpd trebuie sa aiba exact un pam_permit"
		[ -f ${IMAGE_ROOTFS}${base_libdir}/security/pam_listfile.so ] || bbfatal "paza ftp: lipseste pam_listfile.so"
		if grep -q '^kids:' ${IMAGE_ROOTFS}${sysconfdir}/passwd; then
			bbfatal "paza ftp: contul kids e in imagine"
		fi
		stare=$(awk '/^Package: / { p = $2 } /^Status: / && p == "vsftpd" { print; exit }' ${IMAGE_ROOTFS}/var/lib/opkg/status)
		[ "$stare" = "Status: install ok installed" ] || bbfatal "paza ftp: vsftpd nu e configurat in opkg ($stare)"
		mai_mult="$mai_mult, FTP vsftpd fara anonim"
	fi
	# common-auth (libpam-runtime): randul pam_unix fara nullok si nullok_secure. nullok_secure nu e cunoscut de pam_unix
	# 1.7.1 (fiecare logare cu parola ar scrie „unrecognized option” in jurnal), iar nullok ar primi o parola goala; fara
	# ele, un camp gol in /etc/shadow nu deschide nimic
	comun=${IMAGE_ROOTFS}${sysconfdir}/pam.d/common-auth
	[ -f "$comun" ] || bbfatal "paza ssh: lipseste /etc/pam.d/common-auth"
	sed -i -E '/pam_unix\.so/ s/[[:space:]]+nullok(_secure)?([[:space:]]|$)/\2/g' "$comun"
	if grep -Eq '^[^#]*pam_unix\.so.*[[:space:]]nullok' "$comun"; then
		bbfatal "paza ssh: /etc/pam.d/common-auth primeste inca parola goala (nullok)"
	fi
	bbnote "paza ssh: DROPBEAR_EXTRA_ARGS=\"$pastrate\", root fara parola goala, fara nullok, fara telnet si inetd$mai_mult"
}
ROOTFS_POSTPROCESS_COMMAND:append = " hds_paza_ssh_rootfs"

# Paza de model: receptorul pentru care e construita imaginea. Regulile stau ca date, cate un fisier pe model, in
# hdsatelit-modele/<MACHINEBUILD> (viper4kv20 confirmat; viper4kv30 si viper4kv40 cu confirmat=nu). Din ele se scriu:
# - /etc/hdsatelit-model in imagine: regulile citite la pornire de garda din enigma2.sh si de
#   Components/HdsPazaModel.py (pe alt receptor nimic nu scrie pe partitii si interfata arata numai mesajul);
# - e2/update/hdsatelit-model in zip: aceleasi randuri plus imageversion si sumele SHA-256 ale lui kernel.bin si
#   rootfs.tar.bz2, verificat inainte de orice scriere facuta de imagine (actualizarea din meniu) si de scripturile
#   pregateste-imagine si urca-pe-stick.
# Amprenta, ordinea cheilor si de ce fiecare: in capul fisierelor din hdsatelit-modele/. Un MACHINEBUILD fara fisier nu
# are imagine (reteta e sarita: "nu exista reguli"); un fisier stricat (cheie necunoscuta sau lipsa, rand fara =, masina
# sau locul nucleului ori al sistemului diferite de ale masinii) opreste constructia.
HDS_MODELE_DOSAR := "${THISDIR}/hdsatelit-modele"
# cheile fisierului de reguli -> variabilele retetei; cele cu ? pot lipsi (gol = randul nu se scrie)
HDS_MODEL_CHEI = "format:HDS_MODEL_FORMAT distro:HDS_MODEL_DISTRO model:HDS_MODEL_NUME machine:HDS_MODEL_MASINA \
	machinebuild:HDS_MODEL_MACHINEBUILD chip:HDS_MODEL_CIP boxtype:HDS_MODEL_BOXTYPE hw:HDS_MODEL_HW \
	partitions:HDS_MODEL_PARTITII kernel_part:HDS_MODEL_KERNEL_PART kernel_kib:HDS_MODEL_KERNEL_KIB \
	rootfs_part:HDS_MODEL_ROOTFS_PART upd_path?:HDS_MODEL_UPD_PATH emmc_min_kib?:HDS_MODEL_EMMC_MIN \
	emmc_max_kib?:HDS_MODEL_EMMC_MAX confirmat?:HDS_MODEL_CONFIRMAT \
	kernel_name?:HDS_MODEL_KERNEL_NAME rootfs_name?:HDS_MODEL_ROOTFS_NAME"

python () {
    import os
    mb = d.getVar('MACHINEBUILD') or ''
    cale = os.path.join(d.getVar('HDS_MODELE_DOSAR'), mb)
    if not mb or '/' in mb or not os.path.isfile(cale):
        raise bb.parse.SkipRecipe('paza de model: nu exista reguli pentru MACHINEBUILD=%s (hdsatelit-modele/%s)' % (mb, mb))
    chei = {}
    for c in d.getVar('HDS_MODEL_CHEI').split():
        k, v = c.split(':')
        chei[k.rstrip('?')] = (v, k.endswith('?'))
    reguli = {}
    with open(cale, encoding='utf-8') as f:
        for nr, rand in enumerate(f.read().splitlines(), 1):
            if not rand.strip() or rand.startswith('#'):
                continue
            k, egal, v = rand.partition('=')
            if not egal or k not in chei or k in reguli or v != v.strip():
                bb.fatal('paza de model: hdsatelit-modele/%s randul %d nu e o regula buna: %r' % (mb, nr, rand[:80]))
            reguli[k] = v
    for k, (var, poate_lipsi) in chei.items():
        if not poate_lipsi and not reguli.get(k):
            bb.fatal('paza de model: hdsatelit-modele/%s nu are %s=' % (mb, k))
        d.setVar(var, reguli.get(k, ''))
    asteptat = {'format': '1', 'distro': d.getVar('DISTRO_NAME'), 'machinebuild': mb, 'machine': d.getVar('MACHINE'),
        'kernel_part': d.getVar('MTD_KERNEL'), 'rootfs_part': d.getVar('MTD_ROOTFS')}
    for k, v in asteptat.items():
        if reguli[k] != v:
            bb.fatal('paza de model: hdsatelit-modele/%s are %s=%s, constructia are %s' % (mb, k, reguli[k], v))
    for k in ('emmc_min_kib', 'emmc_max_kib'):
        if k in reguli and not reguli[k].isdigit():
            bb.fatal('paza de model: hdsatelit-modele/%s: %s= poate fi numai cifre (KiB)' % (mb, k))
    # numele partitiilor nucleului si ale sistemului (garda de la 0.6.3, V10): amandoua sau niciunul, numai litere,
    # cifre si _ (ca reguliValide din Components/HdsPazaModel.py); fara ele garda cauta kernel si rootfs
    import re
    nume = [k for k in ('kernel_name', 'rootfs_name') if k in reguli]
    if nume and len(nume) != 2:
        bb.fatal('paza de model: hdsatelit-modele/%s: kernel_name= si rootfs_name= vin impreuna' % mb)
    for k in nume:
        if not re.fullmatch(r'[A-Za-z0-9_]+', reguli[k]):
            bb.fatal('paza de model: hdsatelit-modele/%s: %s= poate avea numai litere, cifre si _' % (mb, k))
    if reguli.get('confirmat', 'nu') != 'nu':
        bb.fatal('paza de model: hdsatelit-modele/%s: confirmat= poate fi numai nu (sau lipsa = confirmat)' % mb)
}

# Dosarul imaginii in zip, acelasi pe toate modelele: e2/update (acolo cauta actualizarea din meniu,
# Screens/HdsSoftwareUpdate.py, si acolo pune reteta marcajul). Stratul masinii da pe V30 amiko/${MACHINE}; pe V20 si V40
# e chiar e2/update. In imagine nu intra fisierul de informatii al masinii din /usr/lib, deci valoarea tine numai de zip.
IMAGEDIR = "e2/update"

# the rules as key=value lines on stdout, in the order of the rules file; upd_path and confirmat only when the model has them
# (so are emmc_min_kib and emmc_max_kib: the internal memory limits in KiB, read by the guard from 0.6.1 on)
hds_reguli_model() {
	[ "${MACHINEBUILD}" = "${HDS_MODEL_MACHINEBUILD}" ] || bbfatal "paza de model: regulile sunt pentru ${HDS_MODEL_MACHINEBUILD}, constructia e pentru ${MACHINEBUILD}"
	[ "${MTD_KERNEL}" = "${HDS_MODEL_KERNEL_PART}" ] || bbfatal "paza de model: nucleul masinii e pe ${MTD_KERNEL}, regulile spun ${HDS_MODEL_KERNEL_PART}"
	[ "${MTD_ROOTFS}" = "${HDS_MODEL_ROOTFS_PART}" ] || bbfatal "paza de model: sistemul masinii e pe ${MTD_ROOTFS}, regulile spun ${HDS_MODEL_ROOTFS_PART}"
	hds_dosar="${HDS_MODEL_UPD_PATH}"
	if [ -n "$hds_dosar" ]; then
		case "$hds_dosar" in
			/*[!A-Za-z0-9_./-]*|[!/]*) bbfatal "paza de model: dosarul de recuperare $hds_dosar nu e o cale sigura" ;;
		esac
		[ ${#hds_dosar} -le 60 ] || bbfatal "paza de model: dosarul de recuperare are peste 60 de caractere"
	fi
	case "${HDS_MODEL_CONFIRMAT}" in
		''|nu) ;;
		*) bbfatal "paza de model: confirmat=${HDS_MODEL_CONFIRMAT} (poate fi numai nu)" ;;
	esac
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
	[ -z "$hds_dosar" ] || printf 'upd_path=%s\n' "$hds_dosar"
	[ -z "${HDS_MODEL_EMMC_MIN}" ] || printf 'emmc_min_kib=%s\n' "${HDS_MODEL_EMMC_MIN}"
	[ -z "${HDS_MODEL_EMMC_MAX}" ] || printf 'emmc_max_kib=%s\n' "${HDS_MODEL_EMMC_MAX}"
	[ -z "${HDS_MODEL_CONFIRMAT}" ] || printf 'confirmat=%s\n' "${HDS_MODEL_CONFIRMAT}"
}

# Primul Amiko Viper 4K (V10, masina viper4k, lotul imagine-060-v10): aceeasi functie, plus numele partitiilor
# nucleului si ale sistemului (kernel_name, rootfs_name; la V10 linuxkernel1 si userdata), citite de garda de la 0.6.3,
# dupa partitions= ca in fisierul de reguli. Numai pe viper4k: pe celelalte masini functia de mai sus ramane aceeasi,
# deci si imaginile lor. pregateste-meta-local-060.sh opreste stratul daca cele doua se despart (alt corp decat
# functia de mai sus cu cele trei randuri de aici).
hds_reguli_model:viper4k() {
	[ "${MACHINEBUILD}" = "${HDS_MODEL_MACHINEBUILD}" ] || bbfatal "paza de model: regulile sunt pentru ${HDS_MODEL_MACHINEBUILD}, constructia e pentru ${MACHINEBUILD}"
	[ "${MTD_KERNEL}" = "${HDS_MODEL_KERNEL_PART}" ] || bbfatal "paza de model: nucleul masinii e pe ${MTD_KERNEL}, regulile spun ${HDS_MODEL_KERNEL_PART}"
	[ "${MTD_ROOTFS}" = "${HDS_MODEL_ROOTFS_PART}" ] || bbfatal "paza de model: sistemul masinii e pe ${MTD_ROOTFS}, regulile spun ${HDS_MODEL_ROOTFS_PART}"
	[ -n "${HDS_MODEL_KERNEL_NAME}" ] && [ -n "${HDS_MODEL_ROOTFS_NAME}" ] || bbfatal "paza de model: pe ${MACHINE} regulile trebuie sa aiba kernel_name= si rootfs_name="
	hds_dosar="${HDS_MODEL_UPD_PATH}"
	if [ -n "$hds_dosar" ]; then
		case "$hds_dosar" in
			/*[!A-Za-z0-9_./-]*|[!/]*) bbfatal "paza de model: dosarul de recuperare $hds_dosar nu e o cale sigura" ;;
		esac
		[ ${#hds_dosar} -le 60 ] || bbfatal "paza de model: dosarul de recuperare are peste 60 de caractere"
	fi
	case "${HDS_MODEL_CONFIRMAT}" in
		''|nu) ;;
		*) bbfatal "paza de model: confirmat=${HDS_MODEL_CONFIRMAT} (poate fi numai nu)" ;;
	esac
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
		"kernel_name=${HDS_MODEL_KERNEL_NAME}" \
		"rootfs_name=${HDS_MODEL_ROOTFS_NAME}" \
		"kernel_part=${HDS_MODEL_KERNEL_PART}" \
		"kernel_kib=${HDS_MODEL_KERNEL_KIB}" \
		"rootfs_part=${HDS_MODEL_ROOTFS_PART}"
	[ -z "$hds_dosar" ] || printf 'upd_path=%s\n' "$hds_dosar"
	[ -z "${HDS_MODEL_EMMC_MIN}" ] || printf 'emmc_min_kib=%s\n' "${HDS_MODEL_EMMC_MIN}"
	[ -z "${HDS_MODEL_EMMC_MAX}" ] || printf 'emmc_max_kib=%s\n' "${HDS_MODEL_EMMC_MAX}"
	[ -z "${HDS_MODEL_CONFIRMAT}" ] || printf 'confirmat=%s\n' "${HDS_MODEL_CONFIRMAT}"
}

# Octagon SF8008 (masina sf8008, lotul imagine-060-sf8008): aceeasi asezare a partitiilor ca la V10 (linuxkernel1 si
# userdata), deci exact corpul functiei viper4k de mai sus. pregateste-meta-local-060.sh opreste stratul daca cele doua
# se despart.
hds_reguli_model:sf8008() {
	[ "${MACHINEBUILD}" = "${HDS_MODEL_MACHINEBUILD}" ] || bbfatal "paza de model: regulile sunt pentru ${HDS_MODEL_MACHINEBUILD}, constructia e pentru ${MACHINEBUILD}"
	[ "${MTD_KERNEL}" = "${HDS_MODEL_KERNEL_PART}" ] || bbfatal "paza de model: nucleul masinii e pe ${MTD_KERNEL}, regulile spun ${HDS_MODEL_KERNEL_PART}"
	[ "${MTD_ROOTFS}" = "${HDS_MODEL_ROOTFS_PART}" ] || bbfatal "paza de model: sistemul masinii e pe ${MTD_ROOTFS}, regulile spun ${HDS_MODEL_ROOTFS_PART}"
	[ -n "${HDS_MODEL_KERNEL_NAME}" ] && [ -n "${HDS_MODEL_ROOTFS_NAME}" ] || bbfatal "paza de model: pe ${MACHINE} regulile trebuie sa aiba kernel_name= si rootfs_name="
	hds_dosar="${HDS_MODEL_UPD_PATH}"
	if [ -n "$hds_dosar" ]; then
		case "$hds_dosar" in
			/*[!A-Za-z0-9_./-]*|[!/]*) bbfatal "paza de model: dosarul de recuperare $hds_dosar nu e o cale sigura" ;;
		esac
		[ ${#hds_dosar} -le 60 ] || bbfatal "paza de model: dosarul de recuperare are peste 60 de caractere"
	fi
	case "${HDS_MODEL_CONFIRMAT}" in
		''|nu) ;;
		*) bbfatal "paza de model: confirmat=${HDS_MODEL_CONFIRMAT} (poate fi numai nu)" ;;
	esac
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
		"kernel_name=${HDS_MODEL_KERNEL_NAME}" \
		"rootfs_name=${HDS_MODEL_ROOTFS_NAME}" \
		"kernel_part=${HDS_MODEL_KERNEL_PART}" \
		"kernel_kib=${HDS_MODEL_KERNEL_KIB}" \
		"rootfs_part=${HDS_MODEL_ROOTFS_PART}"
	[ -z "$hds_dosar" ] || printf 'upd_path=%s\n' "$hds_dosar"
	[ -z "${HDS_MODEL_EMMC_MIN}" ] || printf 'emmc_min_kib=%s\n' "${HDS_MODEL_EMMC_MIN}"
	[ -z "${HDS_MODEL_EMMC_MAX}" ] || printf 'emmc_max_kib=%s\n' "${HDS_MODEL_EMMC_MAX}"
	[ -z "${HDS_MODEL_CONFIRMAT}" ] || printf 'confirmat=%s\n' "${HDS_MODEL_CONFIRMAT}"
}

# Octagon SF8008 MINI 4K (masina sf8008m, lotul imagine-060-sf8008m): aceeasi asezare a partitiilor ca la SF8008 si V10
# (linuxkernel1 si userdata), deci exact corpul functiei viper4k de mai sus. pregateste-meta-local-060.sh opreste
# stratul daca cele doua se despart.
hds_reguli_model:sf8008m() {
	[ "${MACHINEBUILD}" = "${HDS_MODEL_MACHINEBUILD}" ] || bbfatal "paza de model: regulile sunt pentru ${HDS_MODEL_MACHINEBUILD}, constructia e pentru ${MACHINEBUILD}"
	[ "${MTD_KERNEL}" = "${HDS_MODEL_KERNEL_PART}" ] || bbfatal "paza de model: nucleul masinii e pe ${MTD_KERNEL}, regulile spun ${HDS_MODEL_KERNEL_PART}"
	[ "${MTD_ROOTFS}" = "${HDS_MODEL_ROOTFS_PART}" ] || bbfatal "paza de model: sistemul masinii e pe ${MTD_ROOTFS}, regulile spun ${HDS_MODEL_ROOTFS_PART}"
	[ -n "${HDS_MODEL_KERNEL_NAME}" ] && [ -n "${HDS_MODEL_ROOTFS_NAME}" ] || bbfatal "paza de model: pe ${MACHINE} regulile trebuie sa aiba kernel_name= si rootfs_name="
	hds_dosar="${HDS_MODEL_UPD_PATH}"
	if [ -n "$hds_dosar" ]; then
		case "$hds_dosar" in
			/*[!A-Za-z0-9_./-]*|[!/]*) bbfatal "paza de model: dosarul de recuperare $hds_dosar nu e o cale sigura" ;;
		esac
		[ ${#hds_dosar} -le 60 ] || bbfatal "paza de model: dosarul de recuperare are peste 60 de caractere"
	fi
	case "${HDS_MODEL_CONFIRMAT}" in
		''|nu) ;;
		*) bbfatal "paza de model: confirmat=${HDS_MODEL_CONFIRMAT} (poate fi numai nu)" ;;
	esac
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
		"kernel_name=${HDS_MODEL_KERNEL_NAME}" \
		"rootfs_name=${HDS_MODEL_ROOTFS_NAME}" \
		"kernel_part=${HDS_MODEL_KERNEL_PART}" \
		"kernel_kib=${HDS_MODEL_KERNEL_KIB}" \
		"rootfs_part=${HDS_MODEL_ROOTFS_PART}"
	[ -z "$hds_dosar" ] || printf 'upd_path=%s\n' "$hds_dosar"
	[ -z "${HDS_MODEL_EMMC_MIN}" ] || printf 'emmc_min_kib=%s\n' "${HDS_MODEL_EMMC_MIN}"
	[ -z "${HDS_MODEL_EMMC_MAX}" ] || printf 'emmc_max_kib=%s\n' "${HDS_MODEL_EMMC_MAX}"
	[ -z "${HDS_MODEL_CONFIRMAT}" ] || printf 'confirmat=%s\n' "${HDS_MODEL_CONFIRMAT}"
}

hds_marcaj_model_rootfs() {
	install -d ${IMAGE_ROOTFS}${sysconfdir}
	hds_reguli_model > ${IMAGE_ROOTFS}${sysconfdir}/hdsatelit-model
	chmod 0644 ${IMAGE_ROOTFS}${sysconfdir}/hdsatelit-model
}
ROOTFS_POSTPROCESS_COMMAND += "hds_marcaj_model_rootfs "

# Runs at the end of IMAGE_CMD of the machine's image type, after the machine code has closed the zip and removed
# ${IMAGEDIR}: the sums are taken from the files inside the zip (what gets written), then the marker is added to it.
# The type is dinobotemmcmultiboot on u57 (V20, V30) and dinobotemmc on u571 (V40); both make the same
# ${IMAGE_NAME}_mmc.zip with ${IMAGEDIR}/{kernel.bin,rootfs.tar.bz2,imageversion}. Without the second line the V40 zip
# would come out without the marker and the update from the menu would refuse it, with no error at build time.
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
IMAGE_CMD:dinobotemmc:append = " hds_marcaj_model_zip; "
# Primul Amiko Viper 4K (V10, masina viper4k, lotul imagine-060-v10): tipul de imagine al masinii e amikoemmc
# (meta-amiko, amiko-emmc_image.bbclass si IMAGE_CMD:amikoemmc:append din amiko-hisi.inc), care face acelasi
# ${IMAGE_NAME}_mmc.zip cu ${IMAGEDIR}/{kernel.bin,rootfs.tar.bz2,imageversion} (si, in plus, *_recovery_emmc.zip cu
# usb_update.bin, pe care nu-l atingem); fara randul acesta zip-ul V10 ar iesi fara marcaj.
IMAGE_CMD:amikoemmc:append = " hds_marcaj_model_zip; "
# Octagon SF8008 (masina sf8008, lotul imagine-060-sf8008): tipul de imagine al masinii e octagonemmc (meta-octagon,
# octagon-emmc_image.bbclass si IMAGE_CMD:octagonemmc:append din octagon-hisi.inc), acelasi zip ${IMAGE_NAME}_mmc.zip
# cu ${IMAGEDIR}/{kernel.bin,rootfs.tar.bz2,imageversion} plus *_recovery_emmc.zip; fara randul acesta zip-ul ar iesi
# fara marcaj.
IMAGE_CMD:octagonemmc:append = " hds_marcaj_model_zip; "
