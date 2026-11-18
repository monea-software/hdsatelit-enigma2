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
# TEMELE EXTERNE (Components/HdsTemaExterna.py, incarcat numai pentru ele): la alegere verificarea intreaga (tot XML-ul si
# includerile, rezolutia, fonturile, componentele) si jurnalul activarii pe disc, inainte de schimbarea setarii; la pornire
# numararea pornirilor in proba (o tema care opreste receptorul nu se incarca la nesfarsit, si dupa o repornire intreaga) si
# retragerea dupa trei opriri neasteptate in zece minute, chiar daca proba s-a terminat. Trei erori de ecran in 30 de secunde
# (mytest.py) retrag tema cu MOTIV_ECRANE, inainte de singura repornire a interfetei, numai daca macar una a trecut prin
# fisierele temei (eroareDinTema); un plugin care cade singur reporneste interfata, dar tema ramane. Cu tema HD Satelit nu ruleaza nimic din ele.
#
# Modulul nu importa nimic din enigma2 la incarcare (skin.py il cheama inainte de ecrane; probele de pe PC dau radacina,
# config si fisierele din RAM).

import json
import os
import re

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
MOTIV_ECRANE = "ecrane"
MOTIV_INCLUDE = "include"
MOTIV_REZOLUTIE = "rezolutie"
# R2K 0.7.5: placa nu primeste rezolutia temei (HdsTemaExterna.verificaRezolutiaPlacii); detaliul "1920x1080|2560x1440"
MOTIV_REZOLUTIE_PLACA = "rezolutie_placa"
MOTIV_SCRIERE = "scriere"
# atatea opriri neasteptate in zece minute retrag tema si dupa sfarsitul probei (modul sigur vine la cinci)
PRAG_CADERI = 3
# jurnalul activarii (Components/HdsTemaExterna.py); refuzul de acolo ramane si dupa repornirea receptorului
ACTIVARE = "/etc/enigma2/hds-tema-activare.json"


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
	MOTIV_LIPSA: N_("fișierul temei lipsește"),
	MOTIV_NU_E_SKIN: N_("fișierul nu e o temă"),
	MOTIV_XML: N_("fișierul temei nu se poate citi: %s"),
	MOTIV_CADERE: N_("interfața s-a oprit neașteptat cu ea; cauza exactă nu a fost stabilită"),
	MOTIV_ECRANE: N_("ecranele au dat erori de mai multe ori la rând; cauza exactă nu a fost stabilită"),
	MOTIV_INCLUDE: N_("lipsește sau e stricată o parte a temei: %s"),
	MOTIV_REZOLUTIE: N_("rezoluția temei nu e bună: %s"),
	MOTIV_REZOLUTIE_PLACA: N_("receptorul acesta arată interfața până la %s, iar tema cere %s. Alege FHD (1920x1080) în "
		"setările temei: tema revine singură la repornirea interfeței"),
	MOTIV_SCRIERE: N_("alegerea nu se poate ține minte pe receptor: discul e plin sau nu se poate scrie"),
}


def _jurnal(text):
	print("[HdsSkinuri] %s" % text)


# ------------------------------------------------------------------ fisierele temelor care nu sunt UTF-8 de la cap la coada
# Temele facute sau schimbate de oameni cu un editor de Windows pot avea randuri salvate in codarea veche a limbii lor
# (MERCUS-FHD, darog69, forum 1342: ecranul vremii cu "Wilgotno\x9c\xe6" in Windows-1250, restul fisierului in UTF-8, fara
# antet <?xml encoding?>). Expat cere UTF-8 si refuza tot fisierul ("not well-formed (invalid token)"), in orice imagine.
# Aici, NUMAI dupa un asemenea refuz: randurile care sunt UTF-8 bun raman neatinse, iar celelalte se citesc in codarea veche
# a limbii receptorului (implicit Windows-1250). Pe rand intreg, nu pe octet: "SZCZEG\xd3\xa3\xd3W" are "\xd3\xa3" care ar
# trece drept UTF-8 (alta litera). Fisierul omului nu se schimba pe disc. Un fisier UTF-8 bun sau cu antetul altei codari
# nu ajunge niciodata aici (se citeste ca pana acum); unul stricat altfel ramane refuzat, cu eroarea lui.
CODARE_VECHE = "cp1250"
CODARE_LIMBA = {"ru": "cp1251", "uk": "cp1251", "bg": "cp1251", "mk": "cp1251", "be": "cp1251", "sr": "cp1251",
	"el": "cp1253", "tr": "cp1254", "lt": "cp1257", "lv": "cp1257", "et": "cp1257", "he": "cp1255", "ar": "cp1256",
	"de": "cp1252", "fr": "cp1252", "es": "cp1252", "it": "cp1252", "pt": "cp1252", "nl": "cp1252",
	"da": "cp1252", "sv": "cp1252", "no": "cp1252", "nb": "cp1252", "fi": "cp1252", "ca": "cp1252", "is": "cp1252"}
