#!/usr/bin/python3
# -*- coding: utf-8 -*-
# HDSatelit timerTask.py: trezirea din oprirea completa. Monea Software pentru HD Satelit, 24.09.2026.
#
# Cod propriu, instalat ca /usr/bin/timerTask.py de dinobot-hihalt-u57.bbappend (stratul meta-local).
# Il porneste /usr/bin/hihalt (binar inchis) la oprire, din /etc/rc0.d/S89suspend, cu
# "python /usr/bin/timerTask.py". Atunci retelele sunt oprite si radacina e numai citire.
#
# Ce face: citeste temporizatoarele din /etc/enigma2/timers.xml (si din pm_timers.xml, numai daca exista),
# alege cel mai devreme inceput viitor si cheama /usr/bin/hipmoc, fara shell:
#   - niciun temporizator viitor: "hipmoc" fara argument (asteptare adanca, trezire numai din telecomanda);
#   - altfel "hipmoc <secunde>": receptorul porneste singur dupa atatea secunde.
# Inregistrarile si comutarile (justplay) trezesc cu AVANS secunde inainte; temporizatoarele de pornire din
# pm_timers.xml (wakeup, wakeuptostandby) la ora lor. Cele dezactivate si cele din trecut nu conteaza.
# Orice fisier lipsa sau stricat se scrie pe stderr si se sare: receptorul se opreste oricum.
#
# Variabilele HDS_* schimba caile si ora, numai pentru probe (pe receptor nu sunt puse):
#   HDS_TIMERS_XML, HDS_PM_TIMERS_XML, HDS_HIPMOC, HDS_NOW (secunde Unix).

import os
import sys
import time

try:
    import xml.etree.ElementTree as ET
except Exception:  # pachetul python3-xml lipsa: fara temporizatoare, dar oprirea merge mai departe
    ET = None

TIMERS_XML = os.environ.get("HDS_TIMERS_XML", "/etc/enigma2/timers.xml")
PM_TIMERS_XML = os.environ.get("HDS_PM_TIMERS_XML", "/etc/enigma2/pm_timers.xml")
HIPMOC = os.environ.get("HDS_HIPMOC", "/usr/bin/hipmoc")

AVANS = 300                 # s, inregistrari si comutari: pornirea receptorului dureaza, inregistrarea nu asteapta
MINIM = 120                 # s, mai putin nu dam: receptorul trebuie sa apuce sa intre in asteptare
MAXIM = 400 * 24 * 3600     # s, hipmoc citeste numarul intr-un long de 32 de biti; peste un an nu are rost
TIPURI_TREZIRE = ("wakeup", "wakeuptostandby")


def jurnal(mesaj):
    try:
        sys.stderr.write("[timerTask] %s\n" % mesaj)
        sys.stderr.flush()
    except Exception:
        pass


def intreg(text, implicit=None):
    try:
        return int(float(text))
    except (TypeError, ValueError, OverflowError):
        return implicit


def temporizatoare(cale, lipsa_se_spune):
    """Elementele <timer> din fisier; lista goala daca fisierul lipseste sau nu se poate citi."""
    if not os.path.isfile(cale):
        if lipsa_se_spune:
            jurnal("%s lipseste" % cale)
        return []
    if ET is None:
        jurnal("modulul xml lipseste, %s nu se poate citi" % cale)
        return []
    try:
        return ET.parse(cale).getroot().findall("timer")
    except Exception as e:
        jurnal("%s nu se poate citi (%s), il sar" % (cale, e))
        return []


def momente_de_trezire(lista, acum, avans, doar_pornire):
    rezultat = []
    for t in lista:
        if intreg(t.get("disabled"), 0) != 0:
            continue
        if doar_pornire and (t.get("timertype") or "wakeup") not in TIPURI_TREZIRE:
            continue
        inceput = intreg(t.get("begin"))
        if inceput is None:
            jurnal("temporizator fara begin valid, il sar")
            continue
        if inceput > acum:
            rezultat.append(inceput - avans)
    return rezultat


def secunde_pana_la_trezire(acum):
    """None: fara trezire la timp. Altfel secundele de dat lui hipmoc, intre MINIM si MAXIM."""
    momente = momente_de_trezire(temporizatoare(TIMERS_XML, True), acum, AVANS, False)
    if os.path.exists(PM_TIMERS_XML):
        momente += momente_de_trezire(temporizatoare(PM_TIMERS_XML, False), acum, 0, True)
    if not momente:
        return None
    return max(MINIM, min(MAXIM, min(momente) - acum))


def main():
    try:
        acum = intreg(os.environ.get("HDS_NOW")) or int(time.time())
        secunde = secunde_pana_la_trezire(acum)
    except Exception as e:  # plasa: nimic neprevazut nu are voie sa opreasca oprirea
        jurnal("eroare neasteptata (%s), opresc fara trezire la timp" % e)
        secunde = None
    if secunde is None:
        comanda = [HIPMOC]
        jurnal("niciun temporizator viitor, pornire numai din telecomanda")
    else:
        # hipmoc citeste argumentul cu strtol(.., 0): un zero in fata ar fi octal. str() al unui intreg >= MINIM
        # nu are zero in fata.
        comanda = [HIPMOC, str(int(secunde))]
        jurnal("trezire peste %d s (%s)" % (secunde, time.strftime("%Y-%m-%d %H:%M:%S",
                                                                   time.localtime(acum + secunde))))
    try:
        import subprocess
        return subprocess.call(comanda)
    except Exception as e:
        jurnal("nu pot porni %s (%s)" % (HIPMOC, e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
