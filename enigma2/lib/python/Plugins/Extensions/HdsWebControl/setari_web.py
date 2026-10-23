# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# setari_web.py: ecranele de setari din data/setup.xml in interfata web (HdsWebControl).
#
# Pe televizor, intrarile de meniu cu <setup id="..."/> (Sound Output & Downmix, OSD Preferences cu "What to show
# at startup", Hard Drive Standby, Front Panel Display, External Keyboard, Analog RF Modulator) deschid
# Screens/Setup.py, care citeste randurile din data/setup.xml. Aici e aceeasi lista, construita la fel:
# - aceleasi randuri, in aceeasi ordine, cu aceleasi reguli ca Setup.addItems: level= fata de nivelul utilizatorului
#   (config.usage.setup_level), requires= din SystemInfo, randurile ConfigNothing sarite;
# - acelasi text, tradus, cu semnul „(în lucru)” / „(netestat)” din stare= (Components/HdsStareMeniu.py), si acelasi
#   text de ajutor (description=);
# - aceleasi alegeri: luate chiar din setarea config (ConfigSelection / ConfigBoolean / ConfigInteger / ConfigSlider),
#   / ConfigNumber, nu scrise a doua oara. ConfigSet (alegere multipla, de pilda vitezele de derulare): o bifa pentru
#   fiecare alegere, trimise ca lista despartita prin virgula; valoarea se pune ca toggleChoice de pe televizor (lista in
#   ordinea alegerilor), last_value se tine ca o copie (ca ConfigSet.onDeselect), deci se scrie si se citeste inapoi la
#   fel. Un text (ConfigText) se scrie si din web numai daca setarea spune cat poate fi de lung (atributul
#   web_text_max pus de modulul ei, de pilda numele receptorului pe televizor din Components/HdsStandbyTv.py); gol
#   inseamna valoarea implicita a setarii, aratata in casuta (web_text_gol: textul sau o functie care il da).
#   Setarile de alt fel (alte texte, ore) se arata, dar se schimba de pe televizor.
# La „Salvează”: valoarea pusa (notificatorii ei lucreaza ca la stanga/dreapta pe televizor), changedFinal ca la
# parasirea randului, save() ca la Verde si configfile.save() ca la inchiderea meniului „Settings”.
# Setarea se ia din textul randului (config.av.downmix_ac3) prin atribute, fara eval (Setup.py foloseste eval pe
# fisierul imaginii; aici cererea vine din retea, deci numai randurile din setup.xml, si numai prin getattr).
# Se deschid numai ecranele la care duce o intrare de meniu pe care o vede si televizorul (meniu_web.cheiSetup).
#
# Rute (poarta comuna a HdsJsonResource; ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF):
#   GET  /api/setari                           lista ecranelor de setari din meniu
#   GET  /api/setari?id=<cheie>                randurile ecranului
#   POST /api/setari-seteaza?id=<cheie>&r<N>=<valoare>...   schimba si salveaza randurile trimise (N = numarul
#                                               randului in lista de mai sus); o valoare straina nu schimba nimic
#   GET  /setari                               pagina (?id=<cheie> alege ecranul)
#
# Sub lista ecranelor, caseta discreta „Interfața web” cu randul „Cere codul și în rețeaua
# locală” (acelasi ca pe televizor, in ecranul interfetei web) si nota „Asocierea cu cod e oprită în rețeaua locală”
# cand e oprita. Rutele ei sunt in plugin.py (/api/interfata-web, /api/interfata-web-seteaza).
# tot acolo randurile „Aplicații de telefon” (pornit din fabrica, din casa fara
# parola) si „Acces din afara casei” (oprit din fabrica; pornit, din afara numai cu utilizatorul root si parola pentru
# aplicatii), aceleasi ca pe televizor, cu parola, aplicatiile conectate si „Fă altă parolă pentru aplicații”
# (aplicatii_web.py). Integrarea 0.2.4: cu „Cere codul și în rețeaua locală” pornit, notele spun ca aplicatiile cer
# parola si din casa.
#
# primul rand al casetei e „Tema interfeței web” (Clasic sau Pro, cadru_web.py),
# aplicata pe loc si tinuta minte in acest browser (cookie-ul hds_tema), nu pe receptor.
# randul a devenit caseta „Aspectul interfeței web”, facuta dupa ecranul Stitch „Tema și
# culori” (design-web-stitch/tema-si-culori.png si clasic/tema-si-culori.png): 1. tema (Clasic, Pro), doua cartonase
# cu o previzualizare mica; 2. schema de culori: „Ca pe televizor” (implicit, culorile skinului), paleta skinului
# HD Satelit si familiile de palete de pe televizor, fiecare cu variantele ei (palete.txt din HdsSkinSetari, ca pe
# televizor: familia, apoi varianta); 3. unde se tine minte: alegerea se aplica pe loc in acest browser (cookie-urile
# hds_tema si hds_culori), iar „Fă-le implicite pe receptor” le pune pentru browserele fara alegere proprie.
# Tema si culorile web sunt ale interfetei web: nu schimba nimic pe televizor (skinul isi are alegerea lui).
# Rutele: GET /api/tema-web (implicitele de pe receptor si paletele) si POST /api/tema-web-seteaza?tema=&culori=.
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2; setup.xml (~10 KB) se citeste numai cand se schimba.

import os
import xml.etree.ElementTree as ET

CALE_SETUP = None          # probele pun aici un setup.xml; pe receptor: ${datadir}/enigma2/setup.xml
MAX_RANDURI = 80
MAX_CIFRE = 999999999      # un ConfigNumber n-are limita; pagina primeste cel mult 9 cifre


