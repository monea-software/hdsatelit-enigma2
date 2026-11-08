# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Sloturile si setarile din Screens.Ci.CiSelection, prin poarta web comuna.

Se citesc stari deja pastrate in memorie. Nu se asteapta raspunsul modulului.
MMI are un singur consumator: getMMIScreen sterge semnul mmiScreenReady.
O citire web ar putea lua mesajul inaintea dialogului de pe televizor.
"""

MAX_SLOTURI = 4
SETARI = {
	"canDescrambleMultipleServices": ("Multiple service support", ("auto", "no", "yes")),
	"canHandleHighBitrates": ("High bitrate support", ("no", "yes")),
}


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def N_(text):
	return text


def _ci():
	from enigma import eDVBCI_UI
	from Components.config import config
	from Components.SystemInfo import SystemInfo
	return eDVBCI_UI.getInstance(), config, SystemInfo.get("CommonInterfaceSupportsHighBitrates", False)


def _setari(config, slot, debit):
	rezultat = {}
	for nume, (text, valori) in SETARI.items():
		if nume == "canHandleHighBitrates" and not debit:
			continue
		element = getattr(config.ci[slot], nume)
		rezultat[nume] = {"text": _t(text), "valoare": element.value,
			"alegeri": [(v, _t({"auto": "Auto", "no": "No", "yes": "Yes"}[v])) for v in valori]}
	return rezultat


def stare():
	ui, config, debit = _ci()
	sloturi = []
	for slot in range(MAX_SLOTURI):
		cod = ui.getState(slot)
		if cod == -1:
			continue
		text = {0: _t("no module found"), 1: _t("init module"), 2: _t("Modul pregătit.")}
		sloturi.append({"slot": slot, "titlu": _t("Slot %d") % (slot + 1),
			"stare": cod, "text": text.get(cod, _t("Stare CI necunoscută.")),
			"modul": ui.getAppName(slot) if cod == 2 else "",
			"setari": _setari(config, slot, debit)})
	return {"result": True, "sloturi": sloturi,
		"message": "" if sloturi else _t("Receptorul nu are sloturi CI."),
		"mmi_motiv": _t("Meniul MMI al modulului se folosește pe televizor. "
			"Citirea lui din web ar putea consuma mesajul destinat televizorului.")}


def comanda(date):
	ui, config, debit = _ci()
	text_slot = date.get("slot", "")
	if text_slot not in tuple(str(n) for n in range(MAX_SLOTURI)):
		return {"result": False, "message": _t("Slot CI nevalid.")}
	slot = int(text_slot)
	if ui.getState(slot) == -1:
		return {"result": False, "message": _t("Slot CI nevalid.")}
	actiune = date.get("actiune", "")
	if actiune == "reset":
		ui.setReset(slot)
	elif actiune == "init":
		ui.setInit(slot)
	elif actiune == "salveaza":
		setari = _setari(config, slot, debit)
		chei = set(date) - {"actiune", "slot", "token"}
		if not chei or any(k not in setari or date[k] not in SETARI[k][1] for k in chei):
			return {"result": False, "message": _t("Setare CI nevalidă.")}
		# Validam toate valorile inainte de prima schimbare si de notificarile ei.
		for nume in setari:
			if nume in chei:
				element = getattr(config.ci[slot], nume)
				element.value = date[nume]
				element.save()
	else:
		return {"result": False, "message": _t("Comandă CI necunoscută.")}
	return {"result": True, "message": _t("Comanda CI a fost trimisă.")}


def argumente(request):
	rezultat = {}
	for cheie, valori in (getattr(request, "args", None) or {}).items():
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		valoare = (valori or [b""])[0]
		if isinstance(valoare, bytes):
			valoare = valoare.decode("utf-8", "replace")
		rezultat[cheie] = str(valoare)
	return rezultat


def rute(baza, resource):
	class Stare(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, stare())
			except Exception as eroare:
				print("[HdsWebControl] citire CI: %r" % (eroare,))
				return self._eroare(request, _t("Sloturile CI nu se pot citi acum."), 503)

	class Comanda(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, comanda(argumente(request)))
			except Exception as eroare:
				print("[HdsWebControl] comanda CI: %r" % (eroare,))
				return self._eroare(request, _t("Comanda CI nu se poate executa acum."), 503)

		def render_GET(self, request):
			return self._eroare(request, _t("Comenzile CI cer POST."), 405)

	class Pagina(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			from .meniu_comun_web import pagina
			return pagina(request, pagina_text)

	return ({b"ci": Stare(), b"ci-comanda": Comanda()}, {b"common-interface": Pagina()})


def pagina_text(stil, config_pagina):
	from .meniu_comun_web import sablon
	from .traducere_pagini import traduce
	return sablon(traduce(PAGINA, TEXTE_PAGINA), stil, config_pagina)


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Common Interface</title>
<style>__STIL_COMUN__ __STIL_PAGINI__
.slot select{max-width:100%;min-height:44px;}
.slot label{display:block;margin:12px 0;}
.slot label span{display:block;margin-bottom:6px;}
.slot h2,.slot p{overflow-wrap:anywhere;}
</style>
</head>
<body><main>
<h1>Common Interface</h1>
<p id="mesaj" class="mesaj" role="status" aria-live="polite">Se citesc sloturile CI...</p>
<div id="sloturi"></div>
<p id="mmi" class="nota"></p>
</main>
<script>
__SCRIPT_COMUN__
var ocupat = false, modificate = {}, prima = true;
function el(tip, text){
  var nod = document.createElement(tip);
  if(text !== undefined){ nod.textContent = text; }
  return nod;
}
function trimite(slot, actiune, formular){
  if(ocupat){ return; }
  ocupat = true;
  var revizie = modificate[slot];
  var date = formular ? new URLSearchParams(new FormData(formular)) : new URLSearchParams();
  date.set("slot", slot); date.set("actiune", actiune);
  cerere("/api/ci-comanda", "POST", date).then(function(d){
    mesaj(d.message, !d.result);
    if(d.result){
      if(actiune === "salveaza" && modificate[slot] === revizie){ delete modificate[slot]; }
      return citeste();
    }
  }).catch(nimicNuRaspunde).then(function(){ ocupat = false; });
}
function arata(d){
  var loc = $("sloturi"); loc.textContent = "";
  $("mmi").textContent = d.sloturi.length ? d.mmi_motiv : "";
  if(!d.sloturi.length){ mesaj(d.message); }
  d.sloturi.forEach(function(s){
    var card = el("section"); card.className = "card slot";
    card.appendChild(el("h2", s.titlu));
    card.appendChild(el("p", s.text));
    if(s.modul){ card.appendChild(el("p", s.modul)); }
    var butoane = el("div"); butoane.className = "butoane";
    [["Reset", "reset"], ["Init", "init"]].forEach(function(a){
      var b = el("button", a[0]); b.type = "button";
      b.addEventListener("click", function(){ trimite(s.slot, a[1]); });
      butoane.appendChild(b);
    });
    card.appendChild(butoane);
    var formular = el("form");
    Object.keys(s.setari).forEach(function(nume){
      var setare = s.setari[nume], label = el("label"), select = el("select");
      label.appendChild(el("span", setare.text)); select.name = nume;
      setare.alegeri.forEach(function(a){
        var opt = el("option", a[1]); opt.value = a[0]; select.appendChild(opt);
      });
      select.value = setare.valoare; label.appendChild(select); formular.appendChild(label);
      select.addEventListener("change", function(){ modificate[s.slot] = (modificate[s.slot] || 0) + 1; });
    });
    var salveaza = el("button", "Salvează"); salveaza.type = "submit";
    formular.appendChild(salveaza);
    formular.addEventListener("submit", function(e){ e.preventDefault(); trimite(s.slot, "salveaza", formular); });
    card.appendChild(formular); loc.appendChild(card);
  });
}
function citeste(){
  return cerere("/api/ci").then(function(d){
    if(d.result){
      // Un raspuns deja in zbor nu trebuie sa stearga editarile nesalvate.
      if(Object.keys(modificate).length){ return; }
      if(prima){ mesaj(""); prima = false; }
      arata(d);
    } else { mesaj(d.message, true); }
  });
}
// Citirea urmatoare incepe dupa raspuns; nu inlocuieste un formular editat.
function bucla(){
  var editeaza = document.activeElement && /^(SELECT|OPTION)$/.test(document.activeElement.tagName);
  var pas = document.hidden || ocupat || Object.keys(modificate).length || editeaza
    ? Promise.resolve() : citeste().catch(nimicNuRaspunde);
  pas.then(function(){ setTimeout(bucla, 5000); });
}
bucla();
</script>
</body></html>
"""

TEXTE_PAGINA = {
	"html": (N_("Common Interface"), N_("Se citesc sloturile CI...")),
	"js": (N_("Reset"), N_("Init"), N_("Salvează")),
}
