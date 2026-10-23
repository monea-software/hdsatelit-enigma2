# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# standby_tv_web.py: iesirea HDMI si CEC in interfata web (HdsWebControl), perechea sectiunii „Standby și televizorul”
# din Setari (Components/HdsStandbyTv.py). Setarile insele sunt in /setari?id=hds_standby_tv (setari_web.py, din
# data/setup.xml); aici e numai starea, din HdsStandbyTv.stare(), deci nicio a doua logica.
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat):
#   GET  /api/standby-tv     {result, in_standby, hdmi: {disponibil, oprita, text, nota}, cec: {disponibil, pornit,
#                             raspunde, text, nume, nota, telecomanda, activ, ultima_tasta, golite}, adresa_fizica};
#                             cu ?jurnal=1 si cec.jurnal: jurnalul CEC (HdsStandbyTv.jurnalCec: mesajele primite si
#                             trimise si tastele date mai departe, cu ora), numai la cerere (panoul citeste la 5 s)
#   GET  /api/telecomanda-tv {result, titlu, despre, coloane, randuri: [{cod, receptor, tv}], panou: [{cod, eticheta}],
#                             pornita, ...}: tabelul tastelor televizorului (HdsStandbyTv.tabelTaste) si tastele panoului
#                             "Mai multe taste"; pagina /telecomanda-tv (pagina_resursa, legata in plugin.py) il arata si
#                             trimite tastele panoului prin /api/remotecontrol, ca telecomanda din web.
# Panoul principal („Acum pe receptor”): in_panou(pagina) pune sub randul „Standby” randurile „Ieșirea HDMI” si „CEC”
# (fiecare numai pe un receptor care are intrarea driverului), stilul si citirea la 5 secunde; fara ancorele panoului
# pagina ramane neschimbata. Sub randul "CEC", nota cu numele aratat de televizor in lista intrarilor HDMI (CEC e
# deschis pentru nume pe orice receptor care il are) si ora la care l-a cerut televizorul ultima oara.
#
# FIRUL: render_GET ruleaza pe firul enigma2; o cerere citeste doua fisiere mici din /proc/msp, fara disc si fara
# retea. Modulul nu importa nimic din enigma2 la incarcare: probele de pe PC dau modulul lor (T).

