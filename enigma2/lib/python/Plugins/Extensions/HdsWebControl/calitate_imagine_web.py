# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# calitate_imagine_web.py: „Calitatea imaginii” in interfata web (HdsWebControl), perechea ecranului de pe televizor
# (Meniu > Setări > Video & Display Settings > Calitatea imaginii, Screens/HdsCalitateImagine.py).
#
# O SINGURA LOGICA: profilurile, reglajele, scrierea in placa, comparatia si iesirea HDR sunt in
# Components/HdsCalitateImagine.py; aici numai citirea argumentelor, verificarea lor si pagina.
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; ce schimba
# ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/calitate-imagine              „Reglajele după canal”, profilul de acum, cele 9 profiluri cu reglajele lor
#                                           (valoarea salvata, eticheta, descrierea, comparatia), iesirea HDR (alegerile
#                                           primite de televizor, ce e scris acum, intrebarea in curs), textul brut
#   POST /api/calitate-imagine-seteaza      profil=<sd_sdr|...>, <reglaj>=0..100 (multiplu de 5), pornit=0|1; cu
#   incearca=1
#                                           valorile se vad pe loc fara sa se salveze (numai pentru profilul de acum;
#                                           revin
#                                           singure dupa 3 minute fara „Păstrează”); renunta=1 pune inapoi ce e salvat.
#                                           O singura valoare gresita nu schimba nimic.
#   POST /api/calitate-imagine-implicite    profil=<profil>|toate: valorile din fabrica, salvate
#   POST /api/calitate-imagine-hdr          iesire=auto|hdr10|hlg|none: canalul porneste din nou si pe televizor apare
#                                           intrebarea (20 s; fara raspuns revine iesirea de dinainte)
#   POST /api/calitate-imagine-comparatie   reglaj=<cheie>&pornit=0|1: jumatate de ecran cu reglajul, jumatate fara;
#                                           se opreste singura dupa 60 de secunde
#   GET  /calitate-imagine                  pagina
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2 (cateva scrieri scurte in /proc). Fisierul nu importa nimic
# din enigma2 la incarcare: probele de pe PC dau modulul lor (M), setarile lor si sesiunea lor.

MAX_TEXT = 40
CHEI_FIXE = ("profil", "pornit", "incearca", "renunta", "iesire", "reglaj")
CHEI_REGLAJE = ("luminozitate", "contrast", "saturatie", "nuanta", "claritate", "zgomot", "zgomot_cadru", "blocuri",
	"contururi", "contrast_adaptiv", "culori")
CHEI = CHEI_FIXE + CHEI_REGLAJE
ECRAN_TV = "HdsCalitateImagine"


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _m(M=None):
	if M is not None:
		return M
	from Components import HdsCalitateImagine
	return HdsCalitateImagine


def _config():
	from Components.config import config
	return config


def stare(M=None):
	"""Pentru GET /api/calitate-imagine."""
	M = _m(M)
	M.initConfig()
	c = M.calitate()
	config = _config()
	acum = c.profilAcum()
	rez = {"result": True, "oferit": bool(c.oferit), "simulare": bool(c.simulare),
		"pornit": bool(config.hds_calitate.pornit.value), "fabrica": M.FABRICA, "pas": M.PAS,
		"acum": {"profil": acum, "text": c.textAcum(), "latime": c.latime, "inaltime": c.inaltime},
		"incercat": bool(c.incercat), "comparatie": c.comparatie, "profiluri": []}
	for profil in M.PROFILURI:
		reglaje = []
		salvate = M.valoriProfil(profil, salvate=True)
		for cheie, e in M.elementeProfil(profil):
			r = M.REGLAJ[cheie]
			reglaje.append({"cheie": cheie, "nume": _t(r[4]), "descriere": _t(r[5]), "valoare": salvate[cheie],
				"fel": r[3], "oprit": _t("Oprit") if r[3] == M.MODUL else "",
				"comparatie": profil == acum and c.comparatieOferita(cheie)})
		rez["profiluri"].append({"cheie": profil, "nume": M.numeProfil(profil), "acum": profil == acum,
			"reglaje": reglaje})
	alegeri = c.alegeriHdr()
	intrebare = None
	if c.intrebare is not None:
		intrebare = {"valoare": c.intrebare["valoare"], "nume": M.numeIesireHdr(c.intrebare["valoare"]),
			"secunde": max(0, int(round(c.intrebare["termen"] - c.ceas())))}
	rez["hdr"] = {"oferit": bool(alegeri), "alegere": config.hds_calitate.iesire_hdr.value,
		"alegeri": [[v, M.numeIesireHdr(v)] for v in alegeri], "scris": c.hdrScris,
		"scris_nume": M.numeIesireHdr(c.hdrScris) if c.hdrScris else "", "intrebare": intrebare,
		"tv": c.tv() if c.hdrOferit() else None}
	rez["brut"] = (c.driver.citeste() or "") if c.oferit else ""
	return rez


