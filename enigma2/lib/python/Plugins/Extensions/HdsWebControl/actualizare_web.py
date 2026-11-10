# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# actualizare_web.py: imagine de pe stick, cu acelasi flux de verificare si scriere ca pe TV.
#
# Pe televizor: ecranul de actualizare (Screens/HdsSoftwareUpdate.py) arata pachetele gasite pe stick sau pe disc, cu
# verdictul pazei de model pentru fiecare (pentru acest receptor, sau de ce nu se scrie). Aici: aceeasi lista, din
# aceeasi logica (HdsSoftwareUpdate.cautaCandidati: marcajul fiecarui pachet fata de amprenta receptorului, citita o
# data), cu textul intreg al fiecarui refuz. Adaptorul refoloseste metodele ecranului, iar intrebarile si rezultatul
# apar in pagina. Nu trimite taste catre TV si nu deschide ferestre in sesiunea lui.
#
# Rute prin poarta comuna HdsJsonResource; actiunile cer POST si CSRF:
#   GET /api/actualizare-pachete   pachetele gasite acum si verdictul pazei pentru fiecare
#   GET /api/actualizare-stare     lucrarea si intrebarea curenta
#   POST /api/actualizare-verifica id=<pachet din lista>, fara cale primita din browser
#   POST /api/actualizare-instaleaza   cere ultima confirmare, fara scriere
#   POST /api/actualizare-raspunde intrebare=<id unic>&da=0|1
#   POST /api/actualizare-opreste  renunta dupa verificare, inainte de scriere
#   GET /actualizare               pagina (aceeasi poarta ca /paznic: reteaua locala, apoi browserul asociat)
#
# FIRUL: lista mediilor montate se ia pe firul enigma2 (harddiskmanager nu e de atins din alt fir); citirea dosarelor si
# a zipurilor si amprenta ruleaza pe un fir separat (Components/HdsPazaModel.LucrareFundal, rezultatul cules cu un
# eTimer), iar raspunsul pleaca dupa (NOT_DONE_YET). Fisierul nu importa nimic din enigma2 la incarcare: probele de pe
# PC dau modulele lor (U = ecranul de actualizare, H = paza de model).

import json
import re
import secrets

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


def pachete(U, H, discuri, candidati=None):
	"""Pachetele de pe `discuri`, fiecare ca dict pentru pagina (ruleaza pe firul separat: numai fisiere)."""
	rez = []
	for c in U.cautaCandidati(discuri) if candidati is None else candidati:
		cod, text = c.get("paza") or (H.REFUZ_NECITIT, "")
		# numele stickului (Tools/MediuImagine.pregatesteNumeStick): refuz numai daca montarea nu s-a putut muta, ca in
		# lista de pe televizor
		stick = getattr(U, "scurtNumeStick", lambda m: None)(c.get("nume_stick"))
		# stickul pus pe numai citire, fara alt disc pentru dezarhivare (U.marcheazaMediu); verificarea e in pagina Discurile
		fara_loc = bool(c.get("numai_citire")) and not c.get("loc_lucru") and c.get("fel") != "rea"
		rez.append({
			"nume": U.numeImagineStraina(c) if c.get("fel") == "straina" else U._numePachet(c),
			"fel": c.get("fel") or "",
			"stare": U.textFel(c["fel"]) if c.get("fel") else "",
			"versiune": c.get("versiune") or "",
			"mediu": "  ·  ".join(x for x in (c["disc"].description or c["disc"].mountpoint, c.get("usb")) if x),
			"tip": c["tip"],
			"cod": cod,
			"bun": cod == H.PACHET_BUN and not stick and not fara_loc,
			"verdict": stick or (_t("Pe stick se poate numai citi") if fara_loc else "") or (
				_t("Nu este imagine HD Satelit și nu o putem verifica") if c.get("fel") == "straina" else H.scurtRefuz(cod)),
			"text": (_t("Pune stickul în calculator, schimbă-i numele într-unul fără spații și fără semne (de exemplu "
				"HDSATELIT), apoi introdu-l din nou în receptor.") if stick else "") or (U.textStickCazut(c, cu_ok=False) if fara_loc else "") or text or "",
			"repara": _t("Repară") if fara_loc and c.get("disc_reparat") else "",
		})
	return rez


