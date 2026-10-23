# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# lansator.py: pornirea, predarea ecranului si a telecomenzii, si oprirea navigatorului web (/usr/bin/hds-navigator,
# pachetul separat hds-navigator, WPE WebKit). Nimic de aici nu ruleaza la pornirea receptorului: modulul se importa
# abia la prima chemare, iar procesul navigatorului traieste numai cat e deschis.
#
# Protocolul cu lansatorul (hds-navigator.c): comenzi pe intrarea standard, cate una pe rand; randuri „HDS-NAV ...” pe
# iesire. Textele din pagina si cele scrise de om trec numai in base64 si nu se scriu in jurnal (nici adresele).
#
# Predarea ecranului:
#   1. lansatorul porneste --ascuns: deseneaza in memorie, enigma2 arata ecranul de progres;
#   2. la „PRIMA-PAGINA”: eRCInput.lock(), fbClass.lock(), apoi „arata” (lansatorul apuca /dev/input/event* si scrie
#      pe /dev/fb0);
#   3. o fereastra a enigma2 peste navigator (tastatura, intrebari, meniul navigatorului): „ascunde”, se asteapta
#      „ASCUNS” (lansatorul a eliberat telecomanda), apoi unlock pe amandoua si redesenarea; la sfarsit iar lock si
#      „arata”;
#   4. la inchidere: „iesire”, apoi SIGTERM si SIGKILL pe grupul de procese daca nu iese; lacatele se ridica la
#      sfarsitul procesului (sau imediat, daca a cazut).
# Tastele care ajung la enigma2 cat navigatorul e pe ecran (telecomanda din interfata web, tastatura emulatorului)
# se prind cu o legatura pe toate tastele si se trimit lansatorului („tasta <cod> <1|0|2>”).
#
# Stratul lansatorului: peste pagina lansatorul deseneaza singur chenarul pe selectie (--chenar, setarea „Chenarul pe
# selecție”) si textele de ajutor de jos (TEXTE_STRAT, traduse aici si date cu --text cheie=base64), fiindca enigma2 nu
# poate desena cat navigatorul are ecranul. Scrisul: OK pe un camp de text sau TEXT deschid tastatura enigma2.
# Indicatorul (mouse din sageti): ALBASTRU sau meniul navigatorului il pornesc si il opresc (randul „INDICATOR 1|0”).
# Stilul chenarului (0.2.7): culoarea, forma, grosimea si pulsul alese de om pleaca la pornire ca
# --chenar-culoare/-forma/-grosime/-puls, numai cele care difera de fabrica (cu setarile din fabrica linia de comanda e
# cea de dinainte), iar cat navigatorul e deschis cu comanda "chenar <0|1> <culoare> <forma> <grosime> <puls>"
# (schimbaChenar: dupa Setari navigator din meniul navigatorului si dupa pagina web /navigator); raspunsul "CHENAR ...".
#
# Fara ecran de tip framebuffer (emulatorul SDL: fbClass.getInstance() e None) nu se pune niciun lacat; lansatorul
# deseneaza in memorie, iar toate tastele trec prin legatura de mai sus.
#
# MOD_HBBTV (aplicatia HbbTV a canalului, pornita la ROSU de Components/HdsHbbtvPornire.py): lansatorul porneste cu
# --hbbtv (fundal transparent, User-Agent-ul cu partea HbbTV, tastele ca la HbbTV) si fara --intrare, deci fara
# EVIOCGRAB; enigma2 nu pune eRCInput.lock, numai lacatul pe fb0, iar tastele le imparte ascultatorul (HdsHbbtvPornire),
# nu legatura de aici. Ferestrele cerute de pagina (alert, confirm, <select>, autentificare) se refuza: peste aplicatie
# nu se deschide nimic. Setarile marirea si literele nu se aplica (aplicatiile sunt facute pe 1280x720). Cu
# hbbtv["utilizator"] lansatorul coboara pe acel utilizator fara root dupa deschiderea lui /dev/fb0 (--utilizator).
# Stratul HbbTV: lansatorul pune in pagina obiectele OIPF (hds-hbbtv.js) si spune "HBBTV strat 1"; atunci
# prima pagina ramane ascunsa (aplicatia porneste ascunsa, ETSI TS 102 796 cap. 6.2.2.4) pana cand ascultatorul cere
# reia() la Application.show(). Randurile "HBBTV <comanda> ..." (cererile paginii) merg la ascultator (laHbbtv); starea
# spre pagina pleaca prin hbbtvParte (tinuta de lansator pentru documentele urmatoare) si hbbtvEv (un eveniment);
# starea de pornire (partile mici) vine cu stare_hbbtv si pleaca pe linia de comanda (--hbbtv-parte). Scriptul stratului
# e cel din acest pachet (CALE_HBBTV_JS, --hbbtv-js), cand exista; altfel cel al navigatorului.
# Din hds-navigator 0.6.0: vizibil(da) ascunde pagina fata de WebKit (aplicatia pornita automat si inca nevazuta
# nu deseneaza); cedeaza() opreste pe loc (opresteAcum) o asemenea aplicatie cand alt navigator vrea locul. Fereastra
# video o muta ascultatorul (HdsHbbtvPornire), nu lansatorul.
#
# MOD_CAM (0.2.8): cand interfata camului cere utilizator si parola inainte de prima pagina si
# ecranul raspunde singur cu datele de pe receptor (intrare_cam.py), continuaIncarcarea() lasa navigatorul ascuns pana la
# prima pagina (ecranul de progres ramane), in loc de reia(), care i-ar da ecranul inainte sa aiba ce arata.
#
# JURNALUL ERORILOR (JURNAL_ERORI, /home/root/logs/hds-navigator.log): la o oprire cu eroare, ultimele randuri ale
# iesirii de erori si ultimele stari HDS-NAV, curatate (curata_rand, stare_scurta), cu codul de iesire si motivul;
# rotit in .1 peste JURNAL_OCTETI_MAX. Se vede in Jurnalele sistemului (televizor si web).
#
# Modulul nu importa enigma2 la incarcare: tot ce tine de enigma2 trece prin Mediu, inlocuit la probele de pe PC.

import base64
import collections
import json
import os
import re
import signal
import time

CALE_LANSATOR = "/usr/bin/hds-navigator"
# libjpeg-turbo, pe care e construit WebKit; ldconfig (rulat de scripturile de instalare ale pachetelor, de pilda la o
# actualizare prin opkg) poate lega libjpeg.so.62 de libjpeg9b.so a producatorului (acelasi SONAME, alta versiune), iar
# navigatorul cade la prima poza JPEG (HbbTV pe SAT.1 Gold). enigma2.sh pune legatura la loc la fiecare
# pornire a interfetei; aici se pune si inaintea fiecarui navigator, pentru timpul dintre o actualizare si repornire.
DOSAR_BIBLIOTECI = "/usr/lib"
LEGATURA_JPEG = "libjpeg.so.62"


def jpegBun(dosar=DOSAR_BIBLIOTECI):
	"""Pune legatura libjpeg.so.62 pe libjpeg-turbo (libjpeg.so.62.<x>, fisier adevarat), daca arata in alta parte.
	True cand a schimbat ceva; nu arunca."""
	try:
		legatura = os.path.join(dosar, LEGATURA_JPEG)
		if not os.path.islink(legatura):
			return False
		bun = None
		for nume in sorted(os.listdir(dosar)):
			cale = os.path.join(dosar, nume)
			if nume.startswith(LEGATURA_JPEG + ".") and os.path.isfile(cale) and not os.path.islink(cale):
				bun = nume
		if bun is None or os.readlink(legatura) == bun:
			return False
		nou = legatura + ".hds-nou"
		if os.path.lexists(nou):
			os.unlink(nou)
		os.symlink(bun, nou)
		os.replace(nou, legatura)
		_jurnal("libjpeg.so.62 pus inapoi pe %s" % bun)
		return True
	except Exception as e:
		_jurnal("libjpeg.so.62: %s" % e.__class__.__name__)
		return False