def _t(text):
	"""Traducerea enigma2; un text gol ramane gol (gettext ar da antetul fisierului .po)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _jurnal(text):
	print("[HdsWebControl] setari: %s" % text)


_CACHE = {"cale": None, "semn": None, "radacina": None}


def _caleSetup():
	if CALE_SETUP:
		return CALE_SETUP
	try:
		from enigma import eEnv
		return eEnv.resolve("${datadir}/enigma2/setup.xml")
	except Exception:
		return "/usr/share/enigma2/setup.xml"


def _radacina():
	cale = _caleSetup()
	try:
		semn = os.path.getmtime(cale)
	except OSError:
		semn = None
	if _CACHE["radacina"] is None or _CACHE["cale"] != cale or _CACHE["semn"] != semn:
		try:
			radacina = ET.parse(cale).getroot()
		except Exception as eroare:
			_jurnal("nu pot citi %s: %s" % (cale, eroare))
			radacina = None
		_CACHE.update(cale=cale, semn=semn, radacina=radacina)
	return _CACHE["radacina"]


def _nodSetup(cheie):
	radacina = _radacina()
	if radacina is None:
		return None
	for x in radacina.findall("setup"):
		if x.get("key") == cheie:
			return x
	return None


def titlu(cheie):
	nod = _nodSetup(cheie)
	return _t(nod.get("title", "")) if nod is not None else ""


def _config(config=None):
	if config is not None:
		return config
	from Components.config import config as c
	return c


def _nivel(config):
	try:
		return int(config.usage.setup_level.index)
	except Exception:
		return 0


def _cerinta(nume, SystemInfo=None):
	"""requires= din setup.xml, ca Setup.addItems: SystemInfo.get(nume, False)."""
	if not nume:
		return True
	if SystemInfo is None:
		try:
			from Components.SystemInfo import SystemInfo
		except Exception:
			return True
	return bool(SystemInfo.get(nume, False))


def _element(config, cale):
	"""Setarea pentru textul unui rand („config.av.downmix_ac3”), prin getattr; None daca nu exista."""
	parti = (cale or "").strip().split(".")
	if len(parti) < 2 or parti[0] != "config" or not all(p.isidentifier() and not p.startswith("_") for p in parti):
		return None
	obiect = config
	for p in parti[1:]:
		try:
			obiect = getattr(obiect, p)
		except Exception:
			return None
	return obiect


def _fel(el):
	"""'bool', 'alegere', 'multime', 'numar', 'glisor', 'cifre', 'text' sau 'citire', dupa clasa setarii (numele
	claselor din config.py)."""
	clase = [c.__name__ for c in type(el).__mro__]
	if "ConfigNothing" in clase:
		return None
	if "ConfigBoolean" in clase:
		return "bool"
	if "ConfigSelection" in clase:
		return "alegere"
	if "ConfigSet" in clase:
		return "multime"        # alegere multipla: pe televizor stanga/dreapta si OK bifeaza fiecare alegere
	if "ConfigSlider" in clase:
		return "glisor"
	if "ConfigInteger" in clase and "ConfigPIN" not in clase:
		return "numar"
	if "ConfigNumber" in clase:
		return "cifre"          # numar fara limite scrise (ConfigNumber): pe televizor se scrie cu cifrele
	if "ConfigText" in clase and "ConfigPassword" not in clase and _lungimeText(el):
		return "text"           # text care se scrie si din web: setarea spune cat de lung (web_text_max)
	return "citire"


def _lungimeText(el):
	"""web_text_max al unei setari text (cate caractere primeste din web), sau 0 daca textul nu se schimba din web."""
	try:
		n = int(getattr(el, "web_text_max", 0) or 0)
	except (TypeError, ValueError):
		return 0
	return n if 0 < n <= 80 else 0


def _textGol(el):
	"""Ce arata casuta goala (valoarea implicita a setarii), din web_text_gol: un text sau o functie."""
	gol = getattr(el, "web_text_gol", None)
	try:
		gol = gol() if callable(gol) else gol
	except Exception as eroare:
		_jurnal("web_text_gol: %s" % eroare)
		return ""
	return str(gol or "")


def _textStare(nod):
	try:
		from Components import HdsStareMeniu
		return HdsStareMeniu.textNod(nod, _t)
	except ImportError:
		return _t(nod.get("text") or "??")


def _randuri(cheie, config, SystemInfo=None):
	"""[(nodul, setarea)] vizibile, in ordinea si cu regulile lui Setup.addItems."""
	nod = _nodSetup(cheie)
	if nod is None:
		return []
	nivel = _nivel(config)
	rez = []
	for x in nod:
		if x.tag != "item":
			continue
		try:
			nivel_rand = int(x.get("level", 0))
		except (TypeError, ValueError):
			nivel_rand = 0
		if nivel_rand > nivel:
			continue
		if not _cerinta(x.get("requires"), SystemInfo):
			continue
		el = _element(config, x.text)
		if el is None or _fel(el) is None:
			continue
		rez.append((x, el))
		if len(rez) >= MAX_RANDURI:
			break
	return rez


def _alegeri(el, fel):
	if fel == "bool":
		d = getattr(el, "descriptions", {False: "no", True: "yes"})
		return [["0", _t(d[False]) if d[False] else "0"], ["1", _t(d[True]) if d[True] else "1"]]
	rez = []
	for x in el.choices.choices if isinstance(el.choices.choices, list) else list(el.choices.choices.items()):
		if isinstance(x, tuple):
			rez.append([str(x[0]), _t(str(x[1])) if x[1] else str(x[0])])
		else:
			rez.append([str(x), _t(str(x))])
	return rez


def _alegeriMultime(el):
	"""[[valoare, textul de pe televizor]] ale unui ConfigSet: textul e cel din ConfigSet.genString (description)."""
	return [[str(c), str(el.description[c])] for c in el.choices]


def _descriere(el, fel):
	d = {"fel": fel}
	if fel == "bool":
		d["valoare"] = "1" if el.value else "0"
		d["alegeri"] = _alegeri(el, fel)
	elif fel == "alegere":
		d["valoare"] = str(el.value)
		d["alegeri"] = _alegeri(el, fel)
	elif fel == "multime":
		d["valoare"] = [str(c) for c in el.value]
		d["alegeri"] = _alegeriMultime(el)
	elif fel == "numar":
		minim, maxim = el.limits[0]
		d.update(valoare=str(el.value), min=int(minim), max=int(maxim), pas=1)
	elif fel == "glisor":
		d.update(valoare=str(el.value), min=int(el.min), max=int(el.max), pas=int(el.increment or 1))
	elif fel == "cifre":
		d.update(valoare=str(el.value), min=0, max=MAX_CIFRE, pas=1)
	elif fel == "text":
		d.update(valoare=str(el.value or ""), max=_lungimeText(el), gol=_textGol(el))
	else:
		try:
			d["valoare_text"] = el.getText()
		except Exception:
			d["valoare_text"] = ""
	return d


def ecran(cheie, config=None, SystemInfo=None):
	"""GET /api/setari?id=<cheie>."""
	config = _config(config)
	nod = _nodSetup(cheie)
	if nod is None:
		return {"result": False, "message": _t("Ecranul de setări „%s” nu există.") % cheie[:40]}
	randuri = []
	for i, (x, el) in enumerate(_randuri(cheie, config, SystemInfo)):
		r = _descriere(el, _fel(el))
		r.update(nr=i, text=_textStare(x), ajutor=_t(x.get("description")) if x.get("description") else "",
			setare=(x.text or "").strip())
		randuri.append(r)
	return {"result": True, "id": cheie, "titlu": _t(nod.get("title", "")), "randuri": randuri}


def _valoareNoua(el, fel, text):
	"""Valoarea de pus pentru textul primit, sau (None, motivul) daca nu e una din valorile televizorului."""
	if fel == "bool":
		if text not in ("0", "1"):
			return None
		return text == "1"
	if fel == "alegere":
		for v in el.choices:
			if str(v) == text:
				return v
		return None
	if fel == "multime":
		# "2,8,16": fiecare bucata e una din alegeri, o singura data; gol = nicio alegere (si pe televizor se pot scoate
		# toate). Lista iese in ordinea alegerilor, ca dupa toggleChoice.
		alegeri = list(el.choices)
		if text == "":
			return []
		alese = []
		for bucata in text.split(","):
			gasita = [i for i, v in enumerate(alegeri) if str(v) == bucata]
			if not gasita or gasita[0] in alese:
				return None
			alese.append(gasita[0])
		return [alegeri[i] for i in sorted(alese)]
	if fel == "cifre":
		# ca tastele cifrelor pe televizor: numai cifre (zerourile din fata cad, ConfigNumber.conform)
		if not text.isdigit() or int(text) > MAX_CIFRE:
			return None
		return int(text)
	if fel == "text":
		# ca pe televizor orice litera, dar fara caractere de control si cel mult web_text_max; gol = implicitul
		text = text.strip()
		if len(text) > _lungimeText(el) or any(ord(c) < 0x20 or 0x7F <= ord(c) < 0xA0 for c in text):
			return None
		return text
	if fel in ("numar", "glisor"):
		try:
			n = int(text)
		except (TypeError, ValueError):
			return None
		if fel == "numar":
			minim, maxim = el.limits[0]
		else:
			minim, maxim = el.min, el.max
			pas = int(el.increment or 1)
			if (n - minim) % pas:
				return None
		if n < minim or n > maxim:
			return None
		return n
	return None


def seteaza(cheie, valori, config=None, SystemInfo=None, configfile=None):
	"""POST /api/setari-seteaza: {"r<N>": text}. Toate valorile trebuie sa fie bune, altfel nu se schimba nimic."""
	config = _config(config)
	if _nodSetup(cheie) is None:
		return {"result": False, "message": _t("Ecranul de setări „%s” nu există.") % cheie[:40]}
	randuri = _randuri(cheie, config, SystemInfo)
	noi = []
	for nume, text in valori.items():
		if not nume.startswith("r") or not nume[1:].isdigit():
			continue
		i = int(nume[1:])
		if i >= len(randuri):
			rez = ecran(cheie, config, SystemInfo)
			rez.update(result=False, message=_t("Lista setărilor s-a schimbat. Pagina se încarcă din nou."))
			return rez
		x, el = randuri[i]
		fel = _fel(el)
		v = _valoareNoua(el, fel, text)
		if v is None:
			rez = ecran(cheie, config, SystemInfo)
			rez.update(result=False, message=_t("Valoarea „%s” nu e bună pentru „%s”.") % (text[:40], _textStare(x)))
			return rez
		noi.append((el, v))
	if not noi:
		rez = ecran(cheie, config, SystemInfo)
		rez.update(result=False, message=_t("Nu s-a trimis nicio setare."))
		return rez
	for el, v in noi:
		if el.value != v:
			el.value = v
		# ca la parasirea randului pe televizor (ConfigElement.onDeselect), apoi ca la Verde (save). O lista (ConfigSet)
		# se tine minte ca o copie, ca in ConfigSet.onDeselect: toggleChoice o schimba pe loc
		if getattr(el, "last_value", None) != el.value:
			try:
				el.changedFinal()
			except Exception as eroare:
				_jurnal("changedFinal: %s" % eroare)
			el.last_value = el.value[:] if isinstance(el.value, list) else el.value
		el.save()
	if configfile is None:
		from Components.config import configfile
	configfile.save()
	rez = ecran(cheie, config, SystemInfo)
	rez.update(result=True, message=_t("Salvat."))
	return rez


def argumente(request):
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:MAX_RANDURI + 4]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie != "id" and not (cheie.startswith("r") and cheie[1:].isdigit() and len(cheie) <= 4):
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:80].strip()
	return rez


def rute(baza, resource, chei=None):
	"""({nume: resursa}, resursa paginii). `chei()` da ecranele permise: [(cheie, textul intrarii de meniu)], din
	meniu_web.cheiSetup (numai ce vede si televizorul)."""

	def _permise():
		try:
			return chei() if chei is not None else []
		except Exception as eroare:
			_jurnal("lista ecranelor: %s" % eroare)
			return []

	class StareResource(baza):
		def render_GET(self, request):
			a = argumente(request)
			cheie = a.get("id", "")
			permise = _permise()
			if not cheie:
				return self._raspunde(request, {"result": True, "ecrane": [{"id": c, "text": t, "titlu": titlu(c)}
					for c, t in permise]})
			if cheie not in [c for c, _t2 in permise]:
				return self._eroare(request, _t("Ecranul de setări „%s” nu e în meniu.") % cheie[:40], 404)
			try:
				return self._raspunde(request, ecran(cheie))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class SeteazaResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			a = argumente(request)
			cheie = a.pop("id", "")
			if cheie not in [c for c, _t2 in _permise()]:
				return self._eroare(request, _t("Ecranul de setări „%s” nu e în meniu.") % cheie[:40], 404)
			try:
				return self._raspunde(request, seteaza(cheie, a))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)

	class PaginaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	class TemaWebResource(baza):
		"""GET /api/tema-web: implicitele interfetei web de pe receptor (tema, culorile) si paletele de ales."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stareTemaWeb())
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class TemaWebSeteazaResource(baza):
		"""POST /api/tema-web-seteaza?tema=clasic|pro&culori=<id>: implicitele pentru browserele fara alegere proprie.
		Numai interfata web: skinul si alegerea de pe televizor raman neatinse."""
		schimbaCeva = True

		def render_POST(self, request):
			a = getattr(request, "args", None) or {}

			def unu(nume):
				v = (a.get(nume) or [b""])[0]
				v = v.decode("ascii", "replace") if isinstance(v, bytes) else str(v)
				return v.strip()[:40] or None
			try:
				rezultat = seteazaTemaWeb(unu(b"tema"), unu(b"culori"))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)
			return self._raspunde(request, rezultat, 200 if rezultat.get("result") else 400)

		def render_GET(self, request):
			return self.render_POST(request)

	api = {b"setari": StareResource(), b"setari-seteaza": SeteazaResource(), b"tema-web": TemaWebResource(),
		b"tema-web-seteaza": TemaWebSeteazaResource()}
	return api, PaginaResource()