class _Afisare:
	"""Destinatia textelor ecranului cand lucrarea este ceruta din browser."""
	def __init__(self):
		self.text = ""

	def setText(self, text):
		self.text = text

	def setList(self, lista):
		pass

	def moveToIndex(self, index):
		pass

	def show(self):
		pass

	def hide(self):
		pass


def controler(U, sesiune):
	"""Adaptor de afisare, fara Screen sau ferestre TV. Pregatirea, sumele, simularea,
	copia si scrierea sunt chiar metodele HdsSoftwareUpdate, mostenite fara rescriere."""
	class Actualizare(U.HdsSoftwareUpdate):
		def __init__(self):
			self._afisare = {n: _Afisare() for n in ("detaliu", "lista", "iesire", "key_green", "key_yellow")}
			self._console = U.Console()
			self._candidati, self._reparari = [], []
			self._candidatAles = self._lucrare = self._semnVerificat = None
			self._faza, self._ultimaIesire = "lista", ""
			self._ocupat = self._opreste = self._arataCorect = self._scriereRealaPornita = False
			self._analizaVazuta = False
			self._renuntat = False
			self.intrebare = None
			self.refuz = ""
			self["iesire"].setText("")
			self._raspuns = None
			self._ident = ""
			self.session = self
			self.nav = sesiune.nav

		def __getitem__(self, nume):
			return self._afisare[nume]

		def hide(self):
			pass

		def show(self):
			pass

		def _randPachet(self, candidat):
			return candidat

		def _randuriLista(self):
			return self._candidati

		def _reparareSelectata(self):
			return None

		def _candidatSelectat(self):
			return self._candidatAles

		def _repara(self, disc):
			self["detaliu"].setText(_t("Verifică și repară stickul din pagina Discurile, apoi caută din nou software-ul."))

		def _reincarca(self):
			if not self._ocupat:
				U.elibereazaActualizarea(self)
				self._faza = "lista"

		def _intreaba(self, callback, text, titlu, da, implicit_da, randuri):
			self.intrebare = {"id": secrets.token_hex(24), "text": text, "titlu": titlu, "da": da}
			self._raspuns = callback

		def open(self, clasa, text, *args, **kwargs):
			self.refuz = text

		def openWithCallback(self, callback, clasa, text, *args, **kwargs):
			# Si exceptia copiei esuate ramane o alegere explicita, cu Nu implicit.
			self._intreaba(callback, text, _t("Instalarea este oprită"), _t("Da, continuă"), False, (0, 0))

		def _arataRefuzPaza(self, text):
			self.refuz = text

		def stare(self):
			return {"result": True, "id": self._ident, "faza": self._faza,
				"ocupat": self._ocupat, "scriere": self._scriereRealaPornita,
				"poate_instala": self._faza == "rezultat" and self._arataCorect and not self._scriereRealaPornita,
				"poate_renunta": not self._scriereRealaPornita and self._faza not in ("verificare", "anulare") and
					(self._ocupat or self._faza == "rezultat" or self.intrebare is not None),
				"mesaj": self["detaliu"].text, "analiza": self["iesire"].text,
				"refuz": self.refuz, "intrebare": self.intrebare}

		def verifica(self, ident, candidat):
			if self._ocupat or self._scriereRealaPornita or self.intrebare or self._faza != "lista":
				return False
			self.refuz = ""
			self["iesire"].setText("")
			self._opreste = self._renuntat = False
			self._ident, self._candidatAles = ident, candidat
			self._candidati = [candidat]
			self._ok()
			return self._ocupat or self._faza == "rezultat" or self.intrebare is not None

		def instaleaza(self, ident):
			if ident != self._ident or not self.stare()["poate_instala"] or self.intrebare:
				return False
			self._ok()
			return self.intrebare is not None

		def raspunde(self, ident, da):
			if not self.intrebare or ident != self.intrebare["id"] or da not in ("0", "1"):
				return False
			callback, self._raspuns = self._raspuns, None
			self.intrebare = None  # un raspuns repetat sau vechi nu mai poate porni nimic
			callback(da == "1")
			return True

		def opreste(self):
			# Copierea si sumele se pot anula, ca pe TV; ofgwrite -n este lasat sa termine.
			if self._scriereRealaPornita or self._faza == "anulare" or (self._ocupat and self._faza == "verificare"):
				return False
			self.intrebare, self._raspuns = None, None
			self._renuntat = True
			if self._ocupat:
				self._faza = "anulare"
			self._laInchidere()
			self._arataCorect = False
			self["detaliu"].setText(_t("Ai renunțat. Nu s-a instalat nimic pe receptor."))
			return True

		def _actualizareEliberata(self):
			if self._renuntat:
				self._faza, self._ocupat = "lista", False

	return Actualizare()


