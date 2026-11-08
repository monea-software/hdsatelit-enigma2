SUMMARY = "Imaginea HDSatelit"
DESCRIPTION = "enigma2 HDSatelit pe baza OE-Alliance. Monea Software pentru HD Satelit."
LICENSE = "MIT"
# versiunea se tine dupa configure.ac din depozitul imaginii (AC_INIT) si dupa DISTRO_VERSION din hdsatelit.conf
PV = "0.7.1"

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
# Uclan Ustym 4K PRO (masina ustym4kpro, lotul ustym4kpro): geamanul lui SF8008 (stratul meta-uclan e o copie a lui
# meta-octagon); nucleul lui (linux-uclan 4.4.35, defconfig ustym4kpro) NU are nici el WireGuard inauntru, iar masina are
# si ea trasatura oem-info (ustym4kpro.conf), deci aceleasi doua randuri ca pe sf8008.
BAD_RECOMMENDATIONS:remove:ustym4kpro = "kernel-module-wireguard kernel-module-wireguard-4.4.35 wireguard-module"
BAD_RECOMMENDATIONS:append:ustym4kpro = " oem-info"
# Octagon SF8008 MINI 4K (masina sf8008m, lotul imagine-060-sf8008m): nucleul lui (linux-octagon 4.4.35, defconfig
# sf8008m) NU are nici el WireGuard inauntru, deci modulul din afara nucleului intra si aici, ca pe sf8008. oem-info nu
# e recomandat pe sf8008m (masina nu are trasatura oem-info, iar reteta lui e numai pentru sf8008, sfx6008 si sx88v2),
# deci nu e nevoie de el in BAD_RECOMMENDATIONS; verifica-pachete-060.sh il cere oricum lipsa din manifest.
BAD_RECOMMENDATIONS:remove:sf8008m = "kernel-module-wireguard kernel-module-wireguard-4.4.35 wireguard-module"
# GigaBlue UHD TRIO 4K (masina gbmv200, MACHINEBUILD gbtrio4k, lotul modele-noi-0611): nucleul lui (linux-gigablue
# 4.4.35, defconfig gbmv200) NU are nici el WireGuard inauntru, deci modulul din afara nucleului intra si aici, ca pe
# sf8008. oem-info nu e recomandat (masina nu are trasatura oem-info: gbmv200.conf, gigablue-mv200.inc).
BAD_RECOMMENDATIONS:remove:gbtrio4k = "kernel-module-wireguard kernel-module-wireguard-4.4.35 wireguard-module"
# Receptoarele Broadcom (06.11.2026, lotul vuplus4k): Vu+ Solo 4K (linux-vuplus 3.14.28), Uno 4K SE (4.1.20), Duo 4K
# (4.1.45) si AX HD51 (masina hd51, linux-gfutures 4.10.12). Niciun defconfig nu are CONFIG_WIREGUARD (grep pe
# recipes-linux/linux-vuplus-*/<masina>/defconfig si linux-gfutures-4.10.12/hd51/defconfig, OE-Alliance 6.0), deci modulul
# din afara nucleului intra, ca pe viper4k; CONFIG_TUN=m pe toate, deci kernel-module-tun ramane.
BAD_RECOMMENDATIONS:remove:vusolo4k = "kernel-module-wireguard kernel-module-wireguard-4.4.35 wireguard-module"
BAD_RECOMMENDATIONS:remove:vuuno4kse = "kernel-module-wireguard kernel-module-wireguard-4.4.35 wireguard-module"
BAD_RECOMMENDATIONS:remove:vuduo4k = "kernel-module-wireguard kernel-module-wireguard-4.4.35 wireguard-module"
BAD_RECOMMENDATIONS:remove:hd51 = "kernel-module-wireguard kernel-module-wireguard-4.4.35 wireguard-module"

INHIBIT_DEFAULT_DEPS = "1"
PACKAGE_ARCH = "${MACHINE_ARCH}"
PSEUDO_INCLUDE_PATHS .= ",${TMPDIR}/rootfs/${MACHINE}"
SSTATE_ALLOW_OVERLAP_FILES += "${DEPLOY_DIR_IMAGE}"

export IMAGE_BASENAME = "hdsatelit-image"

