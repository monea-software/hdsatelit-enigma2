# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAsistentaControl.py: partea de control a Asistentei de la distanta (nivelul B, "Control complet"): textul ecranului
# deschis pe receptor (op "ecran"), tastele telecomenzii (op "taste") si scrierea intr-un camp de text (op "text"). Cu
# textul ecranului si cu tastele, echipa face prin meniuri orice ar face omul cu telecomanda.
#
# ECRANELE PRIVATE: modulele de acces (orice ecran al lor, dupa clasa si dupa modul), Accesul SSH, programul de beta
# testeri (numele, e-mailul), Wi-Fi-ul (retele, parola), VPN-ul, controlul parental (PIN), setarile interfetei web (cheia
# pentru scripturi), codul de asociere si ORICE ecran care are in lista un camp de parola sau de PIN. Daca unul dintre
# ecranele din stiva (nu numai cel de sus) e privat, tot ecranul e privat: "ecran" da numai "(ecran privat)" si clasa,
# "taste" primeste numai EXIT, "text" si captura sunt refuzate. O tastatura de pe ecran deschisa peste parola Wi-Fi e deci
# tot privata.
#
# TASTELE: numai din lista alba TASTE (fara POWER si fara oprire), cel mult MAX_TASTE pe cerere, cu PAUZA_MS intre ele,
# trimise ca tastele adevarate ale telecomenzii (eRCMapper.inject cu dispozitivul nativ, ca in interfata web; fara el,
# harta de actiuni). Inainte de fiecare tasta se verifica din nou ecranul: daca a devenit privat, merge numai EXIT.
#
# FIRUL: interfata enigma2 nu e sigura intre fire; brokerul ruleaza pe firul sesiunii. Toate atingerile ecranului merg
# prin PeFir: cererea intra intr-o coada, firul enigma2 e trezit (reactor.callFromThread) si o face; ceasul semnului
# (Screens/HdsAsistentaSemn.Controler, o data pe secunda) goleste si el coada, ca plasa. Tastele pleaca una pe tic de
# eTimer, nu cu sleep pe firul enigma2. Modulul nu importa nimic din enigma2 la incarcare: probele de pe PC dau ecrane
# false (orice obiect cu aceleasi metode).

import os
import re
import threading
import time

# lista alba a tastelor (numele din cerere -> codul Linux al tastei, ca telecomanda fizica si interfata web)
TASTE = {
	"0": 11, "1": 2, "2": 3, "3": 4, "4": 5, "5": 6, "6": 7, "7": 8, "8": 9, "9": 10,
	"sus": 103, "jos": 108, "stanga": 105, "dreapta": 106,
	"ok": 352, "exit": 174, "menu": 139, "info": 358, "epg": 365,
	"rosu": 398, "verde": 399, "galben": 400, "albastru": 401,
	"ch+": 402, "ch-": 403, "vol+": 115, "vol-": 114, "mute": 113,
	"text": 388, "help": 138, "audio": 392, "subt": 370, "tv": 377, "radio": 385, "fav": 364,
	"anterior": 412, "urmator": 407, "pauza": 119, "redare": 207, "stop": 128,
	"inapoi-rapid": 168, "inainte-rapid": 208, "timer": 359,
}
# aceleasi taste sub alte nume (engleza, prescurtari)
ALIASURI = {
	"up": "sus", "down": "jos", "left": "stanga", "right": "dreapta", "back": "exit", "inapoi": "exit",
	"meniu": "menu", "red": "rosu", "green": "verde", "yellow": "galben", "blue": "albastru",
	"ttx": "text", "teletext": "text", "chplus": "ch+", "chminus": "ch-", "volplus": "vol+", "volminus": "vol-",
	"pause": "pauza", "play": "redare",
}
# un pas fara tasta: asteapta ASTEAPTA_MS (de pilda dupa ce se deschide un ecran care se incarca greu)
ASTEAPTA = "asteapta"
ASTEAPTA_MS = 1200
# apasarea lunga: "ok:lung" (ca tasta tinuta)
SUFIX_LUNG = ":lung"
MAX_TASTE = 20
PAUZA_MS = 400
# dupa ultima tasta, cat se asteapta pana se citeste ecranul
LINISTE_MS = 900
# pe un ecran privat merge numai iesirea
TASTE_PE_PRIVAT = ("exit",)
TEXT_MAXIM = 200

