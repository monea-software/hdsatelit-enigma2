# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsCodorMpeg2.py: codorul de ecrane de pornire al imaginii, vazut din Python.
#
# Components/HdsEcranePornire.py face conversia NUMAI prin acest modul: converteste() cheama faceEcranPornire de mai
# jos, fara nicio unealta de rezerva (gst-launch/mpeg2enc/ffmpeg nu au poarta de marime).
# faceEcranPornire cheama functia din enigma2 (lib/gdi/ecranpornire.cpp), care:
#   - citeste marimea pozei din antet si o opreste daca e prea mare, INAINTE de a cere memorie;
#   - decodeaza JPG sau PNG cu libjpeg / libpng (amandoua deja in imagine);
#   - intoarce poza dupa eticheta EXIF (poza de telefon tinut vertical);
#   - o aduce la 1920x1080 fara deformare, taind simetric ce depaseste;
#   - scrie un rand jos numai daca i se da unul (imaginea da textul gol: randul cu siturile si versiunea il scrie
#     interfata peste poza, la pornire, Components/HdsSemnaturaPornire.py);
#   - o codeaza ca un cadru I MPEG-2 (lib/gdi/mpeg2intra.cpp) si scrie fisierul cerut.
# Deci receptorul nu are nevoie de nicio unealta din afara imaginii pentru poza omului.
#
# Fisierul care merge (/usr/share/backdrop.mvi) nu se atinge de aici: scriem fisierul cerut, iar HdsEcranePornire il
# muta la locul lui (scrie in .nou si face os.replace).

from enigma import faEcranPornire

# Codul de cuantizare de pornire (1..31; mai mic = poza mai buna si fisier mai mare). 4 e cel din galeria retetei si
# da fisiere sub 350 KB la poze obisnuite. Daca fisierul iese prea mare, functia din enigma2 reia singura cu o
# cuantizare mai aspra.
CUANTIZARE = 4


def N_(text):
    """Marcheaza un text pentru xgettext (--keyword=N_) fara sa-l traduca acum: tabelul se traduce la folosire."""
    return text


# Ce a raspuns codorul, in vorbe pentru om (codurile sunt scrise in lib/gdi/ecranpornire.h); traduse la folosire
MESAJE = {
    -1: N_("poza nu mai există sau nu poate fi citită"),
    -2: N_("fișierul ales nu este o poză JPG sau PNG"),
    -3: N_("poza are prea mulți pixeli (peste 24 de milioane)"),
    -4: N_("poza pare stricată și nu a putut fi citită"),
    -6: N_("nu s-a putut scrie textul: lipsește fontul interfeței"),
    -7: N_("poza nu a putut fi codată"),
    -8: N_("fișierul nu a putut fi scris în memoria receptorului"),
    -9: N_("poza are prea multe detalii mărunte și nu încape ca ecran de pornire; alege o poză mai simplă"),
}


def _t(text):
    """Traducerea enigma2 (functia _ din builtins), sau textul insusi pe PC."""
    try:
        return _(text)  # noqa: F821
    except NameError:
        return text


def faceEcranPornire(cale_poza, cale_mvi, rand_jos=""):
    """Poza omului -> cadru I MPEG-2 de 1920x1080, fara text (rand_jos gol) sau cu randul dat scris jos.

    Asa il cheama HdsEcranePornire.converteste(): intoarce ceva adevarat daca a scris fisierul, si arunca o exceptie
    cu motivul daca nu (motivul ajunge in mesajul aratat omului).
    """
    cod = faEcranPornire(cale_poza, cale_mvi, rand_jos or "", CUANTIZARE)
    if cod:
        raise RuntimeError(_t(MESAJE[cod]) if cod in MESAJE else _t("codorul a răspuns %d") % cod)
    return True
