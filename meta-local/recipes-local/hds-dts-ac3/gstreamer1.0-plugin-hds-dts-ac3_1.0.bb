SUMMARY = "HDSatelit: sunetul DTS recodat in AC3 pentru iesirea digitala (elementul GStreamer hdsdtsac3)"
DESCRIPTION = "Element GStreamer care primeste DTS (audio/x-dts, de la dcaparse) si da AC3 (audio/x-ac3) pentru \
HDMI sau iesirea optica, cand televizorul sau amplificatorul stie AC3 dar nu DTS: nucleul DTS decodat cu \
libavcodec (core_only, cel mult 5.1), recodat in AC3 la 640 kb/s cu codorul AC3 din libavcodec. Se foloseste numai \
cand dvbaudiosink nu primeste DTS (recodarea pornita, peticul din gstreamer1.0-plugin-dvbmediasink.bbappend de \
alaturi). Monea Software pentru HD Satelit."
LICENSE = "GPL-2.0-only"
LIC_FILES_CHKSUM = "file://gsthdsdtsac3.c;beginline=2;endline=3;md5=fb87bc14f85a0e8e73d2e038b3c2f7e1"
PV = "1.0"

SRC_URI = "file://gsthdsdtsac3.c"
S = "${UNPACKDIR}"

# ffmpeg: FFmpeg-ul imaginii (recipes-local/ffmpeg/ffmpeg_8.%.bbappend: LGPL, decodorul dca, codoarele ac3 si
# ac3_fixed); gstreamer1.0-plugins-base: gstreamer-audio-1.0
DEPENDS = "gstreamer1.0 gstreamer1.0-plugins-base ffmpeg"

inherit pkgconfig

do_configure[noexec] = "1"

# Constructia se opreste daca libavcodec din sysroot nu e cel LGPL al imaginii (fara el elementul s-ar lega de o
# biblioteca nedistribuibila) sau daca ii lipseste decodorul DTS ori codorul AC3.
do_compile() {
    if grep -q "$(printf '\r')" ${S}/gsthdsdtsac3.c; then
        bbfatal "hds-dts-ac3: sursa are sfarsit de rand CRLF"
    fi
    codec=$(ls ${STAGING_LIBDIR}/libavcodec.so.* | head -n 1)
    [ -f "$codec" ] || bbfatal "hds-dts-ac3: lipseste libavcodec in sysroot"
    grep -aq "libavcodec license: LGPL version 2.1 or later" "$codec" || bbfatal "hds-dts-ac3: libavcodec nu e LGPL"
    for c in "DCA (DTS Coherent Acoustics)" "ATSC A/52A (AC-3)"; do
        grep -aqF "$c" "$codec" || bbfatal "hds-dts-ac3: libavcodec fara $c"
    done
    ${CC} ${CFLAGS} ${LDFLAGS} -std=gnu11 -shared -fPIC -Wall -Wextra -Werror=implicit-function-declaration \
        -DVERSIUNE='"${PV}"' -o ${B}/libgsthdsdtsac3.so ${S}/gsthdsdtsac3.c \
        $(pkg-config --cflags --libs gstreamer-1.0 gstreamer-audio-1.0 libavcodec libavutil)
}

do_install() {
    install -d ${D}${libdir}/gstreamer-1.0
    install -m 0755 ${B}/libgsthdsdtsac3.so ${D}${libdir}/gstreamer-1.0/libgsthdsdtsac3.so
}

FILES:${PN} = "${libdir}/gstreamer-1.0/libgsthdsdtsac3.so"
# dcaparse (audioparsers din -good) pune cadrele DTS intregi in fata elementului
RDEPENDS:${PN} = "gstreamer1.0-plugins-good-audioparsers"
