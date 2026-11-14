# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# FFmpeg-ul PROPRIU al lui Media Center (Kodi), separat de cel al imaginii. 13.11.2026, agentul KOD.
# De ce: FFmpeg-ul imaginii (recipes-local/ffmpeg/ffmpeg_9.%.bbappend) e taiat intentionat: fara demultiplexoare,
# protocoale si aproape toate decodoarele, fiindca in imagine fisierele le desface GStreamer. Kodi insa foloseste FFmpeg
# pentru tot (desfacerea MP4/MKV/TS, sunetul AAC/MP3/AC3, pozele JPG/PNG, sunetele interfetei, subtitrarile); cu cel al
# imaginii Media Center cadea la pornire (SIGSEGV la incarcarea sunetelor interfetei, „image/jpg” nerecunoscut; proba pe
# receptorul de probe, 13.11.2026 18:19). Hotararea pentru imagine ramane neatinsa: aici e o copie a ACELEIASI versiuni (9.0.2, aceleasi
# nume de biblioteci: libavcodec.so.63 ...), LGPL-2.1-or-later (fara gpl, version3, nonfree), cu decodoarele,
# demultiplexoarele, parserele si protocoalele FFmpeg, instalata in /usr/lib/kodi/ffmpeg si incarcata NUMAI de Kodi
# (stb-kodi-%.bbappend pune dosarul la inceputul LD_LIBRARY_PATH in invelisul /usr/bin/kodi). OpenSSL 3 (Apache-2.0)
# pentru https e permis fara gpl. Video-ul ramane pe decodorul receptorului (libstbplayer); decodoarele video din FFmpeg
# sunt numai rezerva Kodi.
require recipes-multimedia/ffmpeg/ffmpeg_${PV}.bb
FILESEXTRAPATHS:prepend := "${COREBASE}/meta/recipes-multimedia/ffmpeg/ffmpeg:"

BPN = "ffmpeg"
# reteta de baza spune PROVIDES = "libav"; copia lui Media Center nu furnizeaza nimic altora
PROVIDES = "${PN}"
SUMMARY = "FFmpeg pentru Media Center (Kodi), LGPL, separat de cel al imaginii"

PACKAGECONFIG = "avfilter avcodec avformat swresample swscale openssl"
EXTRA_FFCONF:append = " --disable-gpl --disable-version3 --disable-nonfree --disable-programs --disable-doc"

LIBDIR_MC = "${libdir}/kodi/ffmpeg"

do_install:append() {
    install -d ${D}${LIBDIR_MC}
    for l in avcodec avfilter avformat avutil swresample swscale; do
        mv ${D}${libdir}/lib$l.so.* ${D}${LIBDIR_MC}/ || bbfatal "media-center-ffmpeg: lipseste lib$l"
    done
    rm -rf ${D}${libdir}/*.so ${D}${libdir}/*.a ${D}${libdir}/pkgconfig ${D}${includedir} ${D}${bindir} ${D}${datadir}
    grep -aq "LGPL version 2.1 or later" ${D}${LIBDIR_MC}/libavcodec.so.* || \
        bbfatal "media-center-ffmpeg: libavcodec nu spune LGPL version 2.1 or later"
}

# un singur pachet, fara nume de biblioteca (ar ciocni cu libavcodec63 ... ale imaginii) si fara sa se dea drept
# furnizorul lor: Kodi si restul imaginii raman legate de pachetele imaginii; copia de aici o alege numai invelisul Kodi
PACKAGES = "${PN}-dbg ${PN}"
FILES:${PN} = "${LIBDIR_MC}/*.so.*"
FILES:${PN}-dbg = "${LIBDIR_MC}/.debug"
LICENSE:${PN} = "LGPL-2.1-or-later"
DEBIAN_NOAUTONAME:${PN} = "1"
PRIVATE_LIBS = "libavcodec.so.63 libavfilter.so.12 libavformat.so.63 libavutil.so.61 libswresample.so.7 libswscale.so.10"
RDEPENDS:${PN} = ""
RRECOMMENDS:${PN} = ""
PR = "r0.hds1"