# engleza nu e aici: interfata in engleza nu spune nimic despre limba temei (un polonez cu meniul in engleza ramane pe 1250)
SETARI = "/etc/enigma2/settings"


def codareVeche(setari=None):
	"""Codarea veche a limbii alese pe receptor (config.osd.language din settings), implicit Windows-1250."""
	try:
		with open(setari or SETARI, encoding="utf-8", errors="replace") as f:
			for rand in f:
				if rand.startswith("config.osd.language="):
					return CODARE_LIMBA.get(rand.split("=", 1)[1].strip()[:2].lower(), CODARE_VECHE)
	except (IOError, OSError):
		pass
	return CODARE_VECHE


def recodeaza(octeti, codare=None):
	"""(text UTF-8 in octeti, cate randuri s-au citit in codarea veche) sau None cand fisierul nu e de reparat aici: e UTF-8
	bun (eroarea XML e alta), are antetul altei codari (expat il citeste dupa antet) sau Python-ul n-are codarea veche."""
	try:
		octeti.decode("utf-8")
		return None
	except UnicodeDecodeError:
		pass
	inceput = octeti[:200].lstrip(b"\xef\xbb\xbf \t\r\n")
	if inceput.startswith(b"<?xml"):
		antet = inceput.split(b"?>", 1)[0].lower().replace(b"'", b'"')
		if b"encoding=" in antet and b'encoding="utf-8"' not in antet and b'encoding="utf8"' not in antet:
			return None
	codare = codare or codareVeche()
	import codecs
	try:
		codecs.lookup(codare)
	except LookupError:
		return None  # fara codarea in Python-ul receptorului: tema ramane refuzata cu eroarea ei, ca pana acum
	randuri, schimbate = [], 0
	for rand in octeti.split(b"\n"):
		try:
			randuri.append(rand.decode("utf-8"))
		except UnicodeDecodeError:
			try:
				randuri.append(rand.decode(codare))
			except UnicodeDecodeError:
				randuri.append(_randAmestecat(rand, codare))
			schimbate += 1
	return "\n".join(randuri).encode("utf-8"), schimbate


def _randAmestecat(rand, codare):
	"""Un rand cu litere UTF-8 si litere in codarea veche deodata (de pilda Ł in UTF-8 are octetul 0x81, pe care Windows-1250 nu
	il are, deci randul nu se poate citi intreg in nicio codare): bucatile UTF-8 bune raman, octetii ramasi se citesc in codarea
	veche (un octet fara litera acolo devine semnul de inlocuire), ca tema sa nu fie refuzata pentru un singur rand."""
	bucati, i = [], 0
	while i < len(rand):
		try:
			bucati.append(rand[i:].decode("utf-8"))
			break
		except UnicodeDecodeError as e:
			bucati.append(rand[i:i + e.start].decode("utf-8"))
			bucati.append(rand[i + e.start:i + e.end].decode(codare, "replace"))
			i += e.end
	return "".join(bucati)


def _recodat(cale, codare=None):
	"""(octeti UTF-8, randuri) din fisierul de la cale, cand recodeaza() il poate repara, altfel None."""
	try:
		with open(cale, "rb") as f:
			octeti = f.read()
	except (IOError, OSError):
		return None
	return recodeaza(octeti, codare)