def _cuMesaj(rez, reusit, mesaj):
	rez["result"] = reusit
	rez["message"] = mesaj
	return rez


def _valoare(text):
	"""0..100, rotunjit la pasul de 5; None pentru orice altceva."""
	try:
		v = int(text)
	except (TypeError, ValueError):
		return None
	if v < 0 or v > 100:
		return None
	return int(round(v / 5.0)) * 5


def _citeste(argumente, M):
	"""Argumentele -> (valorile bune, None) sau (None, mesajul de eroare)."""
	v = {}
	for cheie in ("pornit", "incearca", "renunta"):
		if cheie in argumente:
			if argumente[cheie] not in ("0", "1"):
				return None, _t("„%s” se alege cu 1 (da) sau 0 (nu).") % cheie
			v[cheie] = argumente[cheie] == "1"
	profil = argumente.get("profil")
	reglaje = dict((k, argumente[k]) for k in CHEI_REGLAJE if k in argumente)
	if profil is not None and profil not in M.PROFILURI:
		return None, _t("Profilul „%s” nu există.") % profil[:MAX_TEXT]
	if reglaje and profil is None:
		return None, _t("Spune și profilul (profil=hd_sdr, de exemplu).")
	if profil is not None:
		permise = M.PE_CLASA[profil.split("_")[0]]
		valori = {}
		for cheie, text in reglaje.items():
			if cheie not in permise:
				return None, _t("Reglajul „%s” nu e al acestui profil.") % cheie
			n = _valoare(text)
			if n is None:
				return None, _t("Valorile se dau ca numere între 0 și 100.")
			valori[cheie] = n
		v["profil"] = profil
		v["valori"] = valori
	return v, None


def seteaza(argumente, M=None):
	"""POST /api/calitate-imagine-seteaza."""
	M = _m(M)
	M.initConfig()
	c = M.calitate()
	config = _config()
	if not c.oferit:
		return _cuMesaj(stare(M), False, _t("Receptorul acesta nu are blocul de calitate a imaginii."))
	v, eroare = _citeste(argumente, M)
	if eroare:
		return _cuMesaj(stare(M), False, eroare)
	if v.get("renunta"):
		M.anuleaza()
		return _cuMesaj(stare(M), True, _t("Am pus înapoi reglajele păstrate."))
	profil = v.get("profil")
	if v.get("incearca"):
		acum = c.profilAcum()
		pornit = v.get("pornit", config.hds_calitate.pornit.value)
		if acum is None or (profil is not None and profil != acum):
			return _cuMesaj(stare(M), True, _t("Profilul acesta nu e al canalului de acum: îl vezi când pornești un canal %s.") %
				M.numeProfil(profil or acum or "hd_sdr"))
		if pornit:
			valori = M.valoriProfil(acum, salvate=True)
			valori.update(v.get("valori") or {})
		else:
			valori = M.valoriFabrica(acum.split("_")[0])
		c.incearca(acum, valori, web=True)
		return _cuMesaj(stare(M), True, _t("Se vede acum pe televizor. Apasă „Păstrează” ca să rămână."))
	if "pornit" not in v and not v.get("valori"):
		return _cuMesaj(stare(M), False, _t("Nu s-a trimis nicio setare."))
	if "pornit" in v:
		config.hds_calitate.pornit.value = v["pornit"]
	for cheie, n in (v.get("valori") or {}).items():
		M.element(profil, cheie).value = str(n)
	M.salveaza()
	return _cuMesaj(stare(M), True, _t("Păstrat. Se vede și pe televizor."))


