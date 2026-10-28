SUMMARY = "Pachetele imaginii HDSatelit"
DESCRIPTION = "Baza OE-Alliance, driverele masinii, enigma2 HDSatelit si feedul propriu de actualizari."
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"
PV = "0.1.0"

PACKAGE_ARCH = "${MACHINE_ARCH}"
inherit packagegroup
ALLOW_EMPTY:${PN} = "1"

# driverele masinii (dinobot-dvb-modules, dinobot-libs, dinobot-hihalt, partitii...) vin prin
# MACHINE_ESSENTIAL_EXTRA_RDEPENDS din packagegroup-core-boot
#
# openssh-sftp-server (20.09.2026): SFTP prin dropbear-ul deja existent. Dropbear are deja suport SFTP
# compilat implicit (DROPBEAR_SFTPSERVER 1, SFTPSERVER_PATH "/usr/libexec/sftp-server" -- vezi
# default_options.h din sursa dropbear) -- doar binarul sftp-server lipsea din imagine, acum adaugat aici.
# NU exista niciun dropbear_%.bbappend: argumentul "-r" al dropbear e deja folosit pentru cheia de gazda
# RSA (vezi /etc/init.d/dropbear), nu e liber pentru calea sftp-server -- SFTP se activeaza doar prin
# prezenta binarului la calea compilata mai sus, nu printr-un argument de pornire nou.
# Detalii cu dovezi: STADIU-PROIECT-IMAGINE.md, sectiunea 20.09.2026 "Acces FTP prin SFTP".
#
# python3-twisted-core/-web (20.09.2026): HdsWebControl (interfata web proprie, scrisa de la zero pe
# twisted.web, cf. AGENTS.md) NU pornea deloc pe imaginea compilata -- jurnalul arata "[HdsWebControl] nu
# am putut porni: No module named 'twisted'" (gasit intr-un test pe hardware real). Cauza: pachetul lipsea
# cu totul din imagine, desi codul (plugin.py) chiar importa `twisted.web`/`twisted.internet`, doar cu
# import intarziat (in interiorul functiilor, nu la nivel de modul, de-aici de ce py_compile trecea
# oricum). Reteta `python3-twisted` (25.5.0) exista deja in stratul comun (`meta-openembedded/meta-python`,
# cu patch-uri OE-Alliance deja aplicate), impartita pe subpachete -- adaugate explicit doar cele doua
# chiar folosite de codul nostru (`-core` pentru `twisted.internet.reactor`, `-web` pentru
# `twisted.web.resource`/`server.Site`), nu pachetul meta intreg (ar aduce si `-mail`/`-conch`/`-words`
# etc., nefolosite). Detalii cu dovezi: STADIU-PROIECT-IMAGINE.md, sectiunea 20.09.2026 "HdsWebControl nu
# pornea -- twisted lipsea".
#
# ethtool (20.09.2026): gasit lipsa cu totul din manifest la investigarea bug-ului de retea de pe primul
# flash real (eth0 "deconectat" desi cablul/DHCP pareau OK). Cod propriu, clean-room, in hdsatelit-image:
# `lib/python/Components/Network.py` (self.ethtool_bin = "ethtool", getLinkState) si
# `lib/python/Screens/NetworkSetup.py` (cauta literal "Link detected: yes" in iesirea comenzii) folosesc
# NECONDITIONAT binarul `ethtool` ca sa decida daca interfata e "conectata" in ecranul de retea. Fara
# binar, comanda esueaza ("not found"), textul de iesire nu contine niciodata "Link detected: yes", deci
# ecranul arata "deconectat" INDIFERENT daca IP-ul chiar s-a obtinut prin DHCP la nivel de sistem de
# operare -- un bug real, separat de starea reala a retelei. Detalii cu dovezi: STADIU-PROIECT-IMAGINE.md,
# sectiunea 20.09.2026 "bug real de retea (eth0) pe primul boot REAL de pe flash".
#
# hdsatelit-watchdog (21.09.2026): plasa de siguranta pentru pornirea NATIVA de pe flash -- receptorul de
# test s-a blocat complet la o scanare de satelit (fir de kernel, ex. "dvb_demux_release"), fara SSH, fara
# telecomanda, doar scoaterea din priza a mers. Proces separat, cu linie proprie "respawn" in /etc/inittab
# (vezi sysvinit-inittab_2.88dsf.bbappend din acest strat), care hraneste watchdogul hardware confirmat pe
# receptor (/dev/watchdog, driver sp805-wdt, 60s) cat timp enigma2 e sanatos si opreste hranirea la un
# blocaj CONFIRMAT -- daca sistemul ingheata complet (inclusiv acest paznic), contorul hardware forteaza
# oricum o repornire dura, garantat, independent de orice software. Testat izolat pe hardware real (ambele
# ramuri). Detalii, sursa driverului si dovada: STADIU-PROIECT-IMAGINE.md, sectiunea 21.09.2026.
#
# gstreamer1.0-* (21.09.2026, pilot automat): servicemp3.cpp a fost portat la GStreamer 1.0 si compilat
# cu succes (enigma2-hdsatelit.bb, DEPENDS+EXTRA_OECONF) -- fara pachetele RUNTIME de aici, binarul ar porni
# dar orice incercare de redare locala/flux ar cadea cu "failed to create GStreamer pipeline". Alegere
# deliberata, cf. rigorii cerute (la fel ca la ofgwrite/twisted):
#   - gstreamer1.0-plugins-base: elementele de baza (playbin, decodebin, typefind, audio/video-convert) --
#     fara ele playbin nici nu se poate crea.
#   - gstreamer1.0-plugins-good: demultiplexoare/parsoare pentru containere comune fara probleme de licenta
#     (matroska, avi, qtdemux/isomp4 pentru MP4) -- acopera formatele cele mai intalnite la fisiere locale.
#   - gstreamer1.0-plugin-dvbmediasink: sink-ul hardware pentru acest SoC (u57/cortexa15hf-neon-vfpv4,
#     confirmat deja compilat in stratul comun, cf. investigatiei din STADIU-PROIECT-IMAGINE.md) -- foloseste
#     ACELASI lant de decodare hardware ca televiziunea live, nu decodare pe procesor.
# Din gstreamer1.0-plugins-bad si -ugly intra numai subpachetele alese, niciodata umbrelele (care ar aduce decodoare
# cu brevete sau licente nepotrivite):
#   - -ugly-asf: desface fisierele .wmv, .wma si .asf (video VC-1/WMV9 la decodorul placii, sunetul WMA 1/2 la
#     gstreamer1.0-libav); -bad-mpegpsdemux: .mpg si .vob (MPEG-PS; licenta dubla MPL 1.1 sau LGPL, aleasa LGPL);
#     -bad-mpegtsdemux: TS din fisiere si IPTV; -bad-opusparse: Opus in TS (opusdec e deja in -base);
#     -bad-videoparsersbad: parserele video (MPEG-2, H.264, H.265, VC-1) pentru fisiere; -ugly-dvdsub: subtitrarile
#     DVD din .vob (dvdsubparse lipeste pachetele; desenul il face decodorul propriu din enigma2);
#   - gstreamer1.0-libav, numai peste FFmpeg-ul nostru restrans si LGPL (recipes-local/ffmpeg): WMA 1/2, ALAC,
#     TrueHD/MLP si DTS fara LBR pe procesor, codorul AC3; fara decodoare video in software.
# Formatele pe care nu le acopera nici acestea, nici -good si dvbmediasink nu se redau (esec clar, cu numele
# formatului pe ecran).
#
# DVD copiat (dosar VIDEO_TS sau fisier .iso), fara decriptare: libdvdread (cu peticul din recipes-local/libdvdread,
# fara incarcarea bibliotecii de decriptare), libdvdnav (navigarea si meniurile) si libdreamdvd (redarea pe decodorul
# placii, GPL-2.0-or-later). Bibliotecile vin acum in imagine, desi serviciul DVD din enigma2 vine mai tarziu prin
# actualizari: o actualizare prin pachete nu poate aduce biblioteci noi de sistem.
#
# exFAT pe stick-uri si discuri: fuse-exfat (montarea prin FUSE, nucleul nu are driver exFAT) si exfatprogs (mkfs.exfat,
# fsck.exfat); amandoua GPL-2.0, specificatia exFAT e publica.
#
# VPN: openvpn, wireguard-tools si kernel-module-tun. Pornirea ramane la om (ecranul VPN din enigma2); imaginea nu
# porneste nicio conexiune singura. Modulul WireGuard din afara nucleului, openresolv si utilitarele FUSE cu setuid nu
# intra (BAD_RECOMMENDATIONS in hdsatelit-image.bb): nucleul are WireGuard, iar montarea FUSE se face ca root.
#
# hdsatelit-feed: /etc/opkg/hdsatelit-feed.conf, canalul public al actualizarilor prin pachete (DISTRO_FEED_URI din
# hdsatelit.conf).
#
# Codorul MPEG-2 pentru ecranul de pornire NU vine dintr-un pachet: e al nostru, scris in imagine
# (lib/gdi/mpeg2intra.cpp, un cadru I MPEG-2, brevetele au expirat in 2018), chemat prin lib/gdi/emvi.cpp si
# lib/gdi/ecranpornire.cpp. Asa poza utilizatorului devine ecran de pornire fara niciun pachet nou: ffmpeg
# ar fi insemnat 24 MB masurati pe pachetele acestei masini, iar mjpegtools inca un pachet de compilat.
# Probat pe calculator: 14 probe trecute, inclusiv poze de telefon intoarse, PNG cu paleta si fisiere stricate.
#
# hds-ocr + hds-ocr-modele (25.09.2026 seara, odata cu legatura din lib/gui/esubtitle.cpp): subtitrarile DVB citite ca
# text cand „Mărirea subtitrărilor DVB" = OCR (Components/HdsOcrSubtitrari.py). hds-ocr e procesul separat legat de
# libtesseract (Apache-2.0; enigma2 vorbeste cu el numai prin socket), pornit la cerere, fara script de init;
# hds-ocr-modele aduce modelele tessdata_fast ale celor 8 limbi cu cele mai multe subtitrari DVB (23,9 MB,
# /usr/share/hds-ocr/tessdata) si lista celor care se descarca la cerere (Components/HdsOcrModele.py).
# tesseract/leptonica vin din meta-oe cu bbappend-urile de pe PC (fara motorul vechi, fara OpenMP, fara biblioteci de
# formate); detalii si ce se probeaza: lucru-sesiune/ocr-dvb/cloud/PENTRU-PC.md.
#
# glibc-gconv-* (subtitrarile filmelor): pistele de subtitrare text din MKV care nu sunt UTF-8 (Windows-1250, ISO-8859-2,
# ISO-8859-15/16, UTF-16) se convertesc de GStreamer prin iconv, care are nevoie de modulele gconv ale limbii (~48 KB
# impreuna). Fisierele de subtitrare de langa film nu au nevoie de ele: le citeste Python.
#
# hds-navigator (0.2.6, etapa N1 a navigatorului web): navigatorul web pe televizor, functie a imaginii, pornit numai
# la cerere din meniu (Media > Navigator web), din interfata web (/navigator) si pentru interfata web a camului.
# Lansatorul nostru (recipes-local/hds-navigator) pe WPE WebKit 2.54 (recipes-local/wpewebkit), desen direct pe
# /dev/fb0, fara Wayland, fara video in WebKit, fara JIT. Prin dependente aduce: libwpewebkit-2.0-1 (cu WPEWebProcess
# si WPENetworkProcess), ICU 77 cu datele filtrate la limbile meniului (recipes-local/icu), libsoup 3, libepoxy
# (recipes-local/libepoxy), woff2 si brotli, libwebp, libxslt, libgcrypt, libxkbcommon si fonturile DejaVu Sans si
# Serif. Imaginea nu are feed online, deci navigatorul sta in imagine si nu se mai ofera instalarea lui. Marimea
# masurata la constructie: lucru-sesiune/pilot-26-09/hbbtv/n1-n2/progres.md.
#
# hdsatelit-noduri (0.2.7, lotul hbbtv-receptor-027): `mdev -s &` din S06hotplug.sh (initscripts, meta-oe-alliance) pune la
# fiecare pornire, dupa udev, root:root 0660 pe toate nodurile din /dev, si pe /dev/null, /dev/urandom, /dev/tty, /dev/ptmx.
# Navigatorul HbbTV ruleaza ca hdsnav si cadea cu SIGABRT (GLib nu putea deschide /dev/null). Scriptul S42 al pachetului
# asteapta mdev si pune la loc numai null/zero/full/random/urandom 0666, tty/ptmx 0666 root:tty si fb0/mali 0660 root:video.
# Dovezile (proba pe .122, mdev care strica un nod refacut): lucru-sesiune/pilot-26-09/hbbtv/receptor-027/progres.md.
#
# hdsatelit-jurnal (0.5.0, lotul imagine-050): jurnalul sistemului de dinainte de o oprire necurata pastrat la pornire
# (/home/root/logs/messages.cadere) si jurnalul driverului Wi-Fi rtl8188fu coborat la erori dupa incarcare; rotirea
# jurnalului (1024 KB x 4) e in busybox_%.bbappend.
#
# gstreamer1.0-plugins-bad-dash (0.5.0, lotul dash-050): elementul dashdemux, pentru canalele DVB-I si fluxurile IPTV
# in MPEG-DASH (.mpd). Pe 0.4.12 `gst-inspect-1.0 dashdemux` dadea "No such element" si niciun canal .mpd nu pornea.
# dashdemux2 (gstreamer1.0-plugins-good-adaptivedemux2, in imagine din 0.4.0) nu ajunge: servicemp3 face "playbin"
# (playbin v2, cu decodebin2), iar adaptivedemux2 refuza trecerea la READY fara parinte "streams-aware" (numai
# urisourcebin, decodebin3, playbin3). decodebin2 il scoate si trece la urmatorul element cu aceleasi caps: dashdemux
# (rangul PRIMARY, gst-plugins-bad 1.28.4, ext/dash), care nu cere asa ceva. Optiunea "dash" e deja in PACKAGECONFIG-ul
# implicit al retetei (cu libxml2, deja in imagine), deci nu e nevoie de bbappend. Aduce prin dependinte
# libgstadaptivedemux-1.0-0, libgsturidownloader-1.0-0 si libgstisoff-1.0-0; impreuna ~320 KB instalati, LGPL-2.1+.
# Dovezile si proba: lucru-sesiune/pilot-26-09/dash-050/progres.md.
#
# gstreamer1.0-plugins-bad-hls (0.5.0, lotul hls-050): elementul hlsdemux, pentru canalele DVB-I si fluxurile IPTV in
# HLS (.m3u8). Acelasi motiv ca la dash: hlsdemux2 (adaptivedemux2, rangul PRIMARY + 1) cere parinte "streams-aware" si
# decodebin2 din playbin v2 il scoate; hlsdemux clasic (rangul PRIMARY, ext/hls) nu cere asa ceva. Optiunea "hls" e deja
# in PACKAGECONFIG-ul implicit (descifrarea segmentelor AES-128 prin openssl: libcrypto3, deja in imagine), iar
# peticele pentru hlsdemux sunt deja in bbappend-ul din meta-oe-alliance; deci nici aici bbappend. Foloseste aceleasi
# biblioteci libgstadaptivedemux-1.0-0 si libgsturidownloader-1.0-0 ca dash: in plus numai libgsthls.so, ~88 KB
# instalati, LGPL-2.1+. Dovezile si proba: lucru-sesiune/pilot-26-09/hls-050/progres.md.
#
# hdsatelit-ipv6 (0.5.0, lotul strat-050): IPv6 oprit din fabrica. Scriptul rcS S40 pune disable_ipv6 = 1 (all si
# default) cand lipseste fisierul-semn /etc/hds-ipv6-pornit si 0 cand exista; clientul DHCPv6 are aceeasi poarta
# (recipes-local/odhcp6c). Semnul il pune si il scoate setarea IPv6 din enigma2.
#
# libdvbcsa (0.5.0, lotul strat-050): biblioteca algoritmului comun de cifrare DVB (CSA), GPL-2.0-or-later, sursa fixata
# in recipes-local/libdvbcsa; o va folosi programul care descifreaza mai tarziu inregistrarile, care nu e inca in
# imagine (fara /usr/bin/hds-decodare alegerea ramane ascunsa in enigma2).
RDEPENDS:${PN} = "\
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugin-dvbmediasink \
    packagegroup-core-boot \
    packagegroup-base \
    enigma2-hdsatelit \
    hdsatelit-skin \
    hdsatelit-bootlogo \
    hdsatelit-watchdog \
    hdsatelit-netguard \
    hdsatelit-noduri \
    hdsatelit-jurnal \
    hdsatelit-ipv6 \
    hdsatelit-fonturi-tiresias \
    hdsatelit-feed \
    tuxbox-common \
    showiframe \
    aio-grab \
    bash \
    dropbear \
    openssh-sftp-server \
    python3-twisted-core \
    python3-twisted-web \
    opkg \
    procps \
    tzdata \
    wget \
    e2fsprogs-mke2fs \
    e2fsprogs-e2fsck \
    e2fsprogs-tune2fs \
    e2fsprogs-resize2fs \
    dosfstools \
    mtools \
    parted \
    util-linux-blkid \
    util-linux-sfdisk \
    partitions-by-name \
    volatile-media \
    modutils-loadscript \
    early-configure \
    rc-local \
    wireless-tools \
    wpa-supplicant \
    rt8188fu \
    firmware-rt8188fu \
    iproute2 \
    hdparm \
    ca-certificates \
    ofgwrite \
    ethtool \
    hds-ocr \
    hds-ocr-modele \
    glibc-gconv-cp1250 \
    glibc-gconv-iso8859-2 \
    glibc-gconv-iso8859-15 \
    glibc-gconv-iso8859-16 \
    glibc-gconv-utf-16 \
    hds-navigator \
    gstreamer1.0-plugins-ugly-asf \
    gstreamer1.0-plugins-ugly-dvdsub \
    gstreamer1.0-plugins-bad-mpegpsdemux \
    gstreamer1.0-plugins-bad-mpegtsdemux \
    gstreamer1.0-plugins-bad-opusparse \
    gstreamer1.0-plugins-bad-videoparsersbad \
    gstreamer1.0-plugins-bad-dash \
    gstreamer1.0-plugins-bad-hls \
    gstreamer1.0-libav \
    libdvdread \
    libdvdnav \
    libdreamdvd \
    libdvbcsa \
    fuse-exfat \
    exfatprogs \
    openvpn \
    wireguard-tools \
    kernel-module-tun \
"
