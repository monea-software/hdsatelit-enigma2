# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# afisaj_web.py: „Afișajul din față” in interfata web (HdsWebControl), perechea ecranului de pe televizor.
#
# Pe televizor: Meniu > Setări > Sistem și dispozitive > Afișajul din față (Screens/HdsAfisaj.py). Aici:
# aceleasi grupe si alegeri (Components/HdsAfisajDate.py), fiecare cu desenul exact al celor 4 cifre pentru valoarea de
# acum (sau exemplul), cautarea, lista de rotire (ordinea, durata, eticheta scurta), mesajele scurte, asteptarea,
# setarile (viteza derularii, luminozitatea ziua si noaptea, textul tau, ora din alt oras), ceasurile afisajului
# (minutarul, cronometrul) si modul „Personaj” (setarile lui si expresiile, fiecare animata pe pagina si trecuta o data
# pe afisajul adevarat la clic), din aceeasi logica (Components/HdsAfisaj.py, Components/HdsAfisajPersonaj.py).
# Desenele le face pagina din masti (acelasi desen ca HdsAfisajLitere.svg), deci receptorul trimite numai numere.
# Schimbarile se fac intai pe pagina; afisajul adevarat le arata pe loc (previzualizarea, nesalvata), iar „Salvează”
# le scrie o singura data (o scriere in setari, nu cate una pe clic).
#
# Rute (poarta comuna a HdsJsonResource; ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF):
#   GET  /api/afisaj                     starea afisajului, setarile, lista de rotire, grupele (cu cate bifate)
#   GET  /api/afisaj?grupa=<id>          in plus alegerile grupei, cu desenele valorii de acum (sau ale exemplului)
#   GET  /api/afisaj?catalog=1           in plus toate alegerile (id, nume, grupa, desenul exemplului): cautarea
#   GET  /api/afisaj?orase=1             in plus fusurile pentru „Ora din alt oraș” (cateva sute; pagina le cere o data)
#   POST /api/afisaj-seteaza?lista=..&evenimente=..&asteptare=..&viteza=..&luminozitate=..&luminozitate_noapte=..
#        &noapte_de_la=..&noapte_pana_la=..&text=..&personaj=..&personaj_ritm=..&personaj_noaptea=..
#                                                          salveaza si aplica (oricare dintre ele)
#   POST /api/afisaj-seteaza?personaj_arata=<expresia>  expresia personajului o data pe afisaj, acum, fara salvare
#   POST /api/afisaj-seteaza?previzualizare=1&lista=..&asteptare=..   afisajul arata lista, fara salvare
#   POST /api/afisaj-seteaza?previzualizare=0                         afisajul revine la lista salvata
#   POST /api/afisaj-seteaza?functionare=ora|canal|stins              forma veche (scripturi)
#   POST /api/afisaj-seteaza?minutar=<minute>  |  ?cronometru=porneste|opreste|zero
#        ceasurile afisajului, pe loc, fara salvare (nu sunt setari)
#   GET  /afisaj                         pagina
#
# Etichetele paginii, notele si mesajele din script trec prin _t() (ETICHETE, NOTA, TEXTE_JS si, pentru personaj,
# HdsAfisajPersonaj.ETICHETE_WEB in locul __P_<CHEIE>__), iar lang e limba receptorului; numele alegerilor, ale
# expresiilor si mesajele API vin deja traduse din HdsAfisaj, HdsAfisajDate si HdsAfisajPersonaj.
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2; o grupa inseamna cel mult cateva zeci de citiri scurte
# (valorile din memorie, tunerul tinut minte 0,5 s); catalogul foloseste numai exemplele si se tine minte pe limba.
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau modulele lor (A, D).