import time


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textul se traduce la afisare cu _t()."""
	return text


T_HDMI_OPRITA = N_(u"oprită (televizorul vede „Fără semnal”)")
T_HDMI_PORNITA = N_(u"pornită")
T_HDMI_PORNITA_STANDBY = N_(u"pornită: în standby trimite imagine neagră (setarea e Nu)")
T_HDMI_OPRITA_TREAZ = N_(u"oprită, deși receptorul nu e în standby")
T_HDMI_RESCRISA = N_(u"Ultima oprire după aprinderea televizorului: %s.")
T_CEC_NEPORNIT = N_(u"nu s-a putut porni")
T_CEC_FARA_MESAJ = N_(u"pornit, niciun mesaj trimis încă")
T_CEC_TRIMIS = N_(u"ultimul mesaj, la %s: %s")
T_CEC_NU_RASPUNDE = N_(u"Televizorul nu răspunde la CEC. Pornește SIMPLINK (sau CEC) din setările televizorului.")
T_NUME = N_(u"Numele pe televizor: %s.")
T_NUME_CERUT = N_(u"Numele pe televizor: %s, cerut de televizor la %s.")
T_TASTE_OPRITE = N_(u"Tastele televizorului: oprite din setări.")
T_TASTE_ASTEAPTA = N_(u"Tastele televizorului: pornite, nicio tastă primită încă.")
T_TASTE_ULTIMA = N_(u"Tastele televizorului: ultima, %s, la %s.")
MESAJE = {
	"standby": N_(u"stinge televizorul"),
	"inactive_source": N_(u"receptorul nu mai e pe ecran"),
	"image_view_on": N_(u"aprinde televizorul"),
	"active_source": N_(u"trece pe intrarea receptorului"),
	"report_physical_address": N_(u"anunță receptorul"),
	"set_osd_name": N_(u"anunță receptorul"),
	"report_power_status": N_(u"răspunde televizorului"),
	"cec_version": N_(u"răspunde televizorului"),
	"feature_abort": N_(u"răspunde televizorului"),
	"menu_status": N_(u"răspunde televizorului"),
}


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _st(T=None):
	if T is not None:
		return T
	from Components import HdsStandbyTv
	return HdsStandbyTv


def _ora(cand):
	try:
		return time.strftime("%H:%M", time.localtime(float(cand)))
	except (TypeError, ValueError, OverflowError, OSError):
		return ""


def textHdmi(s):
	"""(textul randului „Ieșirea HDMI”, nota de sub el) din HdsStandbyTv.stare()."""
	nota = u""
	if s.get("ultima_rescriere") and s.get("in_standby"):
		nota = _t(T_HDMI_RESCRISA) % _ora(s.get("ultima_rescriere"))
	if s.get("in_standby"):
		if s.get("oprita_de_noi") and s.get("iesire") != "pornita":
			return _t(T_HDMI_OPRITA), nota
		if not s.get("hdmi_setare"):
			return _t(T_HDMI_PORNITA_STANDBY), nota
		return _t(T_HDMI_PORNITA), nota
	if s.get("iesire") == "oprita":
		return _t(T_HDMI_OPRITA_TREAZ), nota
	return _t(T_HDMI_PORNITA), nota


def textCec(s):
	if not s.get("cec_deschis"):
		return _t(T_CEC_NEPORNIT)
	u = s.get("cec_ultimul")
	if not u:
		return _t(T_CEC_FARA_MESAJ)
	if not u.get("trimis"):
		return _t(T_CEC_NU_RASPUNDE)
	return _t(T_CEC_TRIMIS) % (_ora(u.get("cand")), _t(MESAJE.get(u.get("mesaj"), u.get("mesaj") or u"")))


def notaCec(s):
	"""Nota de sub randul "CEC": numele aratat de televizor si, daca l-a cerut, ora; apoi tastele televizorului."""
	if not s.get("cec_deschis") or not s.get("nume_tv"):
		return u""
	if s.get("nume_cerut"):
		nota = _t(T_NUME_CERUT) % (s.get("nume_tv"), _ora(s.get("nume_cerut")))
	else:
		nota = _t(T_NUME) % s.get("nume_tv")
	taste = notaTaste(s)
	return nota + (u" " + taste if taste else u"")


def notaTaste(s):
	"""Tastele televizorului (setarea "Comanda din telecomanda televizorului"): oprite, pornite fara taste sau ultima."""
	if "cec_telecomanda" not in s:
		return u""
	if not s.get("cec_telecomanda"):
		return _t(T_TASTE_OPRITE)
	u = s.get("cec_ultima_tasta")
	if not u or not u.get("eticheta"):
		return _t(T_TASTE_ASTEAPTA)
	return _t(T_TASTE_ULTIMA) % (u.get("eticheta"), _ora(u.get("cand")))


def stare(T=None, jurnal=False):
	"""GET /api/standby-tv -> (cod, corp); cu `jurnal`, si jurnalul CEC (cec.jurnal)."""
	M = _st(T)
	s = M.stare() or {}
	text, nota = textHdmi(s)
	corp = {
		"result": True,
		"in_standby": bool(s.get("in_standby")),
		"hdmi": {"disponibil": bool(s.get("hdmi_disponibil")), "setare": bool(s.get("hdmi_setare")),
			"oprita": bool(s.get("oprita_de_noi")), "iesire": s.get("iesire"), "paza": bool(s.get("paza")),
			"rescrieri_ora": int(s.get("rescrieri_ora") or 0), "text": text, "nota": nota},
		"cec": {"disponibil": bool(s.get("cec_disponibil")), "pornit": bool(s.get("cec_deschis")),
			"stinge": bool(s.get("cec_stinge")), "porneste": bool(s.get("cec_porneste")),
			"raspunde": s.get("cec_raspunde"), "text": textCec(s), "nume": s.get("nume_tv"),
			"nume_implicit": s.get("nume_implicit"), "nume_cerut": s.get("nume_cerut"),
			"primite": int(s.get("cec_primite") or 0), "nota": notaCec(s),
			"telecomanda": bool(s.get("cec_telecomanda")), "activ": bool(s.get("cec_activ")),
			"ultima_tasta": s.get("cec_ultima_tasta"), "golite": int(s.get("cec_golite") or 0)},
		"adresa_fizica": s.get("adresa_fizica"),
	}
	if jurnal:
		f = getattr(M, "jurnalCec", None)
		corp["cec"]["jurnal"] = f() if f is not None else []
	return 200, corp


def _cuJurnal(request):
	"""?jurnal=1 in cerere."""
	try:
		v = (getattr(request, "args", None) or {}).get(b"jurnal") or []
		return bool(v) and v[0] not in (b"", b"0")
	except Exception:
		return False


def rute(baza, resource=None, T=None):
	"""Resursele de sub /api: {nume: resursa}. `baza` e HdsJsonResource din plugin.py."""

	class StareResource(baza):
		def render_GET(self, request):
			try:
				cod, corp = stare(T=T, jurnal=_cuJurnal(request))
				return self._raspunde(request, corp, cod)
			except Exception as eroare:
				print("[HdsWebControl] standby si televizorul: %s" % eroare)
				return self._eroare(request, _t("Eroare pe receptor."), 500)

	class TabelResource(baza):
		"""GET /api/telecomanda-tv: tabelul tastelor televizorului (pagina /telecomanda-tv)."""

		def render_GET(self, request):
			try:
				corp = tabel(T=T)
				return self._raspunde(request, corp, 200 if corp.get("result") else 500)
			except Exception as eroare:
				print("[HdsWebControl] tastele televizorului: %s" % eroare)
				return self._eroare(request, _t("Eroare pe receptor."), 500)

	return {b"standby-tv": StareResource(), b"telecomanda-tv": TabelResource()}


# ---------------------------------------------------------------- randurile din panoul principal

# sfarsitul randului "Standby" al panoului, fara textul lui (panoul se traduce in limba receptorului)
ANCORA_HTML = u'<span id="stStandby">-</span></div>'
ANCORA_CSS = u"</style>"
ANCORA_JS = u"</script>"

# numele randului, tradus la punere (panoul e deja tradus cand primeste randurile)
T_RAND_HDMI = N_(u"Ieșirea HDMI")
PANOU_HTML = u"""
      <div class="status-linie cu-nota stb-tv ascuns" id="stbHdmiRand"><span>Ieșirea HDMI</span><span class="stb-val" id="stbHdmi">-</span><span class="nota-rand ascuns" id="stbHdmiNota"></span></div>
      <div class="status-linie cu-nota stb-tv ascuns" id="stbCecRand"><span>CEC</span><span class="stb-val" id="stbCec">-</span><span class="nota-rand ascuns" id="stbCecNota"></span></div>"""

PANOU_CSS = u"""  .stb-tv.ascuns,.stb-tv .ascuns{display:none;}
  .stb-tv .stb-val{margin-left:auto;text-align:right;word-break:break-word;}
  .stb-tv .stb-val.atentie{color:#f5b83d;}
"""

PANOU_JS = u"""function standbyTvDeseneaza(d){
  var h = document.getElementById("stbHdmiRand"), c = document.getElementById("stbCecRand");
  if(!d || !d.result){ h.classList.add("ascuns"); c.classList.add("ascuns"); return; }
  h.classList.toggle("ascuns", !(d.hdmi && d.hdmi.disponibil));
  c.classList.toggle("ascuns", !(d.cec && d.cec.disponibil));
  if(d.hdmi){
    document.getElementById("stbHdmi").textContent = d.hdmi.text || "-";
    var n = document.getElementById("stbHdmiNota");
    n.textContent = d.hdmi.nota || ""; n.classList.toggle("ascuns", !d.hdmi.nota);
  }
  if(d.cec){
    var v = document.getElementById("stbCec");
    v.textContent = d.cec.text || "-";
    v.classList.toggle("atentie", d.cec.pornit && d.cec.raspunde === false);
    var cn = document.getElementById("stbCecNota");
    cn.textContent = d.cec.nota || ""; cn.classList.toggle("ascuns", !d.cec.nota);
  }
}
function actualizeazaStandbyTv(){
  cerere("/api/standby-tv").then(standbyTvDeseneaza).catch(function(){}).then(function(){
    setTimeout(actualizeazaStandbyTv, 5000);
  });
}
actualizeazaStandbyTv();
"""


def in_panou(pagina):
	"""Panoul principal cu randurile „Ieșirea HDMI” si „CEC”: HTML-ul sub randul „Standby”, stilul inainte de primul
	</style>, scriptul inainte de ultimul </script>. Fara oricare ancora pagina ramane cum e."""
	try:
		if ANCORA_HTML not in pagina or ANCORA_CSS not in pagina or ANCORA_JS not in pagina or "stbHdmiRand" in pagina:
			return pagina
		rand = _t(T_RAND_HDMI).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
		html = PANOU_HTML.replace(u"<span>%s</span>" % T_RAND_HDMI, u"<span>%s</span>" % rand, 1)
		pagina = pagina.replace(ANCORA_HTML, ANCORA_HTML + html, 1)
		pagina = pagina.replace(ANCORA_CSS, PANOU_CSS + ANCORA_CSS, 1)
		i = pagina.rindex(ANCORA_JS)
		return pagina[:i] + _traducePagina(PANOU_JS, "js") + pagina[i:]
	except Exception as eroare:
		print("[HdsWebControl] randurile standby si televizorul: %s" % eroare)
		return pagina


# ---------------------------------------------------------------- pagina /telecomanda-tv (tastele televizorului)

T_PAGINA_TITLU = N_(u"Telecomanda televizorului")
T_PAGINA_DESPRE = N_(u"Cu SIMPLINK (CEC) pornit pe televizor, tastele telecomenzii televizorului comandă receptorul cât televizorul îl arată. Puterea și volumul rămân ale televizorului.")
T_PAGINA_OPRITA = N_(u"Comanda din telecomanda televizorului e oprită. O pornești în Setări, Standby și televizorul.")
T_COL_RECEPTOR = N_(u"Tasta receptorului")
T_COL_TV = N_(u"Pe telecomanda televizorului")
T_PAGINA_PANOU = N_(u"Tastele pe care telecomanda televizorului nu le are: pe televizor ține apăsat OK, sau apasă-le aici.")
T_TRIMISA = N_(u"Trimisă: %s.")
T_NETRIMISA = N_(u"Receptorul nu a primit tasta.")


def tabel(T=None):
	"""GET /api/telecomanda-tv: tabelul tastelor si tastele panoului (pentru pagina)."""
	M = _st(T)
	rez = {"result": True, "titlu": _t(T_PAGINA_TITLU), "despre": _t(T_PAGINA_DESPRE),
		"coloane": [_t(T_COL_RECEPTOR), _t(T_COL_TV)], "panou_text": _t(T_PAGINA_PANOU),
		"trimisa": _t(T_TRIMISA), "netrimisa": _t(T_NETRIMISA)}
	try:
		s = M.stare() or {}
		rez["pornita"] = bool(s.get("cec_telecomanda"))
		rez["oprita_text"] = u"" if rez["pornita"] else _t(T_PAGINA_OPRITA)
		rez["randuri"] = [{"cod": cod, "receptor": e, "tv": c} for cod, e, c in M.tabelTaste()]
		rez["panou"] = [{"cod": cod, "eticheta": M.etichetaTastei(cod)} for cod in M.PANOU_TASTE]
	except Exception as eroare:
		return {"result": False, "message": "%s" % eroare}
	return rez


PAGINA_TELECOMANDA = u"""<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLU__</title>
<style>__STIL_COMUN__
  main{max-width:820px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 10px;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .nota{color:var(--text-slab);font-size:.9rem;line-height:1.45;margin:0 0 10px;}
  table{width:100%;border-collapse:collapse;font-size:.95rem;}
  th,td{text-align:left;padding:8px 6px;border-bottom:1px solid var(--bordura);vertical-align:top;}
  th{color:var(--text-slab);font-weight:600;}
  .taste{display:flex;flex-wrap:wrap;gap:8px;}
  .taste button{min-height:44px;min-width:44px;padding:8px 12px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  .ascuns{display:none;}
</style>
</head>
<body>
<main>
  <h1 id="titlu">__TITLU__</h1>
  <p class="nota" id="despre"></p>
  <p class="nota ascuns" id="oprita"></p>
  <div class="card"><table><thead><tr><th id="c1"></th><th id="c2"></th></tr></thead><tbody id="randuri"></tbody></table></div>
  <div class="card"><p class="nota" id="panouText"></p><div class="taste" id="panou"></div><p class="nota" id="mesaj" aria-live="polite"></p></div>
</main>
<script>
var CFG = __CONFIG__;
var DATE = null;
function $(id){ return document.getElementById(id); }
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
function cerere(cale, metoda){
  var optiuni = {method: metoda || "GET", cache: "no-store", credentials: "same-origin", headers: {}};
  if(CFG.csrf){ optiuni.headers["X-HDS-CSRF"] = CFG.csrf; }
  return fetch(adresa(cale), optiuni).then(function(r){
    if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("browser deconectat"); }
    return r.json();
  });
}
function trimite(t){
  cerere("/api/remotecontrol?command=" + t.cod, "POST").then(function(d){
    $("mesaj").textContent = d && d.result ? DATE.trimisa.replace("%s", t.eticheta) : DATE.netrimisa;
  }).catch(function(){ $("mesaj").textContent = DATE.netrimisa; });
}
function arata(d){
  DATE = d;
  $("titlu").textContent = d.titlu; document.title = d.titlu;
  $("despre").textContent = d.despre;
  $("oprita").textContent = d.oprita_text || ""; $("oprita").classList.toggle("ascuns", !d.oprita_text);
  $("c1").textContent = d.coloane[0]; $("c2").textContent = d.coloane[1];
  var tb = $("randuri"); tb.textContent = "";
  (d.randuri || []).forEach(function(r){
    var tr = document.createElement("tr"), a = document.createElement("td"), b = document.createElement("td");
    a.textContent = r.receptor; b.textContent = r.tv; tr.appendChild(a); tr.appendChild(b); tb.appendChild(tr);
  });
  $("panouText").textContent = d.panou_text;
  var p = $("panou"); p.textContent = "";
  (d.panou || []).forEach(function(t){
    var b = document.createElement("button"); b.type = "button"; b.textContent = t.eticheta;
    b.addEventListener("click", function(){ trimite(t); }); p.appendChild(b);
  });
}
cerere("/api/telecomanda-tv").then(function(d){ if(d && d.result){ arata(d); } }).catch(function(){});
</script>
</body>
</html>
"""


def pagina_telecomanda(request):
	"""GET /telecomanda-tv: pagina cu tabelul tastelor televizorului si tastele panoului (aceeasi poarta ca /setari)."""
	from . import plugin as P
	if not P._esteAdresaLocala(P._adresaClient(request)):
		request.setResponseCode(403)
		request.setHeader(b"content-type", b"text/plain; charset=utf-8")
		return u_t("Acces permis doar din rețeaua locală.").encode("utf-8")
	P._anteteHtml(request)
	if P.PARAM_JETON in request.args and P._jetonValid(request):
		config_pagina = P._configPanou("", P._jetonConfigurat(), "")
	else:
		secret, browser = P._sesiuneDinCerere(request)
		if browser is None:
			return P._PAGINA_ASOCIERE.encode("utf-8")
		config_pagina = P._configPanou(P.csrfPentru(secret), "", browser.get("nume", ""))
	return pagina_text(P._STIL_COMUN, config_pagina).encode("utf-8", "replace")


def pagina_text(stil, config_pagina):
	import html
	return _traducePagina(PAGINA_TELECOMANDA).replace("__STIL_COMUN__", stil).replace("__CONFIG__", config_pagina).replace(
		"__TITLU__", html.escape(_t(T_PAGINA_TITLU), quote=False))


def pagina_resursa(resource):
	"""Resursa paginii /telecomanda-tv (legata in plugin.py)."""

	class PaginaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			return pagina_telecomanda(request)

	return PaginaResource()


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