# ecranele private, dupa clasa (numele exact) si dupa tipar (clasa sau modul)
CLASE_PRIVATE = frozenset((
	"CamSetup", "CamInfo", "HdsAccesSsh", "HdsVpn", "WlanConnectScreen", "WlanScanScreen", "WlanStatusScreen",
	"HdsWifiCanaleScreen", "ParentalControlSetup", "ParentalControlChangePin", "ParentalControlEditor",
	"ParentalControlBouquetEditor", "PinInput", "HdsWebControlSetup", "HdsCodAsociere", "IptvSetup",
))
MODULE_PRIVATE = frozenset((
	"Screens.CamSetup", "Screens.CamInfo", "Screens.Ci", "Screens.HdsAccesSsh", "Screens.HdsVpn",
	"Screens.HdsBetaTester", "Screens.WlanSetup", "Screens.IptvSetup", "Screens.HdsWebControlSetup",
	"Screens.HdsCodAsociere", "Screens.ParentalControlSetup",
))
# orice clasa sau modul cu numele unui modul de acces, al unei parole, al Wi-Fi-ului, al accesului SSH, al VPN-ului sau al
# programului de beta testeri (ale noastre si ale pluginurilor din afara)
_TIPAR_PRIVAT = re.compile(r"(?i)(cam|card|parol|passw|wpa|wlan|wifi|ssh|vpn|beta|parental|token|login(?!fo)|email|"
	r"cheie|chei\b|pinin)")
# campurile de parola si de PIN (clasele elementelor de setari)
CAMPURI_PRIVATE = ("ConfigPassword", "ConfigPIN")

RANDURI_LISTA = 40          # cate randuri dintr-o lista (in jurul celui ales)
TEXT_ECRAN_MAX = 16 * 1024

_REFERINTA = re.compile(r"^\d+:\d+:[0-9A-Fa-f]+:")
# numele interne din randurile meniurilor (entryID, greutatea): litere mici, cifre, _ . -, fara spatii
_ID_INTERN = re.compile(r"^[a-z0-9_.-]+$")
# atributele cu numele unui rand facut dintr-un obiect
_ATRIBUTE_TEXT = ("titlu", "nume", "text", "name", "title", "eticheta")


def _jurnal(text):
	print("[HdsAsistentaControl] %s" % text)


# ---------------------------------------------------------------- tastele

def normalizeazaTasta(nume):
	"""(nume, lung) pentru un nume din cerere, sau (None, False) cand nu e in lista alba. ASTEAPTA ramane ASTEAPTA."""
	n = (nume or "").strip().lower()
	lung = False
	if n.endswith(SUFIX_LUNG):
		n = n[:-len(SUFIX_LUNG)]
		lung = True
	if n == ASTEAPTA and not lung:
		return ASTEAPTA, False
	n = ALIASURI.get(n, n)
	if n in TASTE:
		return n, lung
	return None, False


def imparteTaste(text):
	"""(lista [(nume, lung)], greseli): tastele unei cereri ("menu jos jos ok"); greseli = numele necunoscute."""
	lista, greseli = [], []
	for bucata in (text or "").split():
		nume, lung = normalizeazaTasta(bucata)
		if nume is None:
			greseli.append(bucata)
		else:
			lista.append((nume, lung))
	return lista, greseli


def apasaTasta(cod, lung=False):
	"""Tasta ca de pe telecomanda receptorului: eRCMapper.inject (dispozitivul nativ, deci legaturile keymap.xml ale
	telecomenzii), cu repetari pentru apasarea lunga; fara eRCMapper, prin harta de actiuni (la fel ca interfata web)."""
	try:
		from enigma import eRCMapper
		m = eRCMapper.getInstance()
	except Exception:
		m = None
	if m is not None:
		m.inject(cod, 0)
		if lung:
			for _i in range(5):
				m.inject(cod, 2)
		m.inject(cod, 1)
		return
	from enigma import eActionMap
	harta = eActionMap.getInstance()
	harta.keyPressed("dreambox advanced remote control (native)", cod, 0)
	harta.keyPressed("dreambox advanced remote control (native)", cod, 1)


