# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# acces_web.py: accesul canalului de pe televizor in interfata web (HdsWebControl), perechea paginii accesului a celei
# de-a doua bare (pagina 4: lista CAID-urilor, sistemul si CAID-ul prin care se decripteaza acum, randurile de la cam,
# numele camului) si a casetei din bara de jos (sistemul decriptat acum, intr-o caseta).
#
# O SINGURA LOGICA: totul vine din Components/Converter/HdsCommon.py, prin aceleasi functii ca bara (ca_entries,
# group_caids, caid_name, ecm_active, active_system_short, ecm_rows, cam_name), deci web-ul spune exact ce spune
# televizorul. Numele
# cititorului, adresele si porturile nu ajung aici (ecm_rows nu le are).
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat):
#   GET /api/acces-canal    {result, activ, canal, acces: "criptat" | "fta" | "", sisteme: [{nume, acum}],
#                            caids: [{caid, pid, sistem, acum}], acum: {sistem, caid} | null, cam, de_la_cam: [rand]}
# „acces” e starea pe care o arata bara (Reader.acces: starea de acum, iar pana la analiza cea tinuta minte pe canal);
# gol cat nu se stie, ca bara, care nu mai scrie FTA inainte de analiza.
# Panoul principal („Acum pe receptor”): in_panou(pagina) pune randul „Acces” sub randul „Canal”: sistemul decriptat
# acum intr-o caseta, celelalte ca text, apoi detaliile (CAID-urile si randurile de la cam) la cerere; citit la 5 s.
# Sub rand, la canalul criptat, pasii decriptarii (pasi_decriptare_web.py, /api/pasi-decriptare, aceleasi randuri ca
# sub mesajul de pe televizor), numai cu setarea lor pornita; cititi la 2 s cat canalul e criptat, altfel deloc.
#
# FIRUL: render_GET ruleaza pe firul enigma2; o cerere citeste serviciul redat si fisierul de stare al camului (memorat
# o secunda de Components/HdsEcm.py), fara retea. Modulul nu importa nimic din enigma2 la incarcare: probele de pe PC
# dau modulul lor (C = HdsCommon) si navigatia lor.

import re

MAX_CAIDS = 32
_CONTROL = re.compile(u"[\u0000-\u001f\u007f-\u009f\ud800-\udfff]")


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _c(C=None):
	if C is not None:
		return C
	from Components.Converter import HdsCommon
	return HdsCommon


def _nav(nav=None):
	if nav is not None:
		return nav
	try:
		import NavigationInstance
		return NavigationInstance.instance
	except Exception:
		return None


def curat(text, n=200):
	"""Text pentru JSON: fara caractere de control, taiat; pagina il pune numai ca text."""
	try:
		t = text if isinstance(text, str) else str(text)
	except Exception:
		return ""
	return _CONTROL.sub(u" ", t)[:n].strip()


class _Sursa(object):
	"""Ce asteapta HdsCommon.Reader de la o sursa: serviciul (si referinta)."""

	def __init__(self, service, ref):
		self.service = service
		self.serviceref = ref


def _nume(C, caid):
	try:
		return C.caid_name(caid) or (u"0x%04X" % caid)
	except Exception:
		return u"0x%04X" % caid


def stare(C=None, nav=None):
	"""GET /api/acces-canal -> (cod, corp)."""
	C = _c(C)
	nav = _nav(nav)
	corp = {"result": True, "activ": False, "canal": u"", "acces": u"", "sisteme": [], "caids": [], "acum": None,
		"cam": u"", "de_la_cam": []}
	service = nav.getCurrentService() if nav is not None else None
	ref = nav.getCurrentlyPlayingServiceReference() if nav is not None else None
	if service is None or ref is None:
		return 200, corp
	r = C.Reader(_Sursa(service, ref), None)
	if r.info() is None or r.kind() not in C.DVB_KINDS_ALL:
		return 200, corp
	try:
		corp["canal"] = curat(r.info().getName(), 128)
	except Exception:
		corp["canal"] = u""
	corp["activ"] = True
	intrari = C.ca_entries(r)
	acces = r.acces()
	corp["acces"] = "criptat" if (intrari or acces == "criptat") else ("fta" if acces == "fta" else u"")
	acum = C.ecm_active(r)
	if acum > 0:
		# acelasi text ca in caseta din bara de jos (HdsSignal AccessBox)
		corp["acum"] = {"sistem": curat(C.active_system_short(r) or _nume(C, acum), 40), "caid": u"%04X" % acum}
	for nume, caids in C.group_caids([c for c, _p in intrari]):
		corp["sisteme"].append({"nume": curat(nume, 40), "acum": acum > 0 and acum in caids})
	for caid, pid in intrari[:MAX_CAIDS]:
		corp["caids"].append({"caid": u"%04X" % caid, "pid": pid if 0 < pid < 0x1FFF else None,
			"sistem": curat(_nume(C, caid), 40), "acum": caid == acum})
	corp["de_la_cam"] = [curat(x, 160) for x in C.ecm_rows(r)]
	# numele modulului CI sau al camului ales; cand camul raspunde pentru acest canal dar imaginea nu se vede inca in
	# bara (cam_name cere imaginea decodata), numele camului ales in gestiunea camurilor
	corp["cam"] = curat(C.cam_name(r) or (C.access_module_name() if acum > 0 else u""), 60)
	return 200, corp


