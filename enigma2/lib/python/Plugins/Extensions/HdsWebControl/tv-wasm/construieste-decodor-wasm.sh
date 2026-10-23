#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
#
# construieste-decodor-wasm.sh: construieste decodorul wasm al paginii "TV in browser" (hdsdec.js + hdsdec.wasm, langa
# acest fisier in imagine). OpenEmbedded nu are emscripten, deci fisierele stau gata facute in depozit; scriptul le
# reface oricand, din aceleasi surse:
#   - FFmpeg 8.1.3 (https://ffmpeg.org/releases/ffmpeg-8.1.3.tar.xz, sha256 verificat mai jos; semnatura .asc a
#     cheii "FFmpeg release signing key", amprenta FCF9 86EA 15E6 E293 A564 4F10 B432 2F04 D676 58D8), numai libavcodec
#     si libavutil, LGPL-2.1-or-later: FARA --enable-gpl, FARA --enable-nonfree;
#   - decodoarele: mpeg1video, mpeg2video, mp2float, mp3float, ac3 (brevetele lor au expirat); fara E-AC-3, H.264,
#     HEVC, AAC (numai variantele libere);
#   - emscripten 6.0.9, containerul oficial emscripten/emsdk:6.0.9
#     (sha256:96617f27fe16421588241def73908fd348a7f9d260440ed0d00b36dcf7a063cc);
#   - puntea noastra hdsdec.c (de langa acest fisier).
# Fara fire (pagina receptorului e http, deci fara SharedArrayBuffer), cu SIMD wasm (-msimd128: Chrome 91+, Firefox
# 89+, Safari 16.4+). Construirea dureaza cam un minut.
#
# Rulare (din WSL, cu docker): bash construieste-decodor-wasm.sh [dosarul de iesire]
#   sursa FFmpeg: $LUCRU/ffmpeg-8.1.3.tar.xz (LUCRU implicit ~/mpeg2-wasm); se descarca daca lipseste
#   iesirea implicita: $LUCRU/iesire
# La sfarsit: sha256 al fisierelor si bibliotecile emscripten legate in hdsdec.wasm (pentru ecranul Licente).
set -euo pipefail

AICI="$(cd "$(dirname "$0")" && pwd)"
LUCRU="${LUCRU:-$HOME/mpeg2-wasm}"
IESIRE="${1:-$LUCRU/iesire}"
FFV=8.1.3
FF_SHA256=7138d28c96d9d3e3af4ee3d8cad72741f8ffb40da90c1112235dea3ecd3178a3
IMAGINE=emscripten/emsdk:6.0.9@sha256:96617f27fe16421588241def73908fd348a7f9d260440ed0d00b36dcf7a063cc
DEC="mpeg1video,mpeg2video,mp2float,mp3float,ac3"
PAR="mpegvideo,mpegaudio,ac3"
B=b-imagine

mkdir -p "$LUCRU" "$IESIRE"
if [ ! -f "$LUCRU/ffmpeg-$FFV.tar.xz" ]; then
	curl -fL -o "$LUCRU/ffmpeg-$FFV.tar.xz" "https://ffmpeg.org/releases/ffmpeg-$FFV.tar.xz"
fi
echo "$FF_SHA256  $LUCRU/ffmpeg-$FFV.tar.xz" | sha256sum -c -
cp "$AICI/hdsdec.c" "$LUCRU/hdsdec.c"
rm -rf "$LUCRU/ffmpeg-$FFV"
tar -C "$LUCRU" -xf "$LUCRU/ffmpeg-$FFV.tar.xz"

cat > "$LUCRU/in-container-imagine.sh" <<EOF
set -euo pipefail
cd /w
rm -rf $B && mkdir $B && cd $B
emconfigure ../ffmpeg-$FFV/configure --target-os=none --arch=emscripten --enable-cross-compile \\
  --cc=emcc --cxx=em++ --ar=emar --ranlib=emranlib --nm=emnm \\
  --disable-x86asm --disable-inline-asm --disable-asm --disable-runtime-cpudetect --disable-autodetect \\
  --disable-doc --disable-stripping --disable-programs --disable-network --disable-pthreads --disable-debug \\
  --disable-everything --disable-avformat --disable-avfilter --disable-avdevice --disable-swscale --disable-swresample \\
  --enable-decoder=$DEC --enable-parser=$PAR \\
  --optflags="-O3" --extra-cflags="-msimd128" --extra-ldflags="-msimd128" > configure.log 2>&1
grep -E "^License:" configure.log || true
emmake make -j8 > make.log 2>&1
emcc -O3 -msimd128 -I. -I../ffmpeg-$FFV ../hdsdec.c libavcodec/libavcodec.a libavutil/libavutil.a -o hdsdec.js \\
  -sMODULARIZE=1 -sEXPORT_NAME=HdsDec -sENVIRONMENT=web,worker -sFILESYSTEM=0 \\
  -sALLOW_MEMORY_GROWTH=1 -sINITIAL_MEMORY=33554432 -sSTACK_SIZE=1048576 \\
  -sEXPORTED_FUNCTIONS=_dec_open,_dec_push,_dec_reset,_dec_close,_dec_erori,_malloc,_free \\
  -sEXPORTED_RUNTIME_METHODS=ccall,HEAPU8,HEAPU32,HEAPF32 -v > link.log 2>&1
grep wasm-ld link.log | tr ' ' '\n' | grep -E '^-l' | sort -u > biblioteci.txt
ls -la hdsdec.js hdsdec.wasm
EOF
docker run --rm -u "$(id -u):$(id -g)" -v "$LUCRU:/w" "$IMAGINE" nice -n 10 bash /w/in-container-imagine.sh
cp "$LUCRU/$B/hdsdec.js" "$LUCRU/$B/hdsdec.wasm" "$IESIRE/"
cp "$LUCRU/$B/biblioteci.txt" "$IESIRE/biblioteci-emscripten.txt"
grep -E "^License:" "$LUCRU/$B/configure.log" > "$IESIRE/licenta-configure.txt" || true
echo "== iesirea: $IESIRE"
cat "$IESIRE/licenta-configure.txt"
echo "== bibliotecile emscripten legate:"
cat "$IESIRE/biblioteci-emscripten.txt"
sha256sum "$IESIRE/hdsdec.js" "$IESIRE/hdsdec.wasm"
ls -la "$IESIRE"
