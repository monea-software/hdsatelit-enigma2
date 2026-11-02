# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""HdsMultumiri: randul de multumiri pentru toti beta testerii, jos in "Despre imagine" (Screens/Information.py,
HdsAbout.populate; pagina web /informatii/despre ia acelasi text).

Numele vin de pe server (https://stb.hdsatelit.com/forum/testeri.json, lista publica a testerilor), deja in ordinea
lor: cele mai multe XP de tester primul, la XP egal cine s-a inscris mai devreme. Imaginea ia numai campul "nume", in
ordinea primita (fara sortare proprie), deci un tester nou apare fara imagine noua. Numai numele alese de testeri pe
site si pe forum; serverul nu trimite altceva.

Doua copii, aceeasi forma {"v": 1, "actualizat": <unix, de pe server>, "nume": [...]}:
  - in imagine: ${datadir}/enigma2/multumiri-testeri.json (data/multumiri-testeri.json, refacuta la fiecare versiune
    de unealta multumiri_versiune.py --despre), pentru receptorul fara internet;
  - pe receptor: /etc/enigma2/hds-multumiri.json, scrisa atomic de actualizeaza(). Se arata copia cu "actualizat" mai
    nou; la egalitate, cea de pe receptor.
actualizeaza() cere lista cel mult o data pe zi (copia de pe receptor mai veche de o zi, socotita dupa ora scrierii
ei, si nicio incercare in ultima zi de la pornirea interfetei); un raspuns rau sau lipsa retelei nu schimba nimic.
porneste() o cheama pe un fir separat cand se deschide "Despre imagine" (pe televizor sau in web); ecranul arata ce
are, iar o lista noua se vede la urmatoarea deschidere. Fara dosarul copiei de pe receptor (pe PC) nu cere nimic.

Numele se curata: fara caractere de control sau de format (directie, latime zero), spatiile unite intr-unul (altfel
tabelul ar despica randul in eticheta / valoare), cel mult LUNGIME_MAX semne (unul mai lung se scurteaza cu "..."
tipografic, ca testerul sa ramana pe lista), cel mult NUME_MAX nume.

Modul curat (fara enigma la incarcare): probele pe PC in test_multumiri_testeri_0621.py.
"""

import json
import os
import re
import threading
import time

NUME_IMAGINE = "multumiri-testeri.json"
CALE_IMAGINE = None                       # None: ${datadir}/enigma2/multumiri-testeri.json; probele pun alta cale
CALE_RECEPTOR = "/etc/enigma2/hds-multumiri.json"
URL = "https://stb.hdsatelit.com/forum/testeri.json"
TIMP = 10.0                               # secunde, pentru conectare si fiecare citire
MARIME_MAX = 2 * 1024 * 1024              # octetii raspunsului si ai unei copii
NUME_MAX = 1000
LUNGIME_MAX = 40
ZI = 24 * 3600

NOU = "nou"
SARIT = "sarit"
EROARE = "eroare"

# caracterele de control (C0, C1) si de format (directia textului, latime zero, separatorii de rand si paragraf)
_ASCUNSE = re.compile(u"[\x00-\x1f\x7f-\x9f­؜᠎​-‏ -‮⁠-⁯﻿￹-￻]")
_STARE = {"incercare": None, "fir": None}


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_): textul se traduce la folosire."""
	return text


TEXT = N_("Mulțumim tuturor beta testerilor care au participat la realizarea imaginii HD Satelit: %s.")


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _jurnal(text):
	print("[HdsMultumiri] %s" % text)


def cale_imagine():
	"""Copia venita cu imaginea: ${datadir}/enigma2/multumiri-testeri.json."""
	if CALE_IMAGINE:
		return CALE_IMAGINE
	try:
		from enigma import eEnv
		return eEnv.resolve("${datadir}/enigma2/" + NUME_IMAGINE)
	except Exception:
		return "/usr/share/enigma2/" + NUME_IMAGINE


# ---------------------------------------------------------------- numele

def curat(nume):
	"""Un nume curat, sau "" (nu e sir sau nu ramane nimic din el)."""
	if not isinstance(nume, str):
		return ""
	nume = " ".join(_ASCUNSE.sub(" ", nume).split())
	if len(nume) > LUNGIME_MAX:
		nume = nume[:LUNGIME_MAX - 1].rstrip() + u"…"
	return nume


def curata(lista):
	"""Numele curate, in ordinea primita, cel mult NUME_MAX; cele care nu raman nimic se sar."""
	rez = []
	for n in lista if isinstance(lista, list) else []:
		n = curat(n)
		if n:
			rez.append(n)
			if len(rez) >= NUME_MAX:
				break
	return rez


def _actualizat(valoare, rezerva=0):
	if isinstance(valoare, bool) or not isinstance(valoare, (int, float)) or valoare <= 0:
		return int(rezerva)
	return int(valoare)


def copie_din_raspuns(corp, acum=None):
	"""Raspunsul serverului (octeti) -> octetii copiei {"v": 1, "actualizat", "nume"}, sau None: raspuns rau (prea
	mare, JSON stricat, fara lista "testeri", niciun nume). Folosita si de unealta care face copia din imagine."""
	if not isinstance(corp, bytes) or len(corp) > MARIME_MAX:
		return None
	try:
		d = json.loads(corp.decode("utf-8"))
	except (ValueError, UnicodeDecodeError):
		return None
	if not isinstance(d, dict) or not isinstance(d.get("testeri"), list):
		return None
	nume = curata([t.get("nume") for t in d["testeri"] if isinstance(t, dict)])
	if not nume:
		return None
	copie = {"v": 1, "actualizat": _actualizat(d.get("actualizat"), time.time() if acum is None else acum),
		"nume": nume}
	return (json.dumps(copie, ensure_ascii=False, indent=1) + "\n").encode("utf-8")


def _citeste_copie(cale):
	"""(actualizat, nume) dintr-o copie, sau None (lipseste, stricata, fara niciun nume)."""
	try:
		with open(cale, "rb") as f:
			date = f.read(MARIME_MAX + 1)
		if len(date) > MARIME_MAX:
			return None
		d = json.loads(date.decode("utf-8"))
	except (IOError, OSError, ValueError, UnicodeDecodeError):
		return None
	if not isinstance(d, dict) or d.get("v") != 1:
		return None
	nume = curata(d.get("nume"))
	if not nume:
		return None
	return _actualizat(d.get("actualizat")), nume


def nume():
	"""Numele de aratat: copia de pe receptor, altfel cea din imagine (si cea din imagine cand e mai noua, dupa o
	versiune noua pe un receptor fara internet), altfel nimic."""
	receptor = _citeste_copie(CALE_RECEPTOR)
	imagine = _citeste_copie(cale_imagine())
	if receptor and (not imagine or receptor[0] >= imagine[0]):
		return receptor[1]
	return imagine[1] if imagine else []


def text(lista=None, traducere=None):
	"""Fraza tradusa cu numele unite prin ", "; fara niciun nume, "" (randul nu apare)."""
	lista = nume() if lista is None else lista
	if not lista:
		return ""
	insiruire = ", ".join(lista)
	try:
		return (traducere or _t)(TEXT) % insiruire
	except (TypeError, ValueError):
		return TEXT % insiruire


# ---------------------------------------------------------------- actualizarea de pe server

def _citeste_url(url, timp, limita):
	from urllib.request import Request, urlopen
	cerere = Request(url, headers={"User-Agent": "hdsatelit-receptor/1", "Accept-Encoding": "identity",
		"Accept": "application/json"})
	r = urlopen(cerere, timeout=timp)
	try:
		lung = r.headers.get("Content-Length")
		if lung and lung.isdigit() and int(lung) > limita:
			raise ValueError("prea mare (%s octeti)" % lung)
		date = r.read(limita + 1)
	finally:
		r.close()
	if len(date) > limita:
		raise ValueError("prea mare (peste %d octeti)" % limita)
	return date


def _scrie_atomic(cale, octeti):
	"""Fisier temporar langa cel bun, fsync, os.replace; o cadere lasa copia veche neatinsa."""
	nou = cale + ".nou"
	try:
		with open(nou, "wb") as f:
			f.write(octeti)
			f.flush()
			os.fsync(f.fileno())
		os.replace(nou, cale)
	except BaseException:
		try:
			os.remove(nou)
		except OSError:
			pass
		raise


def e_timpul(acum=None):
	"""Se cere lista acum? Numai pe receptor (dosarul copiei exista), cel mult o incercare pe zi de la pornirea
	interfetei, si numai cand copia de pe receptor lipseste, e mai veche de o zi sau are ora in viitor (ceasul pus
	abia dupa scriere)."""
	acum = time.time() if acum is None else acum
	if not os.path.isdir(os.path.dirname(CALE_RECEPTOR) or "."):
		return False
	ultima = _STARE["incercare"]
	if ultima is not None and 0 <= acum - ultima < ZI:
		return False
	try:
		varsta = acum - os.path.getmtime(CALE_RECEPTOR)
	except OSError:
		return True
	return not 0 <= varsta < ZI


def actualizeaza(acum=None, citeste_url=None):
	"""Lista de pe server, scrisa atomic in copia de pe receptor cand e buna. Blocanta (fir separat).
	-> (stare, mesaj): NOU (scrisa), SARIT (nu e timpul) sau EROARE (nimic schimbat)."""
	acum = time.time() if acum is None else acum
	if not e_timpul(acum):
		return SARIT, "nu e timpul"
	_STARE["incercare"] = acum
	try:
		corp = (citeste_url or _citeste_url)(URL, TIMP, MARIME_MAX)
	except Exception as e:
		return EROARE, "%s: %s" % (type(e).__name__, e)
	octeti = copie_din_raspuns(corp, acum)
	if octeti is None:
		return EROARE, "raspuns respins"
	try:
		_scrie_atomic(CALE_RECEPTOR, octeti)
	except (IOError, OSError) as e:
		return EROARE, "scriere: %s" % e
	return NOU, "%d nume" % len(json.loads(octeti.decode("utf-8"))["nume"])


def _lucreaza():
	try:
		stare, mesaj = actualizeaza()
	except Exception as e:
		stare, mesaj = EROARE, "%s: %s" % (type(e).__name__, e)
	if stare != SARIT:
		_jurnal("%s (%s)" % (stare, mesaj))


def _fir_daemon(functie):
	t = threading.Thread(target=functie, name="hds-multumiri")
	t.daemon = True
	t.start()
	return t


def porneste(fir=None):
	"""Din "Despre imagine" (ecranul si pagina web): actualizarea pe un fir separat, cand e timpul si nu merge deja
	una. -> True daca a pornit."""
	vechi = _STARE["fir"]
	if vechi is not None and vechi.is_alive():
		return False
	if not e_timpul():
		return False
	_STARE["fir"] = (fir or _fir_daemon)(_lucreaza)
	return True
