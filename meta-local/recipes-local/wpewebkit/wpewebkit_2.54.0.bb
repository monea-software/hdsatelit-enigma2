SUMMARY = "WPE WebKit: motorul web pentru navigatorul de pe receptor"
DESCRIPTION = "WPE WebKit 2.54 construit numai cu API-ul WPEPlatform (fara libwpe, fara Wayland, fara DRM/GBM), \
               fara video, sunet web, WebGL, WebRTC si inspector. Intra in imagine prin hds-navigator (navigatorul web)."
HOMEPAGE = "https://wpewebkit.org/"
BUGTRACKER = "https://bugs.webkit.org/"
LICENSE = "BSD-2-Clause & LGPL-2.0-or-later"
LIC_FILES_CHKSUM = "file://Source/WebCore/LICENSE-LGPL-2.1;md5=a778a33ef338abbaf8b8a7c36b6eec80"

# Reteta pornita din meta-webkit (Igalia, ramura main, wpewebkit.inc + wpewebkit_2.54.0.bb), strat MIT,
# adusa aici pentru ca meta-webkit cere seria wrynose, iar OE-ul nostru e whinlatter.
# Schimbari fata de meta-webkit:
#   - fara REQUIRED_DISTRO_FEATURES = "opengl": distributia nu are opengl; EGL/GLES vin din dinobot-opengl
#     (PREFERRED_PROVIDER virtual/egl si virtual/libgles2 al masinii u57);
#   - numai WPEPlatform (fara API-ul vechi libwpe, deci fara WPEBackend-fdo, care cere Wayland si
#     EGL_WL_bind_wayland_display); platforma pentru fbdev o aduce lansatorul (hds-navigator);
#   - scoase: GStreamer (video, webaudio, webcodecs, mediastream), WebGL/ANGLE, Vulkan, GBM/libdrm,
#     procesul GPU, WebDriver, inspectorul, PDF.js, ATK, hyphen, sysprof, libbacktrace, AVIF, JPEG XL, LCMS;
#   - 0003: procesul web accepta si ecranul EGL implicit (Mali pe fbdev nu are EGL_MESA_platform_surfaceless);
#   - 0004: WPE_DISABLE_HARDWARE_ACCELERATION=1 in mediul lansatorului alege desenul fara GL (Skia pe procesor, direct in
#     memoria partajata); API-ul WPE nu are politica de accelerare (numai GTK);
#   - 0005: doua surse care nu se compileaza cu ENABLE_VIDEO=OFF (JSHTMLMediaElementCustom.cpp fara garda VIDEO,
#     AcceleratedBackingStore.cpp foloseste DRM_FORMAT_XRGB8888 fara libdrm: se ia din antetul UAPI al nucleului);
#   - 0006: cu WPE_DISABLE_HARDWARE_ACCELERATION procesul web nu mai deschide ecranul EGL (desenul e oricum pe
#     procesor), deci merge si pe receptoare fara nicio biblioteca EGL; libEGL nu e legat direct (numai prin
#     libepoxy, care il incarca la nevoie), de aceea EGL/GLES raman doar recomandate;
#   - -O2 in locul lui -Os din distributie: pe MIPS JavaScript merge prin interpretor, iar pe ARMv7 interpretorul ramane
#     rezerva JIT-ului de baza (blocul JIT8 de la sfarsit).

DEPENDS = " \
    bison-native glib-2.0-native gperf-native libxml2-native ninja-native ruby-native unifdef-native \
    fontconfig freetype glib-2.0 harfbuzz icu jpeg sqlite3 zlib libpng libtasn1 \
    libwebp libxml2 libxslt libepoxy libgcrypt libsoup libxkbcommon woff2 \
    virtual/egl virtual/libgles2 \
"

SRC_URI = "https://wpewebkit.org/releases/${BPN}-${PV}.tar.xz;name=tarball \
           file://0001-bmalloc-libpas-avoid-C-stdatomic-in-C-build.patch \
           file://0002-WebDriver-Fix-build-when-logging-is-disabled.patch \
           file://0003-WPE-use-the-default-EGL-display-when-surfaceless-is-missing.patch \
           file://0004-WPE-allow-disabling-hardware-acceleration-from-the-environment.patch \
           file://0005-Fix-the-build-with-ENABLE_VIDEO-OFF.patch \
           file://0006-WPE-do-not-open-an-EGL-display-when-hardware-acceleration-is-disabled.patch \
           file://0007-WebCore-treat-application-vnd.hbbtv.xhtml-xml-as-XHTML.patch \
           "
