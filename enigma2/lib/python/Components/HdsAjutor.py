# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAjutor.py: ajutorul receptorului, fara internet si fara poze (din 0.6.8). Aceleasi pagini ca ajutorul online
# (stb.hdsatelit.com/ajutor), numai textul, in romana si in engleza; celelalte limbi ale interfetei vad paginile in
# engleza, cu textele din jurul lor (titluri, butoane, numele partilor) in limba lor.
#
# Datele vin in pachetul hdsatelit-ajutor (separat de enigma2, se actualizeaza prin feed cand se schimba textele), in
# DOSAR: index.json (capitolele, paginile, tabelul ecran -> pagina, textele din jur in cele 13 limbi), <limba>.dat
# (paginile, fiecare comprimata separat cu dictionarul de la inceputul fisierului; locul ei in index.json) si
# cauta-<limba>.dat (cuvintele fiecarei pagini, pentru cautare). Le scrie unealta
# hdsatelit-unelte/situl-imaginii/unelte/fa_ajutor_receptor.py din aceeasi sursa ca site-ul. Fara pachet, ecranele
# spun ca ajutorul nu e instalat (TEXT_LIPSA) si nimic altceva nu se schimba.
#
# Folosesc modulul: tasta HELP pe orice ecran (porneste(), din mytest.py: o legare globala a tastelor, cu prioritatea
# imediat dupa navigator si HbbTV, care o primesc intai cat sunt pe ecran), ecranele Screens/HdsAjutor.py („Ajutor” din
# meniul principal: capitolele, paginile, cautarea) si pagina web /ajutor (HdsWebControl/ajutor_web.py).
#
# Ecranul -> pagina (pagina_ecranului): numele clasei ecranului si ale bazelor ei, cheia setup.xml a ecranului Setup,
# intrarea de meniu care l-a deschis (meniul de dedesubt are cursorul pe ea), argumentul cu care s-a deschis (felul
# scanarii, repornirea, ghidul multiplu), cheia submeniului; rezerva: pagina meniului de dedesubt, apoi cuprinsul.
#
# Nimic nu se incarca pana la prima folosire (fara cost la pornire, la zap sau in meniu); fisierul nu importa nimic
# din enigma2 la incarcare, deci merge si in probele de pe PC.

import io
import json
import os
import zlib

DOSAR = "/usr/share/hdsatelit-ajutor"
# imediat dupa -0x7FFFFFFF (navigatorul, HbbTV, culegerea canalelor si captura le leaga acolo si iau tastele cat
# sunt pe ecran), inaintea oricarei harti de taste a ecranelor
PRIORITATE_TASTE = -0x7FFFFFFE
KEY_HELP = 138
FLAG_MAKE = 0
CAUTARE_MAXIM = 60
LIMBI_TEXT_IMPLICIT = ("ro", "en")

# ecranele peste care HELP nu deschide nimic: receptorul e in standby (televizorul poate fi stins)
FARA_AJUTOR = ("Standby", "StandbySummary")

# mesajul de pe ecran cand pachetul ajutorului lipseste (index.json are textele, dar aici nu e niciun index)
TEXT_LIPSA = {
	"ro": "Ajutorul nu e instalat pe acest receptor. Îl aduce actualizarea software.",
	"en": "The help is not installed on this receiver. A software update brings it.",
	"de": "Die Hilfe ist auf diesem Receiver nicht installiert. Ein Software-Update bringt sie.",
	"fr": "L'aide n'est pas installée sur ce récepteur. Une mise à jour logicielle l'apporte.",
	"es": "La ayuda no está instalada en este receptor. Una actualización de software la trae.",
	"it": "L'aiuto non è installato su questo ricevitore. Lo porta un aggiornamento software.",
	"hu": "A súgó nincs telepítve ezen a vevőn. Egy szoftverfrissítés hozza.",
	"cs": "Nápověda není v tomto přijímači nainstalována. Přinese ji aktualizace softwaru.",
	"pl": "Pomoc nie jest zainstalowana w tym odbiorniku. Przyniesie ją aktualizacja oprogramowania.",
	"pt": "A ajuda não está instalada neste recetor. Uma atualização de software trá-la.",
	"nl": "De help is niet geïnstalleerd op deze ontvanger. Een software-update brengt hem.",
	"ru": "Справка не установлена на этом приёмнике. Её принесёт обновление программ.",
	"tr": "Yardım bu alıcıda kurulu değil. Bir yazılım güncellemesi getirir.",
}
# textele din jur cand index.json nu le are (pachet mai vechi decat codul)
TEXTE_REZERVA = {
	"ro": {"ajutor": "Ajutor", "inchide": "Închide", "cuprins": "Cuprins", "cauta": "Caută"},
	"en": {"ajutor": "Help", "inchide": "Close", "cuprins": "Contents", "cauta": "Search"},
}


