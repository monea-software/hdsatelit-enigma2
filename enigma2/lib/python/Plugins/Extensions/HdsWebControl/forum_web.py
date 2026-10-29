# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# forum_web.py: „Forumul receptorului” in interfata web (HdsWebControl).
#
# Perechea ecranului de pe televizor (Screens/HdsForumReceptor.py): subiectul modelului de pe forum (il citeste
# oricine), scrierea unui mesaj cu capturi (numai beta testerii inscrisi), numele de pe forum, galeria capturilor
# receptorului (stick / memoria receptorului), captura facuta acum si poza urcata de pe calculator. Logica:
# Components/HdsForumReceptor.py (forumul) si Components/HdsCapturi.py (capturile).
#
# Rute (poarta comuna a HdsJsonResource; ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF):
#   GET  /api/forum-receptor                      starea locala: inscris, numele, limitele
#   POST /api/forum-receptor-fa?fa=<ce>           citeste (inainte=), trimite (text=, poze=loc/nume,...), nume (nume=)
#   GET  /api/forum-receptor-lucrare?n=<nr>       rezultatul unei lucrari pornite aici (forum, captura, poza urcata)
#   GET  /api/forum-receptor-poza?p=<id>          o poza a unui mesaj, adusa de receptor de pe forum
#   GET  /api/capturi                             locurile si capturile, cele mai noi primele
#   GET  /api/captura-poza?nume=&loc=             o captura (numai prin HdsCapturi.cale: lista alba a numelor)
#   POST /api/captura-fa                          captura de acum, pe un fir
#   POST /api/captura-urca                        poza de pe calculator, octeti bruti (application/octet-stream)
#   POST /api/captura-sterge?capturi=loc/nume,..  stergerea, in doi pasi (pas=intreaba, apoi cod=)
#   GET  /forum-receptor                          pagina
#
# POZELE FORUMULUI: CSP-ul paginilor (plugin._anteteHtml) are img-src 'self', deci pozele de pe forum vin prin receptor.
# Id-ul unei poze il face receptorul numai pentru adresele primite in raspunsul forumului si trecute de
# HdsForumReceptor.adresaPoza (aceeasi origine cu forumul); navigatorul trimite numai id-ul, niciodata o adresa sau o
# cale. Descarcarea merge pe un fir (HdsForumReceptor.descarcaPoza, in RAM, cu limita); pana e gata ruta raspunde 503,
# iar pagina mai incearca.
#
# CORPUL CERERILOR: 64 KB peste tot (plugin.MAX_CORP_CERERE), deci textul unui mesaj are in pagina cel mult TEXT_MAX_WEB
# semne (o litera cu diacritic, codata in formular, are 6 octeti). Poza urcata are limita ei, numai pe /api/captura-urca
# (plugin.MAX_CORP_CAPTURA).
#
# FIRELE: render_* ruleaza pe firul enigma2; tot ce asteapta (forumul, grab, scrierea pe stick) merge pe fire, iar
# pagina intreaba de rezultat (/api/forum-receptor-lucrare). Fisierul nu importa nimic din enigma2 la incarcare:
# probele de pe PC dau modulele lor (F, C, B).

import hashlib
import itertools
import os
import re
import threading
import time

CAMPURI_FA = ("fa", "inainte", "text", "poze", "nume")
TEXT_MAX_WEB = 8000
POZE_MAX = 4
URCARE_MAX = 4 * 1024 * 1024
LATIME_MAX = 1920
MAX_LUCRARI = 24
MAX_POZE_FORUM = 400
MAX_CAPTURI = 300
REINCERCARE_POZA_S = 30

