SUMMARY = "Imaginea HDSatelit"
DESCRIPTION = "enigma2 HDSatelit pe baza OE-Alliance. Monea Software pentru HD Satelit."
LICENSE = "MIT"
# versiunea se tine dupa configure.ac din depozitul imaginii (AC_INIT) si dupa DISTRO_VERSION din hdsatelit.conf
PV = "0.7.5"

# hdsatelit-nume-local: numele hdsatelit.local in reteaua de acasa (avahi-publish), pe langa numele receptorului
IMAGE_INSTALL = "hdsatelit-base hdsatelit-ssh hdsatelit-nume-local"
# Completarile in imagine (0.7.5, HDS_COMPLETARI_IN_IMAGINE si HDS_COMPLETARI_PACHETE din conf/distro/hdsatelit.conf; Eduard
# 13.11.2026 11:44): limbile din feed, recunoasterea textului si driverele USB din feed, pe masinile unde incap
def hds_completari_in_imagine(d):
    if d.getVar('HDS_COMPLETARI_IN_IMAGINE') != '1':
        return ''
    pachete = (d.getVar('HDS_COMPLETARI_PACHETE') or '').split()
    # recunoasterea textului nu se construieste pentru MIPS
    if (d.getVar('TARGET_ARCH') or '').startswith('mips'):
        pachete = [p for p in pachete if not p.startswith('hds-ocr')]
    return (' ' + ' '.join(pachete)) if pachete else ''
IMAGE_INSTALL:append = "${@hds_completari_in_imagine(d)}"

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
# Tot GigaBlue TRIO 4K: clasa GigaBlue face ext4-ul radacinii de marime fixa (gigablue-mv200.inc: IMAGE_ROOTFS_SIZE ?=
# "624288" KB). 0.7.1 incapea la limita, 0.7.2 nu mai incapea (mkfs.ext4: Could not allocate block); partitia userdata are
# 7000M, deci 768 MiB e in siguranta. Pana la 0.7.4 valoarea statea numai in local.conf-ul dosarului de constructie
# (fa-dosar-build-60.sh, 9e70ee19f); aici e in strat, deci intra la orice dosar gbtrio4k (overridul vine din
# MACHINEOVERRIDES =. MACHINEBUILD, gigablue-oem.inc). Proba la constructie: bitbake -e hdsatelit-image | grep ^IMAGE_ROOTFS_SIZE=
IMAGE_ROOTFS_SIZE:gbtrio4k = "786432"
# Receptoarele Broadcom (06.11.2026, lotul vuplus4k): Vu+ Solo 4K (linux-vuplus 3.14.28), Uno 4K SE (4.1.20), Duo 4K
# (4.1.45) si AX HD51 (masina hd51, linux-gfutures 4.10.12). Niciun defconfig nu are CONFIG_WIREGUARD (grep pe
# recipes-linux/linux-vuplus-*/<masina>/defconfig si linux-gfutures-4.10.12/hd51/defconfig, OE-Alliance 6.0), deci modulul
# din afara nucleului intra, ca pe viper4k; CONFIG_TUN=m pe toate, deci kernel-module-tun ramane.
BAD_RECOMMENDATIONS:remove:vusolo4k = "kernel-module-wireguard kernel-module-wireguard-4.4.35 wireguard-module"
BAD_RECOMMENDATIONS:remove:vuultimo4k = "kernel-module-wireguard kernel-module-wireguard-4.4.35 wireguard-module"
BAD_RECOMMENDATIONS:remove:vuuno4kse = "kernel-module-wireguard kernel-module-wireguard-4.4.35 wireguard-module"
BAD_RECOMMENDATIONS:remove:vuzero4k = "kernel-module-wireguard kernel-module-wireguard-4.4.35 wireguard-module"
BAD_RECOMMENDATIONS:remove:vuduo4k = "kernel-module-wireguard kernel-module-wireguard-4.4.35 wireguard-module"
BAD_RECOMMENDATIONS:remove:vuduo4kse = "kernel-module-wireguard kernel-module-wireguard-4.4.35 wireguard-module"
# Vu+ Duo 4K Lite (VU1): nucleul linux-vuplus 4.1.20 al lui (meta-vuplusde, defconfig_initrd) nu are nici el
# CONFIG_WIREGUARD; CONFIG_TUN=m
BAD_RECOMMENDATIONS:remove:vuduo4klite = "kernel-module-wireguard kernel-module-wireguard-4.4.35 wireguard-module"
# GigaBlue UHD Quad 4K Pro (ALFA, 12.11.2026): nucleul linux-gigablue 4.1.20 (sursa "pro", defconfig_initrd gb7252) nu are
# CONFIG_WIREGUARD; CONFIG_TUN=m
BAD_RECOMMENDATIONS:remove:gbquad4kpro = "kernel-module-wireguard kernel-module-wireguard-4.4.35 wireguard-module"
# GigaBlue UHD X3 4K (MGX, 12.11.2026): nucleul linux-gigablue 4.1.20 (gb72604/defconfig) nu are CONFIG_WIREGUARD;
# CONFIG_TUN=m
BAD_RECOMMENDATIONS:remove:gbx34k = "kernel-module-wireguard kernel-module-wireguard-4.4.35 wireguard-module"
BAD_RECOMMENDATIONS:remove:hd51 = "kernel-module-wireguard kernel-module-wireguard-4.4.35 wireguard-module"
# Zgemma H17 COMBO (MH7, 12.11.2026; masina h17, meta-airdigital, linux-airdigital 4.10.12): defconfig-ul h17 nu are
# CONFIG_WIREGUARD; CONFIG_TUN=m. Clasa imaginii masinii (airdigital-emmc_image_multiboot16gb.bbclass) face ext4-ul radacinii
# de marime fixa IMAGE_ROOTFS_SIZE (589824 KB in airdigital-arm.inc) si il pune in disk.img-ul de 1 GiB, in userdata (p12,
# 684015 KiB in imaginea publica). Radacina Duo 4K 0.7.4 are 390 MiB de fisiere (-i 4096: ~36 MiB tabele de inoduri, plus
# jurnalul): 640 MiB lasa loc si incape tot in userdata-ul din disk.img. Arhiva de stick are rootfs.tar.bz2, nu ext4-ul.
BAD_RECOMMENDATIONS:remove:h17 = "kernel-module-wireguard kernel-module-wireguard-4.4.35 wireguard-module"
IMAGE_ROOTFS_SIZE:h17 = "655360"
# Dreambox DM900 si DM920 (MDM dm900 wireguard, 12.11.2026; meta-dream, linux-dreambox 3.14-1.17): defconfig-urile
# dm900 si dm920 nu au CONFIG_WIREGUARD, deci modulul din afara nucleului intra (wireguard-linux-compat merge de la 3.10);
# CONFIG_TUN=m, deci kernel-module-tun ramane.
BAD_RECOMMENDATIONS:remove:dm900 = "kernel-module-wireguard kernel-module-wireguard-4.4.35 wireguard-module"
BAD_RECOMMENDATIONS:remove:dm920 = "kernel-module-wireguard kernel-module-wireguard-4.4.35 wireguard-module"
# Zgemma H9 COMBO si H9 TWIN (MH9, 12.11.2026; masina h9combo, meta-airdigital): nucleul linux-airdigital 4.4.35 (defconfig
# h9combo) nu are CONFIG_WIREGUARD; CONFIG_TUN=m. Clasa imaginii masinii (airdigital-fastboot8gb_image.bbclass) face
# ext4-ul radacinii de marime fixa, IMAGE_ROOTFS_SIZE = 460800 KB (450 MiB), iar radacina 0.7.4 are ~462 MiB (SF8008
# 0.7.4, 12.11.2026): ca pe GigaBlue TRIO 4K, 768 MiB (partitia userdata are cateva GB). Numai ext4-ul din deploy; arhiva
# de stick are rootfs.tar.bz2.
BAD_RECOMMENDATIONS:remove:h9combo = "kernel-module-wireguard kernel-module-wireguard-4.4.35 wireguard-module"
IMAGE_ROOTFS_SIZE:h9combo = "786432"
# Novaler Multibox 4K PRO (MNP, 12.11.2026; masina multiboxpro, meta-maxytec): maxytec-hisil-3798mv200.inc si multiboxpro.conf
# pun MTD_ROOTFS = "mmcblk0p20", dar in tabela producatorului (bootargs-8gb.bin) p20 e linuxkernel2, iar pornirea
# (maxytec-fastboot8gb_image.bbclass, STARTUP) e root=/dev/mmcblk0p23 rootsubdir=linuxrootfs1 kernel=/dev/mmcblk0p19.
# hds_reguli_model compara MTD_ROOTFS cu rootfs_part= din reguli; garda din imagine citeste /proc/cmdline (p23). Deci aici
# valoarea adevarata. Nucleul linux-maxytec 4.4.35 (defconfig multiboxpro) are CONFIG_WIREGUARD=y (in nucleu, ca pe V20) si
# CONFIG_TUN=m: BAD_RECOMMENDATIONS ramane cel implicit (fara modulul din afara). Clasa imaginii masinii nu fixeaza marimea
# ext4-ului radacinii (fara IMAGE_ROOTFS_SIZE, spre deosebire de H9).
MTD_ROOTFS:multiboxpro = "mmcblk0p23"
# Zgemma H9 TWIN SE si H9 COMBO SE (MHS, 12.11.2026; masina h9combose): acelasi nucleu si aceeasi clasa de imagine ca
# h9combo de mai sus (defconfig-ul h9combose e identic cu h9combo in OE-Alliance 6.0), deci aceleasi doua randuri.
BAD_RECOMMENDATIONS:remove:h9combose = "kernel-module-wireguard kernel-module-wireguard-4.4.35 wireguard-module"
IMAGE_ROOTFS_SIZE:h9combose = "786432"