def citesteXml(cale, codare=None):
	"""Radacina XML a unui fisier al temei: ET.parse ca pana acum; numai cand expat il refuza si fisierul are randuri in
	codarea veche a limbii (nu UTF-8), le citeste pe acelea in ea (recodeaza), cu un rand in jurnal. Altfel eroarea de la
	ET.parse, neschimbata."""
	import xml.etree.ElementTree as ET
	try:
		return ET.parse(cale).getroot()
	except ET.ParseError:
		r = _recodat(cale, codare)
		if r is None:
			raise
	_jurnal("%s: %d randuri care nu sunt UTF-8, citite ca %s" % (cale, r[1], codare or codareVeche()))
	return ET.fromstring(r[0])


def radacina():
	from enigma import eEnv
	return eEnv.resolve("${datadir}/enigma2/")


def _temaExterna():
	"""Components/HdsTemaExterna.py, incarcat numai cand e nevoie; None unde nu exista (probele cu modulul singur)."""
	try:
		from Components import HdsTemaExterna
		return HdsTemaExterna
	except ImportError:
		return None


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


def _inceputSkin(evenimente):
	"""elementele de la inceputul temei, pana la primul <screen>/<windowstyle>/<fonts> (verificaSkin nu citeste tot)"""
	for eveniment, el in evenimente:
		yield el
		if el.tag in ("screen", "windowstyle", "fonts"):
			return


def verificaSkin(cale):
	"""{"bun", "motiv", "detaliu", "latime", "inaltime"}: fisierul exista si incepe cu <skin>; rezolutia din primul
	<output><resolution> (citire de la inceput, oprita la primul <screen>)."""
	rez = {"bun": False, "motiv": "", "detaliu": "", "latime": 0, "inaltime": 0}
	if not cale or not os.path.isfile(cale):
		rez["motiv"] = MOTIV_LIPSA
		return rez
	import xml.etree.ElementTree as ET
	try:
		try:
			evenimente = list(_inceputSkin(ET.iterparse(cale, events=("start",))))
		except ET.ParseError:
			# randuri in codarea veche a limbii (nu UTF-8): citite ca in skin.py (citesteXml), altfel eroarea de mai sus
			r = _recodat(cale)
			if r is None:
				raise
			import io
			evenimente = list(_inceputSkin(ET.iterparse(io.BytesIO(r[0]), events=("start",))))
		radacina_gasita = False
		for el in evenimente:
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
	n = t.count("%s")
	if n > 1:
		# mai multe valori, despartite prin | in detaliu (MOTIV_REZOLUTIE_PLACA)
		p = (str(detaliu).split("|") + [""] * n)[:n]
		try:
			return t % tuple(p)
		except (TypeError, ValueError):
			return t
	return t % detaliu if n else t


def pastreazaAlegerea(r):
	"""True cand tema aleasa ramane aleasa dupa refuz: numai la rezolutia pe care placa n-o primeste. Tema nu e stricata;
	cand omul pune FHD in setarile ei, fisierul se schimba si tema porneste singura (skinDePornit, laPornire)."""
	return bool(r) and r.get("motiv") == MOTIV_REZOLUTIE_PLACA


def avertismentRezolutie(nume, v, traducere=None):
	"""Textul pentru un skin pe care ecranele HD Satelit ajung cu litere mici, sau "". Ecranele noastre se scaleaza la
	rezolutia skinului ales (skin.py, ScaraEcran), deci incap la orice rezolutie (1280x720, 1024x576, 3840x2160 fara
	nimic de spus); fonturile se inmultesc cu latimea / 1920, ca textul sa incapa in cutii, deci pe un skin mai ingust de
	LATIME_LITERE_MICI (720x576: 30 px -> 11 px) literele lor sunt mici."""
	if not v.get("latime") or v["latime"] >= LATIME_LITERE_MICI:
		return ""
	return _t("Tema %s e făcută pentru %dx%d. Ecranele HD Satelit se micșorează ca să încapă în ea, deci literele lor "
		"sunt mici.", traducere) % (nume, v["latime"], v["inaltime"])