def implicite(argumente, M=None):
	"""POST /api/calitate-imagine-implicite."""
	M = _m(M)
	M.initConfig()
	profil = argumente.get("profil")
	if profil != "toate" and profil not in M.PROFILURI:
		return _cuMesaj(stare(M), False, _t("Alege un profil sau „toate”."))
	M.implicite(None if profil == "toate" else profil)
	M.salveaza()
	if profil == "toate":
		mesaj = _t("Toate profilurile au acum valorile din fabrică.")
	else:
		mesaj = _t("Profilul %s are acum valorile din fabrică.") % M.numeProfil(profil)
	return _cuMesaj(stare(M), True, mesaj)


def _ocupat(sesiune):
	"""Refuzul pentru o iesire HDR noua: aceleasi conditii ca la Video (standby, cautare, alta intrebare) si ecranul
	„Calitatea imaginii” deschis pe televizor."""
	try:
		from . import video_web
		refuz = video_web.ocupat(sesiune)
	except ImportError:
		refuz = None if sesiune is not None else _t("Interfața web nu are încă legătura cu ecranul receptorului.")
	if refuz:
		return refuz
	curent = getattr(sesiune, "current_dialog", None)
	if curent is not None and type(curent).__name__ == ECRAN_TV:
		return _t("Pe televizor e deschis ecranul Calitatea imaginii. Închide-l, apoi încearcă din nou.")
	return None


def hdr(argumente, M=None, sesiune=None):
	"""POST /api/calitate-imagine-hdr."""
	M = _m(M)
	M.initConfig()
	c = M.calitate()
	valoare = argumente.get("iesire")
	if valoare not in c.alegeriHdr():
		return _cuMesaj(stare(M), False, _t("Televizorul acesta nu primește această ieșire HDR."))
	refuz = _ocupat(sesiune)
	if refuz:
		return _cuMesaj(stare(M), False, refuz)
	pornit, mesaj = M.incearcaHdr(sesiune, valoare)
	return _cuMesaj(stare(M), pornit, mesaj)


def comparatie(argumente, M=None):
	"""POST /api/calitate-imagine-comparatie."""
	M = _m(M)
	M.initConfig()
	c = M.calitate()
	pornit = argumente.get("pornit")
	if pornit not in ("0", "1"):
		return _cuMesaj(stare(M), False, _t("„pornit” se alege cu 1 (da) sau 0 (nu)."))
	if pornit == "0":
		c.opresteComparatia()
		return _cuMesaj(stare(M), True, _t("Comparația e oprită."))
	cheie = argumente.get("reglaj")
	if cheie not in M.CHEI or not c.comparatieOferita(cheie):
		return _cuMesaj(stare(M), False, _t("Reglajul acesta nu are comparație pe canalul de acum."))
	c.pornesteComparatia(cheie, secunde=M.SECUNDE_COMPARATIE)
	return _cuMesaj(stare(M), True, _t("Pe televizor: în dreapta cu reglajul, în stânga fără. Se oprește singură după %d de secunde.") %
		M.SECUNDE_COMPARATIE)


def argumente(request):
	"""Argumentele cererii ca text scurt: {cheie: text}, fara token; numai cheile cunoscute."""
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:30]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie not in CHEI:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:MAX_TEXT].strip()
	return rez