def _jurnal(text):
	print("[HdsAjutor] %s" % text)


# ------------------------------------------------------------------ textul de cautare
# ACEEASI functie ca fa_ajutor_receptor.py normalizeaza (proba le compara): litere mici, fara diacritice, orice alt semn
# decat litere si cifre devine spatiu. Fara unicodedata (pachet separat in imagine).
_FARA_SEMNE = {}
for _din, _in in (("ăâáàäãåā", "a"), ("îíìïī", "i"), ("șşśš", "s"), ("țţť", "t"), ("éèëêěē", "e"), ("óòöôõőø", "o"),
		("úùüûůűū", "u"), ("çćč", "c"), ("ñńň", "n"), ("ýÿ", "y"), ("žźż", "z"), ("ř", "r"), ("ď", "d"), ("ğ", "g"),
		("ł", "l"), ("ı", "i"), ("ß", "ss")):
	for _c in _din:
		_FARA_SEMNE[ord(_c)] = _in


def normalizeaza(text):
	t = (text or "").lower().translate(_FARA_SEMNE)
	return " ".join("".join(c if c.isalnum() else " " for c in t).split())


# ------------------------------------------------------------------ datele
_tinut = {"dosar": None, "semn": None, "index": None, "dictionare": {}}


def dosar():
	return DOSAR


def _semn(cale):
	try:
		s = os.stat(cale)
		return (s.st_mtime, s.st_size)
	except OSError:
		return None


def index():
	"""index.json al pachetului (tinut in memorie cat nu se schimba fisierul), sau None cand pachetul lipseste ori
	fisierul e stricat"""
	cale = os.path.join(dosar(), "index.json")
	semn = _semn(cale)
	if semn is None:
		_tinut.update(dosar=None, semn=None, index=None, dictionare={})
		return None
	if _tinut["semn"] == semn and _tinut["dosar"] == dosar() and _tinut["index"] is not None:
		return _tinut["index"]
	try:
		with io.open(cale, encoding="utf-8") as f:
			idx = json.load(f)
		if not isinstance(idx, dict) or not idx.get("pagini") or not idx.get("capitole"):
			raise ValueError("index fara pagini")
	except Exception as e:
		_jurnal("index.json: %s" % e)
		idx = None
	_tinut.update(dosar=dosar(), semn=semn, index=idx, dictionare={})
	return idx


def instalat():
	return index() is not None


def versiune():
	idx = index()
	return (idx or {}).get("versiune") or ""


def limba_interfetei():
	"""codul de doua litere al limbii interfetei („ro”, „en”, „de” ...), „ro” cand nu se poate afla"""
	try:
		from Components.Language import language
		cod = (language.getLanguage() or "").split("_")[0].lower()
	except Exception:
		cod = ""
	return cod or "ro"


def limba_ui(limba=None):
	"""limba textelor din jur: limba interfetei daca e una dintre cele 13, altfel engleza"""
	limba = limba or limba_interfetei()
	idx = index() or {}
	if limba in (idx.get("limbi") or TEXT_LIPSA):
		return limba
	return "en"