def argumente(request):
	rez = {}
	for cheie, valori in (getattr(request, "args", None) or {}).items():
		try:
			cheie = cheie.decode("ascii") if isinstance(cheie, bytes) else cheie
			valoare = valori[0].decode("utf-8") if isinstance(valori[0], bytes) else valori[0]
		except (UnicodeError, IndexError, TypeError, AttributeError):
			continue
		if cheie in ("id", "intrebare", "da") and isinstance(valoare, str) and len(valoare) <= 128:
			rez[cheie] = valoare
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


def rute(baza, resource, NOT_DONE_YET, U=None, H=None, sesiune=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py."""

	_lucrari = []   # lucrarile in curs; fara referinta pastrata, eTimer-ul lor e cules si raspunsul nu mai pleaca
	_inventar = {}
	_controler = []

	def lucrare():
		if not _controler:
			if sesiune is None:
				from . import plugin as P
				s = P._sesiune
			else:
				s = sesiune() if callable(sesiune) else sesiune
			if s is None:
				raise ValueError(_t("Sesiunea receptorului nu este disponibilă. Încearcă din nou."))
			_controler.append(controler(_u(U), s))
		return _controler[0]

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

			def gata(rezultat, eroare):
				for lucrare in pastrata:
					if lucrare in _lucrari:
						_lucrari.remove(lucrare)
				try:
					if eroare:
						corp = resursa._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)
					else:
						lista, candidati = rezultat
						_inventar.clear()
						for rand, candidat in zip(lista, candidati):
							ident = secrets.token_hex(24)
							rand["id"] = ident
							_inventar[ident] = candidat
						corp = resursa._raspunde(request, raspuns(lista, h))
					request.write(corp)
					request.finish()
				except Exception as problema:
					print("[HdsWebControl] actualizare: raspunsul nu a plecat (browser plecat?): %s" % problema)

			def citeste():
				candidati = u.cautaCandidati(discuri)
				return pachete(u, h, discuri, candidati), candidati

			fir = h.LucrareFundal(citeste, gata)
			pastrata.append(fir)
			_lucrari.append(fir)
			return NOT_DONE_YET

	class StareResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, lucrare().stare())
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class ActiuneResource(baza):
		schimbaCeva = True
		actiune = ""

		def render_POST(self, request):
			try:
				c, arg = lucrare(), argumente(request)
				if self.actiune == "verifica":
					candidat = _inventar.get(arg.get("id"))
					if candidat is None:
						return self._eroare(request, _t("Pachetul nu mai este în lista citită. Caută din nou software-ul."), 409)
					bun = c.verifica(arg.get("id"), candidat)
				elif self.actiune == "instaleaza":
					bun = c.instaleaza(arg.get("id"))
				elif self.actiune == "raspunde":
					bun = c.raspunde(arg.get("intrebare"), arg.get("da"))
				else:
					bun = c.opreste()
				rez = c.stare()
				rez["result"] = bool(bun)
				if not bun:
					rez["message"] = rez["mesaj"] or _t("Comanda nu mai este disponibilă. Verifică starea din pagină.")
				return self._raspunde(request, rez)
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class PaginaResource(resource.Resource):
		"""GET /actualizare: pagina „Imagine nouă de pe stick” (actualizarile prin pachete sunt la /actualizari)."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {b"actualizare-pachete": PacheteResource(), b"actualizare-stare": StareResource()}
	for nume in ("verifica", "instaleaza", "raspunde", "opreste"):
		r = ActiuneResource()
		r.actiune = nume
		api[("actualizare-" + nume).encode("ascii")] = r
	return api, PaginaResource()


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
		"citeste": _t("Se caută software de receptor pe stick și pe disc..."),
		"niciunul": _t("Nu am găsit software de receptor pe stick sau pe disc."),
		"nuRaspunde": _t("Receptorul nu răspunde. Verifică dacă este pornit și în aceeași rețea."),
		"eroare": _t("Receptorul nu a putut citi software-ul de pe stick."),
		"gasite": _t("Variante de software găsite: %d."),
		"pentru": _t("Software-ul de acum este pentru %s."),
		"verifica": _t("Verifică software-ul"),
		"instaleaza": _t("Instalează pe receptor"),
		"opreste": _t("Renunță"),
		"nu": _t("Nu"),
		"analiza": _t("Vezi ce a analizat ofgwrite"),
	}


