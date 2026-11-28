# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Mirror the active ConfigListScreen; persistence belongs to its own actions."""

import hashlib
import hmac
import json
import os
import re
import weakref

from .meniu_comun_web import _t, N_

MAX_RANDURI = 300
MAX_TEXT = 4096


def _secret(el, text):
	from Components.HdsAsistentaControl import campSecret
	# What the television shows, the web shows too: an address is plain text on both, written and read in clear.
	# Only real password and key fields are kept out of the page (after saving the row says "set"), like on the television.
	return campSecret(el, text)


def _fel(el, text):
	from Components import config as C
	# Unknown subclasses may implement pickers or actions instead of values.
	permise = ("ConfigBoolean", "ConfigYesNo", "ConfigOnOff", "ConfigEnableDisable", "ConfigSelection",
		"ConfigSelectionNumber", "ConfigSatlist", "ConfigInteger", "ConfigSlider", "ConfigNumber",
		"ConfigText", "ConfigSearchText", "ConfigPassword", "ConfigPIN", "ConfigSet")
	if type(el) not in tuple(getattr(C, n) for n in permise if hasattr(C, n)):
		return "citire"
	if _secret(el, text):
		return "secret" if isinstance(el, (C.ConfigText, C.ConfigPIN)) and not isinstance(el, C.ConfigNumber) else "citire"
	from . import setari_web as S
	return S._fel(el, plugin=True) or "citire"


def _descriereValoare(el, text):
	from . import setari_web as S
	fel = _fel(el, text)
	if _secret(el, text):
		# Never send the stored value, its length or a reusable digest.
		v = el.value
		v = "".join(str(x) for x in v) if isinstance(v, (tuple, list)) else str(v if v is not None else "")
		return {"fel": fel if fel == "secret" else "citire", "secret": True,
			"valoare_text": v, "max": MAX_TEXT}
	if fel == "text":
		limita = getattr(el, "web_text_max", MAX_TEXT) or MAX_TEXT
		return {"fel": fel, "valoare": str(el.value or ""), "max": min(int(limita), MAX_TEXT)}
	if fel == "citire":
		from Components.config import ConfigPassword
		if isinstance(el, ConfigPassword):
			return {"fel": fel, "valoare_text": str(el.value or "")}
		return {"fel": fel, "valoare_text": _t("Se folosește pe televizor.")}
	return S._descriere(el, fel, plugin=True)


def _descriere(el, text):
	d = _descriereValoare(el, text)
	d["blocat"] = not getattr(el, "enabled", True) or el.isReadOnly()
	return d


def _actiuni(dlg, cod):
	from Components.ActionMap import ActionMap
	from Tools.KeyBindings import queryKeyBinding
	rez = []
	for h in dlg.values():
		if not isinstance(h, ActionMap) or not h.enabled or not h.exec_active:
			continue
		for context in h.contexts:
			for nume, functie in h.actions.items():
				if nume in getattr(h, "disbledActions", ()) or not callable(functie):
					continue
				if any(k == cod and flags & 3 for k, flags in queryKeyBinding(context, nume)):
					rez.append((h.prio, h, context, nume, functie))
	return sorted(rez, key=lambda x: x[0])


def _etichetaTastei(dlg, nume, rezerva):
	label = dlg.get(nume)
	return str(label.getText() or rezerva) if label is not None and hasattr(label, "getText") else rezerva


