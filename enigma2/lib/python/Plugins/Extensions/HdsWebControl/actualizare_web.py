# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# actualizare_web.py: „Actualizare software” in interfata web (HdsWebControl), numai pentru citire.
#
# Pe televizor: ecranul de actualizare (Screens/HdsSoftwareUpdate.py) arata pachetele gasite pe stick sau pe disc, cu
# verdictul pazei de model pentru fiecare (pentru acest receptor, sau de ce nu se scrie). Aici: aceeasi lista, din
# aceeasi logica (HdsSoftwareUpdate.cautaCandidati: marcajul fiecarui pachet fata de amprenta receptorului, citita o
# data), cu textul intreg al fiecarui refuz. Scrierea nu se face de aici: are doua intrebari si simularea, pe televizor,
# cu omul langa receptor; pagina spune unde e ecranul.
#
# Rute (poarta comuna a HdsJsonResource; nimic nu schimba ceva):
#   GET /api/actualizare-pachete   pachetele gasite acum si verdictul pazei pentru fiecare
#   GET /actualizare               pagina (aceeasi poarta ca /paznic: reteaua locala, apoi browserul asociat)
#
# FIRUL: lista mediilor montate se ia pe firul enigma2 (harddiskmanager nu e de atins din alt fir); citirea dosarelor si
# a zipurilor si amprenta ruleaza pe un fir separat (Components/HdsPazaModel.LucrareFundal, rezultatul cules cu un
# eTimer), iar raspunsul pleaca dupa (NOT_DONE_YET). Fisierul nu importa nimic din enigma2 la incarcare: probele de pe
# PC dau modulele lor (U = ecranul de actualizare, H = paza de model).

import json
import re

try:
	from html import escape as _escape
except ImportError:  # Python 2 (probele vechi)
	from cgi import escape as _escape


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _limba():
	"""Codul limbii interfetei pentru <html lang>, „ro” daca nu se poate afla"""
	try:
		from Components.Language import language
		cod = (language.getLanguage() or "").split("_")[0].lower()
	except Exception:
		cod = ""
	cod = "".join(ch for ch in cod if "a" <= ch <= "z")[:3]
	return cod or "ro"


def _u(U=None):
	if U is not None:
		return U
	from Screens import HdsSoftwareUpdate
	return HdsSoftwareUpdate


def _h(H=None):
	if H is not None:
		return H
	from Components import HdsPazaModel
	return HdsPazaModel


def pachete(U, H, discuri):
	"""Pachetele de pe `discuri`, fiecare ca dict pentru pagina (ruleaza pe firul separat: numai fisiere)."""
	rez = []
	for c in U.cautaCandidati(discuri):
		cod, text = c.get("paza") or (H.REFUZ_NECITIT, "")
		rez.append({
			"nume": U._numePachet(c),
			"versiune": c.get("versiune") or "",
			"mediu": c["disc"].description or c["disc"].mountpoint,
			"tip": c["tip"],
			"cod": cod,
			"bun": cod == H.PACHET_BUN,
			"verdict": H.scurtRefuz(cod),
			"text": text or "",
		})
	return rez


def raspuns(lista, H, radacina=None):
	"""Corpul lui GET /api/actualizare-pachete. "versiune" = cea care ruleaza acum (etc/image-version,
	HdsPazaModel.versiuneAcum), nu imaginea scrisa din reguli, care ramane aceeasi dupa o actualizare prin pachete."""
	reguli = H.citesteReguli(radacina) or {}
	acum = getattr(H, "versiuneAcum", None)
	return {
		"result": True,
		"pachete": lista,
		"model": reguli.get("model", ""),
		"versiune": (acum(radacina) if acum is not None else "") or reguli.get("version", ""),
	}