LEGATURA = '<a href="/afisaj">Afișajul din față</a>'
MAX_LISTA_TEXT = 2000
MAX_TEXT = 120
MAX_VALOARE = 40
MAX_ARGUMENTE = 16
# previzualizarea din pagina tine atat fara o cerere noua a paginii (pagina o reinnoieste la 10 s cat are schimbari
# nesalvate): o pagina inchisa fara „Salvează” sau „Renunță” nu lasa afisajul pe lista nesalvata
TERMEN_PREVIZUALIZARE_S = 120


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textul se traduce la afisare cu _t()."""
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
	from Components import HdsAfisaj
	return HdsAfisaj


def _d(D=None):
	if D is not None:
		return D
	from Components import HdsAfisajDate
	return HdsAfisajDate


def _p():
	from Components import HdsAfisajPersonaj
	return HdsAfisajPersonaj


# ---------------------------------------------------------------- datele

_VALORI = {}


def _valori(A):
	"""Cititorul valorilor de acum (acelasi ca ecranul de pe televizor), cu sesiunea afisajului pornit. Se pastreaza
	intre cereri, ca procentul procesorului si viteza retelei sa aiba citirea de dinainte."""
	afisaj = getattr(A, "_afisaj", None)
	sesiune = afisaj.session if afisaj is not None else None
	v = _VALORI.get("v")
	if v is None or v.session is not sesiune or not isinstance(v, A.Valori):
		v = A.Valori(sesiune)
		_VALORI["v"] = v
	else:
		v.reimprospateaza()
	return v


def _desen(desen):
	return {"cadre": [list(c) for c in desen.cadre], "durate": list(desen.durate), "bucla": bool(desen.bucla)}


def _nota(D, d):
	"""Nota alegerii: nota datei si cat costa citirea (aceleasi ca pe televizor)."""
	cost = getattr(D, "notaCost", None)
	parti = [_t(d.nota) if d.nota else "", cost(d) if cost is not None else ""]
	return " ".join(p for p in parti if p)


def _descriere(D, d, f):
	"""Campurile de text ale unei alegeri: numele, formatul (numai cand data are mai multe), eticheta scurta care poate
	trece inainte (numai cand formatul nu o scrie deja) si nota."""
	are = getattr(D, "areEticheta", None)
	scurt = D.SCURT.get(d.id, "") if (are(d, f) if are is not None else D.SCURT.get(d.id)) else ""
	return {"id": D.idAlegere(d, f), "text": D.textAlegere(d, f), "data": _t(d.eticheta),
		"format": _t(f.eticheta) if len(d.formate) > 1 else "", "grupa": d.grupa, "scurt": scurt, "nota": _nota(D, d)}


def _intrare(A, D, v, i, viteza):
	desen, exemplu = v.desen(i.d, i.f, viteza)
	rez = _descriere(D, i.d, i.f)
	rez.update({"durata": i.durata, "durata_text": A.textDurata(i.durata), "eticheta": bool(i.eticheta),
		"desen": _desen(desen) if desen is not None else None, "exemplu": exemplu})
	return rez


def _alegeri(A, D, alegeri, viteza, v=None):
	"""Randurile unei grupe (sau ale cautarii) cu desenul valorii de acum, altfel al exemplului."""
	rez = []
	for d, f in alegeri:
		if v is None:
			desen, exemplu = D.desenExemplu(d, f, viteza), True
		else:
			desen, exemplu = v.desen(d, f, viteza)
		x = _descriere(D, d, f)
		x.update({"desen": _desen(desen) if desen is not None else None, "exemplu": exemplu})
		rez.append(x)
	return rez


_CATALOG = {}


def _limba():
	"""Limba receptorului pentru lang (de ex. „de” din „de_DE”); „ro” fara limba citibila (probele de pe PC)."""
	try:
		from Components.Language import language
		cod = (language.getLanguage() or "").split("_")[0].lower()
	except Exception:
		cod = ""
	if 2 <= len(cod) <= 3 and cod.isalpha():
		return cod
	return "ro"


def catalog(A=None, D=None):
	"""Toate alegerile cu desenul exemplului (cautarea din pagina); tinut minte pe limba si pe viteza."""
	A, D = _a(A), _d(D)
	viteza = _viteza(A)
	cheie = (_limba(), viteza)
	if cheie not in _CATALOG:
		_CATALOG.clear()
		_CATALOG[cheie] = _alegeri(A, D, D.toateAlegerile(), viteza)
	return _CATALOG[cheie]


def _viteza(A):
	try:
		return int(A.stare().get("viteza") or 300)
	except (TypeError, ValueError):
		return 300


def stare(A=None, D=None, grupa=None, cu_catalog=False, cu_orase=False):
	"""Pentru GET /api/afisaj. Fusurile orasului (cateva sute) numai cu cu_orase: pagina le cere o singura data."""
	A, D = _a(A), _d(D)
	s = A.stare()
	rez = {"result": True}
	rez.update(s)
	viteza = _viteza(A)
	v = _valori(A)
	lista = A.citesteLista(s["lista"])
	evenimente = A.citesteEvenimente(s["evenimente"])
	rez["lista_intrari"] = [_intrare(A, D, v, i, viteza) for i in lista]
	rez["alegeri_setari"] = {
		"asteptare": [list(a) for a in A.alegeriAsteptare()],
		"viteza": [list(a) for a in A.alegeriViteza()],
		"luminozitate": [list(a) for a in A.alegeriLuminozitate()],
		"luminozitate_noapte": [list(a) for a in A.alegeriLuminozitateNoapte()],
		"noapte_de_la": [list(a) for a in A.alegeriNoapteDeLa()],
		"noapte_pana_la": [list(a) for a in A.alegeriNoaptePanaLa()],
		"minutar": [list(a) for a in A.alegeriMinutar()],
	}
	P = _p()
	for cheie in P.CHEI:
		rez["alegeri_setari"][cheie] = [list(a) for a in P.ALEGERI[cheie]()]
	rez["personaj_expresii"] = P.pentruWeb()
	if cu_orase:
		rez["alegeri_setari"]["oras"] = [[v, D.orasDinNume(t) if v else t] for v, t in A.alegeriOras()]
	rez["durate"] = [[dur, A.textDurata(dur)] for dur in A.DURATE]
	ids_lista = set(i.id() for i in lista)
	id_asteptare = A.ALEGERE_ASTEPTARE.get(s["asteptare"])
	grupe = []
	for g, nume in D.GRUPE:
		bifate = 0
		for d, f in D.alegeriGrupa(g):
			id_ = D.idAlegere(d, f)
			if (g == D.GRUPA_EVENIMENTE and d.id in evenimente and evenimente[d.id].id == f.id) or id_ in ids_lista \
					or id_ == id_asteptare:
				bifate += 1
		grupe.append([g, _t(nume), bifate])
	rez["grupe"] = grupe
	rez["grupa_evenimente"] = D.GRUPA_EVENIMENTE
	rez["grupa_asteptare"] = D.GRUPA_ASTEPTARE
	rez["asteptare_alegeri"] = dict(A.ALEGERE_ASTEPTARE)
	rez["max_lista"] = A.MAX_LISTA
	if grupa and grupa in [g for g, _n in D.GRUPE]:
		rez["grupa"] = grupa
		rez["alegeri"] = _alegeri(A, D, D.alegeriGrupa(grupa), viteza, v)
	if cu_catalog:
		rez["catalog"] = catalog(A, D)
	return rez


MESAJ_FARA_ALEGERE = N_("Lipsește ce se schimbă: lista, evenimente, asteptare, viteza, luminozitate, "
	"luminozitate_noapte, noapte_de_la, noapte_pana_la, text, oras, minutar, cronometru sau previzualizare.")
MESAJ_PREVIZUALIZARE = N_("Afișajul arată lista de pe pagină. Nu e salvată încă.")
MESAJ_FARA_PREVIZUALIZARE = N_("Afișajul arată din nou lista salvată.")
CHEI_SETEAZA = ("lista", "evenimente", "asteptare", "viteza", "luminozitate", "luminozitate_noapte", "noapte_de_la",
	"noapte_pana_la", "text", "functionare", "oras", "personaj", "personaj_ritm", "personaj_noaptea")


def seteaza(argumente, A=None, D=None):
	"""POST /api/afisaj-seteaza: o valoare straina nu schimba nimic."""
	A, D = _a(A), _d(D)
	if "personaj_arata" in argumente:
		# o expresie a personajului, o data pe afisaj, acum (previzualizarea, fara salvare)
		reusit, mesaj = A.arataExpresia(argumente.get("personaj_arata"))
		rez = stare(A, D)
		rez.update({"result": bool(reusit), "message": mesaj})
		return rez
	if "minutar" in argumente or "cronometru" in argumente:
		# ceasurile afisajului: pe loc, fara salvare
		if "minutar" in argumente:
			reusit, mesaj = A.minutar(argumente.get("minutar"))
		else:
			reusit, mesaj = A.cronometru(argumente.get("cronometru"))
		rez = stare(A, D)
		rez.update({"result": bool(reusit), "message": mesaj})
		return rez
	if "previzualizare" in argumente:
		if argumente.get("previzualizare") == "0":
			A.previzualizeaza(None)
			mesaj = _t(MESAJ_FARA_PREVIZUALIZARE)
			reusit = True
		else:
			lista = argumente.get("lista", "")
			intrari, eroare = A.valideazaLista(lista)
			asteptare = argumente.get("asteptare")
			if asteptare is not None and asteptare not in A.ASTEPTARE:
				intrari, eroare = None, _t("Alegerea pentru așteptare nu există.")
			if eroare:
				reusit, mesaj = False, eroare
			else:
				A.previzualizeaza(A.scrieLista(intrari), asteptare, TERMEN_PREVIZUALIZARE_S)
				reusit, mesaj = True, _t(MESAJ_PREVIZUALIZARE)
		rez = stare(A, D)
		rez.update({"result": reusit, "message": mesaj})
		return rez
	valori = dict((k, argumente[k]) for k in CHEI_SETEAZA if k in argumente)
	if not valori:
		rez = stare(A, D)
		rez.update({"result": False, "message": _t(MESAJ_FARA_ALEGERE)})
		return rez
	reusit, mesaj = A.seteaza(**valori)
	rez = stare(A, D)
	rez.update({"result": bool(reusit), "message": mesaj})
	return rez


def faraLegaturaDacaLipseste(pagina, A=None):
	"""Panoul si /ecrane: legatura spre /afisaj ramane numai pe un receptor cu afisaj in fata; aceeasi hotarare ca
	intrarea din menu.xml (requires="HdsAfisaj")."""
	try:
		if _a(A).disponibil():
			return pagina
	except Exception as eroare:
		print("[afisaj_web] disponibil: %s" % eroare)
	# dupa adresa, nu dupa text: pagina e tradusa in limba receptorului
	import re
	legatura = r'<a href="%s">[^<]*</a>' % re.escape(re.search(r'href="([^"]+)"', LEGATURA).group(1))
	return re.sub(legatura, "", re.sub("  " + legatura + "\n", "", pagina))


def argumente(request):
	"""Argumentele cererii ca text: {cheie: text}, fara token; lista are voie mai lunga, restul e scurt."""
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:MAX_ARGUMENTE]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie == "token" or not cheie or len(cheie) > 24:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		maxim = {"lista": MAX_LISTA_TEXT, "evenimente": MAX_LISTA_TEXT, "text": MAX_TEXT}.get(cheie, MAX_VALOARE)
		rez[cheie] = u"%s" % v
		rez[cheie] = rez[cheie][:maxim] if cheie == "text" else rez[cheie][:maxim].strip()
	return rez


def rute(baza, resource, A=None, D=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py."""

	class StareResource(baza):
		"""GET /api/afisaj: numai citire."""

		def render_GET(self, request):
			try:
				a = argumente(request)
				return self._raspunde(request, stare(A, D, a.get("grupa"), a.get("catalog") == "1", a.get("orase") == "1"))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class SeteazaResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, seteaza(argumente(request), A, D))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class PaginaResource(resource.Resource):
		"""GET /afisaj: pagina „Afișajul din față”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"afisaj": StareResource(),
		b"afisaj-seteaza": SeteazaResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /paznic si /procesor."""
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
	return pagina_text(P._STIL_COMUN, config_pagina).encode("utf-8", "replace")