class Oglinda:
	def __init__(self):
		self.dialog = None
		self.identitate = ""
		self.revizie = 0
		self.semn = None
		self.elemente = []
		self.sare = os.urandom(32)

	def _curent(self, sesiune):
		from Components.ConfigList import ConfigListScreen
		dlg = getattr(sesiune, "current_dialog", None)
		if (not isinstance(dlg, ConfigListScreen) or not getattr(sesiune, "in_exec", False)
			or not getattr(dlg, "execing", False)):
			return None
		return dlg if dlg.get("config") is not None else None

	def _randuri(self, dlg):
		lista = dlg["config"].list
		if not isinstance(lista, (list, tuple)) or len(lista) > MAX_RANDURI:
			raise ValueError("unsupported list")
		return lista

	def _id(self, el):
		for ref, nume in self.elemente:
			if ref() is el:
				return nume
		nume = os.urandom(8).hex()
		self.elemente.append((weakref.ref(el), nume))
		return nume

	def stare(self, sesiune):
		dlg = self._curent(sesiune)
		if dlg is None:
			self.dialog = None
			self.elemente = []
			self.semn = None
			return {"result": True, "activ": False, "message": _t("Deschide un ecran de setări pe televizor. Ecranele fără listă se folosesc pe televizor.")}
		if self.dialog is None or self.dialog() is not dlg:
			self.dialog = weakref.ref(dlg)
			self.identitate = os.urandom(12).hex()
			self.elemente = []
			self.semn = None
		randuri = []
		amprente = []
		lista = self._randuri(dlg)
		active = {id(r[1]) for r in lista if isinstance(r, (tuple, list)) and len(r) > 1}
		self.elemente = [(ref, nume) for ref, nume in self.elemente if ref() is not None and id(ref()) in active]
		for r in lista:
			if not isinstance(r, (tuple, list)) or not r:
				continue
			text = str(r[0])[:MAX_TEXT]
			if len(r) < 2:
				randuri.append({"text": text, "fel": "titlu"})
				continue
			el = r[1]
			from Components.config import ConfigElement
			if not isinstance(el, ConfigElement):
				continue
			d = _descriere(el, text)
			d.update(id=self._id(el), text=text)
			# Help strings can contain values. Export only the actual row label.
			randuri.append(d)
			if _secret(el, text):
				amprente.append(hmac.new(self.sare, repr(el.value).encode("utf-8", "replace"), hashlib.sha256).hexdigest())
		verde, rosu = _actiuni(dlg, 399), _actiuni(dlg, 398)
		d = {"result": True, "activ": True, "ecran": self.identitate, "titlu": str(dlg.getTitle()),
			"randuri": randuri, "verde": bool(verde), "rosu": bool(rosu),
			"verde_text": _etichetaTastei(dlg, "key_green", _t("Tasta verde a ecranului")),
			"rosu_text": _etichetaTastei(dlg, "key_red", _t("Tasta roșie a ecranului"))}
		semn = json.dumps([d, amprente, [(id(h), c, n, id(f)) for _p, h, c, n, f in verde + rosu]], sort_keys=True)
		if semn != self.semn:
			self.semn = semn
			self.revizie += 1
		d["revizie"] = str(self.revizie)
		return d

	def comanda(self, sesiune, arg):
		stare = self.stare(sesiune)
		if (not stare.get("activ") or arg.get("ecran") != stare["ecran"]
			or arg.get("revizie") != stare["revizie"]):
			return dict(stare, result=False, message=_t("Ecranul sau setările s-au schimbat. Verifică lista și încearcă din nou."))
		dlg = self.dialog()
		if self._curent(sesiune) is not dlg:
			return self._refuzaEcran(sesiune)
		fel = arg.get("actiune")
		if fel in ("verde", "rosu"):
			actiuni = _actiuni(dlg, 399 if fel == "verde" else 398)
			if not actiuni:
				return dict(stare, result=False, message=_t("Această tastă se folosește pe televizor."))
			# Consume the revision before invoking a handler (also on exceptions).
			self.semn = None
			for _p, _h, _c, _n, functie in actiuni:
				if self._curent(sesiune) is not dlg or functie() != 0:
					break
			return dict(self.stare(sesiune), message=_t("Tasta a fost trimisă ecranului. Dacă a cerut confirmare, răspunde pe televizor."))
		if fel != "schimba":
			return dict(stare, result=False, message=_t("Comandă necunoscută."))
		rand = next((r for r in self._randuri(dlg) if len(r) > 1 and self._id(r[1]) == arg.get("rand")), None)
		if rand is None:
			return dict(stare, result=False, message=_t("Rândul nu mai este în listă."))
		el, text = rand[1], str(rand[0])
		d = _descriere(el, text)
		if d["blocat"]:
			return dict(stare, result=False, message=_t("Această setare se schimbă de pe televizor."))
		valoare = arg.get("valoare", "")
		if len(valoare) > MAX_TEXT or any(ord(c) < 32 or 127 <= ord(c) < 160 for c in valoare):
			return dict(stare, result=False, message=_t("Valoarea nu este potrivită pentru acest rând."))
		from Components import config as C
		from . import setari_web as S
		if d["fel"] in ("text", "secret"):
			if d["fel"] == "secret" and not valoare:
				return stare
			if isinstance(el, C.ConfigPIN):
				v = int(valoare) if valoare.isascii() and valoare.isdigit() and len(valoare) == el.getLength() else None
			elif len(valoare) <= d["max"]:
				v = valoare
			else:
				v = None
		else:
			v = S._valoareNoua(el, d["fel"], valoare, plugin=True)
		if v is None:
			return dict(stare, result=False, message=_t("Valoarea nu este potrivită pentru acest rând."))
		lista = dlg["config"]
		anterior = hmac.new(self.sare, repr(el.value).encode("utf-8", "replace"), hashlib.sha256).digest()
		lista.setCurrentIndex(self._randuri(dlg).index(rand))
		# Selection callbacks may replace the list or open another dialog.
		if (self._curent(sesiune) is not dlg or not any(len(r) > 1 and r[1] is el for r in self._randuri(dlg))
			or _descriere(el, text) != d
			or anterior != hmac.new(self.sare, repr(el.value).encode("utf-8", "replace"), hashlib.sha256).digest()):
			return dict(self.stare(sesiune), result=False, message=_t("Rândul nu mai este în listă."))
		self.semn = None
		if el.value != v:
			el.value = v
			# ConfigText.setValue does not notify (the keyboard does it explicitly).
			if isinstance(el, C.ConfigText) and not isinstance(el, C.ConfigNumber):
				el.changed()
			# Notifiers can close the dialog and destroy its list widget.
			if self._curent(sesiune) is not dlg:
				return self._refuzaEcran(sesiune)
			lista.invalidate(rand)
			dlg.entryChanged()
		if self._curent(sesiune) is not dlg:
			return self._refuzaEcran(sesiune)
		return dict(self.stare(sesiune), message=_t("Valoarea este în ecran. Salvează cu tasta verde a ecranului."))

	def _refuzaEcran(self, sesiune):
		return dict(self.stare(sesiune), result=False,
			message=_t("Ecranul sau setările s-au schimbat. Verifică lista și încearcă din nou."))