PREFIX = "HDS-NAV "
PARTI_LINIE = ("app", "canal", "config", "programe", "taste")   # partile starii HbbTV puse pe linia de comanda

# Jurnalul erorilor navigatorului: la o oprire cu eroare (caderea, termenele, blocarea, memoria, pagina neincarcata)
# se scriu ultimele randuri ale iesirii de erori (stderr: WebKit, GLib, randurile HDS-NAV de eroare) si ultimele stari
# HDS-NAV, cu codul de iesire si motivul. Inainte, iesirea de erori se arunca si codul ajungea numai pe /dev/console
# (diagnoza SAT.1 Gold a cerut reluari de mana). Fiecare rand trece prin curata_rand (fara adrese, chei, e-mailuri,
# siruri lungi, IP-uri); adresa paginii nu se scrie niciodata. Fisierul sta in dosarul jurnalelor, deci il arata
# Jurnalele sistemului pe televizor si in interfata web; cel mult JURNAL_OCTETI_MAX, apoi trece in <nume>.1 (unul
# singur vechi), cel mult JURNAL_PE_PORNIRE blocuri de la o pornire a enigma2 (memoria interna).
JURNAL_ERORI = "/home/root/logs/hds-navigator.log"
JURNAL_OCTETI_MAX = 32 * 1024
JURNAL_RANDURI_ERORI = 40
JURNAL_RANDURI_STARI = 20
JURNAL_RAND_MAX = 200
JURNAL_PE_PORNIRE = 30
_jurnal_scrise = [0]

_RE_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_RE_ADRESA = re.compile(r"(?i)\b[a-z][a-z0-9+.-]{1,15}://\S*")
_RE_ADRESA_FARA_BARE = re.compile(r"(?i)\b(?:data|blob|javascript|about):\S+")
_RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_RE_CHEIE = re.compile(r"(?i)\b(token|apikey|api_key|key|pass\w*|parola|secret\w*|auth\w*|cookie\w*|session\w*|sid|jwt)"
	r"(\s*[=:]\s*)\S+")
_RE_PURTATOR = re.compile(r"(?i)\bbearer\s+\S+")
_RE_SIR = re.compile(r"[A-Za-z0-9+/_=-]{24,}")
_RE_IP = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_RE_FEL = re.compile(r"^[A-Z][A-Z0-9-]{0,23}$")
_RE_ARG = re.compile(r"^(?:-?[0-9]{1,7}|[a-z][a-z0-9-]{0,23})$")


def curata_rand(rand, maxim=JURNAL_RAND_MAX):
	"""Un rand pentru jurnalul erorilor, fara ce poate fi personal sau secret: adresele (orice schema://..., data:,
	blob:, javascript:), e-mailurile, valorile dupa token/key/parola/auth/cookie/session (si Bearer), sirurile lungi
	(24 de semne sau mai mult: chei, base64, hex) si adresele IP; caracterele de control devin spatii; cel mult maxim."""
	r = _RE_CONTROL.sub(" ", rand if isinstance(rand, str) else str(rand)).strip()
	r = _RE_ADRESA.sub("<adresa>", r)
	r = _RE_ADRESA_FARA_BARE.sub("<adresa>", r)
	r = _RE_EMAIL.sub("<email>", r)
	r = _RE_CHEIE.sub(lambda m: m.group(1) + m.group(2) + "<ascuns>", r)
	r = _RE_PURTATOR.sub("Bearer <ascuns>", r)
	r = _RE_SIR.sub("<sir>", r)
	r = _RE_IP.sub("<ip>", r)
	return r[:maxim]


def stare_scurta(rand):
	"""Un rand HDS-NAV (fara prefix) pentru jurnal: felul si numai argumentele care sunt numere sau cuvinte mici
	(proces-web, procesor, strat ...); base64 (texte din pagina, adrese) si orice altceva devin "*"."""
	cuv = rand.split(" ")
	fel = cuv[0] if _RE_FEL.match(cuv[0]) else "?"
	return " ".join([fel] + [a if _RE_ARG.match(a) else "*" for a in cuv[1:9]])


def scrie_jurnal_rotit(cale, bloc, maxim=JURNAL_OCTETI_MAX):
	"""Adauga bloc la sfarsitul jurnalului cale; cand ar trece de maxim octeti, jurnalul de pana acum trece in
	<cale>.1 (cel vechi se pierde). Fara legaturi simbolice (O_NOFOLLOW), fisier nou cu drepturile 0600, dosarul trebuie
	sa existe. False la orice eroare (nu arunca)."""
	date = bloc.encode("utf-8", "replace")[:maxim]
	try:
		if not os.path.isdir(os.path.dirname(cale)) or os.path.islink(cale):
			return False
		if os.path.isfile(cale) and os.path.getsize(cale) + len(date) > maxim:
			os.replace(cale, cale + ".1")
		fd = os.open(cale, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0), 0o600)
		try:
			os.write(fd, date)
		finally:
			os.close(fd)
		return True
	except (IOError, OSError):
		return False


TERMEN_PORNIRE_S = 20      # de la pornirea procesului pana la „PORNIT”
TERMEN_INCARCARE_S = 30     # de la „PORNIT” pana la prima pagina desenata
TERMEN_VIU_S = 10           # fara niciun rand atata timp: navigatorul e blocat
TERMEN_ASCUNS_MS = 2000     # asteptarea lui „ASCUNS” inainte de a lua ecranul inapoi oricum
OPRIRE_SIGTERM_S = 3
OPRIRE_SIGKILL_S = 2
MEMORIE_MINIMA_KB = 150 * 1024
# Modul HbbTV pe un ecran de 1920: pagina desenata la 1280x720 si marita de lansator la copiere (--marire-la-copiere,
# hds-navigator 0.6.0), ca tastele sa raspunda repede. Desenul WebKit direct la scara 1,5 e mai clar si se vede
# corect pe receptor, dar raspunde la taste cu 30-50 % mai incet (masurat pe SUPER RTL si ARD): il porneste numai
# setarea "HbbTV clar" (hbbtv["marire_copiere"] = False, din Components/HdsHbbtvPornire), oprita din fabrica.
HBBTV_MARIRE_LA_COPIERE = True
# Stratul HbbTV (obiectele OIPF, hds-hbbtv.js) din acest pachet, dat navigatorului cu --hbbtv-js (optiunea e in
# hds-navigator, ca si --hbbtv-parte): o reparatie a stratului ajunge astfel si printr-o actualizare a
# pachetului enigma2, fara navigator nou. Fara fisier, navigatorul il ia pe al lui (/usr/share/hds-navigator).
CALE_HBBTV_JS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hds-hbbtv.js")
LATIME_CSS = 1280           # pagina vede 1280 de puncte CSS pe latime (scara 1,5 pe un ecran de 1920)
TEXT_MAXIM = 4096
PRIORITATE_TASTE = -0x7FFFFFFF

MOD_CAM = "cam"
MOD_OBISNUIT = "obisnuit"
MOD_HBBTV = "hbbtv"

