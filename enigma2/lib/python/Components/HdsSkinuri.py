# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsSkinuri.py: alegerea skinului, aceeasi pe televizor (Skin Selection: Plugins/SystemPlugins/SkinSelector/plugin.py,
# deschis din Screens/SkinSelector.py) si in interfata web (HdsWebControl/intrari_web.py, pagina /skin), si pornirea
# sigura cu skinul ales (skin.py).
#
# - lista(): skinurile instalate de fapt, cate un dosar cu skin.xml chiar sub ${datadir}/enigma2
#   (/usr/share/enigma2/<dosar>/skin.xml), fara skin_default; skinul imaginii (HDSatelit) primul, apoi celelalte in
#   ordine alfabetica. skin.xml din radacina (o rama veche de 720x576 cu un singur ecran) nu e un skin de ales.
# - verificaSkin(): inainte de alegere, fisierul trebuie sa existe si sa inceapa cu elementul <skin> (numai inceputul
#   se citeste); rezolutia din <output> se citeste: ecranele HD Satelit care lipsesc din alt skin sunt scrise pentru
#   1920x1080 si skin.py le scaleaza la rezolutia lui (ScaraEcran), deci incap la orice rezolutie; numai la un skin mai
#   ingust de LATIME_LITERE_MICI (720x576) se spune ca literele lor ajung mici (avertismentRezolutie).
# - alege(): config.skin.primary_skin = "<dosar>/skin.xml", salvat; skinul se incarca la pornirea urmatoare a interfetei.
#
# PORNIREA (skinDePornit, chemat de skin.py inainte de ecrane): skinul ales se incarca primul, iar HDSatelit/skin.xml
# dupa el, ca rezerva: un ecran pe care skinul ales nu il are (ecranele proprii Hds* si celelalte ale imaginii) se ia
# din HDSatelit, scalat la rezolutia skinului ales si cu culorile si fonturile HDSatelit (skin.py); rama ferestrelor
# ramane a skinului ales. In modul sigur (HDS_MOD_SIGUR=1)
# skinul e mereu HDSatelit, ca la skin_user.xml. Tema interfetei (Clasic / Pro, Components/HdsTemaTv.py) e o varianta
# a skinului HDSatelit: skin_pro.xml se incarca numai cand skinul ales e HDSatelit, iar tema se alege numai atunci.
# Intoarcerea sigura pe HDSatelit, cu motivul spus omului:
#   - fisierul lipseste sau nu e un skin: se vede la pornire, se incarca HDSatelit;
#   - XML stricat (loadSkin cade): skin.py prinde eroarea, incarca HDSatelit si cheama incarcareCazuta();
#   - interfata se opreste neasteptat cu skinul ales (de pilda un font care nu e font: addFont opreste enigma2 din
#     cod nativ, fara exceptie Python): inainte de a-l incarca, skinDePornit scrie in RAM semnul PROBA (skinul si
#     secundele de la pornirea receptorului, ca /proc/uptime); daca la pornirea urmatoare semnul e tot acolo si
#     tools/enigma2.sh a scris intre timp o oprire neasteptata in /tmp/hds-enigma2.caderi (mecanismul modului sigur,
#     Components/HdsModSigur.py), skinul nu se mai incarca. Semnul se sterge dupa PROBA_S secunde de mers ale
#     interfetei (pornireReusita, din extensia SkinSelector la pornirea sesiunii). Peste el ramane modul sigur, la a
#     cincea oprire in 10 minute.
#   La intoarcere setarea se pune inapoi pe HDSatelit (salvata la pornirea sesiunii) si motivul se tine in RAM (REFUZ):
#   televizorul il spune o data dupa pornire (mesaj), ecranul Skin Selection si pagina /skin il arata cat e acolo. O
#   alegere noua il sterge (si a aceluiasi skin: omul vrea sa incerce din nou).
#
# Modulul nu importa nimic din enigma2 la incarcare (skin.py il cheama inainte de ecrane; probele de pe PC dau radacina,
# config si fisierele din RAM).

import json
import os

IMPLICIT = "Default Skin"
NUME_POZA = "prev.png"
POZA_LIPSA = "SystemPlugins/SkinSelector/noprev.png"
DOSAR_IMAGINE = "HDSatelit"
SKIN_IMAGINE = DOSAR_IMAGINE + "/skin.xml"
LATIME_IMAGINE = 1920
INALTIME_IMAGINE = 1080
# sub latimea aceasta (720x576 si alte skinuri SD) ecranele HD Satelit scalate au litere mici (avertismentRezolutie)
LATIME_LITERE_MICI = 1024

