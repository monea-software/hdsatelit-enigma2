# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsImagineOnline.py: imaginea completa a receptorului, luata de pe internet direct pe stick, cu o singura apasare.
# Fereastra e Screens/HdsImagineOnline.py, pagina web HdsWebControl/imagine_online_web.py; amandoua citesc si pornesc
# totul de aici (o singura stare, o singura lucrare odata). Acelasi fisier merge si in pachetul-punte de pe imaginile
# vechi (0.6.x), unde sta intr-un plugin, langa MediuImagine.py si HdsReinstalare.py (de aceea _modul si _mediu).
#
# Drumul, numai dupa „Da” (sau singur in standby):
#   1. lista imaginilor: <server>/feed/<canal>/imagini.json, primita numai cu imagini.json.sig de langa ea, verificata pe
#      octetii primiti cu cheile feedului (Components/HdsSemnatura.py, scopul imagini.json). Modelul e machinebuild= din
#      /etc/hdsatelit-model; versiunea aleasa e cea mai mare, numai mai noua decat cea de acum;
#   2. locul: tinta_scriere citeste /proc/cmdline. Se scrie numai locul din care ruleaza imaginea, dat explicit programului
#      de scriere. De pe stick, de pe un disc sau dintr-o asezare necunoscuta nu se scrie;
#   3. descarcarea numai pe stick (hdsatelit/imagine-noua/<fisier>.partial), cu reluare (Range); memoria interna nu se
#      atinge. Fara stick sau cu loc putin nu porneste;
#   4. fisierul se citeste inapoi de pe stick (cache-ul golit), mai mare sau cu alta suma = sters si oprire; apoi cele patru
#      fisiere ale pachetului in dosarul curat, marcajul de model si sumele din el (Components/HdsPazaModel.py);
#   5. copia completa pe stick (Components/HdsCopieSetari.fa_copia), recitita; o copie cazuta opreste tot. La prima
#      pornire o pune la loc HdsCopieSetari.pornire din enigma2.sh, fara intrebari;
#   6. simularea, cu aceleasi argumente; rezultatul trebuie sa numeasca exact fisierele si locul. Chiar inainte de
#      scriere: inregistrarile, mediul, marcajul, fisierele neschimbate, locul;
#   7. scrierea, intr-o sesiune noua: init 4 opreste tot grupul de procese al lui enigma2.sh. Programul reporneste singur.
#   8. la pornirea urmatoare se compara versiunea si locul cu cele scrise pe stick inainte (scriere.json).
#      Acolo ramane si identitatea copiei facute la pasul 5, ca prima pornire sa o aleaga exact.
# Orice nepotrivire inseamna oprire fara scriere, cu un mesaj simplu; descarcarea ramasa se reia de unde a ramas.
#
# Marcajul si sumele raman si dupa lista semnata: lista spune ce a publicat serverul, marcajul spune ca pachetul e al
# acestui receptor. Fisierul nu importa nimic din enigma la incarcare (probele de pe PC: teste/test_imagine_online_*.py).
#
# Imaginile altor echipe: aici nu sta niciun nume si nicio adresa. Un plugin le da cu inregistreaza_imagini (vezi acolo) si
# le scoate cu scoate_imagini. Se arata numai cand omul intra in fereastra din meniu sau in pagina web, intr-o sectiune a lor,
# cu starea „Neverificată”; nu apar singure si nu se pun niciodata din standby. Dupa OK vine avertismentul, cu „Nu” ales.
# De la paza raman: numai pe stick, locul care ruleaza, copia completa, simularea stricta. Ce nu se poate cere de la ele:
# marcajul de model si sumele din el; o suma data de plugin se verifica, iar un marcaj gasit in arhiva se respecta.

import errno
import hashlib
import json
import os
import posixpath
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time
import zipfile

try:
	from urllib.request import Request, urlopen, build_opener, HTTPRedirectHandler
	from urllib.parse import urlsplit
	from urllib.error import HTTPError, URLError
	from http.client import HTTPException
except ImportError:  # Python 2 (probe vechi)
	from urllib2 import Request, urlopen, HTTPError, URLError, build_opener, HTTPRedirectHandler
	from urlparse import urlsplit
	from httplib import HTTPException


