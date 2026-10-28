SUMMARY = "Skinul HDSatelit"
DESCRIPTION = "Skinul HDSatelit pentru enigma2 (1920x1080), cu fonturile si componentele lui Python. Monea Software pentru HD Satelit."
LICENSE = "CLOSED"
PV = "0.1.0"

# arborele de instalare al skinului, montat doar-citire de oe.sh din hdsatelit-unelte/receptor/skin/src/usr;
# o cale file:// absoluta se despacheteaza cu tot cu cale, deci sursa ajunge in skin/hds/skin
SRC_URI = "file:///hds/skin;subdir=skin"
S = "${UNPACKDIR}/skin/hds/skin"

inherit allarch

do_configure[noexec] = "1"
do_compile[noexec] = "1"

do_install() {
    install -d ${D}${datadir}/enigma2 ${D}${libdir}/enigma2
    cp -R --no-preserve=ownership ${S}/share/enigma2/HDSatelit ${D}${datadir}/enigma2/
    if [ -d ${S}/lib/enigma2/python ]; then
        cp -R --no-preserve=ownership ${S}/lib/enigma2/python ${D}${libdir}/enigma2/
        find ${D}${libdir}/enigma2/python -name "__pycache__" -type d -prune -exec rm -rf {} +
        # .pyc vechi puse langa .py: Python 3 nu le foloseste, doar ocupa loc
        find ${D}${libdir}/enigma2/python -name "*.pyc" -type f -delete
        # do_rootfs esua (20.09.2026): Components/Converter/Hds*.py (47 fisiere) sunt o COPIE VECHE,
        # ramasa in arborele skinului dintr-o vreme cand codul convertoarelor traia aici; codul CHIAR
        # intretinut acum e in hdsatelit-image/lib/python/Components/Converter/ (Makefile.am il instaleaza
        # deja prin reteta enigma2-hdsatelit, de care skinul depinde oricum -- vezi RDEPENDS mai jos), ultima
        # modificare 17.09 acolo fata de 15.09 aici, cu imbunatatiri reale (identificare Amiko Viper 4K,
        # tratare erori la numarul de clienti de flux) absente in copia asta. Cele doua retete instalau
        # amandoua acelasi loc (${libdir}/enigma2/python/Components/Converter/...), ceea ce facea do_rootfs
        # sa esueze la revendicarea fisierelor. Skinul insusi nu are nimic altceva sub Components/ (verificat:
        # doar Converter/Hds*.py existau acolo) -- Plugins/Extensions/HdsSkinSetari/ (singurul cod Python
        # skin-specific real) ramane instalat normal, neatins de linia de mai jos.
        rm -rf ${D}${libdir}/enigma2/python/Components
    fi
    find ${D} -type d -exec chmod 0755 {} +
    find ${D} -type f -exec chmod 0644 {} +
}

FILES:${PN} = "${datadir}/enigma2/HDSatelit ${libdir}/enigma2/python"
# componentele Python ale skinului (HdsCommon) folosesc json
RDEPENDS:${PN} = "enigma2-hdsatelit python3-json"