_LUCRARI = {}
_NUMAR = itertools.count(1)
_POZE = {}
_DESCARCARI = {}
_lacat = threading.Lock()
_ID_POZA = re.compile(r"\A[0-9a-f]{20}\Z")
_LOC = re.compile(r"\A[a-z]{1,16}\Z")


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele se traduc la folosire."""
	return text


def _t(text):
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _jurnal(text):
	print("[HdsWebControl] forum: %s" % text)


def _f(F=None):
	if F is not None:
		return F
	from Components import HdsForumReceptor
	return HdsForumReceptor


def _c(C=None):
	if C is not None:
		return C
	from Components import HdsCapturi
	return HdsCapturi


def _b(B=None):
	if B is not None:
		return B
	from Components import HdsBetaTester
	return HdsBetaTester


def _mc():
	from . import meniu_comun_web
	return meniu_comun_web


# ------------------------------------------------------------------ lucrarile (fire)

class _Fir(threading.Thread):
	"""O functie pe un fir, cu .gata, .reusit, .mesaj, .rezultat (ca HdsForumReceptor.Lucrare). Functia intoarce
	(reusit, rezultat_sau_mesaj)."""

	def __init__(self, functie, nume="hds-forum-web"):
		threading.Thread.__init__(self, name=nume)
		self.daemon = True
		self._functie = functie
		self.gata = False
		self.reusit = False
		self.mesaj = ""
		self.rezultat = None

	def run(self):
		try:
			ok, rez = self._functie()
			self.reusit = bool(ok)
			if ok:
				self.rezultat = rez
			else:
				self.mesaj = rez or _t("Nu s-a putut face.")
		except Exception as eroare:
			_jurnal("%s: %s" % (self.name, eroare))
			self.mesaj = _t("Eroare pe receptor: %s") % eroare
		self.gata = True


def _lucrare(fel, l):
	"""Tine lucrarea `l` (fir pornit) si intoarce numarul ei pentru /api/forum-receptor-lucrare."""
	with _lacat:
		while len(_LUCRARI) >= MAX_LUCRARI:
			_LUCRARI.pop(min(_LUCRARI))
		n = next(_NUMAR)
		_LUCRARI[n] = (fel, l)
	return {"result": True, "lucrare": n}


def _capturaInCurs():
	with _lacat:
		for n, (fel, l) in _LUCRARI.items():
			if fel == "captura" and not l.gata:
				return n
	return None


# ------------------------------------------------------------------ textele mici

def textMax(F=None):
	try:
		return max(2, min(TEXT_MAX_WEB, int(_f(F).TEXT_MAX)))
	except Exception:
		return TEXT_MAX_WEB


def textTradus(cod, F=None):
	"""„Tradus din germană” (aceleasi fraze ca pe receptor, din Components.HdsForumReceptor), sau "" fara limba."""
	try:
		tradus = _f(F).textTradus
	except (ImportError, AttributeError):
		return ""
	return tradus(cod)


def oraCapturii(secunde, acum=None):
	"""„azi, OO:MM” / „ieri, OO:MM” / „ZZ.LL.AAAA, OO:MM” in ora receptorului (secunde UNIX)."""
	try:
		t = time.localtime(int(secunde))
	except (TypeError, ValueError, OverflowError, OSError):
		return ""
	n = time.localtime(time.time() if acum is None else acum)
	ora = time.strftime("%H:%M", t)
	if (t.tm_year, t.tm_yday) == (n.tm_year, n.tm_yday):
		return _t("azi, %s") % ora
	ieri = time.localtime(time.mktime(n) - 24 * 3600)
	if (t.tm_year, t.tm_yday) == (ieri.tm_year, ieri.tm_yday):
		return _t("ieri, %s") % ora
	return "%s, %s" % (time.strftime("%d.%m.%Y", t), ora)


def _sir(x, maxim):
	return x[:maxim] if isinstance(x, str) else ""


# ------------------------------------------------------------------ pozele forumului

def idPoza(adresa):
	"""Id-ul unei poze a forumului (adresa deja verificata); adresa se tine numai pe receptor."""
	i = hashlib.sha1(adresa.encode("utf-8", "replace")).hexdigest()[:20]
	with _lacat:
		_POZE.pop(i, None)
		_POZE[i] = adresa
		while len(_POZE) > MAX_POZE_FORUM:
			_POZE.pop(next(iter(_POZE)))
	return i


def _adresa(F, adresa):
	"""Adresa absoluta a unei poze sau a subiectului, numai de pe serverul forumului (HdsForumReceptor.adresaPoza)."""
	if not isinstance(adresa, str) or not adresa:
		return ""
	try:
		return F.adresaPoza(adresa) or ""
	except Exception:
		return ""


def fir(r, F=None):
	"""Raspunsul `subiect` al forumului, curatat pentru pagina: textele taiate, pozele ca id-uri, ora locala."""
	F = _f(F)
	r = r if isinstance(r, dict) else {}
	s = r.get("subiect") if isinstance(r.get("subiect"), dict) else {}
	mesaje = []
	for m in (r.get("mesaje") if isinstance(r.get("mesaje"), list) else [])[:60]:
		if not isinstance(m, dict):
			continue
		nr = m.get("nr")
		if isinstance(nr, bool) or not isinstance(nr, int):
			continue
		poze = []
		for p in (m.get("poze") if isinstance(m.get("poze"), list) else [])[:8]:
			a = _adresa(F, p.get("adresa")) if isinstance(p, dict) else ""
			if a:
				poze.append(idPoza(a))
		try:
			ora = F.oraLocala(m.get("cand") or "")
		except Exception:
			ora = ""
		mesaje.append({
			"nr": nr,
			"autor": _sir(m.get("autor"), 80),
			"insigna": m.get("insigna") if m.get("insigna") in ("echipa", "tester") else "",
			"ora": ora,
			"text": _sir(m.get("text"), 40000),
			"tradus": textTradus(m.get("tradus_din"), F),
			"poze": poze,
			"asteapta": m.get("stare") == "asteapta",
			# pozele unui mesaj care asteapta aprobarea vin fara adresa (HdsForumReceptor.pozeAscunse): pagina spune
			# „Pozele se văd după aprobare.” in locul lor
			"poze_ascunse": any(isinstance(p, dict) and not p.get("adresa")
				for p in (m.get("poze") if isinstance(m.get("poze"), list) else [])),
		})
	return {
		"subiect": {"titlu": _sir(s.get("titlu"), 200), "adresa": _adresa(F, s.get("adresa"))},
		"mesaje": mesaje,
		"mai_vechi": bool(r.get("mai_vechi")),
		"poti_scrie": bool(r.get("poti_scrie")),
		"nume": _sir(r.get("nume"), 80),
	}


def pozaForum(arg, F=None):
	"""GET /api/forum-receptor-poza?p=<id> -> ("fisier", cale, tip) sau ("json", corp, cod)."""
	F = _f(F)
	p = arg.get("p", "")
	if not _ID_POZA.match(p):
		return "json", {"result": False, "message": _t("Poza nu mai există.")}, 404
	with _lacat:
		adresa = _POZE.get(p)
		l = _DESCARCARI.get(p)
	if adresa is None:
		return "json", {"result": False, "message": _t("Poza nu mai există.")}, 404
	if l is not None and l[1].gata:
		if l[1].reusit and isinstance(l[1].rezultat, str) and os.path.isfile(l[1].rezultat):
			return "fisier", l[1].rezultat, tipPoza(l[1].rezultat)
		if not l[1].reusit and time.monotonic() - l[0] < REINCERCARE_POZA_S:
			return "json", {"result": False, "gata": True, "message": l[1].mesaj}, 502
		l = None
	if l is None:
		lucrare = F.descarcaPoza(adresa)
		with _lacat:
			_DESCARCARI[p] = (time.monotonic(), lucrare)
			while len(_DESCARCARI) > MAX_POZE_FORUM:
				_DESCARCARI.pop(next(iter(_DESCARCARI)))
	return "json", {"result": False, "gata": False, "message": _t("Poza se aduce de pe forum...")}, 503


def tipPoza(cale):
	"""Tipul pozei dupa primii octeti (fisierele vin de la componente, dar tipul nu se ghiceste dupa nume)."""
	try:
		with open(cale, "rb") as f:
			cap = f.read(8)
	except (OSError, IOError):
		return "application/octet-stream"
	if cap.startswith(b"\x89PNG"):
		return "image/png"
	return "image/jpeg"


# ------------------------------------------------------------------ starea, comenzile forumului

def stare(F=None):
	"""GET /api/forum-receptor."""
	F = _f(F)
	inscris = bool(F.poateScrie())
	rez = {"result": True, "inscris": inscris, "poze_max": POZE_MAX, "text_max": textMax(F),
		"urcare_max": URCARE_MAX, "latime_max": LATIME_MAX}
	if inscris:
		try:
			rez["nume"] = F.numePublic() or ""
		except Exception:
			rez["nume"] = ""
	return rez


def _perechi(text, C):
	"""„loc/nume,loc/nume” -> ([(loc, nume, cale)], None) sau (None, mesaj). Numai capturi existente
	(HdsCapturi.cale)."""
	rez = []
	vazute = set()
	for bucata in [b for b in (text or "").split(",") if b.strip()][:POZE_MAX + 1]:
		loc, _sep, nume = bucata.strip().partition("/")
		if not _LOC.match(loc) or (loc, nume) in vazute:
			return None, _t("O captură aleasă nu mai există. Alege din nou.")
		cale = C.cale(nume, loc)
		if not cale:
			return None, _t("O captură aleasă nu mai există. Alege din nou.")
		vazute.add((loc, nume))
		rez.append((loc, nume, cale))
	if len(rez) > POZE_MAX:
		return None, _t("Un mesaj poate avea cel mult %d poze.") % POZE_MAX
	return rez, None


def fa(arg, F=None, C=None, B=None):
	"""POST /api/forum-receptor-fa."""
	F = _f(F)
	ce = arg.get("fa", "")
	if ce == "citeste":
		try:
			inainte = int(arg.get("inainte") or 0)
		except ValueError:
			inainte = 0
		if inainte > 0:
			return _lucrare("citeste-vechi", F.citeste(inainte))
		return _lucrare("citeste", F.citeste(None))
	if ce not in ("trimite", "nume"):
		return {"result": False, "message": _t("Cerere necunoscută.")}
	if not F.poateScrie():
		return {"result": False, "message": _t("Ca să scrii pe forum, devino beta tester.")}
	if ce == "trimite":
		text = (arg.get("text") or "").replace("\r\n", "\n").strip()
		if len(text) < 2:
			return {"result": False, "message": _t("Scrie întâi mesajul.")}
		if len(text) > textMax(F):
			return {"result": False, "message": _t("Mesajul e prea lung.")}
		perechi, eroare = _perechi(arg.get("poze", ""), _c(C))
		if eroare:
			return {"result": False, "message": eroare}
		return _lucrare("trimite", F.trimite(text, [p[2] for p in perechi]))
	B = _b(B)
	nume = B.textNume(arg.get("nume", ""), B.NUME_PUBLIC_MAX + 1)
	if not B.numePublicValid(nume):
		return {"result": False, "message": _t("Numele public are 2-40 de semne: litere, cifre, spațiu, punct, "
			"liniuță.")}
	schimba = getattr(F, "schimbaNume", None)
	if schimba is None:
		return {"result": False, "message": _t("Numele nu se poate schimba încă de aici.")}
	return _lucrare("nume", schimba(nume))


def _rezultatCaptura(l):
	if isinstance(l, _Fir):
		return l.rezultat if isinstance(l.rezultat, dict) else {}
	cale = getattr(l, "cale", "") or ""
	return {"nume": os.path.basename(cale), "loc": getattr(l, "loc", "") or "",
		"amovibil": bool(getattr(l, "amovibil", True))}


def lucrare(arg, F=None, C=None):
	"""GET /api/forum-receptor-lucrare?n= -> {gata, result, message, ...}."""
	try:
		n = int(arg.get("n", "0"))
	except ValueError:
		n = 0
	with _lacat:
		x = _LUCRARI.get(n)
	if x is None:
		return {"result": False, "gata": True, "message": _t("Cererea nu mai există. Încearcă din nou.")}
	fel, l = x
	if not l.gata:
		return {"result": True, "gata": False, "pas": _sir(getattr(l, "pas", ""), 200)}
	# lucrarea terminata ramane (pana o scot cele mai noi, MAX_LUCRARI): o captura ceruta din doua navigatoare deodata
	# are acelasi numar, iar al doilea afla si el rezultatul
	if not l.reusit:
		return {"result": False, "gata": True, "message": l.mesaj or _t("Nu s-a putut face.")}
	if fel in ("citeste", "citeste-vechi"):
		F = _f(F)
		if fel == "citeste":
			# ultimele mesaje sunt in pagina: insigna randului forumului (meniul testerului, /beta-tester) se sterge
			tineVazut = getattr(F, "tineVazut", None)
			if tineVazut is not None:
				tineVazut(l.rezultat)
		rez = fir(l.rezultat, F)
		rez.update({"result": True, "gata": True, "message": ""})
		cod_jeton = getattr(l, "cod_jeton", "")
		rez["nota_jeton"] = F.textEroare(cod_jeton) if cod_jeton else ""
		return rez
	if fel == "trimite":
		r = l.rezultat if isinstance(l.rezultat, dict) else {}
		if r.get("stare") == "asteapta":
			mesaj = _t("Mesajul așteaptă aprobarea moderatorului; până atunci îl vezi numai tu.")
		else:
			mesaj = _t("Mesajul e pe forum.")
		return {"result": True, "gata": True, "message": mesaj, "stare": r.get("stare") or "aprobat"}
	if fel == "nume":
		r = l.rezultat if isinstance(l.rezultat, dict) else {}
		return {"result": True, "gata": True, "nume": _sir(r.get("nume"), 80), "message": _t("Numele e salvat.")}
	r = _rezultatCaptura(l)
	if fel == "captura":
		try:
			mesaj = _c(C).textSalvata(r.get("loc"), r.get("amovibil", True))
		except Exception:
			mesaj = ""
	else:
		mesaj = _t("Poza e pusă între capturi.")
	return {"result": True, "gata": True, "nume": r.get("nume", ""), "loc": r.get("loc", ""), "message": mesaj}


# ------------------------------------------------------------------ capturile

def _locuri(C):
	rez = []
	for l in C.locuri():
		if isinstance(l, dict) and l.get("cheie"):
			rez.append({"cheie": l["cheie"], "nume": _sir(l.get("nume"), 60), "disponibil": bool(l.get("disponibil"))})
	return rez


def capturi(C=None, acum=None):
	"""GET /api/capturi: locurile (cu numarul capturilor), capturile (cele mai noi primele) si locul cu cea mai noua."""
	C = _c(C)
	locuri = _locuri(C)
	lista = []
	for x in C.lista()[:MAX_CAPTURI]:
		lista.append({"nume": x.get("nume", ""), "loc": x.get("loc", ""), "ora": oraCapturii(x.get("cand"), acum),
			"marime": int(x.get("marime") or 0)})
	for l in locuri:
		l["numar"] = sum(1 for x in lista if x["loc"] == l["cheie"])
	if lista:
		loc_nou = lista[0]["loc"]
	else:
		loc_nou = next((l["cheie"] for l in locuri if l["disponibil"]), "memorie")
	return {"result": True, "locuri": locuri, "capturi": lista, "loc_nou": loc_nou}


def pozaCaptura(arg, C=None):
	"""GET /api/captura-poza -> ("fisier", cale, tip) sau ("json", corp, cod). Calea vine NUMAI din HdsCapturi.cale."""
	cale = _c(C).cale(arg.get("nume", ""), arg.get("loc", ""))
	if not cale:
		return "json", {"result": False, "message": _t("Captura nu mai există.")}, 404
	return "fisier", cale, tipPoza(cale)


def capturaFa(C=None):
	"""POST /api/captura-fa: captura pe un fir (paza imaginii se citeste aici, pe firul enigma2)."""
	C = _c(C)
	n = _capturaInCurs()
	if n is not None:
		return {"result": True, "lucrare": n}
	return _lucrare("captura", C.faPeFir())


def _felPoza(octeti):
	if octeti[:3] == b"\xff\xd8\xff":
		return "jpg"
	if octeti[:8] == b"\x89PNG\r\n\x1a\n":
		return "png"
	return ""


def capturaUrca(octeti, C=None):
	"""POST /api/captura-urca: poza (deja micsorata de pagina) pusa intre capturi, pe un fir -> (corp, cod)."""
	C = _c(C)
	if not octeti:
		return {"result": False, "message": _t("Alege o poză.")}, 400
	if len(octeti) > URCARE_MAX:
		return {"result": False, "message": _t("Poza e prea mare.")}, 413
	if not _felPoza(octeti):
		return {"result": False, "message": _t("Poza trebuie să fie JPG sau PNG.")}, 400

	def lucru():
		loc = next((l["cheie"] for l in _locuri(C) if l["disponibil"]), "memorie")
		ok, rez = C.adauga(octeti, loc)
		return (True, {"nume": rez, "loc": loc}) if ok else (False, rez)
	f = _Fir(lucru, "hds-forum-urca")
	f.start()
	return _lucrare("urcare", f), 200


def sterge(arg, C=None, mc=None):
	"""POST /api/captura-sterge?capturi=loc/nume,...: pas=intreaba (intrebarea si codul), apoi cod= (stergerea)."""
	C = _c(C)
	mc = mc or _mc()
	perechi, eroare = _perechi(arg.get("capturi", ""), C)
	if eroare:
		return {"result": False, "message": eroare}
	if not perechi:
		return {"result": False, "message": _t("Alege întâi capturile.")}
	tinta = ",".join(sorted("%s/%s" % (p[0], p[1]) for p in perechi))
	if arg.get("pas") == "renunta":
		mc.uita("captura-sterge", tinta)
		return {"result": True, "message": _t("Nu s-a făcut nimic.")}
	if arg.get("pas") == "intreaba":
		if len(perechi) == 1:
			intrebare = _t("Ștergi captura aleasă?")
		else:
			intrebare = _t("Ștergi cele %d capturi alese?") % len(perechi)
		return mc.raspunsIntrebare("captura-sterge", tinta, intrebare, _t("Da, șterge"))
	if not mc.verifica("captura-sterge", tinta, arg.get("cod", "")):
		return mc.codGresit()
	gresite = []
	for loc, nume, _cale in perechi:
		ok, mesaj = C.sterge(nume, loc)
		if not ok:
			gresite.append(mesaj)
	if gresite:
		return {"result": False, "message": gresite[0]}
	return {"result": True, "message": _t("Captura s-a șters.") if len(perechi) == 1 else _t("Capturile s-au șters.")}


# ------------------------------------------------------------------ rutele

def trimiteFisier(request, cale, tip):
	"""O poza de pe disc, cu twisted.web.static.File (citita pe bucati de conexiune), cu tipul dat."""
	from twisted.web import static
	f = static.File(cale, defaultType=tip)
	f.contentTypes = {os.path.splitext(cale)[1].lower(): tip}
	f.contentEncodings = {}
	f.type = tip
	f.encoding = None
	request.setHeader(b"cache-control", b"private, max-age=300")
	request.setHeader(b"x-content-type-options", b"nosniff")
	return f.render(request)


def rute(baza, resource, F=None, C=None, B=None, mc=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py."""

	def _m():
		return mc or _mc()

	def _arg(request, chei, lung=200):
		return _m().argumente(request, chei, lung)

	def _eroare(obiect, request, eroare):
		return obiect._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class _Citeste(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, self.lucru(request))
			except Exception as eroare:
				return _eroare(self, request, eroare)

	class _Schimba(baza):
		schimbaCeva = True

		def render_GET(self, request):
			return self._eroare(request, _t("Cererea se trimite cu POST."), 405)

		def render_POST(self, request):
			try:
				rez = self.lucru(request)
				if isinstance(rez, tuple):
					return self._raspunde(request, rez[0], rez[1])
				return self._raspunde(request, rez)
			except Exception as eroare:
				return _eroare(self, request, eroare)

	class _Fisier(baza):
		def render_GET(self, request):
			try:
				fel, a, b = self.lucru(request)
				if fel == "fisier":
					return trimiteFisier(request, a, b)
				return self._raspunde(request, a, b)
			except Exception as eroare:
				return _eroare(self, request, eroare)

	class StareResource(_Citeste):
		def lucru(self, request):
			return stare(F)

	class FaResource(_Schimba):
		def lucru(self, request):
			arg = _arg(request, CAMPURI_FA, TEXT_MAX_WEB + 16)
			for cheie, maxim in (("inainte", 12), ("poze", 400), ("nume", 80), ("fa", 16)):
				if cheie in arg:
					arg[cheie] = arg[cheie][:maxim]
			return fa(arg, F, C, B)

	class LucrareResource(_Citeste):
		def lucru(self, request):
			return lucrare(_arg(request, ("n",), 12), F, C)

	class PozaForumResource(_Fisier):
		def lucru(self, request):
			return pozaForum(_arg(request, ("p",), 24), F)

	class CapturiResource(_Citeste):
		def lucru(self, request):
			return capturi(C)

	class CapturaPozaResource(_Fisier):
		def lucru(self, request):
			return pozaCaptura(_arg(request, ("nume", "loc"), 80), C)

	class CapturaFaResource(_Schimba):
		def lucru(self, request):
			return capturaFa(C)

	class CapturaUrcaResource(_Schimba):
		def lucru(self, request):
			try:
				request.content.seek(0)
				octeti = request.content.read(URCARE_MAX + 1)
			except Exception as eroare:
				return {"result": False, "message": _t("Poza nu a ajuns întreagă: %s") % eroare}, 400
			return capturaUrca(octeti, C)

	class CapturaStergeResource(_Schimba):
		def lucru(self, request):
			refuz = _m().numaiBrowser(request)
			if refuz:
				return {"result": False, "message": refuz}
			return sterge(_arg(request, ("capturi", "pas", "cod"), 400), C, _m())

	class PaginaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			return _m().pagina(request, pagina_text)

	api = {
		b"forum-receptor": StareResource(),
		b"forum-receptor-fa": FaResource(),
		b"forum-receptor-lucrare": LucrareResource(),
		b"forum-receptor-poza": PozaForumResource(),
		b"capturi": CapturiResource(),
		b"captura-poza": CapturaPozaResource(),
		b"captura-fa": CapturaFaResource(),
		b"captura-urca": CapturaUrcaResource(),
		b"captura-sterge": CapturaStergeResource(),
	}
	return api, PaginaResource()


