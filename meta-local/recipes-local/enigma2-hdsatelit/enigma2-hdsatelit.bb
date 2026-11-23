SUMMARY = "Enigma2 pentru HDSatelit Image (Monea Software pentru HD Satelit)"
DESCRIPTION = "Interfata receptorului HDSatelit, derivata GPLv2 din codul enigma2 din 2011, adusa la Python 3.13."
HOMEPAGE = "https://hdsatelit.com"
LICENSE = "GPL-2.0-only"
# LICENSE trimite la LICENSE.GPLv2 (textul GPL), la LICENSE.original-2011 (licenta enigma2 de la care pornim) si la
# doc/REMOVED-FILES (ce s-a scos din sursa din 2011 din cauza licentelor): toate ajung in dosarul licentelor, deci si in
# lista licentelor din imagine
LIC_FILES_CHKSUM = "file://LICENSE;md5=730404357c1f5cc99e543a52ded00509 \
                    file://LICENSE.GPLv2;md5=eb723b61539feef013de476e68b5c50a \
                    file://LICENSE.original-2011;md5=c9e255efa454e0155c1fd758df7dcaf3 \
                    file://doc/REMOVED-FILES;md5=4b261c5f2ba30fec67f20d8740294e27"

# dependintele cerute de configure.ac din depozitul nostru
# GStreamer PORNIT (21.09.2026, pilot automat): servicemp3.cpp a fost portat de la GStreamer 0.10 la
# 1.0 (playbin2->playbin, GST_BUFFER_DATA/SIZE->gst_buffer_map, semnalele appsink new-buffer/pull-buffer
# -> new-sample/pull-sample, gst_tag_list_free->unref, plus un PyBuffer_FromMemory ramas din Python 2,
# inlocuit cu PyBytes_FromStringAndSize).
# gstreamer1.0/-plugins-base dau headerele + pkg-config module-le cerute de
# configure.ac (gstreamer-1.0, gstreamer-pbutils-1.0); pachetele RUNTIME sunt in hdsatelit-base.bb.
DEPENDS = " \
    freetype fribidi libdvbsi++ libpng libxml2 libsigc++-3 \
    jpeg giflib \
    gstreamer1.0 gstreamer1.0-plugins-base \
    python3 swig-native gettext-native \
    "
# DVD copiat, fara decriptare: antetele si bibliotecile pentru serviciul DVD (libdvdnav peste libdvdread; libdreamdvd
# reda pe decodorul placii). Serviciul vine mai tarziu prin actualizari, dar bibliotecile trebuie sa fie deja in
# imagine (hdsatelit-base): o actualizare prin pachete nu aduce biblioteci noi de sistem.
DEPENDS += "libdvdread libdvdnav libdreamdvd"
# CI+ in enigma2 (lib/dvb_ci, din sursele GPL enigma2 OE-Alliance, commitul 29d951a6ec2e019680741efdad5ca7e7902b20e4,
# 12.11.2026): autentificarea si descifrarea CI+ folosesc libcrypto (OpenSSL 3, recipes-local/openssl). La rulare
# libcrypto3 vine singura (shlibs). Certificatele aparatului NU sunt in imagine: le pune omul in /etc/ciplus.
DEPENDS += "openssl"
# Accelerarea 2D pe placa (TDE HiSilicon, 25.09.2026, lotul accel-tde; 26.09.2026, lotul 1d al pilotului): pe
# MACHINE_FEATURES "hiaccel" (meta-dinobot u57.conf) --with-libhiaccel -> HAVE_HISILICON_ACCEL in lib/gdi/accel.cpp,
# care incarca libhiaccel.so (dinobot-libs-u57) cu dlopen la pornire, numai cand placa exista si setarea e pornita.
# Constructia NU cere biblioteca (fara DEPENDS, fara -lhiaccel, fara NEEDED in enigma2), iar la rulare e doar
# recomandata (RRECOMMENDS): fara ea, desenul ramane pe procesor. Pleaca PORNITA pe receptoarele care o au (fara niciun
# fisier); singura oprire e /etc/enigma2/hds-fara-accel (alegerea „Oprita” din setari sau din web, ssh, ori scris
# singur dupa o cadere cu placa folosita, dupa 2 reporniri la rand ale receptorului in primele 10 minute cu placa
# folosita, sau dupa 3 caderi in 10 minute dupa ce placa a lucrat). /etc/enigma2/hds-cu-accel nu mai inseamna nimic.

inherit autotools-brokensep pkgconfig python3native python3targetconfig

# sursa: depozitul git local /hds/hdsatelit-image, ramura main (dosarul enigma2/ al sursei publice, facut depozit
# git; vezi README.md). Pentru o constructie fixata, SRCREV poate primi comiterea acelui depozit in locul lui ${AUTOREV}.
SRC_URI = "git:///hds/hdsatelit-image;protocol=file;branch=main"
SRCREV = "${AUTOREV}"
PV = "0.7.9+git${SRCPV}"

# --with-boxtype=${MACHINE}: configure.ac defineste HAVE_HISILICON pentru masinile HiSilicon (u57 si celelalte u5x/u4x,
# familia sf8008). Pe ele video0 si audio0 duc la acelasi player: lib/dvb/decoder.cpp pune atunci poza radio/RaSS pe
# playerul separat al pozei (sursa 0xff), fiindca sursa MEMORY reface playerul comun fara sunet. Poza ramane deschisa
# pana la poza urmatoare, pana la video adevarat pe orice decodor sau pana la zap (fara ceasul de 150 ms: VIDEO_STOP-ul
# lui ar inegri poza). Cere un configure.ac care stie optiunea: cu unul mai vechi constructia cade la do_configure
# (unknown-configure-option e in ERROR_QA). Invers, configure.ac cel nou se opreste singur daca vine --with-libhiaccel
# fara o masina HiSilicon sau nobox, iar do_configure:append de mai jos verifica rezultatul.
EXTRA_OECONF = " \
    --with-libsdl=no \
    --with-gstreamer=yes \
    --with-debug \
    --with-boxtype=${MACHINE} \
    ${@bb.utils.contains("MACHINE_FEATURES", "hiaccel", "--with-libhiaccel", "", d)} \
    "

