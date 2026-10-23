# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# hds-surse.bbclass: sursele programelor GPL, LGPL si MPL din imagine, pastrate la fiecare construire (INHERIT global,
# in configurarea distributiei sau in local.conf; clasa archiver lucreaza pe fiecare reteta).
#
# Ce se pastreaza, in ${DEPLOY_DIR}/sources/<arhitectura>/<reteta>-<versiune>/:
#   - sursa originala, exact fisierele din SRC_URI (arhivele descarcate, peticele, fisierele locale ale retetei), plus
#     fisierul series cu ordinea peticelor (ARCHIVER_MODE[src] = "original");
#   - reteta (.bb, .bbappend si .inc) (ARCHIVER_MODE[recipe] = "1").
# Cu reteta, sursa originala si peticele, oricine reface pachetul exact ca la noi; configurarea si straturile vin
# din arhiva straturilor (receptor/imagine-hdsatelit/oe-build/surse-versiune.sh le strange pe versiune).
#
# Numai retetele pentru receptor (target), nu uneltele de pe PC. Licentele inchise raman pe dinafara, la fel ca la
# archiver. enigma2-hdsatelit se ia din depozitul git local: archiver ar pune in arhiva si dosarul .git (istoria de
# lucru), deci se scoate de aici; codul imaginii intra in arhiva versiunii cu git archive, la comiterea construita.
#
# Arhivele sunt in sstate (do_deploy_archives): o reteta neschimbata nu se arhiveaza din nou.
#
# do_ar_original din archiver impacheteaza o sursa git numai din clona din DL_DIR (git2/...); cand descarcarea a
# pastrat numai arhiva git scurta (gitshallow_*.tar.gz, de exemplu la glibc), sursa ar lipsi fara niciun mesaj.
# hds_surse_verifica (dupa do_ar_original) o despacheteaza la comiterea retetei si o pune in arhiva, fara .git, iar
# orice alta sursa din SRC_URI care nu e in DL_DIR opreste construirea. Arhiva se face cu tar | xz prin bash cu
# pipefail: un tar cazut opreste construirea, iar fisierul inceput se sterge (altfel ar ramane o arhiva trunchiata).
#
# MS-PL si MS-RL (copyleft pe fisier) sunt in aceeasi clasa cu LGPL si MPL in lista licentelor (lista_licente.py),
# deci si sursa lor se pastreaza.

inherit archiver

ARCHIVER_MODE[src] = "original"
ARCHIVER_MODE[recipe] = "1"
ARCHIVER_MODE[diff] = "0"
ARCHIVER_MODE[dumpdata] = "0"
ARCHIVER_MODE[srpm] = "0"

COPYLEFT_RECIPE_TYPES = "target"
COPYLEFT_LICENSE_INCLUDE = "GPL* LGPL* AGPL* MPL* EPL* CDDL* EUPL* MS-PL MS-RL"
COPYLEFT_LICENSE_EXCLUDE = "CLOSED Proprietary Commercial*"
COPYLEFT_PN_EXCLUDE = "enigma2-hdsatelit"

python hds_surse_verifica() {
    import shutil
    import subprocess
    import tempfile

    if d.getVarFlag("ARCHIVER_MODE", "src") != "original":
        return
    ar_outdir = d.getVar("ARCHIVER_OUTDIR")
    urls = []
    for url in (d.getVar("SRC_URI") or "").split():
        decoded = bb.fetch2.decodeurl(url)
        for param in ("destsuffix", "subdir"):
            decoded[5].pop(param, None)
        urls.append(bb.fetch2.encodeurl(decoded))
    ld = bb.data.createCopy(d)
    ld.setVar("SRC_URI", "")
    fetch = bb.fetch2.Fetch(urls, ld)
    for url in fetch.urls:
        ud = fetch.ud[url]
        local = fetch.localpath(url).rstrip("/")
        if os.path.exists(local):
            continue
        scurta = getattr(ud, "fullshallow", None)
        if not (getattr(ud, "shallow", False) and scurta and os.path.isfile(scurta)):
            bb.fatal("hds-surse: sursa %s nu e in DL_DIR (%s); arhiva sursei ar fi incompleta" % (url, local))
        nume = bb.fetch2.decodeurl(url)[5].get("name", "")
        fisier = "%s%s.tar.xz" % (d.getVar("PF"), "-" + nume if nume else "")
        dosar = tempfile.mkdtemp(dir=d.getVar("ARCHIVER_WORKDIR"))
        fetch.unpack(dosar, (url,))
        bb.utils.mkdirhier(ar_outdir)
        arhiva = os.path.join(ar_outdir, fisier)
        comanda = "tar --exclude=.git --sort=name --owner=0 --group=0 --numeric-owner -cf - . | xz %s > %s" % (
            d.getVar("XZ_DEFAULTS"), arhiva)
        try:
            subprocess.check_call(["bash", "-o", "pipefail", "-c", comanda], cwd=dosar)
        except subprocess.CalledProcessError as e:
            if os.path.exists(arhiva):
                os.remove(arhiva)
            bb.fatal("hds-surse: arhiva %s nu s-a putut face (tar | xz, iesirea %d)" % (fisier, e.returncode))
        shutil.rmtree(dosar)
        bb.note("hds-surse: %s din %s (arhiva git scurta, fara .git)" % (fisier, os.path.basename(scurta)))
}
do_ar_original[postfuncs] += "hds_surse_verifica"
do_ar_original[dirs] += "${ARCHIVER_WORKDIR}"