RAM = "/tmp"
PROBA = RAM + "/hds-skin-proba"
REFUZ = RAM + "/hds-skin-refuz"
# acelasi fisier ca in tools/enigma2.sh.in (HDS_CADERI) si Components/HdsModSigur.py (CADERI)
CADERI = os.environ.get("HDS_CADERI") or RAM + "/hds-enigma2.caderi"
UPTIME = "/proc/uptime"
PROBA_S = 60

MOTIV_LIPSA = "lipsa"
MOTIV_NU_E_SKIN = "nu_e_skin"
MOTIV_XML = "xml"
MOTIV_CADERE = "cadere"


def N_(text):
	return text


def _t(text, traducere=None):
	if traducere is not None:
		try:
			return traducere(text)
		except Exception:
			return text
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


TEXT_MOTIV = {
	MOTIV_LIPSA: N_("fișierul skinului lipsește"),
	MOTIV_NU_E_SKIN: N_("fișierul nu e un skin"),
	MOTIV_XML: N_("skin.xml nu se poate citi: %s"),
	MOTIV_CADERE: N_("interfața s-a oprit neașteptat la pornirea cu el"),
}


def _jurnal(text):
	print("[HdsSkinuri] %s" % text)


def radacina():
	from enigma import eEnv
	return eEnv.resolve("${datadir}/enigma2/")


def _config(config=None):
	if config is not None:
		return config
	from Components.config import config
	return config


def lista(root=None):
	"""Numele skinurilor instalate (dosarele cu skin.xml chiar sub radacina), HDSatelit primul."""
	if root is None:
		root = radacina()
	skinuri = []
	try:
		nume = os.listdir(root)
	except OSError:
		return skinuri
	for n in nume:
		if n.startswith("skin_default") or n.startswith("."):
			continue
		if os.path.isfile(os.path.join(root, n, "skin.xml")):
			skinuri.append(n)
	skinuri.sort(key=lambda x: (x != DOSAR_IMAGINE, x.lower()))
	return skinuri


def numeDinValoare(valoare):
	"""Dosarul skinului dintr-o valoare a lui config.skin.primary_skin ("HDSatelit/skin.xml" -> "HDSatelit"), sau
	None cand valoarea nu e de forma <dosar>/skin.xml."""
	valoare = valoare or ""
	if not valoare.endswith("/skin.xml"):
		return None
	nume = valoare[:-len("/skin.xml")]
	if not nume or "/" in nume or "\\" in nume:
		return None
	return nume


def esteImaginii(valoare):
	"""True cand valoarea inseamna skinul imaginii (si cand e goala sau veche: "skin.xml" din radacina)."""
	return numeDinValoare(valoare) in (None, DOSAR_IMAGINE)


def curent(config=None):
	"""Dosarul skinului ales ("HDSatelit"), sau None cand alegerea nu are "/skin.xml" (skinul implicit)."""
	valoare = _config(config).skin.primary_skin.value
	i = valoare.find("/skin.xml")
	if i == -1:
		return None
	return valoare[:i]


def fisier(nume):
	"""Valoarea pentru config.skin.primary_skin."""
	if nume == IMPLICIT:
		return "skin.xml"
	return nume + "/skin.xml"


def caleSkin(root, nume):
	"""Calea lui skin.xml pentru un nume din lista, sau None pentru un nume care nu poate fi din lista (cai cu .., cu
	bare, cu inceput absolut, skin_default, fara skin.xml chiar in dosarul lui)."""
	if not isinstance(nume, str) or not nume or "\0" in nume:
		return None
	if "/" in nume or "\\" in nume or nume in (".", "..") or nume.startswith("skin_default") or nume.startswith("."):
		return None
	dosar = os.path.join(root, nume)
	baza = os.path.realpath(root)
	if os.path.commonpath([baza, os.path.realpath(dosar)]) != baza:
		return None
	cale = os.path.join(dosar, "skin.xml")
	return cale if os.path.isfile(cale) else None


def previzualizare(root, nume, poza_lipsa=None):
	"""Calea pozei skinului (prev.png din dosarul lui), altfel `poza_lipsa` (noprev.png al extensiei)."""
	if nume == IMPLICIT:
		cale = os.path.join(root, NUME_POZA)
	else:
		cale = os.path.join(root, nume, NUME_POZA)
	if not os.path.exists(cale):
		if poza_lipsa is None:
			from Tools.Directories import resolveFilename, SCOPE_PLUGINS
			poza_lipsa = resolveFilename(SCOPE_PLUGINS, POZA_LIPSA)
		cale = poza_lipsa
	return cale