def N_(text):
	"""Marcheaza un text pentru xgettext (--keyword=N_) fara sa-l traduca acum."""
	return text


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi pe PC."""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


SERVER = "https://stb.hdsatelit.com"
NUME_LISTA = "imagini.json"
SCOP_LISTA = "imagini.json"
MARIME_LISTA_MAX = 256 * 1024
MARIME_SEMNATURA_MAX = 8 * 1024
TIMP_LISTA = 20
TIMP_DESCARCARE = 60
UA = "hdsatelit-receptor/1"
FORMAT = 1
DOSAR_PE_STICK = "hdsatelit/imagine-noua"
SUFIX_PARTIAL = ".partial"
FIS_SCRIERE = "scriere.json"
FIS_ESEC = "scrieri-esuate.json"
FOLDER_CURAT = ".hds-actualizare-extrasa"
SUBCALE_UPDATE = ("e2", "update")
NUME_MARCAJ = "hdsatelit-model"
NUME_PACHET = ("kernel.bin", "rootfs.tar.bz2", "imageversion", NUME_MARCAJ)
CALE_PROGRAM = "/usr/bin/ofgwrite"
NUME_JURNAL_STICK = "hds-actualizare-jurnal.txt"
JURNAL = "/home/root/logs/hds-imagine-online.log"
MARIME_JURNAL = 256 * 1024
REZERVA_LOC = 128 * 1024 * 1024
BLOC = 1024 * 1024
FSYNC_LA = 32 * 1024 * 1024
INCERCARI_FARA_PROGRES = 6
INCERCARI_DESCARCARE = 30
PAUZA_INCERCARE_S = 20
PRIMA_VERIFICARE = 300
ZI = 24 * 3600
REINCERCARE = 3 * 3600
ASTEPTARE_INREGISTRARE_MS = 60000
ASTEPTARE_STICK_MS = 40000
FEREASTRA_INREGISTRARE_S = 15 * 60
FEREASTRA_STANDBY_S = 3600
STANDBY_DUPA_REPORNIRE = "/tmp/hds-standby-dupa-repornire"
SEMN_STRAINA_VALABIL_S = 2 * 3600
MAX_NUME_STRAIN = 60

_RX_VERSIUNE = re.compile(r"^[0-9]{1,3}(?:\.[0-9]{1,3}){2,3}\Z")
_RX_SHA256 = re.compile(r"^[0-9a-f]{64}\Z")
_RX_MASINA = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}\Z")
_RX_FISIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}\.zip\Z")
_RX_ADRESA = re.compile(r"^/descarcari/[a-z0-9][a-z0-9._-]{0,63}/[A-Za-z0-9][A-Za-z0-9._-]{0,120}\.zip\Z")
_RX_DATA_ISO = re.compile(r"^([0-9]{4})-([0-9]{2})-([0-9]{2})\Z")
_RX_DATA_RO = re.compile(r"^([0-9]{2})\.([0-9]{2})\.([0-9]{4})\Z")
_RX_MMC = re.compile(r"^/dev/mmcblk0p([0-9]{1,3})\Z")
_RX_LOC = re.compile(r"^linuxrootfs([1-9])\Z")
_RX_NUME_PARTITIE = re.compile(r"^[A-Za-z0-9_]{1,32}\Z")
_RX_URL = re.compile(r"^https?://[A-Za-z0-9.-]+(?::[0-9]{1,5})?/[^\s?#]*\.zip(?:\?[^\s#]*)?\Z")

LUNI = (N_("ianuarie"), N_("februarie"), N_("martie"), N_("aprilie"), N_("mai"), N_("iunie"), N_("iulie"), N_("august"),
	N_("septembrie"), N_("octombrie"), N_("noiembrie"), N_("decembrie"))

# ce se poate spune omului; un singur rand de fiecare, fara cuvinte tehnice
T_DA = N_("Da, actualizează")
T_NU = N_("Nu acum")
T_IMAGINE = N_("Există o imagine nouă pentru receptorul tău: %s. Acum ai %s. O instalez acum? Canalele și setările tale rămân.")
T_VERSIUNE = N_("Există o versiune nouă pentru receptorul tău: %s. Acum ai %s. O instalez acum? Canalele și setările tale rămân.")
T_FARA_STICK = N_("Pune un stick USB și apasă din nou.")
T_FARA_LOC = N_("Pe stick nu e destul loc: trebuie %d MB liberi.")
T_LOC_STRAIN = N_("Receptorul rulează acum de pe stick sau dintr-un loc necunoscut, deci nu pun singur imaginea nouă. O poți lua de pe site.")
T_NUME_STICK = N_("Numele stickului are spații sau semne cu care instalarea nu merge. Schimbă-i numele în calculator (de exemplu HDSATELIT) și apasă din nou.")
T_LA_ZI = N_("Ai cea mai nouă imagine pentru receptorul tău.")
T_FARA_RETEA = N_("Legătura la internet s-a întrerupt. Apasă din nou: descărcarea continuă de unde a rămas.")
T_FARA_SERVER = N_("Serverul de actualizări nu răspunde acum. Încearcă mai târziu.")
T_NESEMNATA = N_("Lista imaginilor nu e semnată de HD Satelit. Nu s-a instalat nimic.")
T_FARA_FISIER = N_("Imaginea nouă nu se găsește pe server. Încearcă mai târziu.")
T_NEPOTRIVIT = N_("Imaginea descărcată nu se potrivește. Nu s-a instalat nimic. Apasă din nou ca s-o descarc iar.")
T_ALT_RECEPTOR = N_("Imaginea nu este pentru acest receptor. Nu s-a instalat nimic.")
T_STICK_STRICAT = N_("Stickul a fost scos sau are o eroare. Nu s-a instalat nimic.")
T_FARA_COPIE = N_("Copia setărilor nu s-a putut face pe stick. Nu s-a instalat nimic.")
T_SIMULARE = N_("Verificarea de dinainte de instalare n-a ieșit bine. Nu s-a instalat nimic.")
T_OPRIT = N_("Oprit. Nu s-a instalat nimic. Dacă apeși din nou, descărcarea continuă de unde a rămas.")
T_NESCRIS = N_("Imaginea nouă nu s-a instalat. Receptorul a rămas pe %s.")
P_CAUT = N_("Se caută imaginea nouă...")
P_DESCARC = N_("Se descarcă imaginea pe stick: %d%% (%d din %d MB).")
P_VERIFIC = N_("Se verifică imaginea de pe stick...")
P_PREGATESC = N_("Se pregătește imaginea pe stick...")
P_COPIE = N_("Se face copia completă pe stick...")
P_INAINTE = N_("Se verifică totul înainte de instalare...")
P_ASTEPT = N_("Instalarea așteaptă să se termine înregistrarea și pornește singură.")
P_SCRIU = N_("Imaginea se instalează acum. Nu opri receptorul: repornește singur, iar canalele și setările revin singure.")
T_FEED_PORNIT = N_("Instalez actualizarea. Canalele, setările și pluginurile rămân. Interfața repornește singură când receptorul e liber.")
T_FEED_OCUPAT = N_("Așteaptă să se termine operația de acum.")
T_COPIE_CERUTA = N_("Setările din copia făcută înainte de instalare se pun la loc acum. Interfața repornește o dată, când receptorul e liber.")
T_COPIE_LIPSA = N_("Introdu stickul folosit la instalare. Setările se vor pune singure la loc.")
# identitatea copiei asteptate, cand dupa o scriere buna copia nu era pe niciun stick (in dosarul restaurarii, ca sa ramana si
# dupa repornire); se cauta la fiecare VERIFICARE_COPIE_MS, pana apare stickul
FIS_COPIE_ASTEPTATA = "copie-asteptata.json"
VERIFICARE_COPIE_MS = 30000
T_STANDBY = N_("Actualizare singură în standby")
T_ALTE = N_("Alte imagini")
T_NEVERIFICATA = N_("Neverificată")
T_INSTALEAZA = N_("Instalează")
T_STRAINA = N_("Nu este imagine HD Satelit, ci %s. Nu știm dacă este compatibilă cu acest receptor, pentru că nu ne aparține și nu o putem verifica.")
T_STRAINA_MODEL = N_("Dacă nu este făcută pentru modelul acestui receptor, receptorul poate rămâne fără pornire până la recuperarea de pe stick.")
T_STRAINA_COPIE = N_("Dacă o instalezi, ea înlocuiește imaginea HD Satelit. Setările și lista de canale se copiază întâi pe stick.")
T_STRAINA_INTREBARE = N_("Continui?")
T_STRAINA_TITLU = N_("Imagine care nu este HD Satelit")
T_STRAINA_DA = N_("Da, continuă")
VALORI_STANDBY = (("amandoua", N_("imaginea și pachetele")), ("majore", N_("numai imaginea")), ("minore", N_("numai pachetele")),
	("oprita", N_("oprită")))

# rezultatele cautarii
NECAUTAT, LA_ZI, OFERTA, LOC_STRAIN, FARA_RETEA, FARA_RASPUNS, NESEMNATA, EROARE = (
	"necautat", "la-zi", "oferta", "loc-strain", "fara-retea", "fara-raspuns", "nesemnata", "eroare")

# radacina receptorului (probele dau un receptor fals) si adresa serverului
RADACINA = None
# fereastra (in punte o pune pluginul, altfel Screens/HdsImagineOnline.py)
ECRAN = None
PAZA_PROPRIE = False
# imaginea are feedul ei (porneste(session, cu_feed=True)): cautarea citeste si stare.json al feedului si alege intre
# imaginea completa si actualizarea din feed (alege_oferta); in puntea de pe 0.6.x ramane False
CU_FEED = False


def _rad():
	return RADACINA or "/"


def _langa(nume):
	"""Modulul `nume`, din fisierul de langa acesta (puntea) sau din dosarul Tools vecin (probele de pe PC)."""
	import importlib.util
	import sys
	aici = os.path.dirname(os.path.abspath(__file__))
	cheie = "HdsImagineOnline_" + nume
	if cheie in sys.modules:
		return sys.modules[cheie]
	for dosar in (aici, os.path.join(aici, "..", "Tools"), os.path.join(aici, "..", "..", "Tools")):
		cale = os.path.join(dosar, nume + ".py")
		if os.path.isfile(cale):
			spec = importlib.util.spec_from_file_location(cheie, cale)
			m = importlib.util.module_from_spec(spec)
			spec.loader.exec_module(m)
			sys.modules[cheie] = m
			return m
	raise ImportError(nume)


def _modul(nume):
	"""Components/<nume>; pe PC, modulul din acelasi dosar."""
	try:
		return __import__("Components." + nume, fromlist=[nume])
	except ImportError:
		return __import__(nume)


def _paza():
	"""Components/HdsPazaModel; in punte, copia adusa de ea: marcajele imaginilor noi au campuri pe care paza veche nu le
	stie, iar o paza veche ar refuza fara folos."""
	return _langa("HdsPazaModel") if PAZA_PROPRIE else _modul("HdsPazaModel")


def _mediu():
	"""Tools/MediuImagine; pe imaginile fara paza numelui de stick (puntea), copia de langa acest fisier."""
	try:
		from Tools import MediuImagine as M
		if hasattr(M, "verificaNumeStick") and hasattr(M, "ofgwriteReparat") and hasattr(M, "mutaMontarea"):
			return M
	except ImportError:
		pass
	return _langa("MediuImagine")


def _jurnal(rand):
	"""Un rand in jurnalul din dosarul jurnalelor de pe memoria interna (numai text scurt, nu imagini). Nu arunca."""
	print("[HdsImagineOnline] %s" % rand)
	text = "%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), rand)
	cale = os.path.join(_rad(), JURNAL.lstrip("/"))
	try:
		scrie = getattr(_modul("HdsPachete"), "scrie_jurnal_rotit", None)
		if scrie is not None:
			scrie(cale, text, MARIME_JURNAL, sincron=True)
		elif not os.path.exists(cale) or os.path.getsize(cale) < MARIME_JURNAL:
			os.makedirs(os.path.dirname(cale), exist_ok=True)
			with open(cale, "a", encoding="utf-8") as f:
				f.write(text)
	except Exception:
		pass


# ---------------------------------------------------------------- versiunile si datele

def compara(a, b):
	return _modul("HdsPachete").compara_versiuni(a, b)


def text_data(data):
	"""„2026-11-04” sau „04.11.2026” -> „4 noiembrie 2026”, cu luna in limba receptorului; "" cand nu are forma."""
	m = _RX_DATA_ISO.match(data or "")
	if m:
		an, luna, zi = int(m.group(1)), int(m.group(2)), int(m.group(3))
	else:
		m = _RX_DATA_RO.match(data or "")
		if not m:
			return ""
		zi, luna, an = int(m.group(1)), int(m.group(2)), int(m.group(3))
	if not 1 <= luna <= 12 or not 1 <= zi <= 31:
		return ""
	return "%d %s %d" % (zi, _t(LUNI[luna - 1]), an)


def versiune_cu_data(versiune, data):
	t = text_data(data)
	return "%s (%s)" % (versiune, t) if t else u"%s" % versiune


def data_din_jurnal(versiune, rad=None):
	"""Data versiunii din jurnalul imaginii (/usr/share/enigma2/jurnal-versiuni.json); "" cand nu e acolo."""
	try:
		with open(os.path.join(rad or _rad(), "usr/share/enigma2/jurnal-versiuni.json"), "r", encoding="utf-8") as f:
			for v in json.load(f).get("versiuni") or []:
				if v.get("versiune") == versiune:
					return v.get("data") or ""
	except (IOError, OSError, ValueError, AttributeError):
		pass
	return ""


def versiunea_acum(rad=None):
	"""Versiunea care ruleaza acum (a pachetului enigma2-hdsatelit), altfel imaginea scrisa."""
	i = _modul("HdsActualizari").imaginea(rad or _rad())
	return i.get("versiune") or i.get("baza") or ""


def masina_acum(rad=None):
	"""machinebuild= din regulile modelului: singura sursa buna (/etc/hostname si SystemInfo cad pe nume vechi)."""
	reguli = _paza().citesteReguli(rad or _rad()) or {}
	m = reguli.get("machinebuild") or ""
	return m if _RX_MASINA.match(m) else ""


# ---------------------------------------------------------------- lista semnata

def adresa_lista(canal):
	return "%s/feed/%s/%s" % (SERVER, canal if canal in ("proba", "public") else "public", NUME_LISTA)


def valideaza_lista(d):
	"""Lista greselilor unei liste semnate (goala = buna); aceleasi reguli ca unelte/stb/fa_lista_imagini.py."""
	if not isinstance(d, dict):
		return ["nu e obiect"]
	g = []
	if d.get("format") != FORMAT:
		g.append("format")
	imagini = d.get("imagini")
	if not isinstance(imagini, list):
		return g + ["imagini"]
	for x in imagini:
		if not isinstance(x, dict) or not _RX_MASINA.match(u"%s" % x.get("masina", "")) or \
				not _RX_VERSIUNE.match(u"%s" % x.get("versiune", "")) or \
				not _RX_FISIER.match(u"%s" % x.get("fisier", "")) or not _RX_ADRESA.match(u"%s" % x.get("adresa", "")) or \
				not str(x.get("adresa", "")).endswith("/" + str(x.get("fisier", ""))) or \
				not _RX_SHA256.match(u"%s" % x.get("sha256", "")) or not isinstance(x.get("marime"), int) or \
				isinstance(x.get("marime"), bool) or x.get("marime") <= 0:
			g.append("imagine")
			break
	if not isinstance(d.get("date_versiuni", {}), dict):
		g.append("date_versiuni")
	return g


class _RedirectSigur(HTTPRedirectHandler):
	def __init__(self, oficial=True):
		self.oficial = oficial

	def redirect_request(self, req, fp, code, msg, headers, newurl):
		if self.oficial and urlsplit(newurl).scheme.lower() != "https":
			raise URLError("redirect fara HTTPS")
		nou = HTTPRedirectHandler.redirect_request(self, req, fp, code, msg, headers, newurl)
		if nou is not None and urlsplit(req.full_url).netloc.lower() != urlsplit(newurl).netloc.lower():
			nou.remove_header("Authorization")
		return nou


def _deschide(cerere, timeout, oficial=True):
	if oficial and urlsplit(cerere.full_url).scheme.lower() != "https":
		raise URLError("adresa fara HTTPS")
	return build_opener(_RedirectSigur(oficial)).open(cerere, timeout=timeout)


def _cere(adresa, credentiale, maxim, deschide=None, timp=TIMP_LISTA):
	"""(corp, None) sau (None, cod): cod = FARA_RASPUNS sau EROARE. Numai GET; fara parole in mesaje."""
	import base64
	antete = {"User-Agent": UA, "Accept": "*/*", "Cache-Control": "no-cache"}
	if credentiale:
		antete["Authorization"] = "Basic " + base64.b64encode(("%s:%s" % credentiale).encode("utf-8")).decode("ascii")
	try:
		r = (deschide or _deschide)(Request(adresa, headers=antete), timeout=timp)
		try:
			corp = r.read(maxim + 1)
		finally:
			r.close()
	except HTTPError as e:
		return None, FARA_RASPUNS if e.code >= 500 else EROARE
	except (URLError, HTTPException, socket.timeout, socket.error, OSError, ValueError):
		return None, FARA_RASPUNS
	if len(corp) > maxim:
		return None, EROARE
	return corp, None


def citeste_lista(canal="public", credentiale=None, deschide=None):
	"""(lista, None) sau (None, cod). Lista trece numai cu semnatura buna, verificata pe octetii primiti. O semnatura care
	nu se potriveste se cere inca o data, impreuna cu lista: publicarea se poate schimba intre cele doua cereri."""
	S = _modul("HdsSemnatura")
	adresa = adresa_lista(canal)
	for _incercare in range(2):
		corp, cod = _cere(adresa, credentiale, MARIME_LISTA_MAX, deschide)
		if cod:
			return None, cod
		semnatura, cod = _cere(adresa + ".sig", credentiale, MARIME_SEMNATURA_MAX, deschide)
		if cod == FARA_RASPUNS:
			return None, cod
		bun, motiv, ident = S.verifica(corp, semnatura, SCOP_LISTA)
		if bun:
			break
		if motiv == S.FARA_VERIFICARE:
			break
	if not bun:
		_jurnal("lista refuzata: %s" % S.text_motiv(motiv, ident))
		return None, NESEMNATA
	try:
		d = json.loads(corp.decode("utf-8"))
	except (ValueError, UnicodeDecodeError):
		return None, NESEMNATA
	g = valideaza_lista(d)
	if g:
		_jurnal("lista semnata, cu forma rea: %s" % ", ".join(g))
		return None, NESEMNATA
	return d, None


def oferta_din_feed(stare, img, canal, rad=None):
	"""Oferta "versiune noua" din stare.json al feedului, sau None: numai o versiune care se instaleaza din meniu (fara
	imagine_noua, pe baza receptorului, pe canalul lui) si mai noua decat cea care ruleaza."""
	if not isinstance(stare, dict) or not isinstance(img, dict) or not img.get("versiune"):
		return None
	if stare.get("imagine_noua") or stare.get("baza") != img.get("baza"):
		return None
	if stare.get("canal") and stare.get("canal") != canal:
		return None
	v = _modul("HdsActualizari").versiunea_starii(stare)
	if not v or compara(v, img["versiune"]) <= 0:
		return None
	return {"fel": "feed", "versiune": v, "data": stare.get("data") or "", "acum": img["versiune"],
		"data_acum": data_din_jurnal(img["versiune"], rad)}


def _baza(versiune):
	"""Baza unei versiuni: primele doua parti ("0.7.2" -> "0.7"), ca HdsCopieSetari.baza_versiunii; "" cand nu are forma."""
	parti = u"%s" % (versiune or "")
	parti = parti.split(".")
	return ".".join(parti[:2]) if len(parti) >= 3 and all(p.isdigit() for p in parti[:3]) else ""


def alege_oferta(imagine, feed):
	"""Intre imaginea completa si actualizarea din feed. Feedul cand aduce cel putin aceeasi versiune: pune numai
	pachetele, fara stick si fara instalare de la zero, deci setarile si pluginurile raman pe loc. Imaginea completa
	numai cand e mai noua decat ce da feedul (o baza noua) sau cand feedul nu are nimic. (09.11.2026, darog69: 0.7.2
	era si in feed, dar fereastra a pus imaginea de la zero si setarile s-au pierdut.)"""
	if feed and (not imagine or compara(feed["versiune"], imagine["versiune"]) >= 0):
		return feed
	return imagine


def alege_imaginea(lista, masina, acum, canal="public"):
	"""Cea mai noua imagine a modelului `masina`, numai mai noua decat `acum`; None cand nu e. „forteaza” (o proba pe
	canalul de proba) lasa si aceeasi versiune; pe canalul public nu inseamna nimic."""
	alese = None
	for x in (lista or {}).get("imagini") or []:
		if x.get("masina") != masina:
			continue
		if acum and compara(x["versiune"], acum) <= 0 and not (canal == "proba" and x.get("forteaza") is True):
			continue
		if alese is None or compara(x["versiune"], alese["versiune"]) > 0:
			alese = x
	return alese


# ---------------------------------------------------------------- imaginile altor echipe (date de un plugin)

_STRAINE = {}


def _curat(text, maxim=MAX_NUME_STRAIN):
	return re.sub(r"[\x00-\x1f\x7f]", "", u"%s" % (text or "")).strip()[:maxim]


def inregistreaza_imagini(sectiune, imagini):
	"""Pentru pluginuri: lista imaginilor unei sectiuni, inlocuieste ce avea sectiunea. Se cheama oricand, de pe firul enigma2;
	lista ramane pana la scoate_imagini sau pana la repornirea interfetei, deci pluginul o da la fiecare pornire.
	`sectiune`: titlul sectiunii, deja tradus de plugin (de pilda cel pe care il arata el).
	`imagini`: lista de dict-uri:
		nume     textul aratat, de pilda numele echipei si al imaginii; obligatoriu
		versiune textul versiunii; obligatoriu
		adresa   adresa http:// sau https:// a arhivei .zip (cu kernel.bin si rootfs.tar.bz2 in acelasi dosar); obligatorie
		model    machinebuild, text sau lista (viper4kv20, sf8008); se arata numai pe modelul acesta; obligatoriu
		sha256   suma arhivei, 64 de semne hex; daca e data, se verifica pe stick; fara ea, nu se verifica nimic
		marime   marimea arhivei in octeti; fara ea se cere de la server
	Intoarce cate intrari a primit; una rea se lasa deoparte si se scrie in jurnal. Lista goala scoate sectiunea."""
	bune = []
	for x in imagini or []:
		try:
			nume, versiune = _curat(x.get("nume")), _curat(x.get("versiune"), 30)
			adresa = u"%s" % (x.get("adresa") or "")
			model = x.get("model")
			modele = [model] if isinstance(model, str) else list(model or [])
			suma = (u"%s" % (x.get("sha256") or "")).strip().lower()
			marime = x.get("marime") or 0
			if not nume or not versiune or not _RX_URL.match(adresa) or not modele or \
					not all(isinstance(m, str) and _RX_MASINA.match(m) for m in modele) or \
					(suma and not _RX_SHA256.match(suma)) or not isinstance(marime, int) or isinstance(marime, bool) or marime < 0:
				raise ValueError("forma")
		except (AttributeError, TypeError, ValueError) as e:
			_jurnal("o imagine straina lasata deoparte (%s): %s" % (e, _curat(x, 120)))
			continue
		cale = adresa.split("?", 1)[0].rsplit("/", 1)[-1]
		fisier = re.sub(r"[^A-Za-z0-9._-]", "_", cale).lstrip("._")[-120:] or "imagine.zip"
		fisier = hashlib.sha256(adresa.encode("utf-8")).hexdigest()[:16] + "-" + fisier
		ident = hashlib.sha256(json.dumps([_curat(sectiune), nume, versiune, adresa, modele, suma, marime],
			ensure_ascii=True, sort_keys=True).encode("utf-8")).hexdigest()[:16]
		bune.append({"id": ident, "sectiune": _curat(sectiune), "nume": nume, "versiune": versiune, "url": adresa, "modele": modele,
			"sha256": suma, "marime": marime, "fisier": fisier, "straina": True})
	cheie = _curat(sectiune)
	if bune:
		_STRAINE[cheie] = bune
	else:
		_STRAINE.pop(cheie, None)
	return len(bune)


def scoate_imagini(sectiune=None):
	"""Pentru pluginuri: scoate o sectiune (omul a oprit-o); fara sectiune, toate."""
	if sectiune is None:
		_STRAINE.clear()
	else:
		_STRAINE.pop(_curat(sectiune), None)


def imagini_straine(masina=None):
	"""Intrarile date de pluginuri pentru modelul acesta, in ordinea sectiunilor."""
	masina = masina_acum() if masina is None else masina
	return [x for s in sorted(_STRAINE) for x in _STRAINE[s] if masina in x["modele"]]


def numele_strainei(x):
	return "%s %s" % (x["nume"], x["versiune"])


def text_avertisment_strain(x):
	"""Intrebarea de la OK, cu „Nu” ales: aceleasi fraze ca la imaginea altora de pe stick. Fraza copiei sta dupa un rand gol:
	acolo fereastra intrebarilor are randurile ei mai mici, iar intrebarea ramane la vedere si in limbile cu fraze lungi."""
	return "\n".join((_t(T_STRAINA) % numele_strainei(x), _t(T_STRAINA_MODEL), _t(T_STRAINA_INTREBARE))) + "\n\n" + _t(T_STRAINA_COPIE)


def marime_de_pe_server(adresa, deschide=None):
	"""Marimea arhivei spusa de server (HEAD), None cand nu o spune."""
	try:
		cerere = Request(adresa, headers={"User-Agent": UA})
		cerere.get_method = lambda: "HEAD"
		r = deschide(cerere, timeout=TIMP_LISTA) if deschide else _deschide(cerere, timeout=TIMP_LISTA, oficial=False)
		try:
			n = _intreg(r.headers.get("Content-Length"))
		finally:
			r.close()
	except (URLError, HTTPException, socket.timeout, socket.error, OSError, ValueError):
		return None
	return n if n > 0 else None


# ---------------------------------------------------------------- locul in care se scrie

def _camp(cmdline, cheie):
	for cuvant in (cmdline or "").split():
		if cuvant.startswith(cheie + "="):
			return cuvant[len(cheie) + 1:]
	return ""


def _refuz_loc(motiv):
	return {"bun": False, "motiv": motiv}


def tinta_scriere(cmdline, reguli=None):
	"""Locul din care ruleaza imaginea, din /proc/cmdline si partitiile date de bootloader:
	{"bun": True, "kernel", "radacina", "subdosar", "loc", "argumente"} sau {"bun": False, "motiv"}. Se scrie numai aici:
	nucleul si radacina se dau explicit programului de scriere, cu -m<N> numai cand sistemul sta in subdosarul
	linuxrootfs<N> (fara el programul refuza dispozitivul dat). Numai pe partitii cu numele asteptate; de pe stick, de pe
	disc, cu UUID sau cu alt nume de subdosar nu se scrie."""
	H = _paza()
	reguli = reguli or {}
	radacina = _camp(cmdline, "root")
	kernel = _camp(cmdline, "kernel")
	subdosar = _camp(cmdline, "rootsubdir")
	if radacina.startswith("/dev/sd") or kernel.startswith("/dev/sd"):
		return _refuz_loc("stick")
	if not _RX_MMC.match(radacina):
		return _refuz_loc("radacina necunoscuta")
	partitii = H.partitiiDinCmdline(cmdline) or []
	nume = dict((i + 1, p[0]) for i, p in enumerate(partitii))

	def numele(dispozitiv):
		m = _RX_MMC.match(dispozitiv or "")
		return nume.get(int(m.group(1))) if m else None

	def locul(partitie):
		for i, p in enumerate(partitii):
			if p[0] == partitie:
				return "/dev/mmcblk0p%d" % (i + 1)
		return ""
	if subdosar:
		m = _RX_LOC.match(subdosar)
		if not m:
			return _refuz_loc("subdosar necunoscut")
		loc = int(m.group(1))
		if not _RX_MMC.match(kernel) or numele(kernel) != "linuxkernel%d" % loc or numele(radacina) != "userdata":
			return _refuz_loc("partitiile nu sunt ale locului %d" % loc)
	else:
		loc = 0
		n_kernel = reguli.get("kernel_name") or "kernel"
		n_rootfs = reguli.get("rootfs_name") or "rootfs"
		if not _RX_NUME_PARTITIE.match(n_kernel) or not _RX_NUME_PARTITIE.match(n_rootfs):
			return _refuz_loc("nume de partitii ciudate")
		if numele(radacina) != n_rootfs:
			return _refuz_loc("radacina nu e pe partitia ei")
		dupa_nume = locul(n_kernel)
		if kernel and kernel != dupa_nume:
			return _refuz_loc("nucleul nu e pe partitia lui")
		kernel = dupa_nume
		if not kernel:
			return _refuz_loc("lipseste partitia nucleului")
		for cheie, valoare in (("kernel_part", kernel), ("rootfs_part", radacina)):
			din_reguli = reguli.get(cheie)
			if din_reguli and "/dev/" + din_reguli != valoare:
				return _refuz_loc("regulile modelului spun alt loc")
	argumente = ["-k" + kernel[len("/dev/"):], "-r" + radacina[len("/dev/"):]]
	if loc:
		argumente.append("-m%d" % loc)
	return {"bun": True, "kernel": kernel, "radacina": radacina, "subdosar": subdosar, "loc": loc, "argumente": argumente}


def radacina_e_aceea(tinta, stat=os.stat):
	"""True numai daca sistemul care ruleaza sta chiar pe dispozitivul din /proc/cmdline. O eroare inseamna nu."""
	try:
		return stat("/").st_dev == stat(tinta["radacina"]).st_rdev
	except (OSError, KeyError):
		return False


def citeste_tinta(rad=None, verifica_radacina=True):
	"""Locul de acum, pentru acest receptor."""
	rad = rad or _rad()
	try:
		with open(os.path.join(rad, "proc/cmdline")) as f:
			cmdline = f.read(8192)
	except (IOError, OSError, ValueError):
		return _refuz_loc("/proc/cmdline")
	tinta = tinta_scriere(cmdline, _paza().citesteReguli(rad))
	if tinta.get("bun") and verifica_radacina and not radacina_e_aceea(tinta, _STAT):
		return _refuz_loc("sistemul nu ruleaza de pe dispozitivul din /proc/cmdline")
	return tinta


_STAT = os.stat


def simulare_buna(iesire, tinta, dosar):
	"""Verificarea proprie a simularii, din text (programul scrie „Successfully flashed” si cand nu scrie nimic): exact un
	nucleu si un sistem, cele din `dosar`, numai dispozitivele locului, subdosarul locului, nicio eroare si niciun semn ca ar
	scrie altundeva. Orice alta forma inseamna nu."""
	randuri = [r.strip() for r in (iesire or "").splitlines()]
	text = "\n".join(randuri).lower()
	if not randuri or "flashing currently not running image" in text:
		return False
	if any(x in text for x in ("error", "not found", "missing", "no such file")):
		return False
	nuclee, sisteme, kernele, radacini = [], [], [], []
	for r in randuri:
		for inceput, lista in (("Found kernel file: ", nuclee), ("Found rootfs file: ", sisteme),
				("Found tar.xz rootfs file: ", sisteme), ("Found nfi file: ", sisteme)):
			if r.startswith(inceput):
				lista.append(r[len(inceput):].strip())
		m = re.match(r"^Using (\S+) as (kernel|rootfs) device$", r)
		if m:
			(kernele if m.group(2) == "kernel" else radacini).append(m.group(1))
		m = re.match(r"^(?:Using|Found) cmdLine (kernel|rootfs) device: (\S+)$", r)
		if m:
			(kernele if m.group(1) == "kernel" else radacini).append(m.group(2))
	try:
		baza = os.path.realpath(dosar)
	except (OSError, ValueError):
		baza = dosar
	if len(nuclee) != 1 or len(sisteme) != 1 or \
			os.path.normpath(nuclee[0]) != os.path.normpath(os.path.join(baza, "kernel.bin")) or \
			os.path.normpath(sisteme[0]) != os.path.normpath(os.path.join(baza, "rootfs.tar.bz2")):
		return False
	if not kernele or not radacini or set(kernele) != set([tinta["kernel"]]) or set(radacini) != set([tinta["radacina"]]):
		return False
	subdosare = [r[len("Current root sub dir is:"):].strip() for r in randuri if r.startswith("Current root sub dir is:")]
	if tinta["subdosar"]:
		return tinta["subdosar"] in subdosare and set(subdosare) == set([tinta["subdosar"]]) and \
			("Flashing multiboot partition %d" % tinta["loc"]) in randuri
	return not any(subdosare)


# ---------------------------------------------------------------- stickul

def _montari():
	"""Textul lui /proc/mounts; probele dau MONTARI."""
	if MONTARI is not None:
		return MONTARI
	with open("/proc/mounts", encoding="utf-8", errors="surrogateescape") as f:
		return f.read()


MONTARI = None


def e_pe_stick(cale):
	"""True numai daca `cale` sta pe un stick USB: nici memoria interna, nici RAM-ul, nici ceva necunoscut."""
	M = _mediu()
	permis, motiv, _dispozitiv, _punct = M.verificaMediuScriere(cale, textMontari=_montari(), stat=_STAT)
	return bool(permis) and motiv == M.PERMIS_USB


def loc_liber(dosar):
	try:
		s = os.statvfs(dosar)
	except (AttributeError, OSError):
		return None
	return s.f_bavail * s.f_frsize


def loc_necesar(imagine):
	"""Arhiva, pachetul scos din ea (cat arhiva: fisierele sunt deja comprimate) si copia, cu rezerva."""
	return 2 * imagine["marime"] + REZERVA_LOC


def stickuri(rad=None):
	"""Punctele de montare ale stickurilor USB, cu locul liber: [(punct, liber)]. Discurile si memoria interna nu intra."""
	C = _modul("HdsCopieSetari")
	rez = []
	for m in C.medii(rad or _rad()):
		if m.get("fel") == "stick" and e_pe_stick(m["punct"]):
			rez.append((m["punct"], loc_liber(m["punct"])))
	return rez


def dosar_imagine(punct):
	return os.path.join(punct, *DOSAR_PE_STICK.split("/"))


def curata_imaginile_vechi(punct, pastreaza=None):
	"""Scoate de pe stick arhivele luate de aici pentru alte versiuni si dosarul curat; lasa arhiva in lucru."""
	dosar = dosar_imagine(punct)
	try:
		for nume in os.listdir(dosar):
			if pastreaza and nume in (pastreaza, pastreaza + SUFIX_PARTIAL):
				continue
			if nume.endswith((".zip", ".zip" + SUFIX_PARTIAL)):
				os.remove(os.path.join(dosar, nume))
	except OSError:
		pass
	shutil.rmtree(os.path.join(punct, FOLDER_CURAT), ignore_errors=True)


def alege_stick(imagine, rad=None):
	"""(punct, None) sau (None, textul pentru om): stickul cu cel mai mult loc; arhiva inceputa de pe el conteaza ca loc."""
	lista = stickuri(rad)
	if not lista:
		return None, _t(T_FARA_STICK)

	def loc_real(punct, liber):
		if liber is None:
			return 0
		n = 0
		for sufix in ("", SUFIX_PARTIAL):
			try:
				n = max(n, os.path.getsize(os.path.join(dosar_imagine(punct), imagine["fisier"] + sufix)))
			except OSError:
				pass
		return liber + n
	lista.sort(key=lambda x: loc_real(x[0], x[1]), reverse=True)
	punct, liber = lista[0]
	if loc_real(punct, liber) < loc_necesar(imagine):
		return None, _t(T_FARA_LOC) % (loc_necesar(imagine) // (1024 * 1024) + 1)
	motiv, punct = motiv_nume_stick(punct)
	if motiv:
		return None, _t(T_NUME_STICK)
	return punct, None


def motiv_nume_stick(cale, muta=True):
	"""(motiv, cale): muta montarea nesigura si pastreaza o cale buna, inclusiv cand lista mediilor da calea fizica."""
	M = _mediu()
	motiv, punct = M.verificaNumeStick(cale, textMontari=_montari())
	if muta and motiv in (M.REFUZ_SPATII, M.REFUZ_SEMNE) and punct:
		reala = posixpath.normpath(os.path.realpath(cale))
		try:
			if M.mutaMontarea(punct):
				nou = posixpath.join(posixpath.dirname(punct), re.sub(r"[^A-Za-z0-9._+,:@=-]", "", posixpath.basename(punct)))
				if posixpath.normpath(cale) == reala and (reala == punct or reala.startswith(punct + "/")):
					cale = nou + reala[len(punct):]
				motiv, _punct = M.verificaNumeStick(cale, textMontari=_montari())
		except (IOError, OSError) as e:
			_jurnal("montarea nu s-a mutat: %s" % e)
	return motiv, cale


# ---------------------------------------------------------------- descarcarea, cu reluare

def _sterge(cale):
	try:
		os.remove(cale)
	except OSError:
		pass


def _intreg(valoare, implicit=-1):
	try:
		return int(valoare)
	except (TypeError, ValueError):
		return implicit


def _start_range(antet):
	"""(inceput, total) din „bytes 100-199/1000”; (None, None) cand nu are forma."""
	m = re.match(r"^bytes ([0-9]+)-[0-9]+/([0-9]+)$", (antet or "").strip())
	return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def descarca(imagine, dosar, credentiale=None, progres=None, oprit=None, deschide=None, timp=TIMP_DESCARCARE,
		pauza=PAUZA_INCERCARE_S, dormi=time.sleep):
	"""Descarca arhiva in <dosar>/<fisier>.partial, reluand de unde a ramas. Intoarce (cale, None), cu fisierul gata, inca
	nerecitit, sau (None, cod): cod = retea (legatura cazuta de prea multe ori, .partial ramane), lipsa (404), loc,
	stick, marime sau oprit. La 200 pe o cerere cu Range se ia de la zero; la 416 fisierul inceput se sterge."""
	import base64
	marime = imagine["marime"]
	cale = os.path.join(dosar, imagine["fisier"])
	partial = cale + SUFIX_PARTIAL
	try:
		os.makedirs(dosar, exist_ok=True)
		if os.path.isfile(cale):
			if os.path.getsize(cale) == marime:
				return cale, None
			os.remove(cale)
		n = os.path.getsize(partial) if os.path.isfile(partial) else 0
	except OSError:
		return None, "stick"
	if n > marime:
		_sterge(partial)
		n = 0
	antete_baza = {"User-Agent": UA, "Accept": "application/octet-stream", "Cache-Control": "no-cache"}
	if credentiale and not imagine.get("straina"):
		antete_baza["Authorization"] = "Basic " + base64.b64encode(("%s:%s" % credentiale).encode("utf-8")).decode("ascii")
	adresa = imagine.get("url") or SERVER + imagine["adresa"]
	fara_progres = 0
	incercari = 0
	while n < marime:
		incercari += 1
		if oprit is not None and oprit():
			return None, "oprit"
		antete = dict(antete_baza)
		if n:
			antete["Range"] = "bytes=%d-" % n
		inainte = n
		try:
			cerere = Request(adresa, headers=antete)
			r = deschide(cerere, timeout=timp) if deschide else _deschide(cerere, timeout=timp, oficial=not imagine.get("straina"))
			try:
				cod = r.getcode()
				if n and cod == 206:
					inceput, total = _start_range(r.headers.get("Content-Range"))
					if inceput != n or total != marime:
						return None, "marime"
				elif cod == 200:
					if n:
						_jurnal("serverul a dat tot fisierul: descarcarea o ia de la zero")
					n = 0
				else:
					return None, "marime"
				mod = "ab" if n else "wb"
				try:
					f = open(partial, mod)
				except (IOError, OSError):
					return None, "stick"
				with f:
					din_sync = 0
					while n < marime:
						if oprit is not None and oprit():
							return None, "oprit"
						# socket.timeout si caderile de retea se prind mai jos; o scriere cazuta inseamna stickul
						bucata = r.read(min(BLOC, marime - n))
						if not bucata:
							break
						try:
							f.write(bucata)
							din_sync += len(bucata)
							n += len(bucata)
							if din_sync >= FSYNC_LA:
								f.flush()
								os.fsync(f.fileno())
								din_sync = 0
						except (IOError, OSError) as e:
							return None, "loc" if e.errno == errno.ENOSPC else "stick"
						if progres is not None:
							progres(n, marime)
					try:
						f.flush()
						os.fsync(f.fileno())
					except (IOError, OSError) as e:
						return None, "loc" if e.errno == errno.ENOSPC else "stick"
			finally:
				try:
					r.close()
				except Exception:
					pass
		except HTTPError as e:
			if e.code == 416:
				_sterge(partial)
				n = 0
			elif e.code in (401, 403, 404, 410):
				return None, "lipsa"
		except (URLError, HTTPException, socket.timeout, socket.error, OSError, ValueError, EOFError):
			pass
		if n >= marime:
			break
		fara_progres = fara_progres + 1 if n <= inainte else 0
		if fara_progres >= INCERCARI_FARA_PROGRES or incercari >= INCERCARI_DESCARCARE:
			return None, "retea"
		dormi(pauza)
	if n != marime:
		return None, "marime"
	try:
		os.rename(partial, cale)
	except OSError:
		return None, "stick"
	return cale, None


def goleste_cache(cale):
	"""Fisierul se scoate din memoria sistemului, ca urmatoarea citire sa vina chiar de pe stick."""
	fd = os.open(cale, os.O_RDONLY)
	try:
		os.fsync(fd)
		if hasattr(os, "posix_fadvise"):
			os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
	finally:
		os.close(fd)


def suma_de_pe_stick(cale, oprit=None):
	"""(sha256, marime) citite din fisierul de pe stick, dupa golirea cache-ului."""
	goleste_cache(cale)
	h = hashlib.sha256()
	n = 0
	with open(cale, "rb") as f:
		while True:
			if oprit is not None and oprit():
				return None, n
			bucata = f.read(BLOC)
			if not bucata:
				break
			h.update(bucata)
			n += len(bucata)
	return h.hexdigest(), n


def _nume_din_zip(z, cu_marcaj=True):
	"""{nume din NUME_PACHET: numele adevarat din arhiva}: dosarul care are si nucleul, si sistemul, si marcajul. Arhivele
	publice il tin in dosarul pe care il cauta Maintenance Mode (amiko/viper4kv20, octagon/sf8008) sau in e2/update; cu mai
	multe dosare se ia primul, iar marcajul si sumele hotarasc oricum daca e cel bun. Imaginile altora n-au marcaj: acolo
	ajung nucleul si sistemul, cu e2/update intai."""
	dosare = {}
	ordine = []
	for n in z.namelist():
		curat = n.replace("\\", "/")
		dosar, _bara, scurt = curat.rpartition("/")
		if scurt in NUME_PACHET:
			if dosar not in dosare:
				dosare[dosar] = {}
				ordine.append(dosar)
			dosare[dosar].setdefault(scurt, n)
	cerute = ("kernel.bin", "rootfs.tar.bz2") + ((NUME_MARCAJ,) if cu_marcaj else ())
	bune = [d for d in ordine if all(x in dosare[d] for x in cerute)]
	if not cu_marcaj:
		bune.sort(key=lambda d: 0 if d == "/".join(SUBCALE_UPDATE) or d.endswith("/" + "/".join(SUBCALE_UPDATE)) else 1)
	return dosare[bune[0]] if bune else {}


def dosar_curat(punct):
	return os.path.join(punct, FOLDER_CURAT, *SUBCALE_UPDATE)


def scoate_pachetul(cale_zip, punct, oprit=None, cu_marcaj=True):
	"""Numai cele patru fisiere ale pachetului in dosarul curat de pe stick (golit intai). Intoarce dosarul."""
	tinta = dosar_curat(punct)
	shutil.rmtree(tinta, ignore_errors=True)
	os.makedirs(tinta, exist_ok=True)
	with zipfile.ZipFile(cale_zip) as z:
		nume = _nume_din_zip(z, cu_marcaj)
		if not nume:
			raise ValueError("arhiva nu are pachetul")
		for scurt in NUME_PACHET:
			if scurt not in nume:
				continue
			with z.open(nume[scurt]) as sursa, open(os.path.join(tinta, scurt), "wb") as dest:
				while True:
					if oprit is not None and oprit():
						raise ValueError("oprit")
					bucata = sursa.read(BLOC)
					if not bucata:
						break
					dest.write(bucata)
				dest.flush()
				os.fsync(dest.fileno())
	return tinta


def citeste_marcaj(dosar):
	H = _paza()
	try:
		cale = os.path.join(dosar, NUME_MARCAJ)
		if os.path.getsize(cale) > H.MARIME_MAXIMA_TEXT:
			return ""
		with open(cale, "rb") as f:
			return f.read().decode("utf-8", "replace")
	except OSError:
		return None


def verifica_pachetul(dosar, imagine, rad=None, oprit=None):
	"""(semnul fisierelor, None) sau (None, textul pentru om): marcajul pentru acest receptor, versiunea si modelul cele din
	lista semnata, sumele din marcaj, citite de pe stick."""
	H = _paza()
	text_marcaj = citeste_marcaj(dosar)
	straina = imagine.get("straina")
	if straina and text_marcaj is None:
		return H.semnFisiere(dosar), None
	cod, _text, marcaj = H.verificaPachet(text_marcaj, radacina=rad or RADACINA)
	if cod != H.PACHET_BUN:
		_jurnal("marcajul: %s" % cod)
		return None, _t(T_ALT_RECEPTOR)
	if not straina and (marcaj.get("machinebuild") != imagine.get("masina") or marcaj.get("version") != imagine.get("versiune")):
		_jurnal("marcajul e pentru %s %s, lista spune %s %s" % (marcaj.get("machinebuild"), marcaj.get("version"),
			imagine.get("masina"), imagine.get("versiune")))
		return None, _t(T_ALT_RECEPTOR)
	semn = H.semnFisiere(dosar)
	for nume in ("kernel.bin", "rootfs.tar.bz2"):
		goleste_cache(os.path.join(dosar, nume))
	sume = H.sumeSha256(dosar, oprit=oprit)
	if sume is None or H.sumeGresite(marcaj, sume) or H.semnFisiere(dosar) != semn:
		return None, _t(T_NEPOTRIVIT)
	return semn, None


# ---------------------------------------------------------------- copia completa

def pluginuri_de_om(rad=None):
	"""Numele pluginurilor puse de om (ca Components/HdsReinstalare.pluginuri_puse_de_om, si pe imaginile vechi)."""
	try:
		R = _modul("HdsReinstalare")
		if not hasattr(R, "pluginuri_puse_de_om"):
			raise ImportError("HdsReinstalare")
	except ImportError:
		R = _langa("HdsReinstalare")
	return R.pluginuri_puse_de_om(rad or _rad())


def completeaza_pluginurile(dosar_copie, rad=None):
	"""O copie facuta de o imagine veche nu are randul pluginuri=: il primeste aici, ca imaginea noua sa le puna la loc."""
	C = _modul("HdsCopieSetari")
	cale = os.path.join(dosar_copie, C.DESCRIERE)
	with open(cale, "rb") as f:
		text = f.read().decode("ascii", "replace")
	if re.search(r"^pluginuri=", text, re.M):
		return False
	rand = "pluginuri=%s" % ",".join(pluginuri_de_om(rad))
	parti = text.split("\nmd5 ", 1)
	nou = parti[0] + "\n" + rand + ("\nmd5 " + parti[1] if len(parti) > 1 else "\n")
	C._scrie_atomic(cale, nou.encode("ascii", "replace"))
	return True


def fa_copia_verificata(punct, text_setari, rad=None):
	"""(dosarul copiei, None) sau (None, motiv): copia completa pe stick, apoi recitita de acolo fisier cu fisier."""
	C = _modul("HdsCopieSetari")
	kw = {"fel": "automata"}
	if rad:
		kw["rad"] = rad
	# 0.7.4: pluginurile puse din fisiere, care nu sunt in feeduri, intra in copie cu pachetul lor refacut (dupa imaginea
	# noua se instaleaza din copie). Modulul copiei de pe imaginile vechi (puntea) nu stie parametrul.
	if getattr(C, "FA_COPIA_REFACE_PACHETE", False):
		kw["reface_pachete"] = True
	rez = C.fa_copia(punct, text_setari, **kw)
	if not rez.get("ok") or not rez.get("cale"):
		return None, " ".join(rez.get("mesaje") or []) or "copia"
	dosar = rez["cale"]
	completeaza_pluginurile(dosar, rad)
	for nume in os.listdir(dosar):
		goleste_cache(os.path.join(dosar, nume))
	# cu regulile punerii la loc, nu numai md5: o copie pe care prima pornire ar refuza-o opreste scrierea acum
	verifica = getattr(C, "verifica_punerea", None) or C.verifica_copia
	motiv = verifica(dosar)
	if motiv:
		return None, motiv
	return dosar, None


# ---------------------------------------------------------------- scrierea

def comanda_simulare(tinta, dosar):
	return [CALE_PROGRAM, "-n"] + tinta["argumente"] + [dosar]


def simuleaza(tinta, dosar, ruleaza=None):
	"""Iesirea simularii (-n: nu scrie nimic), cu aceleasi argumente ca scrierea."""
	p = (ruleaza or subprocess.run)(comanda_simulare(tinta, dosar), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
		stderr=subprocess.STDOUT, timeout=120)
	iesire = p.stdout
	return iesire.decode("utf-8", "replace") if isinstance(iesire, bytes) else (iesire or "")


def comanda_scriere(tinta, dosar):
	"""Comanda shell a scrierii. init 4 opreste enigma2; daca programul se intoarce (n-a scris, n-a repornit), interfata
	revine singura, ca receptorul sa nu ramana cu ecranul negru."""
	return ("sync; echo '[hds] init 4'; init 4; sleep 3; echo '[hds] pornesc scrierea'; %s; cod=$?; "
		"echo \"[hds] programul s-a intors, cod: $cod\"; sync; sleep 5; init 3") % " ".join(
		[shlex.quote(CALE_PROGRAM)] + [shlex.quote(a) for a in tinta["argumente"]] + [shlex.quote(dosar)])


def lanseaza(comanda, cale_jurnal, env_ofgwrite=None):
	"""Comanda, detasata de acest proces, intr-o sesiune noua: init opreste la schimbarea nivelului tot grupul de procese al
	lui enigma2.sh, iar o comanda pornita simplu cu „&” moare odata cu enigma2 (receptorul ramane cu ecranul negru)."""
	with open(cale_jurnal, "wb") as jurnal:
		subprocess.Popen(["/bin/sh", "-c", comanda], stdin=subprocess.DEVNULL, stdout=jurnal, stderr=subprocess.STDOUT,
			close_fds=True, start_new_session=True, env=env_ofgwrite)


def scrie_semnul_scrierii(punct, imagine, tinta, din_standby=False, copie=None):
	"""Ce trebuie sa se vada la pornirea urmatoare; pe stick, fiindca radacina se rescrie."""
	identitate = None
	if copie:
		C = _modul("HdsCopieSetari")
		d = C.citeste_descriere(copie)
		if d is None:
			raise IOError("copie fara descriere")
		# Merge si cu modulul copiei de pe imaginile vechi, folosit de punte.
		identitate = {"nume": os.path.basename(copie.rstrip("/\\")), "descriere": C._md5(os.path.join(copie, C.DESCRIERE)),
			"amprenta": d["amprenta"], "model": d["model"]}
	cale = os.path.join(dosar_imagine(punct), FIS_SCRIERE)
	with open(cale + ".nou", "w", encoding="utf-8") as f:
		json.dump({"versiune": imagine["versiune"], "sha256": imagine.get("sha256", ""), "kernel": tinta["kernel"], "radacina": tinta["radacina"],
			"subdosar": tinta["subdosar"], "cand": int(time.time()), "din_standby": bool(din_standby),
			"straina": bool(imagine.get("straina")),
			"copie": identitate}, f, sort_keys=True)
		f.flush()
		os.fsync(f.fileno())
	os.replace(cale + ".nou", cale)


def cheia_scrierii(imagine, tinta):
	return [imagine.get("versiune"), imagine.get("sha256", "")] + [tinta.get(c) for c in ("kernel", "radacina", "subdosar")]


def semn_oferta(oferta):
	return hashlib.sha256(json.dumps(oferta, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest()


def scrieri_esuate(punct):
	try:
		with open(os.path.join(dosar_imagine(punct), FIS_ESEC), encoding="utf-8") as f:
			return json.load(f)
	except (IOError, OSError, ValueError):
		return []


def verifica_dupa_scriere(punct, rad=None):
	"""Dupa pornire: None cand pe stick nu e nicio scriere de verificat; altfel {"bun", "scris", "din_standby", "acum"}.
	Bun = versiunea e cel putin cea scrisa si receptorul ruleaza din acelasi loc. Semnul se sterge, iar dosarul curat la fel:
	imaginea descarcata ramane pe stick pana la urmatoarea actualizare."""
	cale = os.path.join(dosar_imagine(punct), FIS_SCRIERE)
	try:
		with open(cale, "r", encoding="utf-8") as f:
			d = json.load(f)
	except (IOError, OSError, ValueError):
		return None
	if d.get("straina") and abs(time.time() - _intreg(d.get("cand"), 0)) > SEMN_STRAINA_VALABIL_S:
		# imaginea altora a pornit si acest cod n-a mai rulat de atunci: semnul e vechi, nu spune nimic despre imaginea de acum
		_sterge(cale)
		return None
	acum = versiunea_acum(rad)
	tinta = citeste_tinta(rad, verifica_radacina=False)
	aceeasi = bool(tinta.get("bun")) and all(tinta.get(c) == d.get(c) for c in ("kernel", "radacina", "subdosar"))
	# dupa imaginea altora acest cod nu mai ruleaza: daca ruleaza, n-a scris
	bun = not d.get("straina") and aceeasi and bool(acum) and compara(acum, u"%s" % d.get("versiune")) >= 0
	if not bun:
		esecuri = scrieri_esuate(punct)
		cheie = cheia_scrierii(d, d)
		if cheie not in esecuri:
			esecuri.append(cheie)
			_modul("HdsCopieSetari")._scrie_atomic(os.path.join(dosar_imagine(punct), FIS_ESEC),
				json.dumps(esecuri).encode("utf-8"))
	_jurnal("dupa scriere: scris %s, acum %s, acelasi loc: %s" % (d.get("versiune"), acum, aceeasi))
	_sterge(cale)
	shutil.rmtree(os.path.join(punct, FOLDER_CURAT), ignore_errors=True)
	copie = d.get("copie") if isinstance(d.get("copie"), dict) else None
	return {"bun": bun, "scris": d.get("versiune"), "din_standby": bool(d.get("din_standby")), "acum": acum, "copie": copie}


def copie_gresita_la_pornire(rez, copie):
	"""True cand punerea la loc automata de la prima pornire (rezultat.json, motivul "automat") a luat alta copie decat cea
	facuta chiar inainte de scriere (identitatea din scriere.json): de pilda o copie mai veche de pe un disc montat inaintea
	stickului. Atunci copia buna se cere si ea (restaurare_ramasa). Rezultatul unei cereri din meniu nu se atinge, nici
	unul fara numele copiei (nu se stie ce s-a pus)."""
	if not isinstance(rez, dict) or not isinstance(copie, dict) or rez.get("motiv") != "automat":
		return False
	pusa = rez.get("copie") if isinstance(rez.get("copie"), dict) else {}
	nume = u"%s" % (pusa.get("nume") or "")
	return bool(nume) and nume != u"%s" % (copie.get("nume") or "")


def restaurare_ramasa(copie, rad=None):
	"""Dupa o scriere buna, la pornirea sesiunii: copia facuta chiar inainte de scriere (identitatea din scriere.json) trebuia
	pusa la loc de HdsCopieSetari.pornire, din enigma2.sh, inainte de interfata. Daca acolo nu s-a pus nimic (stickul s-a
	montat abia dupa cele 20 de secunde de asteptare, de pilda), nu exista rezultat.json, nici semnul "gata": copia se cere
	acum (cererea o pune enigma2.sh la urmatoarea pornire a interfetei). La fel cand prima pornire a pus alta copie
	(copie_gresita_la_pornire: una mai veche, de pe un mediu montat inaintea stickului). ("ceruta", cale), ("lipsa", None)
	cand copia nu e pe niciun mediu, sau ("", None) cand nu e nimic de facut (copia buna a rulat, cu sau fara succes, sau
	asteapta deja)."""
	if not isinstance(copie, dict):
		return "", None
	C = _modul("HdsCopieSetari")
	r = rad or _rad()
	try:
		if C.cerere_in_asteptare(r):
			return "", None
		rez = C.citeste_rezultat(r)
		gresita = copie_gresita_la_pornire(rez, copie)
		if (rez is not None or os.path.exists(os.path.join(C.dosar_restaurare(r), C.SEMN_GATA))) and not gresita:
			return "", None
	except Exception as e:
		_jurnal("restaurarea de dupa scriere: %s" % e)
		return "", None
	asteptata = os.path.join(C.dosar_restaurare(r), FIS_COPIE_ASTEPTATA)
	for c in C.copii(rad=r):
		try:
			if C.identitate_copie(c["id"]) != copie:
				continue
		except (IOError, OSError, ValueError):
			continue
		ok, _mesaj = C.cere_punerea(c["id"], rad=r)
		_jurnal("dupa scriere: copia %s nu fusese pusa la loc la pornire%s; %s" % (os.path.basename(c["id"]),
			(" (pusa a fost %s)" % ((rez["copie"] if isinstance(rez.get("copie"), dict) else {}).get("nume") or "alta"))
				if gresita else "",
			"ceruta acum" if ok else "cererea nu s-a putut scrie"))
		if ok:
			_sterge(asteptata)
		return ("ceruta", c["id"]) if ok else ("", None)
	if not os.path.exists(asteptata):
		_jurnal("dupa scriere: copia facuta inainte de scriere nu e pe niciun mediu montat; o astept")
		try:
			os.makedirs(os.path.dirname(asteptata), exist_ok=True)
			C._scrie_atomic(asteptata, json.dumps(copie, sort_keys=True).encode("utf-8"), 0o600)
		except (IOError, OSError) as e:
			_jurnal("copia asteptata: %s" % e)
	return "lipsa", None


def copie_asteptata(rad=None):
	"""Identitatea copiei asteptate (restaurare_ramasa a gasit-o lipsa), sau None."""
	try:
		C = _modul("HdsCopieSetari")
		with open(os.path.join(C.dosar_restaurare(rad or _rad()), FIS_COPIE_ASTEPTATA), "r", encoding="utf-8") as f:
			d = json.load(f)
		return d if isinstance(d, dict) else None
	except (IOError, OSError, ValueError, ImportError):
		return None


class _AsteptareCopie(object):
	"""Copia lipsa dupa o scriere buna: la fiecare VERIFICARE_COPIE_MS se cauta din nou pe stickurile montate. Cand apare
	stickul, copia se cere si interfata se reporneste singura cand receptorul e liber (nu sub o inregistrare, o lucrare sau
	o intrebare deschisa). Omul doar baga stickul."""

	def __init__(self):
		from enigma import eTimer
		self.ceas = eTimer()
		try:
			self._legatura = self.ceas.timeout.connect(self.verifica)
		except AttributeError:
			self.ceas.callback.append(self.verifica)
		self.repornesc = False

	def porneste(self):
		self.ceas.start(VERIFICARE_COPIE_MS, True)

	def verifica(self):
		if self.repornesc:
			return self._reporneste()
		copie = copie_asteptata()
		if copie is None:
			return
		fel, _cale = restaurare_ramasa(copie)
		if fel == "ceruta":
			self.repornesc = True
			_arata_restaurarea("ceruta")
			return self.ceas.start(VERIFICARE_COPIE_MS, True)
		if fel == "lipsa":
			return self.ceas.start(VERIFICARE_COPIE_MS, True)
		# punerea la loc a rulat altfel (din meniu): nu mai e nimic de asteptat
		try:
			_sterge(os.path.join(_modul("HdsCopieSetari").dosar_restaurare(_rad()), FIS_COPIE_ASTEPTATA))
		except Exception:
			pass

	def _reporneste(self):
		if _reporneste_cand_e_liber():
			self.repornesc = False
			return
		self.ceas.start(VERIFICARE_COPIE_MS, True)


_asteptare = []


def _asteapta_copia(repornesc=False):
	try:
		if not _asteptare:
			_asteptare.append(_AsteptareCopie())
		_asteptare[0].repornesc = _asteptare[0].repornesc or repornesc
		_asteptare[0].porneste()
	except Exception as e:
		_jurnal("asteptarea copiei: %s" % e)


def _reporneste_cand_e_liber():
	"""Repornirea interfetei pentru copia ceruta, ca la actualizarea rapida: numai cand TryQuitMainloop n-ar intreba nimic
	(fara inregistrare acum sau in 6 minute, fara lucrare in fundal, fara alta intrebare de repornire). True cand a pornit
	sau nu se mai poate face nimic de aici; False = se incearca din nou."""
	session = imagine_online.session
	if session is None:
		return True
	try:
		from Plugins.Extensions.HdsWebControl.actualizari_web import reporneste_rapid
		rez = reporneste_rapid(lambda: session)(lambda *a: None)
	except Exception as e:
		_jurnal("repornirea pentru copie: %s" % e)
		from Screens.Standby import TryQuitMainloop
		session.open(TryQuitMainloop, 3)
		return True
	return rez not in ("inregistrare", "lucrare", "intrebare")


# ---------------------------------------------------------------- setarea

def config_imagine():
	"""config.hds_imagine_online.standby: ce se pune singur in standby (imaginea completa, pachetele din feed, amandoua sau
	nimic); implicit amandoua."""
	from Components.config import config, ConfigSubsection, ConfigSelection
	if "hds_imagine_online" not in config.content.items:
		config.hds_imagine_online = ConfigSubsection()
		config.hds_imagine_online.standby = ConfigSelection(default="amandoua",
			choices=[(v, _t(t)) for v, t in VALORI_STANDBY])
	return config.hds_imagine_online


def standby_voie(fel):
	"""fel: "imagine" sau "feed". Fara setare (o eroare): nu."""
	try:
		v = config_imagine().standby.value
	except Exception:
		return False
	return v == "amandoua" or (fel == "imagine" and v == "majore") or (fel == "feed" and v == "minore")


def seteaza_standby(valoare):
	c = config_imagine().standby
	if valoare not in [v for v, _x in VALORI_STANDBY]:
		return False
	c.value = valoare
	c.save()
	try:
		from Components.config import configfile
		configfile.save()
	except Exception:
		pass
	return True


# ---------------------------------------------------------------- inregistrarile

def inregistrare_in_fereastra(session, secunde):
	"""True cand ceva se inregistreaza acum sau incepe in urmatoarele `secunde`. O eroare inseamna da: o scriere nu trebuie
	sa rupa o inregistrare."""
	try:
		nav = session.nav
		if nav.getRecordings():
			return True
		urm = nav.RecordTimer.getNextRecordingTime()
		return urm > 0 and urm - time.time() <= secunde
	except Exception as e:
		_jurnal("inregistrarile nu se pot citi: %s" % e)
		return True


def in_standby():
	try:
		from Screens import Standby
		return Standby.inStandby is not None
	except Exception:
		return False


# ---------------------------------------------------------------- lucrarea (o singura data, pentru ecran si web)

class ImagineOnline(object):
	"""Starea comuna a ferestrei si a paginii web. Metodele ruleaza pe firul enigma2; reteaua si stickul pe fire separate,
	care scriu numai pas si progres (fereastra si pagina le citesc la rand)."""

	def __init__(self):
		self.faza = "liber"     # liber | caut | lucrez | astept | scriu
		self.pas = ""
		self.progres = (0, 0)
		self.mesaj = ""
		self.rezultat = NECAUTAT
		self.oferta = None
		self.din_standby = False
		self.session = None
		self.fabrica_lucrare = None
		self.fabrica_ceas = None
		self._lucrare = None
		self._opreste = False
		self._semn = None
		self._dosar = None
		self._copie = None
		self._refa_copia = False
		self._punct = None
		self._tinta = None
		self._imagine = None
		self._ceas = None
		self._legatura = None
		# ultima cautare a citit stare.json al feedului si acolo nu era nimic mai nou (fara imagine_noua)
		self.feed_la_zi = False

	# ---- firele
	def _lucreaza(self, functie, gata):
		fabrica = self.fabrica_lucrare
		if fabrica is None:
			fabrica = _paza().LucrareFundal
		self._lucrare = fabrica(functie, gata)

	def _oprit(self):
		return self._opreste

	def ocupat(self):
		return self.faza != "liber"

	def _credentiale(self, canal, rad):
		return _modul("HdsActualizari").citeste_netrc(rad) if canal == "proba" else None

	# ---- cautarea
	def cauta(self, la_sfarsit=None):
		"""Citeste lista semnata si alege imaginea; pe imaginile cu feedul lor (CU_FEED) citeste si stare.json al feedului,
		iar cand feedul aduce aceeasi versiune oferta e actualizarea din feed (alege_oferta). la_sfarsit() dupa aceea, pe
		firul enigma2. False cand e alta lucrare."""
		if self.ocupat():
			return False
		rad = _rad()
		A = _modul("HdsActualizari")
		canal_feed, _surse, baza_feed = A.canalul(rad)
		canal = canal_feed if canal_feed in ("proba", "public") else "public"
		credentiale = self._credentiale(canal, rad)
		cu_feed = CU_FEED and canal_feed in ("proba", "public")
		self.faza, self.pas, self.progres, self.mesaj = "caut", _t(P_CAUT), (0, 0), ""

		def citeste():
			feed, feed_la_zi = None, False
			if cu_feed:
				try:
					img = A.imaginea(rad)
					if img.get("versiune"):
						stare, cod = A.descarca_stare(A.adresa_stare(canal_feed, baza_feed or img["baza"]),
							A.citeste_netrc(rad) if canal_feed == "proba" else None)
						if not cod:
							feed = oferta_din_feed(stare, img, canal_feed, rad)
							feed_la_zi = feed is None and not stare.get("imagine_noua")
				except Exception as e:
					_jurnal("starea feedului: %s" % e)
			return citeste_lista(canal, credentiale), A.fara_retea(rad), feed, feed_la_zi

		def gata(rez, eroare):
			self._lucrare = None
			self.faza, self.pas = "liber", ""
			self.feed_la_zi = False
			if eroare or rez is None:
				self.rezultat = EROARE
			else:
				(lista, cod), fara, feed, self.feed_la_zi = rez
				if cod and feed:
					# lista imaginilor nu s-a citit, dar feedul are o versiune noua: ea e oferta
					self.oferta, self.rezultat = feed, OFERTA
				elif cod == FARA_RASPUNS and fara:
					self.rezultat = FARA_RETEA
				elif cod:
					self.rezultat = cod
				else:
					self._din_lista(lista, canal, rad, feed)
			if self.rezultat != OFERTA:
				self.oferta = None
			if la_sfarsit is not None:
				la_sfarsit()
		self._lucreaza(citeste, gata)
		return True

	def _din_lista(self, lista, canal, rad, feed=None):
		masina = masina_acum(rad)
		acum = versiunea_acum(rad)
		imagine = alege_imaginea(lista, masina, acum, canal) if masina else None
		oferta_imagine = None
		if imagine is not None:
			date = lista.get("date_versiuni") or {}
			oferta_imagine = {"fel": "imagine", "imagine": imagine, "canal": canal, "versiune": imagine["versiune"],
				"data": imagine.get("data") or "", "acum": acum, "data_acum": date.get(acum) or data_din_jurnal(acum, rad)}
		oferta = alege_oferta(oferta_imagine, feed)
		if oferta is None:
			self.rezultat = LA_ZI
			self.oferta = None
			return
		if oferta_imagine is not None and oferta is feed:
			_jurnal("oferta: actualizarea din feed %s, nu imaginea completa %s (aceeasi versiune, fara instalare de la zero)"
				% (feed["versiune"], imagine["versiune"]))
		self.oferta = oferta
		self.rezultat = OFERTA

	def text_oferta(self, oferta=None):
		"""Fraza ferestrei, cu versiunile si datele lor."""
		o = oferta or self.oferta
		if not o:
			return ""
		noua, acum = versiune_cu_data(o["versiune"], o["data"]), versiune_cu_data(o["acum"], o["data_acum"])
		return _t(T_IMAGINE if o["fel"] == "imagine" else T_VERSIUNE) % (noua, acum)

	# ---- „Da, actualizeaza”
	def poate_porni(self, oferta=None):
		"""("", punctul stickului) sau (textul de ce nu, None); pregateste montarea stickului cand numele o cere."""
		if self.ocupat():
			return _t(P_CAUT) if self.faza == "caut" else (self.pas or self.mesaj), None
		o = oferta or self.oferta
		if o and o.get("fel") == "feed":
			# actualizarea din feed: fara stick si fara loc de scriere; o opreste numai alta lucrare a actualizarilor
			return _modul("HdsActualizari").actualizari.poate_porni(), None
		if not o or o.get("fel") != "imagine":
			return _t(T_LA_ZI), None
		tinta = citeste_tinta()
		if not tinta.get("bun"):
			_jurnal("locul nu e bun: %s" % tinta.get("motiv"))
			return _t(T_LOC_STRAIN), None
		punct, text = alege_stick(o["imagine"])
		if not punct:
			return text, None
		return "", punct

	def porneste(self, din_standby=False, versiune=None, oferta=None):
		"""Un singur „Da”: tot drumul, pana la scriere. `versiune` si `oferta`: ce a vazut omul inainte de Da. False, cu
		mesajul de ce, cand nu porneste; nu s-a schimbat nimic."""
		if (versiune is not None and (not self.oferta or self.oferta.get("versiune") != versiune)) or \
				(oferta is not None and oferta != semn_oferta(self.oferta)):
			self.mesaj = _t(T_LA_ZI)
			return False
		motiv, punct = self.poate_porni()
		if motiv:
			self.mesaj = motiv
			return False
		if self.oferta.get("fel") == "feed":
			# "Da" la o versiune din feed (fereastra, meniul sau pagina web): actualizarea obisnuita, care cauta, instaleaza
			# si reporneste interfata cand receptorul e liber
			if not porneste_feed(self.session):
				self.mesaj = _modul("HdsActualizari").actualizari.mesaj or _t(T_FEED_OCUPAT)
				return False
			_jurnal("porneste: actualizarea din feed %s, %s" % (self.oferta.get("versiune"), "din standby" if din_standby else
				"cerut de om"))
			self.mesaj = _t(T_FEED_PORNIT)
			return True
		imagine = self.oferta["imagine"]
		if din_standby and any(cheia_scrierii(imagine, citeste_tinta()) in scrieri_esuate(p) for p, _liber in _stickuri_sigur()):
			self.mesaj = _t(T_NESCRIS) % (versiunea_acum_sigur() or "?")
			return False
		credentiale = self._credentiale(self.oferta.get("canal"), _rad())
		_jurnal("porneste: %s pe %s, %s" % (imagine["versiune"], imagine["masina"], "din standby" if din_standby else "cerut de om"))
		self._incepe(imagine, punct, din_standby, credentiale)
		return True

	def porneste_straina(self, ident, confirmat=False):
		"""Imaginea altora (inregistreaza_imagini), numai dupa avertisment: `confirmat` spune ca omul a ales Da la el. Niciodata
		din standby. False, cu mesajul de ce, cand nu porneste; nu s-a schimbat nimic."""
		x = [i for i in imagini_straine() if i["id"] == ident]
		if not x or not confirmat:
			self.mesaj = _t(T_FARA_FISIER) if not x else _t(T_OPRIT)
			return False
		if self.ocupat():
			self.mesaj = self.pas or _t(P_CAUT)
			return False
		if not citeste_tinta().get("bun"):
			self.mesaj = _t(T_LOC_STRAIN)
			return False
		imagine = dict(x[0], masina=masina_acum())
		punct, text = alege_stick(imagine)
		if not punct:
			self.mesaj = text
			return False
		_jurnal("imagine straina, dupa avertisment: %s, %s" % (numele_strainei(imagine), imagine["url"]))
		self._incepe(imagine, punct, False, None)
		return True

	def _incepe(self, imagine, punct, din_standby, credentiale):
		self._copie, self._refa_copia = None, False
		self._imagine, self._punct, self.din_standby = imagine, punct, bool(din_standby)
		self._tinta = citeste_tinta()
		self._opreste = False
		self.mesaj = ""
		self.faza, self.pas, self.progres = "lucrez", _t(P_DESCARC) % (0, 0, imagine["marime"] // (1024 * 1024)), (0, imagine["marime"])
		_jurnal("locul: %s" % self._tinta["argumente"])
		self._lucreaza(lambda: self._drum_stick(imagine, punct, credentiale), self._dupa_stick)

	def text_lucrare(self, oferta=None):
		"""Fraza de sus cat merge lucrarea: imaginea altora spune ce este, altfel fraza ofertei."""
		i = self._imagine or {}
		if i.get("straina") and self.faza in ("lucrez", "astept", "scriu"):
			return _t(T_STRAINA) % numele_strainei(i)
		return self.text_oferta(oferta)

	def opreste(self):
		"""Rosu in fereastra, sau pagina web: se opreste la urmatoarea bucata; fisierul inceput ramane."""
		if self.faza in ("lucrez", "astept"):
			self._opreste = True
			if self.faza == "astept":
				self._gata(_t(T_OPRIT))
			return True
		return False

	def _progres(self, n, total):
		self.progres = (n, total)
		self.pas = _t(P_DESCARC) % (n * 100 // max(total, 1), n // (1024 * 1024), total // (1024 * 1024))

	def _drum_stick(self, imagine, punct, credentiale):
		"""Pe firul separat: descarcarea, citirea de pe stick, pachetul, marcajul si sumele. Intoarce (dosar, semn, text)."""
		straina = imagine.get("straina")
		if straina and not imagine["marime"]:
			imagine["marime"] = marime_de_pe_server(imagine["url"]) or 0
			if not imagine["marime"]:
				return None, None, _t(T_FARA_FISIER)
			liber = loc_liber(punct)
			if liber is not None and liber < loc_necesar(imagine):
				return None, None, _t(T_FARA_LOC) % (loc_necesar(imagine) // (1024 * 1024) + 1)
		curata_imaginile_vechi(punct, imagine["fisier"])
		dosar = dosar_imagine(punct)
		cale, cod = descarca(imagine, dosar, credentiale, self._progres, self._oprit)
		if cod:
			_jurnal("descarcarea: %s" % cod)
			return None, None, {"retea": _t(T_FARA_RETEA), "lipsa": _t(T_FARA_FISIER), "oprit": _t(T_OPRIT),
				"marime": _t(T_NEPOTRIVIT), "loc": _t(T_FARA_LOC) % (loc_necesar(imagine) // (1024 * 1024) + 1)}.get(cod,
				_t(T_STICK_STRICAT))
		self.pas, self.progres = _t(P_VERIFIC), (0, 0)
		try:
			suma, marime = suma_de_pe_stick(cale, self._oprit)
		except (IOError, OSError):
			return None, None, _t(T_STICK_STRICAT)
		if suma is None:
			return None, None, _t(T_OPRIT)
		if marime != imagine["marime"] or (imagine.get("sha256") and suma != imagine["sha256"]) or (not straina and not imagine.get("sha256")):
			_jurnal("arhiva de pe stick: %d octeti, suma %s; lista: %d, %s" % (marime, suma, imagine["marime"], imagine.get("sha256")))
			_sterge(cale)
			return None, None, _t(T_NEPOTRIVIT)
		self.pas = _t(P_PREGATESC)
		try:
			pachet = scoate_pachetul(cale, punct, self._oprit, cu_marcaj=not straina)
		except (IOError, OSError) as e:
			return None, None, _t(T_FARA_LOC) % (loc_necesar(imagine) // (1024 * 1024) + 1) if e.errno == errno.ENOSPC else \
				_t(T_STICK_STRICAT)
		except (ValueError, KeyError, zipfile.BadZipFile, RuntimeError) as e:
			_jurnal("arhiva: %s" % e)
			if self._opreste:
				return None, None, _t(T_OPRIT)
			_sterge(cale)
			return None, None, _t(T_ALT_RECEPTOR if straina else T_NEPOTRIVIT)
		semn, text = verifica_pachetul(pachet, imagine, RADACINA, self._oprit)
		if text:
			return None, None, text
		return pachet, semn, None

	def _dupa_stick(self, rez, eroare):
		self._lucrare = None
		if eroare or rez is None:
			_jurnal("lucrarea: %s" % eroare)
			return self._gata(_t(T_STICK_STRICAT))
		dosar, semn, text = rez
		if text:
			return self._gata(text)
		if self._opreste:
			return self._gata(_t(T_OPRIT))
		self._dosar, self._semn = dosar, semn
		# copia chiar inainte de scriere, cu setarile de acum (config.pickle numai pe firul enigma2)
		self.pas, self.progres = _t(P_COPIE), (0, 0)
		try:
			text_setari = _modul("HdsCopieSetari").text_setari_acum()
		except Exception as e:
			_jurnal("setarile: %s" % e)
			return self._gata(_t(T_FARA_COPIE))
		if text_setari is None and "Components.config" in sys.modules:
			return self._gata(_t(T_FARA_COPIE))
		try:
			_modul("HdsCulegereCanale").inainte_de_copie()
		except Exception as e:
			_jurnal("baza canalelor: %s" % e)
		punct, tinta = self._punct, self._tinta

		def copia_si_simularea():
			dosar_copie, motiv = fa_copia_verificata(punct, text_setari, RADACINA)
			if motiv:
				_jurnal("copia: %s" % motiv)
				return _t(T_FARA_COPIE), ""
			self._copie = dosar_copie
			self.pas = _t(P_INAINTE)
			if self._opreste:
				return _t(T_OPRIT), ""
			return "", simuleaza(tinta, dosar)

		self._lucreaza(copia_si_simularea, self._dupa_copie)

	def _dupa_copie(self, rez, eroare):
		self._lucrare = None
		if eroare or rez is None:
			_jurnal("copia sau simularea: %s" % eroare)
			return self._gata(_t(T_SIMULARE))
		text, iesire = rez
		if text:
			return self._gata(text)
		if not simulare_buna(iesire, self._tinta, self._dosar):
			_jurnal("simularea nu e buna:\n%s" % iesire[-2000:])
			return self._gata(_t(T_SIMULARE))
		self._poarta()

	def _ceasul(self, ms):
		if self._ceas is None:
			fabrica = self.fabrica_ceas
			if fabrica is None:
				from enigma import eTimer as fabrica
			t = fabrica()
			try:
				self._legatura = t.timeout.connect(self._poarta)
			except AttributeError:
				t.callback.append(self._poarta)
			self._ceas = t
		self._ceas.stop()
		self._ceas.start(int(ms), True)

	def _poarta(self):
		"""Ultima poarta, pe firul enigma2, chiar inainte de scriere."""
		if self.faza not in ("lucrez", "astept") or self._opreste:
			return self._gata(_t(T_OPRIT))
		if self.din_standby and not in_standby():
			_jurnal("omul a pornit receptorul: scrierea din standby ramane pentru data viitoare")
			return self._gata("")
		fereastra = FEREASTRA_STANDBY_S if self.din_standby else FEREASTRA_INREGISTRARE_S
		if inregistrare_in_fereastra(self.session, fereastra):
			if self.din_standby:
				_jurnal("o inregistrare in ora urmatoare: scrierea din standby ramane pentru data viitoare")
				return self._gata("")
			self.faza, self.pas = "astept", _t(P_ASTEPT)
			self._refa_copia = True
			return self._ceasul(ASTEPTARE_INREGISTRARE_MS)
		if self._refa_copia:
			if not e_pe_stick(self._punct):
				return self._gata(_t(T_STICK_STRICAT))
			self._refa_copia = False
			self.faza = "lucrez"
			return self._dupa_stick((self._dosar, self._semn, None), None)
		refuz = self._refuz_inainte_de_scriere()
		if refuz:
			return self._gata(refuz)
		self._scrie()

	def _refuz_inainte_de_scriere(self):
		H = _paza()
		dosar = self._dosar
		M = _mediu()
		permis, motiv, _d, _p = M.verificaMediuScriere(dosar, textMontari=_montari(), stat=_STAT)
		if not permis or motiv != M.PERMIS_USB:
			_jurnal("mediul nu e bun: %s" % motiv)
			return _t(T_STICK_STRICAT)
		if motiv_nume_stick(dosar, muta=False)[0]:
			return _t(T_NUME_STICK)
		try:
			if not self._copie:
				return _t(T_FARA_COPIE)
			for nume in os.listdir(self._copie):
				goleste_cache(os.path.join(self._copie, nume))
			if _modul("HdsCopieSetari").verifica_copia(self._copie):
				return _t(T_FARA_COPIE)
		except (IOError, OSError, ValueError):
			return _t(T_FARA_COPIE)
		text_marcaj = citeste_marcaj(dosar)
		if not ((self._imagine or {}).get("straina") and text_marcaj is None):
			cod, _text, _marcaj = H.verificaPachet(text_marcaj, radacina=RADACINA)
			if cod != H.PACHET_BUN:
				return _t(T_ALT_RECEPTOR)
		if H.semnFisiere(dosar) != self._semn:
			return _t(T_NEPOTRIVIT)
		tinta = citeste_tinta()
		if not tinta.get("bun") or tinta.get("argumente") != self._tinta.get("argumente"):
			return _t(T_LOC_STRAIN)
		return None

	def _scrie(self):
		env_ofgwrite = None
		try:
			env_ofgwrite = _modul("HdsTexteOfgwrite").scrieTexteOfgwrite()
		except Exception as e:
			_jurnal("textele programului de instalare: %s" % e)
		try:
			_modul("HdsCulegereCanale").opreste_scrierile()
		except Exception as e:
			_jurnal("baza canalelor: %s" % e)
		try:
			_modul("HdsAfisaj").actualizare(True)
		except Exception:
			pass
		try:
			scrie_semnul_scrierii(self._punct, self._imagine, self._tinta, self.din_standby, self._copie)
			comanda = comanda_scriere(self._tinta, self._dosar)
			_jurnal("scrierea: %s" % comanda)
			lanseaza(comanda, os.path.join(self._punct, NUME_JURNAL_STICK), env_ofgwrite=env_ofgwrite)
		except (IOError, OSError) as e:
			_jurnal("scrierea n-a pornit: %s" % e)
			try:
				_modul("HdsAfisaj").actualizare(False)
			except Exception:
				pass
			return self._gata(_t(T_STICK_STRICAT))
		self.faza, self.pas, self.progres, self.mesaj = "scriu", _t(P_SCRIU), (0, 0), ""

	def _gata(self, text):
		self.faza, self.pas, self.progres = "liber", "", (0, 0)
		self.mesaj = text
		self._opreste = False
		if self._ceas is not None:
			self._ceas.stop()
		if text:
			_jurnal("oprit: %s" % text)

	# ---- pentru fereastra si web
	def stare_publica(self):
		o = self.oferta or {}
		return {"faza": self.faza, "pas": self.pas, "progres": list(self.progres), "mesaj": self.mesaj,
			"oferta": semn_oferta(self.oferta),
			"rezultat": self.rezultat, "text": self.text_lucrare() if o or self._imagine else "", "versiune": o.get("versiune") or "",
			"fel": o.get("fel") or "", "acum": versiunea_acum_sigur(), "standby": _standby_valoare(),
			"straine": _straine_publice()}


def _straine_publice():
	"""Imaginile altora pentru pagina web: fara adrese, cu starea si avertismentul."""
	try:
		return [{"id": x["id"], "sectiune": x["sectiune"], "nume": numele_strainei(x), "stare": _t(T_NEVERIFICATA),
			"avertisment": text_avertisment_strain(x)} for x in imagini_straine()]
	except Exception as e:
		_jurnal("imaginile altora: %s" % e)
		return []


# versiunea de acum, tinuta minte dupa data si marimea status-ului opkg (12.11.2026): pagina web o cere la 2 s, iar fiecare
# cerere citea si desfacea intreg /var/lib/opkg/status pe firul principal (sute de KB); se schimba numai cand opkg instaleaza
_versiune_tinuta = {"semn": None, "valoare": ""}


def _semn_status(rad):
	try:
		s = os.stat(os.path.join(rad, "var", "lib", "opkg", "status"))
		return (rad, s.st_mtime_ns, s.st_size)
	except OSError:
		return None


def versiunea_acum_sigur():
	try:
		rad = _rad()
		semn = _semn_status(rad)
		if semn is not None and semn == _versiune_tinuta["semn"]:
			return _versiune_tinuta["valoare"]
		v = versiunea_acum(rad)
		_versiune_tinuta["semn"], _versiune_tinuta["valoare"] = semn, v
		return v
	except Exception:
		return ""


def _standby_valoare():
	try:
		return config_imagine().standby.value
	except Exception:
		return "amandoua"


imagine_online = ImagineOnline()


# ---------------------------------------------------------------- verificarea (fereastra singura, standby)

class Verificare(object):
	"""La 5 minute dupa pornire si apoi o data pe zi: lista semnata (si, pe imaginile cu feedul lor, starea feedului). O
	versiune noua da fereastra pe ecranul obisnuit, o singura data la o pornire („Nu acum” o arata iar la urmatoarea
	pornire). In standby porneste singura, daca setarea o lasa si conditiile sunt bune. Nu arata nimic cat merge alta
	lucrare."""

	def __init__(self, session, io=None, cu_feed=True):
		from enigma import eTimer
		self.session = session
		self.io = io or imagine_online
		self.io.session = session
		self.cu_feed = cu_feed
		self.aratata = None
		self.oferta_feed = None
		self._feed = None
		self.ceas = eTimer()
		self.ceas_standby = eTimer()
		self.ceas_pornire = eTimer()
		try:
			self._l1 = self.ceas.timeout.connect(self.verifica)
			self._l2 = self.ceas_standby.timeout.connect(self._dupa_standby)
			self._l3 = self.ceas_pornire.timeout.connect(self._dupa_pornire)
		except AttributeError:
			self.ceas.callback.append(self.verifica)
			self.ceas_standby.callback.append(self._dupa_standby)
			self.ceas_pornire.callback.append(self._dupa_pornire)

	def porneste(self, intarziere=PRIMA_VERIFICARE):
		"""O singura data, de la pornire. Stickul se cauta dupa ce s-a montat."""
		self.programeaza(intarziere)
		self.ceas_pornire.start(ASTEPTARE_STICK_MS, True)
		try:
			from Components.config import config
			config.misc.standbyCounter.addNotifier(self._la_standby, initial_call=False)
		except Exception as e:
			_jurnal("standby: %s" % e)

	def programeaza(self, intarziere):
		self.ceas.stop()
		self.ceas.startLongTimer(int(intarziere))

	def _dupa_pornire(self):
		try:
			dupa_pornire()
		except Exception as e:
			_jurnal("dupa pornire: %s" % e)

	def _zilnic(self):
		try:
			return _modul("HdsActualizari").zilnic_pornit()
		except Exception:
			return True

	def verifica(self):
		self.ceas.stop()
		if not self._zilnic():
			return self.programeaza(ZI)
		if not self.io.cauta(self._dupa_lista):
			self.programeaza(REINCERCARE)

	def _dupa_lista(self):
		if self.io.rezultat == OFERTA:
			self.oferta_feed = None
			if self.cu_feed and (self.io.oferta or {}).get("fel") == "imagine" and not self._versiune_stiuta():
				# pe o imagine cu feed versiunea vine din status-ul opkg: fara ea (o instalare neterminata, un status
				# stricat) "acum" ar fi baza, iar fereastra ar propune singura imaginea de la zero (09.11.2026, darog69)
				_jurnal("fereastra: versiunea de acum nu se stie din status-ul opkg; imaginea completa nu se propune singura")
				return self.programeaza(ZI)
			if self.cu_feed and (self.io.oferta or {}).get("fel") == "imagine" and self.io.feed_la_zi and \
					_baza(self.io.oferta.get("versiune")) and _baza(self.io.oferta.get("versiune")) == _baza(self._baza_acum()):
				# imaginea completa pe aceeasi baza (0.7.x peste 0.7.y), dar feedul bazei spune ca nu e nimic nou: un feed
				# ramas in urma (cache) sau o publicare numai ca imagine. Fereastra singura nu propune instalarea de la zero
				# (09.11.2026, darog69, a doua ipoteza: feed vechi din cache dupa prima actualizare); din meniu ramane.
				# Pretul: o versiune publicata numai ca imagine, pe aceeasi baza, nu mai apare singura.
				_jurnal("fereastra: imaginea %s e pe aceeasi baza, iar feedul nu are nimic nou; nu o propun singura"
					% self.io.oferta.get("versiune"))
				return self.programeaza(ZI)
			self._hotaraste()
			return self.programeaza(ZI)
		if not self.cu_feed:
			return self.programeaza(ZI if self.io.rezultat == LA_ZI else REINCERCARE)
		self._citeste_feedul()

	def _baza_acum(self):
		try:
			return _modul("HdsActualizari").imaginea(_rad()).get("baza") or ""
		except Exception:
			return ""

	def _versiune_stiuta(self):
		try:
			return bool(_modul("HdsActualizari").imaginea(_rad()).get("versiune"))
		except Exception:
			return False

	def _citeste_feedul(self):
		"""Feedul imaginii: o versiune noua (si cand vin numai pachete) are aceeasi fereastra; Da = actualizarea obisnuita."""
		A = _modul("HdsActualizari")
		rad = _rad()
		canal, _surse, baza = A.canalul(rad)
		img = A.imaginea(rad)
		if canal not in ("proba", "public") or not img.get("versiune"):
			return self.programeaza(ZI)
		credentiale = A.citeste_netrc(rad) if canal == "proba" else None
		adresa = A.adresa_stare(canal, baza or img["baza"])

		def gata(rez, eroare):
			stare, cod = rez if rez and not eroare else ({}, A.EROARE)
			self._feed = None
			o = None if cod else oferta_din_feed(stare, img, canal, rad)
			if o:
				self.oferta_feed = o
				self._hotaraste()
			self.programeaza(ZI)
		fabrica = self.io.fabrica_lucrare or _paza().LucrareFundal
		self._feed = fabrica(lambda: A.descarca_stare(adresa, credentiale), gata)

	def oferta(self):
		return self.io.oferta if self.io.rezultat == OFERTA and self.io.oferta else self.oferta_feed

	def _hotaraste(self):
		o = self.oferta()
		if not o or self.io.ocupat():
			return
		if in_standby():
			return self._incearca_standby(o)
		cheie = (o["fel"], o["versiune"])
		if self.aratata != cheie:
			self.aratata = cheie
			self._arata(o)

	def _arata(self, o):
		"""Pe ecranul obisnuit: notificarea o deschide cand ecranul principal e in fata."""
		try:
			from Tools import Notifications
			Notifications.AddNotification(ecranul(), o)
		except Exception as e:
			_jurnal("fereastra: %s" % e)

	def _la_standby(self, _element=None):
		"""La intrarea in standby: dupa doua minute se incearca singur; la iesire, fereastra."""
		self.ceas_standby.stop()
		self.ceas_standby.start(120000, True)
		try:
			from Screens import Standby
			if Standby.inStandby is not None and self._la_trezire not in Standby.inStandby.onClose:
				Standby.inStandby.onClose.append(self._la_trezire)
		except Exception as e:
			_jurnal("standby: %s" % e)

	def _dupa_standby(self):
		self._hotaraste()

	def _la_trezire(self):
		self.ceas_standby.stop()
		self.ceas_standby.start(60000, True)

	def _incearca_standby(self, o):
		"""Numai cu setarea pornita, cu stick cu loc (pentru imagine), fara inregistrare acum sau in ora urmatoare."""
		if not standby_voie(o["fel"]):
			return
		if inregistrare_in_fereastra(self.session, FEREASTRA_STANDBY_S):
			return
		if o["fel"] == "imagine":
			motiv, _punct = self.io.poate_porni(o)
			if motiv:
				return _jurnal("in standby nu pornesc: %s" % motiv)
			self.io.porneste(din_standby=True)
		else:
			self._feed_in_standby()

	def _feed_in_standby(self):
		try:
			with open(os.path.join(_rad(), STANDBY_DUPA_REPORNIRE.lstrip("/")), "w") as f:
				f.write("1\n")
		except (IOError, OSError):
			pass
		if not porneste_feed(self.session):
			_sterge(os.path.join(_rad(), STANDBY_DUPA_REPORNIRE.lstrip("/")))


def porneste_feed(session):
	"""„Da” la o versiune din feed: actualizarea obisnuita (cauta, instaleaza, reporneste interfata), fara stick."""
	A = _modul("HdsActualizari")
	if A.actualizari.ocupat():
		return False
	try:
		from Plugins.Extensions.HdsWebControl.actualizari_web import reporneste_rapid
	except ImportError:
		return False
	return bool(A.actualizari.actualizeazaRapid(reporneste_rapid(lambda: session)))


def ecranul():
	if ECRAN is not None:
		return ECRAN
	from Screens.HdsImagineOnline import HdsImagineOnline
	return HdsImagineOnline


_verificare = []


def dupa_pornire():
	"""Ce a ramas de la o scriere facuta de aici (pe stick) si intoarcerea in standby dupa o actualizare pornita de acolo."""
	pune_standby = False
	cale = os.path.join(_rad(), STANDBY_DUPA_REPORNIRE.lstrip("/"))
	if os.path.exists(cale):
		_sterge(cale)
		pune_standby = True
	for punct, _liber in _stickuri_sigur():
		r = verifica_dupa_scriere(punct)
		if r is None:
			continue
		pune_standby = pune_standby or r["din_standby"]
		if not r["bun"]:
			try:
				from Tools import Notifications
				from Screens.MessageBox import MessageBox
				Notifications.AddPopup(_t(T_NESCRIS) % (r["acum"] or "?"), MessageBox.TYPE_INFO, 30, "HdsImagineOnline")
			except Exception as e:
				_jurnal("mesajul: %s" % e)
		elif r.get("copie"):
			fel, _cale_copie = restaurare_ramasa(r["copie"])
			if fel:
				# setarile intai: fara standby pana nu revin; repornirea (ceruta) sau cautarea stickului (lipsa) o face
				# _AsteptareCopie
				pune_standby = False
				_arata_restaurarea(fel)
				_asteapta_copia(repornesc=fel == "ceruta")
		break
	else:
		# o copie asteptata de la o pornire de dinainte (stickul inca nebagat)
		if copie_asteptata() is not None:
			_asteapta_copia()
	if pune_standby:
		try:
			from Tools import Notifications
			from Screens.Standby import Standby
			if not in_standby():
				Notifications.AddNotification(Standby)
		except Exception as e:
			_jurnal("inapoi in standby: %s" % e)


def _arata_restaurarea(fel):
	""""ceruta": un mesaj scurt; repornirea o da apoi _AsteptareCopie, cand receptorul e liber (enigma2.sh pune copia la loc
	inainte de interfata). "lipsa": un mesaj care cere stickul; copia se cauta singura cand apare."""
	try:
		from Tools import Notifications
		from Screens.MessageBox import MessageBox
		Notifications.AddPopup(_t(T_COPIE_CERUTA if fel == "ceruta" else T_COPIE_LIPSA), MessageBox.TYPE_INFO,
			10 if fel == "ceruta" else 30, "HdsImagineOnlineCopie")
	except Exception as e:
		_jurnal("mesajul restaurarii: %s" % e)


def _stickuri_sigur():
	try:
		return stickuri()
	except Exception as e:
		_jurnal("stickurile: %s" % e)
		return []


def porneste(session, cu_feed=True):
	"""Din mytest.py (sau din pluginul-punte), dupa ce s-a facut sesiunea. Pornirea nu depinde de el."""
	global CU_FEED
	config_imagine()
	imagine_online.session = session
	if cu_feed:
		CU_FEED = True
		_modul("HdsActualizari").FEREASTRA_ACTIVA = True
	if not _verificare:
		v = Verificare(session, cu_feed=cu_feed)
		_verificare.append(v)
		v.porneste()
