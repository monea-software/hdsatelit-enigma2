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
