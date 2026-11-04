SUMMARY = "HDSatelit: probele receptorului pornite de beta tester (setul actualizabil prin feed)"
DESCRIPTION = "Probele automate ale receptorului (tunerele si semnalul, imaginea si sunetul, HDMI, reteaua, ceasul, \
stocarea, memoria, procesorul, DAB+, T2-MI, HbbTV, navigatorul, actualizarea, telecomanda, afisajul), in \
/usr/share/hdsatelit-probe. Le porneste beta testerul din meniul lui (Screens/HdsProbe.py, pagina web /probe), prin \
cadrul Components/HdsProbe.py din enigma2-hdsatelit. Pachet separat de enigma2: o proba noua vine prin feed fara o \
versiune noua a imaginii. Cadrul foloseste setul numai cu index.json.sig bun (Ed25519, cheile feedului, scopul \
hdsatelit-probe) si cu suma fiecarui fisier din index; altfel ramane setul care vine cu imaginea. Datele din files/ le \
scrie fa_pachet_probe.py, din uneltele noastre, din aceeasi sursa ca imaginea \
(lib/python/Components/HdsProbeIncluse), nu se schimba de mana. Monea Software pentru HD Satelit."
LICENSE = "GPL-2.0-only"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/GPL-2.0-only;md5=801f80980d171dd6425610833a22dbe6"
# PV = versiunea setului din index.json (AAAA.LL.ZZ, cu .N la a doua schimbare din aceeasi zi); o scrie
# fa_pachet_probe.py pachet, impreuna cu lista fisierelor de mai jos
PV = "2026.10.26"
PR = "r0"
HDS_PROBE_FISIERE = "actualizare.py afisaj.py ceas.py dab.py decodor.py hbbtv.py hdmi.py memorie.py navigator.py procesor.py receptor.py retea.py stocare.py t2mi.py telecomanda.py tunere.py"

SRC_URI = "file://index.json file://index.json.sig file://verifica_probe.py \
	${@' '.join('file://' + f for f in d.getVar('HDS_PROBE_FISIERE').split())}"
S = "${UNPACKDIR}"

inherit allarch

do_configure[noexec] = "1"
do_compile[noexec] = "1"

do_install() {
    install -d ${D}${datadir}/hdsatelit-probe
    for f in index.json index.json.sig ${HDS_PROBE_FISIERE}; do
        install -m 0644 ${S}/$f ${D}${datadir}/hdsatelit-probe/$f
    done
    # paza: index.json cu versiunea retetei, fiecare proba cu suma din index si cu forma ceruta (PROBA, TEXTE, ruleaza),
    # semnatura de langa index; altfel constructia se opreste (receptorul n-ar folosi pachetul). verifica_probe.py nu
    # se instaleaza. Semnatura adevarata o verifica fa_pachet_probe.py (cu inelul imaginii) si receptorul.
    python3 ${S}/verifica_probe.py ${D}${datadir}/hdsatelit-probe "${PV}" --cu-semnatura || bbfatal "hdsatelit-probe: datele nu sunt bune"
}

FILES:${PN} = "${datadir}/hdsatelit-probe"
# cadrul probelor (Components/HdsProbe.py) vine in enigma2-hdsatelit de la 0.6.8
RDEPENDS:${PN} = "enigma2-hdsatelit (>= 0.6.8)"