OGLINDA = Oglinda()


def argumente(request):
	# Do not trim or truncate values: spaces can be significant, especially in keys.
	rez = {}
	for k in ("ecran", "revizie", "actiune", "rand", "valoare"):
		v = (request.args.get(k.encode("ascii")) or [b""])[0]
		rez[k] = v.decode("utf-8", "strict") if isinstance(v, bytes) else str(v)
	if any(len(v) > (MAX_TEXT if k == "valoare" else 64) for k, v in rez.items()):
		raise ValueError("oversized argument")
	return rez


def rute(baza):
	from .meniu_comun_web import sesiune

	class Stare(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, OGLINDA.stare(sesiune()))
			except Exception:
				return self._eroare(request, _t("Ecranul nu se poate oglindi. Folosește televizorul."))

	class Comanda(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, OGLINDA.comanda(sesiune(), argumente(request)))
			except Exception:
				# Plugin exceptions may contain secrets. Never echo or log their text.
				return self._eroare(request, _t("Ecranul nu a primit schimbarea. Verifică pe televizor și reîncarcă lista."))

	return {b"setari-deschise": Stare(), b"setari-deschise-comanda": Comanda()}


def pagina_text(stil, config_pagina):
	from . import meniu_comun_web as C
	return C.sablon(_traducePagina(PAGINA), stil, config_pagina)


