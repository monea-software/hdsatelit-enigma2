# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsEcranePornire.py: datele si comenzile ecranului de pornire (poza pusa de enigma2.sh cu showiframe
# /usr/share/backdrop.mvi, inainte sa porneasca interfata). Aceeasi sursa pentru ecranul de pe televizor
# (Screens/HdsEcranPornire.py) si pentru interfata web (HdsWebControl/ecran_pornire_web.py).
#
# Galeria o instaleaza reteta hdsatelit-bootlogo in /usr/share/hdsatelit/ecrane-pornire/: cate un .mvi pentru fiecare
# ecran, ecrane.json (grupele, ecranele, ecranul implicit si „inlocuiri”: ecranul scos din galerie -> cel care ii ia
# locul) si mici/<id>.jpg, previzualizarile de 480x270. Pozele nu au niciun text: randul cu siturile si versiunea
# imaginii se scrie pe OSD, peste poza, la pornire (Components/HdsSemnaturaPornire.py). La fel poza omului: se aduce
# la 1920x1080 si se codeaza fara niciun rand scris in ea.
#
# Reguli:
# 1. Octetii primiti din retea nu se scriu peste /usr/share/backdrop.mvi. Poza urcata se scrie intai in dosarul ei
#    (/etc/enigma2/hdsatelit/ecrane-mele/), se converteste acolo, si abia fisierul .mvi rezultat se pune pe locul
#    ecranului activ, prin scriere alaturi + os.replace (o pana de curent in mijloc lasa fisierul vechi intreg, nu
#    unul pe jumatate, care ar opri receptorul la sigla).
# 2. Niciun nume primit din retea nu intra intr-o cale. Se accepta doar identificatori din [a-z0-9-], iar calea
#    construita e verificata la final cu os.path.realpath, sa stea chiar in dosarul ei.
# 3. Memoria flash nu se umple: inainte de a primi o poza se verifica spatiul liber, se tin cel mult MAX_PROPRII
#    ecrane proprii, iar poza sursa se pastreaza doar daca e mica.
# 4. Punerea unui ecran nu reporneste interfata si nu atinge showiframe (vezi aplica() si nota de langa ea).
# 5. Pachetul hdsatelit-bootlogo e proprietarul lui /usr/share/backdrop.mvi, deci o actualizare a lui pune la loc
#    ecranul implicit. verificaLaPornire() pune din nou ecranul ales de om (sau pe cel care ii ia locul, daca a fost
#    scos din galerie), pe un fir separat, si scrie pe flash numai cand fisierul chiar difera.
# 6. Ecranele din galerie se pot sterge, ca sa se elibereze loc (nu ecranul implicit, nici cel pus sau ales acum).
#    Fisierele (.mvi si poza mica) se sterg de pe disc, iar id-ul se tine minte in ecrane-sterse.json, langa alegere:
#    o actualizare a pachetului le aduce inapoi, iar verificaLaPornire() le sterge din nou. „Pune la loc” goleste
#    lista; ecranele revin cu urmatoarea actualizare a pachetului (sau indata, daca fisierele sunt inca pe disc).
#
# Numele grupelor si ale ecranelor: in ecrane.json in romana (si engleza, pentru cine citeste fisierul); pe televizor
# se traduc in limba interfetei ca orice text (_t pe numele romanesc, NUME_GALERIE le arata lui xgettext), iar pagina
# web, care e in romana, le ia romanesti.

from __future__ import absolute_import

import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import threading
import time

# ------------------------------------------------------------------ locuri pe disc
CALE_GALERIE = "/usr/share/hdsatelit/ecrane-pornire"
CALE_GALERIE_MICI = CALE_GALERIE + "/mici"
CALE_LISTA = CALE_GALERIE + "/ecrane.json"
CALE_ACTIV = "/usr/share/backdrop.mvi"
CALE_PROPRII = "/etc/enigma2/hdsatelit/ecrane-mele"
CALE_ALES = "/etc/enigma2/hdsatelit/ecran-pornire-ales.json"

# ecranul pus de reteta ca /usr/share/backdrop.mvi, cand ecrane.json nu spune altul
IMPLICIT = "grila"

# ------------------------------------------------------------------ limite (si de ce atat)
# Poza omului: 8 MB. O poza de telefon de 12 megapixeli in JPG are 3-6 MB, iar un PNG de 1920x1080 are 1,3-2,8 MB.
# Mai mult n-are rost: imaginea se aduce oricum la 1920x1080, iar corpul cererii sta in memoria procesului enigma2
# pana e citit intreg. Restul rutelor raman la 64 KB.
MAX_POZA = 8 * 1024 * 1024
# Sub atat nici nu are ce sa fie o poza adevarata (antetul singur e mai mare).
MIN_POZA = 128
# Bomba de decompresie: un PNG de 100 de octeti poate declara 60000x60000 si umple memoria decodorului. Latura maxima
# acceptata; 10000 de puncte acopera orice aparat foto din comert.
MAX_LATURA = 10000
# Cate ecrane proprii se tin (memoria flash a receptorului e mica).
MAX_PROPRII = 6
# Cate marcaje JPEG se citesc cel mult cautand marimea pozei (vezi masuraPoza).
MAX_PASI_JPEG = 2000
# Poza sursa se pastreaza (ca sa se poata reface ecranul) doar daca e sub atat.
MAX_POZA_PASTRATA = 1024 * 1024
# Sub atat spatiu liber nu se mai primeste nimic: un rootfs plin opreste receptorul cu totul, nu doar functia asta.
MIN_SPATIU_LIBER = 20 * 1024 * 1024