# starile
OPRIT = "oprit"
PORNIRE = "pornire"          # procesul porneste
INCARCARE = "incarcare"      # a pornit, se incarca prima pagina
ARATAT = "aratat"            # navigatorul are ecranul si telecomanda
ASCUNS = "ascuns"            # o fereastra a enigma2 e peste navigator
OPRIRE = "oprire"

# ferestrele pe care le cere pagina (nu tastele navigatorului)
FERESTRE_PAGINA = ("tastatura", "adresa", "autentificare", "dialog", "alegere")

# flagurile enigma2 pentru taste (eActionMap): apasare, ridicare, repetare, lunga, ASCII
_VALOARE_TASTA = {0: 1, 1: 0, 2: 2}

_activ = [None]


def activ():
	"""Navigatorul deschis acum (unul singur), sau None."""
	n = _activ[0]
	return n if n is not None and n.stare != OPRIT else None


def cedeaza():
	"""Locul pentru alt navigator (navigatorul obisnuit, interfata camului, stergerea datelor): o aplicatie HbbTV pornita
	automat si inca nevazuta (Components/HdsHbbtvPornire.Controlor.cedeaza) se opreste pe loc. -> navigatorul
	deschis dupa (None: locul e liber)."""
	n = activ()
	if n is not None and n.mod == MOD_HBBTV:
		f = getattr(n.a, "cedeaza", None)
		if f is not None:
			try:
				f()
			except Exception as e:
				_jurnal("cedarea locului: %s" % e)
	return activ()


def _text(valoare):
	"""Numai text (ferestrele enigma2 intorc text sau None; orice altceva inseamna gol)."""
	return valoare if isinstance(valoare, str) else ""


def b64(text):
	if not text:
		return "-"
	return base64.b64encode(text.encode("utf-8")).decode("ascii")


def jsonB64(valoare):
	"""JSON (numai ASCII) in base64: starea HbbTV spre lansator; nu se rupe un rand si nu se scrie in jurnal."""
	return base64.b64encode(json.dumps(valoare, ensure_ascii=True, separators=(",", ":")).encode("ascii")).decode("ascii")


def din_b64(text):
	if not text or text == "-":
		return ""
	try:
		return base64.b64decode(text.encode("ascii"), validate=True).decode("utf-8", "replace")
	except (ValueError, TypeError, UnicodeError):
		return ""


def _jurnal(text):
	print("[HdsNavigator] %s" % text)


class Mediu(object):
	"""Legatura cu enigma2 si cu sistemul; la probele de pe PC se inlocuieste."""

	def container(self):
		from enigma import eConsoleAppContainer
		return eConsoleAppContainer()

	def ceas_nou(self, functie):
		from enigma import eTimer
		t = eTimer()
		t.callback.append(functie)
		return t

	def fb(self):
		try:
			from enigma import fbClass
			return fbClass.getInstance()
		except Exception:
			return None

	def rc(self):
		try:
			from enigma import eRCInput
			return eRCInput.getInstance()
		except Exception:
			return None

	def harta_taste(self):
		from enigma import eActionMap
		return eActionMap.getInstance()

	def marime_ecran(self):
		from enigma import getDesktop
		s = getDesktop(0).size()
		return s.width(), s.height()

	def intrari(self):
		try:
			return sorted(os.path.join("/dev/input", n) for n in os.listdir("/dev/input") if n.startswith("event"))
		except OSError:
			return []

	def memorie_libera_kb(self):
		try:
			with open("/proc/meminfo") as f:
				for rand in f:
					if rand.startswith("MemAvailable:"):
						return int(rand.split()[1])
		except (IOError, OSError, ValueError, IndexError):
			pass
		return None

	def exista(self, cale):
		return os.path.exists(cale)

	def semnal(self, pid, sig):
		try:
			os.kill(pid, sig)
		except OSError:
			pass

	def culege(self, pid):
		"""waitpid scurt dupa SIGKILL, ca procesul sa nu ramana zombi."""
		for _i in range(20):
			try:
				if os.waitpid(pid, os.WNOHANG)[0]:
					return
			except OSError:
				return
			time.sleep(0.01)

	def limba(self):
		try:
			from Components.Language import language
			return (language.getLanguage() or "ro")[:2]
		except Exception:
			return "ro"

	def jurnal_erori(self, bloc):
		"""Un bloc in jurnalul erorilor (JURNAL_ERORI, rotit), cel mult JURNAL_PE_PORNIRE de la pornirea enigma2."""
		if _jurnal_scrise[0] >= JURNAL_PE_PORNIRE:
			return False
		_jurnal_scrise[0] += 1
		return scrie_jurnal_rotit(JURNAL_ERORI, bloc)

	def prefix_retea(self, mod):
		"""Prefixul pornirii cand omul a pornit VPN-ul numai pentru navigator si HbbTV (Components/HdsVpn.py:
		ip netns exec <namespace-ul VPN-ului>); [] cand VPN-ul e oprit, in alt mod sau lipseste din imagine (fara
		programele VPN, SystemInfo["HdsVpn"], modulul nici nu se incarca): pornirea de pana acum. Interfata camului
		(MOD_CAM) e pe receptor (127.0.0.1), deci ramane mereu in afara."""
		if mod == MOD_CAM:
			return []
		try:
			from Components.SystemInfo import SystemInfo
			if not SystemInfo.get("HdsVpn"):
				return []
			from Components import HdsVpn
			return list(HdsVpn.prefixNavigator())
		except Exception as e:
			_jurnal("VPN: %s" % e.__class__.__name__)
			return []


class Ascultator(object):
	"""Ce afla ecranul de la navigator. Metodele sunt chemate pe firul enigma2."""

	def laPas(self, pas, procent):
		"""pas: 'pornire' sau 'incarcare'; procent: al incarcarii paginii (-1 fara)."""

	def poateArata(self):
		"""Chemat la prima pagina, inainte de lacat: False opreste navigatorul (ecranul nu mai e liber)."""
		return True

	def laAratat(self):
		"""Navigatorul are ecranul."""

	def laEcranInapoi(self):
		"""Enigma2 are din nou ecranul (dupa unlock): ecranul se redeseneaza."""

	def laCerere(self, fel, date):
		"""O fereastra de deschis peste navigator (navigatorul e deja ascuns): tastatura, adresa, autentificare,
		dialog, alegere, meniu, iesire, favorite, inchide. Dupa ea ecranul cheama reia()."""

	def laFavorit(self, adresa, titlu):
		"""Raspunsul la ceresFavorit()."""

	def laOprit(self, motiv):
		"""Procesul s-a terminat. motiv: None (inchis de noi), sau un cod de eroare (vezi TEXTE_EROARE)."""

	def laPrimaPaginaAscunsa(self):
		"""Modul HbbTV cu stratul JS: prima pagina e gata, dar ramane ascunsa (fara lacat) pana la reia()."""

	def laHbbtv(self, comanda, argumente):
		"""Modul HbbTV: un rand "HBBTV <comanda> <argumente>" (stratul JS sau cererile paginii, vezi hds-hbbtv.js)."""

	def laIncarcare(self):
		"""O pagina noua incepe sa se incarce dupa prima pagina (randul "INCARCARE"), cat navigatorul e pe ecran sau
		ascuns: de pilda aplicatia HbbTV merge mai departe dupa o tasta (HdsHbbtvPornire, ROSU-ul urmarit)."""


def N_(text):
	return text


