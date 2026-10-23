# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsModSigur.py: modul sigur al interfetei, dupa opriri neasteptate repetate.
#
# tools/enigma2.sh.in numara opririle neasteptate ale lui enigma2 (in /tmp/hds-enigma2.caderi, secunde de la pornirea
# receptorului) si, de la a 5-a in 10 minute, pune semnul /tmp/hds-mod-sigur. Cat timp semnul exista, enigma2 porneste
# cu HDS_MOD_SIGUR=1 in mediu, iar acest modul spune ce se schimba in acel proces:
#   - incarcatorul de pluginuri (Components/PluginComponent.py) porneste numai pluginurile venite cu imaginea
#     (pluginPermis); celelalte raman instalate, doar nu se incarca;
#   - skin.py nu citeste /etc/enigma2/skin_user.xml, iar fonturile descarcate de om nu se inregistreaza; skinul e
#     HDSatelit/skin.xml asa cum e pe disc, deci cu paleta si afisajul alese in setarile skinului (HdsSkinSetari, al
#     imaginii, le scrie chiar in skin.xml);
#   - primul ecran e mesajul modului sigur (Screens/HdsModSigur.py), cu alegerile „Pornește normal”, „Pune înapoi
#     setările de dinainte” si „Vezi ce s-a întâmplat”; aceleasi in interfata web (/mod-sigur).
# Starea se ia din mediul procesului, nu din semn: procesul ramane in modul sigur pana la repornirea interfetei.
#
# Pluginurile imaginii: dosarele Plugins/<fel>/<nume> ale pachetelor care erau in imagine la construire, dupa listele
# opkg (/var/lib/opkg/info/<pachet>.list). Pachetele imaginii vin din lista licentelor facuta la construire
# (/usr/share/hdsatelit/licente/lista.json, cheia „instalate”); fara ea (imagini de dinainte de 0.1.6) se iau pachetele
# enigma2-hdsatelit si hdsatelit-skin, singurele cu pluginuri in imagine. Un plugin copiat de mana sau dintr-un pachet
# instalat dupa scriere nu e in aceste liste. Fara nicio lista opkg (emulatorul) nu se poate spune care sunt ale
# imaginii: atunci nu se opreste nimic si ecranul o spune.
#
# Setarile de dinainte: la fiecare pornire enigma2.sh pastreaza in RAM o copie a lui settings, luata dupa carligul
# enigma2_pre_start.sh, deci cu setarile cu care porneste interfata (/tmp/hds-setari-la-pornire, 0600). Dupa 10 minute
# de mers ale aceluiasi proces (deci fara oprire neasteptata), numai in afara modului sigur, copia devine
# /etc/enigma2/settings.bune: o scriere pe memoria interna la o pornire a interfetei cu alte setari decat copia de pe
# disc, nimic cand sunt la fel. „Setările de dinainte” sunt deci ale ultimei porniri a interfetei care a mers 10 minute.
#
# Alegerile nu schimba nimic pe loc: scriu cererea in RAM (/tmp/hds-mod-sigur.cerere: „normal” sau „setari”) si cer
# repornirea interfetei. enigma2.sh face cererea la pornirea urmatoare si numai atunci sterge semnul si numaratoarea si
# scrie randul de iesire in jurnalul opririlor (/home/root/logs/hds-caderi.log). Settings nu se scrie de aici: la
# iesirea curata configfile.save() ar scrie peste el setarile din memorie. Daca repornirea e refuzata (TryQuitMainloop
# intreaba cand o inregistrare e in curs sau aproape), cererea se sterge si modul sigur continua.
# Treapta a doua (enigma2.sh): cand si modul sigur se opreste neasteptat de 3 ori, setarile de dinainte se pun inapoi
# singure, o singura data, iar modul sigur continua; semnul primeste randurile „oprire=” si „automat=”.
#
# Ce s-a intamplat: numaratoarea din RAM, jurnalul opririlor si ultimul raport de eroare din /home/root/logs (XML-ul
# scris de main/bsod.cpp, cu jurnalul enigma2 in CDATA la inceput, sau textul scris de mytest.py cand un ecran nu se
# deschide). Din el se scoate eroarea Python (felul, mesajul, locul), extensia in care a aparut sau, la o cadere in
# codul nativ, ultima extensie care a scris in jurnal. Randurile de jurnal se arata numai in textul brut, fara
# randurile cu jetonul web sau cu parole (un raport poate avea setarile intregi).
#
# FIRUL: stare() citeste fisiere mici (jurnalul opririlor de cel mult 64 KiB, inceputul unui raport XML sau sfarsitul
# unui raport text) la deschiderea ecranului sau a paginii; textul brut se citeste pe un fir (peFir), iar rezultatul se
# pune pe ecran din firul enigma2, cu un eTimer. Listele opkg (cateva sute de fisiere mici) se citesc o singura data pe
# proces, numai in modul sigur. Copia setarilor se scrie pe un fir separat. Modulul nu importa nimic din enigma2 la
# incarcare: probele de pe PC dau caile lor prin constantele de mai jos.

import io
import json
import os
import re
import threading
import time

VAR_MEDIU = "HDS_MOD_SIGUR"
RAM = "/tmp"
SEMN = RAM + "/hds-mod-sigur"
CERERE = RAM + "/hds-mod-sigur.cerere"
CADERI = RAM + "/hds-enigma2.caderi"
SETARI_PORNIRE = RAM + "/hds-setari-la-pornire"
# rezultatul ultimei copii a setarilor (un cuvant, in RAM): numai pentru cine se uita pe receptor
COPIE_FACUTA = RAM + "/hds-setari-bune.facut"
SETARI = "/etc/enigma2/settings"
SETARI_BUNE = SETARI + ".bune"
SETARI_DINAINTE = SETARI + ".inainte-de-mod-sigur"
DOSAR_JURNALE = "/home/root/logs"
JURNAL_CADERI = DOSAR_JURNALE + "/hds-caderi.log"
LISTA_LICENTE = "/usr/share/hdsatelit/licente/lista.json"
OPKG_INFO = "/var/lib/opkg/info"
PREFIX_PLUGINURI = "/usr/lib/enigma2/python/Plugins/"
PREFIX_PYTHON = "/usr/lib/enigma2/python/"
# pachetele cu pluginuri din imagine, cand lista licentelor lipseste
PACHETE_REZERVA = ("enigma2-hdsatelit", "hdsatelit-skin")
CHEIE_JETON = "config.plugins.hdswebcontrol.token"

# aceleasi valori ca in enigma2.sh (HDS_MOD_SIGUR_PRAG, HDS_MOD_SIGUR_PRAG2, fereastra de 600 s a numaratorii)
PRAG = 5
PRAG2 = 3
FEREASTRA_S = 600
COPIE_DUPA_S = 600
MAX_CITIRE = 256 * 1024
# un raport XML al lui bsod.cpp incepe cu antetul si jurnalul (inelul de 16 KiB din bsod.cpp); anexele de dupa
# (setarile, pachetele, sumele fisierelor Python) nu se citesc
MAX_CITIRE_XML = 64 * 1024
MAX_SETARI = 1024 * 1024
MAX_LISTA = 4 * 1024 * 1024
MAX_PACHETE = 3000
# cate randuri se arata: opririle din jurnal, randurile de jurnal cercetate inaintea erorii, textul brut
MAX_EVENIMENTE = 8
MAX_RANDURI_JURNAL = 8
MAX_BRUT_RANDURI = 400
# dintr-un raport de eroare, textul brut are ultimele randuri ale jurnalului (inaintea lor e pornirea interfetei)
MAX_BRUT_RAPORT = 60
MAX_RAPOARTE_BRUTE = 2
# fraza de sub mesaj: cate litere din numele extensiilor oprite (restul: „și încă N”); lista intreaga e in „Ce s-a
# întâmplat”. Masurat cu fontul skinului: incape in 4 randuri in toate limbile, si cu fraza treptei a doua.
MAX_NUME_EXPLICATIE = 64
# cat asteapta firul enigma2 intre doua priviri la firul care citeste textul brut
PAS_FIR_MS = 50