def alege(nume, config=None, root=None, traducere=None, refuz=None):
	"""OK pe ecran si /api/skin-alege: (bun, mesaj, avertisment). Tema trebuie sa fie din lista si sa inceapa cu <skin>; o
	tema externa e verificata intreaga, iar jurnalul activarii se scrie inainte de schimbarea setarii. Alegerea se salveaza si
	se vede la pornirea urmatoare a interfetei. Refuzul tinut minte se sterge (si pentru aceeasi tema: omul vrea sa o incerce
	din nou)."""
	if root is None:
		root = radacina()
	cale = caleSkin(root, nume)
	if cale is None:
		return False, _t("Tema nu există.", traducere), ""
	v = verificaSkin(cale)
	if not v["bun"]:
		return False, _t("Tema %s nu se poate folosi: %s.", traducere) % (nume, textMotiv(v["motiv"], v["detaliu"],
			traducere)), ""
	avertisment = avertismentRezolutie(nume, v, traducere)
	T = _temaExterna() if nume != DOSAR_IMAGINE else None
	if T is not None:
		verificata = T.verifica(cale, root)
		if not verificata["bun"]:
			return False, _t("Tema %s nu se poate folosi: %s.", traducere) % (nume, textMotiv(verificata["motiv"],
				verificata["detaliu"], traducere)), ""
		if not T.pregatesteActivarea(fisier(nume), cale):
			return False, _t("Tema %s nu se poate folosi: %s.", traducere) % (nume, textMotiv(MOTIV_SCRIERE, "", traducere)), ""
		lipsa = T.textAvertisment(verificata, traducere)
		avertisment = (avertisment + " " + lipsa).strip() if lipsa else avertisment
	c = _config(config).skin.primary_skin
	c.value = fisier(nume)
	c.save()
	# o alegere noua: motivul vechi nu mai e de spus (iar aceeasi tema aleasa din nou primeste o noua incercare)
	stergeRefuz(refuz)
	return True, _t("Tema aleasă se vede după repornirea interfeței.", traducere), avertisment


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
	"""True cand /tmp/hds-enigma2.caderi are o oprire neasteptata scrisa la sau dupa `pornit` (secunde de uptime). O oprire
	ceruta (al treilea cuvant: oprire, tools/enigma2.sh.in) nu e vina skinului."""
	try:
		with open(caderi or CADERI, encoding="utf-8", errors="replace") as f:
			for rand in f:
				p = rand.split()
				if p and p[0].isdigit() and int(p[0]) >= pornit and p[2:3] != ["oprire"]:
					return True
	except (IOError, OSError):
		pass
	return False


def citesteRefuz(cale=None):
	return _citesteJson(cale or REFUZ)


def refuzDeSpus(refuz=None, activare=None):
	"""Selectorul si pagina web: refuzul din RAM sau, dupa o repornire a receptorului, cel din jurnalul activarii."""
	r = citesteRefuz(refuz)
	if r:
		return r
	a = _citesteJson(activare or ACTIVARE)
	if a and a.get("stare") == "refuzat":
		return {"skin": a.get("skin", ""), "motiv": a.get("motiv", ""), "detaliu": a.get("detaliu", ""), "aratat": True}
	return None


def stergeRefuz(cale=None, activare=None):
	_sterge(cale or REFUZ)
	# refuzul tinut minte pe disc nu mai e de spus dupa o alegere noua (la o tema externa, jurnalul e deja scris din nou)
	a = _citesteJson(activare or ACTIVARE)
	if a and a.get("stare") == "refuzat":
		_sterge(activare or ACTIVARE)


def _amprenta(cale):
	try:
		T = _temaExterna()
		return T.amprentaFisier(cale) if T is not None else ""
	except Exception:
		return ""