SRC_URI[tarball.sha256sum] = "efa9bcc3cb891c2d88f50eec710d9ccee71cbdf1040420361eb98c17355eb452"

inherit cmake pkgconfig perlnative python3native

export WK_USE_CCACHE = "NO"

EXTRA_OECMAKE = " \
    -DPORT=WPE -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_DISABLE_PRECOMPILE_HEADERS=ON \
    -DENABLE_UNIFIED_BUILDS=ON \
    -DENABLE_WPE_PLATFORM=ON \
    -DENABLE_WPE_PLATFORM_HEADLESS=ON \
    -DENABLE_WPE_PLATFORM_DRM=OFF \
    -DENABLE_WPE_PLATFORM_WAYLAND=OFF \
    -DENABLE_WPE_LEGACY_API=OFF \
    -DENABLE_WPE_QT_API=OFF \
    -DENABLE_WPE_1_1_API=OFF \
    -DUSE_GBM=OFF \
    -DUSE_LIBDRM=OFF \
    -DENABLE_GPU_PROCESS=OFF \
    -DUSE_GSTREAMER=OFF \
    -DENABLE_VIDEO=OFF \
    -DENABLE_WEB_AUDIO=OFF \
    -DENABLE_WEB_CODECS=OFF \
    -DENABLE_MEDIA_STREAM=OFF \
    -DENABLE_MEDIA_RECORDER=OFF \
    -DENABLE_MEDIA_SESSION=OFF \
    -DENABLE_ENCRYPTED_MEDIA=OFF \
    -DENABLE_WEB_RTC=OFF \
    -DENABLE_WEBGL=OFF \
    -DENABLE_WEBXR=OFF \
    -DUSE_VULKAN=OFF \
    -DENABLE_SPEECH_SYNTHESIS=OFF \
    -DENABLE_SPELLCHECK=OFF \
    -DUSE_LIBHYPHEN=OFF \
    -DUSE_ATK=OFF \
    -DUSE_AVIF=OFF \
    -DUSE_JPEGXL=OFF \
    -DUSE_LCMS=OFF \
    -DUSE_WOFF2=ON \
    -DENABLE_XSLT=ON \
    -DENABLE_GAMEPAD=OFF \
    -DENABLE_WEBDRIVER=OFF \
    -DENABLE_REMOTE_INSPECTOR=OFF \
    -DENABLE_PDFJS=OFF \
    -DENABLE_BUBBLEWRAP_SANDBOX=OFF \
    -DENABLE_JOURNALD_LOG=OFF \
    -DUSE_SYSPROF_CAPTURE=OFF \
    -DUSE_LIBBACKTRACE=OFF \
    -DENABLE_INTROSPECTION=OFF \
    -DENABLE_DOCUMENTATION=OFF \
    -DENABLE_MINIBROWSER=OFF \
    -DENABLE_API_TESTS=OFF \
    -DENABLE_JIT=OFF \
    -DENABLE_DFG_JIT=OFF \
    -DENABLE_FTL_JIT=OFF \
"

# Thumb2 pe ARMv7: cod mai mic; JIT-ul de baza (blocul JIT8) are backend numai pentru Thumb2.
ARM_INSTRUCTION_SET:armv7a = "thumb"
ARM_INSTRUCTION_SET:armv7ve = "thumb"

# Fara informatii de depanare (legarea libWPEWebKit cu -g cere zeci de GB) si -O2 pentru viteza interpretorului.
FULL_OPTIMIZATION = "-O2 -pipe"

# Directorul de build ramane intre reconfigurari: o schimbare mica de patch nu mai recompileaza tot WebKit.
do_configure[cleandirs] = ""

# ninja merge mai departe dupa o eroare (-k 0): o singura rulare arata toate unitatile care nu se compileaza.
EXTRA_OECMAKE_BUILD = "-k 0"

LEAD_SONAME = "libWPEWebKit-2.0.so"

# mimalloc e legat direct in bmalloc; copia instalata de sursa inclusa (anteturi, .pc, cmake) nu se foloseste.
# inspector.gresource (inspectorul web) se instaleaza si cu inspectorul oprit; pe receptor nu e nevoie de el.
do_install:append() {
    rm -rf ${D}${libdir}/mimalloc-* ${D}${includedir}/mimalloc-* ${D}${libdir}/cmake/mimalloc-*
    rm -f ${D}${libdir}/pkgconfig/mimalloc.pc
    rmdir --ignore-fail-on-non-empty ${D}${libdir}/cmake
    rm -f ${D}${datadir}/wpe-webkit-2.0/inspector.gresource
    rmdir --ignore-fail-on-non-empty ${D}${datadir}/wpe-webkit-2.0 ${D}${datadir}
}

