# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# acces_ssh_web.py: „Acces SSH” in interfata web (HdsWebControl), perechea ecranului de pe televizor
# (Screens/HdsAccesSsh.py, Setari > Retea & Conexiuni > Acces SSH). Aceleasi date, aceleasi texte si aceleasi comenzi,
# din acelasi modul, Components/HdsAccesSsh.py: parola de administrator (arata, ascunde, fa una noua), cheile SSH
# (adauga din text lipit sau de pe stick, sterge), „Fără parolă în rețeaua locală”, starile periculoase (banda de sus)
# si, ca optiune, textul brut al fisierelor serverului SSH.
#
# Cine are voie: poarta comuna a HdsJsonResource (reteaua locala, apoi ?token= sau cookie-ul browserului; ce schimba
# ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului) lasa sa treaca si browserele „libere” (in
# reteaua locala, cu codul oprit, orice aparat din casa intra fara cod) si cheia pentru scripturi. Aici, parola, textul
# brut si orice schimbare cer in plus un browser conectat CU CODUL de pe televizor (nivel „asociat”): altfel oricine din
# casa ar citi parola lui root sau si-ar pune cheia, adica ar intra ca root fara sa fi vazut televizorul. Browserele
# libere si cheia pentru scripturi vad numai starea; pagina arata unui browser liber conectarea cu codul, pe loc.
# Tot de aceea, cat ecranul „Acces SSH” e deschis pe televizor, telecomanda si captura de ecran ale panoului
# (plugin.py, RemoteControlResource si ScreenshotResource) cer si ele nivelul „asociat”: refuzEcranDeschis().
#   GET  /api/acces-ssh                          starea, fara parola si fara hash (oricine trece de poarta)
#   POST /api/acces-ssh-parola                   textul parolei, cat timp nu a fost ascunsa
#   POST /api/acces-ssh-ascunde                  „Am notat parola”: textul clar se sterge, parola ramane
#   POST /api/acces-ssh-parola-noua?confirmat=1  o parola noua
#   POST /api/acces-ssh-adauga   (corp: cheie=)  cheile publice lipite (una sau mai multe, si blocuri SSH2); acelasi
#                                                drum si pentru "Adaugă cheia acestui calculator": pagina citeste
#                                                fisierul .pub ales de pe calculator (input type=file, FileReader) si
#                                                trimite textul lui ca pe o cheie lipita (aceleasi verificari)
#   POST /api/acces-ssh-stick                    cheile din dosarul hdsatelit/ssh de pe stick
#   POST /api/acces-ssh-sterge?amprenta=..&confirmat=1   sterge o cheie
#   POST /api/acces-ssh-fara-parola?pornit=0|1  (pornit=1 cere si confirmat=1)
#   GET  /api/acces-ssh-brut?pagina=<n>          textul brut al unui fisier (fara /etc/shadow si fara parola)
#   GET  /acces-ssh                              pagina
# Parola, textul brut si toate cele cu POST: numai nivelul „asociat” (altfel 403 cu „trebuie_cod”).
# Comenzile pornesc o lucrare pe firul modulului (una deodata, comuna cu televizorul) si raspund pe loc; pagina citeste
# rezultatul din GET /api/acces-ssh („lucrare”) si il arata langa butoanele casetei din care a pornit. Parola se cere
# din nou cand se schimba „parola_semn” (inode si ora fisierului parolei, nimic din parola) sau cand se termina o
# lucrare „parola-noua”, niciodata cat merge o lucrare.
# Etichetele paginii si mesajele din script trec prin _t() (ETICHETE, TEXTE_JS), iar lang e limba receptorului.
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2 si citesc numai cateva fisiere mici; ce scrie sau porneste un
# program merge pe firul lucrarilor. Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau modulul lor.

