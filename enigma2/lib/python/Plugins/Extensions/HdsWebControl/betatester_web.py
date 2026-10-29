# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# betatester_web.py: „Beta tester” in interfata web (HdsWebControl).
#
# Orice setare de pe receptor are pereche in interfata web.
# Pe televizor: Meniu > Setari > Beta tester (Screens/HdsBetaTester.py). Aici: acelasi acord (felurile bifate din
# fabrica, fiecare cu randul lui, numele si e-mailul optionale, bifa notei nebifata, „Sunt de acord” numai cu ea),
# acelasi meniu al testerului (vizibil numai dupa inscriere): mesajul, „Ce am trimis”, raspunsurile echipei, datele
# trimise, „Ce trimit acum”, aparitia publica si legarea unui cont, nota, iesirea cu stergerea. Aceeasi logica:
# Components/HdsBetaTester.py.
#
# Rute (poarta comuna a HdsJsonResource; ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF):
#   GET  /api/beta-tester                   starea, textele, bifele, „Ce am trimis”, „Ce trimit acum”, raspunsurile
#   POST /api/beta-tester-fa?fa=<ce>        acord, bife, mesaj, profil, leaga, cod-legare, profil-stare, dezleaga,
#                                           raspunsuri, iesire (iesirea in doi pasi: pas=intreaba, apoi cod=)
#   GET  /api/beta-tester-lucrare?n=<nr>    rezultatul unei cereri spre server pornite de fa (profil, raspunsuri)
#   GET  /beta-tester                       pagina
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2; cererile spre server ruleaza pe firul lor
# (HdsBetaTester.Cerere), iar pagina intreaba de rezultat. Fisierul nu importa nimic din enigma2 la incarcare: probele
# de pe PC dau modulul lor (B) si setarile lor.

import itertools

CAMPURI = ("fa", "nume", "email", "nota", "fel", "text", "ecran", "jurnal", "captura", "nume_public", "cod", "pas",
	"n", "automat") + ("jurnale", "canale", "sistem", "utilizare", "receptor", "probe")
_LUCRARI = {}
_NUMAR = itertools.count(1)
MAX_LUCRARI = 16


def _t(text):
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _b(B=None):
	if B is not None:
		return B
	from Components import HdsBetaTester
	return HdsBetaTester


def _modulExista(nume):
	"""Pagina altui modul al imaginii (ajutorul de la distanta, probele) se arata numai daca modulul exista."""
	try:
		import importlib.util
		return importlib.util.find_spec(nume) is not None
	except Exception:
		return False


def _mc():
	from . import meniu_comun_web
	return meniu_comun_web


def stare(B=None, b=None):
	"""Pentru GET /api/beta-tester."""
	B = _b(B)
	b = b if b is not None else B.initConfig()
	inscris = B.inscris(b)
	rez = {
		"result": True,
		"inscris": inscris,
		"nota_veche": B.notaVeche(b),
		"feluri": [{"fel": f, "eticheta": B.eticheta(f), "rand": B.randScurt(f),
			"bifat": bool(getattr(b, f).value) if (inscris or B.notaVeche(b)) else True} for f in B.FELURI],
		"antet": _t(B.ANTET_ACORD),
		"bifa_nota": _t(B.BIFA_NOTA),
		"nota_scurta": _t(B.NOTA_SCURTA),
		"adresa_nota": B.ADRESA_NOTA,
		"nume": b.nume.value if inscris else "",
		"email": b.email.value if inscris else "",
		"automat": bool(b.automat.value) if (inscris or B.notaVeche(b)) else True,
		"automat_eticheta": _t(B.AUTOMAT[0]),
		"automat_rand": _t(B.AUTOMAT[1]),
		"numar": B.randNumar(),
	}
	B.ceNumar()
	if inscris:
		rez.update({
			"id": b.id.value,
			"acord": B.oraLocala(b.acord.value),
			"nota": int(b.nota.value),
			"trimise": [list(r) for r in B.randuriTrimise()],
			"ultimul": B.ultimulPachet(),
			"raspunsuri": B.textRaspunsuri(),
			"raspunsuri_noi": B.raspunsuriNoi(),
			"public": b.public.value,
			"feluri_mesaj": [[f, _t(B.FELURI_MESAJ_TEXT[f])] for f in B.FELURI_MESAJ],
			"ecran": B.ultimulEcranTitlu(),
			"text_id": textIdentificator(B, b),
			"ultima": B.randUltimaTrimitere(),
			"pagini": [[cale, _t(nume)] for cale, nume, modul in PAGINI_ALTE if _paginaArata(cale, modul)],
			"canal_testeri": canalTesteri(B),
			"legare_forum": B.legareForum(),
		})
	return rez


