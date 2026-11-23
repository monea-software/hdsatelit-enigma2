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
import sys
import time

CALE_CONFIG = "/etc/enigma2/hdsdvbi.conf"
INTERVAL_IMPLICIT = "3600"
MAX_URL = 1024
MAX_URL_URI = 64
MAX_REINCARCARE_S = 600   # listele se descarca cu 15 s pe lista; mai mult de atat inseamna un fir pierdut


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect; textul se traduce la folosire cu _()"""
	return text


# fara_liste (0.6.2): reincarcarea s-a terminat fara nimic de descarcat (pluginul: _FARA_LISTE); ecranul si pagina web
# spun atunci TEXT_FARA_LISTE, nu "terminată cu succes"
_REINCARCARE = {"in_curs": False, "gata": False, "succes": None, "eroare": "", "ora": 0, "fara_liste": False}
TEXT_FARA_LISTE = N_("Nu e nicio listă DVB-I de descărcat: alege țara sau pune o adresă în Adrese puse de mână "
	"(avansat).")


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
		"regiune": "", "liste_oprite": [], "liste_puse": [], "rezerva": "da", "toate_tarile": "da"}


def taraReceptorului():
	"""Codul de 3 litere al tarii receptorului: din locul ales (Components/HdsLocul), altfel din limba meniului
	(Components/HdsListeCabluTerestru.tara_alfa3); "" cand nu se stie."""
	try:
		from Components import HdsListeCabluTerestru as L
	except Exception:
		return ""
	try:
		from Components import HdsLocul
		t = (HdsLocul.stare().get("tara") or "").strip().upper()
		if _codTara(t):
			return t
		if L.ALFA3.get(t):
			return L.ALFA3[t]
	except Exception:
		pass
	try:
		t = L.tara_alfa3() or ""
		return t if _codTara(t) else ""
	except Exception:
		return ""


def _cuTaraReceptorului(config, tara=None):
	"""Fara randul tara in fisier (tara nealeasa niciodata): tara receptorului, ca listele ei sa se ia singure;
	"tara_automata" o arata. Un rand "tara =" gol (Nicio tara, aleasa de om) ramane gol."""
	tara = taraReceptorului() if tara is None else tara
	config["tara"] = tara
	config["tara_automata"] = bool(tara)
	return config


def citeste(cale=None, tara_receptorului=None):
	"""Setarile din fisier (formatul pluginului); fara fisier, cele implicite. Fara randul tara, tara receptorului
	(_cuTaraReceptorului; tara_receptorului e pentru probe)."""
	config = implicit()
	cale = cale or CALE_CONFIG
	if not os.path.exists(cale):
		if cale == CALE_CONFIG:
			_memoreaza(config)
		return _cuTaraReceptorului(config, tara_receptorului)
	scrisa = False
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
					scrisa = True
					config["tara"] = val.upper() if _codTara(val.upper()) else ""
				elif cheie == "regiune":
					config["regiune"] = val if _regiuneBuna(val) else ""
				elif cheie in ("lista_oprita", "lista_pusa"):
					lista = config["liste_oprite" if cheie == "lista_oprita" else "liste_puse"]
					if urlBun(val) and val not in lista and len(lista) < MAX_URL_URI:
						lista.append(val)
				elif cheie == "rezerva":
					config["rezerva"] = val.lower()
				elif cheie == "toate_tarile":
					config["toate_tarile"] = val.lower()
	except (IOError, OSError) as eroare:
		print("[HdsDvbISetari] citirea %s: %s" % (cale, eroare))
	if not scrisa:
		_cuTaraReceptorului(config, tara_receptorului)
	if cale == CALE_CONFIG:
		_memoreaza(config)
	return config


def _memoreaza(config):
	from Components import HdsSalvareLista
	HdsSalvareLista.memoreaza(config)


def scrie(config, cale=None, plugin=None):
	"""Nu suprapune salvarea paginii existente peste salvarea listei."""
	from Components import HdsSalvareLista as L
	if (cale is None or cale == CALE_CONFIG) and L._OCUPAT[0]:
		return False
	if not L._ZAVOR.acquire(False):
		return False
	try:
		return _scrie(config, cale, plugin)
	finally:
		L._ZAVOR.release()


def _scrie(config, cale=None, plugin=None):
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
		"# toate_tarile = da / nu: si listele celorlalte tari, dupa ale tarii alese, grupate pe tari (TODO 1883)",
		"toate_tarile = %s" % config.get("toate_tarile", "da"),
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
		if cale == CALE_CONFIG:
			def notifica():
				_memoreaza(config)
				m = sys.modules.get("Components.HdsDvbIRezerva")
				if m is not None:
					m.rezervaSchimbata(rezervaPornita(config))
			import threading
			if threading.current_thread() is threading.main_thread():
				notifica()
			else:
				from twisted.internet import reactor
				reactor.callFromThread(notifica)
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
		# 0.6.2: "adresa" (text deja tradus), ca pagina web; urlBun refuza si spatiile
		return False, _("Adresa trebuie să înceapă cu http:// sau https:// și să nu aibă spații sau semne speciale.")
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


# Lista scoasa de om din lista de canale nu mai revine singura. Din fabrica buchetul "Canale de pe internet (DVB-I)" e
# in lista si gol, cu explicatia (pluginul DVB-I, _asiguraBuchetul); cand omul il scoate din lista de canale
# (Screens/ChannelSelection.removeBouquet), semnul de mai jos tine minte asta: pluginul nu-l mai scrie si nu-l mai
# leaga, nici la pornire, nici la reincarcarea din ora in ora. Descarcarea listelor, starea si trecerea pe internet merg mai departe. Randul
# "Arată lista în lista de canale" (ecranul DVB-I si pagina web) il pune la loc sau il scoate. Semnul e un fisier
# separat de hdsdvbi.conf (scrierea setarilor ar fixa tara aleasa singura), cate un cuvant pe rand: tv, radio; in
# /etc/enigma2, deci si in copia setarilor.
CALE_SCOASA = "/etc/enigma2/hdsdvbi.scoasa"
FELURI_BUCHET = {"userbouquet.hdsdvbi.tv": "tv", "userbouquet.hdsdvbi.radio": "radio"}
R_IN_LISTA = "in_lista"


def felBuchet(fisier):
	"""'tv' / 'radio' pentru fisierul (sau calea, sau referinta cu FROM BOUQUET) unui buchet DVB-I, altfel None."""
	text = fisier or ""
	if 'FROM BOUQUET "' in text:
		text = text.split('FROM BOUQUET "', 1)[1].split('"', 1)[0]
	return FELURI_BUCHET.get(os.path.basename(text))


def listeScoase(cale=None):
	"""Felurile scoase de om din lista de canale: set din 'tv', 'radio'."""
	try:
		with open(cale or CALE_SCOASA, "r", encoding="utf-8", errors="replace") as f:
			return set(c for c in f.read().split() if c in ("tv", "radio"))
	except (IOError, OSError):
		return set()


def tineMinteScoasa(feluri, scoasa=True, cale=None):
	"""Semnul listei scoase pus (scoasa=True) sau ridicat pentru felurile date. Fara niciun fel ramas, fisierul se
	sterge. -> True daca s-a schimbat ceva."""
	cale = cale or CALE_SCOASA
	vechi = listeScoase(cale)
	nou = (vechi | set(feluri)) if scoasa else (vechi - set(feluri))
	if nou == vechi:
		return False
	if scoasa:
		_pazaStieDeOm()
	try:
		if not nou:
			os.unlink(cale)
			return True
		tmp = cale + ".nou"
		with open(tmp, "w", encoding="utf-8") as f:
			f.write("".join("%s\n" % x for x in sorted(nou)))
		os.replace(tmp, cale)
		return True
	except (IOError, OSError) as eroare:
		print("[HdsDvbISetari] semnul listei scoase: %s" % eroare)
		return False


def _pazaStieDeOm():
	"""Paza buchetelor imaginii (Components/HdsBucheteOrfane, ceasul de un minut) leaga la loc DVB-I TV si DVB-I Radio cand
	lipsesc amandoua dintr-odata, ca dupa o lista de canale pusa de alt program; scoaterea de acum e a omului, ca la
	editorul de canale: paza o tine minte si nu le mai pune la loc. Numai daca paza e incarcata (fara import aici)."""
	import sys
	O = sys.modules.get("Components.HdsBucheteOrfane")
	try:
		if O is not None and isinstance(getattr(O, "_PAZA", None), dict):
			O._PAZA["omul"] = True
	except Exception as eroare:
		print("[HdsDvbISetari] paza buchetelor: %s" % eroare)


def scoasaDeOm(fisier, cale=None):
	"""Omul a scos din lista de canale buchetul `fisier` (numele, calea sau referinta): daca e al DVB-I, nu se mai pune
	singur la loc. -> True daca s-a tinut minte acum."""
	fel = felBuchet(fisier)
	return bool(fel) and tineMinteScoasa([fel], True, cale)


def inListaDeCanale(cale_bouquets=None, cale=None):
	"""Randul "Arată lista în lista de canale": da cand buchetul DVB-I TV e chiar in bouquets.tv si nu e scos de om."""
	if "tv" in listeScoase(cale):
		return False
	try:
		with open(cale_bouquets or "/etc/enigma2/bouquets.tv", "r", encoding="utf-8", errors="replace") as f:
			return 'FROM BOUQUET "userbouquet.hdsdvbi.tv"' in f.read()
	except (IOError, OSError):
		return False


def comutaInLista(plugin=None, cale=None, cale_bouquets=None):
	"""OK pe randul "Arată lista în lista de canale" (si Da/Nu din web): lista DVB-I (TV si radio) pusa la loc in lista
	de canale, sau scoasa, pe loc. -> True daca acum e in lista."""
	return puneInLista(not inListaDeCanale(cale_bouquets, cale), plugin, cale)


def puneInLista(da, plugin=None, cale=None):
	"""Lista DVB-I pusa in lista de canale (da) sau scoasa (nu): semnul, apoi legarea prin plugin (fara plugin numai
	semnul). Cu da, listele se si descarca din nou, ca buchetul gol sa se umple. -> da."""
	tineMinteScoasa(["tv", "radio"], not da, cale)
	try:
		p = _plugin(plugin)
	except Exception:
		p = None
	try:
		if p is not None and hasattr(p, "legaInLista"):
			p.legaInLista(da)
	except Exception as eroare:
		print("[HdsDvbISetari] legarea listei DVB-I: %s" % eroare)
	if da and p is not None and getattr(p, "_manager", None) is not None:
		reincarca(plugin=p)
	return bool(da)


def rezervaPornita(config):
	return str(config.get("rezerva", "da")).lower() in ("da", "yes", "1", "true")


def comutaRezerva(config):
	config["rezerva"] = "nu" if rezervaPornita(config) else "da"


# TODO 1883 (Eduard 29.10.2026 13:24): "Acolo intră listele din toate țările, per țări, indiferent că e din România sau
# din alte țări. Ca o sursă suplimentară de canale care dacă merg în țara aia bine, dacă nu iar bine." Cu toate_tarile
# (implicit da), dupa listele tarii alese vin listele adevarate (nu de proba) ale celorlalte tari si cele fara tara,
# grupate pe tari (in buchet cu un marcaj pe tara: pluginul DVB-I, grupeAdrese). Nimic nu se scoate; alegerea tarii
# ramane (listele ei primele, regiunea, listele de proba puse de mana). Registrele dau tarile TINTA ale unei liste, nu
# daca e blocata in afara lor: semnul "numai în <țara>" nu se pune, fiindca nu se stie (incercarea din casa,
# HdsDvbIIncercare, spune "oprite pentru țara ta" la canalele care chiar nu merg).

def toateTarilePornit(config):
	return str(config.get("toate_tarile", "da")).lower() in ("da", "yes", "1", "true")


def comutaToateTarile(config):
	config["toate_tarile"] = "nu" if toateTarilePornit(config) else "da"


def listeleAltorTari(config, registru=None):
	"""[{"adresa", "lista", "furnizor", "tara"}]: listele adevarate din registre care nu sunt ale tarii alese (si nici
	scoase de om), cu tara grupei (prima tara tinta; "" = fara tara), dupa numele tarii (cele fara tara la coada), apoi
	dupa nume; [] cu toate_tarile oprit"""
	if not toateTarilePornit(config):
		return []
	tara = (config.get("tara") or "").upper()
	oprite = set(config.get("liste_oprite", []))
	rez = []
	for l in _registru(registru).get("liste", []):
		if l.get("proba") or l["adresa"] in oprite:
			continue
		tinte = [t.upper() for t in l.get("tari", [])]
		if tara and tara in tinte:
			continue
		rez.append({"adresa": l["adresa"], "lista": l.get("lista", ""), "furnizor": l.get("furnizor", ""),
			"tara": tinte[0] if tinte else ""})
	nume = dict((t, numeTara(t).lower()) for t in set(x["tara"] for x in rez if x["tara"]))
	rez.sort(key=lambda x: (not x["tara"], nume.get(x["tara"], ""), x["lista"].lower()))
	return rez


def grupeAdrese(config, registru=None):
	"""{adresa: cod de tara} pentru marcajele buchetului (pluginul DVB-I): listele tarii alese -> tara ei, ale
	celorlalte -> tara grupei lor ("" = fara tara); {} cu toate_tarile oprit (buchetul ca inainte, fara marcaje)"""
	if not toateTarilePornit(config):
		return {}
	rez = {}
	tara = (config.get("tara") or "").upper()
	if tara:
		for l in listeleTarii(config, registru):
			if l["aleasa"]:
				rez[l["adresa"]] = tara
	for l in listeleAltorTari(config, registru):
		rez.setdefault(l["adresa"], l["tara"])
	return rez


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
		try:
			rez += [l["adresa"] for l in listeleAltorTari(config, registru)]
		except Exception as eroare:
			print("[HdsDvbISetari] listele celorlalte tari: %s" % eroare)
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


def faraListe(stare=None):
	"""(True, tara) cand ultima reincarcare DVB-I a aflat ca tara de acum (cod de 3 litere) nu are liste in registre
	(Plugins/SystemPlugins/HdsDvbI, starea "fara_liste"); altfel (False, ""). Folosit de lista de canale (OK si textul
	buchetului DVB-I gol) si de pagina web a listei."""
	try:
		st = _dateStare(stare) or {}
		if st.get("fara_liste") and st.get("tara"):
			return True, st.get("tara")
	except Exception as e:
		print("[HdsDvbISetari] starea DVB-I: %s" % e)
	return False, ""


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
		if not listeleTarii(config, registru):
			return "chihlimbar", "%s · %s" % (cap, _("nicio listă încă")), _(
				"Registrele DVB-I nu au încă nicio listă pentru această țară. Receptorul verifică singur în fiecare zi.")
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


def numarAscunse(stare=None):
	"""EPG2: (cate canale sunt ascunse din buchet pana merg din nou, cate adrese s-au scos din liste: clipuri si imagini
	de proba), din starea DVB-I"""
	stare = _dateStare(stare)
	ascunse = sum(1 for c in stare.get("canale") or [] if c.get("ascuns"))
	scoase = stare.get("scoase")
	try:
		n_scoase = sum(int(v) for v in scoase.values()) if isinstance(scoase, dict) else 0
	except (TypeError, ValueError):
		n_scoase = 0
	return ascunse, n_scoase


def textAscunse(stare=None):
	"""EPG2: fraza din explicatia randului incercarilor: canalele care nu merg din casa nu apar in lista de canale pana
	merg din nou, clipurile si imaginile de proba nu intra deloc; cu numerele de acum"""
	ascunse, scoase = numarAscunse(stare)
	text = _("Canalele care nu merg din casa ta nu apar în lista de canale până merg din nou; clipurile și imaginile de "
		"probă din liste nu intră deloc.")
	if ascunse or scoase:
		text += " " + _("Acum ascunse: %d, scoase: %d.") % (ascunse, scoase)
	return text


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
	"""cate canale (TV si radio) a dat lista la ultima descarcare in buchet (EPG2: fara cele ascunse pana merg din nou),
	sau None daca nu s-a descarcat"""
	for l in stare.get("liste") or []:
		if l.get("adresa") == adresa and l.get("ok"):
			return max(0, int(l.get("tv", 0)) + int(l.get("radio", 0)) - int(l.get("ascunse", 0) or 0))
	return None


# ------------------------------------------------------------------ listele care nu raspund (DVK, 15.11.2026)
# O lista care nu raspunde sta in pauza crescatoare (Components/HdsDvbISurse, DVJ). Ecranul DVB-I, ecranul avansat si
# pagina web spun la fiecare lista de cand nu raspunde si cand se incearca din nou. Datele vin din aceeasi stare ca a
# pluginului (pluginul._surse()): o a doua citire a fisierului ar ramane in urma, pentru ca starea se citeste o data.
TEXT_SEMN_NU_RASPUNDE = N_("nu răspunde")


def _surse(plugin=None):
	try:
		f = getattr(_plugin(plugin), "_surse", None)
		return f() if f is not None else None
	except Exception:
		return None


def _deCand(secunde):
	"""'Nu răspunde de 3 zile.' din secundele trecute de la prima cadere (zile peste o zi, ore sub o zi)"""
	ore = int(max(0, secunde)) // 3600
	zile = ore // 24
	if zile >= 2:
		# romana: 20-99 (si 100, 200 ...) cer "de" inainte de substantiv
		if zile % 100 == 0 or zile % 100 >= 20:
			return _("Nu răspunde de %d de zile.") % zile
		return _("Nu răspunde de %d zile.") % zile
	if zile == 1:
		return _("Nu răspunde de o zi.")
	if ore >= 20:
		return _("Nu răspunde de %d de ore.") % ore
	if ore >= 2:
		return _("Nu răspunde de %d ore.") % ore
	if ore == 1:
		return _("Nu răspunde de o oră.")
	return _("Nu răspunde de mai puțin de o oră.")


def textNuRaspunde(adresa, surse=None, acum=None, plugin=None):
	"""'' daca lista raspunde (sau n-a fost incercata), altfel fraza intreaga: 'Nu răspunde de 3 zile. Următoarea
	încercare: azi, 14:30.' Numai citire; nimic de ales sau de confirmat pentru om."""
	su = surse if surse is not None else _surse(plugin)
	if su is None or not adresa:
		return ""
	try:
		v = su.faraRaspuns(adresa)
	except Exception:
		return ""
	if not v:
		return ""
	prima, _urmatoarea = v
	acum = time.time() if acum is None else acum
	if acum < prima - 300:
		# ceasul receptorului e in urma (pornire inainte de NTP): nici durata, nici ora pauzei nu sunt adevarate, iar
		# pluginul o incearca oricum la trecerea urmatoare (HdsDvbISurse.inPauza, CEAS_INAPOI_S); nu spunem nimic
		return ""
	text = _deCand(acum - prima)
	try:
		pana = su.inPauza(adresa, acum)
	except Exception:
		pana = 0
	if pana:
		return "%s %s" % (text, _("Următoarea încercare: %s.") % oraText(pana, acum))
	return "%s %s" % (text, _("Se încearcă din nou la următoarea reîncărcare."))