def limba_text(limba=None):
	"""limba paginilor: a interfetei cand paginile o au (romana, engleza), altfel engleza"""
	limba = limba or limba_interfetei()
	idx = index() or {}
	limbi = idx.get("limbi_text") or LIMBI_TEXT_IMPLICIT
	return limba if limba in limbi else ("en" if "en" in limbi else limbi[0])


def in_engleza(limba=None):
	"""True cand paginile se arata in alta limba decat a interfetei"""
	limba = limba or limba_interfetei()
	return limba_text(limba) != limba


def text(cheie, limba=None):
	"""un text din jurul paginilor, in limba interfetei (rezerva: engleza, apoi romana, apoi cheia)"""
	limba = limba_ui(limba)
	if cheie == "lipsa":
		return TEXT_LIPSA.get(limba) or TEXT_LIPSA["en"]
	texte = (index() or {}).get("texte") or {}
	for L in (limba, "en", "ro"):
		t = (texte.get(L) or {}).get(cheie) or (TEXTE_REZERVA.get(L) or {}).get(cheie)
		if t:
			return t
	return cheie


def capitole(limba=None):
	"""[{"i", "cod", "adresa", "titlu", "pagini": [index]}] in ordinea capitolelor; paginile dupa titlu, ca pe site"""
	idx = index()
	if not idx:
		return []
	L = limba_text(limba)
	rez = []
	for i, c in enumerate(idx["capitole"]):
		pagini = sorted(c.get("pagini") or [], key=lambda p: (titlu_pagina(p, L) or "").lower())
		rez.append({"i": i, "cod": c.get("cod") or "", "adresa": c.get("adresa") or "",
			"titlu": (c.get("t") or {}).get(L) or (c.get("t") or {}).get("ro") or "", "pagini": pagini})
	return rez


def numar_pagini():
	return len((index() or {}).get("pagini") or [])


def _pagina_index(i):
	idx = index()
	if not idx or not isinstance(i, int) or not 0 <= i < len(idx["pagini"]):
		return None
	return idx["pagini"][i]


def titlu_pagina(i, limba=None):
	p = _pagina_index(i)
	if p is None:
		return ""
	L = limba_text(limba) if limba not in ("ro", "en") else limba
	return (p.get("t") or {}).get(L) or (p.get("t") or {}).get("ro") or ""


def capitol_pagina(i):
	p = _pagina_index(i)
	return p.get("cap") if p else None


def cheie_pagina(i):
	"""„capitol/pagina”, ca adresa paginii pe site"""
	p = _pagina_index(i)
	return p.get("c") if p else None


def index_cheie(cheie):
	idx = index()
	if not idx or not cheie:
		return None
	cheie = cheie.strip("/")
	for i, p in enumerate(idx["pagini"]):
		if p.get("c") == cheie:
			return i
	return None


def cai_web(i):
	p = _pagina_index(i)
	return list(p.get("web") or []) if p else []


def adresa_online(i, limba=None):
	"""adresa paginii pe site (cu poze), in limba paginilor"""
	idx = index() or {}
	ch = cheie_pagina(i)
	if not ch:
		return ""
	site = (idx.get("site") or "https://stb.hdsatelit.com").rstrip("/")
	return "%s%s/ajutor/%s/" % (site, "" if limba_text(limba) == "ro" else "/en", ch)


def _dictionar(L):
	idx = index()
	if L in _tinut["dictionare"]:
		return _tinut["dictionare"][L]
	loc = (idx.get("dictionar") or {}).get(L) or [0, 0]
	zd = b""
	if loc[1]:
		with open(os.path.join(dosar(), "%s.dat" % L), "rb") as f:
			f.seek(loc[0])
			zd = f.read(loc[1])
	_tinut["dictionare"][L] = zd
	return zd


