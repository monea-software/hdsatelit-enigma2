# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# FFmpeg pentru imaginea HD Satelit: o biblioteca LGPL-2.1-or-later, redistribuibila, numai cu decodoarele si codorul
# de care are nevoie receptorul. Se aplica peste reteta OE si peste bbappend-ul stratului comun (care pune gpl, openssl,
# x264, x265, librtmp, srt, libbluray, libxml2, libfreetype si dav1d: cu gpl si OpenSSL 3 configure-ul FFmpeg cere
# --enable-nonfree, iar biblioteca iesita spune "nonfree and unredistributable").
#
# Ce ramane (lista hotarata pentru imagine):
#   decodoare: alac (ALAC), truehd si mlp (TrueHD/MLP din fisiere), dca (DTS, fara componenta LBR: peticul
#              0001-dca-fara-lbr.patch), wmav1 si wmav2 (WMA 1 si 2, sunetul fisierelor .wmv/.wma/.asf);
#   codoare: ac3 si ac3_fixed (sunetul DTS recodat in AC3 5.1 pentru iesirea digitala; varianta potrivita se alege
#            dupa proba de procesor pe receptor);
#   parsere: dca si ac3 (plus mlp, cerut de configure-ul FFmpeg pentru decodoarele truehd si mlp).
# Fara demultiplexoare, multiplexoare, protocoale, dispozitive, accelerari si filtre de flux: desfacerea fisierelor o
# face GStreamer. Nu intra: gpl, version3, nonfree, openssl, peticul AC-4 al stratului comun (ffmpeg_ac4.patch, scos),
# WMA Pro si WMA Lossless, E-AC3, AAC, H.264/H.265 si celelalte decodoare video.
#
# Constructia se opreste daca la configurare licenta nu e LGPL version 2.1 or later, daca gpl, version3, nonfree sau
# o biblioteca scoasa e pornita, daca lista decodoarelor, codoarelor sau parserelor difera de cea de mai sus sau daca a
# ramas vreun demultiplexor, multiplexor, protocol, dispozitiv, accelerare sau filtru de flux; dupa instalare, daca
# libavcodec nu spune LGPL sau daca o biblioteca libav*/libsw* cere o biblioteca scoasa (libssl, libcrypto ...).
# Programul ffmpeg (pachetul ffmpeg) ramane numai pentru probele de pe calculator; imaginea ia numai bibliotecile.

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI:remove = "file://ffmpeg_ac4.patch"
SRC_URI += "file://0001-dca-fara-lbr.patch"

PR:append = ".hds1"

PACKAGECONFIG:remove = "gpl openssl x264 x265 librtmp srt libbluray libxml2 libfreetype dav1d avdevice alsa theora"

# la coada lui EXTRA_FFCONF din bbappend-ul stratului comun: configure ia optiunile in ordine, deci --disable-* de aici
# le anuleaza pe --enable-* de dinainte
EXTRA_FFCONF:append = " \
    --disable-gpl \
    --disable-version3 \
    --disable-nonfree \
    --disable-decoders \
    --enable-decoder=alac \
    --enable-decoder=truehd \
    --enable-decoder=mlp \
    --enable-decoder=dca \
    --enable-decoder=wmav1 \
    --enable-decoder=wmav2 \
    --disable-encoders \
    --enable-encoder=ac3 \
    --enable-encoder=ac3_fixed \
    --disable-parsers \
    --enable-parser=dca \
    --enable-parser=ac3 \
    --disable-demuxers \
    --disable-muxers \
    --disable-protocols \
    --disable-devices \
    --disable-hwaccels \
    --disable-bsfs \
"

HDS_FFMPEG_DECODOARE = "alac dca mlp truehd wmav1 wmav2"
HDS_FFMPEG_CODOARE = "ac3 ac3_fixed"
HDS_FFMPEG_PARSERE = "ac3 dca mlp"