def refuza(valoare, motiv, detaliu="", cale=None):
	"""Tine minte in RAM de ce skinul ales nu a pornit (pentru mesajul de pe televizor si pentru pagina)."""
	r = {"skin": valoare, "motiv": motiv, "detaliu": detaliu, "aratat": False}
	if motiv == MOTIV_REZOLUTIE_PLACA:
		try:
			r["amprenta"] = _amprenta(os.path.join(radacina(), valoare))
		except Exception:
			r["amprenta"] = ""
	_scrieJson(cale or REFUZ, r)
	T = _temaExterna()
	if T is not None:
		T.marcheazaRefuz(valoare, motiv, detaliu)
	_jurnal("skinul %s nu porneste (%s %s), ramane %s" % (valoare, motiv, detaliu, SKIN_IMAGINE))
	return r


def _cauzaCaderii(pornit=None):
	"""MI6 0.7.5: cauza ultimei caderi (Components/HdsTemaExterna.cauzaCaderii), detaliul refuzului MOTIV_CADERE pentru
	raportul temei; "" cand nu se stie. Nu arunca."""
	try:
		T = _temaExterna()
		return T.cauzaCaderii(pornit) if T is not None else ""
	except Exception:
		return ""


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
		if not (pastreazaAlegerea(r) and r.get("amprenta") and _amprenta(os.path.join(root, valoare)) != r["amprenta"]):
			return None, r
		# refuzul rezolutiei, dar tema si-a schimbat fisierul (FHD in setarile ei): o noua incercare
		_sterge(refuz or REFUZ)
	semn = _citesteJson(proba)
	if semn and semn.get("skin") == valoare and _caderiDupa(int(semn.get("pornit") or 0), caderi):
		_sterge(proba)
		return None, refuza(valoare, MOTIV_CADERE, _cauzaCaderii(int(semn.get("pornit") or 0)), refuz)
	cale = os.path.join(root, valoare)
	v = verificaSkin(cale)
	if not v["bun"]:
		_sterge(proba)
		return None, refuza(valoare, v["motiv"], v["detaliu"], refuz)
	acum = _uptime(uptime) if uptime is None or isinstance(uptime, str) else int(uptime)
	T = _temaExterna()
	if T is not None:
		if T.caderiRecente(acum, caderi or CADERI) >= PRAG_CADERI:
			_sterge(proba)
			return None, refuza(valoare, MOTIV_CADERE, _cauzaCaderii(), refuz)
		motiv = T.laPornire(valoare, cale)
		if motiv:
			_sterge(proba)
			return None, refuza(valoare, motiv[0], motiv[1], refuz)
	if not _scrieJson(proba, {"skin": valoare, "pornit": acum}) and T is not None:
		# fara semnul probei, o oprire la pornire n-ar mai retrage tema: nu se activeaza
		return None, refuza(valoare, MOTIV_SCRIERE, "", refuz)
	return valoare, None


def incarcareCazuta(valoare, eroare, proba=None, refuz=None):
	"""skin.py: incarcarea temei alese a cazut: XML stricat sau o tema stricata (EroareTema, cu motivul ei)."""
	_sterge(proba or PROBA)
	motiv = getattr(eroare, "motiv", None)
	return refuza(valoare, motiv or MOTIV_XML, getattr(eroare, "detaliu", "") if motiv else str(eroare)[:200], refuz)


def pornireReusita(proba=None):
	"""Interfata a mers PROBA_S secunde cu skinul ales: semnul probei se sterge."""
	_sterge(proba or PROBA)
	T = _temaExterna() if skinPornit() != SKIN_IMAGINE else None
	if T is not None:
		T.probaReusita()


def iesireCeruta():
	"""mytest.py, cand interfata se opreste la cerere: pornirea asta nu se numara impotriva temei externe."""
	if skinPornit() != SKIN_IMAGINE:
		T = _temaExterna()
		if T is not None:
			T.iesireCeruta()


def eroareDinTema(stiva, valoare=None, root=None, info=None):
	"""mytest.py, la fiecare eroare de ecran: True cand stiva trece prin fisierele temei externe pornite (dosarul ei sau
	fisierele pachetului ei: convertoare, randatoare, pluginul ei). Cu tema HD Satelit, False."""
	valoare = valoare or skinPornit()
	if valoare == SKIN_IMAGINE or esteImaginii(valoare):
		return False
	T = _temaExterna()
	if T is None:
		return True
	import posixpath
	dosar = posixpath.dirname(posixpath.join(root or radacina(), valoare))
	return T.stivaDinTema(stiva, dosar, info)