FILES:${PN} += "${libdir}/wpe-webkit*/injected-bundle/libWPEInjectedBundle.so"

# glib-networking da TLS pentru libsoup (https); fara el paginile https nu se deschid.
RDEPENDS:${PN} += "glib-networking"
RRECOMMENDS:${PN} += "ca-certificates virtual-egl virtual-libgles2"

# Vu+ 4K (lotul vuplus4k): eglplatform.h din vuplus-libgles-<masina> cere BROADCOM_PLATFORM (altfel include X11/Xlib.h),
# ca la libepoxy_1.5.10.bbappend; desenul ramane pe procesor (peticul 0006), deci EGL nu se foloseste la rulare.
CFLAGS:append:vusolo4k = " -DBROADCOM_PLATFORM"
CFLAGS:append:vuuno4k = " -DBROADCOM_PLATFORM"
CFLAGS:append:vuultimo4k = " -DBROADCOM_PLATFORM"
CXXFLAGS:append:vusolo4k = " -DBROADCOM_PLATFORM"
CXXFLAGS:append:vuuno4k = " -DBROADCOM_PLATFORM"
CXXFLAGS:append:vuultimo4k = " -DBROADCOM_PLATFORM"
CFLAGS:append:vuuno4kse = " -DBROADCOM_PLATFORM"
CFLAGS:append:vuzero4k = " -DBROADCOM_PLATFORM"
CXXFLAGS:append:vuuno4kse = " -DBROADCOM_PLATFORM"
CXXFLAGS:append:vuzero4k = " -DBROADCOM_PLATFORM"
CFLAGS:append:vuduo4klite = " -DBROADCOM_PLATFORM"
CXXFLAGS:append:vuduo4klite = " -DBROADCOM_PLATFORM"
CFLAGS:append:gbquad4kpro = " -DBROADCOM_PLATFORM"
CXXFLAGS:append:gbquad4kpro = " -DBROADCOM_PLATFORM"
CFLAGS:append:gbx34k = " -DBROADCOM_PLATFORM"
CXXFLAGS:append:gbx34k = " -DBROADCOM_PLATFORM"
CFLAGS:append:ax51 = " -DBROADCOM_PLATFORM"
CXXFLAGS:append:ax51 = " -DBROADCOM_PLATFORM"
CFLAGS:append:osmio4kplus = " -DBROADCOM_PLATFORM"
CXXFLAGS:append:osmio4kplus = " -DBROADCOM_PLATFORM"
CFLAGS:append:osmini4k = " -DBROADCOM_PLATFORM"
CXXFLAGS:append:osmini4k = " -DBROADCOM_PLATFORM"
CFLAGS:append:osmio4k = " -DBROADCOM_PLATFORM"
CXXFLAGS:append:osmio4k = " -DBROADCOM_PLATFORM"
CFLAGS:append:zgemmah17combo = " -DBROADCOM_PLATFORM"
CXXFLAGS:append:zgemmah17combo = " -DBROADCOM_PLATFORM"
# Dreambox DM900 si DM920 (MDM dm900 egl): ca la libepoxy_1.5.10.bbappend (EGL din libvc5dream)
CFLAGS:append:dm900 = " -DBROADCOM_PLATFORM"
CFLAGS:append:dm920 = " -DBROADCOM_PLATFORM"
CXXFLAGS:append:dm900 = " -DBROADCOM_PLATFORM"
CXXFLAGS:append:dm920 = " -DBROADCOM_PLATFORM"
CFLAGS:append:vuduo4k = " -DBROADCOM_PLATFORM"
CFLAGS:append:vuduo4kse = " -DBROADCOM_PLATFORM"
CXXFLAGS:append:vuduo4k = " -DBROADCOM_PLATFORM"
CXXFLAGS:append:vuduo4kse = " -DBROADCOM_PLATFORM"