# textul lipit: cateva chei publice (o cheie RSA de 4096 de biti are ~750 de semne); corpul cererii are oricum cel mult
# 64 KB (_CerereHds din plugin.py)
MAX_TEXT_WEB = 16384
MAX_AMPRENTA = 64


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textul se traduce la afisare cu _t()."""
	return text


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _a(A=None):
	if A is not None:
		return A
	from Components import HdsAccesSsh
	return HdsAccesSsh


def _arg(request, nume, maxim=200):
	valori = (getattr(request, "args", None) or {}).get(nume.encode("ascii"))
	if not valori:
		return ""
	v = valori[0]
	if isinstance(v, bytes):
		v = v.decode("utf-8", "replace")
	return str(v)[:maxim]


def _cuJeton(request):
	"""Cererea vine cu ?token= (scripturi): poarta a trecut-o pe jeton, nu pe cookie-ul browserului asociat."""
	return b"token" in (getattr(request, "args", None) or {})


def _sesiunePlugin(request):
	from . import plugin as P
	return P._sesiuneDinCerere(request)


def nivel(request, sesiune_cerere=None):
	"""„jeton” (?token=), „asociat” (cookie-ul unui browser conectat cu codul de pe televizor) sau „liber” (browser din
	reteaua locala intrat fara cod)."""
	if _cuJeton(request):
		return "jeton"
	_secret, browser = (sesiune_cerere or _sesiunePlugin)(request)
	if browser is not None and not browser.get("liber"):
		return "asociat"
	return "liber"


NEASOCIAT = {"result": False, "trebuie_cod": True,
	"message": N_("Parola și cheile se văd și se schimbă numai dintr-un browser conectat cu codul de pe televizor.")}

ECRAN_DESCHIS = N_("Cât ecranul „Acces SSH” e deschis pe televizor, telecomanda și captura de ecran merg numai dintr-un "
	"browser conectat cu codul de pe televizor.")


def refuzEcranDeschis(request, A=None, sesiune_cerere=None):
	"""Pentru telecomanda si captura de ecran din plugin.py: raspunsul de refuz (403) daca ecranul „Acces SSH” e deschis
	pe televizor si cererea nu vine dintr-un browser conectat cu codul; altfel None. Cu ecranul deschis, o tasta sau o
	captura data unui browser liber ori cheii pentru scripturi ar ocoli poarta paginii (parola mare pe ecran, OK pe
	„Fără parolă în rețeaua locală”)."""
	try:
		A = _a(A)
		if not A.ecranDeschis():
			return None
	except Exception:
		return None
	if nivel(request, sesiune_cerere) == "asociat":
		return None
	return {"result": False, "trebuie_cod": True, "message": _t(ECRAN_DESCHIS)}


def _lucrare(nume):
	"""Caseta paginii in care se arata o lucrare si rezultatul ei."""
	return {"parola-noua": "parola", "ascunde-parola": "parola", "adauga-chei": "chei", "stick": "chei",
		"sterge-cheie": "chei", "fara-parola": "fara"}.get(nume or "", "")


def stare(A=None, nivel_cerere="asociat"):
	"""Starea pentru pagina: ce arata ecranul de pe televizor, cu textele lui, fara parola."""
	A = _a(A)
	s = A.stare()
	lucrare = s["lucrare"]
	ultima = dict(lucrare["ultima"], caseta=_lucrare(lucrare["ultima"]["nume"])) if lucrare["ultima"] else None
	return {
		"result": True,
		"nivel": nivel_cerere,
		"asociat": nivel_cerere == "asociat",
		"fel_parola": s["fel_parola"],
		"parola_de_vazut": bool(s["parola_de_vazut"] and s["fel_parola"] == "pusa"),
		"parola_semn": s["parola_semn"],
		"program": s["program"],
		"text_parola": A.textParola(s),
		"text_parola_scurt": A.textParolaScurt(s),
		"alarme": A.textAlarme(s),
		"text_chei": A.textChei(s),
		"chei": [{"text": A.textCheie(c), "nume": A.numeCheie(c), "amprenta": c["amprenta"], "tip": c["nume_tip"],
			"biti": c["biti"], "comentariu": c["comentariu"], "optiuni": c["optiuni"]} for c in s["chei"]],
		"randuri_necunoscute": s["randuri_necunoscute"],
		"fara_parola": s["fara_parola"],
		"text_fara_parola": A.textFaraParola(s["fara_parola"]),
		"fara_dovada": s["fara_dovada"],
		"lucreaza": lucrare["lucreaza"],
		"lucreaza_caseta": _lucrare(lucrare["lucreaza"]),
		"text_lucreaza": A.textLucrare(lucrare["lucreaza"]) if lucrare["lucreaza"] else "",
		"ultima": ultima,
		"pagini": [{"titlu": t, "cale": c} for t, c, _x in A.paginiBrute(cu_text=False)],
	}


def _pornit(A, numar, mesaj):
	if numar is None:
		return {"result": False, "message": _t("Așteaptă să se termine ce ai pornit înainte (pe televizor sau aici).")}
	return {"result": True, "lucrare": numar, "message": mesaj}


def parola(request, A=None):
	A = _a(A)
	s = A.stare()
	text = A.parolaDeAratat() if (s["parola_de_vazut"] and s["fel_parola"] == "pusa") else ""
	if not text:
		return {"result": False, "message": _t("Parola nu se mai arată. Dacă ai uitat-o, fă una nouă.")}, 404
	return {"result": True, "parola": text, "parola_semn": s["parola_semn"]}, 200


def brut(request, A=None):
	"""Textul brut al unui fisier din paginiBrute() (fara /etc/shadow si fara fisierul parolei)."""
	A = _a(A)
	pagini = A.paginiBrute()
	try:
		i = int(_arg(request, "pagina", 4) or "0")
	except ValueError:
		i = 0
	i = max(0, min(len(pagini) - 1, i))
	titlu, cale, text = pagini[i]
	return {"result": True, "pagina": i, "pagini": len(pagini), "titlu": titlu, "cale": cale, "text": text}


def ascunde(request, A=None):
	A = _a(A)
	return _pornit(A, A.pornesteAscunde(), A.textLucrare(A.LUCRARE_ASCUNDE))


def parolaNoua(request, A=None):
	A = _a(A)
	if _arg(request, "confirmat") != "1":
		return {"result": False, "message": _t("Confirmă parola nouă: cea de acum nu mai merge după aceea.")}
	return _pornit(A, A.pornesteParolaNoua(), A.textLucrare(A.LUCRARE_PAROLA_NOUA))


def adauga(request, A=None):
	A = _a(A)
	text = _arg(request, "cheie", MAX_TEXT_WEB + 1)
	if len(text) > MAX_TEXT_WEB:
		return {"result": False, "message": _t("Textul e prea lung pentru câteva chei publice.")}
	if not text.strip():
		return {"result": False, "message": _t("Nu ai dat nicio cheie.")}
	return _pornit(A, A.pornesteAdaugaChei(text), A.textLucrare(A.LUCRARE_CHEI))


def stick(request, A=None):
	A = _a(A)
	return _pornit(A, A.pornesteStick(), A.textLucrare(A.LUCRARE_STICK))


def sterge(request, A=None):
	A = _a(A)
	amprenta = _arg(request, "amprenta", MAX_AMPRENTA)
	if not amprenta.startswith("SHA256:"):
		return {"result": False, "message": _t("Lipsește amprenta cheii.")}
	if _arg(request, "confirmat") != "1":
		return {"result": False, "message": _t("Confirmă ștergerea cheii.")}
	return _pornit(A, A.pornesteSterge(amprenta), A.textLucrare(A.LUCRARE_STERGE))


def faraParola(request, A=None):
	A = _a(A)
	pornit = _arg(request, "pornit")
	if pornit not in ("0", "1"):
		return {"result": False, "message": _t("Alege pornit sau oprit.")}
	if pornit == "1" and _arg(request, "confirmat") != "1":
		return {"result": False, "message": _t("Confirmă: oricine din rețeaua ta de acasă va intra pe receptor fără parolă.")}
	return _pornit(A, A.pornesteFaraParola(pornit == "1"), A.textLucrare(A.LUCRARE_FARA_PAROLA))


def rute(baza, resource, A=None, sesiune_cerere=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py;
	`sesiune_cerere(request)` da (secret, browser) ca _sesiuneDinCerere din plugin.py (probele de pe PC dau una a lor)."""

	def neasociat(request):
		if nivel(request, sesiune_cerere) == "asociat":
			return None
		return dict(NEASOCIAT, message=_t(NEASOCIAT["message"]))

	class StareResource(baza):
		"""GET /api/acces-ssh: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(A, nivel(request, sesiune_cerere)))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class ParolaResource(baza):
		"""POST /api/acces-ssh-parola: textul parolei, numai browserului asociat (poarta cere POST + CSRF)."""
		schimbaCeva = True

		def render_POST(self, request):
			refuz = neasociat(request)
			if refuz is not None:
				return self._raspunde(request, refuz, 403)
			try:
				corp, cod = parola(request, A)
				return self._raspunde(request, corp, cod)
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class BrutResource(baza):
		"""GET /api/acces-ssh-brut: numai citire, numai browserului asociat (cheile si jurnalul nu se dau oricui)."""

		def render_GET(self, request):
			refuz = neasociat(request)
			if refuz is not None:
				return self._raspunde(request, refuz, 403)
			try:
				return self._raspunde(request, brut(request, A))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class _Comanda(baza):
		schimbaCeva = True
		lucru = None

		def render_POST(self, request):
			refuz = neasociat(request)
			if refuz is not None:
				return self._raspunde(request, refuz, 403)
			try:
				return self._raspunde(request, type(self).lucru(request, A))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # poarta cere POST din browser; cu ?token= raspunsul e refuzul

	class AscundeResource(_Comanda):
		lucru = staticmethod(ascunde)

	class ParolaNouaResource(_Comanda):
		lucru = staticmethod(parolaNoua)

	class AdaugaResource(_Comanda):
		lucru = staticmethod(adauga)

	class StickResource(_Comanda):
		lucru = staticmethod(stick)

	class StergeResource(_Comanda):
		lucru = staticmethod(sterge)

	class FaraParolaResource(_Comanda):
		lucru = staticmethod(faraParola)

	class PaginaResource(resource.Resource):
		"""GET /acces-ssh: pagina „Acces SSH”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"acces-ssh": StareResource(),
		b"acces-ssh-parola": ParolaResource(),
		b"acces-ssh-brut": BrutResource(),
		b"acces-ssh-ascunde": AscundeResource(),
		b"acces-ssh-parola-noua": ParolaNouaResource(),
		b"acces-ssh-adauga": AdaugaResource(),
		b"acces-ssh-stick": StickResource(),
		b"acces-ssh-sterge": StergeResource(),
		b"acces-ssh-fara-parola": FaraParolaResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /limbi si /paznic; pagina se da numai browserului asociat (sau cu ?token=)."""
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
	"""Drumul de pe televizor spre ecran (meniu_web.drumHtml); modulul incarcat singur (probele de pe PC) da „Meniu”."""
	try:
		from .meniu_web import drumHtml
	except ImportError:
		return "Meniu"
	return drumHtml(id_intrare)


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


def _json(obiect):
	"""JSON pentru interiorul lui <script>: fara „</” (nu poate inchide scriptul)."""
	import json
	return json.dumps(obiect, ensure_ascii=False).replace("</", "<\\/")


# etichetele fixe ale paginii: __T_<CHEIE>__ in PAGINA, traduse si scapate pentru HTML
ETICHETE = {
	"TITLU": N_("Acces SSH"),
	"INCARCARE": N_("Se citește starea..."),
	"CONECTARE": N_("Conectează browserul cu codul"),
	"CONECTARE_TEXT": N_("Parola și cheile se văd și se schimbă numai dintr-un browser conectat cu codul de pe "
		"televizor. Așa, cine e doar în rețeaua ta de acasă nu le poate afla."),
	"ARATA_COD": N_("Arată codul pe televizor"),
	"COD": N_("Codul de pe televizor"),
	"CONECTEAZA": N_("Conectează"),
	"PAROLA": N_("Parola de administrator (root)"),
	"ASCUNDE": N_("Am notat parola, ascunde-o"),
	"NOUA": N_("Fă o parolă nouă"),
	"CUM": N_("Cum te conectezi"),
	"CUM_TEXT": N_("De pe calculator, în terminal:"),
	"CUM_NOTA": N_("Cu o cheie SSH pusă mai jos, calculatorul intră fără parolă. Fișierele se copiază cu SFTP (de "
		"exemplu WinSCP sau FileZilla), cu aceleași date."),
	"CHEI": N_("Cheile SSH"),
	"LIPESTE": N_("Lipește cheia publică (conținutul fișierului .pub, de exemplu id_ed25519.pub):"),
	"ADAUGA": N_("Adaugă cheia"),
	"ADAUGA_FISIER": N_("Adaugă cheia acestui calculator"),
	"ADAUGA_FISIER_NOTA": N_("Adaugă cheia acestui calculator: alegi fișierul cheii publice de pe calculator (de exemplu "
		"id_ed25519.pub din dosarul .ssh), iar pagina îl adaugă, ca pe o cheie lipită."),
	"STICK": N_("Adaugă cheile de pe stick"),
	"STICK_NOTA": N_("De pe stick: pune dosarul hdsatelit/ssh cu fișierul authorized_keys sau cu cheile .pub, bagă "
		"stickul în receptor, apoi apasă butonul. Nu pune niciodată cheia privată (fișierul fără .pub)."),
	"FARA": N_("Fără parolă în rețeaua locală"),
	"FARA_NOTA": N_("Rămâne oprit dacă nu ai un motiv anume. Pornit, oricine din rețeaua ta de acasă intră pe receptor "
		"fără parolă."),
	"BRUT": N_("Text brut (fișierele serverului SSH)"),
	"BRUT_BUTON": N_("Text brut"),
	"FISIER": N_("Fișierul"),
}

# nota de jos: %s e drumul din meniul televizorului (HTML facut de meniu_web.drumHtml)
NOTA_TV = N_("Aceleași lucruri sunt pe televizor, în %s.")

# mesajele scriptului, traduse pe receptor si date paginii ca JSON (TXT)
TEXTE_JS = {
	"neasteptat": N_("Receptorul a răspuns neașteptat (HTTP %s)."),
	"necitit": N_("Receptorul nu a putut citi starea."),
	"nuRaspundeRetea": N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
	"nuRaspunde": N_("Receptorul nu răspunde."),
	"seTrimite": N_("Se trimite..."),
	"parolaNumaiCod": N_("Parola se vede numai dintr-un browser conectat cu codul de pe televizor."),
	"faParolaNoua": N_("Fă o parolă nouă"),
	"faParola": N_("Fă o parolă"),
	"sterge": N_("Șterge"),
	"cuOptiuni": N_("(cu opțiuni)"),
	"intrebareSterge": N_("Ștergi cheia %s?"),
	"intrebareAscunde": N_("Ai notat parola? După aceea nu se mai arată nici aici, nici pe televizor."),
	"intrebareNoua": N_("Faci o parolă nouă? Cea de acum nu mai merge."),
	"intrebareFara": N_("Pornești intrarea fără parolă? Oricine din rețeaua ta de acasă va intra pe receptor."),
	"porneste": N_("Pornește"),
	"opreste": N_("Oprește"),
	"lipesteIntai": N_("Lipește întâi cheia publică."),
	"cheiePrivata": N_("Ai lipit o cheie privată. Nu a plecat din pagină. Pune cheia publică (fișierul .pub); cheia "
		"privată rămâne numai la tine."),
	"fisierPrivat": N_("Ai ales o cheie privată. Nu a plecat din pagină. Alege cheia publică (fișierul .pub); cheia "
		"privată rămâne numai la tine."),
	"fisierGol": N_("Fișierul ales e gol."),
	"fisierMare": N_("Fișierul ales e prea mare pentru o cheie publică."),
	"fisierNecitit": N_("Fișierul ales nu s-a putut citi."),
	"seCereCodul": N_("Se cere codul..."),
	"codulPeTv": N_("Codul e pe televizor."),
	"scrieCodul": N_("Scrie codul aici, apoi apasă Conectează."),
	"codNecerut": N_("Codul nu s-a putut cere."),
	"codSase": N_("Codul are 6 cifre."),
	"conectat": N_("Conectat."),
	"codGresit": N_("Codul nu a mers."),
	"jetonTitlu": N_("Numai starea"),
	"jetonText": N_("Cu cheia pentru scripturi pagina arată numai starea. Parola și cheile se văd și se schimbă numai "
		"dintr-un browser conectat cu codul de pe televizor."),
	"textBrut": N_("Text brut"),
	"peScurt": N_("Pe scurt"),
}


def pagina_text(stil, config_pagina):
	import html
	text = _traducePagina(PAGINA)
	for cheie, eticheta in ETICHETE.items():
		text = text.replace("__T_%s__" % cheie, html.escape(_t(eticheta), quote=True))
	nota = html.escape(_t(NOTA_TV), quote=False)
	nota = nota.replace("%s", _drumMeniu("hds_acces_ssh"), 1) if "%s" in nota else nota
	return (text.replace("__LIMBA__", _limba()).replace("__NOTA_TV__", nota)
		.replace("__TEXTE_JS__", _json(dict((k, _t(v)) for k, v in TEXTE_JS.items())))
		.replace("__MAX_TEXT__", str(MAX_TEXT_WEB)).replace("__STIL_COMUN__", stil).replace("__CONFIG__", config_pagina))


PAGINA = """<!DOCTYPE html>
<html lang="__LIMBA__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="same-origin">
<title>__T_TITLU__</title>
<style>__STIL_COMUN__
  main{max-width:820px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  h2{font-size:.95rem;margin:0 0 10px;color:var(--text-slab);text-transform:uppercase;letter-spacing:.04em;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .card.alarma{border-color:#c0392b;background:#3a1714;}
  .alarma p{margin:0 0 6px;color:#ffb4a8;font-weight:600;line-height:1.45;}
  .alarma p:last-child{margin:0;}
  .parola{font-family:ui-monospace,Consolas,monospace;font-size:2rem;letter-spacing:.06em;color:#f5b83d;margin:4px 0 8px;word-break:break-all;}
  .parola.scurt{font-family:inherit;font-size:1.4rem;letter-spacing:0;word-break:normal;}
  .text{font-size:.98rem;line-height:1.45;margin:0 0 8px;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .cod{font-family:ui-monospace,Consolas,monospace;background:#0f1216;border:1px solid var(--bordura);border-radius:6px;padding:6px 8px;display:inline-block;}
  .butoane{display:flex;flex-wrap:wrap;gap:10px;margin-top:12px;}
  button{min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  button.verde{background:var(--verde);border-color:var(--verde);color:#fff;}
  button.albastru{background:var(--albastru);border-color:var(--albastru);color:#fff;}
  button.rosu{background:#8f2a1f;border-color:#8f2a1f;color:#fff;}
  button:disabled{opacity:.5;cursor:default;}
  select{min-height:44px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;max-width:100%;}
  input#cod{min-height:44px;width:9em;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:1.1rem ui-monospace,Consolas,monospace;letter-spacing:.1em;}
  textarea{width:100%;box-sizing:border-box;min-height:96px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:.85rem ui-monospace,Consolas,monospace;}
  table{width:100%;border-collapse:collapse;font-size:.95rem;}
  td{padding:8px 6px;border-bottom:1px solid var(--bordura);text-align:left;vertical-align:middle;}
  td.actiune{text-align:right;width:1%;white-space:nowrap;}
  .amprenta{font-family:ui-monospace,Consolas,monospace;font-size:.85rem;word-break:break-all;color:var(--text-slab);margin-top:4px;}
  pre{white-space:pre-wrap;word-break:break-word;background:#0f1216;border:1px solid var(--bordura);border-radius:8px;padding:10px;font:.85rem/1.45 ui-monospace,Consolas,monospace;margin:12px 0 0;max-height:60vh;overflow:auto;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.95rem;min-height:1.3em;}
  .mesaj:empty{min-height:0;margin:0;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
  @media (max-width:560px){
    .parola{font-size:1.6rem;}
    table, tbody, tr, td{display:block;width:auto;}
    tr{border-bottom:1px solid var(--bordura);padding:6px 0;}
    td{border-bottom:0;padding:4px 0;}
    td.actiune{text-align:left;width:auto;}
  }
</style>
</head>
<body>
<main>
<h1>__T_TITLU__</h1>
<p class="mesaj" id="incarcare">__T_INCARCARE__</p>
<div id="continut" class="ascuns">
  <section class="card alarma ascuns" id="alarme" role="alert"></section>
  <section class="card ascuns" id="conectare">
    <h2 id="titluConectare">__T_CONECTARE__</h2>
    <p class="text" id="textConectare">__T_CONECTARE_TEXT__</p>
    <div class="butoane" id="butoaneCod">
      <button type="button" class="albastru" id="arataCod">__T_ARATA_COD__</button>
      <input id="cod" inputmode="numeric" autocomplete="one-time-code" maxlength="8" placeholder="12 34 56" aria-label="__T_COD__">
      <button type="button" class="verde" id="conecteaza">__T_CONECTEAZA__</button>
    </div>
    <p class="mesaj" id="mesajCod"></p>
  </section>
  <section class="card" id="casetaParola">
    <h2>__T_PAROLA__</h2>
    <p class="parola ascuns" id="parola"></p>
    <p class="text" id="textParola"></p>
    <div class="butoane">
      <button type="button" class="verde ascuns" id="ascunde">__T_ASCUNDE__</button>
      <button type="button" id="noua">__T_NOUA__</button>
    </div>
    <div id="locparola"></div>
  </section>
  <section class="card">
    <h2>__T_CUM__</h2>
    <p class="text">__T_CUM_TEXT__ <span class="cod" id="comanda">ssh root@receptor</span></p>
    <p class="nota">__T_CUM_NOTA__</p>
  </section>
  <section class="card">
    <h2>__T_CHEI__</h2>
    <p class="nota" id="numar"></p>
    <table id="tabel"><tbody id="chei"></tbody></table>
    <p class="text" style="margin-top:12px"><label for="cheie">__T_LIPESTE__</label></p>
    <textarea id="cheie" spellcheck="false" autocomplete="off" placeholder="ssh-ed25519 AAAA... nume@calculator"></textarea>
    <div class="butoane">
      <button type="button" class="verde" id="adauga">__T_ADAUGA__</button>
      <button type="button" class="albastru" id="adaugaFisier">__T_ADAUGA_FISIER__</button>
      <button type="button" class="albastru" id="stick">__T_STICK__</button>
    </div>
    <input type="file" id="fisierCheie" class="ascuns" accept=".pub" aria-label="__T_ADAUGA_FISIER__">
    <div id="locchei"></div>
    <p class="nota">__T_ADAUGA_FISIER_NOTA__</p>
    <p class="nota">__T_STICK_NOTA__</p>
  </section>
  <section class="card">
    <h2>__T_FARA__</h2>
    <p class="text" id="textFara"></p>
    <div class="butoane"><button type="button" id="fara"></button></div>
    <div id="locfara"></div>
    <p class="nota">__T_FARA_NOTA__</p>
  </section>
  <section class="card">
    <h2>__T_BRUT__</h2>
    <div class="butoane"><button type="button" id="comutaBrut">__T_BRUT_BUTON__</button><select id="fisier" class="ascuns" aria-label="__T_FISIER__"></select></div>
    <pre id="brut" class="ascuns"></pre>
  </section>
  <p class="mesaj" id="mesaj"></p>
  <p class="nota">__NOTA_TV__</p>
</div>
</main>
<script>
var CFG = __CONFIG__;
// fisierul cheii ales de pe calculator: cel mult cat textul lipit (MAX_TEXT_WEB, acelasi plafon ca pe receptor)
var MAX_FISIER = __MAX_TEXT__;
var TXT = __TEXTE_JS__;
var DATE = null;
var ASTEPT = null;
// parola se cere o data pentru fiecare parola: din nou cand se schimba semnul ei sau cand se termina o parola noua
var PAROLA_CERUTA = false;
var SEMN_PAROLA = null;
var ULTIMA_VAZUTA = null;
var BRUT_VIZIBIL = false;
var VAZUT_LUCRAND = false;
function $(id){ return document.getElementById(id); }
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
function cerere(cale, metoda, date){
  var optiuni = {method: metoda || "GET", cache: "no-store", credentials: "same-origin", headers: {}};
  if(CFG.csrf){ optiuni.headers["X-HDS-CSRF"] = CFG.csrf; }
  if(date){
    optiuni.headers["Content-Type"] = "application/x-www-form-urlencoded";
    optiuni.body = date.toString();
  }
  return fetch(adresa(cale), optiuni).then(function(r){
    if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("browser deconectat"); }
    return r.json().catch(function(){ return {result: false, message: TXT.neasteptat.replace("%s", r.status)}; });
  });
}
// rezultatul unei comenzi se arata langa butoanele casetei din care a pornit (parola, chei, fara)
function mesaj(text, eroare, caseta){
  var m = $("mesaj");
  if(caseta){ var loc = $("loc" + caseta); if(loc){ loc.appendChild(m); } }
  m.textContent = text || "";
  m.classList.toggle("eroare", !!eroare);
  if(text && m.scrollIntoView){ m.scrollIntoView({block: "nearest"}); }
}
function arataParola(d){
  $("textParola").textContent = d.text_parola;
  $("ascunde").classList.toggle("ascuns", !(d.parola_de_vazut && d.asociat));
  $("noua").textContent = d.fel_parola === "pusa" ? TXT.faParolaNoua : TXT.faParola;
  $("noua").classList.toggle("ascuns", !d.program);
  var p = $("parola");
  if(d.parola_semn !== SEMN_PAROLA){ SEMN_PAROLA = d.parola_semn; PAROLA_CERUTA = false; }
  if(!d.parola_de_vazut || d.lucreaza === "parola-noua"){
    // starea in cateva cuvinte, ca pe televizor; cat se face o parola noua, cea veche nu mai ramane pe ecran
    PAROLA_CERUTA = false;
    p.textContent = d.lucreaza === "parola-noua" ? d.text_lucreaza : d.text_parola_scurt;
    p.classList.add("scurt"); p.classList.remove("ascuns");
    return;
  }
  if(!d.asociat){
    p.textContent = ""; p.classList.add("ascuns"); PAROLA_CERUTA = false;
    $("textParola").textContent = TXT.parolaNumaiCod;
    return;
  }
  if(PAROLA_CERUTA || d.lucreaza){ return; }
  PAROLA_CERUTA = true;
  cerere("/api/acces-ssh-parola", "POST", new URLSearchParams()).then(function(r){
    if(r.result){ p.textContent = r.parola; p.classList.remove("scurt"); p.classList.remove("ascuns"); }
    else { PAROLA_CERUTA = false; }
  }).catch(function(){ PAROLA_CERUTA = false; });
}
function arataChei(d, ocupat){
  var n = (d.chei || []).length;
  $("numar").textContent = d.text_chei;
  $("tabel").classList.toggle("ascuns", !n);
  var corp = $("chei"); corp.textContent = "";
  (d.chei || []).forEach(function(k){
    var tr = document.createElement("tr");
    var c = document.createElement("td");
    var nume = document.createElement("div");
    nume.textContent = k.tip + (k.tip === "RSA" ? " " + k.biti : "") + (k.comentariu ? " „" + k.comentariu + "”" : "") + (k.optiuni ? " " + TXT.cuOptiuni : "");
    var a = document.createElement("div"); a.className = "amprenta"; a.textContent = k.amprenta;
    c.appendChild(nume); c.appendChild(a);
    var ac = document.createElement("td"); ac.className = "actiune";
    var b = document.createElement("button"); b.type = "button"; b.className = "rosu"; b.textContent = TXT.sterge;
    b.disabled = ocupat || !d.asociat;
    b.addEventListener("click", function(){
      if(!confirm(TXT.intrebareSterge.replace("%s", k.nume))){ return; }
      trimite("/api/acces-ssh-sterge", {amprenta: k.amprenta, confirmat: "1"}, "chei");
    });
    ac.appendChild(b); tr.appendChild(c); tr.appendChild(ac); corp.appendChild(tr);
  });
}
function arataAlarme(d){
  var z = $("alarme"); z.textContent = "";
  (d.alarme || []).forEach(function(t){ var p = document.createElement("p"); p.textContent = t; z.appendChild(p); });
  z.classList.toggle("ascuns", !(d.alarme || []).length);
}
function arataPagini(d){
  var s = $("fisier");
  if(s.options && s.options.length === (d.pagini || []).length){ return; }
  s.textContent = "";
  (d.pagini || []).forEach(function(pg, i){
    var o = document.createElement("option"); o.value = String(i); o.textContent = pg.titlu + " (" + pg.cale + ")"; s.appendChild(o);
  });
}
function arata(d){
  DATE = d;
  var ocupat = !!d.lucreaza;
  if(d.ultima && d.ultima.id !== ULTIMA_VAZUTA){
    ULTIMA_VAZUTA = d.ultima.id;
    if(d.ultima.nume === "parola-noua" && d.ultima.reusit){ PAROLA_CERUTA = false; }
  }
  arataAlarme(d);
  arataParola(d);
  arataChei(d, ocupat);
  arataPagini(d);
  $("textFara").textContent = d.text_fara_parola;
  $("fara").textContent = d.fara_parola ? TXT.opreste : TXT.porneste;
  $("fara").className = d.fara_parola ? "verde" : "";
  ["ascunde", "noua", "adauga", "adaugaFisier", "stick", "fara"].forEach(function(id){ $(id).disabled = ocupat || !d.asociat; });
  $("comutaBrut").disabled = !d.asociat;
  $("conectare").classList.toggle("ascuns", d.asociat);
  if(d.nivel === "jeton"){
    $("titluConectare").textContent = TXT.jetonTitlu;
    $("textConectare").textContent = TXT.jetonText;
    $("butoaneCod").classList.add("ascuns"); $("mesajCod").classList.add("ascuns");
  }
  // lucrarea in curs (pornita de aici sau de pe televizor), apoi rezultatul ei, langa butoanele casetei ei
  if(ocupat){ mesaj(d.text_lucreaza, false, d.lucreaza_caseta); VAZUT_LUCRAND = true; }
  else if(d.ultima && ((ASTEPT !== null && d.ultima.id >= ASTEPT) || VAZUT_LUCRAND)){
    mesaj(d.ultima.mesaj, !d.ultima.reusit, d.ultima.caseta);
    if(ASTEPT !== null && d.ultima.nume === "adauga-chei" && d.ultima.reusit){ $("cheie").value = ""; }
    ASTEPT = null; VAZUT_LUCRAND = false;
  }
}
function citeste(){
  return cerere("/api/acces-ssh").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || TXT.necitit; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    var h = location.hostname || "receptor";
    $("comanda").textContent = "ssh root@" + (h.indexOf(":") !== -1 ? "[" + h + "]" : h);
    arata(d);
  }).catch(function(){ $("incarcare").textContent = TXT.nuRaspundeRetea; });
}
function trimite(cale, valori, caseta){
  var q = new URLSearchParams();
  Object.keys(valori || {}).forEach(function(k){ q.set(k, valori[k]); });
  mesaj(TXT.seTrimite, false, caseta);
  return cerere(cale, "POST", q).then(function(r){
    mesaj(r.message, !r.result, caseta);
    if(r.result && r.lucrare){ ASTEPT = r.lucrare; citeste(); }
  }).catch(function(){ mesaj(TXT.nuRaspunde, true, caseta); });
}
$("ascunde").addEventListener("click", function(){
  if(!confirm(TXT.intrebareAscunde)){ return; }
  trimite("/api/acces-ssh-ascunde", {}, "parola");
});
$("noua").addEventListener("click", function(){
  if(DATE && DATE.fel_parola === "pusa" && !confirm(TXT.intrebareNoua)){ return; }
  PAROLA_CERUTA = false;
  trimite("/api/acces-ssh-parola-noua", {confirmat: "1"}, "parola");
});
$("adauga").addEventListener("click", function(){
  var t = $("cheie").value;
  if(!t.trim()){ mesaj(TXT.lipesteIntai, true, "chei"); return; }
  // o cheie privata lipita din greseala nu pleaca nicaieri (nici spre receptor) si nu ramane in pagina
  if(/PRIVATE KEY-----|PuTTY-User-Key-File/.test(t)){
    $("cheie").value = "";
    mesaj(TXT.cheiePrivata, true, "chei");
    return;
  }
  trimite("/api/acces-ssh-adauga", {cheie: t}, "chei");
});
// "Adaugă cheia acestui calculator": fisierul .pub ales de pe calculator, citit in pagina si trimis pe acelasi drum
// ca o cheie lipita (/api/acces-ssh-adauga); o cheie privata aleasa din greseala nu pleaca nicaieri
$("adaugaFisier").addEventListener("click", function(){ $("fisierCheie").value = ""; $("fisierCheie").click(); });
$("fisierCheie").addEventListener("change", function(){
  var f = this.files && this.files[0];
  if(!f){ return; }
  if(f.size > MAX_FISIER){ mesaj(TXT.fisierMare, true, "chei"); return; }
  var r = new FileReader();
  r.onload = function(){
    var t = String(r.result || "");
    $("fisierCheie").value = "";
    if(!t.trim()){ mesaj(TXT.fisierGol, true, "chei"); return; }
    if(/PRIVATE KEY-----|PuTTY-User-Key-File/.test(t)){ mesaj(TXT.fisierPrivat, true, "chei"); return; }
    trimite("/api/acces-ssh-adauga", {cheie: t}, "chei");
  };
  r.onerror = function(){ $("fisierCheie").value = ""; mesaj(TXT.fisierNecitit, true, "chei"); };
  r.readAsText(f);
});
$("stick").addEventListener("click", function(){ trimite("/api/acces-ssh-stick", {}, "chei"); });
// textul brut: numai din browserul conectat cu codul, fisierul ales in lista
function citesteBrut(){
  cerere("/api/acces-ssh-brut?pagina=" + encodeURIComponent($("fisier").value || "0")).then(function(d){
    $("brut").textContent = d.result ? d.cale + "\\n\\n" + d.text : (d.message || TXT.necitit);
  }).catch(function(){ $("brut").textContent = TXT.nuRaspunde; });
}
$("comutaBrut").addEventListener("click", function(){
  BRUT_VIZIBIL = !BRUT_VIZIBIL;
  $("brut").classList.toggle("ascuns", !BRUT_VIZIBIL); $("fisier").classList.toggle("ascuns", !BRUT_VIZIBIL);
  $("comutaBrut").textContent = BRUT_VIZIBIL ? TXT.peScurt : TXT.textBrut;
  if(BRUT_VIZIBIL){ citesteBrut(); }
});
$("fisier").addEventListener("change", citesteBrut);
// conectarea cu codul de pe televizor (aceleasi cereri ca pagina de conectare a receptorului: /asociere/cod, /asociere)
function mesajCod(text, eroare){ var m = $("mesajCod"); m.textContent = text || ""; m.classList.toggle("eroare", !!eroare); }
function asociere(cale, date){
  return fetch(cale, {method: "POST", cache: "no-store", credentials: "same-origin",
    headers: {"Content-Type": "application/x-www-form-urlencoded"}, body: date.toString()}).then(function(r){
    return r.json().catch(function(){ return {result: false, mesaj: TXT.neasteptat.replace("%s", r.status)}; });
  });
}
$("arataCod").addEventListener("click", function(){
  mesajCod(TXT.seCereCodul);
  asociere("/asociere/cod", new URLSearchParams("reafiseaza=1")).then(function(r){
    // receptorul spune unde se vede codul (pe ecran acum, dupa iesirea din meniu sau dupa pornirea din standby)
    mesajCod(r.result ? (r.mesaj || TXT.codulPeTv) + " " + TXT.scrieCodul : (r.mesaj || TXT.codNecerut), !r.result);
    if(r.result){ $("cod").focus(); }
  }).catch(function(){ mesajCod(TXT.nuRaspunde, true); });
});
$("conecteaza").addEventListener("click", function(){
  var cod = $("cod").value.replace(/[^0-9]/g, "");
  if(cod.length !== 6){ mesajCod(TXT.codSase, true); return; }
  asociere("/asociere", new URLSearchParams("cod=" + cod)).then(function(r){
    if(r.result){ mesajCod(TXT.conectat); location.reload(); return; }
    mesajCod(r.mesaj || TXT.codGresit, true);
  }).catch(function(){ mesajCod(TXT.nuRaspunde, true); });
});
$("fara").addEventListener("click", function(){
  if(!DATE){ return; }
  if(DATE.fara_parola){ trimite("/api/acces-ssh-fara-parola", {pornit: "0"}, "fara"); return; }
  if(!confirm(TXT.intrebareFara)){ return; }
  trimite("/api/acces-ssh-fara-parola", {pornit: "1", confirmat: "1"}, "fara");
});
// citirea urmatoare: des cat se asteapta rezultatul unei comenzi, apoi la 3 secunde
function planifica(){ setTimeout(function(){ citeste().then(planifica, planifica); }, ASTEPT === null ? 3000 : 700); }
citeste().then(planifica, planifica);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
TEXTE_PAGINA = {
	"html": (
		N_("__T_CUM_TEXT__ <span class=\"cod\" id=\"comanda\">ssh root@receptor</span>"),
		N_("ssh-ed25519 AAAA... nume@calculator"),
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
