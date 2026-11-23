# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsCautaSetari - „Caută setări”: cautarea in tot meniul receptorului, ca la telefoanele Android. Scrii cateva litere
# si apar meniurile, ecranele si randurile de setari care le au in nume, cu locul lor in meniu si valoarea de acum;
# OK deschide ecranul cu cursorul pe randul gasit. Ecranul de pe televizor e Screens/HdsCautaSetari.py, perechea web
# HdsWebControl/cauta_setari_web.py (/cauta-setari); amandoua folosesc indexul de aici.
#
# INDEXUL se face din fisierele imaginii, cu aceleasi reguli ca televizorul:
# - data/menu.xml: fiecare <menu> si <item> pe care il arata Screens/Menu.py acum (level= fata de
#   config.usage.setup_level, requires= din SystemInfo, cu „!”, ordinea dupa weight), cu drumul de la primul nivel, si
#   extensiile agatate de un meniu (PluginComponent.getPluginsForMenu, ca Menu.__init__);
# - data/setup.xml: randurile ecranelor <setup id="..."/> la care duce o intrare vizibila, cu regulile lui
#   Screens/Setup.addItems (level=, requires= fara „!”, conditional=, randurile ConfigNothing sau fara setare sarite);
# - ecranele noastre cu randuri proprii (nu din setup.xml): REGISTRU de mai jos, pe entryID-ul intrarii care deschide
#   ecranul (textul randului de pe ecran, setarea config, cuvinte de cautare); o extensie isi poate inscrie randurile
#   cu inregistreaza(). Randurile unei intrari ascunse (requires=, level=) nu intra in index.
# Textele sunt cele de pe ecran, traduse in limba meniului. Cautarea merge pe textul tradus, pe textul scris in fisier si
# pe traducerea romaneasca, fara diacritice si fara majuscule („setari” si „SETARI” gasesc „Setări”). Fiecare cuvant
# cautat trebuie sa fie undeva in titlu, in drum sau in cuvintele de cautare si descriere, si macar unul in afara
# drumului; titlul cantareste cel mai mult.
# Un ecran de setari la care duc doua intrari (avsetup, usage) are randurile sub amandoua; in rezultate ramane drumul
# care se potriveste mai bine.
#
# Indexul se face o data, la prima cautare, si se reface numai cand se schimba limba, nivelul, menu.xml / setup.xml,
# SystemInfo-ul din requires=, rezultatul unui conditional= sau randurile inscrise; valorile de acum se citesc la
# afisare, numai pentru rezultatele aratate. Valoarea se arata numai la setarile simple (Da / Nu, alegeri, numere,
# glisoare), niciodata la texte (parole, chei, adrese). Conditional= se evalueaza fara eval: numai setari config,
# valori scrise, comparatii, and / or / not (ast); ce nu se poate evalua arata randul, ca Setup.conditieAdevarata.
#
# Deschiderea (deschide()): un meniu se deschide ca submeniu (Screens/Menu.Menu); o intrare ca in Menu.runScreen /
# openSetup, cu argumentele citite cu ast.literal_eval; un rand de setari deschide ecranul lui si muta cursorul pe rand
# (dupa setare, apoi dupa textul randului). Intrarile <code>, oprirea si repornirea receptorului si extensiile nu se
# pornesc din cautare: se deschide meniul lor cu cursorul pe ele, iar OK-ul ramane al omului. La inchidere setarile se
# salveaza cand un meniu de deasupra are flushConfigOnClose, ca la inchiderea meniului.
#
# Fisierul nu importa nimic din enigma2 la incarcare: il folosesc ecranul, interfata web si probele de pe PC.

import ast
import os
import re
import unicodedata
import xml.etree.ElementTree as ET