_ID_BUN = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
SURSE = ("galerie", "propriu")


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi pe PC."""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def N_(text):
	"""Marcheaza un text pentru xgettext (--keyword=N_) fara sa-l traduca acum."""
	return text


# Numele romanesti ale grupelor si ecranelor din ecrane.json (reteta hdsatelit-bootlogo), ca xgettext sa le puna in
# po/*.po; la afisare trec prin _t. O grupa sau un ecran nou in galerie se adauga si aici.
NUME_GALERIE = (
	N_("Logo"), N_("Natură"), N_("Peisaje"), N_("Flori"), N_("Sărbători"), N_("Univers"), N_("Animale"),
	N_("Picturi"),
	N_("Grilă"), N_("Unde"), N_("Orbită"), N_("Auroră"), N_("Antenă"), N_("Fibre"), N_("Valuri"), N_("Particule"),
	N_("Fagure"), N_("Circuit"), N_("Pădure"), N_("Cascadă"), N_("Toamnă"), N_("Primăvară"), N_("Plajă"),
	N_("Munți"), N_("Lac de munte"), N_("Deșert"), N_("Lavandă"), N_("Trandafiri"), N_("Orhidee"),
	N_("Cireș înflorit"), N_("Lalele"), N_("Crăciun"), N_("Sat de iarnă"), N_("Paște"), N_("Inel orbital"),
	N_("Calea Lactee"), N_("Pisoi"), N_("Cățeluș"), N_("Vulpe"), N_("Căprioară"), N_("Pictură"), N_("Acuarelă"),
)


def _ro(d):
	"""Numele romanesc al unei grupe sau al unui ecran din ecrane.json (id-ul daca lipseste)."""
	return d.get("ro") or d["id"]


def _inLimba(d, limba):
	"""Numele dintr-o limba scrisa in ecrane.json („ro”, „en”), altfel cel romanesc."""
	return d.get(limba) or _ro(d)


# ------------------------------------------------------------------ cai sigure
def _idBun(text):
	return isinstance(text, str) and bool(_ID_BUN.match(text))


# realpath-ul dosarelor noastre, o data pe dosar (lista() cere zeci de cai la fiecare desen al ecranului)
_RADACINI = {}


def _radacina(dosar):
	r = _RADACINI.get(dosar)
	if r is None:
		r = _RADACINI[dosar] = os.path.realpath(dosar)
	return r


def _inDosar(dosar, nume):
	"""Calea dosar/nume, dar numai daca dupa realpath chiar sta in dosar. Altfel None."""
	cale = os.path.join(dosar, nume)
	try:
		real = os.path.realpath(cale)
		radacina = _radacina(dosar)
	except OSError:
		return None
	if real != radacina and not real.startswith(radacina + os.sep):
		return None
	return cale


def caleEcran(sursa, id_ecran):
	"""Fisierul .mvi al unui ecran, sau None daca sursa/id nu sunt bune ori fisierul nu exista."""
	if sursa not in SURSE or not _idBun(id_ecran):
		return None
	dosar = CALE_GALERIE if sursa == "galerie" else CALE_PROPRII
	cale = _inDosar(dosar, id_ecran + ".mvi")
	if cale is None or not os.path.isfile(cale):
		return None
	return cale


def caleMic(sursa, id_ecran):
	"""Poza mica de previzualizare (JPG), sau None. La ecranele proprii, daca previzualizarea facuta pe receptor
	lipseste, se intoarce poza sursa pastrata (tot o poza adevarata)."""
	if sursa not in SURSE or not _idBun(id_ecran):
		return None
	if sursa == "galerie":
		cale = _inDosar(CALE_GALERIE_MICI, id_ecran + ".jpg")
		return cale if cale and os.path.isfile(cale) else None
	for nume in (id_ecran + "-mic.jpg", id_ecran + ".jpg", id_ecran + ".png"):
		cale = _inDosar(CALE_PROPRII, nume)
		if cale and os.path.isfile(cale):
			return cale
	return None


def tipulPozei(cale):
	"""Tipul MIME al unei previzualizari, citit din primii octeti (nu dupa extensie)."""
	try:
		with open(cale, "rb") as f:
			inceput = f.read(8)
	except OSError:
		return None
	fel = felPoza(inceput + b"\0" * MIN_POZA)
	if fel == "jpg":
		return "image/jpeg"
	if fel == "png":
		return "image/png"
	return None


# ------------------------------------------------------------------ lista ecranelor
def _citesteDate():
	"""ecrane.json intreg, cu campurile verificate: {"grupe", "ecrane", "implicit", "inlocuiri"}."""
	gol = {"grupe": [], "ecrane": [], "implicit": IMPLICIT, "inlocuiri": {}}
	try:
		with open(CALE_LISTA, "r", encoding="utf-8") as f:
			date = json.load(f)
	except (OSError, ValueError):
		return gol
	if not isinstance(date, dict):
		return gol
	grupe = [g for g in date.get("grupe", []) if isinstance(g, dict) and _idBun(g.get("id", ""))]
	ecrane = [e for e in date.get("ecrane", []) if isinstance(e, dict) and _idBun(e.get("id", ""))]
	implicit = date.get("implicit")
	inlocuiri = date.get("inlocuiri")
	if not isinstance(inlocuiri, dict):
		inlocuiri = {}
	return {
		"grupe": grupe,
		"ecrane": ecrane,
		"implicit": implicit if _idBun(implicit) else IMPLICIT,
		"inlocuiri": dict((k, v) for k, v in inlocuiri.items() if _idBun(k) and _idBun(v)),
	}


def _citesteLista():
	date = _citesteDate()
	return date["grupe"], date["ecrane"]


def implicit():
	"""Ecranul pus de reteta, „Ecranul din fabrică” (grila, daca ecrane.json nu spune altul). Citeste numai lista, nu
	cauta ecranul pus acum."""
	return _citesteDate()["implicit"]


def _amprenta(cale):
	"""Marimea si un rezumat ieftin al fisierului, ca sa stim care ecran e cel activ fara sa citim toata galeria.
	Nu e criptografie: doar ca sa recunoastem acelasi fisier."""
	try:
		marime = os.path.getsize(cale)
		with open(cale, "rb") as f:
			cap = f.read(4096)
			if marime > 8192:
				f.seek(-4096, os.SEEK_END)
				coada = f.read(4096)
			else:
				coada = b""
	except OSError:
		return None
	h = hashlib.sha256()
	h.update(str(marime).encode("ascii"))
	h.update(cap)
	h.update(coada)
	return h.hexdigest()


def _ales():
	try:
		with open(CALE_ALES, "r", encoding="utf-8") as f:
			date = json.load(f)
	except (OSError, ValueError):
		return None
	if not isinstance(date, dict):
		return None
	if date.get("sursa") not in SURSE or not _idBun(date.get("id", "")):
		return None
	return date


def _scrieAles(sursa, id_ecran):
	a = _ales()
	if a is not None and a["sursa"] == sursa and a["id"] == id_ecran:
		return  # aceeasi alegere: nimic de scris pe flash
	try:
		os.makedirs(os.path.dirname(CALE_ALES), exist_ok=True)
		nou = CALE_ALES + ".nou"
		with open(nou, "w", encoding="utf-8") as f:
			json.dump({"sursa": sursa, "id": id_ecran, "cand": int(time.time())}, f)
			f.flush()
			try:
				os.fsync(f.fileno())
			except OSError:
				pass
		os.replace(nou, CALE_ALES)
	except OSError:
		pass  # alegerea tot s-a aplicat; doar nu o putem tine minte


# ------------------------------------------------------------------ ecranele sterse din galerie
def _caleSterse():
	"""ecrane-sterse.json, in acelasi dosar cu alegerea (/etc/enigma2/hdsatelit): trece si prin actualizari si prin
	copia setarilor facuta la scrierea imaginii."""
	return os.path.join(os.path.dirname(CALE_ALES), "ecrane-sterse.json")


def sterse():
	"""Id-urile ecranelor din galerie sterse de om, in ordinea stergerii."""
	try:
		with open(_caleSterse(), "r", encoding="utf-8") as f:
			date = json.load(f)
	except (OSError, ValueError):
		return []
	ids = date.get("sterse") if isinstance(date, dict) else None
	if not isinstance(ids, list):
		return []
	rez = []
	for i in ids:
		if _idBun(i) and i not in rez:
			rez.append(i)
	return rez


def _scrieSterse(ids):
	cale = _caleSterse()
	try:
		if not ids:
			if os.path.exists(cale):
				os.remove(cale)
			return True
		os.makedirs(os.path.dirname(cale), exist_ok=True)
		nou = cale + ".nou"
		with open(nou, "w", encoding="utf-8") as f:
			json.dump({"sterse": ids}, f)
			f.flush()
			try:
				os.fsync(f.fileno())
			except OSError:
				pass
		os.replace(nou, cale)
		return True
	except OSError:
		return False


def _stergeFisiereleGaleriei(id_ecran):
	"""Sterge .mvi si poza mica ale unui ecran din galerie. Intoarce cati octeti s-au eliberat."""
	eliberat = 0
	for dosar, nume in ((CALE_GALERIE, id_ecran + ".mvi"), (CALE_GALERIE_MICI, id_ecran + ".jpg")):
		cale = _inDosar(dosar, nume)
		if cale and os.path.isfile(cale):
			try:
				marime = os.path.getsize(cale)
				os.remove(cale)
				eliberat += marime
			except OSError:
				pass
	return eliberat


def _refuzStergereGalerie(id_ecran, date=None):
	"""De ce nu se poate sterge ecranul din galerie, sau None daca se poate."""
	if date is None:
		date = _citesteDate()
	if id_ecran == date["implicit"]:
		return _t("Ecranul din fabrică nu se șterge: receptorul se întoarce la el când lipsește altul.")
	a = activ()
	if a is not None and a["sursa"] == "galerie" and a["id"] == id_ecran:
		return _t("Acesta este ecranul pus acum. Alege întâi altul, apoi șterge-l.")
	ales = _ales()
	if ales is not None and ales["sursa"] == "galerie" and ales["id"] == id_ecran:
		return _t("Acesta este ecranul ales. Alege întâi altul, apoi șterge-l.")
	return None


def laLoc():
	"""„Pune la loc ecranele șterse”: uita lista. Ce e inca pe disc se vede indata; restul revine cu urmatoarea
	actualizare a pachetului galeriei. Intoarce (bun, mesaj)."""
	ids = sterse()
	if not ids:
		return False, _t("Nu ai șters niciun ecran din galerie.")
	if not _scrieSterse([]):
		return False, _t("Nu am putut scrie lista ecranelor șterse.")
	lipsa = [i for i in ids if caleEcran("galerie", i) is None]
	if lipsa:
		return True, _t("Ecranele șterse revin la următoarea actualizare a imaginii.")
	return True, _t("Ecranele șterse sunt din nou în galerie.")


def activ():
	"""Ce ecran e pus acum, dupa FISIERUL de pe disc, nu doar dupa insemnare: o actualizare de pachet poate inlocui
	backdrop.mvi pe sub noi. Intoarce {'sursa','id'} sau None."""
	a = _ales()
	if a is None:
		# omul n-a ales niciodata: e pus ecranul implicit din pachet, daca fisierul activ chiar e el
		implicit = _citesteDate()["implicit"]
		cale = caleEcran("galerie", implicit)
		if cale is not None and _amprenta(cale) == _amprenta(CALE_ACTIV):
			return {"sursa": "galerie", "id": implicit}
		return None
	cale = caleEcran(a["sursa"], a["id"])
	if cale is None:
		return None
	if _amprenta(cale) != _amprenta(CALE_ACTIV):
		return None  # cineva sau ceva a schimbat ecranul activ: nu spunem „pus acum” despre altul
	return {"sursa": a["sursa"], "id": a["id"]}


def _numeFrumos(id_ecran):
	nume = id_ecran.replace("-", " ").strip()
	return nume[:1].upper() + nume[1:]


def proprii():
	"""Ecranele facute din pozele omului, cel mai nou primul."""
	rezultat = []
	try:
		nume_fisiere = sorted(os.listdir(CALE_PROPRII))
	except OSError:
		return rezultat
	for nume in nume_fisiere:
		if not nume.endswith(".mvi"):
			continue
		id_ecran = nume[:-4]
		if not _idBun(id_ecran):
			continue
		cale = os.path.join(CALE_PROPRII, nume)
		try:
			cand = int(os.path.getmtime(cale))
		except OSError:
			cand = 0
		rezultat.append({
			"id": id_ecran,
			"sursa": "propriu",
			"nume": _numeFrumos(id_ecran),
			"grup": "proprii",
			"are_poza": caleMic("propriu", id_ecran) is not None,
			"cand": cand,
		})
	rezultat.sort(key=lambda x: -x["cand"])
	return rezultat


def lista(limba=None):
	"""Tot ce trebuie ca sa se deseneze ecranul si pagina: grupele care au macar un ecran (o grupa ramasa goala nu
	se arata), ecranele din galerie (fara cele sterse de om), ecranele proprii, ecranul implicit si care e pus acum.
	limba=None: numele in limba interfetei (ecranul de pe televizor); „ro”: numele romanesti (pagina web, care e in
	romana); alt cod: numele din ecrane.json in acea limba, daca il are."""
	date = _citesteDate()
	date_sterse = sterse()
	pus = activ()
	ales = _ales()

	def folosit(sursa, id_ecran):
		return any(x is not None and x["sursa"] == sursa and x["id"] == id_ecran for x in (pus, ales))

	iesire = []
	for e in date["ecrane"]:
		if e["id"] in date_sterse and e["id"] != date["implicit"]:
			continue  # sters de om; fisierul poate fi inca pe disc pana la verificarea de la pornire
		if caleEcran("galerie", e["id"]) is None:
			continue  # scris in lista, dar fisierul nu e instalat: nu-l aratam
		iesire.append({
			"id": e["id"],
			"sursa": "galerie",
			"nume": _t(_ro(e)) if limba is None else _inLimba(e, limba),
			"grup": e.get("grup", ""),
			"are_poza": caleMic("galerie", e["id"]) is not None,
			# se poate sterge: nu ecranul din fabrica, nici cel pus sau ales acum (vezi sterge())
			"se_sterge": e["id"] != date["implicit"] and not folosit("galerie", e["id"]),
		})
	stiute = set(g["id"] for g in date["grupe"])
	for e in iesire:
		if e["grup"] not in stiute:
			e["grup"] = "altele"      # grupa lipsa din lista: ecranul nu dispare, sta la „Altele”
	cu_ecrane = set(e["grup"] for e in iesire)
	iesire_grupe = [{"id": g["id"], "nume": _t(_ro(g)) if limba is None else _inLimba(g, limba)}
		for g in date["grupe"] if g["id"] in cu_ecrane]
	if "altele" in cu_ecrane and "altele" not in stiute:
		iesire_grupe.append({"id": "altele", "nume": "Altele" if limba == "ro" else _t("Altele")})
	mele = proprii()
	for e in mele:
		e["se_sterge"] = not folosit("propriu", e["id"])
	if mele:
		iesire_grupe.append({"id": "proprii", "nume": "Pozele mele" if limba == "ro" else _t("Pozele mele")})
	return {
		"grupe": iesire_grupe,
		"ecrane": iesire,
		"proprii": mele,
		"activ": pus,
		"implicit": date["implicit"],
		"sterse": len([i for i in date_sterse if i != date["implicit"]]),
		"max_octeti": MAX_POZA,
		"max_proprii": MAX_PROPRII,
		"poate_converti": bool(pregatitDeConversie()),
	}


def inlocuitor(id_ecran, date=None):
	"""Ecranul din galerie care ia locul lui id_ecran cand acesta nu mai e instalat (sau l-a sters omul): cel din
	„inlocuiri”, apoi primul din aceeasi grupa, apoi ecranul implicit. Intoarce un id care exista, sau None daca galeria
	lipseste."""
	if date is None:
		date = _citesteDate()
	fara = set(sterse()) - set([date["implicit"]])
	instalate = [e for e in date["ecrane"] if e["id"] not in fara and caleEcran("galerie", e["id"]) is not None]
	ids = [e["id"] for e in instalate]
	if id_ecran in ids:
		return id_ecran
	nou = date["inlocuiri"].get(id_ecran)
	if nou in ids:
		return nou
	# grupa ecranului cerut; daca el nu mai e in lista, grupa ecranului care ii lua locul (sters si el de om)
	grup = None
	for cautat in (id_ecran, nou):
		for e in date["ecrane"]:
			if e["id"] == cautat:
				grup = e.get("grup")
		if grup:
			break
	for e in instalate:
		if grup and e.get("grup") == grup:
			return e["id"]
	if date["implicit"] in ids:
		return date["implicit"]
	return ids[0] if ids else None


# ------------------------------------------------------------------ punerea ecranului
# Un singur zavor pentru tot ce pune un ecran de pornire: ecranul de pe televizor, interfata web, firul de conversie
# al unei poze urcate si verificarea de la pornire pot cere punerea in acelasi timp; fara zavor iesea un backdrop.mvi
# amestecat din doua fisiere.
_ZAVOR_PUNERE = threading.Lock()

# Un cadru I MPEG-2 incepe cu antetul de secventa 00 00 01 B3. Ecranele noastre au zeci de KB; sub 4 KB nu poate fi
# un ecran intreg de 1920x1080.
_INCEPUT_MPEG2 = b"\x00\x00\x01\xb3"
_MARIME_MINIMA = 4096

# PUNEREA NU FACE NIMIC CAT MERGE INTERFATA, IN AFARA DE SCRIEREA FISIERULUI: nu reporneste enigma2, nu cheama si nu
# opreste showiframe (pe u5/u4 el tine HDMI-ul si demux-ul; il porneste enigma2.sh cu backdrop.mvi NUMAI inainte de
# enigma2 si il opreste NUMAI dupa ce enigma2 a iesit, iar el nu tine fisierul deschis), nu scrie in partitia logo.
# Drumul: fisier temporar langa tinta, fsync, citit inapoi si comparat cu ecranul ales (marime si sha256), abia apoi
# os.replace si fsync pe dosar. Ecranul nou se vede la urmatoarea pornire a receptorului. Lucrul se face pe un fir
# separat, si din ecranul de pe televizor, si din web: firul enigma2 nu asteapta dupa memoria flash.


class EroarePunere(OSError):
	"""Copia ecranului nu a iesit identica cu fisierul ales (nu se pune nimic)."""


def _pareEcranBun(cale):
	"""Fisierul chiar e un ecran de pornire? (marime cu sens si antet de secventa MPEG-2)"""
	try:
		if os.path.getsize(cale) < _MARIME_MINIMA:
			return False
		with open(cale, "rb") as f:
			return f.read(4) == _INCEPUT_MPEG2
	except OSError:
		return False


def _rezumat(cale):
	"""sha256 al intregului fisier (ecranele au sute de KB: se citeste in bucati)."""
	h = hashlib.sha256()
	with open(cale, "rb") as f:
		while True:
			bucata = f.read(65536)
			if not bucata:
				break
			h.update(bucata)
	return h.hexdigest()


def _fsyncDosar(dosar):
	"""Numele nou (dupa os.replace) ajunge pe flash abia cu fsync pe dosar. Unde nu se poate (Windows), nimic."""
	try:
		fd = os.open(dosar or ".", os.O_RDONLY)
	except (OSError, AttributeError):
		return
	try:
		os.fsync(fd)
	except OSError:
		pass
	finally:
		os.close(fd)


def _curataRamase(tinta):
	"""Sterge fisierele temporare ramase de la o punere intrerupta (cadere de curent intre copiere si mutare): numai
	cele cu forma noastra, <tinta>.<pid>.<fir>.nou. Se cheama sub _ZAVOR_PUNERE, deci nu atinge o punere in curs din
	acest proces."""
	dosar, nume = os.path.split(tinta)
	tipar = re.compile(r"^%s\.[0-9]+\.[0-9]+\.nou$" % re.escape(nume))
	try:
		nume_fisiere = os.listdir(dosar or ".")
	except OSError:
		return 0
	sterse = 0
	for n in nume_fisiere:
		if tipar.match(n):
			try:
				os.unlink(os.path.join(dosar, n))
				sterse += 1
			except OSError:
				pass
	return sterse


def _copiazaAtomic(sursa, tinta):
	"""sursa -> tinta: temporar langa tinta, fsync, verificare (marime si sha256 egale cu sursa), os.replace, fsync pe
	dosar. La orice esec temporarul se sterge, tinta ramane cum era si se arunca OSError (EroarePunere la verificare)."""
	# nume temporar unic: doua puneri deodata nu mai scriu in acelasi fisier
	nou = "%s.%d.%d.nou" % (tinta, os.getpid(), threading.current_thread().ident or 0)
	try:
		asteptat = _rezumat(sursa)
		marime = os.path.getsize(sursa)
		shutil.copyfile(sursa, nou)
		with open(nou, "rb") as f:
			try:
				os.fsync(f.fileno())
			except OSError:
				pass
		if os.path.getsize(nou) != marime or _rezumat(nou) != asteptat:
			raise EroarePunere(_t("copia nu este identică cu ecranul ales"))
		os.replace(nou, tinta)
	except BaseException:
		try:
			os.unlink(nou)
		except OSError:
			pass
		raise
	_fsyncDosar(os.path.dirname(tinta))


def aplica(sursa, id_ecran):
	"""Pune ecranul ales pe locul ecranului activ. Intoarce (bun, mesaj). Numai scrie fisierul (vezi sus): nu reporneste
	interfata si nu atinge showiframe; ecranul se vede la urmatoarea pornire. Se cheama de pe un fir separat (ecranul
	de pe televizor si web-ul), nu de pe firul enigma2."""
	cale = caleEcran(sursa, id_ecran)
	if cale is None:
		return False, _t("Ecranul cerut nu există.")
	if not _pareEcranBun(cale):
		# un ecran ramas pe jumatate (cadere de curent la conversie, copiere intrerupta) NU ajunge ecran de pornire:
		# receptorul ar porni fara imagine
		return False, _t("Fișierul acelui ecran nu este întreg. Alege altul sau pune-l din nou.")
	with _ZAVOR_PUNERE:
		_curataRamase(CALE_ACTIV)
		try:
			deja = os.path.isfile(CALE_ACTIV) and _rezumat(CALE_ACTIV) == _rezumat(cale)
		except OSError:
			deja = False
		if not deja:
			# acelasi ecran pus din nou nu mai scrie nimic pe flash
			try:
				_copiazaAtomic(cale, CALE_ACTIV)
			except OSError as eroare:
				return False, _t("Nu am putut pune ecranul: %s") % eroare
		_scrieAles(sursa, id_ecran)
	return True, _t("Ecranul de pornire a fost schimbat. Se vede la următoarea pornire a receptorului.")


def _verifica():
	"""Pune din nou ecranul ales, daca fisierul activ nu mai e el (actualizarea pachetului a pus la loc ecranul
	implicit) sau daca ecranul ales a fost scos din galerie (atunci pe cel care ii ia locul). Intoarce
	(ce s-a facut, sursa, id) pentru jurnal; nimic nu se scrie cand ecranul pus e deja cel bun."""
	# ecranele sterse de om si aduse inapoi de o actualizare a pachetului se sterg din nou (fara cel implicit si fara
	# cel ales, care nu se pot sterge oricum)
	a = _ales()
	implicit_ = implicit()
	for id_sters in sterse():
		if id_sters != implicit_ and not (a is not None and a["sursa"] == "galerie" and a["id"] == id_sters):
			if _stergeFisiereleGaleriei(id_sters):
				print("[HdsEcranePornire] la pornire: sters din nou galerie/%s" % id_sters)
	if a is None:
		return "nimic", None, None       # omul n-a ales niciodata: ramane ecranul implicit din pachet
	sursa, id_ecran = a["sursa"], a["id"]
	if caleEcran(sursa, id_ecran) is None:
		if sursa == "galerie":
			nou = inlocuitor(id_ecran)
		else:
			nou = _citesteDate()["implicit"]    # poza proprie stearsa de pe disc: ecranul implicit
		if nou is None or caleEcran("galerie", nou) is None:
			return "fara-galerie", sursa, id_ecran
		bun, _mesaj = aplica("galerie", nou)
		return ("inlocuit" if bun else "esuat"), "galerie", nou
	if _amprenta(caleEcran(sursa, id_ecran)) == _amprenta(CALE_ACTIV):
		return "la-zi", sursa, id_ecran
	bun, _mesaj = aplica(sursa, id_ecran)
	return ("pus-din-nou" if bun else "esuat"), sursa, id_ecran


def verificaLaPornire():
	"""Chemata o data la pornirea interfetei: _verifica() pe un fir separat (citirea si, rar, scrierea pe flash nu tin
	firul enigma2). Nu arunca: pornirea receptorului nu depinde de ea."""
	def fir():
		try:
			ce, sursa, id_ecran = _verifica()
			if ce not in ("nimic", "la-zi"):
				print("[HdsEcranePornire] la pornire: %s %s/%s" % (ce, sursa, id_ecran))
		except Exception as eroare:
			print("[HdsEcranePornire] verificarea de la pornire: %s" % eroare)
	t = threading.Thread(target=fir, name="HdsEcranePornire")
	t.daemon = True
	t.start()
	return t


def sterge(id_ecran, sursa=None):
	"""Sterge un ecran propriu sau unul din galerie. Fara sursa: poza proprie cu acest id, daca exista, altfel ecranul
	din galerie. Nu se sterg ecranul din fabrica si ecranul pus sau ales acum. Intoarce (bun, mesaj)."""
	if not _idBun(id_ecran) or sursa not in (None,) + SURSE:
		return False, _t("Ecranul cerut nu există.")
	if sursa is None:
		sursa = "propriu" if caleEcran("propriu", id_ecran) is not None else "galerie"
	if sursa == "galerie":
		return _stergeDinGalerie(id_ecran)
	if caleEcran("propriu", id_ecran) is None:
		return False, _t("Ecranul cerut nu există.")
	a = activ()
	if a is not None and a["sursa"] == "propriu" and a["id"] == id_ecran:
		return False, _t("Acesta este ecranul pus acum. Alege întâi altul, apoi șterge-l.")
	ales = _ales()
	if ales is not None and ales["sursa"] == "propriu" and ales["id"] == id_ecran:
		return False, _t("Acesta este ecranul ales. Alege întâi altul, apoi șterge-l.")
	sterse = 0
	for nume in (id_ecran + ".mvi", id_ecran + "-mic.jpg", id_ecran + ".jpg", id_ecran + ".png"):
		cale = _inDosar(CALE_PROPRII, nume)
		if cale and os.path.isfile(cale):
			try:
				os.remove(cale)
				sterse += 1
			except OSError:
				pass
	return (sterse > 0), (_t("Ecranul a fost șters.") if sterse else _t("Nu am putut șterge ecranul."))


def _stergeDinGalerie(id_ecran):
	"""Sterge un ecran din galerie: fisierele de pe disc si id-ul tinut minte (vezi regula 6 de sus)."""
	date = _citesteDate()
	if not any(e["id"] == id_ecran for e in date["ecrane"]) or id_ecran in sterse():
		return False, _t("Ecranul cerut nu există.")
	refuz = _refuzStergereGalerie(id_ecran, date)
	if refuz:
		return False, refuz
	ids = sterse() + [id_ecran]
	if not _scrieSterse(ids):
		return False, _t("Nu am putut șterge ecranul.")
	_stergeFisiereleGaleriei(id_ecran)
	return True, _t("Ecranul a fost șters din galerie. „Pune la loc ecranele șterse” îl aduce înapoi.")


# ------------------------------------------------------------------ poza omului: verificari
def felPoza(octeti):
	"""Ce fel de poza e, DUPA CONTINUT, nu dupa numele fisierului. 'jpg', 'png' sau None."""
	if not octeti or len(octeti) < MIN_POZA:
		return None
	if octeti[:3] == b"\xff\xd8\xff":
		return "jpg"
	if octeti[:8] == b"\x89PNG\r\n\x1a\n":
		return "png"
	return None


def masuraPoza(octeti, fel):
	"""(latime, inaltime) citite din ANTETUL pozei, fara sa o decodam. None daca nu se pot citi."""
	try:
		if fel == "png":
			if octeti[12:16] != b"IHDR":
				return None
			latime, inaltime = struct.unpack(">II", octeti[16:24])
			return int(latime), int(inaltime)
		if fel == "jpg":
			# Se cheama pe firul reactorului (web), deci pasii sunt numarati: octetii de umplutura se sar cu find()
			# (in C), iar dupa MAX_PASI_JPEG marcaje fara SOF poza e socotita stricata. O poza adevarata are cateva
			# zeci de marcaje inainte de SOF; 2000 de pasi tin cel mult cateva milisecunde.
			i = 2
			n = len(octeti)
			pasi = 0
			while i + 9 < n:
				pasi += 1
				if pasi > MAX_PASI_JPEG:
					return None
				if octeti[i] != 0xFF:
					i = octeti.find(b"\xff", i)
					if i < 0:
						return None
					continue
				marcaj = octeti[i + 1]
				if marcaj == 0xFF:
					i += 1  # octeti de umplutura intre marcaje
					continue
				if marcaj == 0x01 or 0xD0 <= marcaj <= 0xD8:
					i += 2  # marcaje fara continut
					continue
				if marcaj in (0xD9, 0xDA):
					return None  # am ajuns la datele imaginii fara sa gasim marimea
				if marcaj == 0x00:
					i += 2  # FF00: octet de umplutura in datele imaginii, nu un marcaj (ca in libjpeg)
					continue
				lungime = struct.unpack(">H", octeti[i + 2:i + 4])[0]
				if lungime < 2:
					return None
				# SOF0..SOF15 poarta marimea; C4 (tabele Huffman), C8 si CC nu sunt SOF
				if 0xC0 <= marcaj <= 0xCF and marcaj not in (0xC4, 0xC8, 0xCC):
					inaltime, latime = struct.unpack(">HH", octeti[i + 5:i + 9])
					return int(latime), int(inaltime)
				i += 2 + lungime
			return None
	except (struct.error, IndexError):
		return None
	return None


def verificaPoza(octeti):
	"""Toate verificarile pe octetii primiti din retea. (fel, latime, inaltime, mesaj_eroare)."""
	if not octeti or len(octeti) < MIN_POZA:
		return None, 0, 0, _t("Fișierul este gol sau prea mic pentru o poză.")
	if len(octeti) > MAX_POZA:
		return None, 0, 0, _t("Poza este prea mare (peste %d MB).") % (MAX_POZA // (1024 * 1024))
	fel = felPoza(octeti)
	if fel is None:
		return None, 0, 0, _t("Fișierul nu este o poză JPG sau PNG.")
	masura = masuraPoza(octeti, fel)
	if masura is None:
		return None, 0, 0, _t("Poza pare stricată: nu i se poate citi mărimea.")
	latime, inaltime = masura
	if latime < 16 or inaltime < 16:
		return None, 0, 0, _t("Poza este prea mică (cel puțin 16x16 puncte).")
	if latime > MAX_LATURA or inaltime > MAX_LATURA:
		return None, 0, 0, _t("Poza are laturile prea mari (cel mult %d puncte).") % MAX_LATURA
	return fel, latime, inaltime, ""


def _spatiuLiber(dosar):
	try:
		s = os.statvfs(dosar)
		return s.f_bavail * s.f_frsize
	except (OSError, AttributeError, ValueError):
		return None


def _taieLaCuvant(id_ecran, n):
	"""id-ul de cel mult n semne, taiat la ultimul cuvant intreg: numele se vede pe ecran („poza-de-la-nunta”, nu
	„poza-de-la-nunta-verisoa”). Un singur cuvant mai lung de n semne se taie oricum."""
	if len(id_ecran) <= n:
		return id_ecran
	taiat = id_ecran[:n + 1]
	if "-" in taiat:
		return taiat[:taiat.rfind("-")].strip("-")
	return id_ecran[:n]


def _idLiber(nume_cerut):
	"""Un identificator numai din [a-z0-9-], plecand de la numele fisierului dat de om. Numele primit din retea NU
	ajunge niciodata intr-o cale asa cum a venit."""
	baza = os.path.basename((nume_cerut or "").replace("\\", "/"))
	baza = os.path.splitext(baza)[0].lower()
	for semn, inlocuitor_ in (("ă", "a"), ("â", "a"), ("î", "i"), ("ș", "s"), ("ş", "s"), ("ț", "t"), ("ţ", "t")):
		baza = baza.replace(semn, inlocuitor_)
	baza = _taieLaCuvant(re.sub(r"[^a-z0-9]+", "-", baza).strip("-"), 24)
	if not baza or not _idBun(baza):
		baza = "poza"
	candidat = baza
	n = 1
	while os.path.exists(os.path.join(CALE_PROPRII, candidat + ".mvi")):
		n += 1
		candidat = "%s-%d" % (_taieLaCuvant(baza, 20) or "poza", n)
		if not _idBun(candidat):
			candidat = "poza-%d" % n
		if n > 999:
			return None
	return candidat


# ------------------------------------------------------------------ convertorul de pe receptor
# Poza omului se face ecran de pornire NUMAI prin codorul nostru MPEG-2 (Components/HdsCodorMpeg2.py ->
# lib/gdi/ecranpornire.cpp). Acela citeste marimea din antetul pozei si opreste pozele prea mari INAINTE de a cere
# memorie, verifica din nou marimea dupa decodare, decodeaza cu libjpeg/libpng si aduce poza la 1920x1080 fara
# deformare, fara niciun text scris in ea.
# NU se trece la gst-launch-1.0, mpeg2enc sau ffmpeg: acele unelte nu au nicio poarta de marime, iar cu enigma2
# compilat cu -fno-exceptions (configure.ac) o alocare cazuta nu se poate prinde, ci opreste receptorul fara niciun
# mesaj. Codorul nostru e singurul drum; daca el refuza poza, omul primeste un mesaj limpede (HdsCodorMpeg2.MESAJE).


def _unealta(nume):
	for dosar in ("/usr/bin", "/bin", "/usr/sbin", "/sbin", "/usr/local/bin"):
		cale = os.path.join(dosar, nume)
		if os.path.isfile(cale) and os.access(cale, os.X_OK):
			return cale
	return None


def pregatitDeConversie():
	"""Numele codorului care face conversia, sau '' daca nu e in imagine (nu ar trebui sa se intample: HdsCodorMpeg2
	face parte din imagine). Aratat si in pagina web (poate_converti)."""
	try:
		from Components.HdsCodorMpeg2 import faceEcranPornire  # noqa: F401
	except Exception:
		return ""
	return "HdsCodorMpeg2"


def _sterge(cale):
	try:
		os.remove(cale)
	except OSError:
		pass


def _ruleaza(comanda, timeout_s=120, intrare=None):
	p = subprocess.run(comanda, input=intrare, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout_s)
	return p.returncode, p.stdout, (p.stderr or b"").decode("utf-8", "replace")[-400:]


def converteste(cale_poza, cale_mvi):
	"""Poza omului -> cadru I MPEG-2 (1920x1080), fara niciun text scris in ea (randul cu siturile si versiunea il
	scrie interfata peste poza, la pornire). (bun, mesaj, unealta_folosita). Scrie intai in .nou, apoi os.replace."""
	nou = cale_mvi + ".nou"
	eroare_codor = _t("Receptorul nu poate transforma poza în ecran de pornire (%s).")
	try:
		from Components.HdsCodorMpeg2 import faceEcranPornire
	except Exception as eroare:
		return False, eroare_codor % eroare, ""
	try:
		iesit = faceEcranPornire(cale_poza, nou, "")
	except Exception as eroare:
		_sterge(nou)
		return False, eroare_codor % eroare, ""
	if iesit is not False and os.path.isfile(nou) and os.path.getsize(nou) > 1024:
		os.replace(nou, cale_mvi)
		return True, "", "HdsCodorMpeg2.faceEcranPornire"
	_sterge(nou)
	return False, eroare_codor % _t("codorul nu a scris fișierul"), ""


def _facePozaMica(cale_poza, cale_mica):
	"""Previzualizarea mica pentru pagina web si pentru ecranul de pe televizor (480x270 JPG). Daca nu se poate, nu e
	o problema: se arata un chenar gol. Se incearca doar cu ce exista deja pe receptor."""
	gst = _unealta("gst-launch-1.0")
	if not gst:
		return False
	nou = cale_mica + ".nou"
	try:
		cod, _iesire, _eroare = _ruleaza([
			gst, "-q", "filesrc", "location=" + cale_poza, "!", "decodebin", "!",
			"videoconvert", "!", "videoscale", "add-borders=true", "!",
			"video/x-raw,format=I420,width=480,height=270", "!",
			"jpegenc", "quality=75", "!", "filesink", "location=" + nou,
		], timeout_s=60)
		if cod == 0 and os.path.isfile(nou) and os.path.getsize(nou) > 512:
			os.replace(nou, cale_mica)
			return True
	except (OSError, subprocess.SubprocessError):
		pass
	_sterge(nou)
	return False


# ------------------------------------------------------------------ poza omului: tot drumul
def primestePoza(octeti, nume_cerut="", aplica_acum=True):
	"""Verifica octetii primiti, ii scrie in dosarul ecranelor proprii, converteste si (daca se cere) pune ecranul.
	NICIODATA nu scrie octetii primiti peste ecranul activ."""
	fel, latime, inaltime, eroare = verificaPoza(octeti)
	if fel is None:
		return {"result": False, "message": eroare}
	try:
		os.makedirs(CALE_PROPRII, exist_ok=True)
	except OSError as e:
		return {"result": False, "message": _t("Nu am putut pregăti dosarul ecranelor: %s") % e}
	liber = _spatiuLiber(CALE_PROPRII)
	if liber is not None and liber < MIN_SPATIU_LIBER:
		return {"result": False, "message": _t("Nu mai este loc în memoria receptorului. Șterge un ecran propriu.")}
	if len(proprii()) >= MAX_PROPRII:
		return {"result": False,
			"message": _t("Ai deja %d ecrane proprii. Șterge unul înainte de a pune altul.") % MAX_PROPRII}
	if not pregatitDeConversie():
		return {"result": False,
			"message": _t("Receptorul nu are încă unealta care face ecranul de pornire dintr-o poză.")}

	id_ecran = _idLiber(nume_cerut)
	if id_ecran is None:
		return {"result": False, "message": _t("Nu am putut alege un nume pentru ecran.")}
	cale_poza = os.path.join(CALE_PROPRII, id_ecran + "." + fel)
	cale_mvi = os.path.join(CALE_PROPRII, id_ecran + ".mvi")
	cale_mica = os.path.join(CALE_PROPRII, id_ecran + "-mic.jpg")
	try:
		nou = cale_poza + ".nou"
		with open(nou, "wb") as f:
			f.write(octeti)
			f.flush()
			os.fsync(f.fileno())
		os.replace(nou, cale_poza)
	except OSError as e:
		return {"result": False, "message": _t("Nu am putut salva poza: %s") % e}

	bun, mesaj, unealta = converteste(cale_poza, cale_mvi)
	if not bun:
		_sterge(cale_poza)
		return {"result": False, "message": mesaj}

	_facePozaMica(cale_poza, cale_mica)
	try:
		if os.path.getsize(cale_poza) > MAX_POZA_PASTRATA:
			# Poza sursa mare NU se tine pe flash, nici daca previzualizarea nu s-a putut face: altfel sase poze de
			# cate 8 MB ar ocupa 48 MB de rootfs (exact ce pazeste MIN_SPATIU_LIBER), iar pagina ar trimite spre
			# telefon poza intreaga drept „previzualizare”. Fara previzualizare, chenarul arata „fara previzualizare”.
			_sterge(cale_poza)
	except OSError:
		pass

	raspuns = {
		"result": True,
		"id": id_ecran,
		"sursa": "propriu",
		"latime": latime,
		"inaltime": inaltime,
		"unealta": unealta,
		"message": _t("Poza a fost pregătită ca ecran de pornire."),
	}
	if aplica_acum:
		pus, mesaj_pus = aplica("propriu", id_ecran)
		raspuns["pus"] = pus
		raspuns["message"] = mesaj_pus if pus else (
			_t("Poza a fost pregătită, dar nu am putut pune ecranul: %s") % mesaj_pus)
	return raspuns