# ---------------------------------------------------------------- stiva ecranelor si ecranele private

def stiva(session):
	"""Ecranele deschise, de jos in sus: cele din session.dialog_stack (tupluri (ecran, aratat)) si cel de sus."""
	ecrane = []
	for el in list(getattr(session, "dialog_stack", None) or []):
		d = el[0] if isinstance(el, tuple) else el
		if d is not None:
			ecrane.append(d)
	sus = getattr(session, "current_dialog", None)
	if sus is not None and (not ecrane or ecrane[-1] is not sus):
		ecrane.append(sus)
	return ecrane


def _clase(ecran):
	try:
		return [c.__name__ for c in type(ecran).__mro__]
	except Exception:
		return [type(ecran).__name__]


def _modul(ecran):
	return getattr(type(ecran), "__module__", "") or ""


def _elementPrivat(element):
	return any(n in CAMPURI_PRIVATE for n in _clase(element))


def _intrariConfig(ecran):
	"""Intrarile listelor de setari ale ecranului (ConfigList: tupluri (eticheta, element[, ajutor]))."""
	gasite = []
	try:
		componente = list(ecran.values())
	except Exception:
		return gasite
	for comp in componente:
		lista = getattr(comp, "list", None)
		if not isinstance(lista, (list, tuple)):
			continue
		for e in lista[:400]:
			if isinstance(e, (list, tuple)) and len(e) >= 2 and _esteElement(e[1]):
				gasite.append(e)
	return gasite


def _esteElement(x):
	return hasattr(x, "getText") and hasattr(x, "value") and not isinstance(x, (str, bytes))


def ecranPrivat(ecran):
	"""True daca ecranul e privat: dupa clasa (si clasele de baza), dupa modul, sau fiindca are un camp de parola/PIN."""
	if ecran is None:
		return False
	clase = _clase(ecran)
	modul = _modul(ecran)
	if any(c in CLASE_PRIVATE for c in clase) or modul in MODULE_PRIVATE:
		return True
	if _TIPAR_PRIVAT.search(type(ecran).__name__) or _TIPAR_PRIVAT.search(modul.rsplit(".", 1)[-1] if modul else ""):
		return True
	if modul.startswith("Plugins.") and _TIPAR_PRIVAT.search(modul):
		return True
	for e in _intrariConfig(ecran):
		if _elementPrivat(e[1]):
			return True
	return False


def privat(ecrane, ssh_deschis=False):
	"""(privat, clasa): primul ecran privat din stiva (oricare, nu numai cel de sus); ssh_deschis = ecranul Accesului
	SSH e deschis (HdsAccesSsh.ecranDeschis), chiar daca nu e in stiva."""
	for e in ecrane:
		if ecranPrivat(e):
			return True, type(e).__name__
	if ssh_deschis:
		return True, "HdsAccesSsh"
	return False, ""


def _sshDeschis():
	try:
		from Components import HdsAccesSsh
		return bool(HdsAccesSsh.ecranDeschis())
	except Exception:
		return False


# ---------------------------------------------------------------- textul ecranului

def _titlu(ecran):
	try:
		t = ecran.getTitle()
		if t:
			return str(t)
	except Exception:
		pass
	try:
		t = ecran["Title"].text
		if t:
			return str(t)
	except Exception:
		pass
	return ""


def _text(comp):
	"""Textul unei componente cu text (StaticText, Label, ScrollLabel, Button, Input), sau None."""
	for nume in ("getText",):
		f = getattr(comp, nume, None)
		if callable(f):
			try:
				t = f()
			except Exception:
				return None
			return t if isinstance(t, str) else None
	t = getattr(comp, "text", None)
	return t if isinstance(t, str) else None


