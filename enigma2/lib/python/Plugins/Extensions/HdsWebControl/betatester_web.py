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
#                                           raspunsuri, iesire (iesirea in doi pasi: pas=intreaba, apoi cod=),
#                                           accepta-nota (acordul pe nota noua cu alegerile de dinainte),
#                                           nota-mai-tarziu (banda notei noi revine maine)
# Cat nota acceptata e mai veche, cadru_web.py pune sus pe orice pagina banda anuntului (bandaNota); pe /beta-tester,
# in locul ei, caseta notei noi cu starea „Trimiterea e oprita pana accepti nota noua”.
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
		"randuri": dict((k, _t(v)) for k, v in (B.RANDURI_MENIU if inscris else B.RANDURI_VIZITATOR).items()),
	}
	B.ceNumar()
	if B.notaVeche(b):
		rez["nota_noua"] = textNotaNoua(B)
	if not inscris:
		rez.update({
			"intrebare": _t(B.INTREBARE),
			"invitatie": _t("Ca beta tester trimiți date anonime care ajută imaginea și poți scrie pe forumul "
				"receptorului."),
			"avantaje": [[glif, titlu, rand] for _cheie, glif, titlu, rand in B.avantaje(existaAvantaje(B))],
		})
	if inscris:
		noi = B.raspunsuriNoi()
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
			"automat_text": _t("(automat în fiecare zi)") if b.automat.value else "",
			"din": _t("Înscris din %s") % dataScurta(B.oraLocala(b.acord.value)),
			"nume_forum": numeForum(b),
			"insigna_raspunsuri": (_t("un răspuns nou") if noi == 1 else _t("%d răspunsuri noi") % noi) if noi else "",
			"insigna_forum": insignaForum(),
			"forum_verifica": verificaForum(),
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


def existaAvantaje(B):
	"""Avantajele legate de un modul, aratate numai daca modulul e pe receptor (ca pe receptor)."""
	return {
		"canal_testeri": B.modulCanalTesteri() is not None,
		"forum": _modulExista("Screens.HdsForumReceptor"),
		"asistenta": _paginaArata("/asistenta", "Screens.HdsAsistenta"),
	}


def dataScurta(text):
	""""AAAA-LL-ZZ HH:MM" -> "ZZ.LL.AAAA"; altfel textul ca atare."""
	import re
	m = re.match(r"\A(\d{4})-(\d{2})-(\d{2})", text or "")
	return "%s.%s.%s" % (m.group(3), m.group(2), m.group(1)) if m else (text or "")


def _forum():
	try:
		from Components import HdsForumReceptor
		return HdsForumReceptor
	except Exception:
		return None


def insignaForum():
	"""Mesajele noi de pe forum de la ultima vizita (HdsForumReceptor.mesajeNoiCunoscute), ca text; "" fara ele."""
	F = _forum()
	if F is None or not _modulExista("Screens.HdsForumReceptor"):
		return ""
	return F.textMesajeNoi(F.mesajeNoiCunoscute())


def verificaForum():
	"""O citire a forumului in fundal, cel mult una la cateva minute (pagina nu o asteapta); True cand a pornit una
	acum: pagina isi cere starea inca o data peste cateva secunde, ca sa arate numarul."""
	F = _forum()
	if F is None or not _modulExista("Screens.HdsForumReceptor"):
		return False
	return bool(F.verificaMesajeNoi())


def numeForum(b):
	"""Numele cu care apare omul pe forum (cel dat de forum sau cel public), "" cand nu se stie inca."""
	try:
		from Components import HdsForumReceptor
		nume = HdsForumReceptor.numePublic()
	except Exception:
		nume = ""
	return nume or b.public.value or ""


def canalTesteri(B):
	"""Bifa canalului testerilor (Primeste intai versiunile pentru testeri) pentru pagina, sau None fara ea. Se schimba
	prin POST /api/actualizari-testeri (pornit=1|0), ruta modulului canalului testerilor."""
	A = B.modulCanalTesteri()
	if A is None:
		return None
	return {"eticheta": _t(A.TEXT_BIFA_TESTERI), "nota": _t(getattr(A, "TEXT_NOTA_TESTERI", "")) if getattr(A,
		"TEXT_NOTA_TESTERI", "") else "", "pornit": B.canalTesteriPornit(A)}