inherit image
inherit hds-usb-image

# Lista licentelor din imagine, facuta la construire (classes/hds-licente.bbclass): /usr/share/hdsatelit/licente,
# citita de ecranul „Licențe” si de pagina web /licente
inherit hds-licente hds-licente-60

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
	# regulile pam_access: numai o regula „-” potrivita lasa root fara parola. „Fără parolă în rețeaua locală” vine pornita
	# (acasa se intra direct, ca la celelalte imagini), deci cel mult o regula „-”, pentru root, numai cu retelele de
	# acasa (nicio adresa ALL), apoi + : ALL : ALL pentru toti ceilalti
	regula=${IMAGE_ROOTFS}${sysconfdir}/security/hds-ssh-retea-locala.conf
	[ "$(grep -v '^#' "$regula" | grep . | tail -n 1)" = "+ : ALL : ALL" ] || bbfatal "paza ssh: $regula nu trimite pe ceilalti la parola"
	[ "$(grep -c '^-' "$regula")" -le 1 ] || bbfatal "paza ssh: $regula are mai multe reguli -"
	if grep '^-' "$regula" | grep -qvE '^- : root : 127\.0\.0\.0/8 10\.0\.0\.0/8 172\.16\.0\.0/12 192\.168\.0\.0/16 169\.254\.0\.0/16 '; then
		bbfatal "paza ssh: regula „Fără parolă în rețeaua locală” nu e a retelelor de acasa"
	fi
	if grep '^-' "$regula" | grep -qw ALL; then
		bbfatal "paza ssh: regula „Fără parolă în rețeaua locală” lasa fara parola adrese din afara casei"
	fi
	# Telnet (hdsatelit-ssh r3): numai inetd-ul nostru, numai cu programul de logare care inchide legaturile din afara casei
	telnet_conf=${IMAGE_ROOTFS}${sysconfdir}/hds-telnet-inetd.conf
	if [ -e "$telnet_conf" ]; then
		[ -x ${IMAGE_ROOTFS}${sbindir}/hds-telnet-poarta ] || bbfatal "paza telnet: lipseste /usr/sbin/hds-telnet-poarta"
		[ "$(grep -v '^#' "$telnet_conf" | grep . | grep -c 'telnetd -i -l /usr/sbin/hds-telnet-poarta$')" = 1 ] && \
			[ "$(grep -v '^#' "$telnet_conf" | grep -c .)" = 1 ] || bbfatal "paza telnet: $telnet_conf porneste altceva decat hds-telnet-poarta"
		mai_mult_telnet=", telnet numai din casa (hds-telnet-poarta)"
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
	bbnote "paza ssh: DROPBEAR_EXTRA_ARGS=\"$pastrate\", root fara parola goala, fara nullok, fara busybox-telnetd si busybox-inetd${mai_mult_telnet:-}$mai_mult"
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
	kernel_name?:HDS_MODEL_KERNEL_NAME rootfs_name?:HDS_MODEL_ROOTFS_NAME familie?:HDS_MODEL_FAMILIE \
	stocare?:HDS_MODEL_STOCARE"

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
    # familie=broadcom (Vu+ 4K, lotul vuplus4k): garda citeste cipul, tipul placii si locul sistemului din alte noduri
    # (Components/HdsPazaModel.py si tools/enigma2.sh.in); fara cheie = HiSilicon, ca pana acum
    if reguli.get('familie', 'broadcom') != 'broadcom':
        bb.fatal('paza de model: hdsatelit-modele/%s: familie= poate fi numai broadcom (sau lipsa = HiSilicon)' % mb)
    # stocare=nand (Vu+ Solo SE, lotul mips-solose 06.11.2026): memoria interna e NAND (partitii mtdN in /proc/mtd), nu
    # eMMC; garda citeste atunci cipul, tipul placii si partitiile din alta parte (capul lui hdsatelit-modele/vusolose).
    # Lipsa = eMMC, ca pana acum. Nucleul si sistemul trebuie sa fie partitii mtd, iar masina sa fie una cu memorie mica.
    if 'stocare' in reguli:
        if reguli['stocare'] != 'nand':
            bb.fatal('paza de model: hdsatelit-modele/%s: stocare= poate fi numai nand (sau lipsa = eMMC)' % mb)
        for k in ('kernel_part', 'rootfs_part'):
            if not re.fullmatch(r'mtd[0-9]+', reguli[k]):
                bb.fatal('paza de model: hdsatelit-modele/%s: cu stocare=nand, %s= trebuie sa fie mtdN' % (mb, k))
        if ('hdsflashmic' not in (d.getVar('OVERRIDES') or '').split(':')
                and not (d.getVar('HDS_VARIANTA') == 'usb' and mb == 'vusolose')):
            bb.fatal('paza de model: hdsatelit-modele/%s are stocare=nand, dar masina %s nu e in HDS_MASINI_FLASH_MIC '
                '(conf/distro/hdsatelit.conf)' % (mb, d.getVar('MACHINE')))
}

