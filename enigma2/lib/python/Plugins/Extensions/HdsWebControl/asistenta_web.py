# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# asistenta_web.py: Asistenta de la distanta in interfata web (HdsWebControl), perechea ecranului de pe receptor
# (Screens/HdsAsistenta.py), pentru oricine. Aceeasi stare, aceleasi texte si acelasi jurnal, din
# Components/HdsAsistenta.py; in meniul web e randul /asistenta din Setari (data/menu.xml).
# Pagina de pornire are lista "Cât timp" (cele cinci durate, A.alegeriDurata, 2 ore alese la deschidere), randul scurt
# (A.TEXT_SCURT), legatura "Termenii și condițiile" (textul intreg, A.textTermeni, intr-o fereastra peste pagina) si
# butonul Start, care porneste cu durata aleasa. Pornita, pagina arata pana cand e pornita, lista "Schimbă durata"
# (aceleasi cinci; alegerea o schimba pe loc, socotita de acum, perechea Verde de pe receptor), butonul Oprește si
# jurnalul. Oprește intreaba intai, in pagina, "Oprești asistența?" (Nu cu focus / "Da, opresc"), perechea intrebarii
# de la Rosu de pe receptor (RCF, 15-16.11.2026: pe televizor Rosu "Oprește" sta dupa Start in locul lui "Înapoi" si a
# oprit din greseala trei sesiuni); linkul Oprește din banda de sus a celorlalte pagini duce aici, cu intrebarea deschisa
# (/asistenta#opreste). Codul sesiunii nu se trimite browserului: ramane intern, intre receptor, server si echipa. Cand echipa a
# trimis concluzii (op "concluzii"), pagina le arata sub jurnal, si dupa oprire: "Ce am găsit și ce am făcut", textul
# si multumirile (A.stareConcluzii). Cat exista copia setarilor facuta cand a intrat echipa (A.stareCopie, si dupa
# oprire), pagina arata ziua si ora ei si butonul "Pune înapoi cum era", perechea tastei Albastre de pe receptor: o
# intrebare in pagina (aceeasi ca la "Copia setărilor", cu Nu / Da, pune la loc; fara fereastra browserului, ca restul
# paginii), apoi cererea si repornirea interfetei, ca la /api/copie-setari-pune; sesiunea nu se opreste.
# Start porneste pe loc din orice browser acceptat de poarta locala, cu termenii bifati.
# Nu cere asocierea cu codul de pe televizor. HdsAsistentaSemn.pornesteWeb anunta pe receptor
# ca a pornit din web, fara sa ceara o apasare acolo. Exteriorul ramane respins de poarta comuna.
# Oprirea merge din orice browser acceptat. Cat asistenta e activa, paginile web au sus
# o banda (bandaWeb, pusa de meniu_comun_web.pagina), cu linkul Oprește spre intrebarea din pagina.
#
# Rute (poarta comuna meniu_comun_web; ce schimba ceva cere, cu cookie, POST si antetul CSRF):
#   GET  /api/asistenta            starea, pana cand e pornita, ultimele randuri din jurnal (fara cod), ultimele
#                                  concluzii ale echipei
#   GET  /api/asistenta-catalog    lista operatiilor in limba receptorului
#   POST /api/asistenta-cere?accept=1&durata=M   Start, cu durata aleasa (minute, una din A.DURATE_MIN; lipsa: 2 ore);
#                                       asistenta pornita e mereu completa (nivelul B)
#   POST /api/asistenta-durata?durata=M  "Schimbă durata": durata sesiunii de acum, socotita de acum (A.schimbaDurata)
#   POST /api/asistenta-opreste    opreste
#   POST /api/asistenta-pune-inapoi     "Pune înapoi cum era": cere punerea la loc a copiei de asistenta si reporneste
#                                       interfata (A.cerePunereaInapoi)
#   POST /api/asistenta-raspunde?id=N&varianta=I   raspunsul omului la intrebarea echipei (op "intrebare", 0.7.7), perechea
#                                       ferestrei de pe televizor: aceeasi intrebare, aceleasi variante, ca butoane in
#                                       pagina; primul raspuns (televizor sau web) o inchide peste tot (A.raspundeIntrebare)
#   POST /api/asistenta-raspunde?id=N&text=T   raspunsul scris (0.7.8, intrebarea cu "*"): campul si "Trimite" din pagina,
#                                       perechea tastaturii de pe televizor (A.raspundeIntrebareText)
#   GET  /asistenta                pagina
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau modulul lor (A).