# Paza pe masinile cu "hiaccel" (u57): constructia se opreste daca configure nu a ales calea HiSilicon a pozei; altfel
# imaginea iese si se instaleaza fara nicio eroare, iar radioul ramane fara sunet.
do_configure:append() {
	if ${@bb.utils.contains('MACHINE_FEATURES', 'hiaccel', 'true', 'false', d)}; then
		grep -q '^#define HAVE_HISILICON 1' ${B}/enigma2_config.h || \
			bbfatal "enigma2_config.h fara HAVE_HISILICON pe ${MACHINE}: --with-boxtype=${MACHINE} nu a ajuns la configure sau masina lipseste din lista din configure.ac"
	fi
}

# Primul Amiko Viper 4K (V10, masina viper4k, lotul imagine-060-v10; codul de la 0.6.3): pe el nu exista demonul
# Dinobot care mapeaza memoria pozelor si a filmelor (showiframe Amiko afiseaza un cadru si iese, platforma o tine
# libreader), deci paza scrierilor pe video0/audio0 din lib/dvb/hdspazavideo.h (maparea de 34 611 200 o in
# /proc/vmallocinfo) ar refuza orice film, flux IPTV si poza radio. HDS_FARA_MEMORIE_ES=1 face ca paza sa lase
# scrierile fara sa citeasca nimic. NUMAI pe viper4k: pe u57 si u571 (V20, V30, V40) CXXFLAGS ramane neschimbat, deci
# si paza. Paza de mai jos opreste constructia pe viper4k daca sursa nu mai stie macro-ul (comitere mai veche de 0.6.3);
# construieste-060.sh verifica in jurnalul do_compile ca macro-ul a ajuns la compilator pe viper4k si numai acolo.
CXXFLAGS:append:viper4k = " -DHDS_FARA_MEMORIE_ES=1"
do_configure:append:viper4k() {
	grep -q 'HDS_FARA_MEMORIE_ES' ${S}/lib/dvb/hdspazavideo.h || \
		bbfatal "lib/dvb/hdspazavideo.h nu stie HDS_FARA_MEMORIE_ES (codul V10 e de la 0.6.3): pe ${MACHINE} filmele ar fi refuzate"
	grep -q '^#define HAVE_HISILICON 1' ${B}/enigma2_config.h || \
		bbfatal "enigma2_config.h fara HAVE_HISILICON pe ${MACHINE}: --with-boxtype=${MACHINE} nu a ajuns la configure"
}
# Octagon SF8008 (masina sf8008, lotul imagine-060-sf8008): aceeasi platforma ca V10 (libreader, showiframe care numai
# afiseaza un cadru, fara maparea Dinobot), deci aceeasi paza oprita si aceeasi verificare; configure.ac pune sf8008 in
# HAVE_HISILICON.
CXXFLAGS:append:sf8008 = " -DHDS_FARA_MEMORIE_ES=1"
do_configure:append:sf8008() {
	grep -q 'HDS_FARA_MEMORIE_ES' ${S}/lib/dvb/hdspazavideo.h || \
		bbfatal "lib/dvb/hdspazavideo.h nu stie HDS_FARA_MEMORIE_ES (codul V10 e de la 0.6.3): pe ${MACHINE} filmele ar fi refuzate"
	grep -q '^#define HAVE_HISILICON 1' ${B}/enigma2_config.h || \
		bbfatal "enigma2_config.h fara HAVE_HISILICON pe ${MACHINE}: --with-boxtype=${MACHINE} nu a ajuns la configure"
}
# Octagon SX88V2 4K DUAL OS si SX988 4K DUAL OS (V19, 14.11.2026; masinile sx88v2 si sx988): aceeasi platforma ca SF8008
# (libreader: octagon-reader-<masina>; showiframe: octagon-showiframe-hisi3798mv300 si -hisi3798mv200advca au EXACT arhiva
# lui SF8008, sha256 8c691126...: programul care numai afiseaza un cadru), deci aceeasi paza oprita si aceeasi verificare.
# configure.ac pune sx88v2 si sx988 in HAVE_HISILICON; HAVE_HISILICON_LIBREADER le cere randul din V19/configure-ac-v19.patch.
CXXFLAGS:append:sx88v2 = " -DHDS_FARA_MEMORIE_ES=1"
CXXFLAGS:append:sx988 = " -DHDS_FARA_MEMORIE_ES=1"
do_configure:append:sx88v2() {
	grep -q '^#define HAVE_HISILICON 1' ${B}/enigma2_config.h || \
		bbfatal "enigma2_config.h fara HAVE_HISILICON pe ${MACHINE}: --with-boxtype=${MACHINE} nu a ajuns la configure"
	grep -q '^#define HAVE_HISILICON_LIBREADER 1' ${B}/enigma2_config.h || \
		bbfatal "enigma2_config.h fara HAVE_HISILICON_LIBREADER pe ${MACHINE}: lipseste randul V19 din configure.ac"
}
do_configure:append:sx988() {
	grep -q '^#define HAVE_HISILICON 1' ${B}/enigma2_config.h || \
		bbfatal "enigma2_config.h fara HAVE_HISILICON pe ${MACHINE}: --with-boxtype=${MACHINE} nu a ajuns la configure"
	grep -q '^#define HAVE_HISILICON_LIBREADER 1' ${B}/enigma2_config.h || \
		bbfatal "enigma2_config.h fara HAVE_HISILICON_LIBREADER pe ${MACHINE}: lipseste randul V19 din configure.ac"
}
# Octagon SF8008 MINI 4K (masina sf8008m, lotul imagine-060-sf8008m): aceeasi platforma ca SF8008 (libreader,
# showiframe care numai afiseaza un cadru), deci aceeasi paza oprita si aceeasi verificare; configure.ac pune sf8008m in
# HAVE_HISILICON.
CXXFLAGS:append:sf8008m = " -DHDS_FARA_MEMORIE_ES=1"
do_configure:append:sf8008m() {
	grep -q 'HDS_FARA_MEMORIE_ES' ${S}/lib/dvb/hdspazavideo.h || \
		bbfatal "lib/dvb/hdspazavideo.h nu stie HDS_FARA_MEMORIE_ES (codul V10 e de la 0.6.3): pe ${MACHINE} filmele ar fi refuzate"
	grep -q '^#define HAVE_HISILICON 1' ${B}/enigma2_config.h || \
		bbfatal "enigma2_config.h fara HAVE_HISILICON pe ${MACHINE}: --with-boxtype=${MACHINE} nu a ajuns la configure"
}
# Uclan Ustym 4K PRO (masina ustym4kpro, lotul ustym4kpro): aceeasi platforma ca SF8008 (libreader, showiframe care
# numai afiseaza un cadru; driverele aceleasi afara de hi-dvb.ko, compilat din aceeasi sursa), deci aceeasi paza oprita
# si aceeasi verificare; configure.ac pune ustym4kpro in HAVE_HISILICON si in familia libreader.
CXXFLAGS:append:ustym4kpro = " -DHDS_FARA_MEMORIE_ES=1"
do_configure:append:ustym4kpro() {
	grep -q 'HDS_FARA_MEMORIE_ES' ${S}/lib/dvb/hdspazavideo.h || \
		bbfatal "lib/dvb/hdspazavideo.h nu stie HDS_FARA_MEMORIE_ES (codul V10 e de la 0.6.3): pe ${MACHINE} filmele ar fi refuzate"
	grep -q '^#define HAVE_HISILICON 1' ${B}/enigma2_config.h || \
		bbfatal "enigma2_config.h fara HAVE_HISILICON pe ${MACHINE}: --with-boxtype=${MACHINE} nu a ajuns la configure"
	grep -q '^#define HAVE_HISILICON_LIBREADER 1' ${B}/enigma2_config.h || \
		bbfatal "enigma2_config.h fara HAVE_HISILICON_LIBREADER pe ${MACHINE}: configure.ac nu stie masina in familia libreader"
}
# GigaBlue UHD TRIO 4K (masina gbmv200, modelul gbtrio4k, lotul modele-noi-0611): aceeasi platforma ca SF8008 si
# Ustym (libreader, showiframe care numai afiseaza un cadru, aceeasi arhiva showiframe; 93 din 105 fisiere ale driverelor
# identice cu cele Octagon sau Uclan), deci aceeasi paza oprita si aceeasi verificare; configure.ac pune gbmv200
# (--with-boxtype=${MACHINE}) in HAVE_HISILICON si in familia libreader.
CXXFLAGS:append:gbtrio4k = " -DHDS_FARA_MEMORIE_ES=1"
do_configure:append:gbtrio4k() {
	grep -q 'HDS_FARA_MEMORIE_ES' ${S}/lib/dvb/hdspazavideo.h || \
		bbfatal "lib/dvb/hdspazavideo.h nu stie HDS_FARA_MEMORIE_ES (codul V10 e de la 0.6.3): pe ${MACHINE} filmele ar fi refuzate"
	grep -q '^#define HAVE_HISILICON 1' ${B}/enigma2_config.h || \
		bbfatal "enigma2_config.h fara HAVE_HISILICON pe ${MACHINE}: --with-boxtype=${MACHINE} nu a ajuns la configure"
	grep -q '^#define HAVE_HISILICON_LIBREADER 1' ${B}/enigma2_config.h || \
		bbfatal "enigma2_config.h fara HAVE_HISILICON_LIBREADER pe ${MACHINE}: configure.ac nu stie masina in familia libreader"
}
# ZGEMMA H8.2H Plus (masina h8, Hi3716MV430) si H8.2H SE (masina h8se, Hi3798MV200): drivere Airdigital din meta-airdigital,
# fara libreader si fara showiframe Dinobot, deci fara maparea de 34 611 200 o (/proc/vmallocinfo nu o are pe niciunul, citit
# pe receptoare 23.11.2026); cu paza, orice film, flux IPTV si poza radio ar fi refuzate. configure.ac pune h8 si h8se in
# HAVE_HISILICON, nu si in familia libreader. Randurile stau aici, nu intr-un .bbappend din meta-local: la constructia 6.0
# oe-build/strat-60 are recipes-local/enigma2-hdsatelit/enigma2-hdsatelit.bbappend si il inlocuieste pe cel cu acelasi nume
# (asa a iesit 0.7.8 pe H8 cu paza). PR r1: pachetul refacut din aceeasi sursa 0.7.8 trece peste cel publicat (-r0).
CXXFLAGS:append:h8 = " -DHDS_FARA_MEMORIE_ES=1"
CXXFLAGS:append:h8se = " -DHDS_FARA_MEMORIE_ES=1"
PR:h8 = "r1"
PR:h8se = "r1"
do_configure:append:h8() {
	grep -q 'HDS_FARA_MEMORIE_ES' ${S}/lib/dvb/hdspazavideo.h || \
		bbfatal "lib/dvb/hdspazavideo.h nu stie HDS_FARA_MEMORIE_ES: pe ${MACHINE} filmele ar fi refuzate"
	grep -q '^#define HAVE_HISILICON 1' ${B}/enigma2_config.h || bbfatal "H8: lipseste decodorul HiSilicon"
	! grep -q '^#define HAVE_HISILICON_LIBREADER 1' ${B}/enigma2_config.h || bbfatal "H8: libreader nu apartine acestui BSP"
}
do_configure:append:h8se() {
	grep -q 'HDS_FARA_MEMORIE_ES' ${S}/lib/dvb/hdspazavideo.h || \
		bbfatal "lib/dvb/hdspazavideo.h nu stie HDS_FARA_MEMORIE_ES: pe ${MACHINE} filmele ar fi refuzate"
	grep -q '^#define HAVE_HISILICON 1' ${B}/enigma2_config.h || bbfatal "H8 SE: lipseste decodorul HiSilicon"
	! grep -q '^#define HAVE_HISILICON_LIBREADER 1' ${B}/enigma2_config.h || bbfatal "H8 SE: libreader nu apartine acestui BSP"
}