# Dosarul imaginii in zip, acelasi pe toate modelele: e2/update (acolo cauta actualizarea din meniu,
# Screens/HdsSoftwareUpdate.py, si acolo pune reteta marcajul). Stratul masinii da pe V30 amiko/${MACHINE}; pe V20 si V40
# e chiar e2/update. In imagine nu intra fisierul de informatii al masinii din /usr/lib, deci valoarea tine numai de zip.
IMAGEDIR = "e2/update"
# Receptoarele Broadcom (lotul vuplus4k): incarcatorul lor citeste de pe stick numai dosarul masinii, deci acolo ramane
# dosarul din stratul masinii. Vu+: vuplus/${UPDATE_DIR} (vuplus.inc, IMAGEDIR ?=; vusolo4k.conf face cu el _usb.zip in
# IMAGE_CMD:tar:prepend si sterge apoi dosarul vuplus). AX HD51: hd51 (gfutures-oem.inc, randul ax51; gfutures-arm.inc
# face _multi.zip si _recovery_emmc.zip in IMAGE_CMD:hdemmc:append). Actualizarea din meniu (Screens/HdsSoftwareUpdate.py)
# cauta kernel.bin, deci pe Vu+ (kernel_auto.bin) nu gaseste pachetul si nu scrie nimic: imaginea se pune de pe stick.
IMAGEDIR:vusolo4k = "vuplus/${UPDATE_DIR}"
IMAGEDIR:vuuno4kse = "vuplus/${UPDATE_DIR}"
IMAGEDIR:vuduo4k = "vuplus/${UPDATE_DIR}"
IMAGEDIR:hd51 = "hd51"
# Vu+ Solo SE (lotul mips-solose, 06.11.2026): incarcatorul CFE cauta imaginea pe stick numai in vuplus/solose
# (UPDATE_DIR din vusolose.conf), deci zip-ul _usb.zip pastreaza dosarul masinii.
IMAGEDIR:vusolose = "vuplus/${UPDATE_DIR}"

# the rules as key=value lines on stdout, in the order of the rules file; upd_path and confirmat only when the model has them
# (so are emmc_min_kib and emmc_max_kib: the internal memory limits in KiB, read by the guard from 0.6.1 on; stocare only on
# the NAND receivers, where it comes before confirmat)
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
	[ -z "${HDS_MODEL_STOCARE}" ] || printf 'stocare=%s\n' "${HDS_MODEL_STOCARE}"
	[ -z "${HDS_MODEL_CONFIRMAT}" ] || printf 'confirmat=%s\n' "${HDS_MODEL_CONFIRMAT}"
	[ -z "${HDS_MODEL_FAMILIE}" ] || printf 'familie=%s\n' "${HDS_MODEL_FAMILIE}"
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
	[ -z "${HDS_MODEL_STOCARE}" ] || printf 'stocare=%s\n' "${HDS_MODEL_STOCARE}"
	[ -z "${HDS_MODEL_CONFIRMAT}" ] || printf 'confirmat=%s\n' "${HDS_MODEL_CONFIRMAT}"
	[ -z "${HDS_MODEL_FAMILIE}" ] || printf 'familie=%s\n' "${HDS_MODEL_FAMILIE}"
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
	[ -z "${HDS_MODEL_STOCARE}" ] || printf 'stocare=%s\n' "${HDS_MODEL_STOCARE}"
	[ -z "${HDS_MODEL_CONFIRMAT}" ] || printf 'confirmat=%s\n' "${HDS_MODEL_CONFIRMAT}"
	[ -z "${HDS_MODEL_FAMILIE}" ] || printf 'familie=%s\n' "${HDS_MODEL_FAMILIE}"
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
	[ -z "${HDS_MODEL_STOCARE}" ] || printf 'stocare=%s\n' "${HDS_MODEL_STOCARE}"
	[ -z "${HDS_MODEL_CONFIRMAT}" ] || printf 'confirmat=%s\n' "${HDS_MODEL_CONFIRMAT}"
	[ -z "${HDS_MODEL_FAMILIE}" ] || printf 'familie=%s\n' "${HDS_MODEL_FAMILIE}"
}

