# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Textele ferestrei programului de instalare (ofgwrite), in limba omului, pregatite inainte de init 4.
Cheama: Screens/HdsSoftwareUpdate.py si Components/HdsImagineOnline.py; peticul lui: ofgwrite-texte-5.0.4.patch.

Toate citirile fișierului de traduceri se fac aici, înainte de init 4. ofgwrite
primește conținutul verificat în OFGWRITE_TEXTS și nu mai citește fișierul după
oprirea interfeței. Valoarea goală cere engleza și inhibă orice citire C de pe disc.
La orice eroare, instalarea continuă cu engleza; excepțiile nu ies din helper.

Gettext-ul HDS are msgid în română. Un msgid nemodificat este o traducere validă
doar când configurația E2 spune ro; pentru altă limbă înseamnă catalog lipsă și
rândul folosește engleza. Fără builtins._ instalat se păstrează engleza chiar dacă
limba configurată este ro. Funcția nu schimbă limba sau mediul global Enigma2.
"""

import builtins
import os
import stat
import sys
import tempfile


CALE_TEXTE = "/tmp/.ofgwrite-texte"
MAX_FISIER = 32768
MAX_RANDURI = 128
MAX_CHEIE = 255
MAX_TRADUCERE = 768


def _identitate(text):
    return text


def _mesaje(_):
    # Lista literală este vizibilă pentru xgettext --keyword=_ și se evaluează
    # la fiecare apel: limba poate fi schimbată după importul acestui modul.
    return (
        ("Writing and verifying Dream kernel A", _("Se instalează și se verifică nucleul Dream A...")),
        ("Flashing failed", _("Instalarea a eșuat")),
        ("Done", _("Finalizat")),
        ("Step %d of %d", _("Pasul %d din %d")),
        ("Check only, nothing is written", _("Doar verificare, nu se instalează nimic")),
        ("Do not switch off the receiver", _("Nu opri receptorul")),
        ("Restart in %d s", _("Repornire în %d s")),
        ("Ends in %d s", _("Se închide în %d s")),
        ("Writing ext4 kernel", _("Se instalează nucleul ext4...")),
        ("Deleting rootfs", _("Se șterge sistemul vechi...")),
        ("Extracting rootfs", _("Se dezarhivează sistemul...")),
        ("Erasing kernel", _("Se șterge nucleul vechi...")),
        ("Writing kernel", _("Se instalează nucleul...")),
        ("Copying rootfs", _("Se copiază sistemul...")),
        ("Erasing rootfs", _("Se șterge sistemul vechi...")),
        ("Writing rootfs", _("Se instalează sistemul...")),
        ("Enigma2 could not be stopped, switching to runlevel 2 failed.", _("Enigma2 și serviciile nu au putut fi oprite.")),
        ("Nothing was flashed.", _("Nu s-a instalat nimic.")),
        ("Wait until E2 is stopped", _("Se așteaptă oprirea Enigma2...")),
        ("Enigma2 could not be stopped.", _("Enigma2 nu a putut fi oprit.")),
        ("Enigma2 starts again, nothing was flashed.", _("Enigma2 pornește din nou. Nu s-a instalat nimic.")),
        ("The flash environment could not be prepared.", _("Nu s-a putut pregăti instalarea.")),
        ("The mounts could not be moved to the flash environment.", _("Nu s-au putut pregăti partițiile pentru instalare.")),
        ("The root file system could not be mounted again.", _("Partiția sistemului nu a putut fi montată din nou.")),
        ("The root file system could not be mounted read-only.", _("Partiția sistemului nu a putut fi montată doar pentru citire.")),
        ("The rootfs could not be unpacked. The flashed image will not start like this.", _("Sistemul nu a putut fi dezarhivat. Imaginea instalată nu poate porni în această stare.")),
        ("Flash a backup.", _("Instalează o copie de siguranță.")),
        ("The check was successful.", _("Verificarea s-a încheiat cu succes.")),
        ("The kernel was flashed.", _("Nucleul a fost instalat.")),
        ("The kernel could not be flashed. The flashed image will not start like this.", _("Nucleul nu a putut fi instalat. Imaginea instalată nu poate porni în această stare.")),
        ("Killing processes", _("Se închid procesele...")),
        ("Syncing filesystem", _("Se sincronizează fișierele...")),
        ("init 2", _("Se opresc Enigma2 și serviciile...")),
        ("Mount rootfs", _("Se montează partiția sistemului...")),
        ("The root file system could not be mounted.", _("Partiția sistemului nu a putut fi montată.")),
        ("The rootfs could not be flashed. The flashed image will not start like this.", _("Sistemul nu a putut fi instalat. Imaginea instalată nu poate porni în această stare.")),
        ("Create Kernel.img", _("Se creează kernel.img...")),
        ("The image was flashed.", _("Imaginea a fost instalată.")),
        ("Bad blocks: %d (uncritical, when no changes)", _("Blocuri defecte: %d (fără risc dacă numărul nu crește)")),
        ("Flashing UBI image", _("Se instalează imaginea UBI...")),
        ("Formatting remaining eraseblocks", _("Se formatează blocurile de memorie rămase...")),
        ("ofgwrite - written by Betacentauri", _("ofgwrite - creat de Betacentauri")),
    )


def _limbaCurenta():
    try:
        from Components.config import config
        for sectiune, camp in (("osd", "language"), ("misc", "locale")):
            try:
                valoare = getattr(getattr(config, sectiune), camp).value
                if isinstance(valoare, str) and valoare:
                    return valoare.lower().replace("-", "_").split("_")[0]
            except Exception:
                pass
    except Exception:
        pass
    return ""


def _semnaturaFormat(text):
    semnatura = []
    pozitie = 0
    while pozitie < len(text):
        if text[pozitie] != "%":
            pozitie += 1
            continue
        pozitie += 1
        if pozitie == len(text) or text[pozitie] not in "ds%":
            raise ValueError("format neacceptat")
        semnatura.append(text[pozitie])
        pozitie += 1
    return tuple(semnatura)


def _textValid(text, limita):
    if not isinstance(text, str) or not text:
        raise ValueError("text lipsă")
    if len(text) > limita:
        raise ValueError("text prea lung")
    for caracter in text:
        cod = ord(caracter)
        if cod < 32 or 127 <= cod <= 159 or cod in (0x2028, 0x2029):
            raise ValueError("caracter de control")
    brut = text.encode("utf-8", "strict")
    if len(brut) > limita:
        raise ValueError("text prea lung")
    return brut


def _sterge(cale):
    try:
        os.unlink(cale)
    except Exception:
        pass


def scrieTexteOfgwrite():
    """Întoarce o copie env cu snapshot verificat, ori OFGWRITE_TEXTS='' (engleză)."""
    try:
        mediu = os.environ.copy()
    except Exception:
        mediu = {}
    # Suprascrie inclusiv un snapshot vechi moștenit de procesul Enigma2.
    mediu["OFGWRITE_TEXTS"] = ""
    temporar = None
    descriptor = None
    try:
        codare = sys.getfilesystemencoding().lower().replace("_", "-")
        if codare not in ("utf-8", "utf8"):
            raise ValueError("mediul nu folosește UTF-8")
        _ = getattr(builtins, "_", _identitate)
        if not callable(_) or _ is _identitate:
            raise ValueError("gettext nu este instalat")
        limba = _limbaCurenta()
        directie = "rtl" if limba in ("ar", "fa", "he", "ur", "ps", "sd", "ug", "yi", "ckb", "dv") else "ltr"
        originale = _mesaje(_identitate)
        traduse = _mesaje(_)
        if not 0 < len(traduse) <= MAX_RANDURI or len(traduse) != len(originale):
            raise ValueError("număr de texte neacceptat")
        randuri = [("OFGWRITE-TEXTS-1\t%s\n" % directie).encode("ascii")]
        chei = set()
        exista_traducere = False
        for (engleza, romana), (cheie, traducere) in zip(originale, traduse):
            if cheie != engleza or engleza in chei:
                raise ValueError("cheie neacceptată")
            chei.add(engleza)
            # Validarea precedă revenirea la engleză: un catalog stricat nu poate
            # ascunde formate noi, controale, octeți prea mulți ori UTF-8 invalid.
            _textValid(traducere, MAX_TRADUCERE)
            if _semnaturaFormat(engleza) != _semnaturaFormat(traducere):
                raise ValueError("formatul traducerii diferă")
            if traducere == romana and limba != "ro":
                traducere = engleza
            exista_traducere = exista_traducere or traducere != engleza
            randuri.append(_textValid(engleza, MAX_CHEIE) + b"\t" + _textValid(traducere, MAX_TRADUCERE) + b"\n")
        if not exista_traducere:
            raise ValueError("catalog fără traduceri")
        randuri.append(b"OFGWRITE-END\n")
        continut = b"".join(randuri)
        if len(continut) > MAX_FISIER:
            raise ValueError("fișier prea lung")
        descriptor, temporar = tempfile.mkstemp(prefix=".ofgwrite-texte.", dir="/tmp")
        os.fchmod(descriptor, 0o600)
        fisier = os.fdopen(descriptor, "wb")
        descriptor = None  # fdopen deține descriptorul de acum înainte.
        with fisier:
            fisier.write(continut)
            fisier.flush()
            os.fsync(fisier.fileno())
        os.replace(temporar, CALE_TEXTE)
        temporar = None
        descriptor = os.open(CALE_TEXTE, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
        detalii = os.fstat(descriptor)
        if not stat.S_ISREG(detalii.st_mode) or detalii.st_uid != os.geteuid() or detalii.st_size != len(continut):
            raise ValueError("fișier de traduceri neacceptat")
        fisier = os.fdopen(descriptor, "rb")
        descriptor = None  # fdopen deține și descriptorul recitirii.
        with fisier:
            recitit = fisier.read(MAX_FISIER + 1)
        if len(recitit) > MAX_FISIER or recitit != continut:
            raise ValueError("recitirea traducerilor a eșuat")
        # Decodarea strictă și codarea mediului UTF-8 păstrează aceiași octeți și
        # aceeași ordine a caracterelor până la getenv din procesul ofgwrite.
        mediu["OFGWRITE_TEXTS"] = recitit.decode("utf-8", "strict")
    except Exception:
        mediu["OFGWRITE_TEXTS"] = ""
        _sterge(CALE_TEXTE)
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except Exception:
                pass
        if temporar is not None:
            _sterge(temporar)
    return mediu
