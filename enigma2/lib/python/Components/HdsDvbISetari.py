# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsDvbISetari: setarile DVB-I (listele de canale prin internet) si reincarcarea lor, intr-un singur loc pentru
# ecranele de pe televizor (Screens/HdsDvbI.py: HdsDvbISetup si HdsDvbIReloadNow) si pentru pagina web /dvb-i
# (HdsWebControl/internet_web.py).
#
# Setarile stau in /etc/enigma2/hdsdvbi.conf, in formatul pluginului (Plugins/SystemPlugins/HdsDvbI/plugin.py, care il
# citeste la pornire): activ, interval_refresh, predefinite (cheile listelor bifate), url (cate un rand pentru fiecare
# adresa proprie). Inainte, ecranul avea copia lui de citire si scriere, care pierdea interval_refresh (il scria mereu
# 3600); aici se citeste si se scrie tot, iar scrierea merge printr-un fisier .nou si o redenumire.
#
# Reincarcarea: aceeasi ca pe televizor (reincarca_acum din plugin, pe firul lui), cu starea tinuta aici (in curs,
# reusita, eroarea, ora), ca pagina web sa vada si o reincarcare pornita de pe televizor. Inainte de reincarcare,
# managerul pluginului primeste setarile de acum din fisier: el le citea o singura data, la pornire, deci o lista bifata
# sau o adresa adaugata intre timp nu se descarca pana la repornire.
#
# In plus: tara (tara = DEU, din registrele DVB-I: Components/HdsDvbIRegistru), regiunea (regiune =, din
# listele descarcate), listele tarii scoase sau puse de mana (lista_oprita / lista_pusa, cate un rand) si trecerea
# singura pe internet (rezerva = da / nu, Components/HdsDvbIRezerva); randurile ecranului si capul lui (randuriSetari,
# rezumatEcran), aceleasi in pagina web. Adresele puse de mana (url) si listele predefinite raman, ca optiune avansata.
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau pluginul lor.

import os
import time

CALE_CONFIG = "/etc/enigma2/hdsdvbi.conf"
INTERVAL_IMPLICIT = "3600"
MAX_URL = 1024
MAX_URL_URI = 64
MAX_REINCARCARE_S = 600   # listele se descarca cu 15 s pe lista; mai mult de atat inseamna un fir pierdut

_REINCARCARE = {"in_curs": False, "gata": False, "succes": None, "eroare": "", "ora": 0}


def _plugin(plugin=None):
	if plugin is not None:
		return plugin
	from Plugins.SystemPlugins.HdsDvbI import plugin as p
	return p


def listePredefinite(plugin=None):
	"""[(cheie, descriere, adresa, tara)] din pluginul DVB-I (o singura lista, a lui); [] daca pluginul lipseste."""
	try:
		return [(cheie, descriere, adresa, tara) for cheie, adresa, descriere, tara in _plugin(plugin).LISTE_PREDEFINITE]
	except Exception as eroare:
		print("[HdsDvbISetari] listele predefinite: %s" % eroare)
		return []


def implicit():
	return {"activ": "da", "interval_refresh": INTERVAL_IMPLICIT, "url_uri": [], "predefinite": [], "tara": "",
		"regiune": "", "liste_oprite": [], "liste_puse": [], "rezerva": "da"}


def citeste(cale=None):
	"""Setarile din fisier (formatul pluginului); fara fisier, cele implicite."""
	config = implicit()
	cale = cale or CALE_CONFIG
	if not os.path.exists(cale):
		return config
	try:
		with open(cale, "r", encoding="utf-8", errors="replace") as f:
			for linie in f:
				linie = linie.strip()
				if not linie or linie.startswith("#") or "=" not in linie:
					continue
				cheie, val = linie.split("=", 1)
				cheie, val = cheie.strip().lower(), val.strip()
				if cheie == "activ":
					config["activ"] = val.lower()
				elif cheie == "interval_refresh":
					config["interval_refresh"] = val
				elif cheie == "url":
					if val:
						config["url_uri"].append(val)
				elif cheie == "predefinite":
					config["predefinite"] = [x.strip() for x in val.split(",") if x.strip()]
				elif cheie == "tara":
					config["tara"] = val.upper() if _codTara(val.upper()) else ""
				elif cheie == "regiune":
					config["regiune"] = val if _regiuneBuna(val) else ""
				elif cheie in ("lista_oprita", "lista_pusa"):
					lista = config["liste_oprite" if cheie == "lista_oprita" else "liste_puse"]
					if urlBun(val) and val not in lista and len(lista) < MAX_URL_URI:
						lista.append(val)
				elif cheie == "rezerva":
					config["rezerva"] = val.lower()
	except (IOError, OSError) as eroare:
		print("[HdsDvbISetari] citirea %s: %s" % (cale, eroare))
	return config