def verificaSkin(cale):
	"""{"bun", "motiv", "detaliu", "latime", "inaltime"}: fisierul exista si incepe cu <skin>; rezolutia din primul
	<output><resolution> (citire de la inceput, oprita la primul <screen>)."""
	rez = {"bun": False, "motiv": "", "detaliu": "", "latime": 0, "inaltime": 0}
	if not cale or not os.path.isfile(cale):
		rez["motiv"] = MOTIV_LIPSA
		return rez
	import xml.etree.ElementTree as ET
	try:
		radacina_gasita = False
		for eveniment, el in ET.iterparse(cale, events=("start",)):
			if not radacina_gasita:
				radacina_gasita = True
				if el.tag != "skin":
					rez["motiv"] = MOTIV_NU_E_SKIN
					return rez
				continue
			if el.tag == "resolution" and not rez["latime"]:
				try:
					rez["latime"] = int(el.get("xres") or 0)
					rez["inaltime"] = int(el.get("yres") or 0)
				except ValueError:
					pass
			if el.tag in ("screen", "windowstyle", "fonts"):
				break
	except Exception as eroare:
		rez["motiv"] = MOTIV_XML
		rez["detaliu"] = str(eroare)[:200]
		return rez
	rez["bun"] = True
	return rez


def textMotiv(motiv, detaliu="", traducere=None):
	t = TEXT_MOTIV.get(motiv)
	if t is None:
		return detaliu or motiv
	t = _t(t, traducere)
	return t % detaliu if "%s" in t else t


def avertismentRezolutie(nume, v, traducere=None):
	"""Textul pentru un skin pe care ecranele HD Satelit ajung cu litere mici, sau "". Ecranele noastre se scaleaza la
	rezolutia skinului ales (skin.py, ScaraEcran), deci incap la orice rezolutie (1280x720, 1024x576, 3840x2160 fara
	nimic de spus); fonturile se inmultesc cu latimea / 1920, ca textul sa incapa in cutii, deci pe un skin mai ingust de
	LATIME_LITERE_MICI (720x576: 30 px -> 11 px) literele lor sunt mici."""
	if not v.get("latime") or v["latime"] >= LATIME_LITERE_MICI:
		return ""
	return _t("Skinul %s e făcut pentru %dx%d. Ecranele HD Satelit se micșorează ca să încapă în el, deci literele lor "
		"sunt mici.", traducere) % (nume, v["latime"], v["inaltime"])


def alege(nume, config=None, root=None, traducere=None, refuz=None):
	"""OK pe ecran si /api/skin-alege: (bun, mesaj, avertisment). Skinul trebuie sa fie din lista si sa inceapa cu
	<skin>; alegerea se salveaza si se vede la pornirea urmatoare a interfetei. Refuzul tinut minte se sterge (si pentru
	acelasi skin: omul vrea sa-l incerce din nou)."""
	if root is None:
		root = radacina()
	cale = caleSkin(root, nume)
	if cale is None:
		return False, _t("Skinul nu există.", traducere), ""
	v = verificaSkin(cale)
	if not v["bun"]:
		return False, _t("Skinul %s nu se poate folosi: %s.", traducere) % (nume, textMotiv(v["motiv"], v["detaliu"],
			traducere)), ""
	c = _config(config).skin.primary_skin
	c.value = fisier(nume)
	c.save()
	# o alegere noua: motivul vechi nu mai e de spus (iar acelasi skin ales din nou primeste o noua incercare)
	stergeRefuz(refuz)
	return True, _t("Skinul ales se vede după repornirea interfeței.", traducere), avertismentRezolutie(nume, v, traducere)


def aspect(config=None):
	return _config(config).skin.layout_meniu.value


def seteazaAspect(valoare, config=None):
	"""Aspectul meniului (lista sau dale), salvat pe loc."""
	c = _config(config).skin.layout_meniu
	c.value = valoare
	c.save()


def comutaAspect(config=None):
	"""Tasta galbena: lista <-> dale."""
	seteazaAspect("lista" if aspect(config) == "dale" else "dale", config)


# ------------------------------------------------------------------ pornirea sigura

def _uptime(cale=None):
	try:
		with open(cale or UPTIME, encoding="utf-8", errors="replace") as f:
			return int(float(f.read().split()[0]))
	except (IOError, OSError, ValueError, IndexError):
		return 0


