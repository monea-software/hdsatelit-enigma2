# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# traducere_subtitrari_web.py: „Traducerea subtitrărilor” in interfata web (HdsWebControl), perechea ecranului de pe
# televizor (Screens/HdsTraducereSubtitrari.py) pentru traducerea automata a subtitrarilor text (teletext, fisiere si
# textul citit din subtitrarile DVB). Tot aici, ca pe televizor: „Tradu bara de jos” (bara: titlurile emisiunii de acum
# si urmatoare de pe bara de jos, cu traducerea pornita), „Tradu EPG” (epg) si contorul ghidului, din
# Components/HdsTraducereEpg.py (starea are bara, bara_activ si traducere_pornita); "Tradu teletextul" (teletext),
# "Teletextul tradus" (teletext_mod), "Tradu HbbTV" (hbbtv) si contorul lor, din Components/HdsTraducereTexte.py
# (starea "texte_tradus"; zero cu ce=texte).
#
# O SINGURA LOGICA: setarile (config.hds_traducere), serviciile, cheile, proba, contorul, instructiunile si textul de
# confidentialitate vin din Components/HdsTraducereSubtitrari.py, exact ce foloseste ecranul. Notificarile puse de
# modul pe setari leaga singure nucleul (eSubtitleWidget) la orice schimbare salvata de aici.
#
# CHEILE: se pot numai scrie si sterge. Raspunsurile spun doar daca un serviciu are cheie (chei().stare()), niciodata
# cheia; cheia se primeste NUMAI din corpul unei cereri POST: scrisa in adresa (care ramane in istoricul browserului
# si in jurnale) e refuzata si nu se salveaza. Twisted amesteca in request.args argumentele din adresa cu cele din
# corp, deci adresa se citeste separat, din request.uri. Cheia unui server (LibreTranslate, compatibil OpenAI, adresa
# proprie) se leaga de adresa salvata atunci si pleaca numai spre ea (T.cheiePentru): o adresa schimbata de aici
# spre alt server nu primeste cheia veche. Cat timp fisierul cheilor a fost pus deoparte la pornire (nu se mai putea
# citi pe acest receptor), starea are chei_din_nou (T.textCheiDinNou), aratat langa cheie, ca pe televizor.
#
# Rute (toate prin poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat;
# ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/traducere-subtitrari              valorile, alegerile, ce cere fiecare serviciu, care serviciu are cheie,
#                                               ce lipseste, confidentialitatea, instructiunile tuturor serviciilor si
#                                               starea traducatorului (contorul, proba, pauza)
#   POST /api/traducere-subtitrari-seteaza      oricare dintre valori (si rezerve=cod,cod in ordine); o valoare rea
#                                               refuza tot (nimic schimbat); principal=<cod> singur: „Fă-l principal”
#   POST /api/traducere-subtitrari-cheie        corpul: serviciu=<cod>&cheie=<cheia> (cheie goala = stearsa); la
#                                               serviciu=propriu cheia e valoarea antetului adresei proprii
#   POST /api/traducere-subtitrari-proba        porneste „Probează traducerea”; rezultatul vine in starea din GET
#   POST /api/traducere-subtitrari-zero         contorul pus la zero
#   GET  /traducere-subtitrari                  pagina
#
# SERVICIILE apar in ordinea din T.SERVICII (Azure primul, cel din fabrica), cu eticheta scurta (T.ETICHETE) sub
# alegere; avertismentul platii automate (Google Cloud) se arata sub alegerea serviciului si inaintea pasilor din
# instructiuni.
#
# ADRESA PROPRIE (propriu): randurile ei (adresa-sablon, metoda, corpul, felul corpului, numele antetului, felul
# raspunsului, calea) se vad numai cand e aleasa; corpul si felul lui numai la POST, calea numai la raspuns JSON.
# Valoarea antetului e campul parola al cheii (ruta cheii, serviciu=propriu). La salvare se refuza o adresa rea (schema,
# nume si parola, spatii, locuri in numele serverului, http in afara casei, adresa receptorului insusi: T.clasaAdresa,
# la fel si la adresele LibreTranslate / compatibil OpenAI, cu mesajul tradus din modul), un nume de antet sau o cale
# rea, un corp prea lung sau cu caractere de control; lipsa lui {text} si corpul JSON stricat le spune „ce lipseste”
# (campurile se salveaza pe rand, deci nu se pot cere toate deodata). Corpul se pastreaza pe un singur rand
# (T.curataCorp).
# SERVICIILE DE REZERVA: lista in ordine (config.hds_traducere.rezerve, T.rezerve / T.rezerveValide), cu Sus, Jos,
# Scoate si Adauga (numai serviciile care nu sunt deja in lant), salvata prin seteaza (rezerve=cod,cod); starea
# fiecaruia (merge, asteapta, oprit dupa refuzurile cheii, oprit pana la schimbarea setarilor, nefolosit pentru
# campuri lipsa) si contorul (pe rezerva, randurile fiecarui serviciu, trecerile) vin din stare(); starea
# principalului sta langa numele lui. SERVICIILE OPRITE dupa refuzurile cheii (stare()["oprite"]: ce s-a
# intamplat si ce faci, texte gata traduse din modul, ca mesajul de pe televizor) se arata in cardul probei.
# GROQ SI CLOUDFLARE WORKERS: modelul (model_groq, model_cloudflare; modelele propuse din T.MODELE_GROQ si
# T.MODELE_CLOUDFLARE in lista campului) si, la Cloudflare, ID-ul contului (cont_cloudflare, 32 de semne hex, verificat
# la salvare cu T.contCloudflareBun, ca pe televizor).
# REGIUNEA Azure se alege dintr-o lista (T.REGIUNI_AZURE, cu Global); o valoare veche din afara listei ramane
# aratata ca atare. La proba: Detalii (codul exact al erorii) si regiunea gasita singura. Contorul: La timp, in
# asteptare = traducerea a venit cat ecranul astepta gol (originalul nu s-a vazut); Traduse dupa afisare = numai
# cand originalul chiar s-a vazut.
# Sus, legatura spre pagina pas cu pas (/traducere-configurare). Traducerea (proba, ultimele pagini) se
# scrie in culoarea traducerii afisate sub original pe televizor (#fff3b0, lib/gui/esubtitle.cpp), originalul alb.
#
# SERVICIUL PRINCIPAL: sus in cardul rezervelor „Serviciul principal: ...”; langa fiecare serviciu gata (starea
# „gata”, T.serviciiGata: campurile complete) butonul „Fă-l principal”, in lista rezervelor si sub ea pentru cele gata
# care nu sunt in lista. Butonul trimite principal=<cod> la seteaza, singur in cerere (T.punePrincipal: principalul nou
# iese din rezerve, fostul intra primul; salvat pe loc). Pagina pas cu pas (/traducere-configurare) trimite la fel.
# LIMBA: mesajele raspunsurilor (refuzul unei valori, „Salvat.”), felurile erorilor, starea cheii si textele noi
# ale paginii (randul „Tradu bara de jos”, starea lui din cardul ghidului) trec prin _t (traducerea enigma2, limba
# meniului), ca mesajul sa fie intr-o singura limba si cand sfatul vine tradus din modul (T.textMotivAdresa). Numele
# campurilor din mesajul de refuz sunt cele de pe televizor (deja traduse). Textele paginii vin in starea GET
# („texte”); scriptul le pune peste cele romanesti din HTML (care raman pentru cine nu are limba).
# STAREA CHEII: din T.stareCheie, ca pe televizor: „Cheie pusă pentru alt server (gazda): nu pleacă...” cand cheia
# e legata de alta adresa decat cea de acum (cheie_oprita), cu clasa de avertisment. Nota „trebuie puse din nou” e
# rosie numai la serviciile care cer cheie; la celelalte, o nota blanda, galbena.
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2 (reactorul e bucla enigma2); apelurile sunt scurte, proba
# merge pe firul ei (in modul). Fisierul nu importa nimic la incarcare: probele de pe PC dau modulul lor (T).

MAX_TEXT = 300            # regiunea, adresele, modelele, calea adresei proprii
MAX_ADRESA_PROPRIE = 500  # adresa-sablon a adresei proprii
MAX_CHEIE_BRUT = 2048     # cheia lipita, cu spatii si randuri noi; modulul o curata si o refuza peste 512 caractere
MAX_VALOARE = 4096        # orice argument citit (peste, tot refuzat)
MAX_ARGUMENTE = 32
CONTOR_WEB_S = 5
PROBA_WEB_S = 15          # cat urmareste pagina o proba
PROBA_GARDA_S = 20        # o proba „in lucru” mai veche de atat nu mai opreste una noua

ALEGERI = ("serviciu", "limba", "afisare", "tarziu", "citire", "propriu_metoda", "propriu_tip_corp", "propriu_raspuns",
	"teletext_mod")
DA_NU = ("pornit", "dvb", "bara", "epg", "teletext", "hbbtv")
TEXTE = ("regiune", "adresa_libre", "adresa_openai", "model_gemini", "model_openai", "model_groq", "model_cloudflare",
	"cont_cloudflare")
ADRESE = ("adresa_libre", "adresa_openai")
TEXTE_PROPRIU = ("propriu_adresa", "propriu_corp", "propriu_antet", "propriu_cale")
CHEI_VALORI = ("pornit", "serviciu", "limba", "afisare", "tarziu", "citire", "dvb", "bara", "epg") + TEXTE + \
	("propriu_metoda", "propriu_tip_corp", "propriu_raspuns") + TEXTE_PROPRIU + ("teletext", "teletext_mod", "hbbtv")