# NVM (0.7.7, 15.11.2026; Eduard 23:10: navigatorul si pe Vu+ Solo SE si pe celelalte receptoare MIPS): MIPS pe 32 de biti
# (tune mips32el pe vusolose, vusolo2, vuduo2, vuzero si sh1, deci un singur pachet mips32el pentru toate). WebKit 2.54 are
# inca ramura MIPS (WebKitFeatures.cmake: JIT oprit, C_LOOP, fara WebAssembly, mimalloc; -mno-lxc1-sxc1), dar libpas
# alege pe GCC pas_pair de 128 de biti pe orice tinta afara de ARM32: 0020 da tuturor tintelor pe 32 de biti caile ARM32
# (libpas nu aloca pe 32 de biti). 0021: WTF SequenceLocked (SharedTimebase.cpp) cere atomice de 64 de biti fara lacat, pe
# care MIPS32 nu le are: acolo cuvinte de 32 de biti. Numai pe MIPS, ca pachetele ARM sa ramana neschimbate. Desenul e pe
# procesor ca pe ARM (0004/0006), deci EGL-ul Broadcom al masinii (vuplus-libgles-<masina>) nu se foloseste la rulare;
# antetul lui eglplatform.h pe Solo SE are tipurile void * si nu cere BROADCOM_PLATFORM.
SRC_URI:append:mipsarch = " file://0020-libpas-use-the-ARM32-pair-paths-on-every-32-bit-target.patch \
                            file://0021-WTF-SequenceLocked-use-32-bit-words-without-lock-free-64-bit-atomics.patch"

# YTV (0.7.7, 16.11.2026; Eduard 15.11 23:05 si 23:07: YouTube din meniul Aplicatii, filme si live cu sunet): pe ARM WebKit-ul
# are video HTML5 si Media Source Extensions prin GStreamer, decodate de placa receptorului (acelasi decodor ca la canal, dat
# cu imprumut de enigma2: Components/HdsDecodorWeb.py). Blocul vine din stratul de proba meta-video (lotul hbbtv-video A si B,
# pachetul r0.video3 probat pe Viper 4K V20: <video> si MSE pe placa, YouTube pentru televizor cu sunet). Totul e numai :arm,
# deci pachetele ARM nu schimba nimic pe MIPS; pe mips32el acelasi video il pune blocul YTS9 de la sfarsit.
#   - GStreamer, video si MSE pornite; GL, MPEG-TS si WebRTC prin GStreamer oprite (Mali-450 nu compune cu GL, MPEG-TS nu
#     cere nimic); EME (DRM) si sunetul web raman oprite;
#   - 0008: GStreamerChecks.cmake cere componentele gl si mpegts numai cand optiunile lor sunt pornite (gst-plugins-base din
#     imagine e construit fara GL, deci fara gstreamer-gl-1.0);
#   - 0009: quirk-ul "hdsdvb" (WEBKIT_GST_QUIRKS si WEBKIT_GST_HOLE_PUNCH_QUIRK): filmul ajunge comprimat la dvbvideosink/
#     dvbaudiosink (aceleasi sink-uri ca playerul receptorului), parserele tin locul decodoarelor in registrul codecurilor,
#     decodoarele video pe procesor (VP8/VP9/AV1/Theora) si HEVC/VP9/AV1 (nemasurate pe placa) sunt scoase, pozitia vine din
#     decodor (get-decoder-time), cautarea merge pe cadre cheie si se incheie fara ASYNC_DONE; decodorul il imprumuta enigma2
#     pe socketul din HDS_DECODOR (cere/ok, fereastra, gata) si fereastra video o muta tot enigma2;
#   - 0010: navigatorul deseneaza fara compunere de straturi (pe procesor): la desenul elementului <video> zona se goleste
#     (alfa 0, se vede planul video de sub grafica) si dreptunghiul pleaca spre enigma2;
#   - 0011: MSE (playbin3): uridecodebin3/decodebin3 se opresc la caps-urile sink-urilor placii;
#   - 0012: sink-urile placii primesc e2-async (preroll), fara de care playsink din playbin3 (MSE) ramane in READY;
#   - DEPENDS cu gstreamer1.0 si gstreamer1.0-plugins-base; RDEPENDS cu pluginurile folosite la rulare, toate deja in imaginile
#     ARM 0.7.6 (verificat pe cele 18 manifeste); dvbmediasink e pachetul masinii, tot in imagine. Biblioteca creste cu ~2,4 MB.
# PR r0.video3: acelasi nume ca pachetul probat; e mai mare decat 2.54.0-r0 al lui 0.7.6, deci actualizarea il ia.
PR:arm = "r0.video3"
DESCRIPTION:arm = "WPE WebKit 2.54 construit numai cu API-ul WPEPlatform (fara libwpe, fara Wayland, fara DRM/GBM), \
                   cu video HTML5 si MSE prin GStreamer, decodate de placa receptorului (fara GL, fara MPEG-TS, fara EME), \
                   fara sunet web, WebGL, WebRTC si inspector."