def _cadru():
	from . import cadru_web
	return cadru_web


def stareTemaWeb():
	"""Pentru /api/tema-web: implicitele de pe receptor si alegerile (paletele de pe televizor, pe familii)."""
	C = _cadru()
	tema, culori = C.implicite()
	rez = {"result": True, "tema_implicita": tema, "culori_implicite": culori,
		"nume_culori_implicite": C.numePaleta(culori), "teme": list(C.TEME)}
	rez.update(C.listaCulori())
	return rez


def seteazaTemaWeb(tema, culori):
	if tema is None and culori is None:
		return {"result": False, "message": _t("Alege tema sau schema de culori.")}
	return _cadru().seteazaImplicite(tema, culori)


def pagina(request):
	from . import plugin as P
	if not P._esteAdresaLocala(P._adresaClient(request)):
		request.setResponseCode(403)
		request.setHeader(b"content-type", b"text/plain; charset=utf-8")
		return _t("Acces permis doar din rețeaua locală.").encode("utf-8")
	P._anteteHtml(request)
	if P.PARAM_JETON in request.args and P._jetonValid(request):
		config_pagina = P._configPanou("", P._jetonConfigurat(), "")
	else:
		secret, browser = P._sesiuneDinCerere(request)
		if browser is None:
			return P._PAGINA_ASOCIERE.encode("utf-8")
		config_pagina = P._configPanou(P.csrfPentru(secret), "", browser.get("nume", ""))
	return pagina_text(P._STIL_COMUN, config_pagina).encode("utf-8", "replace")


def _drumMeniu(id_intrare):
	"""Drumul de pe televizor spre ecran (meniu_web.drumHtml); modulul incarcat singur, fara pachet (probele de pe
	PC), nu are meniul, deci ramane „Meniu”."""
	try:
		from .meniu_web import drumHtml
	except ImportError:
		return "Meniu"
	return drumHtml(id_intrare)


def _nivelHtml():
	"""Numele setarii nivelului (config.usage.setup_level) cum il arata televizorul."""
	import html
	return html.escape(_t("Setup Mode"), quote=False)