# Pachetul tine de masina, nu numai de procesor: configure primeste --with-boxtype=${MACHINE} (HAVE_HISILICON pe
# u5x/u4x: poza radio, alegerea demux-ului, inregistrarea citita fara blocare) si --with-libhiaccel dupa
# MACHINE_FEATURES. Cu arhitectura procesorului (cortexa15hf-neon-vfpv4) acelasi nume de pachet ar putea ajunge pe
# alta masina cortexa15 fara HiSilicon, din acelasi TMPDIR sau din acelasi feed. Pe masina, pachetul iese in
# deploy/ipk/${MACHINE_ARCH}/ (u57), iar dosarul de lucru e work/${MACHINE_ARCH}-oe-linux-gnueabi/.
PACKAGE_ARCH = "${MACHINE_ARCH}"

FILES:${PN} += " \
    ${libdir}/enigma2 \
    ${datadir}/enigma2 \
    ${datadir}/fonts \
    ${datadir}/keymaps \
    ${datadir}/meta \
    ${sysconfdir}/image-version \
    "
# Receptoarele cu memorie interna mica (suprascrierea hdsflashmic, conf/distro/hdsatelit.conf; Vu+ Solo SE, lotul
# mips-solose, 06.11.2026): fiecare limba a interfetei (/usr/share/enigma2/po/<limba>, ~0,6 MB comprimata in UBIFS, 33 de
# limbi = ~19 MB) intra in pachetul ei, enigma2-hdsatelit-po-<limba>, in feedul imaginii; in imagine raman romana si
# engleza (hotararea lui Eduard, 06.11.2026: „pastrezi numai ce trebuie neaparat, de pilda romana si engleza”). O limba
# lipsa nu strica nimic: Components/Language.py ramane pe limba de dinainte („Selected language does not exist!”).
# Pachetul tine de masina (PACKAGE_ARCH mai jos), deci impartirea de aici nu ajunge pe masinile cu eMMC; acolo e cea de
# mai jos (imaginea mica).
PACKAGES_DYNAMIC += "^${PN}-po-.*"
# ${PN}-po-toate (componenta hdsatelit-partea-doua, 06.11.2026 seara): un pachet gol care depinde de TOATE limbile facute
# aici, ca partea a doua de pe stick (hdsatelit-partea-doua-continut) sa le ceara fara sa stie lista; lista o da chiar
# impartirea de mai jos, deci o limba noua intra singura.
PACKAGES:append:hdsflashmic = " ${PN}-po-toate"
ALLOW_EMPTY:${PN}-po-toate = "1"
FILES:${PN}-po-toate = ""
python populate_packages:prepend:hdsflashmic () {
    dosar = d.expand('${datadir}/enigma2/po')
    limbi = do_split_packages(d, dosar, r'^([a-zA-Z_]+)$', d.expand('${PN}-po-%s'), 'Traducerea interfetei HD Satelit: %s',
        allow_dirs=True, prepend=True)
    if not limbi:
        bb.fatal('enigma2-hdsatelit: impartirea limbilor nu a facut niciun pachet po-*')
    d.setVar('RDEPENDS:' + d.expand('${PN}-po-toate'), ' '.join(sorted(limbi)))
    d.setVar('SUMMARY:' + d.expand('${PN}-po-toate'), 'Toate limbile interfetei HD Satelit (%d)' % len(limbi))
}
RDEPENDS:${PN}:append:hdsflashmic = " ${PN}-po-ro ${PN}-po-en"