DEPENDS:append:arm = " gstreamer1.0 gstreamer1.0-plugins-base"
SRC_URI:append:arm = " file://0008-GStreamer-require-gl-and-mpegts-only-when-their-options-are-on.patch \
                       file://0009-GStreamer-add-the-hdsdvb-quirk-for-the-board-decoder-of-satellite-receivers.patch \
                       file://0010-GStreamer-punch-the-video-hole-when-painting-without-compositing.patch \
                       file://0011-GStreamer-hdsdvb-stops-decodebin3-at-the-caps-of-the-board-sinks.patch \
                       file://0012-GStreamer-hdsdvb-board-sinks-preroll-e2-async-for-playbin3-and-MSE.patch"
EXTRA_OECMAKE:remove:arm = "-DUSE_GSTREAMER=OFF -DENABLE_VIDEO=OFF"
EXTRA_OECMAKE:append:arm = " \
    -DUSE_GSTREAMER=ON \
    -DENABLE_VIDEO=ON \
    -DENABLE_MEDIA_SOURCE=ON \
    -DUSE_GSTREAMER_GL=OFF \
    -DUSE_GSTREAMER_MPEGTS=OFF \
    -DUSE_GSTREAMER_WEBRTC=OFF \
"
RDEPENDS:${PN}:append:arm = " \
    gstreamer1.0-plugins-base-app \
    gstreamer1.0-plugins-base-playback \
    gstreamer1.0-plugins-base-typefindfunctions \
    gstreamer1.0-plugins-base-audioconvert \
    gstreamer1.0-plugins-base-audioresample \
    gstreamer1.0-plugins-base-volume \
    gstreamer1.0-plugins-good-isomp4 \
    gstreamer1.0-plugins-good-matroska \
    gstreamer1.0-plugins-good-audioparsers \
    gstreamer1.0-plugins-good-id3demux \
    gstreamer1.0-plugins-bad-videoparsersbad \
"

