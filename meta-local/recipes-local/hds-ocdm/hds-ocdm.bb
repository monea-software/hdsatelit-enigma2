SUMMARY = "HDSatelit: biblioteca OpenCDM a navigatorului (filmele protejate in WPE WebKit, decodate de placa)"
DESCRIPTION = "libocdm.so cu interfata OpenCDM ceruta de WPE WebKit (ENABLE_THUNDER) pentru EME: Clear Key (AES pe \
procesor) si Widevine prin modulul pe care receptorul omului il aduce de la Google, folosit prin interfata publica CDM \
(numai decriptarea; cadrele raman comprimate pentru decodorul placii). Modulul nu e in pachet. Monea Software pentru HD Satelit."
LICENSE = "GPL-2.0-only"
LIC_FILES_CHKSUM = "file://hds-ocdm.cpp;beginline=2;endline=3;md5=fb87bc14f85a0e8e73d2e038b3c2f7e1"
PV = "0.1"
# r0 (WVN1, 25.11.2026, Eduard 10:31: Netflix si celelalte in navigatorul nostru, prin decodarea placii, fara Kodi)
# r1 (WVN1, 25.11.2026 23:45): RDEPENDS nspr. Modulul Widevine adus de la Google are libnspr4.so printre bibliotecile cerute (singura care
# lipsea din imagine; vazut pe Viper 4K V20: "dlopen: libnspr4.so: cannot open shared object file", cererea de licenta refuzata).
PR = "r1"

# content_decryption_module.h: interfata publica CDM (BSD, depozitul chromium/cdm), numai la compilare; nu intra in pachet.
SRC_URI = "file://open_cdm.h file://open_cdm_adapter.h file://hds-ocdm.cpp file://hds-ocdm-gst.cpp \
           git://chromium.googlesource.com/chromium/cdm;protocol=https;branch=main;name=cdm;destsuffix=cdm"
# revizia din 05.2022, neschimbata pana in 08.2024: antetul cu care e facut modulul armhf 4.10.2662.3 (2023)
SRCREV_cdm = "fef0b5aa1bd31efb88dfab804bdbe614f3d54f28"
S = "${UNPACKDIR}"

DEPENDS = "gstreamer1.0 libgcrypt"
RDEPENDS:${PN} += "nspr"

inherit pkgconfig

do_configure[noexec] = "1"

do_compile() {
    if grep -q "$(printf '\r')" ${S}/open_cdm.h ${S}/open_cdm_adapter.h ${S}/hds-ocdm.cpp ${S}/hds-ocdm-gst.cpp; then
        bbfatal "hds-ocdm: sursa are sfarsit de rand CRLF"
    fi
    ${CXX} ${CXXFLAGS} ${LDFLAGS} -std=gnu++17 -fPIC -shared -fvisibility=hidden -Wall -Wextra -Wl,--no-undefined \
        -Wl,-soname,libocdm.so.1 -I${S} -I${S}/cdm \
        -o ${B}/libocdm.so.1 ${S}/hds-ocdm.cpp ${S}/hds-ocdm-gst.cpp \
        $(pkg-config --cflags --libs gstreamer-1.0) $(pkg-config --cflags --libs libgcrypt) -ldl -lpthread
}

do_install() {
    install -d ${D}${libdir} ${D}${includedir}/opencdm
    install -m 0755 ${B}/libocdm.so.1 ${D}${libdir}/libocdm.so.1
    ln -sf libocdm.so.1 ${D}${libdir}/libocdm.so
    install -m 0644 ${S}/open_cdm.h ${S}/open_cdm_adapter.h ${D}${includedir}/opencdm/
}
