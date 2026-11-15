# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# hds-pyc-curat.bbclass: dupa "opkg remove" nu mai raman fisierele compilate scrise la rulare pentru fisierele .py ale
# pachetului (TODO 13.11 21:30). opkg sterge numai ce e in lista pachetului; <nume>.pyc / <nume>.pyo langa sursa (cum
# stau pe receptor), __pycache__/<nume>.*.pyc si originalele .py2 ale traducatorului Python 2 raman, cu dosarul lor
# (python3-e2icjson lasa .pyc; un plugin din Plugins/Extensions ramane cu plugin.pyc, deci tot plugin, fara pachet).
#
# Stergerile din interfata (Extensii, pagina web, temele) le curata enigma2 insusi (Components/HdsPycRamase.py, din
# Components/Ipkg.py). Clasa aceasta acopera stergerea din consola: fiecare pachet cu fisiere .py primeste la inceputul
# lui pkg_postrm un bloc cu dosarele si numele fisierelor lui .py, scrise la construire (in postrm lista opkg a
# pachetului nu mai e de folos: opkg a sters deja fisierele). Blocul:
#   - nu face nimic intr-o radacina de imagine ($D) si la "upgrade" (fisierele noi sunt deja la locul lor);
#   - sterge numai fisierele care poarta numele unui .py al pachetului si numai daca sursa nu mai exista;
#   - sterge cu rmdir (numai gol) __pycache__ si dosarele in care pachetul avea .py, cele mai adanci intai; niciodata
#     dosarul comun de deasupra (Plugins/Extensions, site-packages).
# Pachetele fara fisiere .py nu se schimba. Blocul se pune inaintea scriptului pachetului (un "exit 0" de la coada
# scriptului autorului nu-l mai sare); fiecare comanda a blocului iese cu 0, deci merge si sub "#!/bin/sh -e".
#
# Folosire: INHERIT += "hds-pyc-curat" in conf/distro/hdsatelit.conf. Schimba semnatura do_package a tuturor
# retetelor (prima constructie reface ambalarea tuturor pachetelor); de aceea se porneste o data cu o constructie
# intreaga, nu in mijlocul unui lot.

# pachetele care nu se sterg niciodata: fara bloc (altfel postrm-ul lor ar purta sute de randuri)
HDS_PYC_CURAT_SARITE ?= "enigma2 enigma2-hdsatelit python3-core python3-modules"

PACKAGESPLITFUNCS += "hds_pyc_curat"

python hds_pyc_curat() {
    import os

    pkgdest = d.getVar('PKGDEST')
    sarite = (d.getVar('HDS_PYC_CURAT_SARITE') or '').split()
    for pkg in (d.getVar('PACKAGES') or '').split():
        if pkg in sarite:
            continue
        radacina = os.path.join(pkgdest, pkg)
        if not os.path.isdir(radacina):
            continue
        perechi = []
        for dosar, dosare, fisiere in os.walk(radacina):
            dosare[:] = [x for x in dosare if x != '__pycache__']
            nume = sorted(f[:-3] for f in fisiere if f.endswith('.py') and len(f) > 3)
            if not nume:
                continue
            rel = '/' + os.path.relpath(dosar, radacina).replace(os.sep, '/')
            if rel == '/.':
                continue
            if any(c in rel + ''.join(nume) for c in ' \t\n\'"\\$`*?[]'):
                bb.note('hds-pyc-curat: %s: nume cu caractere speciale in %s, sarit' % (pkg, rel))
                continue
            perechi.append((rel, nume))
        if not perechi:
            continue
        # cele mai adanci dosare intai: un subdosar sters lasa parintele gol
        perechi.sort(key=lambda p: p[0].count('/'), reverse=True)
        randuri = '\n'.join('%s %s' % (rel, ' '.join(nume)) for rel, nume in perechi)
        bloc = '''# HD Satelit (hds-pyc-curat): compilatele scrise la rulare pentru fisierele .py ale pachetului
if [ -z "$D" ] && [ "$1" != "upgrade" ]; then
while read -r hds_d hds_n; do
    for hds_s in $hds_n; do
        [ -e "$hds_d/$hds_s.py" ] && continue
        rm -f "$hds_d/$hds_s.pyc" "$hds_d/$hds_s.pyo" "$hds_d/$hds_s.py2" 2>/dev/null
        rm -f "$hds_d/__pycache__/$hds_s".*.pyc "$hds_d/__pycache__/$hds_s".*.pyo 2>/dev/null
    done
    rmdir "$hds_d/__pycache__" 2>/dev/null || true
    rmdir "$hds_d" 2>/dev/null || true
done <<'HDS_PYC_CURAT'
%s
HDS_PYC_CURAT
fi
''' % randuri
        vechi = d.getVar('pkg_postrm:%s' % pkg) or ''
        if vechi.startswith('#!'):
            prim, _, rest = vechi.partition('\n')
            nou = prim + '\n' + bloc + rest
        else:
            nou = '#!/bin/sh\n' + bloc + vechi
        d.setVar('pkg_postrm:%s' % pkg, nou)
}
