# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsForumReceptor.py: forumul modelului pe receptor (ecranele din Screens/HdsForumReceptor.py si pagina web
# /forum-receptor). Clientul rutelor forumului pentru receptoare (SERVER_FORUM: subiect, poza, mesaj) si al jetonului de
# forum de la serverul testerilor (forum-jeton, cu identificatorul si cheia profilului din Components/HdsBetaTester.py).
#
# - citeste(inainte=None): subiectul modelului, cel mult 20 de mesaje; cu jetonul (numai beta testerii inscrisi) vin si
#   mesajele lui care asteapta moderatorul si dreptul de scriere. Fara jeton (vizitator, sau jetonul refuzat) numai
#   citirea.
# - trimite(text, cai_poze): jetonul, fiecare poza pe bucati de cel mult BUCATA octeti (base64 in JSON comprimat gzip,
#   o "incarcare" de 16 cifre hexa aleasa aici), apoi mesajul. Cererile spre forum au ritmul lor (_Ritm), sub limita
#   serverului; "prea multe" de la server se reincearca dupa o pauza.
# - jetonul se tine numai in memorie, pana cu JETON_REZERVA_S inainte de expirare. Fara profil la serverul testerilor,
#   receptorul si-l face singur (ruta `profil`, fara nume public: forumul ii da un nume pana alege omul unul), apoi cere
#   din nou jetonul. La trimitere, cat serverul inca nu are acordul abia dat (pleaca prin coada), jetonul se mai cere de
#   cateva ori, la ASTEPTARE_ACORD_S.
# - descarcaPoza(adresa): pozele mesajelor, pe un fir, in DOSAR_POZE (RAM), cu limita de marime.
#
# Tot ce vorbeste cu serverele ruleaza pe fire (Lucrare); ecranele si pagina web asteapta .gata. Erorile tehnice raman
# in jurnal; omul vede numai un text scurt (textEroare) dupa ce a cerut ceva.
#
# Adresa forumului: SERVER_FORUM; pentru probe un fisier in RAM (CALE_SERVER_PROBA) poate da alt server, numai http://
# spre 127.0.0.1 sau reteaua locala (aceeasi regula ca serverul testerilor).
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC il folosesc direct.

import base64
import hashlib
import json
import os
import re
import threading
import time

SERVER_FORUM = "https://stb.hdsatelit.com/forum/api/receptor/"
CALE_SERVER_PROBA = "/tmp/hds-forum-server"
PROTOCOL = 1

BUCATA = 160 * 1024
BUCATI_MAX = 25
POZA_MAX = BUCATA * BUCATI_MAX
POZE_MAX = 4
TEXT_MIN = 2
TEXT_MAX = 20000
MESAJE_PE_PAGINA = 20
JETON_REZERVA_S = 120
TIMP_CERERE_S = 30
REINCERCARI = 4
PAUZA_PREA_MULTE_S = 10
ASTEPTARE_ACORD_S = 20
INCERCARI_ACORD = 6

# ritmul cererilor spre forum: serverul primeste cel mult 30 pe minut de pe o adresa, cu o rafala de 15
RITM_PE_SECUNDA = 0.45
RITM_RAFALA = 10

DOSAR_POZE = "/tmp/hds-forum-poze"
POZA_DESCARCATA_MAX = 6 * 1024 * 1024
POZE_DOSAR_MAX = 24 * 1024 * 1024