# paginile altor module, aratate in meniul testerului numai daca modulul exista (probele receptorului si
# asistenta de la distanta; asistenta numai cu SystemInfo["HdsAsistenta"] adevarat, ca pe televizor)
PAGINI_ALTE = (
	("/probe", "Probele receptorului", "Screens.HdsProbe"),
	("/asistenta", "Cere ajutor de la distanță", "Screens.HdsAsistenta"),
)


def _paginaArata(cale, modul):
	if not _modulExista(modul):
		return False
	if cale == "/asistenta":
		try:
			from Components.SystemInfo import SystemInfo
			return bool(SystemInfo.get("HdsAsistenta"))
		except Exception:
			return False
	return True


def canalTesteri(B):
	"""Bifa canalului testerilor (Primeste intai versiunile pentru testeri) pentru pagina, sau None fara ea. Se schimba
	prin POST /api/actualizari-testeri (pornit=1|0), ruta modulului canalului testerilor."""
	A = B.modulCanalTesteri()
	if A is None:
		return None
	return {"eticheta": _t(A.TEXT_BIFA_TESTERI), "nota": _t(getattr(A, "TEXT_NOTA_TESTERI", "")) if getattr(A,
		"TEXT_NOTA_TESTERI", "") else "", "pornit": B.canalTesteriPornit(A)}


def textIdentificator(B, b):
	"""Acelasi text ca jos in meniul testerului de pe televizor."""
	return _t("Identificatorul tău: %s\nAcordul din %s, nota de confidențialitate versiunea %d.\n"
		"Pentru ștergerea datelor fără receptor, scrie la contact@hdsatelit.com cu identificatorul.") % (b.id.value,
		B.oraLocala(b.acord.value), int(b.nota.value))


def _bife(arg, B):
	return dict((f, arg.get(f) == "1") for f in B.FELURI)


def _lucrare(cerere, ruta):
	if cerere is None:
		return {"result": False, "message": _t("Nu ești înscris în programul de beta testeri.")}
	while len(_LUCRARI) >= MAX_LUCRARI:
		_LUCRARI.pop(min(_LUCRARI))
	n = next(_NUMAR)
	_LUCRARI[n] = (ruta, cerere)
	return {"result": True, "lucrare": n, "message": _t("Se trimite...")}