def _textRand(e, adancime=0):
	"""Textul unui rand dintr-o lista oarecare: sirurile din el (fara referinte de canal, cai), cel mult trei."""
	if isinstance(e, str):
		return e
	parti = []

	def culege(x, ad):
		if len(parti) >= 3 or ad > 3:
			return
		if isinstance(x, str):
			s = x.strip()
			# dupa primul text, fara numele interne (hds_scanare, 15): nu spun nimic omului din echipa
			if parti and _ID_INTERN.match(s):
				return
			if s and not s.startswith("/") and not _REFERINTA.match(s) and len(s) <= 200 and s not in parti:
				parti.append(s)
		elif isinstance(x, (list, tuple)):
			for y in x:
				culege(y, ad + 1)
		elif x is not None and not isinstance(x, (int, float, bool, bytes)):
			# un rand facut dintr-un obiect (cautarea setarilor, listele noastre): numele lui
			for nume in _ATRIBUTE_TEXT:
				v = getattr(x, nume, None)
				if isinstance(v, str) and v.strip():
					culege(v, ad + 1)
					break
	culege(e, adancime)
	return " | ".join(parti)


def _valoare(element):
	if _elementPrivat(element):
		return "***"
	try:
		v = element.getText()
	except Exception:
		try:
			v = str(element.value)
		except Exception:
			v = "?"
	return v if isinstance(v, str) else str(v)


def _indexAles(comp):
	for nume in ("getCurrentIndex", "getSelectedIndex", "getIndex"):
		f = getattr(comp, nume, None)
		if callable(f):
			try:
				i = f()
				if isinstance(i, int):
					return i
			except Exception:
				pass
	i = getattr(comp, "index", None)
	return i if isinstance(i, int) else None