# Imaginea mica (0.7.4, 10.11.2026; lucru-sesiune/oe-60/imagine-mica/PROIECT-IMAGINE-MICA.md, 2a si P2): pe toate
# celelalte masini (eMMC si Solo SE pe stick) cele 15 limbi native (HDS_LIMBI_NATIVE, conf/distro/hdsatelit.conf) raman
# INAUNTRUL lui enigma2-hdsatelit, iar numai celelalte 15 trec in pachetele enigma2-hdsatelit-po-<limba>, in feed (~25 MB
# mai putin in radacina). Fisierele limbilor native nu se muta dintr-un pachet in altul, deci actualizarea din meniu a
# receptoarelor de pe bazele vechi nu poate da peste „un pachet ar scrie peste fisierele altui pachet”. O limba nenativa
# aleasa de om vine singura din feed (Components/HdsLimbaRestaurare.py). Paza: toate nativele au catalogul, iar
# numarul pachetelor e HDS_LIMBI_FEED_NUMAR (o limba noua in po/Makefile.am cere o hotarare: nativa sau din feed).
# Fara return in acest bloc: codul se lipeste in fata functiei populate_packages.
python populate_packages:prepend () {
    if 'hdsflashmic' not in (d.getVar('OVERRIDES') or '').split(':'):
        import re
        hds_native = (d.getVar('HDS_LIMBI_NATIVE') or '').split()
        hds_dosar = d.expand('${datadir}/enigma2/po')
        hds_lipsa = [l for l in hds_native if not os.path.isfile(os.path.join(d.getVar('PKGD') + hds_dosar, l,
            'LC_MESSAGES', 'enigma2.mo'))]
        if not hds_native or hds_lipsa:
            bb.fatal('enigma2-hdsatelit: limbile native fara catalog: %s' % (' '.join(hds_lipsa) or 'HDS_LIMBI_NATIVE gol'))
        hds_limbi = do_split_packages(d, hds_dosar, r'^(?!(?:%s)$)([a-zA-Z_]+)$' % '|'.join(re.escape(l) for l in hds_native),
            d.expand('${PN}-po-%s'), 'Traducerea interfetei HD Satelit: %s', allow_dirs=True, prepend=True)
        if len(hds_limbi) != int(d.getVar('HDS_LIMBI_FEED_NUMAR') or '0'):
            bb.fatal('enigma2-hdsatelit: %d limbi in feed (%s), asteptate %s (HDS_LIMBI_FEED_NUMAR)' % (len(hds_limbi),
                ' '.join(sorted(hds_limbi)), d.getVar('HDS_LIMBI_FEED_NUMAR')))
}

# Afisajul color (hotararea A, 10.11.2026; PROIECT-IMAGINE-MICA.md 1c si 4e): /usr/share/enigma2/HDSatelit/afisaj-color
# (13,8 MB: pozele 480x320 si 400x240, orbita, fonturile) il folosesc numai receptoarele cu LCD color (HDS_AFISAJ_COLOR,
# conf/distro/hdsatelit.conf). Pe celelalte nimic nu citeste dosarul (meniul Afisaj, pagina web si vremea intreaba intai
# esteColor()), deci se sterge la constructie; pe Vu+ 4K ramane, si merge din prima secunda, fara internet.
do_install:append() {
    if [ "${HDS_AFISAJ_COLOR}" != "1" ]; then
        rm -rf ${D}${datadir}/enigma2/HDSatelit/afisaj-color
    fi
}