def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele se traduc la folosire, cu _t."""
	return text


NUME_CAMP = {
	"pornit": N_("Traducerea automată"), "serviciu": N_("Serviciul"), "limba": N_("Limba traducerii"),
		"afisare": N_("Afișarea"),
	"tarziu": N_("Traducerea care întârzie"), "citire": N_("Timpul de citire"), "dvb": N_("Și subtitrările DVB"),
	"regiune": N_("Regiunea"),
	"adresa_libre": N_("Adresa serverului LibreTranslate"), "adresa_openai": N_("Adresa serverului compatibil OpenAI"),
	"model_gemini": N_("Modelul Gemini"), "model_openai": N_("Modelul serverului compatibil OpenAI"),
	"model_groq": N_("Modelul Groq"), "model_cloudflare": N_("Modelul Cloudflare Workers"),
	"cont_cloudflare": N_("ID-ul contului Cloudflare"),
	"propriu_adresa": N_("Adresa-șablon"), "propriu_metoda": N_("Metoda"), "propriu_corp": N_("Corpul cererii"),
	"propriu_tip_corp": N_("Felul corpului"), "propriu_antet": N_("Numele antetului"), "propriu_raspuns": N_("Felul "
		"răspunsului"),
	"propriu_cale": N_("Calea traducerii"), "rezerve": N_("Serviciile de rezervă"), "bara": N_("Tradu bara de jos"),
	"epg": N_("Tradu EPG"), "principal": N_("Serviciul principal"), "teletext": N_("Tradu teletextul"),
	"teletext_mod": N_("Teletextul tradus"), "hbbtv": N_("Tradu HbbTV"),
}


# de ce nu e buna lista rezervelor (T.rezerveValide)
SFAT_REZERVE = {
	"necunoscut": N_("Lista rezervelor are un serviciu necunoscut."),
	"dublura": N_("Un serviciu apare de două ori în lista rezervelor."),
	"principal": N_("Serviciul ales nu intră și în lista rezervelor."),
}
# starea unui serviciu din lant (T.instanta().stareLant)
TEXT_STARE_SERVICIU = {"merge": N_("gata"), "setari": N_("oprit până schimbi setările"), "lipsa": N_("nu se folosește")}
# ce se adauga la mesajul unei valori refuzate a adresei proprii
SFAT_PROPRIU = {
	"adresa_gresita": N_("Adresa-șablon începe cu https:// (sau http:// pentru un server din rețeaua de acasă), fără "
		"spații, fără nume și parolă și fără locuri în numele serverului."),
	"propriu_http": N_("O adresă http:// merge numai pentru un server din rețeaua de acasă (de exemplu 192.168.1.50); "
		"pentru un server de pe internet scrie https://."),
	"propriu_antet": N_("Numele antetului are numai litere, cifre și - _ . (de exemplu Authorization); Host, "
		"Content-Type și Content-Length nu se pot alege."),
	"propriu_cale": N_("Calea are chei și numere despărțite prin punct, fără spații (de exemplu "
		"data.translations.0.translatedText)."),
	"propriu_corp": N_("Corpul are cel mult %d de semne, fără caractere de control."),
}

# felurile erorilor (Components/HdsTraducereSubtitrari.FELURI_EROARE) -> cum le scrie pagina
TEXT_EROARE = {"cheie": N_("cheie refuzată"), "cota": N_("cota terminată"), "retea": N_("fără rețea"),
	"termen": N_("prea lent"), "raspuns": N_("răspuns neașteptat"), "limba": N_("limbă netradusă"),
	"lipsa": N_("lipsă date"), "adresa": N_("adresă refuzată")}
# de unde a venit o traducere din „ultimele”
TEXT_DE_UNDE = {"memorie": N_("memorie"), "serviciu": N_("serviciu"), "rezerva": N_("rezervă"), "sarita": N_("sărită")}

_PROBA_PORNITA = [None]   # time.monotonic() la ultima proba pornita de aici
# numele unor campuri in mesajul de refuz: eticheta de pe televizor (deja tradusa) si serviciul ei
NUME_CAMP_TV = {
	"pornit": N_("Traducerea subtitrărilor"), "dvb": N_("Și subtitrările DVB (imagini)"),
	"regiune": N_("Regiunea (numai dacă resursa nu e Global)"), "propriu_adresa": N_("Adresa (șablon)"),
	"propriu_corp": N_("Corpul cererii (șablon)"), "propriu_antet": N_("Numele antetului (opțional)"),
	"propriu_cale": N_("Calea traducerii în răspuns"),
}
NUME_CAMP_SERVICIU = {
	"adresa_libre": (N_("Adresa serverului"), N_("LibreTranslate")), "adresa_openai": (N_("Adresa serverului"),
		N_("OpenAI")),
	"model_gemini": (N_("Modelul"), N_("Gemini")), "model_openai": (N_("Modelul"), N_("OpenAI")),
}


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins, cautata la fiecare apel), sau textul insusi fara ea (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def numeCamp(camp):
	"""numele campului in mesajul de refuz, tradus (eticheta de pe televizor)"""
	if camp in NUME_CAMP_SERVICIU:
		eticheta, serviciu = NUME_CAMP_SERVICIU[camp]
		return "%s (%s)" % (_t(eticheta), serviciu)
	return _t(NUME_CAMP_TV.get(camp) or NUME_CAMP[camp])


def textEroare(fel, necunoscut=None):
	"""numele felului unei erori, tradus; un fel necunoscut da `necunoscut` (implicit chiar felul)"""
	return _t(TEXT_EROARE.get(fel, (fel or "") if necunoscut is None else necunoscut))


def texte_pagina():
	"""textele paginii care se schimba dupa limba receptorului; scriptul le pune peste cele romanesti din HTML"""
	return {
		"bara": _t("Tradu bara de jos"),
		"bara_nota": _t("Traduce titlurile emisiunii de acum și ale celei următoare de pe bara de jos, cu aceleași "
			"servicii și chei. Merge când traducerea subtitrărilor e pornită și folosește foarte puțin din cotă: "
			"fiecare titlu se cere o singură dată. INFO de pe bară arată textul original. Cu „Tradu EPG” pornită, bara "
			"se traduce oricum."),
		"bara_prin_epg": _t("se traduce prin „Tradu EPG”"),
		"bara_oprita": _t("oprită"),
		"bara_fara_traducere": _t("pornită, dar traducerea automată e oprită"),
		"bara_pornita": _t("pornită"),
		"bara_necompletat": _t("pornită, dar serviciul nu e completat"),
		"principal": _t("Serviciul principal"),
		"fa_principal": _t("Fă-l principal"),
		"alte_gata": _t("Alte servicii gata de folosit, care nu sunt în lista rezervelor:"),
		"teletext": _t("Tradu teletextul"),
		"teletext_nota": _t(
			"Traduce paginile de teletext pe care le deschizi (tasta TEXT) în limba traducerii, cu aceleași "
			"servicii și chei. Pagina apare întâi în original, apoi tradusă. În teletext, AUDIO arată originalul "
			"paginii, iar MENU are aceleași alegeri. Consumă din cota serviciului, de aceea din fabrică e oprită; "
			"un text tradus o dată nu se mai cere."),
		"teletext_mod": _t("Teletextul tradus"),
		"teletext_mod_nota": _t(
			"În pagină: rândurile traduse iau locul celor originale, în cele 40 de coloane ale paginii, cu "
			"aceleași culori; ce nu încape se taie cu „…”. Într-un panou: pagina originală, mai mică, în stânga, "
			"și traducerea întreagă în dreapta."),
		"hbbtv": _t("Tradu HbbTV"),
		"hbbtv_nota": _t(
			"Traduce textele văzute din aplicațiile HbbTV (tasta ROȘIE), ca „Traduce pagina” din browsere: numai "
			"textele de pe ecran, nu adresele, codul sau câmpurile de scris. Pagina apare întâi în original. "
			"Consumă din cota serviciului, de aceea din fabrică e oprită. Aplicațiile deschise pe https rămân "
			"deocamdată în original."),
		"texte_titlu": _t("Ce s-a tradus din teletext și HbbTV"),
	}


def _epg(E=None):
	"""Components.HdsTraducereEpg (traducerea ghidului), modulul dat de probe, sau None"""
	if E is not None:
		return E
	try:
		from Components import HdsTraducereEpg
		return HdsTraducereEpg
	except Exception:
		return None


def _stareEpg(E=None):
	"""starea traducerii ghidului pentru pagina (contorul separat), sau None"""
	E = _epg(E)
	if E is None:
		return None
	st = dict(E.instanta().stare())
	c = dict(st.get("contor") or {})
	erori = c.get("erori") or {}
	c["erori_lista"] = [[f, textEroare(f), n] for f, n in sorted(erori.items()) if n]
	c["timp_mediu"] = _secunde(c.get("ms_mediu"))
	c["de_la_ora"] = _oraDin(c.get("de_la"))
	c["ultimele"] = [dict(p, timp=_secunde(p.get("ms"))) for p in c.get("ultimele") or []]
	if c.get("ultima_eroare"):
		c["ultima_eroare"] = dict(c["ultima_eroare"])
		c["ultima_eroare"]["fel_text"] = textEroare(c["ultima_eroare"].get("fel"), "")
	st["contor"] = c
	return st


def _texte(X=None):
	"""Components.HdsTraducereTexte (teletextul si HbbTV), modulul dat de probe, sau None"""
	if X is not None:
		return X
	try:
		from Components import HdsTraducereTexte
		return HdsTraducereTexte
	except Exception:
		return None


def _stareTexte(X=None):
	"""starea traducerii teletextului si a HbbTV pentru pagina: {fel: {pornit, activ, memorie, pe_disc, contor}}"""
	X = _texte(X)
	if X is None:
		return None
	rez = {}
	for fel in X.FELURI:
		st = dict(X.stare(fel))
		c = dict(st.get("contor") or {})
		c.pop("ultimele", None)
		c["timp_mediu"] = _secunde(c.get("ms_mediu"))
		c["de_la_ora"] = _oraDin(c.get("de_la"))
		if c.get("ultima_eroare"):
			c["ultima_eroare"] = dict(c["ultima_eroare"])
			c["ultima_eroare"]["fel_text"] = textEroare(c["ultima_eroare"].get("fel"), "")
		rez[fel] = {"pornit": st.get("pornit"), "activ": st.get("activ"), "memorie": st.get("memorie"),
			"pe_disc": st.get("pe_disc"), "contor": c}
	return rez


def _tr(T=None):
	"""Components.HdsTraducereSubtitrari (sau modulul dat de probe)"""
	if T is not None:
		return T
	from Components import HdsTraducereSubtitrari
	return HdsTraducereSubtitrari


def _secunde(ms):
	return None if ms is None else ("%.2f s" % (ms / 1000.0)).replace(".", ",")


def _durata(secunde):
	secunde = int(secunde or 0)
	if secunde >= 60:
		return "%d min %d s" % (secunde // 60, secunde % 60) if secunde % 60 else "%d min" % (secunde // 60)
	return "%d s" % secunde


def _oraDin(de_la):
	if not de_la:
		return None
	import time
	try:
		return time.strftime("%H:%M", time.localtime(de_la))
	except (TypeError, ValueError, OverflowError, OSError):
		return None


def _optiuni(element):
	"""[[cod, text]] dintr-un ConfigSelection, in ordinea lui"""
	return [[c, element.description[c]] for c in element.choices]


def valori(s, T=None):
	T = _tr(T)
	return {
		"pornit": bool(s.pornit.value), "serviciu": s.serviciu.value, "limba": s.limba.value,
		"afisare": s.afisare.value, "tarziu": s.tarziu.value, "dvb": bool(s.dvb.value),
		"regiune": s.regiune.value or "", "adresa_libre": s.adresa_libre.value or "",
		"adresa_openai": s.adresa_openai.value or "", "model_gemini": s.model_gemini.value or "",
		"model_openai": s.model_openai.value or "",
		"model_groq": _valoare(s, "model_groq", "") or "",
		"model_cloudflare": _valoare(s, "model_cloudflare", "") or "",
		"cont_cloudflare": _valoare(s, "cont_cloudflare", "") or "",
		"propriu_adresa": s.propriu_adresa.value or "", "propriu_metoda": s.propriu_metoda.value,
		"propriu_corp": s.propriu_corp.value or "", "propriu_tip_corp": s.propriu_tip_corp.value,
		"propriu_antet": s.propriu_antet.value or "", "propriu_raspuns": s.propriu_raspuns.value,
		"propriu_cale": s.propriu_cale.value or "",
		"rezerve": list(T.rezerve(s)),
		"bara": bool(_valoare(s, "bara", True)),
		"epg": bool(_valoare(s, "epg", False)),
		"citire": _valoare(s, "citire", "normal"),
		"teletext": bool(_valoare(s, "teletext", False)),
		"teletext_mod": _valoare(s, "teletext_mod", "pagina"),
		"hbbtv": bool(_valoare(s, "hbbtv", False)),
	}


def _valoare(s, camp, implicit):
	"""valoarea unei setari care poate lipsi (ConfigSubsection da KeyError, nu AttributeError)"""
	try:
		return getattr(s, camp).value
	except (KeyError, AttributeError):
		return implicit


def alegeri(T, s):
	"""Alegerile, ca pe televizor; „Limba meniului” spune si limba de acum a meniului."""
	try:
		meniu = "%s (%s)" % (s.limba.description["meniu"], T.numeLimba(T.limbaMeniului()))
	except Exception:
		meniu = s.limba.description["meniu"]
	return {
		# cu unde lucreaza fiecare: (pe internet) sau (local), dupa adresa pusa (T.numeCuLoc); din ele si lista
		# rezervelor, Adauga un serviciu si randul serviciului principal din pagina
		"serviciu": [[c, T.numeCuLoc(c, s) if hasattr(T, "numeCuLoc") else T.numeServiciu(c)] for c in T.SERVICII],
		"limba": [["meniu", meniu]] + [[c, T.numeLimba(c)] for c, n in T.LIMBI_TINTA],
		"afisare": _optiuni(s.afisare),
		"tarziu": _optiuni(s.tarziu),
		"citire": _optiuni(s.citire),
		"propriu_metoda": _optiuni(s.propriu_metoda),
		"propriu_tip_corp": _optiuni(s.propriu_tip_corp),
		"propriu_raspuns": _optiuni(s.propriu_raspuns),
		"teletext_mod": _optiuni(s.teletext_mod) if _valoare(s, "teletext_mod", None) is not None else [],
	}


def _stareTraducator(T):
	"""instanta().stare() cu textele gata facute pentru pagina (timpii in secunde cu virgula, numele erorilor);
	dictionarele din modul nu se schimba"""
	st = dict(T.instanta().stare())
	c = dict(st.get("contor") or {})
	erori = c.get("erori") or {}
	c["erori_lista"] = [[f, textEroare(f), erori[f]] for f in T.FELURI_EROARE if erori.get(f)]
	c["timp_mediu"] = _secunde(c.get("ms_mediu"))
	c["timp_max"] = _secunde(c.get("ms_max"))
	c["de_la_ora"] = _oraDin(c.get("de_la"))
	ultimele = []
	for p in c.get("ultimele") or []:
		q = dict(p)
		q["timp"] = _secunde(p.get("ms"))
		q["de_unde_text"] = (_t(TEXT_DE_UNDE[p.get("de_unde")]) if p.get("de_unde") in TEXT_DE_UNDE else
			(p.get("de_unde") or ""))
		ultimele.append(q)
	c["ultimele"] = ultimele
	if c.get("ultima_eroare"):
		c["ultima_eroare"] = dict(c["ultima_eroare"])
		c["ultima_eroare"]["fel_text"] = textEroare(c["ultima_eroare"].get("fel"), "")
	nume = dict((cod, T.numeServiciu(cod)) for cod in T.SERVICII)
	c["pe_servicii_lista"] = [[cod, nume[cod], (c.get("pe_servicii") or {})[cod]] for cod in T.SERVICII
		if (c.get("pe_servicii") or {}).get(cod)]
	treceri = []
	for t in c.get("treceri") or []:
		q = dict(t)
		q["text"] = _t("%s: de la %s la %s (%s%s)") % (t.get("ora", ""), nume.get(t.get("de_la"), t.get("de_la")),
			nume.get(t.get("la"), t.get("la")), textEroare(t.get("motiv"), t.get("motiv") or ""),
			_t(", limita pe zi") if t.get("pe_zi") else "")
		treceri.append(q)
	c["treceri"] = treceri
	lant = []
	for x in st.get("lant") or []:
		q = dict(x)
		if x.get("stare") == "asteapta":
			q["stare_text"] = _t("așteaptă încă %s (%s)") % (_durata(x.get("asteapta_s")),
				textEroare(x.get("motiv"), ""))
		elif x.get("stare") == "lipsa":
			q["stare_text"] = _t("nu se folosește: %s") % (x.get("lipsa_text") or _t("lipsesc câmpuri"))
		elif x.get("stare") == "setari":
			q["stare_text"] = "%s (%s)" % (_t(TEXT_STARE_SERVICIU["setari"]), textEroare(x.get("motiv"), ""))
		elif x.get("stare") == "refuzat":
			q["stare_text"] = _t("oprit: cheia refuzată de %d ori la rând") % (x.get("refuzuri_oprire") or
				x.get("refuzuri") or 0)
		else:
			q["stare_text"] = _t(TEXT_STARE_SERVICIU.get(x.get("stare"), ""))
		lant.append(q)
	st["lant"] = lant
	st["contor"] = c
	if st.get("proba"):
		p = dict(st["proba"])
		p.pop("laRezultat", None)
		p["timp"] = _secunde(p.get("ms"))
		st["proba"] = p
	st["pauza_text"] = _durata(st.get("pauza_s")) if st.get("pauza_s") else ""
	# serviciile oprite dupa refuzurile cheii: textul intreg (ce s-a intamplat, ce faci), ca pe televizor
	st["oprite_text"] = u" ".join(u"%s %s" % (o.get("text") or u"", o.get("ce_faci") or u"")
		for o in st.get("oprite") or [])
	return st


def stare(T=None):
	"""Pentru GET /api/traducere-subtitrari (si raspunsul celorlalte rute, cu „message”). Fara nicio cheie: din
	configuratie (care are cheia) pleaca numai textul celor lipsa si al confidentialitatii."""
	T = _tr(T)
	s = T.initConfig()
	cfg = T.configuratia(s)
	fel_cheie, text_cheie = T.stareCheie(cfg) if hasattr(T, "stareCheie") else ("", "")
	din_nou = T.textCheiDinNou() if hasattr(T, "textCheiDinNou") else ""
	cere_cheie = "cheie" in T.CERE.get(cfg["serviciu"], ())
	return {
		"result": True,
		"valori": valori(s, T),
		"regiuni": [[c, _t("Global") if not c else "%s (%s)" % (n, c)] for c, n in getattr(T, "REGIUNI_AZURE", ())],
		"alegeri": alegeri(T, s),
		"cere": dict((c, list(T.CERE.get(c, ()))) for c in T.SERVICII),
		"chei": T.chei().stare(),
		"chei_din_nou": din_nou,
		"chei_din_nou_bland": (T.textCheiDinNouBland() if hasattr(T, "textCheiDinNouBland") else "") if din_nou and
			not cere_cheie else "",
		"cheie_oprita": cfg.get("cheie_oprita") or "",
		"cheie_fel": fel_cheie,
		"cheie_text": text_cheie,
		"texte": texte_pagina(),
		"lipsa_text": T.textCeLipseste(cfg),
		"confidentialitate": T.textConfidentialitate(cfg),
		"instructiuni": dict((c, T.instructiuni(c)) for c in T.SERVICII),
		"feluri_eroare": [[f, textEroare(f)] for f in T.FELURI_EROARE],
		"implicite": {"model_gemini": getattr(T, "MODEL_GEMINI_IMPLICIT", ""),
			"model_groq": getattr(T, "MODEL_GROQ_IMPLICIT", ""),
			"model_cloudflare": getattr(T, "MODEL_CLOUDFLARE_IMPLICIT", "")},
		# modelele propuse la Groq si la Cloudflare Workers (lista de sub camp, in pagina)
		"modele_propuse": {"groq": list(getattr(T, "MODELE_GROQ", ())),
			"cloudflare": list(getattr(T, "MODELE_CLOUDFLARE", ()))},
		"stare": _stareTraducator(T),
		"epg": _stareEpg(),
		"texte_tradus": _stareTexte(),
		"gata": list(T.serviciiGata(s)) if hasattr(T, "serviciiGata") else [],
	}


def _cuMesaj(T, rezultat, mesaj):
	d = stare(T)
	d["result"] = rezultat
	d["message"] = mesaj
	return d


def textBun(v):
	"""cel mult MAX_TEXT caractere, fara caractere de control"""
	if len(v) > MAX_TEXT:
		return False
	return not any(ord(c) < 32 or 127 <= ord(c) < 160 or c in u"  " for c in v)


def regiuneBuna(v):
	"""regiunea resursei Azure: litere, cifre, liniute (de exemplu westeurope)"""
	return all((c.isalnum() and ord(c) < 128) or c in "-_" for c in v)


def corpBun(v):
	"""corpul-sablon primit din pagina: randuri noi si tab-uri permise (se fac spatii), alte caractere de control nu"""
	return not any((ord(c) < 32 and c not in u"\r\n\t") or 127 <= ord(c) < 160 for c in v)


def motivPropriu(T, camp, v):
	"""o valoare a adresei proprii (deja fara spatii la capete): "" daca e buna, altfel cheia din SFAT_PROPRIU"""
	if not v:
		return ""
	if camp == "propriu_adresa":
		if len(v) > MAX_ADRESA_PROPRIE:
			return "adresa_gresita"
		return T.motivAdresaPropriu(v)
	if camp == "propriu_antet":
		return "" if T.numeAntetBun(v) else "propriu_antet"
	if camp == "propriu_cale":
		return "" if textBun(v) and T.caleBuna(v) else "propriu_cale"
	if camp == "propriu_corp":
		return "" if corpBun(v) and len(T.curataCorp(v)) <= T.MAX_CORP_PROPRIU else "propriu_corp"
	return ""


def _sfat(T, motiv, valoare=""):
	"""ce se adauga la mesajul unei valori refuzate: SFAT_PROPRIU tradus; adresa receptorului insusi cu textul tradus
	din modul (acelasi ca pe televizor)"""
	if motiv == "adresa_receptor":
		return T.textMotivAdresa(motiv, valoare)
	return _t(SFAT_PROPRIU[motiv]) % T.MAX_CORP_PROPRIU if motiv == "propriu_corp" else _t(SFAT_PROPRIU[motiv])


def _principal(argumente, T, s, configfile=None):
	"""„Fă-l principal” (principal=<cod>, singur in cerere): T.punePrincipal, apoi serviciul si rezervele salvate"""
	if any(camp in argumente for camp in CHEI_VALORI + ("rezerve",)):
		return _cuMesaj(T, False, _t("Valoare greșită pentru: %s.") % numeCamp("principal") + " " +
			_t("Nu s-a schimbat nimic."))
	inainte = (s.serviciu.value, s.rezerve.value)
	reusit, mesaj = T.punePrincipal(argumente["principal"], s)
	if not reusit:
		return _cuMesaj(T, False, mesaj)
	if (s.serviciu.value, s.rezerve.value) != inainte:
		s.serviciu.save()
		s.rezerve.save()
		if configfile is None:
			from Components.config import configfile
		configfile.save()
	return _cuMesaj(T, True, mesaj)


def seteaza(argumente, T=None, configfile=None):
	"""POST /api/traducere-subtitrari-seteaza: numai cheile date; toate se verifica INAINTE de orice schimbare (un
	ConfigSelection primit cu o valoare necunoscuta ar pune tacut valoarea implicita); o valoare rea refuza tot.
	principal=<cod> e o cerere aparte („Fă-l principal”, _principal)."""
	T = _tr(T)
	s = T.initConfig()
	if "principal" in argumente:
		return _principal(argumente, T, s, configfile)
	noi = {}
	rele = []
	sfaturi = []
	adresa_rea = False		# o adresa LibreTranslate / compatibil OpenAI cu forma rea (nu a receptorului insusi)
	for camp in CHEI_VALORI:
		if camp not in argumente:
			continue
		v = argumente[camp]
		if camp in TEXTE_PROPRIU:
			v = v.strip()
			motiv = motivPropriu(T, camp, v)
			if motiv:
				rele.append(camp)
				sfat = _sfat(T, motiv, v)
				if sfat not in sfaturi:
					sfaturi.append(sfat)
			else:
				noi[camp] = T.curataCorp(v) if camp == "propriu_corp" else v
		elif camp in ALEGERI:
			if v in list(getattr(s, camp).choices):
				noi[camp] = v
			else:
				rele.append(camp)
		elif camp in DA_NU:
			if v in ("0", "1"):
				noi[camp] = v == "1"
			else:
				rele.append(camp)
		else:
			v = v.strip()
			if camp == "cont_cloudflare":
				v = v.lower()
			if not textBun(v) or (camp in ADRESE and v and not T.adresaBuna(v)) or \
					(camp == "regiune" and not regiuneBuna(v)):
				rele.append(camp)
				adresa_rea = adresa_rea or camp in ADRESE
			elif camp == "cont_cloudflare" and v and not T.contCloudflareBun(v):
				# ID-ul contului Cloudflare: 32 de semne hex (textul campului, ca pe televizor)
				rele.append(camp)
				sfat = _t("Pentru %s lipsește: %s.") % (T.numeServiciu("cloudflare"), _t(T._TEXT_CAMP["cont_gresit"]))
				if sfat not in sfaturi:
					sfaturi.append(sfat)
			elif camp in ADRESE and v and T.clasaAdresa(v) == T.RECEPTOR:
				rele.append(camp)
				sfat = _sfat(T, "adresa_receptor", v)
				if sfat not in sfaturi:
					sfaturi.append(sfat)
			else:
				noi[camp] = v
	if "rezerve" in argumente:
		lista, eroare, rau = T.rezerveValide(argumente["rezerve"], noi.get("serviciu", s.serviciu.value))
		if eroare:
			rele.append("rezerve")
			sfaturi.append(_t(SFAT_REZERVE[eroare]))
		else:
			noi["rezerve"] = ",".join(lista)
	if rele:
		mesaj = _t("Valoare greșită pentru: %s.") % ", ".join(numeCamp(c) for c in rele)
		if adresa_rea:
			mesaj += " " + _t("Adresa începe cu http:// sau https://, fără nume și parolă în ea.")
		for sfat in sfaturi:
			mesaj += " " + sfat
		return _cuMesaj(T, False, mesaj + " " + _t("Nu s-a schimbat nimic."))
	if not noi:
		return _cuMesaj(T, False, _t("Nu s-a trimis nicio alegere."))
	for camp in CHEI_VALORI + ("rezerve",):
		if camp in noi:
			element = s.rezerve if camp == "rezerve" else getattr(s, camp)
			if element.value != noi[camp]:
				element.value = noi[camp]
	for camp in noi:
		(s.rezerve if camp == "rezerve" else getattr(s, camp)).save()
	if configfile is None:
		from Components.config import configfile
	configfile.save()
	return _cuMesaj(T, True, _t("Salvat."))


def _raspunsCheie(T, rezultat, mesaj):
	"""raspunsul rutei cheii: niciodata cheia, numai care serviciu are una"""
	return {"result": rezultat, "message": mesaj, "chei": T.chei().stare()}


def cheie(argumente, din_adresa, T=None):
	"""POST /api/traducere-subtitrari-cheie. `din_adresa` = numele argumentelor scrise in adresa."""
	T = _tr(T)
	if "cheie" in din_adresa:
		return _raspunsCheie(T, False, _t("Cheia nu se trimite în adresă: adresa rămâne în istoricul browserului și în "
			"jurnale. Trimite-o în corpul cererii POST. Nu s-a salvat nimic."))
	serviciu = argumente.get("serviciu", "")
	if serviciu not in T.SERVICII:
		return _raspunsCheie(T, False, _t("Serviciu necunoscut. Nu s-a schimbat nimic."))
	if "cheie" not in argumente:
		return _raspunsCheie(T, False, _t("Lipsește câmpul „cheie” (gol înseamnă ștergerea cheii). Nu s-a schimbat "
			"nimic."))
	valoare = argumente["cheie"]
	if len(valoare) > MAX_CHEIE_BRUT:
		return _raspunsCheie(T, False, _t("Cheia e prea lungă. Nu s-a schimbat nimic."))
	reusit, mesaj = T.chei().schimba(serviciu, valoare)
	return _raspunsCheie(T, bool(reusit), mesaj)


def proba(T=None):
	"""POST /api/traducere-subtitrari-proba: porneste proba si raspunde pe loc; pagina urmareste starea din GET."""
	import time
	T = _tr(T)
	t = T.instanta()
	p = t.ultima_proba or {}
	if p.get("stare") == "lucru" and _PROBA_PORNITA[0] is not None and \
			time.monotonic() - _PROBA_PORNITA[0] < PROBA_GARDA_S:
		return _cuMesaj(T, True, _t("Proba merge deja; rezultatul vine în câteva secunde."))
	_PROBA_PORNITA[0] = time.monotonic()
	if t.proba():
		return _cuMesaj(T, True, "Proba a pornit.")
	return _cuMesaj(T, False, (t.ultima_proba or {}).get("traducere") or _t("Proba nu a putut porni."))


def contorLaZero(T=None, ce="", E=None, X=None):
	"""POST /api/traducere-subtitrari-zero[?ce=epg|texte]: contorul subtitrarilor, al ghidului (ce=epg) sau al
	teletextului si HbbTV (ce=texte)"""
	T = _tr(T)
	if ce == "texte":
		X = _texte(X)
		if X is not None:
			for fel in X.FELURI:
				X.instanta(fel).puneContorulLaZero()
		return _cuMesaj(T, True, _t("Contorul e pus la zero."))
	if ce == "epg":
		E = _epg(E)
		if E is not None:
			E.instanta().puneContorulLaZero()
		return _cuMesaj(T, True, _t("Contorul ghidului e pus la zero."))
	T.instanta().puneContorulLaZero()
	return _cuMesaj(T, True, _t("Contorul e pus la zero."))


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


def rute(baza, resource, T=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py; T e modulul
	dat de probe (implicit Components.HdsTraducereSubtitrari, incarcat la prima cerere)."""

	class StareResource(baza):
		"""GET /api/traducere-subtitrari: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(T))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class _Schimba(baza):
		schimbaCeva = True

		def fa(self, request):
			raise NotImplementedError

		def render_POST(self, request):
			try:
				return self._raspunde(request, self.fa(request))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class SeteazaResource(_Schimba):
		def fa(self, request):
			return seteaza(argumente(request), T)

	class ProbaResource(_Schimba):
		def fa(self, request):
			return proba(T)

	class ZeroResource(_Schimba):
		def fa(self, request):
			return contorLaZero(T, argumente(request).get("ce", ""))

	class CheieResource(baza):
		"""POST /api/traducere-subtitrari-cheie: numai POST, cheia numai din corp; eroarea nu repeta nimic primit."""
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, cheie(argumente(request), cheiDinAdresa(request), T))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor (%s).") % eroare.__class__.__name__, 500)

		def render_GET(self, request):
			return self._eroare(request, _t("Cheia se trimite numai cu POST, în corpul cererii. Nu s-a salvat nimic."),
				405)

	class PaginaResource(resource.Resource):
		"""GET /traducere-subtitrari: pagina „Traducerea subtitrărilor”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"traducere-subtitrari": StareResource(),
		b"traducere-subtitrari-seteaza": SeteazaResource(),
		b"traducere-subtitrari-cheie": CheieResource(),
		b"traducere-subtitrari-proba": ProbaResource(),
		b"traducere-subtitrari-zero": ZeroResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /subtitrari: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; un browser
	neconectat primeste pagina de asociere. Pagina schimba ceva pe receptor, deci cu cookie primeste tokenul CSRF."""
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
		_drumMeniu("hds_traducere_subtitrari")).replace("__CONTOR_MS__", str(CONTOR_WEB_S * 1000)).replace(
		"__PROBA_MS__", str(PROBA_WEB_S * 1000)).replace("__MAX_CORP__", str(MAX_CORP_WEB)).replace(
		"__MAX_ADRESA__", str(MAX_ADRESA_PROPRIE))


MAX_CORP_WEB = 1000       # = T.MAX_CORP_PROPRIU (fisierul nu importa modulul la incarcare)


# Tot ce vine de la receptor (texte de subtitrari, erori, instructiuni) se pune numai cu textContent; adresa sursei
# instructiunilor numai daca incepe cu http:// sau https://.
PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Traducerea subtitrărilor</title>
<style>__STIL_COMUN__
  main{max-width:760px;margin:0 auto;overflow-wrap:anywhere;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  h2{font-size:1rem;margin:0 0 4px;color:var(--text-slab);font-weight:600;}
  h3{font-size:1rem;margin:10px 0 6px;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:14px 16px;margin:0 0 12px;}
  .rand{display:grid;grid-template-columns:1fr minmax(150px,330px);gap:8px 10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--bordura);}
  .rand label{font-size:.98rem;}
  .rand select,.rand input{min-height:44px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;width:100%;min-width:0;}
  .rand .tot{grid-column:1/-1;}
  .rand textarea{min-height:88px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;width:100%;min-width:0;resize:vertical;}
  a.configurare{display:inline-flex;align-items:center;min-height:44px;padding:10px 14px;margin:0 0 12px;border-radius:8px;border:1px solid var(--bordura);background:var(--panou);color:var(--text);font-weight:600;text-decoration:none;max-width:100%;}
  .butoane{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0 0;}
  .rand .butoane{margin:0;}
  button{min-height:44px;padding:10px 14px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;cursor:pointer;}
  button:disabled{opacity:.55;cursor:default;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .rand .nota{margin:0;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .avertisment{color:#f0c674;background:rgba(240,198,116,.12);border:1px solid rgba(240,198,116,.45);border-radius:8px;padding:8px 10px;margin:10px 0 0;line-height:1.45;}
  .traducere-sub{color:#fff3b0;}
  .lipsa{color:#ffb4a8;background:rgba(192,57,43,.14);border:1px solid rgba(192,57,43,.45);border-radius:8px;padding:8px 10px;margin:10px 0 0;line-height:1.45;}
  .cheie-pusa{color:#8fd19e;} .cheie-lipsa{color:#f0c674;}
  .ascuns{display:none !important;}
  dl.valori{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;margin:8px 0;font-size:.92rem;}
  dl.valori dt{color:var(--text-slab);} dl.valori dd{margin:0;}
  ol.pasi{margin:6px 0;padding:0 0 0 22px;line-height:1.5;}
  ol.pasi li{margin:0 0 4px;}
  ol.pasi li .butoane{margin:6px 0 4px;}
  ul.alte{margin:6px 0;padding:0 0 0 22px;line-height:1.5;}
  ul.alte li .butoane{margin:6px 0 4px;}
  ul.erori{margin:6px 0;padding:0 0 0 18px;line-height:1.5;font-size:.92rem;}
  a.sursa{display:inline-block;padding:12px 0;}
  .tabel{overflow-x:auto;margin:8px 0 0;}
  .tabel table{border-collapse:collapse;width:100%;font-size:.85rem;}
  .tabel th,.tabel td{text-align:left;padding:5px 6px;border-bottom:1px solid var(--bordura);vertical-align:top;}
  .tabel th{color:var(--text-slab);font-weight:600;}
  .tabel td.text{min-width:9em;}
  .tabel td.fix{white-space:nowrap;}
  @media (max-width:520px){ .rand{grid-template-columns:1fr;gap:6px;}
    dl.valori.lung{grid-template-columns:1fr;gap:0;} dl.valori.lung dd{margin:0 0 6px;}
    .tabel thead{display:none;} .tabel tr{display:block;padding:6px 0;border-bottom:1px solid var(--bordura);}
    .tabel td{display:inline;border:0;padding:0 8px 0 0;} .tabel td.text{display:block;min-width:0;padding:3px 0 0;} }
</style>
</head>
<body>
<main>
<h1>Traducerea subtitrărilor</h1>
<p><a class="configurare" id="legatura-configurare" href="/traducere-configurare">Configurare pas cu pas (recunoaște cheia, caută serverul din casă)</a></p>
<p class="mesaj" id="incarcare">Se citesc setările...</p>
<div id="continut" class="ascuns">
  <section class="card" id="card-traducere">
    <h2>Traducerea</h2>
    <div class="rand" id="rand-pornit"><label for="alege-pornit">Traducerea automată</label><select id="alege-pornit"></select></div>
    <div class="rand" id="rand-serviciu"><label for="alege-serviciu">Serviciul</label><select id="alege-serviciu"></select></div>
    <p class="nota ascuns" id="eticheta-serviciu"></p>
    <p class="avertisment ascuns" id="avertisment-serviciu"></p>
    <div class="rand ascuns" id="rand-propriu_adresa">
      <label for="camp-propriu_adresa">Adresa-șablon</label>
      <input type="text" id="camp-propriu_adresa" maxlength="__MAX_ADRESA__" autocomplete="off" autocapitalize="off" spellcheck="false" inputmode="url" placeholder="http://192.168.1.50:5000/translate">
      <p class="nota tot">Locurile: {text} textul de tradus, {sursa} limba subtitrării (sau auto când nu se știe), {tinta} limba traducerii (de exemplu ro). Începe cu https://; http:// merge numai pentru un server din rețeaua de acasă.</p>
    </div>
    <div class="rand ascuns" id="rand-propriu_metoda"><label for="alege-propriu_metoda">Metoda</label><select id="alege-propriu_metoda"></select></div>
    <div class="rand ascuns" id="rand-propriu_tip_corp"><label for="alege-propriu_tip_corp">Felul corpului</label><select id="alege-propriu_tip_corp"></select></div>
    <div class="rand ascuns" id="rand-propriu_corp">
      <label for="camp-propriu_corp">Corpul cererii</label>
      <textarea class="tot" id="camp-propriu_corp" maxlength="__MAX_CORP__" rows="4" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder='{"q": "{text}", "source": "{sursa}", "target": "{tinta}", "format": "text"}'></textarea>
      <p class="nota tot">La JSON pune locurile între ghilimele, de exemplu "q": "{text}". La formular, de exemplu q={text}&amp;target={tinta}.</p>
    </div>
    <div class="rand ascuns" id="rand-propriu_antet">
      <label for="camp-propriu_antet">Numele antetului</label>
      <input type="text" id="camp-propriu_antet" maxlength="64" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="Authorization">
      <p class="nota tot">Opțional, numai dacă serverul cere o cheie. Valoarea lui se pune mai jos, ca o cheie.</p>
    </div>
    <div class="rand" id="rand-cheie">
      <label for="cheie" id="eticheta-cheie">Cheia API</label>
      <input type="password" id="cheie" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="lipește cheia aici">
      <p class="nota tot"><span id="cheie-stare"></span> <span id="cheie-optionala" class="ascuns">Cheia e opțională: numai dacă serverul cere cheie.</span><span id="cheie-antet" class="ascuns">Valoarea antetului, de exemplu Bearer, un spațiu și cheia ta; pleacă numai dacă ai scris numele antetului.</span></p>
      <p class="lipsa tot ascuns" id="chei-din-nou"></p>
      <div class="butoane tot"><button type="button" id="cheie-salveaza">Salvează cheia</button><button type="button" id="cheie-sterge">Șterge cheia</button></div>
      <p class="nota tot">Cheia se păstrează pe receptor, criptată; nu se mai arată niciodată.</p>
    </div>
    <div class="rand ascuns" id="rand-propriu_raspuns"><label for="alege-propriu_raspuns">Felul răspunsului</label><select id="alege-propriu_raspuns"></select></div>
    <div class="rand ascuns" id="rand-propriu_cale">
      <label for="camp-propriu_cale">Calea traducerii</label>
      <input type="text" id="camp-propriu_cale" maxlength="300" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="translatedText">
      <p class="nota tot">Chei și numere (de la 0) despărțite prin punct, de exemplu translatedText sau data.translations.0.translatedText; * ia toate elementele, lipite în ordine (de exemplu 0.*.0).</p>
    </div>
    <p class="nota ascuns" id="ajutor-propriu">Exemplu, un LibreTranslate al tău din casă: adresa http://192.168.1.50:5000/translate, metoda POST, corpul JSON {"q": "{text}", "source": "{sursa}", "target": "{tinta}", "format": "text"}, răspunsul JSON, calea translatedText. Fiecare rând de subtitrare pleacă într-o cerere separată. Dacă proba nu merge, mesajul arată începutul răspunsului serverului.</p>
    <div class="rand" id="rand-regiune">
      <label for="camp-regiune">Regiunea</label>
      <select id="camp-regiune"></select>
      <p class="nota tot">Regiunea resursei Translator, ca în portal (Overview › Location), de exemplu Germany West Central (germanywestcentral). Global dacă resursa e „Global”; altfel de exemplu westeurope. Dacă nu o știi, apasă „Probează traducerea”: receptorul o caută singur.</p>
    </div>
    <div class="rand" id="rand-adresa_libre">
      <label for="camp-adresa_libre">Adresa serverului</label>
      <input type="text" id="camp-adresa_libre" maxlength="300" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="http://192.168.1.50:5000">
      <p class="nota tot">Adresa serverului LibreTranslate, de exemplu http://192.168.1.50:5000</p>
    </div>
    <div class="rand" id="rand-adresa_openai">
      <label for="camp-adresa_openai">Adresa serverului</label>
      <input type="text" id="camp-adresa_openai" maxlength="300" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="http://192.168.1.50:11434">
      <p class="nota tot">De exemplu http://192.168.1.50:11434 pentru Ollama sau http://192.168.1.50:1234 pentru LM Studio.</p>
    </div>
    <div class="rand" id="rand-model_gemini">
      <label for="camp-model_gemini">Modelul</label>
      <input type="text" id="camp-model_gemini" maxlength="300" autocomplete="off" autocapitalize="off" spellcheck="false">
      <p class="nota tot" id="nota-model_gemini"></p>
    </div>
    <div class="rand" id="rand-model_openai">
      <label for="camp-model_openai">Modelul</label>
      <input type="text" id="camp-model_openai" maxlength="300" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="gemma3:4b">
      <p class="nota tot">Numele modelului de pe server, de exemplu gemma3:4b sau qwen2.5:7b.</p>
    </div>
    <div class="rand" id="rand-cont_cloudflare">
      <label for="camp-cont_cloudflare">ID-ul contului Cloudflare</label>
      <input type="text" id="camp-cont_cloudflare" maxlength="300" autocomplete="off" autocapitalize="off" spellcheck="false">
      <p class="nota tot">32 de litere și cifre, din panoul Cloudflare, la Account ID.</p>
    </div>
    <div class="rand" id="rand-model_groq">
      <label for="camp-model_groq">Modelul</label>
      <input type="text" id="camp-model_groq" maxlength="300" list="modele-groq" autocomplete="off" autocapitalize="off" spellcheck="false">
      <datalist id="modele-groq"></datalist>
      <p class="nota tot" id="nota-model_groq"></p>
    </div>
    <div class="rand" id="rand-model_cloudflare">
      <label for="camp-model_cloudflare">Modelul</label>
      <input type="text" id="camp-model_cloudflare" maxlength="300" list="modele-cloudflare" autocomplete="off" autocapitalize="off" spellcheck="false">
      <datalist id="modele-cloudflare"></datalist>
      <p class="nota tot" id="nota-model_cloudflare"></p>
    </div>
    <p class="nota">Regiunea, adresa, modelul și celelalte câmpuri se salvează când ieși din câmp (sau apeși Enter).</p>
    <p class="lipsa ascuns" id="lipsa"></p>
    <p class="mesaj" id="mesaj-traducere"></p>
  </section>
  <section class="card" id="card-rezerve">
    <h2>Servicii de rezervă</h2>
    <p id="rezerve-principal"></p>
    <p class="nota">Când serviciul ales nu poate traduce (prea multe cereri, limita pe zi, cheie refuzată, fără răspuns), cererea trece singură la următorul din listă care are câmpurile completate; primul revine după ce îi trece așteptarea. Lista se face din servicii diferite.</p>
    <ol class="pasi" id="rezerve-lista"></ol>
    <p class="nota ascuns" id="rezerve-gol">Nicio rezervă: la o eroare, traducerea așteaptă.</p>
    <div class="ascuns" id="alte-gata"><p class="nota" id="alte-gata-titlu">Alte servicii gata de folosit, care nu sunt în lista rezervelor:</p><ul class="alte" id="alte-gata-lista"></ul></div>
    <div class="rand" id="rand-rezerva"><label for="alege-rezerva">Adaugă un serviciu</label><select id="alege-rezerva"></select><div class="butoane tot"><button type="button" id="rezerva-adauga">Adaugă</button></div></div>
    <p class="nota">Cheia, adresa sau modelul unei rezerve se pun alegând-o pe rând la „Serviciul” (sau din configurarea pas cu pas).</p>
    <p class="mesaj" id="mesaj-rezerve"></p>
  </section>
  <section class="card" id="card-afisare">
    <h2>Cum se arată</h2>
    <div class="rand" id="rand-limba"><label for="alege-limba">Limba traducerii</label><select id="alege-limba"></select></div>
    <div class="rand" id="rand-afisare">
      <label for="alege-afisare">Afișarea</label><select id="alege-afisare"></select>
      <p class="nota tot">Sub original, traducerea se scrie cu <span class="traducere-sub">galben deschis</span>, ca s-o deosebești de original.</p>
    </div>
    <div class="rand" id="rand-tarziu">
      <label for="alege-tarziu">Traducerea care întârzie</label><select id="alege-tarziu"></select>
      <p class="nota tot">Originalul nu apare înaintea traducerii: până vine ea, ecranul rămâne gol. „Se pune când vine”: traducerea se așteaptă. „Rămâne originalul”: după 2 secunde apare originalul și rămâne netradus. Un rând care nu se poate traduce (eroare, prea multe cereri) apare în original, cu „(netradus)” în față.</p>
    </div>
    <div class="rand" id="rand-citire">
      <label for="alege-citire">Timpul de citire</label><select id="alege-citire"></select>
      <p class="nota tot">Cât stă cel puțin pe ecran o subtitrare tradusă, după lungimea ei. Obișnuit: cam 17 semne pe secundă, între 1,5 și 7 secunde. Mai lung și Cel mai lung: mai mult timp pentru citit. Subtitrarea tradusă stă oricum cel puțin cât ar fi stat originalul, iar următoarea apare după ea.</p>
    </div>
    <div class="rand" id="rand-dvb">
      <label for="alege-dvb">Și subtitrările DVB (imagini)</label><select id="alege-dvb"></select>
      <p class="nota tot">Subtitrările DVB sunt imagini: textul lor se citește întâi cu recunoașterea textului (OCR), apoi se traduce.</p>
    </div>
    <div class="rand" id="rand-bara">
      <label for="alege-bara" id="eticheta-bara">Tradu bara de jos</label><select id="alege-bara"></select>
      <p class="nota tot" id="nota-bara">Traduce titlurile emisiunii de acum și ale celei următoare de pe bara de jos, cu aceleași servicii și chei. Merge când traducerea subtitrărilor e pornită și folosește foarte puțin din cotă: fiecare titlu se cere o singură dată. INFO de pe bară arată textul original. Cu „Tradu EPG” pornită, bara se traduce oricum.</p>
    </div>
    <div class="rand" id="rand-epg">
      <label for="alege-epg">Tradu EPG</label><select id="alege-epg"></select>
      <p class="nota tot">Traduce automat titlurile și descrierile emisiunilor care sunt pe ecran (bara de jos, a doua bară, ghidul, detaliile emisiunii, pagina Ghidul canalului) în limba traducerii, cu aceleași servicii și chei. Consumă din cota serviciului, de aceea din fabrică e oprită. Textul deja în limba ta nu se trimite, iar o traducere ținută minte nu se mai cere. În detaliile emisiunii, pe televizor, INFO arată textul original.</p>
    </div>
    <div class="rand" id="rand-teletext">
      <label for="alege-teletext" id="eticheta-teletext">Tradu teletextul</label><select id="alege-teletext"></select>
      <p class="nota tot" id="nota-teletext">Traduce paginile de teletext pe care le deschizi (tasta TEXT) în limba traducerii, cu aceleași servicii și chei. Pagina apare întâi în original, apoi tradusă. În teletext, AUDIO arată originalul paginii, iar MENU are aceleași alegeri. Consumă din cota serviciului, de aceea din fabrică e oprită; un text tradus o dată nu se mai cere.</p>
    </div>
    <div class="rand" id="rand-teletext_mod">
      <label for="alege-teletext_mod" id="eticheta-teletext_mod">Teletextul tradus</label><select id="alege-teletext_mod"></select>
      <p class="nota tot" id="nota-teletext_mod">În pagină: rândurile traduse iau locul celor originale, în cele 40 de coloane ale paginii, cu aceleași culori; ce nu încape se taie cu „…”. Într-un panou: pagina originală, mai mică, în stânga, și traducerea întreagă în dreapta.</p>
    </div>
    <div class="rand" id="rand-hbbtv">
      <label for="alege-hbbtv" id="eticheta-hbbtv">Tradu HbbTV</label><select id="alege-hbbtv"></select>
      <p class="nota tot" id="nota-hbbtv">Traduce textele văzute din aplicațiile HbbTV (tasta ROȘIE), ca „Traduce pagina” din browsere: numai textele de pe ecran, nu adresele, codul sau câmpurile de scris. Pagina apare întâi în original. Consumă din cota serviciului, de aceea din fabrică e oprită. Aplicațiile deschise pe https rămân deocamdată în original.</p>
    </div>
    <p class="mesaj" id="mesaj-afisare"></p>
  </section>
  <section class="card" id="card-confidentialitate">
    <h2>Confidențialitate</h2>
    <p id="confidentialitate"></p>
  </section>
  <section class="card" id="card-proba">
    <h2>Probează traducerea</h2>
    <p class="nota">Trimite o frază de probă serviciului ales și arată traducerea, cât a durat și ce serviciu a răspuns.</p>
    <p class="nota eroare ascuns" id="oprite"></p>
    <div class="butoane"><button type="button" id="proba">Probează traducerea</button></div>
    <dl class="valori lung ascuns" id="proba-rezultat">
      <dt>Originalul</dt><dd id="proba-original"></dd>
      <dt id="proba-eticheta">Traducerea</dt><dd id="proba-traducere"></dd>
      <dt id="proba-timp-eticheta">Timpul</dt><dd id="proba-timp"></dd>
      <dt>Serviciul</dt><dd id="proba-serviciu"></dd>
      <dt id="proba-detaliu-eticheta">Detalii</dt><dd id="proba-detaliu"></dd>
    </dl>
    <p class="mesaj" id="mesaj-proba"></p>
  </section>
  <section class="card" id="card-instructiuni">
    <h2>Instrucțiuni pas cu pas</h2>
    <div class="rand" id="rand-instructiuni"><label for="alege-instructiuni">Arată instrucțiunile pentru</label><select id="alege-instructiuni"></select></div>
    <h3 id="instr-titlu"></h3>
    <p class="nota ascuns" id="instr-curand">Instrucțiunile vin în curând.</p>
    <p class="avertisment ascuns" id="instr-avertisment"></p>
    <ol class="pasi" id="instr-pasi"></ol>
    <p class="nota" id="instr-cota"></p>
    <p class="nota" id="instr-depasire"></p>
    <p class="nota" id="instr-verificat"></p>
    <a class="sursa ascuns" id="instr-sursa" target="_blank" rel="noopener"></a>
  </section>
  <section class="card" id="card-contor">
    <h2>Ce s-a tradus</h2>
    <p class="nota ascuns" id="contor-tv"></p>
    <dl class="valori" id="contor-valori"></dl>
    <ul class="erori" id="contor-erori"></ul>
    <p class="nota eroare ascuns" id="contor-pauza"></p>
    <p class="nota ascuns" id="contor-ultima"></p>
    <h3 class="ascuns" id="contor-treceri-titlu">Treceri la alt serviciu</h3>
    <ul class="erori ascuns" id="contor-treceri"></ul>
    <div class="tabel"><table><thead><tr><th>Ora</th><th>Originalul</th><th>Traducerea</th><th>De unde</th><th>Timpul</th></tr></thead><tbody id="contor-ultimele"></tbody></table></div>
    <p class="nota" id="contor-de-la"></p>
    <div class="butoane"><button type="button" id="contor-zero">Pune contorul la zero</button></div>
    <p class="mesaj" id="mesaj-contor"></p>
  </section>
  <section class="card ascuns" id="card-contor-epg">
    <h2>Ce s-a tradus din EPG</h2>
    <dl class="valori" id="contor-epg-valori"></dl>
    <ul class="erori" id="contor-epg-erori"></ul>
    <p class="nota ascuns" id="contor-epg-ultima"></p>
    <div class="tabel"><table><thead><tr><th>Ora</th><th>Originalul</th><th>Traducerea</th><th>Serviciul</th><th>Timpul</th></tr></thead><tbody id="contor-epg-ultimele"></tbody></table></div>
    <p class="nota" id="contor-epg-de-la"></p>
    <div class="butoane"><button type="button" id="contor-epg-zero">Pune contorul ghidului la zero</button></div>
    <p class="mesaj" id="mesaj-contor-epg"></p>
  </section>
  <section class="card ascuns" id="card-contor-texte">
    <h2 id="contor-texte-titlu">Ce s-a tradus din teletext și HbbTV</h2>
    <dl class="valori" id="contor-texte-valori"></dl>
    <div class="butoane"><button type="button" id="contor-texte-zero">Pune contorul la zero</button></div>
    <p class="mesaj" id="mesaj-contor-texte"></p>
  </section>
  <p class="nota">Aceleași setări sunt pe televizor, în __DRUM_MENIU__.</p>
</div>
</main>
<script>
var CFG = __CONFIG__;
var ALEGERI = ["pornit", "serviciu", "limba", "afisare", "tarziu", "citire", "dvb", "bara", "epg", "propriu_metoda", "propriu_tip_corp", "propriu_raspuns", "teletext", "teletext_mod", "hbbtv"];
var AFISARE = {limba: 1, afisare: 1, tarziu: 1, citire: 1, dvb: 1, bara: 1, epg: 1, teletext: 1, teletext_mod: 1, hbbtv: 1};
var TEXTE = ["regiune", "adresa_libre", "adresa_openai", "model_gemini", "model_openai", "model_groq", "model_cloudflare", "cont_cloudflare"];
var TEXTE_PROPRIU = ["propriu_adresa", "propriu_corp", "propriu_antet", "propriu_cale"];
var PROPRIU = ["propriu_adresa", "propriu_metoda", "propriu_tip_corp", "propriu_corp", "propriu_antet", "propriu_raspuns", "propriu_cale"];
var DA_NU = {pornit: [["1", "Pornită"], ["0", "Oprită"]], dvb: [["1", "Da"], ["0", "Nu"]], bara: [["1", "Da"], ["0", "Nu"]], epg: [["1", "Da"], ["0", "Nu"]], teletext: [["1", "Da"], ["0", "Nu"]], hbbtv: [["1", "Da"], ["0", "Nu"]]};
var CONTOR_MS = __CONTOR_MS__, PROBA_MS = __PROBA_MS__;
var ultim = null;
var instrAles = null;
var probaPana = 0;
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
function umple(s, alegeri, valoare){
  sterge(s);
  var gasit = false;
  alegeri.forEach(function(a){
    var o = document.createElement("option"); o.value = a[0]; o.textContent = a[1]; s.appendChild(o);
    if(a[0] === valoare){ gasit = true; }
  });
  s.value = gasit ? valoare : (alegeri.length ? alegeri[0][0] : "");
}
function seVedeCamp(camp, serv, cere){
  if(camp === "regiune"){ return serv === "azure"; }
  var p = camp.split("_");
  return p[1] === serv && cere.indexOf(p[0]) !== -1;
}
function seVedePropriu(camp, v){
  if(v.serviciu !== "propriu"){ return false; }
  if(camp === "propriu_corp" || camp === "propriu_tip_corp"){ return v.propriu_metoda === "POST"; }
  if(camp === "propriu_cale"){ return v.propriu_raspuns !== "text"; }
  return true;
}
function puneTot(d, fortat){
  ["valori", "alegeri", "cere", "chei", "chei_din_nou", "chei_din_nou_bland", "cheie_fel", "cheie_text", "texte", "lipsa_text", "confidentialitate", "instructiuni", "feluri_eroare", "implicite", "modele_propuse", "regiuni", "stare", "epg", "texte_tradus", "gata"].forEach(function(k){
    if(d[k] !== undefined){ ultim[k] = d[k]; }
  });
  var v = ultim.valori;
  ALEGERI.forEach(function(k){
    var s = $("alege-" + k);
    if(!fortat && document.activeElement === s){ return; }
    umple(s, DA_NU[k] || ultim.alegeri[k] || [], DA_NU[k] ? (v[k] ? "1" : "0") : String(v[k]));
  });
  TEXTE.concat(TEXTE_PROPRIU).forEach(function(k){
    var i = $("camp-" + k);
    if(k === "regiune"){
      if(fortat || document.activeElement !== i){
        var reg = (ultim.regiuni || []).slice(), are = false;
        reg.forEach(function(a){ if(a[0] === (v.regiune || "")){ are = true; } });
        if(!are){ reg.push([v.regiune, v.regiune]); }
        umple(i, reg, v.regiune || "");
      }
      return;
    }
    if(fortat || document.activeElement !== i){ i.value = v[k] || ""; }
  });
  var implicit = (ultim.implicite || {}).model_gemini || "";
  $("camp-model_gemini").placeholder = implicit;
  paragraf("nota-model_gemini", implicit ? "Implicit " + implicit + "." : "");
  ["groq", "cloudflare"].forEach(function(c){
    var imp = (ultim.implicite || {})["model_" + c] || "", dl = $("modele-" + c);
    $("camp-model_" + c).placeholder = imp;
    paragraf("nota-model_" + c, imp ? "Implicit " + imp + "." : "");
    sterge(dl);
    (((ultim.modele_propuse || {})[c]) || []).forEach(function(m){ var o = document.createElement("option"); o.value = m; dl.appendChild(o); });
  });
  var serv = v.serviciu, cere = ultim.cere[serv] || [];
  paragraf("avertisment-serviciu", ((ultim.instructiuni || {})[serv] || {}).avertisment || "");
  paragraf("eticheta-serviciu", ((ultim.instructiuni || {})[serv] || {}).eticheta || "");
  TEXTE.forEach(function(k){ arata($("rand-" + k), seVedeCamp(k, serv, cere)); });
  PROPRIU.forEach(function(k){ arata($("rand-" + k), seVedePropriu(k, v)); });
  var propriu = serv === "propriu";
  arata($("ajutor-propriu"), propriu);
  $("eticheta-cheie").textContent = propriu ? "Valoarea antetului" : "Cheia API";
  $("cheie").placeholder = propriu ? "de exemplu Bearer și cheia" : "lipește cheia aici";
  var pusa = !!(ultim.chei && ultim.chei[serv]);
  var oprita = pusa && ultim.cheie_fel === "oprita";
  var st = $("cheie-stare");
  st.textContent = ultim.cheie_text || (pusa ? "Cheie pusă" : "Fără cheie");
  st.classList.toggle("cheie-pusa", pusa && !oprita); st.classList.toggle("cheie-lipsa", !pusa || oprita);
  arata($("cheie-optionala"), !propriu && cere.indexOf("cheie") === -1);
  arata($("cheie-antet"), propriu);
  $("cheie-sterge").disabled = !pusa;
  var dn = $("chei-din-nou"), bland = !!ultim.chei_din_nou_bland;
  dn.textContent = bland ? ultim.chei_din_nou_bland : (ultim.chei_din_nou || ""); arata(dn, !!ultim.chei_din_nou);
  dn.classList.toggle("lipsa", !bland); dn.classList.toggle("avertisment", bland);
  $("eticheta-bara").textContent = tx("bara", "Tradu bara de jos");
  if(ultim.texte && ultim.texte.bara_nota){ $("nota-bara").textContent = ultim.texte.bara_nota; }
  ["teletext", "teletext_mod", "hbbtv"].forEach(function(k){
    var e = $("eticheta-" + k); e.textContent = tx(k, e.textContent);
    var n = $("nota-" + k); n.textContent = tx(k + "_nota", n.textContent);
  });
  var l = $("lipsa"); l.textContent = ultim.lipsa_text || ""; arata(l, !!ultim.lipsa_text);
  $("confidentialitate").textContent = ultim.confidentialitate || "";
  puneInstructiuni(fortat);
  puneProba();
  puneContor();
  puneContorEpg();
  puneContorTexte();
  puneRezerve();
}
function puneContorTexte(){
  var x = ultim.texte_tradus;
  arata($("card-contor-texte"), !!x);
  if(!x){ return; }
  $("contor-texte-titlu").textContent = tx("texte_titlu", "Ce s-a tradus din teletext și HbbTV");
  var dl = $("contor-texte-valori"); sterge(dl);
  [["teletext", tx("teletext", "Tradu teletextul")], ["hbbtv", tx("hbbtv", "Tradu HbbTV")]].forEach(function(p){
    var e = x[p[0]]; if(!e){ return; }
    var c = e.contor || {};
    valoare(dl, p[1], e.pornit ? (e.activ ? "pornită" : "pornită, dar serviciul nu e completat") : "oprită");
    valoare(dl, "Texte traduse", String(c.bucati || 0) + ", " + String(c.semne || 0) + " semne trimise (din cota serviciului), " + String(c.cereri || 0) + " cereri");
    valoare(dl, "Deja în limba ta (netrimise)", String(c.deja_in_limba || 0));
    valoare(dl, "Traduceri ținute minte", String(e.memorie || 0) + (e.pe_disc ? " (și pe stick sau disc)" : " (numai până la repornire)"));
    var u = c.ultima_eroare;
    if(u){ valoare(dl, "Ultima eroare", (u.ora || "") + ": " + (u.text || "")); }
  });
}
function puneContorEpg(){
  var e = ultim.epg;
  arata($("card-contor-epg"), !!e);
  if(!e){ return; }
  var c = e.contor || {};
  var dl = $("contor-epg-valori"); sterge(dl);
  valoare(dl, tx("bara", "Tradu bara de jos"), textBara(e));
  valoare(dl, "Tradu EPG", e.pornit ? (e.activ ? "pornită" : "pornită, dar serviciul nu e completat") : "oprită");
  valoare(dl, "Texte traduse", String(c.bucati || 0));
  valoare(dl, "Semne trimise (din cota serviciului)", String(c.semne || 0));
  valoare(dl, "Cereri", String(c.cereri || 0));
  valoare(dl, "Deja în limba ta (netrimise)", String(c.deja_in_limba || 0));
  valoare(dl, "Sărite (nu mai erau pe ecran)", String(c.sarite || 0));
  valoare(dl, "Pe rezervă", String(c.pe_rezerva || 0));
  valoare(dl, "Traduceri ținute minte", String(e.memorie || 0) + (e.pe_disc ? " (și pe stick sau disc)" : " (numai până la repornire)"));
  valoare(dl, "Timpul mediu", c.timp_mediu || "-");
  var ul = $("contor-epg-erori"); sterge(ul);
  var erori = c.erori_lista || [];
  if(!erori.length){ var li0 = document.createElement("li"); li0.textContent = "Nicio eroare."; ul.appendChild(li0); }
  erori.forEach(function(x){ var li = document.createElement("li"); li.textContent = x[1] + ": " + x[2]; ul.appendChild(li); });
  var u = c.ultima_eroare;
  paragraf("contor-epg-ultima", u ? "Ultima eroare, la " + (u.ora || "") + ": " + (u.text || "") : "");
  var t = $("contor-epg-ultimele"); sterge(t);
  (c.ultimele || []).forEach(function(p){
    var r = document.createElement("tr");
    celula(r, p.ora || "", "fix");
    celula(r, p.original || "", "text");
    celula(r, p.traducere || "", "text traducere-sub");
    celula(r, numeServ(p.serviciu || ""), "fix");
    celula(r, p.timp || "", "fix");
    t.appendChild(r);
  });
  paragraf("contor-epg-de-la", c.de_la_ora ? "Numărate de la ora " + c.de_la_ora + "." : "");
}
function tx(cheie, ro){ return (ultim && ultim.texte && ultim.texte[cheie]) || ro; }
function textBara(e){
  if(e.pornit){ return tx("bara_prin_epg", "se traduce prin „Tradu EPG”"); }
  if(!e.bara){ return tx("bara_oprita", "oprită"); }
  if(!e.traducere_pornita){ return tx("bara_fara_traducere", "pornită, dar traducerea automată e oprită"); }
  return e.bara_activ ? tx("bara_pornita", "pornită") : tx("bara_necompletat", "pornită, dar serviciul nu e completat");
}
function numeServ(cod){ var n = cod; (ultim.alegeri.serviciu || []).forEach(function(a){ if(a[0] === cod){ n = a[1]; } }); return n; }
function puneRezerve(){
  var v = ultim.valori, lista = (v.rezerve || []).slice(), stari = {}, gata = ultim.gata || [];
  ((ultim.stare || {}).lant || []).forEach(function(x){ stari[x.serviciu] = x; });
  var sp = stari[v.serviciu];
  $("rezerve-principal").textContent = tx("principal", "Serviciul principal") + ": " + numeServ(v.serviciu) +
    (sp && sp.stare_text && sp.stare !== "merge" ? " (" + sp.stare_text + ")" : "") + ".";
  var ol = $("rezerve-lista"); sterge(ol);
  lista.forEach(function(cod, i){
    var li = document.createElement("li");
    var n = document.createElement("span"); n.textContent = numeServ(cod); li.appendChild(n);
    var x = stari[cod];
    if(x && x.stare_text){ var st = document.createElement("span"); st.className = "nota"; st.textContent = " (" + x.stare_text + ")"; li.appendChild(st); }
    var b = document.createElement("div"); b.className = "butoane";
    [["Sus", i > 0, i - 1], ["Jos", i < lista.length - 1, i + 1], ["Scoate", true, -1]].forEach(function(a){
      var bt = document.createElement("button"); bt.type = "button"; bt.textContent = a[0]; bt.disabled = !a[1];
      bt.addEventListener("click", function(){
        var l = lista.slice();
        if(a[2] < 0){ l.splice(i, 1); } else { var t = l[a[2]]; l[a[2]] = l[i]; l[i] = t; }
        salveazaRezerve(l);
      });
      b.appendChild(bt);
    });
    if(gata.indexOf(cod) !== -1){ b.appendChild(butonPrincipal(cod)); }
    li.appendChild(b); ol.appendChild(li);
  });
  arata(ol, !!lista.length);
  arata($("rezerve-gol"), !lista.length);
  var libere = (ultim.alegeri.serviciu || []).filter(function(a){ return a[0] !== v.serviciu && lista.indexOf(a[0]) === -1; });
  var s = $("alege-rezerva");
  if(document.activeElement !== s){ umple(s, libere, s.value); }
  $("rezerva-adauga").disabled = !libere.length;
  var alte = gata.filter(function(c){ return lista.indexOf(c) === -1; });
  var ul = $("alte-gata-lista"); sterge(ul);
  alte.forEach(function(cod){
    var li = document.createElement("li");
    var n = document.createElement("span"); n.textContent = numeServ(cod); li.appendChild(n);
    var b = document.createElement("div"); b.className = "butoane"; b.appendChild(butonPrincipal(cod)); li.appendChild(b);
    ul.appendChild(li);
  });
  arata($("alte-gata"), !!alte.length);
  $("alte-gata-titlu").textContent = tx("alte_gata", "Alte servicii gata de folosit, care nu sunt în lista rezervelor:");
}
function butonPrincipal(cod){
  var bt = document.createElement("button"); bt.type = "button"; bt.id = "fa-principal-" + cod; bt.textContent = tx("fa_principal", "Fă-l principal");
  bt.addEventListener("click", function(){ var q = new URLSearchParams(); q.set("principal", cod); trimite(q, "mesaj-rezerve"); });
  return bt;
}
function salveazaRezerve(l){ var q = new URLSearchParams(); q.set("rezerve", l.join(",")); trimite(q, "mesaj-rezerve"); }
function paragraf(id, text){ var p = $(id); p.textContent = text || ""; arata(p, !!text); }
function puneInstructiuni(fortat){
  var s = $("alege-instructiuni");
  var serv = instrAles || ultim.valori.serviciu;
  if(fortat || document.activeElement !== s){ umple(s, ultim.alegeri.serviciu || [], serv); }
  var d = (ultim.instructiuni || {})[serv] || {};
  var pasi = d.pasi || [], gol = !pasi.length;
  $("instr-titlu").textContent = d.titlu || "";
  var ol = $("instr-pasi"); sterge(ol);
  pasi.forEach(function(p){ var li = document.createElement("li"); li.textContent = p; ol.appendChild(li); });
  arata(ol, !gol);
  arata($("instr-curand"), gol);
  paragraf("instr-avertisment", gol ? "" : (d.avertisment || ""));
  paragraf("instr-cota", gol || !d.cota ? "" : "Cât e gratuit: " + d.cota);
  paragraf("instr-depasire", gol || !d.depasire ? "" : "La depășire: " + d.depasire);
  paragraf("instr-verificat", gol ? "" : d.verificat);
  var a = $("instr-sursa");
  if(!gol && /^https?:\\/\\//.test(d.sursa || "")){ a.href = d.sursa; a.textContent = "Pagina oficială: " + d.sursa; arata(a, true); }
  else { a.textContent = ""; arata(a, false); }
}
function puneProba(){
  var p = ultim.stare && ultim.stare.proba;
  arata($("proba-rezultat"), !!p);
  if(!p){ return; }
  var lucru = p.stare === "lucru", eroare = p.stare === "eroare";
  $("proba-original").textContent = p.original || "";
  $("proba-eticheta").textContent = eroare ? "Eroarea" : "Traducerea";
  var t = $("proba-traducere");
  t.textContent = lucru ? "Se traduce..." : (p.traducere || "");
  t.classList.toggle("eroare", eroare);
  t.classList.toggle("traducere-sub", !eroare && !lucru);
  $("proba-timp").textContent = p.timp || "";
  arata($("proba-timp"), !!p.timp); arata($("proba-timp-eticheta"), !!p.timp);
  $("proba-serviciu").textContent = p.serviciu || "";
  $("proba-detaliu").textContent = p.detaliu || "";
  arata($("proba-detaliu"), !!p.detaliu); arata($("proba-detaliu-eticheta"), !!p.detaliu);
  if(p.nota && !lucru){ mesaj("mesaj-proba", p.nota); }
  $("proba").disabled = lucru && Date.now() < probaPana;
}
function valoare(dl, eticheta, text){
  var dt = document.createElement("dt"); dt.textContent = eticheta; dl.appendChild(dt);
  var dd = document.createElement("dd"); dd.textContent = text; dl.appendChild(dd);
}
function celula(r, text, clasa){ var td = document.createElement("td"); td.textContent = text; td.className = clasa; r.appendChild(td); }
function puneContor(){
  var s = ultim.stare || {}, c = s.contor || {};
  // televizorul stins: nimic nu se traduce, de aceea contorul sta (fraza tradusa vine de la receptor)
  paragraf("contor-tv", s.tv_stins_text || "");
  var dl = $("contor-valori"); sterge(dl);
  valoare(dl, "Pagini", String(c.pagini || 0));
  valoare(dl, "Din memorie", String(c.din_memorie || 0));
  valoare(dl, "La timp, în așteptare", String(c.in_asteptare || 0));
  valoare(dl, "Traduse după afișare", String(c.dupa_afisare || 0));
  valoare(dl, "Sărite", String(c.sarite || 0));
  valoare(dl, "Cereri", String(c.cereri || 0));
  valoare(dl, "Pe rezervă", String(c.pe_rezerva || 0));
  valoare(dl, "Lucrează acum", s.lucreaza_nume || (s.pauza_s ? "niciun serviciu (pauză)" : "-"));
  (c.pe_servicii_lista || []).forEach(function(x){ valoare(dl, "Rânduri de la " + x[1], String(x[2])); });
  valoare(dl, "Timpul mediu", c.timp_mediu || "-");
  valoare(dl, "Cel mai lung", c.timp_max || "-");
  var ul = $("contor-erori"); sterge(ul);
  var erori = c.erori_lista || [];
  if(!erori.length){ var li0 = document.createElement("li"); li0.textContent = "Nicio eroare."; ul.appendChild(li0); }
  erori.forEach(function(e){ var li = document.createElement("li"); li.textContent = e[1] + ": " + e[2]; ul.appendChild(li); });
  paragraf("contor-pauza", s.pauza_s ? "Traducerea stă în pauză după erori încă " + s.pauza_text + "." : "");
  paragraf("oprite", s.oprite_text || "");
  var u = c.ultima_eroare;
  paragraf("contor-ultima", u ? "Ultima eroare, la " + (u.ora || "") + ": " + (u.text || "") + (u.detaliu ? " (" + u.detaliu + ")" : "") : "");
  var tr = $("contor-treceri"); sterge(tr);
  (c.treceri || []).forEach(function(x){ var li = document.createElement("li"); li.textContent = x.text || ""; tr.appendChild(li); });
  arata(tr, !!(c.treceri || []).length); arata($("contor-treceri-titlu"), !!(c.treceri || []).length);
  var t = $("contor-ultimele"); sterge(t);
  (c.ultimele || []).forEach(function(p){
    var r = document.createElement("tr");
    celula(r, p.ora || "", "fix");
    celula(r, p.original || "", "text");
    celula(r, p.traducere || "", "text traducere-sub");
    celula(r, p.de_unde_text || "", "fix");
    celula(r, p.timp || "", "fix");
    t.appendChild(r);
  });
  paragraf("contor-de-la", c.de_la_ora ? "Numărate de la ora " + c.de_la_ora + "." : "");
}
function trimite(q, unde){
  mesaj(unde, "Se salvează...");
  cerere("/api/traducere-subtitrari-seteaza", "POST", q).then(function(d){
    mesaj(unde, d.message, !d.result);
    if(d.valori){ puneTot(d, true); }
  }).catch(function(){ mesaj(unde, "Receptorul nu răspunde.", true); });
}
function improspateaza(){
  return cerere("/api/traducere-subtitrari").then(function(d){ if(d.result){ puneTot(d, false); } return d; });
}
function trimiteCheie(q){
  mesaj("mesaj-traducere", "Se salvează cheia...");
  cerere("/api/traducere-subtitrari-cheie", "POST", q).then(function(d){
    mesaj("mesaj-traducere", d.message, !d.result);
    if(d.chei){ ultim.chei = d.chei; }
    improspateaza().catch(function(){});
  }).catch(function(){ mesaj("mesaj-traducere", "Receptorul nu răspunde.", true); });
}
function urmaresteProba(){
  improspateaza().then(function(){
    var p = ultim.stare && ultim.stare.proba;
    if(p && p.stare === "lucru"){
      if(Date.now() < probaPana){ setTimeout(urmaresteProba, 1000); }
      else { mesaj("mesaj-proba", "Serviciul nu a răspuns în " + Math.round(PROBA_MS / 1000) + " secunde.", true); $("proba").disabled = false; }
    } else { mesaj("mesaj-proba", ""); }
  }).catch(function(){ if(Date.now() < probaPana){ setTimeout(urmaresteProba, 1000); } });
}
ALEGERI.forEach(function(k){
  var s = $("alege-" + k);
  s.addEventListener("change", function(){
    var q = new URLSearchParams(); q.set(k, s.value);
    if(k === "serviciu"){ instrAles = null; }
    trimite(q, AFISARE[k] ? "mesaj-afisare" : "mesaj-traducere");
  });
});
TEXTE.concat(TEXTE_PROPRIU).forEach(function(k){
  var i = $("camp-" + k);
  i.addEventListener("change", function(){ var q = new URLSearchParams(); q.set(k, i.value.trim()); trimite(q, "mesaj-traducere"); });
});
if(CFG.jeton){ $("legatura-configurare").href = adresa("/traducere-configurare"); }
$("cheie-salveaza").addEventListener("click", function(){
  var i = $("cheie"), v = i.value.trim();
  if(!v){ mesaj("mesaj-traducere", "Scrie sau lipește întâi cheia.", true); return; }
  i.value = "";
  var q = new URLSearchParams(); q.set("serviciu", ultim.valori.serviciu); q.set("cheie", v);
  trimiteCheie(q);
});
$("cheie").addEventListener("keydown", function(e){ if(e && e.key === "Enter"){ $("cheie-salveaza").click(); } });
$("cheie-sterge").addEventListener("click", function(){
  if(!confirm("Ștergi cheia acestui serviciu de pe receptor?")){ return; }
  var q = new URLSearchParams(); q.set("serviciu", ultim.valori.serviciu); q.set("cheie", "");
  trimiteCheie(q);
});
$("rezerva-adauga").addEventListener("click", function(){
  var c = $("alege-rezerva").value;
  if(!c){ return; }
  var l = (ultim.valori.rezerve || []).slice(); l.push(c); salveazaRezerve(l);
});
$("alege-instructiuni").addEventListener("change", function(){
  var v = $("alege-instructiuni").value;
  instrAles = v === ultim.valori.serviciu ? null : v;
  puneInstructiuni(true);
});
$("proba").addEventListener("click", function(){
  mesaj("mesaj-proba", "Se trimite proba...");
  $("proba").disabled = true;
  cerere("/api/traducere-subtitrari-proba", "POST", new URLSearchParams()).then(function(d){
    mesaj("mesaj-proba", d.message, !d.result);
    probaPana = d.result ? Date.now() + PROBA_MS : 0;
    if(d.valori){ puneTot(d, false); }
    if(d.result){ setTimeout(urmaresteProba, 1000); } else { $("proba").disabled = false; }
  }).catch(function(){ mesaj("mesaj-proba", "Receptorul nu răspunde.", true); $("proba").disabled = false; });
});
$("contor-zero").addEventListener("click", function(){
  mesaj("mesaj-contor", "Se pune contorul la zero...");
  cerere("/api/traducere-subtitrari-zero", "POST", new URLSearchParams()).then(function(d){
    mesaj("mesaj-contor", d.message, !d.result); if(d.valori){ puneTot(d, false); }
  }).catch(function(){ mesaj("mesaj-contor", "Receptorul nu răspunde.", true); });
});
$("contor-texte-zero").addEventListener("click", function(){
  mesaj("mesaj-contor-texte", "Se pune contorul la zero...");
  var q = new URLSearchParams(); q.set("ce", "texte");
  cerere("/api/traducere-subtitrari-zero", "POST", q).then(function(d){
    mesaj("mesaj-contor-texte", d.message, !d.result); if(d.valori){ puneTot(d, false); }
  }).catch(function(){ mesaj("mesaj-contor-texte", "Receptorul nu răspunde.", true); });
});
$("contor-epg-zero").addEventListener("click", function(){
  mesaj("mesaj-contor-epg", "Se pune contorul la zero...");
  var q = new URLSearchParams(); q.set("ce", "epg");
  cerere("/api/traducere-subtitrari-zero", "POST", q).then(function(d){
    mesaj("mesaj-contor-epg", d.message, !d.result); if(d.valori){ puneTot(d, false); }
  }).catch(function(){ mesaj("mesaj-contor-epg", "Receptorul nu răspunde.", true); });
});
function seVede(){ return document.visibilityState === "visible"; }
setInterval(function(){ if(ultim && seVede()){ improspateaza().catch(function(){}); } }, CONTOR_MS);
document.addEventListener("visibilitychange", function(){ if(ultim && seVede()){ improspateaza().catch(function(){}); } });
function citeste(){
  cerere("/api/traducere-subtitrari").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi setările."; return; }
    ultim = {};
    arata($("incarcare"), false); arata($("continut"), true);
    puneTot(d, true);
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
		N_("Traducerea subtitrărilor"),
		N_("Configurare pas cu pas (recunoaște cheia, caută serverul din casă)"),
		N_("Se citesc setările..."),
		N_("Traducerea"),
		N_("Traducerea automată"),
		N_("Serviciul"),
		N_("Adresa-șablon"),
		N_("Locurile: {text} textul de tradus, {sursa} limba subtitrării (sau auto când nu se știe), "
			"{tinta} limba traducerii (de exemplu ro). Începe cu https://; http:// merge numai pentru un "
			"server din rețeaua de acasă."),
		N_("Metoda"),
		N_("Felul corpului"),
		N_("Corpul cererii"),
		N_("La JSON pune locurile între ghilimele, de exemplu \"q\": \"{text}\". La formular, de exemplu "
			"q={text}&amp;target={tinta}."),
		N_("Numele antetului"),
		N_("Opțional, numai dacă serverul cere o cheie. Valoarea lui se pune mai jos, ca o cheie."),
		N_("Cheia API"),
		N_("Cheia e opțională: numai dacă serverul cere cheie."),
		N_("Valoarea antetului, de exemplu Bearer, un spațiu și cheia ta; pleacă numai dacă ai scris numele "
			"antetului."),
		N_("Salvează cheia"),
		N_("Șterge cheia"),
		N_("Cheia se păstrează pe receptor, criptată; nu se mai arată niciodată."),
		N_("Felul răspunsului"),
		N_("Calea traducerii"),
		N_("Chei și numere (de la 0) despărțite prin punct, de exemplu translatedText sau "
			"data.translations.0.translatedText; * ia toate elementele, lipite în ordine (de exemplu 0.*.0)."),
		N_("Exemplu, un LibreTranslate al tău din casă: adresa http://192.168.1.50:5000/translate, metoda "
			"POST, corpul JSON {\"q\": \"{text}\", \"source\": \"{sursa}\", \"target\": \"{tinta}\", \"format\": \"text\"}, "
			"răspunsul JSON, calea translatedText. Fiecare rând de subtitrare pleacă într-o cerere separată. "
			"Dacă proba nu merge, mesajul arată începutul răspunsului serverului."),
		N_("Regiunea"),
		N_("Regiunea resursei Translator, ca în portal (Overview › Location), de exemplu Germany West "
			"Central (germanywestcentral). Global dacă resursa e „Global”; altfel de exemplu westeurope. "
			"Dacă nu o știi, apasă „Probează traducerea”: receptorul o caută singur."),
		N_("Adresa serverului"),
		N_("Adresa serverului LibreTranslate, de exemplu http://192.168.1.50:5000"),
		N_("De exemplu http://192.168.1.50:11434 pentru Ollama sau http://192.168.1.50:1234 pentru LM "
			"Studio."),
		N_("Modelul"),
		N_("Numele modelului de pe server, de exemplu gemma3:4b sau qwen2.5:7b."),
		N_("ID-ul contului Cloudflare"),
		N_("32 de litere și cifre, din panoul Cloudflare, la Account ID."),
		N_("Regiunea, adresa, modelul și celelalte câmpuri se salvează când ieși din câmp (sau apeși Enter)."),
		N_("Servicii de rezervă"),
		N_("Când serviciul ales nu poate traduce (prea multe cereri, limita pe zi, cheie refuzată, fără "
			"răspuns), cererea trece singură la următorul din listă care are câmpurile completate; primul "
			"revine după ce îi trece așteptarea. Lista se face din servicii diferite."),
		N_("Nicio rezervă: la o eroare, traducerea așteaptă."),
		N_("Alte servicii gata de folosit, care nu sunt în lista rezervelor:"),
		N_("Adaugă un serviciu"),
		N_("Adaugă"),
		N_("Cheia, adresa sau modelul unei rezerve se pun alegând-o pe rând la „Serviciul” (sau din "
			"configurarea pas cu pas)."),
		N_("Cum se arată"),
		N_("Limba traducerii"),
		N_("Afișarea"),
		N_("Sub original, traducerea se scrie cu <span class=\"traducere-sub\">galben deschis</span>, ca s-o "
			"deosebești de original."),
		N_("Traducerea care întârzie"),
		N_("Originalul nu apare înaintea traducerii: până vine ea, ecranul rămâne gol. „Se pune când vine”: "
			"traducerea se așteaptă. „Rămâne originalul”: după 2 secunde apare originalul și rămâne "
			"netradus. Un rând care nu se poate traduce (eroare, prea multe cereri) apare în original, cu "
			"„(netradus)” în față."),
		N_("Timpul de citire"),
		N_("Cât stă cel puțin pe ecran o subtitrare tradusă, după lungimea ei. Obișnuit: cam 17 semne pe "
			"secundă, între 1,5 și 7 secunde. Mai lung și Cel mai lung: mai mult timp pentru citit. "
			"Subtitrarea tradusă stă oricum cel puțin cât ar fi stat originalul, iar următoarea apare după "
			"ea."),
		N_("Și subtitrările DVB (imagini)"),
		N_("Subtitrările DVB sunt imagini: textul lor se citește întâi cu recunoașterea textului (OCR), "
			"apoi se traduce."),
		N_("Tradu bara de jos"),
		N_("Traduce titlurile emisiunii de acum și ale celei următoare de pe bara de jos, cu aceleași "
			"servicii și chei. Merge când traducerea subtitrărilor e pornită și folosește foarte puțin din "
			"cotă: fiecare titlu se cere o singură dată. INFO de pe bară arată textul original. Cu „Tradu "
			"EPG” pornită, bara se traduce oricum."),
		N_("Tradu EPG"),
		N_("Traduce automat titlurile și descrierile emisiunilor care sunt pe ecran (bara de jos, a doua "
			"bară, ghidul, detaliile emisiunii, pagina Ghidul canalului) în limba traducerii, cu aceleași "
			"servicii și chei. Consumă din cota serviciului, de aceea din fabrică e oprită. Textul deja în "
			"limba ta nu se trimite, iar o traducere ținută minte nu se mai cere. În detaliile emisiunii, pe "
			"televizor, INFO arată textul original."),
		N_("Tradu teletextul"),
		N_("Traduce paginile de teletext pe care le deschizi (tasta TEXT) în limba traducerii, cu aceleași "
			"servicii și chei. Pagina apare întâi în original, apoi tradusă. În teletext, AUDIO arată "
			"originalul paginii, iar MENU are aceleași alegeri. Consumă din cota serviciului, de aceea din "
			"fabrică e oprită; un text tradus o dată nu se mai cere."),
		N_("Teletextul tradus"),
		N_("În pagină: rândurile traduse iau locul celor originale, în cele 40 de coloane ale paginii, cu "
			"aceleași culori; ce nu încape se taie cu „…”. Într-un panou: pagina originală, mai mică, în "
			"stânga, și traducerea întreagă în dreapta."),
		N_("Tradu HbbTV"),
		N_("Traduce textele văzute din aplicațiile HbbTV (tasta ROȘIE), ca „Traduce pagina” din browsere: "
			"numai textele de pe ecran, nu adresele, codul sau câmpurile de scris. Pagina apare întâi în "
			"original. Consumă din cota serviciului, de aceea din fabrică e oprită. Aplicațiile deschise pe "
			"https rămân deocamdată în original."),
		N_("Confidențialitate"),
		N_("Probează traducerea"),
		N_("Trimite o frază de probă serviciului ales și arată traducerea, cât a durat și ce serviciu a "
			"răspuns."),
		N_("Originalul"),
		N_("Timpul"),
		N_("Detalii"),
		N_("Instrucțiuni pas cu pas"),
		N_("Arată instrucțiunile pentru"),
		N_("Instrucțiunile vin în curând."),
		N_("Ce s-a tradus"),
		N_("Treceri la alt serviciu"),
		N_("Ora"),
		N_("De unde"),
		N_("Pune contorul la zero"),
		N_("Ce s-a tradus din EPG"),
		N_("Pune contorul ghidului la zero"),
		N_("Ce s-a tradus din teletext și HbbTV"),
		N_("Aceleași setări sunt pe televizor, în __DRUM_MENIU__."),
		N_("http://192.168.1.50:5000/translate"),
		N_("Authorization"),
		N_("lipește cheia aici"),
		N_("translatedText"),
		N_("http://192.168.1.50:5000"),
		N_("http://192.168.1.50:11434"),
		N_("gemma3:4b"),
	),
	"js": (
		N_("Pornită"),
		N_("Oprită"),
		N_("Da"),
		N_("Nu"),
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Implicit"),
		N_("Valoarea antetului"),
		N_("Cheia API"),
		N_("de exemplu Bearer și cheia"),
		N_("lipește cheia aici"),
		N_("Cheie pusă"),
		N_("Fără cheie"),
		N_("Tradu bara de jos"),
		N_("Ce s-a tradus din teletext și HbbTV"),
		N_("Tradu teletextul"),
		N_("Tradu HbbTV"),
		N_("pornită"),
		N_("pornită, dar serviciul nu e completat"),
		N_("oprită"),
		N_("Texte traduse"),
		N_("semne trimise (din cota serviciului),"),
		N_("cereri"),
		N_("Deja în limba ta (netrimise)"),
		N_("Traduceri ținute minte"),
		N_("(și pe stick sau disc)"),
		N_("(numai până la repornire)"),
		N_("Ultima eroare"),
		N_("Tradu EPG"),
		N_("Semne trimise (din cota serviciului)"),
		N_("Cereri"),
		N_("Sărite (nu mai erau pe ecran)"),
		N_("Pe rezervă"),
		N_("Timpul mediu"),
		N_("Nicio eroare."),
		N_("Ultima eroare, la"),
		N_("Numărate de la ora"),
		N_("se traduce prin „Tradu EPG”"),
		N_("pornită, dar traducerea automată e oprită"),
		N_("Serviciul principal"),
		N_("Sus"),
		N_("Jos"),
		N_("Scoate"),
		N_("Alte servicii gata de folosit, care nu sunt în lista rezervelor:"),
		N_("Fă-l principal"),
		N_("Cât e gratuit:"),
		N_("La depășire:"),
		N_("Pagina oficială:"),
		N_("Eroarea"),
		N_("Traducerea"),
		N_("Se traduce..."),
		N_("Pagini"),
		N_("Din memorie"),
		N_("La timp, în așteptare"),
		N_("Traduse după afișare"),
		N_("Sărite"),
		N_("Lucrează acum"),
		N_("niciun serviciu (pauză)"),
		N_("Rânduri de la"),
		N_("Cel mai lung"),
		N_("Traducerea stă în pauză după erori încă"),
		N_("Se salvează..."),
		N_("Receptorul nu răspunde."),
		N_("Se salvează cheia..."),
		N_("Serviciul nu a răspuns în"),
		N_("secunde."),
		N_("Scrie sau lipește întâi cheia."),
		N_("Ștergi cheia acestui serviciu de pe receptor?"),
		N_("Se trimite proba..."),
		N_("Se pune contorul la zero..."),
		N_("Receptorul nu a putut citi setările."),
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