INHIBIT_DEFAULT_DEPS = "1"
PACKAGE_ARCH = "${MACHINE_ARCH}"
PSEUDO_INCLUDE_PATHS .= ",${TMPDIR}/rootfs/${MACHINE}"
SSTATE_ALLOW_OVERLAP_FILES += "${DEPLOY_DIR_IMAGE}"

export IMAGE_BASENAME = "hdsatelit-image"

inherit image
inherit hds-usb-image

# Completarile in imagine (0.7.5, 13.11.2026; STADIU-CPL.md): radacina creste cu 78-87 MiB (SF8008 0.7.4: 497,9 + 78,1 MiB).
# Clasele HiSilicon ale producatorilor (octagon-hisi.inc, uclan-hisi.inc, amiko-hisi.inc, gigablue-mv200.inc: 624288 KB;
# dinobot-emmc*.inc, airdigital-arm.inc: 589824 KB) fac ext4-ul userdata/linuxrootfs1 al imaginii de recuperare la marime
# fixa (octagon-emmc_image.bbclass); pe receptor sloturile sunt dosare in partitia userdata (3580 MiB pe SF8008 MINI, 7000
# MiB pe SF8008, Ustym, TRIO, V10). Unde completarile sunt in imagine, minimul devine 768 MiB, ca la GigaBlue TRIO 4K (deja
# in 0.7.4 publicata): ~124 MiB liberi pe SF8008, ~205 pe V20. Atribuire, nu python () {}: functia anonima din image.bbclass
# a pus deja valoarea in comanda (74b160cfc). Suprascrierile pe masina de mai sus (gbtrio4k, h17, h9combo, h9combose) raman.
HDS_ROOTFS_MINIM_MASINA := "${IMAGE_ROOTFS_SIZE}"
IMAGE_ROOTFS_SIZE = "${@'786432' if d.getVar('HDS_COMPLETARI_IN_IMAGINE') == '1' and (d.getVar('HDS_ROOTFS_MINIM_MASINA') or '').strip() in ('589824', '624288') else d.getVar('HDS_ROOTFS_MINIM_MASINA')}"

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
		# FTP are comutatorul lui (hds-ftp-retea-locala.conf, hdsatelit-ssh r4), cu aceleasi reguli ca la SSH
		regula_ftp=${IMAGE_ROOTFS}${sysconfdir}/security/hds-ftp-retea-locala.conf
		[ -f "$regula_ftp" ] || bbfatal "paza ftp: lipseste $regula_ftp"
		[ "$(grep -v '^#' "$regula_ftp" | grep . | tail -n 1)" = "+ : ALL : ALL" ] || bbfatal "paza ftp: $regula_ftp nu trimite pe ceilalti la parola"
		if grep '^-' "$regula_ftp" | grep -qw ALL; then
			bbfatal "paza ftp: $regula_ftp lasa fara parola adrese din afara casei"
		fi
		[ "$(grep -c '^-' "$regula_ftp")" -le 1 ] || bbfatal "paza ftp: $regula_ftp are mai multe reguli -"
		if grep '^-' "$regula_ftp" | grep -qvE '^- : root : 127\.0\.0\.0/8 10\.0\.0\.0/8 172\.16\.0\.0/12 192\.168\.0\.0/16 169\.254\.0\.0/16 '; then
			bbfatal "paza ftp: regula FTP fara parola nu e a retelelor de acasa"
		fi
		grep -q 'accessfile=/etc/security/hds-ftp-retea-locala.conf' "$pamftp" || bbfatal "paza ftp: /etc/pam.d/vsftpd fara comutatorul FTP"
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