def scrie(config, cale=None, plugin=None):
	"""Scrie setarile in formatul pluginului. -> True daca s-au scris."""
	cale = cale or CALE_CONFIG
	chei = ", ".join(c for c, _d, _a, _t in listePredefinite(plugin))
	linii = [
		"# Configurare HdsDvbI: HDSatelit DVB-I over Internet",
		"# activ = da / nu",
		"activ = %s" % config.get("activ", "da"),
		"# interval_refresh = secunde intre reincarcari automate (0 = dezactivat)",
		"interval_refresh = %s" % config.get("interval_refresh", INTERVAL_IMPLICIT),
		"# predefinite = cheile listelor predefinite separate prin virgula",
		"# Cheile disponibile: %s" % chei,
		"predefinite = %s" % ", ".join(config.get("predefinite", [])),
		"# url = URL personal DVB-I (adauga cate o linie pentru fiecare URL)",
	]
	for url in config.get("url_uri", []):
		linii.append("url = %s" % url)
	linii += [
		"# tara = codul tarii (3 litere, ca DEU) din registrele DVB-I; listele ei se iau singure",
		"tara = %s" % config.get("tara", ""),
		"# regiune = regiunea din lista (numerotarea canalelor dupa tabelul ei)",
		"regiune = %s" % config.get("regiune", ""),
		"# rezerva = da / nu: trecerea singura pe internet cand satelitul nu se receptioneaza",
		"rezerva = %s" % config.get("rezerva", "da"),
		"# lista_oprita / lista_pusa = listele tarii scoase sau adaugate de mana (cate un rand)",
	]
	for url in config.get("liste_oprite", []):
		linii.append("lista_oprita = %s" % url)
	for url in config.get("liste_puse", []):
		linii.append("lista_pusa = %s" % url)
	nou = cale + ".nou"
	try:
		with open(nou, "w", encoding="utf-8") as f:
			f.write("\n".join(linii) + "\n")
		os.replace(nou, cale)
		return True
	except (IOError, OSError) as eroare:
		print("[HdsDvbISetari] scrierea %s: %s" % (cale, eroare))
		try:
			os.unlink(nou)
		except OSError:
			pass
		return False


def esteActiv(config):
	return str(config.get("activ", "da")).lower() in ("da", "yes", "1", "true")


def numarListe(config, registru=None):
	"""cate liste se descarca: ale tarii alese, cele predefinite bifate si adresele puse de mana (fara dubluri)"""
	return len(adreseDeDescarcat(config, registru))


def textStare(config):
	"""Randul de stare de pe televizor: "DVB-I: ACTIV | Liste: 2"."""
	return _("DVB-I: %s | Liste: %d") % (_("ACTIV") if esteActiv(config) else _("INACTIV"), numarListe(config))


def comutaActiv(config):
	"""Galben pe televizor: activ <-> inactiv."""
	config["activ"] = "nu" if esteActiv(config) else "da"


def comutaPredefinita(config, cheie, plugin=None):
	"""OK pe o lista predefinita: bifata <-> nebifata. -> False pentru o cheie necunoscuta (nimic schimbat)."""
	if cheie not in [c for c, _d, _a, _t in listePredefinite(plugin)]:
		return False
	predefinite = set(config.get("predefinite", []))
	if cheie in predefinite:
		predefinite.discard(cheie)
	else:
		predefinite.add(cheie)
	config["predefinite"] = sorted(predefinite)
	return True


def urlBun(url):
	"""O adresa proprie: http:// sau https://, fara spatii si fara caractere de control (fisierul are un rand pe adresa)."""
	if not url or len(url) > MAX_URL:
		return False
	if not url.startswith(("http://", "https://")):
		return False
	return not any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in url)


def adaugaUrl(config, url):
	"""Albastru pe televizor (Adauga URL). -> (reusit, mesaj)."""
	url = (url or "").strip()
	if not urlBun(url):
		return False, _("URL invalid. Trebuie să înceapă cu http:// sau https://")
	url_uri = config.setdefault("url_uri", [])
	if len(url_uri) >= MAX_URL_URI:
		return False, _("Sunt prea multe adrese proprii. Șterge una înainte.")
	url_uri.append(url)
	return True, ""