def _drumMeniu(id_intrare):
	"""Drumul de pe televizor spre ecran (meniu_web.drumHtml); modulul incarcat singur, fara pachet (probele de pe
	PC), nu are meniul, deci ramane „Meniu”."""
	try:
		from .meniu_web import drumHtml
	except ImportError:
		return "Meniu"
	return drumHtml(id_intrare)


# etichetele fixe ale paginii: __T_<CHEIE>__ in PAGINA, traduse si scapate pentru HTML (aceleasi texte ca pe
# televizor, deci aceleasi traduceri)
ETICHETE = {
	"TITLU": N_("Afișajul din față"),
	"INCARCARE": N_("Se citește starea..."),
	"GRUPE": N_("Grupe"),
	"CAUTA": N_("Caută"),
	"CAUTA_LOC": N_("Caută o alegere"),
	"CAUTA_EXEMPLU": N_("De exemplu: temperatura, canal, volumul."),
	"ROTIRE": N_("Lista de rotire"),
	"SETARI": N_("Setări"),
	"ASTEPTARE": N_("În așteptare"),
	"VITEZA": N_("Viteza derulării"),
	"LUMINA_ZI": N_("Luminozitatea, ziua"),
	"LUMINA_NOAPTE": N_("Luminozitatea, noaptea"),
	"NOAPTE_DE_LA": N_("Noaptea începe"),
	"NOAPTE_PANA_LA": N_("Noaptea se termină"),
	"TEXT": N_("Textul tău"),
	"ORAS": N_("Ora din alt oraș"),
	"CEASURI": N_("Ceasurile afișajului"),
	"MINUTAR": N_("Minutarul"),
	"CRONOMETRU": N_("Cronometrul"),
	"PORNESTE": N_("Pornește"),
	"OPRESTE": N_("Oprește"),
	"ZERO": N_("De la zero"),
	"CEASURI_NOTA": N_("Pornesc pe loc, fără Salvează. Se văd pe afișaj când sunt în lista de rotire (grupa „Ora și data”)."),
	"SALVEAZA": N_("Salvează"),
	"RENUNTA": N_("Renunță la schimbări"),
}

# nota de sub alegeri: %s e drumul din meniul televizorului (HTML facut de meniu_web.drumHtml)
NOTA = N_("Afișajul din fața receptorului are 4 cifre. Alegerile bifate trec pe rând, fiecare cât ai ales; un text "
	"lung se derulează. Mesajele scurte trec în fața listei câteva secunde. Aceleași alegeri sunt pe televizor, în %s.")

# mesajele scriptului, traduse pe receptor si date paginii ca JSON (TXT); starea afisajului are aceleasi texte ca
# ecranul de pe televizor
TEXTE_JS = {
	"neasteptat": N_("Receptorul a răspuns neașteptat (HTTP %s)."),
	"necitit": N_("Receptorul nu a putut citi starea."),
	"nu_raspunde_retea": N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
	"nu_raspunde": N_("Receptorul nu răspunde."),
	"se_salveaza": N_("Se salvează..."),
	"fara_afisaj": N_("Receptorul acesta nu are afișaj în față."),
	"nepornit": N_("Afișajul pornește după ce receptorul termină pornirea."),
	"nu_primeste": N_("Afișajul nu primește textul. Repornește receptorul."),
	"arata": N_("Acum afișajul arată: %s"),
	"arata_asteptare": N_("În așteptare, afișajul arată: %s"),
	"stins": N_("Acum afișajul este stins."),
	"exemplu": N_("Acum nu are ce arăta; desenul e un exemplu."),
	"gol": N_("Lista e goală: afișajul arată ora."),
	"nimic": N_("Nimic de arătat aici."),
	"gasite": N_("Găsite pentru „%s”: %d"),
	"sus": N_("Mută mai sus"),
	"jos": N_("Mută mai jos"),
	"scoate": N_("Scoate din listă"),
	"eticheta": N_("eticheta"),
	"nesalvat": N_("Ai schimbări nesalvate. Afișajul le arată deja; Salvează le păstrează."),
	"max_lista": N_("Lista de rotire poate avea cel mult %d alegeri."),
	"evenimente": N_("Mesajele scurte trec în fața listei câteva secunde, când se întâmplă ceva."),
	"asteptare": N_("În așteptare: alegi una"),
	"acum": N_("Acum pe afișaj"),
	"text_gol": N_("Îl scrii în Setări, la „Textul tău”."),
	"durata": N_("Durata: %s"),
}


def _json(obiect):
	"""JSON pentru interiorul lui <script>: fara „</” (nu poate inchide scriptul)."""
	import json
	return json.dumps(obiect, ensure_ascii=False).replace("</", "<\\/")


def pagina_text(stil, config_pagina):
	import html
	text = _traducePagina(PAGINA)
	for cheie, eticheta in ETICHETE.items():
		text = text.replace("__T_%s__" % cheie, html.escape(_t(eticheta), quote=True))
	for cheie, eticheta in _p().ETICHETE_WEB.items():
		text = text.replace("__P_%s__" % cheie, html.escape(_t(eticheta), quote=True))
	nota = html.escape(_t(NOTA), quote=False)
	nota = nota.replace("%s", _drumMeniu("hds_afisaj"), 1) if "%s" in nota else nota
	return (text.replace("__LIMBA__", _limba()).replace("__NOTA__", nota)
		.replace("__TEXTE_JS__", _json(dict((k, _t(v)) for k, v in TEXTE_JS.items())))
		.replace("__STIL_COMUN__", stil).replace("__CONFIG__", config_pagina))


