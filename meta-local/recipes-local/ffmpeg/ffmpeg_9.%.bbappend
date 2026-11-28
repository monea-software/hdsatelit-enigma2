# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# FFmpeg pentru imaginea HD Satelit: o biblioteca LGPL-2.1-or-later, redistribuibila, numai cu decodoarele si codoarele
# de care are nevoie receptorul. Se aplica peste reteta OE si peste bbappend-ul stratului comun (care pune gpl, openssl,
# x264, x265, librtmp, srt, libbluray, libxml2, libfreetype si dav1d: cu gpl si OpenSSL 3 configure-ul FFmpeg cere
# --enable-nonfree, iar biblioteca iesita spune "nonfree and unredistributable").
#
# Ce ramane (lista hotarata pentru imagine):
#   decodoare: alac (ALAC), truehd si mlp (TrueHD/MLP din fisiere), dca (DTS, fara componenta LBR: peticul
#              0001-dca-fara-lbr.patch), wmav1 si wmav2 (WMA 1 si 2, sunetul fisierelor .wmv/.wma/.asf);
#              0.8.0 (FFM0, 25.11.2026): mp3float, opus, vorbis si flac (formate fara brevete), pentru pluginurile care
#              reda radio de pe internet direct prin FFmpeg (IPAudioPro: avformat_open_input, avcodec_find_decoder,
#              swr_convert, iesirea pe ALSA). Decodorul opus face si legatura libavcodec -> libswresample (configure:
#              "enabled opus_decoder && prepend avcodec_deps swresample"), fara de care pluginul nu se incarca
#              ("undefined symbol: swr_convert");
#              0.8.0 (FFM1, 25.11.2026, hotararea lui Eduard din 25.11.2026 07:42: "AAC intreg, ca la OE-Alliance"): aac si
#              aac_latm (AAC-LC, HE-AAC v1 si v2: SBR si PS sunt lipite in decodorul aac), pentru radio de pe internet si
#              pentru fluxurile AAC pe care placa nu le ia; sunetul canalelor si al filmelor merge tot prin placa. Varianta
#              in virgula mobila (aac), nu aac_fixed: masinile MIPS ale imaginii au virgula mobila in hardware (DEFAULTTUNE
#              mips32el, compilare -mhard-float), ca la OE-Alliance; aac fata de aac_fixed nu e masurat pe MIPS;
#              0.8.0 (DLB1, 25.11.2026, hotararea lui Eduard din 25.11.2026 09:03: "Da" la decodoarele AC-3 si E-AC-3): ac3 si
#              eac3 (Dolby Digital si Dolby Digital Plus), pentru receptoarele a caror placa nu are decodor Dolby (masurat pe
#              ZGEMMA H8: canalele si filmele cu AC-3 / E-AC-3 erau mute); unde placa decodeaza sau trece sunetul mai departe,
#              sunetul ramane pe placa. Varianta in virgula mobila (ac3), nu ac3_fixed: decodorul eac3 se construieste numai
#              peste ac3 in virgula mobila (configure: eac3_decoder_select="ac3_decoder"), deci ac3_fixed ar fi fost un al
#              doilea decodor AC-3 in plus; MIPS-urile au virgula mobila in hardware (vezi mai sus); nemasurat pe MIPS;
#   codoare: ac3 si ac3_fixed (sunetul DTS recodat in AC3 5.1 pentru iesirea digitala; varianta potrivita se alege
#            dupa proba de procesor pe receptor);
#   parsere: dca si ac3 (plus mlp, cerut de configure-ul FFmpeg pentru decodoarele truehd si mlp); din 0.8.0 si flac si
#            mpegaudio, cerute de demultiplexoarele flac si mp3 (asa le da configure); din FFM1 si aac si aac_latm;
#   demultiplexoare (0.8.0): mp3, ogg, flac si hls (radio de pe internet; hls trage dupa el aac, ac3, eac3, mov si mpegts,
#            numai pentru desfacere); din FFM1 si aac (ADTS) si loas (LATM); gstreamer1.0-libav nu inregistreaza niciun demultiplexor din
#            lista (rang NONE), deci desfacerea fisierelor o face tot GStreamer;
#   protocoale (0.8.0): http, https, tcp, tls si crypto (segmentele HLS cifrate AES-128, din libavutil; listele HLS le
#            citeste demultiplexorul hls prin http/https); TLS prin GnuTLS (LGPL-2.1-or-later, deja in imagine), niciodata
#            prin OpenSSL.
# Fara multiplexoare, dispozitive si accelerari. Nu intra: gpl, version3, nonfree, openssl, peticul AC-4 al stratului
# comun (ffmpeg_ac4.patch, scos), WMA Pro si WMA Lossless, DTS-HD, AC-4, MPEG-H, FDK AAC, H.264/H.265/VVC si
# celelalte decodoare video.
#
# Constructia se opreste daca la configurare licenta nu e LGPL version 2.1 or later, daca gpl, version3, nonfree sau
# o biblioteca scoasa e pornita, daca GnuTLS nu e pornit, daca lista decodoarelor, codoarelor, parserelor,
# demultiplexoarelor, protocoalelor sau filtrelor de flux difera de cea de mai jos sau daca a ramas vreun multiplexor,
# dispozitiv sau accelerare; dupa instalare, daca libavcodec nu spune LGPL, daca o biblioteca libav*/libsw* cere o
# biblioteca scoasa (libssl, libcrypto ...), daca libavcodec nu cere libswresample sau libavformat nu cere libgnutls.
# Programul ffmpeg (pachetul ffmpeg) ramane numai pentru probele de pe calculator; imaginea ia numai bibliotecile.

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI:remove = "file://ffmpeg_ac4.patch"
SRC_URI += "file://0001-dca-fara-lbr.patch"