PAGINA = r"""<!DOCTYPE html>
<html lang="ro"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Setările deschise pe televizor</title><style>__STIL_COMUN__
__STIL_PAGINI__
main{max-width:880px;margin:auto}.rand{overflow-wrap:anywhere}input,select{width:100%;min-width:0}button{min-height:44px}
@media(max-width:560px){main{padding-bottom:110px}}
</style></head><body><main>
<p><a href="/meniu">Meniu</a> · <a href="/extensii">Plugins</a> · <a href="/">Telecomandă</a></p>
<h1 id="titlu">Setările deschise pe televizor</h1>
<p class="nota">Aceeași listă ca pe televizor. Schimbările rămân în ecran până folosești tasta lui de salvare. Confirmările și alegătoarele se folosesc pe televizor.</p>
<p id="mesaj" role="status"></p><section id="randuri" class="card"></section>
<div class="butoane"><button type="button" id="verde" class="principal">Tasta verde a ecranului</button><button type="button" id="rosu" class="rosu">Tasta roșie a ecranului</button><button type="button" id="citeste">Reîncarcă lista</button></div>
</main><script>
__SCRIPT_COMUN__
var DATE=null, OCUPAT=false, CEAS=null, EDITAT=false, PLECAT=false, CITIRE=false, GENERATIE=0, URMATOARE=null, IN_CURS="";
function el(t,text){var e=document.createElement(t);if(text!==undefined){e.textContent=text;}return e;}
function nota(t){$("mesaj").textContent=t||"";}
function programeaza(){clearTimeout(CEAS);if(!PLECAT){CEAS=setTimeout(citeste,document.hidden?5000:1500);}}
function arata(d){
  DATE=d;var p=$("randuri");p.textContent="";
  $("titlu").textContent=d.titlu||"Setările deschise pe televizor";
  $("verde").disabled=!d.activ||!d.verde;$("rosu").disabled=!d.activ||!d.rosu;
  $("verde").textContent=d.verde_text||"Tasta verde a ecranului";$("rosu").textContent=d.rosu_text||"Tasta roșie a ecranului";
  if(!d.activ){nota(d.message);return;}
  d.randuri.forEach(function(r){
    if(r.fel==="titlu"){p.appendChild(el("h2",r.text));return;}
    var div=el("div"), l=el("label",r.text), c;div.className="rand";
    if(r.fel==="bool"||r.fel==="alegere"){
      c=el("select");(r.alegeri||[]).forEach(function(a){var o=el("option",a[1]);o.value=a[0];c.appendChild(o);});c.value=r.valoare;
    }else if(r.fel==="text"||r.fel==="secret"){
      c=el("input");c.type="text";c.value=r.fel==="secret"?"":r.valoare;c.maxLength=r.max;c.autocomplete="off";c.spellcheck=false;
      if(r.secret){c.dataset.hdsSecret="1";c.placeholder=r.valoare_text||"";}
    }else if(["numar","glisor","cifre"].indexOf(r.fel)!==-1){
      c=el("input");c.type="number";c.min=r.min;c.max=r.max;c.step=r.pas;c.value=r.valoare;
    }else if(r.fel==="multime"){
      c=el("select");c.multiple=true;(r.alegeri||[]).forEach(function(a){var o=el("option",a[1]);o.value=a[0];o.selected=r.valoare.indexOf(a[0])!==-1;c.appendChild(o);});
    }else{c=el("span",r.valoare_text||"");}
    if(c.tagName!=="SPAN"){
      c.disabled=!!r.blocat;
      c.id="r-"+r.id;l.htmlFor=c.id;
      c.addEventListener("input",function(){EDITAT=true;});
      c.addEventListener("change",function(){
        var v=c.multiple?Array.prototype.filter.call(c.options,function(o){return o.selected;}).map(function(o){return o.value;}).join(","):c.value;
        trimite("schimba",r.id,v,d.ecran);
      });
    }
    div.appendChild(l);div.appendChild(c);p.appendChild(div);
  });
}
function citeste(){
  clearTimeout(CEAS);if(OCUPAT||CITIRE||EDITAT||document.querySelector("#randuri :focus")){programeaza();return Promise.resolve();}
  CITIRE=true;var generatie=GENERATIE;return cerere("/api/setari-deschise").then(function(d){
    if(generatie!==GENERATIE||EDITAT||OCUPAT||PLECAT){return;}
    if(d.result){if(!DATE||DATE.ecran!==d.ecran||DATE.revizie!==d.revizie||DATE.activ!==d.activ){arata(d);}}else{nota(d.message);}
  }).catch(function(){if(generatie===GENERATIE){nota("Receptorul nu răspunde.");}}).then(function(){CITIRE=false;programeaza();});
}
function trimite(actiune,rand,valoare,ecranCerut){
  if(!DATE||!DATE.activ||PLECAT){return;}
  var ecran=ecranCerut||DATE.ecran;
  if(ecran!==DATE.ecran){return;}
  if(OCUPAT){if(IN_CURS==="schimba"&&actiune!=="schimba"){URMATOARE={actiune:actiune,ecran:ecran};}return;}
  OCUPAT=true;IN_CURS=actiune;var generatie=++GENERATIE;clearTimeout(CEAS);var q=new URLSearchParams();q.set("ecran",ecran);q.set("revizie",DATE.revizie);q.set("actiune",actiune);
  if(rand){q.set("rand",rand);q.set("valoare",valoare);}
  Array.prototype.forEach.call(document.querySelectorAll("#randuri input,#randuri select"),function(c){c.disabled=true;});
  var reusit=false;
  cerere("/api/setari-deschise-comanda","POST",q).then(function(d){
    if(PLECAT||generatie!==GENERATIE){return;}
    reusit=!!d.result;EDITAT=false;if(d.randuri||d.activ===false){arata(d);}nota(d.message);
    if(!d.result&&!d.randuri){DATE=null;}
  }).catch(function(){nota("Receptorul nu răspunde. Reîncarcă lista înainte să încerci din nou.");DATE=null;}).then(function(){
    OCUPAT=false;IN_CURS="";$("citeste").disabled=false;
    if(DATE){$("verde").disabled=!DATE.activ||!DATE.verde;$("rosu").disabled=!DATE.activ||!DATE.rosu;}
    else{$("verde").disabled=true;$("rosu").disabled=true;}
    var urmatoare=URMATOARE;URMATOARE=null;
    if(reusit&&urmatoare&&DATE&&DATE.activ&&DATE.ecran===ecran&&urmatoare.ecran===ecran){trimite(urmatoare.actiune,null,null,ecran);}else{programeaza();}
  });
}
$("verde").onclick=function(){trimite("verde");};$("rosu").onclick=function(){trimite("rosu");};
$("citeste").onclick=function(){if(!OCUPAT){EDITAT=false;DATE=null;document.activeElement.blur();citeste();}};
window.addEventListener("pagehide",function(){PLECAT=true;++GENERATIE;clearTimeout(CEAS);$("randuri").textContent="";DATE=null;URMATOARE=null;});
window.addEventListener("pageshow",function(){PLECAT=false;EDITAT=false;citeste();});
citeste();
</script></body></html>
"""

TEXTE_PAGINA = {
	"html": (
		N_("Setările deschise pe televizor"), N_("Meniu"), N_("Plugins"), N_("Telecomandă"),
		N_("Aceeași listă ca pe televizor. Schimbările rămân în ecran până folosești tasta lui de salvare. Confirmările și alegătoarele se folosesc pe televizor."),
		N_("Tasta verde a ecranului"), N_("Tasta roșie a ecranului"), N_("Reîncarcă lista"),
	),
	"js": (
		N_("Setările deschise pe televizor"), N_("Receptorul nu răspunde."),
		N_("Tasta verde a ecranului"), N_("Tasta roșie a ecranului"),
		N_("Receptorul nu răspunde. Reîncarcă lista înainte să încerci din nou."),
	),
}


def _traducePagina(sablon, fel="pagina"):
	from .traducere_pagini import traduce
	return traduce(sablon, TEXTE_PAGINA, fel)
