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
PV = "0.6.8+git${SRCPV}"

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
# t2mi_decap (decapsulatorul T2-MI) sta sub python/Hds/DabT2/t2/bin: .debug-ul lui, altfel QA debug-files
FILES:${PN}-dbg += "${libdir}/enigma2/python/.debug ${libdir}/enigma2/python/*/.debug \
    ${libdir}/enigma2/python/Hds/DabT2/t2/bin/.debug"

# python3-cryptography: semnatura Ed25519 a actualizarilor (Components/HdsSemnatura.py); fara ea nicio actualizare
# semnata nu se instaleaza, deci se cere aici, nu se lasa pe seama altor pachete care o aduc intamplator. E reteta
# separata (nu vine din python3), deci si in DEPENDS: numai pentru ordinea constructiei si proba QA build-deps.
DEPENDS += "python3-cryptography"
RDEPENDS:${PN} = " \
    python3-core python3-codecs python3-xml python3-threading python3-fcntl python3-netclient \
    python3-shell python3-pickle python3-email python3-mime python3-misc python3-math \
    python3-json python3-crypt python3-compression \
    python3-cryptography \
    "

# libhiaccel.so se incarca cu dlopen (nu e NEEDED): pachetul care o da e numai recomandat; in imagine vine oricum
# (dinobot-libs-u57 vine prin MACHINE_ESSENTIAL_EXTRA_RDEPENDS, vezi packagegroups/hdsatelit-base.bb; pe receptorul de proba e
# dinobot-libs-u57 20210604-r2)
RRECOMMENDS:${PN} += "${@bb.utils.contains("MACHINE_FEATURES", "hiaccel", "dinobot-libs-${MACHINE}", "", d)}"