# .hds2 (0.8.0, FFM0): FFmpeg largit pentru radio de pe internet; .hds3 (FFM1): si AAC; .hds4 (DLB1): si AC-3 / E-AC-3;
# mai mare decat cele dinainte, deci receptoarele il pot lua din feed
PR:append = ".hds4"

PACKAGECONFIG:remove = "gpl openssl x264 x265 librtmp srt libbluray libxml2 libfreetype dav1d avdevice alsa theora"

# GnuTLS pentru https (reteta OE nu are PACKAGECONFIG pentru el)
DEPENDS += "gnutls"

# la coada lui EXTRA_FFCONF din bbappend-ul stratului comun: configure ia optiunile in ordine, deci --disable-* de aici
# le anuleaza pe --enable-* de dinainte
EXTRA_FFCONF:append = " \
    --disable-gpl \
    --disable-version3 \
    --disable-nonfree \
    --disable-openssl \
    --enable-gnutls \
    --disable-decoders \
    --enable-decoder=alac \
    --enable-decoder=truehd \
    --enable-decoder=mlp \
    --enable-decoder=dca \
    --enable-decoder=wmav1 \
    --enable-decoder=wmav2 \
    --enable-decoder=mp3float \
    --enable-decoder=opus \
    --enable-decoder=vorbis \
    --enable-decoder=flac \
    --enable-decoder=aac \
    --enable-decoder=aac_latm \
    --enable-decoder=ac3 \
    --enable-decoder=eac3 \
    --disable-encoders \
    --enable-encoder=ac3 \
    --enable-encoder=ac3_fixed \
    --disable-parsers \
    --enable-parser=dca \
    --enable-parser=ac3 \
    --enable-parser=aac \
    --enable-parser=aac_latm \
    --disable-demuxers \
    --enable-demuxer=mp3 \
    --enable-demuxer=ogg \
    --enable-demuxer=flac \
    --enable-demuxer=hls \
    --enable-demuxer=aac \
    --enable-demuxer=loas \
    --disable-muxers \
    --disable-protocols \
    --enable-protocol=http \
    --enable-protocol=https \
    --enable-protocol=tcp \
    --enable-protocol=tls \
    --enable-protocol=crypto \
    --disable-devices \
    --disable-hwaccels \
    --disable-bsfs \
"

HDS_FFMPEG_DECODOARE = "aac aac_latm ac3 alac dca eac3 flac mlp mp3float opus truehd vorbis wmav1 wmav2"
HDS_FFMPEG_CODOARE = "ac3 ac3_fixed"
HDS_FFMPEG_PARSERE = "aac aac_latm ac3 dca flac mlp mpegaudio"
HDS_FFMPEG_DEMULTIPLEXOARE = "aac ac3 eac3 flac hls loas mov mp3 mpegts ogg"
HDS_FFMPEG_PROTOCOALE = "crypto http https tcp tls"
HDS_FFMPEG_FILTRE_FLUX = ""

# componentele pornite de un fel, citite din config_components.h ("#define CONFIG_<NUME>_<FEL> 1"), sortate
hds_ffmpeg_pornite() {
	grep -E "^#define CONFIG_[A-Z0-9_]+_$1 1\$" ${B}/config_components.h | \
		sed -E "s/^#define CONFIG_([A-Z0-9_]+)_$1 1\$/\1/" | tr 'A-Z' 'a-z' | sort | tr '\n' ' ' | sed 's/ $//'
}