CALE_MENIU = None          # probele pun aici un menu.xml; pe receptor resolveFilename(SCOPE_SKIN, "menu.xml")
CALE_SETUP = None          # la fel pentru setup.xml; pe receptor ${datadir}/enigma2/setup.xml
CALE_PLUGINURI = None
# Limitele ecranelor si randurilor urmeaza contractul web existent.
MAX_PLUGINURI = 60
MAX_RANDURI_PLUGIN = 80
MAX_XML_PLUGIN = 512 * 1024
MAX_XML_TOTAL_PLUGIN = 2 * 1024 * 1024
MAX_NODURI_PLUGIN = 8192
MAX_DOSARE_PLUGIN = 2048
_NUME_PLUGIN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]{0,59}$")
_PARTE_PLUGIN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\[(?:[0-9]{1,3}|'[A-Za-z0-9_]{1,40}'|\"[A-Za-z0-9_]{1,40}\")\])*$")
ID_PROPRIU = "hds_cauta_setari"    # intrarea ecranului de cautare: nu se gaseste pe ea insasi
# toate intrarile care deschid ecranul de cautare (prima din Setari si cea din meniul principal): niciuna nu se gaseste
ID_PROPRII = frozenset((ID_PROPRIU, "hds_cauta_setari_principal"))
MAX_REZULTATE = 60
MAX_ADANCIME = 6
MAX_TEXT = 60              # cat se ia dintr-un text cautat (tastatura, web)
MAX_VALOARE = 40
SEPARATOR = " › "     # „Setări › Sunet și subtitrări”; semnul e in fonturile HDSatelit
SIMPLE = ("bool", "alegere", "numar", "glisor", "cifre")
# ecranele care opresc sau repornesc receptorul (Screens/Standby.py): ca in meniu_web.NEDESCHISE
OPRIRI = frozenset((("Standby", "Standby"), ("Standby", "TryQuitMainloop")))


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele se traduc la folosire."""
	return text


# Randurile ecranelor noastre care nu sunt in setup.xml: entryID-ul intrarii din menu.xml -> (textul randului, exact cum
# il scrie ecranul prin _(), setarea config sau "", cuvinte de cautare sau ""). Textul trebuie sa ramana acelasi cu cel
# din ecran: dupa el se gaseste randul cand setarea lipseste (proba test_cauta_setari_024 citeste ecranele).
REGISTRU = {
	"hds_piste_limbi": (       # Screens/HdsPisteLimbi.py
		(N_("Sunet, prima alegere"), "config.hds_piste.audio1", N_("limba sunetului")),
		(N_("Sunet, a doua alegere"), "config.hds_piste.audio2", ""),
		(N_("Sunet, a treia alegere"), "config.hds_piste.audio3", ""),
		(N_("Fără subtitrări niciodată"), "config.hds_piste.fara_subtitrari", ""),
		(N_("Subtitrare, prima alegere"), "config.hds_piste.sub1", N_("limba subtitrării")),
		(N_("Subtitrare, a doua alegere"), "config.hds_piste.sub2", ""),
		(N_("Subtitrare, a treia alegere"), "config.hds_piste.sub3", ""),
		(N_("Tradu automat din orice subtitrare disponibilă"), "config.hds_piste.tradu_orice", ""),
	),
	"hds_subtitrari_aspect": (     # Screens/HdsSubtitrariAspect.py
		(N_("Stil gata făcut"), "", ""),
		(N_("Fontul"), "config.subtitles.hds_stil_font", ""),
		(N_("Grosimea literelor"), "config.subtitles.hds_grosime", ""),
		(N_("Mărimea literelor"), "config.subtitles.hds_marime", ""),
		(N_("Culoarea literelor"), "config.subtitles.hds_culoare", ""),
		(N_("Conturul literelor"), "config.subtitles.hds_contur", ""),
		(N_("Umbră sub litere"), "config.subtitles.hds_umbra", ""),
		(N_("Fundal în spatele rândurilor"), "config.subtitles.hds_fundal", ""),
		(N_("Înălțimea față de marginea de jos"), "config.subtitles.hds_jos", ""),
		(N_("Distanța dintre rânduri"), "config.subtitles.hds_spatiere", ""),
		(N_("Mărirea subtitrărilor DVB"), "config.subtitles.hds_marire_dvb", ""),
	),
	"hds_traducere_subtitrari": (      # Screens/HdsTraducereSubtitrari.py
		(N_("Serviciul"), "config.hds_traducere.serviciu", ""),
		(N_("Limba traducerii"), "config.hds_traducere.limba", ""),
		(N_("Afișarea"), "config.hds_traducere.afisare", ""),
		(N_("Traducerea care întârzie"), "config.hds_traducere.tarziu", ""),
		(N_("Timpul de citire"), "config.hds_traducere.citire", ""),
		(N_("Și subtitrările DVB (imagini)"), "config.hds_traducere.dvb", ""),
		(N_("Tradu bara de jos"), "config.hds_traducere.bara", ""),
		(N_("Tradu EPG"), "config.hds_traducere.epg", ""),
		(N_("Tradu teletextul"), "config.hds_traducere.teletext", ""),
		(N_("Teletextul tradus"), "config.hds_traducere.teletext_mod", ""),
		(N_("Tradu HbbTV"), "config.hds_traducere.hbbtv", ""),
	),
	"hds_ecran_radio": (       # Screens/HdsEcranRadio.py, textele din Components/HdsRadioSetari.ETICHETE
		(N_("Ecranul radio pe tot ecranul"), "config.hds_radio.ecran", ""),
		(N_("Vizualizatorul"), "config.hds_radio.vizualizator", ""),
		(N_("Culorile"), "config.hds_radio.culori", ""),
		(N_("Numărul de bare"), "config.hds_radio.bare", ""),
		(N_("Fluiditatea"), "config.hds_radio.cadre", ""),
		(N_("Ecranul de odihnă"), "config.hds_radio.odihna", ""),
		(N_("Emisiunile următoare"), "config.hds_radio.epg", ""),
		(N_("Bara la schimbarea postului"), "config.hds_radio.bara_la_zap", ""),
	),
	"hds_paznic": (        # Screens/HdsPaznic.py
		(N_("Repornește interfața când nu mai răspunde"), "config.hds_paznic.interfata", ""),
		(N_("Așteaptă înainte de repornire"), "config.hds_paznic.asteptare", ""),
		(N_("Eliberează memoria decodorului în standby"), "config.hds_paznic.repornire_noapte", ""),
	),
	"hds_procesor": (      # Screens/HdsProcesor.py
		(N_("Modul de lucru"), "config.hds_procesor.mod", ""),
	),
	"hds_webcontrol_setup": (      # Screens/HdsWebControlSetup.py
		(N_("Activează HdsWebControl"), "config.plugins.hdswebcontrol.activ", ""),
		(N_("Port TCP"), "config.plugins.hdswebcontrol.port", ""),
		(N_("Aplicații de telefon"), "config.plugins.hdswebcontrol.aplicatii",
			N_("parolă aplicații telefon telecomandă")),
		(N_("Acces din afara casei"), "config.plugins.hdswebcontrol.aplicatii_afara",
			N_("internet router port parolă aplicații telefon")),
		(N_("Actualizarea imaginii pe prima pagină web"), "config.plugins.hdswebcontrol.captura_interval",
			N_("captură ecran secunde reîmprospătare")),
	),
	"time_setup": (        # Screens/Time.py
		(N_("Fus orar"), "config.timezone.val", ""),
		(N_("Fus orar după internet"), "config.timezone.automat", N_("fus orar automat țară")),
		(N_("De unde se ia ora"), "config.hds_time.sync_mode", ""),
		(N_("Server NTP"), "config.hds_time.ntp_server", ""),
	),
	"hds_antena_locul": (  # Screens/HdsLocul.py
		(N_("Alege țara și orașul"), "config.hds_locul.oras", N_("oraș țară")),
		(N_("Scrie coordonatele"), "config.hds_locul.lat", N_("latitudine longitudine coordonate")),
	),
	"hds_navigator_setari": (      # Screens/HdsNavigatorWeb.py, textele din Plugins/Extensions/HdsNavigator/setari.py
		(N_("Pagina de pornire"), "config.plugins.hdsnavigator.pagina_pornire", ""),
		(N_("Mărirea paginii"), "config.plugins.hdsnavigator.marire", ""),
		(N_("Mărimea minimă a literelor"), "config.plugins.hdsnavigator.font_minim", ""),
		(N_("Desenul paginii"), "config.plugins.hdsnavigator.desen", ""),
		(N_("Televizorul pentru YouTube"), "config.plugins.hdsnavigator.agent_tv", ""),   # 0.7.5, APL
		(N_("Chenarul pe selecție"), "config.plugins.hdsnavigator.chenar", ""),
		# 0.2.7: stilul chenarului; pe ecran numai cu chenarul pornit (viteza numai cu pulsul pornit)
		(N_("Culoarea chenarului"), "config.plugins.hdsnavigator.chenar_culoare", ""),
		(N_("Forma chenarului"), "config.plugins.hdsnavigator.chenar_forma", ""),
		(N_("Grosimea chenarului"), "config.plugins.hdsnavigator.chenar_grosime", ""),
		(N_("Chenarul pulsează"), "config.plugins.hdsnavigator.chenar_puls", ""),
		(N_("Viteza pulsului"), "config.plugins.hdsnavigator.chenar_viteza", ""),
		# 0.2.8: setarea principala HbbTV (oprita, nimic HbbTV nu mai porneste)
		(N_("HbbTV (aplicațiile canalelor)"), "config.plugins.hdsnavigator.hbbtv", ""),
		(N_("Semnul roșu HbbTV în bară"), "config.plugins.hdsnavigator.hbbtv_semn", ""),
		# 0.2.8: pornirea automata a aplicatiilor HbbTV, oprita din fabrica
		(N_("Pornirea automată a aplicațiilor HbbTV"), "config.plugins.hdsnavigator.hbbtv_autostart", ""),
		# HbbTV clar: desenul la marimea intreaga, oprit din fabrica; pe ecran numai cu HbbTV pornit
		(N_("HbbTV clar"), "config.plugins.hdsnavigator.hbbtv_clar", N_("claritate pixelat")),
		(N_("Șterge datele HbbTV"), "", ""),
	),
	"video_setup": (       # Screens/VideoSetup.py: randurile nu sunt setari config, se gasesc dupa text
		(N_("Resolution"), "", ""),
		(N_("Frecvență"), "", ""),
		(N_("Culorile pe HDMI"), "", ""),
		(N_("Imaginea 4:3"), "", ""),
		(N_("La schimbarea canalului"), "", ""),
	),
}

# Cuvinte de cautare pentru intrari de meniu care se cauta des cu alt nume decat cel din meniu (entryID -> cuvinte).
CUVINTE = {
	"hds_scanare": N_("căutare canale noi"),
	"hds_antena_rotire": N_("motor DiSEqC USALS"),
	"hds_ipv6": N_("adresa IPv6 odhcp6c DHCPv6"),
	"hds_samba": N_("Samba SMB partajare dosare rețea Windows Explorer NAS"),
	# Locuri din rețea (Media si copia din Rețea & internet): montarile cautate cu numele din alte imagini
	"hds_locuri_retea": N_("montare mount SMB CIFS NFS NAS Windows dosar partajat"),
	"hds_retea_locuri_retea": N_("montare mount SMB CIFS NFS NAS Windows dosar partajat"),
	"hds_antena_locul": N_("oraș țară latitudine longitudine coordonate USALS motor"),
	"audio_setup": N_("sunet AC3 DTS 5.1"),
	"time_setup": N_("ceas oră"),
	"network_setup": N_("rețea internet IP DHCP"),
	"language_setup": N_("limba meniului"),
	"parental_setup": N_("PIN copii"),
	"hds_software_update": N_("versiune nouă"),
	"hds_imagine_online": N_("versiune nouă"),
	"hds_actualizari": N_("actualizări pachete update opkg"),
	"factory_reset": N_("fabrică"),
	"hds_webcontrol_setup": N_("interfața web telefon"),
	"cam_setup": N_("card decriptare"),
	"hds_culegere_canale": N_("culegere canal cu canal"),     # numele vechi al „Scanare detaliată”
	# 0.2.6: intrarile fostelor extensii ale imaginii
	"media_player": N_("filme muzică video fișiere stick USB"),
	"hds_poze": N_("imagini fotografii JPG prezentare"),
	"hds_skin_setari": N_("culori paletă temă aspect"),
	# 0.2.6: navigatorul web
	"hds_navigator_web": N_("internet pagini site browser"),
	# 0.3.2: descarcarea subtitrarilor (in imagine, Components/HdsSubtitrariInternet; nu mai e plugin separat)
	"hds_descarcare_subtitrari": N_("subtitrări internet OpenSubtitles subs.ro SubDL conturi chei"),
}

_EXTRA = {}                # inregistreaza(): randurile extensiilor, ca REGISTRU
_VERSIUNE = [0]            # creste la fiecare inregistreaza(), ca indexul sa se refaca
_TR_RO = []
_FISIERE = {}
_INDEX = {"semn": None, "index": None}
_XML_PLUGIN = {}
_INDEX_PLUGIN = {}
_LECTOR_PLUGIN = None
_LECTURA_PLUGIN = None
_REZULTAT_PLUGIN = ()
_RADACINA_PLUGIN = None
_GENERATIE_PLUGIN = 0
_ULTIMA_SCANARE_PLUGIN = 0.0
_CEAS_PLUGIN = None
_CONTEXT_PLUGIN = None
_DESCHIDERI_PLUGIN = []


def _jurnal(text):
	print("[HdsCautaSetari] %s" % text)


def inregistreaza(entryID, randuri):
	"""Randurile ecranului unei extensii, pe entryID-ul intrarii de meniu care il deschide: [(textul randului, setarea
	config sau "", cuvinte sau "")]. Textul e msgid-ul pe care il scrie ecranul prin _()."""
	_EXTRA[entryID] = tuple((str(t), str(s or ""), str(c or "")) for t, s, c in randuri)
	_VERSIUNE[0] += 1


def registru():
	rez = dict(REGISTRU)
	rez.update(_EXTRA)
	return rez


# ------------------------------------------------------------------ texte

_NU_LITERE = re.compile(r"[\W_]+", re.UNICODE)


def normalizeaza(text):
	"""Textul de cautare: litere mici, fara diacritice (ă â î ș ț, s si t cu sedila, si cele din alte limbi), semnele
	devin spatii. „Setări & Sunet” -> „setari sunet”."""
	if not text:
		return ""
	t = unicodedata.normalize("NFKD", str(text).casefold())
	t = "".join(c for c in t if not unicodedata.combining(c))
	return " ".join(x for x in _NU_LITERE.split(t) if x)


def _tr(text):
	"""Traducerea imaginii (builtins._ pus de Components/Language.py); pe PC, textul asa cum e. Un text gol ramane
	gol (gettext ar da antetul fisierului .po)."""
	if not text:
		return text or ""
	try:
		import builtins
		f = builtins.__dict__.get("_")
	except Exception:
		f = None
	if f is None:
		return text
	try:
		return f(text)
	except Exception:
		return text


def traducereRo():
	"""Traducerea romaneasca a imaginii (catalogul enigma2 „ro”), citita o data: textul romanesc se cauta si cand meniul
	e in alta limba (titlurile scrise in engleza in menu.xml au traducerea lor romaneasca)."""
	if _TR_RO:
		return _TR_RO[0]
	f = None
	try:
		import gettext
		from Tools.Directories import resolveFilename, SCOPE_LANGUAGE
		f = gettext.translation("enigma2", resolveFilename(SCOPE_LANGUAGE, ""), languages=["ro"], fallback=True).gettext
	except Exception as eroare:
		_jurnal("catalogul romanesc: %s" % eroare)

	def ro(text):
		if not text or f is None:
			return text or ""
		try:
			return f(text)
		except Exception:
			return text
	_TR_RO.append(ro)
	return ro


def limbaMeniului():
	try:
		from Components.Language import language
		return language.getLanguage()
	except Exception:
		return ""


def _textNod(nod, tr, text):
	"""Numele cu semnul „(netestat)” / „(în lucru)” (Components/HdsStareMeniu.py), ca pe televizor."""
	try:
		from Components import HdsStareMeniu
		return HdsStareMeniu.textNod(nod, tr, text)
	except ImportError:
		return text


# ------------------------------------------------------------------ fisierele si regulile meniului

def caleMeniu():
	if CALE_MENIU:
		return CALE_MENIU
	try:
		from Tools.Directories import resolveFilename, SCOPE_SKIN
		return resolveFilename(SCOPE_SKIN, "menu.xml")
	except Exception:
		return "/usr/share/enigma2/menu.xml"


def caleSetup():
	if CALE_SETUP:
		return CALE_SETUP
	try:
		from enigma import eEnv
		return eEnv.resolve("${datadir}/enigma2/setup.xml")
	except Exception:
		return "/usr/share/enigma2/setup.xml"


def _radacina(cale):
	"""(radacina XML, semnul fisierului); fisierul se citeste din nou numai cand se schimba (menu.xml ~30 KB). ET.parse
	deschide fisierul binar: codarea vine din fisier, nu din locale (receptorul porneste cu locale C)."""
	try:
		semn = os.path.getmtime(cale)
	except OSError:
		semn = None
	vechi = _FISIERE.get(cale)
	if vechi is not None and vechi[0] == semn:
		return vechi[1], semn
	try:
		radacina = ET.parse(cale).getroot()
	except Exception as eroare:
		_jurnal("nu pot citi %s: %s" % (cale, eroare))
		radacina = None
	_FISIERE[cale] = (semn, radacina)
	return radacina, semn


def nivelUtilizator(config):
	"""config.usage.setup_level.index, ca in Menu.py (0 simplu, 1 intermediar, 2 expert)."""
	try:
		return int(config.usage.setup_level.index)
	except Exception:
		return 0


def _greutate(nod):
	try:
		return int(nod.get("weight", 50))
	except (TypeError, ValueError):
		return 50


def _nivelNod(nod):
	try:
		return int(nod.get("level", 0))
	except (TypeError, ValueError):
		return 0


def cerintaMeniu(nume, SystemInfo):
	"""requires= din menu.xml, ca Menu.addItem / addMenu (cu „!” in fata: ascunsa cand exista)."""
	if not nume:
		return True
	if nume[0] == "!":
		return not SystemInfo.get(nume[1:], False)
	return bool(SystemInfo.get(nume, False))


def cerintaSetup(nume, SystemInfo):
	"""requires= din setup.xml, ca Setup.addItems: SystemInfo.get(nume, False), fara „!”."""
	return not nume or bool(SystemInfo.get(nume, False))


def copiiVizibili(nod, nivel, SystemInfo):
	"""Copiii unui <menu>, ca in Menu.__init__: <item> numai cu level <= nivel, requires= indeplinit; ordinea dupa
	weight (sortare stabila)."""
	copii = []
	for x in nod:
		if x.tag == "item":
			if _nivelNod(x) <= nivel and cerintaMeniu(x.get("requires"), SystemInfo):
				copii.append(x)
		elif x.tag == "menu" and cerintaMeniu(x.get("requires"), SystemInfo):
			copii.append(x)
	copii.sort(key=_greutate)
	return copii


def tinta(nod):
	"""Ce deschide o intrare din menu.xml: {"fel": "ecran", "modul", "ecran", "argumente"} (argumentele citite cu
	ast.literal_eval, None daca nu sunt valori simple), {"fel": "setup", "id"}, {"fel": "cod"} sau None."""
	if nod is None:
		return None
	for x in nod:
		if x.tag == "screen":
			modul = x.get("module") or ""
			ecran = x.get("screen") or modul
			text = (x.text or "").strip()
			argumente = ()
			if text:
				try:
					argumente = ast.literal_eval("(" + text + ",)")
				except (ValueError, SyntaxError):
					argumente = None
			return {"fel": "ecran", "modul": modul, "ecran": ecran, "argumente": argumente}
		if x.tag == "code":
			return {"fel": "cod"}
		if x.tag == "setup":
			return {"fel": "setup", "id": x.get("id") or ""}
	return None


def seDeschideDirect(t):
	"""Ecranul se poate deschide din cautare: un <setup>, sau un ecran din Screens cu argumente simple care nu opreste
	si nu reporneste receptorul. Altfel cautarea duce la meniul intrarii."""
	if not t:
		return False
	if t["fel"] == "setup":
		return bool(t.get("id"))
	return bool(t["fel"] == "ecran" and t["argumente"] is not None and t["modul"].isidentifier()
		and t["ecran"].isidentifier() and (t["modul"], t["ecran"]) not in OPRIRI)


# ------------------------------------------------------------------ setarile

def element(cale, config=None):
	"""Setarea pentru textul unui rand („config.av.downmix_ac3”), prin getattr, fara eval; None daca nu exista."""
	parti = (cale or "").strip().split(".")
	if len(parti) < 2 or parti[0] != "config":
		return None
	if config is None:
		try:
			from Components.config import config
		except Exception:
			return None
	obiect = config
	for p in parti[1:]:
		try:
			if p.isidentifier() and not p.startswith("_"):
				obiect = getattr(obiect, p)
				continue
			nod = ast.parse(p, mode="eval").body
			indici = []
			while isinstance(nod, ast.Subscript):
				k = nod.slice
				if not isinstance(k, ast.Constant) or type(k.value) not in (str, int):
					return None
				if isinstance(k.value, str) and not re.fullmatch(r"[A-Za-z0-9_]{1,40}", k.value):
					return None
				if isinstance(k.value, int) and not 0 <= k.value <= 999:
					return None
				indici.append(k.value)
				nod = nod.value
			if not isinstance(nod, ast.Name) or nod.id.startswith("_"):
				return None
			obiect = getattr(obiect, nod.id)
			for k in reversed(indici):
				obiect = obiect[k]
		except Exception:
			return None
	return obiect


def felSetare(el):
	"""'bool', 'alegere', 'numar', 'glisor', 'cifre' (setarile simple), 'text' (restul) sau None (ConfigNothing), dupa
	numele claselor din config.py, ca setari_web._fel."""
	clase = [c.__name__ for c in type(el).__mro__]
	if "ConfigElement" not in clase or "ConfigNothing" in clase:
		return None
	if "ConfigBoolean" in clase:
		return "bool"
	if "ConfigSelection" in clase:
		return "alegere"
	if "ConfigSlider" in clase:
		return "glisor"
	if "ConfigInteger" in clase and "ConfigPIN" not in clase:
		return "numar"
	if "ConfigNumber" in clase:
		return "cifre"
	return "text"


def valoare(intrare, config=None):
	"""Valoarea de acum a randului, cum o arata ecranul (getText), numai la setarile simple; "" altfel. Intreaga: un
	rand care nu incape deruleaza (lib/gui/elabel.h)."""
	if intrare is None or not intrare.setare:
		return ""
	el = element(intrare.setare, config)
	if el is None or (felSetare(el) not in SIMPLE and not any(c.__name__ in ("ConfigText", "ConfigPassword", "ConfigPIN") for c in type(el).__mro__)):
		return ""
	try:
		text = el.getText()
	except Exception:
		return ""
	return str(text if text is not None else "").strip()


class _Necunoscut(Exception):
	pass


_COMPARATII = {
	ast.Eq: lambda a, b: a == b,
	ast.NotEq: lambda a, b: a != b,
	ast.Lt: lambda a, b: a < b,
	ast.LtE: lambda a, b: a <= b,
	ast.Gt: lambda a, b: a > b,
	ast.GtE: lambda a, b: a >= b,
	ast.In: lambda a, b: a in b,
	ast.NotIn: lambda a, b: a not in b,
}


def _evalueaza(nod, config):
	if isinstance(nod, ast.Constant):
		return nod.value
	if isinstance(nod, ast.Name):
		if nod.id == "config":
			return config
		raise _Necunoscut(nod.id)
	if isinstance(nod, ast.Attribute):
		if nod.attr.startswith("_"):
			raise _Necunoscut(nod.attr)
		return getattr(_evalueaza(nod.value, config), nod.attr)
	if isinstance(nod, ast.Subscript):
		k = nod.slice
		if not isinstance(k, ast.Constant) or type(k.value) not in (str, int):
			raise _Necunoscut("indice")
		if isinstance(k.value, int) and not 0 <= k.value <= 999:
			raise _Necunoscut("indice")
		if isinstance(k.value, str) and not re.fullmatch(r"[A-Za-z0-9_]{1,40}", k.value):
			raise _Necunoscut("indice")
		return _evalueaza(nod.value, config)[k.value]
	if isinstance(nod, (ast.Tuple, ast.List)):
		return [_evalueaza(e, config) for e in nod.elts]
	if isinstance(nod, ast.UnaryOp) and isinstance(nod.op, ast.Not):
		return not _evalueaza(nod.operand, config)
	if isinstance(nod, ast.BoolOp):
		if isinstance(nod.op, ast.And):
			rez = True
			for v in nod.values:
				rez = _evalueaza(v, config)
				if not rez:
					return rez
			return rez
		rez = False
		for v in nod.values:
			rez = _evalueaza(v, config)
			if rez:
				return rez
		return rez
	if isinstance(nod, ast.Compare):
		stanga = _evalueaza(nod.left, config)
		for op, dreapta_nod in zip(nod.ops, nod.comparators):
			f = _COMPARATII.get(type(op))
			if f is None:
				raise _Necunoscut(type(op).__name__)
			dreapta = _evalueaza(dreapta_nod, config)
			if not f(stanga, dreapta):
				return False
			stanga = dreapta
		return True
	raise _Necunoscut(type(nod).__name__)


def conditieAdevarata(expresie, config=None):
	"""conditional= din setup.xml, ca Setup.conditieAdevarata, fara eval: o expresie care nu se poate evalua (sau o
	setare care lipseste) arata randul."""
	if config is None:
		try:
			from Components.config import config
		except Exception:
			return True
	try:
		return bool(_evalueaza(ast.parse((expresie or "").strip(), mode="eval").body, config))
	except Exception:
		return True


def randuriSetup(nodSetup, nivel, SystemInfo, config):
	"""[(nodul <item>, calea setarii)] vizibile pe ecranul Setup, cu regulile lui Setup.addItems."""
	rez = []
	if nodSetup is None:
		return rez
	for x in nodSetup:
		if x.tag != "item" or _nivelNod(x) > nivel:
			continue
		if not cerintaSetup(x.get("requires"), SystemInfo):
			continue
		cond = x.get("conditional")
		if cond and not conditieAdevarata(cond, config):
			continue
		cale = (x.text or "").strip()
		el = element(cale, config)
		if el is None or felSetare(el) is None:
			continue
		rez.append((x, cale))
	return rez


# ------------------------------------------------------------------ indexul

class Intrare(object):
	"""Un rezultat: un meniu („grup”), o intrare de meniu („intrare”), o extensie agatata de un meniu („extensie”) sau
	un rand de setari („rand”). `nod` = nodul din menu.xml al meniului sau al intrarii care deschide ecranul; `parinti` =
	meniurile de deasupra, de la meniul principal pana la cel care o contine."""
	__slots__ = ("cheie", "fel", "titlu", "nume", "drum", "entryID", "setup", "setare", "web", "ajutor", "ordine",
		"nod", "parinti", "_variante", "_cuvTitlu", "_drum", "_cuvDrum", "_alte", "_textSecret", "_configPlugin", "_siPlugin")

	def __init__(self, cheie, fel, titlu, nume, drum, entryID, nod, parinti, ordine, setup="", setare="", web="",
			ajutor="", variante=(), drumuri=(), alte=()):
		self.cheie = cheie
		self.fel = fel
		self.titlu = titlu
		self.nume = nume
		self.drum = list(drum)
		self.entryID = entryID
		self.nod = nod
		self.parinti = list(parinti)
		self.ordine = ordine
		self.setup = setup
		self.setare = setare
		self.web = web
		self.ajutor = ajutor
		v = []
		for t in variante:
			n = normalizeaza(t)
			if n and n not in v:
				v.append(n)
		self._variante = v
		self._cuvTitlu = " ".join(v).split()
		d = []
		for t in drumuri:
			n = normalizeaza(t)
			if n and n not in d:
				d.append(n)
		self._drum = " ".join(d)
		self._cuvDrum = self._drum.split()
		self._alte = " ".join(normalizeaza(t) for t in alte if t)

	def dublura(self):
		"""Cheia dupa care doua rezultate sunt acelasi lucru (randurile aceluiasi ecran de setari sub doua intrari)."""
		if self.fel == "rand" and self.setup:
			return ("setup", self.setup, self.setare)
		# copie="<entryID>" in menu.xml: aceeasi intrare pusa si in locul din meniul standard (Setări > Tunere și scanare,
		# Control parental in Acces condiționat); se arata o singura data, cu drumul gasit primul
		copie = self.nod.get("copie") if self.fel == "intrare" and self.nod is not None else None
		if copie:
			return ("cheie", "m:" + copie)
		return ("cheie", self.cheie)

	def drumText(self, tr=None):
		return SEPARATOR.join(self.drum) if self.drum else (tr or _tr)("Meniu principal")

	def scor(self, cuvinte, intreg):
		"""Cat de bine se potriveste cautarea (cuvintele normalizate), sau None daca un cuvant nu e nicaieri. Drumul
		singur nu ajunge: macar un cuvant trebuie sa fie in titlu, in cuvintele de cautare sau in descriere (altfel
		„setari” ar aduce tot ce sta sub „Setări”)."""
		scor = 0.0
		propriu = False
		for c in cuvinte:
			inDrum = any(w.startswith(c) for w in self._cuvDrum)
			if any(w.startswith(c) for w in self._cuvTitlu):
				# cuvantul si in drum: dintre doua drumuri spre acelasi rand castiga cel care il are
				scor += 6.5 if inDrum else 6
				propriu = True
				continue
			if any(c in v for v in self._variante):
				scor += 4.5 if inDrum else 4
				propriu = True
				continue
			inAlte = c in self._alte
			if inDrum:
				scor += 2
			elif c in self._drum:
				scor += 1.5
			elif inAlte:
				scor += 1
			else:
				return None
			propriu = propriu or inAlte
		if not propriu:
			return None
		if any(v.startswith(intreg) for v in self._variante):
			scor += 5
		if intreg in self._variante:
			scor += 5
		if self.fel != "rand":
			scor += 1          # la potrivire egala, ecranul inaintea randurilor lui
		return scor

	def __repr__(self):
		return "<Intrare %s %r>" % (self.cheie, self.titlu)


class Index(object):
	def __init__(self, intrari):
		self.intrari = list(intrari)
		self._chei = dict((i.cheie, i) for i in self.intrari)

	def __len__(self):
		return len(self.intrari)

	def dupaCheie(self, cheie):
		self._actualizeaza()
		return self._chei.get(cheie)

	def _actualizeaza(self):
		if getattr(self, "_pluginuri", False):
			_actualizeazaPluginuri()
			if _CONTEXT_PLUGIN and _CONTEXT_PLUGIN[0] is self:
				_cuPluginuri(*_CONTEXT_PLUGIN)

	def cauta(self, text, maxim=MAX_REZULTATE):
		"""Rezultatele pentru textul cautat, cele mai potrivite intai (la egalitate, in ordinea din meniu)."""
		self._actualizeaza()
		intreg = normalizeaza((text or "")[:MAX_TEXT])
		if not intreg:
			return []
		cuvinte = intreg.split()
		gasite = []
		for i in self.intrari:
			s = i.scor(cuvinte, intreg)
			if s is not None:
				gasite.append((-s, i.ordine, i))
		gasite.sort(key=lambda x: (x[0], x[1]))
		rez, vazute = [], set()
		for _s, _o, i in gasite:
			d = i.dublura()
			if d in vazute:
				continue
			vazute.add(d)
			rez.append(i)
			if len(rez) >= maxim:
				break
		return rez


def _numeText(nod, setupuri):
	"""Textul scris in menu.xml (msgid-ul); la un <setup> fara text, titlul ecranului din setup.xml (ca Menu.addItem)."""
	text = nod.get("text") or ""
	if not text:
		t = tinta(nod)
		if t and t["fel"] == "setup" and t["id"] in setupuri:
			text = setupuri[t["id"]].get("title", "")
	return text


def _extensiiMeniu(nod):
	"""Extensiile agatate de meniul cu <id val=...> (Menu.__init__): [(nume, id, weight)]."""
	ident = None
	for x in nod:
		if x.tag == "id":
			ident = x.get("val")
			break
	if not ident:
		return []
	try:
		from Components.PluginComponent import plugins
		from Components.HdsPluginuriImagine import meniuriUtilizator
		lista = meniuriUtilizator(plugins, ident)
	except Exception as eroare:
		_jurnal("extensiile meniului %s: %s" % (ident, eroare))
		return []
	rez = []
	for l in lista:
		try:
			rez.append((str(l[0]), str(l[2]), l[3] or 50))
		except (IndexError, TypeError):
			continue
	return rez


def construieste(radMeniu, radSetup, nivel, SystemInfo, config, tr=None, trRo=None, reg=None, extensii=None):
	"""Indexul pentru meniul vazut acum. `extensii(nod)` -> [(nume, id, weight)] (implicit: PluginComponent)."""
	tr = tr or _tr
	trRo = trRo or (lambda t: t)
	reg = registru() if reg is None else reg
	extensii = _extensiiMeniu if extensii is None else extensii
	principal = radMeniu.find("menu") if radMeniu is not None else None
	if principal is None:
		return Index([])
	setupuri = dict((x.get("key"), x) for x in radSetup.findall("setup")) if radSetup is not None else {}
	intrari = []
	nr = [0]

	def ordine():
		nr[0] += 1
		return nr[0]

	def variante(msgid):
		return (tr(msgid), msgid, trRo(msgid))

	def umbla(nod, parinti, drum, drumAlte, adancime):
		# drum: numele traduse (se arata); drumAlte: textele din fisier si traducerile romanesti (se cauta si ele)
		if adancime > MAX_ADANCIME:
			return
		ext = []
		try:
			ext = extensii(nod) or []
		except Exception as eroare:
			_jurnal("extensii: %s" % eroare)
		idExt = set(e[1] for e in ext)
		drumuri = drum + drumAlte
		for x in copiiVizibili(nod, nivel, SystemInfo):
			ident = x.get("entryID") or x.get("key") or ""
			if ident in ID_PROPRII or ident in idExt:
				continue
			msgid = _numeText(x, setupuri)
			nume = tr(msgid)
			numeRo = trRo(msgid)
			titlu = _textNod(x, tr, nume)
			cuvinte = CUVINTE.get(ident, "")
			alte = (tr(cuvinte), cuvinte) if cuvinte else ()
			if x.tag == "menu":
				intrari.append(Intrare("m:" + ident, "grup", titlu, nume, drum, ident, x, parinti, ordine(),
					web=x.get("web") or "", variante=variante(msgid), drumuri=drumuri, alte=alte))
				umbla(x, parinti + [x], drum + [nume], drumAlte + [msgid, numeRo], adancime + 1)
				continue
			t = tinta(x)
			setup = t["id"] if t and t["fel"] == "setup" else ""
			intrari.append(Intrare("m:" + ident, "intrare", titlu, nume, drum, ident, x, parinti, ordine(), setup=setup,
				web=x.get("web") or "", variante=variante(msgid), drumuri=drumuri, alte=alte))
			drumRand = drum + [nume]
			drumuriRand = drumuri + [nume, msgid, numeRo]
			if setup:
				for r, cale in randuriSetup(setupuri.get(setup), nivel, SystemInfo, config):
					m = r.get("text") or ""
					n = tr(m)
					descriere = r.get("description") or ""
					ajutor = tr(descriere) if descriere else ""
					intrari.append(Intrare("s:%s:%s" % (ident, cale), "rand", _textNod(r, tr, n), n, drumRand, ident, x,
						parinti, ordine(), setup=setup, setare=cale, web=x.get("web") or "", ajutor=ajutor,
						variante=variante(m), drumuri=drumuriRand, alte=(ajutor, trRo(descriere) if descriere else "")))
			for k, (m, cale, cuv) in enumerate(reg.get(ident, ())):
				n = tr(m)
				intrari.append(Intrare("r:%s:%d" % (ident, k), "rand", n, n, drumRand, ident, x, parinti, ordine(),
					setare=cale, web=x.get("web") or "", variante=variante(m), drumuri=drumuriRand,
					alte=(tr(cuv), cuv) if cuv else ()))
		for nume, ident, _greut in ext:
			intrari.append(Intrare("e:%s:%s" % (nod.get("key") or "", ident), "extensie", nume, nume, drum, ident, None,
				parinti, ordine(), variante=(nume,), drumuri=drumuri))

	umbla(principal, [principal], [], [], 0)
	return Index(intrari)


def _instantaneu(radMeniu, radSetup, SystemInfo, config):
	"""Ce poate ascunde sau arata randuri fara ca fisierele sa se schimbe: SystemInfo-ul numit in requires= si
	rezultatul fiecarui conditional=."""
	nume, conditii = set(), []
	for rad in (radMeniu, radSetup):
		if rad is None:
			continue
		for x in rad.iter():
			r = x.get("requires")
			if r:
				nume.add(r.lstrip("!"))
			c = x.get("conditional")
			if c:
				conditii.append(c)
	return (tuple((n, bool(SystemInfo.get(n, False))) for n in sorted(nume)),
		tuple(conditieAdevarata(c, config) for c in conditii))


def calePluginuri():
	if CALE_PLUGINURI:
		return CALE_PLUGINURI
	try:
		from Tools.Directories import resolveFilename, SCOPE_PLUGINS
		return resolveFilename(SCOPE_PLUGINS)
	except Exception:
		return "/usr/lib/enigma2/python/Plugins"


def _fisierPlugin(plugin, radacina):
	# Numai cai instalate sub radacina pluginurilor, fara legaturi in afara ei.
	parti = plugin.split("/")
	if len(parti) != 2 or not all(_NUME_PLUGIN.fullmatch(p) for p in parti):
		return None
	baza = os.path.realpath(radacina)
	cale = os.path.realpath(os.path.join(baza, *parti, "setup.xml"))
	try:
		return cale if os.path.commonpath((baza, cale)) == baza else None
	except ValueError:
		return None


def _xmlPlugin(cale):
	# Citire si arbore limitate; declaratiile de entitati sunt respinse inainte de parsare.
	try:
		st = os.stat(cale)
		semn = (st.st_mtime_ns, st.st_size, st.st_ino)
		vechi = _XML_PLUGIN.get(cale)
		if vechi is not None and vechi[0] == semn:
			return vechi[1]
		rad = None
		if st.st_size <= MAX_XML_PLUGIN:
			with open(cale, "rb") as f:
				date = f.read(MAX_XML_PLUGIN + 1)
			# Eliminarea NUL prinde si declaratiile in UTF-16 sau UTF-32.
			control = date.replace(b"\x00", b"").upper()
			if len(date) <= MAX_XML_PLUGIN and b"<!DOCTYPE" not in control and b"<!ENTITY" not in control:
				rad = ET.fromstring(date)
				for nr, _nod in enumerate(rad.iter()):
					if nr >= MAX_NODURI_PLUGIN:
						rad = None
						break
		_XML_PLUGIN[cale] = (semn, rad)
		return rad
	except (ValueError, LookupError, ET.ParseError):
		_XML_PLUGIN[cale] = (semn, None)
		return None
	except OSError:
		_XML_PLUGIN.pop(cale, None)
		return None


class _EcranPlugin:
	# Snapshot XML si texte gettext; nu contine obiecte Enigma2.
	def __init__(self, nod, domeniu):
		from gettext import dgettext
		self.nod = nod
		self.traduceri = {}
		for x in nod.iter():
			for atribut in ("title", "text", "description"):
				text = x.get(atribut)
				if text and text not in self.traduceri:
					try:
						self.traduceri[text] = dgettext(domeniu, text)
					except Exception:
						self.traduceri[text] = text

	def get(self, *args):
		return self.nod.get(*args)

	def __iter__(self):
		return iter(self.nod)


def _ecranePlugin(radacina):
	# Numai fisiere: niciun plugin importat sau chemat, nici pentru metadate.
	rez, vazute, identificatori = [], set(), set()
	buget = MAX_DOSARE_PLUGIN
	octeti = MAX_XML_TOTAL_PLUGIN
	try:
		categorii = sorted(os.listdir(radacina))
	except OSError:
		categorii = []
	for cat in categorii[:MAX_DOSARE_PLUGIN]:
		if not _NUME_PLUGIN.fullmatch(cat):
			continue
		try:
			nume = sorted(os.listdir(os.path.join(radacina, cat)))
		except OSError:
			continue
		for n in nume[:buget]:
			buget -= 1
			cale = _fisierPlugin(cat + "/" + n, radacina)
			if not cale or not os.path.isfile(cale):
				continue
			try:
				marime = os.path.getsize(cale)
			except OSError:
				continue
			if marime > MAX_XML_PLUGIN or marime > octeti:
				continue
			octeti -= marime
			vazute.add(cale)
			rad = _xmlPlugin(cale)
			if rad is None:
				continue
			for x in rad.findall("setup"):
				cheie = x.get("key") or ""
				ident = "%s/%s/%s" % (cat, n, cheie)
				if not _NUME_PLUGIN.fullmatch(cheie) or len(ident) > 80 or ident in identificatori:
					continue
				if any((y.text or "").strip().startswith("config.") for y in x.iter("item")):
					identificatori.add(ident)
					rez.append((ident, cat + "/" + n, _EcranPlugin(x, n)))
				if len(rez) >= MAX_PLUGINURI:
					break
			if len(rez) >= MAX_PLUGINURI:
				break
		if len(rez) >= MAX_PLUGINURI or buget <= 0:
			break
	for cale in list(_XML_PLUGIN):
		if cale not in vazute:
			del _XML_PLUGIN[cale]
	return rez


def _lectorPlugin():
	global _LECTOR_PLUGIN
	if _LECTOR_PLUGIN is None:
		from concurrent.futures import ThreadPoolExecutor
		_LECTOR_PLUGIN = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hds-cauta-xml")
	return _LECTOR_PLUGIN


def _publicaPluginuri():
	import time
	# Numai firul principal publica datele si atinge obiectele config.
	global _LECTURA_PLUGIN, _REZULTAT_PLUGIN, _ULTIMA_SCANARE_PLUGIN
	if _LECTURA_PLUGIN is None:
		return
	viitor, generatie = _LECTURA_PLUGIN
	if not viitor.done():
		if _CEAS_PLUGIN is not None:
			_CEAS_PLUGIN.start(50, True)
		return
	_LECTURA_PLUGIN = None
	try:
		rezultat = viitor.result()
	except Exception:
		rezultat = ()
	if generatie != _GENERATIE_PLUGIN:
		_actualizeazaPluginuri(fortat=True)
		return
	if generatie == _GENERATIE_PLUGIN:
		_REZULTAT_PLUGIN = tuple(rezultat)
		_ULTIMA_SCANARE_PLUGIN = time.monotonic()
		if _CONTEXT_PLUGIN:
			_cuPluginuri(*_CONTEXT_PLUGIN)


def _actualizeazaPluginuri(fortat=False):
	import time
	global _LECTURA_PLUGIN, _RADACINA_PLUGIN, _GENERATIE_PLUGIN
	global _ULTIMA_SCANARE_PLUGIN, _REZULTAT_PLUGIN, _CEAS_PLUGIN
	radacina = calePluginuri()
	if radacina != _RADACINA_PLUGIN:
		_RADACINA_PLUGIN = radacina
		_GENERATIE_PLUGIN += 1
		_REZULTAT_PLUGIN = ()
		_ULTIMA_SCANARE_PLUGIN = 0.0
	_publicaPluginuri()
	acum = time.monotonic()
	if _LECTURA_PLUGIN is not None or (not fortat and acum - _ULTIMA_SCANARE_PLUGIN < 2.0):
		return
	_ULTIMA_SCANARE_PLUGIN = acum
	_LECTURA_PLUGIN = (_lectorPlugin().submit(_ecranePlugin, radacina), _GENERATIE_PLUGIN)
	if _CEAS_PLUGIN is None:
		try:
			from enigma import eTimer
			_CEAS_PLUGIN = eTimer()
			_CEAS_PLUGIN.callback.append(_publicaPluginuri)
		except (ImportError, AttributeError):
			pass
	if _CEAS_PLUGIN is not None:
		_CEAS_PLUGIN.start(50, True)


def _includePlugin(nod, config, SystemInfo, conditionale=True):
	for cerinta in (nod.get("requires") or "").split(";"):
		cerinta = cerinta.strip()
		if not cerinta:
			continue
		negat = cerinta.startswith("!")
		nume = cerinta[1:].strip() if negat else cerinta
		if nume.startswith("config."):
			el = element(nume, config)
			if el is None:
				return False
			v = getattr(el, "value", None)
			activ = bool(v) and str(v).lower() not in ("0", "disable", "false", "no", "off")
		else:
			activ = bool(SystemInfo.get(nume, False))
		if activ == negat:
			return False
	cond = nod.get("conditional")
	return not conditionale or not cond or conditieAdevarata(cond, config)


def _setariWebPlugin(nod, config, SystemInfo):
	# Web-ul arata toate ramurile, cu limita comuna de 80 de randuri.
	# Legaturile duc numai la randurile cuprinse in limita si in gramatica lui.
	vazute = set()
	stiva = [iter(nod)]
	while stiva:
		x = next(stiva[-1], None)
		if x is None:
			stiva.pop()
		elif x.tag == "if":
			stiva.append(iter(x))
		elif x.tag == "item" and _includePlugin(x, config, SystemInfo, conditionale=False):
			cale = (x.text or "").strip()
			if not cale.startswith("config.") or not all(_PARTE_PLUGIN.fullmatch(p) for p in cale.split(".")[1:]):
				continue
			el = element(cale, config)
			if el is not None and felSetare(el) is not None:
				vazute.add(cale)
				if len(vazute) >= MAX_RANDURI_PLUGIN:
					break
	return vazute


def _randuriPlugin(nod, config, SystemInfo, adancime=0):
	# Ca Setup.addIf, fara expresii arbitrare sau acces la starea ecranului.
	if adancime > MAX_ADANCIME:
		return
	for x in nod:
		if x.tag == "if":
			activ = _includePlugin(x, config, SystemInfo)
			gasit = activ
			for copil in x:
				if copil.tag == "elif":
					activ = not gasit and _includePlugin(copil, config, SystemInfo)
					gasit = gasit or activ
				elif copil.tag == "else":
					activ, gasit = not gasit, True
				elif activ:
					yield from _randuriPlugin([copil], config, SystemInfo, adancime + 1)
		elif x.tag == "item" and _includePlugin(x, config, SystemInfo):
			cale = (x.text or "").strip()
			el = element(cale, config)
			if el is not None and felSetare(el) is not None:
				yield x, cale


def _cuPluginuri(baza, config, SystemInfo, tr, trRo):
	from hashlib import sha256
	ecrane = []
	for ident, plugin, nod in _REZULTAT_PLUGIN:
		randuri, vazute = [], set()
		web = _setariWebPlugin(nod, config, SystemInfo)
		for x, cale in _randuriPlugin(nod, config, SystemInfo):
			if cale in vazute or cale not in web:
				continue
			vazute.add(cale)
			randuri.append((x, cale))
			if len(randuri) >= MAX_RANDURI_PLUGIN:
				break
		if randuri:
			ecrane.append((ident, plugin, nod, randuri))
	if not hasattr(baza, "_intrariImagine"):
		baza._intrariImagine = list(baza.intrari)
	baza._pluginuri = True
	if not ecrane:
		if not getattr(baza, "_arePluginuri", False):
			return baza
		baza._arePluginuri = False
		baza.intrari = list(baza._intrariImagine)
		baza._chei = {i.cheie: i for i in baza.intrari}
		_INDEX_PLUGIN.clear()
		return baza
	semn = (id(baza), tuple((ident, id(nod), tuple((id(x), cale) for x, cale in randuri))
		for ident, plugin, nod, randuri in ecrane))
	if _INDEX_PLUGIN.get("semn") == semn:
		return _INDEX_PLUGIN["index"]
	intrari = list(baza._intrariImagine)
	for ident, plugin, nod, randuri in ecrane:
		domeniu = plugin.split("/")[-1]

		def tradu(text):
			if not text:
				return ""
			try:
				t = nod.traduceri.get(text, text)
			except Exception:
				t = text
			return t if t != text else tr(text)

		titlu = tradu(nod.get("title") or "")
		drum = [tr(N_("Pluginuri")), domeniu, titlu]
		# Tinta XML proprie pastreaza pluginul; niciun cod de plugin executat.
		tintaPlugin = ET.Element("item", {"hdsPlugin": plugin})
		for x, cale in randuri:
			m = x.get("text") or ""
			nume = tradu(m)
			date = x.get("data")
			if date and nume.count("%s") == len(date.split(",")):
				try:
					nume = nume % tuple(date.split(","))
				except (ValueError, TypeError):
					pass
			ajutor = tradu(x.get("description") or "")
			cheie = "p:%s:%s" % (ident, sha256(cale.encode("utf-8")).hexdigest()[:24])
			intrari.append(Intrare(cheie, "rand", _textNod(x, tradu, nume), nume,
				drum, ident, tintaPlugin, [], len(intrari) + 1, setup=ident, setare=cale, ajutor=ajutor,
				variante=(nume, m, trRo(m)), drumuri=drum, alte=(ajutor,)))
			intrari[-1]._textSecret = m
			intrari[-1]._configPlugin = config
			intrari[-1]._siPlugin = SystemInfo
	baza._arePluginuri = True
	baza.intrari = intrari
	baza._chei = {i.cheie: i for i in intrari}
	_INDEX_PLUGIN.update(semn=semn, index=baza)
	return baza


def index(config=None, SystemInfo=None, limba=None, tr=None, trRo=None, fortat=False):
	"""Indexul de acum, refacut numai cand s-a schimbat ceva din ce il face (vezi capul fisierului)."""
	if config is None:
		from Components.config import config
	if SystemInfo is None:
		try:
			from Components.SystemInfo import SystemInfo
		except Exception:
			SystemInfo = {}
	radM, semnM = _radacina(caleMeniu())
	radS, semnS = _radacina(caleSetup())
	nivel = nivelUtilizator(config)
	if limba is None:
		limba = limbaMeniului()
	semn = (caleMeniu(), caleSetup(), limba, nivel, semnM, semnS, _instantaneu(radM, radS, SystemInfo, config),
		_VERSIUNE[0])
	if not fortat and _INDEX["index"] is not None and _INDEX["semn"] == semn:
		idx = _INDEX["index"]
	else:
		idx = construieste(radM, radS, nivel, SystemInfo, config, tr=tr, trRo=trRo or traducereRo())
		_INDEX.update(semn=semn, index=idx)
	global _CONTEXT_PLUGIN
	_actualizeazaPluginuri(fortat=fortat)
	_CONTEXT_PLUGIN = (idx, config, SystemInfo, tr or _tr, trRo or traducereRo())
	return _cuPluginuri(*_CONTEXT_PLUGIN)


def uita():
	"""Indexul se face din nou la cautarea urmatoare."""
	global _GENERATIE_PLUGIN, _ULTIMA_SCANARE_PLUGIN, _REZULTAT_PLUGIN, _CONTEXT_PLUGIN
	_INDEX.update(semn=None, index=None)
	_INDEX_PLUGIN.clear()
	_GENERATIE_PLUGIN += 1
	_ULTIMA_SCANARE_PLUGIN = 0.0
	_REZULTAT_PLUGIN = ()
	_CONTEXT_PLUGIN = None


# ------------------------------------------------------------------ deschiderea pe televizor

def _vizibilPlugin(intrare, ecrane, config, si):
	for ident, plugin, nod in ecrane:
		if ident == intrare.setup:
			return intrare.setare in _setariWebPlugin(nod, config, si) and any(
				cale == intrare.setare for _x, cale in _randuriPlugin(nod, config, si))
	return False


def _setupPlugin(nod, configurare, si):
	# Adaptor local: Setup ramane neschimbat pentru restul imaginii.
	from Screens.Setup import Setup

	class HdsSetupPlugin(Setup):
		def __init__(self, sesiune, setup, plugin=None, PluginLanguageDomain=None):
			self.hdsPlugin = plugin
			# Fara plugin=, constructorul nu reciteste XML sau catalogul gettext.
			Setup.__init__(self, sesiune, setup)
			# Cheile pluginului nu activeaza actiuni speciale ale ecranelor imaginii.
			self.setup = plugin + "/" + setup
			self.pluginLanguageDomain = PluginLanguageDomain
			if type(self).__name__ in self.skinName:
				self.skinName.remove(type(self).__name__)

		def refill(self, randuri):
			self.plugin = self.hdsPlugin
			self.xmlPlugin = ET.Element("setupxml")
			self.xmlPlugin.append(nod.nod)
			def tradu(text):
				t = nod.traduceri.get(text, text)
				return t if t != text else _tr(text)
			self.traducere = tradu
			skin = nod.get("skin")
			if skin and skin not in self.skinName:
				self.skinName.insert(0, skin)
			self.pendingHeading = None
			self.addItems(randuri, nod)
			self.setup_title = nod.get("title", "")

		def includeElement(self, x):
			if x.get("conditional"):
				self.conditionale = True
			return _includePlugin(x, configurare, si)

		def addIf(self, randuri, x):
			adancime = getattr(self, "hdsAdancime", 0)
			if adancime >= MAX_ADANCIME:
				return
			self.hdsAdancime = adancime + 1
			try:
				Setup.addIf(self, randuri, x)
			finally:
				self.hdsAdancime = adancime

		def addItems(self, randuri, parinte):
			# Setup primeste numai cai config validate, niciodata expresii de plugin.
			for x in parinte:
				if x.tag == "if":
					self.addIf(randuri, x)
				elif x.tag == "item":
					cale = (x.text or "").strip()
					if cale and (not cale.startswith("config.") or
						not all(_PARTE_PLUGIN.fullmatch(p) for p in cale.split(".")[1:])):
						continue
					if cale and element(cale, configurare) is None:
						continue
					copie = ET.Element("item", dict(x.attrib))
					copie.text = cale
					# Nivelul nu ascunde setari in ecranele pluginurilor.
					copie.set("level", "0")
					Setup.addItems(self, randuri, [copie])

	return HdsSetupPlugin


class DeschiderePlugin:
	# Controlul ramane pe firul principal; viitorul citeste numai XML.
	def __init__(self, sesiune, intrare, config, deschide, laDeschidere):
		from enigma import eTimer
		self.sesiune, self.intrare, self.config = sesiune, intrare, config
		self.ecran = getattr(sesiune, "current_dialog", None)
		self.generatie = _GENERATIE_PLUGIN
		self.deschide, self.laDeschidere = deschide, laDeschidere
		self.terminat, self.rezultat = False, None
		self.viitor = _lectorPlugin().submit(_ecranePlugin, calePluginuri())
		self.ceas = eTimer()
		self.ceas.callback.append(self.actualizeaza)
		_DESCHIDERI_PLUGIN.append(self)
		self.ceas.start(50, True)

	def anuleaza(self, *args):
		self.terminat = True
		self.viitor.cancel()
		self.ceas.stop()
		if self in _DESCHIDERI_PLUGIN:
			_DESCHIDERI_PLUGIN.remove(self)
		self.deschide = self.laDeschidere = None

	def actualizeaza(self):
		if self.terminat:
			return
		if not self.viitor.done():
			self.ceas.start(50, True)
			return
		try:
			ecrane = self.viitor.result()
			if (self.generatie == _GENERATIE_PLUGIN
				and getattr(self.sesiune, "current_dialog", None) is self.ecran
				and _vizibilPlugin(self.intrare, ecrane, self.config,
					getattr(self.intrare, "_siPlugin", {}))):
				nod = next(n for ident, plugin, n in ecrane if ident == self.intrare.setup)
				self.rezultat = self.deschide(nod)
		except Exception:
			self.rezultat = None
		callback = self.laDeschidere
		self.anuleaza()
		if callback is not None:
			callback(self.rezultat)


def poateDeschide(intrare):
	"""(se deschide ecranul insusi?, felul): „ecran” (ecranul intrarii, cu randul ales), „meniu” (meniul care o
	contine, cu cursorul pe ea: <code>, oprirea, extensiile) sau „submeniu” (un meniu)."""
	if intrare.nod is not None and intrare.nod.get("hdsPlugin"):
		_actualizeazaPluginuri()
		return _vizibilPlugin(intrare, _REZULTAT_PLUGIN,
			getattr(intrare, "_configPlugin", None), getattr(intrare, "_siPlugin", {})), "ecran"
	if intrare.fel == "grup":
		return True, "submeniu"
	if intrare.fel == "extensie":
		return False, "meniu"
	if seDeschideDirect(tinta(intrare.nod)):
		return True, "ecran"
	return False, "meniu"


def gasesteRandul(dlg, intrare, config=None):
	"""Indexul randului in lista de setari a ecranului deschis (self["config"], ConfigList) sau -1: dupa setare
	(acelasi obiect), apoi dupa textul randului (fara semnul starii, fara majuscule si diacritice)."""
	try:
		randuri = list(dlg["config"].list or [])
	except Exception:
		return -1
	el = element(intrare.setare, config) if intrare.setare else None
	if el is not None:
		for i, r in enumerate(randuri):
			if len(r) > 1 and r[1] is el:
				return i
	cautat = normalizeaza(intrare.nume)
	if cautat:
		for i, r in enumerate(randuri):
			if r and isinstance(r[0], str):
				eticheta = normalizeaza(r[0])
				if eticheta == cautat or eticheta.startswith(cautat + " "):
					return i
	return -1


def pozitioneaza(dlg, intrare, config=None, incercari=4, pas_ms=250):
	"""Cursorul pe randul gasit. Ecranele care isi umplu lista mai tarziu (dupa un ceas) se mai incearca de cateva ori."""
	i = gasesteRandul(dlg, intrare, config)
	if i >= 0:
		try:
			dlg["config"].setCurrentIndex(i)
			return True
		except Exception as eroare:
			_jurnal("cursorul pe rand: %s" % eroare)
			return False
	if incercari <= 0:
		return False
	try:
		from enigma import eTimer
	except ImportError:
		return False
	ceas = eTimer()
	ramase = [incercari]

	def dinNou():
		j = gasesteRandul(dlg, intrare, config)
		if j >= 0:
			try:
				dlg["config"].setCurrentIndex(j)
			except Exception:
				pass
			return
		ramase[0] -= 1
		if ramase[0] > 0:
			ceas.start(pas_ms, True)
	ceas.callback.append(dinNou)
	dlg.hdsCautaCeas = ceas    # tinut in viata cat dialogul
	ceas.start(pas_ms, True)
	return False


def alegeInMeniu(dlg, entryID):
	"""Cursorul meniului (Screens/Menu.py, sursa "menu") pe intrarea cu entryID-ul dat. Meniul stie singur sa o aleaga
	(Menu.alegeIntrarea, si in modul dale, unde randurile listei au cate trei intrari); altfel, dupa randurile listei."""
	alege = getattr(dlg, "alegeIntrarea", None)
	if alege is not None:
		try:
			return bool(alege(entryID))
		except Exception as eroare:
			_jurnal("cursorul in meniu: %s" % eroare)
			return False
	try:
		lista = dlg["menu"].list
		for i, x in enumerate(lista):
			if len(x) > 2 and x[2] == entryID:
				dlg["menu"].setIndex(i)
				return True
	except Exception as eroare:
		_jurnal("cursorul in meniu: %s" % eroare)
	return False


def _salveazaLaInchidere(intrare):
	noduri = list(intrare.parinti)
	if intrare.fel == "grup" and intrare.nod is not None:
		noduri.append(intrare.nod)
	return any(n.get("flushConfigOnClose") for n in noduri)


def deschide(sesiune, intrare, laInchidere=None, config=None, laDeschidere=None):
	"""Deschide rezultatul. Pentru pluginuri intoarce o DeschiderePlugin asincrona.
	La inchidere pastreaza salvarea meniului si callbackul laInchidere.
	laDeschidere primeste dialogul sau None dupa verificarea XML pe disc.
	"""
	salveaza = _salveazaLaInchidere(intrare)

	def gata(*rezultat):
		if salveaza:
			try:
				from Components.config import configfile
				configfile.save()
			except Exception as eroare:
				_jurnal("salvarea setarilor: %s" % eroare)
		if laInchidere is not None:
			laInchidere(*rezultat)

	merge, fel = poateDeschide(intrare)
	if intrare.nod is not None and intrare.nod.get("hdsPlugin"):
		if not merge:
			return None
		if len(_DESCHIDERI_PLUGIN) >= 4:
			return None
		config = config if config is not None else getattr(intrare, "_configPlugin", None)

		def deschidePlugin(nod):
			plugin = intrare.nod.get("hdsPlugin")
			ecran = _setupPlugin(nod, config, getattr(intrare, "_siPlugin", {}))
			dlg = sesiune.openWithCallback(gata, ecran, intrare.setup.split("/")[-1], plugin=plugin,
				PluginLanguageDomain=plugin.split("/")[-1])
			if dlg is not None:
				pozitioneaza(dlg, intrare, config)
			return dlg

		return DeschiderePlugin(sesiune, intrare, config, deschidePlugin, laDeschidere)
	if fel == "submeniu":
		from Screens.Menu import Menu
		return sesiune.openWithCallback(gata, Menu, intrare.nod)
	if not merge:
		from Screens.Menu import Menu
		dlg = sesiune.openWithCallback(gata, Menu, intrare.parinti[-1])
		if dlg is not None:
			alegeInMeniu(dlg, intrare.entryID)
		return dlg
	t = tinta(intrare.nod)
	if t["fel"] == "setup":
		from Screens.Setup import Setup
		dlg = sesiune.openWithCallback(gata, Setup, t["id"])
	else:
		import importlib
		modul = importlib.import_module("Screens." + t["modul"])
		dlg = sesiune.openWithCallback(gata, getattr(modul, t["ecran"]), *t["argumente"])
	if dlg is not None and intrare.fel == "rand":
		pozitioneaza(dlg, intrare, config)
	return dlg