# JIT8 (dupa 0.7.8): pe ARMv7 (Thumb2, hard-float) JavaScript-ul navigatorului merge cu JIT-ul de baza (Baseline),
# pornit din fabrica; DFG si FTL raman oprite (DFG cade pe ARM pe 32 de biti, FTL nu exista acolo). In 2.54 comutatorul CMake nu
# ajunge: PlatformEnable.h scoate JIT si DFG pentru JSVALUE32_64. Peticele 0022-0030 lasa backend-urile ARMv7 din arhiva sa se
# compileze; 0031 repara put_by_val: pe ARMv7 registrul profilului era acelasi cu al handlerului (r9), iar procesul web cadea la
# prima trecere pe calea lenta. HDS_REQUIRE_JIT opreste constructia daca biblioteca ar iesi tot fara JIT. Lansatorul
# (hds-navigator) tine DFG oprit, limiteaza memoria codului la 8 MiB si trece singur pe interpretor dupa doua porniri la rand cu
# procesul web cazut. Totul e numai :arm, deci JIT8 nu atinge pachetul mips32el (Vu+ Solo SE, Duo2; video pe MIPS: blocul YTS9)
# (WebKit 2.54 nu mai are JIT pentru MIPS32). PR r0.video3.jit3 inlocuieste r0.video3 de mai sus: e mai mare pentru opkg
# (feed_actualizare.compara), deci receptoarele ARM il primesc ca actualizare din feed, fara imagine noua.
# JITD (25.11.2026): si treapta rapida (DFG) e compilata pe ARMv7. Cadea la primul cache de proprietati din codul DFG, fiindca
# WebKit 309239@main ("[ARMv7] Disable JIT") scosese din DFGJITCompiler.cpp ramurile de 32 de biti (cache-ul ajungea NUL in calea
# lenta); peticul 0033 le pune la loc. Peticul 0034 tine in afara DFG-ului de 32 de biti iteratia rapida pe Map / Set (for-of),
# adaugata in WebKit dupa oprirea JIT-ului ARMv7: nodul ei MapStorage nu are backend pe 32 de biti si oprea procesul. Peticul 0035: baza lui
# CheckPrivateBrand (apelul unei metode private) e speculata ca celula si pe 32 de biti; altfel DFG se oprea la verificarea muchiei.
# Amandoua gasite cu probele JavaScriptCore ale WebKit (JSTests/stress) rulate pe jsc ARM in qemu. La rulare DFG ramane oprit din fabrica pe 32 de biti (useDFGJIT = 64 de biti): il porneste
# lansatorul (hds-navigator de la r26, JSC_useDFGJIT=1), care coboara singur la treapta de baza si apoi la interpretor dupa doua
# porniri la rand cu procesul web cazut. Lansatoarele dinainte pun JSC_useDFGJIT=0 sau nu il pun deloc, deci cu ele biblioteca
# merge ca jit3. HDS_REQUIRE_DFG_JIT opreste constructia daca biblioteca ar iesi fara DFG. PR r0.video3.jit4.
HDS_JIT_PATCHES:arm = " \
    file://0022-JSC-allow-existing-ARMv7-JIT-backends-when-requested.patch \
    file://0023-JSC-include-declarations-used-by-32-bit-JIT-headers.patch \
    file://0024-JSC-guard-the-64-bit-only-BigInt-allocation-helper.patch \
    file://0025-JSC-repair-ARM32-cache-header-and-slow-path-selection.patch \
    file://0026-JSC-omit-DFG-cache-alternative-in-baseline-only-builds.patch \
    file://0027-JSC-include-compilation-result-in-baseline-only-builds.patch \
    file://0028-JSC-guard-64-bit-megamorphic-getter-cache-handlers.patch \
    file://0029-JSC-include-baseline-registers-in-32-bit-DFG.patch \
    file://0030-JSC-preserve-ARM32-DFG-string-and-generic-sort-paths.patch \
    file://0031-JSC-ARMv7-keep-the-put_by_val-profile-out-of-the-handler-register.patch \
    file://0033-JSC-restore-the-repatching-inline-caches-of-the-32-bit-DFG.patch \
    file://0034-JSC-keep-the-Map-and-Set-fast-iteration-out-of-the-32-bit-DFG.patch \
    file://0035-JSC-speculate-the-cell-base-of-CheckPrivateBrand-in-the-32-bit-DFG.patch \
"
SRC_URI:append:arm = " ${HDS_JIT_PATCHES}"
EXTRA_OECMAKE:remove:arm = "-DENABLE_JIT=OFF -DENABLE_DFG_JIT=OFF"
EXTRA_OECMAKE:append:arm = " -DENABLE_JIT=ON -DENABLE_DFG_JIT=ON"
CXXFLAGS:append:arm = " -DHDS_REQUIRE_JIT=1 -DHDS_REQUIRE_DFG_JIT=1"
PR:arm = "r0.video3.jit4"
do_configure:prepend:arm() {
    # backend-ul JIT pe 32 de biti e probat numai pe ARMv7 Thumb2 hard-float (TUNE_FEATURES al unui nucleu Cortex-A numeste
    # nucleul, nu arhitectura: pe sf8008 "arm vfp cortexa15 neon vfpv4 callconvention-hard")
    case " ${TUNE_FEATURES} " in
        *" armv7a "*|*" armv7ve "*|*" cortexa5 "*|*" cortexa7 "*|*" cortexa8 "*|*" cortexa9 "*|*" cortexa12 "*|*" cortexa15 "*|*" cortexa17 "*) ;;
        *) bbfatal "wpewebkit: JIT-ul de baza cere ARMv7 (TUNE_FEATURES: ${TUNE_FEATURES})" ;;
    esac
    case " ${TUNE_FEATURES} " in
        *" callconvention-hard "*) ;;
        *) bbfatal "wpewebkit: JIT-ul de baza cere hard-float (TUNE_FEATURES: ${TUNE_FEATURES})" ;;
    esac
    [ "${ARM_INSTRUCTION_SET}" = "thumb" ] || bbfatal "wpewebkit: JIT-ul de baza cere Thumb2 (ARM_INSTRUCTION_SET: ${ARM_INSTRUCTION_SET})"
}
# JITD: o biblioteca noua merita o incercare noua. La instalarea sau actualizarea pachetului se sterge numaratoarea rezervei JIT a
# lansatorului; altfel treapta rapida (sau tot JIT-ul) ar ramane oprita pentru totdeauna pe un receptor unde procesul web a cazut de
# doua ori cu biblioteca dinainte.
pkg_postinst:${PN}:append:arm () {
    rm -f $D/etc/enigma2/hds-navigator-jit-cazut
}

