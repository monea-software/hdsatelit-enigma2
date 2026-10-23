# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# radio_web.py: „Radio pe receptor” in interfata web (HdsWebControl), perechea ecranului radio de pe televizor
# (Screens/HdsEcranRadio.py) si a setarilor lui (Meniu > Audio > Ecranul radio).
#
# O SINGURA LOGICA: datele postului si textele randurilor vin din Components/HdsRadioDate.py (aceleasi functii ca pe
# televizor), setarile si textele lor din Components/HdsRadioSetari.py, barele din Components/HdsRadioDesen.py
# (tinte_bare, niveluri_canale) peste nivelele analizorului pe care il tine ecranul radio (Screens/HdsEcranRadio.py,
# legatura()). Cat pagina cere benzile, analizorul merge (cerereWeb), chiar daca ecranul radio nu se vede; se opreste
# singur la 5 secunde dupa ultima cerere.
#
# Pentru pagina de start (plugin.py, GET /api/statusinfo): semnal_panou, semnalul canalului care merge, ca pe bara.
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; ce schimba
# ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/radio              daca merge un post de radio, datele lui, textele randurilor, starea barelor, setarile
#   GET  /api/radio-benzi        barele (cate sunt alese pe televizor, pana la 24), nivelul stanga / dreapta, starea
#                                analizorului, vizualizatorul si culorile alese; pagina le cere de 4 ori pe secunda,
#                                numai cat e deschisa si merge un post de radio, si deseneaza acelasi vizualizator
#   POST /api/radio-seteaza?ecran=0|1&vizualizator=..&culori=..&bare=..&cadre=..&odihna=..&epg=..&bara_la_zap=0|1
#   POST /api/radio-urmatoarea?ce=vizualizator|culori
#                                vizualizarea sau culorile urmatoare, ca tastele GALBEN / ALBASTRU de pe ecranul radio
#                                (acelasi drum: LegaturaRadio.schimbaAlegerea, cu numele alegerii aratat si pe televizor;
#                                fisierul setarilor se scrie o data, la cateva secunde dupa ultimul clic, nu la fiecare)
#   GET  /radio                  pagina (textele ei noi vin traduse in __TEXTE__, ca pe televizor)
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2; apelurile sunt scurte (datele serviciului, o copie a
# ultimelor nivele). Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau modulele lor.

import json
import time

MAX_VALOARE = 40
BARE_WEB = 24
SALVARE_MS = 8000        # ca pe televizor (Screens/HdsEcranRadio.SALVARE_MS): o scriere dupa ultimul clic
_SALVARE = [None, None]  # [eTimer, configfile] pentru scrierea amanata fara ecranul radio


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _module(S=None, RD=None, DES=None, E=None):
	if S is None:
		from Components import HdsRadioSetari as S
	if RD is None:
		from Components import HdsRadioDate as RD
	if DES is None:
		from Components import HdsRadioDesen as DES
	if E is None:
		try:
			from Screens import HdsEcranRadio as E
		except Exception:
			E = None
	return S, RD, DES, E


def _legatura(E):
	try:
		return E.legatura() if E is not None else None
	except Exception:
		return None


def _setari(S):
	c = S.initConfig()
	rez = {}
	for nume in S.ORDINE:
		element = getattr(c, nume)
		d = {"eticheta": _t(S.ETICHETE[nume]), "descriere": _t(S.DESCRIERI[nume])}
		if nume in S.DA_NU:
			d["valoare"] = bool(element.value)
			d["alegeri"] = [["1", _t("Da")], ["0", _t("Nu")]]
		else:
			d["valoare"] = str(element.value)
			d["alegeri"] = [[str(v), _t(t)] for v, t in S.ALEGERI[nume]]
		rez[nume] = d
	return rez


class _CuNav(object):
	"""Ce asteapta HdsRadioDate de la o sesiune: numai navigatia."""
	__slots__ = ("nav",)

	def __init__(self, nav):
		self.nav = nav


def semnal_panou(nav, RD=None):
	"""Pentru pagina de start (GET /api/statusinfo, campul „semnal”): semnalul si calitatea canalului care merge, in
	procente, si randul de langa ele, aceleasi ca barele SEMNAL / CALITATE de pe televizor si ca ecranul radio
	(HdsRadioDate.semnal_acum). La un post DAB+ / program DVB-T2 din satelit: ale tunerului care tine purtatorul, cu
	„fără date de la tuner” cand controlorul nu le-a citit inca. None fara navigatie sau la o eroare."""
	if nav is None:
		return None
	if RD is None:
		from Components import HdsRadioDate as RD
	try:
		return RD.semnal_acum(_CuNav(nav))
	except Exception as eroare:
		print("[HdsWebControl] semnalul pentru panou: %s" % eroare)
		return None


def stare(sesiune=None, S=None, RD=None, DES=None, E=None):
	"""Pentru GET /api/radio."""
	S, RD, DES, E = _module(S, RD, DES, E)
	rez = {"result": True, "ordine": list(S.ORDINE), "setari": _setari(S), "radio": False,
		"ecran_vizibil": S.ecran_radio_vizibil(), "ecran_pornit": S.ecran_pornit()}
	if sesiune is None:
		rez["mesaj"] = _t("Receptorul pornește.")
		return rez
	leg = _legatura(E)
	analiza = leg.analiza() if leg is not None else None
	try:
		d = RD.date(sesiune, S.numar_epg(), analiza)
	except Exception as eroare:
		print("[HdsWebControl] radio: %s" % eroare)
		rez["mesaj"] = _t("Datele postului nu se pot citi acum.")
		return rez
	rez["radio"] = bool(d.get("radio"))
	if not rez["radio"]:
		rez["mesaj"] = _t("Acum nu merge un post de radio.")
		return rez
	rez["date"] = d
	rez["sigla"] = _numeSigla(d.get("ref"))
	ep = d.get("epg") or {}
	fel = S.valoare("vizualizator")
	putere, calitate = RD.procente_semnal(d)
	eticheta_semnal, eticheta_calitate = RD.etichete_semnal()
	rez["semnal"] = {"putere": putere, "calitate": calitate, "eticheta_putere": eticheta_semnal,
		"eticheta_calitate": eticheta_calitate, "db": (d.get("semnal") or {}).get("db")}
	rez["alegeri"] = _alegeri(S)
	rez["texte"] = {
		"nume": RD.text_nume(d),
		"detalii": RD.text_detalii(d),
		"sunet": RD.text_sunet(d),
		"transponder": RD.text_transponder(d),
		"satelit": RD.text_satelit(d),
		"semnal": RD.text_semnal(d),
		"semnal_slab": bool(RD.semnal_slab(d)),
		"ramas": RD.text_ramas(ep.get("acum")),
		"acum_ora": RD.ora(ep["acum"]["inceput"]) if ep.get("acum") else "",
		"urmatoare": [RD.text_urmatoare(x) for x in (ep.get("urmatoare") or [])],
		"epg_lipsa": "" if d.get("epg") else _t("Postul nu transmite programul emisiunilor."),
		"bare": RD.text_bare(analiza or {"stare": "asteapta"}, fel),
		"bare_detaliu": RD.text_bare_detaliu(analiza or {"stare": "asteapta"}, fel),
	}
	return rez


def _alegeri(S):
	"""Vizualizarea si culorile de acum, cu numele lor (ca pe butoanele paginii si peste barele de pe televizor)."""
	rez = {}
	for nume in S.TASTE_ALEGERI:
		v = S.valoare(nume)
		rez[nume] = {"valoare": v, "text": _t(S.TITLURI_ALEGERE[nume]) % _t(S.text_alegere(nume, v))}
	return rez


def _salveazaAmanat(configfile):
	"""Fara ecranul radio (fara LegaturaRadio): fisierul setarilor se scrie o data, la SALVARE_MS dupa ultimul clic, cu
	un ceas al paginii (eTimer, cerut numai aici: fisierul nu importa nimic din enigma2 la incarcare)."""
	try:
		from enigma import eTimer
	except ImportError:
		configfile.save()
		return
	if _SALVARE[0] is None:
		t = eTimer()

		def scrie():
			try:
				_SALVARE[1].save()
			except Exception as eroare:
				print("[HdsWebControl] radio: setarile: %s" % eroare)
		t.callback.append(scrie)
		_SALVARE[0] = t
	_SALVARE[1] = configfile
	_SALVARE[0].start(SALVARE_MS, True)


def urmatoarea(argumente, sesiune=None, S=None, RD=None, DES=None, E=None, configfile=None):
	"""POST /api/radio-urmatoarea?ce=vizualizator|culori: alegerea urmatoare, ca GALBEN / ALBASTRU pe televizor. Cine
	cauta vizualizarea dorita apasa de mai multe ori la rand: setarea se schimba pe loc, iar fisierul setarilor (pe
	eMMC) se scrie o data, la cateva secunde dupa ultimul clic (acelasi ceas ca tastele de pe televizor)."""
	S, RD, DES, E = _module(S, RD, DES, E)
	nume = argumente.get("ce", "")
	if nume not in S.TASTE_ALEGERI:
		rez = stare(sesiune, S, RD, DES, E)
		rez.update({"result": False, "message": _t("Se poate schimba numai vizualizarea sau culorile.")})
		return rez
	leg = _legatura(E)
	noua = None
	if leg is not None:
		try:
			# porneste si scrierea amanata a ecranului radio (tSalvare)
			noua = leg.schimbaAlegerea(nume)
		except Exception as eroare:
			print("[HdsWebControl] radio: alegerea urmatoare pe ecran: %s" % eroare)
	if noua is None:
		element = getattr(S.initConfig(), nume)
		element.value = S.urmatoarea(nume, element.value)
		element.save()
		if configfile is None:
			from Components.config import configfile
		_salveazaAmanat(configfile)
	rez = stare(sesiune, S, RD, DES, E)
	rez.update({"result": True, "message": _alegeri(S)[nume]["text"]})
	return rez


def _culoare_css(c):
	return "#%06x" % (int(c) & 0xFFFFFF)


def _desen(S, DES):
	"""Vizualizatorul, numarul de bare si culorile alese pe televizor, ca pagina sa deseneze la fel."""
	fel = S.valoare("vizualizator")
	try:
		culori = [_culoare_css(c) for c in DES.tema(S.valoare("culori"))]
	except Exception:
		culori = [_culoare_css(c) for c in DES.TEME["skin"]]
	return {"vizualizator": fel, "culori": culori, "numar_bare": S.numar_bare()}


def _numeSigla(ref):
	"""Numele siglei pentru /api/canale-sigla (canale_web.nume_sigla, ca Renderer/Picon.py), sau None."""
	try:
		from .canale_web import nume_sigla
	except Exception:
		return None
	try:
		return nume_sigla(ref) if ref else None
	except Exception:
		return None


def benzi(sesiune=None, S=None, RD=None, DES=None, E=None, acum=None):
	"""Pentru GET /api/radio-benzi: barele din sunetul adevarat al postului, sau starea care spune de ce nu sunt."""
	S, RD, DES, E = _module(S, RD, DES, E)
	leg = _legatura(E)
	rez = {"result": True, "t": acum if acum is not None else time.time(), "benzi": [], "stanga": 0.0, "dreapta": 0.0}
	rez.update(_desen(S, DES))
	if leg is None or not getattr(leg, "radio", False):
		rez["stare"] = "fara-radio"
		rez["mesaj"] = _t("Acum nu merge un post de radio.")
		rez["detaliu"] = ""
		return rez
	leg.cerereWeb()
	an = getattr(leg, "analizor", None)
	analiza = leg.analiza() or {"stare": "asteapta"}
	rez["stare"] = analiza.get("stare")
	fel = rez["vizualizator"]
	rez["mesaj"] = RD.text_bare(analiza, fel)
	rez["detaliu"] = RD.text_bare_detaliu(analiza, fel)
	if an is None:
		return rez
	nivele = an.nivele(0.25)
	if not nivele:
		return rez
	esantionare = (an.flux.info or {}).get("esantionare", 48000)
	rez["benzi"] = [round(x, 3) for x in DES.tinte_bare(nivele, rez["numar_bare"] or BARE_WEB, esantionare)]
	st, dr = DES.niveluri_canale(nivele)
	rez["stanga"] = round(st, 3)
	rez["dreapta"] = round(dr, 3)
	return rez


def _valoareAleasa(S, nume, text):
	if nume in S.DA_NU:
		return {"1": True, "0": False}.get(text)
	for v, t in S.ALEGERI[nume]:
		if str(v) == text:
			return v
	return None


def seteaza(argumente, sesiune=None, S=None, RD=None, DES=None, E=None, configfile=None):
	"""POST /api/radio-seteaza: toate valorile trimise trebuie sa fie printre alegeri, altfel nu se schimba nimic."""
	S, RD, DES, E = _module(S, RD, DES, E)
	c = S.initConfig()
	noi = {}
	for nume in S.ORDINE:
		if nume in argumente:
			v = _valoareAleasa(S, nume, argumente[nume])
			if v is None:
				rez = stare(sesiune, S, RD, DES, E)
				rez.update({"result": False, "message": _t("Alegerea „%s” nu există pentru „%s”.") % (
					argumente[nume][:MAX_VALOARE], _t(S.ETICHETE[nume]))})
				return rez
			noi[nume] = v
	if not noi:
		rez = stare(sesiune, S, RD, DES, E)
		rez.update({"result": False, "message": _t("Nu s-a trimis nicio setare.")})
		return rez
	for nume, v in noi.items():
		element = getattr(c, nume)
		element.value = v
		element.save()
	if configfile is None:
		from Components.config import configfile
	configfile.save()
	leg = _legatura(E)
	if leg is not None:
		try:
			leg.setariSchimbate()
		except Exception as eroare:
			print("[HdsWebControl] radio: setarile pe ecran: %s" % eroare)
	rez = stare(sesiune, S, RD, DES, E)
	rez.update({"result": True, "message": _t("Salvat. Ecranul radio de pe televizor folosește de acum aceste setări.")})
	return rez


def argumente(request):
	"""Argumentele cererii ca text scurt: {cheie: text}, fara token; numai cheile cunoscute."""
	from Components import HdsRadioSetari as S
	return argumente_din(request, S.ORDINE)


def argumente_din(request, permise):
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:16]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie not in permise:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:MAX_VALOARE].strip()
	return rez


