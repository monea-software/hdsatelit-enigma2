# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# subtitrari_web.py: „Aspectul subtitrărilor” in interfata web (HdsWebControl), perechea ecranului de pe televizor.
#
# Ecranul de pe televizor (Screens/HdsSubtitrariAspect.py, meniul Audio) alege stilul literelor subtitrarilor TEXT
# (teletext, fisiere si textul citit din subtitrarile DVB): un stil gata facut, fontul, grosimea, marimea si culoarea
# literelor, conturul si culoarea lui, umbra (culoarea, directia, distanta, moale sau tare), fundalul (pe fiecare rand
# sau o cutie, culoarea, opacitatea), inaltimea fata de marginea de jos si distanta dintre randuri; si „Mărirea
# subtitrărilor DVB" (clara sau OCR, numai cele care merg, cu nota care spune ce face). Aici sunt aceleasi
# alegeri, grupate la fel; in plus, culorile se pot alege oricare (pe televizor numai din paleta).
#
# Contorul OCR (randul „Recunoașterea textului” de pe televizor): cu OCR ales sau cerut de traducerea subtitrarilor
# (HdsOcrSubtitrari.esteOcrPornit; atunci si o nota care spune asta), pagina arata cate pagini DVB s-au citit
# ca text si cate au ramas imagine, de ce, timpul mediu, avansul paginilor trimise din timp, ultimele pagini (ora,
# rezultat, motiv, timp, text) si ce spune serviciul (viteza masurata, opririle); butonul „Pune contorul la zero”.
# Datele vin din Components/HdsOcrSubtitrari.py (contor(), textContorScurt(), textContorDetalii(),
# puneContorulLaZero()), aceleasi ca pe televizor; pagina le cere din nou la CONTOR_WEB_S secunde cat se vede. Tot in
# card, randul „Limbile recunoașterii” (ca pe televizor: „8 în imagine, 2 descărcate”) cu legatura spre pagina
# /ocr-limbi (ocr_limbi_web.py), unde se descarca sau se sterg modelele limbilor.
# Pista DVB fara limba declarata (Components/HdsOcrLimbaGhicita.py): "Limba: Germană, ghicită după
# sunet" (sau "nedeclarată de post, nu se poate ghici după canal"), iar detaliile au aceeasi fraza ca mesajul scurt de
# pe televizor (HdsOcrSubtitrari.textGhicire).
#
# O SINGURA LOGICA: valorile, alegerile, verificarea si salvarea vin din Components/HdsSubtitrariAspect.py (stare(),
# alegeri(), seteaza(), aplicaStil(), IMPLICITE), exact ce foloseste ecranul. seteaza() schimba config.subtitles.hds_*
# si pune stilul o singura data in eSubtitleWidget, deci o subtitrare text de pe televizor se reface pe loc.
#
# Rute (toate prin poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat;
# ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/subtitrari-aspect                    valorile, alegerile, stilurile gata facute si valorile de la inceput
#   POST /api/subtitrari-aspect-seteaza?cheie=valoare&...   oricare dintre setari (cheile din „alegeri”; umbra=0|1;
#                                                  culorile #rrggbb; marire_dvb=clara|ocr, ocr numai cand exista
#                                                  serviciul si modelele); sau
#                                                  stil=<cheie> pentru un stil gata facut
#   POST /api/subtitrari-aspect-implicite           toate inapoi la valorile de la inceput, salvate
#   GET  /api/subtitrari-ocr                       contorul OCR (numai citire; cere starea serviciului, fara asteptare)
#   POST /api/subtitrari-ocr-zero                  contorul OCR pus la zero (si pauza de dupa erori oprita)
#   GET  /subtitrari                               pagina
# Contorul vine si in /api/subtitrari-aspect (cheia „ocr”), deci pagina il arata si fara ultimele doua rute.
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2 (reactorul e bucla enigma2), apelurile sunt scurte si
# directe. Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau modulul lor (M).


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (probele de pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text

MAX_TEXT = 80
MAX_ARGUMENTE = 24
CONTOR_WEB_S = 5

def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele se traduc la folosire, cu _t."""
	return text


# felul revenirii la imagine (Components/HdsOcrSubtitrari.FELURI_MOTIV) -> cum il scrie pagina
TEXT_FEL = {"termen": N_("prea târziu"), "incredere": N_("text nesigur"), "model": N_("fără model pentru limbă"),
	"serviciu": N_("serviciul oprit"), "ocupat": N_("prea multe deodată"), "fara_text": N_("fără litere"),
		"altele": N_("alt motiv")}
# pista DVB fara limba declarata: dupa ce s-a ghicit limba (Components/HdsOcrLimbaGhicita.SURSE), perechea mesajului
# scurt de pe televizor (HdsOcrSubtitrari.textGhicire, care vine si in "detalii")
TEXT_SURSA_GHICIRE = {"ghid": N_("după ghidul TV"), "ghid_sunet": N_("după ghidul TV"), "sunet": N_("după sunet"),
	"transponder": N_("după celelalte canale de pe transponder")}


def _m(M=None):
	if M is not None:
		return M
	from Components import HdsSubtitrariAspect
	return HdsSubtitrariAspect


def _o(O=None):
	"""Components.HdsOcrSubtitrari (sau cel dat de probe); None daca nu se incarca"""
	if O is not None:
		return O
	try:
		from Components import HdsOcrSubtitrari
		return HdsOcrSubtitrari
	except Exception:
		return None


def _secunde(ms):
	return None if ms is None else ("%.2f s" % (ms / 1000.0)).replace(".", ",")


def contorOcr(M=None, O=None, ping=False):
	"""Pentru GET /api/subtitrari-ocr si cheia „ocr” din /api/subtitrari-aspect: contorul, textele lui (aceleasi ca pe
	televizor), ultimele pagini si ce spune serviciul. ales = OCR e alegerea de acum; pentru_traducere = OCR-ul e cerut
	de traducerea subtitrarilor (cerutDeTraducere); lucreaza = unul din ele (esteOcrPornit): pagina arata contorul."""
	M, O = _m(M), _o(O)
	ales = False
	try:
		ales = M.stare().get("marire_dvb") == "ocr"
	except Exception:
		pass
	if O is None:
		return {"result": True, "ales": ales, "lucreaza": ales, "pentru_traducere": False, "disponibil": False}
	pentru_traducere = _cerutDeTraducere(O)
	lucreaza = ales or pentru_traducere
	s = O.contor()
	if ping and s is not None:
		try:
			O.instanta().ping()          # PONG-ul vine mai tarziu (la cererea urmatoare a paginii)
		except Exception:
			pass
	c = (s or {}).get("contor") or {}
	ultimele = []
	for p in c.get("ultimele", []):
		q = dict(p)
		q["fel_text"] = _t(TEXT_FEL.get(p.get("fel"), "")) if p.get("rezultat") != "text" else ""
		q["timp"] = _secunde(p.get("ms"))
		ultimele.append(q)
	serv = (s or {}).get("serviciu") or {}
	return {
		"result": True, "ales": ales, "lucreaza": lucreaza, "pentru_traducere": pentru_traducere, "disponibil": True,
		"scurt": O.textContorScurt(s), "detalii": O.textContorDetalii(s, cuOk=False),
		"pagini": c.get("pagini", 0), "text": c.get("text", 0), "poza": c.get("poza", 0),
		"din_memorie": c.get("din_memorie", 0),
		"motive": [[f, _t(TEXT_FEL[f]) if f in TEXT_FEL else f, n] for f, n in sorted((c.get("motive") or {}).items(),
			key=lambda x: list(TEXT_FEL).index(x[0]) if x[0] in TEXT_FEL else 99) if n],
		"timp_mediu": _secunde(c.get("timp_mediu_ms")), "timp_max": _secunde(c.get("timp_max_ms")),
		"avans_mediu": _secunde(c.get("avans_mediu_ms")), "la_timp": c.get("la_timp", 0),
		"dupa_afisare": c.get("dupa_afisare", 0), "de_la": c.get("de_la"), "ultimele": ultimele,
		"limba": (s or {}).get("limba"), "model": (s or {}).get("model"), "pauza_s": (s or {}).get("pauza_s", 0),
		"limba_nume": _numeLimbii((s or {}).get("model")),
		"fara_limba": bool((s or {}).get("fara_limba")), "limba_ghicita": (s or {}).get("limba_ghicita"),
		"sursa_ghicire": (s or {}).get("sursa_ghicire"), "limba_text": _textLimba(O, s),
		"limbi": _limbiOcr(),
		"serviciu": {k: serv[k] for k in ("version", "requests", "lines_recognized", "line_cache_hits",
			"page_cache_hits", "timeouts", "budget_timeouts", "expired", "ms_per_unit", "speed_samples", "glyph_lines",
			"glyphs", "immediate", "stretched_lines", "rereads", "rereads_better") if k in serv},
	}


def _numeLimbii(model):
	"""numele limbii unui model („Germană”), nu codul lui; None fara model"""
	if not model:
		return None
	try:
		from Components import HdsOcrModele
		return HdsOcrModele.numeModel(model)
	except Exception:
		return model


def _textLimba(O, s):
	"""Randul "Limba: ..." al cardului OCR: numele limbii modelului; la o pista DVB fara limba declarata si dupa ce s-a
	ghicit ("Germană, ghicită după sunet", cu "fără model pe receptor" cand modelul lipseste) sau ca nu se poate ghici.
	None cand nu e nimic de spus."""
	s = s or {}
	if not s.get("fara_limba"):
		return _numeLimbii(s.get("model"))
	cod = s.get("limba_ghicita")
	if not cod:
		return _t("nedeclarată de post, nu se poate ghici după canal")
	nume = cod
	f = getattr(O, "numeLimba", None)
	try:
		if f is not None:
			nume = f(cod) or cod
	except Exception:
		nume = cod
	text = _t("%s, ghicită %s") % (nume,
		_t(TEXT_SURSA_GHICIRE.get(s.get("sursa_ghicire"), N_("după canal"))))
	if not s.get("model"):
		text += _t(", fără model pe receptor")
	return text


def _cerutDeTraducere(O):
	"""Components/HdsOcrSubtitrari.cerutDeTraducere(): OCR-ul cerut de traducerea subtitrarilor (False daca lipseste)"""
	f = getattr(O, "cerutDeTraducere", None)
	try:
		return bool(f()) if f is not None else False
	except Exception:
		return False


def _limbiOcr():
	"""„8 în imagine, 2 descărcate” (Components/HdsOcrModele.textScurt), sau None daca modulul lipseste"""
	try:
		from Components import HdsOcrModele
		return HdsOcrModele.textScurt()
	except Exception:
		return None


def contorLaZero(M=None, O=None):
	"""POST /api/subtitrari-ocr-zero"""
	O = _o(O)
	if O is None:
		return {"result": False, "message": _t("Recunoașterea textului nu e pe receptor.")}
	O.puneContorulLaZero()
	d = contorOcr(M, O)
	d["message"] = _t("Contorul e pus la zero.")
	return d


def stare(M=None):
	"""Pentru GET /api/subtitrari-aspect: valorile de acum, alegerile [valoare, text], stilurile gata facute, stilul
	care se potriveste acum si valorile de la inceput."""
	M = _m(M)
	M.reimprospateazaFonturi()
	return {
		"result": True,
		"valori": M.stare(),
		"alegeri": M.alegeri(),
		"stiluri": [[c, t] for c, t in M.textStiluri()],
		"stil": M.stilCurent(),
		"implicite": dict(M.IMPLICITE),
		# randul maririi DVB (si nota lui) numai cand are ce alege, ca pe televizor: fara OCR ramane doar „clara”
		"note": {"marire_dvb": M.textNotaMarireDvb()} if M.seAlegeMarireaDvb() else {},
		"ascunse": [] if M.seAlegeMarireaDvb() else ["marire_dvb"],
		"ocr": _contorSigur(M),
	}


def _contorSigur(M):
	"""contorul pentru pagina, sau None daca nu se poate citi (pagina merge oricum)"""
	try:
		return contorOcr(M)
	except Exception:
		return None


def _raspuns(M, rezultat, mesaj):
	return {"result": rezultat, "message": mesaj, "valori": M.stare(), "alegeri": M.alegeri(), "stil": M.stilCurent()}


def seteaza(argumente, M=None):
	"""POST /api/subtitrari-aspect-seteaza: numai cheile date; o valoare necunoscuta refuza tot (nimic schimbat).
	stil=<cheie> pune un stil gata facut (singur, fara alte chei)."""
	M = _m(M)
	if "stil" in argumente:
		if len(argumente) > 1:
			return _raspuns(M, False, _t("Stilul gata făcut se trimite singur. Nu s-a schimbat nimic."))
		if not M.aplicaStil(argumente["stil"], salveaza=True):
			return _raspuns(M, False, _t("Stil necunoscut. Nu s-a schimbat nimic."))
		return _raspuns(M, True, _t("Salvat. O subtitrare text de pe televizor se vede pe loc cu noul aspect."))
	valori = {}
	for cheie in M.CHEI:
		if cheie in argumente and cheie != "umbra":
			valori[cheie] = argumente[cheie]
	if "umbra" in argumente:
		umbra = argumente["umbra"]
		if umbra not in ("0", "1"):
			return _raspuns(M, False, _t("Umbra se alege cu 0 sau 1. Nu s-a schimbat nimic."))
		valori["umbra"] = umbra == "1"
	if not valori:
		return _raspuns(M, False, _t("Nu s-a trimis nicio alegere."))
	respinse = M.seteaza(valori)
	if respinse:
		return _raspuns(M, False, _t("Valoare necunoscută pentru: %s. Nu s-a schimbat nimic.")
			% ", ".join(sorted(respinse)))
	return _raspuns(M, True, _t("Salvat. O subtitrare text de pe televizor se vede pe loc cu noul aspect."))


def implicite(M=None):
	"""POST /api/subtitrari-aspect-implicite: toate valorile de la inceput, salvate."""
	M = _m(M)
	respinse = M.seteaza(dict(M.IMPLICITE))
	if respinse:
		return _raspuns(M, False, _t("Valorile de la început nu s-au putut pune."))
	return _raspuns(M, True, _t("Valorile de la început sunt puse și salvate."))


def argumente(request):
	"""Argumentele cererii ca text scurt: {cheie: text}, fara token."""
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:MAX_ARGUMENTE]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie == "token" or not cheie or len(cheie) > 20:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:MAX_TEXT].strip()
	return rez


def rute(baza, resource, M=None, O=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py; M si O sunt
	modulele date de probe (implicit Components.HdsSubtitrariAspect si Components.HdsOcrSubtitrari)."""

	class AspectResource(baza):
		"""GET /api/subtitrari-aspect: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(M))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class _Schimba(baza):
		schimbaCeva = True

		def fa(self, a):
			raise NotImplementedError

		def render_POST(self, request):
			try:
				return self._raspunde(request, self.fa(argumente(request)))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class SeteazaResource(_Schimba):
		def fa(self, a):
			return seteaza(a, M)

	class ImpliciteResource(_Schimba):
		def fa(self, a):
			return implicite(M)

	class ContorResource(baza):
		"""GET /api/subtitrari-ocr: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, contorOcr(M, O, ping=True))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class ContorZeroResource(_Schimba):
		def fa(self, a):
			return contorLaZero(M, O)

	class PaginaResource(resource.Resource):
		"""GET /subtitrari: pagina „Aspectul subtitrărilor”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"subtitrari-aspect": AspectResource(),
		b"subtitrari-aspect-seteaza": SeteazaResource(),
		b"subtitrari-aspect-implicite": ImpliciteResource(),
		b"subtitrari-ocr": ContorResource(),
		b"subtitrari-ocr-zero": ContorZeroResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /piste: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; un browser neconectat
	primeste pagina de asociere. Pagina schimba ceva pe receptor, deci cu cookie primeste tokenul CSRF."""
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