def rute(baza, resource, NOT_DONE_YET, U=None, H=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py."""

	_lucrari = []   # lucrarile in curs; fara referinta pastrata, eTimer-ul lor e cules si raspunsul nu mai pleaca

	class PacheteResource(baza):
		"""GET /api/actualizare-pachete: numai citire, pe un fir separat."""

		def render_GET(self, request):
			try:
				u, h = _u(U), _h(H)
				discuri = u._discuriMontate()
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)
			resursa = self
			pastrata = []

			def gata(lista, eroare):
				for lucrare in pastrata:
					if lucrare in _lucrari:
						_lucrari.remove(lucrare)
				try:
					if eroare:
						corp = resursa._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)
					else:
						corp = resursa._raspunde(request, raspuns(lista, h))
					request.write(corp)
					request.finish()
				except Exception as problema:
					print("[HdsWebControl] actualizare: raspunsul nu a plecat (browser plecat?): %s" % problema)

			lucrare = h.LucrareFundal(lambda: pachete(u, h, discuri), gata)
			pastrata.append(lucrare)
			_lucrari.append(lucrare)
			return NOT_DONE_YET

	class PaginaResource(resource.Resource):
		"""GET /actualizare: pagina „Imagine nouă de pe stick” (actualizarile prin pachete sunt la /actualizari)."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	return {b"actualizare-pachete": PacheteResource()}, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /paznic."""
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
	return pagina_text(P._STIL_COMUN, config_pagina, _limba()).encode("utf-8", "replace")


def _drumMeniu(id_intrare):
	"""Drumul de pe televizor spre ecran (meniu_web.drumHtml); modulul incarcat singur, fara pachet (probele de pe
	PC), nu are meniul, deci ramane „Meniu”."""
	try:
		from .meniu_web import drumHtml
	except ImportError:
		return "Meniu"
	return drumHtml(id_intrare)


def _e(text):
	return _escape(u"%s" % (text or ""), True)


def texte():
	"""Textele scrise de scriptul paginii, traduse pe receptor"""
	return {
		"citeste": _t("Se caută pachetele pe stick și pe disc..."),
		"niciunul": _t("Niciun pachet găsit pe mediile montate acum."),
		"nuRaspunde": _t("Receptorul nu răspunde. Verifică dacă este pornit și în aceeași rețea."),
		"eroare": _t("Receptorul nu a putut citi pachetele."),
		"gasite": _t("Pachete găsite: %d."),
		"pentru": _t("Software-ul de acum este pentru %s."),
	}


def pagina_text(stil, config_pagina, limba="ro"):
	valori = {
		"__STIL_COMUN__": stil,
		"__LIMBA__": _e(limba or "ro"),
		"__CONFIG__": config_pagina,
		"__TEXTE__": json.dumps(texte(), ensure_ascii=False).replace("</", "<\\/"),
		"__T_TITLU__": _e(_t("Imagine nouă de pe stick")),
		"__T_CAUTA__": _e(_t("Caută din nou pachetele")),
		"__T_NOTA__": _e(_t("Aici se vede numai ce este pe stick și dacă se poate scrie. Scrierea se face pe televizor, "
			"cu simularea și două întrebări înainte:")),
		"__DRUM_MENIU__": _drumMeniu("hds_software_update"),
		"__T_PAZA__": _e(_t("Un pachet se scrie numai dacă are semnul receptorului, semnul este pentru acest receptor "
			"și fișierele lui sunt întregi (sumele se verifică pe televizor, la OK).")),
	}
	# o singura trecere: un nume venit din browser (in __CONFIG__) nu poate fi luat drept semn __X__
	return re.sub(r"__[A-Z_]+__", lambda m: valori.get(m.group(0), m.group(0)), _traducePagina(PAGINA))


PAGINA = u"""<!DOCTYPE html>
<html lang="__LIMBA__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__T_TITLU__</title>
<style>__STIL_COMUN__
  main{max-width:860px;margin:0 auto;}
  h1{font-size:1.3rem;margin:0 0 12px;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:14px 16px;margin:0 0 10px;}
  .card.bun{border-color:var(--verde);}
  .card.rau{border-color:#f5b83d;}
  .verdict{font-weight:bold;margin:0 0 4px;}
  .card.bun .verdict{color:#a8e6b4;}
  .card.rau .verdict{color:#ffb4a8;}
  .nume{margin:0;overflow-wrap:anywhere;}
  .detalii{color:var(--text-slab);font-size:.86rem;margin:4px 0 0;overflow-wrap:anywhere;}
  .motiv{color:var(--text-slab);font-size:.86rem;line-height:1.45;margin:8px 0 0;white-space:pre-line;overflow-wrap:anywhere;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 10px;line-height:1.45;}
  .bara{display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between;margin:0 0 10px;}
  .bara button{min-height:40px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;cursor:pointer;}
  .mesaj{margin:6px 0 10px;line-height:1.45;}
</style>
</head>
<body>
<main>
<h1>__T_TITLU__</h1>
<p class="nota">__T_NOTA__ __DRUM_MENIU__.</p>
<p class="nota">__T_PAZA__</p>
<div class="bara"><p class="mesaj" id="mesaj"></p><button id="cauta" type="button">__T_CAUTA__</button></div>
<div id="lista"></div>
</main>
<script>
var CFG = __CONFIG__;
var T = __TEXTE__;
function $(id){ return document.getElementById(id); }
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
function cerere(cale){
  var optiuni = {method: "GET", cache: "no-store", credentials: "same-origin", headers: {}};
  if(CFG.csrf){ optiuni.headers["X-HDS-CSRF"] = CFG.csrf; }
  return fetch(adresa(cale), optiuni).then(function(r){
    if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("browser deconectat"); }
    return r.json();
  });
}
function element(tip, clasa, text){
  var e = document.createElement(tip); if(clasa){ e.className = clasa; } if(text){ e.textContent = text; } return e;
}
function arata(d){
  var l = $("lista"); l.textContent = "";
  var p = d.pachete || [];
  var sus = p.length ? T.gasite.replace("%d", p.length) : T.niciunul;
  if(d.model){ sus += " " + T.pentru.replace("%s", d.model + (d.versiune ? " (HD Satelit " + d.versiune + ")" : "")); }
  $("mesaj").textContent = sus;
  p.forEach(function(x){
    var c = element("section", "card " + (x.bun ? "bun" : "rau"));
    c.appendChild(element("p", "verdict", x.verdict));
    c.appendChild(element("p", "nume", x.nume));
    c.appendChild(element("p", "detalii", [x.versiune && x.nume.indexOf(x.versiune) === -1 ? x.versiune : "", x.mediu].filter(Boolean).join("  ·  ")));
    if(x.text){ c.appendChild(element("p", "motiv", x.text)); }
    l.appendChild(c);
  });
}
function citeste(){
  $("mesaj").textContent = T.citeste; $("cauta").disabled = true;
  cerere("/api/actualizare-pachete").then(function(d){
    if(!d.result){ $("mesaj").textContent = d.message || T.eroare; return; }
    arata(d);
  }).catch(function(){ $("mesaj").textContent = T.nuRaspunde; })
    .then(function(){ $("cauta").disabled = false; });
}
$("cauta").addEventListener("click", citeste);
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
	),
	"js": (
		N_("browser deconectat"),
		N_("(HD Satelit"),
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