# Uclan Ustym 4K PRO (masina ustym4kpro, lotul ustym4kpro): aceeasi asezare a partitiilor ca la SF8008 (bootargs.bin din
# ustym4kpro-partitions-20220326: aceeasi blkdevparts, root=/dev/mmcblk0p16 rootsubdir=linuxrootfs1, kernel=/dev/mmcblk0p12),
# deci exact corpul functiei sf8008m de mai sus.
hds_reguli_model:ustym4kpro() {
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
	[ -z "${HDS_MODEL_STOCARE}" ] || printf 'stocare=%s\n' "${HDS_MODEL_STOCARE}"
	[ -z "${HDS_MODEL_CONFIRMAT}" ] || printf 'confirmat=%s\n' "${HDS_MODEL_CONFIRMAT}"
	[ -z "${HDS_MODEL_FAMILIE}" ] || printf 'familie=%s\n' "${HDS_MODEL_FAMILIE}"
}

# GigaBlue UHD TRIO 4K (masina gbmv200, MACHINEBUILD gbtrio4k, lotul modele-noi-0611): aceeasi asezare a partitiilor ca la
# SF8008 (bootargs.bin din gbtrio4k-partitions-20221111: aceeasi blkdevparts, root=/dev/mmcblk0p16 rootsubdir=linuxrootfs1,
# kernel=/dev/mmcblk0p12), deci exact corpul functiei ustym4kpro de mai sus. Suprascrierea dupa MACHINEBUILD exista pe
# aceasta masina (MACHINEOVERRIDES din gigablue-oem.inc).
hds_reguli_model:gbtrio4k() {
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
	[ -z "${HDS_MODEL_STOCARE}" ] || printf 'stocare=%s\n' "${HDS_MODEL_STOCARE}"
	[ -z "${HDS_MODEL_CONFIRMAT}" ] || printf 'confirmat=%s\n' "${HDS_MODEL_CONFIRMAT}"
	[ -z "${HDS_MODEL_FAMILIE}" ] || printf 'familie=%s\n' "${HDS_MODEL_FAMILIE}"
}

hds_marcaj_model_rootfs() {
	install -d ${IMAGE_ROOTFS}${sysconfdir}
	hds_reguli_model > ${IMAGE_ROOTFS}${sysconfdir}/hdsatelit-model
	chmod 0644 ${IMAGE_ROOTFS}${sysconfdir}/hdsatelit-model
}
ROOTFS_POSTPROCESS_COMMAND += "hds_marcaj_model_rootfs "

# /usr/lib/enigma.info (lotul acelasi-nivel, 01.11.2026): numai NUMELE imaginii, pentru listele de pornire multipla ale
# altor imagini. Unele imagini (Tools/MultiBoot.py, analyzeSlot si _formatSlotName) arata „displaydistro imgversion
# (compiledate)”; fara fisier citeste etc/image-version, cauta creator= si arata „Unknown Creator”. NUMAI cheile de mai
# jos: fara imagedir (pe Amiko Dinobot loadmodules.sh scrie /proc/stb/info/upd_path numai din imagedir=, deci fara el
# nu scrie nimic, ca fara fisier; paza din teste/test_recuperare_hostname.py), fara model, brand sau socfamily
# (Converter/HdsCommon.box_info ia atunci totul din boxbranding, ca fara fisier). Pe Octagon oem-info, care l-ar rescrie
# la pornire, nu intra (BAD_RECOMMENDATIONS mai sus); pe V10 nu-l citeste niciun script al producatorului.
# checksum = md5 al randurilor de deasupra, ca la OE-Alliance (MultiBoot.checkChecksum, altfel doar un avertisment).
hds_enigma_info_rootfs() {
	install -d ${IMAGE_ROOTFS}${libdir}
	f=${IMAGE_ROOTFS}${libdir}/enigma.info
	printf '%s\n' "distro='hdsatelit'" "displaydistro='HD Satelit'" "imgversion='${DISTRO_VERSION}'" \
		"compiledate='${DATE}'" > $f
	printf 'checksum=%s\n' "$(md5sum < $f | cut -d' ' -f1)" >> $f
	chmod 0644 $f
	if grep -q '^imagedir' $f; then
		bbfatal "hdsatelit-image: enigma.info nu are voie sa aiba imagedir (ar schimba upd_path pe Dinobot)"
	fi
}
hds_enigma_info_rootfs[vardepsexclude] += "DATE"
ROOTFS_POSTPROCESS_COMMAND += "hds_enigma_info_rootfs "