# textele erorilor, pe cod (le arata ecranul, traduse cu textEroare)
TEXTE_EROARE = {
	"lipsa": N_("Navigatorul lipsește din această imagine."),
	"memorie": N_("Memoria liberă a receptorului nu ajunge pentru navigator."),
	"pornire": N_("Navigatorul nu a pornit."),
	"termen-pornire": N_("Navigatorul nu a pornit în %d de secunde."),
	"termen-incarcare": N_("Pagina nu s-a încărcat în %d de secunde."),
	"blocat": N_("Navigatorul nu mai răspunde și a fost oprit."),
	"cazut": N_("Navigatorul s-a oprit singur."),
	"memorie-pagina": N_("Pagina a folosit prea multă memorie și navigatorul a fost oprit."),
	"retea": N_("Pagina nu s-a deschis: legătura în rețea nu merge."),
	"dns": N_("Pagina nu s-a deschis: adresa nu mai există pe internet."),
	"politica": N_("Pagina nu s-a deschis."),
	"certificat": N_("Certificatul interfeței nu a fost primit."),
	"alta": N_("Pagina nu s-a deschis."),
}


# textele stratului lansatorului (desenate de el jos pe ecran)
TEXTE_STRAT = {
	"scrie": N_("OK sau TEXT: scrie"),
	"fara-camp": N_("Niciun câmp de scris pe ecran"),
	"indicator": N_("Indicator: săgețile îl mișcă, OK face clic, ALBASTRU revine la selecție"),
	"scrie-indicator": N_("TEXT: scrie"),
}