# /etc/image-version (in acest pachet, scris de Makefile.am din AC_INIT) si versiunea pachetului (PV, pusa de uneltele de
# constructie in copia stratului) trebuie sa spuna aceeasi versiune: pe 11.11.2026 o constructie 0.7.4 facuta dintr-o comitere
# cu AC_INIT inca 0.7.3 (49170cb328) a ajuns pe Octagon, iar receptorul a spus 0.7.3 (Despre, asistenta, CEC, uneltele) cu
# pachetul 0.7.4 instalat (UPD, 13.11.2026). Constructia se opreste acum in loc sa faca un astfel de pachet.
do_install:append() {
    v=$(sed -n 's/^imageversion=//p' ${D}${sysconfdir}/image-version)
    p=$(echo "${PV}" | sed 's/+.*//')
    [ -n "$v" ] || bbfatal "enigma2-hdsatelit: /etc/image-version fara imageversion="
    [ "$v" = "$p" ] || bbfatal "enigma2-hdsatelit: /etc/image-version spune $v (AC_INIT din configure.ac la ${SRCREV}), pachetul e ${PV}: AC_INIT si PV trebuie sa fie aceeasi versiune"
}

# t2mi_decap (decapsulatorul T2-MI) sta sub python/Hds/DabT2/t2/bin: .debug-ul lui, altfel QA debug-files
FILES:${PN}-dbg += "${libdir}/enigma2/python/.debug ${libdir}/enigma2/python/*/.debug \
    ${libdir}/enigma2/python/Hds/DabT2/t2/bin/.debug"

# SoftCSA (0.7.4, lib/dvb/csaengine.cpp): canalele CSA-ALT (ICAM, Sky Deutschland) se descifreaza in software cu
# libdvbcsa (strat: libdvbcsa_git.bbappend, fixata la 6c459854, 1.2.0, cu dvbcsa_bs_key_set_ecm). Programul o incarca la rulare
# (dlopen, libdvbcsa.so.1): DEPENDS numai pentru ordinea constructiei si proba QA build-deps, RDEPENDS ca sa vina in
# imagine si la actualizare. Codul pune si semnul ${datadir}/hdsatelit/softcsa (data/Makefile.am): dupa el scriptul de
# pornire al modulelor de acces trece singur pe pmt_mode = 6 si extended_cw_api = 1.
DEPENDS += "libdvbcsa"
# :append, fiindca RDEPENDS:${PN} se pune mai jos cu "=" (lista modulelor Python)
RDEPENDS:${PN}:append = " libdvbcsa"
FILES:${PN} += "${datadir}/hdsatelit/softcsa"

# python3-cryptography: semnatura Ed25519 a actualizarilor (Components/HdsSemnatura.py); fara ea nicio actualizare
# semnata nu se instaleaza, deci se cere aici, nu se lasa pe seama altor pachete care o aduc intamplator. E reteta
# separata (nu vine din python3), deci si in DEPENDS: numai pentru ordinea constructiei si proba QA build-deps.
DEPENDS += "python3-cryptography"
RDEPENDS:${PN} = " \
    python3-core python3-codecs python3-xml python3-threading python3-fcntl python3-netclient \
    python3-shell python3-pickle python3-email python3-mime python3-misc python3-math \
    python3-json python3-crypt python3-compression python3-multiprocessing \
    python3-cryptography \
    python3-future python3-image python3-mmap python3-netifaces python3-pexpect python3-pillow python3-process \
    python3-puremagic python3-pyopenssl python3-pyusb python3-requests python3-six python3-treq python3-trio \
    python3-difflib \
    "

# python3-difflib (randul de sus): AutoTimer din feedul OE-Alliance il importa la pornire; pana la 0.7.3 venea prin pachetele
# OCR, iar in 0.7.4 (OCR la cerere) a plecat cu ele, deci se cere aici, ca celelalte biblioteci ale pluginurilor externe.

# Pluginurile externe: bibliotecile de mai sus (ultimele doua randuri) le pune OE-Alliance in toate imaginile, iar scripturile
# de instalare ale multor pluginuri cheama comanda „python”, care pe aceasta baza nu exista
FILES:${PN} += "${bindir}/python"
do_install:append() {
    install -d ${D}${bindir}
    ln -sf python3 ${D}${bindir}/python
}

# libhiaccel.so se incarca cu dlopen (nu e NEEDED): pachetul care o da e numai recomandat; in imagine vine oricum
# (dinobot-libs-u57 vine prin MACHINE_ESSENTIAL_EXTRA_RDEPENDS, vezi packagegroups/hdsatelit-base.bb; pe receptorul de proba e
# dinobot-libs-u57 20210604-r2)
RRECOMMENDS:${PN} += "${@bb.utils.contains("MACHINE_FEATURES", "hiaccel", "dinobot-libs-${MACHINE}", "", d)}"

# cheia aplicatiei OpenSubtitles (reteta hdsatelit-opensubtitles; SBR 15.11.2026): fisierul din care citeste
# Components/HdsSubtitrariInternet/surse/opensubtitles.py; pachet gol cand constructia nu are cheia
RRECOMMENDS:${PN} += "hdsatelit-opensubtitles"

# textele ajutorului (reteta hdsatelit-ajutor, pachet allarch separat): HELP pe orice ecran, Meniu > Informatii despre sistem >
# Ajutor si /ajutor in web (Components/HdsAjutor.py). Recomandat, nu cerut: intra in imaginile noi (imaginea instaleaza
# recomandarile) si vine la actualizarea din meniu odata cu enigma2-hdsatelit (opkg aduce recomandarile din feed; culegerea il
# are in COMUN), iar daca lipseste din feedul unei baze, actualizarea nu se opreste (fara el HELP arata lista tastelor, cu textele
# de rezerva din HdsAjutor.py). Pe hdsflashmic (Vu+ Solo SE NAND, memoria mica) nu: acolo raman lista tastelor si TEXT_LIPSA.
# REL8, 17.11.2026 (hotararea coordonatorului 20:25, varianta (a)).
RRECOMMENDS:${PN} += "hdsatelit-ajutor"
RRECOMMENDS:${PN}:remove:hdsflashmic = "hdsatelit-ajutor"