def _citesteJson(cale):
	try:
		with open(cale, encoding="utf-8") as f:
			d = json.load(f)
		return d if isinstance(d, dict) else None
	except (IOError, OSError, ValueError):
		return None


def _scrieJson(cale, date):
	try:
		temp = cale + ".nou"
		with open(temp, "w", encoding="utf-8") as f:
			json.dump(date, f, ensure_ascii=False)
		os.replace(temp, cale)
		return True
	except (IOError, OSError) as eroare:
		_jurnal("%s: %s" % (cale, eroare))
		return False


def _sterge(cale):
	try:
		os.unlink(cale)
	except OSError:
		pass


def _caderiDupa(pornit, caderi=None):
	"""True cand /tmp/hds-enigma2.caderi are o oprire neasteptata scrisa la sau dupa `pornit` (secunde de uptime)."""
	try:
		with open(caderi or CADERI, encoding="utf-8", errors="replace") as f:
			for rand in f:
				p = rand.split()
				if p and p[0].isdigit() and int(p[0]) >= pornit:
					return True
	except (IOError, OSError):
		pass
	return False


def citesteRefuz(cale=None):
	return _citesteJson(cale or REFUZ)


def stergeRefuz(cale=None):
	_sterge(cale or REFUZ)


def refuza(valoare, motiv, detaliu="", cale=None):
	"""Tine minte in RAM de ce skinul ales nu a pornit (pentru mesajul de pe televizor si pentru pagina)."""
	r = {"skin": valoare, "motiv": motiv, "detaliu": detaliu, "aratat": False}
	_scrieJson(cale or REFUZ, r)
	_jurnal("skinul %s nu porneste (%s %s), ramane %s" % (valoare, motiv, detaliu, SKIN_IMAGINE))
	return r


def skinDePornit(valoare, mediu=None, root="/usr/share/enigma2", proba=None, refuz=None, caderi=None, uptime=None):
	"""Ce skin incarca skin.py: (valoarea de incarcat in plus fata de HDSatelit, sau None; refuzul, sau None).
	None, None = numai HDSatelit, fara nimic de spus (skinul imaginii e cel ales sau modul sigur)."""
	mediu = os.environ if mediu is None else mediu
	proba = proba or PROBA
	if esteImaginii(valoare):
		_sterge(proba)
		return None, None
	if mediu.get("HDS_MOD_SIGUR") == "1":
		return None, None
	r = citesteRefuz(refuz)
	if r and r.get("skin") == valoare:
		return None, r
	semn = _citesteJson(proba)
	if semn and semn.get("skin") == valoare and _caderiDupa(int(semn.get("pornit") or 0), caderi):
		_sterge(proba)
		return None, refuza(valoare, MOTIV_CADERE, "", refuz)
	v = verificaSkin(os.path.join(root, valoare))
	if not v["bun"]:
		_sterge(proba)
		return None, refuza(valoare, v["motiv"], v["detaliu"], refuz)
	_scrieJson(proba, {"skin": valoare, "pornit": _uptime(uptime) if uptime is None or isinstance(uptime, str) else
		int(uptime)})
	return valoare, None


def incarcareCazuta(valoare, eroare, proba=None, refuz=None):
	"""skin.py: loadSkin pe skinul ales a cazut (XML stricat)."""
	_sterge(proba or PROBA)
	return refuza(valoare, MOTIV_XML, str(eroare)[:200], refuz)


def pornireReusita(proba=None):
	"""Interfata a mers PROBA_S secunde cu skinul ales: semnul probei se sterge."""
	_sterge(proba or PROBA)


def textRefuz(r, traducere=None):
	if not r:
		return ""
	nume = numeDinValoare(r.get("skin")) or r.get("skin") or ""
	return _t("Skinul ales (%s) nu a pornit: %s. Interfața a revenit la skinul HD Satelit.", traducere) % (nume,
		textMotiv(r.get("motiv"), r.get("detaliu", ""), traducere))


def deAratat(refuz=None):
	"""Refuzul nespus inca pe televizor (si il marcheaza spus), sau None."""
	cale = refuz or REFUZ
	r = citesteRefuz(cale)
	if not r or r.get("aratat"):
		return None
	r["aratat"] = True
	_scrieJson(cale, r)
	return r


def skinPornit():
	"""Valoarea skinului cu care a pornit interfata acum (skin.py.skinPornit), altfel skinul imaginii."""
	try:
		import skin
		return getattr(skin, "skinPornit", SKIN_IMAGINE) or SKIN_IMAGINE
	except Exception:
		return SKIN_IMAGINE