def pagina(i, limba=None):
	"""Textul unei pagini: {"t": titlu, "p": [[parte, [element]]]}, sau None. Elementele, dupa parte (ultimul camp e
	pagina legata sau -1):
	  la_ce_foloseste, cum_ajungi, ce_vezi, diferente_receptoare, legat_de: [text, legatura]
	  randuri:    [nume, valori, din_fabrica, ce_face, cand_o_schimbi, legatura]
	  taste:      [tasta, ce_face, legatura]
	  pas_cu_pas: [titlu, [pasi], legatura]
	  probleme:   [problema, solutie, legatura]
	Se citeste numai pagina ceruta (locul ei din index.json), nimic tinut in memorie."""
	p = _pagina_index(i)
	if p is None:
		return None
	L = limba_text(limba) if limba not in ("ro", "en") else limba
	loc = (p.get("poz") or {}).get(L)
	if not loc:
		return None
	try:
		zd = _dictionar(L)
		with open(os.path.join(dosar(), "%s.dat" % L), "rb") as f:
			f.seek(loc[0])
			b = f.read(loc[1])
		d = zlib.decompressobj(zlib.MAX_WBITS, zd) if zd else zlib.decompressobj()
		pg = json.loads((d.decompress(b) + d.flush()).decode("utf-8"))
		if not isinstance(pg, dict) or not isinstance(pg.get("p"), list):
			raise ValueError("pagina fara parti")
		return pg
	except Exception as e:
		_jurnal("pagina %s (%s): %s" % (i, L, e))
		return None


def legaturi(pg):
	"""paginile legate dintr-o pagina, in ordinea in care apar, fara repetari"""
	rez = []
	for _parte, elemente in (pg or {}).get("p") or []:
		for e in elemente:
			if isinstance(e, list) and e and isinstance(e[-1], int) and e[-1] >= 0 and e[-1] not in rez:
				rez.append(e[-1])
	return rez


def cauta(intrebare, limba=None, maxim=CAUTARE_MAXIM):
	"""Paginile care au toate cuvintele intrebarii (fiecare ca inceput de cuvant, fara diacritice): [index], cele cu
	cuvintele in titlu intai, apoi dupa cate cuvinte se potrivesc intreg. Cuvintele de o litera nu se cauta (in afara
	cifrelor)."""
	idx = index()
	cuvinte = [w for w in normalizeaza(intrebare).split() if len(w) > 1 or w.isdigit()]
	if not idx or not cuvinte:
		return []
	L = limba_text(limba) if limba not in ("ro", "en") else limba
	try:
		with open(os.path.join(dosar(), "cauta-%s.dat" % L), "rb") as f:
			text_cautare = zlib.decompress(f.read()).decode("utf-8")
	except Exception as e:
		_jurnal("cautarea (%s): %s" % (L, e))
		return []
	gasite = []
	for rand in text_cautare.split("\n"):
		parti = rand.split("\t")
		if len(parti) != 3 or not parti[0].isdigit():
			continue
		titlu, corp = " " + parti[1] + " ", " " + parti[2] + " "
		scor = 0
		for w in cuvinte:
			in_titlu = (" " + w) in titlu
			in_corp = (" " + w) in corp
			if not in_titlu and not in_corp:
				scor = None
				break
			scor += (10 if in_titlu else 0) + (2 if (" " + w + " ") in corp or (" " + w + " ") in titlu else 1)
		if scor is not None:
			gasite.append((-scor, int(parti[0])))
	gasite.sort()
	return [i for _s, i in gasite[:maxim]]


# ------------------------------------------------------------------ ecranul -> pagina
def _clase(obj):
	try:
		return [c.__name__ for c in type(obj).__mro__]
	except Exception:
		return []


def _intrare_meniu(dialog):
	"""entryID-ul intrarii pe care sta cursorul unui ecran Menu (Screens/Menu.py), sau None"""
	if dialog is None or "Menu" not in _clase(dialog):
		return None
	try:
		x = dialog._intrareCurenta()
		return x[2] if x else None
	except Exception:
		return None


