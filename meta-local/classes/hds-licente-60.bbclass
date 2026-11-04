# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# NUMAI pe OE-Alliance 6.0 (pregateste-strat-60.sh o pune in stratul 6.0 si o mosteneste dupa hds-licente). Lista
# licentelor imaginii (files/hds-licente/lista_licente.py, acelasi fisier ca pe 5.6, neschimbat, ca semnatura lui
# do_image pe 5.6 sa ramana aceeasi) citeste license.manifest; in 6.0 acesta s-a schimbat
# (openembedded-core meta/lib/oe/license.py, _substitute_legacy_license):
#   - „&” si „|” au devenit „AND” si „OR” (SPDX), iar exceptiile apar ca „X WITH Y”;
#   - LICENSE = "CLOSED" iese gol in license.manifest (retetele noastre inchise: skinul, paznicul, bootlogo ...);
#   - nume noi: LicenseRef-Proprietary (fost Proprietary), LicenseRef-PD (fost PD), blessing (sqlite, domeniu public),
#     LicenseRef-<reteta>-CLOSED; GCR-docs (documentatia glib, socotita ca LGPL).
# hds_licente_modul de aici incarca acelasi modul si il aduce la 6.0, fara sa schimbe ce face pe expresiile vechi:
# AND/OR se citesc ca &/|, „X WITH Y” ca X (licenta principala, cu textul ei), licenta goala ca CLOSED, numele noi in
# clasele de pe 5.6 (inchisa, fara).

def hds_licente_modul(d):
    import importlib.util
    import re
    cale = hds_licente_fisier(d, d.getVar("HDS_LICENTE_SCRIPT"))
    spec = importlib.util.spec_from_file_location("hds_lista_licente", cale)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    atomi_vechi = m._atomi
    def _atomi(expresie):
        e = re.sub(r"(\S+)\s+WITH\s+[^\s()]+", r"\1", expresie)
        e = re.sub(r"\bAND\b", "&", e)
        e = re.sub(r"\bOR\b", "|", e)
        return atomi_vechi(e)
    m._atomi = _atomi

    clasa_veche = m.clasa_licenta
    def clasa_licenta(lic):
        l = lic.strip()
        if l.startswith("LicenseRef-Proprietary") or (l.startswith("LicenseRef-") and l.endswith("-CLOSED")):
            return clasa_veche("CLOSED")
        if l == "LicenseRef-PD":
            return clasa_veche("PD")
        if l == "blessing":
            return clasa_veche("PD")
        if l == "GCR-docs":
            # licenta documentatiei glib (common-licenses/GCR-docs): cere sursa versiunilor modificate, ca LGPL
            return clasa_veche("LGPL-2.1-only")
        return clasa_veche(l)
    m.clasa_licenta = clasa_licenta

    citeste_vechi = m.citeste_license_manifest
    def citeste_license_manifest(c):
        pachete = citeste_vechi(c)
        for p in pachete:
            if not p["licenta"]:
                p["licenta"] = "CLOSED"
        return pachete
    m.citeste_license_manifest = citeste_license_manifest
    return m