# Paza imaginii mici (0.7.4, 10.11.2026; lucru-sesiune/oe-60/imagine-mica/PROIECT-IMAGINE-MICA.md, riscul 5): ce s-a
# scos din imagine nu are voie sa revina prin dependintele altui pachet (requests aducea chardet, outcome aducea pytest),
# iar limbile si afisajul color trebuie sa fie exact cele hotarate. Citeste starea opkg si dosarele radacinii facute:
# - niciun pachet din HDS_SCOASE_DIN_IMAGINE si niciun hds-ocr-* (recunoasterea textului vine din feed, la cerere);
# - cataloagele din /usr/share/enigma2/po: exact HDS_LIMBI_NATIVE (conf/distro/hdsatelit.conf), fara niciun pachet
#   enigma2-hdsatelit-po-*; pe hdsflashmic exact romana si engleza (pachetele po-ro si po-en);
# - /usr/share/enigma2/HDSatelit/afisaj-color numai unde HDS_AFISAJ_COLOR = 1.
HDS_SCOASE_DIN_IMAGINE = "python3-pytest python3-pygments python3-chardet hds-ocr hds-ocr-modele"
python hds_paza_imagine_mica () {
    import os
    rad = d.getVar('IMAGE_ROOTFS')
    flashmic = 'hdsflashmic' in (d.getVar('OVERRIDES') or '').split(':')
    instalate = set()
    pachet = None
    with open(os.path.join(rad, 'var', 'lib', 'opkg', 'status'), encoding='utf-8', errors='replace') as f:
        for rand in f:
            if rand.startswith('Package:'):
                pachet = rand.split(':', 1)[1].strip()
            elif rand.startswith('Status:') and pachet and rand.split()[-1:] == ['installed']:
                instalate.add(pachet)
    if not instalate:
        bb.fatal('paza imaginii mici: starea opkg din radacina nu are niciun pachet instalat')
    # completarile in imagine (0.7.5, HDS_COMPLETARI_IN_IMAGINE): limbile din feed, OCR si driverele din feed TREBUIE sa fie
    # in imagine; pe celelalte masini, ca inainte, nu au voie
    # pe Solo SE prin USB / chkroot (hdsusb) flashmic e fals si HDS_COMPLETARI_IN_IMAGINE e 1: cele 30 de limbi si driverele,
    # fara OCR (MIPS); pe Solo SE NAND (hdsflashmic) nimic din completari
    completari = d.getVar('HDS_COMPLETARI_IN_IMAGINE') == '1' and not flashmic
    ocr_ok = completari and not (d.getVar('TARGET_ARCH') or '').startswith('mips')
    scoase = sorted(p for p in instalate if (p in (d.getVar('HDS_SCOASE_DIN_IMAGINE') or '').split()
        or p.startswith('hds-ocr-')) and not (ocr_ok and p.startswith('hds-ocr')))
    if scoase:
        bb.fatal('paza imaginii mici: pachete scoase din imagine au revenit (prin dependintele altora): %s' % ' '.join(scoase))
    po = os.path.join(rad, 'usr', 'share', 'enigma2', 'po')
    cataloage = sorted(n for n in (os.listdir(po) if os.path.isdir(po) else [])
        if os.path.isfile(os.path.join(po, n, 'LC_MESSAGES', 'enigma2.mo')))
    pachete_po = sorted(p for p in instalate if p.startswith('enigma2-hdsatelit-po-'))
    if flashmic:
        asteptate, asteptate_po = ['en', 'ro'], ['enigma2-hdsatelit-po-en', 'enigma2-hdsatelit-po-ro']
    else:
        asteptate, asteptate_po = sorted((d.getVar('HDS_LIMBI_NATIVE') or '').split()), []
    if completari:
        # toate limbile: cele native in enigma2-hdsatelit, celelalte HDS_LIMBI_FEED_NUMAR in pachetele lor (po-toate exista
        # numai pe hdsflashmic)
        cu_pachet = sorted(p[len('enigma2-hdsatelit-po-'):] for p in pachete_po)
        numar = int(d.getVar('HDS_LIMBI_FEED_NUMAR') or '0')
        if len(cu_pachet) != numar:
            bb.fatal('paza imaginii mici: completarile in imagine cer %d pachete de limbi, sunt: %s' % (numar,
                ' '.join(pachete_po) or '-'))
        asteptate = sorted(set(asteptate) | set(cu_pachet))
        asteptate_po = pachete_po
        lipsa = [p for p in (['hds-ocr', 'hds-ocr-modele'] if ocr_ok else []) + ['hdsatelit-drivere-feed'] if p not in instalate]
        if lipsa or (ocr_ok and not os.access(os.path.join(rad, 'usr', 'bin', 'hds-ocr'), os.X_OK)):
            bb.fatal('paza imaginii mici: completarile in imagine, dar lipsesc: %s' % (' '.join(lipsa) or 'usr/bin/hds-ocr'))
    if not asteptate or cataloage != asteptate:
        bb.fatal('paza imaginii mici: limbile din imagine sunt %s, asteptate %s' % (' '.join(cataloage) or '-',
            ' '.join(asteptate) or '-'))
    if pachete_po != asteptate_po:
        bb.fatal('paza imaginii mici: pachetele limbilor din imagine sunt %s, asteptate %s' % (' '.join(pachete_po) or '-',
            ' '.join(asteptate_po) or '-'))
    afisaj = os.path.isdir(os.path.join(rad, 'usr', 'share', 'enigma2', 'HDSatelit', 'afisaj-color'))
    if afisaj != (d.getVar('HDS_AFISAJ_COLOR') == '1'):
        bb.fatal('paza imaginii mici: afisajul color %s in imagine, HDS_AFISAJ_COLOR=%s' % ('este' if afisaj else 'lipseste',
            d.getVar('HDS_AFISAJ_COLOR')))
    bb.note('paza imaginii mici: %d limbi in imagine, afisajul color %s, completarile %s, fara %s' % (len(cataloage),
        'da' if afisaj else 'nu', 'in imagine' if completari else 'din feed', ' '.join(p for p in
        (d.getVar('HDS_SCOASE_DIN_IMAGINE') or '').split() if not (ocr_ok and p.startswith('hds-ocr')))))
}
ROOTFS_POSTPROCESS_COMMAND:append = " hds_paza_imagine_mica"

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
	stocare?:HDS_MODEL_STOCARE model_id?:HDS_MODEL_ID"

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
    # model_id= (VU1, 12.11.2026; forma de pe modele-noi-unelte-071): placile al caror tip din driver e comun mai
    # multor modele (Vu+ Duo 4K Lite: boxtype=vuplus, scris la pornire de vuplus-ddbootup) cer modelul exact
    if 'model_id' in reguli and not re.fullmatch(r'[a-z0-9]+', reguli['model_id']):
        bb.fatal('paza de model: model_id trebuie sa aiba numai litere mici si cifre')
    identitati = {'vuduo4klite': 'duo4klite'}
    identitati['gbquad4kpro'] = 'gbquad4kpro'  # GigaBlue UHD Quad 4K Pro (ALFA, 12.11.2026): gbmodel scris de gigablue-ddbootup
    identitati['gbx34k'] = 'gbx34k'  # GigaBlue UHD X3 4K (MGX, 12.11.2026): gbmodel scris de driver si de gigablue-ddbootup
    if mb in identitati and reguli.get('model_id') != identitati[mb]:
        bb.fatal('paza de model: %s cere model_id=%s' % (mb, identitati[mb]))
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
IMAGEDIR:vuultimo4k = "vuplus/${UPDATE_DIR}"
IMAGEDIR:vuuno4kse = "vuplus/${UPDATE_DIR}"
IMAGEDIR:vuzero4k = "vuplus/${UPDATE_DIR}"
IMAGEDIR:vuduo4k = "vuplus/${UPDATE_DIR}"
IMAGEDIR:vuduo4kse = "vuplus/${UPDATE_DIR}"
# Vu+ Duo 4K Lite (VU1): stratul meta-vuplusde nu are UPDATE_DIR; vuplus.inc al lui da IMAGEDIR ?= "vuplus/duo4klite",
# dosarul pe care il cauta incarcatorul pe stick (si imaginea oficiala VU+ oe-20261009)
IMAGEDIR:vuduo4klite = "vuplus/duo4klite"
# GigaBlue UHD Quad 4K Pro (ALFA): aceeasi masina OE ca Quad 4K (gb7252), cu dosarul lui pe stick (IMAGEDIR din
# gigablue-oem.inc, randul gbquad4kpro)
IMAGEDIR:gbquad4kpro = "gigablue/quad4kpro"
# GigaBlue UHD X3 4K (MGX): dosarul de pe stick din gigablue-oem.inc, randul gbx34k
IMAGEDIR:gbx34k = "gigablue/x34k"
# Edision OS mio 4K+, OS mini 4K, OS mio 4K (MED, 13.11.2026): dosarul de pe stick = numele masinii (IMAGEDIR din
# meta-edision/conf/machine/include/edision.inc), ca arhivele OE-Alliance publice
IMAGEDIR:osmio4kplus = "osmio4kplus"
IMAGEDIR:osmini4k = "osmini4k"
IMAGEDIR:osmio4k = "osmio4k"
IMAGEDIR:hd51 = "hd51"
# Zgemma H17 COMBO (MH7): zgemma/h17 (IMAGEDIR din airdigital-oem.inc, randul zgemmah17combo; H17 TWIN e aceeasi masina h17
# cu alt MACHINEBUILD si alt dosar, zgemma/h17twin, deci suprascrierea e pe MACHINEBUILD; imaginile publice OE-Alliance
# 6.0 au _multi.zip cu zgemma/h17/{imageversion,kernel.bin,rootfs.tar.bz2} si _recovery_emmc.zip cu zgemma/h17/disk.img)
IMAGEDIR:zgemmah17combo = "zgemma/h17"
# Dreambox DM900 si DM920 (MDM dm900 imagedir): IMAGE_CMD:tar:prepend din dm900.conf / dm920.conf face
# ${IMAGE_NAME}_mmc.zip cu ${IMAGEDIR}/{kernel.bin,rootfs.tar.bz2,imageversion} si sterge apoi dosarul; dosarul ramane al
# masinii, ca in imaginile OE-Alliance pentru aceste aparate (dm900/, dm920/). In Rescue Mode se urca rootfs.tar.bz2 (Dream
# flash-tarball il desface pe mmcblk0p2 si ruleaza postinst-ul kernel-image, care scrie /boot/zImage pe mmcblk0p1).
IMAGEDIR:dm900 = "dm900"
IMAGEDIR:dm920 = "dm920"
# Vu+ Solo SE (lotul mips-solose, 06.11.2026): incarcatorul CFE cauta imaginea pe stick numai in vuplus/solose
# (UPDATE_DIR din vusolose.conf), deci zip-ul _usb.zip pastreaza dosarul masinii.
IMAGEDIR:vusolose = "vuplus/${UPDATE_DIR}"
# Zgemma Star S (MSS, 12.11.2026; masina sh1, meta-airdigital): zgemma/sh1 (IMAGEDIR din airdigital-oem.inc; imaginile
# publice OE-Alliance 6.0 pentru sh1 au _usb.zip cu zgemma/sh1/{kernel.bin,rootfs.bin,splash.bin,imageversion,noforce})
IMAGEDIR:sh1 = "zgemma/sh1"
# Vu+ Solo2 (MS2, 12.11.2026): la fel, vuplus/solo2 (UPDATE_DIR din vusolo2.conf)
IMAGEDIR:vusolo2 = "vuplus/${UPDATE_DIR}"
# Vu+ Zero (MVZ, 12.11.2026): la fel, vuplus/zero (UPDATE_DIR din vuzero.conf)
IMAGEDIR:vuzero = "vuplus/${UPDATE_DIR}"
# Zgemma H9 COMBO si H9 TWIN (MH9): meniul de recuperare al producatorului cauta pe stick dosarul h9combo
# (IMAGEDIR din airdigital-oem.inc; airdigital-emmc.inc face ${IMAGE_NAME}_multi.zip cu h9combo/{uImage,rootfs.tar.bz2,
# imageversion,force_h9combo_READ.ME} si unforce_h9combo.txt)
IMAGEDIR:h9combo = "h9combo"
# Novaler Multibox 4K PRO (MNP): meniul de recuperare al producatorului cauta pe stick dosarul multiboxpro (IMAGEDIR din
# maxytec-oem.inc; maxytec-hisil-3798mv200.inc face ${IMAGE_NAME}_multi.zip cu multiboxpro/{uImage,rootfs.tar.bz2,
# imageversion,force_multiboxpro_READ.ME} si unforce_multiboxpro.txt)
IMAGEDIR:multiboxpro = "multiboxpro"
# Novaler Multibox 4K SE (MNS, 12.11.2026; masina multiboxse, MACHINEBUILD novaler4kse, meta-maxytec): meniul de
# recuperare al producatorului cauta pe stick dosarul multiboxse (IMAGEDIR din maxytec-oem.inc; IMAGE_CMD:maxytecfastboot8gb
# din maxytec-hisil-3798mv200.inc face ${IMAGE_NAME}_multi.zip cu multiboxse/{uImage,rootfs.tar.bz2,imageversion,
# force_multiboxse_READ.ME} si unforce_multiboxse.txt).
IMAGEDIR:multiboxse = "multiboxse"
# multiboxse.conf si maxytec-hisil-3798mv200.inc scriu MTD_ROOTFS = mmcblk0p20, dar p20 e linuxkernel2 (bootargs-ul
# producatorului, multiboxse-bootargs-20221130, sha256 107436ce: ...16M(linuxkernel1),16M(linuxkernel2),...,-(userdata)),
# iar pornirea scrisa de clasa masinii (maxytec-fastboot8gb_image.bbclass, STARTUP si STARTUP_LINUX_1) e
# root=/dev/mmcblk0p23 rootsubdir=linuxrootfs1 kernel=/dev/mmcblk0p19. Garda compara MTD_ROOTFS cu rootfs_part, deci aici
# locul real; clasa masinii nu citeste MTD_ROOTFS (p23 e scris de mana in ea). enigma.info (alta reteta) ramane cu p20, ca
# la imaginile publice ale masinii.
MTD_ROOTFS:multiboxse = "mmcblk0p23"
# AB-COM PULSe 4K si PULSe 4K MINI (MPU, 12.11.2026): meniul de recuperare al producatorului cauta pe stick dosarul
# masinii (IMAGEDIR = "${MACHINE}" in pulse4k.conf si pulse4kmini.conf; IMAGE_CMD:abfastboot8gb:append din
# abcom-hisil-3798mv200.inc face ${IMAGE_NAME}_mmc.zip cu pulse4k/{uImage,rootfs.tar.bz2,imageversion,
# force_pulse4k_READ.ME} si unforce_pulse4k.txt; la fel pulse4kmini)
IMAGEDIR:pulse4k = "pulse4k"
IMAGEDIR:pulse4kmini = "pulse4kmini"
# Zgemma H9 TWIN SE si H9 COMBO SE (MHS): meniul de recuperare cauta dosarul h9combose (imaginile publice OE-Alliance 6.0
# pentru zgemmah9twinse: h9combose/{uImage,rootfs.tar.bz2,imageversion,force_h9combose_READ.ME} si unforce_h9combose.txt)
IMAGEDIR:h9combose = "h9combose"

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
	[ -z "${HDS_MODEL_ID}" ] || printf 'model_id=%s\n' "${HDS_MODEL_ID}"
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
	[ -z "${HDS_MODEL_ID}" ] || printf 'model_id=%s\n' "${HDS_MODEL_ID}"
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
	[ -z "${HDS_MODEL_ID}" ] || printf 'model_id=%s\n' "${HDS_MODEL_ID}"
}

