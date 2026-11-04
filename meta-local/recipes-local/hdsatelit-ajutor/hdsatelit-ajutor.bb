SUMMARY = "HDSatelit: ajutorul receptorului fara internet (textele paginilor de ajutor, fara poze)"
DESCRIPTION = "Paginile ajutorului online al imaginii (stb.hdsatelit.com/ajutor), numai textul, in romana si in \
engleza, cu tabelul ecran -> pagina si textele din jurul paginilor in cele 13 limbi ale imaginii. Le citesc tasta HELP, \
Meniu > Informatii despre sistem > Ajutor (Screens/HdsAjutor.py) si pagina web /ajutor (HdsWebControl/ajutor_web.py), prin \
Components/HdsAjutor.py din enigma2-hdsatelit. Pachet separat de enigma2: cand se schimba textele, vine prin feed fara \
o versiune noua a imaginii. Datele din files/ le scrie fa_ajutor_receptor.py, din uneltele noastre, din \
aceeasi sursa ca site-ul (nu se schimba de mana). Monea Software pentru HD Satelit."
LICENSE = "GPL-2.0-only"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/GPL-2.0-only;md5=801f80980d171dd6425610833a22dbe6"
# PV = data la care s-au schimbat datele (AAAA.LL.ZZ, cu .N la a doua schimbare din aceeasi zi); il scrie
# fa_ajutor_receptor.py, numai cand amprenta datelor de mai jos nu mai e aceeasi (nu se schimba de mana)
# amprenta datelor: 7d36c82447a0443115b174a85bc2e553fa4015ea2d38992601ed1fd947bdd69e
PV = "2026.10.26"
PR = "r0"

SRC_URI = "file://index.json file://ro.dat file://en.dat file://cauta-ro.dat file://cauta-en.dat file://verifica_ajutor.py"
S = "${UNPACKDIR}"

inherit allarch

do_configure[noexec] = "1"
do_compile[noexec] = "1"

do_install() {
    install -d ${D}${datadir}/hdsatelit-ajutor
    for f in index.json ro.dat en.dat cauta-ro.dat cauta-en.dat; do
        install -m 0644 ${S}/$f ${D}${datadir}/hdsatelit-ajutor/$f
    done
    # paza: index.json valid, cu versiunea retetei, fiecare pagina in fisierul ei si despachetabila; altfel constructia
    # se opreste (receptorul ar arata pagini goale). verifica_ajutor.py nu se instaleaza.
    python3 ${S}/verifica_ajutor.py ${D}${datadir}/hdsatelit-ajutor "${PV}" || bbfatal "hdsatelit-ajutor: datele nu sunt bune"
}

FILES:${PN} = "${datadir}/hdsatelit-ajutor"
