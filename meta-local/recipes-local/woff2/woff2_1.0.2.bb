SUMMARY = "WOFF2: decompresia fonturilor web WOFF 2.0"
DESCRIPTION = "Biblioteca de referinta pentru fonturile WOFF 2.0; o cere WPE WebKit (USE_WOFF2), fiindca freetype-ul \
               imaginii e construit fara brotli si nu stie singur WOFF2."
HOMEPAGE = "https://github.com/google/woff2"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://LICENSE;md5=027c71da9e4664fdf192e6ec615f4d18"

SRC_URI = "git://github.com/google/woff2.git;branch=master;protocol=https"
# eticheta v1.0.2
SRCREV = "1bccf208bca986e53a647dfe4811322adb06ecf8"

DEPENDS = "brotli"

inherit cmake

# CMakeLists.txt cere cmake_minimum_required 2.8.6; CMake 4 refuza politicile mai vechi de 3.5 fara acest prag.
EXTRA_OECMAKE += "-DCMAKE_POLICY_VERSION_MINIMUM=3.5 -DCMAKE_SKIP_RPATH=ON -DNOISY_LOGGING=OFF"

# include/woff2/output.h foloseste uint8_t fara <cstdint>; GCC 13 si mai noi nu il mai aduc indirect.
CXXFLAGS:append = " -include cstdint"

BBCLASSEXTEND = "native"