# YTS9 (YouTube din Aplicatii pe Vu+ Solo SE: pagina se deschidea, filmul nu pornea): acelasi video ca pe ARM (blocul YTV de
# mai sus) si pe MIPS (tune mips32el: Vu+ Solo SE, Solo2, Duo2, Zero). Partea din imagine (imprumutul decodorului,
# Components/HdsDecodorWeb.py, --autoplay) nu are nicio ramura de arhitectura; peticele 0008-0012 nu tin de placa;
# dvbmediasink si pluginurile GStreamer de mai jos sunt deja in imaginea vusolose. Pe Solo SE placa (BCM7429) decodeaza H.264 si
# AAC; VP9/AV1/HEVC le scoate quirk-ul, deci YouTube da H.264 + AAC. Totul numai :mipsarch, ca pachetele ARM sa ramana aceleasi
# (semnaturile sarcinilor ARM neschimbate).
PR:mipsarch = "r0.video3"
DESCRIPTION:mipsarch = "WPE WebKit 2.54 construit numai cu API-ul WPEPlatform (fara libwpe, fara Wayland, fara DRM/GBM), \
                        cu video HTML5 si MSE prin GStreamer, decodate de placa receptorului (fara GL, fara MPEG-TS, fara EME), \
                        fara sunet web, WebGL, WebRTC si inspector; JavaScript prin interpretor (C_LOOP)."
DEPENDS:append:mipsarch = " gstreamer1.0 gstreamer1.0-plugins-base"
SRC_URI:append:mipsarch = " file://0008-GStreamer-require-gl-and-mpegts-only-when-their-options-are-on.patch \
                            file://0009-GStreamer-add-the-hdsdvb-quirk-for-the-board-decoder-of-satellite-receivers.patch \
                            file://0010-GStreamer-punch-the-video-hole-when-painting-without-compositing.patch \
                            file://0011-GStreamer-hdsdvb-stops-decodebin3-at-the-caps-of-the-board-sinks.patch \
                            file://0012-GStreamer-hdsdvb-board-sinks-preroll-e2-async-for-playbin3-and-MSE.patch"
EXTRA_OECMAKE:remove:mipsarch = "-DUSE_GSTREAMER=OFF -DENABLE_VIDEO=OFF"
EXTRA_OECMAKE:append:mipsarch = " \
    -DUSE_GSTREAMER=ON \
    -DENABLE_VIDEO=ON \
    -DENABLE_MEDIA_SOURCE=ON \
    -DUSE_GSTREAMER_GL=OFF \
    -DUSE_GSTREAMER_MPEGTS=OFF \
    -DUSE_GSTREAMER_WEBRTC=OFF \
"
RDEPENDS:${PN}:append:mipsarch = " \
    gstreamer1.0-plugins-base-app \
    gstreamer1.0-plugins-base-playback \
    gstreamer1.0-plugins-base-typefindfunctions \
    gstreamer1.0-plugins-base-audioconvert \
    gstreamer1.0-plugins-base-audioresample \
    gstreamer1.0-plugins-base-volume \
    gstreamer1.0-plugins-good-isomp4 \
    gstreamer1.0-plugins-good-matroska \
    gstreamer1.0-plugins-good-audioparsers \
    gstreamer1.0-plugins-good-id3demux \
    gstreamer1.0-plugins-bad-videoparsersbad \
"