# Novaler Multibox 4K PRO (MNP, 12.11.2026): aceeasi asezare ca la SF8008 si H9 (linuxkernel1 si userdata, bootargs-ul
# producatorului), deci exact corpul functiei sf8008 de mai sus.
hds_reguli_model:multiboxpro() {
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
	[ -z "${HDS_MODEL_ID}" ] || printf 'model_id=%s\n' "${HDS_MODEL_ID}"
}

# Zgemma H9 COMBO si H9 TWIN (MH9, 12.11.2026): aceeasi asezare ca la SF8008 si V10 (linuxkernel1 si userdata, bootargs-ul
# producatorului), deci exact corpul functiei sf8008 de mai sus.
hds_reguli_model:h9combo() {
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
	[ -z "${HDS_MODEL_ID}" ] || printf 'model_id=%s\n' "${HDS_MODEL_ID}"
}

# Novaler Multibox 4K SE (MNS, 12.11.2026): aceeasi asezare ca la SF8008, V10 si H9 COMBO (linuxkernel1 si userdata,
# bootargs-ul producatorului), deci exact corpul functiei sf8008.
hds_reguli_model:multiboxse() {
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
	[ -z "${HDS_MODEL_ID}" ] || printf 'model_id=%s\n' "${HDS_MODEL_ID}"
}