# compara lista pornita a unui fel cu lista hotarata; se opreste la orice diferenta
hds_ffmpeg_lista() {
	[ "$(hds_ffmpeg_pornite $1)" = "$2" ] || bbfatal "ffmpeg: $1 pornite ($(hds_ffmpeg_pornite $1)) nu sunt $2"
}

do_configure:append() {
	grep -q '^#define FFMPEG_LICENSE "LGPL version 2.1 or later"$' ${B}/config.h || \
		bbfatal "ffmpeg: licenta din config.h nu e LGPL version 2.1 or later"
	for o in GPL VERSION3 NONFREE OPENSSL LIBX264 LIBX265 LIBRTMP LIBSRT LIBBLURAY LIBXML2 LIBFREETYPE LIBDAV1D GMP MBEDTLS LIBTLS; do
		if grep -q "^CONFIG_$o=yes" ${B}/ffbuild/config.mak; then
			bbfatal "ffmpeg: CONFIG_$o e pornit"
		fi
	done
	grep -q "^CONFIG_GNUTLS=yes" ${B}/ffbuild/config.mak || bbfatal "ffmpeg: GnuTLS nu e pornit (https)"
	hds_ffmpeg_lista DECODER "${HDS_FFMPEG_DECODOARE}"
	hds_ffmpeg_lista ENCODER "${HDS_FFMPEG_CODOARE}"
	hds_ffmpeg_lista PARSER "${HDS_FFMPEG_PARSERE}"
	hds_ffmpeg_lista DEMUXER "${HDS_FFMPEG_DEMULTIPLEXOARE}"
	hds_ffmpeg_lista PROTOCOL "${HDS_FFMPEG_PROTOCOALE}"
	hds_ffmpeg_lista BSF "${HDS_FFMPEG_FILTRE_FLUX}"
	for f in MUXER INDEV OUTDEV HWACCEL; do
		[ -z "$(hds_ffmpeg_pornite $f)" ] || bbfatal "ffmpeg: componente $f ramase: $(hds_ffmpeg_pornite $f)"
	done
	bbnote "ffmpeg: LGPL, GnuTLS; decodoare ${HDS_FFMPEG_DECODOARE}; codoare ${HDS_FFMPEG_CODOARE}; parsere ${HDS_FFMPEG_PARSERE}; demultiplexoare ${HDS_FFMPEG_DEMULTIPLEXOARE}; protocoale ${HDS_FFMPEG_PROTOCOALE}; filtre de flux ${HDS_FFMPEG_FILTRE_FLUX}"
}

do_install:append() {
	codec=$(ls ${D}${libdir}/libavcodec.so.* | head -n 1)
	[ -f "$codec" ] || bbfatal "ffmpeg: lipseste libavcodec.so"
	grep -aq "libavcodec license: LGPL version 2.1 or later" "$codec" || bbfatal "ffmpeg: libavcodec nu spune LGPL"
	# libavcodec tine si linia de configurare (avcodec_configuration), unde apar --disable-nonfree si --disable-openssl
	# puse aici; se cauta deci numai licenta "nonfree" si optiunile care ar porni ceva interzis
	for s in "nonfree and unredistributable" "--enable-nonfree" "--enable-gpl" "--enable-version3" "--enable-openssl"; do
		if grep -aqF -- "$s" "$codec"; then
			bbfatal "ffmpeg: libavcodec contine $s"
		fi
	done
	for b in ${D}${libdir}/libav*.so.* ${D}${libdir}/libsw*.so.*; do
		[ -L "$b" ] && continue
		cerute=" $(${OBJDUMP} -p "$b" | sed -n 's/^ *NEEDED *//p' | tr '\n' ' ')"
		for s in libssl libcrypto librtmp libxml2 libbluray libx264 libx265 libfreetype libdav1d libsrt libtheora libasound libgmp libmbedtls; do
			case "$cerute" in
			*" $s"*) bbfatal "ffmpeg: $(basename $b) cere $s ($cerute)" ;;
			esac
		done
		case "$(basename $b)" in
		libavcodec.so.*)
			case "$cerute" in *" libswresample.so"*) ;; *) bbfatal "ffmpeg: libavcodec nu cere libswresample ($cerute)" ;; esac ;;
		libavformat.so.*)
			case "$cerute" in *" libgnutls.so"*) ;; *) bbfatal "ffmpeg: libavformat nu cere libgnutls ($cerute)" ;; esac ;;
		esac
	done
}