def _traducere(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


# Stilul chenarului: cuvintele lansatorului (hds-navigator.c, CULORI_NUME ...), care sunt si valorile setarilor
# (setari.CULORI_CHENAR ...); primul e cel din fabrica. Pulsul oprit pleaca drept "oprit", altfel viteza.
CHENAR_CULORI = ("galben", "alb", "verde", "albastru", "portocaliu", "rosu", "auto")
CHENAR_FORME = ("dreptunghi", "rotunjit", "subliniere", "fundal")
CHENAR_GROSIMI = ("normal", "subtire", "gros")
CHENAR_VITEZE = ("normal", "lent", "rapid")


def stilChenar(setari):
	"""(pornit, culoare, forma, grosime, puls) din setarile navigatorului; o valoare lipsa sau necunoscuta e cea din
	fabrica (chenarul pornit, galben, dreptunghi, normal, pulsul normal)."""
	s = setari or {}

	def ales(cheie, voie):
		v = str(s.get(cheie, voie[0]))
		return v if v in voie else voie[0]
	puls = "oprit" if s.get("chenar_puls", True) is False else ales("chenar_viteza", CHENAR_VITEZE)
	return (s.get("chenar", True) is not False, ales("chenar_culoare", CHENAR_CULORI), ales("chenar_forma", CHENAR_FORME),
		ales("chenar_grosime", CHENAR_GROSIMI), puls)


def argumenteChenar(setari):
	"""Optiunile stilului pentru lansator, numai cele care difera de fabrica."""
	_pornit, culoare, forma, grosime, puls = stilChenar(setari)
	a = []
	for optiune, valoare, fabrica in (("--chenar-culoare", culoare, CHENAR_CULORI[0]), ("--chenar-forma", forma, CHENAR_FORME[0]),
			("--chenar-grosime", grosime, CHENAR_GROSIMI[0]), ("--chenar-puls", puls, CHENAR_VITEZE[0])):
		if valoare != fabrica:
			a += [optiune, valoare]
	return a


def rezumatTimpi(timpi, desen=""):
	"""Un rand pentru jurnal: pentru fiecare fel de TIMP, cate, mediana si cel mai mult (ms)."""
	parti = []
	for fel in sorted(timpi):
		v = sorted(timpi[fel])
		if v:
			parti.append("%s: %d, mediana %d ms, cel mai mult %d ms" % (fel, len(v), v[len(v) // 2], v[-1]))
	return "raspunsul la taste (desen %s): %s" % (desen or "?", "; ".join(parti) if parti else "nicio tasta masurata")


def textEroare(motiv, traducere=None):
	"""Textul erorii, tradus (traducere = functia _ a enigma2; fara ea, textul romanesc)."""
	t = traducere or (lambda s: s)
	sablon = TEXTE_EROARE.get(motiv) or TEXTE_EROARE["alta"]
	if motiv == "termen-pornire":
		return t(sablon) % TERMEN_PORNIRE_S
	if motiv == "termen-incarcare":
		return t(sablon) % TERMEN_INCARCARE_S
	return t(sablon)


class Navigator(object):
	"""Un navigator deschis: mod MOD_CAM (o singura gazda, nimic pe disc), MOD_OBISNUIT (orice adresa, profil) sau
	MOD_HBBTV (aplicatia HbbTV a canalului; hbbtv = {"agent": partea HbbTV a User-Agent-ului, "utilizator": numele
	utilizatorului fara root, sau gol})."""

	def __init__(self, ascultator, mod, adresa, mediu=None, setari=None, cam=None, dosar_date=None, dosar_cache=None,
			hbbtv=None, stare_hbbtv=None):
		self.a = ascultator
		self.mod = mod
		self.adresa = adresa
		self.m = mediu or Mediu()
		self.setari = setari            # {"marire", "font_minim", "desen", "chenar", "chenar_culoare" ...}; None = implicite
		self.cam = cam or {}            # modul cam: {"gazda", "port", "schema"}
		self.hbbtv = hbbtv or {}        # modul HbbTV: {"agent", "utilizator", "marire_copiere" (numai cand e oprita)}
		self.stare_hbbtv = stare_hbbtv or {}   # modul HbbTV: partile starii de pornire (app, canal, config, ...)
		self.strat_hbbtv = None         # stratul JS in pagina: None (nu se stie inca), True, False
		self.dosar_date = dosar_date
		self.dosar_cache = dosar_cache
		self.stare = OPRIT
		self.desen = ""
		self.rezerva = ""
		self.camp = "niciunul"
		self.cu_indicator = False
		self.marire = 0
		self.progres = -1
		self.timpi = {}             # randurile „TIMP fel ms”: raspunsul la taste, rezumat in jurnal la inchidere
		self._erori = collections.deque(maxlen=JURNAL_RANDURI_ERORI)   # iesirea de erori, curatata (jurnalul erorilor)
		self._stari = collections.deque(maxlen=JURNAL_RANDURI_STARI)   # ultimele randuri HDS-NAV, scurtate
		self.eroare_incarcare = None
		self._c = None
		self._pid = None
		self._tampon = ""
		self._tampon_err = ""
		self._fb_blocat = False
		self._rc_blocat = False
		self._taste_legate = False
		self._oprit_de_noi = False
		self._dupa_ascuns = None
		self._coada = []            # ferestrele cerute de pagina cat era deschisa alta fereastra a enigma2
		self._asteptat = None       # raspunsul cerut de noi cat navigatorul e ascuns (adresa de acum)
		self._aratat_anuntat = False
		self._motiv = None
		self._pornit_la = None
		self._ceas_pornire = self.m.ceas_nou(self._termenPornire)
		self._ceas_incarcare = self.m.ceas_nou(self._termenIncarcare)
		self._ceas_viu = self.m.ceas_nou(self._termenViu)
		self._ceas_ascuns = self.m.ceas_nou(self._termenAscuns)
		self._ceas_oprire = self.m.ceas_nou(self._treaptaOprire)
		self._treapta = 0

	# ------------------------------------------------------------ pornirea

	def argumente(self):
		"""Argumentele lansatorului (fara program)."""
		latime, inaltime = self.m.marime_ecran()
		scara = latime / float(LATIME_CSS)
		inaltime_css = int(round(inaltime / scara))
		a = ["--latime", str(LATIME_CSS), "--inaltime", str(inaltime_css), "--scara", "%.4f" % scara,
			"--ascuns", "--oom", "1000", "--limba", self.m.limba()]
		hbbtv = self.mod == MOD_HBBTV
		if self.m.fb() is not None and self.m.exista("/dev/fb0"):
			a += ["--fb", "/dev/fb0"]
			# in modul HbbTV telecomanda ramane a enigma2: fara dispozitive de intrare, deci fara EVIOCGRAB
			for i in [] if hbbtv else self.m.intrari():
				a += ["--intrare", i]
		s = self.setari or {}
		if s.get("desen") == "procesor":
			a.append("--cpu")
		if not hbbtv and s.get("chenar", True) is not False:
			a.append("--chenar")  # chenarul pe selectie, desenat de lansator (in modul HbbTV il deseneaza aplicatia)
			a += argumenteChenar(s)
		if not hbbtv:
			for cheie in sorted(TEXTE_STRAT):
				a += ["--text", "%s=%s" % (cheie, b64(_traducere(TEXTE_STRAT[cheie])))]
		font = str(s.get("font_minim", "14"))
		if font.isdigit() and int(font) > 0 and not hbbtv:
			a += ["--font-minim", font]
		marire = str(s.get("marire", "auto"))
		if hbbtv:
			pass
		elif marire == "auto":
			a.append("--marire-auto")
		elif marire.isdigit():
			a += ["--marire", "%.2f" % (int(marire) / 100.0)]
		mem = self.m.memorie_libera_kb()
		if mem:
			a += ["--memorie-mb", str(max(150, min(400, int(mem / 1024 * 0.6))))]
		if self.mod == MOD_CAM:
			gazda = self.cam.get("gazda") or "127.0.0.1"
			port = int(self.cam.get("port") or 0)
			a += ["--efemer", "--numai-gazda", "%s:%d" % (gazda, port)]
			if self.cam.get("schema") == "https":
				a += ["--certificat-local", str(port), "--gazda-certificat", gazda]
		else:
			if hbbtv:
				a.append("--hbbtv")
				# marirea la copiere: HBBTV_MARIRE_LA_COPIERE, afara de cand setarea "HbbTV clar" o opreste.
				# Lansatorul o face numai la scara 1,5; altfel o ignora cu un AVERTISMENT.
				if self.hbbtv.get("marire_copiere", HBBTV_MARIRE_LA_COPIERE) and abs(scara - 1.5) < 0.001:
					a.append("--marire-la-copiere")
				agent = _text(self.hbbtv.get("agent"))
				if agent and not any(ch in agent for ch in "\r\n"):
					a += ["--agent-adaugat", agent]
				utilizator = _text(self.hbbtv.get("utilizator"))
				if utilizator and utilizator.isalnum():
					a += ["--utilizator", utilizator]
				if self.m.exista(CALE_HBBTV_JS):
					a += ["--hbbtv-js", CALE_HBBTV_JS]
				for cheie in PARTI_LINIE:
					if cheie in self.stare_hbbtv:
						a += ["--hbbtv-parte", "%s=%s" % (cheie, jsonB64(self.stare_hbbtv[cheie]))]
			if self.dosar_date:
				a += ["--date", self.dosar_date]
			if self.dosar_cache:
				a += ["--cache", self.dosar_cache]
		a.append(self.adresa)
		return a

	def porneste(self):
		"""Porneste procesul. False (si laOprit cu motivul) daca nu se poate. O aplicatie HbbTV pornita automat si inca
		nevazuta lasa locul altui navigator (cedeaza)."""
		if activ() is not None and activ() is not self and self.mod != MOD_HBBTV:
			cedeaza()
		if activ() is not None and activ() is not self:
			_jurnal("un navigator e deja deschis")
			return False
		if not self.m.exista(CALE_LANSATOR):
			return self._nuAPornit("lipsa")
		jpegBun()
		mem = self.m.memorie_libera_kb()
		if mem is not None and mem < MEMORIE_MINIMA_KB:
			_jurnal("memorie libera %d kB, sub prag" % mem)
			return self._nuAPornit("memorie")
		argv = self.argumente()
		c = self.m.container()
		c.stdoutAvail.append(self._date)
		c.stderrAvail.append(self._dateErr)
		c.appClosed.append(self._inchis)
		self._c = c
		self.stare = PORNIRE
		_activ[0] = self
		self._pornit_la = time.time()
		# programul, apoi argv[0] si argumentele: fara interpretor de comenzi. Cu VPN-ul pornit numai pentru navigator
		# si HbbTV, in fata vine ip netns exec (acelasi proces, deci oprirea pe grup ramane la fel); altfel nimic.
		prefix = self.m.prefix_retea(self.mod) if hasattr(self.m, "prefix_retea") else []
		comanda = list(prefix) + [CALE_LANSATOR] + list(argv)
		if prefix:
			_jurnal("prin VPN (namespace de retea)")
		if c.execute(comanda[0], *comanda) != 0:
			self._desprinde()
			self.stare = OPRIT
			_activ[0] = None
			return self._nuAPornit("pornire")
		try:
			self._pid = c.getPID()
		except Exception:
			self._pid = None
		_jurnal("pornit (mod %s, pid %s)" % (self.mod, self._pid))
		self._ceas_pornire.start(TERMEN_PORNIRE_S * 1000, True)
		self._ceas_viu.start(TERMEN_VIU_S * 1000, True)
		self.a.laPas("pornire", -1)
		return True

	def _nuAPornit(self, motiv):
		self._motiv = motiv
		self.a.laOprit(motiv)
		return False

	# ------------------------------------------------------------ comenzi

	def _scrie(self, rand):
		if self._c is not None and self.stare != OPRIT:
			self._c.write(rand + "\n")

	def url(self, adresa):
		adresa = _text(adresa)
		if adresa and not any(ch in adresa for ch in "\r\n"):
			self._scrie("url " + adresa)

	def inapoi(self):
		self._scrie("inapoi")

	def inainte(self):
		self._scrie("inainte")

	def reincarca(self):
		self._scrie("reincarca")

	def marirePas(self, pas):
		self._scrie("marire-pas %d" % pas)

	def enter(self):
		self._scrie("enter")

	def textInCamp(self, text):
		"""Textul (din interfata web) intra in campul activ al paginii, la cursor. False daca navigatorul nu e pe
		ecran."""
		if self.stare not in (ARATAT, ASCUNS) or not text:
			return False
		self._scrie("text64 " + b64(text[:TEXT_MAXIM]))
		return True

	def valoareCamp(self, text):
		self._scrie("valoare64 " + b64(_text(text)[:TEXT_MAXIM]))

	def autentificare(self, utilizator, parola):
		if not isinstance(utilizator, str):
			self._scrie("autentificare-anulata")
		else:
			self._scrie("autentificare %s %s" % (b64(utilizator), b64(_text(parola))))

	def dialog(self, da, text=None):
		if isinstance(text, str) and da:
			self._scrie("dialog 1 " + b64(text))
		else:
			self._scrie("dialog %d" % (1 if da else 0))

	def alegere(self, index):
		self._scrie("alegere %d" % (index if index is not None else -1))

	def ceresFavorit(self):
		self._scrie("favorit?")

	def ceresAdresa(self):
		"""Adresa de acum, pentru bara de adresa: vine ca cerere „adresa” (si cat navigatorul e ascuns)."""
		self._asteptat = "adresa"
		self._scrie("adresa?")

	def tasta(self, cod, valoare):
		self._scrie("tasta %d %d" % (cod, valoare))

	def hbbtvParte(self, cheie, valoare):
		"""O parte a starii HbbTV spre pagina (si tinuta de lansator pentru documentele urmatoare)."""
		if self.mod == MOD_HBBTV:
			self._scrie("hbbtv-parte %s %s" % (cheie, jsonB64(valoare)))

	def hbbtvEv(self, valoare):
		"""Un eveniment HbbTV spre pagina de acum."""
		if self.mod == MOD_HBBTV:
			self._scrie("hbbtv-ev %s" % jsonB64(valoare))

	def vizibil(self, da):
		"""Modul HbbTV: pagina vizibila sau nu pentru WebKit (aplicatia pornita automat si inca nevazuta nu
		deseneaza); lansatorul raspunde "VIZIBIL 0|1"."""
		if self.mod == MOD_HBBTV:
			self._scrie("vizibil %d" % (1 if da else 0))

	def indicator(self, activ=None):
		"""Indicatorul (mouse din sageti): pornit, oprit, sau comutat (None)."""
		self._scrie("indicator" if activ is None else "indicator %d" % (1 if activ else 0))

	def scrie(self):
		"""Ca tasta TEXT: tastatura pentru campul cu focalizare sau pentru primul camp de pe ecran."""
		self._scrie("scrie")

	def schimbaChenar(self, setari):
		"""Chenarul si stilul lui, schimbate de om cat navigatorul e deschis: lansatorul il deseneaza din nou pe loc (cat e
		ascuns, la 'arata'). setari: ca la pornire ({"chenar", "chenar_culoare", ...}). In modul HbbTV nu exista chenar.
		False daca nu s-a trimis nimic."""
		self.setari = dict(self.setari or {})
		self.setari.update(setari or {})
		if self.mod == MOD_HBBTV or self.stare in (OPRIT, OPRIRE):
			return False
		pornit, culoare, forma, grosime, puls = stilChenar(self.setari)
		self._scrie("chenar %d %s %s %s %s" % (1 if pornit else 0, culoare, forma, grosime, puls))
		return True

	# ------------------------------------------------------------ iesirea procesului

	def _date(self, text):
		self._tampon = self._randuri(self._tampon + text)

	def _dateErr(self, text):
		# iesirea de erori (WebKit, GLib, randurile HDS-NAV de eroare): randurile intregi, curatate, raman in _erori
		# pentru jurnalul erorilor (scris numai la o oprire cu eroare); randurile HDS-NAV se trateaza ca pe iesire
		if isinstance(text, bytes):
			text = text.decode("utf-8", "replace")
		tampon = self._tampon_err + text
		for rand in tampon.split("\n")[:-1]:
			if rand.strip():
				self._erori.append(curata_rand(rand))
		self._tampon_err = self._randuri(tampon)

	def _randuri(self, tampon):
		if isinstance(tampon, bytes):
			tampon = tampon.decode("utf-8", "replace")
		*gata, rest = tampon.split("\n")
		for rand in gata:
			rand = rand.rstrip("\r")
			if rand.startswith(PREFIX):
				try:
					self._rand(rand[len(PREFIX):])
				except Exception as e:
					_jurnal("rand netratat (%s)" % e.__class__.__name__)
		return rest[-65536:]

	def _rand(self, rand):
		if self.stare in (PORNIRE, INCARCARE, ARATAT, ASCUNS):
			self._ceas_viu.start(TERMEN_VIU_S * 1000, True)
		cuv = rand.split(" ")
		fel = cuv[0]
		if fel not in ("VIU", "TIMP", "INDICATOR-LA") and not rand.startswith("HBBTV tradu "):
			self._stari.append(stare_scurta(rand))      # cererile de traducere nu umplu istoria starilor
		if fel == "VIU":
			return
		if fel == "PORNIT":
			self._ceas_pornire.stop()
			if self.stare == PORNIRE:
				self.stare = INCARCARE
				self._ceas_incarcare.start(TERMEN_INCARCARE_S * 1000, True)
				_jurnal("porneste in %.1f s" % (time.time() - (self._pornit_la or time.time())))
				self.a.laPas("incarcare", -1)
			return
		if fel == "DESEN":
			self.desen = " ".join(cuv[1:])[:40]
			_jurnal("desen: %s" % self.desen)
			return
		if fel == "REZERVA":
			self.rezerva = " ".join(cuv[1:])[:60]
			_jurnal("rezerva: %s" % self.rezerva)
			return
		if fel == "REPORNIRE":
			_jurnal("repornire pe procesor")
			return
		if fel == "PROGRES" and len(cuv) > 1 and cuv[1].isdigit():
			self.progres = int(cuv[1])
			if self.stare == INCARCARE:
				self.a.laPas("incarcare", self.progres)
			return
		if fel == "PRIMA-PAGINA":
			self._primaPagina()
			return
		if fel == "INCARCARE":
			if self.stare in (ARATAT, ASCUNS):
				f = getattr(self.a, "laIncarcare", None)
				if f is not None:
					f()
			return
		if fel == "EROARE-INCARCARE":
			self.eroare_incarcare = cuv[1] if len(cuv) > 1 else "alta"
			_jurnal("pagina nu s-a incarcat (%s)" % self.eroare_incarcare)
			if self.stare == INCARCARE and self.mod in (MOD_CAM, MOD_HBBTV):
				self._motiv = self.eroare_incarcare if self.eroare_incarcare in TEXTE_EROARE else "alta"
				self.opreste()
			elif self.mod == MOD_HBBTV and self.stare in (ARATAT, ASCUNS):
				# o aplicatie pornita din alta (createApplication) nu s-a incarcat
				self.a.laHbbtv("eroare-incarcare", [self.eroare_incarcare])
			return
		if fel == "HBBTV" and len(cuv) > 1:
			if cuv[1] == "strat":
				self.strat_hbbtv = len(cuv) > 2 and cuv[2] == "1"
				_jurnal("stratul HbbTV: %s" % ("da" if self.strat_hbbtv else "lipseste"))
			if self.mod == MOD_HBBTV:
				self.a.laHbbtv(cuv[1][:20], cuv[2:10])
			return
		if fel == "EROARE" and len(cuv) > 1 and cuv[1] == "certificat":
			_jurnal("certificatul nu a fost primit")
			if self.stare == INCARCARE and self.mod == MOD_CAM:
				self._motiv = "certificat"
				self.opreste()
			return
		if fel == "EROARE":
			self._motiv = "memorie-pagina" if len(cuv) > 1 and cuv[1] == "memorie" else self._motiv
			_jurnal("eroare: %s" % " ".join(cuv[1:3]))
			return
		if fel == "ARATAT":
			return
		if fel == "ASCUNS":
			self._ceas_ascuns.stop()
			self._dupaAscundere()
			return
		if fel == "CAMP" and len(cuv) > 1:
			self.camp = cuv[1][:16]
			return
		if fel == "INDICATOR" and len(cuv) > 1:
			self.cu_indicator = cuv[1] == "1"
			return
		if fel == "INDICATOR-LA":
			return
		if fel == "CHENAR":
			_jurnal("chenar: %s" % " ".join(cuv[1:6])[:60])
			return
		if fel == "TIMP" and len(cuv) > 2 and cuv[2].isdigit():
			lista = self.timpi.setdefault(cuv[1][:20], [])
			if len(lista) < 5000:
				lista.append(int(cuv[2]))
			return
		if fel == "TIMP":
			return
		if fel == "MARIRE" and len(cuv) > 1 and cuv[1].isdigit():
			self.marire = int(cuv[1])
			return
		if fel == "BLOCAT":
			_jurnal("adresa spre alta gazda oprita")
			return
		if fel == "AVERTISMENT":
			# de exemplu „apucare 16”: telecomanda nu a putut fi apucata (EVIOCGRAB), tastele nu ajung in pagina
			_jurnal("avertisment: %s" % " ".join(cuv[1:3])[:60])
			return
		if fel == "SCRIS":
			_jurnal("TEXT: niciun camp de scris pe ecran")
			return
		if fel == "TASTA" and len(cuv) > 1:
			self._cere(cuv[1], {})
			return
		if fel == "CERERE" and len(cuv) > 1:
			self._cerere(cuv[1], cuv[2:])
			return
		if fel == "FAVORIT":
			self.a.laFavorit(din_b64(cuv[1] if len(cuv) > 1 else ""), din_b64(cuv[2] if len(cuv) > 2 else ""))
			return

	def _cerere(self, fel, arg):
		if fel == "tastatura":
			_jurnal("cerere tastatura (%s)" % (arg[0] if arg else "text")[:16])
			self._cere("tastatura", {"fel": arg[0] if arg else "text", "valoare": din_b64(arg[1] if len(arg) > 1 else "")})
		elif fel == "adresa":
			self._cere("adresa", {"adresa": din_b64(arg[0] if arg else "")})
		elif fel == "autentificare":
			self._cere("autentificare", {"gazda": din_b64(arg[0] if arg else ""), "din_nou": len(arg) > 1 and arg[1] == "1"})
		elif fel == "dialog":
			self._cere("dialog", {"fel": arg[0] if arg else "alerta", "mesaj": din_b64(arg[1] if len(arg) > 1 else ""),
				"implicit": din_b64(arg[2] if len(arg) > 2 else "")})
		elif fel == "alegere":
			try:
				date = json.loads(din_b64(arg[0] if arg else ""))
				optiuni = [(str(o[0]), bool(o[1]), bool(o[2])) for o in date.get("optiuni", [])]
				ales = int(date.get("ales", -1))
			except (ValueError, TypeError, IndexError, AttributeError):
				optiuni, ales = [], -1
			self._cere("alegere", {"optiuni": optiuni, "ales": ales})

	# ------------------------------------------------------------ ecranul si telecomanda

	def _primaPagina(self):
		self._ceas_incarcare.stop()
		if self.stare == INCARCARE and self.mod == MOD_HBBTV and self.strat_hbbtv:
			# aplicatia HbbTV porneste ascunsa: ecranul il ia abia la Application.show() (ascultatorul cheama reia())
			self.stare = ASCUNS
			_jurnal("prima pagina dupa %.1f s (ascunsa)" % (time.time() - (self._pornit_la or time.time())))
			self.a.laPrimaPaginaAscunsa()
			return
		if self.stare == INCARCARE:
			if not self.a.poateArata():
				_jurnal("ecranul nu e liber; navigatorul se opreste")
				self.opreste()
				return
			self._blocheaza()
			self.stare = ARATAT
			self._scrie("arata")
			self._legaTaste(True)
			self._aratat_anuntat = True
			self.a.laAratat()
			_jurnal("prima pagina dupa %.1f s" % (time.time() - (self._pornit_la or time.time())))
		elif self.stare == ARATAT:
			# lansatorul s-a repornit singur pe procesor (--ascuns din nou): ecranul e tot al lui
			self._scrie("arata")

	def _blocheaza(self):
		rc = self.m.rc()
		fb = self.m.fb()
		if fb is None:
			return  # emulatorul (SDL): fara lacate, tastele trec prin legatura
		if rc is not None and not self._rc_blocat and self.mod != MOD_HBBTV:
			rc.lock()
			self._rc_blocat = True
		if not self._fb_blocat:
			fb.lock()
			self._fb_blocat = True

	def _deblocheaza(self):
		if self._rc_blocat:
			rc = self.m.rc()
			if rc is not None:
				rc.unlock()
			self._rc_blocat = False
		if self._fb_blocat:
			fb = self.m.fb()
			if fb is not None:
				fb.unlock()
			self._fb_blocat = False
			self.a.laEcranInapoi()

	def _legaTaste(self, da):
		if da == self._taste_legate or self.mod == MOD_HBBTV:
			return  # in modul HbbTV tastele le imparte ascultatorul (Components/HdsHbbtvPornire.py)
		try:
			h = self.m.harta_taste()
			if da:
				h.bindAction("", PRIORITATE_TASTE, self._tastaEnigma)
			else:
				h.unbindAction("", self._tastaEnigma)
			self._taste_legate = da
		except Exception as e:
			_jurnal("legarea tastelor: %s" % e)

	def _tastaEnigma(self, cod, flag):
		"""Orice tasta ajunsa la enigma2 cat navigatorul e pe ecran merge la navigator (nu si la ecranele de sub el)."""
		if self.stare != ARATAT:
			return 0
		valoare = _VALOARE_TASTA.get(flag)
		if valoare is not None:
			self.tasta(cod, valoare)
		return 1

	def _cere(self, fel, date):
		if self.mod == MOD_HBBTV:
			self._refuzaHbbtv(fel)
			return
		if self.stare == ARATAT:
			self.ascunde(lambda: self.a.laCerere(fel, date))
		elif self.stare == INCARCARE and fel in FERESTRE_PAGINA:
			# pagina cere ceva inainte de prima pagina (de exemplu parola interfetei camului): navigatorul e inca
			# ascuns si fara lacate, deci fereastra se deschide direct; dupa ea, reia() ii da ecranul
			self._ceas_incarcare.stop()
			self.stare = ASCUNS
			self.a.laCerere(fel, date)
		elif self.stare == ASCUNS:
			if fel == self._asteptat:
				self._asteptat = None
				self.a.laCerere(fel, date)
			elif fel in FERESTRE_PAGINA:
				# o fereastra ceruta de pagina cat e deschisa alta: vine dupa ea, nu peste ea
				self._coada.append((fel, date))
			else:
				_jurnal("cererea %s nu se deschide: e deschisa alta fereastra" % fel[:16])
		else:
			_jurnal("cererea %s nu se deschide in starea %s" % (fel[:16], self.stare))

	def _refuzaHbbtv(self, fel):
		"""Modul HbbTV: nicio fereastra a enigma2 peste aplicatie. alert/confirm/prompt se inchid ca refuzate, lista
		unui <select> fara alegere, autentificarea se anuleaza; restul (tastatura, meniul) nu se cere in acest mod."""
		_jurnal("modul HbbTV: fereastra %s refuzata" % fel)
		if fel == "dialog":
			self._scrie("dialog 0")
		elif fel == "alegere":
			self._scrie("alegere -1")
		elif fel == "autentificare":
			self._scrie("autentificare-anulata")

	def ascunde(self, apoi=None):
		"""Enigma2 ia ecranul inapoi (pentru o fereastra peste navigator); `apoi` dupa ce il are."""
		if self.stare != ARATAT:
			if apoi is not None and self.stare == ASCUNS:
				apoi()
			return
		self.stare = ASCUNS
		self._legaTaste(False)
		self._dupa_ascuns = apoi
		self._scrie("ascunde")
		self._ceas_ascuns.start(TERMEN_ASCUNS_MS, True)

	def _termenAscuns(self):
		_jurnal("ASCUNS nu a venit la timp")
		self._dupaAscundere()

	def _dupaAscundere(self):
		apoi, self._dupa_ascuns = self._dupa_ascuns, None
		if self.stare != ASCUNS:
			return
		self._deblocheaza()
		if apoi is not None:
			apoi()

	def continuaIncarcarea(self):
		"""Dupa o cerere a paginii venita inainte de prima pagina, la care s-a raspuns fara nicio fereastra pe ecran
		(intrarea in interfata camului cu datele de pe receptor): navigatorul ramane ascuns, fara
		lacate, si asteapta prima pagina, cu termenul de incarcare pornit din nou; ecranul de progres ramane. In orice
		alta stare (pagina era deja pe ecran, alta fereastra asteapta la rand), ca reia()."""
		if self.stare == ASCUNS and not self._aratat_anuntat and not self._coada and self.mod == MOD_CAM:
			self.stare = INCARCARE
			self._ceas_incarcare.start(TERMEN_INCARCARE_S * 1000, True)
			return
		self.reia()

	def reia(self):
		"""Navigatorul primeste iar ecranul si telecomanda (dupa fereastra enigma2); daca pagina a cerut intre timp
		alta fereastra, vine intai ea."""
		if self.stare != ASCUNS:
			return
		if self._coada:
			fel, date = self._coada.pop(0)
			self.a.laCerere(fel, date)
			return
		self._blocheaza()
		self.stare = ARATAT
		self._scrie("arata")
		self._legaTaste(True)
		if not self._aratat_anuntat:
			self._aratat_anuntat = True
			self.a.laAratat()

	# ------------------------------------------------------------ termene

	def _termenPornire(self):
		if self.stare == PORNIRE:
			_jurnal("termenul de pornire a trecut")
			self._motiv = "termen-pornire"
			self.opreste()

	def _termenIncarcare(self):
		if self.stare == INCARCARE:
			_jurnal("termenul de incarcare a trecut")
			self._motiv = self.eroare_incarcare if self.eroare_incarcare in TEXTE_EROARE else "termen-incarcare"
			self.opreste()

	def _termenViu(self):
		if self.stare in (PORNIRE, INCARCARE, ARATAT, ASCUNS):
			_jurnal("fara semn de viata %d s" % TERMEN_VIU_S)
			self._motiv = "blocat"
			self._omoara()

	# ------------------------------------------------------------ oprirea

	def opreste(self):
		"""Oprirea ceruta de noi: „iesire”, apoi SIGTERM, apoi SIGKILL pe grup."""
		if self.stare in (OPRIT, OPRIRE):
			return
		if self._motiv is None:
			self._oprit_de_noi = True
		self._legaTaste(False)
		self._ceas_pornire.stop()
		self._ceas_incarcare.stop()
		self._ceas_ascuns.stop()
		self.stare = OPRIRE
		if self.mod == MOD_HBBTV:
			# stratul golit pe loc ("ascunde" goleste ce a desenat navigatorul), nu abia dupa oprirea WebKit: imaginea
			# canalului, pusa inainte pe tot ecranul de ascultator (HdsHbbtvPornire.inchide), se vede imediat
			self._scrie_mereu("ascunde")
		self._scrie_mereu("iesire")
		self._treapta = 1
		self._ceas_oprire.start(OPRIRE_SIGTERM_S * 1000, True)

	def opresteAcum(self):
		"""Oprirea pe loc (SIGKILL pe grup, fara asteptare): aplicatia HbbTV pornita automat si nevazuta, cand altcineva
		vrea locul (cedeaza). laOprit vine inainte ca functia sa se intoarca."""
		if self.stare == OPRIT:
			return
		if self._motiv is None:
			self._oprit_de_noi = True
		if self._c is not None:
			self._omoara()
		else:
			self._inchis(-9)

	def _scrie_mereu(self, rand):
		if self._c is not None:
			try:
				self._c.write(rand + "\n")
			except Exception:
				pass

	def _treaptaOprire(self):
		if self.stare != OPRIRE:
			return
		if self._treapta == 1 and self._pid:
			_jurnal("nu a iesit la comanda; SIGTERM")
			self.m.semnal(self._pid, signal.SIGTERM)
			self._treapta = 2
			self._ceas_oprire.start(OPRIRE_SIGKILL_S * 1000, True)
		else:
			self._omoara()

	def _omoara(self):
		"""SIGKILL pe tot grupul (eConsoleAppContainer.kill); dupa kill() appClosed nu mai vine, deci sfarsitul se
		face aici."""
		if self._c is None:
			return
		_jurnal("oprit fortat")
		pid = self._pid
		try:
			self._c.kill()
		except Exception:
			pass
		if pid:
			self.m.culege(pid)
		self._inchis(-9)

	def _desprinde(self):
		c = self._c
		if c is None:
			return
		for lista, f in ((c.stdoutAvail, self._date), (c.stderrAvail, self._dateErr), (c.appClosed, self._inchis)):
			try:
				lista.remove(f)
			except ValueError:
				pass

	def _inchis(self, cod):
		if self.stare == OPRIT:
			return
		for t in (self._ceas_pornire, self._ceas_incarcare, self._ceas_viu, self._ceas_ascuns, self._ceas_oprire):
			t.stop()
		self._legaTaste(False)
		self._desprinde()
		self._c = None
		self.stare = OPRIT
		if _activ[0] is self:
			_activ[0] = None
		self._deblocheaza()
		motiv = None if self._oprit_de_noi and self._motiv is None else (self._motiv or "cazut")
		_jurnal("s-a terminat (cod %s%s)" % (cod, ", " + motiv if motiv else ""))
		_jurnal(rezumatTimpi(self.timpi, self.desen))
		if motiv is not None:
			self._scrieJurnalErori(cod, motiv)
		self.a.laOprit(motiv)

	def _scrieJurnalErori(self, cod, motiv):
		"""Oprirea cu eroare: un bloc in jurnalul erorilor (Mediu.jurnal_erori): ora, modul, motivul, codul de iesire,
		desenul, cat a trait, memoria libera, ultimele stari HDS-NAV si ultimele randuri de pe iesirea de erori. Fara
		adresa paginii. Nu arunca."""
		try:
			rest = self._tampon_err.strip()
			if rest:
				self._erori.append(curata_rand(rest))
				self._tampon_err = ""
			f = getattr(self.m, "jurnal_erori", None)
			if f is None:
				return
			memorie = getattr(self.m, "memorie_libera_kb", lambda: None)()
			durata = time.time() - self._pornit_la if self._pornit_la else 0.0
			randuri = ["%s navigator mod=%s motiv=%s cod=%s desen=%s rezerva=%s durata=%.1f s memorie_libera=%s kB" % (
				time.strftime("%Y-%m-%d %H:%M:%S"), self.mod, motiv, cod, curata_rand(self.desen or "-", 40),
				curata_rand(self.rezerva or "-", 60), durata, memorie if memorie is not None else "?")]
			randuri += ["  stare: " + s for s in self._stari]
			randuri += ["  erori: " + e for e in self._erori] or ["  erori: (nimic pe iesirea de erori)"]
			f("\n".join(randuri) + "\n")
		except Exception as e:
			_jurnal("jurnalul erorilor: %s" % e.__class__.__name__)

	def stareWeb(self):
		"""Pentru interfata web: fara adrese si fara texte."""
		return {"stare": self.stare, "mod": self.mod, "desen": self.desen, "rezerva": self.rezerva,
			"camp": self.camp, "marire": self.marire, "indicator": self.cu_indicator}
