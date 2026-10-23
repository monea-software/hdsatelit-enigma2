# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# traducere_configurare_web.py: „Traducerea subtitrărilor: configurare pas cu pas” in interfata web (HdsWebControl).
# Telefonul ajunge aici din codul QR al ecranului traducerii de pe televizor (/t/<jeton> il asociaza si il trimite
# aici); pagina merge la fel din PC. Pasii: alegi serviciul, iti faci cheia pe pagina oficiala (deschisa intr-o fila
# noua), lipesti cheia, iar receptorul o probeaza pe loc; la reusita o salveaza, porneste traducerea si arata
# confirmarea pe televizor. Pentru serverul din casa (LibreTranslate, Ollama) receptorul il cauta in reteaua de acasa.
#
# O SINGURA LOGICA: recunoasterea cheii, normalizarea adreselor, alegerea modelului, proba, salvarea si cautarea sunt
# in Components/HdsConfigurareTraducere.py (C); setarile, cheile, numele serviciilor si instructiunile in
# Components/HdsTraducereSubtitrari.py (T). Fisierul de fata verifica argumentele, porneste lucrarile si arata starea.
# „Adresă proprie” nu se configureaza aici (pagina /traducere-subtitrari, toate setarile).
#
# CHEIA: se primeste NUMAI din corpul unei cereri POST; scrisa in adresa (care ramane in istoricul browserului si in
# jurnale) e refuzata si nu porneste nimic. Twisted amesteca in request.args argumentele din adresa cu cele din corp,
# deci adresa se citeste separat, din request.uri. Raspunsurile nu contin niciodata o cheie: starea modulului C e fara
# cheie, campurile cu nume de cheie se scot, iar orice text care contine o cheie salvata sau cheia primita in cerere se
# inlocuieste inainte de trimitere.
#
# Rute (toate prin poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat;
# ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/traducere-configurare           starea: ce e ales acum, lucrarea configurarii (pasul, proba, modelul,
#                                             eroarea si ce sa faci), cautarea in retea, instructiunile, regiunile Azure
#   POST /api/traducere-configurare-cheie     corpul: cheie, serviciu (auto sau codul), regiune, fara_proba (0 / 1),
#                                             cont (ID-ul contului Cloudflare, 32 de semne hex; gol = cel din setari)
#   POST /api/traducere-configurare-server    serviciu (libre / openai), adresa, model (gol = il alege receptorul)
#   POST /api/traducere-configurare-model     model: schimba modelul serviciului ales acum si probeaza din nou
#   POST /api/traducere-configurare-cauta     cauta serverele din reteaua de acasa
#   GET  /traducere-configurare               pagina
# Raspunsul fiecarei rute e starea intreaga, cu result si message.
#
# SERVICIUL PRINCIPAL: o cheie lipita pentru alt serviciu decat cel principal intra in rezerve cand principalul merge
# (C, configurare.rezerva): rezultatul spune ca traducerea ramane pe principal si are butonul „Fă-l principal”. Cand
# mai sunt servicii gata (acum.gata, din T.serviciiGata), „Acum pe receptor” spune care e principalul si le arata pe
# fiecare cu „Fă-l principal”. Butonul trimite principal=<cod> la POST /api/traducere-subtitrari-seteaza (pagina cu
# toate setarile, T.punePrincipal: principalul nou iese din rezerve, fostul intra primul; salvat pe loc), apoi pagina
# isi citeste din nou starea.
# UNDE LUCREAZA: numele serviciilor din Acum pe receptor, din rezerve si din cele gata au in paranteza pe internet
# sau local (dupa adresa pusa, T.numeCuLoc); butoanele pasului 1 primesc acelasi lucru din starea 'locuri'.
#
# PAGINA: tot ce vine de la receptor se pune numai cu textContent; legaturile externe numai https, in fila noua, cu
# rel="noopener noreferrer". Cat merge o lucrare, pagina cere starea la URMARIRE_MS, cel mult URMARIRE_MAX_S (sau
# URMARIRE_MODEL_S de la pornire, daca un pas a spus ca modelul se incarca pe calculator; cautarea cel mult
# CAUTARE_MAX_S). Traducerea
# probei se scrie in culoarea traducerii de pe televizor (#fff3b0, lib/gui/esubtitle.cpp).
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2; apelurile sunt scurte, lucrarile merg pe firele lor (in C).
# Fisierul nu importa nimic la incarcare: probele de pe PC dau modulele lor (T si C).


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (probele de pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text

MAX_TEXT = 300            # adresa, modelul
MAX_REGIUNE = 40
MAX_CHEIE_BRUT = 2048     # cheia lipita, cu spatii si randuri noi; modulul o refuza peste 512 caractere
MAX_VALOARE = 4096        # orice argument citit (peste, tot refuzat)
MAX_ARGUMENTE = 16
CHEIE_MIN_ASCUNS = 6      # un text mai scurt nu se cauta in raspunsuri (ar strica texte obisnuite)
URMARIRE_MS = 1000
PRAG_LENT_MS = 1000       # o proba mai lenta: avertismentul „prea lent pentru subtitrari la timp”, si fara „lent”
URMARIRE_MAX_S = 30
URMARIRE_MODEL_S = 90     # „Se încarcă modelul pe calculator...” poate dura pana la un minut
CAUTARE_MAX_S = 25        # modulul se opreste singur dupa cel mult 15 s

SERVERE = ("libre", "openai")
# ordinea butoanelor din pasul 1 („casa” = serverul din casa, „auto” = „Am deja o cheie”)
ORDINE = ("azure", "gemini", "casa", "auto", "deepl", "groq", "cloudflare", "google")
def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele se traduc la folosire, cu _t."""
	return text


# etichetele de sub numele serviciilor, cand T.ETICHETE (serviciu -> text) lipseste sau nu are serviciul
ETICHETE_PAGINA = {
	"azure": N_("Recomandat pentru subtitrări zilnice"),
	"gemini": N_("Cel mai simplu de pornit, fără card; se poate opri dacă te uiți mult"),
	"casa": N_("Fără limită, mai lent pe calculatoarele obișnuite"),
	"groq": N_("Gratuit și rapid; limită pe zi, ajunge pentru câteva filme"),
	"cloudflare": N_("Gratuit; ajunge pentru câteva filme pe zi"),
}
ASCUNSE = ("propriu",)    # nu se configureaza aici
CAMPURI_CHEIE = ("cheie", "chei", "api_key", "key", "antet_valoare")

# pasii scurti de langa butonul „Deschide pagina cheii” (toti pasii vin din T.instructiuni)
PASI_SCURTI = {
	"gemini": (
		N_("Pe pagina deschisă intră cu contul tău Google; prima dată accepți termenii."),
		N_("Apasă „Create API key” și copiază cheia."),
		N_("Nu adăuga card la proiect: așa rămâi pe gratuit."),
	),
	"azure": (
		N_("Intră cu contul Microsoft. Abonamentul Azure gratuit cere un card, numai pentru verificare."),
		N_("Pe pagina deschisă: „Resource group”, „Create new”; „Region” Global; un nume; „Pricing tier” Free F0; apoi "
		"„Review + create” și „Create”."),
		N_("La resursă deschide „Keys and Endpoint” și copiază „KEY 1”."),
		N_("După 30 de zile Microsoft cere trecerea abonamentului pe „Pay as you go”: fă-o; cât rămâi pe Free F0 nu se "
		"plătește nimic."),
	),
	"deepl": (
		N_("Pe pagina deschisă intră în contul DeepL API. Dacă nu ai unul, fă-l gratuit, cu planul „Developer” "
			"(1.000.000 de caractere, o singură dată)."),
		N_("La „API Keys” copiază cheia; dacă nu ai niciuna, apasă „Create key”."),
	),
	"groq": (
		N_("Pe pagina deschisă intră cu emailul sau cu contul tău Google."),
		N_("Apasă „Create API Key”, scrie un nume și copiază cheia (începe cu gsk_); Groq o arată o singură dată."),
		N_("Nu adăuga card la cont, ca să rămâi pe planul gratuit."),
	),
	"cloudflare": (
		N_("Pe pagina deschisă intră în contul Cloudflare (sau fă unul gratuit): se deschide pagina "
			"„Workers AI”. Apasă „Use REST API”."),
		N_("Apasă „Create a Workers AI API Token”, apoi „Create API Token” și „Copy API Token”; copiază și "
			"„Account ID”, de la „Get Account ID”."),
		N_("Nu trece contul pe planul plătit („Workers Paid”), ca să rămâi pe gratuit."),
	),
	"google": (
		N_("Pe pagina deschisă alege proiectul tău (cu facturarea pornită) și pornește „Cloud Translation API”, dacă "
			"nu "
		"e pornit."),
		N_("Apasă „Create credentials”, „API key” și copiază cheia."),
		N_("Ca să nu plătești, coboară cota pe zi a „Cloud Translation API” (vezi toți pașii, mai jos)."),
	),
}


def _tr(T=None):
	"""Components.HdsTraducereSubtitrari (sau modulul dat de probe)"""
	if T is not None:
		return T
	from Components import HdsTraducereSubtitrari
	return HdsTraducereSubtitrari


def _cf(C=None):
	"""Components.HdsConfigurareTraducere (sau modulul dat de probe), incarcat la prima cerere"""
	if C is not None:
		return C
	from Components import HdsConfigurareTraducere
	return HdsConfigurareTraducere


def textBun(v):
	"""cel mult MAX_TEXT caractere, fara caractere de control"""
	if len(v) > MAX_TEXT:
		return False
	return not any(ord(c) < 32 or 127 <= ord(c) < 160 or c in u"  " for c in v)


def regiuneBuna(v):
	"""regiunea resursei Azure: litere, cifre, liniute (de exemplu westeurope)"""
	return 0 < len(v) <= MAX_REGIUNE and all((c.isalnum() and ord(c) < 128) or c in "-_" for c in v)


def contBun(v):
	"""ID-ul contului Cloudflare: 32 de semne hex (de la Account ID)"""
	return len(v) == 32 and all(c in "0123456789abcdef" for c in v)


def doarHttps(adresa):
	"""adresa daca e https, fara spatii, ghilimele si caractere de control; altfel "" """
	if not isinstance(adresa, str) or not adresa.startswith("https://") or len(adresa) > MAX_TEXT:
		return ""
	if any(ord(c) <= 32 or 127 <= ord(c) < 160 or c in "\"'<>\\`" for c in adresa):
		return ""
	return adresa


def _secunde(ms):
	try:
		return ("%.2f s" % (float(ms) / 1000.0)).replace(".", ",")
	except (TypeError, ValueError):
		return None


def _instructiuni(T, serviciu):
	try:
		return dict(T.instructiuni(serviciu) or {})
	except Exception:
		return {}


def serviciiCuCheie(T):
	"""ce poate primi ruta cheii: auto (receptorul recunoaste serviciul) si serviciile care cer cheie"""
	return ["auto"] + [c for c in T.SERVICII if c not in ASCUNSE and "cheie" in T.CERE.get(c, ())]


def _nume(T, cod, s=None):
	"""numele serviciului cu unde lucreaza, in paranteza: (pe internet) sau (local), dupa adresa pusa (T.numeCuLoc)"""
	try:
		return T.numeCuLoc(cod, s) if hasattr(T, "numeCuLoc") else T.numeServiciu(cod)
	except Exception:
		return T.numeServiciu(cod)


def servicii(T):
	"""Pentru pasul 2: numele (titlul Cheia pentru ...), pagina cheii (numai https), pasii scurti si toate
	instructiunile fiecarui serviciu."""
	rez = {}
	for c in T.SERVICII:
		if c in ASCUNSE:
			continue
		d = _instructiuni(T, c)
		rez[c] = {
			"nume": T.numeServiciu(c),
			"cere_cheie": "cheie" in T.CERE.get(c, ()),
			"pagina_cheie": doarHttps(d.get("pagina_cheie", "")),
			"pasi_scurti": [_t(p) for p in PASI_SCURTI.get(c, ())],
			"titlu": d.get("titlu") or "",
			"avertisment": d.get("avertisment") or "",
			"pasi": list(d.get("pasi") or []),
			"cota": d.get("cota") or "",
			"depasire": d.get("depasire") or "",
			"sursa": doarHttps(d.get("sursa", "")),
		}
	return rez


def _valoare(s, camp):
	try:
		return getattr(s, camp).value or ""
	except AttributeError:
		return ""


def _rezerve(T, s, principal):
	"""config.hds_traducere.rezerve (lista ordonata a serviciilor de rezerva, coduri despartite prin virgula, facuta in
	pagina cu toate setarile): None cand setarea nu exista; altfel [{"cod", "nume"}] in ordine, fara codurile
	necunoscute, fara serviciul principal si fara dubluri"""
	try:
		element = s.rezerve          # ConfigSubsection da KeyError (nu AttributeError) pentru o setare lipsa
	except (KeyError, AttributeError):
		return None
	rez = []
	for cod in str(getattr(element, "value", "") or "").split(","):
		cod = cod.strip()
		if cod in T.SERVICII and cod != principal and cod not in [r["cod"] for r in rez]:
			rez.append({"cod": cod, "nume": _nume(T, cod, s)})
	return rez


def acum(T):
	"""Ce e pus acum pe receptor: serviciul (principal), daca are cheie, daca traducerea e pornita, ultima proba,
	rezervele si serviciile gata sa devina principale (gata: [{"cod", "nume"}], T.serviciiGata)."""
	s = T.initConfig()
	serv = s.serviciu.value
	chei = dict(T.chei().stare())
	try:
		cfg = T.configuratia(s)
		lipsa = T.textCeLipseste(cfg)
	except Exception:
		cfg, lipsa = None, ""
	try:
		fel_cheie, text_cheie = T.stareCheie(cfg) if cfg is not None and hasattr(T, "stareCheie") else ("", "")
	except Exception:
		fel_cheie, text_cheie = "", ""
	try:
		din_nou = T.textCheiDinNou() if hasattr(T, "textCheiDinNou") else ""
	except Exception:
		din_nou = ""
	proba = None
	try:
		p = T.instanta().ultima_proba
	except Exception:
		p = None
	if p:
		proba = dict((k, v) for k, v in p.items() if k != "laRezultat")
		proba["timp"] = _secunde(proba.get("ms")) if proba.get("ms") is not None else None
	gata = []
	try:
		if hasattr(T, "serviciiGata"):
			gata = [{"cod": c, "nume": _nume(T, c, s)} for c in T.serviciiGata(s)]
	except Exception:
		gata = []
	return {
		"serviciu": serv,
		"serviciu_nume": _nume(T, serv, s),
		"pornit": bool(s.pornit.value),
		"cere_cheie": "cheie" in T.CERE.get(serv, ()),
		"cheie_pusa": bool(chei.get(serv)),
		"cheie_oprita_text": text_cheie if fel_cheie == "oprita" else "",
		"chei": chei,
		"adresa": {"libre": _valoare(s, "adresa_libre"), "openai": _valoare(s, "adresa_openai")}.get(serv, ""),
		"model": {"gemini": _valoare(s, "model_gemini"), "openai": _valoare(s, "model_openai"),
			"groq": _valoare(s, "model_groq"), "cloudflare": _valoare(s, "model_cloudflare")}.get(serv, ""),
		# ID-ul contului Cloudflare (nu e secret: e in adresa cererii); pasul cheii il propune
		"cont_cloudflare": _valoare(s, "cont_cloudflare"),
		"lipsa_text": lipsa,
		"chei_din_nou": din_nou,
		"proba": proba,
		"rezerve": _rezerve(T, s, serv),
		"gata": gata,
	}


TEXT_AUTOMAT = N_("Automat (receptorul încearcă singur Global și regiunile uzuale)")


def numeRegiuni(T):
	"""{cod: numele din portal} din T.REGIUNI_AZURE (perechi cod, nume), cand exista"""
	rez = {}
	for r in getattr(T, "REGIUNI_AZURE", None) or ():
		if isinstance(r, (list, tuple)) and len(r) > 1:
			rez[str(r[0])] = str(r[1])
	return rez


def _regiuni(lista, nume=None):
	"""[[cod, text]]: "" = Automat (primul); celelalte „Numele din portal (cod)”"""
	nume = nume or {}
	rez = []
	for r in lista or ():
		if isinstance(r, (list, tuple)) and r:
			cod, n = str(r[0]), str(r[1] if len(r) > 1 else "")
		else:
			cod, n = str(r), ""
		n = n or nume.get(cod, "")
		if any(cod == x[0] for x in rez):
			continue
		if not cod:
			text = _t(TEXT_AUTOMAT)
		elif n and n != cod:
			text = "%s (%s)" % (n, cod)
		else:
			text = cod
		rez.append([cod, text])
	return rez


def regiuniAzure(T, C):
	"""lista regiunilor pentru pasul 2: din T.REGIUNI_AZURE (perechi), altfel din C.REGIUNI_AZURE; Automat primul"""
	sursa = getattr(T, "REGIUNI_AZURE", None) or getattr(C, "REGIUNI_AZURE", None) or [""]
	rez = _regiuni(sursa, numeRegiuni(T))
	rez = [r for r in rez if r[0]]
	return [["", _t(TEXT_AUTOMAT)]] + rez


def _faraCampuriCheie(o):
	"""copie fara campurile care ar putea tine o cheie (orice adancime)"""
	if isinstance(o, dict):
		return dict((k, _faraCampuriCheie(v)) for k, v in o.items() if str(k).lower() not in CAMPURI_CHEIE)
	if isinstance(o, (list, tuple)):
		return [_faraCampuriCheie(v) for v in o]
	return o


def _stareModul(obiect, T):
	d = _faraCampuriCheie(dict(obiect.stare() or {}))
	if "regiuni" in d:
		d["regiuni"] = _regiuni(d["regiuni"], numeRegiuni(T))
	return d


def etichete(T):
	"""{cod din ORDINE: eticheta}: din T.ETICHETE cand exista (cheia „casa”, sau „libre” / „openai” pentru serverul
	din casa), altfel ETICHETE_PAGINA"""
	rez = dict((k, _t(v)) for k, v in ETICHETE_PAGINA.items())
	din_t = getattr(T, "ETICHETE", None)
	if not isinstance(din_t, dict):
		return rez
	for cod in ORDINE:
		for cheie in ((cod, "libre", "openai") if cod == "casa" else (cod,)):
			text = din_t.get(cheie)
			if isinstance(text, str) and text.strip() and textBun(text.strip()):
				try:
					rez[cod] = T._t(text.strip()) if hasattr(T, "_t") else text.strip()
				except Exception:
					rez[cod] = text.strip()
				break
	return rez


def locuri(T):
	"""{cod din pasul 1: unde lucreaza}, pus de script in paranteza dupa numele de pe butoane: serviciile din internet
	pe internet, serverul din casa local (T.etichetaLoc, T.ETICHETE_LOC); {} cu un modul fara ele"""
	if not hasattr(T, "etichetaLoc"):
		return {}
	rez = {}
	for cod in ("azure", "gemini", "deepl", "groq", "cloudflare", "google"):
		try:
			rez[cod] = T.etichetaLoc(cod)
		except Exception:
			pass
	try:
		rez["casa"] = T._t(T.ETICHETE_LOC[T.LOC_CASA])
	except Exception:
		pass
	return rez


def _stareBruta(T, C):
	return {
		"result": True,
		"acum": acum(T),
		"servicii": servicii(T),
		"configurare": _stareModul(C.configurator(), T),
		"cautare": _stareModul(C.cautare(), T),
		"regiuni_azure": regiuniAzure(T, C),
		"etichete": etichete(T),
		"locuri": locuri(T),
	}


def _inlocuieste(o, valori):
	if isinstance(o, dict):
		return dict((k, _inlocuieste(v, valori)) for k, v in o.items())
	if isinstance(o, (list, tuple)):
		return [_inlocuieste(v, valori) for v in o]
	if isinstance(o, str):
		for v in valori:
			if v in o:
				o = o.replace(v, "(cheia)")
	return o


def ascundeCheile(d, T, primite=()):
	"""Orice text care contine o cheie salvata sau cheia primita in cerere se inlocuieste (a doua plasa)."""
	valori = []
	try:
		valori = [v for v in (T.chei().citeste() or {}).values() if isinstance(v, str)]
	except Exception:
		pass
	for v in primite:
		if isinstance(v, str):
			valori += [v.strip(), "".join(v.split())]
	valori = sorted(set(v for v in valori if len(v) >= CHEIE_MIN_ASCUNS), key=len, reverse=True)
	return _inlocuieste(d, valori) if valori else d


def stare(T=None, C=None):
	"""Pentru GET /api/traducere-configurare (si raspunsul celorlalte rute, cu „message”)."""
	T = _tr(T)
	return ascundeCheile(_stareBruta(T, _cf(C)), T)


def _raspuns(T, C, rezultat, mesaj, primite=()):
	d = _stareBruta(T, C)
	d["result"] = bool(rezultat)
	d["message"] = mesaj if isinstance(mesaj, str) else str(mesaj or "")
	return ascundeCheile(d, T, primite)


def cheie(argumente, din_adresa, T=None, C=None):
	"""POST /api/traducere-configurare-cheie. `din_adresa` = numele argumentelor scrise in adresa. Toate verificarile
	se fac INAINTE de a porni ceva; mesajele nu repeta nimic din ce s-a primit."""
	T = _tr(T)
	C = _cf(C)
	if "cheie" in din_adresa:
		return _raspuns(T, C, False, _t("Cheia nu se trimite în adresă: adresa rămâne în istoricul browserului și în "
			"jurnale. Lipește-o în pagină. Nu s-a salvat și nu s-a pornit nimic."))
	valoare = argumente.get("cheie", "")
	if len(valoare) > MAX_CHEIE_BRUT:
		return _raspuns(T, C, False, _t("Cheia e prea lungă. Nu s-a pornit nimic."))
	curata = "".join(valoare.split())
	if not curata:
		return _raspuns(T, C, False, _t("Lipește întâi cheia."))
	serviciu = argumente.get("serviciu", "") or "auto"
	if serviciu not in serviciiCuCheie(T):
		return _raspuns(T, C, False, _t("Serviciu necunoscut. Nu s-a pornit nimic."), (valoare,))
	regiune = argumente.get("regiune", "").strip()
	if regiune and not regiuneBuna(regiune):
		return _raspuns(T, C, False, _t("Regiunea e greșită: litere, cifre și liniuțe, de exemplu westeurope. Nu s-a "
			"pornit nimic."), (valoare,))
	cont = argumente.get("cont", "").strip().lower()
	if cont and not contBun(cont):
		return _raspuns(T, C, False, _t("ID-ul contului Cloudflare are 32 de litere și cifre (de la „Account ID”). "
			"Cheia nu a plecat nicăieri."), (valoare,))
	fara_proba = argumente.get("fara_proba", "0") or "0"
	if fara_proba not in ("0", "1"):
		return _raspuns(T, C, False, _t("Valoare greșită pentru „fără probă” (0 sau 1). Nu s-a pornit nimic."),
			(valoare,))
	# curatarea (spatii, randuri noi, prefixe ca „DeepL-Auth-Key ”) o face modulul C
	if cont:
		reusit, mesaj = C.configurator().porneste_cheie(valoare.strip(), serviciu=serviciu, regiune=regiune,
			fara_proba=fara_proba == "1", cont=cont)
	else:
		reusit, mesaj = C.configurator().porneste_cheie(valoare.strip(), serviciu=serviciu, regiune=regiune,
			fara_proba=fara_proba == "1")
	return _raspuns(T, C, reusit, mesaj, (valoare,))


def server(argumente, T=None, C=None):
	"""POST /api/traducere-configurare-server: serverul din casa (LibreTranslate sau compatibil OpenAI / Ollama)."""
	T = _tr(T)
	C = _cf(C)
	serviciu = argumente.get("serviciu", "")
	if serviciu not in SERVERE:
		return _raspuns(T, C, False, _t("Felul serverului e necunoscut: LibreTranslate sau Ollama (compatibil OpenAI). "
			"Nu s-a pornit nimic."))
	adresa = argumente.get("adresa", "").strip()
	model = argumente.get("model", "").strip()
	if not adresa:
		return _raspuns(T, C, False, _t("Scrie adresa serverului, de exemplu 192.168.1.50."))
	if not textBun(adresa) or not textBun(model):
		return _raspuns(T, C, False, _t("Adresa sau modelul sunt prea lungi sau au caractere nepermise. Nu s-a pornit "
			"nimic."))
	normalizeaza = getattr(C, "normalizeazaAdresa", None)
	if normalizeaza is not None:
		adresa, eroare = normalizeaza(serviciu, adresa)
		if eroare or not adresa:
			return _raspuns(T, C, False, _t("%s Nu s-a pornit nimic.") % (eroare or _t("Adresa e greșită.")))
	reusit, mesaj = C.configurator().porneste_server(serviciu, adresa, model)
	return _raspuns(T, C, reusit, mesaj)


def model(argumente, T=None, C=None):
	"""POST /api/traducere-configurare-model: alt model pentru serviciul ales acum, cu proba."""
	T = _tr(T)
	C = _cf(C)
	nume = argumente.get("model", "").strip()
	if not nume:
		return _raspuns(T, C, False, _t("Alege un model."))
	if not textBun(nume):
		return _raspuns(T, C, False, _t("Numele modelului e prea lung sau are caractere nepermise. Nu s-a pornit "
			"nimic."))
	reusit, mesaj = C.configurator().porneste_model(nume)
	return _raspuns(T, C, reusit, mesaj)


def cauta(T=None, C=None):
	"""POST /api/traducere-configurare-cauta: cautarea serverelor din reteaua de acasa."""
	T = _tr(T)
	C = _cf(C)
	reusit, mesaj = C.cautare().porneste()
	return _raspuns(T, C, reusit, mesaj)


def argumente(request):
	"""Argumentele cererii ca text intreg (fara taiere: o valoare prea lunga se refuza, nu se scurteaza), fara token."""
	rez = {}
	toate = list((getattr(request, "args", None) or {}).items())
	for nume, val in toate[:MAX_ARGUMENTE]:
		if isinstance(nume, bytes):
			nume = nume.decode("utf-8", "replace")
		if nume == "token" or not nume or len(nume) > 20:
			continue
		v = (val or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[nume] = str(v)[:MAX_VALOARE + 1]
	return rez


def cheiDinAdresa(request):
	"""Numele argumentelor scrise in adresa (request.args le amesteca cu cele din corp)."""
	uri = getattr(request, "uri", b"") or b""
	if isinstance(uri, bytes):
		uri = uri.decode("utf-8", "replace")
	from urllib.parse import urlsplit, parse_qsl
	try:
		return set(k for k, v in parse_qsl(urlsplit(uri).query, keep_blank_values=True))
	except ValueError:
		return set(["cheie"])     # adresa care nu se poate citi: cheia nu se primeste


def rute(baza, resource, T=None, C=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py; T si C sunt
	modulele date de probe (implicit Components.HdsTraducereSubtitrari si Components.HdsConfigurareTraducere,
	incarcate la prima cerere)."""

	class StareResource(baza):
		"""GET /api/traducere-configurare: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(T, C))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor (%s).") % eroare.__class__.__name__, 500)

	class _Schimba(baza):
		schimbaCeva = True

		def fa(self, request):
			raise NotImplementedError

		def render_POST(self, request):
			try:
				return self._raspunde(request, self.fa(request))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor (%s).") % eroare.__class__.__name__, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class ServerResource(_Schimba):
		def fa(self, request):
			return server(argumente(request), T, C)

	class ModelResource(_Schimba):
		def fa(self, request):
			return model(argumente(request), T, C)

	class CautaResource(_Schimba):
		def fa(self, request):
			return cauta(T, C)

	class CheieResource(baza):
		"""POST /api/traducere-configurare-cheie: numai POST, cheia numai din corp; eroarea nu repeta nimic primit."""
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, cheie(argumente(request), cheiDinAdresa(request), T, C))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor (%s).") % eroare.__class__.__name__, 500)

		def render_GET(self, request):
			return self._eroare(request, _t("Cheia se trimite numai cu POST, din pagină. Nu s-a salvat nimic."), 405)

	class PaginaResource(resource.Resource):
		"""GET /traducere-configurare: pagina „Traducerea subtitrărilor: configurare pas cu pas”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"traducere-configurare": StareResource(),
		b"traducere-configurare-cheie": CheieResource(),
		b"traducere-configurare-server": ServerResource(),
		b"traducere-configurare-model": ModelResource(),
		b"traducere-configurare-cauta": CautaResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /traducere-subtitrari: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; un
	browser neconectat primeste pagina de asociere. Pagina schimba ceva pe receptor, deci cu cookie primeste tokenul
	CSRF."""
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


def pagina_text(stil, config_pagina):
	return _traducePagina(PAGINA).replace("__STIL_COMUN__", stil).replace("__CONFIG__",
		config_pagina).replace("__DRUM_MENIU__",
		_drumMeniu("hds_traducere_subtitrari")).replace("__URMARIRE_MS__", str(URMARIRE_MS)).replace(
		"__URMARIRE_MAX_MS__", str(URMARIRE_MAX_S * 1000)).replace("__URMARIRE_MODEL_MS__",
		str(URMARIRE_MODEL_S * 1000)).replace("__CAUTARE_MAX_MS__", str(CAUTARE_MAX_S * 1000)).replace(
		"__PRAG_LENT_MS__", str(PRAG_LENT_MS))


# Tot ce vine de la receptor (mesaje, pasi, adrese, modele, traduceri) se pune numai cu textContent; o legatura
# externa primeste href numai daca adresa incepe cu https://.
PAGINA = r"""<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Configurarea traducerii</title>
<style>__STIL_COMUN__
  main{max-width:760px;margin:0 auto;overflow-wrap:anywhere;}
  h1{font-size:1.25rem;margin:0 0 6px;line-height:1.3;}
  h2{font-size:1.05rem;margin:0 0 10px;}
  h3{font-size:.98rem;margin:14px 0 6px;}
  p{line-height:1.45;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:14px 16px;margin:0 0 12px;}
  .alegeri{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;}
  .alegere{display:flex;flex-direction:column;align-items:flex-start;gap:4px;width:100%;min-width:0;min-height:76px;padding:12px 14px;border-radius:10px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;text-align:left;cursor:pointer;}
  .alegere strong{font-size:1.02rem;}
  .alegere .desc{color:var(--text-slab);font-size:.86rem;line-height:1.35;}
  .alegere.recomandat{border-color:#3d7a57;}
  .alegere.ales{border-color:var(--accent);box-shadow:inset 0 0 0 2px var(--accent);}
  .eticheta{color:#8fd19e;font-size:.84rem;font-style:normal;font-weight:600;line-height:1.35;}
  .eticheta.rec{display:inline-block;background:var(--accent);color:#fff;border-radius:6px;padding:1px 8px;font-size:.78rem;}
  button{min-height:44px;padding:10px 14px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;cursor:pointer;}
  button:disabled{opacity:.55;cursor:default;}
  .mare{display:flex;align-items:center;justify-content:center;width:100%;min-height:52px;margin:10px 0 0;padding:12px 16px;border-radius:10px;font-weight:600;font-size:1.02rem;text-align:center;text-decoration:none;}
  .principal{background:var(--accent);border:1px solid var(--accent);color:#fff;}
  a.mare{color:#fff;}
  input,select{min-height:44px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;width:100%;min-width:0;}
  label{display:block;margin:12px 0 6px;}
  .cu-buton{display:flex;gap:8px;}
  .cu-buton input{flex:1 1 auto;}
  .cu-buton button{flex:0 0 auto;}
  .nota{color:var(--text-slab);font-size:.86rem;margin:8px 0 0;line-height:1.45;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .bine{color:#8fd19e;font-weight:600;font-size:1.05rem;margin:0 0 8px;}
  .avertisment{color:#f0c674;background:rgba(240,198,116,.12);border:1px solid rgba(240,198,116,.45);border-radius:8px;padding:8px 10px;margin:10px 0 0;line-height:1.45;}
  .traducere-sub{color:#fff3b0;}
  .ascuns{display:none !important;}
  a.leg{display:inline-block;padding:12px 0;line-height:20px;margin:0 18px 0 0;}
  dl.valori{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;margin:8px 0;font-size:.92rem;}
  dl.valori dt{color:var(--text-slab);}
  dl.valori dd{margin:0;min-width:0;}
  ol.pasi,ul.lista{margin:8px 0;padding:0 0 0 22px;line-height:1.5;}
  ol.pasi li,ul.lista li{margin:0 0 5px;}
  details{margin:10px 0 0;}
  summary{padding:11px 0;line-height:22px;cursor:pointer;color:#7fb8ff;}
  .gasit{border:1px solid var(--bordura);border-radius:10px;padding:10px 12px;margin:10px 0 0;background:#171b21;}
  .gasit p{margin:0 0 4px;}
  .lucru{color:#f0c674;}
  table.timpi{border-collapse:collapse;width:100%;font-size:.88rem;margin:6px 0 0;}
  table.timpi th,table.timpi td{text-align:left;padding:5px 6px;border-bottom:1px solid var(--bordura);}
  table.timpi th{color:var(--text-slab);font-weight:600;}
  footer{margin:6px 0 0;}
  @media (max-width:520px){ dl.valori.lung{grid-template-columns:1fr;gap:0;} dl.valori.lung dd{margin:0 0 6px;} }
</style>
</head>
<body>
<main>
<h1>Traducerea subtitrărilor: configurare pas cu pas</h1>
<p class="nota">Alegi serviciul, lipești cheia (sau alegi serverul din casă), iar receptorul o probează pe loc.</p>
<p class="mesaj" id="incarcare">Se citește starea...</p>
<div id="continut" class="ascuns">
  <section class="card" id="card-acum">
    <h2>Acum pe receptor</h2>
    <dl class="valori" id="acum-valori"></dl>
    <p class="avertisment ascuns" id="acum-din-nou"></p>
    <p class="nota ascuns" id="acum-lipsa"></p>
    <dl class="valori lung ascuns" id="acum-proba">
      <dt>Originalul</dt><dd id="acum-proba-original"></dd>
      <dt id="acum-proba-eticheta">Traducerea</dt><dd id="acum-proba-traducere"></dd>
    </dl>
    <div class="ascuns" id="acum-principal-bloc">
      <p id="acum-principal"></p>
      <div id="acum-alte"></div>
    </div>
    <p class="mesaj ascuns" id="mesaj-principal"></p>
  </section>
  <section class="card" id="card-serviciu">
    <h2>1. Alege serviciul</h2>
    <div class="alegeri" id="alegeri">
      <button type="button" class="alegere recomandat" id="alege-azure" aria-pressed="false"><strong>Azure Translator</strong><em class="eticheta rec" id="eticheta-azure">Recomandat pentru subtitrări zilnice</em><span class="desc">2 milioane de caractere pe lună, gratuit (planul Free F0). Cardul se cere la înscriere numai pentru verificare; pe F0 nu se plătește nimic. După 30 de zile contul trece pe „Pay as you go”, fără cost cât rămâi pe F0.</span></button>
      <button type="button" class="alegere" id="alege-gemini" aria-pressed="false"><strong>Gemini</strong><em class="eticheta" id="eticheta-gemini">Cel mai simplu de pornit, fără card; se poate opri dacă te uiți mult</em><span class="desc">Cheia o faci cu contul tău Google. La subtitrări continue poate da „prea multe cereri”.</span></button>
      <button type="button" class="alegere" id="alege-casa" aria-pressed="false"><strong>Serverul din casa ta</strong><em class="eticheta" id="eticheta-casa">Fără limită, mai lent pe calculatoarele obișnuite</em><span class="desc">LibreTranslate sau Ollama pe un calculator din casă. Nimic nu iese din casă.</span></button>
      <button type="button" class="alegere" id="alege-auto" aria-pressed="false"><strong>Am deja o cheie</strong><span class="desc">O lipești, iar receptorul recunoaște singur serviciul.</span></button>
      <button type="button" class="alegere" id="alege-deepl" aria-pressed="false"><strong>DeepL API</strong><span class="desc">Plan gratuit Developer: 1.000.000 de caractere, o singură dată.</span></button>
      <button type="button" class="alegere" id="alege-groq" aria-pressed="false"><strong>Groq</strong><em class="eticheta" id="eticheta-groq">Gratuit și rapid; limită pe zi, ajunge pentru câteva filme</em><span class="desc">Cheia o faci cu emailul sau cu contul tău Google. Pune și o rezervă pentru zilele cu multe subtitrări.</span></button>
      <button type="button" class="alegere" id="alege-cloudflare" aria-pressed="false"><strong>Cloudflare Workers</strong><em class="eticheta" id="eticheta-cloudflare">Gratuit; ajunge pentru câteva filme pe zi</em><span class="desc">Din panoul Cloudflare iei un jeton și ID-ul contului.</span></button>
      <button type="button" class="alegere" id="alege-google" aria-pressed="false"><strong>Google Cloud Translation</strong><span class="desc">Cere card; peste cota gratuită plătești automat.</span></button>
    </div>
    <p class="nota" id="nota-volum">Pentru subtitrări multe (filme întregi, zilnic) e recomandat Azure Translator, planul Free F0: 2 milioane de caractere pe lună; cardul se cere numai la înscriere, iar pe F0 nu se plătește nimic. Gemini e gratuit pentru folosire ocazională, dar la subtitrări continue poate da „prea multe cereri” după câteva minute.</p>
    <p class="nota">„Adresă proprie” (alt serviciu, cu adresa lui) și toate celelalte setări sunt pe pagina cu toate setările:</p>
    <p><a class="leg" href="/traducere-subtitrari">Toate setările traducerii</a></p>
  </section>
  <section class="card ascuns" id="card-cheie">
    <h2 id="cheie-titlu">2. Cheia</h2>
    <p class="avertisment ascuns" id="cheie-avertisment"></p>
    <div id="cheie-pagina-bloc">
      <a class="mare principal ascuns" id="cheie-pagina" target="_blank" rel="noopener noreferrer">Deschide pagina cheii</a>
      <ol class="pasi" id="cheie-pasi"></ol>
      <p>Apoi întoarce-te aici și lipește cheia.</p>
      <details id="cheie-toti"><summary>Toți pașii și cât e gratuit</summary>
        <ol class="pasi" id="cheie-toti-pasi"></ol>
        <p class="nota ascuns" id="cheie-cota"></p>
        <p class="nota ascuns" id="cheie-depasire"></p>
      </details>
    </div>
    <p class="ascuns" id="cheie-auto-nota">Lipește cheia oricărui serviciu: Gemini, DeepL, Azure, Google Cloud, Groq, OpenRouter sau OpenAI. Receptorul recunoaște singur serviciul și o probează.</p>
    <label for="cheie">Lipește cheia</label>
    <div class="cu-buton"><input type="password" id="cheie" autocomplete="off" autocapitalize="off" spellcheck="false" maxlength="2048" placeholder="lipește cheia aici"><button type="button" id="cheie-arata" aria-pressed="false">Arată</button></div>
    <div class="ascuns" id="regiune-bloc">
      <label for="alege-regiune">Regiunea resursei Azure</label>
      <select id="alege-regiune"></select>
      <p class="nota">Regiunea o găsești în portal, la resursa Translator: Overview › Location. Dacă nu știi, lasă „Automat”.</p>
    </div>
    <div class="ascuns" id="cont-bloc">
      <label for="cont-cloudflare">ID-ul contului Cloudflare</label>
      <input type="text" id="cont-cloudflare" maxlength="32" autocomplete="off" autocapitalize="off" spellcheck="false">
      <p class="nota">32 de litere și cifre, din panoul Cloudflare, la Account ID.</p>
    </div>
    <button type="button" class="mare principal" id="cheie-trimite">Verifică și salvează</button>
    <p class="nota">Cheia pleacă numai spre receptor, se păstrează criptată și nu se mai arată niciodată.</p>
    <p class="mesaj" id="mesaj-cheie"></p>
  </section>
  <section class="card ascuns" id="card-casa">
    <h2>2. Serverul din casa ta</h2>
    <p class="nota">Pe un calculator din casă rulează LibreTranslate sau Ollama. Receptorul îl caută în rețeaua de acasă, alege singur modelul și face proba.</p>
    <button type="button" class="mare principal" id="cauta">Caută în rețeaua de acasă</button>
    <p class="mesaj" id="cauta-progres"></p>
    <div id="gasite"></div>
    <div class="ascuns" id="negasit">
      <p id="negasit-titlu">Nu am găsit niciun server în rețea.</p>
      <div id="ajutor"></div>
      <p><a class="leg ascuns" id="instalare-ollama" target="_blank" rel="noopener noreferrer">Instalarea Ollama (pagina oficială)</a><a class="leg ascuns" id="instalare-libre" target="_blank" rel="noopener noreferrer">Instalarea LibreTranslate (pagina oficială)</a></p>
    </div>
    <p class="mesaj" id="mesaj-casa"></p>
    <details id="manual"><summary>Scriu eu adresa (pentru cine vrea)</summary>
      <label for="server-fel">Felul serverului</label>
      <select id="server-fel"><option value="openai">Ollama sau alt server compatibil OpenAI</option><option value="libre">LibreTranslate</option></select>
      <label for="server-adresa">Adresa calculatorului</label>
      <input type="text" id="server-adresa" maxlength="300" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="192.168.1.50">
      <p class="nota">Ajunge adresa IP; portul îl pune receptorul (11434 la Ollama, 5000 la LibreTranslate).</p>
      <label for="server-model">Modelul (numai la Ollama; gol = îl alege receptorul)</label>
      <input type="text" id="server-model" maxlength="300" autocomplete="off" autocapitalize="off" spellcheck="false">
      <button type="button" class="mare" id="server-trimite">Folosește adresa</button>
    </details>
  </section>
  <section class="card ascuns" id="card-rezultat">
    <h2>3. Proba</h2>
    <div class="ascuns" id="rez-lucru">
      <p class="lucru" id="rez-pas"></p>
      <p class="nota" id="rez-rabdare">Proba durează de obicei câteva secunde.</p>
    </div>
    <div class="ascuns" id="rez-ok">
      <p class="bine" id="rez-titlu">Gata. Cheia merge.</p>
      <div class="ascuns" id="rez-rezerva-bloc">
        <p id="rez-rezerva"></p>
        <button type="button" class="mare principal ascuns" id="rez-fa-principal">Fă-l principal</button>
      </div>
      <div class="avertisment ascuns" id="rez-lent-bloc">
        <p id="rez-lent"></p>
        <button type="button" class="mare principal" id="lent-gemini">Folosește Gemini (gratuit, fără card)</button>
        <button type="button" class="mare" id="lent-model">Alege un model mai mic</button>
      </div>
      <dl class="valori lung">
        <dt id="rez-original-et">Originalul</dt><dd id="rez-original"></dd>
        <dt id="rez-traducere-et">Traducerea</dt><dd class="traducere-sub" id="rez-traducere"></dd>
        <dt>Serviciul</dt><dd id="rez-serviciu"></dd>
        <dt id="rez-model-et">Modelul</dt><dd id="rez-model"></dd>
        <dt id="rez-timp-et">Timpul</dt><dd id="rez-timp"></dd>
      </dl>
      <div class="ascuns" id="rez-incercate"><h3>Modelele încercate</h3><table class="timpi"><thead><tr><th>Modelul</th><th>Timpul</th></tr></thead><tbody id="rez-incercate-rand"></tbody></table></div>
      <div class="ascuns" id="rez-modele-bloc">
        <label for="rez-modele">Alt model</label>
        <select id="rez-modele"></select>
        <button type="button" class="mare" id="rez-model-trimite">Folosește modelul ales</button>
      </div>
      <p class="ascuns" id="rez-pornit">Traducerea e pornită; pe televizor a apărut confirmarea.</p>
      <p class="nota ascuns" id="rez-gemini">Gemini e gratuit pentru folosire ocazională, dar la subtitrări continue poate da „prea multe cereri” după câteva minute. Pentru subtitrări multe (filme întregi, zilnic) e recomandat Azure Translator, planul Free F0 (2 milioane de caractere pe lună, fără plată).</p>
      <div class="ascuns" id="rez-rezerve-bloc">
        <p class="nota">Dacă serviciul cade (cota terminată, prea multe cereri), receptorul trece singur la următorul din lista rezervelor.</p>
        <p id="rez-rezerve"></p>
        <p><a class="leg" href="/traducere-subtitrari">Lista rezervelor, în toate setările</a></p>
      </div>
      <p class="nota ascuns" id="rez-mesaj-ok"></p>
    </div>
    <div class="ascuns" id="rez-eroare">
      <p class="eroare" id="rez-mesaj"></p>
      <p id="rez-ce-faci"></p>
    </div>
    <div class="ascuns" id="rez-regiune">
      <p id="rez-regiune-mesaj"></p>
      <label for="rez-regiuni">Regiunea resursei</label>
      <select id="rez-regiuni"></select>
      <p class="nota">Regiunea o găsești în portal, la resursa Translator: Overview › Location.</p>
    </div>
    <details class="ascuns" id="rez-detalii"><summary>Detalii</summary><p class="nota" id="rez-detalii-text"></p></details>
    <div class="ascuns" id="din-nou">
      <p class="nota">Din siguranță, receptorul nu păstrează cheia până nu merge: lipește-o din nou.</p>
      <label for="cheie-din-nou">Lipește din nou cheia</label>
      <div class="cu-buton"><input type="password" id="cheie-din-nou" autocomplete="off" autocapitalize="off" spellcheck="false" maxlength="2048" placeholder="lipește cheia aici"><button type="button" id="cheie-din-nou-arata" aria-pressed="false">Arată</button></div>
      <button type="button" class="mare principal ascuns" id="regiune-reincearca">Încearcă din nou cu regiunea aleasă</button>
      <button type="button" class="mare ascuns" id="fara-proba">Salvează cheia fără probă</button>
      <p class="nota ascuns" id="fara-proba-nota">Dacă știi că cheia e bună și receptorul nu ajunge acum la serviciu, o poți salva fără probă.</p>
    </div>
    <p class="mesaj" id="mesaj-rezultat"></p>
  </section>
  <footer>
    <p><a class="leg" href="/traducere-subtitrari">Toate setările traducerii</a><a class="leg" href="/">Panoul receptorului</a></p>
    <p class="nota">Aceleași setări sunt pe televizor, în __DRUM_MENIU__.</p>
  </footer>
</div>
</main>
<script>
var CFG = __CONFIG__;
var URMARIRE_MS = __URMARIRE_MS__, URMARIRE_MAX_MS = __URMARIRE_MAX_MS__, URMARIRE_MODEL_MS = __URMARIRE_MODEL_MS__, CAUTARE_MAX_MS = __CAUTARE_MAX_MS__;
var PRAG_LENT_MS = __PRAG_LENT_MS__;
var ALEGERI = ["azure", "gemini", "casa", "auto", "deepl", "groq", "cloudflare", "google"];
var CU_CHEIE = {gemini: 1, auto: 1, azure: 1, deepl: 1, google: 1, groq: 1, cloudflare: 1};
var FEL_SERVER = {ollama: "openai", libre: "libre"};
var NUME_FEL = {ollama: "Ollama", libre: "LibreTranslate"};
var AJUTOR_PROVIZORIU = [
  "Calculatorul trebuie să fie pornit, cu Ollama, LM Studio sau LibreTranslate pornit.",
  "Ollama răspunde implicit numai pe calculatorul lui. În aplicația Ollama (Windows sau Mac) pornește în setări expunerea în rețea, sau pune variabila OLLAMA_HOST cu valoarea 0.0.0.0:11434 și pornește din nou Ollama.",
  "LM Studio: în fila „Developer” pornește serverul și bifează „Serve on Local Network”.",
  "LibreTranslate trebuie pornit cu --host 0.0.0.0 (în Docker cu -p 5000:5000).",
  "Paravanul calculatorului (Windows Firewall) poate bloca porturile 11434 sau 5000: lasă aplicația să primească legături din rețeaua privată."
];
var ultim = null, ales = null, lucrareMea = "";
var urmarite = {configurare: null, cautare: null};
var cronometru = null;
var gasiteAfisate = "";
var alteAfisate = "";
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
    return r.json().catch(function(){ return {result: false, message: "Receptorul a răspuns neașteptat (HTTP " + r.status + ")."}; });
  });
}
function mesaj(id, text, eroare){ var m = $(id); m.textContent = text || ""; m.classList.toggle("eroare", !!eroare); }
function sterge(el){ while(el.firstChild){ el.removeChild(el.firstChild); } }
function arata(el, da){ el.classList.toggle("ascuns", !da); }
function paragraf(id, text){ var p = $(id); p.textContent = text || ""; arata(p, !!text); }
function eHttps(a){ return typeof a === "string" && /^https:\/\/[^\s"'<>\\`]+$/.test(a); }
function legatura(a, url){ if(eHttps(url)){ a.href = url; arata(a, true); } else { arata(a, false); } }
function lista(el, texte){
  sterge(el);
  (texte || []).forEach(function(t){ var li = document.createElement("li"); li.textContent = t; el.appendChild(li); });
  arata(el, !!(texte && texte.length));
}
function umple(s, alegeri, valoare){
  sterge(s);
  var gasit = false;
  alegeri.forEach(function(a){
    var o = document.createElement("option"); o.value = a[0]; o.textContent = a[1]; s.appendChild(o);
    if(a[0] === valoare){ gasit = true; }
  });
  s.value = gasit ? valoare : (alegeri.length ? alegeri[0][0] : "");
}
function regiuni(l){
  return (l || []).map(function(r){
    if(typeof r === "string"){ return [r, r || "Automat"]; }
    return [String(r[0]), String(r[1] === undefined ? r[0] : r[1]) || "Automat"];
  });
}
function valoare(dl, eticheta, text){
  var dt = document.createElement("dt"); dt.textContent = eticheta; dl.appendChild(dt);
  var dd = document.createElement("dd"); dd.textContent = text; dl.appendChild(dd);
}
function textDetalii(c){
  var parti = [];
  if(typeof c.cod === "number"){ parti.push(c.cod >= 1000 ? "codul " + c.cod : "HTTP " + c.cod); }
  else if(c.cod){ parti.push("codul " + c.cod); }
  ["cod_intern", "cod_serviciu"].forEach(function(k){ if(c[k] !== undefined && c[k] !== null && c[k] !== ""){ parti.push("codul " + c[k]); } });
  if(c.detalii){ parti.push(String(c.detalii)); }
  return parti.join(", ");
}
function textRezerve(l, inainte, gol){
  var nume = l.map(function(r){ return String(r.nume || r.cod || ""); }).filter(Boolean);
  return nume.length ? inainte + nume.join(" → ") : gol;
}
function secunde(ms){ return (typeof ms === "number") ? (ms / 1000).toFixed(2).replace(".", ",") + " s" : ""; }
function puneTot(d){
  ["acum", "servicii", "configurare", "cautare", "regiuni_azure", "etichete", "locuri"].forEach(function(k){ if(d[k] !== undefined){ ultim[k] = d[k]; } });
  puneEtichete();
  puneLocuri();
  puneAcum();
  puneRezultat();
  puneCautare();
}
function puneEtichete(){
  var e = ultim.etichete || {};
  ["azure", "gemini", "casa", "groq", "cloudflare"].forEach(function(k){ var el = $("eticheta-" + k); if(e[k]){ el.textContent = e[k]; } arata(el, !!(e[k] || el.textContent)); });
}
function puneLocuri(){
  var l = ultim.locuri || {};
  Object.keys(l).forEach(function(c){
    var b = $("alege-" + c), st = b && b.firstChild;
    if(!st || st.nodeType === 3){ return; }
    if(st._nume === undefined){ st._nume = st.textContent; }
    st.textContent = st._nume + (l[c] ? " (" + l[c] + ")" : "");
  });
}
function puneAcum(){
  var a = ultim.acum || {};
  var dl = $("acum-valori"); sterge(dl);
  valoare(dl, "Serviciul", a.serviciu_nume || a.serviciu || "-");
  if(a.cheie_oprita_text){ valoare(dl, "Cheia", a.cheie_oprita_text); }
  else if(a.cere_cheie){ valoare(dl, "Cheia", a.cheie_pusa ? "pusă" : "lipsește"); }
  if(a.adresa){ valoare(dl, "Adresa", a.adresa); }
  if(a.model){ valoare(dl, "Modelul", a.model); }
  valoare(dl, "Traducerea", a.pornit ? "pornită" : "oprită");
  if(a.rezerve){ valoare(dl, "Rezervele", textRezerve(a.rezerve, "", "niciuna")); }
  var p = a.proba;
  valoare(dl, "Ultima probă", p ? ((p.stare === "ok" ? "reușită" : p.stare === "lucru" ? "în lucru" : "nereușită") + (p.ora ? ", la " + p.ora : "") + (p.timp ? ", " + p.timp : "")) : "niciuna încă");
  paragraf("acum-din-nou", a.chei_din_nou);
  paragraf("acum-lipsa", a.lipsa_text);
  var gata = a.gata || [];
  arata($("acum-principal-bloc"), gata.length > 0);
  $("acum-principal").textContent = gata.length ? "Serviciul principal: " + (a.serviciu_nume || a.serviciu || "-") + ". Traducerea pleacă întâi la el, apoi la rezerve, în ordine." : "";
  puneAlte(gata, a.rezerve || []);
  arata($("acum-proba"), !!(p && p.original));
  if(p){
    var eroare = p.stare === "eroare";
    $("acum-proba-original").textContent = p.original || "";
    $("acum-proba-eticheta").textContent = eroare ? "Eroarea" : "Traducerea";
    var t = $("acum-proba-traducere");
    t.textContent = p.stare === "lucru" ? "Se traduce..." : (p.traducere || "");
    t.classList.toggle("eroare", eroare);
    t.classList.toggle("traducere-sub", p.stare === "ok");
  }
}
function puneAlte(gata, rezerve){
  var cheieA = JSON.stringify([gata, rezerve]);
  if(cheieA === alteAfisate){ return; }
  alteAfisate = cheieA;
  var cutie = $("acum-alte"); sterge(cutie);
  var coduri = rezerve.map(function(r){ return r.cod; });
  gata.forEach(function(g){
    var div = document.createElement("div"); div.className = "gasit";
    var p = document.createElement("p");
    var b = document.createElement("strong"); b.textContent = String(g.nume || g.cod || ""); p.appendChild(b);
    var i = coduri.indexOf(g.cod);
    var t = document.createElement("span"); t.className = "nota"; t.textContent = i === -1 ? " (nu e în lista rezervelor)" : " (rezerva " + (i + 1) + ")"; p.appendChild(t);
    div.appendChild(p);
    var bt = document.createElement("button"); bt.type = "button"; bt.className = "mare"; bt.id = "principal-" + g.cod; bt.textContent = "Fă-l principal";
    bt.addEventListener("click", function(){ faPrincipal(g.cod, bt, scriePrincipal); });
    div.appendChild(bt);
    cutie.appendChild(div);
  });
}
function scriePrincipal(text, eroare){ var m = $("mesaj-principal"); m.textContent = text || ""; m.classList.toggle("eroare", !!eroare); arata(m, !!text); }
function scrieRezultat(text, eroare){ mesaj("mesaj-rezultat", text, eroare); }
function faPrincipal(cod, buton, scrie){
  scrie("Se salvează...", false);
  if(buton){ buton.disabled = true; }
  var q = new URLSearchParams(); q.set("principal", cod);
  cerere("/api/traducere-subtitrari-seteaza", "POST", q).then(function(d){
    if(buton){ buton.disabled = false; }
    scrie(d.message || (d.result ? "Salvat." : "Nu s-a schimbat nimic."), !d.result);
    return improspateaza();
  }).catch(function(){ if(buton){ buton.disabled = false; } scrie("Receptorul nu răspunde.", true); });
}
function alege(c){
  ales = c;
  ALEGERI.forEach(function(k){
    var b = $("alege-" + k);
    b.classList.toggle("ales", k === c);
    b.setAttribute("aria-pressed", k === c ? "true" : "false");
  });
  arata($("card-cheie"), !!CU_CHEIE[c]);
  arata($("card-casa"), c === "casa");
  if(CU_CHEIE[c]){ puneCheie(c); } else { puneCasa(); }
  var card = $(c === "casa" ? "card-casa" : "card-cheie");
  if(card.scrollIntoView){ card.scrollIntoView({behavior: "smooth", block: "start"}); }
}
function puneCheie(c){
  var s = (ultim.servicii || {})[c] || {};
  var auto = c === "auto";
  $("cheie-titlu").textContent = auto ? "2. Lipește cheia" : "2. Cheia pentru " + (s.nume || c);
  paragraf("cheie-avertisment", auto ? "" : s.avertisment);
  arata($("cheie-pagina-bloc"), !auto);
  arata($("cheie-auto-nota"), auto);
  legatura($("cheie-pagina"), auto ? "" : s.pagina_cheie);
  lista($("cheie-pasi"), auto ? [] : s.pasi_scurti);
  lista($("cheie-toti-pasi"), s.pasi || []);
  paragraf("cheie-cota", s.cota ? "Cât e gratuit: " + s.cota : "");
  paragraf("cheie-depasire", s.depasire ? "La depășire: " + s.depasire : "");
  arata($("cheie-toti"), !auto && !!(s.pasi && s.pasi.length));
  arata($("regiune-bloc"), c === "azure");
  if(c === "azure"){ umple($("alege-regiune"), regiuni(ultim.regiuni_azure), ""); }
  arata($("cont-bloc"), c === "cloudflare");
  if(c === "cloudflare" && !$("cont-cloudflare").value){ $("cont-cloudflare").value = (ultim.acum || {}).cont_cloudflare || ""; }
  mesaj("mesaj-cheie", "");
}
function puneCasa(){
  var s = ultim.servicii || {};
  legatura($("instalare-ollama"), (s.openai || {}).pagina_cheie || (s.openai || {}).sursa);
  legatura($("instalare-libre"), (s.libre || {}).pagina_cheie || (s.libre || {}).sursa);
}
function eRetea(c){
  if(c.fel){ return c.fel === "retea" || c.fel === "termen"; }
  return /rețe|internet|nu răspunde/i.test((c.mesaj || "") + " " + (c.ce_faci || ""));
}
function textIncercat(x){
  if(typeof x === "string"){ return [x, ""]; }
  if(x && x.length !== undefined){ return [String(x[0]), typeof x[1] === "number" ? secunde(x[1]) : String(x[1] || "")]; }
  x = x || {};
  var nume = x.model || x.nume || x.serviciu_nume || x.serviciu || "";
  var timp = typeof x.ms === "number" ? secunde(x.ms) : (x.timp || "");
  if(x.eroare || x.mesaj){ timp = (timp ? timp + ", " : "") + (x.eroare || x.mesaj); }
  else if(x.ok === false){ timp = (timp ? timp + ", " : "") + "nu a mers"; }
  return [String(nume), String(timp)];
}
function puneRezultat(){
  var c = ultim.configurare || {};
  var u = urmarite.configurare;
  var st = c.stare;
  if(u && u.idVechi !== undefined && c.id === u.idVechi && st !== "lucru"){ st = "lucru"; }
  arata($("card-rezultat"), !!st && st !== "nimic");
  arata($("rez-lucru"), st === "lucru");
  arata($("rez-ok"), st === "ok");
  arata($("rez-eroare"), st === "eroare");
  arata($("rez-regiune"), st === "regiune");
  if(st === "lucru"){
    $("rez-pas").textContent = c.stare === "lucru" && c.pas ? c.pas : "Se pornește proba...";
    $("rez-rabdare").textContent = (c.pas_fel === "incarcare" || /încarc/i.test(c.pas || "")) ? "Încărcarea modelului poate dura până la un minut." : "Proba durează de obicei câteva secunde.";
  }
  if(st === "ok"){
    var p = c.proba;
    var server = !!c.adresa && (c.serviciu === "libre" || c.serviciu === "openai");
    var rezerva = !!c.rezerva, acumServ = (ultim.acum || {}).serviciu;
    $("rez-titlu").textContent = rezerva ? "Gata. Cheia e salvată ca rezervă." : (p ? (server ? "Gata. Serverul merge." : "Gata. Cheia merge.") : "Gata. Cheia e salvată.");
    arata($("rez-rezerva-bloc"), rezerva);
    $("rez-rezerva").textContent = !rezerva ? "" : (acumServ === c.serviciu ? (c.serviciu_nume || c.serviciu) + " e acum serviciul principal." : (c.mesaj || ""));
    arata($("rez-fa-principal"), rezerva && !!c.serviciu && acumServ !== c.serviciu);
    ["rez-original", "rez-original-et", "rez-traducere", "rez-traducere-et"].forEach(function(id){ arata($(id), !!p); });
    $("rez-original").textContent = p ? (p.original || "") : "";
    $("rez-traducere").textContent = p ? (p.traducere || "") : "";
    $("rez-serviciu").textContent = c.afisat || c.serviciu_nume || c.serviciu || "";
    $("rez-model").textContent = c.model || "";
    arata($("rez-model"), !!c.model); arata($("rez-model-et"), !!c.model);
    var timp = p ? secunde(typeof p.ms === "number" ? p.ms : c.ms) : "";
    $("rez-timp").textContent = timp;
    arata($("rez-timp"), !!timp); arata($("rez-timp-et"), !!timp);
    var ms = p ? (typeof p.ms === "number" ? p.ms : c.ms) : null;
    var lent = !!p && (!!c.lent || (typeof ms === "number" && ms > PRAG_LENT_MS));
    arata($("rez-lent-bloc"), lent);
    $("rez-lent").textContent = lent ? (c.sfat_lent || ((server ? "Serverul" : "Serviciul") + " e prea lent pentru subtitrări la timp: proba a durat " + secunde(ms) + ", deci traducerea va apărea după original. Folosește un serviciu din internet (Gemini e gratuit, fără card) sau un model mai mic.")) : "";
    arata($("lent-gemini"), lent && c.serviciu !== "gemini");
    arata($("lent-model"), lent && (c.modele || []).length > 1);
    var inc = c.incercate || [];
    arata($("rez-incercate"), inc.length > 1);
    var tb = $("rez-incercate-rand"); sterge(tb);
    inc.forEach(function(x){
      var t = textIncercat(x), r = document.createElement("tr");
      t.forEach(function(v){ var td = document.createElement("td"); td.textContent = v; r.appendChild(td); });
      tb.appendChild(r);
    });
    var modele = c.modele || [];
    arata($("rez-modele-bloc"), modele.length > 0);
    var sm = $("rez-modele");
    if(document.activeElement !== sm){ umple(sm, modele.map(function(m){ return [m, m]; }), c.model || ""); }
    arata($("rez-pornit"), !!c.salvat && !rezerva);
    arata($("rez-gemini"), c.serviciu === "gemini" && !rezerva);
    var rz = (ultim.acum || {}).rezerve;
    arata($("rez-rezerve-bloc"), !!rz);
    $("rez-rezerve").textContent = rz ? textRezerve(rz, "Rezervele: ", "Fără rezerve.") : "";
    paragraf("rez-mesaj-ok", [p || rezerva ? "" : (c.mesaj || ""), (p || rezerva) ? (c.nota_rezerve || "") : "", c.ce_faci || ""].filter(Boolean).join(" ").trim());
  }
  if(st === "eroare"){
    $("rez-mesaj").textContent = c.mesaj || "Proba nu a reușit.";
    $("rez-ce-faci").textContent = c.ce_faci || "";
  }
  if(st === "regiune"){
    $("rez-regiune-mesaj").textContent = [c.mesaj || "", c.ce_faci || ""].join(" ").trim() || "Cheia cere regiunea resursei Azure.";
    var sr = $("rez-regiuni");
    if(document.activeElement !== sr){
      var l = regiuni(c.regiuni && c.regiuni.length ? c.regiuni : ultim.regiuni_azure).filter(function(r){ return r[0] !== ""; });
      umple(sr, l, sr.value);
    }
  }
  var detalii = (st === "eroare" || st === "regiune") ? textDetalii(c) : "";
  arata($("rez-detalii"), !!detalii);
  $("rez-detalii-text").textContent = detalii;
  var retea = st === "eroare" && eRetea(c) && (lucrareMea === "cheie" || (!lucrareMea && !!CU_CHEIE[c.serviciu]));
  arata($("din-nou"), st === "regiune" || retea);
  arata($("regiune-reincearca"), st === "regiune");
  arata($("fara-proba"), retea);
  arata($("fara-proba-nota"), retea);
}
function puneCautare(){
  var c = ultim.cautare || {};
  var g = c.gasite || [];
  var lucru = c.stare === "lucru" || (!!urmarite.cautare && c.stare !== "gata");
  $("cauta").disabled = lucru;
  if(lucru){
    mesaj("cauta-progres", "Caut în rețeaua " + (c.retea || "de acasă") + ": " + (c.progres || 0) + " din " + (c.total || "...") + ".");
  } else if(c.stare === "gata"){
    mesaj("cauta-progres", g.length ? (g.length === 1 ? "Am găsit un server." : "Am găsit " + g.length + " servere.") : "");
  } else {
    mesaj("cauta-progres", c.mesaj || "");
  }
  var cheieG = JSON.stringify(g);
  if(cheieG !== gasiteAfisate){ gasiteAfisate = cheieG; puneGasite(g); }
  var negasit = c.stare === "gata" && !g.length;
  arata($("negasit"), negasit);
  if(negasit){
    $("negasit-titlu").textContent = c.mesaj || "Nu am găsit niciun server în rețea.";
    var aj = $("ajutor"); sterge(aj);
    var texte = c.ajutor ? (typeof c.ajutor === "string" ? c.ajutor.split("\n") : c.ajutor) : AJUTOR_PROVIZORIU;
    var ul = document.createElement("ul"); ul.className = "lista";
    texte.forEach(function(t){ if(String(t).trim()){ var li = document.createElement("li"); li.textContent = String(t); ul.appendChild(li); } });
    aj.appendChild(ul);
    puneCasa();
  }
}
function puneGasite(g){
  var cutie = $("gasite"); sterge(cutie);
  g.forEach(function(s, i){
    var div = document.createElement("div"); div.className = "gasit";
    var p = document.createElement("p");
    var b = document.createElement("strong"); b.textContent = NUME_FEL[s.fel] || String(s.fel || ""); p.appendChild(b);
    var t = document.createElement("span"); t.textContent = " la " + (s.adresa || ""); p.appendChild(t);
    div.appendChild(p);
    var sel = null;
    if(s.fel === "ollama"){
      var modele = s.modele || [];
      if(modele.length){
        var lab = document.createElement("label"); lab.textContent = "Modelul"; lab.setAttribute("for", "gasit-model-" + i); div.appendChild(lab);
        sel = document.createElement("select"); sel.id = "gasit-model-" + i;
        umple(sel, modele.map(function(m){ return [m, m]; }), s.model_ales || "");
        div.appendChild(sel);
        var n = document.createElement("p"); n.className = "nota"; n.textContent = s.model_ales ? "Ales de receptor: " + s.model_ales + ". Îl poți schimba." : "Alege modelul."; div.appendChild(n);
      } else {
        var n0 = document.createElement("p"); n0.className = "nota"; n0.textContent = "Serverul nu are niciun model descărcat. Descarcă unul pe calculator (vezi toate setările), apoi caută din nou."; div.appendChild(n0);
      }
    } else if(s.fel === "libre"){
      var l = document.createElement("p"); l.className = "nota"; l.textContent = "Limbi: " + ((s.limbi || []).join(", ") || "necunoscute"); div.appendChild(l);
      var a = document.createElement("p"); a.className = "nota"; a.textContent = s.are_tinta ? "Are limba traducerii tale." : "Nu are limba traducerii tale: pornește-l și cu limba ta."; div.appendChild(a);
    }
    var bt = document.createElement("button"); bt.type = "button"; bt.className = "mare principal"; bt.id = "gasit-foloseste-" + i; bt.textContent = "Folosește-l";
    bt.addEventListener("click", function(){
      var q = new URLSearchParams();
      q.set("serviciu", FEL_SERVER[s.fel] || "openai"); q.set("adresa", s.adresa || "");
      var m = sel ? sel.value : (s.model_ales || "");
      if(m){ q.set("model", m); }
      pornesteLucrare("/api/traducere-configurare-server", q, "mesaj-casa", "server", bt);
    });
    div.appendChild(bt);
    cutie.appendChild(div);
  });
}
function pornesteLucrare(cale, q, unde, fel, buton){
  mesaj(unde, "Se trimite...");
  if(buton){ buton.disabled = true; }
  var idVechi = (ultim.configurare || {}).id;
  cerere(cale, "POST", q).then(function(d){
    if(buton){ buton.disabled = false; }
    mesaj(unde, d.message || "", !d.result);
    if(d.result){
      lucrareMea = fel;
      urmarite.configurare = {idVechi: idVechi, start: Date.now()};
      mesaj("mesaj-rezultat", "");
    }
    if(d.acum){ puneTot(d); }
    if(d.result){
      var card = $("card-rezultat");
      if(card.scrollIntoView){ card.scrollIntoView({behavior: "smooth", block: "start"}); }
      continua();
    }
  }).catch(function(){ if(buton){ buton.disabled = false; } mesaj(unde, "Receptorul nu răspunde.", true); });
}
function seLucreaza(fel){
  var c = (ultim || {})[fel] || {}, u = urmarite[fel];
  if(!u){ return false; }
  if(fel === "configurare"){ return c.stare === "lucru" || (u.idVechi !== undefined && c.id === u.idVechi); }
  return c.stare !== "gata" && (c.stare === "lucru" || !u.vazut);
}
function termen(fel){
  var c = (ultim || {})[fel] || {}, u = urmarite[fel];
  if(fel === "cautare"){ return CAUTARE_MAX_MS; }
  if(c.pas_fel === "incarcare" || /încarc/i.test(c.pas || "")){ u.lung = true; }
  return u.lung ? URMARIRE_MODEL_MS : URMARIRE_MAX_MS;
}
function continua(){
  var lucreaza = false;
  ["configurare", "cautare"].forEach(function(fel){
    var u = urmarite[fel];
    if(!u){ return; }
    if(!seLucreaza(fel)){ urmarite[fel] = null; return; }
    if(Date.now() - u.start > termen(fel)){
      urmarite[fel] = null;
      if(fel === "configurare"){ mesaj("mesaj-rezultat", "Receptorul încă lucrează. Reîncarcă pagina peste puțin timp ca să vezi rezultatul.", true); }
      else { mesaj("cauta-progres", "Căutarea durează prea mult. Încearcă din nou.", true); $("cauta").disabled = false; }
      return;
    }
    lucreaza = true;
  });
  puneRezultat();
  puneCautare();
  if(lucreaza && cronometru === null){ cronometru = setTimeout(pas, URMARIRE_MS); }
}
function pas(){
  cronometru = null;
  improspateaza().then(function(){ continua(); }).catch(function(){ continua(); });
}
function improspateaza(){
  return cerere("/api/traducere-configurare").then(function(d){
    if(d.result){
      if(urmarite.cautare && d.cautare && d.cautare.stare === "lucru"){ urmarite.cautare.vazut = true; }
      puneTot(d);
    }
    return d;
  });
}
function trimiteCheie(v, serviciu, regiune, faraProba, unde, buton, cont){
  var q = new URLSearchParams();
  q.set("cheie", v); q.set("serviciu", serviciu);
  if(regiune){ q.set("regiune", regiune); }
  if(cont){ q.set("cont", cont); }
  if(faraProba){ q.set("fara_proba", "1"); }
  pornesteLucrare("/api/traducere-configurare-cheie", q, unde, "cheie", buton);
}
function ascundeCheia(id, buton){ $(id).type = "password"; $(buton).textContent = "Arată"; $(buton).setAttribute("aria-pressed", "false"); }
function comutaArata(id, buton){
  var i = $(id), arat = i.type === "password";
  i.type = arat ? "text" : "password";
  $(buton).textContent = arat ? "Ascunde" : "Arată";
  $(buton).setAttribute("aria-pressed", arat ? "true" : "false");
}
function cheiaDinCamp(id, buton, unde){
  var i = $(id), v = i.value.trim();
  if(!v){ mesaj(unde, "Lipește întâi cheia.", true); if(i.focus){ i.focus(); } return ""; }
  i.value = "";
  ascundeCheia(id, buton);
  return v;
}
ALEGERI.forEach(function(k){ $("alege-" + k).addEventListener("click", function(){ alege(k); }); });
$("cheie-arata").addEventListener("click", function(){ comutaArata("cheie", "cheie-arata"); });
$("cheie-din-nou-arata").addEventListener("click", function(){ comutaArata("cheie-din-nou", "cheie-din-nou-arata"); });
$("cheie-trimite").addEventListener("click", function(){
  var v = cheiaDinCamp("cheie", "cheie-arata", "mesaj-cheie");
  if(!v){ return; }
  trimiteCheie(v, CU_CHEIE[ales] ? ales : "auto", ales === "azure" ? $("alege-regiune").value : "", false, "mesaj-cheie", $("cheie-trimite"), ales === "cloudflare" ? $("cont-cloudflare").value.trim() : "");
});
$("cheie").addEventListener("keydown", function(e){ if(e && e.key === "Enter"){ $("cheie-trimite").click(); } });
$("regiune-reincearca").addEventListener("click", function(){
  var v = cheiaDinCamp("cheie-din-nou", "cheie-din-nou-arata", "mesaj-rezultat");
  if(!v){ return; }
  trimiteCheie(v, "azure", $("rez-regiuni").value, false, "mesaj-rezultat", $("regiune-reincearca"));
});
$("fara-proba").addEventListener("click", function(){
  var v = cheiaDinCamp("cheie-din-nou", "cheie-din-nou-arata", "mesaj-rezultat");
  if(!v){ return; }
  var c = ultim.configurare || {};
  var serv = CU_CHEIE[c.serviciu] ? c.serviciu : (CU_CHEIE[ales] ? ales : "auto");
  trimiteCheie(v, serv, serv === "azure" ? (c.regiune || "") : "", true, "mesaj-rezultat", $("fara-proba"), serv === "cloudflare" ? $("cont-cloudflare").value.trim() : "");
});
$("lent-gemini").addEventListener("click", function(){ alege("gemini"); });
$("lent-model").addEventListener("click", function(){
  var s = $("rez-modele");
  if(s.scrollIntoView){ s.scrollIntoView({behavior: "smooth", block: "center"}); }
  if(s.focus){ s.focus(); }
});
$("rez-fa-principal").addEventListener("click", function(){
  var c = ultim.configurare || {};
  if(c.serviciu){ faPrincipal(c.serviciu, $("rez-fa-principal"), scrieRezultat); }
});
$("rez-model-trimite").addEventListener("click", function(){
  var m = $("rez-modele").value;
  if(!m){ mesaj("mesaj-rezultat", "Alege un model.", true); return; }
  var q = new URLSearchParams(); q.set("model", m);
  pornesteLucrare("/api/traducere-configurare-model", q, "mesaj-rezultat", "model", $("rez-model-trimite"));
});
$("cauta").addEventListener("click", function(){
  mesaj("cauta-progres", "Se pornește căutarea...");
  $("cauta").disabled = true;
  cerere("/api/traducere-configurare-cauta", "POST", new URLSearchParams()).then(function(d){
    if(d.result){ urmarite.cautare = {start: Date.now(), vazut: !!(d.cautare && d.cautare.stare === "lucru")}; gasiteAfisate = ""; }
    if(d.acum){ puneTot(d); }
    if(!d.result){ mesaj("cauta-progres", d.message || "Căutarea nu a pornit.", true); $("cauta").disabled = false; }
    else { continua(); }
  }).catch(function(){ mesaj("cauta-progres", "Receptorul nu răspunde.", true); $("cauta").disabled = false; });
});
$("server-trimite").addEventListener("click", function(){
  var a = $("server-adresa").value.trim();
  if(!a){ mesaj("mesaj-casa", "Scrie adresa calculatorului, de exemplu 192.168.1.50.", true); return; }
  var q = new URLSearchParams();
  q.set("serviciu", $("server-fel").value); q.set("adresa", a);
  var m = $("server-model").value.trim();
  if(m){ q.set("model", m); }
  pornesteLucrare("/api/traducere-configurare-server", q, "mesaj-casa", "server", $("server-trimite"));
});
document.addEventListener("visibilitychange", function(){
  if(ultim && document.visibilityState === "visible" && cronometru === null){ improspateaza().then(continua).catch(function(){}); }
});
function alegereDinAdresa(){
  var m = /[?&]serviciu=([a-z]+)/.exec((typeof location !== "undefined" && location.search) || "");
  if(!m){ return null; }
  var c = m[1] === "libre" || m[1] === "openai" ? "casa" : m[1];
  return ALEGERI.indexOf(c) === -1 ? null : c;
}
function citeste(){
  cerere("/api/traducere-configurare").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi starea."; return; }
    ultim = {};
    arata($("incarcare"), false); arata($("continut"), true);
    puneTot(d);
    if((d.configurare || {}).stare === "lucru"){ urmarite.configurare = {start: Date.now()}; }
    if((d.cautare || {}).stare === "lucru"){ urmarite.cautare = {start: Date.now(), vazut: true}; }
    var c = alegereDinAdresa();
    if(c){ alege(c); }
    continua();
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
citeste();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
TEXTE_PAGINA = {
	"html": (
		N_("Configurarea traducerii"),
		N_("Traducerea subtitrărilor: configurare pas cu pas"),
		N_("Alegi serviciul, lipești cheia (sau alegi serverul din casă), iar receptorul o probează pe loc."),
		N_("Se citește starea..."),
		N_("Acum pe receptor"),
		N_("Originalul"),
		N_("Traducerea"),
		N_("1. Alege serviciul"),
		N_("Azure Translator"),
		N_("Recomandat pentru subtitrări zilnice"),
		N_("2 milioane de caractere pe lună, gratuit (planul Free F0). Cardul se cere la înscriere numai "
			"pentru verificare; pe F0 nu se plătește nimic. După 30 de zile contul trece pe „Pay as you go”, "
			"fără cost cât rămâi pe F0."),
		N_("Gemini"),
		N_("Cel mai simplu de pornit, fără card; se poate opri dacă te uiți mult"),
		N_("Cheia o faci cu contul tău Google. La subtitrări continue poate da „prea multe cereri”."),
		N_("Serverul din casa ta"),
		N_("Fără limită, mai lent pe calculatoarele obișnuite"),
		N_("LibreTranslate sau Ollama pe un calculator din casă. Nimic nu iese din casă."),
		N_("Am deja o cheie"),
		N_("O lipești, iar receptorul recunoaște singur serviciul."),
		N_("DeepL API"),
		N_("Plan gratuit Developer: 1.000.000 de caractere, o singură dată."),
		N_("Groq"),
		N_("Gratuit și rapid; limită pe zi, ajunge pentru câteva filme"),
		N_("Cheia o faci cu emailul sau cu contul tău Google. Pune și o rezervă pentru zilele cu multe "
			"subtitrări."),
		N_("Cloudflare Workers"),
		N_("Gratuit; ajunge pentru câteva filme pe zi"),
		N_("Din panoul Cloudflare iei un jeton și ID-ul contului."),
		N_("Google Cloud Translation"),
		N_("Cere card; peste cota gratuită plătești automat."),
		N_("Pentru subtitrări multe (filme întregi, zilnic) e recomandat Azure Translator, planul Free F0: "
			"2 milioane de caractere pe lună; cardul se cere numai la înscriere, iar pe F0 nu se plătește "
			"nimic. Gemini e gratuit pentru folosire ocazională, dar la subtitrări continue poate da „prea "
			"multe cereri” după câteva minute."),
		N_("„Adresă proprie” (alt serviciu, cu adresa lui) și toate celelalte setări sunt pe pagina cu "
			"toate setările:"),
		N_("Toate setările traducerii"),
		N_("2. Cheia"),
		N_("Deschide pagina cheii"),
		N_("Apoi întoarce-te aici și lipește cheia."),
		N_("Toți pașii și cât e gratuit"),
		N_("Lipește cheia oricărui serviciu: Gemini, DeepL, Azure, Google Cloud, Groq, OpenRouter sau "
			"OpenAI. Receptorul recunoaște singur serviciul și o probează."),
		N_("Lipește cheia"),
		N_("Arată"),
		N_("Regiunea resursei Azure"),
		N_("Regiunea o găsești în portal, la resursa Translator: Overview › Location. Dacă nu știi, lasă "
			"„Automat”."),
		N_("ID-ul contului Cloudflare"),
		N_("32 de litere și cifre, din panoul Cloudflare, la Account ID."),
		N_("Verifică și salvează"),
		N_("Cheia pleacă numai spre receptor, se păstrează criptată și nu se mai arată niciodată."),
		N_("2. Serverul din casa ta"),
		N_("Pe un calculator din casă rulează LibreTranslate sau Ollama. Receptorul îl caută în rețeaua de "
			"acasă, alege singur modelul și face proba."),
		N_("Caută în rețeaua de acasă"),
		N_("Nu am găsit niciun server în rețea."),
		N_("Instalarea Ollama (pagina oficială)"),
		N_("Instalarea LibreTranslate (pagina oficială)"),
		N_("Scriu eu adresa (pentru cine vrea)"),
		N_("Felul serverului"),
		N_("Ollama sau alt server compatibil OpenAI"),
		N_("LibreTranslate"),
		N_("Adresa calculatorului"),
		N_("Ajunge adresa IP; portul îl pune receptorul (11434 la Ollama, 5000 la LibreTranslate)."),
		N_("Modelul (numai la Ollama; gol = îl alege receptorul)"),
		N_("Folosește adresa"),
		N_("3. Proba"),
		N_("Proba durează de obicei câteva secunde."),
		N_("Gata. Cheia merge."),
		N_("Fă-l principal"),
		N_("Folosește Gemini (gratuit, fără card)"),
		N_("Alege un model mai mic"),
		N_("Serviciul"),
		N_("Modelul"),
		N_("Timpul"),
		N_("Modelele încercate"),
		N_("Alt model"),
		N_("Folosește modelul ales"),
		N_("Traducerea e pornită; pe televizor a apărut confirmarea."),
		N_("Gemini e gratuit pentru folosire ocazională, dar la subtitrări continue poate da „prea multe "
			"cereri” după câteva minute. Pentru subtitrări multe (filme întregi, zilnic) e recomandat Azure "
			"Translator, planul Free F0 (2 milioane de caractere pe lună, fără plată)."),
		N_("Dacă serviciul cade (cota terminată, prea multe cereri), receptorul trece singur la următorul "
			"din lista rezervelor."),
		N_("Lista rezervelor, în toate setările"),
		N_("Regiunea resursei"),
		N_("Regiunea o găsești în portal, la resursa Translator: Overview › Location."),
		N_("Detalii"),
		N_("Din siguranță, receptorul nu păstrează cheia până nu merge: lipește-o din nou."),
		N_("Lipește din nou cheia"),
		N_("Încearcă din nou cu regiunea aleasă"),
		N_("Salvează cheia fără probă"),
		N_("Dacă știi că cheia e bună și receptorul nu ajunge acum la serviciu, o poți salva fără probă."),
		N_("Panoul receptorului"),
		N_("Aceleași setări sunt pe televizor, în __DRUM_MENIU__."),
		N_("lipește cheia aici"),
	),
	"js": (
		N_("Calculatorul trebuie să fie pornit, cu Ollama, LM Studio sau LibreTranslate pornit."),
		N_("Ollama răspunde implicit numai pe calculatorul lui. În aplicația Ollama (Windows sau Mac) "
			"pornește în setări expunerea în rețea, sau pune variabila OLLAMA_HOST cu valoarea 0.0.0.0:11434 "
			"și pornește din nou Ollama."),
		N_("LM Studio: în fila „Developer” pornește serverul și bifează „Serve on Local Network”."),
		N_("LibreTranslate trebuie pornit cu --host 0.0.0.0 (în Docker cu -p 5000:5000)."),
		N_("Paravanul calculatorului (Windows Firewall) poate bloca porturile 11434 sau 5000: lasă "
			"aplicația să primească legături din rețeaua privată."),
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Automat"),
		N_("codul"),
		N_("Serviciul"),
		N_("Cheia"),
		N_("pusă"),
		N_("lipsește"),
		N_("Adresa"),
		N_("Modelul"),
		N_("Traducerea"),
		N_("pornită"),
		N_("oprită"),
		N_("Rezervele"),
		N_("Ultima probă"),
		N_("reușită"),
		N_("în lucru"),
		N_("nereușită"),
		N_(", la"),
		N_("niciuna încă"),
		N_("Serviciul principal:"),
		N_(". Traducerea pleacă întâi la el, apoi la rezerve, în ordine."),
		N_("Eroarea"),
		N_("Se traduce..."),
		N_("(nu e în lista rezervelor)"),
		N_("Fă-l principal"),
		N_("Se salvează..."),
		N_("Salvat."),
		N_("Nu s-a schimbat nimic."),
		N_("Receptorul nu răspunde."),
		N_("2. Lipește cheia"),
		N_("2. Cheia pentru"),
		N_("Cât e gratuit:"),
		N_("La depășire:"),
		N_("nu a mers"),
		N_("Se pornește proba..."),
		N_("Încărcarea modelului poate dura până la un minut."),
		N_("Proba durează de obicei câteva secunde."),
		N_("Gata. Cheia e salvată ca rezervă."),
		N_("Gata. Serverul merge."),
		N_("Gata. Cheia merge."),
		N_("Gata. Cheia e salvată."),
		N_("e acum serviciul principal."),
		N_("Serverul"),
		N_("e prea lent pentru subtitrări la timp: proba a durat"),
		N_(", deci traducerea va apărea după original. Folosește un serviciu din internet (Gemini e "
			"gratuit, fără card) sau un model mai mic."),
		N_("Rezervele:"),
		N_("Fără rezerve."),
		N_("Proba nu a reușit."),
		N_("Cheia cere regiunea resursei Azure."),
		N_("Caut în rețeaua"),
		N_("de acasă"),
		N_("din"),
		N_("Am găsit un server."),
		N_("Am găsit"),
		N_("servere."),
		N_("Nu am găsit niciun server în rețea."),
		N_("Ales de receptor:"),
		N_(". Îl poți schimba."),
		N_("Alege modelul."),
		N_("Serverul nu are niciun model descărcat. Descarcă unul pe calculator (vezi toate setările), apoi "
			"caută din nou."),
		N_("Limbi:"),
		N_("Are limba traducerii tale."),
		N_("Nu are limba traducerii tale: pornește-l și cu limba ta."),
		N_("Folosește-l"),
		N_("Se trimite..."),
		N_("Receptorul încă lucrează. Reîncarcă pagina peste puțin timp ca să vezi rezultatul."),
		N_("Căutarea durează prea mult. Încearcă din nou."),
		N_("Arată"),
		N_("Ascunde"),
		N_("Lipește întâi cheia."),
		N_("Alege un model."),
		N_("Se pornește căutarea..."),
		N_("Căutarea nu a pornit."),
		N_("Scrie adresa calculatorului, de exemplu 192.168.1.50."),
		N_("Receptorul nu a putut citi starea."),
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