NUME_PACHET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+._-]{0,127}$")
NUME_PLUGIN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.+-]{0,127}$")
RAPORT = re.compile(r"^enigma2_crash_(\d+)\.log$")
# randurile care nu se arata niciodata: un raport poate avea settings intreg (sendAnonCrashlog=false), deci si
# jetonul web, parolele, codurile PIN (ParentalControl setuppin/servicepin), cheia Wi-Fi (psk), alte chei si secrete.
# Regula e aceeasi pentru /mod-sigur si pentru paginile jurnalelor (HdsJurnale.faraSecrete). Pe langa cuvintele de
# oriunde din rand: o cheie sau un PIN scrise cu spatii in jurul lui = sau : ("api_key = x", "pin = 1234", "cheie_api:
# x"), parola in adresa ("&pwd=x", "?auth=x", "http://ion:parola@..."), antetele Authorization, Bearer si Cookie.
# Cuvintele scurte (key, pin, pass, pwd) se iau numai cu = dupa ele, ca "KEY: 352" sau "keyboard = us" sa ramana.
SECRET = re.compile(
	r"(?i)(token|password|passwd|passphrase|parola|psk|secret"
	r"|pin(?:[.][0-9]+)*\s*="
	r"|key(?:[.][0-9]+)*\s*="
	r"|(?:api|access|private|auth)[ _.-]?key\s*[=:]"
	r"|\bchei[ae](?:[ _.-]?api)?\s*[=:]"
	r"|(?<![a-z0-9])(?:pass|pwd)\s*="
	r"|[?&;](?:pass|pwd|pw|auth|sid|sessionid|sig|signature)="
	r"|\bauthorization\s*[=:]"
	r"|\bbearer\s+[a-z0-9._~+/=-]{6,}"
	r"|\b(?:set-)?cookie\s*:"
	r"|[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@)")
RAND_JURNAL = re.compile(r"^(\d{4})-(\d\d)-(\d\d) (\d\d):(\d\d)(?::(\d\d))? (.*)$")
OPRIRE = re.compile(r"enigma2 s-a oprit neasteptat \(cod (\d+)")
CADRU = re.compile(r'File "([^"]+)", line (\d+), in (.+?)\s*$')
EXCEPTIE = re.compile(r"^\s*(?:[<\[][^>\]]*[>\]]\s*)?([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Exit|Interrupt|"
	r"Iteration|Warning|Fault))(?::\s?(.*))?$")
# eticheta unui rand de jurnal („[NumeExtensie] ...”), dupa ora pusa de ENIGMA_DEBUG_TIME („<   123.456> ”)
ETICHETA = re.compile(r"^\s*(?:<[^>]{0,40}>\s*)?\[([A-Za-z0-9_][A-Za-z0-9_.+-]{0,63})\]")
# antetul raportului text scris de mytest.py (handleScreenCrash), inaintea Traceback-ului
ANTET_RAPORT_TEXT = ("HD Satelit:", "Ecran: ", "Eroare: ")

NORMAL, BUN, ATENTIE, RAU, STINS = "normal", "bun", "atentie", "rau", "stins"