# PRB8 (22.11.2026): probele 0.7.7 (pachetele enigma2-plugin-hds-proba-*, puse de asistenta sau din Extensii) tin in
# /usr/lib/hds-proba/<cod>/vechi copiile fisierelor 0.7.7 si o paza care le pune la loc (la cadere, la 30 de minute fara
# confirmare, la `opkg remove` prin prerm). Paza pune la loc numai fisierele care au inca suma pusa de proba, dar multe
# fisiere ale probelor sunt IDENTICE in 0.7.8 (cbs1077, pcn6077, dcd6077, fwc4077, cur6077, m3q6077...): dupa actualizare
# un fisier 0.7.7 ar ajunge peste 0.7.8. De aceea, la actualizare, inainte ca opkg sa despacheteze pachetul nou si sa
# configureze pachetele ramase neconfigurate (o proba refuzata de paza veche ramane "unpacked" si opkg ii reia postinst-ul):
# pazele se opresc, scripturile probelor din info/ (preinst, postinst, prerm, postrm), S99hds-proba-* si copiile se sterg,
# deci nimic nu mai poate pune la loc fisiere 0.7.7. Fisierele probelor sunt ale lui enigma2-hdsatelit si le rescrie
# pachetul nou; un fisier al altui pachet (modulul de nucleu al unei probe) ramane cum l-a pus proba, cu un rand in jurnal.
# opkg rescrie status-ul din memorie la sfarsit, deci pachetele raman in lista pana la urmatoarea pornire a interfetei:
# numele lor raman in /etc/hds-probe-de-scos, iar tools/enigma2.sh le scoate cu `opkg remove` (fara niciun script).
# Un rand pentru fiecare proba in /home/root/logs/hds-actualizari.log. Numai pe receptor ($D gol); iese mereu cu 0.
# HDS_PROBE_USCAT=1 arata pe ecran ce ar face, fara nicio schimbare (proba pe receptor: scriptul extras din pachet).
# RPR8 (0.7.8): „Repară imaginea” reinstaleaza enigma2-hdsatelit cu ACEEASI versiune ca sa puna la loc fisierele sterse;
# atunci (HDS_REPARA_IMAGINEA=1 in mediul lui opkg, pus de Components/HdsActualizari.py) probele raman: nu e o versiune noua.
pkg_preinst:${PN}() {
if [ -n "$HDS_REPARA_IMAGINEA" ] && [ -z "$D" ]; then
	{ mkdir -p /home/root/logs && echo "$(date '+%Y-%m-%d %H:%M:%S') [probe] repara imaginea: aceeasi versiune, probele raman" >> /home/root/logs/hds-actualizari.log; } 2>/dev/null || true
fi
if [ -z "$D" ] && [ -f /var/lib/opkg/status ] && [ -z "$HDS_REPARA_IMAGINEA" ]; then
( set +e
U=
[ "$HDS_PROBE_USCAT" = 1 ] && U=1
I=/var/lib/opkg/info
jurnal() {
	r="$(date '+%Y-%m-%d %H:%M:%S') [probe 0.7.7] $*"
	if [ -n "$U" ]; then
		echo "$r"
	else
		mkdir -p /home/root/logs
		echo "$r" >> /home/root/logs/hds-actualizari.log
	fi
	}
fa() {
	if [ -n "$U" ]; then echo "  (uscat) $*"; else "$@"; fi
	}
nume=$(sed -n 's/^Package: \(enigma2-plugin-hds-proba-[a-z0-9.+-]*\)$/\1/p' /var/lib/opkg/status)
dosare=$(ls -d /usr/lib/hds-proba/*/ 2>/dev/null)
s99=$(ls /etc/rc?.d/S??hds-proba-* 2>/dev/null)
if [ -n "$nume$dosare$s99" ]; then
	# 1. pazele (numai paza.py din /usr/lib/hds-proba; reincarcarea modulelor, init 4 ... init 3, se lasa sa termine)
	paze=
	for p in /proc/[0-9]*; do
		case "$(tr '\0' ' ' < $p/cmdline 2>/dev/null)" in
		*/usr/lib/hds-proba/*/paza.py*)
			pid=$(basename $p)
			paze="$paze $pid"
			fa kill -TERM $pid 2>/dev/null
			;;
		esac
	done
	if [ -n "$paze" ] && [ -z "$U" ]; then
		sleep 1
		for pid in $paze; do kill -KILL $pid 2>/dev/null; done
	fi
	jurnal "actualizare: probele 0.7.7 se scot, fisierele raman cele ale versiunii noi (pachete: $(echo $nume | wc -w), paze oprite:$paze)"
	# 2. un rand pentru fiecare proba (info/<pachet>.list: "cale<TAB>mod" pe fiecare rand)
	for d in $dosare; do
		st=nepusa
		if [ -f $d/stare.json ]; then
			st=scoasa
			grep -q '"activa": true' $d/stare.json && st=activa
			grep -q '"confirmata": true' $d/stare.json && st="$st, confirmata"
		fi
		altele=
		case "$st" in
		activa*)
			for t in $(awk -F'"' '/"tinta":/ { print $4 }' $d/stare.json | sort -u); do
				awk -F'\t' -v t="$t" '$1 == t { g = 1; exit } END { exit !g }' $I/enigma2-hdsatelit.list 2>/dev/null ||
					altele="$altele $t"
			done
			;;
		esac
		if [ -n "$altele" ]; then
			jurnal "proba $(basename $d): $st; ramane cum l-a pus proba (alt pachet decat enigma2-hdsatelit):$altele"
		else
			jurnal "proba $(basename $d): $st"
		fi
	done
	# 3. nimic nu mai porneste paza la pornire si nimic nu mai pune la loc la `opkg remove`
	for f in $s99; do
		fa rm -f $f
	done
	for n in $nume; do
		fa rm -f $I/$n.preinst $I/$n.postinst $I/$n.prerm $I/$n.postrm
		[ -n "$U" ] || echo $n >> /etc/hds-probe-de-scos
	done
	fa rm -rf /usr/lib/hds-proba
	fa rm -f /tmp/hds-proba-*.log
	[ -n "$U" ] || sync
fi
) || true
fi
true
}

# Urmarirea pornirii (tools/hds-rezerva.sh) priveste ca pornire in dubiu orice pornire fara semnul
# /etc/hds-interfata-pornita. O instalare prin actualizare din meniu inseamna ca interfata a mers pe receptor, deci
# semnul se pune atunci (numai pe receptor: la constructia imaginii $D e plin si nu se face nimic).
pkg_postinst:${PN}() {
if [ -z "$D" ] && [ -f /etc/hdsatelit-model ] && [ ! -f /etc/hds-interfata-pornita ]; then
	printf 'imagine=actualizare\n' > /etc/hds-interfata-pornita
fi
# SoftCSA: modulul de acces isi potriveste pmt_mode / extended_cw_api dupa semnul ${datadir}/hdsatelit/softcsa numai cand
# porneste. Cand semnul vine prima oara cu o actualizare (fara repornirea receptorului), modulul ales porneste din nou, pe
# fundal, abia dupa ce interfata noua serveste /tmp/.listen.camd.socket (alt proces enigma2 decat cel de la instalare):
# repornit cat ruleaza inca interfata veche, modulul ar trece pe pmt_mode 6 fara nimeni la soclu si nu s-ar mai descifra
# nimic pana la repornirea interfetei. Se asteapta cel mult 30 de minute; altfel potrivirea o face modulul la urmatoarea
# lui pornire. /etc/hds-softcsa-semn tine minte ca s-a facut (in imaginea construita se pune de la inceput).
if [ -n "$D" ]; then
	[ -f $D${datadir}/hdsatelit/softcsa ] && touch $D${sysconfdir}/hds-softcsa-semn
elif [ -f ${datadir}/hdsatelit/softcsa ] && [ ! -f ${sysconfdir}/hds-softcsa-semn ]; then
	touch ${sysconfdir}/hds-softcsa-semn
	if [ -x ${sysconfdir}/init.d/softcam ]; then
		# || true: scriptul ruleaza cu set -e, iar pidof fara proces da 1 (actualizarea terminata la pornire, golul
		# dintre interfata veche si cea noua); fara el postinst-ul iesea cu eroare si bucla se oprea chiar la repornire
		vechi=$(pidof enigma2 || true)
		( i=0
		while [ $i -lt 900 ]; do
			acum=$(pidof enigma2 || true)
			if [ -S /tmp/.listen.camd.socket ] && [ -n "$acum" ] && [ "$acum" != "$vechi" ]; then
				${sysconfdir}/init.d/softcam restart
				break
			fi
			sleep 2
			i=$((i + 1))
		done ) > /dev/null 2>&1 < /dev/null &
	fi
fi
# /usr/lib/enigma.info (numele si versiunea imaginii pentru pluginurile OE-Alliance si pentru listele de pornire multipla ale
# altor imagini) il scrie numai reteta imaginii, deci dupa o actualizare prin pachete ramanea pe versiunea imaginii scrise
# (Octagon, 13.11.2026: imgversion='0.7.1' cu 0.7.4 instalata). La instalarea pe receptor se pun la zi NUMAI imgversion si
# compiledate, din /etc/image-version al acestui pachet; restul cheilor raman, iar checksum se socoteste din nou, ca la reteta
# imaginii (md5 al randurilor de deasupra). La constructia imaginii ($D plin) nu se face nimic: acolo il scrie reteta imaginii.
if [ -z "$D" ] && [ -f ${libdir}/enigma.info ] && [ -f ${sysconfdir}/image-version ]; then
	v=$(sed -n 's/^imageversion=//p' ${sysconfdir}/image-version | tr -cd '0-9.')
	b=$(sed -n 's/^imagebuild=//p' ${sysconfdir}/image-version | tr -cd '0-9')
	if [ -n "$v" ] && [ -n "$b" ]; then
		# ZRO1 (21.11.2026): imageversion is kept current too, and a file written before 0.7.8 (no model= line) gets the
		# receiver identity that hds_enigma_info_rootfs (hdsatelit-image.bb) writes in new images: brand, displaybrand,
		# displaymodel (rules name split like HdsCommon._model_din_reguli, so the name on screen does not change),
		# imageversion, model (OpenMultiBoot 1.3 skips images without it). Nothing added when a value is missing.
		# Match keys like Converter/HdsCommon._kv_file: ignore case and surrounding whitespace.
		# awk terminates every retained line, including an unterminated last line before new keys are appended.
		( f=${libdir}/enigma.info
		awk -v version="$v" -v build="$b" -v quote="'" '
			{
				key = $0
				sub(/=.*/, "", key)
				gsub(/^[[:space:]]+|[[:space:]]+$/, "", key)
				key = tolower(key)
				if (index($0, "=")) {
					if (key == "checksum") next
					if (key == "imgversion" || key == "imageversion") { print key "=" quote version quote; next }
					if (key == "compiledate") { print key "=" quote build quote; next }
				}
				print
			}' $f > $f.hds-nou &&
		if ! grep -q -i "^[[:space:]]*model[[:space:]]*=" $f.hds-nou && [ -f ${sysconfdir}/hdsatelit-model ]; then
			n=$(sed -n 's/^model=//p' ${sysconfdir}/hdsatelit-model | head -n 1 | tr -cd 'A-Za-z0-9 ._+()-' |
				sed -e 's/^ *//' -e 's/ *$//' | cut -c1-60)
			m=$(printf '%s' "$n" | sed -e 's/^[^ ]* *//' -e 's/ *$//')
			o="${@''.join(c for c in (d.getVar('BRAND_OEM') or '') if c.isalnum() or c in '_.-')}"
			k="${@''.join(c for c in (d.getVar('MACHINE') or '') if c.isalnum() or c in '_.-')}"
			# each key only when it is MISSING: values already in the file (written by the owner or by another package)
			# stay exactly as they are; model= comes last, so a second run finds it and adds nothing
			if [ -n "$m" ] && [ -n "$k" ] && [ -n "$o" ]; then
				for c in "brand=$o" "displaybrand=${n%% *}" "displaymodel=$m" "imageversion=$v" "model=$k"; do
					grep -q -i "^[[:space:]]*${c%%=*}[[:space:]]*=" $f.hds-nou || printf "%s='%s'\n" "${c%%=*}" "${c#*=}" >> $f.hds-nou
				done
			fi
		fi &&
			printf 'checksum=%s\n' "$(md5sum < $f.hds-nou | cut -d ' ' -f 1)" >> $f.hds-nou &&
			chmod 0644 $f.hds-nou && mv -f $f.hds-nou $f ) || rm -f ${libdir}/enigma.info.hds-nou
	fi