def pagina_text(stil, config_pagina):
	return _traducePagina(PAGINA).replace("__STIL_COMUN__", stil).replace("__CONFIG__",
		config_pagina).replace("__DRUM_MENIU__",
		_drumMeniu("hds_subtitrari_aspect")).replace("__CONTOR_MS__", str(CONTOR_WEB_S * 1000))


# Grupele si randurile, in ordinea ecranului de pe televizor; „cand” = randul se arata numai daca setarea data are
# (sau nu are) valoarea data, ca pe televizor.
PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Aspectul subtitrărilor</title>
<style>__STIL_COMUN__
  main{max-width:760px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  h2{font-size:1rem;margin:0 0 4px;color:var(--text-slab);font-weight:600;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:14px 16px;margin:0 0 12px;}
  .rand{display:grid;grid-template-columns:1fr minmax(150px,330px);gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--bordura);}
  .rand:last-child{border-bottom:0;}
  .rand label{font-size:.98rem;}
  .rand select{min-height:44px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;width:100%;}
  .culoare{display:flex;gap:8px;align-items:center;}
  .culoare select{flex:1;min-width:0;}
  .culoare input[type=color]{width:52px;min-width:52px;height:44px;padding:2px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;cursor:pointer;}
  .butoane{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0 0;}
  .butoane button{min-height:44px;padding:10px 14px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;cursor:pointer;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
  .contor-scurt{font-size:1.05rem;margin:4px 0 6px;}
  .motive{margin:6px 0;padding:0 0 0 18px;line-height:1.5;font-size:.92rem;}
  .tabel{overflow-x:auto;margin:8px 0 0;}
  .tabel table{border-collapse:collapse;width:100%;font-size:.85rem;}
  .tabel th,.tabel td{text-align:left;padding:5px 6px;border-bottom:1px solid var(--bordura);vertical-align:top;}
  .tabel th{color:var(--text-slab);font-weight:600;}
  .tabel td.text{min-width:12em;}
  .tabel td.fix{white-space:nowrap;}
  .rez-text{color:#8fd19e;} .rez-poza{color:#f0c674;}
  #ocr-limbi a{display:inline-block;padding:12px 0;}
  .brut{margin:6px 0 0;}
  .brut summary{cursor:pointer;min-height:44px;display:flex;align-items:center;color:var(--text-slab);font-size:.9rem;}
  .brut pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:.85rem;margin:4px 0 0;color:var(--text-slab);}
  @media (max-width:520px){ .rand{grid-template-columns:1fr;gap:6px;}
    .tabel thead{display:none;} .tabel tr{display:block;padding:6px 0;border-bottom:1px solid var(--bordura);}
    .tabel td{display:inline;border:0;padding:0 8px 0 0;} .tabel td.text{display:block;min-width:0;padding:3px 0 0;} }
</style>
</head>
<body>
<main>
<h1>Aspectul subtitrărilor</h1>
<p class="mesaj" id="incarcare">Se citesc setările...</p>
<div id="continut" class="ascuns">
  <div id="grupe"></div>
  <section class="card ascuns" id="ocr">
    <h2>Recunoașterea textului</h2>
    <p class="nota ascuns" id="ocr-traducere">Recunoașterea textului lucrează și acum: o cere traducerea subtitrărilor.</p>
    <p class="contor-scurt" id="ocr-scurt"></p>
    <p class="nota" id="ocr-detalii"></p>
    <ul class="motive" id="ocr-motive"></ul>
    <p class="nota" id="ocr-serviciu"></p>
    <div class="tabel"><table><thead><tr><th>Ora</th><th>Rezultat</th><th>Timp</th><th>Litere</th><th>Text</th></tr></thead><tbody id="ocr-ultimele"></tbody></table></div>
    <p class="nota ascuns" id="ocr-limbi">Limbile recunoașterii: <span id="ocr-limbi-text"></span>. <a href="/ocr-limbi">Descarcă sau șterge limbi</a></p>
    <div class="butoane"><button type="button" id="ocr-zero">Pune contorul la zero</button></div>
    <details class="brut"><summary>Text brut</summary><pre id="ocr-brut"></pre></details>
  </section>
  <div class="butoane"><button type="button" id="implicite">Valori implicite</button></div>
  <p class="nota">Stilul literelor se aplică subtitrărilor text: teletext și fișiere. Aceleași setări sunt pe televizor, în __DRUM_MENIU__; aici culorile se pot alege oricare.</p>
  <p class="mesaj" id="mesaj"></p>
</div>
</main>
<script>
var CFG = __CONFIG__;
var GRUPE = [
  ["", [["stil", "Stil gata făcut"]]],
  ["Literele", [["stil_font", "Fontul"], ["grosime", "Grosimea literelor"], ["marime", "Mărimea literelor"], ["culoare", "Culoarea literelor"]]],
  ["Conturul", [["contur", "Conturul literelor"], ["culoare_contur", "Culoarea conturului", "contur", "fara", false]]],
  ["Umbra", [["umbra", "Umbră sub litere"], ["culoare_umbra", "Culoarea umbrei", "umbra", true, true], ["directie_umbra", "Direcția umbrei", "umbra", true, true],
    ["distanta_umbra", "Distanța umbrei", "umbra", true, true], ["umbra_moale", "Marginea umbrei", "umbra", true, true]]],
  ["Fundalul", [["fundal", "Fundal în spatele rândurilor"], ["culoare_fundal", "Culoarea fundalului", "fundal", "niciunul", false],
    ["opacitate_fundal", "Opacitatea fundalului", "fundal", "niciunul", false]]],
  ["Așezarea", [["jos", "Înălțimea față de marginea de jos"], ["spatiere", "Distanța dintre rânduri"]]],
  ["Subtitrările DVB", [["marire_dvb", "Mărirea subtitrărilor DVB"]]]
];
var CULORI = {culoare: 1, culoare_contur: 1, culoare_umbra: 1, culoare_fundal: 1};
var ALTA = "__alta";
var ultim = null;
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
function trimite(p){
  mesaj("Se salvează...");
  cerere("/api/subtitrari-aspect-seteaza", "POST", p).then(function(d){ mesaj(d.message, !d.result); if(d.valori){ puneTot(d); improspateazaOcrDupaSchimbare(); } })
    .catch(function(){ mesaj("Receptorul nu răspunde.", true); });
}
var ocrPentruTraducere = false;
function improspateazaOcrDupaSchimbare(){
  if(ultim && ultim.valori && ultim.valori.marire_dvb === "ocr"){ $("ocr").classList.remove("ascuns"); improspateazaOcr(); }
  else if(ocrPentruTraducere){ improspateazaOcr(); }
  else { $("ocr").classList.add("ascuns"); }
}
function alegeriPentru(cheie){
  if(cheie === "stil"){ return ultim.stiluri; }
  return ultim.alegeri[cheie] || [];
}
function umple(s, alegeri, valoare, cuAlta){
  while(s.firstChild){ s.removeChild(s.firstChild); }
  var gasit = false;
  alegeri.forEach(function(a){
    var o = document.createElement("option"); o.value = a[0]; o.textContent = a[1]; s.appendChild(o);
    if(a[0] === valoare){ gasit = true; }
  });
  if(cuAlta){
    var o = document.createElement("option"); o.value = ALTA; o.textContent = "Altă culoare..."; s.appendChild(o);
  }
  s.value = gasit ? valoare : (cuAlta ? ALTA : (alegeri.length ? alegeri[0][0] : ""));
}
function valoareText(cheie){
  if(cheie === "stil"){ return ultim.stil; }
  var v = ultim.valori[cheie];
  if(cheie === "umbra"){ return v ? "1" : "0"; }
  return String(v);
}
function seVede(r){
  if(r.length < 3){ return true; }
  var v = ultim.valori[r[2]];
  return r[4] ? v === r[3] : v !== r[3];
}
function puneTot(d){
  if(d.alegeri){ ultim.alegeri = d.alegeri; }
  if(d.valori){ ultim.valori = d.valori; }
  if(d.stil){ ultim.stil = d.stil; }
  GRUPE.forEach(function(g){
    g[1].forEach(function(r){
      var s = $("alege-" + r[0]); if(!s){ return; }
      var culoare = !!CULORI[r[0]];
      umple(s, alegeriPentru(r[0]), valoareText(r[0]), culoare);
      if(culoare){
        var c = $("culoare-" + r[0]), v = ultim.valori[r[0]];
        if(v && v.charAt(0) === "#"){ c.value = v; c.disabled = false; } else { c.disabled = true; }
      }
      $("rand-" + r[0]).classList.toggle("ascuns", !seVede(r));
    });
  });
}
function construieste(){
  var c = $("grupe");
  while(c.firstChild){ c.removeChild(c.firstChild); }
  GRUPE.forEach(function(g){
    var card = document.createElement("section"); card.className = "card";
    if(g[0]){ var h = document.createElement("h2"); h.textContent = g[0]; card.appendChild(h); }
    var randuri = 0;
    g[1].forEach(function(r){
      if(ultim.ascunse && ultim.ascunse.indexOf(r[0]) !== -1){ return; }
      randuri++;
      var rand = document.createElement("div"); rand.className = "rand"; rand.id = "rand-" + r[0];
      var eticheta = document.createElement("label"); eticheta.textContent = r[1]; eticheta.htmlFor = "alege-" + r[0];
      var s = document.createElement("select"); s.id = "alege-" + r[0];
      var loc = s;
      if(CULORI[r[0]]){
        loc = document.createElement("div"); loc.className = "culoare";
        var ci = document.createElement("input"); ci.type = "color"; ci.id = "culoare-" + r[0];
        ci.setAttribute("aria-label", r[1] + ", orice culoare");
        ci.addEventListener("change", function(){ var q = new URLSearchParams(); q.set(r[0], ci.value); trimite(q); });
        loc.appendChild(s); loc.appendChild(ci);
      }
      s.addEventListener("change", function(){
        if(s.value === ALTA){ var ci2 = $("culoare-" + r[0]); ci2.disabled = false; ci2.click(); return; }
        if(r[0] === "stil" && s.value === "personalizat"){ return; }
        var q = new URLSearchParams(); q.set(r[0], s.value); trimite(q);
      });
      rand.appendChild(eticheta); rand.appendChild(loc); card.appendChild(rand);
      if(ultim.note && ultim.note[r[0]]){
        var n = document.createElement("p"); n.className = "nota"; n.id = "nota-" + r[0]; n.textContent = ultim.note[r[0]]; card.appendChild(n);
      }
    });
    if(randuri){ c.appendChild(card); }
  });
  puneTot(ultim);
}
function sterge(el){ while(el.firstChild){ el.removeChild(el.firstChild); } }
function celula(r, text, clasa){ var td = document.createElement("td"); td.textContent = text; if(clasa){ td.className = clasa; } r.appendChild(td); }
function puneOcr(d){
  var c = $("ocr");
  var ales = !!(d && d.ales && ultim && ultim.valori && ultim.valori.marire_dvb === "ocr");
  ocrPentruTraducere = !!(d && d.pentru_traducere);
  var lucreaza = !!(d && d.disponibil && (ales || ocrPentruTraducere));
  c.classList.toggle("ascuns", !lucreaza);
  if(!lucreaza){ return; }
  $("ocr-traducere").classList.toggle("ascuns", ales || !ocrPentruTraducere);
  $("ocr-scurt").textContent = d.scurt || "";
  $("ocr-detalii").textContent = d.detalii || "";
  var m = $("ocr-motive"); sterge(m);
  (d.motive || []).forEach(function(x){ var li = document.createElement("li"); li.textContent = x[1] + ": " + x[2]; m.appendChild(li); });
  var s = d.serviciu || {}, parti = [];
  if(d.limba_text || d.limba_nume){ parti.push("Limba: " + (d.limba_text || d.limba_nume)); }
  if(s.budget_timeouts){ parti.push("oprite de timpul de lucru: " + s.budget_timeouts); }
  if(s.expired){ parti.push("rămase fără folos: " + s.expired); }
  if(d.de_la){ parti.push("numărate de la " + d.de_la); }
  $("ocr-serviciu").textContent = parti.join(" · ");
  var brut = $("ocr-brut");
  if(brut){ brut.textContent = JSON.stringify({limba: d.limba, model: d.model, limba_ghicita: d.limba_ghicita, sursa_ghicire: d.sursa_ghicire, serviciu: s}, null, 1); }
  $("ocr-limbi").classList.toggle("ascuns", !d.limbi);
  $("ocr-limbi-text").textContent = d.limbi || "";
  var t = $("ocr-ultimele"); sterge(t);
  (d.ultimele || []).forEach(function(p){
    var r = document.createElement("tr");
    celula(r, p.ora || "", "fix");
    var rez = p.rezultat === "text" ? "text" : ("imagine" + (p.fel_text ? ", " + p.fel_text : ""));
    if(p.din_memorie){ rez += " (din memorie)"; }
    celula(r, rez, p.rezultat === "text" ? "rez-text" : "rez-poza");
    celula(r, p.timp || "", "fix");
    celula(r, p.rezultat === "text" ? String(p.caractere || 0) : "", "fix");
    celula(r, p.text || "", "text");
    t.appendChild(r);
  });
}
var contorRuta = "/api/subtitrari-ocr";
function improspateazaOcr(){
  if(document.hidden || $("ocr").classList.contains("ascuns")){ return; }
  cerere(contorRuta).then(function(d){
    if(d && d.result === false && contorRuta !== "/api/subtitrari-aspect"){ contorRuta = "/api/subtitrari-aspect"; return; }
    puneOcr(d && d.ocr !== undefined ? d.ocr : d);
  }).catch(function(){});
}
function citeste(){
  cerere("/api/subtitrari-aspect").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi setările."; return; }
    ultim = d;
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    construieste();
    puneOcr(d.ocr);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
$("ocr-zero").addEventListener("click", function(){
  mesaj("Se pune contorul la zero...");
  cerere("/api/subtitrari-ocr-zero", "POST", new URLSearchParams()).then(function(d){
    mesaj(d.message, !d.result); if(d.result){ puneOcr(d); }
  }).catch(function(){ mesaj("Receptorul nu răspunde.", true); });
});
setInterval(improspateazaOcr, __CONTOR_MS__);
$("implicite").addEventListener("click", function(){
  mesaj("Se pun valorile de la început...");
  cerere("/api/subtitrari-aspect-implicite", "POST", new URLSearchParams()).then(function(d){ mesaj(d.message, !d.result); if(d.valori){ puneTot(d); } })
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
TEXTE_PAGINA = {
	"html": (
		N_("Aspectul subtitrărilor"),
		N_("Se citesc setările..."),
		N_("Recunoașterea textului"),
		N_("Recunoașterea textului lucrează și acum: o cere traducerea subtitrărilor."),
		N_("Ora"),
		N_("Rezultat"),
		N_("Timp"),
		N_("Litere"),
		N_("Text"),
		N_("Limbile recunoașterii: <span id=\"ocr-limbi-text\"></span>. <a href=\"/ocr-limbi\">Descarcă sau "
			"șterge limbi</a>"),
		N_("Pune contorul la zero"),
		N_("Text brut"),
		N_("Valori implicite"),
		N_("Stilul literelor se aplică subtitrărilor text: teletext și fișiere. Aceleași setări sunt pe "
			"televizor, în __DRUM_MENIU__; aici culorile se pot alege oricare."),
	),
	"js": (
		N_("Stil gata făcut"),
		N_("Literele"),
		N_("Fontul"),
		N_("Grosimea literelor"),
		N_("Mărimea literelor"),
		N_("Culoarea literelor"),
		N_("Conturul"),
		N_("Conturul literelor"),
		N_("Culoarea conturului"),
		N_("Umbra"),
		N_("Umbră sub litere"),
		N_("Culoarea umbrei"),
		N_("Direcția umbrei"),
		N_("Distanța umbrei"),
		N_("Marginea umbrei"),
		N_("Fundalul"),
		N_("Fundal în spatele rândurilor"),
		N_("Culoarea fundalului"),
		N_("Opacitatea fundalului"),
		N_("Așezarea"),
		N_("Înălțimea față de marginea de jos"),
		N_("Distanța dintre rânduri"),
		N_("Subtitrările DVB"),
		N_("Mărirea subtitrărilor DVB"),
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Se salvează..."),
		N_("Receptorul nu răspunde."),
		N_("Altă culoare..."),
		N_(", orice culoare"),
		N_("Limba:"),
		N_("oprite de timpul de lucru:"),
		N_("rămase fără folos:"),
		N_("numărate de la"),
		N_("(din memorie)"),
		N_("Receptorul nu a putut citi setările."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Se pune contorul la zero..."),
		N_("Se pun valorile de la început..."),
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