def rute(baza, C=None, nav=None):
	"""Resursele de sub /api: {nume: resursa}. `baza` e HdsJsonResource din plugin.py."""

	class AccesResource(baza):
		def render_GET(self, request):
			try:
				cod, corp = stare(C=C, nav=nav)
				return self._raspunde(request, corp, cod)
			except Exception as eroare:
				print("[HdsWebControl] acces: %s" % eroare)
				return self._eroare(request, _t("Eroare pe receptor."), 500)

	return {b"acces-canal": AccesResource()}


# ---------------------------------------------------------------- randul din panoul principal

# sfarsitul randului "Canal" al panoului, fara textul lui (panoul se traduce in limba receptorului)
ANCORA_HTML = u'<span id="stServiciu">-</span></div>'
ANCORA_CSS = u"</style>"
ANCORA_JS = u"</script>"

PANOU_HTML = u"""
      <div class="status-linie acces-linie ascuns" id="accesRand"><span>Acces</span><span class="acces-val" id="stAcces">-</span></div>
      <div class="acces-pasi ascuns" id="accesPasi" aria-live="polite"><div class="acces-sub">Pașii decriptării</div>
        <ul class="acces-pasi-lista" id="accesPasiLista"></ul></div>
      <details class="acces-detalii ascuns" id="accesDetalii"><summary>Detaliile accesului</summary>
        <div class="acces-cam" id="accesCam"></div>
        <ul class="acces-randuri" id="accesDeLaCam"></ul>
        <div class="acces-sub">CAID-urile canalului</div>
        <ul class="acces-caids" id="accesCaids"></ul>
      </details>"""

PANOU_CSS = u"""  .acces-linie.ascuns,.acces-detalii.ascuns{display:none;}
  .acces-val{text-align:right;}
  .acces-caseta{display:inline-block;background:#4fd18b;color:#0b1a12;border-radius:4px;padding:1px 8px;font-weight:bold;margin-left:6px;}
  .acces-detalii{padding:6px 0;border-bottom:1px solid var(--bordura);font-size:.9rem;}
  .acces-detalii summary{cursor:pointer;color:#7fb8ff;min-height:32px;line-height:32px;}
  .acces-cam{margin:6px 0 2px;font-weight:bold;}
  .acces-sub{margin:8px 0 2px;color:var(--text-slab);}
  .acces-randuri,.acces-caids{margin:0;padding-left:1.1em;}
  .acces-randuri li,.acces-caids li{margin:2px 0;line-height:1.4;word-break:break-word;}
  .acces-caids li.acum{color:#4fd18b;font-weight:bold;}
  .acces-pasi{padding:4px 0 6px;border-bottom:1px solid var(--bordura);font-size:.9rem;}
  .acces-pasi.ascuns{display:none;}
  .acces-pasi-lista{margin:0;padding:0;list-style:none;}
  .acces-pasi-lista li{margin:2px 0;line-height:1.4;word-break:break-word;}
  .acces-pasi-t{display:inline-block;min-width:4.2em;color:var(--text-slab);font-variant-numeric:tabular-nums;}
  @media(max-width:600px){.acces-detalii,.acces-pasi{font-size:15px;}}
"""