def stergeUrl(config, index):
	"""OK pe o adresa proprie: o scoate din lista. -> adresa scoasa sau None."""
	url_uri = config.get("url_uri", [])
	if 0 <= index < len(url_uri):
		return url_uri.pop(index)
	return None


# ------------------------------------------------------------------ tara, regiunea, listele tarii
# Tara se alege din tarile registrelor DVB-I (Components/HdsDvbIRegistru: raspunsul tinut minte pe disc). Listele tarii
# care nu sunt de proba se iau singure; omul poate scoate una (lista_oprita) sau pune una de proba (lista_pusa).
# Adresele puse de mana (url) si listele predefinite raman ca optiune avansata. Regiunea vine din listele descarcate
# (RegionList), iar numerotarea foloseste tabelul LCN al ei.
MAX_REGIUNE = 128


def _codTara(text):
	return len(text) == 3 and text.isalpha() and text.isupper()


def _regiuneBuna(text):
	return 0 < len(text) <= MAX_REGIUNE and not any(c.isspace() or ord(c) < 32 or c in ",=#" for c in text)


def _registru(registru=None):
	if registru is not None:
		return registru
	from Components import HdsDvbIRegistru
	return HdsDvbIRegistru.incarca()


def _R():
	from Components import HdsDvbIRegistru
	return HdsDvbIRegistru


def rezervaPornita(config):
	return str(config.get("rezerva", "da")).lower() in ("da", "yes", "1", "true")


def comutaRezerva(config):
	config["rezerva"] = "nu" if rezervaPornita(config) else "da"


def tariDinRegistre(registru=None):
	"""[(cod, cate liste, cate nu sunt de proba)] din raspunsul tinut minte al registrelor"""
	return _R().tari(_registru(registru).get("liste", []))


def seteazaTara(config, tara):
	"""tara noua (cod de 3 litere sau "" = nicio tara): regiunea si alegerile de liste ale tarii vechi se uita.
	-> False pentru un cod rau (nimic schimbat)"""
	tara = (tara or "").strip().upper()
	if tara and not _codTara(tara):
		return False
	if tara != config.get("tara", ""):
		config["tara"] = tara
		config["regiune"] = ""
		config["liste_oprite"] = []
		config["liste_puse"] = []
	return True


def seteazaRegiune(config, regiune):
	regiune = (regiune or "").strip()
	if regiune and not _regiuneBuna(regiune):
		return False
	config["regiune"] = regiune
	return True


def listeleTarii(config, registru=None):
	"""[{"adresa", "lista", "furnizor", "proba", "aleasa"}] pentru tara aleasa: intai cele adevarate, apoi cele de
	proba; [] fara tara"""
	R = _R()
	liste = R.aleTarii(_registru(registru).get("liste", []), config.get("tara", ""))
	oprite = set(config.get("liste_oprite", []))
	puse = set(config.get("liste_puse", []))
	rez = []
	for l in liste:
		proba = bool(l.get("proba"))
		aleasa = (l["adresa"] in puse) if proba else (l["adresa"] not in oprite)
		rez.append({"adresa": l["adresa"], "lista": l.get("lista", ""), "furnizor": l.get("furnizor", ""),
			"proba": proba, "aleasa": aleasa})
	rez.sort(key=lambda x: x["proba"])
	return rez


def comutaListaTarii(config, adresa, registru=None):
	"""OK pe o lista a tarii: aleasa <-> scoasa. -> False pentru o adresa care nu e a tarii (nimic schimbat)"""
	for l in listeleTarii(config, registru):
		if l["adresa"] != adresa:
			continue
		cheie = "liste_puse" if l["proba"] else "liste_oprite"
		lista = config.setdefault(cheie, [])
		if adresa in lista:
			lista.remove(adresa)
		elif len(lista) < MAX_URL_URI:
			lista.append(adresa)
		else:
			return False
		return True
	return False


def adreseDeDescarcat(config, registru=None, plugin=None):
	"""adresele de descarcat, in ordine si fara dubluri: listele alese ale tarii, apoi cele predefinite bifate, apoi
	adresele puse de mana"""
	rez = []
	if config.get("tara"):
		try:
			rez += [l["adresa"] for l in listeleTarii(config, registru) if l["aleasa"]]
		except Exception as eroare:
			print("[HdsDvbISetari] listele tarii: %s" % eroare)
	bifate = set(config.get("predefinite", []))
	rez += [a for c, _d, a, _t in listePredefinite(plugin) if c in bifate]
	rez += list(config.get("url_uri", []))
	vazute = set()
	unice = []
	for a in rez:
		if a not in vazute:
			vazute.add(a)
			unice.append(a)
	return unice


