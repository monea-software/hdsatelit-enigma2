# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# canal_info_web.py: Informatii despre canal in interfata web (HdsWebControl). Orice ecran de pe receptor are pereche
# in web.
#
# Pe televizor: Meniu > Informatii despre sistem > Channel Information (Screens/ServiceInfo.py), cu patru pagini pe
# tastele colorate: Rosu Serviciu (numele, furnizorul, formatul, rezolutia, HDR, namespace, referinta), Verde PID-uri
# (video, audio, PCR, PMT, teletext, TSID, ONID, SID, in hex si zecimal), Galben Multiplex (tunerul, felul transmisiei,
# satelitul, frecventa, rata de simboluri, polarizarea, modulatia, FEC si restul parametrilor), Albastru Stare tuner
# (tunerele receptorului, sincronizarea, calitatea si nivelul semnalului, rata erorilor). Aici: aceleasi patru pagini,
# toate odata, numai citire, citite din nou la cateva secunde, din aceleasi randuri (Components/HdsInformatiiCanal.py,
# folosit si de ecran). Fara canal (sau in standby, cand receptorul nu reda nimic) randurile arata ca pe televizor
# (N/A si randurile goale); pagina spune in plus ca receptorul e in standby.
#
# Rute (poarta comuna a HdsJsonResource):
#   GET  /api/informatii-canal    cele patru pagini: {"pagini": [{"id", "randuri": [[eticheta, valoare]]}], ...}
#   GET  /informatii-canal        pagina
#
# FIRUL: pe firul enigma2, scurt (informatiile serviciului de acum si starea tunerului, ca ecranul). Fisierul nu
# importa nimic din enigma2 la incarcare: probele de pe PC dau navigatia, serviciul si tunerele lor.

PAGINI = ("serviciu", "pid", "multiplex", "tuner")


def _t(text):
	from .meniu_comun_web import _t as t
	return t(text)


def _M():
	from . import meniu_comun_web
	return meniu_comun_web


def _jurnal(text):
	print("[HdsWebControl] informatii canal: %s" % text)


def _h(H=None):
	if H is not None:
		return H
	from Components import HdsInformatiiCanal
	return HdsInformatiiCanal


class Mediu(object):
	"""Ce ii trebuie paginii din enigma2, luat la cerere; probele de pe PC dau obiectele lor."""

	def __init__(self, nav=None, I=None, centru=None, convertor=None, nimmanager=None, ServiceReference=None,
			rec_info=None, nume_receptor=None, in_standby=None):
		self.nav, self.I, self.centru, self.convertor = nav, I, centru, convertor
		self.nimmanager, self.ServiceReference, self.rec_info = nimmanager, ServiceReference, rec_info
		self.nume_receptor, self.in_standby = nume_receptor, in_standby

	def completeaza(self):
		if self.nav is None:
			import NavigationInstance
			self.nav = NavigationInstance.instance
		if self.I is None:
			from enigma import iServiceInformation
			self.I = iServiceInformation
		if self.centru is None:
			from enigma import eServiceCenter
			self.centru = eServiceCenter.getInstance()
		if self.convertor is None:
			from Tools.Transponder import ConvertToHumanReadable
			self.convertor = ConvertToHumanReadable
		if self.nimmanager is None:
			from Components.NimManager import nimmanager
			self.nimmanager = nimmanager
		if self.ServiceReference is None:
			from ServiceReference import ServiceReference
			self.ServiceReference = ServiceReference
		return self

	def recInfo(self):
		if self.rec_info is not None:
			return self.rec_info
		# legatura emulatorului cu receptorul (pe receptor: is_pc_emu fals), din ecran, unde o pazesc probele
		from Screens.ServiceInfo import getReceiverConnectionInfo
		return getReceiverConnectionInfo()

	def numeReceptor(self):
		if self.nume_receptor is not None:
			return self.nume_receptor
		from Components.About import about
		return about.getReceiverName()

	def standby(self):
		if self.in_standby is not None:
			return bool(self.in_standby)
		try:
			from Screens.Standby import inStandby
			return inStandby is not None
		except Exception:
			return False


def stare(mediu=None, H=None):
	"""GET /api/informatii-canal: cele patru pagini ale ecranului, pentru canalul de acum."""
	H = _h(H)
	m = (mediu or Mediu()).completeaza()
	nav = m.nav
	service = nav.getCurrentService() if nav is not None else None
	info = service.info() if service is not None else None
	feinfo = service.frontendInfo() if service is not None else None
	ref = nav.getCurrentlyPlayingServiceReference() if nav is not None else None
	nume, refstr = H.numeSiReferinta(ref, m.ServiceReference)
	ref_text = ref.toString() if ref else ""
	rec_info = m.recInfo()

	def serviciu():
		return H.randuriServiciu(info, m.I, nume, refstr)

	def pid():
		return H.randuriPid(info, m.I)

	def multiplex():
		return H.randuriTransponder(H.dateFrontend(feinfo, ref, info, m.centru, m.I), ref_text, rec_info, m.convertor)

	def tuner():
		mod = "" if rec_info["is_pc_emu"] else _t("Direct pe receptorul %s") % m.numeReceptor()
		return H.randuriTuner(rec_info, feinfo, ref, m.centru, m.I, m.nimmanager, mod)

	pagini = []
	for id_pagina, functie in zip(PAGINI, (serviciu, pid, multiplex, tuner)):
		try:
			pagini.append({"id": id_pagina, "randuri": [list(r) for r in H.randuriText(functie())]})
		except Exception as eroare:
			# o pagina care nu se poate citi (pe televizor ecranul ar cadea) nu le ascunde pe celelalte
			_jurnal("%s: %r" % (id_pagina, eroare))
			pagini.append({"id": id_pagina, "randuri": [], "eroare": _t("Pagina aceasta nu s-a putut citi acum.")})
	return {"result": True, "are_canal": bool(ref), "standby": m.standby(), "pagini": pagini}


