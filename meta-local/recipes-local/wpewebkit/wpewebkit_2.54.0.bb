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
#   - -O2 in locul lui -Os din distributie: fara JIT pe ARMv7, JavaScript merge prin interpretor.

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

# JavaScript fara JIT pe ARMv7 (ca in meta-webkit); Thumb2 da cod mai mic.
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
CFLAGS:append:vuultimo4k = " -DBROADCOM_PLATFORM"
CXXFLAGS:append:vusolo4k = " -DBROADCOM_PLATFORM"
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
# deci pachetul mips32el (Vu+ Solo SE si celelalte MIPS, blocul NVM de sus) ramane neschimbat, fara video.
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