def numeTara(cod):
	"""numele tarii in limba aleasa (tabelul din Components/HdsListeCabluTerestru); codul daca nu e acolo"""
	if not cod:
		return _("Nicio țară")
	try:
		from Components.HdsListeCabluTerestru import nume_tara
		return nume_tara(cod)
	except Exception:
		return cod


def tariOrdonate(registru=None):
	"""[(cod, nume, cate liste, cate nu sunt de proba)] in ordinea numelui (in limba aleasa)"""
	rez = [(cod, numeTara(cod), n, reale) for cod, n, reale in tariDinRegistre(registru)]
	rez.sort(key=lambda x: x[1].lower())
	return rez


def tariVecine(config, pas, registru=None):
	"""tara de dinainte (pas -1) sau de dupa (pas +1) in ordinea numelor; dupa ultima vine "nicio tara" ("")"""
	coduri = [""] + [c for c, _n, _a, _b in tariOrdonate(registru)]
	tara = config.get("tara", "")
	i = coduri.index(tara) if tara in coduri else 0
	return coduri[(i + pas) % len(coduri)]


def _dateStare(stare=None):
	if stare is not None:
		return stare
	try:
		from Components import HdsDvbIDate
		return HdsDvbIDate.stare()
	except Exception:
		return {}


def regiuniTarii(config, stare=None, registru=None):
	"""[(id, nume, nivel)] regiunile alese ale listelor tarii descarcate (fara grupurile neselectabile), fara dubluri;
	[] cand listele nu au regiuni"""
	adrese = set(l["adresa"] for l in listeleTarii(config, registru) if l["aleasa"]) if config.get("tara") else set()
	rez, vazute = [], set()
	for l in _dateStare(stare).get("liste") or []:
		if l.get("adresa") not in adrese:
			continue
		for r in l.get("regiuni") or []:
			if r.get("alegere") and r.get("id") not in vazute:
				vazute.add(r["id"])
				rez.append((r["id"], r.get("nume") or r["id"], int(r.get("nivel") or 0)))
	return rez


def numeRegiune(config, stare=None, registru=None):
	reg = config.get("regiune", "")
	if not reg:
		return _("toată țara")
	for rid, nume, _n in regiuniTarii(config, stare, registru):
		if rid == reg:
			return nume
	return reg


def regiuneVecina(config, pas, stare=None, registru=None):
	ids = [""] + [r for r, _n, _v in regiuniTarii(config, stare, registru)]
	reg = config.get("regiune", "")
	i = ids.index(reg) if reg in ids else 0
	return ids[(i + pas) % len(ids)]


def oraText(ora, acum=None):
	"""'azi, 19:40' sau '16.10, 19:40'; '' fara ora"""
	if not ora:
		return ""
	t = time.localtime(ora)
	a = time.localtime(time.time() if acum is None else acum)
	if t[:3] == a[:3]:
		return _("azi, %s") % time.strftime("%H:%M", t)
	return time.strftime("%d.%m, %H:%M", t)


def rezumatEcran(config, registru=None, stare=None, reincarcare=None, acum=None):
	"""(culoare, starea mare, detaliile) pentru capul ecranului si al paginii web: culoare "bun", "chihlimbar", "rau"
	sau "slab". Numai ce s-a aflat: listele descarcate, canalele, ora; fara presupuneri."""
	stare = _dateStare(stare)
	reincarcare = reincarcare if reincarcare is not None else stareReincarcare()
	tara = config.get("tara", "")
	liste = stare.get("liste") or []
	ok = [l for l in liste if l.get("ok")]
	canale = len(stare.get("canale") or [])
	cap = numeTara(tara) if tara else _("Fără țară")
	if not esteActiv(config):
		return "slab", _("DVB-I oprit"), _("Listele nu se mai descarcă. Pornește DVB-I din Adrese puse de mână (avansat).")
	if reincarcare.get("in_curs"):
		return "chihlimbar", _("Se reîncarcă listele DVB-I..."), _("Listele se descarcă acum de pe internet.")
	if not tara and not adreseDeDescarcat(config, registru):
		return "slab", _("Nicio țară aleasă"), _("Alege țara: listele ei de canale se iau singure din registrele DVB-I și se actualizează din oră în oră.")
	if tara and not adreseDeDescarcat(config, registru):
		return "chihlimbar", "%s · %s" % (cap, _("nicio listă aleasă")), _(
			"Registrele DVB-I nu au pentru această țară decât liste de probă. Poți bifa una mai jos, ca s-o încerci.")
	if liste and not ok:
		return "rau", _("Nicio listă nu s-a putut descărca"), _("Ultima încercare: %s. Canalele de dinainte rămân.") % (
			oraText(stare.get("ora"), acum) or "?")
	if not liste:
		return "chihlimbar", "%s · %s" % (cap, _("listele nu s-au descărcat încă")), _(
			"Apasă Verde ca să le descarci acum.")
	text = "%s · %s %d · %s %d" % (cap, _("liste:"), len(ok), _("canale:"), canale)
	detalii = _("Listele se iau singure din registrele DVB-I și se actualizează din oră în oră. Ultima actualizare: %s.") % (
		oraText(stare.get("ora"), acum) or "?")
	if len(ok) < len(liste):
		detalii += " " + _("Liste care nu s-au descărcat: %d.") % (len(liste) - len(ok))
	return "bun", text, detalii


