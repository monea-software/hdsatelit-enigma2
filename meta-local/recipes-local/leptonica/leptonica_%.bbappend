# HDSatelit (25.09.2026, lotul ocr-dvb/motor): leptonica e ceruta de tesseract, dar hds-ocr ii da imaginea
# direct din memorie (SetImage cu octeti gri); nu citeste si nu scrie fisiere de imagine. Fara bibliotecile
# de formate: mai putine pachete pe receptor (libtiff, libwebp nu sunt in imagine).
DEPENDS:remove = "jpeg tiff libpng zlib"
PACKAGECONFIG = ""
EXTRA_OECONF += "--without-zlib --without-libpng --without-jpeg --without-giflib --without-libtiff --without-libwebp --without-libwebpmux --without-libopenjpeg"