def textNotaNoua(B):
	"""Textele anuntului notei noi (aceleasi ca pe receptor), pentru pagina /beta-tester si banda de pe orice pagina."""
	return {
		"titlu": _t(B.NOTA_ANUNT_TITLU),
		"anunt": _t(B.NOTA_ANUNT),
		"oprita": _t(B.NOTA_OPRITA),
		"ce_e_nou": _t("Ce e nou"),
		"noutati": B.noutatiNota(),
		"accept_rand": _t(B.NOTA_ACCEPT_RAND),
		"citeste": _t(B.NOTA_BUTOANE["citeste"][0]),
		"accept": _t(B.NOTA_BUTOANE["accept"][0]),
		"mai_tarziu": _t(B.NOTA_BUTOANE["mai_tarziu"][0]),
		"adresa": B.adresaNotei(),
	}


def bandaNota(B=None):
	"""Banda anuntului notei noi, pusa de cadru_web sus pe orice pagina (HTML gata, tradus), cat nota acceptata e mai
	veche si „Mai tarziu” din web nu s-a apasat azi; "" altfel. Accept si Mai tarziu merg prin /api/beta-tester-fa, cu
	jetonul sau antetul CSRF din antetul cadrului (#hdsAntet)."""
	import html as _html
	try:
		B = _b(B)
		if not B.anuntNotaDatorat(cheie="nota_web_zi"):
			return ""
		t = textNotaNoua(B)
	except Exception:
		return ""
	e = _html.escape
	noutati = "".join("<li>%s</li>" % e(x) for x in t["noutati"])
	# sablonul nu are text de tradus (locurile __NUME__ primesc textele deja traduse); trece totusi prin traducere,
	# ca orice sablon de pagina
	banda = _traducePagina(BANDA_NOTA)
	for loc, text in (("__TITLU__", e(t["titlu"])), ("__ANUNT__", e(t["anunt"])), ("__CE_E_NOU__", e(t["ce_e_nou"])),
			("__NOUTATI__", noutati), ("__ACCEPT_RAND__", e(t["accept_rand"])), ("__ADRESA__", e(t["adresa"])),
			("__CITESTE__", e(t["citeste"])), ("__ACCEPT__", e(t["accept"])), ("__MAI_TARZIU__", e(t["mai_tarziu"]))):
		banda = banda.replace(loc, text)
	return banda


BANDA_NOTA = """<section id="hdsNotaNoua" role="alert" style="margin:0 0 16px;padding:14px 18px;border-left:6px solid var(--atentie,#E8B93A);background:var(--panou,#1b2130);border-radius:8px;line-height:1.45;">
<b style="display:block;font-size:1.05rem;margin:0 0 4px;">__TITLU__</b>
<p style="margin:0 0 8px;">__ANUNT__</p>
<b style="display:block;color:var(--atentie,#E8B93A);margin:0 0 2px;">__CE_E_NOU__</b>
<ul style="margin:0 0 8px;padding-left:20px;">__NOUTATI__</ul>
<p style="margin:0 0 10px;font-size:.88rem;opacity:.85;">__ACCEPT_RAND__</p>
<div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;">
<a href="__ADRESA__" target="_blank" rel="noopener" style="display:inline-flex;align-items:center;min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura,#3a4255);color:inherit;text-decoration:none;">__CITESTE__</a>
<button type="button" data-fa="accepta-nota" style="min-height:44px;padding:8px 18px;border-radius:8px;border:1px solid var(--accent,#3D7BE0);background:var(--accent,#3D7BE0);color:#fff;font:inherit;cursor:pointer;">__ACCEPT__</button>
<button type="button" data-fa="nota-mai-tarziu" style="min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura,#3a4255);background:transparent;color:inherit;font:inherit;cursor:pointer;">__MAI_TARZIU__</button>
<span id="hdsNotaMesaj" role="status"></span>
</div>
<script>
(function(){
  var S = document.getElementById("hdsNotaNoua"), A = document.getElementById("hdsAntet"), M = document.getElementById("hdsNotaMesaj");
  if(!S){ return; }
  var J = A ? (A.getAttribute("data-jeton") || "") : "", K = A ? (A.getAttribute("data-csrf") || "") : "";
  S.querySelectorAll("button[data-fa]").forEach(function(b){
    b.addEventListener("click", function(){
      var q = new URLSearchParams(); q.set("fa", b.getAttribute("data-fa"));
      var h = {"Content-Type": "application/x-www-form-urlencoded"}; if(!J){ h["X-HDS-CSRF"] = K; }
      fetch("/api/beta-tester-fa" + (J ? "?token=" + encodeURIComponent(J) : ""), {method: "POST", cache: "no-store",
        credentials: "same-origin", headers: h, body: q.toString()}).then(function(r){ return r.json(); }).then(function(d){
        M.textContent = d.message || "";
        if(d.result){ setTimeout(function(){ S.remove(); if(window.HDS_NOTA_GATA){ window.HDS_NOTA_GATA(); } }, 2500); }
      }).catch(function(){});
    });
  });
})();
</script>
</section>"""


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
	if ce == "accepta-nota":
		# acordul pe nota noua cu alegerile de dinainte (le are receptorul; pagina nu trimite nimic personal)
		ok, mesaj = B.acceptaNotaNoua(b)
		return {"result": ok, "message": mesaj}
	if ce == "nota-mai-tarziu":
		if not B.notaVeche(b):
			return {"result": False, "message": _t("Nu ești înscris în programul de beta testeri.")}
		ok, mesaj = B.amanaAnuntNota(cheie="nota_web_zi")
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
	_uitaJetonulForumului()
	rez["profil"] = B.textProfil(profil)
	rez["message"] = rez["profil"]
	return rez


