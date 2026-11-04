# ICU pentru receptor: datele (libicudata, ~31 MB intregi) filtrate la limbile meniului imaginii (po/Makefile.am din
# hdsatelit-image, 30 de limbi; norvegiana si ca nb, nn). Le foloseste numai WPE WebKit (navigatorul web): formatarea
# datelor si a numerelor (Intl), ordinea alfabetica, numele limbilor si tarilor. Raman intregi toate datele care nu tin
# de o limba: conversiile de codari (paginile vechi in windows-1250, iso-8859-2 si altele), despartirea randurilor si a
# cuvintelor (si dictionarele pentru thai, chineza, japoneza), normalizarea (si adresele IDN), ordinea UCA.
# O pagina intr-o limba din afara listei se deseneaza la fel; numai Intl foloseste regulile generale (root).
# Numai clasa target: icu-native (uneltele de constructie) ramane cel din oe-core. Fisierul filtrului are alt nume decat
# filter.json-ul gol din oe-core, ca sa nu-l ia si icu-native; do_make_icudata il pune in locul aceluia.
# Schema filtrului: icu/source/python/icutools/databuilder/filtration_schema.json din sursa ICU 77.
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI:append:class-target = " file://hds-icu-filtru.json"
PACKAGECONFIG:append:class-target = " make-icudata"

do_make_icudata:prepend:class-target() {
    cp ${UNPACKDIR}/hds-icu-filtru.json ${UNPACKDIR}/filter.json
}