def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_): textele se traduc la folosire."""
	return text


def _t(text):
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _a(A=None):
	if A is not None:
		return A
	from Components import HdsAsistenta
	return HdsAsistenta


def stare(request=None, A=None, B=None):
	"""Starea pentru pagina (si pentru banda): fara codul sesiunii, care ramane intern."""
	A = _a(A)
	s = A.stare()
	return {"result": True, "stare": s.get("stare"), "disponibil": s.get("disponibil"),
		"eroare_pornire": s.get("eroare_pornire") or "",
		"setari_internet": "/retea" if s.get("eroare_pornire") else "",
		"ramas_s": s.get("ramas_s", 0), "jurnal": s.get("jurnal", []), "nivel": s.get("nivel"),
		"durata_implicita": s.get("durata_implicita"),
		# durata sesiunii de acum (minute, 0 = permanent; None cand e oprita) si cele cinci alegeri, cu textul lor
		"durata": s.get("durata"),
		"alegeri_durata": [{"min": m, "text": t} for m, t in (s.get("alegeri_durata") or [])],
		# pana cand e pornita, tradus ("Pornită până la ZZ.LL, HH:MM." / "Pornită, fără sfârșit; ...")
		"permanent": bool(s.get("permanent")), "pana_text": s.get("pana_text") or "",
		# ce face echipa acum, ca pe banda de pe televizor ("lucrează acum" / "a terminat..." / "")
		"activitate": s.get("activitate") or "",
		"concluzii": _concluzii(A),
		# copia pentru "Pune înapoi cum era" ({"data_text", "text", "intrebare"}) sau None
		"copie": s.get("copie"),
		# intrebarea echipei care asteapta raspunsul ({"id", "text", "variante", "ramas_s", "scris"}) sau None (op
		# "intrebare"; "scris": se poate raspunde si cu un text, 0.7.8)
		"intrebare": s.get("intrebare"),
		# AST8: cat merge, ca pe televizor la EXIT: lucreaza in fundal, omul poate privi televizorul ("" cand e oprita)
		"fundal": _fundal(s)}


def _fundal(s):
	"""Randul "Asistența lucrează..." (Screens/HdsAsistentaSemn.textIesire) cat asistenta merge, altfel ""."""
	if s.get("stare") in (None, "", "oprit") or not s.get("disponibil", True):
		return ""
	try:
		from Screens import HdsAsistentaSemn as Semn
		return Semn.textIesire()
	except Exception:
		return ""


def _concluzii(A):
	"""Ultimele concluzii ale echipei ({"text", "ora_text"}) sau None; un modul vechi fara ele da None."""
	try:
		return A.stareConcluzii()
	except Exception:
		return None


def catalog(A=None):
	A = _a(A)
	try:
		from Components import HdsAsistentaCatalog as C
		return {"result": True, "operatii": [{"op": op, "grup": _t(grup), "fel": fel, "text": _t(text)}
			for (op, grup, fel, text) in C.pentru_afisare()]}
	except Exception as e:
		return {"result": False, "message": _t("Nu pot citi catalogul: %s") % e}


def cere(argumente, A=None, B=None, de_incredere=False):
	"""Start din pagina, cu durata aleasa (argumentul durata, minute; lipsa: 2 ore). Browser de incredere: porneste pe
	loc; altfel deschide pagina de pornire pe receptor, cu aceeasi durata pe randul "Cât timp"."""
	A = _a(A)
	kw = {"durata_min": argumente["durata"]} if (argumente or {}).get("durata") else {}
	try:
		from Screens import HdsAsistentaSemn as Semn
		from .meniu_comun_web import sesiune
		if de_incredere:
			reusit, mesaj = Semn.pornesteWeb(sesiune(), **kw)
		else:
			reusit, mesaj = Semn.cerereWeb(sesiune(), **kw)
	except Exception as e:
		reusit, mesaj = False, _t("Eroare pe receptor: %s") % e
	rez = stare(None, A)
	rez.update({"result": bool(reusit) and not bool(rez["eroare_pornire"]),
		"message": rez["eroare_pornire"] or mesaj})
	return rez


def opreste(A=None):
	A = _a(A)
	reusit, mesaj = A.opreste("de om (web)")
	rez = stare(None, A)
	rez.update({"result": bool(reusit), "message": mesaj})
	return rez


def schimbaDurata(argumente, A=None):
	"""POST /api/asistenta-durata: "Schimbă durata" din pagina (perechea Verde de pe ecranul asistentei pornite), pe loc,
	fara intrebare; mesajul e noul "Pornită până la ..."."""
	A = _a(A)
	reusit, mesaj = A.schimbaDurata((argumente or {}).get("durata"), "web")
	rez = stare(None, A)
	rez.update({"result": bool(reusit), "message": mesaj})
	return rez


def raspunde(argumente, A=None):
	"""POST /api/asistenta-raspunde: raspunsul omului la intrebarea echipei, din pagina: indicele variantei sau (0.7.8,
	intrebarea cu "*") textul scris; o intrebare deja inchisa (raspuns de pe televizor, timpul trecut) nu mai primeste
	nimic."""
	A = _a(A)
	try:
		if "text" in argumente:
			ok = A.raspundeIntrebareText(int(argumente.get("id", "")), argumente.get("text", ""), "web")
		else:
			ok = A.raspundeIntrebare(int(argumente.get("id", "")), int(argumente.get("varianta", "")), "web")
	except (TypeError, ValueError, AttributeError):
		ok = False
	rez = stare(None, A)
	rez.update({"result": bool(ok), "message": "" if ok else _t(getattr(A, "TEXT_INTREBARE_INCHISA", ""))})
	return rez


# cati octeti din textul scris trimis de pagina se citesc (200 de semne, cel mult 4 octeti fiecare in UTF-8)
RASPUNS_TEXT_OCTETI = 800


def _argumenteRaspuns(request):
	"""Argumentele raspunsului: id si varianta, numai cifre; textul scris (0.7.8), din UTF-8,
	intreg (A.raspundeIntrebareText il curata: un rand, cel mult 200 de semne)."""
	args = getattr(request, "args", None) or {}
	rez = {}
	for nume in ("id", "varianta"):
		valori = args.get(nume.encode("ascii"))
		if valori:
			v = valori[0]
			if isinstance(v, bytes):
				v = v.decode("ascii", "replace")
			rez[nume] = v if str(v).isdigit() else ""
	valori = args.get(b"text")
	if valori:
		v = valori[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "ignore")
		rez["text"] = str(v)
	return rez


def scriereSecret(C=None):
	"""Scrierea pe receptor este disponibila si cu asistenta pornita."""
	return {"result": True, "permisa": True, "message": ""}


def protejeazaScrierea(text):
	"""Pagina nu adauga opriri ale scrierii din cauza asistentei."""
	return text


SCRIPT_SCRIERE_SECRET = ""


def _sesiuneEnigma():
	try:
		from .meniu_comun_web import sesiune
		return sesiune()
	except Exception:
		return None


def puneInapoi(A=None, sesiune=None):
	"""POST /api/asistenta-pune-inapoi ("Pune înapoi cum era"): cererea de punere la loc a copiei facute cand a intrat
	echipa (A.cerePunereaInapoi), apoi repornirea interfetei, ca /api/copie-setari-pune; enigma2.sh pune copia la loc
	inainte de pornirea interfetei. Sesiunea de asistenta nu se opreste. sesiune: sesiunea enigma2 (probele dau una)."""
	A = _a(A)
	if sesiune is None:
		sesiune = _sesiuneEnigma()
	if sesiune is None:
		rez = stare(None, A)
		rez.update({"result": False, "message": _t("Interfața nu este gata pentru repornire.")})
		return rez
	ok, mesaj = A.cerePunereaInapoi()
	rez = stare(None, A)
	if not ok:
		rez.update({"result": False, "message": mesaj})
		return rez
	from Screens.Standby import TryQuitMainloop
	sesiune.open(TryQuitMainloop, 3)
	rez.update({"result": True,
		"message": _t("Interfața repornește și pune la loc copia. Pagina se reîncarcă singură.")})
	return rez


# linkul "Oprește" al benzii web: nu mai opreste pe loc (RCF, 15-16.11.2026), duce la /asistenta cu intrebarea "Oprești
# asistența?" deschisa (#opreste; Nu cu focus, "Da, opresc"), ca pe receptor; tokenul paginii (CFG.jeton), cand exista,
# merge mai departe
_OPRESTE_BANDA = ("var c=window.CFG||{};"
	"location.href='/asistenta'+(c.jeton?'?token='+encodeURIComponent(c.jeton):'')+'#opreste';return false;")


def bandaWeb(A=None):
	"""Banda pusa sus pe paginile web cat asistenta e activa (HTML gata, tradus), sau "" cand nu e: ca e pornita si pana
	cand ("până la ZZ.LL, HH:MM" / "fără sfârșit") si linkul Oprește, spre intrebarea din pagina asistentei."""
	import html as _html
	try:
		A = _a(A)
		ses = A.sesiune()
		if ses is None or not ses.activa():
			return ""
		text = A.textPana(ses, banda=True)
		try:
			# ce face echipa acum, ca pe banda de pe televizor (un modul vechi fara textActivitate: numai pana cand)
			text = A.textActivitate(ses) or text
		except Exception:
			pass
	except Exception:
		return ""
	return ('<div role="status" style="background:#c0392b;color:#fff;padding:8px 14px;text-align:center;'
		'font:600 .95rem system-ui,sans-serif;">%s · <a href="/asistenta#opreste" onclick="%s" style="color:#fff;">%s</a>'
		'</div>' % (_html.escape(text), _html.escape(_OPRESTE_BANDA, quote=True), _html.escape(_t("Oprește"))))


def _argumente(request):
	"""Argumentele lui Start si ale lui "Schimbă durata": accept si durata (minute)."""
	args = getattr(request, "args", None) or {}
	rez = {}
	for nume in ("accept", "durata"):
		valori = args.get(nume.encode("ascii"))
		if valori:
			v = valori[0]
			if isinstance(v, bytes):
				v = v.decode("utf-8", "replace")
			rez[nume] = v
	return rez


def rute(baza, resource, A=None):
	class StareResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(request, A))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class CatalogResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, catalog(A))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class CereResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				# Poarta comuna a verificat reteaua locala si cererea; Start nu mai cere codul TV.
				return self._raspunde(request, cere(_argumente(request), A, de_incredere=True))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)

	class OpresteResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, opreste(A))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)

	class DurataResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, schimbaDurata(_argumente(request), A))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class PuneInapoiResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, puneInapoi(A))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class RaspundeResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, raspunde(_argumenteRaspuns(request), A))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class PaginaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			from .meniu_comun_web import pagina as poarta
			return poarta(request, pagina_text)

	api = {
		b"asistenta": StareResource(),
		b"asistenta-catalog": CatalogResource(),
		b"asistenta-cere": CereResource(),
		b"asistenta-opreste": OpresteResource(),
		b"asistenta-durata": DurataResource(),
		b"asistenta-pune-inapoi": PuneInapoiResource(),
		b"asistenta-raspunde": RaspundeResource(),
	}
	return api, {b"asistenta": PaginaResource()}


def _drumMeniu(A=None):
	try:
		return _a(A).drumMeniu()
	except Exception:
		return "Meniu > Setări > Asistență de la distanță"


def _termeni(A=None):
	"""Termenii si conditiile intregi (A.textTermeni), ca paragrafe HTML pentru fereastra de peste pagina."""
	import html as _html
	try:
		text = _a(A).textTermeni()
	except Exception:
		return ""
	return "".join("<p>%s</p>" % _html.escape(p) for p in text.split("\n\n") if p.strip())


def pagina_text(stil, config_pagina, A=None):
	return (_traducePagina(PAGINA).replace("__STIL_COMUN__", stil).replace("__CONFIG__", config_pagina)
		.replace("__TERMENI__", _termeni(A)))


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Asistență de la distanță</title>
<style>__STIL_COMUN__
  main{max-width:820px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .scurt{line-height:1.5;margin:0 0 14px;}
  .bifa{display:flex;gap:10px;align-items:center;margin:0 0 16px;cursor:pointer;line-height:1.4;}
  .bifa input{width:22px;height:22px;margin:0;flex:none;accent-color:#46B06A;}
  .bifa a{color:inherit;text-decoration:underline;}
  .jurnal{font-family:monospace;font-size:.82rem;line-height:1.45;white-space:pre-wrap;word-break:break-word;color:var(--text-slab);margin:0;max-height:360px;overflow:auto;}
  button{min-height:44px;padding:8px 22px;border-radius:8px;border:0;color:#fff;font:inherit;font-weight:600;cursor:pointer;}
  .verde{background:#2e8b4e;}
  .rosu{background:#c0392b;}
  .gri{background:#3a4255;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.2em;}
  .eroare{color:#ffb4a8;}
  .nota{color:var(--text-slab);font-size:.85rem;line-height:1.45;}
  .pana{font-weight:600;margin:0 0 12px;}
  .durata{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:0 0 14px;}
  .durata select{min-width:180px;}
  .fereastra{position:fixed;inset:0;background:rgba(0,0,0,.6);display:flex;align-items:center;justify-content:center;padding:16px;z-index:50;}
  .fereastra .card{max-width:760px;width:100%;max-height:86vh;display:flex;flex-direction:column;margin:0;}
  .fereastra h2{font-size:1.1rem;margin:0 0 10px;}
  .fereastra .termeni{overflow:auto;flex:1;margin:0 0 12px;}
  .fereastra .termeni p{font-size:.9rem;line-height:1.5;margin:0 0 8px;}
  .intrebare{background:#1b2130;border:1px solid var(--bordura);border-radius:8px;padding:10px;margin-top:10px;line-height:1.45;}
  .intrebare p{margin:0 0 10px;}
  .intrebare button{margin:0 8px 0 0;}
  .scris{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 8px;}
  .scris input{flex:1 1 220px;min-width:0;}
  .concluzii h2{font-size:1.1rem;margin:0 0 6px;}
  .concluzii .text{white-space:pre-wrap;word-break:break-word;line-height:1.5;margin:0 0 10px;}
  .echipa{border-color:#e0a030;}
  .echipa h2{font-size:1.1rem;margin:0 0 8px;}
  .echipa .text{white-space:pre-wrap;word-break:break-word;line-height:1.5;margin:0 0 12px;}
  .echipa button{margin:0 8px 8px 0;}
  .ascuns{display:none;}
</style>
</head>
<body>
<main>
<h1>Asistență de la distanță</h1>
<p class="mesaj" id="incarcare">Se citește starea...</p>
<section class="card ascuns" id="indisponibil">
  <p>Funcția nu e disponibilă pe această imagine.</p>
</section>
<section class="card ascuns" id="pornire">
  <p class="durata"><label for="durata">Cât timp</label><select id="durata"></select></p>
  <p class="scurt">Echipa HD Satelit vede ecranele, setările și imaginea canalului și poate controla receptorul prin toate meniurile. Echipa vede inclusiv numele de utilizator, parolele, PIN-urile și cheile. Poți opri oricând.</p>
  <p><a href="#" id="termeni">Termenii și condițiile</a></p>
  <button class="verde" id="porneste">Start</button>
  <p class="mesaj" id="mesaj"></p>
  <p class="ascuns" id="internet"><a id="setariInternet" href="/retea">Setările de internet</a></p>
</section>
<section class="card echipa ascuns" id="intrebareEchipa" role="alertdialog" aria-labelledby="intrebareTitlu">
  <h2 id="intrebareTitlu">Întrebare de la HD Satelit</h2>
  <p class="text" id="intrebareEchipaText"></p>
  <div id="intrebareVariante"></div>
  <div class="scris ascuns" id="intrebareScris"><input type="text" id="raspunsScris" maxlength="200" autocomplete="off" placeholder="Scrie răspunsul" aria-label="Scrie răspunsul"><button class="verde" type="button" id="trimiteRaspuns">Trimite</button></div>
  <p class="mesaj" id="mesajIntrebare"></p>
</section>
<section class="card ascuns" id="pornita">
  <p class="pana" id="activitate" role="status"></p>
  <p class="pana" id="stare"></p>
  <p class="nota ascuns" id="conectatNota">Echipa se uită imediat ce poate. Poți închide pagina, asistența rămâne pornită.</p>
  <p class="nota ascuns" id="fundal"></p>
  <p class="durata ascuns" id="randDurata"><label for="durataNoua">Schimbă durata</label><select id="durataNoua"></select></p>
  <p class="mesaj" id="mesajDurata"></p>
  <button class="rosu" id="opreste">Oprește</button>
  <div class="intrebare ascuns" id="intrebareOprire"><p>Oprești asistența?</p>
    <button class="gri" id="oprireNu">Nu</button>
    <button class="rosu" id="oprireDa">Da, opresc</button>
  </div>
  <p class="mesaj" id="mesajOprire"></p>
  <p class="nota ascuns" id="asteptare">Te anunțăm când intrăm. Poți folosi receptorul între timp.</p>
  <p class="nota ascuns" id="asteptareNuOpri">Dacă nu intrăm imediat, las-o pornită măcar 30 de minute: poate ajutăm pe altcineva chiar acum.</p>
  <p class="nota">Jurnalul asistenței</p>
  <pre class="jurnal" id="jurnal"></pre>
</section>
<section class="card ascuns" id="copie">
  <p class="pana" id="copieText"></p>
  <p class="nota">Copia se face singură când intră echipa, înainte de orice schimbare. Butonul pune la loc canalele, setările și rețeaua de atunci; interfața repornește.</p>
  <button class="gri" id="puneInapoi">Pune înapoi cum era</button>
  <div class="intrebare ascuns" id="intrebareCopie"><p id="intrebareText"></p>
    <button class="gri" id="copieNu">Nu</button>
    <button class="rosu" id="copieDa">Da, pune la loc</button>
  </div>
  <p class="mesaj" id="mesajCopie"></p>
</section>
<section class="card concluzii ascuns" id="concluzii">
  <h2>Ce am găsit și ce am făcut</h2>
  <p class="nota" id="concluziiOra"></p>
  <p class="text" id="concluziiText"></p>
  <p class="nota">Mulțumim că ne-ai lăsat să te ajutăm.</p>
</section>
</main>
<div class="fereastra ascuns" id="fereastra" role="dialog" aria-modal="true" aria-labelledby="titluTermeni">
  <div class="card">
    <h2 id="titluTermeni">Termenii și condițiile</h2>
    <div class="termeni">__TERMENI__</div>
    <div><button class="gri" id="inchide">Închide</button></div>
  </div>
</div>
<script>
var CFG = __CONFIG__;
function $(id){ return document.getElementById(id); }
function adresa(cale){ if(!CFG.jeton){ return cale; } return cale + (cale.indexOf("?")===-1?"?":"&") + "token=" + encodeURIComponent(CFG.jeton); }
function cerere(cale, metoda, date){
  var o = {method: metoda||"GET", cache:"no-store", credentials:"same-origin", headers:{}};
  if(CFG.csrf){ o.headers["X-HDS-CSRF"] = CFG.csrf; }
  if(date){ o.headers["Content-Type"]="application/x-www-form-urlencoded"; o.body = date.toString(); }
  return fetch(adresa(cale), o).then(function(r){ return r.json().catch(function(){ return {result:false, message:"HTTP "+r.status}; }); });
}
function mesaj(id,t,e){ var m=$(id); m.textContent=t||""; m.classList.toggle("eroare",!!e); }
function nuRaspunde(){ return "Receptorul nu răspunde."; }
var copiaInapoi = null;
// "Cât timp" (pornire) si "Schimbă durata" (pornita): cele cinci durate, puse o data din stare (textele vin traduse de pe
// receptor); lista de pornire are 2 ore aleasa la deschidere, cea de schimbare urmeaza durata sesiunii cand se schimba
var durateFacute = false, durataVazuta;
function puneDurate(d){
  var lista = d.alegeri_durata || [];
  if(durateFacute || !lista.length){ return; }
  durateFacute = true;
  ["durata","durataNoua"].forEach(function(id){ var s=$(id);
    lista.forEach(function(a){ var o=document.createElement("option"); o.value=String(a.min); o.textContent=a.text; s.appendChild(o); }); });
  $("durata").value = String(d.durata_implicita || lista[0].min);
}
function arataDurata(d, activa){
  $("randDurata").classList.toggle("ascuns", !activa || d.stare==="se-opreste" || !durateFacute);
  if(!activa){ durataVazuta = undefined; return; }
  if(d.durata === durataVazuta){ return; }
  durataVazuta = d.durata;
  var s = $("durataNoua"); s.value = String(d.durata);
  if(s.value !== String(d.durata)){ s.selectedIndex = -1; }
}
var eroarePornireVazuta = "";
var startCuFocus = false;
// deschisa din banda de sus a altei pagini (/asistenta#opreste): intrebarea opririi se arata singura, cand starea spune
// ca asistenta merge
var cereOprirea = location.hash === "#opreste";
function intreabaOprirea(){ $("intrebareOprire").classList.remove("ascuns"); $("oprireNu").focus(); }
// banda de sus e si pe pagina asta: linkul ei schimba numai #opreste, fara reincarcare
window.addEventListener("hashchange", function(){ if(location.hash === "#opreste"){ cereOprirea = true; citeste(); } });
function arata(d){
  var activa = !!d.stare && d.stare!=="oprit";
  $("indisponibil").classList.toggle("ascuns", !!d.disponibil || activa);
  $("pornire").classList.toggle("ascuns", activa || !d.disponibil);
  // randul 170 (perechea OK-ului de pe receptor): prima data cand se vede pagina de pornire, Start primeste focusul,
  // deci Enter (sau OK din telecomanda navigatorului) porneste asistenta dintr-un pas; nu fura focusul altui camp
  if(!activa && d.disponibil && !startCuFocus){ startCuFocus = true;
    if(!document.activeElement || document.activeElement===document.body){ $("porneste").focus(); } }
  $("pornita").classList.toggle("ascuns", !activa);
  puneDurate(d); arataDurata(d, activa);
  if(!activa){ $("intrebareOprire").classList.add("ascuns"); }
  if(cereOprirea){ cereOprirea = false;
    try{ history.replaceState(null, "", location.pathname + location.search); }catch(e){}
    if(activa){ intreabaOprirea(); } }
  if(d.eroare_pornire){ mesaj("mesaj", d.eroare_pornire, true); }
  else if(eroarePornireVazuta){ mesaj("mesaj", ""); }
  eroarePornireVazuta = d.eroare_pornire || "";
  $("internet").classList.toggle("ascuns", !d.eroare_pornire);
  $("setariInternet").href = adresa("/retea");
  $("stare").textContent = d.pana_text || "";
  $("activitate").textContent = d.activitate || "";
  $("activitate").classList.toggle("ascuns", !d.activitate);
  $("fundal").textContent = d.fundal || ""; $("fundal").classList.toggle("ascuns", !d.fundal);
  // conectata si echipa nu lucreaza acum: ca vine si ca pagina se poate inchide (pe receptor A.textConectat)
  $("conectatNota").classList.toggle("ascuns", d.stare!=="conectat" || !!d.activitate);
  $("asteptare").classList.toggle("ascuns", d.stare!=="asteapta");
  $("asteptareNuOpri").classList.toggle("ascuns", d.stare!=="asteapta");
  $("jurnal").textContent = (d.jurnal||[]).join("\\n") || "Jurnalul e gol.";
  var c = d.concluzii;
  $("concluzii").classList.toggle("ascuns", !(c && c.text));
  if(c && c.text){ $("concluziiText").textContent = c.text; $("concluziiOra").textContent = c.ora_text || ""; }
  arataIntrebarea(activa ? d.intrebare : null);
  copiaInapoi = d.copie || null;
  $("copie").classList.toggle("ascuns", !copiaInapoi);
  $("copieText").textContent = copiaInapoi ? (copiaInapoi.text || "") : "";
}
// intrebarea echipei (op "intrebare"): aceleasi variante ca pe receptor, ca butoane; primul raspuns o inchide peste tot;
// din 0.7.8 si raspunsul scris (q.scris): campul si Trimite (Enter), ca tastatura de pe receptor; citirea starii la 3 s nu
// atinge campul cat e aceeasi intrebare
var intrebareVazuta = null, intrebareRaspunsLa = 0;
var TEXT_SCRIE = $("raspunsScris").placeholder;
function arataIntrebarea(q){
  var are = !!(q && ((q.variante && q.variante.length) || q.scris));
  // dupa un raspuns, randul "Răspunsul a plecat la echipă." ramane cateva secunde, apoi intrebarea pleaca
  if(!are && Date.now() - intrebareRaspunsLa < 4000){ return; }
  $("intrebareEchipa").classList.toggle("ascuns", !are);
  if(!are){ intrebareVazuta = null; return; }
  if(intrebareVazuta === q.id){ return; }
  intrebareVazuta = q.id;
  $("intrebareEchipaText").textContent = q.text || "";
  mesaj("mesajIntrebare", "");
  var loc = $("intrebareVariante"); loc.textContent = "";
  (q.variante || []).forEach(function(v, i){
    var b = document.createElement("button"); b.className = "gri"; b.type = "button"; b.textContent = v;
    b.addEventListener("click", function(){ raspundeIntrebarea(q.id, i); });
    loc.appendChild(b);
  });
  $("intrebareScris").classList.toggle("ascuns", !q.scris);
  // intrebarea de inceput (AST8) are eticheta ei pentru campul scris ("Altceva, scriu eu")
  $("raspunsScris").placeholder = q.eticheta_scris || TEXT_SCRIE;
  $("raspunsScris").value = ""; $("raspunsScris").disabled = false; $("trimiteRaspuns").disabled = false;
  if(loc.firstChild){ loc.firstChild.focus(); }
  else if(q.scris){ $("raspunsScris").focus(); }
}
function blocheazaRaspunsul(da){
  Array.prototype.forEach.call($("intrebareVariante").children, function(b){ b.disabled = da; });
  $("raspunsScris").disabled = da; $("trimiteRaspuns").disabled = da;
}
function trimiteRaspunsul(q){
  blocheazaRaspunsul(true);
  cerere("/api/asistenta-raspunde","POST",q).then(function(d){
    intrebareRaspunsLa = Date.now();
    mesaj("mesajIntrebare", d.result ? "Răspunsul a plecat la echipă." : (d.message || nuRaspunde()), !d.result);
  }).catch(function(){ mesaj("mesajIntrebare", nuRaspunde(), true); blocheazaRaspunsul(false); });
}
function raspundeIntrebarea(id, i){
  var q=new URLSearchParams(); q.set("id", String(id)); q.set("varianta", String(i));
  trimiteRaspunsul(q);
}
function raspundeScris(){
  var t = ($("raspunsScris").value || "").trim();
  if(!t || intrebareVazuta === null){ $("raspunsScris").focus(); return; }
  var q=new URLSearchParams(); q.set("id", String(intrebareVazuta)); q.set("text", t);
  trimiteRaspunsul(q);
}
$("trimiteRaspuns").addEventListener("click", raspundeScris);
$("raspunsScris").addEventListener("keydown", function(e){ if(e.key==="Enter"){ e.preventDefault(); raspundeScris(); } });
function citeste(){
  return cerere("/api/asistenta").then(function(d){
    if(d.result===false){ $("incarcare").textContent = d.message||nuRaspunde(); return; }
    $("incarcare").classList.add("ascuns"); arata(d);
  }).catch(function(){ $("incarcare").textContent=nuRaspunde(); });
}
$("termeni").addEventListener("click", function(e){ e.preventDefault(); e.stopPropagation(); $("fereastra").classList.remove("ascuns"); $("inchide").focus(); });
$("inchide").addEventListener("click", function(){ $("fereastra").classList.add("ascuns"); });
$("fereastra").addEventListener("click", function(e){ if(e.target===$("fereastra")){ $("fereastra").classList.add("ascuns"); } });
document.addEventListener("keydown", function(e){ if(e.key==="Escape"){ $("fereastra").classList.add("ascuns"); } });
$("durataNoua").addEventListener("change", function(){
  var q=new URLSearchParams(); q.set("durata", this.value);
  cerere("/api/asistenta-durata","POST",q).then(function(d){ mesaj("mesajDurata", d.message, !d.result); durataVazuta = undefined; arata(d); }).catch(function(){ mesaj("mesajDurata", nuRaspunde(), true); }); });
$("porneste").addEventListener("click", function(){
  var q=new URLSearchParams(); q.set("accept","1"); if($("durata").value){ q.set("durata", $("durata").value); }
  mesaj("mesaj", "Se pornește...");
  cerere("/api/asistenta-cere","POST",q).then(function(d){ var activa=!!d.stare && d.stare!=="oprit"; mesaj("mesaj", activa ? "" : d.message, !d.result); arata(d); }).catch(function(){ mesaj("mesaj", nuRaspunde(), true); }); });
$("opreste").addEventListener("click", intreabaOprirea);
$("oprireNu").addEventListener("click", function(){ $("intrebareOprire").classList.add("ascuns"); });
$("oprireDa").addEventListener("click", function(){ $("intrebareOprire").classList.add("ascuns");
  mesaj("mesajOprire", "Se oprește...");
  cerere("/api/asistenta-opreste","POST", new URLSearchParams()).then(function(d){ mesaj("mesajOprire", d.result ? "" : d.message, !d.result); if(d.result){ mesaj("mesaj", d.message); } arata(d); }).catch(function(){ mesaj("mesajOprire", nuRaspunde(), true); }); });
$("puneInapoi").addEventListener("click", function(){
  if(!copiaInapoi){ return; }
  $("intrebareText").textContent = copiaInapoi.intrebare || "";
  $("intrebareCopie").classList.remove("ascuns"); $("copieNu").focus(); });
$("copieNu").addEventListener("click", function(){ $("intrebareCopie").classList.add("ascuns"); });
$("copieDa").addEventListener("click", function(){
  $("intrebareCopie").classList.add("ascuns");
  mesaj("mesajCopie", "Se cere punerea la loc...");
  cerere("/api/asistenta-pune-inapoi","POST", new URLSearchParams()).then(function(d){ mesaj("mesajCopie", d.message, !d.result); if(d.result){ setTimeout(function(){ location.reload(); }, 20000); } }).catch(function(){ mesaj("mesajCopie", nuRaspunde(), true); }); });
citeste(); setInterval(citeste, 3000);
</script>
</body>
</html>
"""