def stariAdrese(adrese, surse=None, acum=None, plugin=None):
	"""{adresa: textNuRaspunde} numai pentru adresele care nu raspund (pagina web, ecranul avansat)"""
	su = surse if surse is not None else _surse(plugin)
	rez = {}
	if su is None:
		return rez
	for a in adrese or []:
		t = textNuRaspunde(a, su, acum)
		if t:
			rez[a] = t
	return rez


# actiunile randurilor ecranului de pe televizor (Screens/HdsDvbI.py HdsDvbISetup)
R_TARA = "tara"
R_REGIUNE = "regiune"
R_LISTA = "lista"
R_REZERVA = "rezerva"
R_TOATE = "toate_tarile"
R_INCERCARI = "incercari"
R_AVANSAT = "avansat"
R_INCHIDE = "inchide"


def randuriSetari(config, registru=None, stare=None, rez=None, incercare=None, surse=None, acum=None, in_lista=None):
	"""Randurile ecranului DVB-I: [(text, actiune, valoare, explicatie, bifa)], in ordinea din fisa Stitch (dvbi-048);
	bifa = True / False la listele tarii (casuta desenata de ecran), None la celelalte. DVK: lista bifata care nu
	raspunde are semnul scurt in rand si fraza intreaga (de cand, urmatoarea incercare) in explicatie. in_lista: randul
	"Arată lista în lista de canale" (None = citit acum, inListaDeCanale)."""
	stare = _dateStare(stare)
	surse = surse if surse is not None else _surse()
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
		nu = textNuRaspunde(l["adresa"], surse, acum) if l["aleasa"] and surse is not None else ""
		if nu:
			text += " · %s" % _(TEXT_SEMN_NU_RASPUNDE)
			expl = "%s %s" % (nu, expl)
		r.append((text, R_LISTA, l["adresa"], expl, bool(l["aleasa"])))
	n_alte = len(listeleAltorTari(config, registru)) if config.get("tara") and toateTarilePornit(config) else 0
	r.append(("%s %s" % (_("Liste din toate țările:"), (_("da") + (" · %s %d" % (_("liste:"), n_alte) if n_alte else ""))
		if toateTarilePornit(config) else _("nu")), R_TOATE, None,
		_("OK pornește sau oprește. După listele țării tale vin cele ale celorlalte țări, grupate pe țări: canalele merg "
		"dacă furnizorul le lasă și din țara ta."), None))
	r.append(("%s %s" % (_("Trecere singură pe internet când satelitul nu se recepționează:"),
		_("da") if rezervaPornita(config) else _("nu")), R_REZERVA, None,
		_("Când satelitul unui canal nu se recepționează, imaginea vine singură de pe internet, dacă lista are canalul; se întoarce pe satelit când semnalul revine.") + " " +
		_("Aceeași alegere se găsește în Meniu > Setări > Setări listă de canale: „Când canalul nu pornește, treci singur pe sursa DVB-I a postului”. Este pornită din fabrică și independentă de trecerea pe alt canal cu același nume."), None))
	r.append((textIncercari(rez or {}, incercare), R_INCERCARI, None,
		_("OK încearcă din nou toate canalele, din casa ta. Cele oprite pentru țara ta se pot vedea cu VPN-ul receptorului pornit.")
		+ " " + textAscunse(stare), None))
	if in_lista is None:
		in_lista = inListaDeCanale()
	r.append(("%s: %s" % (_("Arată lista în lista de canale"), _("da") if in_lista else _("nu")), R_IN_LISTA, None,
		_("OK pune lista Canale de pe internet (DVB-I) în lista de canale sau o scoate. Scoasă, nu mai revine singură."),
		None))
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