def fa(arg, B=None, b=None, mc=None, captura=None):
	"""POST /api/beta-tester-fa."""
	B = _b(B)
	b = b if b is not None else B.initConfig()
	ce = arg.get("fa", "")
	if ce == "acord":
		if arg.get("nota") != "1":
			return {"result": False, "message": _t("Bifează întâi „%s”") % _t(B.BIFA_NOTA)}
		bife = _bife(arg, B)
		if not any(bife.values()):
			return {"result": False, "message": _t("Bifează cel puțin un fel de date sau alege Renunț.")}
		ok, mesaj = B.acceptaAcord(bife, arg.get("nume", ""), arg.get("email", ""), b, de_unde="setari",
			automat=arg.get("automat", "1") == "1")
		return {"result": ok, "message": mesaj}
	if not B.inscris(b) and ce != "iesire":
		return {"result": False, "message": _t("Nu ești înscris în programul de beta testeri.")}
	if ce == "bife":
		ok, mesaj = B.schimbaBife(_bife(arg, B), arg.get("nume", ""), arg.get("email", ""), b,
			automat=arg.get("automat") == "1" if "automat" in arg else None)
		return {"result": ok, "message": mesaj}
	if ce == "trimite-acum":
		ok, mesaj = B.trimiteAcum()
		return {"result": ok, "message": mesaj}
	if ce == "mesaj":
		poza = None
		if arg.get("captura") == "1":
			poza = (captura or B.capturaOsd)()
		ok, mesaj = B.mesaj(arg.get("fel", ""), arg.get("text", ""), arg.get("ecran", ""), arg.get("jurnal") == "1",
			poza, b)
		if ok and arg.get("captura") == "1" and poza is None:
			mesaj += " " + _t("Captura nu s-a putut face; mesajul pleacă fără ea.")
		return {"result": ok, "message": mesaj}
	if ce in ("leaga", "cod-legare") and not B.legareForum():
		return {"result": False, "message": _t("Legarea cu un cont de pe forum nu e încă gata.")}
	if ce == "profil":
		nume = B.textNume(arg.get("nume_public", ""), B.NUME_PUBLIC_MAX)
		email = B.textNume(arg.get("email", ""), B.EMAIL_MAX) if B.legareForum() else ""
		if nume and not B.numePublicValid(nume):
			return {"result": False, "message": _t("Numele public are 2-40 de semne: litere, cifre, spațiu, punct, "
				"liniuță.")}
		if not B.emailValid(email):
			return {"result": False, "message": _t("Adresa de e-mail nu pare bună.")}
		campuri = {"nume_public": nume or None}
		if B.legareForum():
			campuri["email"] = email or None
		return _lucrare(B.cerereProfil("profil", b, **campuri), "profil")
	if ce == "leaga":
		cod = arg.get("cod", "").strip()
		if not B._COD6.match(cod):
			return {"result": False, "message": _t("Codul are 6 cifre. Îl vezi pe site, pe pagina de legare, când ești "
				"conectat.")}
		return _lucrare(B.cerereProfil("leaga", b, cod=cod), "leaga")
	if ce in ("cod-legare", "profil-stare", "dezleaga"):
		return _lucrare(B.cerereProfil(ce, b), ce)
	if ce == "raspunsuri":
		c = B.Cerere(B.adresaServer(b), "raspunsuri", {"v": B.PROTOCOL, "id": b.id.value})
		c.start()
		return _lucrare(c, "raspunsuri")
	if ce == "iesire":
		mc = mc or _mc()
		if not B.inscris(b) and not B.notaVeche(b):
			return {"result": False, "message": _t("Nu ești înscris în programul de beta testeri.")}
		if arg.get("pas") == "renunta":
			mc.uita("beta-iesire")
			return {"result": True, "message": _t("Nu s-a făcut nimic.")}
		if arg.get("pas") == "intreaba":
			return mc.raspunsIntrebare("beta-iesire", "", _t("Ieși din programul de beta testeri? Serverul șterge toate "
				"datele trimise de acest receptor, iar pe receptor nu mai rămâne nimic."), _t("Da, ieși și șterge"))
		if not mc.verifica("beta-iesire", "", arg.get("cod", "")):
			return mc.codGresit()
		ok, mesaj = B.iesire(b)
		return {"result": ok, "message": mesaj}
	return {"result": False, "message": _t("Cerere necunoscută.")}


def lucrare(arg, B=None, b=None):
	"""GET /api/beta-tester-lucrare?n=: {gata, result, message, profil, adresa, cod}."""
	B = _b(B)
	b = b if b is not None else B.initConfig()
	try:
		n = int(arg.get("n", "0"))
	except ValueError:
		n = 0
	x = _LUCRARI.get(n)
	if x is None:
		return {"result": False, "gata": True, "message": _t("Cererea nu mai există. Încearcă din nou.")}
	ruta, c = x
	if not c.gata:
		return {"result": True, "gata": False}
	_LUCRARI.pop(n, None)
	ok, mesaj = B.mesajRaspunsProfil(c)
	rez = {"result": ok, "gata": True, "message": mesaj}
	if not ok:
		return rez
	if ruta == "raspunsuri":
		B.tineRaspunsuri(c.raspuns)
		B.marcheazaVazute()
		rez["raspunsuri"] = B.textRaspunsuri()
		rez["message"] = ""
		return rez
	if ruta == "cod-legare":
		adresa = str(c.raspuns.get("adresa") or "")[:200]
		rez["adresa"] = adresa if adresa.startswith("https://") else ""
		rez["message"] = _t("Deschide legătura pe aparatul pe care ești conectat pe forum și apasă „Leagă și arată-mă "
			"ca tester”. E valabilă 10 minute.")
		return rez
	profil = c.raspuns.get("profil")
	b.public.value = (profil or {}).get("nume_public") or ""
	B.salveaza(b)
	rez["profil"] = B.textProfil(profil)
	rez["message"] = rez["profil"]
	return rez