PAGINA = """<!DOCTYPE html>
<html lang="__LIMBA__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__T_TITLU__</title>
<style>__STIL_COMUN__
  main{max-width:1180px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  h2{font-size:.9rem;margin:0 0 10px;color:var(--text-slab);text-transform:uppercase;letter-spacing:.04em;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:14px;margin:0 0 12px;}
  .sus{display:grid;grid-template-columns:auto 1fr;gap:16px;align-items:center;}
  .mare svg{display:block;max-width:100%;height:auto;}
  .ales-nume{font-size:1.1rem;font-weight:700;margin:0 0 4px;}
  .ales-detaliu{margin:0 0 4px;}
  .ales-nota,.nota{color:var(--text-slab);font-size:.85rem;line-height:1.45;margin:0;}
  .coloane{display:grid;grid-template-columns:minmax(180px,.8fr) minmax(260px,1.6fr) minmax(240px,1.1fr);gap:12px;}
  .lista{display:flex;flex-direction:column;gap:4px;max-height:560px;overflow:auto;}
  .rand{display:flex;align-items:center;gap:10px;min-height:44px;padding:6px 8px;border-radius:8px;border:1px solid transparent;
    background:#171b22;color:var(--text);font:inherit;text-align:left;cursor:pointer;width:100%;}
  .rand:hover,.rand:focus{border-color:#3a4a66;outline:none;}
  .rand.ales{border-color:#6c8cff;background:#1d2433;}
  .rand .nume{flex:1;min-width:0;}
  .rand .mic{color:var(--text-slab);font-size:.82rem;}
  .rand .numar{color:#4fd18b;font-weight:700;}
  .casuta{width:20px;height:20px;border-radius:4px;background:#2a3350;flex:0 0 auto;position:relative;}
  .casuta.bifat::after{content:"";position:absolute;inset:5px;border-radius:2px;background:#4fd18b;}
  .rand svg{flex:0 0 auto;}
  .cauta{display:flex;gap:6px;margin:0 0 4px;}
  .cauta-exemplu{margin:0 0 8px;}
  .linii{flex:1;min-width:0;display:flex;flex-direction:column;}
  .linii .mic{color:var(--text-slab);font-size:.82rem;white-space:nowrap;overflow:hidden;}
  .lista-nota{margin:0 0 6px;}
  .cauta input,.setare select,.setare input,.intrare select{min-height:40px;padding:6px 8px;border-radius:8px;
    border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;min-width:0;}
  .cauta input{flex:1;}
  .intrare{display:grid;grid-template-columns:1fr auto;gap:6px;padding:8px;border-radius:8px;background:#171b22;}
  .intrare .rand-sus{display:flex;align-items:center;gap:8px;grid-column:1/-1;}
  .intrare .unelte{display:flex;flex-wrap:wrap;gap:6px;grid-column:1/-1;align-items:center;}
  .intrare label.mic{display:inline-flex;align-items:center;gap:6px;min-height:36px;padding:0 6px;cursor:pointer;}
  .intrare input[type=checkbox]{width:22px;height:22px;margin:0;}
  button.mic{min-height:36px;padding:4px 10px;border-radius:8px;border:1px solid var(--bordura);background:#232a35;color:var(--text);font:inherit;cursor:pointer;}
  button.mic:disabled{opacity:.4;cursor:default;}
  .setari{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px;}
  .setare{display:flex;flex-direction:column;gap:4px;}
  .setare label{font-size:.9rem;color:var(--text-slab);}
  .butoane{display:flex;flex-wrap:wrap;gap:10px;align-items:center;}
  .butoane button{min-height:44px;padding:8px 16px;border-radius:8px;border:0;font:inherit;cursor:pointer;color:#fff;}
  .salveaza{background:var(--verde);}
  .renunta{background:#4a5160;}
  .mesaj{margin:8px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  h2.sub{margin:14px 0 8px;}
  .expresii{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:6px;}
  .personaj-mare{margin:0 0 10px;}
  .ascuns{display:none;}
  .coloane>.card{min-width:0;}
  @media (max-width:900px){ .coloane{grid-template-columns:minmax(0,1fr);} .lista{max-height:none;} .sus{grid-template-columns:minmax(0,1fr);} }
</style>
</head>
<body>
<main>
<h1>__T_TITLU__</h1>
<p class="mesaj" id="incarcare">__T_INCARCARE__</p>
<div id="continut" class="ascuns">
  <section class="card sus">
    <div class="mare" id="mare" aria-hidden="true"></div>
    <div>
      <p class="ales-nume" id="alesNume"></p>
      <p class="ales-detaliu" id="alesDetaliu" role="status"></p>
      <p class="ales-nota" id="alesNota"></p>
    </div>
  </section>
  <div class="coloane">
    <section class="card">
      <h2>__T_GRUPE__</h2>
      <div class="cauta"><input id="cauta" type="search" placeholder="__T_CAUTA_LOC__" aria-label="__T_CAUTA_LOC__" aria-describedby="cautaExemplu"></div>
      <p class="nota cauta-exemplu" id="cautaExemplu">__T_CAUTA_EXEMPLU__</p>
      <div class="lista" id="grupe"></div>
    </section>
    <section class="card">
      <h2 id="titluAlegeri"></h2>
      <div class="lista" id="alegeri"></div>
    </section>
    <section class="card">
      <h2 id="titluRotire">__T_ROTIRE__</h2>
      <div class="lista" id="rotire"></div>
    </section>
  </div>
  <section class="card">
    <h2>__T_SETARI__</h2>
    <div class="setari">
      <div class="setare"><label for="s_asteptare">__T_ASTEPTARE__</label><select id="s_asteptare" data-cheie="asteptare"></select></div>
      <div class="setare"><label for="s_viteza">__T_VITEZA__</label><select id="s_viteza" data-cheie="viteza"></select></div>
      <div class="setare"><label for="s_luminozitate">__T_LUMINA_ZI__</label><select id="s_luminozitate" data-cheie="luminozitate"></select></div>
      <div class="setare"><label for="s_luminozitate_noapte">__T_LUMINA_NOAPTE__</label><select id="s_luminozitate_noapte" data-cheie="luminozitate_noapte"></select></div>
      <div class="setare"><label for="s_noapte_de_la">__T_NOAPTE_DE_LA__</label><select id="s_noapte_de_la" data-cheie="noapte_de_la"></select></div>
      <div class="setare"><label for="s_noapte_pana_la">__T_NOAPTE_PANA_LA__</label><select id="s_noapte_pana_la" data-cheie="noapte_pana_la"></select></div>
      <div class="setare"><label for="s_text">__T_TEXT__</label><input id="s_text" maxlength="60" data-cheie="text"></div>
      <div class="setare"><label for="s_oras">__T_ORAS__</label><select id="s_oras" data-cheie="oras"></select></div>
    </div>
  </section>
  <section class="card">
    <h2>__T_CEASURI__</h2>
    <div class="setari">
      <div class="setare"><label for="c_minutar">__T_MINUTAR__</label><select id="c_minutar"></select>
        <p class="nota" id="c_minutar_stare" role="status"></p></div>
      <div class="setare"><label>__T_CRONOMETRU__</label>
        <div class="butoane"><button class="mic" type="button" data-ce="porneste">__T_PORNESTE__</button>
        <button class="mic" type="button" data-ce="opreste">__T_OPRESTE__</button>
        <button class="mic" type="button" data-ce="zero">__T_ZERO__</button></div>
        <p class="nota" id="c_cronometru_stare" role="status"></p></div>
    </div>
    <p class="nota">__T_CEASURI_NOTA__</p>
  </section>
  <section class="card" id="personaj">
    <h2>__P_TITLU__</h2>
    <p class="nota">__P_NOTA__</p>
    <div class="setari">
      <div class="setare"><label for="s_personaj">__P_PORNIT__</label><select id="s_personaj" data-cheie="personaj"></select></div>
      <div class="setare"><label for="s_personaj_ritm">__P_RITM__</label><select id="s_personaj_ritm" data-cheie="personaj_ritm"></select></div>
      <div class="setare"><label for="s_personaj_noaptea">__P_NOAPTEA__</label><select id="s_personaj_noaptea" data-cheie="personaj_noaptea"></select>
        <p class="nota">__P_NOTA_NOAPTEA__</p></div>
    </div>
    <h2 class="sub">__P_EXPRESII__</h2>
    <div class="mare personaj-mare" id="personajMare" aria-hidden="true"></div>
    <div class="expresii" id="expresii"></div>
  </section>
  <section class="card">
    <div class="butoane">
      <button class="salveaza" id="salveaza" type="button">__T_SALVEAZA__</button>
      <button class="renunta" id="renunta" type="button">__T_RENUNTA__</button>
    </div>
    <p class="mesaj" id="mesaj" role="status"></p>
    <p class="nota">__NOTA__</p>
  </section>
</div>
</main>
<script>
var CFG = __CONFIG__;
var TXT = __TEXTE_JS__;
var S = null, GRUPA = null, CATALOG = null, ALES = null, CADRU = 0, CEAS = null;
var LUCRU = null;   // schimbarile de pe pagina: {lista:[{id,durata,eticheta}], evenimente:{data:format}, setari:{}}
var CUNOSCUTE = {}; // id alegere -> alegerea (din grupele citite, din cautare si din lista salvata)
var ORASE = null;   // fusurile pentru „Ora din alt oraș”, cerute o singura data (orase=1)
var PREV = false;   // afisajul arata o lista nesalvata trimisa de pagina
function $(id){ return document.getElementById(id); }
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
function optiuniCerere(metoda, date){
  var optiuni = {method: metoda || "GET", cache: "no-store", credentials: "same-origin", headers: {}};
  if(CFG.csrf){ optiuni.headers["X-HDS-CSRF"] = CFG.csrf; }
  if(date){
    optiuni.headers["Content-Type"] = "application/x-www-form-urlencoded";
    optiuni.body = date.toString();
  }
  return optiuni;
}
function cerere(cale, metoda, date){
  return fetch(adresa(cale), optiuniCerere(metoda, date)).then(function(r){
    if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("browser deconectat"); }
    return r.json().catch(function(){ return {result: false, message: TXT.neasteptat.replace("%s", r.status)}; });
  });
}
function mesaj(text, eroare){ var m = $("mesaj"); m.textContent = text || ""; m.classList.toggle("eroare", !!eroare); }
function el(tip, clasa, text){ var e = document.createElement(tip); if(clasa){ e.className = clasa; } if(text !== undefined){ e.textContent = text; } return e; }
function tine(lista){ (lista || []).forEach(function(a){ if(a && a.id){ CUNOSCUTE[a.id] = a; } }); }
// ---------------------------------------------------------------- desenul (ca HdsAfisajLitere.svg)
var GROS = 10, LAT = 56, INALT = 100, PAS = 74;
function oriz(x0, x1, y){ var t = GROS / 2; return [[x0, y], [x0 + t, y - t], [x1 - t, y - t], [x1, y], [x1 - t, y + t], [x0 + t, y + t]]; }
function vert(x, y0, y1){ var t = GROS / 2; return [[x, y0], [x + t, y0 + t], [x + t, y1 - t], [x, y1], [x - t, y1 - t], [x - t, y0 + t]]; }
var G = (function(){ var s = GROS / 2, st = s, dr = LAT - s, sus = s, mij = INALT / 2, jos = INALT - s, g = 1.5;
  return [[1, oriz(st + g, dr - g, sus)], [2, vert(dr, sus + g, mij - g)], [4, vert(dr, mij + g, jos - g)], [8, oriz(st + g, dr - g, jos)],
    [16, vert(st, mij + g, jos - g)], [32, vert(st, sus + g, mij - g)], [64, oriz(st + g, dr - g, mij)]]; })();
function svg(masti, inaltime, exemplu){
  var n = Math.max(1, masti.length), m = 12, lat = m * 2 + PAS * (n - 1) + LAT + 12, inalt = m * 2 + INALT;
  var aprins = exemplu ? "#9a2f29" : "#ff3b30", stins = "#2a1414";
  var p = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + lat + ' ' + inalt + '" width="' + Math.round(inaltime * lat / inalt) + '" height="' + inaltime + '"><rect width="100%" height="100%" rx="8" fill="#0b0b0b"/>'];
  for(var i = 0; i < masti.length; i++){
    var x0 = m + i * PAS, y0 = m;
    for(var k = 0; k < G.length; k++){
      var pts = G[k][1].map(function(q){ return (x0 + q[0]).toFixed(1) + "," + (y0 + q[1]).toFixed(1); }).join(" ");
      p.push('<polygon points="' + pts + '" fill="' + ((masti[i] & G[k][0]) ? aprins : stins) + '"/>');
    }
    p.push('<circle cx="' + (x0 + LAT + 7) + '" cy="' + (y0 + INALT - 5) + '" r="5" fill="' + ((masti[i] & 128) ? aprins : stins) + '"/>');
  }
  p.push("</svg>");
  return p.join("");
}
function mic(desen, exemplu){ var s = el("span"); s.innerHTML = svg(desen ? desen.cadre[0] : [0, 0, 0, 0], 30, exemplu); return s.firstChild; }
// ---------------------------------------------------------------- desenul mare, animat
function arataMare(){
  if(CEAS){ clearTimeout(CEAS); CEAS = null; }
  var d = ALES && ALES.desen, masti = S ? S.masti : [0, 0, 0, 0], ex = false;
  if(d){ masti = d.cadre[CADRU % d.cadre.length]; ex = !!ALES.exemplu; }
  $("mare").innerHTML = svg(masti, 110, ex);
  // expresia aleasa a personajului si langa lista ei, cadru cu cadru
  var pm = $("personajMare"); if(pm){ pm.innerHTML = (ALES && ALES.grupa === "personaj") ? svg(masti, 80, false) : ""; }
  if(d && d.cadre.length > 1){
    var ms = d.durate[CADRU % d.cadre.length] || 1000;
    CEAS = setTimeout(function(){ CADRU = (CADRU + 1) % d.cadre.length; arataMare(); }, Math.max(100, ms));
  }
}
function alege(a, detaliu, nota){
  ALES = a; CADRU = 0;
  $("alesNume").textContent = a ? (a.data || a.text) : TXT.acum;
  $("alesDetaliu").textContent = detaliu || (a && a.format ? a.format : "");
  $("alesNota").textContent = nota || (a ? ((a.exemplu && a.grupa !== S.grupa_evenimente && a.grupa !== S.grupa_asteptare ? TXT.exemplu + " " : "") + (a.nota || "")) : "");
  arataMare();
}
// ---------------------------------------------------------------- lucrul de pe pagina
function lucruDinStare(s){
  var ev = {}; (s.evenimente || "").split(",").forEach(function(p){ if(p){ var q = p.split(":"); ev[q[0]] = q[1]; } });
  return {lista: (s.lista_intrari || []).map(function(i){ return {id: i.id, durata: i.durata, eticheta: i.eticheta}; }),
    evenimente: ev, setari: {asteptare: s.asteptare, viteza: s.viteza, luminozitate: s.luminozitate,
    luminozitate_noapte: s.luminozitate_noapte, noapte_de_la: s.noapte_de_la, noapte_pana_la: s.noapte_pana_la, text: s.text_tau || "",
    oras: s.oras || "", personaj: s.personaj, personaj_ritm: s.personaj_ritm, personaj_noaptea: s.personaj_noaptea}};
}
function textLista(){ return LUCRU.lista.map(function(i){ return i.id + (i.durata ? "@" + i.durata : "") + (i.eticheta ? "+e" : ""); }).join(","); }
function textEvenimente(){ return Object.keys(LUCRU.evenimente).sort().map(function(k){ return k + ":" + LUCRU.evenimente[k]; }).join(","); }
function schimbat(){ return S && (textLista() !== S.lista || textEvenimente() !== (S.evenimente || "").split(",").filter(Boolean).sort().join(",") ||
  ["asteptare", "viteza", "luminozitate", "luminozitate_noapte", "noapte_de_la", "noapte_pana_la", "personaj", "personaj_ritm",
    "personaj_noaptea"].some(function(k){ return LUCRU.setari[k] !== S[k]; }) ||
  (LUCRU.setari.oras || "") !== (S.oras || "") ||
  LUCRU.setari.text !== (S.text_tau || "")); }
function vizibilSchimbat(){ return S && (textLista() !== S.lista || LUCRU.setari.asteptare !== S.asteptare); }
function bifat(a){
  var data = a.id.split(":")[0];
  if(a.grupa === S.grupa_evenimente){ return LUCRU.evenimente[data] === a.id.split(":")[1]; }
  if(a.grupa === S.grupa_asteptare){ return S.asteptare_alegeri[LUCRU.setari.asteptare] === a.id; }
  return LUCRU.lista.some(function(i){ return i.id === a.id; });
}
function comuta(a){
  var data = a.id.split(":")[0], fmt = a.id.split(":")[1];
  if(a.grupa === S.grupa_evenimente){ if(bifat(a)){ delete LUCRU.evenimente[data]; } else { LUCRU.evenimente[data] = fmt; } }
  else if(a.grupa === S.grupa_asteptare){ Object.keys(S.asteptare_alegeri).forEach(function(k){ if(S.asteptare_alegeri[k] === a.id){ LUCRU.setari.asteptare = k; } }); $("s_asteptare").value = LUCRU.setari.asteptare; }
  else if(bifat(a)){ LUCRU.lista = LUCRU.lista.filter(function(i){ return i.id !== a.id; }); }
  else if(data === "texte.liber" && !(LUCRU.setari.text || "").trim()){ mesaj(TXT.text_gol, true); $("s_text").focus(); return; }
  else if(LUCRU.lista.length >= S.max_lista){ mesaj(TXT.max_lista.replace("%d", S.max_lista), true); return; }
  else { LUCRU.lista.push({id: a.id, durata: 0, eticheta: false}); }
  dupaSchimbare();
}
function gasesteAlegere(id){ return CUNOSCUTE[id] || null; }
function grupaDin(id){ return id.split(".")[0]; }
// ---------------------------------------------------------------- desenul coloanelor
function pastreaza(fa){
  // redesenarea nu muta focusul si derularea: acelasi buton (data-cheie) primeste din nou focusul
  var act = document.activeElement, cheie = act && act.dataset ? act.dataset.cheie : null, sus = {};
  ["grupe", "alegeri", "rotire"].forEach(function(n){ sus[n] = $(n).scrollTop; });
  fa();
  ["grupe", "alegeri", "rotire"].forEach(function(n){ $(n).scrollTop = sus[n]; });
  if(cheie){
    var nou = null;
    document.querySelectorAll("[data-cheie]").forEach(function(e){ if(!nou && e.dataset.cheie === cheie){ nou = e; } });
    if(nou && nou !== document.activeElement){ try { nou.focus({preventScroll: true}); } catch(e){ nou.focus(); } }
  }
}
function deseneazaGrupe(){
  var c = $("grupe"); c.textContent = "";
  (S.grupe || []).forEach(function(g){
    var b = el("button", "rand" + (GRUPA && GRUPA.id === g[0] && !cautat() ? " ales" : "")); b.type = "button"; b.dataset.cheie = "g:" + g[0];
    var n = numarBifate(g[0]);
    b.appendChild(el("span", "nume", g[1]));
    if(n){ b.appendChild(el("span", "numar", String(n))); }
    b.addEventListener("click", function(){ $("cauta").value = ""; citesteGrupa(g[0]); });
    c.appendChild(b);
  });
}
function numarBifate(g){
  if(g === S.grupa_evenimente){ return Object.keys(LUCRU.evenimente).length; }
  if(g === S.grupa_asteptare){ return 1; }
  return LUCRU.lista.filter(function(i){ return grupaDin(i.id) === g; }).length;
}
function cautat(){ return ($("cauta").value || "").trim(); }
function fara(t){ return (t || "").normalize("NFD").replace(/[\\u0300-\\u036f]/g, "").toLowerCase(); }
function linii(a){
  var d = el("span", "linii");
  d.appendChild(el("span", "nume", a.data || a.text));
  // randul mic care nu incape se deruleaza (hds-derulant, cadru_web.py), numai la randul ales, cu mouse-ul sau focusul
  if(a.format){ d.appendChild(el("span", "mic hds-derulant", a.format)); }
  return d;
}
function deseneazaAlegeri(){
  var c = $("alegeri"); c.textContent = ""; var lista, q = cautat();
  if(q && CATALOG){
    var cuvinte = fara(q).split(/\\s+/).filter(Boolean), numeGrupe = {};
    (S.grupe || []).forEach(function(g){ numeGrupe[g[0]] = g[1]; });
    lista = CATALOG.filter(function(a){ var t = fara(a.text + " " + (numeGrupe[a.grupa] || "")); return cuvinte.every(function(w){ return t.indexOf(w) !== -1; }); });
    $("titluAlegeri").textContent = TXT.gasite.replace("%s", q).replace("%d", lista.length);
  } else {
    lista = (GRUPA && GRUPA.alegeri) || [];
    var nume = ""; (S.grupe || []).forEach(function(g){ if(GRUPA && g[0] === GRUPA.id){ nume = g[1]; } });
    $("titluAlegeri").textContent = nume;
    var nota = GRUPA && GRUPA.id === S.grupa_evenimente ? TXT.evenimente : (GRUPA && GRUPA.id === S.grupa_asteptare ? TXT.asteptare : "");
    if(nota){ c.appendChild(el("p", "nota lista-nota", nota)); }
  }
  if(!lista.length){ c.appendChild(el("p", "nota", TXT.nimic)); return; }
  lista.forEach(function(a){
    var b = el("button", "rand hds-derulant-rand" + (ALES && ALES.id === a.id ? " ales" : "")); b.type = "button"; b.dataset.cheie = "a:" + a.id;
    var casuta = el("span", "casuta" + (bifat(a) ? " bifat" : "")); b.appendChild(casuta);
    b.appendChild(linii(a));
    b.appendChild(mic(a.desen, a.exemplu));
    b.addEventListener("click", function(){ comuta(a); alege(a); pastreaza(deseneazaAlegeri); });
    b.addEventListener("focus", function(){ alege(a); });
    b.addEventListener("mouseenter", function(){ alege(a); });
    c.appendChild(b);
  });
}
function deseneazaRotirea(){
  var c = $("rotire"); c.textContent = "";
  $("titluRotire").textContent = document.querySelector("#titluRotire").dataset.titlu + " (" + LUCRU.lista.length + ")";
  if(!LUCRU.lista.length){ c.appendChild(el("p", "nota", TXT.gol)); return; }
  LUCRU.lista.forEach(function(i, k){
    var a = gasesteAlegere(i.id) || {id: i.id, text: i.id, grupa: grupaDin(i.id)};
    var d = el("div", "intrare hds-derulant-rand");
    var sus = el("div", "rand-sus");
    var l = el("span", "linii");
    l.appendChild(el("span", "nume", (k + 1) + ". " + (a.data || a.text)));
    var jos = [a.format || "", i.eticheta && a.scurt ? a.scurt : "", TXT.durata.replace("%s", textDurata(i.durata))].filter(Boolean).join(" \\u00b7 ");
    l.appendChild(el("span", "mic hds-derulant", jos));
    sus.appendChild(l);
    sus.appendChild(mic(a.desen, a.exemplu));
    sus.addEventListener("click", function(){ alege(a); });
    d.appendChild(sus);
    var u = el("div", "unelte");
    var s = document.createElement("select"); s.setAttribute("aria-label", TXT.durata.replace("%s", "")); s.dataset.cheie = "r:" + k + ":durata";
    (S.durate || []).forEach(function(p){ var o = el("option", "", p[1]); o.value = p[0]; s.appendChild(o); });
    s.value = String(i.durata); s.addEventListener("change", function(){ i.durata = parseInt(s.value, 10) || 0; dupaSchimbare(); });
    u.appendChild(s);
    if(a.scurt){ var lb = el("label", "mic"); var cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = !!i.eticheta; cb.dataset.cheie = "r:" + k + ":eticheta";
      cb.addEventListener("change", function(){ i.eticheta = cb.checked; dupaSchimbare(); }); lb.appendChild(cb); lb.appendChild(document.createTextNode(" " + TXT.eticheta + " " + a.scurt)); u.appendChild(lb); }
    [["\\u2191", TXT.sus, -1, "sus"], ["\\u2193", TXT.jos, 1, "jos"]].forEach(function(p){
      var b = el("button", "mic", p[0]); b.type = "button"; b.title = p[1]; b.setAttribute("aria-label", p[1]); b.dataset.cheie = "r:" + k + ":" + p[3];
      b.disabled = (p[2] < 0 && k === 0) || (p[2] > 0 && k === LUCRU.lista.length - 1);
      b.addEventListener("click", function(){ var j = k + p[2]; var t = LUCRU.lista[k]; LUCRU.lista[k] = LUCRU.lista[j]; LUCRU.lista[j] = t; dupaSchimbare(); });
      u.appendChild(b);
    });
    var x = el("button", "mic", TXT.scoate); x.type = "button"; x.dataset.cheie = "r:" + k + ":scoate";
    x.addEventListener("click", function(){ LUCRU.lista.splice(k, 1); dupaSchimbare(); });
    u.appendChild(x);
    d.appendChild(u);
    c.appendChild(d);
  });
}
function textDurata(d){ var t = ""; (S.durate || []).forEach(function(p){ if(String(p[0]) === String(d)){ t = p[1]; } }); return t; }
function deseneazaSetari(){
  document.querySelectorAll(".setare select[data-cheie]").forEach(function(s){
    var cheie = s.dataset.cheie; if(document.activeElement === s){ return; }
    var alegeri = cheie === "oras" ? (ORASE || []) : (S.alegeri_setari[cheie] || []);
    if(cheie !== "oras" || s.options.length !== alegeri.length){
      s.textContent = "";
      alegeri.forEach(function(p){ var o = el("option", "", p[1]); o.value = p[0]; s.appendChild(o); });
    }
    s.value = LUCRU.setari[cheie];
  });
  if(document.activeElement !== $("s_text")){ $("s_text").value = LUCRU.setari.text || ""; }
  deseneazaCeasuri();
}
function deseneazaCeasuri(){
  var s = $("c_minutar");
  if(document.activeElement !== s){
    s.textContent = "";
    (S.alegeri_setari.minutar || []).forEach(function(p){ var o = el("option", "", p[1]); o.value = p[0]; s.appendChild(o); });
    s.value = "0";
  }
  $("c_minutar_stare").textContent = S.minutar_text || "";
  $("c_cronometru_stare").textContent = S.cronometru_text || "";
}
function ceas(cheie, valoare){
  var q = new URLSearchParams(); q.set(cheie, valoare);
  cerere("/api/afisaj-seteaza", "POST", q).then(function(d){
    mesaj(d.message, !d.result);
    if(d.result){ S.minutar_text = d.minutar_text; S.cronometru_text = d.cronometru_text; $("c_minutar").blur(); deseneazaCeasuri(); }
  }).catch(function(){ mesaj(TXT.nu_raspunde, true); });
}
// ---------------------------------------------------------------- personajul: expresiile
function expresie(x){ return {id: "personaj:" + x.id, data: x.nume, text: x.nume, format: x.cand, desen: x.desen, exemplu: false, nota: "", grupa: "personaj"}; }
function deseneazaPersonaj(){
  var c = $("expresii"); c.textContent = "";
  (S.personaj_expresii || []).forEach(function(x){
    var a = expresie(x);
    var b = el("button", "rand hds-derulant-rand" + (ALES && ALES.id === a.id ? " ales" : "")); b.type = "button"; b.dataset.cheie = "p:" + x.id;
    var s = el("span"); s.innerHTML = svg(x.desen.cadre[x.fata] || x.desen.cadre[0], 30, false); b.appendChild(s.firstChild);
    var l = el("span", "linii"); l.appendChild(el("span", "nume", x.nume)); l.appendChild(el("span", "mic hds-derulant", x.cand)); b.appendChild(l);
    // clic: desenul mare o arata cadru cu cadru, iar afisajul adevarat o data
    b.addEventListener("click", function(){ alege(a); pastreaza(deseneazaPersonaj); arataPeAfisaj(x.id); });
    b.addEventListener("focus", function(){ alege(a); });
    b.addEventListener("mouseenter", function(){ alege(a); });
    c.appendChild(b);
  });
}
function arataPeAfisaj(id){
  var q = new URLSearchParams(); q.set("personaj_arata", id);
  cerere("/api/afisaj-seteaza", "POST", q).then(function(d){ mesaj(d.message, !d.result); }).catch(function(){ mesaj(TXT.nu_raspunde, true); });
}
function deseneazaTot(){ pastreaza(function(){ deseneazaGrupe(); deseneazaAlegeri(); deseneazaRotirea(); deseneazaSetari(); deseneazaPersonaj(); }); }
// ---------------------------------------------------------------- previzualizarea pe afisajul adevarat
function trimitePrevizualizarea(){
  var q = new URLSearchParams(); q.set("previzualizare", "1"); q.set("lista", textLista()); q.set("asteptare", LUCRU.setari.asteptare);
  PREV = true;
  return cerere("/api/afisaj-seteaza", "POST", q).then(function(d){ if(!d.result){ mesaj(d.message, true); } else { S.masti = d.masti; S.text = d.text; } }).catch(function(){});
}
function opresteSubPrevizualizarea(){
  var q = new URLSearchParams(); q.set("previzualizare", "0");
  PREV = false;
  return cerere("/api/afisaj-seteaza", "POST", q).catch(function(){});
}
function dupaSchimbare(){
  pastreaza(function(){ deseneazaGrupe(); deseneazaAlegeri(); deseneazaRotirea(); });
  mesaj(schimbat() ? TXT.nesalvat : "");
  if(vizibilSchimbat()){ trimitePrevizualizarea(); } else if(PREV){ opresteSubPrevizualizarea(); }
}
// ---------------------------------------------------------------- citirea
function stareAcum(d){
  var acum;
  if(!d.disponibil){ acum = TXT.fara_afisaj; }
  else if(!d.pornit){ acum = TXT.nepornit; }
  else if(!d.scris){ acum = TXT.nu_primeste; }
  else if(d.text){ acum = (d.in_asteptare ? TXT.arata_asteptare : TXT.arata).replace("%s", d.text); }
  else { acum = TXT.stins; }
  return acum;
}
function primeste(d){
  var prima = !S;
  var tituri = document.querySelector("#titluRotire"); if(!tituri.dataset.titlu){ tituri.dataset.titlu = tituri.textContent; }
  tine(d.lista_intrari);
  tine(d.catalog);
  tine(d.alegeri);
  if(d.alegeri_setari && d.alegeri_setari.oras){ ORASE = d.alegeri_setari.oras; }
  S = d;
  if(prima || !schimbat()){ LUCRU = lucruDinStare(d); }
  if(d.alegeri){ GRUPA = {id: d.grupa, alegeri: d.alegeri}; }
  if(d.catalog){ CATALOG = d.catalog; }
  $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
  deseneazaTot();
  if(!ALES){ alege(null, stareAcum(d), ""); }
}
function citesteGrupa(g){
  cerere("/api/afisaj?grupa=" + encodeURIComponent(g)).then(function(d){ if(d.result){ primeste(d); } }).catch(function(){ mesaj(TXT.nu_raspunde, true); });
}
function citeste(){
  var q = []; if(GRUPA){ q.push("grupa=" + encodeURIComponent(GRUPA.id)); } if(!ORASE){ q.push("orase=1"); }
  var cale = "/api/afisaj" + (q.length ? "?" + q.join("&") : "");
  return cerere(cale).then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || TXT.necitit; return; }
    primeste(d);
    if(!ALES){ arataMare(); }
  }).catch(function(){ $("incarcare").textContent = TXT.nu_raspunde_retea; });
}
$("cauta").addEventListener("input", function(){
  if(!CATALOG){ cerere("/api/afisaj?catalog=1").then(function(d){ if(d.result){ tine(d.catalog); if(GRUPA){ tine(GRUPA.alegeri); } CATALOG = d.catalog; pastreaza(function(){ deseneazaAlegeri(); deseneazaGrupe(); }); } }); }
  deseneazaAlegeri(); deseneazaGrupe();
});
document.querySelectorAll(".setare select[data-cheie]").forEach(function(s){ s.addEventListener("change", function(){ LUCRU.setari[s.dataset.cheie] = s.value; dupaSchimbare(); }); });
$("c_minutar").addEventListener("change", function(){ ceas("minutar", $("c_minutar").value); });
document.querySelectorAll("[data-ce]").forEach(function(b){ b.addEventListener("click", function(){ ceas("cronometru", b.dataset.ce); }); });
$("s_text").addEventListener("input", function(){ LUCRU.setari.text = $("s_text").value; mesaj(schimbat() ? TXT.nesalvat : ""); });
$("salveaza").addEventListener("click", function(){
  var q = new URLSearchParams(); q.set("lista", textLista()); q.set("evenimente", textEvenimente());
  ["asteptare", "viteza", "luminozitate", "luminozitate_noapte", "noapte_de_la", "noapte_pana_la", "text", "oras", "personaj",
    "personaj_ritm", "personaj_noaptea"].forEach(function(k){ q.set(k, LUCRU.setari[k] || ""); });
  mesaj(TXT.se_salveaza);
  cerere("/api/afisaj-seteaza", "POST", q).then(function(d){
    mesaj(d.message, !d.result || (d.pornit && !d.scris));
    if(d.result){ PREV = false; S = null; primeste(d); }
  }).catch(function(){ mesaj(TXT.nu_raspunde, true); });
});
$("renunta").addEventListener("click", function(){
  var q = new URLSearchParams(); q.set("previzualizare", "0");
  PREV = false;
  cerere("/api/afisaj-seteaza", "POST", q).then(function(d){ S = null; ALES = null; primeste(d); mesaj(d.message); }).catch(function(){ mesaj(TXT.nu_raspunde, true); });
});
// pagina inchisa sau parasita cu o previzualizare trimisa: afisajul revine la lista salvata (fetch cu keepalive, ca sa
// plece si cand pagina se inchide, cu antetul CSRF cerut de poarta); receptorul o opreste oricum singur, la termen
window.addEventListener("pagehide", function(){
  if(!PREV){ return; }
  var q = new URLSearchParams(); q.set("previzualizare", "0");
  var o = optiuniCerere("POST", q); o.keepalive = true;
  try { fetch(adresa("/api/afisaj-seteaza"), o); } catch(e){}
  PREV = false;
});
document.addEventListener("visibilitychange", function(){ if(!document.hidden && LUCRU && vizibilSchimbat()){ trimitePrevizualizarea(); } });
citeste().then(function(){ if(S && S.grupe && S.grupe.length){ citesteGrupa(S.grupe[0][0]); } });
setInterval(function(){
  if(document.hidden){ return; }
  citeste();
  if(PREV && vizibilSchimbat()){ trimitePrevizualizarea(); }   // reinnoieste termenul previzualizarii
}, 10000);
</script>
</body>
</html>
"""


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