def textIncercari(rez, incercare=None):
	"""randul cu canalele incercate din casa; rez = {stare: cate} (Components/HdsDvbIDate.rezumat)"""
	if incercare and incercare.get("in_curs"):
		return _("Se încearcă din casă canalele: %d din %d") % (incercare.get("facute", 0), incercare.get("total", 0))
	total = sum(rez.values())
	if not total:
		return _("Canalele încercate din casă: niciun canal în listă")
	if rez.get("", 0) == total:
		return _("Canalele încercate din casă: încă neîncercate")
	return _("Canalele încercate din casă: merg %d, oprite pentru țara ta %d, adrese moarte %d, fără răspuns %d") % (
		rez.get("merge", 0), rez.get("oprit_tara", 0), rez.get("adresa_moarta", 0), rez.get("nu_raspunde", 0))


def textFaraRegistre(raspuns):
	"""mesajul cand niciun registru n-a dat liste: ce s-a intrebat si ce a raspuns fiecare (numai ce s-a masurat)"""
	parti = []
	for r in (raspuns or {}).get("registre", []):
		adresa = r.get("adresa", "")
		gazda = adresa.split("/")[2] if "://" in adresa else adresa
		parti.append("%s: %s" % (gazda, _("nu a răspuns") if r.get("liste", -1) < 0 else _("liste: %d") % r.get("liste", 0)))
	if parti:
		return _("Niciun registru DVB-I nu a dat liste (%s). Verifică legătura receptorului la internet.") % "; ".join(parti)
	return _("Niciun registru DVB-I nu a dat liste. Verifică legătura receptorului la internet.")


def canaleLista(stare, adresa):
	"""cate canale (TV si radio) a dat lista la ultima descarcare, sau None daca nu s-a descarcat"""
	for l in stare.get("liste") or []:
		if l.get("adresa") == adresa and l.get("ok"):
			return int(l.get("tv", 0)) + int(l.get("radio", 0))
	return None


# actiunile randurilor ecranului de pe televizor (Screens/HdsDvbI.py HdsDvbISetup)
R_TARA = "tara"
R_REGIUNE = "regiune"
R_LISTA = "lista"
R_REZERVA = "rezerva"
R_INCERCARI = "incercari"
R_AVANSAT = "avansat"
R_INCHIDE = "inchide"