def rute(baza, resource, B=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py."""

	class StareResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(B))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class FaResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				arg = _mc().argumente(request, CAMPURI, lung=4100)
				if arg.get("fa") == "iesire":
					refuz = _mc().numaiBrowser(request)
					if refuz:
						return self._raspunde(request, {"result": False, "message": refuz})
				return self._raspunde(request, fa(arg, B))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class LucrareResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, lucrare(_mc().argumente(request, ("n",), 12), B))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class PaginaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			return _mc().pagina(request, pagina_text)

	api = {
		b"beta-tester": StareResource(),
		b"beta-tester-fa": FaResource(),
		b"beta-tester-lucrare": LucrareResource(),
	}
	return api, PaginaResource()


def pagina_text(stil, config_pagina):
	return _mc().sablon(_traducePagina(PAGINA), stil, config_pagina, {"__DRUM_MENIU__": _mc().drumHtml(
		"hds_beta_tester")})


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Beta tester</title>
<style>__STIL_COMUN__
__STIL_PAGINI__
  .fel{display:grid;grid-template-columns:30px 1fr;gap:8px;align-items:start;padding:8px 0;border-bottom:1px solid var(--bordura);}
  .fel:last-child{border-bottom:0;}
  .fel b{display:block;font-weight:600;}
  textarea{width:100%;min-height:120px;}
  input[type=text],input[type=email]{width:100%;}
</style>
</head>
<body>
<main>
<h1>Beta tester</h1>
<p class="mesaj" id="incarcare">Se citește starea...</p>
<div id="acord" class="ascuns">
  <section class="card">
    <p class="intrebare" id="antet"></p>
    <p class="intrebare ascuns" id="numarAcord"></p>
    <div id="feluri"></div>
    <div class="fel"><input type="checkbox" id="automat" checked><label for="automat"><b id="automatEticheta"></b><span class="nota" id="automatRand"></span></label></div>
  </section>
  <section class="card">
    <div class="rand"><label for="nume">Numele (opțional)</label><input type="text" id="nume" maxlength="60"></div>
    <div class="rand"><label for="email">E-mailul (opțional)</label><input type="email" id="email" maxlength="120"></div>
  </section>
  <section class="card">
    <div class="fel"><input type="checkbox" id="nota"><label for="nota" id="bifaNota"></label></div>
    <p class="nota"><a id="legaturaNota" href="#" target="_blank" rel="noopener">Nota de confidențialitate</a></p>
    <div class="butoane"><button type="button" class="principal" id="deAcord">Sunt de acord</button><button type="button" id="renunt">Renunț</button></div>
  </section>
</div>
<div id="meniu" class="ascuns">
  <section class="card">
    <p class="intrebare ascuns" id="numarMeniu"></p>
    <p class="nota" id="ultima"></p>
    <div class="butoane"><button type="button" class="principal" id="trimiteAcum">Trimite acum</button></div>
    <p class="nota" id="alte"></p>
    <div class="fel ascuns" id="canalTesteri"><input type="checkbox" id="canalTesteriBifa"><label for="canalTesteriBifa"><b id="canalTesteriEticheta"></b><span class="nota" id="canalTesteriNota"></span></label></div>
  </section>
  <section class="card">
    <h2>Trimite un mesaj</h2>
    <div class="rand"><label for="felMesaj">Felul</label><select id="felMesaj"></select></div>
    <textarea id="textMesaj" maxlength="4000" aria-label="Mesajul"></textarea>
    <div class="rand"><label for="ecranMesaj">Ecranul sau funcția (opțional)</label><input type="text" id="ecranMesaj" maxlength="120"></div>
    <div class="fel"><input type="checkbox" id="jurnalMesaj"><label for="jurnalMesaj">Atașează jurnalul ultimei erori</label></div>
    <div class="fel"><input type="checkbox" id="capturaMesaj"><label for="capturaMesaj">Atașează o captură a ecranului (numai meniurile): se face acum, cu ce arată televizorul</label></div>
    <div class="butoane"><button type="button" class="principal" id="trimiteMesaj">Trimite</button></div>
  </section>
  <section class="card">
    <h2 id="titluRaspunsuri">Răspunsurile echipei</h2>
    <pre class="text" id="raspunsuri"></pre>
    <div class="butoane"><button type="button" id="cereRaspunsuri">Caută răspunsuri noi</button></div>
  </section>
  <section class="card">
    <h2>Ce am trimis</h2>
    <table><thead><tr><th>Data</th><th>Felul</th><th>Mărimea</th><th>Starea</th></tr></thead><tbody id="trimise"></tbody></table>
  </section>
  <section class="card">
    <h2>Datele pe care le trimit</h2>
    <div id="feluriMeniu"></div>
    <div class="fel"><input type="checkbox" id="automatMeniu"><label for="automatMeniu"><b id="automatEticheta2"></b><span class="nota" id="automatRand2"></span></label></div>
    <div class="rand"><label for="numeMeniu">Numele (opțional)</label><input type="text" id="numeMeniu" maxlength="60"></div>
    <div class="rand"><label for="emailMeniu">E-mailul (opțional)</label><input type="email" id="emailMeniu" maxlength="120"></div>
    <div class="butoane"><button type="button" class="principal" id="salveazaBife">Salvează</button></div>
  </section>
  <section class="card">
    <h2>Ce trimit acum</h2>
    <pre class="text" id="ultimul"></pre>
  </section>
  <section class="card">
    <h2>Apariția publică</h2>
    <p class="nota">Opțional: apari cu un nume ales de tine pe pagina testerilor de pe site și la modelul tău. Fără parole pe receptor.</p>
    <p class="nota forum ascuns">E-mailul (opțional) îți face un cont pe forum: primești o legătură și îți pui parola acolo, de pe orice aparat.</p>
    <p class="intrebare" id="profil"></p>
    <div class="rand"><label for="numePublic">Numele public</label><input type="text" id="numePublic" maxlength="40"></div>
    <div class="rand forum ascuns"><label for="emailCont">E-mailul pentru cont (opțional)</label><input type="email" id="emailCont" maxlength="120"></div>
    <div class="butoane"><button type="button" class="principal" id="salveazaProfil">Salvează</button><button type="button" id="nuPublic">Nu mai apar public</button></div>
    <div class="rand forum ascuns"><label for="cod6">Codul de 6 cifre de pe site</label><input type="text" id="cod6" maxlength="6" inputmode="numeric"></div>
    <div class="butoane forum ascuns"><button type="button" id="leaga">Leagă cu codul</button><button type="button" id="codLegare">Leagă de pe acest aparat</button></div>
    <p class="nota forum ascuns" id="legatura"></p>
  </section>
  <section class="card">
    <h2>Nota de confidențialitate</h2>
    <p class="nota" id="notaScurta"></p>
    <p class="nota"><a id="legaturaNota2" href="#" target="_blank" rel="noopener">Nota întreagă</a></p>
  </section>
  <section class="card">
    <h2>Ieși din program și șterge datele</h2>
    <p class="nota" id="identificator" style="white-space:pre-line"></p>
    <div class="butoane"><button type="button" class="rosu" id="iesire">Ieși și șterge datele</button></div>
  </section>
  <div id="confirmare" class="card ascuns"></div>
</div>
<p class="mesaj" id="mesaj"></p>
<p class="nota">Același program e pe televizor, în __DRUM_MENIU__.</p>
</main>
<script>
__SCRIPT_COMUN__
var STARE = null;
function feluri(cutie, lista){
  cutie.textContent = "";
  lista.forEach(function(f){
    var d = document.createElement("div"); d.className = "fel";
    var c = document.createElement("input"); c.type = "checkbox"; c.id = cutie.id + "-" + f.fel; c.checked = !!f.bifat; c.setAttribute("data-fel", f.fel);
    var l = document.createElement("label"); l.htmlFor = c.id;
    var b = document.createElement("b"); b.textContent = f.eticheta; l.appendChild(b);
    var s = document.createElement("span"); s.className = "nota"; s.textContent = f.rand; l.appendChild(s);
    d.appendChild(c); d.appendChild(l); cutie.appendChild(d);
  });
}
function bifeDin(cutie, q){
  cutie.querySelectorAll("input[data-fel]").forEach(function(c){ q.set(c.getAttribute("data-fel"), c.checked ? "1" : "0"); });
}
function arata(d){
  STARE = d;
  $("incarcare").classList.add("ascuns");
  $("acord").classList.toggle("ascuns", d.inscris);
  $("meniu").classList.toggle("ascuns", !d.inscris);
  $("legaturaNota").href = d.adresa_nota; $("legaturaNota2").href = d.adresa_nota;
  ["numarAcord", "numarMeniu"].forEach(function(id){ $(id).textContent = d.numar || ""; $(id).classList.toggle("ascuns", !d.numar); });
  $("automatEticheta").textContent = d.automat_eticheta; $("automatRand").textContent = d.automat_rand;
  $("automatEticheta2").textContent = d.automat_eticheta; $("automatRand2").textContent = d.automat_rand;
  if(!d.inscris){
    $("antet").textContent = d.antet;
    $("bifaNota").textContent = d.bifa_nota;
    if(!$("feluri").childElementCount){ feluri($("feluri"), d.feluri); }
    return;
  }
  if(!$("feluriMeniu").childElementCount){
    feluri($("feluriMeniu"), d.feluri);
    $("numeMeniu").value = d.nume || ""; $("emailMeniu").value = d.email || "";
    $("automatMeniu").checked = !!d.automat;
    $("numePublic").value = d.public || "";
    var s = $("felMesaj"); s.textContent = "";
    (d.feluri_mesaj || []).forEach(function(f){ var o = document.createElement("option"); o.value = f[0]; o.textContent = f[1]; s.appendChild(o); });
    if(d.ecran){ $("ecranMesaj").value = d.ecran; }
  }
  $("notaScurta").textContent = d.nota_scurta;
  $("ultima").textContent = d.ultima || "";
  document.querySelectorAll(".forum").forEach(function(e){ e.classList.toggle("ascuns", !d.legare_forum); });
  var alte = $("alte"); alte.textContent = "";
  (d.pagini || []).forEach(function(p){ var a = document.createElement("a"); a.href = p[0]; a.textContent = p[1]; alte.appendChild(a); alte.appendChild(document.createTextNode("  ")); });
  var ct = d.canal_testeri;
  $("canalTesteri").classList.toggle("ascuns", !ct);
  if(ct){ $("canalTesteriBifa").checked = !!ct.pornit; $("canalTesteriEticheta").textContent = ct.eticheta; $("canalTesteriNota").textContent = ct.nota || ""; }
  $("raspunsuri").textContent = d.raspunsuri || "";
  $("titluRaspunsuri").textContent = "Răspunsurile echipei" + (d.raspunsuri_noi ? " (" + d.raspunsuri_noi + ")" : "");
  var t = $("trimise"); t.textContent = "";
  (d.trimise || []).forEach(function(r){
    var tr = document.createElement("tr");
    r.forEach(function(x){ var td = document.createElement("td"); td.textContent = x; tr.appendChild(td); });
    t.appendChild(tr);
  });
  $("ultimul").textContent = d.ultimul || "Încă nu a plecat niciun pachet.";
  $("identificator").textContent = d.text_id || "";
}
function citeste(){
  return cerere("/api/beta-tester").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi starea."; return; }
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
function canalTesteri(){
  var q = new URLSearchParams(); q.set("pornit", $("canalTesteriBifa").checked ? "1" : "0");
  mesaj("Se trimite...");
  cerere("/api/actualizari-testeri", "POST", q).then(function(d){ mesaj(d.message, !d.result); citeste(); }).catch(nimicNuRaspunde);
}
function fa(q, dupa){
  mesaj("Se trimite...");
  return cerere("/api/beta-tester-fa", "POST", q).then(function(d){
    if(d.lucrare){ asteapta(d.lucrare, dupa); return; }
    mesaj(d.message, !d.result); citeste();
  }).catch(nimicNuRaspunde);
}
function asteapta(n, dupa, pas){
  pas = pas || 0;
  setTimeout(function(){
    cerere("/api/beta-tester-lucrare?n=" + n).then(function(d){
      if(!d.gata && pas < 60){ asteapta(n, dupa, pas + 1); return; }
      mesaj(d.message, !d.result);
      if(d.profil){ $("profil").textContent = d.profil; }
      if(dupa){ dupa(d); }
      citeste();
    }).catch(nimicNuRaspunde);
  }, 500);
}
$("deAcord").addEventListener("click", function(){
  var q = new URLSearchParams(); q.set("fa", "acord"); bifeDin($("feluri"), q);
  q.set("nume", $("nume").value); q.set("email", $("email").value); q.set("nota", $("nota").checked ? "1" : "0");
  q.set("automat", $("automat").checked ? "1" : "0");
  fa(q);
});
$("renunt").addEventListener("click", function(){ mesaj("Nu s-a trimis nimic."); });
$("salveazaBife").addEventListener("click", function(){
  var q = new URLSearchParams(); q.set("fa", "bife"); bifeDin($("feluriMeniu"), q);
  q.set("nume", $("numeMeniu").value); q.set("email", $("emailMeniu").value);
  q.set("automat", $("automatMeniu").checked ? "1" : "0"); fa(q);
});
$("trimiteMesaj").addEventListener("click", function(){
  var q = new URLSearchParams(); q.set("fa", "mesaj"); q.set("fel", $("felMesaj").value); q.set("text", $("textMesaj").value);
  q.set("ecran", $("ecranMesaj").value); q.set("jurnal", $("jurnalMesaj").checked ? "1" : "0"); q.set("captura", $("capturaMesaj").checked ? "1" : "0");
  fa(q).then(function(){ $("textMesaj").value = ""; });
});
$("trimiteAcum").addEventListener("click", function(){ var q = new URLSearchParams(); q.set("fa", "trimite-acum"); fa(q); });
$("canalTesteriBifa").addEventListener("change", canalTesteri);
$("cereRaspunsuri").addEventListener("click", function(){ var q = new URLSearchParams(); q.set("fa", "raspunsuri"); fa(q); });
$("salveazaProfil").addEventListener("click", function(){
  var q = new URLSearchParams(); q.set("fa", "profil"); q.set("nume_public", $("numePublic").value); q.set("email", $("emailCont").value); fa(q);
});
$("nuPublic").addEventListener("click", function(){ var q = new URLSearchParams(); q.set("fa", "dezleaga"); fa(q); });
$("leaga").addEventListener("click", function(){ var q = new URLSearchParams(); q.set("fa", "leaga"); q.set("cod", $("cod6").value); fa(q); });
$("codLegare").addEventListener("click", function(){
  var q = new URLSearchParams(); q.set("fa", "cod-legare");
  fa(q, function(d){
    var p = $("legatura"); p.textContent = "";
    if(d.adresa){ var a = document.createElement("a"); a.href = d.adresa; a.target = "_blank"; a.rel = "noopener"; a.textContent = d.adresa; p.appendChild(a); }
  });
});
$("iesire").addEventListener("click", function(){ var q = new URLSearchParams(); q.set("fa", "iesire"); cuConfirmare("/api/beta-tester-fa", q, function(){ citeste(); }); });
citeste();
setInterval(function(){ if(STARE && STARE.inscris){ citeste(); } }, 30000);
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
		N_("Beta tester"),
		N_("Se citește starea..."),
		N_("Numele (opțional)"),
		N_("E-mailul (opțional)"),
		N_("Nota de confidențialitate"),
		N_("Sunt de acord"),
		N_("Renunț"),
		N_("Trimite acum"),
		N_("Trimite un mesaj"),
		N_("Felul"),
		N_("Mesajul"),
		N_("Ecranul sau funcția (opțional)"),
		N_("Atașează jurnalul ultimei erori"),
		N_("Atașează o captură a ecranului (numai meniurile): se face acum, cu ce arată televizorul"),
		N_("Trimite"),
		N_("Răspunsurile echipei"),
		N_("Caută răspunsuri noi"),
		N_("Ce am trimis"),
		N_("Data"),
		N_("Mărimea"),
		N_("Starea"),
		N_("Datele pe care le trimit"),
		N_("Salvează"),
		N_("Ce trimit acum"),
		N_("Apariția publică"),
		N_("Opțional: apari cu un nume ales de tine pe pagina testerilor de pe site și la modelul tău. Fără parole pe "
			"receptor."),
		N_("E-mailul (opțional) îți face un cont pe forum: primești o legătură și îți pui parola acolo, de pe orice "
			"aparat."),
		N_("Numele public"),
		N_("E-mailul pentru cont (opțional)"),
		N_("Nu mai apar public"),
		N_("Codul de 6 cifre de pe site"),
		N_("Leagă cu codul"),
		N_("Leagă de pe acest aparat"),
		N_("Nota întreagă"),
		N_("Ieși din program și șterge datele"),
		N_("Ieși și șterge datele"),
		N_("Același program e pe televizor, în __DRUM_MENIU__."),
	),
	"js": (
		N_("Răspunsurile echipei"),
		N_("Încă nu a plecat niciun pachet."),
		N_("Receptorul nu a putut citi starea."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Se trimite..."),
		N_("Nu s-a trimis nimic."),
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