# textele de ecran ale paginii (sablonul si scriptul), ca liste scrise direct: le citesc xgettext si probele
TEXTE_PAGINA = {
	"html": (
		N_("Asistență de la distanță"),
		N_("Se citește starea..."),
		N_("Funcția nu e disponibilă pe această imagine."),
		N_("Echipa HD Satelit vede ecranele, setările și imaginea canalului și poate controla receptorul prin toate "
			"meniurile. Echipa vede inclusiv numele de utilizator, parolele, PIN-urile și cheile. Poți opri oricând."),
		N_("Accept <a href=\"#\" id=\"termeni\">termenii și condițiile</a>"),
		N_("Cât timp"),
		N_("Schimbă durata"),
		N_("Start"),
		N_("Setările de internet"),
		N_("Oprește"),
		N_("Oprești asistența?"),
		N_("Da, opresc"),
		N_("Echipa se uită imediat ce poate. Poți închide pagina, asistența rămâne pornită."),
		N_("Te anunțăm când intrăm. Poți folosi receptorul între timp."),
		N_("Dacă nu intrăm imediat, las-o pornită măcar 30 de minute: poate ajutăm pe altcineva chiar acum."),
		N_("Jurnalul asistenței"),
		N_("Termenii și condițiile"),
		N_("Închide"),
		N_("Copia se face singură când intră echipa, înainte de orice schimbare. Butonul pune la loc canalele, "
			"setările și rețeaua de atunci; interfața repornește."),
		N_("Pune înapoi cum era"),
		N_("Nu"),
		N_("Da, pune la loc"),
		N_("Ce am găsit și ce am făcut"),
		N_("Mulțumim că ne-ai lăsat să te ajutăm."),
		N_("Întrebare de la HD Satelit"),
		N_("Scrie răspunsul"),
		N_("Trimite"),
	),
	"js": (
		N_("Receptorul nu răspunde."),
		N_("Jurnalul e gol."),
		N_("Fără bifă, asistența nu pornește."),
		N_("Se pornește..."),
		N_("Se oprește..."),
		N_("Se cere punerea la loc..."),
		N_("Răspunsul a plecat la echipă."),
	),
}


def _traducePagina(sablon, fel="pagina"):
	try:
		from .traducere_pagini import traduce
	except ImportError:
		return sablon.replace("__DRUM_MENIU__", _drumMeniu())
	return traduce(sablon, TEXTE_PAGINA, fel).replace("__DRUM_MENIU__", _drumMeniu())