def eroriEcrane(detaliu="", dinTema=True):
	"""mytest.py, la a treia eroare de ecran in 30 de secunde, inainte de repornirea interfetei: cu o tema externa, tema se
	retrage, deci repornirea e una singura si interfata nu intra in bucla. Numai cand macar una dintre erori a trecut prin
	fisierele temei (dinTema, eroareDinTema): un plugin care cade singur (OAWeatherOverview sub Obsidian-FHD, 12.11.2026) nu
	ia omului tema. True daca s-a retras."""
	valoare = skinPornit()
	if valoare == SKIN_IMAGINE:
		return False
	if not dinTema:
		_jurnal("erorile ecranului %s nu trec prin fisierele temei %s: tema ramane" % (detaliu, valoare))
		return False
	refuza(valoare, MOTIV_ECRANE, str(detaliu)[:200])
	return True


def textRefuz(r, traducere=None):
	if not r:
		return ""
	nume = numeDinValoare(r.get("skin")) or r.get("skin") or ""
	return _t("Tema aleasă (%s) nu a pornit: %s. Interfața a revenit la tema HD Satelit.", traducere) % (nume,
		textMotiv(r.get("motiv"), r.get("detaliu", ""), traducere))


def textStareTema(traducere=None):
	"""Selectorul si pagina web: ce nu merge din tema externa de pe ecran, sau "" (si cu tema HD Satelit)."""
	valoare = skinPornit()
	if valoare == SKIN_IMAGINE:
		return ""
	try:
		import skin
		T = _temaExterna()
		return T.textStare(numeDinValoare(valoare) or valoare, skin.raportTema, traducere) if T is not None else ""
	except Exception as eroare:
		_jurnal("starea temei: %s" % eroare)
		return ""


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


# ------------------------------------------------------------------ skin_user.xml scris pentru alta tema
# SKU (15.11.2026, asistenta 452351, AX HD51, 0.7.5): unealta de setari a unei teme straine (MERCUS-FHD) scrie
# /etc/enigma2/skin_user.xml cu ecranele si fonturile ei (InfoBar, SecondInfoBar; Regular, Bold... din dosarul temei).
# skin.py citeste fisierul la orice tema, inaintea ei, deci dupa intoarcerea pe HD Satelit barele de informatii ramaneau
# cele ale temei straine. Acum skin.py, dupa ce stie tema care porneste de fapt (skinPornit), intreaba
# skinUserPentruAltaTema: un skin_user.xml care trimite numai in dosarele altei teme (fonturi, poze, cai) nu se aplica peste
# tema pornita. Fisierul ramane pe loc, neatins: la intoarcerea pe tema lui se aplica iar (setarile facute cu unealta temei
# nu se pierd, iar unealta il gaseste unde l-a scris). Un fisier fara nicio cale de tema (adaugirile scrise de mana) se
# aplica la orice tema, ca pana acum. Fisierele pe tema din OE-Alliance (skin_user_<tema>.xml) nu sunt atinse.
RADACINA_TEME = "/usr/share/enigma2/"
_CALE_TEMA = re.compile(r"/usr/share/enigma2/+([^/\s\"'<>,;|]+)/")
_BUCATI = re.compile(r"[\s,;|]+")
_NUME_DOSAR = re.compile(r"^[^\\/:*?\"<>|\s]+$")


def _dosarComun(nume):
	"""dosarele de sub radacina temelor care nu sunt ale unei teme: skin_default (al imaginii) si piconurile (puse de om,
	uneori lipsa sau pe stick)"""
	n = nume.lower()
	return n.startswith("skin_default") or n.startswith("picon") or n.startswith(".")