# Runs at the end of IMAGE_CMD of the machine's image type, after the machine code has closed the zip and removed
# ${IMAGEDIR}: the sums are taken from the files inside the zip (what gets written), then the marker is added to it.
# The type is dinobotemmcmultiboot on u57 (V20, V30) and dinobotemmc on u571 (V40); both make the same
# ${IMAGE_NAME}_mmc.zip with ${IMAGEDIR}/{kernel.bin,rootfs.tar.bz2,imageversion}. Without the second line the V40 zip
# would come out without the marker and the update from the menu would refuse it, with no error at build time.
HDS_MARCAJ_ZIP = "${IMAGE_NAME}_mmc.zip"
hds_marcaj_model_zip() {
	zip_imagine="${DEPLOY_DIR_IMAGE}/${HDS_MARCAJ_ZIP}"
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
# Uclan Ustym 4K PRO (masina ustym4kpro, lotul ustym4kpro): tipul de imagine al masinii e uclanemmc (meta-uclan,
# uclan-emmc_image.bbclass si IMAGE_CMD:uclanemmc:append din uclan-hisi.inc, acelasi corp ca octagonemmc), acelasi zip
# ${IMAGE_NAME}_mmc.zip cu ${IMAGEDIR}/{kernel.bin,rootfs.tar.bz2,imageversion} plus *_recovery_emmc.zip.
IMAGE_CMD:uclanemmc:append = " hds_marcaj_model_zip; "
# GigaBlue UHD TRIO 4K (masina gbmv200, MACHINEBUILD gbtrio4k, lotul modele-noi-0611): tipul de imagine al masinii e
# gigablueemmc (meta-gigablue, gigablue-emmc_image.bbclass si IMAGE_CMD:gigablueemmc:append din gigablue-mv200.inc, acelasi
# fel ca octagonemmc: mkupdate cu emmc_partitions.xml), acelasi zip ${IMAGE_NAME}_mmc.zip cu
# ${IMAGEDIR}/{kernel.bin,rootfs.tar.bz2,imageversion} plus *_recovery_emmc.zip.
IMAGE_CMD:gigablueemmc:append = " hds_marcaj_model_zip; "
# Vu+ Solo 4K, Uno 4K SE, Duo 4K (lotul vuplus4k): masina face ${IMAGE_NAME}_usb.zip cu ${IMAGEDIR}/{kernel_auto.bin,
# rootfs.tar.bz2,imageversion,initrd_auto.bin,...} in IMAGE_CMD:tar:prepend (vusolo4k.conf), adica inainte de comanda tar
# a lui image_types.bbclass, care se termina cu „|| [ $? -eq 1 ]”: de aceea randul incepe cu „;”. Numai pe masinile
# acestea (tar e si la alte tipuri de imagine).
HDS_MARCAJ_ZIP:vusolo4k = "${IMAGE_NAME}_usb.zip"
HDS_MARCAJ_ZIP:vuuno4kse = "${IMAGE_NAME}_usb.zip"
HDS_MARCAJ_ZIP:vuduo4k = "${IMAGE_NAME}_usb.zip"
# Sigla incarcatorului Vu+: vuplus.inc pune trasatura bootsplash, iar IMAGE_CMD:tar:prepend al masinii copiaza
# ${DEPLOY_DIR_IMAGE}/splash_cfe_auto.bin (BOOTLOGO_FILENAME) in dosarul de pe stick ca splash_auto.bin. Fisierul il face
# sigla distributiei (reteta ei de sigla, do_deploy, splash480.bmp pe Vu+); hdsatelit-bootlogo nu o face, iar
# prima constructie Solo 4K a cazut acolo (06.11, 12:04). Al nostru: files/hds-splash-vuplus.bmp, BMP Windows 3.x de
# 720 x 480 x 24, aceeasi forma si marime (1036854 o) ca splash480.bmp, facut din backdrop.mvi (sigla HD Satelit) cu
# ffmpeg -f mpegvideo -i backdrop.mvi -frames:v 1 -vf scale=720:480 -pix_fmt bgr24. Prepend-ul retetei se pune inaintea
# celui al masinii (masina se citeste prima), deci fisierul exista cand il copiaza masina.
HDS_SPLASH_VUPLUS := "${THISDIR}/files/hds-splash-vuplus.bmp"
IMAGE_CMD:tar:prepend:vusolo4k = "install -m 0644 ${HDS_SPLASH_VUPLUS} ${DEPLOY_DIR_IMAGE}/splash_cfe_auto.bin; "
IMAGE_CMD:tar:prepend:vuuno4kse = "install -m 0644 ${HDS_SPLASH_VUPLUS} ${DEPLOY_DIR_IMAGE}/splash_cfe_auto.bin; "
IMAGE_CMD:tar:prepend:vuduo4k = "install -m 0644 ${HDS_SPLASH_VUPLUS} ${DEPLOY_DIR_IMAGE}/splash_cfe_auto.bin; "
IMAGE_CMD:tar:append:vusolo4k = "; hds_marcaj_model_zip; "
IMAGE_CMD:tar:append:vuuno4kse = "; hds_marcaj_model_zip; "
IMAGE_CMD:tar:append:vuduo4k = "; hds_marcaj_model_zip; "
# AX HD51 (masina hd51): IMAGE_CMD:hdemmc:append din gfutures-arm.inc face ${IMAGE_NAME}_multi.zip cu
# ${IMAGEDIR}/{imageversion,kernel.bin,rootfs.tar.bz2} (si _recovery_emmc.zip cu disk.img, pe care nu-l atingem).
HDS_MARCAJ_ZIP:hd51 = "${IMAGE_NAME}_multi.zip"
IMAGE_CMD:hdemmc:append = " hds_marcaj_model_zip; "

# Receptoarele cu memorie interna mica (NAND de 256 MB; HDS_MASINI_FLASH_MIC si suprascrierea hdsflashmic din
# conf/distro/hdsatelit.conf; lotul mips-solose, 06.11.2026). Hotararea lui Eduard (06.11.2026 07:52-07:57): imaginea
# trebuie sa incapa INSTALATA in 256 MB, cu loc pentru setari si canale; ce nu e strict necesar sta in feedul imaginii si
# se instaleaza la cerere. NUMAI pe aceste masini; pe eMMC nimic din ce urmeaza nu se aplica.
# - Vu+ Solo SE: tipul de imagine al masinii e ubi (vusolose.conf, IMAGE_CMD:ubi:append): pune in ${IMAGEDIR}
#   (vuplus/solose) root_cfe_auto.bin, kernel_cfe_auto.bin, initrd_cfe_auto.bin, splash_cfe_auto.bin, imageversion si
#   force.update, inchide ${IMAGE_NAME}_usb.zip si sterge dosarul; randul de aici vine dupa al masinii (stratul masinii
#   se citeste inainte de reteta), deci marcajul intra in zip-ul inchis, ca pe eMMC.
# - zip-ul: vusolose.conf il face ${IMAGE_NAME}_usb.zip (ca masinile Vu+ 4K de mai sus); marcajul si paza marimii
#   il cauta in HDS_MARCAJ_ZIP.
HDS_MARCAJ_ZIP:vusolose = "${IMAGE_NAME}_usb.zip"
IMAGE_CMD:ubi:append = " hds_marcaj_model_zip; hds_paza_marime_flash_mic; "
# - sigla incarcatorului CFE: vuplus.inc pune trasatura bootsplash, iar IMAGE_CMD:ubi:append din vusolose.conf copiaza
#   ${DEPLOY_DIR_IMAGE}/splash_cfe_auto.bin (BOOTLOGO_FILENAME) in vuplus/solose. Fisierul il face sigla distributiei (la
#   reteta ei de sigla, do_deploy: splash480.bmp pe vusolose, ca pe vusolo4k); hdsatelit-bootlogo nu il face, iar prima
#   constructie Solo SE a cazut acolo (06.11.2026, 13:42: cp ... splash_cfe_auto.bin: No such file). Al nostru:
#   files/hds-splash-vuplus.bmp, BMP 720 x 480 x 24 (1036854 o, ca splash480.bmp) facut din backdrop.mvi (sigla HD Satelit),
#   acelasi fisier ca la lotul vuplus4k (Solo 4K, Uno 4K SE, Duo 4K; HDS_SPLASH_VUPLUS de mai sus). Prepend: intra
#   inainte de randurile masinii.
IMAGE_CMD:ubi:prepend:vusolose = "install -m 0644 ${HDS_SPLASH_VUPLUS} ${DEPLOY_DIR_IMAGE}/splash_cfe_auto.bin; "
# - compresia UBIFS: mkfs.ubifs pune implicit lzo; zlib strange mai bine (planul de marime e socotit cu zlib), iar
#   nucleul Solo SE (linux-vuplus 3.13.5, defconfig_proxy) are CONFIG_UBIFS_FS_ZLIB=y. MKFS_EXTRA intra in MKUBIFS_ARGS
#   (vuplus.inc). Fara zstd: nucleul 3.13.5 nu il stie.
MKFS_EXTRA:hdsflashmic = "-x zlib"
# - paza marimii: sistemul (root_cfe_auto.bin, UBI) peste HDS_FLASH_MIC_MAXIM_MIB opreste constructia. Pe Solo SE V1
#   UBIFS are ~211 MiB (1745 LEB), din care df arata ~194 MiB; 150 MiB lasa macar ~44 MiB pentru setari, canale, EPG si
#   pachetele instalate de om. Planul (lucru-sesiune/oe-60/mips-solose/STADIU.md) socoteste ~110-120 MB.
HDS_FLASH_MIC_MAXIM_MIB ?= "150"
hds_paza_marime_flash_mic() {
	zip_imagine="${DEPLOY_DIR_IMAGE}/${HDS_MARCAJ_ZIP}"
	octeti=$(unzip -l "$zip_imagine" "${IMAGEDIR}/${ROOTFS_FILE}" | awk -v f="${IMAGEDIR}/${ROOTFS_FILE}" '$4 == f { print $1 }')
	[ -n "$octeti" ] || bbfatal "paza marimii: nu gasesc ${IMAGEDIR}/${ROOTFS_FILE} in $zip_imagine"
	mib=$(expr "$octeti" / 1048576)
	[ "$mib" -le "${HDS_FLASH_MIC_MAXIM_MIB}" ] || \
		bbfatal "paza marimii: sistemul are $mib MiB (${ROOTFS_FILE}), peste ${HDS_FLASH_MIC_MAXIM_MIB} MiB: nu ar mai ramane loc pentru setari si canale"
	bbnote "paza marimii: ${ROOTFS_FILE} are $octeti octeti ($mib MiB, limita ${HDS_FLASH_MIC_MAXIM_MIB} MiB)"
}
# - copia sistemului ca arhiva, pentru masuratori si verificari (marimi_pachete_rootfs.py, verifica-rootfs-060.py,
#   compara-manifest): pe NAND imaginea e UBI, care nu se citeste pe PC. Se face inainte de tipurile de imagine (care
#   ruleaza in paralel si dintre care ubifs goleste /tmp si /boot din radacina), nu intra in zip si nu se publica.
IMAGE_PREPROCESS_COMMAND:append:hdsflashmic = " hds_copie_sistem_flash_mic"
hds_copie_sistem_flash_mic() {
	tar -cjf ${IMGDEPLOYDIR}/${IMAGE_NAME}.sistem.tar.bz2 -C ${IMAGE_ROOTFS} . || bbfatal "copia sistemului nu s-a facut"
}
