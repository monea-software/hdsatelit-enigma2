# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# hds-licente.bbclass: lista licentelor din imagine, facuta la construire (inherit in reteta imaginii).
#
# Pasul ruleaza la inceputul lui do_image (IMAGE_PREPROCESS_COMMAND), pe radacina finala: dupa ce
# license_create_manifest a scris license.manifest si dupa ce rootfs.py a scos run-postinsts, deci lista spune exact
# ce pachete ajung in imagine. Cheama files/hds-licente/lista_licente.py din acest strat (gasit prin BBPATH) si scrie
# in imagine:
#   /usr/share/hdsatelit/licente/lista.json   un rand pe reteta (versiunea, licentele, clasa, pachetele, textele),
#                                             componentele din pachetele inchise si fonturile
#                                             (files/hds-licente/componente.json), pachetele din imagine, build-ul din
#                                             /etc/image-version si adresa sursei (HDS_SURSA_ADRESA)
#   /usr/share/hdsatelit/licente/texte/*.gz   fiecare text de licenta o data, gzip fara nume si fara data
# O copie a lui lista.json merge langa imagine, <IMAGE_NAME>.licente.json (pentru pagina sursei versiunii).
# Pachetele producatorului au in componente.json masina ca "${MACHINE}" (dinobot-libs-${MACHINE}); scriptul o inlocuieste
# cu MACHINE (u57 la V20/V30, u571 la V40) si opreste construirea daca un astfel de pachet lipseste din imagine.
#
# Construirea se opreste cand lista nu poate fi completa: un pachet fara intrare in license.manifest, o licenta din
# afara claselor stiute, o reteta libera fara niciun text de licenta, o componenta cu clasa necunoscuta; dupa scriere,
# verifica() citeste lista inapoi din radacina si opreste construirea daca lipseste sau nu se potriveste cu imaginea
# (versiunea, build-ul, pachetele, textele).

HDS_SURSA_ADRESA ?= "https://hdsatelit.com/codul-sursa/"
HDS_LICENTE_SCRIPT = "files/hds-licente/lista_licente.py"
HDS_LICENTE_DATE = "files/hds-licente/componente.json"

def hds_licente_fisier(d, nume):
    import bb.utils
    cale = bb.utils.which(d.getVar("BBPATH"), nume)
    if not cale:
        bb.fatal("hds-licente: %s lipseste din straturi (BBPATH)" % nume)
    return cale

def hds_licente_modul(d):
    import importlib.util
    cale = hds_licente_fisier(d, d.getVar("HDS_LICENTE_SCRIPT"))
    spec = importlib.util.spec_from_file_location("hds_lista_licente", cale)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul

def hds_licente_sume(d):
    # scriptul si datele lui sunt intrari ale lui do_image: o schimbare in oricare reface pasul
    return " ".join("%s:True" % hds_licente_fisier(d, d.getVar(v)) for v in ("HDS_LICENTE_SCRIPT", "HDS_LICENTE_DATE"))

python hds_licente_imagine() {
    import os
    import shutil
    from oe.rootfs import image_list_installed_packages

    m = hds_licente_modul(d)
    radacina = d.getVar("IMAGE_ROOTFS")
    dosar_licente = d.getVar("LICENSE_DIRECTORY")
    manifest = os.path.join(dosar_licente, d.getVar("SSTATE_PKGARCH"), d.getVar("IMAGE_NAME"), "license.manifest")
    if not os.path.isfile(manifest):
        bb.fatal("hds-licente: lipseste %s (license_create_manifest nu a rulat)" % manifest)
    # ordinea de cautare din license_image.bbclass: intai arhitectura cea mai specifica
    arhitecturi = d.getVar("SSTATE_ARCHS").split()
    arhitecturi.reverse()
    # numele pachetului in imagine (libc6) -> numele din license.manifest (glibc), ca in license_create_manifest
    pkgdata = d.getVar("PKGDATA_DIR")
    instalate = {}
    for pachet in image_list_installed_packages(d):
        legatura = os.path.join(pkgdata, "runtime-reverse", pachet)
        instalate[pachet] = os.path.basename(os.readlink(legatura)) if os.path.islink(legatura) else pachet
    scoase = set(m.SCOASE_DUPA_MANIFEST) | set((d.getVar("ROOTFS_RO_UNNEEDED") or "").split())
    versiune = d.getVar("DISTRO_VERSION")

    lista, texte, erori = m.construieste(manifest, dosar_licente, arhitecturi, instalate, radacina,
        hds_licente_fisier(d, d.getVar("HDS_LICENTE_DATE")), d.getVar("COMMON_LICENSE_DIR"), versiune,
        d.getVar("DISTRO_NAME"), d.getVar("MACHINEBUILD") or d.getVar("MACHINE"), d.getVar("HDS_SURSA_ADRESA"),
        scoase, masina_oe=d.getVar("MACHINE"))
    for eroare in erori:
        bb.error("hds-licente: %s" % eroare)
    if erori:
        bb.fatal("hds-licente: lista licentelor nu se poate face (%d erori)" % len(erori))

    iesire = os.path.join(radacina, m.DOSAR_LISTA)
    marime = m.scrie(lista, texte, iesire)
    erori = m.verifica(radacina, manifest, list(instalate), versiune, scoase)
    for eroare in erori:
        bb.error("hds-licente: %s" % eroare)
    if erori:
        bb.fatal("hds-licente: lista licentelor din imagine e gresita (%d erori)" % len(erori))

    imgdeploy = d.getVar("IMGDEPLOYDIR")
    bb.utils.mkdirhier(imgdeploy)
    shutil.copyfile(os.path.join(iesire, m.NUME_LISTA), os.path.join(imgdeploy, d.getVar("IMAGE_NAME") + ".licente.json"))
    rz = lista["rezumat"]
    bb.note("hds-licente: %d retete, %d pachete, %d texte, %d octeti in /%s" % (rz["retete"], rz["pachete"],
        rz["texte"], marime, m.DOSAR_LISTA))
}
hds_licente_imagine[vardepsexclude] += "SSTATE_ARCHS"

IMAGE_PREPROCESS_COMMAND += "hds_licente_imagine "
do_image[file-checksums] += "${@hds_licente_sume(d)}"