def _pagina_meniu(dialog, e):
	"""pagina unui ecran Menu: submeniul dupa cheia lui, meniul principal dupa clasa"""
	nume = _clase(dialog)
	if "Menu" not in nume:
		return None
	nod = getattr(dialog, "parentNode", None)
	cheie = nod.get("key") if nod is not None and hasattr(nod, "get") else None
	if "MainMenu" in nume or cheie == "mainmenu":
		lista = (e.get("clase") or {}).get("MainMenu") or []
		return lista[0] if lista else None
	return (e.get("meniuri") or {}).get(cheie)


def pagina_ecranului(dialog, dedesubt=()):
	"""Pagina de ajutor a ecranului `dialog` (indexul ei) sau None (atunci: cuprinsul). `dedesubt` = ecranele de sub
	el, de la cel mai apropiat (session.dialog_stack intors)."""
	idx = index()
	if not idx or dialog is None:
		return None
	e = idx.get("ecrane") or {}
	dedesubt = list(dedesubt or ())
	# bara a doua (ecran fara stiva, pus de bara de canale): cand e pe ecran, pagina ei
	a_doua = getattr(dialog, "secondInfoBarScreen", None)
	if a_doua is not None and getattr(a_doua, "shown", False):
		dedesubt.insert(0, dialog)
		dialog = a_doua
	nume = _clase(dialog)
	if "Menu" in nume:
		i = _pagina_meniu(dialog, e)
		if i is not None:
			return i
	if "Setup" in nume:
		i = (e.get("setup") or {}).get(getattr(dialog, "setup", None))
		if i is not None:
			return i
	intrare = _intrare_meniu(dedesubt[0]) if dedesubt else None
	din_meniu = (e.get("intrari") or {}).get(intrare) if intrare else None
	clase = e.get("clase") or {}
	for n in nume:
		lista = clase.get(n)
		if not lista:
			continue
		if len(lista) == 1:
			return lista[0]
		arg = (e.get("argumente") or {}).get(n)
		if arg:
			v = getattr(dialog, arg[0], None)
			if v is not None and ("%s" % v) in arg[1]:
				return arg[1]["%s" % v]
		if din_meniu in lista:
			return din_meniu
		return lista[0]
	if din_meniu is not None:
		return din_meniu
	# rezerva: pagina celui mai apropiat meniu de dedesubt care are pagina (randurile lui descriu si ecranul acesta)
	for d in dedesubt:
		i = _pagina_meniu(d, e)
		if i is not None:
			return i
	return None


# ------------------------------------------------------------------ tasta HELP
class _Tasta(object):
	"""Legarea globala a tastei HELP: pe orice ecran deschide pagina lui de ajutor (Screens/HdsAjutor.py)."""

	def __init__(self, session):
		self.session = session
		self.prinsa = False

	def __call__(self, cod, steag):
		if cod != KEY_HELP:
			return 0
		if steag != FLAG_MAKE:
			# ridicarea si repetarea tastei apasate de noi nu mai merg la ecranele de dedesubt
			return 1 if self.prinsa else 0
		self.prinsa = False
		try:
			s = self.session
			d = s.current_dialog
			nume = _clase(d)
			if d is None or any(n in FARA_AJUTOR for n in nume):
				return 0
			if any(n.startswith("HdsAjutor") for n in nume):
				return 0
			dedesubt = [x[0] for x in reversed(getattr(s, "dialog_stack", None) or [])]
			from Screens.HdsAjutor import deschideDinEcran
			deschideDinEcran(s, d, dedesubt)
			self.prinsa = True
			return 1
		except Exception as e:
			_jurnal("tasta HELP: %s" % e)
			return 0


_legata = [None]


def porneste(session):
	"""Leaga tasta HELP pentru toate ecranele (o data, din mytest.py). Nu citeste nimic de pe disc."""
	if _legata[0] is not None:
		return
	from enigma import eActionMap
	t = _Tasta(session)
	eActionMap.getInstance().bindAction("", PRIORITATE_TASTE, t)
	_legata[0] = t
