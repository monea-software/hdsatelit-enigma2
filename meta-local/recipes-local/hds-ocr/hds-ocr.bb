SUMMARY = "HDSatelit: serviciul local de OCR pentru subtitrarile DVB (hds-ocr)"
DESCRIPTION = "Proces separat de enigma2 care primeste pe socketul unix /tmp/hds-ocr.sock regiunile \
subtitrarilor DVB (8 biti cu paleta), scoate din paleta masca textului, imparte in randuri si le \
recunoaste cu tesseract (LSTM, modele tessdata_fast), apoi intoarce textul UTF-8, dreptunghiul, linia \
de baza, culorile umpluturii/conturului/casetei si increderea pe cuvant. Protocolul: hds_ocr_protocol.h \
(in pachetul -dev) si PROTOCOL.md din lucru-sesiune/ocr-dvb/motor. Timpul de lucru al unei pagini se \
socoteste de cand incepe recunoasterea, dupa numarul si latimea randurilor si viteza masurata pe \
receptor; paginile si randurile deja citite primesc raspunsul pe loc, fara coada, iar un rand nou facut \
numai din litere deja citite sigur se compune din memoria glifelor, fara tesseract. Pornire la cerere: \
enigma2 porneste hds-ocr cand are nevoie (socket lipsa), serviciul iese singur dupa --idle-exit \
secunde fara cereri (enigma2 da 300); fara script de init. Licenta MIT (fisierele proprii); se leaga de libtesseract (Apache-2.0), \
motiv pentru care ramane proces separat: enigma2 (GPL-2.0-only) vorbeste cu el numai prin socket. \
Monea Software pentru HD Satelit."
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://hds-ocr.cpp;beginline=3;endline=12;md5=c1e835ad7dea9a839f6476599934a2ef \
                    file://hds_ocr_protocol.h;beginline=3;endline=12;md5=c1e835ad7dea9a839f6476599934a2ef"
PV = "0.2.0"

SRC_URI = "file://hds-ocr.cpp file://hds_ocr_protocol.h"
S = "${UNPACKDIR}"

# tesseract vine cu bbappend-ul din acest strat (fara motorul vechi, fara OpenMP, fara curl/libarchive);
# leptonica e ceruta direct: hds-ocr.cpp cheama setMsgSeverity din ea
DEPENDS = "tesseract leptonica"

inherit pkgconfig

do_configure[noexec] = "1"

do_compile() {
    if grep -q "$(printf '\r')" ${S}/hds-ocr.cpp ${S}/hds_ocr_protocol.h; then
        bbfatal "hds-ocr: sursa are sfarsit de rand CRLF"
    fi
    ${CXX} ${CXXFLAGS} ${LDFLAGS} -std=c++17 -Wall -Wextra -Wno-unused-parameter -pthread \
        -o ${B}/hds-ocr ${S}/hds-ocr.cpp $(pkg-config --cflags --libs tesseract lept)
}

do_install() {
    install -d ${D}${bindir} ${D}${includedir}/hds-ocr
    install -m 0755 ${B}/hds-ocr ${D}${bindir}/hds-ocr
    install -m 0644 ${S}/hds_ocr_protocol.h ${D}${includedir}/hds-ocr/hds_ocr_protocol.h
}

FILES:${PN} = "${bindir}/hds-ocr"
FILES:${PN}-dev = "${includedir}/hds-ocr"

# modelele: romana (implicitul pentru piste fara limba) si lista modelelor descarcabile; celelalte limbi din imagine
# vin cu hds-ocr-modele (packagegroups/hdsatelit-base.bb), restul se descarca pe receptor la cerere
RRECOMMENDS:${PN} = "hds-ocr-modele-ron hds-ocr-modele-lista"