# ------------------------------------------------------------------ cautarea acum (lista de canale, pagina web)
def cautaAcum(la_gata=None, plugin=None):
	"""Cele mai noi liste DVB-I acum: registrele intrebate din nou, apoi reincarcarea cu setarile din fisier (tara
	receptorului cand omul n-a ales alta); dupa ea reincarcarea din ora in ora merge singura. la_gata(succes, eroare)
	pe firul enigma2. -> False daca o cautare sau o reincarcare e deja in curs."""
	if _REINCARCARE["in_curs"] and time.time() - _REINCARCARE["ora"] < MAX_REINCARCARE_S:
		return False

	def _dupaRegistre(raspuns):
		if not reincarca(la_gata=la_gata, plugin=plugin) and la_gata is not None:
			la_gata(False, "")
	return intreabaRegistrele(la_gata=_dupaRegistre)


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
	_REINCARCARE.update(in_curs=True, gata=False, succes=None, eroare="", ora=acum, fara_liste=False)
	manager = getattr(p, "_manager", None)
	if manager is not None:
		try:
			manager._config = citeste()
		except Exception as eroare:
			print("[HdsDvbISetari] setarile managerului: %s" % eroare)

	def _gata(succes, eroare=None):
		fara = bool(succes) and bool((getattr(p, "_FARA_LISTE", None) or [False])[0])
		_REINCARCARE.update(in_curs=False, gata=True, succes=bool(succes), eroare=str(eroare or ""), fara_liste=fara)
		if la_gata is not None:
			la_gata(succes, eroare)

	try:
		p.reincarca_acum(la_gata=_gata)
	except Exception as eroare:
		_gata(False, str(eroare))
	return True