_HEX16 = re.compile(r"\A[0-9a-f]{16}\Z")


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele se traduc la afisare."""
	return text


# „Tradus din ...” ca fraza intreaga pe limba sursei (numele limbii se acorda altfel in fiecare limba); aceleasi pe
# receptor si in web
TRADUS_DIN = {
	"ro": N_("Tradus din română"), "en": N_("Tradus din engleză"), "de": N_("Tradus din germană"),
	"fr": N_("Tradus din franceză"), "es": N_("Tradus din spaniolă"), "it": N_("Tradus din italiană"),
	"hu": N_("Tradus din maghiară"), "cs": N_("Tradus din cehă"), "pl": N_("Tradus din poloneză"),
	"pt": N_("Tradus din portugheză"), "nl": N_("Tradus din neerlandeză"), "ru": N_("Tradus din rusă"),
	"tr": N_("Tradus din turcă"), "uk": N_("Tradus din ucraineană"),
}


def textTradus(limba):
	"""„Tradus din engleză” pentru limba sursei a unui mesaj tradus; o limba fara fraza: „Tradus automat”; fara limba:
	""."""
	limba = limba.strip().lower()[:8] if isinstance(limba, str) else ""
	if not re.match(r"\A[a-z]{2,3}\Z", limba):
		return ""
	return _t(TRADUS_DIN.get(limba, N_("Tradus automat")))


# Un mesaj care asteapta aprobarea vine cu pozele fara adresa (forumul nu le arata nimanui inca): autorul vede fraza in
# locul lor, ca sa stie ca au plecat.
TEXT_POZE_ASCUNSE = N_("Pozele se văd după aprobare.")


def pozeAscunse(mesaj):
	"""Mesajul are poze pe care forumul nu le arata inca (fara adresa)."""
	poze = mesaj.get("poze") if isinstance(mesaj, dict) else None
	return isinstance(poze, list) and any(isinstance(p, dict) and not p.get("adresa") for p in poze)


def textCuPozeAscunse(text, mesaj):
	"""Textul mesajului, cu fraza pozelor ascunse pe un rand nou cand e cazul."""
	if not pozeAscunse(mesaj):
		return text
	return (text + "\n" if text else "") + _t(TEXT_POZE_ASCUNSE)


def _t(text):
	"""Traducerea enigma2, sau textul insusi (probele de pe PC)."""
	if not text:
		return text or ""
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def _jurnal(text):
	print("[HdsForumReceptor] %s" % text)


def _beta():
	from Components import HdsBetaTester
	return HdsBetaTester


# ------------------------------------------------------------------ textele pentru om

ERORI = {
	"jeton": N_("Legătura cu forumul a expirat. Încearcă din nou."),
	"fara_acord": N_("Serverul nu are încă acordul tău. Mai încearcă peste câteva minute."),
	"cheie": N_("Profilul e legat de alt receptor."),
	"nume_luat": N_("Numele e deja folosit. Alege altul."),
	"nume": N_("Numele public are 2-40 de semne: litere, cifre, spațiu, punct, liniuță."),
	"neinscris": N_("Ca să scrii pe forum, devino beta tester."),
	"blocat": N_("Nu mai poți scrie pe forum de pe acest receptor."),
	"inchis": N_("Subiectul e închis: nu se mai pot scrie mesaje."),
	"prea_multe": N_("Prea multe mesaje într-un timp scurt. Mai încearcă peste câteva minute."),
	"text": N_("Mesajul e gol sau prea lung."),
	"model": N_("Forumul nu are încă un subiect pentru acest receptor."),
	"subiect": N_("Forumul nu are încă un subiect pentru acest receptor."),
	"poza": N_("O poză nu a putut fi urcată: trebuie să fie JPG sau PNG, de cel mult 4 MB."),
	"poze": N_("Un mesaj poate avea cel mult 4 poze."),
	"fara_internet": N_("Receptorul nu ajunge la forum. Verifică legătura la internet."),
	"server": N_("Forumul nu răspunde acum. Încearcă mai târziu."),
}


def textEroare(cod):
	"""Textul scurt pentru om al unui cod de eroare (al serverelor sau al clientului)."""
	return _t(ERORI.get(cod) or ERORI["server"])


# ------------------------------------------------------------------ adresele

def serverValid(adresa):
	return _beta().serverValid(adresa)


def adresaForum():
	"""SERVER_FORUM, sau serverul de proba din CALE_SERVER_PROBA (numai http:// spre 127.0.0.1 sau reteaua locala)."""
	try:
		with open(CALE_SERVER_PROBA, "rb") as f:
			proba = f.read(256).decode("utf-8", "replace").strip()
	except (OSError, IOError):
		proba = ""
	if proba.startswith("http://") and serverValid(proba):
		return proba if proba.endswith("/") else proba + "/"
	return SERVER_FORUM


def _origine(adresa):
	m = re.match(r"\A(https?://[^/?#]+)", adresa or "")
	return m.group(1) if m else ""


def adresaPoza(adresa, forum=None):
	"""Adresa absoluta a unei poze din raspunsul `subiect`, numai de pe acelasi server cu forumul; altfel ""."""
	adresa = (adresa or "").strip()
	origine = _origine(forum or adresaForum())
	if not origine or not adresa or any(c in adresa for c in "\r\n\t <>\"'\\"):
		return ""
	if adresa.startswith("/") and not adresa.startswith("//"):
		return origine + adresa
	if _origine(adresa) == origine:
		return adresa
	return ""


def limbaForum(limba=None):
	"""Limba receptorului in forma forumului: doua litere mici ('ro_RO' -> 'ro')."""
	if limba is None:
		limba = _beta().limba()
	m = re.match(r"\A([A-Za-z]{2})", limba or "")
	return m.group(1).lower() if m else "ro"


# ------------------------------------------------------------------ cererile

class EroareForum(Exception):
	def __init__(self, cod, text=""):
		Exception.__init__(self, cod)
		self.cod = cod
		self.text = text   # textul pentru om cand e altul decat ERORI[cod] (ceasul receptorului, din HdsCeasHttps)


def _faraInternet(e):
	"""EroareForum pentru o cerere cazuta: daca de vina e ceasul receptorului (certificatul pare nevalabil dupa un flash),
	textul lui HdsCeasHttps; altfel textul obisnuit al lui fara_internet."""
	try:
		from Components import HdsCeasHttps
		text = HdsCeasHttps.mesaj(e) or ""
	except Exception:
		text = ""
	return EroareForum("fara_internet", text)


def _posteaza(url, corp, timp=TIMP_CERERE_S):
	"""POST JSON comprimat gzip (ca serverul testerilor) -> (cod HTTP, dict). O eroare de retea -> EroareForum."""
	B = _beta()
	_brut, gz = B.comprima(corp)
	try:
		cod, octeti = B._posteazaHttp(url, gz, timp)
	except Exception as e:
		_jurnal("cererea %s: %s" % (url.rsplit("/", 1)[-1] or url, B._mesajEroare(e)))
		raise _faraInternet(e)
	return cod, B._json(octeti)


def codDinRaspuns(cod, raspuns):
	"""Codul erorii unui raspuns care nu e 2xx: `eroare` din JSON, altfel dupa codul HTTP (nginx da HTML la 413/429)."""
	eroare = raspuns.get("eroare") if isinstance(raspuns, dict) else None
	if isinstance(eroare, str) and re.match(r"\A[a-z_]{1,32}\Z", eroare):
		return eroare
	if cod == 429:
		return "prea_multe"
	if cod == 413:
		return "poza"
	return "server"


class _Ritm(object):
	"""Ritmul cererilor spre forum (o galeata care se goleste cu `pe_secunda`): cel mult `rafala` deodata, apoi
	asteptare. Ruleaza numai pe fire."""

	def __init__(self, pe_secunda=RITM_PE_SECUNDA, rafala=RITM_RAFALA, ceas=None, doarme=None):
		self.pe_secunda = pe_secunda
		self.rafala = rafala
		self.ceas = ceas or time.monotonic
		self.doarme = doarme or time.sleep
		self.nivel = 0.0
		self.ultim = None
		self.lacat = threading.Lock()

	def asteapta(self):
		with self.lacat:
			acum = self.ceas()
			if self.ultim is not None:
				self.nivel = max(0.0, self.nivel - (acum - self.ultim) * self.pe_secunda)
			self.ultim = acum
			pauza = 0.0
			if self.nivel + 1 > self.rafala:
				pauza = (self.nivel + 1 - self.rafala) / self.pe_secunda
			self.nivel += 1
		if pauza > 0:
			self.doarme(pauza)


_ritm = _Ritm()


def cereForum(ruta, corp, forum=None, ritm=None, doarme=None):
	"""O cerere spre forum, cu ritmul si reincercarea la 'prea multe' -> raspunsul (dict) sau EroareForum."""
	forum = forum or adresaForum()
	ritm = ritm or _ritm
	doarme = doarme or time.sleep
	for incercare in range(REINCERCARI):
		ritm.asteapta()
		cod, raspuns = _posteaza(forum + ruta, corp)
		if 200 <= cod < 300 and raspuns.get("ok") is True:
			return raspuns
		eroare = codDinRaspuns(cod, raspuns)
		if eroare == "prea_multe" and incercare + 1 < REINCERCARI:
			_jurnal("%s: prea multe cereri, astept" % ruta)
			doarme(PAUZA_PREA_MULTE_S * (incercare + 1))
			continue
		_jurnal("%s: %s %s" % (ruta, cod, eroare))
		raise EroareForum(eroare)
	raise EroareForum("prea_multe")


# ------------------------------------------------------------------ jetonul

_jeton = {"jeton": "", "id": "", "expira": 0.0, "nume": "", "cont": None}
_lacat_jeton = threading.Lock()


def uitaJetonul():
	"""Jetonul (si numele stiut odata cu el) se uita: urmatoarea cerere ia unul nou, cu numele de acum (dupa o
	schimbare a numelui public, si din Aparitia publica)."""
	with _lacat_jeton:
		_jeton.update({"jeton": "", "id": "", "expira": 0.0, "nume": ""})


def _context():
	"""Ce trebuie firelor din setari, citit pe firul care cheama (firul enigma2)."""
	B = _beta()
	b = B.initConfig()
	inscris = B.inscris(b)
	return {"inscris": inscris, "id": b.id.value if inscris else "", "cheie": B.cheieProfil() if inscris else "",
		"testeri": B.adresaServer(b), "forum": adresaForum(), "limba": limbaForum(), "model": B._modelTinut()[0]}


def _model(ctx):
	if not ctx.get("model"):
		ctx["model"] = _beta().modelSiPaza()[0]
	if not ctx["model"]:
		raise EroareForum("model")
	return ctx["model"]


def _faProfil(ctx):
	"""Profilul receptorului la serverul testerilor (ruta `profil`), fara nume public si fara e-mail."""
	cod, raspuns = _posteaza(ctx["testeri"] + "profil", {"v": PROTOCOL, "id": ctx["id"], "cheie": ctx["cheie"],
		"nume_public": None, "email": None})
	if not (200 <= cod < 300):
		eroare = codDinRaspuns(cod, raspuns)
		_jurnal("profil: %s %s" % (cod, eroare))
		raise EroareForum(eroare)


def jeton(ctx, nou=False, acum=None, doarme=None):
	"""Jetonul de forum (pe un fir): din memorie, sau cerut serverului testerilor (forum-jeton) -> jetonul sau
	EroareForum (fara_acord, cheie, prea_multe, ...). Fara profil, il face singur si cere din nou. Cu
	ctx["asteapta_acord"], la fara_acord mai incearca de INCERCARI_ACORD ori (acordul abia dat e inca in coada)."""
	if not ctx.get("inscris"):
		raise EroareForum("neinscris")
	doarme = doarme or time.sleep
	acum_ = time.monotonic() if acum is None else acum
	with _lacat_jeton:
		if not nou and _jeton["jeton"] and _jeton["id"] == ctx["id"] and acum_ < _jeton["expira"] - JETON_REZERVA_S:
			return _jeton["jeton"]
	profil_facut = False
	asteptari = 0
	while True:
		cod, raspuns = _posteaza(ctx["testeri"] + "forum-jeton", {"v": PROTOCOL, "id": ctx["id"],
			"cheie": ctx["cheie"]})
		if 200 <= cod < 300 and raspuns.get("ok") is True and isinstance(raspuns.get("jeton"), str):
			break
		eroare = codDinRaspuns(cod, raspuns)
		_jurnal("forum-jeton: %s %s" % (cod, eroare))
		if eroare == "fara_profil" and not profil_facut:
			_faProfil(ctx)
			profil_facut = True
			continue
		if eroare == "fara_acord" and ctx.get("asteapta_acord") and asteptari < INCERCARI_ACORD:
			asteptari += 1
			doarme(ASTEPTARE_ACORD_S)
			continue
		raise EroareForum(eroare)
	if acum is None:
		acum_ = time.monotonic()
	try:
		expira_s = max(60, min(24 * 3600, int(raspuns.get("expira_s") or 3600)))
	except (TypeError, ValueError):
		expira_s = 3600
	nume = raspuns.get("nume") if isinstance(raspuns.get("nume"), str) else ""
	cont = raspuns.get("cont") if isinstance(raspuns.get("cont"), str) else None
	with _lacat_jeton:
		_jeton.update({"jeton": raspuns["jeton"][:4096], "id": ctx["id"], "expira": acum_ + expira_s, "cont": cont})
		if nume:
			_jeton["nume"] = nume[:80]
		return _jeton["jeton"]


def _tineNumeleForumului(raspuns):
	"""`nume` din raspunsul `subiect` cu jeton: numele cu care apare receptorul (si cel dat de forum)."""
	nume = raspuns.get("nume") if isinstance(raspuns, dict) else None
	if isinstance(nume, str) and nume.strip():
		with _lacat_jeton:
			_jeton["nume"] = nume.strip()[:80]


# ------------------------------------------------------------------ lucrarile (fire)

class Lucrare(threading.Thread):
	"""O lucrare cu forumul pe un fir: .gata, .reusit, .mesaj (text pentru om la nereusita), .rezultat, .cod (codul
	erorii, "" la reusita), .pas (ce face acum, pentru ecran), .cod_jeton (de ce n-a mers jetonul la citire, sau "")."""

	def __init__(self, functie, nume="hds-forum"):
		threading.Thread.__init__(self, name=nume)
		self.daemon = True
		self._functie = functie
		self.gata = False
		self.reusit = False
		self.mesaj = ""
		self.rezultat = None
		self.cod = ""
		self.pas = ""
		self.cod_jeton = ""

	def run(self):
		try:
			self.rezultat = self._functie(self)
			self.reusit = True
		except EroareForum as e:
			self.cod = e.cod
			self.mesaj = e.text or textEroare(e.cod)
		except Exception as e:
			_jurnal("%s: %s: %s" % (self.name, type(e).__name__, e))
			self.cod = "server"
			self.mesaj = textEroare("server")
		self.gata = True


def _porneste(functie, nume, porneste=True):
	l = Lucrare(functie, nume)
	if porneste:
		l.start()
	return l


def _citeste(lucrare, ctx, inainte):
	model = _model(ctx)
	corp = {"v": PROTOCOL, "model": model, "limba": ctx["limba"]}
	if inainte is not None:
		corp["inainte"] = int(inainte)
	if ctx.get("inscris"):
		try:
			corp["jeton"] = jeton(ctx)
		except EroareForum as e:
			lucrare.cod_jeton = e.cod
	try:
		r = cereForum("subiect", corp, ctx["forum"])
	except EroareForum as e:
		if e.cod != "jeton" or "jeton" not in corp:
			raise
		# jetonul tinut minte nu mai e bun: unul nou, o data
		uitaJetonul()
		corp["jeton"] = jeton(ctx, nou=True)
		r = cereForum("subiect", corp, ctx["forum"])
	if "jeton" in corp:
		_tineNumeleForumului(r)
	return r


def citeste(inainte=None, porneste=True):
	"""Subiectul modelului -> Lucrare; .rezultat = raspunsul `subiect` ({subiect, mesaje, mai_vechi, poti_scrie,
	nume}). inainte: numarul mesajului de la care se citesc cele mai vechi."""
	ctx = _context()
	return _porneste(lambda l: _citeste(l, ctx, inainte), "hds-forum-citeste", porneste)


# ------------------------------------------------------------------ mesajele noi (insigna randului forumului)
# Cel mai mare numar de mesaj vazut in ecranul forumului sau in pagina lui, pe subiect, intr-un fisier mic langa starea
# testerului. Meniul testerului si pagina /beta-tester arata cate mesaje au venit de atunci. Prima socoteala (sau alt
# subiect, dupa alt model) tine ce e acum ca vazut: un tester nou nu vede tot subiectul ca nou.

FISIER_VAZUT = "forum-vazut.json"
VERIFICARE_WEB_S = 300
_noi = {"n": 0, "cand": None, "lucreaza": False}


def ngettext(unu, multe, n):
	"""Pluralul tradus (Components.HdsPlural: Forma, al carei % merge si fara numar in forma pentru 1)."""
	try:
		from Components.HdsPlural import ngettext as plural
	except ImportError:
		return unu if n == 1 else multe
	return plural(unu, multe, n)


def textMesajeNoi(n):
	"""Insigna randului forumului: "" fara mesaje noi."""
	if not isinstance(n, int) or n <= 0:
		return ""
	return ngettext("un mesaj nou", "%d mesaje noi", n) % n


def _caleVazut():
	return os.path.join(_beta().DOSAR, FISIER_VAZUT)


def _subiectSiUltimul(rezultat):
	"""(numarul subiectului, cel mai mare numar de mesaj) dintr-o citire; (None, None) fara ele."""
	r = rezultat if isinstance(rezultat, dict) else {}
	s = r.get("subiect") if isinstance(r.get("subiect"), dict) else {}
	subiect = s.get("nr")
	numere = [m.get("nr") for m in (r.get("mesaje") if isinstance(r.get("mesaje"), list) else [])
		if isinstance(m, dict) and isinstance(m.get("nr"), int) and not isinstance(m.get("nr"), bool)]
	if not isinstance(subiect, int) or isinstance(subiect, bool) or not numere:
		return None, None
	return subiect, max(numere)


def _citesteVazut():
	try:
		with open(_caleVazut(), "r") as f:
			d = json.load(f)
	except (IOError, OSError, ValueError):
		return {}
	return d if isinstance(d, dict) else {}


def _scrieVazut(subiect, nr):
	cale = _caleVazut()
	try:
		if not os.path.isdir(os.path.dirname(cale)):
			os.makedirs(os.path.dirname(cale))
		with open(cale + ".nou", "w") as f:
			json.dump({"subiect": subiect, "nr": nr}, f)
		os.replace(cale + ".nou", cale)
	except (IOError, OSError) as e:
		_jurnal("mesajele vazute: %s" % e)


def tineVazut(rezultat):
	"""Dupa citirea ultimelor mesaje in ecranul forumului sau in pagina lui: tot ce e acolo e vazut."""
	subiect, nr = _subiectSiUltimul(rezultat)
	if subiect is None:
		return
	d = _citesteVazut()
	if d.get("subiect") != subiect or not isinstance(d.get("nr"), int) or d["nr"] < nr:
		_scrieVazut(subiect, nr)
	_noi["n"] = 0
	_noi["cand"] = time.monotonic()


def mesajeNoi(rezultat):
	"""Cate mesaje din citire sunt dupa ultimul vazut; tine numarul pentru pagina web (mesajeNoiCunoscute)."""
	subiect, nr = _subiectSiUltimul(rezultat)
	if subiect is None:
		return 0
	d = _citesteVazut()
	vazut = d.get("nr")
	if d.get("subiect") != subiect or not isinstance(vazut, int) or isinstance(vazut, bool):
		_scrieVazut(subiect, nr)
		n = 0
	else:
		n = sum(1 for m in rezultat.get("mesaje") or []
			if isinstance(m, dict) and isinstance(m.get("nr"), int) and m["nr"] > vazut)
	_noi["n"] = n
	_noi["cand"] = time.monotonic()
	return n


def mesajeNoiCunoscute():
	"""Ultimul numar aflat (meniul testerului sau verificaMesajeNoi), fara cerere la forum."""
	return _noi["n"]


def verificaMesajeNoi(dupa_s=VERIFICARE_WEB_S):
	"""Pentru pagina /beta-tester, care nu asteapta forumul: o citire pe fir, cel mult una la dupa_s secunde; numarul
	vine apoi in mesajeNoiCunoscute(). -> True daca a pornit una acum."""
	if _noi["lucreaza"] or (_noi["cand"] is not None and time.monotonic() - _noi["cand"] < dupa_s):
		return False
	_noi["lucreaza"] = True
	_noi["cand"] = time.monotonic()

	def lucru():
		try:
			l = citeste(porneste=False)
			l.run()
			if l.reusit:
				mesajeNoi(l.rezultat)
		except Exception as e:
			_jurnal("mesajele noi: %s" % e)
		finally:
			_noi["lucreaza"] = False
	t = threading.Thread(target=lucru, name="hds-forum-noi")
	t.daemon = True
	t.start()
	return True


def cereJetonul(porneste=True):
	"""Jetonul, pregatit cat omul scrie (si profilul, daca lipseste) -> Lucrare; .rezultat = {nume, cont}."""
	ctx = _context()
	ctx["asteapta_acord"] = True

	def lucru(_l):
		jeton(ctx)
		with _lacat_jeton:
			return {"nume": _jeton["nume"], "cont": _jeton["cont"]}
	return _porneste(lucru, "hds-forum-jeton", porneste)


def textValid(text):
	text = curataText(text)
	return TEXT_MIN <= len(text) <= TEXT_MAX


def curataText(text):
	"""Textul scris de om: fara caractere de control (afara de rand nou si tab), fara spatii la capete."""
	text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
	return "".join(c for c in text if c >= " " or c in "\n\t").strip()


def _bucati(octeti):
	return [octeti[i:i + BUCATA] for i in range(0, len(octeti), BUCATA)] or [b""]


def _urcaPoza(ctx, cale_poza, ritm=None):
	"""O poza pe bucati -> id-ul atasamentului de pe forum."""
	try:
		with open(cale_poza, "rb") as f:
			octeti = f.read(POZA_MAX + 1)
	except (OSError, IOError) as e:
		_jurnal("poza %s: %s" % (cale_poza, e))
		raise EroareForum("poza")
	if not octeti or len(octeti) > POZA_MAX or not (octeti[:3] == b"\xff\xd8\xff" or octeti[:8] == b"\x89PNG\r\n\x1a\n"):
		raise EroareForum("poza")
	bucati = _bucati(octeti)
	incarcare = os.urandom(8).hex()
	poza = None
	for i, bucata in enumerate(bucati):
		corp = {"v": PROTOCOL, "jeton": jeton(ctx), "incarcare": incarcare, "bucata": i, "bucati": len(bucati),
			"date": base64.b64encode(bucata).decode("ascii")}
		try:
			r = cereForum("poza", corp, ctx["forum"], ritm)
		except EroareForum as e:
			if e.cod != "jeton":
				raise
			uitaJetonul()
			corp["jeton"] = jeton(ctx, nou=True)
			r = cereForum("poza", corp, ctx["forum"], ritm)
		poza = r.get("poza")
	if poza is None or isinstance(poza, bool):
		_jurnal("poza: ultima bucata fara id")
		raise EroareForum("poza")
	return poza


def _trimite(lucrare, ctx, text, cai_poze, ritm=None):
	text = curataText(text)
	if not (TEXT_MIN <= len(text) <= TEXT_MAX):
		raise EroareForum("text")
	cai_poze = list(cai_poze or [])
	if len(cai_poze) > POZE_MAX:
		raise EroareForum("poze")
	model = _model(ctx)
	jeton(ctx)
	ids = []
	for k, c in enumerate(cai_poze):
		lucrare.pas = _t("Se urcă poza %(k)d din %(n)d...") % {"k": k + 1, "n": len(cai_poze)}
		ids.append(_urcaPoza(ctx, c, ritm))
	lucrare.pas = _t("Se trimite mesajul...")
	corp = {"v": PROTOCOL, "jeton": jeton(ctx), "model": model, "limba": ctx["limba"], "text": text, "poze": ids}
	try:
		r = cereForum("mesaj", corp, ctx["forum"], ritm)
	except EroareForum as e:
		if e.cod != "jeton":
			raise
		uitaJetonul()
		corp["jeton"] = jeton(ctx, nou=True)
		r = cereForum("mesaj", corp, ctx["forum"], ritm)
	m = r.get("mesaj") if isinstance(r.get("mesaj"), dict) else {}
	return {"nr": m.get("nr"), "stare": m.get("stare") or "aprobat"}


def trimite(text, cai_poze, porneste=True, ritm=None):
	"""Mesajul nou -> Lucrare (jetonul, pozele pe bucati, mesajul); .rezultat = {nr, stare}; stare "asteapta" = la
	moderator (il vede numai receptorul care l-a scris)."""
	ctx = _context()
	ctx["asteapta_acord"] = True
	return _porneste(lambda l: _trimite(l, ctx, text, cai_poze, ritm), "hds-forum-trimite", porneste)


def _schimbaNume(ctx, nume):
	if not ctx.get("inscris"):
		raise EroareForum("neinscris")
	cod, raspuns = _posteaza(ctx["testeri"] + "profil", ctx["profil"])
	if not (200 <= cod < 300):
		eroare = codDinRaspuns(cod, raspuns)
		_jurnal("profil: %s %s" % (cod, eroare))
		raise EroareForum(eroare)
	uitaJetonul()
	with _lacat_jeton:
		_jeton["nume"] = nume
	# un jeton nou si o citire a subiectului: forumul afla numele nou pe loc (si la mesajele vechi)
	try:
		corp = {"v": PROTOCOL, "model": _model(ctx), "limba": ctx["limba"], "jeton": jeton(ctx, nou=True)}
		_tineNumeleForumului(cereForum("subiect", corp, ctx["forum"]))
	except EroareForum as e:
		_jurnal("numele nou la forum: %s" % e.cod)
	with _lacat_jeton:
		return {"nume": _jeton["nume"] or nume}


def schimbaNume(nume, porneste=True):
	"""Numele public nou (ruta `profil` a serverului testerilor) -> Lucrare; .rezultat = {"nume": numele nou}. Dupa
	reusita: jeton nou si o citire a subiectului, ca forumul sa arate numele nou pe loc. Nume nepotrivit: Lucrare
	terminata cu .cod = "nume", fara cerere."""
	B = _beta()
	nume = B.textNume(nume, B.NUME_PUBLIC_MAX + 1)
	if not B.numePublicValid(nume):
		l = Lucrare(lambda _l: None, "hds-forum-nume")
		l.cod = "nume"
		l.mesaj = textEroare("nume")
		l.gata = True
		return l
	ctx = _context()
	if ctx.get("inscris"):
		ctx["profil"] = B.corpProfil("profil", nume_public=nume)
	return _porneste(lambda _l: _schimbaNume(ctx, nume), "hds-forum-nume", porneste)


def poateScrie():
	"""Beta tester inscris (scrierea pe forum)."""
	try:
		return _beta().inscris()
	except Exception:
		return False


def numePublic():
	"""Numele cu care apare omul pe forum: cel stiut de la jeton sau de la forum (si numele dat de forum, cand omul nu
	si-a ales unul), altfel numele public tinut in setari; "" cand inca nu se stie."""
	with _lacat_jeton:
		if _jeton["nume"]:
			return _jeton["nume"]
	try:
		return _beta().initConfig().public.value or ""
	except Exception:
		return ""


# ------------------------------------------------------------------ ora si pozele

def oraLocala(cand, acum=None):
	"""'AAAA-LL-ZZTHH:MMZ' (UTC) -> 'azi, OO:MM' / 'ieri, OO:MM' / 'ZZ.LL.AAAA, OO:MM' in ora receptorului."""
	m = re.match(r"\A(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})", cand or "")
	if not m:
		return ""
	import calendar
	try:
		s = calendar.timegm((int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5)), 0,
			0, 0, 0))
	except (ValueError, OverflowError):
		return ""
	t = time.localtime(s)
	n = time.localtime(time.time() if acum is None else acum)
	ora = time.strftime("%H:%M", t)
	if (t.tm_year, t.tm_yday) == (n.tm_year, n.tm_yday):
		return _t("azi, %s") % ora
	ieri = time.localtime(time.mktime(n) - 24 * 3600)
	if (t.tm_year, t.tm_yday) == (ieri.tm_year, ieri.tm_yday):
		return _t("ieri, %s") % ora
	return "%s, %s" % (time.strftime("%d.%m.%Y", t), ora)