_lacat = threading.Lock()
_imagine = {"calculat": False, "set": None, "sursa": None}
_oprite = []
_ceas = {"t": None, "legatura": None}
# ceasurile si legaturile firelor de citire in curs (tinute in viata pana la sfarsit)
_fire = []


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textele din tabele se traduc la folosire."""
	return text


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi pe PC."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _formaRo(unu, multe, n):
	"""Fara Components/HdsPlural (modulul incarcat singur): pluralul din catalogul instalat de enigma2, daca e; altfel
	forma romaneasca (msgid-urile sunt in romana): unu pentru n == 1, altfel multe, fara "de" ("20 canale")."""
	try:
		import builtins
		f = getattr(getattr(builtins.__dict__.get("_"), "__self__", None), "ngettext", None)
		if f is not None:
			return f(unu, multe, n)
	except Exception:
		pass
	return unu if n == 1 else multe


def ngettext(unu, multe, n):
	"""Pluralul tradus (Components/HdsPlural.ngettext: formele din Plural-Forms ale limbii, intors ca Forma, al carei %
	merge si cand forma pentru 1 n-are numarul, ca "un canal" din ro.po). Fara pachetul Components (probele de pe PC),
	forma romaneasca de mai sus. Numele e cel stiut de xgettext."""
	try:
		from Components.HdsPlural import ngettext as plural
	except ImportError:
		return _formaRo(unu, multe, n)
	return plural(unu, multe, n)


def _cuNumar(text, n):
	"""Textul cu numarul pus, daca forma aleasa il are (singularul poate fi „o dată”, fara numar)."""
	return text % n if "%d" in text else text


def _log(text):
	print("[HdsModSigur] %s" % text)


def _ora(secunde, forma="%d.%m.%Y, %H:%M"):
	"""„31.12.2026, 14:30” (ora receptorului) din secunde de la 1970, sau "" daca nu se poate."""
	try:
		return time.strftime(forma, time.localtime(secunde))
	except (ValueError, OSError, OverflowError, TypeError):
		return ""


# ------------------------------------------------------------------ starea procesului

def activ(mediu=None):
	"""True cand acest proces enigma2 a pornit in modul sigur (HDS_MOD_SIGUR=1 pus de enigma2.sh)."""
	return (os.environ if mediu is None else mediu).get(VAR_MEDIU) == "1"


def semnPus():
	"""Semnul din RAM: pornirea urmatoare a interfetei e tot in modul sigur."""
	return os.path.exists(SEMN)


def citesteSemn(cale=None):
	"""Semnul scris de enigma2.sh: {"ora": secunde de la 1970 sau None, "opriri": cate opriri au fost si in modul sigur
	(randurile „oprire=”), "automat": None sau {"rez": „da” / „lipsa” / pasul care n-a mers, "cand": ora in cuvinte}}."""
	text = _citesteText(cale or SEMN, 4096, coada=False) or ""
	rez = {"ora": None, "opriri": 0, "automat": None}
	for rand in text.split("\n"):
		if rand.startswith("ora="):
			v = rand[4:].strip()
			if v.isdigit():
				rez["ora"] = int(v)
		elif rand.startswith("oprire="):
			rez["opriri"] += 1
		elif rand.startswith("automat=") and rez["automat"] is None:
			parti = rand[8:].split()
			cand = _ora(int(parti[1])) if len(parti) > 1 and parti[1].isdigit() else ""
			rez["automat"] = {"rez": parti[0] if parti else "", "cand": cand}
	return rez


def oraSemn(cale=None):
	"""Secundele (ceasul receptorului, fara fus orar) cand enigma2.sh a pus semnul, din randul „ora=”, sau None."""
	return citesteSemn(cale)["ora"]


def cerereLasata(cale=None):
	"""Cuvantul cererii care asteapta repornirea („normal”, „setari”, „automat”), sau "" daca nu e niciuna."""
	text = _citesteText(cale or CERERE, 64, coada=False) or ""
	return text.strip().split("\n")[0][:12] if text.strip() else ""


# ------------------------------------------------------------------ pluginurile imaginii

def _pacheteImagine(lista=None):
	"""(pachete, sursa): pachetele din imagine dupa lista licentelor („lista”) sau cele de rezerva („rezerva”)."""
	lista = lista or LISTA_LICENTE
	try:
		if os.path.getsize(lista) <= MAX_LISTA:
			with io.open(lista, "r", encoding="utf-8") as f:
				date = json.load(f)
			instalate = date.get("instalate") if isinstance(date, dict) else None
			if isinstance(instalate, list):
				pachete = [p for p in instalate[:MAX_PACHETE] if isinstance(p, str) and NUME_PACHET.match(p)]
				if pachete:
					return pachete, "lista"
	except (IOError, OSError) as e:
		if getattr(e, "errno", None) != 2:        # lipsa (imagini de dinainte de 0.1.6) nu e o eroare
			_log("lista pachetelor imaginii nu se poate citi: %s" % e)
	except ValueError as e:
		_log("lista pachetelor imaginii nu se poate citi: %s" % e)
	return list(PACHETE_REZERVA), "rezerva"


def pluginuriDinListe(pachete, info=None, prefix=None):
	"""(set de „<fel>/<nume>”, cate liste s-au citit) din listele opkg ale pachetelor date."""
	info = info or OPKG_INFO
	prefix = prefix or PREFIX_PLUGINURI
	gasite = set()
	citite = 0
	for pachet in pachete:
		try:
			with io.open(os.path.join(info, pachet + ".list"), "r", encoding="utf-8", errors="surrogateescape") as f:
				text = f.read(MAX_LISTA)
		except (IOError, OSError):
			continue
		citite += 1
		if prefix not in text:
			continue
		for rand in text.split("\n"):
			cale = rand.split("\t", 1)[0].strip()
			if not cale.startswith(prefix):
				continue
			parti = cale[len(prefix):].split("/")
			# numai fisierele dintr-un dosar de plugin (Plugins/<fel>/<nume>/...), nu __init__.py al felului
			if len(parti) >= 3 and parti[0] and parti[1]:
				gasite.add(parti[0] + "/" + parti[1])
	return gasite, citite


def pluginuriImagine(lista=None, info=None, din_nou=False):
	"""(set de „<fel>/<nume>” sau None, sursa): pluginurile venite cu imaginea. None = nu se poate afla (nicio lista
	opkg a pachetelor imaginii). Se calculeaza o data pe proces."""
	with _lacat:
		if _imagine["calculat"] and not din_nou and lista is None and info is None:
			return _imagine["set"], _imagine["sursa"]
	pachete, sursa = _pacheteImagine(lista)
	gasite, citite = pluginuriDinListe(pachete, info)
	if not gasite and sursa == "lista":
		gasite, citite = pluginuriDinListe(PACHETE_REZERVA, info)
		sursa = "rezerva"
	# nicio lista, sau liste fara niciun plugin (de exemplu enigma2-hdsatelit.list lipsa sau taiata): nu se poate
	# spune care sunt ale imaginii, deci nu se opreste nimic (altfel s-ar opri si interfata web a imaginii)
	rez = (gasite, sursa) if gasite else (None, None)
	if not gasite:
		_log("pluginurile imaginii nu se pot afla (%d liste opkg citite, niciun plugin in ele): nu se opreste nimic"
			% citite)
	if lista is None and info is None:
		with _lacat:
			_imagine.update(calculat=True, set=rez[0], sursa=rez[1])
	return rez


def pluginPermis(fel, nume):
	"""Chemata de incarcatorul de pluginuri pentru fiecare dosar Plugins/<fel>/<nume> cu plugin.py. In afara modului
	sigur, mereu True. In modul sigur, True numai pentru pluginurile imaginii (sau pentru toate, daca nu se poate
	afla care sunt); celelalte se tin minte pentru ecran si pagina web."""
	if not activ():
		return True
	try:
		imagine, _sursa = pluginuriImagine()
	except Exception as e:
		_log("pluginurile imaginii: %s" % e)
		return True
	if imagine is None:
		return True
	cheie = "%s/%s" % (fel, nume)
	if cheie in imagine:
		return True
	with _lacat:
		if cheie not in _oprite:
			_oprite.append(cheie)
			_log("extensia %s nu porneste in modul sigur (nu a venit cu imaginea; ramane instalata)" % cheie)
	return False


def oprite():
	"""Pluginurile oprite in acest proces: [„<fel>/<nume>”], in ordinea gasirii."""
	with _lacat:
		return list(_oprite)


def numeExtensie(cheie):
	"""„Extensions/NumeX” -> „NumeX”."""
	return (cheie or "").split("/", 1)[-1]


def pluginuriPeDisc(prefix=None):
	"""{nume: „<fel>/<nume>”} pentru dosarele Plugins/<fel>/<nume> de pe disc (cateva zeci, numai numele)."""
	prefix = prefix or PREFIX_PLUGINURI
	rez = {}
	try:
		feluri = os.listdir(prefix)
	except (IOError, OSError):
		return rez
	for fel in feluri:
		try:
			nume = os.listdir(os.path.join(prefix, fel))
		except (IOError, OSError):
			continue
		for n in nume:
			if NUME_PLUGIN.match(n) and n != "__pycache__" and not n.endswith((".py", ".pyc", ".pyo")):
				rez.setdefault(n, fel + "/" + n)
	return rez


# ------------------------------------------------------------------ opririle

def _citesteText(cale, maxim=MAX_CITIRE, coada=True):
	"""Textul fisierului (cel mult `maxim` octeti; cu `coada`, sfarsitul lui), sau None."""
	try:
		with open(cale, "rb") as f:
			if coada:
				try:
					f.seek(0, 2)
					marime = f.tell()
					if marime > maxim:
						f.seek(marime - maxim)
					else:
						f.seek(0)
				except (IOError, OSError):
					pass
			date = f.read(maxim)
	except (IOError, OSError):
		return None
	return date.decode("utf-8", "replace")


def _citesteRaport(cale):
	"""Textul unui raport de eroare: la XML-ul lui bsod.cpp inceputul (antetul si jurnalul sunt primele, anexele mari
	vin dupa), la textul lui mytest.py sfarsitul (Traceback-ul e la urma). None daca nu se poate citi."""
	try:
		with open(cale, "rb") as f:
			inceput = f.read(MAX_CITIRE_XML)
			if inceput.lstrip()[:1] == b"<":
				return inceput.decode("utf-8", "replace")
			f.seek(0, 2)
			marime = f.tell()
			if marime <= len(inceput):
				return inceput.decode("utf-8", "replace")
			f.seek(max(0, marime - MAX_CITIRE))
			return f.read(MAX_CITIRE).decode("utf-8", "replace")
	except (IOError, OSError):
		return None


def _uptime():
	try:
		with open("/proc/uptime", "rb") as f:
			return int(float(f.read().split()[0]))
	except (IOError, OSError, ValueError, IndexError):
		return None


def opririRecente(acum=None, cale=None):
	"""[(secunde de la oprire, cod)] din numaratoarea din RAM, numai cele din ultimele 10 minute, cele noi primele."""
	text = _citesteText(cale or CADERI, 64 * 1024) or ""
	acum = _uptime() if acum is None else acum
	rez = []
	for rand in text.split("\n"):
		parti = rand.split()
		if len(parti) < 2 or not parti[0].isdigit() or not parti[1].isdigit():
			continue
		t, cod = int(parti[0]), int(parti[1])
		if acum is None or (t <= acum and acum - t <= FEREASTRA_S):
			rez.append((0 if acum is None else acum - t, cod))
	rez.reverse()
	return rez


# ce inseamna codul de iesire al lui enigma2, in cuvinte (codurile numarate de enigma2.sh)
TEXTE_COD = {
	5: N_("eroare în programul interfeței"),
	134: N_("cădere în program (oprire forțată)"),
	137: N_("oprită după ecranul de eroare"),
	139: N_("cădere în program (acces greșit la memorie)"),
	143: N_("nu mai răspundea și a fost oprită de paznicul receptorului"),
}


# 0.3.0: cauza fiecarei opriri, scrisa de enigma2.sh la sfarsitul randului („; cauza: <fel>[: <amanunte>]”, din
# fisierul lasat de bsodFatal, main/bsod.cpp); randul spune cauza in cuvinte, nota de sub el locul (fisierul si randul
# erorii Python, biblioteca in care a cazut programul). Randurile vechi, fara cauza, raman cu textul codului.
CAUZA = re.compile(r"; cauza: ([a-z+]+)(?:: (.*))?$")
LOC_CPP = re.compile(r"\bin ([A-Za-z0-9._+/-]+)")
TEXTE_CAUZA = {
	"python": N_("eroare în codul Python al interfeței"),
	"c++": N_("cădere în programul interfeței"),
	"placa": N_("cădere în placa 2D (accelerarea s-a oprit singură)"),
	"eroare": N_("eroare fatală în programul interfeței"),
	"oprire": N_("oprită la cerere, nu e o cădere"),
	"memorie": N_("oprită de sistem: memoria s-a terminat"),
	"paznic": N_("nu mai răspundea și a fost oprită de paznicul receptorului"),
	"necunoscuta": N_("oprită fără raport de eroare"),
}


def cauzaDinRand(rest):
	"""-> (fel, locul) din randul jurnalului: fel e o cheie din TEXTE_CAUZA (sau None la un rand vechi), locul e textul
	tehnic (fisierul si randul erorii Python, biblioteca caderii) sau „”."""
	m = CAUZA.search(rest or "")
	if not m:
		return None, ""
	fel, amanunte = m.group(1), (m.group(2) or "").strip()
	if fel == "c++":
		loc = LOC_CPP.search(amanunte)
		if "hiaccel" in amanunte or "placii 2D" in amanunte:
			fel = "placa"
		return fel, loc.group(1) if loc else ""
	if fel not in TEXTE_CAUZA:
		return None, ""
	return fel, amanunte if fel == "python" else ""


def textCod(cod):
	if cod in TEXTE_COD:
		return _t(TEXTE_COD[cod])
	if cod > 128:
		return _t("oprită de semnalul %d") % (cod - 128)
	return _t("oprită cu codul %d") % cod


def _data(an, luna, zi, ora, minut):
	return "%s.%s.%s, %s:%s" % (zi, luna, an, ora, minut)


# randurile scrise de enigma2.sh despre modul sigur, in ordinea in care se cauta (cele mai lungi intai):
# (inceputul randului, fel, textul)
INTAMPLARI = (
	("modul sigur: iesire", "iesire", N_("ieșire din modul sigur")),
	("setarile de dinainte puse inapoi singure", "setari", N_("setările de dinainte puse înapoi singure")),
	("setarile de dinainte nu s-au pus inapoi singure", "setari",
		N_("setările de dinainte nu s-au putut pune înapoi singure")),
	("setarile de dinainte puse inapoi", "setari", N_("setările de dinainte puse înapoi")),
	("setarile de dinainte nu s-au pus inapoi", "setari", N_("setările de dinainte nu s-au putut pune înapoi")),
)


def evenimente(cale=None, maxim=MAX_EVENIMENTE):
	"""Ultimele intamplari din jurnalul opririlor, cele noi primele: [{"cand", "fel", "text", "cod"}] (la opriri si
	"placa_2d": oprirea a venit cu accelerarea 2D pornita; se spune pe o nota sub rand, ca randul sa ramana intreg).
	fel: „oprire”, „mod_sigur”, „mod_sigur_opriri” (si modul sigur s-a oprit), „iesire”, „setari”; randurile de alt
	fel (unirea setarilor din copie, accelerarea 2D) raman numai in textul brut."""
	text = _citesteText(cale or JURNAL_CADERI, 64 * 1024) or ""
	rez = []
	for rand in reversed(text.split("\n")):
		m = RAND_JURNAL.match(rand.strip())
		if not m:
			continue
		an, luna, zi, ora, minut, _sec, rest = m.groups()
		cand = _data(an, luna, zi, ora, minut)
		o = OPRIRE.search(rest)
		ev = None
		if o:
			cod = int(o.group(1))
			cauza, loc = cauzaDinRand(rest)
			ev = {"cand": cand, "fel": "oprire", "cod": cod, "text": _t(TEXTE_CAUZA[cauza]) if cauza else textCod(cod),
				"placa_2d": "placa 2D folosita" in rest, "cauza": cauza, "loc": loc}
		else:
			for inceput, fel, descriere in INTAMPLARI:
				if rest.startswith(inceput):
					ev = {"cand": cand, "fel": fel, "cod": None, "text": _t(descriere)}
					break
			if ev is None and rest.startswith("modul sigur:"):
				if "si in modul sigur" in rest:
					ev = {"cand": cand, "fel": "mod_sigur_opriri", "cod": None,
						"text": _t("oprit și în modul sigur, setările de dinainte se pun înapoi singure")}
				else:
					ev = {"cand": cand, "fel": "mod_sigur", "cod": None, "text": _t("pornit în modul sigur")}
		if ev is None:
			continue
		rez.append(ev)
		if len(rez) >= maxim:
			break
	return rez


# ------------------------------------------------------------------ rapoartele de eroare

def rapoarte(dosare=None):
	"""Rapoartele de eroare, cele noi primele: [(cale, ora)]; ora e din numele fisierului (secunde)."""
	gasite = []
	for dosar in (dosare or (DOSAR_JURNALE, RAM)):
		try:
			nume = os.listdir(dosar)
		except (IOError, OSError):
			continue
		for n in nume:
			m = RAPORT.match(n)
			if m:
				gasite.append((os.path.join(dosar, n), int(m.group(1))))
	gasite.sort(key=lambda x: x[1], reverse=True)
	return gasite


def _jurnalDinRaport(text):
	"""(jurnalul enigma2, data scrisa, ecranul, eroarea scrisa) din textul unui raport: XML-ul lui bsod.cpp (jurnalul in
	CDATA) sau textul lui mytest.py (antetul „HD Satelit:”, „Ecran:”, „Eroare:”, apoi Traceback-ul; antetul nu e jurnal
	si nu intra in el)."""
	data = ecran = eroare = ""
	m = re.search(r"<crashdate>([^<]{1,60})</crashdate>", text)
	if m:
		data = m.group(1).strip()
	i = text.find("<enigma2crashlog>")
	if i >= 0:
		j = text.find("</enigma2crashlog>", i)
		corp = text[i + len("<enigma2crashlog>"):j if j >= 0 else len(text)]
		# „]]>” din jurnal e scris ca „]]]]><![CDATA[>” (main/xmlgenerator.cpp)
		corp = corp.replace("]]]]><![CDATA[>", "\x00")
		corp = corp.replace("<![CDATA[", "").replace("]]>", "").replace("\x00", "]]>")
		return corp.strip("\n"), data, ecran, eroare
	randuri_ = text.split("\n")
	k = 0
	while k < len(randuri_) and k < 6 and (randuri_[k].startswith(ANTET_RAPORT_TEXT) or not randuri_[k].strip()):
		if randuri_[k].startswith("Ecran: "):
			ecran = randuri_[k][7:].strip()
		elif randuri_[k].startswith("Eroare: "):
			eroare = randuri_[k][8:].strip()
		k += 1
	return "\n".join(randuri_[k:]), data, ecran, eroare


def _numeEcran(text):
	"""„<class 'Screens.PositionerSetup.HdsPositionerSetup'>” -> „HdsPositionerSetup”."""
	m = re.search(r"'([A-Za-z0-9_.]+)'", text or "")
	return (m.group(1) if m else (text or "")).split(".")[-1]


def _caleScurta(cale):
	if cale.startswith(PREFIX_PYTHON):
		return cale[len(PREFIX_PYTHON):]
	return cale


def analizaEroare(jurnal):
	"""Ultima eroare Python din textul unui jurnal: {"fel", "mesaj", "cadre": [(cale, rand, functie)], "randuri":
	ultimele randuri dinaintea ei}, sau None daca jurnalul nu are un Traceback."""
	randuri_ = jurnal.split("\n")
	poz = -1
	for k in range(len(randuri_) - 1, -1, -1):
		if "Traceback (most recent call last):" in randuri_[k]:
			poz = k
			break
	if poz < 0:
		return None
	cadre = []
	fel = mesaj = ""
	for rand in randuri_[poz + 1:poz + 400]:
		c = CADRU.search(rand)
		if c:
			cadre.append((c.group(1), int(c.group(2)), c.group(3)))
			continue
		if not cadre:
			continue
		e = EXCEPTIE.match(rand)
		if e and not rand.startswith((" ", "\t")):
			fel, mesaj = e.group(1), (e.group(2) or "").strip()
			break
		if rand and not rand.startswith((" ", "\t")):
			# un rand fara indentare care nu e o exceptie cunoscuta: „Nume: mesaj”
			m = re.match(r"^([A-Za-z_][A-Za-z0-9_.]*): (.*)$", rand)
			if m:
				fel, mesaj = m.group(1), m.group(2).strip()
			break
	inainte = [r.rstrip() for r in randuri_[max(0, poz - 60):poz] if r.strip() and not SECRET.search(r)]
	return {"fel": fel, "mesaj": mesaj, "cadre": cadre, "randuri": inainte[-MAX_RANDURI_JURNAL:]}


def ultimeleRanduri(jurnal, n=MAX_RANDURI_JURNAL):
	"""Ultimele randuri ale jurnalului unei caderi fara eroare Python (un semnal in codul nativ): cele dinaintea
	registrelor scrise de main/bsod.cpp („PC: ...”), fara randurile goale si fara secrete."""
	randuri_ = jurnal.split("\n")
	for k in range(len(randuri_) - 1, -1, -1):
		if randuri_[k].lstrip().startswith("PC: "):
			randuri_ = randuri_[:k]
			break
	randuri_ = [r.rstrip() for r in randuri_ if r.strip() and not SECRET.search(r) and r.strip() != "-------"]
	return randuri_[-n:]


def extensieDinJurnal(randuri_, pe_disc):
	"""„<fel>/<nume>” al ultimei extensii care a scris in randurile date („[NumeExtensie] ...”), cautand de la sfarsit;
	"" daca niciun rand nu are eticheta unei extensii de pe disc (`pe_disc`: {nume: „<fel>/<nume>”})."""
	for rand in reversed(randuri_ or []):
		m = ETICHETA.match(rand)
		if m and m.group(1) in pe_disc:
			return pe_disc[m.group(1)]
	return ""


def analizaRaport(cale, ora=None, imagine=None, pe_disc=None):
	"""Rezumatul unui raport de eroare, pentru ecran si web, sau None daca nu se poate citi."""
	text = _citesteRaport(cale)
	if text is None:
		return None
	jurnal, data, ecran, eroare = _jurnalDinRaport(text)
	e = analizaEroare(jurnal) or {"fel": "", "mesaj": "", "cadre": [], "randuri": ultimeleRanduri(jurnal)}
	rez = {"cale": cale, "ora": ora, "cand": "", "ecran": _numeEcran(ecran) if ecran else "", "fel": e["fel"],
		"mesaj": e["mesaj"] or ("" if e["fel"] else eroare), "loc": "", "rand": 0, "functie": "", "extensie": "",
		"extensie_imagine": None, "extensie_jurnal": "", "randuri": e["randuri"]}
	rez["cand"] = (_ora(ora) if ora else "") or data
	# locul: ultimul cadru din codul enigma2 (nu din biblioteca Python); extensia: ultimul cadru dintr-un plugin
	loc = None
	for cadru in e["cadre"]:
		if cadru[0].startswith(PREFIX_PYTHON):
			loc = cadru
		if cadru[0].startswith(PREFIX_PLUGINURI):
			parti = cadru[0][len(PREFIX_PLUGINURI):].split("/")
			if len(parti) >= 3 and NUME_PLUGIN.match(parti[1]):
				rez["extensie"] = parti[0] + "/" + parti[1]
	if loc is None and e["cadre"]:
		loc = e["cadre"][-1]
	if loc is not None:
		rez["loc"], rez["rand"], rez["functie"] = _caleScurta(loc[0]), loc[1], loc[2]
	# fara extensie in Traceback (o cadere in codul nativ): ultima extensie care a scris in jurnal inaintea erorii
	if not rez["extensie"] and rez["randuri"]:
		rez["extensie_jurnal"] = extensieDinJurnal(rez["randuri"], pluginuriPeDisc() if pe_disc is None else pe_disc)
	ext = rez["extensie"] or rez["extensie_jurnal"]
	if ext and imagine is not None:
		rez["extensie_imagine"] = ext in imagine
	return rez


def ultimaEroare(imagine=None, pe_disc=None):
	for cale, ora in rapoarte()[:3]:
		r = analizaRaport(cale, ora, imagine, pe_disc)
		if r is not None:
			return r
	return None


# ------------------------------------------------------------------ copia setarilor

def copie(cale=None):
	"""{"exista", "cand"}: copia setarilor de dinainte (settings.bune) si ora ei."""
	cale = cale or SETARI_BUNE
	try:
		st = os.stat(cale)
	except OSError:
		return {"exista": False, "cand": ""}
	if st.st_size <= 0:
		return {"exista": False, "cand": ""}
	return {"exista": True, "cand": _ora(st.st_mtime)}


def facCopia(pornire=None, bune=None, facuta=None, mediu=None):
	"""Copia setarilor cu care a pornit interfata devine settings.bune. Chemata o data pe proces, dupa 10 minute de mers.
	Intoarce un cuvant: „facuta”, „la_fel” (aceeasi ca pe disc, nimic scris), „mod_sigur”, „lipsa” (fara copia din
	RAM: interfata nu a pornit prin enigma2.sh), „stricata” (fara niciun rand config.), „eroare”. Cuvantul ramane in RAM
	(COPIE_FACUTA), numai pentru cine se uita pe receptor."""
	pornire, bune, facuta = pornire or SETARI_PORNIRE, bune or SETARI_BUNE, facuta or COPIE_FACUTA
	if activ(mediu):
		return "mod_sigur"
	try:
		with open(pornire, "rb") as f:
			date = f.read(MAX_SETARI + 1)
	except (IOError, OSError):
		return "lipsa"
	if len(date) > MAX_SETARI or not re.search(br"(?m)^config\.", date):
		return "stricata"
	try:
		with open(bune, "rb") as f:
			vechi = f.read(MAX_SETARI + 1)
	except (IOError, OSError):
		vechi = None
	rez = "la_fel"
	if vechi != date:
		nou = bune + ".nou"
		try:
			fd = os.open(nou, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o600)
			try:
				os.write(fd, date)
				os.fsync(fd)
			finally:
				os.close(fd)
			os.replace(nou, bune)
		except (IOError, OSError) as e:
			_log("copia setarilor nu s-a scris: %s" % e)
			try:
				os.remove(nou)
			except OSError:
				pass
			return "eroare"
		rez = "facuta"
	try:
		with io.open(facuta, "w", encoding="utf-8", newline="\n") as f:
			f.write(u"%s\n" % rez)
	except (IOError, OSError):
		pass
	return rez


def _laCeas():
	def lucru():
		try:
			_log("copia setarilor de dinainte: %s" % facCopia())
		except Exception as e:
			_log("copia setarilor de dinainte: %s" % e)
	t = threading.Thread(target=lucru, name="HdsModSigurCopie")
	t.daemon = True
	t.start()


def _programeazaCopia():
	from enigma import eTimer
	t = eTimer()
	try:
		_ceas["legatura"] = t.timeout.connect(_laCeas)
	except AttributeError:
		t.callback.append(_laCeas)
	t.start(COPIE_DUPA_S * 1000, True)
	_ceas["t"] = t


# ------------------------------------------------------------------ citirile pe fir

def peFir(lucru, gata, fabrica_ceas=None):
	"""lucru() pe un fir separat; gata(rezultat, eroare) pe firul enigma2, dintr-un eTimer care se uita la fir la
	fiecare PAS_FIR_MS. `eroare` e None cand lucru() s-a terminat bine. Intoarce firul."""
	if fabrica_ceas is None:
		from enigma import eTimer as fabrica_ceas
	rez = {}

	def fir():
		try:
			rez["gata"] = lucru()
		except Exception as e:
			rez["eroare"] = e

	ceas = fabrica_ceas()
	pastrat = [ceas, None]

	def verifica():
		if "gata" not in rez and "eroare" not in rez:
			return
		ceas.stop()
		with _lacat:
			if pastrat in _fire:
				_fire.remove(pastrat)
		try:
			gata(rez.get("gata"), rez.get("eroare"))
		except Exception as e:
			_log("citirea de pe fir: %s" % e)

	try:
		ceas.callback.append(verifica)
	except AttributeError:
		pastrat[1] = ceas.timeout.connect(verifica)
	with _lacat:
		_fire.append(pastrat)
	t = threading.Thread(target=fir, name="HdsModSigurCitire")
	t.daemon = True
	t.start()
	ceas.start(PAS_FIR_MS, False)
	return t


# ------------------------------------------------------------------ pornirea (mytest.py)

def porneste():
	"""Chemata din mytest.py dupa ce se face sesiunea. In modul sigur intoarce clasa ecranului care se deschide primul;
	altfel programeaza copia setarilor peste 10 minute si intoarce None. Nu arunca."""
	este = activ()
	try:
		from Components.SystemInfo import SystemInfo
		SystemInfo["HdsModSigur"] = este
	except Exception as e:
		_log("SystemInfo: %s" % e)
	if este:
		imagine, sursa = pluginuriImagine()
		_log("pornit in modul sigur; pluginurile imaginii dupa %s, oprite: %s" % (
			sursa or "nimic (nu se poate afla)", ", ".join(oprite()) or "niciunul"))
		try:
			from Screens.HdsModSigur import HdsModSigur
			return HdsModSigur
		except Exception as e:
			_log("ecranul: %s" % e)
			return None
	try:
		_programeazaCopia()
	except Exception as e:
		_log("copia setarilor nu s-a programat: %s" % e)
	return None


# ------------------------------------------------------------------ alegerile

def _sterge(*cai):
	for cale in cai:
		try:
			os.remove(cale)
		except OSError:
			pass


def _scrieCererea(cuvant):
	try:
		with io.open(CERERE, "w", encoding="utf-8", newline="\n") as f:
			f.write(u"%s\n" % cuvant)
		return True
	except (IOError, OSError) as e:
		_log("cererea %s: %s" % (cuvant, e))
		return False


def _setariPuseSingure(s=None):
	a = (s if s is not None else {"automat": citesteSemn()["automat"]}).get("automat") or {}
	return a.get("rez") == "da"


def pornesteNormal():
	"""„Pornește normal”: cererea „normal” pentru enigma2.sh. (ok, text). Semnul si numaratoarea le sterge enigma2.sh
	la pornirea urmatoare, cand face cererea."""
	if not _scrieCererea("normal"):
		return False, textCerereNescrisa()
	return True, _t("La repornire pornesc toate extensiile.")


def punInapoiSetarile():
	"""„Pune înapoi setările de dinainte”: cererea „setari” pentru enigma2.sh, numai cu settings.bune si numai daca
	setarile nu au fost deja puse inapoi singure. (ok, text)."""
	if _setariPuseSingure():
		return False, textSetariDejaPuse()
	c = copie()
	if not c["exista"]:
		return False, textFaraCopie()
	if not _scrieCererea("setari"):
		return False, textCerereNescrisa()
	return True, _t("La repornire se pun înapoi setările din %s.") % c["cand"]


def anuleazaCererea():
	"""Repornirea a fost refuzata: cererea nu se mai face, modul sigur continua."""
	_sterge(CERERE)


def repornireCuIntrebare(sesiune):
	"""True cand repornirea interfetei cere o confirmare pe televizor (TryQuitMainloop intreaba cand o inregistrare e in
	curs sau incepe in mai putin de 6 minute, sau cand sunt lucrari in fundal)."""
	try:
		nav = sesiune.nav
		if nav.getRecordings():
			return True
		urmatoarea = nav.RecordTimer.getNextRecordingTime()
		if urmatoarea > 0 and urmatoarea - time.time() < 360:
			return True
	except Exception:
		pass
	try:
		from Components.Task import job_manager
		if job_manager.getPendingJobs():
			return True
	except Exception:
		pass
	return False


def reporneste(sesiune, dupa_ms=0, la_refuz=None):
	"""Repornirea interfetei, ca din meniu (TryQuitMainloop 3). Cu `dupa_ms` incepe dupa atatea milisecunde (raspunsul
	unei cereri web pleaca inainte, textul alegerii se vede pe ecran). TryQuitMainloop cheama raspunsul numai cand
	repornirea nu se face (la „Da” opreste interfata direct, la „Nu” inchide intrebarea cu True): atunci cererea se
	sterge si se cheama `la_refuz`. False fara sesiune."""
	if sesiune is None:
		return False

	def refuzata(*_a):
		anuleazaCererea()
		_log("repornirea interfetei nu s-a facut: cererea stearsa, modul sigur continua")
		if la_refuz is not None:
			la_refuz()

	def acum():
		from Screens.Standby import TryQuitMainloop
		sesiune.openWithCallback(refuzata, TryQuitMainloop, 3)

	if dupa_ms <= 0:
		acum()
		return True
	from enigma import eTimer
	t = eTimer()
	try:
		_ceas["repornire_legatura"] = t.timeout.connect(acum)
	except AttributeError:
		t.callback.append(acum)
	t.start(dupa_ms, True)
	_ceas["repornire"] = t
	return True


# ------------------------------------------------------------------ textele (aceleasi pe televizor si in web)

def titlu():
	return _t("Mod sigur")


def textMesaj():
	return _t("Receptorul a căzut de mai multe ori la pornire. Am pornit în mod sigur.")


def textFaraCopie():
	"""Raspunsul la alegerea setarilor cand nu exista copia (OK pe randul stins, butonul din web)."""
	return _t("Nu se poate încă: nu există o copie a setărilor. Alege „Pornește normal” sau „Vezi ce s-a întâmplat”.")


def textNuSePoate(s):
	"""Raspunsul la OK pe alegerea setarilor cand nu se poate (randul stins)."""
	return textSetariDejaPuse() if _setariPuseSingure(s) else textFaraCopie()


def textSetariDejaPuse():
	return _t("Nu mai e nevoie: setările de dinainte sunt deja puse înapoi.")


def textCerereNescrisa():
	return _t("Cererea nu s-a putut scrie în memoria receptorului.")


def textRepornireRefuzata():
	return _t("Interfața nu s-a repornit, deci alegerea nu s-a făcut. Receptorul rămâne în modul sigur; poți alege din "
		"nou.")


def textPentruExtensii(mediu=None):
	"""Fraza pentru ecranul si pagina Extensii in modul sigur, sau "" in afara lui."""
	if not activ(mediu):
		return ""
	n = len(oprite())
	if not n:
		return _t("Mod sigur: pornesc numai extensiile venite cu imaginea.")
	return _cuNumar(ngettext("Mod sigur: o extensie instalată de tine e oprită acum, nu ștearsă.",
		"Mod sigur: %d extensii instalate de tine sunt oprite acum, nu șterse.", n), n)


def textPanou(mediu=None):
	"""Banda panoului web (plugin.py, /api/statusinfo) cat timp interfata e in modul sigur, sau "" in afara lui. Numai
	variabila de mediu: panoul o cere la 3 s."""
	if not activ(mediu):
		return ""
	return _t("Receptorul e în modul sigur: extensiile instalate de tine sunt oprite. Vezi ce s-a întâmplat și alege "
		"cum continui.")


def textPentruFonturi(mediu=None):
	"""Fraza pentru ecranul si pagina Fonturi in modul sigur, sau "" in afara lui."""
	if not activ(mediu):
		return ""
	return _t("Mod sigur: fonturile descărcate nu sunt încărcate acum; rămân pe receptor și pornesc după ieșire.")


def _listaScurta(nume, max_litere=MAX_NUME_EXPLICATIE):
	"""Numele, cate incap in `max_litere` (cel putin unul), apoi „și încă N”."""
	ales = []
	for n in nume:
		if ales and len(", ".join(ales + [n])) > max_litere:
			break
		ales.append(n)
	rest = len(nume) - len(ales)
	text = ", ".join(ales)
	if rest:
		text += " " + _cuNumar(ngettext("și încă una", "și încă %d", rest), rest)
	return text


def textExplicatie(s):
	"""Fraza de sub mesaj: cate opriri au fost, setarile puse inapoi singure si extensiile oprite (primele nume; lista
	intreaga in „Ce s-a întâmplat”)."""
	fraze = []
	n = s.get("recente") or 0
	if n > 0:
		fraze.append(_cuNumar(ngettext("Interfața s-a oprit neașteptat o dată în ultimele 10 minute.",
			"Interfața s-a oprit neașteptat de %d ori în ultimele 10 minute.", n), n))
	a = s.get("automat") or {}
	if a.get("rez") == "da":
		fraze.append(_t("Modul sigur s-a oprit și el, așa că am pus înapoi singur setările de dinainte."))
	elif a:
		fraze.append(_t("Modul sigur s-a oprit și el, dar setările de dinainte nu s-au putut pune înapoi."))
	nume = [numeExtensie(c) for c in s.get("oprite") or []]
	if s.get("imagine_necunoscuta"):
		fraze.append(_t("Nu am putut afla care extensii vin cu imaginea, așa că au pornit toate."))
	elif nume:
		fraze.append(_t("Extensiile instalate de tine sunt oprite acum, nu șterse: %s.") % _listaScurta(nume))
	else:
		fraze.append(_t("Pe receptor nu era nicio extensie instalată de tine."))
	return " ".join(fraze)


ALEGERI = ("normal", "setari", "detalii")


def alegeri(s):
	"""[(cheie, titlu, descriere, se_poate)] pentru lista de pe ecran si butoanele din web."""
	c = s.get("copie") or {}
	if _setariPuseSingure(s):
		setari, poate = _t("Setările de dinainte sunt deja puse înapoi: receptorul le-a pus singur, după ce și modul "
			"sigur s-a oprit neașteptat."), False
	elif c.get("exista"):
		setari, poate = _t("Pune înapoi setările din %s, salvate după 10 minute de mers fără cădere, apoi repornește "
			"interfața. Setările de acum rămân păstrate într-o copie.") % c.get("cand"), True
	else:
		setari, poate = _t("Nu există încă o copie a setărilor. Receptorul o face singur după 10 minute de mers fără "
			"cădere."), False
	return [
		("normal", _t("Pornește normal"), _t("Repornește interfața cu toate extensiile. Dacă eroarea apare din nou de "
			"5 ori în 10 minute, receptorul revine singur în modul sigur."), True),
		("setari", _t("Pune înapoi setările de dinainte"), setari, poate),
		("detalii", _t("Vezi ce s-a întâmplat"), _t("Ultima eroare pe scurt, opririle din ultima vreme și extensiile "
			"oprite."), True),
	]


def stare():
	"""Tot ce arata ecranul si pagina web."""
	este = activ()
	imagine, sursa = pluginuriImagine() if este else (None, None)
	semn = citesteSemn()
	st = {
		"activ": este,
		"semn": semnPus(),
		"cerere": cerereLasata(),
		"prag": PRAG,
		"recente": len(opririRecente()),
		"evenimente": evenimente(),
		"oprite": oprite(),
		"imagine_necunoscuta": bool(este and imagine is None),
		"sursa_imagine": sursa,
		"copie": copie(),
		"automat": semn["automat"],
		"opriri_mod_sigur": semn["opriri"],
		"ultima": ultimaEroare(imagine),
	}
	# raportul e de dinaintea opririi care a pus semnul (paznicul, cod 143, nu lasa raport): amandoua orele sunt
	# secunde de la 1970 (numele raportului, randul „ora=” al semnului), deci fusul orar nu conteaza
	u = st["ultima"]
	if u and u.get("ora") and semn["ora"]:
		u["vechi"] = semn["ora"] - u["ora"] > 120
	# numaratoarea din RAM se sterge la iesirea din modul sigur: dupa ea, numarul e „de la iesire”, nu al ultimelor 10
	# minute (opririle de dinainte raman in lista de dedesubt)
	for ev in st["evenimente"]:
		if ev["fel"] == "oprire":
			break
		if ev["fel"] == "iesire":
			st["dupa_iesire"] = True
			break
	return st


def _textLoc(u):
	if not u.get("loc"):
		return ""
	t = _t("%s, rândul %d") % (u["loc"], u["rand"])
	if u.get("functie") and u["functie"] not in ("<module>",):
		t += _t(", în %s") % u["functie"]
	return t


def _textExtensie(cheie, u, s):
	nume = numeExtensie(cheie)
	if not nume:
		return ""
	if cheie in (s.get("oprite") or []):
		return _t("%s, instalată de tine, oprită acum") % nume
	if u.get("extensie_imagine") is True:
		return _t("%s, a imaginii") % nume
	if u.get("extensie_imagine") is False:
		return _t("%s, instalată de tine") % nume
	return nume


def randuri(s):
	"""Randurile ecranului „Ce s-a întâmplat” si ale paginii web:
	(„titlu”, text): numele grupei;
	(„rand”, eticheta, valoare, ton): o valoare in cuvinte, colorata dupa ton;
	(„linie”, text): un element al listei de deasupra (o extensie oprita), in coloana valorilor;
	(„nota”, text): lamurirea tehnica a randului de deasupra, mai mica.
	Randurile de jurnal nu sunt aici: ele sunt text brut (tasta ALBASTRA, sectiunea „Text brut” din web)."""
	R = []
	R.append(("titlu", _t("Opririle interfeței")))
	n = s.get("recente") or 0
	eticheta = _t("De la ieșirea din modul sigur") if s.get("dupa_iesire") else _t("În ultimele 10 minute")
	R.append(("rand", eticheta, _cuNumar(ngettext("o oprire neașteptată", "%d opriri neașteptate", n), n) if n else
		_t("niciuna"), RAU if n >= PRAG else (ATENTIE if n else BUN)))
	for ev in s.get("evenimente") or []:
		ton = RAU if ev["fel"] == "oprire" else (ATENTIE if ev["fel"] in ("mod_sigur", "mod_sigur_opriri") else NORMAL)
		if ev.get("cauza") == "oprire":
			ton = NORMAL          # oprire ceruta (SIGTERM fara paznic): nu e o cadere
		text = ev["text"] + (" (%s %d)" % (_t("cod"), ev["cod"]) if ev.get("cod") is not None else "")
		R.append(("rand", ev["cand"], text, ton))
		if ev.get("loc"):
			R.append(("nota", (_t("Locul erorii: %s") if ev.get("cauza") == "python" else _t("Locul căderii: %s")) %
				ev["loc"]))
		if ev.get("placa_2d") and ev.get("cauza") not in ("placa",):
			R.append(("nota", _t("Placa 2D lucra în acel moment, dar oprirea nu e pusă pe seama ei.") if ev.get("cauza")
				else _t("Placa 2D lucra în acel moment.")))
	if not s.get("evenimente"):
		R.append(("rand", _t("Jurnalul opririlor"), _t("gol"), STINS))

	R.append(("titlu", _t("Ultima eroare")))
	u = s.get("ultima")
	if not u:
		R.append(("rand", _t("Raportul de eroare"), _t("nu există"), STINS))
	else:
		cand = u.get("cand") or _t("nu se știe")
		if u.get("vechi"):
			cand = _t("%s, înaintea ultimei opriri (ea nu a lăsat raport)") % cand
		R.append(("rand", _t("Când"), cand, ATENTIE if u.get("vechi") else NORMAL))
		if u.get("ecran"):
			R.append(("rand", _t("Ecranul"), u["ecran"], NORMAL))
		if u.get("fel") or u.get("mesaj"):
			R.append(("rand", _t("Eroarea"), ": ".join(x for x in (u.get("fel"), u.get("mesaj")) if x), RAU))
		else:
			R.append(("rand", _t("Eroarea"), _t("cădere în programul receptorului"), RAU))
			R.append(("nota", _t("În codul nativ, fără eroare Python; registrele sunt în textul brut.")))
		loc = _textLoc(u)
		if loc:
			R.append(("rand", _t("Locul"), loc, NORMAL))
		if u.get("extensie"):
			R.append(("rand", _t("Extensia"), _textExtensie(u["extensie"], u, s), ATENTIE))
		elif u.get("extensie_jurnal"):
			R.append(("rand", _t("Ultima extensie din jurnal"), _textExtensie(u["extensie_jurnal"], u, s), ATENTIE))
			R.append(("nota", _t("A scris în jurnal chiar înainte de cădere.")))
		if u.get("randuri"):
			R.append(("nota", _t("Ultimele rânduri din jurnal, dinaintea erorii, sunt în textul brut.")))

	R.append(("titlu", _t("Modul sigur")))
	if s.get("activ"):
		R.append(("rand", _t("Starea"), _t("pornit acum"), ATENTIE))
	elif s.get("semn"):
		R.append(("rand", _t("Starea"), _t("pornește la repornirea interfeței"), ATENTIE))
	else:
		R.append(("rand", _t("Starea"), _t("oprit"), BUN))
	if s.get("activ"):
		if s.get("imagine_necunoscuta"):
			R.append(("rand", _t("Extensii oprite"), _t("niciuna (nu se poate afla care sunt ale imaginii)"), ATENTIE))
		else:
			nume = [numeExtensie(c) for c in s.get("oprite") or []]
			k = len(nume)
			R.append(("rand", _t("Extensii oprite"), _cuNumar(ngettext("o extensie", "%d extensii", k), k) if k else _t("niciuna"),
				ATENTIE if k else NORMAL))
			for x in nume:
				R.append(("linie", x))
	c = s.get("copie") or {}
	R.append(("rand", _t("Copia setărilor"), (_t("făcută pe %s") % c["cand"]) if c.get("exista") else _t("nu există încă"),
		BUN if c.get("exista") else STINS))
	a = s.get("automat") or {}
	if a:
		if a.get("rez") == "da":
			R.append(("rand", _t("Puse înapoi singure"), a.get("cand") or _t("da"), ATENTIE))
		else:
			R.append(("rand", _t("Puse înapoi singure"), _t("nu s-a putut (copia lipsea)") if a.get("rez") == "lipsa" else
				_t("nu s-a putut (memoria plină?)"), RAU))
		R.append(("nota", _cuNumar(ngettext("După o oprire neașteptată și în modul sigur.",
			"După %d opriri neașteptate și în modul sigur.", s.get("opriri_mod_sigur") or PRAG2),
			s.get("opriri_mod_sigur") or PRAG2)))
	cerere = s.get("cerere")
	if cerere == "setari":
		R.append(("rand", _t("La repornire"), _t("se pun înapoi setările de dinainte"), ATENTIE))
	elif cerere == "normal":
		R.append(("rand", _t("La repornire"), _t("pornește normal, cu toate extensiile"), ATENTIE))
	elif cerere == "automat":
		R.append(("rand", _t("La repornire"), _t("se pun înapoi singure setările de dinainte"), ATENTIE))
	return R


# ------------------------------------------------------------------ textul brut

def _faraSecrete(text):
	return "\n".join(r for r in text.split("\n") if not SECRET.search(r))


def _coada(text, n=MAX_BRUT_RANDURI):
	randuri_ = text.rstrip("\n").split("\n")
	return "\n".join(randuri_[-n:])


def textBrutRaport(text):
	"""Textul brut al unui raport: la XML-ul lui bsod.cpp, jurnalul enigma2 (fara sumele fisierelor Python si fara
	restul anexelor, care nu spun ce s-a intamplat); la textul lui mytest.py, tot."""
	if "<enigma2crashlog>" not in text:
		return text
	return _jurnalDinRaport(text)[0]


def titluPagina(titlu_, pagina, total):
	"""Titlul textului brut pe televizor: numele scurt si „(n/m)”; calea e in prima linie a textului."""
	return "%s (%d/%d)" % (titlu_, pagina, total)


def titluRaport(ora):
	"""„Raport de eroare, 31.12.2026, 14:30:05”: cu secundele, fiindca doua opriri pot lasa rapoarte in acelasi minut."""
	cand = _ora(ora, "%d.%m.%Y, %H:%M:%S") if ora else ""
	return (_t("Raport de eroare, %s") % cand) if cand else _t("Raport de eroare")


def paginiBrute(cu_text=True):
	"""[(titlu, cale, text)] pentru textul brut (tasta albastra pe televizor, lista din web), fara secrete. Titlul e
	scurt (fara cale). Fara `cu_text` numai lista fisierelor (text gol), fara sa le citeasca. Cu text, citirile au cativa
	zeci de KiB: pe receptor se cheama pe un fir (peFir)."""
	pagini = []
	t = _citesteText(JURNAL_CADERI, 64 * 1024) if cu_text else ""
	pagini.append((_t("Jurnalul opririlor"), JURNAL_CADERI, "" if not cu_text else
		(_faraSecrete(_coada(t)) if t else _t("Fișierul nu există: nicio oprire neașteptată scrisă."))))
	for cale, ora in rapoarte()[:MAX_RAPOARTE_BRUTE]:
		t = _citesteRaport(cale) if cu_text else ""
		if t is not None:
			pagini.append((titluRaport(ora), cale,
				_faraSecrete(_coada(textBrutRaport(t), MAX_BRUT_RAPORT)) if cu_text else ""))
	t = _citesteText(CADERI, 16 * 1024) if cu_text else ""
	pagini.append((_t("Numărătoarea opririlor"), CADERI, "" if not cu_text else
		(_t("Fiecare rând: secunde de la pornirea receptorului și codul opririi.") + "\n\n" + t.strip() if t and t.strip()
		else _t("Goală: nicio oprire numărată de la ultima pornire a receptorului."))))
	return pagini