def pagina_text(stil, config_pagina, limba="ro"):
	valori = {
		"__STIL_COMUN__": stil,
		"__LIMBA__": _e(limba or "ro"),
		"__CONFIG__": config_pagina,
		"__TEXTE__": json.dumps(texte(), ensure_ascii=False).replace("</", "<\\/"),
		"__T_TITLU__": _e(_t("Imagine nouă de pe stick")),
		"__T_CAUTA__": _e(_t("Caută din nou software de receptor")),
		"__T_NOTA__": _e(_t("Verifică software-ul pornește direct verificarea, fără să instaleze imaginea pe receptor. După verificare, Instalează pe receptor arată efectul și cere acordul tău înainte de scriere. Pe televizor, aceeași funcție este la:")),
		"__DRUM_MENIU__": _drumMeniu("hds_software_update"),
		"__T_PAZA__": _e(_t("Software-ul HD Satelit se instalează numai dacă este făcut pentru acest receptor și fișierele lui sunt întregi. Se păstrează verificarea locului de instalare, simularea și copia de siguranță. O imagine care nu este HD Satelit cere mai întâi un acord după avertisment, pentru că nu o putem verifica.")),
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
  .card.bun{border-color:#3b82f6;}
  .card.noua{border-color:#4fd18b;}
  .card.rau{border-color:#ff6b5e;}
  .cap{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin:0 0 6px;}
  .semn{width:16px;height:16px;flex:none;background:#ff6b5e;}
  .card.bun .semn,.card.bun .eticheta{background:#3b82f6;}
  .card.straina{border-color:#f5b83d;}
  .card.straina .semn,.card.straina .eticheta{background:#f5b83d;color:#10162a;}
  .card.noua .semn,.card.noua .eticheta{background:#4fd18b;color:#10162a;}
  .eticheta{margin-left:auto;padding:4px 10px;background:#ff6b5e;color:#fff;font-weight:bold;font-size:.85rem;text-transform:uppercase;}
  .verdict{margin:0 0 4px;font-size:.9rem;}
  .card.bun .verdict{color:#a8e6b4;}
  .card.rau .verdict{color:#ffb4a8;}
  .nume{margin:0;font-weight:bold;flex:1 1 200px;overflow-wrap:anywhere;}
  .detalii{color:var(--text-slab);font-size:.86rem;margin:4px 0 0;overflow-wrap:anywhere;}
  .motiv{color:var(--text-slab);font-size:.86rem;line-height:1.45;margin:8px 0 0;white-space:pre-line;overflow-wrap:anywhere;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 10px;line-height:1.45;}
  .bara{display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between;margin:0 0 10px;}
  .bara button{min-height:40px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;cursor:pointer;}
  .mesaj{margin:6px 0 10px;line-height:1.45;}
  button{min-height:40px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura);background:var(--panou);color:var(--text);font:inherit;cursor:pointer;}
  button:disabled{opacity:.55;cursor:default;}
  #lucrare,#intrebare{white-space:pre-line;overflow-wrap:anywhere;}
  #intrebare{border:2px solid #f5b83d;}
  details{margin:10px 0;white-space:pre-line;}
</style>
</head>
<body>
<main>
<h1>__T_TITLU__</h1>
<p class="nota">__T_NOTA__ __DRUM_MENIU__.</p>
<p class="nota">__T_PAZA__</p>
<div class="bara"><p class="mesaj" id="mesaj"></p><button id="cauta" type="button">__T_CAUTA__</button></div>
<section id="lucrare" class="card" hidden aria-live="polite"></section>
<section id="intrebare" class="card" hidden role="alertdialog" aria-modal="false"></section>
<div id="comenzi" class="bara"></div>
<div id="lista"></div>
</main>
<script>
var CFG = __CONFIG__;
var T = __TEXTE__;
var STARE = {}, trimite = false, initializat = false, ultimaStare = "", generatie = 0, numarCitire = 0, ultimaCitire = 0;
function $(id){ return document.getElementById(id); }
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
function cerere(cale, date){
  var optiuni = {method: date ? "POST" : "GET", cache: "no-store", credentials: "same-origin", headers: {}};
  if(CFG.csrf){ optiuni.headers["X-HDS-CSRF"] = CFG.csrf; }
  if(date){ optiuni.headers["Content-Type"] = "application/x-www-form-urlencoded;charset=UTF-8";
    optiuni.body = Object.keys(date).map(function(k){ return encodeURIComponent(k)+"="+encodeURIComponent(date[k]); }).join("&"); }
  return fetch(adresa(cale), optiuni).then(function(r){
    if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("browser deconectat"); }
    return r.json();
  });
}
function element(tip, clasa, text){
  var e = document.createElement(tip); if(clasa){ e.className = clasa; } if(text){ e.textContent = text; } return e;
}
function buton(parinte, text, functie){
  var b = element("button", "", text); b.type = "button"; b.disabled = trimite;
  b.addEventListener("click", functie); parinte.appendChild(b); return b;
}
function comanda(actiune, date){
  if(trimite){ return; } generatie++; trimite = true; blocheaza();
  cerere("/api/actualizare-" + actiune, date || {}).then(function(d){
    if(d.faza){ arataStare(d); }
    if(!d.result){ $("mesaj").textContent = d.message || T.eroare; }
  }).catch(function(){ $("mesaj").textContent = T.nuRaspunde; })
    .then(function(){ trimite = false; blocheaza(); });
}
function blocheaza(){
  var ocupat = trimite || STARE.ocupat || STARE.scriere || !!STARE.intrebare || STARE.faza === "rezultat";
  $("cauta").disabled = !!ocupat;
  document.querySelectorAll("button.verifica").forEach(function(b){ b.disabled = !!ocupat; });
  $("comenzi").querySelectorAll("button").forEach(function(b){ b.disabled = trimite; });
  $("intrebare").querySelectorAll("button").forEach(function(b){ b.disabled = trimite; });
}
function arataStare(d){
  var semn = JSON.stringify([d.id,d.faza,d.ocupat,d.scriere,d.poate_instala,d.poate_renunta,d.mesaj,d.analiza,d.refuz,d.intrebare]);
  if(semn === ultimaStare){ STARE = d; blocheaza(); return; } ultimaStare = semn;
  var veche = STARE.intrebare && STARE.intrebare.id; STARE = d;
  var l = $("lucrare"); l.textContent = ""; l.hidden = !d.mesaj && !d.refuz;
  l.appendChild(element("p", "", d.mesaj));
  if(d.refuz){ l.appendChild(element("p", "", d.refuz)); }
  if(d.analiza){ var a = element("details"); a.appendChild(element("summary", "", T.analiza));
    a.appendChild(element("p", "", d.analiza)); l.appendChild(a); }
  var c = $("comenzi"); c.textContent = "";
  if(d.poate_instala && !d.intrebare){ buton(c, T.instaleaza, function(){ comanda("instaleaza", {id:d.id}); }); }
  if(d.poate_renunta){
    buton(c, T.opreste, function(){ comanda("opreste", {}); });
  }
  var q = $("intrebare"), intrebare = d.intrebare;
  if(!intrebare){ q.hidden = true; q.textContent = ""; }
  else if(veche !== intrebare.id){
    q.textContent = ""; q.hidden = false;
    q.appendChild(element("h2", "", intrebare.titlu)); q.appendChild(element("p", "", intrebare.text));
    var nu = buton(q, T.nu, function(){ comanda("raspunde", {intrebare:intrebare.id, da:"0"}); });
    buton(q, intrebare.da, function(){ comanda("raspunde", {intrebare:intrebare.id, da:"1"}); });
    nu.focus();
  }
  blocheaza();
}
function arata(d){
  var l = $("lista"); l.textContent = "";
  var p = d.pachete || [];
  var sus = p.length ? T.gasite.replace("%d", p.length) : T.niciunul;
  if(d.model){ sus += " " + T.pentru.replace("%s", d.model + (d.versiune ? " (HD Satelit " + d.versiune + ")" : "")); }
  $("mesaj").textContent = sus;
  p.forEach(function(x){
    var c = element("section", "card " + (x.bun ? "bun" : "rau") + (x.fel === "noua" || x.fel === "straina" ? " " + x.fel : ""));
    var cap = element("div", "cap");
    cap.appendChild(element("span", "semn"));
    cap.appendChild(element("p", "nume", x.nume));
    if(x.stare){ cap.appendChild(element("span", "eticheta", x.stare)); }
    c.appendChild(cap);
    c.appendChild(element("p", "verdict", x.verdict.charAt(0).toUpperCase() + x.verdict.slice(1)));
    c.appendChild(element("p", "detalii", [x.versiune && x.nume.indexOf(x.versiune) === -1 ? x.versiune : "", x.mediu].filter(Boolean).join("  ·  ")));
    if(x.text){ c.appendChild(element("p", "motiv", x.text)); }
    if(x.repara){
      var rp = document.createElement("a"); rp.href = adresa("/discuri?f=verificare"); rp.textContent = x.repara; rp.style.color = "inherit";
      c.appendChild(rp);
    }
    if(x.id && (x.bun || x.fel === "straina")){
      var v = buton(c, T.verifica, function(){ comanda("verifica", {id:x.id}); }); v.className = "verifica";
    }
    l.appendChild(c);
  });
  blocheaza();
}
function citeste(){
  var curenta = generatie;
  $("mesaj").textContent = T.citeste; $("cauta").disabled = true;
  cerere("/api/actualizare-pachete").then(function(d){
    if(trimite || curenta !== generatie){ return; }
    if(!d.result){ $("mesaj").textContent = d.message || T.eroare; return; }
    arata(d);
  }).catch(function(){ if(curenta === generatie && !trimite){ $("mesaj").textContent = T.nuRaspunde; } })
    .then(blocheaza);
}
function citesteStare(){
  if(trimite){ return; }
  var curenta = generatie, citire = ++numarCitire;
  cerere("/api/actualizare-stare").then(function(d){
    if(trimite || curenta !== generatie || citire < ultimaCitire){ return; }
    ultimaCitire = citire;
    if(!d.result){ $("mesaj").textContent = d.message || T.eroare; return; }
    arataStare(d);
    if(!initializat){ initializat = true; citeste(); }
  }).catch(function(){ if(!trimite && curenta === generatie && citire >= ultimaCitire){ ultimaCitire = citire; $("mesaj").textContent = T.nuRaspunde; } });
}
$("cauta").addEventListener("click", citeste);
citesteStare();
setInterval(citesteStare, 1500);
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
