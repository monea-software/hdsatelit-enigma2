# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Sloturile si setarile din Screens.Ci.CiSelection, prin poarta web comuna.

Se citesc stari deja pastrate in memorie. Nu se asteapta raspunsul modulului.
MMI are un singur consumator: getMMIScreen sterge semnul mmiScreenReady.
O citire web ar putea lua mesajul inaintea dialogului de pe televizor.
"""

import json

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


def _alocari():
	from Tools import CIHelper
	return CIHelper


def _slot_alocare(date, ui):
	text = date.get("slot", "")
	if text not in tuple(str(n) for n in range(MAX_SLOTURI)) or ui.getState(int(text)) != 2:
		raise ValueError("slot")
	return int(text)


def alocare(date):
	ui, config, debit = _ci()
	try:
		slot = _slot_alocare(date, ui)
	except ValueError:
		return {"result": False, "message": _t("Modulul CI nu mai este pregătit.")}
	helper = _alocari()
	editor = helper.citesteEditor(slot)
	try:
		cunoscute = helper.caidCunoscute(slot)
	except Exception:
		cunoscute = []
	return dict(editor, result=True, cunoscute=cunoscute)


def alegeri(date):
	ui, config, debit = _ci()
	try:
		_slot_alocare(date, ui)
		de_la = int(date.get("de_la", "0"))
		text = date.get("text", "")
		if not 0 <= de_la <= 100000 or len(text) > 60:
			raise ValueError("pagina")
		rezultat = _alocari().alegeriAlocare(date.get("fel", ""), text, de_la, 100)
		return dict(rezultat, result=True)
	except ValueError:
		return {"result": False, "message": _t("Alegere CI nevalidă.")}


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
			"alocare": cod == 2,
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
		chei = set(date) - {"actiune", "slot", "token", "initiale"}
		if not chei or any(k not in setari or date[k] not in SETARI[k][1] for k in chei):
			return {"result": False, "message": _t("Setare CI nevalidă.")}
		try:
			initiale = json.loads(date["initiale"])
			if not isinstance(initiale, dict) or any(n not in initiale for n in chei):
				raise ValueError("initiale")
		except (KeyError, ValueError, TypeError):
			return {"result": False, "message": _t("Recitește setările slotului înainte de salvare.")}
		if any(getattr(config.ci[slot], n).value != initiale[n] for n in chei):
			return {"result": False, "message": _t("Setările slotului s-au schimbat din alt ecran. Alegerile tale rămân în formular. Redeschide pagina pentru datele actuale.")}
		# Validam toate valorile inainte de prima schimbare si de notificarile ei.
		for nume in setari:
			if nume in chei:
				element = getattr(config.ci[slot], nume)
				element.value = date[nume]
				element.save()
	elif actiune in ("alocare-salveaza", "alocare-aplica"):
		helper = _alocari()
		try:
			_slot_alocare(date, ui)
			if set(date) - {"actiune", "slot", "token", "reguli", "revizie"}:
				raise ValueError("camp")
			if actiune == "alocare-aplica":
				editor = helper.reaplicaAlocarea(slot, date.get("revizie"))
			else:
				text = date.get("reguli", "")
				if len(text) > 256 * 1024:
					raise ValueError("reguli")
				reguli = helper.valideazaAlocarea(json.loads(text))
				editor = helper.salveazaEditor(slot, reguli, date.get("revizie"))
		except helper.AlocareSchimbata:
			return {"result": False, "message": _t("Alocările CI s-au schimbat din alt ecran. Ciorna rămâne aici. Redeschide editorul pentru datele actuale.")}
		except helper.AlocareNeaplicata as eroare:
			return {"result": False, "salvat": True, "aplicat": False, "revizie": eroare.revizie,
				"message": _t("Salvat, neaplicat. Verifică modulul și alege Reîncearcă aplicarea. Închide păstrează salvarea.")}
		except (ValueError, TypeError):
			return {"result": False, "message": _t("Alocare CI nevalidă.")}
		return {"result": True, "salvat": True, "aplicat": True, "revizie": editor["revizie"],
			"message": _t("Alocările CI au fost salvate și aplicate.")}
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
	class Alocare(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, alocare(argumente(request)))
			except Exception as eroare:
				print("[HdsWebControl] citire alocari CI: %r" % (eroare,))
				return self._eroare(request, _t("Alocările CI nu se pot citi. Fișierul existent a fost păstrat."), 503)

	class Alegeri(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, alegeri(argumente(request)))
			except Exception as eroare:
				print("[HdsWebControl] alegeri CI: %r" % (eroare,))
				return self._eroare(request, _t("Lista de canale nu se poate citi acum."), 503)

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

	return ({b"ci": Stare(), b"ci-comanda": Comanda(), b"ci-alocare": Alocare(), b"ci-alegeri": Alegeri()},
		{b"common-interface": Pagina()})


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
.alocare{margin-top:20px;border-top:1px solid;padding-top:15px;}
.alocare li{margin:8px 0;overflow-wrap:anywhere;}
.alocare li button{margin-left:12px;}
.alocare input,.alocare select{max-width:100%;width:100%;min-height:44px;}
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
var ocupat = false, modificate = {}, editoare = {}, prima = true;
function el(tip, text){
  var nod = document.createElement(tip);
  if(text !== undefined){ nod.textContent = text; }
  return nod;
}
function trimite(slot, actiune, formular, initiale){
  if(ocupat){ return; }
  ocupat = true;
  var revizie = modificate[slot];
  var date = formular ? new URLSearchParams(new FormData(formular)) : new URLSearchParams();
  if(actiune === "salveaza"){
    Object.keys(initiale).forEach(function(n){ if(date.get(n) === initiale[n]){ date.delete(n); } });
    if(!Array.from(date.keys()).length){ delete modificate[slot]; ocupat = false; return; }
    date.set("initiale", JSON.stringify(initiale));
  }
  date.set("slot", slot); date.set("actiune", actiune);
  cerere("/api/ci-comanda", "POST", date).then(function(d){
    mesaj(d.message, !d.result);
    if(d.result){
      if(initiale){ Object.keys(initiale).forEach(function(n){ if(date.has(n)){ initiale[n] = date.get(n); } }); }
      if(actiune === "salveaza" && modificate[slot] === revizie){ delete modificate[slot]; }
      return citeste();
    }
  }).catch(nimicNuRaspunde).then(function(){ ocupat = false; });
}
function eticheta(text, nod){
  var label = el("label"); label.appendChild(el("span", text)); label.appendChild(nod); return label;
}
function deschideAlocare(s, card, buton){
  if(ocupat || editoare[s.slot]){ return; }
  ocupat = true;
  editoare[s.slot] = {};
  cerere("/api/ci-alocare?slot=" + s.slot).then(function(d){
    if(!d.result){ delete editoare[s.slot]; mesaj(d.message, true); return; }
    var formular = el("form"), lista = el("ul"), draft = {rev:0, salvata:0, revizie:d.revizie, neaplicata:d.neaplicata};
    formular.className = "alocare"; editoare[s.slot] = draft; buton.disabled = true;
    var reguli = d.reguli;
    formular.appendChild(el("h3", "Alocă canale modulului")); formular.appendChild(lista);
    formular.appendChild(el("p", "Decodările multiple se schimbă în setările slotului."));
    var stareEditor = el("p"); stareEditor.setAttribute("role", "status"); formular.appendChild(stareEditor);
    function schimbata(){ draft.rev++; stareSalvare(); }
    function randuri(){
      lista.textContent = "";
      [["servicii", "Canal"], ["furnizori", "Furnizor"], ["caid", "CAID"]].forEach(function(f){
        reguli[f[0]].forEach(function(r, index){
          var text = f[0] === "caid" ? r.toString(16).toUpperCase().padStart(4, "0") : r.name;
          if(f[0] === "furnizori"){ text += " [" + r.namespace.toString(16).toUpperCase().padStart(8, "0") + "]"; }
          var li = el("li", f[1] + ": " + text), sterge = el("button", "Șterge"); sterge.type = "button";
          sterge.addEventListener("click", function(){ reguli[f[0]].splice(index, 1); schimbata(); randuri(); });
          li.appendChild(sterge); lista.appendChild(li);
        });
      });
      if(!lista.children.length){ lista.appendChild(el("li", "Nu sunt alocări. Se păstrează alegerea automată a modulului.")); }
    }
    function adauga(fel, valoare){
      var cheie = JSON.stringify(valoare);
      if(!reguli[fel].some(function(r){ return JSON.stringify(r) === cheie; })){
        reguli[fel].push(valoare); schimbata(); randuri();
      }
    }
    var fel = el("select");
    [["servicii", "Canale"], ["furnizori", "Furnizori"]].forEach(function(v){ var o = el("option", v[1]); o.value = v[0]; fel.appendChild(o); });
    fel.value = "servicii"; formular.appendChild(eticheta("Adaugă din lista receptorului", fel));
    var cautare = el("input"); cautare.type = "search"; cautare.maxLength = 60;
    formular.appendChild(eticheta("Caută după nume", cautare));
    var cauta = el("button", "Caută"), rezultate = el("select"), adaugaAles = el("button", "Adaugă selecția");
    var inapoi = el("button", "Înapoi"), inainte = el("button", "Mai multe"), optiuni = [], deLa = 0, generatie = 0;
    rezultate.size = 6; rezultate.setAttribute("aria-label", "Canale sau furnizori");
    [cauta, adaugaAles, inapoi, inainte].forEach(function(b){ b.type = "button"; });
    adaugaAles.disabled = true; inapoi.disabled = true; inainte.disabled = true;
    function cautaLista(start){
      var numar = ++generatie, tip = fel.value, text = cautare.value;
      adaugaAles.disabled = true; inapoi.disabled = true; inainte.disabled = true; rezultate.disabled = true;
      var date = new URLSearchParams({slot:s.slot, fel:tip, text:text, de_la:start});
      cerere("/api/ci-alegeri?" + date.toString()).then(function(r){
        if(numar !== generatie || editoare[s.slot] !== draft || fel.value !== tip || cautare.value !== text){ return; }
        if(!r.result){ mesaj(r.message, true); return; }
        deLa = start; optiuni = r.alegeri; rezultate.textContent = "";
        optiuni.forEach(function(v, i){
          var nume = v.name + (tip === "furnizori" ? " [" + v.namespace.toString(16).toUpperCase().padStart(8, "0") + "]" : "");
          var o = el("option", nume); o.value = i; rezultate.appendChild(o);
        });
        rezultate.value = "0"; rezultate.dataset.fel = tip;
        rezultate.disabled = false;
        adaugaAles.disabled = !optiuni.length; inapoi.disabled = !start; inainte.disabled = !r.mai_sunt;
      }).catch(function(e){ if(numar === generatie && editoare[s.slot] === draft){ nimicNuRaspunde(e); } });
    }
    cauta.addEventListener("click", function(){ cautaLista(0); });
    cautare.addEventListener("keydown", function(e){ if(e.key === "Enter"){ e.preventDefault(); cautaLista(0); } });
    cautare.addEventListener("input", function(){ generatie++; adaugaAles.disabled = true; inapoi.disabled = true; inainte.disabled = true; });
    fel.addEventListener("change", function(){ cautaLista(0); });
    inapoi.addEventListener("click", function(){ cautaLista(Math.max(0, deLa - 100)); });
    inainte.addEventListener("click", function(){ cautaLista(deLa + 100); });
    adaugaAles.addEventListener("click", function(){ var r = optiuni[Number(rezultate.value)]; if(r){ adauga(rezultate.dataset.fel, r); } });
    [cauta, rezultate, inapoi, inainte, adaugaAles].forEach(function(n){ formular.appendChild(n); });
    var cunoscute = el("select"), manual = el("input"), adaugaCaid = el("button", "Adaugă CAID");
    var scris = el("option", "Scrie CAID (hexazecimal)"); scris.value = ""; cunoscute.appendChild(scris);
    d.cunoscute.forEach(function(c){
      var hex = c.caid.toString(16).toUpperCase().padStart(4, "0"), o = el("option", hex + (c.name ? " - " + c.name : ""));
      o.value = hex; cunoscute.appendChild(o);
    });
    manual.type = "text"; manual.maxLength = 6; manual.placeholder = "0B00"; adaugaCaid.type = "button";
    formular.appendChild(eticheta("CAID cunoscute din canalele scanate și modul", cunoscute));
    formular.appendChild(eticheta("CAID hexazecimal", manual)); formular.appendChild(adaugaCaid);
    adaugaCaid.addEventListener("click", function(){
      var text = (cunoscute.value || manual.value).trim();
      if(!/^(?:0x)?[0-9a-f]{1,4}$/i.test(text) || parseInt(text, 16) === 0){
        mesaj("CAID nevalid. Folosește 1-4 cifre hexazecimale, de exemplu 0B00.", true); return;
      }
      adauga("caid", parseInt(text, 16)); manual.value = "";
    });
    var salveaza = el("button", "Salvează și aplică"), reincearca = el("button", "Reîncearcă aplicarea"), inchide = el("button", "Închide");
    salveaza.type = "submit"; reincearca.type = "button"; inchide.type = "button";
    formular.appendChild(salveaza); formular.appendChild(reincearca); formular.appendChild(inchide);
    formular.appendChild(el("p", "Închide renunță numai la modificările nesalvate. Salvarea trimisă nu se anulează."));
    function stareSalvare(){
      reincearca.hidden = !draft.neaplicata;
      salveaza.disabled = draft.neaplicata && draft.rev === draft.salvata;
      if(draft.neaplicata && !stareEditor.textContent){ stareEditor.textContent = "Salvat, neaplicat. Verifică modulul și alege Reîncearcă aplicarea. Închide păstrează salvarea."; }
    }
    function inchideEditor(){
      if(editoare[s.slot] !== draft){ return; }
      generatie++; delete editoare[s.slot]; card.removeChild(formular); buton.disabled = false;
    }
    inchide.addEventListener("click", inchideEditor);
    function executa(aplicaDoar){
      if(ocupat || (!aplicaDoar && salveaza.disabled)){ return; } ocupat = true; var rev = draft.rev;
      inchide.disabled = true; reincearca.disabled = true; salveaza.disabled = true;
      var date = new URLSearchParams({slot:s.slot, actiune:aplicaDoar ? "alocare-aplica" : "alocare-salveaza", revizie:draft.revizie});
      if(!aplicaDoar){ date.set("reguli", JSON.stringify(reguli)); }
      cerere("/api/ci-comanda", "POST", date).then(function(r){
        if(editoare[s.slot] !== draft){ return; }
        mesaj(r.message, !r.result); stareEditor.textContent = r.message;
        if(r.salvat){
          draft.revizie = r.revizie; draft.neaplicata = !r.aplicat;
          if(!aplicaDoar){ draft.salvata = rev; }
        }
        if(r.result && draft.rev === draft.salvata){ inchideEditor(); return citeste(); }
      }).catch(nimicNuRaspunde).then(function(){
        ocupat = false; inchide.disabled = false; reincearca.disabled = false; stareSalvare();
      });
    }
    formular.addEventListener("submit", function(e){ e.preventDefault(); executa(false); });
    reincearca.addEventListener("click", function(){ executa(true); });
    randuri(); stareSalvare(); card.appendChild(formular); cautaLista(0);
  }).catch(function(e){ delete editoare[s.slot]; nimicNuRaspunde(e); }).then(function(){ ocupat = false; });
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
    var formular = el("form"), initiale = {};
    Object.keys(s.setari).forEach(function(nume){
      var setare = s.setari[nume], label = el("label"), select = el("select");
      initiale[nume] = setare.valoare;
      label.appendChild(el("span", setare.text)); select.name = nume;
      setare.alegeri.forEach(function(a){
        var opt = el("option", a[1]); opt.value = a[0]; select.appendChild(opt);
      });
      select.value = setare.valoare; label.appendChild(select); formular.appendChild(label);
      select.addEventListener("change", function(){ modificate[s.slot] = (modificate[s.slot] || 0) + 1; });
    });
    var salveaza = el("button", "Salvează"); salveaza.type = "submit";
    formular.appendChild(salveaza);
    formular.addEventListener("submit", function(e){ e.preventDefault(); trimite(s.slot, "salveaza", formular, initiale); });
    card.appendChild(formular);
    if(s.alocare){
      var aloca = el("button", "Alocă canale modulului"); aloca.type = "button";
      aloca.addEventListener("click", function(){ deschideAlocare(s, card, aloca); }); card.appendChild(aloca);
    }
    loc.appendChild(card);
  });
}
function citeste(){
  return cerere("/api/ci").then(function(d){
    if(d.result){
      // Un raspuns deja in zbor nu trebuie sa stearga editarile nesalvate.
      if(Object.keys(modificate).length || Object.keys(editoare).length){ return; }
      if(prima){ mesaj(""); prima = false; }
      arata(d);
    } else { mesaj(d.message, true); }
  });
}
// Citirea urmatoare incepe dupa raspuns; nu inlocuieste un formular editat.
function bucla(){
  var editeaza = document.activeElement && /^(SELECT|OPTION|INPUT|TEXTAREA)$/.test(document.activeElement.tagName);
  var pas = document.hidden || ocupat || Object.keys(modificate).length || Object.keys(editoare).length || editeaza
    ? Promise.resolve() : citeste().catch(nimicNuRaspunde);
  pas.then(function(){ setTimeout(bucla, 5000); });
}
bucla();
</script>
</body></html>
"""