def rute(baza, resource, mediu=None, H=None):
	"""({nume: resursa de sub /api}, {nume: resursa pagina}); `mediu` si `H` sunt pentru probele de pe PC."""

	class StareResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(mediu, H))
			except Exception as eroare:
				_jurnal(repr(eroare))
				return self._eroare(request, _t("Eroare pe receptor."), 500)

	class PaginaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			return _M().pagina(request, pagina_text, False)

	return {b"informatii-canal": StareResource()}, {b"informatii-canal": PaginaResource()}


def pagina_text(stil, config_pagina):
	M = _M()
	return M.sablon(_traducePagina(PAGINA), stil, config_pagina, {"__DRUM_MENIU__": M.drumHtml("service_info_screen")})


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Informații despre canal</title>
<style>__STIL_COMUN__
__STIL_PAGINI__
  .pagini{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,400px),1fr));gap:12px;}
  .pagini .card{margin:0;}
  .status-linie>span:first-child{flex:0 0 auto;max-width:55%;}
  .rand-plin{padding:8px 0;border-bottom:1px solid var(--bordura);font-size:.9rem;overflow-wrap:anywhere;}
  .rand-plin:last-child{border-bottom:0;}
</style>
</head>
<body>
<main>
<h1>Informații despre canal</h1>
<p class="mesaj" id="incarcare">Se citesc informațiile...</p>
<div id="continut" class="ascuns">
  <p class="nota ascuns" id="standby">Receptorul e în standby: nu redă niciun canal, deci rândurile arată ca pe televizor fără canal.</p>
  <div class="pagini">
    <section class="card"><h2>Serviciu</h2><div id="p_serviciu"></div></section>
    <section class="card"><h2>PID-uri</h2><div id="p_pid"></div></section>
    <section class="card"><h2>Multiplex</h2><div id="p_multiplex"></div></section>
    <section class="card"><h2>Stare tuner</h2><div id="p_tuner"></div></section>
  </div>
  <p class="nota">Numai citire. Pagina se citește din nou la câteva secunde. Pe televizor, aceleași rânduri sunt pe tastele colorate (Roșu, Verde, Galben, Albastru), în __DRUM_MENIU__.</p>
</div>
<p class="mesaj" id="mesaj"></p>
<div id="confirmare" class="card ascuns"></div>
</main>
<script>
__SCRIPT_COMUN__
function arataPagina(p){
  var c = $("p_" + p.id); if(!c){ return; }
  c.textContent = "";
  if(p.eroare){ var e = document.createElement("p"); e.className = "nota eroare"; e.textContent = p.eroare; c.appendChild(e); return; }
  (p.randuri || []).forEach(function(r){
    if(!r[0] && !r[1]){ return; }
    if(!r[0]){ var d = document.createElement("div"); d.className = "rand-plin"; d.textContent = r[1]; c.appendChild(d); return; }
    var l = document.createElement("div"); l.className = "status-linie";
    var a = document.createElement("span"); a.textContent = r[0].replace(/:$/, "");
    var b = document.createElement("span"); b.textContent = r[1];
    l.appendChild(a); l.appendChild(b); c.appendChild(l);
  });
}
function citeste(){
  if(document.hidden){ return; }
  cerere("/api/informatii-canal").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi informațiile."; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    $("standby").classList.toggle("ascuns", !d.standby);
    (d.pagini || []).forEach(arataPagina);
    mesaj("");
  }).catch(function(){
    if(!$("continut").classList.contains("ascuns")){ nimicNuRaspunde(); return; }
    $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea.";
  });
}
citeste();
setInterval(citeste, 4000);
document.addEventListener("visibilitychange", citeste);
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
		N_("Informații despre canal"),
		N_("Se citesc informațiile..."),
		N_("Receptorul e în standby: nu redă niciun canal, deci rândurile arată ca pe televizor fără canal."),
		N_("Serviciu"),
		N_("PID-uri"),
		N_("Multiplex"),
		N_("Stare tuner"),
		N_("Numai citire. Pagina se citește din nou la câteva secunde. Pe televizor, aceleași rânduri sunt "
			"pe tastele colorate (Roșu, Verde, Galben, Albastru), în __DRUM_MENIU__."),
	),
	"js": (
		N_("Receptorul nu a putut citi informațiile."),
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