def _randuriLista(nume, comp):
	lista = getattr(comp, "list", None)
	if not isinstance(lista, (list, tuple)) or not lista:
		return None
	ales = _indexAles(comp)
	n = len(lista)
	inceput = 0
	if ales is not None and ales >= RANDURI_LISTA // 3:
		inceput = max(0, min(ales - RANDURI_LISTA // 3, n - RANDURI_LISTA))
	sfarsit = min(n, inceput + RANDURI_LISTA)
	randuri = ['Lista "%s" (rândul %s din %d):' % (nume, (ales + 1) if ales is not None else "?", n)]
	for i in range(inceput, sfarsit):
		e = lista[i]
		semn = ">" if i == ales else " "
		if isinstance(e, (list, tuple)) and len(e) >= 2 and _esteElement(e[1]):
			rand = "%s [%d] %s = %s" % (semn, i + 1, e[0], _valoare(e[1]))
			if i == ales and len(e) > 2 and isinstance(e[2], str) and e[2].strip():
				rand += "\n      ajutor: " + e[2].strip()
		else:
			rand = "%s [%d] %s" % (semn, i + 1, _textRand(e))
		randuri.append(rand)
	if sfarsit < n:
		randuri.append("  ... încă %d rânduri" % (n - sfarsit))
	return randuri


def textEcran(ecrane, mod_ascii=False, ssh_deschis=False):
	"""Textul ecranului de sus, pentru echipa: stiva (clasele si titlurile), listele cu randul ales, setarile
	"eticheta = valoare", textele si tastele colorate. Ecran privat: numai "(ecran privat)" si clasele."""
	if not ecrane:
		return "(niciun ecran deschis)"
	e_privat, clasa = privat(ecrane, ssh_deschis)
	if e_privat:
		return "(ecran privat) %s\nEcrane: %s\nPe un ecran privat merge numai EXIT." % (clasa,
			" > ".join(type(e).__name__ for e in ecrane))
	cap = []
	for e in ecrane:
		t = _titlu(e)
		cap.append('%s "%s"' % (type(e).__name__, t) if t else type(e).__name__)
	sus = ecrane[-1]
	parti = ["Ecrane: " + " > ".join(cap),
		"Sus: %s (%s)" % (type(sus).__name__, _modul(sus)),
		"Tastatura: " + ("câmp de text deschis (scrii cu op text)" if mod_ascii else "telecomanda")]
	texte, taste, liste = [], [], []
	try:
		componente = list(sus.items())
	except Exception:
		componente = []
	for nume, comp in componente:
		if nume == "Title":
			continue
		r = _randuriLista(nume, comp)
		if r is not None:
			liste.extend(r)
			continue
		t = _text(comp)
		if t is None or not t.strip():
			continue
		t = " ".join(t.split()) if len(t) < 300 else t.strip()
		if nume.startswith("key_"):
			taste.append("%s=%s" % (nume[4:], t))
		else:
			texte.append("  %s: %s" % (nume, t))
	parti.extend(liste)
	if texte:
		parti.append("Texte:")
		parti.extend(texte)
	if taste:
		parti.append("Taste: " + " | ".join(taste))
	text = "\n".join(parti)
	if len(text) > TEXT_ECRAN_MAX:
		text = text[:TEXT_ECRAN_MAX] + "\n... (taiat)"
	return text


def modAscii():
	try:
		from Components import HdsMouseEcran
		return HdsMouseEcran.modAscii()
	except Exception:
		return False


# ---------------------------------------------------------------- lucrul pe firul enigma2

class PeFir(object):
	"""Lucrul cerut de firul sesiunii, facut pe firul enigma2. lucru(gata) ruleaza pe firul principal si cheama
	gata(rezultat) o singura data, pe loc sau mai tarziu (din eTimer). trezeste(f): pune f pe firul principal
	(reactor.callFromThread); fara el, coada o goleste numai ceasul controlerului (goleste)."""

	def __init__(self, trezeste=None):
		self._coada = []
		self._lacat = threading.Lock()
		self._trezeste = trezeste

	def cere(self, lucru, termen_s=30):
		"""Rezultatul lui lucru, sau None dupa termen_s (lucrul scos din coada daca n-a inceput)."""
		ev = threading.Event()
		cutie = []

		def gata(rez):
			if not cutie:
				cutie.append(rez)
				ev.set()
		intrare = (lucru, gata)
		with self._lacat:
			self._coada.append(intrare)
		if self._trezeste is not None:
			try:
				self._trezeste(self.goleste)
			except Exception as e:
				_jurnal("trezire: %r" % (e,))
		if not ev.wait(termen_s):
			with self._lacat:
				if intrare in self._coada:
					self._coada.remove(intrare)
			return None
		return cutie[0]

	def goleste(self):
		"""Pe firul principal: face tot ce asteapta in coada."""
		while True:
			with self._lacat:
				if not self._coada:
					return
				lucru, gata = self._coada.pop(0)
			try:
				lucru(gata)
			except Exception as e:
				_jurnal("lucru: %r" % (e,))
				gata(None)

	def asteapta(self):
		with self._lacat:
			return len(self._coada)


class SirTaste(object):
	"""Tastele unei cereri, apasate pe rand (pas() la fiecare tic de PAUZA_MS, pe firul enigma2). Inainte de fiecare
	tasta se uita la ecran: pe un ecran privat merge numai EXIT, iar sirul se opreste la prima tasta oprita."""

	def __init__(self, taste, ecrane, apasa=apasaTasta, ssh_deschis=_sshDeschis):
		self.taste = list(taste)
		self.ecrane = ecrane            # functie: stiva de acum
		self.apasa = apasa
		self.ssh = ssh_deschis
		self.trimise = []
		self.oprit = ""
		self._asteapta = 0

	def pas(self):
		"""Un tic: True cat mai sunt de facut, False la sfarsit (sau la oprire)."""
		if self._asteapta > 0:
			self._asteapta -= 1
			return True
		if not self.taste:
			return False
		nume, lung = self.taste.pop(0)
		if nume == ASTEAPTA:
			self._asteapta = max(0, ASTEAPTA_MS // PAUZA_MS - 1)
			self.trimise.append(ASTEAPTA)
			return True
		e_privat, clasa = privat(self.ecrane(), self.ssh())
		if e_privat and nume not in TASTE_PE_PRIVAT:
			self.oprit = "ecran privat (%s): numai EXIT; oprit la %s" % (clasa, nume)
			self.taste = []
			return False
		self.apasa(TASTE[nume], lung)
		self.trimise.append(nume + (SUFIX_LUNG if lung else ""))
		return bool(self.taste)


# ---------------------------------------------------------------- scrierea textului

def scrieText(ecrane, text, mod_ascii, scrie, ssh_deschis=False):
	"""(cod, mesaj): scrie text in campul deschis pe ecranul de sus. scrie(text) -> rezultatul lui
	HdsMouseEcran.MouseEcran.text (semnele, prin actiunea gotAsciiCode a ecranului). Refuzat pe un ecran privat, pe un
	camp de parola si cand nu e niciun camp de text deschis."""
	if not ecrane:
		return 1, "(niciun ecran deschis)"
	e_privat, clasa = privat(ecrane, ssh_deschis)
	if e_privat:
		return 1, "(ecran privat: %s; textul nu se scrie)" % clasa
	if not mod_ascii:
		return 1, "(niciun câmp de text deschis: deschide-l întâi, de pilda cu OK pe rand)"
	text = (text or "")[:TEXT_MAXIM]
	semne = 0
	for i in range(0, len(text), 64):
		rez = scrie(text[i:i + 64]) or {}
		if rez.get("facut") != "text":
			return 1, "(campul nu a primit textul: %s)" % rez.get("facut", "nimic")
		semne += int(rez.get("semne") or 0)
	return 0, "scrise %d semne" % semne


def asteptareTaste(n):
	"""Cat poate dura un sir de n taste pe receptor, cu linistea de la sfarsit (pentru termenul cererii)."""
	return (n * max(PAUZA_MS, ASTEAPTA_MS) + LINISTE_MS) / 1000.0 + 10


def acum():
	return time.monotonic()


# ---------------------------------------------------------------- scrierea directa a unei setari (op "setare-scrie")

# numai sub aceste prefixe (video, sunet, interfata, subtitrari, telecomanda, tunerele, ora, ghidul, inregistrarile,
# reteaua) si niciodata o cheie care se potriveste SETARI_OPRITE (parole, chei, nume, e-mail, modulele de acces)
SETARI_SCRIERE = (
	"config.av.", "config.osd.", "config.usage.", "config.subtitles.", "config.skin.", "config.misc.rcused",
	"config.Nims.", "config.timezone.", "config.epg.", "config.recording.", "config.network.",
)
SETARI_OPRITE = re.compile(r"(?i)(pass|pwd|parola|psk|secret|token|key|pin|auth|login|user|card|cam|mail|email|nume|"
	r"name|ssid|wpa|wlan|hdswebcontrol|hds_beta)")
_CHEIE = re.compile(r"^config(\.[A-Za-z0-9_]{1,40}){1,8}$")


def cheieScriere(cheie):
	"""'' daca cheia se poate scrie, altfel motivul."""
	if not isinstance(cheie, str) or not _CHEIE.match(cheie):
		return "cheie rea"
	if not any(cheie.startswith(p) or cheie + "." == p for p in SETARI_SCRIERE):
		return "cheie in afara listei permise"
	if SETARI_OPRITE.search(cheie):
		return "cheie oprita (parole, chei, date personale, modulele de acces)"
	return ""


def elementSetare(radacina, cheie):
	"""Elementul de setari pentru cheie ("config.av.videomode.HDMI"), urmand atributele si indicii (config.Nims.0...),
	sau None."""
	obj = radacina
	for parte in cheie.split(".")[1:]:
		try:
			if parte.isdigit():
				obj = obj[int(parte)]
			else:
				obj = getattr(obj, parte)
		except Exception:
			return None
	return obj if _esteElement(obj) and hasattr(obj, "save") else None


def scrieSetare(radacina, cheie, valoare, salveaza=None, dupa=None):
	"""(cod, mesaj): pune valoarea (din text, ca in fisierul settings) pe elementul cheii, cu efectele lui (notificarile
	elementului), il salveaza si salveaza fisierul (salveaza(): configfile.save). dupa(cheie): ce mai trebuie facut dupa
	schimbare (la tunere, actualizarea lor, ca din meniu)."""
	motiv = cheieScriere(cheie)
	if motiv:
		return 1, "(%s: %s)" % (motiv, cheie)
	if _elementPrivat_dupa_cheie(cheie):
		return 1, "(cheie oprita: %s)" % cheie
	el = elementSetare(radacina, cheie)
	if el is None:
		return 1, "(setare necunoscuta: %s)" % cheie
	if _elementPrivat(el):
		return 1, "(camp de parola: %s)" % cheie
	vechi = _valoare(el)
	try:
		nou = el.fromstring(valoare) if hasattr(el, "fromstring") else valoare
		el.value = nou
	except Exception as e:
		return 1, "(valoare respinsa pentru %s: %s)" % (cheie, type(e).__name__)
	try:
		el.save()
		if salveaza is not None:
			salveaza()
	except Exception as e:
		return 1, "(nu s-a putut salva %s: %s)" % (cheie, type(e).__name__)
	if dupa is not None:
		try:
			dupa(cheie)
		except Exception as e:
			_jurnal("dupa %s: %r" % (cheie, e))
	return 0, "%s: %s -> %s" % (cheie, vechi, _valoare(el))


def _elementPrivat_dupa_cheie(cheie):
	return bool(SETARI_OPRITE.search(cheie))


# ---------------------------------------------------------------- pachetele din feedurile noastre (instaleaza)

# numai pluginurile si modulele din feed (enigma2-plugin-...); dependintele le aduce opkg singur
PACHET = re.compile(r"^enigma2-plugin-[a-z0-9][a-z0-9.+-]{0,62}$")
# feedurile imaginii (stb.hdsatelit.com) si al pluginurilor si modulelor (Monea Software, moneasoftware.com)
GAZDE_NOASTRE = ("stb.hdsatelit.com", "feed.hdsatelit.com", "moneasoftware.com")
_SRC = re.compile(r"^\s*src(?:/gz)?\s+(\S+)\s+(\S+)")


def feeduriNoastre(dosar="/etc/opkg"):
	"""Numele surselor opkg ale feedurilor noastre (adresa pe una din GAZDE_NOASTRE)."""
	nume = []
	try:
		fisiere = sorted(os.listdir(dosar))
	except Exception:
		return nume
	for f in fisiere:
		if not f.endswith(".conf"):
			continue
		try:
			with open(os.path.join(dosar, f), encoding="utf-8", errors="replace") as h:
				for rand in h:
					m = _SRC.match(rand)
					if m:
						gazda = m.group(2).split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0].lower()
						if gazda in GAZDE_NOASTRE:
							nume.append(m.group(1))
		except Exception:
			continue
	return nume


def pachetInFeed(pachet, feeduri, liste="/var/lib/opkg/lists"):
	"""True daca pachetul e in indexul (descarcat de opkg update) al unuia dintre feedurile noastre."""
	semn = "Package: %s\n" % pachet
	for f in feeduri:
		try:
			with open(os.path.join(liste, f), encoding="utf-8", errors="replace") as h:
				if semn in h.read() + "\n":
					return True
		except Exception:
			continue
	return False


# ---------------------------------------------------------------- transponderele din lamedb (citire)

def transpondere(text_lamedb, namespace=None, maxim=1500):
	"""Transponderele din lamedb (numai sectiunea lor: namespace:tsid:onid si parametrii), fara canale si fara nimic
	al omului; namespace (hex) le alege pe ale unui satelit."""
	randuri = []
	sectiune = False
	cap = None
	ns = namespace.lower().lstrip("0") if namespace else None
	for rand in (text_lamedb or "").splitlines():
		r = rand.strip()
		if r == "transponders":
			sectiune = True
			continue
		if not sectiune:
			continue
		if r == "end":
			break
		if r == "/":
			cap = None
			continue
		if cap is None:
			cap = r
			continue
		if ns is not None and cap.split(":")[0].lower().lstrip("0") != ns:
			continue
		randuri.append("%s  %s" % (cap, r))
		if len(randuri) >= maxim:
			randuri.append("... (taiat la %d)" % maxim)
			break
	return "\n".join(randuri) or "(niciun transponder)"