def _caleLocala(adresa):
	ext = ".png" if adresa.lower().split("?")[0].endswith(".png") else ".jpg"
	return os.path.join(DOSAR_POZE, hashlib.sha1(adresa.encode("utf-8")).hexdigest()[:24] + ext)


def _citesteHttp(url, maxim):
	from urllib.request import Request, urlopen
	r = urlopen(Request(url, headers={"User-Agent": "hdsatelit-receptor/1", "Accept": "image/*"}), timeout=TIMP_CERERE_S)
	try:
		return r.getcode(), r.read(maxim + 1)
	finally:
		r.close()


def _faLoc(limita=POZE_DOSAR_MAX):
	"""Cele mai vechi poze descarcate se sterg pana cand dosarul trece sub limita."""
	try:
		f = []
		for n in os.listdir(DOSAR_POZE):
			c = os.path.join(DOSAR_POZE, n)
			s = os.stat(c)
			f.append((s.st_mtime, c, s.st_size))
	except OSError:
		return
	f.sort()
	total = sum(x[2] for x in f)
	while f and total > limita:
		_mt, c, m = f.pop(0)
		try:
			os.remove(c)
		except OSError:
			pass
		total -= m


def _descarca(adresa, citeste=None):
	c = _caleLocala(adresa)
	if os.path.isfile(c):
		return c
	cod, octeti = (citeste or _citesteHttp)(adresa, POZA_DESCARCATA_MAX)
	if cod != 200 or len(octeti) > POZA_DESCARCATA_MAX or not (octeti[:3] == b"\xff\xd8\xff" or
			octeti[:8] == b"\x89PNG\r\n\x1a\n"):
		_jurnal("poza descarcata: %s, %d octeti" % (cod, len(octeti or b"")))
		raise EroareForum("server")
	try:
		os.makedirs(DOSAR_POZE, exist_ok=True)
		_faLoc(POZE_DOSAR_MAX - len(octeti))
		nou = c + ".nou"
		with open(nou, "wb") as f:
			f.write(octeti)
		os.replace(nou, c)
	except (OSError, IOError) as e:
		_jurnal("poza descarcata: %s" % e)
		raise EroareForum("server")
	return c


def descarcaPoza(adresa, porneste=True, citeste=None):
	"""Poza unui mesaj (adresa din raspunsul `subiect`) pe un fir -> Lucrare; .rezultat = calea locala."""
	forum = adresaForum()

	def lucru(_l):
		url = adresaPoza(adresa, forum)
		if not url:
			raise EroareForum("server")
		try:
			return _descarca(url, citeste)
		except EroareForum:
			raise
		except Exception as e:
			_jurnal("poza descarcata: %s" % e)
			raise _faraInternet(e)
	return _porneste(lucru, "hds-forum-poza", porneste)


def golestePozele():
	"""Pozele descarcate se sterg (la inchiderea forumului)."""
	try:
		for n in os.listdir(DOSAR_POZE):
			try:
				os.remove(os.path.join(DOSAR_POZE, n))
			except OSError:
				pass
	except OSError:
		pass