def rute(baza, resource, M=None, sesiune=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py; sesiune() da
	sesiunea enigma2 (pentru intrebarea de pe televizor)."""
	sesiune = sesiune or (lambda: None)

	def _raspunsSigur(self, request, functie):
		try:
			return self._raspunde(request, functie())
		except Exception as eroare:
			return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class StareResource(baza):
		"""GET /api/calitate-imagine: numai citire."""

		def render_GET(self, request):
			return _raspunsSigur(self, request, lambda: stare(M))

	class _Schimba(baza):
		schimbaCeva = True
		functie = None

		def render_POST(self, request):
			return _raspunsSigur(self, request, lambda: self.functie(argumente(request)))

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class SeteazaResource(_Schimba):
		def functie(self, a):
			return seteaza(a, M=M)

	class ImpliciteResource(_Schimba):
		def functie(self, a):
			return implicite(a, M=M)

	class HdrResource(_Schimba):
		def functie(self, a):
			return hdr(a, M=M, sesiune=sesiune())

	class ComparatieResource(_Schimba):
		def functie(self, a):
			return comparatie(a, M=M)

	class PaginaResource(resource.Resource):
		"""GET /calitate-imagine: pagina „Calitatea imaginii”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"calitate-imagine": StareResource(),
		b"calitate-imagine-seteaza": SeteazaResource(),
		b"calitate-imagine-implicite": ImpliciteResource(),
		b"calitate-imagine-hdr": HdrResource(),
		b"calitate-imagine-comparatie": ComparatieResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /egalizator si /procesor."""
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
	"""Drumul de pe televizor spre ecran (meniu_web.drumHtml); modulul incarcat singur (probele de pe PC) da „Meniu”."""
	try:
		from .meniu_web import drumHtml
	except ImportError:
		return "Meniu"
	return drumHtml(id_intrare)


def _limba():
	"""Limba receptorului pentru lang (de ex. „de” din „de_DE”); „ro” fara limba citibila (probele de pe PC)."""
	try:
		from Components.Language import language
		cod = (language.getLanguage() or "").split("_")[0].lower()
	except Exception:
		cod = ""
	if 2 <= len(cod) <= 3 and cod.isalpha():
		return cod
	return "ro"


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textele se traduc la folosire."""
	return text


# etichetele fixe ale paginii: __T_<CHEIE>__ in PAGINA, traduse si scapate pentru HTML
ETICHETE = {
	"TITLU": N_("Calitatea imaginii"),
	"INCARCARE": N_("Se citesc reglajele..."),
	"ACUM": N_("Acum"),
	"REGLAJE": N_("Reglaje"),
	"PORNIT": N_("Reglajele după canal"),
	"NOTA_PORNIT": N_("Fără bifă, imaginea rămâne ca din fabrică."),
	"PROFIL": N_("Profilul"),
	"PASTREAZA": N_("Păstrează"),
	"RENUNTA": N_("Renunță"),
	"IMPLICITE": N_("Înapoi la implicite"),
	"IMPLICITE_TOATE": N_("Toate profilurile la implicite"),
	"HDR": N_("Ieșire HDR"),
	"NOTA_HDR": N_("Automat: canalele HDR ies în HDR, celelalte în SDR. Mereu HDR10 sau HLG: și meniurile și canalele SDR ies în HDR, fără clipire la schimbarea canalului. Canalul pornește din nou și pe televizor apare o întrebare: fără răspuns în 20 de secunde revine ieșirea de dinainte."),
	"INCEARCA_HDR": N_("Încearcă pe televizor"),
	"BRUT": N_("Text brut"),
	"NOTA_BRUT": N_("Ce arată acum blocul de calitate al plăcii (/proc/msp/pq)."),
}

# nota de la sfarsit: %s e drumul din meniul televizorului (HTML facut de meniu_web.drumHtml)
NOTA_JOS = N_("Aceleași reglaje sunt pe televizor, în %s. Luminozitatea, contrastul, saturația și nuanța schimbă și meniurile. Ce se vede cu adevărat se judecă pe televizor: capturile de ecran nu arată prelucrarea plăcii.")

# textele scriptului, traduse pe receptor si date paginii ca JSON (TXT); %s se inlocuieste in ordine (fmt)
TEXTE_JS = {
	"neasteptat": N_("Receptorul a răspuns neașteptat (HTTP %s)."),
	"necitit": N_("Receptorul nu a putut citi reglajele."),
	"lipsa": N_("Receptorul acesta nu are blocul de calitate a imaginii."),
	"nu_raspunde_retea": N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
	"nu_raspunde": N_("Receptorul nu răspunde."),
	"acum": N_("(acum)"),
	"fabrica": N_("Din fabrică: %s."),
	"comparatie": N_("Comparație"),
	"fara_imagine": N_("Acum nu e nicio imagine: reglajele se văd când pornești un canal TV."),
	"alt_profil": N_("Profilul acesta nu e al canalului de acum: îl vezi când pornești un canal %s."),
	"pe_loc": N_("Ce schimbi se vede pe loc pe televizor."),
	"hdr_acum": N_("Ieșire HDR acum: %s."),
	"intrebare": N_("Pe televizor: %s. Mai sunt %s s până revine ieșirea de dinainte."),
	"nepastrat": N_("Ai schimbări nepăstrate: rămân numai după „Păstrează”."),
	"alege_iesire": N_("Alege întâi o ieșire."),
	"confirma_profil": N_("Pui înapoi valorile din fabrică pentru profilul %s?"),
	"confirma_toate": N_("Pui înapoi valorile din fabrică pentru toate profilurile?"),
}


def _json(obiect):
	"""JSON pentru interiorul lui <script>: fara „</” (nu poate inchide scriptul)."""
	import json
	return json.dumps(obiect, ensure_ascii=False).replace("</", "<\\/")


def pagina_text(stil, config_pagina):
	"""Pagina cu etichetele traduse si scapate pentru HTML (quote=True: unele pot sta in atribute)."""
	import html
	text = _traducePagina(PAGINA)
	for cheie, eticheta in ETICHETE.items():
		text = text.replace("__T_%s__" % cheie, html.escape(_t(eticheta), quote=True))
	nota = html.escape(_t(NOTA_JOS), quote=True)
	nota = nota.replace("%s", _drumMeniu("hds_calitate_imagine"), 1) if "%s" in nota else nota
	return (text.replace("__LIMBA__", _limba()).replace("__NOTA_JOS__", nota)
		.replace("__TEXTE_JS__", _json(dict((k, _t(v)) for k, v in TEXTE_JS.items())))
		.replace("__STIL_COMUN__", stil).replace("__CONFIG__", config_pagina))


PAGINA = """<!DOCTYPE html>
<html lang="__LIMBA__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__T_TITLU__</title>
<style>__STIL_COMUN__
  main{max-width:980px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  h2{font-size:.95rem;margin:0 0 10px;color:var(--text-slab);text-transform:uppercase;letter-spacing:.04em;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .acum{font-size:1.02rem;line-height:1.45;margin:0 0 6px;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .rand{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:0 0 12px;}
  button{min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  button.verde{background:var(--verde);border-color:var(--verde);color:#fff;}
  button.ales{background:var(--albastru);border-color:var(--albastru);color:#fff;}
  button:disabled{opacity:.5;cursor:default;}
  select{min-height:44px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;max-width:100%;}
  .comutator{display:flex;align-items:center;gap:10px;min-height:44px;font-size:1rem;}
  .comutator input{width:22px;height:22px;}
  .reglaj{display:grid;grid-template-columns:minmax(150px,230px) 1fr 64px 130px;gap:6px 12px;align-items:center;padding:8px 0;border-bottom:1px solid var(--bordura);}
  .reglaj .nume{font-weight:bold;}
  .reglaj .val{text-align:right;font-variant-numeric:tabular-nums;}
  .reglaj input[type=range]{width:100%;min-height:36px;accent-color:#9fb4ff;}
  .reglaj .desc{grid-column:1 / -1;color:var(--text-slab);font-size:.82rem;line-height:1.4;}
  .reglaj button{min-height:36px;padding:4px 10px;font-size:.85rem;}
  .hdr label{display:flex;align-items:center;gap:10px;min-height:44px;}
  .hdr input{width:20px;height:20px;}
  pre{white-space:pre-wrap;word-break:break-word;font-size:.78rem;background:#0f1216;padding:10px;border-radius:8px;max-height:420px;overflow:auto;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
  details summary{cursor:pointer;min-height:32px;}
  @media (max-width:640px){ .reglaj{grid-template-columns:1fr 56px;} .reglaj input[type=range]{grid-column:1 / -1;grid-row:2;} .reglaj .comp{grid-column:1 / -1;} }
</style>
</head>
<body>
<main>
<h1>__T_TITLU__</h1>
<p class="mesaj" id="incarcare">__T_INCARCARE__</p>
<div id="continut" class="ascuns">
  <section class="card">
    <h2>__T_ACUM__</h2>
    <p class="acum" id="acum"></p>
    <p class="nota" id="acum_hdr"></p>
  </section>
  <section class="card" id="reglaje">
    <h2>__T_REGLAJE__</h2>
    <div class="rand">
      <label class="comutator"><input type="checkbox" id="pornit"> __T_PORNIT__</label>
    </div>
    <p class="nota" id="nota_pornit">__T_NOTA_PORNIT__</p>
    <div class="rand" id="rand_profil">
      <label for="profil">__T_PROFIL__</label>
      <select id="profil"></select>
    </div>
    <p class="nota" id="nota_profil"></p>
    <div id="lista"></div>
    <div class="rand" style="margin-top:12px">
      <button type="button" class="verde" id="pastreaza">__T_PASTREAZA__</button>
      <button type="button" id="renunta">__T_RENUNTA__</button>
      <button type="button" id="implicite">__T_IMPLICITE__</button>
      <button type="button" id="implicite_toate">__T_IMPLICITE_TOATE__</button>
    </div>
    <p class="nota" id="nepastrat"></p>
    <p class="mesaj" id="mesaj"></p>
  </section>
  <section class="card hdr ascuns" id="card_hdr">
    <h2>__T_HDR__</h2>
    <div id="alegeri_hdr"></div>
    <p class="nota">__T_NOTA_HDR__</p>
    <div class="rand" style="margin-top:8px"><button type="button" id="incearca_hdr">__T_INCEARCA_HDR__</button></div>
    <p class="mesaj" id="mesaj_hdr"></p>
  </section>
  <section class="card">
    <details>
      <summary>__T_BRUT__</summary>
      <p class="nota">__T_NOTA_BRUT__</p>
      <pre id="text_brut"></pre>
    </details>
  </section>
  <p class="nota">__NOTA_JOS__</p>
</div>
</main>
<script>
var CFG = __CONFIG__;
var TXT = __TEXTE_JS__;
var D = null, SCHIMBAT = false, CEAS_INCERCARE = null, PROFIL = null;
function $(id){ return document.getElementById(id); }
function fmt(t){ var a = Array.prototype.slice.call(arguments, 1); return String(t).replace(/%s/g, function(){ return a.length ? String(a.shift()) : ""; }); }
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
function cerere(cale, metoda, date){
  var o = {method: metoda || "GET", cache: "no-store", credentials: "same-origin", headers: {}};
  if(CFG.csrf){ o.headers["X-HDS-CSRF"] = CFG.csrf; }
  if(date){ o.headers["Content-Type"] = "application/x-www-form-urlencoded"; o.body = date.toString(); }
  return fetch(adresa(cale), o).then(function(r){
    if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("browser deconectat"); }
    return r.json().catch(function(){ return {result: false, message: fmt(TXT.neasteptat, r.status)}; });
  });
}
function mesaj(id, t, e){ var m = $(id); m.textContent = t || ""; m.classList.toggle("eroare", !!e); }
function profilDate(cheie){ var g = null; ((D && D.profiluri) || []).forEach(function(p){ if(p.cheie === cheie){ g = p; } }); return g; }
function textValoare(r, v){ v = parseInt(v, 10); return (r.fel === "modul" && v === 0) ? r.oprit : String(v); }
function construiesteProfiluri(d){
  var s = $("profil"); s.textContent = "";
  d.profiluri.forEach(function(p){ var o = document.createElement("option"); o.value = p.cheie; o.textContent = p.nume + (p.acum ? " " + TXT.acum : ""); s.appendChild(o); });
}
function construiesteLista(){
  var p = profilDate(PROFIL), l = $("lista"); l.textContent = "";
  if(!p){ return; }
  p.reglaje.forEach(function(r){
    var rand = document.createElement("div"); rand.className = "reglaj";
    var n = document.createElement("label"); n.className = "nume"; n.textContent = r.nume; n.htmlFor = "r_" + r.cheie;
    var g = document.createElement("input"); g.type = "range"; g.min = 0; g.max = 100; g.step = D.pas; g.value = r.valoare; g.id = "r_" + r.cheie;
    var v = document.createElement("span"); v.className = "val"; v.id = "v_" + r.cheie; v.textContent = textValoare(r, r.valoare);
    var c = document.createElement("span"); c.className = "comp";
    if(r.comparatie){
      var b = document.createElement("button"); b.type = "button"; b.textContent = TXT.comparatie; b.id = "c_" + r.cheie;
      b.classList.toggle("ales", D.comparatie === r.cheie);
      b.addEventListener("click", function(){ comparatie(r.cheie); });
      c.appendChild(b);
    }
    var e = document.createElement("div"); e.className = "desc"; e.textContent = r.descriere + " " + fmt(TXT.fabrica, D.fabrica);
    g.addEventListener("input", function(){ v.textContent = textValoare(r, g.value); schimbare(); });
    rand.appendChild(n); rand.appendChild(g); rand.appendChild(v); rand.appendChild(c); rand.appendChild(e); l.appendChild(rand);
    noduriReglaje[r.cheie] = g;
  });
}
var noduriReglaje = {};
function arataReglaje(d){
  $("pornit").checked = d.pornit;
  if(!PROFIL || !profilDate(PROFIL)){ PROFIL = (d.acum && d.acum.profil) || "hd_sdr"; }
  $("profil").value = PROFIL;
  construiesteLista();
  SCHIMBAT = false; $("nepastrat").textContent = "";
  arataStinse();
}
function arataStinse(){
  var p = $("pornit").checked;
  ["rand_profil", "lista", "implicite", "implicite_toate"].forEach(function(id){ $(id).classList.toggle("ascuns", !p); });
  var acum = D && D.acum ? D.acum.profil : null;
  $("nota_profil").textContent = !p ? "" : (!acum ? TXT.fara_imagine :
    (PROFIL !== acum ? fmt(TXT.alt_profil, (profilDate(PROFIL) || {}).nume) : TXT.pe_loc));
}
function arataStarea(d){
  $("acum").textContent = d.acum.text || "";
  var h = d.hdr || {};
  $("acum_hdr").textContent = h.scris ? fmt(TXT.hdr_acum, h.scris_nume) : "";
  $("card_hdr").classList.toggle("ascuns", !h.oferit);
  var c = $("alegeri_hdr");
  if(h.oferit && c.getAttribute("data-alegeri") !== JSON.stringify(h.alegeri)){
    c.textContent = ""; c.setAttribute("data-alegeri", JSON.stringify(h.alegeri));
    h.alegeri.forEach(function(a){
      var l = document.createElement("label"); var i = document.createElement("input"); i.type = "radio"; i.name = "hdr"; i.value = a[0];
      i.checked = a[0] === h.alegere; l.appendChild(i); l.appendChild(document.createTextNode(a[1])); c.appendChild(l);
    });
  }
  if(h.intrebare){ mesaj("mesaj_hdr", fmt(TXT.intrebare, h.intrebare.nume, h.intrebare.secunde)); }
  $("incearca_hdr").disabled = !!h.intrebare;
  (d.profiluri || []).forEach(function(p){ p.reglaje.forEach(function(r){ var b = $("c_" + r.cheie); if(b){ b.classList.toggle("ales", d.comparatie === r.cheie); } }); });
  $("text_brut").textContent = d.brut || "";
}
function valori(){
  var q = {profil: PROFIL, pornit: $("pornit").checked ? "1" : "0"}, p = profilDate(PROFIL);
  if(p){ p.reglaje.forEach(function(r){ if(noduriReglaje[r.cheie]){ q[r.cheie] = noduriReglaje[r.cheie].value; } }); }
  return q;
}
function trimite(cale, v){
  var q = new URLSearchParams(); Object.keys(v).forEach(function(k){ q.set(k, v[k]); });
  return cerere(cale, "POST", q).then(function(d){
    if(!d.result){ return d; }
    D = d; arataStarea(d); return d;
  }).catch(function(){ return {result: false, message: TXT.nu_raspunde}; });
}
function schimbare(){
  mesaj("mesaj", "");
  SCHIMBAT = true; $("nepastrat").textContent = TXT.nepastrat;
  arataStinse();
  clearTimeout(CEAS_INCERCARE);
  CEAS_INCERCARE = setTimeout(function(){ var v = valori(); v.incearca = "1"; trimite("/api/calitate-imagine-seteaza", v).then(function(d){ if(d && !d.result){ mesaj("mesaj", d.message, true); } }); }, 250);
}
function comparatie(cheie){
  var porneste = D.comparatie !== cheie;
  trimite("/api/calitate-imagine-comparatie", {reglaj: cheie, pornit: porneste ? "1" : "0"}).then(function(d){ mesaj("mesaj", d.message, !d.result); });
}
function citeste(cuReglaje){
  return cerere("/api/calitate-imagine").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || TXT.necitit; return; }
    if(!d.oferit){ $("incarcare").textContent = TXT.lipsa; return; }
    var prima = !D; D = d;
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    if(prima){ construiesteProfiluri(d); }
    if(prima || cuReglaje || !SCHIMBAT){ arataReglaje(d); }
    arataStarea(d);
  }).catch(function(){ $("incarcare").textContent = TXT.nu_raspunde_retea; });
}
$("pornit").addEventListener("change", schimbare);
$("profil").addEventListener("change", function(){
  if(SCHIMBAT){ trimite("/api/calitate-imagine-seteaza", {renunta: "1"}); }
  PROFIL = $("profil").value; construiesteLista(); SCHIMBAT = false; $("nepastrat").textContent = ""; arataStinse();
});
$("pastreaza").addEventListener("click", function(){
  trimite("/api/calitate-imagine-seteaza", valori()).then(function(d){ mesaj("mesaj", d.message, !d.result); if(d.result){ arataReglaje(d); } });
});
$("renunta").addEventListener("click", function(){
  trimite("/api/calitate-imagine-seteaza", {renunta: "1"}).then(function(d){ mesaj("mesaj", d.message, !d.result); if(d.result){ arataReglaje(d); } });
});
$("implicite").addEventListener("click", function(){
  if(!confirm(fmt(TXT.confirma_profil, (profilDate(PROFIL) || {}).nume))){ return; }
  trimite("/api/calitate-imagine-implicite", {profil: PROFIL}).then(function(d){ mesaj("mesaj", d.message, !d.result); if(d.result){ arataReglaje(d); } });
});
$("implicite_toate").addEventListener("click", function(){
  if(!confirm(TXT.confirma_toate)){ return; }
  trimite("/api/calitate-imagine-implicite", {profil: "toate"}).then(function(d){ mesaj("mesaj", d.message, !d.result); if(d.result){ arataReglaje(d); } });
});
$("incearca_hdr").addEventListener("click", function(){
  var ales = document.querySelector("input[name=hdr]:checked");
  if(!ales){ mesaj("mesaj_hdr", TXT.alege_iesire, true); return; }
  trimite("/api/calitate-imagine-hdr", {iesire: ales.value}).then(function(d){ mesaj("mesaj_hdr", d.message, !d.result); });
});
citeste(true);
setInterval(function(){ if(!document.hidden){ citeste(false); } }, 2000);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
TEXTE_PAGINA = {
	"html": (
	),
	"js": (
		N_("browser deconectat"),
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