PANOU_JS = u"""var accesCriptat = false, ACCES_PASI_MS = 2000;
function accesDeseneaza(d){
  var rand = document.getElementById("accesRand"), det = document.getElementById("accesDetalii");
  accesCriptat = !!(d && d.result && d.activ && d.acces === "criptat");
  if(!accesCriptat){ accesPasiDeseneaza(null); }
  if(!d || !d.result || !d.activ){ rand.classList.add("ascuns"); det.classList.add("ascuns"); return; }
  rand.classList.remove("ascuns");
  var v = document.getElementById("stAcces"); v.textContent = "";
  if(d.acces !== "criptat"){ v.textContent = d.acces === "fta" ? "liber (fără criptare)" : "-"; det.classList.add("ascuns"); return; }
  // sistemul prin care se decripteaza acum sta intr-o caseta, ca in bara de jos; celelalte ca text simplu
  var altele = (d.sisteme || []).filter(function(s){ return !s.acum; }).map(function(s){ return s.nume; });
  if(d.acum){ var c = document.createElement("span"); c.className = "acces-caseta"; c.textContent = d.acum.sistem; v.appendChild(c); }
  else { v.appendChild(document.createTextNode("criptat, nedecriptat acum")); }
  if(altele.length){ v.appendChild(document.createTextNode(" · " + altele.join(" / "))); }
  det.classList.remove("ascuns");
  document.getElementById("accesCam").textContent = d.cam ? "Modul de acces: " + d.cam : "";
  var ul = document.getElementById("accesDeLaCam"); ul.textContent = "";
  (d.de_la_cam || []).forEach(function(r){ var li = document.createElement("li"); li.textContent = r; ul.appendChild(li); });
  var uc = document.getElementById("accesCaids"); uc.textContent = "";
  (d.caids || []).forEach(function(x){
    var li = document.createElement("li"); li.className = x.acum ? "acum" : "";
    li.textContent = x.sistem + " · CAID " + x.caid + (x.pid ? " · PID ECM: " + x.pid : "") + (x.acum ? " · decriptat acum" : "");
    uc.appendChild(li);
  });
}
function actualizeazaAcces(){
  cerere("/api/acces-canal").then(accesDeseneaza).catch(function(){}).then(function(){ setTimeout(actualizeazaAcces, 5000); });
}
// pasii decriptarii canalului de pe televizor: numai la canalul criptat, numai cu setarea lor pornita (altfel lista goala)
function accesPasiDeseneaza(d){
  var b = document.getElementById("accesPasi"), ul = document.getElementById("accesPasiLista");
  if(!d || !d.result || !d.pornit || !d.criptat || !accesCriptat || !(d.pasi || []).length){ b.classList.add("ascuns"); return; }
  ul.textContent = "";
  d.pasi.forEach(function(p){
    var li = document.createElement("li"), t = document.createElement("span");
    t.className = "acces-pasi-t"; t.textContent = p.t || "";
    li.appendChild(t); li.appendChild(document.createTextNode(" " + (p.text || "")));
    ul.appendChild(li);
  });
  b.classList.remove("ascuns");
}
var accesPasiOprit = false;
function actualizeazaPasi(){
  if(!accesCriptat || document.hidden){ setTimeout(actualizeazaPasi, ACCES_PASI_MS); return; }
  cerere("/api/pasi-decriptare").then(function(d){
    // setarea oprita: se intreaba din nou mai rar (poate fi pornita intre timp din Setari)
    accesPasiOprit = !(d && d.pornit);
    accesPasiDeseneaza(d);
  }).catch(function(){}).then(function(){ setTimeout(actualizeazaPasi, accesPasiOprit ? 10000 : ACCES_PASI_MS); });
}
actualizeazaAcces();
actualizeazaPasi();
"""


def in_panou(pagina):
	"""Panoul principal cu randul „Acces”: HTML-ul sub randul „Canal”, stilul inainte de primul </style>, scriptul
	inainte de ultimul </script>. Fara oricare ancora (alta pagina, panou schimbat) pagina ramane cum e."""
	try:
		if ANCORA_HTML not in pagina or ANCORA_CSS not in pagina or ANCORA_JS not in pagina or "accesRand" in pagina:
			return pagina
		pagina = pagina.replace(ANCORA_HTML, ANCORA_HTML + _traducePagina(PANOU_HTML), 1)
		pagina = pagina.replace(ANCORA_CSS, PANOU_CSS + ANCORA_CSS, 1)
		i = pagina.rindex(ANCORA_JS)
		return pagina[:i] + _traducePagina(PANOU_JS, "js") + pagina[i:]
	except Exception as eroare:
		print("[HdsWebControl] randul accesului: %s" % eroare)
		return pagina


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele se traduc la folosire."""
	return text


TEXTE_PAGINA = {
	"html": (
		N_("Acces"),
		N_("Pașii decriptării"),
		N_("Detaliile accesului"),
		N_("CAID-urile canalului"),
	),
	"js": (
		N_("liber (fără criptare)"),
		N_("criptat, nedecriptat acum"),
		N_("Modul de acces:"),
		N_("· decriptat acum"),
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
