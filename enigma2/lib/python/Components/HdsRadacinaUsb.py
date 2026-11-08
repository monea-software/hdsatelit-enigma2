# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com & hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
"""Pornirea de pe USB: radacina reala, fstab si swap pe acelasi disc.

Nu modifica partitiile si nu foloseste dispozitive MTD. Linia de pornire
poate apartine nucleului comun din NAND, deci nu stabileste radacina.
"""

import json
import os
import re
import stat
import subprocess
import tempfile

_UUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\Z")
_DISC = re.compile(r"sd[a-z]+\Z")
_USB = re.compile(r"/usb[0-9]+/")
_MARCA = "# hdsatelit: swap pentru radacina USB"


def _cale(rad, cale):
    return os.path.join(rad, cale.lstrip("/"))


def _citeste(cale):
    with open(cale, encoding="utf-8", errors="surrogateescape") as f:
        return f.read(1024 * 1024)


def descrieRadacina(rad="/", devnum=None, realpath=None):
    """Identitatea montarii active. O informatie lipsa inseamna necunoscut."""
    necunoscut = {"fel": "necunoscut"}
    try:
        if devnum is None:
            dev = os.stat(rad).st_dev
            devnum = os.major(dev), os.minor(dev)
        numar = "%d:%d" % devnum
        montare = None
        for rand in _citeste(_cale(rad, "proc/self/mountinfo")).splitlines():
            campuri = rand.split()
            if len(campuri) < 10 or campuri[4] != "/" or "-" not in campuri:
                continue
            sep = campuri.index("-")
            if campuri[2] == numar and len(campuri) > sep + 2:
                montare = campuri[sep + 1:sep + 3]
        if not montare:
            return necunoscut
        fel, sursa = montare
        if fel == "ubifs" and re.fullmatch(r"ubi[0-9]+[:_].+", sursa):
            return {"fel": "nand"}
        if fel != "ext4":
            return necunoscut
        real = (realpath or os.path.realpath)(_cale(rad, "sys/dev/block/" + numar))
        real = real.replace("\\", "/")
        if not _USB.search(real):
            return necunoscut
        parti = real.split("/")
        if "block" not in parti:
            return necunoscut
        i = parti.index("block")
        if len(parti) != i + 3:
            return necunoscut
        disc, partitie = parti[i + 1:]
        if not _DISC.fullmatch(disc) or not re.fullmatch(disc + r"[0-9]+", partitie):
            return necunoscut
        return {"fel": "usb", "disc": disc, "partitie": partitie, "numar": numar}
    except (OSError, ValueError, AttributeError, IndexError):
        return necunoscut


def radacinaUsb(rad="/"):
    return descrieRadacina(rad).get("fel") == "usb"


def radacinaNand(rad="/"):
    return descrieRadacina(rad).get("fel") == "nand"


def _ruleaza(args):
    p = subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, timeout=15, check=False)
    return p.returncode, p.stdout.decode("utf-8", "replace")


def _numarBloc(cale):
    try:
        s = os.stat(cale)
        if stat.S_ISBLK(s.st_mode):
            return os.major(s.st_rdev), os.minor(s.st_rdev)
    except (OSError, AttributeError):
        pass
    return None


def _swap(rad, info, ruleaza, bloc):
    """Un singur swap de pe discul radacinii, cu UUID unic intre discuri."""
    cod, text = ruleaza(["blkid"])
    if cod:
        return None
    volume = []
    for linie in text.splitlines():
        sursa, sep, date = linie.partition(":")
        if not sep or not re.fullmatch(r"/dev/[A-Za-z0-9/_-]+", sursa):
            continue
        campuri = dict(re.findall(r'\b([A-Z0-9_]+)="([^"\n]*)"', date))
        volume.append((sursa, campuri))
    disc = info["disc"]
    loc = _cale(rad, "sys/block/" + disc)
    rezultat = []
    for partitie in sorted(os.listdir(loc)):
        if not re.fullmatch(disc + r"[0-9]+", partitie):
            continue
        if partitie == info["partitie"]:
            continue
        baza = os.path.join(loc, partitie)
        try:
            if not _citeste(os.path.join(baza, "partition")).strip().isdigit():
                continue
            numar = tuple(int(x) for x in _citeste(os.path.join(baza, "dev")).strip().split(":"))
        except (OSError, ValueError):
            continue
        sursa = "/dev/" + partitie
        if bloc(_cale(rad, sursa)) != numar:
            continue
        potrivite = [date for dev, date in volume if dev == sursa]
        if len(potrivite) != 1 or potrivite[0].get("TYPE") != "swap":
            continue
        uuid = potrivite[0].get("UUID", "")
        if not _UUID.fullmatch(uuid):
            continue
        if sum(date.get("UUID", "").lower() == uuid.lower() for dev, date in volume) != 1:
            continue
        rezultat.append({"dispozitiv": sursa, "uuid": uuid, "numar": numar})
    return rezultat[0] if len(rezultat) == 1 else None


def _fstab(rad, uuid=None):
    """Scoate montarea NAND a radacinii; pastreaza restul configurarilor."""
    cale = _cale(rad, "etc/fstab")
    if os.path.islink(cale):
        raise OSError("fstab este o legatura")
    original = _citeste(cale)
    linii = []
    for linie in original.splitlines():
        campuri = linie.split()
        if len(campuri) >= 3 and campuri[1:3] == ["/", "ubifs"]:
            continue
        if _MARCA in linie:
            continue
        linii.append(linie)
    if uuid:
        exista = any(len(c) >= 3 and c[0].lower() == ("UUID=" + uuid).lower()
                     and c[2] == "swap" for c in (x.split() for x in linii))
        if not exista:
            linii.append("UUID=%s none swap sw 0 0 %s" % (uuid, _MARCA))
    nou = "\n".join(linii) + "\n"
    if nou == original:
        return
    fd, temporar = tempfile.mkstemp(prefix=".fstab-hds-", dir=os.path.dirname(cale))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", errors="surrogateescape") as f:
            f.write(nou)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temporar, stat.S_IMODE(os.stat(cale).st_mode))
        os.replace(temporar, cale)
    finally:
        if os.path.exists(temporar):
            os.unlink(temporar)


def porneste(rad="/", info=None, ruleaza=None, bloc=None):
    """Chemat la pornire. Nu opreste televizorul cand swap-ul lipseste."""
    info = info if info is not None else descrieRadacina(rad)
    if info.get("fel") != "usb":
        return {"stare": "nefolosit"}
    ruleaza, bloc = ruleaza or _ruleaza, bloc or _numarBloc
    try:
        # Corectarea radacinii nu depinde de existenta swap-ului.
        _fstab(rad)
        swap = _swap(rad, info, ruleaza, bloc)
        if not swap:
            return {"stare": "fara_swap"}
        active = []
        for linie in _citeste(_cale(rad, "proc/swaps")).splitlines()[1:]:
            campuri = linie.split()
            if campuri:
                active.append(campuri[0])
        deja = any(bloc(_cale(rad, dev)) == swap["numar"] for dev in active)
        if not deja:
            # UUID-ul a fost verificat ca unic si apartine aceluiasi disc.
            cod, text = ruleaza(["swapon", "UUID=" + swap["uuid"]])
            if cod:
                return {"stare": "eroare_swap", "cod": cod}
        _fstab(rad, swap["uuid"])
        return {"stare": "gata", "uuid": swap["uuid"]}
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as e:
        return {"stare": "eroare", "motiv": str(e)}


if __name__ == "__main__":
    print(json.dumps(porneste(), ensure_ascii=True))
