SUMMARY = "Fonturile Tiresias Infofont si Tiresias PCfont"
DESCRIPTION = "Fonturile Tiresias Infofont si PCfont (obisnuit si gros), facute pentru citirea usoara de catre oamenii \
care vad slab, pentru subtitrarile text (ecranul Aspectul subtitrarilor). Fisierele sunt cele din arhivele oficiale \
(tiresias.org/fonts: infofont.zip, pcfont.zip; aceleasi, octet cu octet, in fonts-tiresias_0.1.orig.tar.gz al Debian), \
nemodificate, doar redenumite fara spatii. Tiresias Screenfont NU e aici: nu e liber. Fonturile au numai Latin-1 \
(fara literele romanesti cu caciula si virgula, afara de a, i cu caciula): enigma2 scrie cu fontul imaginii textul pe care ele nu-l pot scrie intreg."
# GPL-3.0-or-later cu exceptia de font (textul in LICENTA-TIRESIAS.txt). Fonturile sunt date citite la rulare de
# FreeType prin addFont (Components/HdsSubtitrariAspect.py), nu cod legat in enigma2 (GPL-2.0-only).
LICENSE = "GPL-3.0-or-later"
# md5 al fisierului din git, cu capete de rand LF (textul GPLv3 obisnuit, ca in retetele oe-alliance); 3c34afdc...
# era md5-ul copiei CRLF de pe Windows. .gitattributes tine files/ octet cu octet, deci md5-ul e acelasi peste tot.
LIC_FILES_CHKSUM = "file://COPYING;md5=d32239bcb673463ab874e80d47fae504"
PV = "1.0"

SRC_URI = " \
    file://TiresiasInfofont.ttf \
    file://TiresiasInfofontBold.ttf \
    file://TiresiasPCfont.ttf \
    file://TiresiasPCfontBold.ttf \
    file://COPYING \
    file://LICENTA-TIRESIAS.txt \
    "
S = "${UNPACKDIR}"

inherit allarch

do_configure[noexec] = "1"
do_compile[noexec] = "1"

do_install() {
    install -d ${D}${datadir}/fonts/tiresias
    for f in TiresiasInfofont TiresiasInfofontBold TiresiasPCfont TiresiasPCfontBold; do
        install -m 0644 ${S}/$f.ttf ${D}${datadir}/fonts/tiresias/$f.ttf
    done
    # licenta langa fonturi, cum cere GPL la fiecare copie data mai departe
    install -m 0644 ${S}/COPYING ${D}${datadir}/fonts/tiresias/COPYING
    install -m 0644 ${S}/LICENTA-TIRESIAS.txt ${D}${datadir}/fonts/tiresias/LICENTA-TIRESIAS.txt
}

FILES:${PN} = "${datadir}/fonts/tiresias"
