SUMMARY = "Ecranele de pornire HD Satelit"
DESCRIPTION = "Imaginea afisata de enigma2.sh la pornire (/usr/share/backdrop.mvi) si galeria de ecrane gata \
facute, din care utilizatorul alege din meniu sau din interfata web. Pozele nu au text: randul cu siturile si \
versiunea imaginii le scrie interfata peste poza, la pornire. Monea Software pentru HD Satelit."
LICENSE = "CLOSED"
PV = "0.5.0"

SRC_URI = " \
    file://backdrop.mvi \
    file://ecrane.json \
    file://ecran-acuarela.mvi \
    file://ecran-antena.mvi \
    file://ecran-aurora.mvi \
    file://ecran-caledelactee.mvi \
    file://ecran-caprioara.mvi \
    file://ecran-cascada.mvi \
    file://ecran-catelus.mvi \
    file://ecran-circuit.mvi \
    file://ecran-cirese.mvi \
    file://ecran-craciun.mvi \
    file://ecran-desert.mvi \
    file://ecran-fibre.mvi \
    file://ecran-grila.mvi \
    file://ecran-hexagon.mvi \
    file://ecran-iarna.mvi \
    file://ecran-inel.mvi \
    file://ecran-lac.mvi \
    file://ecran-lalele.mvi \
    file://ecran-lavanda.mvi \
    file://ecran-munti.mvi \
    file://ecran-orbita.mvi \
    file://ecran-orhidee.mvi \
    file://ecran-padure.mvi \
    file://ecran-particule.mvi \
    file://ecran-paste.mvi \
    file://ecran-pictura.mvi \
    file://ecran-pisoi.mvi \
    file://ecran-plaja.mvi \
    file://ecran-primavara.mvi \
    file://ecran-toamna.mvi \
    file://ecran-trandafiri.mvi \
    file://ecran-unde.mvi \
    file://ecran-valuri.mvi \
    file://ecran-vulpe.mvi \
    file://mici \
    "
S = "${UNPACKDIR}"

inherit allarch

do_configure[noexec] = "1"
do_compile[noexec] = "1"

do_install() {
    install -d ${D}${datadir}
    install -m 0644 ${S}/backdrop.mvi ${D}${datadir}/backdrop.mvi
    # galeria: ecranele din care se alege, plus lista cu numele, grupele si inlocuirile lor
    install -d ${D}${datadir}/hdsatelit/ecrane-pornire
    install -m 0644 ${S}/ecrane.json ${D}${datadir}/hdsatelit/ecrane-pornire/ecrane.json
    for f in ${S}/ecran-*.mvi; do
        install -m 0644 "$f" ${D}${datadir}/hdsatelit/ecrane-pornire/$(basename "$f" | sed 's/^ecran-//')
    done
    # previzualizarile mici (480x270 JPG), facute din chiar fisierele .mvi de mai sus: ePicLoad si browserul
    # citesc JPG/PNG, nu un cadru MPEG-2, iar receptorul nu are decodor MPEG-2 in afara stratului video
    install -d ${D}${datadir}/hdsatelit/ecrane-pornire/mici
    for f in ${S}/mici/*.jpg; do
        install -m 0644 "$f" ${D}${datadir}/hdsatelit/ecrane-pornire/mici/$(basename "$f")
    done
}

FILES:${PN} = "${datadir}/backdrop.mvi ${datadir}/hdsatelit/ecrane-pornire"