TEXTE_PAGINA = {
	"html": (N_("Common Interface"), N_("Se citesc sloturile CI...")),
	"js": (N_("Reset"), N_("Init"), N_("Salvează"), N_("Alocă canale modulului"),
		N_("Șterge"), N_("Canal"), N_("Furnizor"), N_("Nu sunt alocări. Se păstrează alegerea automată a modulului."),
		N_("Canale"), N_("Furnizori"), N_("Adaugă din lista receptorului"), N_("Caută după nume"), N_("Caută"),
		N_("Adaugă selecția"), N_("Înapoi"), N_("Mai multe"), N_("Canale sau furnizori"),
		N_("Adaugă CAID"), N_("Scrie CAID (hexazecimal)"), N_("CAID cunoscute din canalele scanate și modul"),
		N_("CAID hexazecimal"), N_("CAID nevalid. Folosește 1-4 cifre hexazecimale, de exemplu 0B00."),
		N_("Decodările multiple se schimbă în setările slotului."), N_("Reîncearcă aplicarea"),
		N_("Salvat, neaplicat. Verifică modulul și alege Reîncearcă aplicarea. Închide păstrează salvarea."),
		N_("Închide renunță numai la modificările nesalvate. Salvarea trimisă nu se anulează."),
		N_("Salvează și aplică"), N_("Închide")),
}