# componentele pornite de un fel, citite din config_components.h ("#define CONFIG_<NUME>_<FEL> 1"), sortate
hds_ffmpeg_pornite() {
	grep -E "^#define CONFIG_[A-Z0-9_]+_$1 1\$" ${B}/config_components.h | \
		sed -E "s/^#define CONFIG_([A-Z0-9_]+)_$1 1\$/\1/" | tr 'A-Z' 'a-z' | sort | tr '\n' ' ' | sed 's/ $//'
}

do_configure:append() {
	grep -q '^#define FFMPEG_LICENSE "LGPL version 2.1 or later"$' ${B}/config.h || \
		bbfatal "ffmpeg: licenta din config.h nu e LGPL version 2.1 or later"
	for o in GPL VERSION3 NONFREE OPENSSL LIBX264 LIBX265 LIBRTMP LIBSRT LIBBLURAY LIBXML2 LIBFREETYPE LIBDAV1D; do
		if grep -q "^CONFIG_$o=yes" ${B}/ffbuild/config.mak; then
			bbfatal "ffmpeg: CONFIG_$o e pornit"
		fi
	done
	[ "$(hds_ffmpeg_pornite DECODER)" = "${HDS_FFMPEG_DECODOARE}" ] || \
		bbfatal "ffmpeg: decodoarele pornite ($(hds_ffmpeg_pornite DECODER)) nu sunt ${HDS_FFMPEG_DECODOARE}"
	[ "$(hds_ffmpeg_pornite ENCODER)" = "${HDS_FFMPEG_CODOARE}" ] || \
		bbfatal "ffmpeg: codoarele pornite ($(hds_ffmpeg_pornite ENCODER)) nu sunt ${HDS_FFMPEG_CODOARE}"
	[ "$(hds_ffmpeg_pornite PARSER)" = "${HDS_FFMPEG_PARSERE}" ] || \
		bbfatal "ffmpeg: parserele pornite ($(hds_ffmpeg_pornite PARSER)) nu sunt ${HDS_FFMPEG_PARSERE}"
	for f in DEMUXER MUXER PROTOCOL INDEV OUTDEV HWACCEL BSF; do
		[ -z "$(hds_ffmpeg_pornite $f)" ] || bbfatal "ffmpeg: componente $f ramase: $(hds_ffmpeg_pornite $f)"
	done
	bbnote "ffmpeg: LGPL; decodoare ${HDS_FFMPEG_DECODOARE}; codoare ${HDS_FFMPEG_CODOARE}; parsere ${HDS_FFMPEG_PARSERE}"
}

do_install:append() {
	codec=$(ls ${D}${libdir}/libavcodec.so.* | head -n 1)
	[ -f "$codec" ] || bbfatal "ffmpeg: lipseste libavcodec.so"
	grep -aq "libavcodec license: LGPL version 2.1 or later" "$codec" || bbfatal "ffmpeg: libavcodec nu spune LGPL"
	# libavcodec tine si linia de configurare (avcodec_configuration), unde apare --disable-nonfree pus aici; se
	# cauta deci numai licenta "nonfree" si optiunile care ar porni ceva interzis
	for s in "nonfree and unredistributable" "--enable-nonfree" "--enable-gpl" "--enable-version3" "--enable-openssl"; do
		if grep -aqF -- "$s" "$codec"; then
			bbfatal "ffmpeg: libavcodec contine $s"
		fi
	done
	for b in ${D}${libdir}/libav*.so.* ${D}${libdir}/libsw*.so.*; do
		[ -L "$b" ] && continue
		cerute=" $(${OBJDUMP} -p "$b" | sed -n 's/^ *NEEDED *//p' | tr '\n' ' ')"
		for s in libssl libcrypto librtmp libxml2 libbluray libx264 libx265 libfreetype libdav1d libsrt libtheora libasound; do
			case "$cerute" in
			*" $s"*) bbfatal "ffmpeg: $(basename $b) cere $s ($cerute)" ;;
			esac
		done
	done
}