def rute(baza, resource, sesiune=None, module=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py; `sesiune`
	e o functie care da sesiunea enigma2; `module` (S, RD, DES, E) il dau probele de pe PC."""
	S, RD, DES, E = module or (None, None, None, None)

	def _ses():
		try:
			return sesiune() if sesiune is not None else None
		except Exception:
			return None

	class StareResource(baza):
		"""GET /api/radio: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(_ses(), S, RD, DES, E))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class BenziResource(baza):
		"""GET /api/radio-benzi: numai citire (tine analizorul pornit cateva secunde)."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, benzi(_ses(), S, RD, DES, E))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class SeteazaResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				perm = (S.ORDINE if S is not None else None)
				arg = argumente_din(request, perm) if perm is not None else argumente(request)
				return self._raspunde(request, seteaza(arg, _ses(), S, RD, DES, E))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class UrmatoareaResource(baza):
		"""POST /api/radio-urmatoarea?ce=vizualizator|culori (GALBEN / ALBASTRU din pagina)."""
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, urmatoarea(argumente_din(request, ("ce",)), _ses(), S, RD, DES, E))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class PaginaResource(resource.Resource):
		"""GET /radio: pagina „Radio pe receptor”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"radio": StareResource(),
		b"radio-benzi": BenziResource(),
		b"radio-seteaza": SeteazaResource(),
		b"radio-urmatoarea": UrmatoareaResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /limbi si /ceas."""
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


def texte_pagina():
	"""Textele paginii care se schimba dupa limba receptorului (traduse ca pe televizor); pagina le pune la incarcare
	in locul celor romanesti scrise in HTML."""
	return {
		"viz": _t("Altă vizualizare"),
		"cul": _t("Alte culori"),
		"egal": _t("Egalizator"),
		# nota tastelor: fraza veche (tradusa) si fraza tastei verzi (egalizatorul), fiecare cu textul ei
		"nota_taste": _t("Pe televizor, pe ecranul radio: tasta galbenă trece la altă vizualizare, tasta albastră la "
			"alte culori. Alegerea se ține minte.") + " " + _t("Tasta verde deschide egalizatorul."),
		"nota_bare": _t("Barele urmăresc sunetul adevărat al postului, pe benzi de frecvență, oricare ar fi formatul "
			"sunetului (MPEG, AAC, AC-3, E-AC-3, DTS, PCM), și când sunetul pleacă neschimbat spre bara de sunet."),
		"nu_raspunde": _t("Receptorul nu răspunde."),
		"nu_raspunde_lung": _t("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		"fara_piesa": _t("nu a sosit încă"),
		"fara_text": _t("Nu a sosit încă niciun text radio."),
	}


def _json_script(d):
	"""JSON pus intr-un <script>: fara „</” (care ar inchide scriptul) si fara caracterele de rand noi din JS."""
	return json.dumps(d, ensure_ascii=True).replace("</", "<\\/")


def _litera(text):
	"""Traducerea literei; fara traducere (probele de pe PC), prima litera a textului."""
	t = _t(text)
	if not t or t == text:
		t = text[:1]
	return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def pagina_text(stil, config_pagina):
	return _traducePagina(PAGINA).replace("__STIL_COMUN__", stil).replace("__CONFIG__",
		config_pagina).replace("__TEXTE__",
		_json_script(texte_pagina())).replace("__DRUM_MENIU__", _drumMeniu("hds_ecran_radio")).replace(
		# literele barelor de nivel (canalul stang si cel drept), cate una, in limba paginii (N_ e definit mai jos,
		# deci textele se iau aici, la randare)
		# TRANSLATORS: o singura litera, prescurtarea pentru canalul stang al sunetului (en L)
		"__NIVEL_S__", _litera(N_("S (stânga)"))).replace(
		# TRANSLATORS: o singura litera, prescurtarea pentru canalul drept al sunetului (en R)
		"__NIVEL_D__", _litera(N_("D (dreapta)")))


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Radio pe receptor</title>
<style>__STIL_COMUN__
  main{max-width:900px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  h2{font-size:.95rem;margin:0 0 10px;color:var(--text-slab);text-transform:uppercase;letter-spacing:.04em;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .post{display:flex;gap:14px;align-items:center;}
  .post img{width:110px;height:66px;object-fit:contain;background:#0f1216;border-radius:6px;}
  .nume{font-size:1.4rem;font-weight:bold;word-break:break-word;}
  .slab{color:var(--text-slab);font-size:.92rem;line-height:1.45;}
  .rand{padding:6px 0;border-bottom:1px solid var(--bordura);line-height:1.45;word-break:break-word;}
  .rand:last-child{border-bottom:0;}
  .rand.cu-eticheta{display:grid;grid-template-columns:minmax(90px,max-content) 1fr;column-gap:10px;}
  .eticheta{color:var(--text-slab);}
  .piesa{color:#f5b83d;font-weight:bold;}
  .rosu{color:#ffb4a8;}
  canvas{width:100%;height:180px;background:#0a0f1a;border-radius:8px;display:block;}
  .nivel{display:grid;grid-template-columns:24px 1fr;gap:6px;align-items:center;margin-top:8px;font-size:.85rem;color:var(--text-slab);}
  .nivel div{height:10px;background:#1b2230;border-radius:5px;overflow:hidden;}
  .nivel span{display:block;height:100%;width:0;background:linear-gradient(90deg,#2fb84f,#e8c53a 70%,#e5484d);}
  .taste-viz{display:flex;flex-wrap:wrap;gap:10px;margin-top:10px;}
  .taste-viz button{display:inline-flex;align-items:center;gap:8px;background:#0f1216;border-color:var(--bordura);color:var(--text);}
  .taste-viz .patrat{display:inline-block;width:16px;height:16px;border-radius:3px;}
  .semnal-bare{display:grid;grid-template-columns:max-content minmax(80px,1fr) 3.5em;gap:8px 10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--bordura);}
  .semnal-bare b{font-size:.85rem;letter-spacing:.03em;}
  .semnal-bare .bara{height:10px;background:#232c40;border-radius:5px;overflow:hidden;}
  .semnal-bare .bara span{display:block;height:100%;width:0;}
  .setare{display:grid;grid-template-columns:1fr minmax(160px,300px);gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--bordura);}
  .setare:last-child{border-bottom:0;}
  .setare .nota{grid-column:1 / -1;}
  select{min-height:44px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;width:100%;}
  button{min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid var(--verde);background:var(--verde);color:#fff;font:inherit;cursor:pointer;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:4px 0 0;line-height:1.45;}
  .mesaj-bare{color:var(--text);font-size:1rem;line-height:1.45;text-align:center;margin:0;padding:28px 8px;background:#0a0f1a;border-radius:8px;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
  @media (max-width:560px){ .setare{grid-template-columns:1fr;} .post img{width:80px;height:48px;} }
</style>
</head>
<body>
<main>
<h1>Radio pe receptor</h1>
<p class="mesaj" id="incarcare">Se citesc datele...</p>
<div id="continut" class="ascuns">
  <section class="card" id="cardPost">
    <div class="post"><img id="sigla" class="ascuns" alt=""><div><div class="nume" id="nume"></div><div class="slab" id="detalii"></div></div></div>
    <p class="slab" id="faraRadio"></p>
  </section>
  <section class="card" id="cardEmisiuni">
    <h2>Emisiunile</h2>
    <div id="emisiuni"></div>
  </section>
  <section class="card" id="cardRds">
    <h2>Piesa și textul radio</h2>
    <div class="rand cu-eticheta"><span class="eticheta">Piesa</span><span class="piesa" id="piesa"></span></div>
    <div class="rand" id="radiotext"></div>
  </section>
  <section class="card" id="cardSunet">
    <h2>Sunetul</h2>
    <p class="mesaj-bare ascuns" id="mesajBare"></p>
    <canvas id="bare" width="900" height="180" aria-label="Barele de frecvență ale sunetului"></canvas>
    <div class="nivel" id="nivelBare"><b>__NIVEL_S__</b><div><span id="nivelS"></span></div><b>__NIVEL_D__</b><div><span id="nivelD"></span></div></div>
    <div class="taste-viz">
      <button type="button" id="vizUrmatoare"><span class="patrat" style="background:#e8c53a"></span><span id="txViz">Altă vizualizare</span></button>
      <button type="button" id="culoriUrmatoare"><span class="patrat" style="background:#3a7bd5"></span><span id="txCul">Alte culori</span></button>
      <button type="button" id="egalizator"><span class="patrat" style="background:#22a84a"></span><span id="txEgal">Egalizator</span></button>
    </div>
    <p class="nota" id="alegeriAcum"></p>
    <p class="nota" id="notaTaste">Pe televizor, pe ecranul radio: tasta galbenă trece la altă vizualizare, tasta albastră la alte culori. Alegerea se ține minte. Tasta verde deschide egalizatorul.</p>
    <p class="nota" id="notaBare">Barele urmăresc sunetul adevărat al postului, pe benzi de frecvență, oricare ar fi formatul sunetului (MPEG, AAC, AC-3, E-AC-3, DTS, PCM), și când sunetul pleacă neschimbat spre bara de sunet.</p>
  </section>
  <section class="card" id="cardTehnic">
    <h2>Recepția</h2>
    <div class="semnal-bare" id="semnalBare">
      <b id="etichetaPutere" style="color:#9fb4ff"></b><div class="bara" id="sinaPutere"><span id="baraPutere" style="background:#9fb4ff"></span></div><span id="valoarePutere"></span>
      <b id="etichetaCalitate" style="color:#2fb84f"></b><div class="bara" id="sinaCalitate"><span id="baraCalitate" style="background:#2fb84f"></span></div><span id="valoareCalitate"></span>
    </div>
    <div class="rand" id="sunet"></div>
    <div class="rand" id="transponder"></div>
    <div class="rand" id="satelit"></div>
    <div class="rand" id="semnal"></div>
  </section>
  <section class="card">
    <h2>Setările ecranului radio</h2>
    <div id="setari"></div>
    <p><button type="button" id="salveaza">Salvează</button></p>
    <p class="mesaj" id="mesaj"></p>
    <p class="nota">Aceleași setări sunt pe televizor, în __DRUM_MENIU__, și cu OK ținut apăsat pe ecranul radio.</p>
  </section>
</div>
</main>
<script>
var CFG = __CONFIG__;
// textele traduse de receptor (radio_web.texte_pagina); fara ele raman cele romanesti din HTML
var TX = __TEXTE__;
var DATE = null;
var SCHIMBAT = false;
var BARE = [], VARF = [], PANA = [];
var CERERE_BENZI = false;
var SIGLA = null;
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
function text(id, t){ $(id).textContent = t || ""; }
function tx(cheie, implicit){ return (TX && TX[cheie]) || implicit; }
function aplicaTexte(){
  [["txViz", "viz"], ["txCul", "cul"], ["txEgal", "egal"], ["notaTaste", "nota_taste"], ["notaBare", "nota_bare"]].forEach(function(r){
    if(TX && TX[r[1]]){ $(r[0]).textContent = TX[r[1]]; }
  });
}
function randEmisiune(eticheta, t, extra){
  var d = document.createElement("div"); d.className = eticheta !== null ? "rand cu-eticheta" : "rand";
  if(eticheta !== null){ var e = document.createElement("span"); e.className = "eticheta"; e.textContent = eticheta; d.appendChild(e); }
  var s = document.createElement("span"); s.textContent = t + (extra ? "  (" + extra + ")" : "");
  d.appendChild(s);
  return d;
}
function arataPost(d){
  var radio = !!d.radio;
  ["cardEmisiuni", "cardRds", "cardSunet", "cardTehnic"].forEach(function(id){ $(id).classList.toggle("ascuns", !radio); });
  $("faraRadio").textContent = radio ? "" : (d.mesaj || "");
  if(!radio){ text("nume", ""); text("detalii", ""); $("sigla").classList.add("ascuns"); SIGLA = null; return; }
  var t = d.texte, x = d.date;
  text("nume", t.nume); text("detalii", t.detalii);
  var s = $("sigla");
  if(d.sigla !== SIGLA){
    SIGLA = d.sigla;
    s.classList.toggle("ascuns", !SIGLA);
    s.onerror = function(){ s.classList.add("ascuns"); };
    if(SIGLA){ s.src = adresa("/api/canale-sigla?p=" + encodeURIComponent(SIGLA)); }
  }
  var em = $("emisiuni"); em.textContent = "";
  var ep = x.epg;
  if(!ep){ em.appendChild(randEmisiune(null, t.epg_lipsa)); }
  else {
    if(ep.acum){ em.appendChild(randEmisiune("Acum", t.acum_ora + "  " + ep.acum.titlu, t.ramas)); }
    t.urmatoare.forEach(function(u, i){ em.appendChild(randEmisiune(i === 0 ? "Urmează" : "", u)); });
  }
  var r = x.rds || {};
  // lipsa textelor RDS se spune ca atare (n-au sosit), fara sa se afirme ca postul nu le trimite
  text("piesa", r.piesa || tx("fara_piesa", "nu a sosit încă"));
  $("piesa").className = r.piesa ? "piesa" : "slab";
  text("radiotext", (r.text || tx("fara_text", "Nu a sosit încă niciun text radio.")) + (r.rass ? "  (RaSS)" : ""));
  text("sunet", t.sunet); text("transponder", t.transponder); text("satelit", t.satelit); text("semnal", t.semnal);
  ["sunet", "transponder", "satelit"].forEach(function(id){ $(id).classList.toggle("ascuns", !t[id]); });
  $("semnal").classList.toggle("rosu", !!t.semnal_slab);
  arataSemnal(d.semnal || {});
  arataAlegeri(d.alegeri || {});
}
// semnalul si calitatea ca bare, ca pe televizor (aceleasi cuvinte si aceleasi valori, din /api/radio); o valoare pe
// care tunerul nu o da isi ascunde cuvantul, bara si procentul (altfel sina goala ar arata ca 0%)
function arataSemnal(s){
  var are = false;
  [["Putere", s.putere, s.eticheta_putere], ["Calitate", s.calitate, s.eticheta_calitate]].forEach(function(r){
    var v = r[1], gol = (v === null || v === undefined);
    text("eticheta" + r[0], r[2] || "");
    $("bara" + r[0]).style.width = gol ? "0" : Math.max(0, Math.min(100, v)) + "%";
    text("valoare" + r[0], gol ? "" : v + "%");
    ["eticheta", "sina", "valoare"].forEach(function(p){ $(p + r[0]).classList.toggle("ascuns", gol); });
    if(!gol){ are = true; }
  });
  $("semnalBare").classList.toggle("ascuns", !are);
}
function arataAlegeri(a){
  var t = [];
  if(a.vizualizator){ t.push(a.vizualizator.text); }
  if(a.culori){ t.push(a.culori.text); }
  text("alegeriAcum", t.join(". "));
}
function urmatoarea(ce){
  cerere("/api/radio-urmatoarea", "POST", new URLSearchParams({ce: ce})).then(function(d){
    $("alegeriAcum").textContent = d.message || "";
    if(d.setari){ DATE = d; arataAlegeri(d.alegeri || {}); if(!SCHIMBAT){ arataSetari(d); } }
  }).catch(function(){ $("alegeriAcum").textContent = tx("nu_raspunde", "Receptorul nu răspunde."); });
}
function randSetare(nume, s){
  var d = document.createElement("div"); d.className = "setare";
  var l = document.createElement("label"); l.setAttribute("for", "s_" + nume); l.textContent = s.eticheta;
  var sel = document.createElement("select"); sel.id = "s_" + nume;
  s.alegeri.forEach(function(a){ var o = document.createElement("option"); o.value = a[0]; o.textContent = a[1]; sel.appendChild(o); });
  sel.value = (typeof s.valoare === "boolean") ? (s.valoare ? "1" : "0") : s.valoare;
  sel.addEventListener("change", function(){ SCHIMBAT = true; });
  var n = document.createElement("p"); n.className = "nota"; n.textContent = s.descriere;
  d.appendChild(l); d.appendChild(sel); d.appendChild(n);
  return d;
}
function arataSetari(d){
  var c = $("setari"); c.textContent = "";
  (d.ordine || []).forEach(function(n){ c.appendChild(randSetare(n, d.setari[n])); });
  SCHIMBAT = false;
}
function citeste(cuSetari){
  return cerere("/api/radio").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi datele."; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    DATE = d;
    arataPost(d);
    if(cuSetari || !SCHIMBAT){ arataSetari(d); }
  }).catch(function(){ $("incarcare").textContent = tx("nu_raspunde_lung", "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."); });
}
// acelasi vizualizator si aceleasi culori ca pe televizor (Components/HdsRadioDesen.py): culorile sunt
// [jos, mijloc, sus, varf], cu trecerile la 62% si 86% din inaltime
function pasBare(valori, acum){
  var n = valori.length;
  if(BARE.length !== n){ BARE = []; VARF = []; PANA = []; for(var k = 0; k < n; k++){ BARE.push(0); VARF.push(0); PANA.push(0); } }
  for(var i = 0; i < n; i++){
    BARE[i] = Math.max(valori[i], BARE[i] - 0.4);
    if(BARE[i] >= VARF[i]){ VARF[i] = BARE[i]; PANA[i] = acum + 0.35; } else if(acum > PANA[i]){ VARF[i] = Math.max(BARE[i], VARF[i] - 0.12); }
  }
}
function culoareDupaInaltime(cul, v){ return v < 0.62 ? cul[0] : (v < 0.86 ? cul[1] : cul[2]); }
function gradient(g, x0, y0, x1, y1, cul){
  var gr = g.createLinearGradient(x0, y0, x1, y1);
  gr.addColorStop(0, cul[0]); gr.addColorStop(0.619, cul[0]); gr.addColorStop(0.62, cul[1]);
  gr.addColorStop(0.859, cul[1]); gr.addColorStop(0.86, cul[2]); gr.addColorStop(1, cul[2]);
  return gr;
}
// starile in care barele nu se pot arata: mesajul ia locul panzei si al barelor S / D (nu la „asteapta”, cand barele
// vin in cateva clipe)
var FARA_BARE = ["fara-bare", "aac-fara-bare", "necunoscut", "fara-date", "fara-radio"];
function deseneaza(b, faraBare){
  var c = $("bare"), g = c.getContext("2d"), L = c.width, I = c.height;
  var fel = b.vizualizator || "varfuri", cul = (b.culori && b.culori.length === 4) ? b.culori : ["#374ea1", "#9fb4ff", "#f5b83d", "#d8e0f0"];
  c.classList.toggle("ascuns", fel === "oprit" || !!faraBare);
  if(faraBare){ return; }
  g.fillStyle = "#0a0f1a"; g.fillRect(0, 0, L, I);
  var acum = Date.now() / 1000;
  if(fel === "nivel"){
    pasBare([b.stanga || 0, b.dreapta || 0], acum);
    var h = Math.round(I * 0.28), lat = L - 60;
    [["S", I / 2 - h - 8], ["D", I / 2 + 8]].forEach(function(r, k){
      g.fillStyle = cul[3]; g.font = "bold 22px sans-serif"; g.textAlign = "right"; g.textBaseline = "middle";
      g.fillText(r[0], 44, r[1] + h / 2);
      g.fillStyle = gradient(g, 60, 0, 60 + lat, 0, cul); g.fillRect(60, r[1], Math.round(BARE[k] * lat), h);
      g.fillStyle = cul[3]; g.fillRect(60 + Math.round(VARF[k] * (lat - 4)), r[1], 4, h);
    });
    return;
  }
  var n = b.benzi.length;
  if(!n || fel === "oprit"){ return; }
  pasBare(b.benzi, acum);
  if(fel === "cerc"){
    var cx = L / 2, cy = I / 2, r0 = I * 0.2, lung = I * 0.5 - r0 - 4;
    g.strokeStyle = cul[0]; g.lineWidth = 2; g.beginPath(); g.arc(cx, cy, r0 - 4, 0, 2 * Math.PI); g.stroke();
    g.lineWidth = Math.max(3, Math.min(14, Math.PI * r0 / n * 0.55)); g.lineCap = "round";
    for(var j = 0; j < n; j++){
      var ab = Math.PI * (j + 0.5) / n, d = 4 + BARE[j] * lung;
      g.strokeStyle = culoareDupaInaltime(cul, BARE[j]);
      [Math.PI / 2 - ab, Math.PI / 2 + ab].forEach(function(u){
        g.beginPath(); g.moveTo(cx + r0 * Math.cos(u), cy + r0 * Math.sin(u));
        g.lineTo(cx + (r0 + d) * Math.cos(u), cy + (r0 + d) * Math.sin(u)); g.stroke();
      });
    }
    return;
  }
  var spatiu = Math.max(2, L / n * 0.18), l = (L - spatiu * (n - 1)) / n;
  for(var i = 0; i < n; i++){
    var x = i * (l + spatiu);
    if(fel === "oglinda"){
      var hm = Math.round(BARE[i] * (I / 2));
      g.fillStyle = gradient(g, 0, I / 2, 0, 0, cul); g.fillRect(x, I / 2 - hm, l, hm);
      g.fillStyle = gradient(g, 0, I / 2, 0, I, cul); g.fillRect(x, I / 2, l, hm);
      continue;
    }
    var hb = Math.round(BARE[i] * (I - 6));
    g.fillStyle = gradient(g, 0, I, 0, 0, cul); g.fillRect(x, I - hb, l, hb);
    if(fel === "varfuri"){ g.fillStyle = cul[3]; g.fillRect(x, I - Math.round(VARF[i] * (I - 6)) - 4, l, 4); }
  }
}
function benzi(){
  if(CERERE_BENZI || document.hidden || !DATE || !DATE.radio){ return; }
  CERERE_BENZI = true;
  cerere("/api/radio-benzi").then(function(b){
    if(!b.result){ return; }
    var faraBare = !!b.mesaj && FARA_BARE.indexOf(b.stare) !== -1;
    text("mesajBare", b.mesaj || "");
    $("mesajBare").classList.toggle("ascuns", !b.mesaj);
    $("nivelBare").classList.toggle("ascuns", faraBare || b.vizualizator === "oprit");
    deseneaza(b, faraBare);
    $("nivelS").style.width = Math.round((b.stanga || 0) * 100) + "%";
    $("nivelD").style.width = Math.round((b.dreapta || 0) * 100) + "%";
    if(b.culori && b.culori.length === 4){
      var fundal = "linear-gradient(90deg," + b.culori[0] + "," + b.culori[1] + " 62%," + b.culori[2] + ")";
      $("nivelS").style.background = fundal; $("nivelD").style.background = fundal;
    }
  }).catch(function(){}).then(function(){ CERERE_BENZI = false; });
}
$("salveaza").addEventListener("click", function(){
  var q = new URLSearchParams();
  (DATE.ordine || []).forEach(function(n){ var s = $("s_" + n); if(s){ q.set(n, s.value); } });
  $("mesaj").textContent = "Se trimite...";
  cerere("/api/radio-seteaza", "POST", q).then(function(d){
    $("mesaj").textContent = d.message || ""; $("mesaj").classList.toggle("eroare", !d.result);
    if(d.setari){ DATE = d; arataPost(d); if(d.result){ arataSetari(d); } }
  }).catch(function(){ $("mesaj").textContent = tx("nu_raspunde", "Receptorul nu răspunde."); $("mesaj").classList.add("eroare"); });
});
$("vizUrmatoare").addEventListener("click", function(){ urmatoarea("vizualizator"); });
$("culoriUrmatoare").addEventListener("click", function(){ urmatoarea("culori"); });
$("egalizator").addEventListener("click", function(){ location.href = "/egalizator"; });
aplicaTexte();
citeste(true);
setInterval(function(){ citeste(false); }, 5000);
setInterval(benzi, 250);
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
		N_("Radio pe receptor"),
		N_("Se citesc datele..."),
		N_("Emisiunile"),
		N_("Piesa și textul radio"),
		N_("Piesa"),
		N_("Sunetul"),
		N_("Altă vizualizare"),
		N_("Alte culori"),
		N_("Egalizator"),
		N_("Pe televizor, pe ecranul radio: tasta galbenă trece la altă vizualizare, tasta albastră la alte "
			"culori. Alegerea se ține minte. Tasta verde deschide egalizatorul."),
		N_("Barele urmăresc sunetul adevărat al postului, pe benzi de frecvență, oricare ar fi formatul "
			"sunetului (MPEG, AAC, AC-3, E-AC-3, DTS, PCM), și când sunetul pleacă neschimbat spre bara de "
			"sunet."),
		N_("Recepția"),
		N_("Setările ecranului radio"),
		N_("Salvează"),
		N_("Aceleași setări sunt pe televizor, în __DRUM_MENIU__, și cu OK ținut apăsat pe ecranul radio."),
		N_("Barele de frecvență ale sunetului"),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Acum"),
		N_("Urmează"),
		N_("nu a sosit încă"),
		N_("Nu a sosit încă niciun text radio."),
		N_("Putere"),
		N_("Calitate"),
		N_("Receptorul nu răspunde."),
		N_("Receptorul nu a putut citi datele."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Se trimite..."),
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