def dosareTeme(radacina_xml, root=None):
	"""Dosarele de teme spre care trimite un skin deja citit (elementul <skin>), {dosar: de cate ori}: cai absolute sub
	radacina temelor (/usr/share/enigma2/<dosar>/..., de pilda fonturile) si cai relative care incep cu dosarul unei teme
	(<dosar>/okna/bara.png). Se numara dosarul imaginii (HDSatelit), dosarele cu skin.xml si, numai la caile absolute, cele
	care nu mai exista (tema dezinstalata, ale carei fonturi si poze lipsesc). skin_default si piconurile nu se numara."""
	if root is None:
		root = radacina()
	gasite = {}
	stiute = {}

	def eTema(d, absoluta):
		cheie = (d, absoluta)
		if cheie not in stiute:
			if d in (".", "..") or not _NUME_DOSAR.match(d) or _dosarComun(d):
				stiute[cheie] = False
			elif d == DOSAR_IMAGINE or os.path.isfile(os.path.join(root, d, "skin.xml")):
				stiute[cheie] = True
			else:
				stiute[cheie] = absoluta and not os.path.exists(os.path.join(root, d))
		return stiute[cheie]

	def numara(d, absoluta):
		if eTema(d, absoluta):
			gasite[d] = gasite.get(d, 0) + 1

	for el in radacina_xml.iter():
		valori = list(el.attrib.values())
		if el.text:
			valori.append(el.text)
		for v in valori:
			if not v or "/" not in v:
				continue
			for d in _CALE_TEMA.findall(v):
				numara(d, True)
			for bucata in _BUCATI.split(v):
				if "/" in bucata and not bucata.startswith("/"):
					numara(bucata.split("/", 1)[0], False)
	return gasite


def skinUserPentruAltaTema(radacina_user, tema, root=None, radacina_tema=None, proprietar=None):
	"""Dosarul temei pentru care e scris skin_user.xml (deja citit), cand e alta decat `tema` (valoarea temei care porneste,
	"MERCUS-FHD/skin.xml"); atunci fisierul nu se aplica. None cand se aplica: fara nicio cale de tema (scris de mana) sau
	cand trimite si in dosarele temei pornite. `radacina_tema` (skin.xml-ul temei pornite, citit) adauga dosarele spre care
	trimite chiar tema: o varianta (X-Black) care isi ia pozele din dosarul temei de baza (X) primeste si fisierul scris in X.
	`proprietar` (TEM, amintireSkinUser): tema straina in a carei sesiune s-a schimbat fisierul ("" = sesiunea temei imaginii,
	None = nu se stie: in ambele cazuri hotaraste continutul, ca pana acum). Conteaza NUMAI cand continutul nu trimite in nicio
	tema instalata: cand trimite, hotaraste continutul (cazul MERCUS-FHD de la asistenta 452351)."""
	if root is None:
		root = radacina()
	gasite = dosareTeme(radacina_user, root)
	dosar = numeDinValoare(tema) or DOSAR_IMAGINE
	instalate = [d for d in gasite if d == DOSAR_IMAGINE or os.path.isfile(os.path.join(root, d, "skin.xml"))]
	if not instalate and proprietar:
		# fara cai spre o tema instalata (unealta care scrie fonturi din /usr/share/fonts): hotaraste tema straina in a carei
		# sesiune s-a schimbat fisierul. Schimbat sub tema imaginii ("") nu hotaraste nimic: asa arata si fisierul altei teme
		# pus la loc dintr-o copie (sau din FTP) inainte ca tema lui sa fie instalata, pe care continutul il opreste corect.
		if proprietar in (dosar, DOSAR_IMAGINE):
			return None
		if radacina_tema is not None and proprietar in dosareTeme(radacina_tema, root):
			return None
		return proprietar
	if not gasite:
		return None
	if dosar in gasite:
		return None
	if radacina_tema is not None and set(dosareTeme(radacina_tema, root)) & set(gasite):
		return None
	return max(sorted(gasite), key=lambda d: gasite[d])