def pagina_text(stil, config_pagina):
	return _mc().sablon(_traducePagina(PAGINA), stil, config_pagina, {"__DRUM_MENIU__": _mc().drumHtml(
		"hds_beta_tester")})



PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Forumul receptorului</title>
<style>__STIL_COMUN__
__STIL_PAGINI__
  main.forum{max-width:1240px;}
  .ic{width:20px;height:20px;flex:none;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;}
  .subiect{color:var(--text-slab);margin:-6px 0 18px;line-height:1.5;display:flex;flex-wrap:wrap;gap:4px 16px;align-items:baseline;}
  .subiect b{color:var(--text);font-weight:600;}
  .subiect a{color:var(--legatura,#7fb8ff);}
  .coloane{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:24px;align-items:start;}
  .bara-fir{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:0 0 8px;}
  .bara-fir .nota{margin:0;}
  .bloc{background:var(--rand,var(--panou));border:1px solid var(--bordura);border-radius:6px;padding:16px 20px;margin:0 0 4px;outline:none;}
  .bloc.ales,.bloc:focus-visible{background:var(--ales,var(--panou));color:var(--ales-text,var(--text));box-shadow:inset 6px 0 0 var(--chihlimbar,var(--galben));}
  .cap-mesaj{display:flex;flex-wrap:wrap;align-items:center;gap:6px 12px;margin:0 0 8px;font-size:.9rem;}
  .autor{font-weight:700;font-size:1.02rem;}
  .insigna{display:inline-block;font-size:.7rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;padding:2px 8px;border-radius:4px;border:1px solid var(--chihlimbar,var(--galben));color:var(--chihlimbar,var(--galben));}
  .insigna.echipa{background:var(--albastru);border-color:var(--albastru);color:#fff;}
  .insigna.asteapta{border-style:dashed;}
  .ora,.tradus,.nr{color:var(--text-slab);}
  .tradus{font-style:italic;}
  .nr{margin-left:auto;font-size:.8rem;font-family:monospace;}
  .text-mesaj{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.55;font-size:1.02rem;}
  .nota-poze{margin:10px 0 0;color:var(--text-slab);font-style:italic;font-size:.9rem;}
  .poze{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0 0;}
  .poze a{display:block;width:200px;max-width:calc(50% - 4px);aspect-ratio:16/9;border:1px solid var(--bordura);border-radius:4px;overflow:hidden;background:var(--panou-2,var(--fundal));}
  .poze img{width:100%;height:100%;object-fit:cover;display:block;color:transparent;}
  .poze a.lipsa{display:flex;align-items:center;justify-content:center;padding:8px;font-size:.8rem;color:var(--text-slab);text-align:center;text-decoration:none;}
  .gol{color:var(--text-slab);padding:18px 0;}
  .laturi{position:sticky;top:12px;}
  .cutie{background:var(--panou);border:1px solid var(--bordura);border-radius:8px;padding:18px;margin:0 0 12px;}
  .cutie h2{font-size:1.2rem;font-weight:600;margin:0;}
  .cutie .nota{margin:0;}
  .scrie{display:grid;grid-template-columns:minmax(0,1fr);gap:10px;grid-template-areas:"titlu" "limba" "text" "atasate" "alege" "fa" "incarca" "trimite" "apari" "stare";}
  .scrie h2{grid-area:titlu;}
  .scrie .nota-limba{grid-area:limba;}
  .scrie textarea{grid-area:text;width:100%;min-height:140px;resize:vertical;}
  .scrie .atasate{grid-area:atasate;}
  #alege{grid-area:alege;}
  #faCaptura{grid-area:fa;}
  #incarca{grid-area:incarca;}
  #trimite{grid-area:trimite;}
  .scrie .apari{grid-area:apari;}
  .scrie .mesaj{grid-area:stare;margin:0;}
  .scrie button{display:flex;align-items:center;justify-content:center;gap:8px;width:100%;}
  .scrie button.mare{min-height:56px;font-size:1.06rem;font-weight:600;}
  .scrie button.hds-b.legatura{min-height:40px;background:none;border:0;color:var(--legatura,#7fb8ff);text-decoration:underline;cursor:pointer;font:inherit;}
  .scrie .scurt{display:none;}
  .numar-atasate{display:inline-flex;align-items:center;justify-content:center;min-width:22px;height:22px;padding:0 6px;border-radius:11px;background:var(--chihlimbar,var(--galben));color:#1d1700;font-size:.8rem;font-weight:700;}
  .numar-atasate:empty{display:none;}
  .atasate:empty{display:none;}
  .atasate{display:flex;flex-direction:column;gap:6px;}
  .atasate .lista-atasate{display:flex;flex-wrap:wrap;gap:8px;}
  .atasat{position:relative;width:100px;aspect-ratio:16/9;border:1px solid var(--bordura);border-radius:4px;overflow:hidden;background:var(--panou-2,var(--fundal));}
  .atasat img{width:100%;height:100%;object-fit:cover;display:block;}
  .atasat button.hds-b{position:absolute;top:3px;right:3px;width:28px;height:28px;min-height:0;padding:0;border-radius:50%;border:1px solid var(--bordura);background:var(--fundal);color:var(--text);font:inherit;font-size:1rem;line-height:1;cursor:pointer;}
  .apari{color:var(--text-slab);font-size:.9rem;}
  .apari b{color:var(--text);}
  .nume-forum{display:flex;gap:8px;margin:10px 0 0;}
  .nume-forum input{flex:1 1 auto;min-width:0;}
  .vizitator p{margin:8px 0 0;line-height:1.5;}
  a.buton{display:inline-flex;align-items:center;justify-content:center;min-height:48px;padding:8px 22px;border-radius:6px;background:var(--accent);color:#fff;text-decoration:none;font-weight:600;margin:12px 0 0;}
  .fereastra{position:fixed;inset:0;z-index:70;background:rgba(0,0,0,.62);display:flex;align-items:center;justify-content:center;padding:16px;}
  .fereastra.ascuns{display:none;}
  .fereastra-in{background:var(--fundal);color:var(--text);border:1px solid var(--bordura);border-radius:10px;width:min(1120px,100%);max-height:100%;display:flex;flex-direction:column;overflow:hidden;}
  .cap-galerie{display:flex;flex-wrap:wrap;align-items:center;gap:10px 16px;padding:18px 22px 12px;border-bottom:2px solid var(--chihlimbar,var(--galben));}
  .cap-galerie h2{flex:1 1 auto;margin:0;font-size:1.5rem;font-weight:400;display:flex;align-items:center;gap:10px;}
  .cap-galerie h2 .ic{width:28px;height:28px;color:var(--chihlimbar,var(--galben));}
  .pastila{border:1px solid var(--bordura);border-radius:6px;padding:6px 12px;font-size:.92rem;}
  .file{display:flex;flex-wrap:wrap;gap:8px;padding:12px 22px 4px;}
  #file button{flex:0 1 auto;min-width:150px;}
  #file button[aria-selected="true"]{background:var(--accent);border-color:var(--accent);color:#fff;}
  .galerie .mesaj{padding:0 22px;margin:6px 0;}
  .grila{flex:1 1 auto;overflow:auto;display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:12px;padding:6px 22px 16px;align-content:start;}
  .tila{position:relative;display:flex;flex-direction:column;padding:6px;border:2px solid transparent;border-radius:8px;background:var(--rand,var(--panou));cursor:pointer;outline:none;}
  .tila:focus-visible{border-color:var(--text-slab);}
  .tila[aria-checked="true"]{border-color:var(--chihlimbar,var(--galben));}
  .tila img{width:100%;aspect-ratio:16/9;object-fit:cover;border-radius:4px;background:var(--panou-2,var(--fundal));display:block;}
  .tila .semn{position:absolute;top:12px;left:12px;width:30px;height:30px;border-radius:50%;background:var(--chihlimbar,var(--galben));color:#1d1700;font-weight:700;display:flex;align-items:center;justify-content:center;}
  .tila .jos-tila{display:flex;justify-content:space-between;gap:8px;padding:6px 2px 0;font-size:.85rem;color:var(--text-slab);}
  .intrebare-galerie{margin:0 22px 8px;padding:12px 16px;border:1px solid var(--bordura);border-radius:8px;background:var(--panou);}
  .intrebare-galerie p{margin:0 0 8px;}
  .butoane-galerie{display:flex;flex-wrap:wrap;gap:8px;padding:12px 22px;border-top:1px solid var(--bordura);}
  .butoane-galerie button{display:inline-flex;align-items:center;gap:8px;}
  .butoane-galerie .principal{margin-left:auto;}
  body.cu-fereastra{overflow:hidden;}
  main.forum .ascuns{display:none;}
  @media (max-width:959px){ .coloane{grid-template-columns:minmax(0,1fr);} .laturi{position:static;} }
  @media (max-width:759px){
    main.forum.cu-scriere{padding-bottom:170px;}
    .scrie{position:fixed;z-index:45;left:0;right:0;bottom:var(--cadru-jos,0px);margin:0;border-radius:0;border-left:0;border-right:0;padding:8px 10px;gap:6px;background:var(--antet,var(--panou));
      grid-template-columns:minmax(0,1fr) auto auto;grid-template-areas:"apari apari apari" "atasate atasate atasate" "text alege trimite" "stare stare stare";}
    .scrie h2,.scrie .nota-limba,#faCaptura,#incarca,.scrie .lung{display:none;}
    .scrie .scurt{display:inline;}
    .scrie textarea{min-height:48px;height:48px;resize:none;}
    .scrie button{width:auto;min-height:48px;padding:6px 12px;flex-direction:column;gap:2px;font-size:.75rem;}
    .scrie button.mare{min-height:48px;font-size:.75rem;}
    #alege,#trimite{padding:6px 12px;min-width:56px;}
    main.forum.cu-scriere .bloc{scroll-margin-bottom:calc(var(--cadru-jos,0px) + 160px);}
    .atasat{width:64px;}
    .fereastra{padding:0;}
    .fereastra-in{border-radius:0;height:100%;}
    .grila{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;padding:6px 10px 12px;}
    .cap-galerie,.file,.butoane-galerie{padding-left:10px;padding-right:10px;}
    #file button{flex:1 1 0;min-width:0;}
    .butoane-galerie button{flex:1 1 45%;justify-content:center;}
    .butoane-galerie .principal{margin-left:0;}
  }
</style>
</head>
<body>
<main class="forum" id="pagina">
<h1>Forumul receptorului</h1>
<p class="subiect" id="subiect">Se citește forumul...</p>
<p class="mesaj" id="mesaj"></p>
<div class="coloane">
  <section aria-labelledby="titluFir">
    <h2 class="hds-ascuns" id="titluFir">Mesajele</h2>
    <div class="bara-fir"><button type="button" id="maiVechi" class="ascuns">Mai vechi</button><p class="nota" id="numar"></p></div>
    <div id="mesaje" aria-live="polite"></div>
  </section>
  <aside class="laturi">
    <div id="vizitator" class="cutie vizitator ascuns">
      <h2>Scrie și tu pe forum</h2>
      <p>Aici scriu beta testerii acestui receptor. Ca să scrii și tu, devino beta tester.</p>
      <a class="buton" href="/beta-tester">Devino beta tester</a>
    </div>
    <div id="scrie" class="cutie scrie ascuns">
      <h2>Scrie un mesaj</h2>
      <p class="nota nota-limba">O singură limbă: forumul traduce singur.</p>
      <textarea id="text" maxlength="8000" placeholder="Scrie mesajul tău..." aria-label="Mesajul"></textarea>
      <div class="atasate" id="atasate"></div>
      <button type="button" class="principal" id="alege"><svg class="ic" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M21 16l-5-5-8 8"/></svg><span class="lung">Alege din capturile receptorului</span><span class="scurt">Capturi</span><span class="numar-atasate" id="nrAtasate"></span></button>
      <button type="button" id="faCaptura"><svg class="ic" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7l2-3h4l2 3"/><circle cx="12" cy="13.5" r="3.5"/></svg><span>Fă o captură acum</span></button>
      <button type="button" class="hds-b legatura" id="incarca">sau încarcă o poză de pe calculator</button>
      <button type="button" class="principal mare" id="trimite" aria-label="Trimite pe forum"><svg class="ic" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M4 12l16-8-6 16-3-6-7-2z"/></svg><span class="lung">Trimite pe forum</span></button>
      <p class="nota apari"><span>Apari ca:</span> <b id="numeAcum"></b></p>
      <p class="mesaj" id="mesajScrie"></p>
    </div>
    <div id="numeCutie" class="cutie ascuns">
      <h2><label for="nume">Numele tău pe forum</label></h2>
      <div class="nume-forum"><input type="text" id="nume" maxlength="40" autocomplete="nickname"><button type="button" id="salveazaNume">Salvează</button></div>
      <p class="mesaj" id="mesajNume"></p>
    </div>
  </aside>
</div>
<input type="file" id="fisier" accept="image/*" class="ascuns">
<div id="galerie" class="fereastra galerie ascuns" role="dialog" aria-modal="true" aria-labelledby="titluGalerie">
  <div class="fereastra-in">
    <div class="cap-galerie"><h2 id="titluGalerie"><svg class="ic" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M21 16l-5-5-8 8"/></svg><span>Capturile receptorului</span></h2><span class="pastila" id="nrAlese"></span></div>
    <div class="file" role="tablist" id="file"></div>
    <p class="mesaj" id="mesajGalerie"></p>
    <div class="grila" id="grila"></div>
    <div class="intrebare-galerie ascuns" id="intrebare"></div>
    <div class="butoane-galerie">
      <button type="button" id="gFa"><svg class="ic" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7l2-3h4l2 3"/><circle cx="12" cy="13.5" r="3.5"/></svg><span>Fă o captură acum</span></button>
      <button type="button" id="gIncarca"><svg class="ic" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 16V4M7 9l5-5 5 5M4 20h16"/></svg><span>Încarcă de pe calculator</span></button>
      <button type="button" class="rosu" id="gSterge">Șterge</button>
      <button type="button" id="gRenunta">Renunță</button>
      <button type="button" class="principal" id="gAdauga">Adaugă la mesaj</button>
    </div>
  </div>
</div>
<p class="nota">Același forum e pe televizor: __DRUM_MENIU__, Forumul receptorului.</p>
</main>
<script>
__SCRIPT_COMUN__
var STARE = null, MESAJE = [], VECHI = false, CITESC = false, PRIMA = true, ATASATE = [];
var GAL = {loc: "", locuri: [], capturi: [], alese: [], ceas: null};
var PENTRU = "scrie";
function el(eticheta, clasa, text){ var e = document.createElement(eticheta); if(clasa){ e.className = clasa; } if(text){ e.textContent = text; } return e; }
function spune(id, text, eroare){ var m = $(id); if(!m){ mesaj(text, eroare); return; } m.textContent = text || ""; m.classList.toggle("eroare", !!eroare); }
function cheie(a){ return a.loc + "/" + a.nume; }
function urlCaptura(a){ return adresa("/api/captura-poza?nume=" + encodeURIComponent(a.nume) + "&loc=" + encodeURIComponent(a.loc)); }
function lucrare(n, pas, dupa, unde){
  setTimeout(function(){
    cerere("/api/forum-receptor-lucrare?n=" + n).then(function(d){
      if(!d.gata){
        if(d.pas && unde){ spune(unde, d.pas); }
        if(pas < 900){ lucrare(n, pas + 1, dupa, unde); return; }
        dupa({result: false, message: "Receptorul nu a terminat la timp. Încearcă din nou."}); return;
      }
      dupa(d);
    }).catch(function(){ dupa({result: false, message: "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."}); });
  }, pas ? 700 : 300);
}
function porneste(cale, q, dupa, unde){
  cerere(cale, "POST", q).then(function(d){
    if(!d.result || !d.lucrare){ dupa(d); return; }
    lucrare(d.lucrare, 0, dupa, unde);
  }).catch(function(){ dupa({result: false, message: "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."}); });
}
function citesteStarea(){
  cerere("/api/forum-receptor").then(function(d){
    if(!d.result){ spune("subiect", d.message || "Receptorul nu a putut citi starea.", true); return; }
    STARE = d;
    $("vizitator").classList.toggle("ascuns", d.inscris);
    $("scrie").classList.toggle("ascuns", !d.inscris);
    $("numeCutie").classList.toggle("ascuns", !d.inscris);
    $("pagina").classList.toggle("cu-scriere", !!d.inscris);
    $("text").maxLength = d.text_max || 8000;
    if(d.inscris){ arataNumele(d.nume || ""); }
    citesteFir(0, true);
  }).catch(function(){ spune("subiect", "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea.", true); });
}
function arataNumele(nume){
  if(!STARE){ return; }
  STARE.nume = nume;
  $("numeAcum").textContent = nume;
  $("scrie").querySelector(".apari").classList.toggle("ascuns", !nume);
  if(document.activeElement !== $("nume")){ $("nume").value = nume; }
}
function citesteFir(inainte, deLaCapat){
  if(!inainte){ if(CITESC){ return; } CITESC = true; }
  var q = new URLSearchParams(); q.set("fa", "citeste");
  if(inainte){ q.set("inainte", String(inainte)); }
  if(inainte){ spune("numar", "Se citește forumul..."); }
  porneste("/api/forum-receptor-fa", q, function(d){
    if(!inainte){ CITESC = false; }
    if(!d.result){ spune(MESAJE.length ? "numar" : "subiect", d.message || "Forumul nu se poate citi acum.", true); return; }
    arataSubiectul(d.subiect || {});
    if(deLaCapat){ MESAJE = []; }
    var primul = inainte && MESAJE.length ? MESAJE[0].nr : null;
    uneste(d.mesaje || []);
    if(inainte || deLaCapat || MESAJE.length === (d.mesaje || []).length){ VECHI = !!d.mai_vechi; }
    if(STARE && STARE.inscris && d.nume){ arataNumele(d.nume); }
    if(d.nota_jeton){ spune("mesajScrie", d.nota_jeton, true); }
    arataMesajele();
    if(primul){ var e = $("m" + primul); if(e){ e.scrollIntoView({block: "start"}); } }
    else if(PRIMA && MESAJE.length){ PRIMA = false; var u = $("m" + MESAJE[MESAJE.length - 1].nr); if(u){ u.scrollIntoView({block: "end"}); } }
  }, inainte ? "numar" : null);
}
function arataSubiectul(s){
  var p = $("subiect"); p.textContent = ""; p.classList.remove("eroare");
  if(s.titlu){ p.appendChild(el("b", "", s.titlu)); }
  if(s.adresa){ var a = el("a", "", "Deschide subiectul pe forum"); a.href = s.adresa; a.target = "_blank"; a.rel = "noopener"; p.appendChild(a); }
}
function uneste(lista){
  var dupaNr = {};
  MESAJE.forEach(function(m){ dupaNr[m.nr] = m; });
  lista.forEach(function(m){ dupaNr[m.nr] = m; });
  MESAJE = Object.keys(dupaNr).map(function(k){ return dupaNr[k]; }).sort(function(a, b){ return a.nr - b.nr; });
}
function arataMesajele(){
  var c = $("mesaje"); c.textContent = "";
  if(!MESAJE.length){ c.appendChild(el("p", "gol", "Încă nu e niciun mesaj aici.")); }
  MESAJE.forEach(function(m){ c.appendChild(blocMesaj(m)); });
  $("maiVechi").classList.toggle("ascuns", !VECHI);
  spune("numar", MESAJE.length ? "Mesaje afișate: {n}".replace("{n}", MESAJE.length) : "");
}
function blocMesaj(m){
  var b = el("article", "bloc"); b.id = "m" + m.nr; b.tabIndex = 0;
  var cap = el("div", "cap-mesaj");
  cap.appendChild(el("span", "autor", m.autor));
  if(m.insigna === "echipa"){ var e = el("span", "insigna", "Echipa"); e.classList.add("echipa"); cap.appendChild(e); }
  if(m.insigna === "tester"){ cap.appendChild(el("span", "insigna", "Beta tester")); }
  if(m.asteapta){ var w = el("span", "insigna", "Așteaptă aprobarea"); w.classList.add("asteapta"); cap.appendChild(w); }
  if(m.ora){ cap.appendChild(el("span", "ora", m.ora)); }
  if(m.tradus){ cap.appendChild(el("span", "tradus", m.tradus)); }
  cap.appendChild(el("span", "nr", "#" + m.nr));
  b.appendChild(cap);
  b.appendChild(el("p", "text-mesaj", m.text));
  if(m.poze_ascunse){ b.appendChild(el("p", "nota-poze", "Pozele se văd după aprobare.")); }
  if(m.poze && m.poze.length){
    var z = el("div", "poze");
    m.poze.forEach(function(id){ z.appendChild(pozaForum(id)); });
    b.appendChild(z);
  }
  b.addEventListener("click", function(){
    document.querySelectorAll(".bloc.ales").forEach(function(x){ if(x !== b){ x.classList.remove("ales"); } });
    b.classList.toggle("ales");
  });
  return b;
}
function pozaForum(id){
  var a = el("a", ""); a.href = adresa("/api/forum-receptor-poza?p=" + encodeURIComponent(id)); a.target = "_blank"; a.rel = "noopener";
  var i = el("img", ""); i.alt = "Poza din mesaj"; i.loading = "lazy"; i.decoding = "async";
  var incercari = 0;
  i.addEventListener("error", function(){
    if(incercari < 8){ incercari++; setTimeout(function(){ i.src = a.href + "&i=" + incercari; }, 800 * incercari); return; }
    a.textContent = "Poza nu s-a putut aduce."; a.classList.add("lipsa");
  });
  a.addEventListener("click", function(ev){ ev.stopPropagation(); });
  i.src = a.href; a.appendChild(i);
  return a;
}
function arataAtasate(){
  var c = $("atasate"); c.textContent = "";
  $("nrAtasate").textContent = ATASATE.length ? String(ATASATE.length) : "";
  if(!ATASATE.length){ return; }
  c.appendChild(el("p", "nota", "Capturi atașate: {n} din {m}".replace("{n}", ATASATE.length).replace("{m}", maxPoze())));
  var l = el("div", "lista-atasate");
  ATASATE.forEach(function(a, k){
    var d = el("div", "atasat");
    var i = el("img", ""); i.alt = a.nume; i.src = urlCaptura(a); d.appendChild(i);
    var x = el("button", "hds-b", "\\u00d7"); x.type = "button"; x.setAttribute("aria-label", "Scoate captura");
    x.addEventListener("click", function(){ ATASATE.splice(k, 1); arataAtasate(); });
    d.appendChild(x); l.appendChild(d);
  });
  c.appendChild(l);
}
function maxPoze(){ return (STARE && STARE.poze_max) || 4; }
function ataseaza(a, unde){
  if(ATASATE.some(function(x){ return cheie(x) === cheie(a); })){ return; }
  if(ATASATE.length >= maxPoze()){ spune(unde || "mesajScrie", "Mesajul are deja {m} capturi; noua captură e în galerie.".replace("{m}", maxPoze())); return; }
  ATASATE.push({nume: a.nume, loc: a.loc}); arataAtasate();
}
$("trimite").addEventListener("click", function(){
  var text = $("text").value.trim();
  if(text.length < 2){ spune("mesajScrie", "Scrie întâi mesajul.", true); $("text").focus(); return; }
  var q = new URLSearchParams(); q.set("fa", "trimite"); q.set("text", text); q.set("poze", ATASATE.map(cheie).join(","));
  var b = $("trimite"); b.disabled = true; spune("mesajScrie", "Se trimite...");
  porneste("/api/forum-receptor-fa", q, function(d){
    b.disabled = false; spune("mesajScrie", d.message, !d.result);
    if(d.result){ $("text").value = ""; ATASATE = []; arataAtasate(); citesteFir(0, false); }
  }, "mesajScrie");
});
$("salveazaNume").addEventListener("click", function(){
  var q = new URLSearchParams(); q.set("fa", "nume"); q.set("nume", $("nume").value.trim());
  var b = $("salveazaNume"); b.disabled = true; spune("mesajNume", "Se trimite...");
  porneste("/api/forum-receptor-fa", q, function(d){
    b.disabled = false; spune("mesajNume", d.message, !d.result);
    if(d.result){ $("nume").blur(); arataNumele(d.nume || $("nume").value.trim()); citesteFir(0, true); }
  }, "mesajNume");
});
$("nume").addEventListener("keydown", function(ev){ if(ev.key === "Enter"){ $("salveazaNume").click(); } });
$("maiVechi").addEventListener("click", function(){ if(MESAJE.length){ citesteFir(MESAJE[0].nr, false); } });
function faCaptura(unde, dupa){
  spune(unde, "Se face captura...");
  porneste("/api/captura-fa", new URLSearchParams(), function(d){
    spune(unde, d.message, !d.result);
    if(d.result && d.nume){ dupa(d); }
  }, unde);
}
$("faCaptura").addEventListener("click", function(){ faCaptura("mesajScrie", function(d){ ataseaza(d); }); });
$("gFa").addEventListener("click", function(){ faCaptura("mesajGalerie", function(d){ pozaNouaInGalerie(d); }); });
function alegeFisier(pentru){ PENTRU = pentru; $("fisier").value = ""; $("fisier").click(); }
$("incarca").addEventListener("click", function(){ alegeFisier("scrie"); });
$("gIncarca").addEventListener("click", function(){ alegeFisier("galerie"); });
$("fisier").addEventListener("change", function(){ var f = this.files && this.files[0]; if(f){ urca(f, PENTRU); } });
function blobDin(c, calitate){ return new Promise(function(gata){ c.toBlob(function(b){ gata(b); }, "image/jpeg", calitate); }); }
function micsoreaza(f){
  var maxim = (STARE && STARE.latime_max) || 1920, limita = (STARE && STARE.urcare_max) || 4194304;
  if(!window.createImageBitmap){ return Promise.resolve(f); }
  return createImageBitmap(f).then(function(bmp){
    var k = Math.min(1, maxim / Math.max(1, bmp.width));
    var c = document.createElement("canvas"); c.width = Math.max(1, Math.round(bmp.width * k)); c.height = Math.max(1, Math.round(bmp.height * k));
    var x = c.getContext("2d"); x.fillStyle = "#ffffff"; x.fillRect(0, 0, c.width, c.height); x.drawImage(bmp, 0, 0, c.width, c.height);
    if(bmp.close){ bmp.close(); }
    return blobDin(c, 0.85).then(function(b){ return b && b.size > limita ? blobDin(c, 0.7) : b; }).then(function(b){ return b && b.size > limita ? blobDin(c, 0.5) : b; });
  });
}
function urca(f, pentru){
  var unde = pentru === "galerie" ? "mesajGalerie" : "mesajScrie";
  spune(unde, "Se pregătește poza...");
  micsoreaza(f).then(function(b){
    if(!b){ throw new Error("poza"); }
    if(b.size > ((STARE && STARE.urcare_max) || 4194304)){ spune(unde, "Poza e prea mare.", true); return; }
    var antete = {"Content-Type": "application/octet-stream"};
    if(CFG.csrf){ antete["X-HDS-CSRF"] = CFG.csrf; }
    spune(unde, "Se trimite...");
    return fetch(adresa("/api/captura-urca"), {method: "POST", body: b, cache: "no-store", credentials: "same-origin", headers: antete}).then(function(r){
      if(r.status === 413){ return {result: false, message: "Poza e prea mare."}; }
      return r.json().catch(function(){ return {result: false, message: "Receptorul a răspuns neașteptat (HTTP " + r.status + ")."}; });
    }).then(function(d){
      if(!d.result || !d.lucrare){ spune(unde, d.message, true); return; }
      lucrare(d.lucrare, 0, function(x){
        spune(unde, x.message, !x.result);
        if(x.result && x.nume){ if(pentru === "galerie"){ pozaNouaInGalerie(x); } else { ataseaza(x); } }
      }, unde);
    });
  }).catch(function(){ spune(unde, "Poza nu se poate citi. Alege o poză JPG sau PNG.", true); });
}
function deschideGaleria(){
  GAL.alese = ATASATE.map(function(a){ return {nume: a.nume, loc: a.loc}; }); GAL.loc = "";
  $("intrebare").classList.add("ascuns"); spune("mesajGalerie", "");
  $("galerie").classList.remove("ascuns"); document.body.classList.add("cu-fereastra");
  citesteCapturi(true);
  clearInterval(GAL.ceas); GAL.ceas = setInterval(function(){ if(!document.hidden){ citesteCapturi(false); } }, 5000);
  $("gAdauga").focus();
}
function inchideGaleria(){
  clearInterval(GAL.ceas); GAL.ceas = null;
  $("galerie").classList.add("ascuns"); document.body.classList.remove("cu-fereastra");
  $("alege").focus();
}
function citesteCapturi(prima){
  return cerere("/api/capturi").then(function(d){
    if(!d.result){ spune("mesajGalerie", d.message, true); return; }
    GAL.locuri = d.locuri || []; GAL.capturi = d.capturi || [];
    if(prima || !GAL.loc){ GAL.loc = d.loc_nou; }
    var exista = {}; GAL.capturi.forEach(function(c){ exista[cheie(c)] = true; });
    GAL.alese = GAL.alese.filter(function(a){ return exista[cheie(a)]; });
    var inainte = ATASATE.length;
    ATASATE = ATASATE.filter(function(a){ return exista[cheie(a)]; });
    if(ATASATE.length !== inainte){ arataAtasate(); }
    arataGaleria();
  }).catch(function(){ spune("mesajGalerie", "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea.", true); });
}
function arataGaleria(){
  var f = $("file"); f.textContent = "";
  GAL.locuri.forEach(function(l){
    var b = el("button", "", l.disponibil ? l.nume + " (" + l.numar + ")" : l.nume); b.type = "button"; b.setAttribute("role", "tab");
    b.setAttribute("aria-selected", l.cheie === GAL.loc ? "true" : "false"); b.disabled = !l.disponibil;
    b.addEventListener("click", function(){ GAL.loc = l.cheie; arataGaleria(); });
    f.appendChild(b);
  });
  var g = $("grila"); g.textContent = "";
  var lista = GAL.capturi.filter(function(c){ return c.loc === GAL.loc; });
  if(!lista.length){ g.appendChild(el("p", "gol", "Nicio captură aici încă: fă una acum sau apasă tasta de captură de pe telecomandă.")); }
  lista.forEach(function(c){
    var k = GAL.alese.findIndex(function(a){ return cheie(a) === cheie(c); });
    var t = el("div", "tila"); t.tabIndex = 0; t.setAttribute("role", "checkbox"); t.setAttribute("aria-checked", k >= 0 ? "true" : "false");
    t.setAttribute("aria-label", c.ora);
    var i = el("img", ""); i.alt = ""; i.loading = "lazy"; i.src = urlCaptura(c); t.appendChild(i);
    if(k >= 0){ t.appendChild(el("span", "semn", String(k + 1))); }
    var j = el("div", "jos-tila"); j.appendChild(el("span", "", c.ora)); j.appendChild(el("span", "", marime(c.marime))); t.appendChild(j);
    t.addEventListener("click", function(){ comuta(c); });
    t.addEventListener("keydown", function(ev){ if(ev.key === " " || ev.key === "Enter"){ ev.preventDefault(); comuta(c); } });
    g.appendChild(t);
  });
  $("nrAlese").textContent = "Alese: {n} (până la {m})".replace("{n}", GAL.alese.length).replace("{m}", maxPoze());
  $("gSterge").disabled = !GAL.alese.length;
}
function marime(o){ return o >= 1048576 ? (o / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(o / 1024)) + " KB"; }
function comuta(c){
  var k = GAL.alese.findIndex(function(a){ return cheie(a) === cheie(c); });
  if(k >= 0){ GAL.alese.splice(k, 1); }
  else if(GAL.alese.length >= maxPoze()){ spune("mesajGalerie", "Poți alege cel mult {m} capturi.".replace("{m}", maxPoze()), true); return; }
  else { GAL.alese.push({nume: c.nume, loc: c.loc}); }
  spune("mesajGalerie", ""); arataGaleria();
}
function pozaNouaInGalerie(d){
  GAL.loc = d.loc;
  if(GAL.alese.length < maxPoze() && !GAL.alese.some(function(a){ return cheie(a) === cheie(d); })){ GAL.alese.push({nume: d.nume, loc: d.loc}); }
  citesteCapturi(false);
}
$("alege").addEventListener("click", deschideGaleria);
$("gRenunta").addEventListener("click", inchideGaleria);
$("gAdauga").addEventListener("click", function(){ ATASATE = GAL.alese.slice(); arataAtasate(); inchideGaleria(); });
$("galerie").addEventListener("keydown", function(ev){ if(ev.key === "Escape"){ inchideGaleria(); } });
$("gSterge").addEventListener("click", function(){
  var q = new URLSearchParams(); q.set("capturi", GAL.alese.map(cheie).join(",")); q.set("pas", "intreaba");
  cerere("/api/captura-sterge", "POST", q).then(function(d){
    if(!d.result || !d.confirmare){ spune("mesajGalerie", d.message, !d.result); return; }
    var c = d.confirmare, cutie = $("intrebare"); cutie.textContent = "";
    cutie.appendChild(el("p", "", c.intrebare));
    var b = el("div", "butoane");
    var da = el("button", "rosu", c.buton); da.type = "button";
    var nu = el("button", "", "Renunță"); nu.type = "button";
    da.addEventListener("click", function(){
      var q2 = new URLSearchParams(); q2.set("capturi", q.get("capturi")); q2.set("cod", c.cod);
      cutie.classList.add("ascuns");
      cerere("/api/captura-sterge", "POST", q2).then(function(r){ spune("mesajGalerie", r.message, !r.result); if(r.result){ GAL.alese = []; } citesteCapturi(false); }).catch(nimicNuRaspunde);
    });
    nu.addEventListener("click", function(){
      var q3 = new URLSearchParams(); q3.set("capturi", q.get("capturi")); q3.set("pas", "renunta");
      cutie.classList.add("ascuns"); cerere("/api/captura-sterge", "POST", q3).catch(function(){});
    });
    b.appendChild(da); b.appendChild(nu); cutie.appendChild(b);
    cutie.classList.remove("ascuns"); nu.focus();
  }).catch(nimicNuRaspunde);
});
citesteStarea();
setInterval(function(){ if(STARE && !document.hidden && !CITESC){ citesteFir(0, false); } }, 60000);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
TEXTE_PAGINA = {
	"html": (
		N_("Forumul receptorului"),
		N_("Se citește forumul..."),
		N_("Mesajele"),
		N_("Mai vechi"),
		N_("Scrie și tu pe forum"),
		N_("Aici scriu beta testerii acestui receptor. Ca să scrii și tu, devino beta tester."),
		N_("Devino beta tester"),
		N_("Scrie un mesaj"),
		N_("O singură limbă: forumul traduce singur."),
		N_("Alege din capturile receptorului"),
		N_("Capturi"),
		N_("Fă o captură acum"),
		N_("sau încarcă o poză de pe calculator"),
		N_("Trimite pe forum"),
		N_("Apari ca:"),
		N_("Numele tău pe forum"),
		N_("Salvează"),
		N_("Capturile receptorului"),
		N_("Încarcă de pe calculator"),
		N_("Șterge"),
		N_("Renunță"),
		N_("Adaugă la mesaj"),
		N_("Același forum e pe televizor: __DRUM_MENIU__, Forumul receptorului."),
		N_("Scrie mesajul tău..."),
		N_("Mesajul"),
	),
	"js": (
		N_("Receptorul nu a terminat la timp. Încearcă din nou."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Receptorul nu a putut citi starea."),
		N_("Se citește forumul..."),
		N_("Forumul nu se poate citi acum."),
		N_("Deschide subiectul pe forum"),
		N_("Încă nu e niciun mesaj aici."),
		N_("Mesaje afișate: {n}"),
		N_("Echipa"),
		N_("Beta tester"),
		N_("Așteaptă aprobarea"),
		N_("Pozele se văd după aprobare."),
		N_("Poza din mesaj"),
		N_("Poza nu s-a putut aduce."),
		N_("Capturi atașate: {n} din {m}"),
		N_("Scoate captura"),
		N_("Mesajul are deja {m} capturi; noua captură e în galerie."),
		N_("Scrie întâi mesajul."),
		N_("Se trimite..."),
		N_("Se face captura..."),
		N_("Se pregătește poza..."),
		N_("Poza e prea mare."),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Poza nu se poate citi. Alege o poză JPG sau PNG."),
		N_("Nicio captură aici încă: fă una acum sau apasă tasta de captură de pe telecomandă."),
		N_("Alese: {n} (până la {m})"),
		N_("Poți alege cel mult {m} capturi."),
		N_("Renunță"),
	),
}


def _traducePagina(sablon, fel="pagina"):
	"""Sablonul in limba receptorului; fara pachetul HdsWebControl (probele de pe PC), sablonul ca atare."""
	try:
		from .traducere_pagini import traduce
	except ImportError:
		return sablon
	return traduce(sablon, TEXTE_PAGINA, fel)
# ---------------------------------------------------------------- sfarsitul traducerii paginilor