def _uitaJetonulForumului():
	"""Numele public s-a schimbat: jetonul forumului (cu numele vechi in el) se uita, ca forumul sa arate numele nou."""
	try:
		from Components import HdsForumReceptor
		HdsForumReceptor.uitaJetonul()
	except Exception:
		pass


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
  main.beta{max-width:1180px;}
  .cap{margin:0 0 18px;}
  .cap h1{font-size:1.9rem;font-weight:500;margin:0;}
  .cap p{margin:0;color:var(--text-slab);}
  .grila{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:18px;align-items:start;}
  .randuri{display:flex;flex-direction:column;gap:6px;}
  .rm{background:var(--rand,var(--panou));border:1px solid var(--bordura);border-radius:6px;}
  .rm>summary,a.rm{display:grid;grid-template-columns:40px minmax(0,1fr) auto 20px;gap:4px 14px;align-items:center;padding:12px 16px;min-height:44px;cursor:pointer;list-style:none;color:var(--text);text-decoration:none;}
  .rm>summary::-webkit-details-marker{display:none;}
  .rm[open]>summary,.rm>summary:hover,a.rm:hover,.rm>summary:focus-visible,a.rm:focus-visible{background:var(--ales,var(--panou));color:var(--ales-text,var(--text));box-shadow:inset 4px 0 0 var(--chihlimbar,var(--galben));outline:none;}
  .rm svg{width:28px;height:28px;}
  .rm .t{display:flex;flex-direction:column;gap:2px;min-width:0;}
  .rm .t b{font-weight:500;font-size:1.08rem;}
  .rm .t span{color:var(--text-slab);font-size:.86rem;line-height:1.35;}
  .rm .sageata{width:18px;height:18px;transition:transform .15s;}
  .rm[open] .sageata{transform:rotate(90deg);}
  .rm.rosu b,.rm.rosu svg{color:var(--rosu);}
  .rm.ascuns,a.rm.ascuns{display:none;}
  .insigna.ascuns{padding:0;background:none;}
  .rm-bifa{display:grid;grid-template-columns:40px minmax(0,1fr) auto;gap:4px 14px;align-items:center;padding:12px 16px;cursor:pointer;}
  .rm .corp{padding:4px 16px 16px 70px;}
  .insigna{display:inline-block;padding:3px 10px;border-radius:4px;background:var(--chihlimbar,var(--galben));color:#1d1700;font-size:.82rem;font-weight:700;white-space:nowrap;}
  .valoare{color:var(--chihlimbar,var(--galben));font-size:.92rem;white-space:nowrap;}
  .panou-t{background:var(--panou);border:1px solid var(--bordura);border-radius:8px;padding:18px;display:flex;flex-direction:column;gap:14px;}
  .panou-t .titlu{display:flex;gap:12px;align-items:center;}
  .panou-t .titlu svg{width:44px;height:44px;padding:8px;border-radius:6px;background:var(--rand,var(--fundal));color:var(--chihlimbar,var(--galben));}
  .panou-t .titlu b{display:block;font-size:1.3rem;font-weight:600;}
  .panou-t .titlu span{color:var(--text-slab);font-size:.88rem;}
  .camp{display:flex;flex-direction:column;gap:2px;border-top:1px solid var(--bordura);padding:12px 0 0;}
  .camp span{color:var(--text-slab);font-size:.85rem;}
  .camp b{font-size:1.1rem;font-weight:600;}
  .camp b.chihlimbar{color:var(--chihlimbar,var(--galben));}
  .banda{border-left:5px solid var(--chihlimbar,var(--galben));background:var(--rand,var(--panou));color:var(--chihlimbar,var(--galben));padding:12px 16px;border-radius:4px;margin:0;line-height:1.45;}
  button.mare{width:100%;min-height:52px;font-size:1.1rem;font-weight:600;}
  .invitatie h2{font-size:1.6rem;line-height:1.3;margin:0 0 6px;font-weight:600;}
  .invitatie>p{color:var(--text-slab);margin:0 0 14px;}
  .avantaje{display:flex;flex-direction:column;gap:8px;margin:0 0 12px;}
  .avantaj{display:grid;grid-template-columns:44px 1fr;gap:14px;align-items:start;background:var(--rand,var(--panou));border:1px solid var(--bordura);border-radius:6px;padding:12px 16px;}
  .avantaj svg{width:28px;height:28px;margin:6px;color:var(--chihlimbar,var(--galben));}
  .avantaj b{display:block;font-weight:600;}
  .avantaj span{color:var(--text-slab);font-size:.88rem;}
  .fel{display:grid;grid-template-columns:30px 1fr;gap:8px;align-items:start;padding:8px 0;border-bottom:1px solid var(--bordura);}
  .fel:last-child{border-bottom:0;}
  .fel b{display:block;font-weight:600;}
  textarea{width:100%;min-height:120px;}
  input[type=text],input[type=email]{width:100%;}
  a.buton{display:inline-flex;align-items:center;min-height:44px;padding:8px 18px;border-radius:8px;background:var(--accent);color:#fff;text-decoration:none;}
  .nota-bifa{border:2px solid var(--chihlimbar,var(--galben));border-radius:6px;padding:4px 12px;}
  @media (max-width:820px){ .grila{grid-template-columns:1fr;} .rm .corp{padding:4px 12px 14px 12px;} }
</style>
</head>
<body>
<main class="beta">
<header class="cap"><h1>Beta tester</h1></header>
<p class="mesaj" id="incarcare">Se citește starea...</p>
<div id="notaNoua" class="ascuns">
  <section class="card">
    <p class="banda" id="notaOprita"></p>
    <h2 id="notaTitlu" style="margin-top:14px"></h2>
    <p class="intrebare" id="notaAnunt"></p>
    <b id="notaCeNou"></b>
    <ul id="notaNoutati"></ul>
    <p class="nota" id="notaAcceptRand"></p>
    <div class="butoane"><a class="buton" id="notaCiteste" href="#" target="_blank" rel="noopener"></a><button type="button" class="principal" id="notaAccept"></button></div>
  </section>
  <section class="card"><div class="butoane"><button type="button" class="rosu" id="iesireVeche">Ieși din program și șterge datele</button></div></section>
</div>
<div id="acord" class="ascuns">
  <div class="grila">
    <div>
      <section class="invitatie">
        <h2 id="titluInvitatie"></h2>
        <p id="textInvitatie"></p>
        <div class="avantaje" id="listaAvantaje"></div>
        <p class="banda ascuns" id="numarAcord"></p>
      </section>
      <section class="card">
        <h2>Devino beta tester</h2>
        <p class="intrebare" id="antet"></p>
        <div id="feluri"></div>
        <div class="fel"><input type="checkbox" id="automat" checked><label for="automat"><b id="automatEticheta"></b><span class="nota" id="automatRand"></span></label></div>
      </section>
      <section class="card">
        <div class="rand"><label for="nume">Numele (opțional)</label><input type="text" id="nume" maxlength="60"></div>
        <div class="rand"><label for="email">E-mailul (opțional)</label><input type="email" id="email" maxlength="120"></div>
      </section>
      <section class="card">
        <div class="fel nota-bifa"><input type="checkbox" id="nota"><label for="nota" id="bifaNota"></label></div>
        <p class="nota"><a id="legaturaNota" href="#" target="_blank" rel="noopener">Nota de confidențialitate</a></p>
        <div class="butoane"><button type="button" class="principal" id="deAcord">Sunt de acord</button><button type="button" id="renunt">Renunț</button></div>
      </section>
    </div>
    <aside class="randuri">
      <a class="rm" href="/forum-receptor"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 5h16v11H9l-5 4z"/></svg><div class="t"><b>Forumul receptorului</b><span data-rand="forum"></span></div><span></span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="sageata"><path d="m9 6 6 6-6 6"/></svg></a>
    </aside>
  </div>
</div>
<div id="meniu" class="ascuns">
  <div class="grila">
    <nav class="randuri" id="randuri">
      <a class="rm" href="/forum-receptor" id="r-forum"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 5h16v11H9l-5 4z"/></svg><div class="t"><b>Forumul receptorului</b><span data-rand="forum"></span></div><span class="insigna ascuns" id="insignaForum"></span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="sageata"><path d="m9 6 6 6-6 6"/></svg></a>
      <details class="rm" id="r-mesaj"><summary><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 3 3 10.5l7 2.5 2.5 7z"/><path d="m10 13 4-4"/></svg><div class="t"><b>Trimite un mesaj</b><span data-rand="mesaj"></span></div><span></span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="sageata"><path d="m9 6 6 6-6 6"/></svg></summary>
        <div class="corp">
          <div class="rand"><label for="felMesaj">Felul</label><select id="felMesaj"></select></div>
          <textarea id="textMesaj" maxlength="4000" aria-label="Mesajul"></textarea>
          <div class="rand"><label for="ecranMesaj">Ecranul sau funcția (opțional)</label><input type="text" id="ecranMesaj" maxlength="120"></div>
          <div class="fel"><input type="checkbox" id="jurnalMesaj"><label for="jurnalMesaj">Atașează jurnalul ultimei erori</label></div>
          <div class="fel"><input type="checkbox" id="capturaMesaj"><label for="capturaMesaj">Atașează o captură a ecranului (numai meniurile): se face acum, cu ce arată televizorul</label></div>
          <div class="butoane"><button type="button" class="principal" id="trimiteMesaj">Trimite</button></div>
        </div>
      </details>
      <details class="rm" id="r-raspunsuri"><summary><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18v12H3z"/><path d="m3 7 9 6 9-6"/></svg><div class="t"><b id="titluRaspunsuri">Răspunsurile echipei</b><span data-rand="raspunsuri"></span></div><span class="insigna ascuns" id="insignaRaspunsuri"></span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="sageata"><path d="m9 6 6 6-6 6"/></svg></summary>
        <div class="corp">
          <pre class="text" id="raspunsuri"></pre>
          <div class="butoane"><button type="button" id="cereRaspunsuri">Caută răspunsuri noi</button></div>
        </div>
      </details>
      <details class="rm" id="r-trimise"><summary><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 16h6"/></svg><div class="t"><b>Ce am trimis</b><span data-rand="trimise"></span></div><span></span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="sageata"><path d="m9 6 6 6-6 6"/></svg></summary>
        <div class="corp">
          <table><thead><tr><th>Data</th><th>Felul</th><th>Mărimea</th><th>Starea</th></tr></thead><tbody id="trimise"></tbody></table>
        </div>
      </details>
      <details class="rm" id="r-date"><summary><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 4h16v6H4zM4 14h16v6H4z"/><path d="M8 7h.01M8 17h.01"/></svg><div class="t"><b>Datele pe care le trimit</b><span data-rand="date"></span></div><span></span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="sageata"><path d="m9 6 6 6-6 6"/></svg></summary>
        <div class="corp">
          <div id="feluriMeniu"></div>
          <div class="fel"><input type="checkbox" id="automatMeniu"><label for="automatMeniu"><b id="automatEticheta2"></b><span class="nota" id="automatRand2"></span></label></div>
          <div class="rand"><label for="numeMeniu">Numele (opțional)</label><input type="text" id="numeMeniu" maxlength="60"></div>
          <div class="rand"><label for="emailMeniu">E-mailul (opțional)</label><input type="email" id="emailMeniu" maxlength="120"></div>
          <div class="butoane"><button type="button" class="principal" id="salveazaBife">Salvează</button></div>
        </div>
      </details>
      <details class="rm" id="r-acum"><summary><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01"/></svg><div class="t"><b>Ce trimit acum</b><span data-rand="acum"></span></div><span></span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="sageata"><path d="m9 6 6 6-6 6"/></svg></summary>
        <div class="corp"><pre class="text" id="ultimul"></pre></div>
      </details>
      <a class="rm ascuns" href="/asistenta" id="r-asistenta"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .8-1 1.5v.7M12 17h.01"/></svg><div class="t"><b>Cere ajutor de la distanță</b><span data-rand="asistenta"></span></div><span></span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="sageata"><path d="m9 6 6 6-6 6"/></svg></a>
      <a class="rm ascuns" href="/probe" id="r-probe"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/></svg><div class="t"><b>Probele receptorului</b><span data-rand="probe"></span></div><span></span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="sageata"><path d="m9 6 6 6-6 6"/></svg></a>
      <div class="rm ascuns" id="canalTesteri"><label class="rm-bifa" for="canalTesteriBifa"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 12a8 8 0 0 1-14 5.3L4 15M4 12a8 8 0 0 1 14-5.3L20 9"/><path d="M20 4v5h-5M4 20v-5h5"/></svg><div class="t"><b id="canalTesteriEticheta"></b><span id="canalTesteriNota"></span></div><input type="checkbox" id="canalTesteriBifa"></label></div>
      <details class="rm" id="r-public"><summary><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg><div class="t"><b>Apariția publică</b><span data-rand="public"></span></div><span class="valoare" id="valoarePublic"></span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="sageata"><path d="m9 6 6 6-6 6"/></svg></summary>
        <div class="corp">
          <p class="nota">Opțional: apari cu un nume ales de tine pe pagina testerilor de pe site și la modelul tău. Fără parole pe receptor.</p>
          <p class="nota forum ascuns">E-mailul (opțional) îți face un cont pe forum: primești o legătură și îți pui parola acolo, de pe orice aparat.</p>
          <p class="intrebare" id="profil"></p>
          <div class="rand"><label for="numePublic">Numele public</label><input type="text" id="numePublic" maxlength="40"></div>
          <div class="rand forum ascuns"><label for="emailCont">E-mailul pentru cont (opțional)</label><input type="email" id="emailCont" maxlength="120"></div>
          <div class="butoane"><button type="button" class="principal" id="salveazaProfil">Salvează</button><button type="button" id="nuPublic">Nu mai apar public</button></div>
          <div class="rand forum ascuns"><label for="cod6">Codul de 6 cifre de pe site</label><input type="text" id="cod6" maxlength="6" inputmode="numeric"></div>
          <div class="butoane forum ascuns"><button type="button" id="leaga">Leagă cu codul</button><button type="button" id="codLegare">Leagă de pe acest aparat</button></div>
          <p class="nota forum ascuns" id="legatura"></p>
        </div>
      </details>
      <details class="rm" id="r-nota"><summary><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3 4 6v6c0 4.5 3.4 8 8 9 4.6-1 8-4.5 8-9V6z"/></svg><div class="t"><b>Nota de confidențialitate</b><span data-rand="nota"></span></div><span></span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="sageata"><path d="m9 6 6 6-6 6"/></svg></summary>
        <div class="corp">
          <p class="nota" id="notaScurta"></p>
          <p class="nota"><a id="legaturaNota2" href="#" target="_blank" rel="noopener">Nota întreagă</a></p>
        </div>
      </details>
      <details class="rm rosu" id="r-iesire"><summary><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 4h5v16h-5M10 8l-4 4 4 4M6 12h10"/></svg><div class="t"><b>Ieși din program și șterge datele</b><span data-rand="iesire"></span></div><span></span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="sageata"><path d="m9 6 6 6-6 6"/></svg></summary>
        <div class="corp">
          <div class="butoane"><button type="button" class="rosu" id="iesire">Ieși și șterge datele</button></div>
        </div>
      </details>
      <div id="confirmare" class="card ascuns"></div>
    </nav>
    <aside class="panou-t">
      <div class="titlu"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3 6.4 20.2l1.1-6.2L3 9.6l6.2-.9z"/></svg><div><b>Ești beta tester</b><span id="inscrisDin"></span></div></div>
      <div class="camp"><span>Numele tău pe forum</span><b class="chihlimbar" id="numeForum"></b></div>
      <div class="camp"><b id="ultima"></b><span id="automatUltima"></span></div>
      <p class="banda ascuns" id="numarMeniu"></p>
      <button type="button" class="principal mare" id="trimiteAcum">Trimite acum</button>
      <p class="nota" data-rand="trimite_acum"></p>
      <p class="nota" id="identificator" style="white-space:pre-line"></p>
    </aside>
  </div>
</div>
<p class="mesaj" id="mesaj"></p>
<p class="nota">Același program e pe televizor, în __DRUM_MENIU__.</p>
</main>
<div hidden><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" id="svg-actualizare"><path d="M12 16V4M6 10l6-6 6 6M4 20h16"/></svg><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" id="svg-traducere"><path d="M4 5h16v11H9l-5 4z"/></svg><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" id="svg-conexiune"><path d="M4 14h16v6H4z"/><path d="M8 17h.01M12 17h.01M8 10a6 6 0 0 1 8 0M5 7a10 10 0 0 1 14 0"/></svg><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" id="svg-noutati"><path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3 6.4 20.2l1.1-6.2L3 9.6l6.2-.9z"/></svg><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" id="svg-informatii"><circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/></svg></div>
<script>
__SCRIPT_COMUN__
var STARE = null;
var LOC_CONFIRMARE = $("confirmare").parentNode;
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
function avantaje(lista){
  var cutie = $("listaAvantaje"); if(cutie.childElementCount){ return; }
  (lista || []).forEach(function(a){
    var d = document.createElement("div"); d.className = "avantaj";
    var i = document.getElementById("svg-" + a[0]); if(i){ d.appendChild(i.cloneNode(true)); } else { d.appendChild(document.createElement("span")); }
    var t = document.createElement("div");
    var b = document.createElement("b"); b.textContent = a[1]; t.appendChild(b);
    var s = document.createElement("span"); s.textContent = a[2]; t.appendChild(s);
    d.appendChild(t); cutie.appendChild(d);
  });
}
function arata(d){
  STARE = d;
  $("incarcare").classList.add("ascuns");
  $("acord").classList.toggle("ascuns", d.inscris);
  $("meniu").classList.toggle("ascuns", !d.inscris);
  var nv = d.nota_noua;
  $("notaNoua").classList.toggle("ascuns", !nv);
  if(nv){
    // nota acceptata e mai veche: nimic nu pleaca pana la Accept (acordul nou cu alegerile de dinainte)
    $("acord").classList.add("ascuns"); $("meniu").classList.add("ascuns");
    $("notaOprita").textContent = nv.oprita; $("notaTitlu").textContent = nv.titlu; $("notaAnunt").textContent = nv.anunt;
    $("notaCeNou").textContent = nv.ce_e_nou; $("notaAcceptRand").textContent = nv.accept_rand;
    var u = $("notaNoutati"); u.textContent = "";
    (nv.noutati || []).forEach(function(x){ var li = document.createElement("li"); li.textContent = x; u.appendChild(li); });
    $("notaCiteste").textContent = nv.citeste; $("notaCiteste").href = nv.adresa; $("notaAccept").textContent = nv.accept;
    $("notaNoua").appendChild($("confirmare"));
    return;
  }
  LOC_CONFIRMARE.appendChild($("confirmare"));
  $("legaturaNota").href = d.adresa_nota; $("legaturaNota2").href = d.adresa_nota;
  ["numarAcord", "numarMeniu"].forEach(function(id){ $(id).textContent = d.numar || ""; $(id).classList.toggle("ascuns", !d.numar); });
  $("automatEticheta").textContent = d.automat_eticheta; $("automatRand").textContent = d.automat_rand;
  $("automatEticheta2").textContent = d.automat_eticheta; $("automatRand2").textContent = d.automat_rand;
  document.querySelectorAll("[data-rand]").forEach(function(e){ e.textContent = (d.randuri || {})[e.getAttribute("data-rand")] || ""; });
  if(!d.inscris){
    $("titluInvitatie").textContent = d.intrebare || "";
    $("textInvitatie").textContent = d.invitatie || "";
    avantaje(d.avantaje);
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
  $("inscrisDin").textContent = d.din || "";
  $("numeForum").textContent = d.nume_forum || "Apari cu numele dat de forum.";
  $("notaScurta").textContent = d.nota_scurta;
  $("ultima").textContent = d.ultima || "";
  $("automatUltima").textContent = d.automat_text || "";
  $("valoarePublic").textContent = d.public || "";
  document.querySelectorAll(".forum").forEach(function(e){ e.classList.toggle("ascuns", !d.legare_forum); });
  var pagini = (d.pagini || []).map(function(p){ return p[0]; });
  $("r-asistenta").classList.toggle("ascuns", pagini.indexOf("/asistenta") === -1);
  $("r-probe").classList.toggle("ascuns", pagini.indexOf("/probe") === -1);
  var ct = d.canal_testeri;
  $("canalTesteri").classList.toggle("ascuns", !ct);
  if(ct){ $("canalTesteriBifa").checked = !!ct.pornit; $("canalTesteriEticheta").textContent = ct.eticheta; $("canalTesteriNota").textContent = ct.nota || (d.randuri || {}).canal_testeri || ""; }
  $("raspunsuri").textContent = d.raspunsuri || "";
  $("insignaRaspunsuri").textContent = d.insigna_raspunsuri || "";
  $("insignaRaspunsuri").classList.toggle("ascuns", !d.insigna_raspunsuri);
  $("insignaForum").textContent = d.insigna_forum || "";
  $("insignaForum").classList.toggle("ascuns", !d.insigna_forum);
  if(d.forum_verifica && !REVENIT){ REVENIT = true; setTimeout(citeste, 5000); }
  var t = $("trimise"); t.textContent = "";
  (d.trimise || []).forEach(function(r){
    var tr = document.createElement("tr");
    r.forEach(function(x){ var td = document.createElement("td"); td.textContent = x; tr.appendChild(td); });
    t.appendChild(tr);
  });
  $("ultimul").textContent = d.ultimul || "Încă nu a plecat niciun pachet.";
  $("identificator").textContent = d.text_id || "";
}
var REVENIT = false;
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
$("r-raspunsuri").addEventListener("toggle", function(){ if($("r-raspunsuri").open && STARE && STARE.insigna_raspunsuri){ var q = new URLSearchParams(); q.set("fa", "raspunsuri"); fa(q); } });
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
$("iesireVeche").addEventListener("click", function(){ var q = new URLSearchParams(); q.set("fa", "iesire"); cuConfirmare("/api/beta-tester-fa", q, function(){ citeste(); }); });
$("notaAccept").addEventListener("click", function(){ var q = new URLSearchParams(); q.set("fa", "accepta-nota"); fa(q); });
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
		N_("Devino beta tester"),
		N_("Numele (opțional)"),
		N_("E-mailul (opțional)"),
		N_("Nota de confidențialitate"),
		N_("Sunt de acord"),
		N_("Renunț"),
		N_("Forumul receptorului"),
		N_("Trimite un mesaj"),
		N_("Felul"),
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
		N_("Cere ajutor de la distanță"),
		N_("Probele receptorului"),
		N_("Apariția publică"),
		N_("Opțional: apari cu un nume ales de tine pe pagina testerilor de pe site și la modelul tău. Fără "
			"parole pe receptor."),
		N_("E-mailul (opțional) îți face un cont pe forum: primești o legătură și îți pui parola acolo, de "
			"pe orice aparat."),
		N_("Numele public"),
		N_("E-mailul pentru cont (opțional)"),
		N_("Nu mai apar public"),
		N_("Codul de 6 cifre de pe site"),
		N_("Leagă cu codul"),
		N_("Leagă de pe acest aparat"),
		N_("Nota întreagă"),
		N_("Ieși din program și șterge datele"),
		N_("Ieși și șterge datele"),
		N_("Ești beta tester"),
		N_("Numele tău pe forum"),
		N_("Trimite acum"),
		N_("Același program e pe televizor, în __DRUM_MENIU__."),
		N_("Mesajul"),
	),
	"js": (
		N_("Apari cu numele dat de forum."),
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