def randuriSetari(config, registru=None, stare=None, rez=None, incercare=None):
	"""Randurile ecranului DVB-I: [(text, actiune, valoare, explicatie, bifa)], in ordinea din fisa Stitch (dvbi-048);
	bifa = True / False la listele tarii (casuta desenata de ecran), None la celelalte."""
	stare = _dateStare(stare)
	r = [("%s %s" % (_("Țara:"), numeTara(config.get("tara", ""))), R_TARA, None,
		_("STÂNGA/DREAPTA schimbă țara. OK deschide lista țărilor din registrele DVB-I."), None)]
	if config.get("tara") and regiuniTarii(config, stare, registru):
		r.append(("%s %s" % (_("Regiunea:"), numeRegiune(config, stare, registru)), R_REGIUNE, None,
			_("STÂNGA/DREAPTA schimbă regiunea. Ordinea canalelor urmează numerele date pentru regiunea ta."), None))
	for l in listeleTarii(config, registru) if config.get("tara") else []:
		n = canaleLista(stare, l["adresa"])
		text = l["lista"] or l["adresa"]
		if n is not None and l["aleasa"]:
			text += " · %s %d" % (_("canale:"), n)
		elif l["proba"]:
			text += " (%s)" % _("listă de probă")
		expl = _("OK scoate sau pune lista. Furnizor: %s.") % (l["furnizor"] or "?")
		if l["proba"]:
			expl += " " + _("Listă de probă a registrului: canalele ei pot să nu meargă.")
		r.append((text, R_LISTA, l["adresa"], expl, bool(l["aleasa"])))
	r.append(("%s %s" % (_("Trecere singură pe internet când satelitul nu se recepționează:"),
		_("da") if rezervaPornita(config) else _("nu")), R_REZERVA, None,
		_("Când satelitul unui canal nu se recepționează, imaginea vine singură de pe internet, dacă lista are canalul; se întoarce pe satelit când semnalul revine."), None))
	r.append((textIncercari(rez or {}, incercare), R_INCERCARI, None,
		_("OK încearcă din nou toate canalele, din casa ta. Cele oprite pentru țara ta se pot vedea cu VPN-ul receptorului pornit."), None))
	r.append(("%s %d" % (_("Adrese puse de mână și liste predefinite (avansat):"), len(config.get("url_uri", [])) +
		len(config.get("predefinite", []))), R_AVANSAT, None,
		_("OK deschide adresele puse de mână, listele predefinite și pornirea DVB-I."), None))
	r.append((_("Închide"), R_INCHIDE, None, "", None))
	return r


# ------------------------------------------------------------------ intrebarea registrelor (pe un fir)
_REGISTRE = {"in_curs": False, "ora": 0}


def stareRegistre():
	return dict(_REGISTRE)


def intreabaRegistrele(la_gata=None, acum=None, intreaba=None, salveaza=None, fir=True):
	"""intreaba toate registrele pe un fir si scrie raspunsul pe disc; la_gata(raspuns) pe firul enigma2 (sau pe loc,
	fara reactor). -> False daca o intrebare e deja in curs. 'intreaba'/'salveaza'/'fir' sunt pentru probe."""
	acum = time.time() if acum is None else acum
	if _REGISTRE["in_curs"] and acum - _REGISTRE["ora"] < MAX_REINCARCARE_S:
		return False
	_REGISTRE.update(in_curs=True, ora=acum)
	R = _R()
	intreaba = intreaba or R.intreabaToate
	salveaza = salveaza or R.salveaza

	def _lucru():
		raspuns = None
		try:
			raspuns = intreaba()
			if raspuns.get("liste"):
				salveaza(raspuns)
		except Exception as eroare:
			print("[HdsDvbISetari] registrele: %s" % eroare)
		_REGISTRE.update(in_curs=False)
		if la_gata is not None:
			try:
				from twisted.internet import reactor
				reactor.callFromThread(la_gata, raspuns)
			except Exception:
				la_gata(raspuns)

	if fir:
		import threading
		threading.Thread(target=_lucru, name="HdsDvbI-registre", daemon=True).start()
	else:
		_lucru()
	return True


# ------------------------------------------------------------------ reincarcarea
def stareReincarcare():
	return dict(_REINCARCARE)


def reincarca(la_gata=None, plugin=None, acum=None):
	"""Reincarcarea acum (ca DVB-I Reload Now pe televizor): managerul primeste setarile din fisier, apoi
	plugin.reincarca_acum pe firul lui. `la_gata(succes, eroare)` vine pe firul enigma2. -> False daca o reincarcare e
	deja in curs (nu porneste a doua)."""
	acum = time.time() if acum is None else acum
	# o reincarcare "in curs" de mai mult de MAX_REINCARCARE_S nu mai raspunde (firul ei n-a dat rezultatul): nu mai opreste
	if _REINCARCARE["in_curs"] and acum - _REINCARCARE["ora"] < MAX_REINCARCARE_S:
		return False
	p = _plugin(plugin)
	_REINCARCARE.update(in_curs=True, gata=False, succes=None, eroare="", ora=acum)
	manager = getattr(p, "_manager", None)
	if manager is not None:
		try:
			manager._config = citeste()
		except Exception as eroare:
			print("[HdsDvbISetari] setarile managerului: %s" % eroare)

	def _gata(succes, eroare=None):
		_REINCARCARE.update(in_curs=False, gata=True, succes=bool(succes), eroare=str(eroare or ""))
		if la_gata is not None:
			la_gata(succes, eroare)

	try:
		p.reincarca_acum(la_gata=_gata)
	except Exception as eroare:
		_gata(False, str(eroare))
	return True