def pagina_text(stil, config_pagina):
	return _traducePagina(PAGINA).replace("__STIL_COMUN__", stil).replace("__CONFIG__",
		config_pagina).replace("__NIVEL__",
		_nivelHtml()).replace("__DRUM_MENIU__", _drumMeniu("usage_setup"))


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Setări</title>
<style>__STIL_COMUN__
  main{max-width:820px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .rand{display:grid;grid-template-columns:1fr minmax(160px,280px);gap:6px 10px;align-items:center;padding:10px 0;border-bottom:1px solid var(--bordura);}
  .rand:last-child{border-bottom:0;}
  .rand label{font-size:.98rem;}
  .rand .ajutor{grid-column:1/-1;color:var(--text-slab);font-size:.82rem;line-height:1.4;margin:0;}
  .rand .citire{color:var(--text-slab);}
  .rand .multime{display:flex;flex-wrap:wrap;gap:4px 14px;}
  .rand .multime label{display:inline-flex;align-items:center;gap:8px;min-height:44px;font-size:.95rem;}
  .rand .multime input{width:22px;height:22px;min-height:0;padding:0;margin:0;}
  select,input{min-height:44px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;width:100%;}
  button{min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  button.verde{background:var(--verde);border-color:var(--verde);color:#fff;}
  .butoane{display:flex;flex-wrap:wrap;gap:10px;margin-top:12px;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
  ul.ecrane{list-style:none;padding:0;margin:0;}
  ul.ecrane li{padding:8px 0;border-bottom:1px solid var(--bordura);}
  a.inapoi{color:var(--text-slab);font-size:.9rem;}
  #interfataWeb h2{font-size:1rem;margin:0 0 4px;color:var(--text-slab);font-weight:600;}
  /* Aspectul interfetei web: dupa ecranul Stitch „Tema și culori” (Pro: cartonase de sticla cu bifa rotunda si
     mostre rotunde; Clasic: cartonase pline cu chenar chihlimbariu la cel ales si mostre in banda) */
  .aspect-pas{margin:20px 0 10px;}
  .aspect-pas h3{margin:0;font-size:1.05rem;font-weight:700;display:flex;align-items:center;gap:8px;}
  .aspect-pas h3::before{content:"";width:6px;height:6px;border-radius:50%;background:var(--marca,#9fb4ff);}
  .aspect-sub{margin:4px 0 0;color:var(--text-slab);font-size:.85rem;line-height:1.45;}
  .teme-alegere{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px;}
  .tema-card{position:relative;display:flex;flex-direction:column;gap:10px;padding:16px;cursor:pointer;
    background:var(--panou-2,#181c23);border:1px solid var(--bordura);border-radius:12px;}
  .tema-card input{position:absolute;opacity:0;width:1px;height:1px;}
  .tema-card:has(input:focus-visible){outline:2px solid var(--marca,#9fb4ff);outline-offset:2px;}
  .tema-cap{display:flex;align-items:center;gap:12px;}
  .tema-ic{display:inline-flex;align-items:center;justify-content:center;width:40px;height:40px;border-radius:10px;
    background:var(--buton);border:1px solid var(--bordura);color:var(--text-2,var(--text));flex:none;}
  .tema-ic svg{width:22px;height:22px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;}
  .tema-nume{display:flex;flex-direction:column;gap:2px;min-width:0;}
  .tema-nume b{font-size:1.05rem;}
  .tema-nume small{align-self:flex-start;font-size:.7rem;font-weight:700;letter-spacing:.04em;padding:1px 7px;border-radius:4px;
    background:var(--buton);color:var(--text-slab);}
  .tema-bifa{margin-left:auto;width:22px;height:22px;border-radius:50%;border:2px solid var(--text-slab);flex:none;}
  .tema-card.aleasa{border:2px solid var(--marca,#9fb4ff);padding:15px;background:var(--panou);}
  .tema-card.aleasa .tema-bifa{border-color:var(--marca,#9fb4ff);background:var(--marca,#9fb4ff);
    box-shadow:inset 0 0 0 4px var(--panou);}
  .tema-card.aleasa .tema-nume small{background:var(--accent);color:#fff;}
  .tema-text{color:var(--text-2,var(--text-slab));font-size:.85rem;line-height:1.45;}
  .tema-mini{display:flex;gap:6px;height:84px;padding:8px;border-radius:8px;background:var(--fundal);border:1px solid var(--bordura);overflow:hidden;}
  .tema-mini i{display:block;}
  .mini-clasic{flex-direction:column;gap:3px;}
  .mini-clasic .m-titlu{width:42%;height:9px;border-radius:2px;background:var(--text-slab);opacity:.8;}
  .mini-clasic .m-linie{height:2px;background:var(--chihlimbar);margin-bottom:4px;}
  .mini-clasic .m-rand{flex:1;border-radius:2px;background:var(--rand,var(--panou-2));}
  .mini-clasic .m-ales{background:var(--ales);box-shadow:inset 4px 0 0 var(--chihlimbar);}
  .mini-pro .m-bara{width:22%;border-radius:4px;background:var(--meniu-fundal,var(--panou));border:1px solid var(--bordura);
    box-shadow:inset 0 10px 0 -4px var(--ales);}
  .mini-pro .m-loc{flex:1;display:grid;grid-template-columns:1fr 1fr;gap:5px;}
  .mini-pro .m-card{border-radius:5px;background:var(--panou);border:1px solid var(--bordura);}
  .mini-pro .m-lat{grid-column:1/-1;}
  .culori-alegere{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;}
  #aspectWeb .paleta-card{display:flex;flex-direction:column;align-items:stretch;gap:10px;text-align:left;padding:14px;min-height:0;
    background:var(--panou-2,#181c23);border:1px solid var(--bordura);border-radius:12px;color:var(--text);cursor:pointer;font:inherit;}
  #aspectWeb .paleta-card .p-cap{display:flex;align-items:center;gap:8px;font-weight:700;}
  #aspectWeb .paleta-card .p-cap small{font-weight:600;font-size:.7rem;padding:1px 6px;border-radius:4px;background:var(--buton);color:var(--text-slab);}
  #aspectWeb .paleta-card .p-sub{color:var(--text-slab);font-size:.78rem;font-weight:400;}
  #aspectWeb .paleta-card[aria-pressed="true"],#aspectWeb .paleta-card.deschisa{border:2px solid var(--marca,#9fb4ff);padding:13px;background:var(--panou);}
  .mostre{display:flex;gap:6px;align-items:center;}
  .mostre i{display:block;width:26px;height:26px;border-radius:50%;border:1px solid rgba(127,127,127,.45);}
  .variante{margin-top:12px;padding:14px;border-radius:12px;border:1px solid var(--bordura);background:var(--panou-2,#181c23);}
  .culori-alegere .variante{grid-column:1 / -1;margin-top:0;}
  .variante-lista{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px;margin-top:10px;}
  #aspectWeb .varianta{display:flex;flex-direction:column;gap:6px;align-items:flex-start;padding:10px;border-radius:8px;font:inherit;font-size:.82rem;
    background:var(--buton);border:1px solid var(--bordura);color:var(--text);cursor:pointer;}
  #aspectWeb .varianta[aria-pressed="true"]{border:2px solid var(--marca,#9fb4ff);padding:9px;}
  #aspectWeb .varianta .mostre i{width:20px;height:20px;}
  html[data-tema="clasic"] .tema-card,html[data-tema="clasic"] #aspectWeb .paleta-card,html[data-tema="clasic"] .variante{border-radius:4px;background:var(--rand);border-color:transparent;}
  html[data-tema="clasic"] .tema-card.aleasa,html[data-tema="clasic"] #aspectWeb .paleta-card[aria-pressed="true"],
  html[data-tema="clasic"] #aspectWeb .paleta-card.deschisa,html[data-tema="clasic"] #aspectWeb .varianta[aria-pressed="true"]{border-color:var(--chihlimbar);background:var(--ales);}
  html[data-tema="clasic"] .tema-card.aleasa .tema-bifa{border-color:var(--chihlimbar);background:var(--chihlimbar);box-shadow:inset 0 0 0 4px var(--ales);}
  html[data-tema="clasic"] .tema-card.aleasa .tema-nume b{color:var(--ales-text);}
  html[data-tema="clasic"] .tema-card.aleasa .tema-nume small{background:transparent;color:var(--chihlimbar);border:1px solid var(--chihlimbar);}
  html[data-tema="clasic"] .aspect-pas h3::before{background:var(--chihlimbar);}
  html[data-tema="clasic"] .mostre{gap:0;}
  html[data-tema="clasic"] .mostre i{flex:1;width:auto;height:28px;border-radius:0;border:0;}
  html[data-tema="clasic"] #aspectWeb .varianta{border-radius:4px;align-items:stretch;}
  html[data-tema="clasic"] .tema-ic{background:transparent;border-color:var(--bordura);}
  .rand.ales{background:#22304a;border-radius:8px;padding-left:10px;padding-right:10px;}
  form.cauta-setari{display:flex;gap:8px;margin:0 0 14px;}
  form.cauta-setari input{flex:1;min-height:44px;padding:8px 12px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;}
  form.cauta-setari button{min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  @media (max-width:560px){ .rand{grid-template-columns:1fr;} }
</style>
</head>
<body>
<main>
<p><a class="inapoi" id="inapoi" href="/meniu">Înapoi la meniu</a></p>
<h1 id="titlu">Setări</h1>
<form class="cauta-setari" action="/cauta-setari" method="get" role="search"><input type="search" name="q" maxlength="60" placeholder="Caută setări" aria-label="Caută setări" autocomplete="off"><button type="submit">Caută</button></form>
<p class="mesaj" id="incarcare">Se citesc setările...</p>
<section class="card ascuns" id="lista"><ul class="ecrane" id="ecrane"></ul></section>
<section class="card ascuns" id="aspectWeb" aria-labelledby="aspectTitlu">
  <h2 id="aspectTitlu">Aspectul interfeței web</h2>
  <p class="nota aspect-intro">Tema și culorile paginilor web. Sunt numai ale interfeței web: tema și culorile de pe televizor nu se schimbă de aici.</p>
  <div class="aspect-pas"><h3>1. Tema interfeței web</h3><p class="aspect-sub">Cum arată paginile: meniul, butoanele, cardurile, rândurile.</p></div>
  <div class="teme-alegere" role="radiogroup" aria-label="Tema interfeței web">
    <label class="tema-card" data-tema-card="clasic"><input type="radio" name="temaWeb" value="clasic">
      <span class="tema-cap"><span class="tema-ic" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M3 5h18v12H3zM8 21h8"/></svg></span><span class="tema-nume"><b>Clasic</b><small>Aerisită</small></span><span class="tema-bifa" aria-hidden="true"></span></span>
      <span class="tema-text">Ca meniul de pe televizor: rânduri mari, titlul cu linie chihlimbarie, meniul se deschide din butonul Meniu.</span>
      <span class="tema-mini mini-clasic" aria-hidden="true"><i class="m-titlu"></i><i class="m-linie"></i><i class="m-rand m-ales"></i><i class="m-rand"></i><i class="m-rand"></i></span>
    </label>
    <label class="tema-card" data-tema-card="pro"><input type="radio" name="temaWeb" value="pro">
      <span class="tema-cap"><span class="tema-ic" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z"/></svg></span><span class="tema-nume"><b>Pro</b><small>Densă</small></span><span class="tema-bifa" aria-hidden="true"></span></span>
      <span class="tema-text">Mai multe lucruri pe ecran; pe ecranele late meniul stă mereu în stânga.</span>
      <span class="tema-mini mini-pro" aria-hidden="true"><i class="m-bara"></i><span class="m-loc"><i class="m-card"></i><i class="m-card"></i><i class="m-card m-lat"></i></span></span>
    </label>
  </div>
  <div class="aspect-pas"><h3>2. Schema de culori</h3><p class="aspect-sub">Culorile paginilor web: aceleași palete ca pe televizor, alese separat. Întâi familia, apoi varianta.</p></div>
  <div class="culori-alegere" id="culoriAlegere"><p class="nota">Se citesc paletele...</p></div>
  <div class="variante ascuns" id="variante"><p class="aspect-sub" id="varianteTitlu"></p><div class="variante-lista" id="varianteLista"></div></div>
  <div class="aspect-pas"><h3>3. Unde se ține minte</h3><p class="aspect-sub" id="aspectStare"></p></div>
  <div class="butoane"><button type="button" class="verde" id="aspectImplicit">Fă-le implicite pe receptor</button>
    <button type="button" id="aspectRevino">Revino la implicitele receptorului</button></div>
  <p class="mesaj" id="aspectMesaj"></p>
</section>
<section class="card ascuns" id="interfataWeb">
  <h2>Interfața web</h2>
  <div class="rand"><label for="codRetea">Cere codul și în rețeaua locală</label>
    <select id="codRetea"><option value="0">Nu</option><option value="1">Da</option></select>
    <p class="ajutor" id="codReteaNota"></p></div>
  <div class="rand"><label for="aplicatii">Aplicații de telefon</label>
    <select id="aplicatii"><option value="0">Nu</option><option value="1">Da</option></select>
    <p class="ajutor" id="aplicatiiNota"></p></div>
  <div class="rand"><label for="aplicatiiAfara">Acces din afara casei</label>
    <select id="aplicatiiAfara"><option value="0">Nu</option><option value="1">Da</option></select>
    <p class="ajutor" id="aplicatiiAfaraNota"></p></div>
  <div class="butoane"><button type="button" id="codReteaSalveaza">Salvează</button>
    <button type="button" class="ascuns" id="parolaAplicatii">Fă altă parolă pentru aplicații</button></div>
  <p class="mesaj" id="codReteaMesaj"></p>
</section>
<div id="continut" class="ascuns">
  <section class="card"><div id="randuri"></div>
    <div class="butoane"><button type="button" class="verde" id="salveaza">Salvează</button></div>
  </section>
  <p class="nota">Aceleași rânduri, cu aceleași alegeri, sunt pe televizor în ecranul cu același nume. Rândurile care se văd depind de „__NIVEL__”, ales pe televizor în __DRUM_MENIU__. Setările fără listă de alegeri se schimbă de pe televizor.</p>
</div>
<p class="mesaj" id="mesaj"></p>
</main>
<script>
var CFG = __CONFIG__;
var ID = new URLSearchParams(location.search).get("id") || "";
// venit din „Caută setări” (/setari?id=...&setare=config...): randul cautat e ales si adus in fata o data
var SETARE = new URLSearchParams(location.search).get("setare") || "";
var SETARE_ARATATA = false;
var DATE = null;
function $(id){ return document.getElementById(id); }
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
function cerere(cale, metoda, date){
  var optiuni = {method: metoda || "GET", cache: "no-store", credentials: "same-origin", headers: {}};
  if(CFG.csrf){ optiuni.headers["X-HDS-CSRF"] = CFG.csrf; }
  if(date){
    optiuni.headers["Content-Type"] = "application/x-www-form-urlencoded";
    optiuni.body = date.toString();
  }
  return fetch(adresa(cale), optiuni).then(function(r){
    if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("browser deconectat"); }
    return r.json().catch(function(){ return {result: false, message: "Receptorul a răspuns neașteptat (HTTP " + r.status + ")."}; });
  });
}
function mesaj(text, eroare){ var m = $("mesaj"); m.textContent = text || ""; m.classList.toggle("eroare", !!eroare); }
function control(r){
  var c;
  if(r.fel === "bool" || r.fel === "alegere"){
    c = document.createElement("select");
    (r.alegeri || []).forEach(function(a){ var o = document.createElement("option"); o.value = a[0]; o.textContent = a[1]; c.appendChild(o); });
    c.value = r.valoare;
  } else if(r.fel === "multime"){
    // alegere multipla (ConfigSet): o bifa pentru fiecare alegere, ca OK pe fiecare alegere pe televizor
    c = document.createElement("div"); c.className = "multime"; c.setAttribute("role", "group"); c.setAttribute("aria-label", r.text);
    var alese = {};
    (r.valoare || []).forEach(function(v){ alese[v] = true; });
    (r.alegeri || []).forEach(function(a){
      var l = document.createElement("label"), b = document.createElement("input");
      b.type = "checkbox"; b.value = a[0]; b.checked = !!alese[a[0]];
      l.appendChild(b); l.appendChild(document.createTextNode(a[1])); c.appendChild(l);
    });
    c.id = "r" + r.nr; c.setAttribute("data-inainte", (r.valoare || []).join(","));
    return c;
  } else if(r.fel === "numar" || r.fel === "glisor" || r.fel === "cifre"){
    c = document.createElement("input"); c.type = "number"; c.min = r.min; c.max = r.max; c.step = r.pas; c.value = r.valoare;
  } else if(r.fel === "text"){
    // text scris si din web (de pilda numele receptorului pe televizor); casuta goala arata valoarea implicita
    c = document.createElement("input"); c.type = "text"; c.maxLength = r.max; c.value = r.valoare || "";
    c.placeholder = r.gol || ""; c.autocomplete = "off"; c.spellcheck = false;
  } else {
    c = document.createElement("span"); c.className = "citire"; c.textContent = r.valoare_text || ""; return c;
  }
  c.id = "r" + r.nr; c.setAttribute("data-inainte", r.valoare);
  return c;
}
// valoarea de trimis a unui rand: la alegerea multipla, alegerile bifate despartite prin virgula, in ordinea lor
function valoareControl(r, c){
  if(r.fel === "multime"){
    return Array.prototype.filter.call(c.querySelectorAll("input[type=checkbox]"), function(b){ return b.checked; })
      .map(function(b){ return b.value; }).join(",");
  }
  return c.value;
}
function arata(d){
  DATE = d;
  $("titlu").textContent = d.titlu;
  document.title = d.titlu;
  var c = $("randuri"); c.textContent = "";
  var ales = null;
  d.randuri.forEach(function(r){
    var div = document.createElement("div"); div.className = "rand";
    if(SETARE && r.setare === SETARE){ div.className = "rand ales"; ales = div; }
    var l = document.createElement("label"); l.textContent = r.text; l.setAttribute("for", "r" + r.nr);
    div.appendChild(l); div.appendChild(control(r));
    if(r.ajutor){ var p = document.createElement("p"); p.className = "ajutor"; p.textContent = r.ajutor; div.appendChild(p); }
    c.appendChild(div);
  });
  if(!d.randuri.length){ var n = document.createElement("p"); n.className = "nota"; n.textContent = "Niciun rând de arătat la nivelul ales."; c.appendChild(n); }
  if(ales && !SETARE_ARATATA){
    SETARE_ARATATA = true;
    ales.scrollIntoView({block: "center"});
    var x = ales.querySelector("select,input"); if(x){ x.focus(); }
  }
}
function notaCodRetea(d){
  var n = d.cod_retea_locala
    ? "Fiecare browser sau telefon nou din rețeaua locală are nevoie o dată de codul arătat pe televizor."
    : "Asocierea cu cod e oprită în rețeaua locală: browserele și telefoanele din casă intră fără cod. Din afara rețelei locale receptorul nu răspunde.";
  if(!d.cod_retea_locala && d.fara_cod){ n += " Dacă pornești codul, și acest browser va avea nevoie de codul de pe televizor."; }
  if(d.cod_retea_locala && d.aplicatii){ n += " Aplicațiile de telefon cer atunci și acasă utilizatorul root și parola pentru aplicații."; }
  n += " Același rând e pe televizor, în " + (d.drum || "Meniu") + ".";
  $("codReteaNota").textContent = n;
}
function notaAplicatii(d){
  var n, a, p = d.parola_aplicatii || "";
  if(d.aplicatii){
    n = d.cod_retea_locala
      ? "Pornit: aplicațiile obișnuite de telefon pentru receptoare Enigma2 (canale, telecomandă, ghid, înregistrări, liste m3u) intră și din casă numai cu utilizatorul root și parola pentru aplicații" + (p ? " " + p : "") + ", fiindcă rândul de mai sus cere codul și în rețeaua locală."
      : "Pornit: aplicațiile obișnuite de telefon pentru receptoare Enigma2 (canale, telecomandă, ghid, înregistrări, liste m3u) intră din casă fără parolă. În aplicație scrii adresa receptorului și portul 80; utilizatorul și parola rămân goale.";
    var v = d.aplicatii_vazute || [];
    if(v.length){ n += " Conectate: " + v.map(function(x){ return x.nume + " (" + x.adresa + ")"; }).join(", ") + "."; }
  } else {
    n = "Oprit. Pornit (cum vine din fabrică), receptorul răspunde aplicațiilor obișnuite de telefon pentru receptoare Enigma2, din casă fără parolă.";
  }
  if(d.aplicatii_afara){
    a = "Pornit: din afara rețelei locale aplicațiile intră numai cu utilizatorul root și parola pentru aplicații" + (p ? " " + p : "") + ". Pe router trimiți un port spre receptor.";
  } else {
    a = "Oprit din fabrică: din afara rețelei locale receptorul nu răspunde aplicațiilor." + (p ? " Pornit, le cere utilizatorul root și parola " + p + "." : "");
  }
  if(!d.aplicatii){ a += " Merge numai cu rândul de mai sus pornit."; }
  $("aplicatiiNota").textContent = n;
  $("aplicatiiAfaraNota").textContent = a;
  $("parolaAplicatii").classList.toggle("ascuns", !d.aplicatii);
}
function citesteInterfataWeb(){
  cerere("/api/interfata-web").then(function(d){
    if(!d.result){ return; }
    $("codRetea").value = d.cod_retea_locala ? "1" : "0";
    $("codRetea").setAttribute("data-inainte", $("codRetea").value);
    notaCodRetea(d);
    $("aplicatii").value = d.aplicatii ? "1" : "0";
    $("aplicatii").setAttribute("data-inainte", $("aplicatii").value);
    $("aplicatiiAfara").value = d.aplicatii_afara ? "1" : "0";
    $("aplicatiiAfara").setAttribute("data-inainte", $("aplicatiiAfara").value);
    notaAplicatii(d);
    $("interfataWeb").classList.remove("ascuns");
    if(location.hash === "#interfataWeb"){ $("interfataWeb").scrollIntoView({block: "start"}); }
  }).catch(function(){});
}
// aspectul interfetei web (cadru_web.py): tema si schema de culori, aplicate pe loc in acest browser (cookie-urile
// hds_tema si hds_culori); „Fă-le implicite pe receptor” le pune pentru browserele fara alegere proprie
// (/api/tema-web-seteaza). Nimic de aici nu schimba tema sau culorile de pe televizor.
var ASPECT = null;
function cookieAspect(nume){
  var m = document.cookie.match(new RegExp("(?:^|; )" + nume + "=([a-z0-9-]{1,40})(?:;|$)"));
  return m ? m[1] : "";
}
function puneCookie(nume, v){
  document.cookie = nume + "=" + v + "; Path=/; Max-Age=" + (v ? "31536000" : "0") + "; SameSite=Strict";
}
function temaAcum(){ return document.documentElement.getAttribute("data-tema") === "pro" ? "pro" : "clasic"; }
function culoriAcum(){ return document.documentElement.getAttribute("data-culori") || "tv"; }
function numeTema(t){ return t === "pro" ? "Pro" : "Clasic"; }
function numeCulori(id){
  if(!ASPECT){ return id === "tv" ? "Ca pe televizor" : id; }
  if(id === ASPECT.tv.id){ return ASPECT.tv.nume; }
  if(id === ASPECT.skin.id){ return ASPECT.skin.nume; }
  var n = id;
  ASPECT.familii.forEach(function(f){ f.palete.forEach(function(p){ if(p.id === id){ n = p.nume; } }); });
  return n;
}
function cateVariante(n){ return n === 1 ? "o variantă" : n + " variante"; }
function stareAspect(){
  var t = temaAcum(), c = culoriAcum(), proprii = !!(cookieAspect("hds_tema") || cookieAspect("hds_culori"));
  var s = "În acest browser: " + numeTema(t) + ", " + numeCulori(c) + (proprii ? " (alese aici)." : " (implicitele receptorului).");
  if(ASPECT){ s += " Implicite pe receptor, pentru browserele fără alegere proprie: " + numeTema(ASPECT.tema_implicita) + ", " + numeCulori(ASPECT.culori_implicite) + "."; }
  $("aspectStare").textContent = s;
  $("aspectRevino").disabled = !proprii;
}
function mostre(lista){
  var s = document.createElement("span"); s.className = "mostre"; s.setAttribute("aria-hidden", "true");
  (lista || []).forEach(function(c){ var i = document.createElement("i"); i.style.background = c; s.appendChild(i); });
  return s;
}
function alegeCulori(id){
  puneCookie("hds_culori", id);
  location.hash = "aspectWeb";
  location.reload();
}
function cardPaleta(titlu, sub, lista, apasat, eticheta){
  var b = document.createElement("button"); b.type = "button"; b.className = "paleta-card";
  b.setAttribute("aria-pressed", apasat ? "true" : "false");
  var cap = document.createElement("span"); cap.className = "p-cap"; cap.textContent = titlu;
  if(eticheta){ var e = document.createElement("small"); e.textContent = eticheta; cap.appendChild(e); }
  b.appendChild(cap);
  if(sub){ var p = document.createElement("span"); p.className = "p-sub"; p.textContent = sub; b.appendChild(p); }
  b.appendChild(mostre(lista));
  return b;
}
function arataVariante(f, faraDerulare){
  var V = $("variante"), A = $("culoriAlegere");
  V.classList.add("ascuns");
  var L = $("varianteLista"); L.textContent = "";
  $("varianteTitlu").textContent = f.nume + ": " + cateVariante(f.palete.length) + ". Alege una; se aplică pe loc în acest browser.";
  f.palete.forEach(function(p){
    var b = document.createElement("button"); b.type = "button"; b.className = "varianta";
    b.setAttribute("aria-pressed", p.id === culoriAcum() ? "true" : "false");
    var n = document.createElement("span"); n.textContent = p.nume; b.appendChild(n); b.appendChild(mostre(p.mostre));
    b.addEventListener("click", function(){ alegeCulori(p.id); });
    L.appendChild(b);
  });
  // variantele se deschid chiar sub randul familiei apasate (pe toata latimea grilei), nu la capatul listei, si se aduc
  // in vedere: altfel se deschideau in afara ecranului si nu se vedea ce s-a intamplat
  var card = A.querySelector('.paleta-card[data-familie="' + f.id + '"]');
  if(card){
    var dupa = card, sus = card.offsetTop;
    Array.prototype.forEach.call(A.querySelectorAll(".paleta-card"), function(x){ if(x.offsetTop === sus){ dupa = x; } });
    A.insertBefore(V, dupa.nextSibling);
  }
  V.classList.remove("ascuns");
  Array.prototype.forEach.call(document.querySelectorAll("#culoriAlegere .paleta-card"), function(x){
    x.classList.toggle("deschisa", x.getAttribute("data-familie") === f.id);
  });
  if(!faraDerulare && V.scrollIntoView){ V.scrollIntoView({block: "nearest", behavior: "smooth"}); }
}
function arataCulori(d){
  ASPECT = d;
  var A = $("culoriAlegere"), V = $("variante");
  // variantele pot sta in grila (sub familia deschisa): scoase intai, ca golirea grilei sa nu le stearga
  if(V && V.parentNode === A){ V.classList.add("ascuns"); A.parentNode.insertBefore(V, A.nextSibling); }
  A.textContent = "";
  var c = culoriAcum(), deschis = null;
  var tv = cardPaleta(d.tv.nume, "Culorile alese pe televizor, în Setări skin.", d.tv.mostre, c === d.tv.id, "Implicită");
  tv.addEventListener("click", function(){ alegeCulori(d.tv.id); });
  A.appendChild(tv);
  var sk = cardPaleta(d.skin.nume, "Paleta de bază a skinului.", d.skin.mostre, c === d.skin.id, "");
  sk.addEventListener("click", function(){ alegeCulori(d.skin.id); });
  A.appendChild(sk);
  d.familii.forEach(function(f){
    var are = f.palete.some(function(p){ return p.id === c; });
    // cartonasul familiei: fundalul si randul primei variante, apoi doua accente din variantele ei (ca sa se vada ce alegi)
    var p0 = f.palete[0] || {mostre: []}, pa = f.palete[Math.min(3, f.palete.length - 1)] || p0, pb = f.palete[Math.min(5, f.palete.length - 1)] || p0;
    var b = cardPaleta(f.nume, cateVariante(f.palete.length), [p0.mostre[0], p0.mostre[1], pa.mostre[2], pb.mostre[2]], are, "");
    b.setAttribute("data-familie", f.id);
    b.addEventListener("click", function(){ arataVariante(f); });
    A.appendChild(b);
    if(are){ deschis = f; }
  });
  if(!d.familii.length){
    var n = document.createElement("p"); n.className = "nota";
    n.textContent = "Paletele de pe televizor nu se găsesc pe receptor (lipsește skinul HDSatelit?).";
    A.appendChild(n);
  }
  if(deschis){ arataVariante(deschis, true); }
  stareAspect();
}
// cartonasul temei alese: clasa „aleasa” (fara :has(), ca sa se vada si in browserele mai vechi)
function marcheazaTema(){
  Array.prototype.forEach.call(document.querySelectorAll('input[name="temaWeb"]'), function(r){
    r.parentNode.classList.toggle("aleasa", r.checked);
  });
}
function citesteAspect(){
  $("aspectWeb").classList.remove("ascuns");
  Array.prototype.forEach.call(document.querySelectorAll('input[name="temaWeb"]'), function(r){ r.checked = r.value === temaAcum(); });
  marcheazaTema();
  stareAspect();
  cerere("/api/tema-web").then(function(d){
    if(!d.result){ $("culoriAlegere").textContent = d.message || "Receptorul nu a putut citi paletele."; return; }
    arataCulori(d);
    if(location.hash === "#aspectWeb"){ $("aspectWeb").scrollIntoView({block: "start"}); }
  }).catch(function(){ $("culoriAlegere").textContent = "Receptorul nu răspunde."; });
}
Array.prototype.forEach.call(document.querySelectorAll('input[name="temaWeb"]'), function(r){
  r.addEventListener("change", function(){
    var t = r.value === "pro" ? "pro" : "clasic";
    document.cookie = "hds_tema=" + t + "; Path=/; Max-Age=31536000; SameSite=Strict";
    document.documentElement.setAttribute("data-tema", t);
    marcheazaTema();
    stareAspect();
  });
});
$("aspectImplicit").addEventListener("click", function(){
  var q = new URLSearchParams(); q.set("tema", temaAcum()); q.set("culori", culoriAcum());
  var m = $("aspectMesaj"); m.textContent = "Se salvează..."; m.classList.remove("eroare");
  cerere("/api/tema-web-seteaza", "POST", q).then(function(d){
    m.textContent = d.message || ""; m.classList.toggle("eroare", !d.result);
    if(d.result && ASPECT){ ASPECT.tema_implicita = d.tema_implicita; ASPECT.culori_implicite = d.culori_implicite; stareAspect(); }
  }).catch(function(){ m.textContent = "Receptorul nu răspunde."; m.classList.add("eroare"); });
});
$("aspectRevino").addEventListener("click", function(){
  puneCookie("hds_tema", ""); puneCookie("hds_culori", "");
  location.hash = "aspectWeb"; location.reload();
});
$("codReteaSalveaza").addEventListener("click", function(){
  var m = $("codReteaMesaj"), cereri = [];
  [["codRetea", "cod_retea_locala"], ["aplicatii", "aplicatii"], ["aplicatiiAfara", "aplicatii_afara"]].forEach(function(x){
    var v = $(x[0]).value;
    if(v !== $(x[0]).getAttribute("data-inainte")){ var q = new URLSearchParams(); q.set(x[1], v); cereri.push(q); }
  });
  if(!cereri.length){ m.textContent = "Nu ai schimbat nimic."; m.classList.remove("eroare"); return; }
  m.textContent = "Se salvează..."; m.classList.remove("eroare");
  var mesaje = [];
  var lant = Promise.resolve(true);
  cereri.forEach(function(q){
    lant = lant.then(function(bun){
      if(!bun){ return false; }
      return cerere("/api/interfata-web-seteaza", "POST", q).then(function(d){ mesaje.push(d.message || ""); return !!d.result; });
    });
  });
  lant.then(function(bun){
    m.textContent = mesaje.join(" "); m.classList.toggle("eroare", !bun);
    citesteInterfataWeb();
  }).catch(function(){ m.textContent = "Receptorul nu răspunde."; m.classList.add("eroare"); });
});
$("parolaAplicatii").addEventListener("click", function(){
  var m = $("codReteaMesaj");
  if(!confirm("Faci o parolă nouă pentru aplicații? Din afara casei, aplicațiile care o folosesc pe cea veche nu mai primesc răspuns până nu scrii în ele parola nouă.")){ return; }
  var q = new URLSearchParams(); q.set("parola_aplicatii_noua", "1");
  m.textContent = "Se face parola nouă..."; m.classList.remove("eroare");
  cerere("/api/interfata-web-seteaza", "POST", q).then(function(d){
    m.textContent = d.message || ""; m.classList.toggle("eroare", !d.result);
    citesteInterfataWeb();
  }).catch(function(){ m.textContent = "Receptorul nu răspunde."; m.classList.add("eroare"); });
});
function citeste(){
  if(!ID){
    citesteAspect();
    citesteInterfataWeb();
    return cerere("/api/setari").then(function(d){
      $("incarcare").classList.add("ascuns"); $("lista").classList.remove("ascuns");
      var ul = $("ecrane"); ul.textContent = "";
      (d.ecrane || []).forEach(function(e){ var li = document.createElement("li"); var a = document.createElement("a"); a.href = adresa("/setari?id=" + encodeURIComponent(e.id)); a.textContent = e.text + (e.titlu && e.titlu !== e.text ? " (" + e.titlu + ")" : ""); li.appendChild(a); ul.appendChild(li); });
    });
  }
  return cerere("/api/setari?id=" + encodeURIComponent(ID)).then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi setările."; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
$("inapoi").href = adresa("/meniu");
$("salveaza").addEventListener("click", function(){
  var q = new URLSearchParams(); q.set("id", ID); var n = 0;
  DATE.randuri.forEach(function(r){
    var c = $("r" + r.nr);
    if(!c || c.tagName === "SPAN"){ return; }
    var v = valoareControl(r, c);
    if(v !== undefined && v !== c.getAttribute("data-inainte")){ q.set("r" + r.nr, v); n++; }
  });
  if(!n){ mesaj("Nu ai schimbat nimic."); return; }
  mesaj("Se salvează...");
  cerere("/api/setari-seteaza", "POST", q).then(function(d){ mesaj(d.message, !d.result); if(d.randuri){ arata(d); } })
    .catch(function(){ mesaj("Receptorul nu răspunde.", true); });
});
citeste();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele se traduc la folosire."""
	return text


TEXTE_PAGINA = {
	"html": (
		N_("Setări"),
		N_("Înapoi la meniu"),
		N_("Caută"),
		N_("Se citesc setările..."),
		N_("Aspectul interfeței web"),
		N_("Tema și culorile paginilor web. Sunt numai ale interfeței web: tema și culorile de pe televizor "
			"nu se schimbă de aici."),
		N_("1. Tema interfeței web"),
		N_("Cum arată paginile: meniul, butoanele, cardurile, rândurile."),
		N_("Clasic"),
		N_("Aerisită"),
		N_("Ca meniul de pe televizor: rânduri mari, titlul cu linie chihlimbarie, meniul se deschide din "
			"butonul Meniu."),
		N_("Pro"),
		N_("Densă"),
		N_("Mai multe lucruri pe ecran; pe ecranele late meniul stă mereu în stânga."),
		N_("2. Schema de culori"),
		N_("Culorile paginilor web: aceleași palete ca pe televizor, alese separat. Întâi familia, apoi "
			"varianta."),
		N_("Se citesc paletele..."),
		N_("3. Unde se ține minte"),
		N_("Fă-le implicite pe receptor"),
		N_("Revino la implicitele receptorului"),
		N_("Interfața web"),
		N_("Cere codul și în rețeaua locală"),
		N_("Nu"),
		N_("Da"),
		N_("Aplicații de telefon"),
		N_("Acces din afara casei"),
		N_("Salvează"),
		N_("Fă altă parolă pentru aplicații"),
		N_("Aceleași rânduri, cu aceleași alegeri, sunt pe televizor în ecranul cu același nume. Rândurile "
			"care se văd depind de „__NIVEL__”, ales pe televizor în __DRUM_MENIU__. Setările fără listă de "
			"alegeri se schimbă de pe televizor."),
		N_("Caută setări"),
		N_("Tema interfeței web"),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Niciun rând de arătat la nivelul ales."),
		N_("Fiecare browser sau telefon nou din rețeaua locală are nevoie o dată de codul arătat pe "
			"televizor."),
		N_("Asocierea cu cod e oprită în rețeaua locală: browserele și telefoanele din casă intră fără cod. "
			"Din afara rețelei locale receptorul nu răspunde."),
		N_("Dacă pornești codul, și acest browser va avea nevoie de codul de pe televizor."),
		N_("Aplicațiile de telefon cer atunci și acasă utilizatorul root și parola pentru aplicații."),
		N_("Același rând e pe televizor, în"),
		N_("Meniu"),
		N_("Pornit: aplicațiile obișnuite de telefon pentru receptoare Enigma2 (canale, telecomandă, ghid, "
			"înregistrări, liste m3u) intră și din casă numai cu utilizatorul root și parola pentru aplicații"),
		N_(", fiindcă rândul de mai sus cere codul și în rețeaua locală."),
		N_("Pornit: aplicațiile obișnuite de telefon pentru receptoare Enigma2 (canale, telecomandă, ghid, "
			"înregistrări, liste m3u) intră din casă fără parolă. În aplicație scrii adresa receptorului și "
			"portul 80; utilizatorul și parola rămân goale."),
		N_("Conectate:"),
		N_("Oprit. Pornit (cum vine din fabrică), receptorul răspunde aplicațiilor obișnuite de telefon "
			"pentru receptoare Enigma2, din casă fără parolă."),
		N_("Pornit: din afara rețelei locale aplicațiile intră numai cu utilizatorul root și parola pentru "
			"aplicații"),
		N_(". Pe router trimiți un port spre receptor."),
		N_("Oprit din fabrică: din afara rețelei locale receptorul nu răspunde aplicațiilor."),
		N_("Pornit, le cere utilizatorul root și parola"),
		N_("Merge numai cu rândul de mai sus pornit."),
		N_("Clasic"),
		N_("Ca pe televizor"),
		N_("o variantă"),
		N_("În acest browser:"),
		N_("(alese aici)."),
		N_("(implicitele receptorului)."),
		N_("Implicite pe receptor, pentru browserele fără alegere proprie:"),
		N_(". Alege una; se aplică pe loc în acest browser."),
		N_("Culorile alese pe televizor, în Setări skin."),
		N_("Implicită"),
		N_("Paleta de bază a skinului."),
		N_("Paletele de pe televizor nu se găsesc pe receptor (lipsește skinul HDSatelit?)."),
		N_("Receptorul nu a putut citi paletele."),
		N_("Receptorul nu răspunde."),
		N_("Se salvează..."),
		N_("Nu ai schimbat nimic."),
		N_("Faci o parolă nouă pentru aplicații? Din afara casei, aplicațiile care o folosesc pe cea veche "
			"nu mai primesc răspuns până nu scrii în ele parola nouă."),
		N_("Se face parola nouă..."),
		N_("Receptorul nu a putut citi setările."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
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