# MJT8 (Eduard 25.11.2026 10:39; adus peste blocul YTS9 de MJT1): JIT-ul de baza si pe MIPS32 (tune mips32el: Vu+ Solo SE, Duo2;
# -march=mips32, release 1, hard-float, o32). WebKit a scos backend-ul MIPS in ianuarie 2024 (272866@main); 0032 il readuce in
# 2.54: asamblorul si MacroAssembler-ul MIPS (numai instructiuni din release 1: fara seb/seh/ext/ins/rotr), offlineasm mips.rb
# (LLInt in asamblare in locul lui C_LOOP), registrele JIT si YARR, apelurile o32 (zona de 16 octeti a argumentelor), salvarile
# s0/s1. Peste el raman reparatiile generale pe 32 de biti 0022-0030 si 0031 (registrul profilului e schimbat numai pe ARMv7,
# dar scoaterea registrului handlerului dintre registrele de lucru la put_by_val si verificarea ei se compileaza si pe MIPS;
# 0032 e facut peste toata seria). DFG si FTL raman oprite, ca pe ARM.
# HDS_REQUIRE_JIT opreste constructia daca biblioteca ar iesi tot fara JIT. Lansatorul (hds-navigator) trece singur pe
# interpretor dupa doua porniri la rand cu procesul web cazut, ca pe ARM; pe MIPS interpretorul de rezerva (JSC_useJIT=0) e
# LLInt-ul in asamblare, nu C_LOOP, iar intoarcerea completa e pachetul r0.video3. Totul numai :mipsarch: semnaturile ARM raman
# aceleasi. PR r0.video3.mjit1 inlocuieste r0.video3 din blocul YTS9: e mai mare pentru opkg, deci receptoarele MIPS il primesc
# ca actualizare din feed.
SRC_URI:append:mipsarch = " \
    file://0022-JSC-allow-existing-ARMv7-JIT-backends-when-requested.patch \
    file://0023-JSC-include-declarations-used-by-32-bit-JIT-headers.patch \
    file://0024-JSC-guard-the-64-bit-only-BigInt-allocation-helper.patch \
    file://0025-JSC-repair-ARM32-cache-header-and-slow-path-selection.patch \
    file://0026-JSC-omit-DFG-cache-alternative-in-baseline-only-builds.patch \
    file://0027-JSC-include-compilation-result-in-baseline-only-builds.patch \
    file://0028-JSC-guard-64-bit-megamorphic-getter-cache-handlers.patch \
    file://0029-JSC-include-baseline-registers-in-32-bit-DFG.patch \
    file://0030-JSC-preserve-ARM32-DFG-string-and-generic-sort-paths.patch \
    file://0031-JSC-ARMv7-keep-the-put_by_val-profile-out-of-the-handler-register.patch \
    file://0032-JSC-restore-the-MIPS32-assembler-LLInt-and-baseline-JIT.patch \
"
EXTRA_OECMAKE:remove:mipsarch = "-DENABLE_JIT=OFF"
EXTRA_OECMAKE:append:mipsarch = " -DENABLE_JIT=ON -DENABLE_C_LOOP=OFF -DENABLE_WEBASSEMBLY=OFF"
CXXFLAGS:append:mipsarch = " -DHDS_REQUIRE_JIT=1"
DESCRIPTION:mipsarch = "WPE WebKit 2.54 construit numai cu API-ul WPEPlatform (fara libwpe, fara Wayland, fara DRM/GBM), \
                        cu video HTML5 si MSE prin GStreamer, decodate de placa receptorului (fara GL, fara MPEG-TS, fara EME), \
                        fara sunet web, WebGL, WebRTC si inspector; JavaScript prin LLInt in asamblare MIPS si JIT-ul de baza (fara DFG)."
PR:mipsarch = "r0.video3.mjit1"

# WVN1 (0.8.0, 25.11.2026; Eduard 10:31: Netflix, Disney+, HBO Max, SkyShowtime in navigatorul nostru, cu imaginea filmului
# decodata de placa, fara Kodi): Encrypted Media Extensions prin singurul backend CDM al WPE 2.54 pe GStreamer, Thunder /
# OpenCDM, cu biblioteca noastra libocdm (reteta hds-ocdm): Clear Key si Widevine (modulul adus de receptorul omului de la
# Google, folosit prin interfata publica CDM, numai decriptarea). Decriptorul GStreamer al WebKit-ului (webkitthunder) lasa
# cadrele comprimate, deci drumul spre dvbvideosink / dvbaudiosink ramane cel de la YouTube (quirk-ul hdsdvb, 0009-0012).
# Numai :arm (schimba semnatura wpewebkit pe toate masinile ARM). Blocul e ultimul: PR:arm de aici castiga peste cel din JIT8 / JITD.
# 0036: saltul (currentTime / pornirea de la o secunda data): pozitia ramane la tinta saltului pana cand decodorul placii arata
# o imagine noua (vazut pe Octagon 25.11: Shaka a sarit iar inapoi la pozitia veche citita din decodor si filmul s-a oprit).
SRC_URI:append:arm = " file://0036-GStreamer-hdsdvb-keep-the-position-at-the-seek-target-until-the-board-shows-a-new-picture.patch"
DEPENDS:append:arm = " hds-ocdm"
RDEPENDS:${PN}:append:arm = " hds-ocdm"
EXTRA_OECMAKE:remove:arm = "-DENABLE_ENCRYPTED_MEDIA=OFF"
EXTRA_OECMAKE:append:arm = " -DENABLE_ENCRYPTED_MEDIA=ON -DENABLE_THUNDER=ON"
PR:arm = "r0.video3.jit4.wvn1"