fi
# 0.7.6 (NVK, 15.11.2026; SVA, poarta 0.7.6; TODO 15.11 07:00 (agent_tv)): instalat pe alta cale decat Actualizari (o
# extensie din Extensii care il cere, ca ServiceApp "enigma2-hdsatelit (>= versiunea)", "Actualizeaza toate", opkg scris de
# mana), pachetul venea singur, fara tema si fara restul setului, si lasa interfata veche pornita peste fisierele noi:
# modulele Python incarcate la pornire raman vechi, cele incarcate mai tarziu sunt noi, si un ecran cade (Vu+ Solo 4K,
# 15.11.2026: KeyError 'agent_tv' in Setari navigator). Postinst-ul e codul NOU care ruleaza pe orice cale, si cand opkg e
# pornit de Extensii vechi (0.7.5 -> 0.7.6), deci de aici se termina actualizarea. Actualizari reporneste singura interfata
# (semnul ei /etc/enigma2/hds-actualizare.in-curs sau pachetele din /tmp/hds-actualizare in linia de comanda a lui opkg):
# atunci nimic. Altfel, pe fundal, dupa ce nu mai ruleaza niciun opkg (cel mult 20 de minute) si daca merge inca acelasi
# enigma2: i se cere interfetei pornite actualizarea rapida a paginii web (POST /api/actualizari-rapid, si in 0.7.5: cauta in
# feedul semnat, pune tema si restul setului, apoi reporneste interfata pe calea sigura; pe o inregistrare in curs asteapta
# sau intreaba pe televizor). Se urmareste cat lucreaza ea (GET /api/actualizari, "rapid": true, cel mult 30 de minute); daca
# s-a oprit fara repornire (nimic de pus, alta lucrare in curs), se cere numai repornirea interfetei
# (POST /api/accel-reporneste = TryQuitMainloop 3), afara de cazul in care omul a raspuns Nu pe televizor. Portul si cheia
# paginii, din setarile receptorului; nimic nu se scrie in jurnal.
if [ -z "$D" ] && [ -f ${sysconfdir}/hdsatelit-model ]; then
	vechi=$(pidof enigma2 || true)
	prin_actualizari=
	[ -f ${sysconfdir}/enigma2/hds-actualizare.in-curs ] && prin_actualizari=1
	for p in $(pidof opkg || true); do
		grep -q hds-actualizare /proc/$p/cmdline 2>/dev/null && prin_actualizari=1
	done
	if [ -n "$vechi" ] && [ -z "$prin_actualizari" ]; then
		( sleep 5
		# opkg liber si dupa inca 5 s (Extensii poate porni mai multe opkg unul dupa altul); actualizarea rapida nu porneste
		# cat tine altul lacatul lui opkg
		i=0
		while [ $i -lt 600 ]; do
			if pidof opkg > /dev/null; then
				sleep 2
			else
				sleep 5
				pidof opkg > /dev/null || break
			fi
			i=$((i + 1))
		done
		[ "$(pidof enigma2 || true)" = "$vechi" ] || exit 0
		[ -f ${sysconfdir}/enigma2/hds-actualizare.in-curs ] && exit 0
		port=$(sed -n 's/^config\.plugins\.hdswebcontrol\.port=//p' ${sysconfdir}/enigma2/settings | tr -cd '0-9')
		cheie=$(sed -n 's/^config\.plugins\.hdswebcontrol\.token=//p' ${sysconfdir}/enigma2/settings | tr -cd 'A-Za-z0-9_-')
		gazda=127.0.0.1
		[ -n "$port" ] && [ "$port" != 80 ] && gazda=127.0.0.1:$port
		# Origin ca o pagina a receptorului (paza cererilor straine din HdsWebControl/asociere.py)
		wget -q -O /dev/null --header "Origin: http://$gazda" --post-data= "http://$gazda/api/actualizari-rapid?token=$cheie" || true
		s=
		i=0
		while [ $i -lt 180 ]; do
			sleep 10
			[ "$(pidof enigma2 || true)" = "$vechi" ] || exit 0
			s=$(wget -q -O - --header "Origin: http://$gazda" "http://$gazda/api/actualizari?token=$cheie" 2>/dev/null || true)
			# fara raspuns (pagina ocupata o clipa) se mai asteapta; numai "rapid": false opreste urmarirea
			case "$s" in
			''|*'"rapid": true'*|*'"rapid":true'*) ;;
			*) break ;;
			esac
			i=$((i + 1))
		done
		[ $i -lt 180 ] || exit 0
		[ "$(pidof enigma2 || true)" = "$vechi" ] || exit 0
		[ -f ${sysconfdir}/enigma2/hds-actualizare.in-curs ] && exit 0
		case "$s" in
		*'"rapid_pas": "refuzata"'*|*'"rapid_pas":"refuzata"'*) exit 0 ;;
		esac
		wget -q -O /dev/null --header "Origin: http://$gazda" --post-data= "http://$gazda/api/accel-reporneste?token=$cheie"
		) > /dev/null 2>&1 < /dev/null &
	fi
fi
true
}

# La scoaterea pachetului (fara semnul SoftCSA dupa el) modulul porneste din nou si revine pe pmt_mode = 0; altfel ar
# ramane pe 6, iar fara /tmp/.listen.camd.socket nu s-ar mai descifra nimic. opkg nu cheama postrm-ul pachetului vechi la
# o actualizare sau la o intoarcere pe o versiune mai veche: acolo potrivirea o face modulul la urmatoarea lui pornire.
pkg_postrm:${PN}() {
if [ -z "$D" ] && [ ! -f ${datadir}/hdsatelit/softcsa ] && [ -f ${sysconfdir}/hds-softcsa-semn ]; then
	rm -f ${sysconfdir}/hds-softcsa-semn
	[ -x ${sysconfdir}/init.d/softcam ] && ( sleep 3; ${sysconfdir}/init.d/softcam restart ) > /dev/null 2>&1 < /dev/null &
fi
true
}