# ------------------------------------------------------------------ amintirea lui skin_user.xml si fisierul pe tema
# TEM (16.11.2026; TODO 15.11 22:25 SKU, completari la TODO 15.11 13:05 FR11, asistenta 452351):
# 1. Semnul de mai sus (caile spre dosarul temei) nu vede unealta unei teme care scrie skin_user.xml fara asemenea cai. Semnul
#    in plus: imaginea tine minte, langa skin_user.xml (hds-skin-user.json), amprenta fisierului si tema care a pornit ultima
#    data. Cand amprenta s-a schimbat in sesiunea unei teme straine, fisierul e al ei. Schimbat sub tema imaginii nu hotaraste
#    nimic (poate fi un fisier al altei teme pus la loc dintr-o copie), deci un fisier scris de mana cu o cale spre un dosar
#    lipsa ramane luat drept al unei teme dezinstalate, ca pana acum. Fisierul existent dinainte (fara amintire) ramane la
#    semnul din continut. Se scrie numai cand se schimba fisierul sau tema pornita; orice greseala = nu se stie.
# 2. Fisierul pe tema, ca in imaginile OE-Alliance (skin.py: USER_SKIN_TEMPLATE "skin_user_%s.xml" cu dosarul temei;
#    Tools/Directories.py, SCOPE_GUISKIN): cand exista pentru tema care porneste, se aplica el in locul lui skin_user.xml.
AMINTIRE_SKIN_USER = "hds-skin-user.json"


def caiSkinUserTema(tema):
	"""Unde se cauta fisierul pe tema pornita, in ordinea din imaginile OE-Alliance: [(nume, "config"|"skin")] =
	/etc/enigma2/<dosar>/skin_user_<dosar>.xml, /etc/enigma2/skin_user_<dosar>.xml, /usr/share/enigma2/<dosar>/
	skin_user_<dosar>.xml (nume relativ la /etc/enigma2, respectiv la radacina temelor). [] cand valoarea nu are dosar."""
	dosar = numeDinValoare(tema)
	if not dosar or not _NUME_DOSAR.match(dosar) or dosar in (".", ".."):
		return []
	nume = "skin_user_%s.xml" % dosar
	return [(dosar + "/" + nume, "config"), (nume, "config"), (dosar + "/" + nume, "skin")]


def _semnSkinUser(cale):
	"""md5-ul fisierului, "" cand lipseste; None cand nu se poate citi"""
	import hashlib
	try:
		with open(cale, "rb") as f:
			return hashlib.md5(f.read()).hexdigest()
	except (IOError, OSError) as eroare:
		if os.path.exists(cale):
			_jurnal("%s: %s" % (cale, eroare))
			return None
		return ""


def amintireSkinUser(cale_user, tema, cale_amintire=None):
	"""skin.py, la fiecare pornire (nu in modul sigur): a cui e skin_user.xml dupa sesiunea in care s-a schimbat. Intoarce
	dosarul temei straine, "" (schimbat sub tema imaginii; skinUserPentruAltaTema il trateaza ca None) sau None (nu se stie: fisier dinainte de amintire, lipsa,
	greseala). Tine la zi amintirea: amprenta de acum, proprietarul ei si tema care porneste acum (`tema`, skinPornit)."""
	try:
		cale_amintire = cale_amintire or os.path.join(os.path.dirname(cale_user), AMINTIRE_SKIN_USER)
		semn = _semnSkinUser(cale_user)
		if semn is None:
			return None
		dosar = numeDinValoare(tema) or DOSAR_IMAGINE
		vechi = _citesteJson(cale_amintire)
		if vechi is None or not isinstance(vechi.get("semn"), str):
			proprietar = None
		elif vechi["semn"] == semn:
			proprietar = vechi.get("proprietar")
			if not (proprietar is None or isinstance(proprietar, str)):
				proprietar = None
		else:
			sesiune = vechi.get("sesiune")
			proprietar = "" if not isinstance(sesiune, str) or sesiune in ("", DOSAR_IMAGINE) else sesiune
		if not semn:
			proprietar = None
		nou = {"semn": semn, "proprietar": proprietar, "sesiune": dosar}
		if nou != vechi:
			_scrieJson(cale_amintire, nou)
		return proprietar
	except Exception as eroare:
		_jurnal("amintirea lui skin_user.xml: %s" % eroare)
		return None