# AB-COM PULSe 4K si PULSe 4K MINI (MPU, 12.11.2026): aceeasi asezare ca la SF8008 si H9 COMBO (linuxkernel1 si userdata,
# bootargs-ul producatorului), deci exact corpul functiei sf8008 de mai sus, pentru fiecare masina.
hds_reguli_model:pulse4k() {
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
	[ -z "${HDS_MODEL_ID}" ] || printf 'model_id=%s\n' "${HDS_MODEL_ID}"
}
hds_reguli_model:pulse4kmini() {
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
	[ -z "${HDS_MODEL_ID}" ] || printf 'model_id=%s\n' "${HDS_MODEL_ID}"
}

# Zgemma H9 TWIN SE si H9 COMBO SE (MHS, 12.11.2026): aceeasi asezare ca la H9 COMBO, SF8008 si V10 (linuxkernel1 si
# userdata, bootargs-ul producatorului), deci exact corpul functiei sf8008.
hds_reguli_model:h9combose() {
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
	[ -z "${HDS_MODEL_ID}" ] || printf 'model_id=%s\n' "${HDS_MODEL_ID}"
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
	[ -z "${HDS_MODEL_ID}" ] || printf 'model_id=%s\n' "${HDS_MODEL_ID}"
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
	[ -z "${HDS_MODEL_ID}" ] || printf 'model_id=%s\n' "${HDS_MODEL_ID}"
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
	[ -z "${HDS_MODEL_ID}" ] || printf 'model_id=%s\n' "${HDS_MODEL_ID}"
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

# Data constructiei pe fisierele din care listele de pornire multipla ale altor imagini scot data (papuga, Satedu
# t=32518 #190354, 08.11.2026: „W bootmenu data wydania to 2018-03-09”). reproducible_final_image_task (image.bbclass,
# IMAGE_PREPROCESS_COMMAND:append) pune pe TOATE fisierele REPRODUCIBLE_TIMESTAMP_ROOTFS, implicit 1520598896 =
# 2018-03-09 12:34:56 UTC. Listele care nu citesc enigma.info (sau citesc o forma veche a lui) iau data cea mai noua dintre
# usr/bin/enigma2, var/lib/opkg/status si usr/share/bootlogo.mvi (mtime), deci aratau 2018-03-09. Numai cele trei fisiere
# primesc data din compiledate (aceeasi zi ca enigma.info si imagebuild din /etc/image-version); restul ramane
# reproductibil. Ruleaza dupa reproducible_final_image_task (acelasi :append, citit dupa inherit image).
hds_data_fisiere_imagine() {
	z="${DATE}"
	data="$(echo "$z" | cut -c1-4)-$(echo "$z" | cut -c5-6)-$(echo "$z" | cut -c7-8) 12:00:00 UTC"
	for f in ${bindir}/enigma2 ${localstatedir}/lib/opkg/status ${datadir}/bootlogo.mvi; do
		[ -e "${IMAGE_ROOTFS}$f" ] || [ -L "${IMAGE_ROOTFS}$f" ] || continue
		touch -h -d "$data" "${IMAGE_ROOTFS}$f"
	done
	bbnote "hds_data_fisiere_imagine: enigma2, opkg/status, bootlogo.mvi cu data $data"
}
hds_data_fisiere_imagine[vardepsexclude] += "DATE"
IMAGE_PREPROCESS_COMMAND:append = " hds_data_fisiere_imagine "

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
HDS_MARCAJ_ZIP:vuultimo4k = "${IMAGE_NAME}_usb.zip"
HDS_MARCAJ_ZIP:vuuno4kse = "${IMAGE_NAME}_usb.zip"
HDS_MARCAJ_ZIP:vuzero4k = "${IMAGE_NAME}_usb.zip"
HDS_MARCAJ_ZIP:vuduo4k = "${IMAGE_NAME}_usb.zip"
HDS_MARCAJ_ZIP:vuduo4kse = "${IMAGE_NAME}_usb.zip"
HDS_MARCAJ_ZIP:vuduo4klite = "${IMAGE_NAME}_usb.zip"
HDS_MARCAJ_ZIP:gbquad4kpro = "${IMAGE_NAME}_usb.zip"
HDS_MARCAJ_ZIP:gbx34k = "${IMAGE_NAME}_usb.zip"
HDS_MARCAJ_ZIP:osmio4kplus = "${IMAGE_NAME}_usb.zip"
HDS_MARCAJ_ZIP:osmini4k = "${IMAGE_NAME}_usb.zip"
HDS_MARCAJ_ZIP:osmio4k = "${IMAGE_NAME}_usb.zip"
# Sigla incarcatorului Vu+: vuplus.inc pune trasatura bootsplash, iar IMAGE_CMD:tar:prepend al masinii copiaza
# ${DEPLOY_DIR_IMAGE}/splash_cfe_auto.bin (BOOTLOGO_FILENAME) in dosarul de pe stick ca splash_auto.bin. Fisierul il face
# sigla distributiei (reteta ei de sigla, do_deploy, splash480.bmp pe Vu+); hdsatelit-bootlogo nu o face, iar
# prima constructie Solo 4K a cazut acolo (06.11, 12:04). Al nostru: files/hds-splash-vuplus.bmp, BMP Windows 3.x de
# 720 x 480 x 24, aceeasi forma si marime (1036854 o) ca splash480.bmp, facut din backdrop.mvi (sigla HD Satelit) cu
# ffmpeg -f mpegvideo -i backdrop.mvi -frames:v 1 -vf scale=720:480 -pix_fmt bgr24. Prepend-ul retetei se pune inaintea
# celui al masinii (masina se citeste prima), deci fisierul exista cand il copiaza masina.
HDS_SPLASH_VUPLUS := "${THISDIR}/files/hds-splash-vuplus.bmp"
IMAGE_CMD:tar:prepend:vusolo4k = "install -m 0644 ${HDS_SPLASH_VUPLUS} ${DEPLOY_DIR_IMAGE}/splash_cfe_auto.bin; "
IMAGE_CMD:tar:prepend:vuultimo4k = "install -m 0644 ${HDS_SPLASH_VUPLUS} ${DEPLOY_DIR_IMAGE}/splash_cfe_auto.bin; "
IMAGE_CMD:tar:prepend:vuuno4kse = "install -m 0644 ${HDS_SPLASH_VUPLUS} ${DEPLOY_DIR_IMAGE}/splash_cfe_auto.bin; "
IMAGE_CMD:tar:prepend:vuzero4k = "install -m 0644 ${HDS_SPLASH_VUPLUS} ${DEPLOY_DIR_IMAGE}/splash_cfe_auto.bin; "
IMAGE_CMD:tar:prepend:vuduo4k = "install -m 0644 ${HDS_SPLASH_VUPLUS} ${DEPLOY_DIR_IMAGE}/splash_cfe_auto.bin; "
IMAGE_CMD:tar:prepend:vuduo4kse = "install -m 0644 ${HDS_SPLASH_VUPLUS} ${DEPLOY_DIR_IMAGE}/splash_cfe_auto.bin; "
IMAGE_CMD:tar:append:vusolo4k = "; hds_marcaj_model_zip; "
IMAGE_CMD:tar:append:vuultimo4k = "; hds_marcaj_model_zip; "
IMAGE_CMD:tar:append:vuuno4kse = "; hds_marcaj_model_zip; "
IMAGE_CMD:tar:append:vuzero4k = "; hds_marcaj_model_zip; "
IMAGE_CMD:tar:append:vuduo4k = "; hds_marcaj_model_zip; "
IMAGE_CMD:tar:append:vuduo4kse = "; hds_marcaj_model_zip; "
# Vu+ Duo 4K Lite (VU1, 12.11.2026): IMAGE_CMD:tar:prepend din meta-vuplusde/conf/machine/include/vuplus.inc copiaza
# sigla din ${DEPLOY_DIR_IMAGE}/splash.bin (BOOTLOGO_FILENAME, alt nume decat la celelalte Vu+ 4K): a noastra,
# files/hds-splash-vuduo4klite.bmp, BMP Windows 3.x 720 x 540 x 24 (1166454 o, ca splash_auto.bin al imaginii
# oficiale VU+), facuta din hds-splash-vuplus.bmp. Acelasi prepend pune pe stick si boot.bin (incarcatorul),
# gpt.bin (tabela de partitii) si rescue.bin, din vuplus-initrd-cfe-vuduo4klite; imaginea obisnuita VU+ NU le are
# (numai imaginea FACTORY), deci le scoatem din zip inainte de marcaj. initrd.bin ramane: e acelasi fisier ca
# initrd_vu.bin din arhiva VU+ (sha256 ede431d8, STADIU-VU1-CI-UNICABLE-DUO4KLITE.md).
HDS_SPLASH_VUDUO4KLITE := "${THISDIR}/files/hds-splash-vuduo4klite.bmp"
IMAGE_CMD:tar:prepend:vuduo4klite = "install -m 0644 ${HDS_SPLASH_VUDUO4KLITE} ${DEPLOY_DIR_IMAGE}/splash.bin; "
IMAGE_CMD:tar:append:vuduo4klite = "; zip -d ${DEPLOY_DIR_IMAGE}/${IMAGE_NAME}_usb.zip ${IMAGEDIR}/boot.bin ${IMAGEDIR}/gpt.bin ${IMAGEDIR}/rescue.bin; hds_marcaj_model_zip; "
# GigaBlue UHD Quad 4K Pro (ALFA, 12.11.2026): IMAGE_CMD:tar:prepend din meta-gigablue/conf/machine/include/gigablue-arm.inc
# face ${IMAGE_NAME}_usb.zip cu ${IMAGEDIR}/{kernel.bin,rootfs.tar.bz2,imageversion,splash.bin,boot.bin,gpt.bin,rescue.bin,
# bolt_20250625.bin} (incarcatorul, tabela si salvarea vin din gigablue-initrd-cfe-gbquad4kpro, ale producatorului pentru
# aceasta placa) si sterge apoi *.manifest din deploy. Spre deosebire de Lite (placa GigaBlue cu imaginea VU+, unde VU+ pune
# fisierele de pornire numai in imaginea FACTORY), aici arhiva ramane ca in OE-Alliance: pe GigaBlue ARM ele sunt in orice
# imagine de stick. Sigla incarcatorului (BOOTLOGO_FILENAME splash.bin): a noastra, files/hds-splash-gigablue.bmp, BMP
# Windows 3.x 720 x 576 x 24 (1244214 o, forma siglelor GigaBlue), din profilul alfa 0.7.1 (8d02d6da5).
HDS_SPLASH_GIGABLUE := "${THISDIR}/files/hds-splash-gigablue.bmp"
IMAGE_CMD:tar:prepend:gbquad4kpro = "install -m 0644 ${HDS_SPLASH_GIGABLUE} ${DEPLOY_DIR_IMAGE}/splash.bin; "
IMAGE_CMD:tar:append:gbquad4kpro = "; hds_marcaj_model_zip; "
# GigaBlue UHD X3 4K (MGX, 12.11.2026): acelasi IMAGE_CMD:tar:prepend din gigablue-arm.inc, deci acelasi zip _usb.zip cu
# gigablue/x34k/{kernel.bin,rootfs.tar.bz2,imageversion,splash.bin,boot.bin,gpt.bin,rescue.bin} (fara bolt_*.bin: masina
# gb72604 nu are trasatura bolt), ca arhivele OE-Alliance publice pentru gbx34k; sigla noastra, ca la Quad 4K Pro
IMAGE_CMD:tar:prepend:gbx34k = "install -m 0644 ${HDS_SPLASH_GIGABLUE} ${DEPLOY_DIR_IMAGE}/splash.bin; "
IMAGE_CMD:tar:append:gbx34k = "; hds_marcaj_model_zip; "
# AX HD51 (masina hd51): IMAGE_CMD:hdemmc:append din gfutures-arm.inc face ${IMAGE_NAME}_multi.zip cu
# ${IMAGEDIR}/{imageversion,kernel.bin,rootfs.tar.bz2} (si _recovery_emmc.zip cu disk.img, pe care nu-l atingem).
HDS_MARCAJ_ZIP:hd51 = "${IMAGE_NAME}_multi.zip"
# Dreambox DM900 si DM920 (MDM dm900 marcaj): zip-ul _mmc.zip (HDS_MARCAJ_ZIP implicit) il inchide IMAGE_CMD:tar:prepend al
# masinii, inainte de comanda tar a lui image_types.bbclass, ca pe Vu+: deci marcajul vine in IMAGE_CMD:tar:append, cu „;”.
IMAGE_CMD:tar:append:dm900 = "; hds_marcaj_model_zip; "
IMAGE_CMD:tar:append:dm920 = "; hds_marcaj_model_zip; "
IMAGE_CMD:hdemmc:append = " hds_marcaj_model_zip; "
# Zgemma H17 COMBO (MH7): IMAGE_CMD:airdigitalemmc:append din airdigital-arm.inc (meta-airdigital) face
# ${IMAGE_NAME}_recovery_emmc.zip (disk.img, nu-l atingem) si ${IMAGE_NAME}_multi.zip cu ${IMAGEDIR}/{imageversion,
# kernel.bin,rootfs.tar.bz2}, apoi sterge dosarul; randul retetei vine dupa al masinii, deci marcajul intra in zip-ul inchis.
HDS_MARCAJ_ZIP:zgemmah17combo = "${IMAGE_NAME}_multi.zip"
IMAGE_CMD:airdigitalemmc:append = " hds_marcaj_model_zip; "
# Zgemma H9 COMBO si H9 TWIN (MH9): IMAGE_CMD:zgemmafastboot8gb:append din airdigital-emmc.inc (meta-airdigital) face
# ${IMAGE_NAME}_recovery_emmc.zip (al producatorului, nu-l atingem) si ${IMAGE_NAME}_multi.zip cu
# ${IMAGEDIR}/{uImage,rootfs.tar.bz2,imageversion}; randul retetei vine dupa al masinii, deci marcajul intra in zip-ul inchis.
HDS_MARCAJ_ZIP:h9combo = "${IMAGE_NAME}_multi.zip"
# Novaler Multibox 4K SE (MNS): IMAGE_CMD:maxytecfastboot8gb:append din maxytec-hisil-3798mv200.inc (meta-maxytec) face
# ${IMAGE_NAME}_recovery_emmc.zip (al producatorului, nu-l atingem) si ${IMAGE_NAME}_multi.zip cu
# ${IMAGEDIR}/{uImage,rootfs.tar.bz2,imageversion}; marcajul il pune randul comun IMAGE_CMD:maxytecfastboot8gb:append.
HDS_MARCAJ_ZIP:multiboxse = "${IMAGE_NAME}_multi.zip"
# Zgemma H9 TWIN SE si H9 COMBO SE (MHS): aceeasi ${IMAGE_NAME}_multi.zip din airdigital-emmc.inc
HDS_MARCAJ_ZIP:h9combose = "${IMAGE_NAME}_multi.zip"
IMAGE_CMD:zgemmafastboot8gb:append = " hds_marcaj_model_zip; "
# Novaler Multibox 4K PRO (MNP): IMAGE_CMD:maxytecfastboot8gb:append din maxytec-hisil-3798mv200.inc (meta-maxytec) face
# ${IMAGE_NAME}_recovery_emmc.zip (al producatorului, nu-l atingem) si ${IMAGE_NAME}_multi.zip cu
# ${IMAGEDIR}/{uImage,rootfs.tar.bz2,imageversion}; randul retetei vine dupa al masinii, deci marcajul intra in zip-ul inchis.
HDS_MARCAJ_ZIP:multiboxpro = "${IMAGE_NAME}_multi.zip"
# Familia maxytec (Novaler Multibox 4K PRO si 4K SE): randul comun, o singura data
IMAGE_CMD:maxytecfastboot8gb:append = " hds_marcaj_model_zip; "
# AB-COM PULSe 4K si PULSe 4K MINI (MPU): IMAGE_CMD:abfastboot8gb:append din abcom-hisil-3798mv200.inc (meta-abcom) face
# ${IMAGE_NAME}_recovery_emmc.zip (al producatorului, nu-l atingem) si ${IMAGE_NAME}_mmc.zip cu
# ${IMAGEDIR}/{uImage,rootfs.tar.bz2,imageversion}; randul retetei vine dupa al masinii, deci marcajul intra in zip-ul inchis.
IMAGE_CMD:abfastboot8gb:append = " hds_marcaj_model_zip; "
# Edision OS mio 4K+, OS mini 4K, OS mio 4K (MED, 13.11.2026): tipul de imagine al masinii e emmcimg
# (meta-edision/classes/osmio4k-emmcimg.bbclass; IMAGE_CMD:emmcimg:append din edision-arm.inc face
# ${IMAGE_NAME}_recovery_emmc.zip, pe care nu-l atingem, si ${IMAGE_NAME}_usb.zip cu ${IMAGEDIR}/{kernel.bin,
# rootfs.tar.bz2,imageversion}, apoi sterge dosarul); randul retetei vine dupa al masinii, deci marcajul intra in
# zip-ul inchis. emmcimg exista numai in meta-edision. splash.bin il copiaza masina numai in arhiva de recuperare;
# trebuie sa existe in deploy, altfel comanda cade: sigla noastra, ca la GigaBlue.
IMAGE_CMD:emmcimg:prepend:osmio4kplus = "install -m 0644 ${HDS_SPLASH_GIGABLUE} ${DEPLOY_DIR_IMAGE}/splash.bin; "
IMAGE_CMD:emmcimg:prepend:osmini4k = "install -m 0644 ${HDS_SPLASH_GIGABLUE} ${DEPLOY_DIR_IMAGE}/splash.bin; "
IMAGE_CMD:emmcimg:prepend:osmio4k = "install -m 0644 ${HDS_SPLASH_GIGABLUE} ${DEPLOY_DIR_IMAGE}/splash.bin; "
IMAGE_CMD:emmcimg:append = " hds_marcaj_model_zip; "

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
# Zgemma Star S (MSS): IMAGE_CMD:ubi:append din airdigital-mipsel.inc face ${IMAGE_NAME}_usb.zip cu zgemma/sh1 (kernel.bin =
# vmlinux gzip, rootfs.bin = UBI, splash.bin, imageversion, noforce) si sterge apoi dosarul; randul nostru vine dupa
HDS_MARCAJ_ZIP:sh1 = "${IMAGE_NAME}_usb.zip"
# Vu+ Solo2: vusolo2.conf face acelasi ${IMAGE_NAME}_usb.zip, cu reboot.update in loc de force.update
HDS_MARCAJ_ZIP:vusolo2 = "${IMAGE_NAME}_usb.zip"
# Vu+ Zero: vuzero.conf face acelasi ${IMAGE_NAME}_usb.zip, cu force.update (ca Solo SE)
HDS_MARCAJ_ZIP:vuzero = "${IMAGE_NAME}_usb.zip"
IMAGE_CMD:ubi:append = " hds_marcaj_model_zip; hds_paza_marime_flash_mic; "
# - sigla incarcatorului CFE: vuplus.inc pune trasatura bootsplash, iar IMAGE_CMD:ubi:append din vusolose.conf copiaza
#   ${DEPLOY_DIR_IMAGE}/splash_cfe_auto.bin (BOOTLOGO_FILENAME) in vuplus/solose. Fisierul il face sigla distributiei (la
#   reteta ei de sigla, do_deploy: splash480.bmp pe vusolose, ca pe vusolo4k); hdsatelit-bootlogo nu il face, iar prima
#   constructie Solo SE a cazut acolo (06.11.2026, 13:42: cp ... splash_cfe_auto.bin: No such file). Al nostru:
#   files/hds-splash-vuplus.bmp, BMP 720 x 480 x 24 (1036854 o, ca splash480.bmp) facut din backdrop.mvi (sigla HD Satelit),
#   acelasi fisier ca la lotul vuplus4k (Solo 4K, Uno 4K SE, Duo 4K; HDS_SPLASH_VUPLUS de mai sus). Prepend: intra
#   inainte de randurile masinii.
IMAGE_CMD:ubi:prepend:vusolose = "install -m 0644 ${HDS_SPLASH_VUPLUS} ${DEPLOY_DIR_IMAGE}/splash_cfe_auto.bin; "
# Zgemma Star S (MSS): airdigital-mipsel.inc copiaza ${DEPLOY_DIR_IMAGE}/splash.bin (BOOTLOGO_FILENAME) in zgemma/sh1; e un
# BMP 720 x 576 x 24 (cel din imaginea publica OE-Alliance 6.0 a masinii), adica formatul siglei noastre GigaBlue
IMAGE_CMD:ubi:prepend:sh1 = "install -m 0644 ${HDS_SPLASH_GIGABLUE} ${DEPLOY_DIR_IMAGE}/splash.bin; "
IMAGE_CMD:ubi:prepend:vusolo2 = "install -m 0644 ${HDS_SPLASH_VUPLUS} ${DEPLOY_DIR_IMAGE}/splash_cfe_auto.bin; "
IMAGE_CMD:ubi:prepend:vuzero = "install -m 0644 ${HDS_SPLASH_VUPLUS} ${DEPLOY_DIR_IMAGE}/splash_cfe_auto.bin; "
# - compresia UBIFS: mkfs.ubifs pune implicit lzo; zlib strange mai bine (planul de marime e socotit cu zlib), iar
#   nucleul Solo SE (linux-vuplus 3.13.5, defconfig_proxy) are CONFIG_UBIFS_FS_ZLIB=y. MKFS_EXTRA intra in MKUBIFS_ARGS
#   (vuplus.inc). Fara zstd: nucleul 3.13.5 nu il stie.
MKFS_EXTRA:hdsflashmic = "-x zlib"
# Zgemma Star S (MSS): sh1.conf da MKUBIFS_ARGS intreg, fara ${MKFS_EXTRA}; nucleul linux-airdigital 4.10.12 (defconfig sh1)
# are CONFIG_UBIFS_FS_ZLIB=y, deci aceeasi compresie zlib ca pe Solo SE
MKUBIFS_ARGS:append:sh1 = " -x zlib"
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
