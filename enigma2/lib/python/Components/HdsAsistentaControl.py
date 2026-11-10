# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAsistentaControl.py: partea de control a Asistentei de la distanta (nivelul B, "Control complet"): textul ecranului
# deschis pe receptor (op "ecran"), tastele telecomenzii (op "taste") si scrierea intr-un camp de text (op "text"). Cu
# textul ecranului si cu tastele, echipa face prin meniuri orice ar face omul cu telecomanda.
#
# Echipa vede toate meniurile. Numai valorile conturilor, parolelor si cheilor sunt scoase din textul si imaginea
# trimise echipei. Ecranul omului ramane in clar. Scrierea unui secret cere oprirea asistentei inainte de prima litera.
#
# TASTELE: numai din lista alba TASTE (fara POWER si fara oprire), cel mult MAX_TASTE pe cerere, cu PAUZA_MS intre ele,
# trimise ca tastele adevarate ale telecomenzii (eRCMapper.inject cu dispozitivul nativ, ca in interfata web; fara el,
# harta de actiuni).
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
import unicodedata
from functools import lru_cache
from urllib.parse import unquote, urlsplit

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
TEXT_MAXIM = 200

# campurile de parola si de PIN (clasele elementelor de setari): echipa nu le scrie (scrieSetare)
CAMPURI_PAROLA = ("ConfigPassword", "ConfigPIN")

# Curatarea secretelor din textele care PLEACA spre echipa (jurnalele, Tools/HdsJurnalInterfata.py; raportul de
# setari si tot textul brokerului, Components/HdsAsistentaBroker.mascheaza; recunoasterea randurilor secrete din
# /setari). Nu schimba ecranul omului. Numai iesirea spre echipa pierde valorile private.
# Cheile interne si etichetele secretelor, cu sau fara diacritice.
_SECRET = re.compile(r"(?i)(parol|password|passwd|passphrase|(?:^|[._\s])(?:pass|pwd|psk)(?:\b|[._])|token|secret|jeton|"
	r"chei[ae]|api[ _.-]?key|key(?:\b|[._0-9])|(?:^|[._\s])pin(?:\b|[._0-9])|servicepin|setuppin|"
	r"auth|cookie|cod[ _.-]?(?:de[ _.-]?)?asociere|(?:^|[._\s])(?:biss|cw)(?:\b|[._0-9])|"
	r"control[ _.-]?word|cuvant[ _.-](?:de[ _.-])?control)")
# In text natural, numarul sau numele unei taste arata sensul lui key. Caile interne (remote.key, hotkey etc.)
# si cheile de acces raman secrete; un alt secret din acelasi text se verifica in continuare.
_CHEIE_TASTA = re.compile(r"(?i)(?<![\w.-])(?:hotkey|(?:[0-9]|red|green|yellow|blue|ok|exit|menu|info|epg|"
	r"power|volume|channel|up|down|left|right|arrow|function|keyboard|hot|remote(?:[ -]control)?|button)\s+key)\b(?![._0-9])")
_CONTEXT_CHEIE_ACCES = re.compile(r"(?i)\b(?:api|access|public|private|encryption|aes|rsa|ssh|wpa|wep|wi[ -]?fi|biss)\b")
_URL_PAROLA = re.compile(r"(?i)([a-z][a-z0-9+.-]*://[^/\s:@]+:)[^\s/@]*(@)")
# adresa unui canal de la un furnizor are contul in cale: /live/<utilizator>/<parola>/<id>.ts (Components/HdsIptvClient.py)
_URL_CALE_CONT = re.compile(r"(?i)(://[^/\s]+/(?:live|movie|series|timeshift)/)[^/\s]+/[^/\s]+/")
_URL_PARAMETRU = re.compile(r"([?&;])([^=&#;\s]+)=([^&#;\s]*)")
_ATRIBUIRE = re.compile(r"^([^=:|\n]+)(\s*[=:|]\s*)(.*)$")
_SECRET_JURNAL = re.compile(r"(?i)(\b(?:password|passwd|passphrase|parol[ăa]|psk|token|secret|pwd|pass|pin|key|"
	r"api[ _.-]?key|chei[ae](?:[ _.-]?api)?|biss[0-9]*|cw|control[ _.-]?word|cuv[âa]nt[ _.-](?:de[ _.-])?control)\s*[=:]\s*)"
	r"(?:\"[^\"]*\"|'[^']*'|[^\s,;&]+)")
_BEARER = re.compile(r"(?i)(\bbearer\s+)[a-z0-9._~+/=-]+")
_VALOARE_CONT = re.compile(r"[^,;&]*")
_ANTET_SECRET = re.compile(r"(?i)(\b(?:authorization|(?:set-)?cookie)\s*[=:]\s*).*$")


# Fiecare regula de mai sus cere macar unul dintre semnele = : | sau cuvantul bearer (o adresa cu cont are "://"). Un
# text fara ele nu se poate schimba, deci nu mai trece prin cele sapte expresii (rapoartele 573125 si 891312:
# capturile pentru web verificau la fiecare schimbare de pe ecran toate randurile listelor mari ale AJPanel, iar firul
# principal statea ocupat cate doua minute).
_POATE_SECRET = re.compile(r"(?i)[=:|]|bearer")
_BETA_ID = re.compile(r"(?i)hds_beta\.(?:id|cod)\b")


def cheieSecreta(cheie):
	return _cheieSecreta(str(cheie))


@lru_cache(maxsize=4096)
def _cheieSecreta(cheie):
	text = "".join(c for c in unicodedata.normalize("NFKD", cheie) if not unicodedata.combining(c))
	if not _CONTEXT_CHEIE_ACCES.search(text):
		text = _CHEIE_TASTA.sub("", text)
	return bool(_SECRET.search(text) or _BETA_ID.search(text))


@lru_cache(maxsize=8192)
def _textCuSecret(text):
	"""Raspunsul pentru acelasi text se tine minte: listele se reverifica la fiecare schimbare de pe ecran."""
	return mascheazaSecrete(text) != text


def mascheazaSecrete(text):
	"""Pastreaza etichetele si adresele, inlocuind numai valorile secrete."""
	if not text:
		return ""
	if not _POATE_SECRET.search(text):
		return mascheazaConturi(text) if "%3a" in text.lower() else text
	randuri = []
	for rand in (text or "").splitlines():
		rand = _URL_PAROLA.sub(r"\1***\2", rand)
		rand = _URL_CALE_CONT.sub(r"\1***/***/", rand)
		rand = _URL_PARAMETRU.sub(lambda m: m.group(1) + m.group(2) + "=***"
			if cheieSecreta(unquote(m.group(2))) or m.group(2).lower() in ("pw", "sid", "sessionid", "sig", "signature")
			else m.group(0), rand)
		m = _ATRIBUIRE.match(rand)
		if m and (cheieSecreta(m.group(1)) or _etichetaPrivata(m.group(1), False)):
			rand = m.group(1) + m.group(2) + "***"
		elif m and _etichetaPrivata(m.group(1), True):
			# numele de utilizator: numai valoarea lui, pana la , ; sau & (optiunile de dupa, de pilda password=, trec
			# prin curatarea de mai jos)
			valoare = _VALOARE_CONT.match(m.group(3)).group(0)
			rand = m.group(1) + m.group(2) + "***" + m.group(3)[len(valoare):]
		rand = _ANTET_SECRET.sub(r"\1***", rand)
		taste = () if _CONTEXT_CHEIE_ACCES.search(rand) else tuple(_CHEIE_TASTA.finditer(rand))
		rand = _SECRET_JURNAL.sub(lambda m: m.group(0) if any(t.start() <= m.start() < t.end() for t in taste)
			else m.group(1) + "***", rand)
		rand = _BEARER.sub(r"\1***", rand)
		randuri.append(rand)
	return mascheazaConturi("\n".join(randuri))

# Conturile din adresele salvate nu pleaca spre echipa, inclusiv forma din referintele de serviciu
# (http%3a//nume%3aparola@gazda), unde mascheazaSecrete nu ajunge.
_URL_CONT = re.compile(r"(?i)([a-z][a-z0-9+.-]*(?:://|%3a//))[^/\s@?#]*(@|%40)")
_URL_CALE_CONT_CODAT = re.compile(r"(?i)(%3a//[^/\s]+/(?:live|movie|series|timeshift)/)[^/\s]+/[^/\s]+/")
_URL_UTILIZATOR = re.compile(r"(?i)([?&;](?:user|username|usr|uname|login|utilizator)=)[^&#;\s]*")


def mascheazaConturi(text):
	"""Numele de utilizator din adrese devine stelute; gazda, portul, calea si ceilalti parametri raman."""
	rand = _URL_CONT.sub(r"\1***\2", text or "")
	rand = _URL_CALE_CONT_CODAT.sub(r"\1***/***/", rand)
	return _URL_UTILIZATOR.sub(r"\1***", rand)


RANDURI_LISTA = 40          # cate randuri dintr-o lista (in jurul celui ales)
TEXT_ECRAN_MAX = 16 * 1024

_REFERINTA = re.compile(r"^\d+:\d+:[0-9A-Fa-f]+:")
# numele interne din randurile meniurilor (entryID, greutatea): litere mici, cifre, _ . -, fara spatii
_ID_INTERN = re.compile(r"^[a-z0-9_.-]+$")
# atributele cu numele unui rand facut dintr-un obiect
_ATRIBUTE_TEXT = ("titlu", "nume", "text", "name", "title", "eticheta")


def _jurnal(text):
	print("[HdsAsistentaControl] %s" % text)


def N_(text):
	"""Marcaj pentru catalog; traducerea se face cand mesajul este afisat."""
	return text


TEXT_OPRESTE_SECRET = N_("Oprește asistența de la distanță înainte să scrii parola sau cheia. "
	"O poți porni din nou după ce salvezi. Echipa HD Satelit nu are nevoie de parola ta.")
TEXT_OPRESTE_INTERFATA = N_("Oprește asistența de la distanță înainte să deschizi interfața web a modulului. "
	"O poți porni din nou după ce închizi pagina.")


def asistentaActiva():
	"""Cat poate pleca ceva spre echipa. Dupa Oprește (SE_OPRESTE) nu mai pleaca nimic: un raspuns facut dupa oprire se
	arunca (HdsAsistenta.Sesiune._trimite_raspuns si _ceruta_raspuns), deci omul poate scrie parola imediat, fara sa
	astepte cererea serverului care se mai incheie."""
	from Components import HdsAsistenta
	sesiune = HdsAsistenta.sesiune()
	return sesiune is not None and sesiune.activa()


def _sesiuneInterfata():
	"""Sesiunea enigma2 pentru campurile care nu-si stiu ecranul (Input fara hdsSession, ConfigPassword in afara
	unei liste): mesajul trebuie sa apara, nu doar tasta sa fie oprita."""
	try:
		from Screens.HdsAsistentaSemn import _session
		return _session()
	except Exception:
		return None


def cereOprirePentruSecret(session=None):
	"""True refuza scrierea. Nu retine si nu reia caracterul care a pornit avertismentul."""
	if not asistentaActiva():
		return False
	if session is None:
		session = _sesiuneInterfata()
	if session is not None and not getattr(session, "hdsAvertismentSecret", False):
		from Screens.MessageBox import MessageBox
		session.hdsAvertismentSecret = True

		def raspuns(opreste=False):
			session.hdsAvertismentSecret = False
			if opreste:
				from Components import HdsAsistenta
				HdsAsistenta.opreste()

		session.openWithCallback(raspuns, MessageBox, _(TEXT_OPRESTE_SECRET), MessageBox.TYPE_YESNO,
			default=False, list=[(_("Oprește asistența"), True), (_("Înapoi"), False)])
	return True


_CONT = re.compile(r"(?i)(?:^|[._\s-])(?:user(?:name)?|usr|uname|login|utilizator)(?:[0-9]*$|[._\s-])|nume\s+de\s+utilizator")
# Etichetele ecranelor sunt traduse: parola si numele de utilizator in limbile imaginii (dupa scoaterea diacriticelor),
# si cheile lipite fara despartitor (httpuser, httppwd din sectiunea [webif] a modulelor de acces).
_PAROLA_LIMBI = re.compile(r"(?i)passw|pwd(?:\b|[._0-9])|kennwort|mot de passe|contrase|wachtw|has[lł]o|heslo|"
	r"jelszo|lozink|geslo|salasan|adgangskode|losenord|passord|parool|slaptazod|sifre|senha|lykilor|"
	r"парол|κωδικ|كلمة (?:المرور|السر)")
_CONT_LIMBI = re.compile(r"(?i)user(?:name)?[0-9]*\s*$|benutzer|utilisateur|usuari|utente|gebruiker|uzytkownik|"
	r"uzivatel|felhasznalo|korisni[kc]|uporabni|kayttaja|bruger|anvandar|bruker|kasutaja|naudotoj|lietotaj|"
	r"kullan[ıi]c[ıi]|notand|utilizador|пользовател|"
	r"користувач|корисни|"
	r"χρηστη|مستخدم")


@lru_cache(maxsize=4096)
def _etichetaPrivata(eticheta, cont):
	"""Parola (si, cu cont=True, numele de utilizator) dupa o eticheta in orice limba a imaginii."""
	text = "".join(c for c in unicodedata.normalize("NFKD", eticheta) if not unicodedata.combining(c))
	if _PAROLA_LIMBI.search(text):
		return True
	return bool(cont and (_CONT.search(text) or _CONT_LIMBI.search(text)))


def campSecret(element=None, eticheta="", cont=False):
	"""Un camp de parola/cheie; cont=True include si numele de utilizator numai pentru iesirea spre echipa."""
	return bool(getattr(element, "hdsSecret", False) or (element is not None and _elementParola(element))
		or cheieSecreta(eticheta) or _etichetaPrivata(str(eticheta), bool(cont)))


def _componentaSecreta(comp, nume):
	"""O componenta a ecranului (Label, StaticText) cu valoare privata, dupa marcaj, clasa sau numele ei. Tastele
	colorate (key_red, key_green ...) spun numai ce face tasta: numele lor nu le face secrete."""
	if str(nume).startswith("key_"):
		return campSecret(comp)
	return campSecret(comp, nume, cont=True)


def ecranCuCampSecret(ecran):
	if getattr(ecran, "hdsCampSecret", False):
		return True
	try:
		cur = ecran["config"].getCurrent()
		if cur and len(cur) > 1:
			return campSecret(cur[1], cur[0])
	except Exception:
		pass
	return campSecret(eticheta=_titlu(ecran))


def interfataLocalaBlocata(adresa, interfete=None, rezolva=None, verifica_chiar_oprita=False):
	"""Pe fir separat: numai adresele locale pe porturile modulelor active sunt oprite cat merge asistenta."""
	if not verifica_chiar_oprita and not asistentaActiva():
		return False
	import socket
	try:
		from Components.HdsParolaLocala import esteAdresaLocala
		u = urlsplit(adresa)
		if u.scheme.lower() not in ("http", "https"):
			return False
		port = u.port or (443 if u.scheme.lower() == "https" else 80)
		gazda = (u.hostname or "").rstrip(".").lower()
		locala = gazda in ("localhost", "localhost.localdomain", socket.gethostname().lower())
		if esteAdresaLocala(gazda) or gazda in ("0.0.0.0", "::"):
			locala = True
		if not locala:
			adrese = [r[4][0].split("%", 1)[0]
				for r in (rezolva or socket.getaddrinfo)(gazda, port, 0, socket.SOCK_STREAM)]
			locala = any(esteAdresaLocala(ip) or ip in ("0.0.0.0", "::") for ip in adrese)
		if not locala:
			return False
		if interfete is None:
			from Components import HdsModuleAcces, HdsInterfeteCam
			interfete = list(HdsModuleAcces.interfete_web())
			rezultat = HdsInterfeteCam.rezultat() or {}
			for modul in rezultat.get("cam_uri", ()):
				interfete.extend(i for i in modul.get("interfete", ()) if i.get("web"))
		return port in {int(i.get("port") or 0) for i in interfete}
	except Exception:
		# O navigare locala care nu se poate verifica nu pleaca spre interfata cu conturile omului.
		return True


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


# ---------------------------------------------------------------- stiva ecranelor

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


def _elementParola(element):
	return any(n in CAMPURI_PAROLA for n in _clase(element))


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
		for e in lista:
			if isinstance(e, (list, tuple)) and len(e) >= 2 and _esteElement(e[1]):
				gasite.append(e)
	return gasite


def _esteElement(x):
	return hasattr(x, "getText") and hasattr(x, "value") and not isinstance(x, (str, bytes))


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
	if _elementParola(element):
		# parola: ce arata randul pe televizor ("pusă" / "nepusă", sau textul cat omul il scrie)
		try:
			return str(element.getMulti(False)[1])
		except Exception:
			return ""
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
			valoare = "[ascuns]" if campSecret(e[1], e[0], cont=True) else _valoare(e[1])
			rand = "%s [%d] %s = %s" % (semn, i + 1, e[0], valoare)
			if i == ales and len(e) > 2 and isinstance(e[2], str) and e[2].strip():
				rand += "\n      ajutor: " + e[2].strip()
		else:
			rand = "%s [%d] %s" % (semn, i + 1, _textRand(e))
		randuri.append(rand)
	if sfarsit < n:
		randuri.append("  ... încă %d rânduri" % (n - sfarsit))
	return randuri


# flagurile unei referinte de serviciu (lib/service/iservice.h)
_FLAG_DOSAR = 7          # isDirectory | mustDescent | canDescent
_FLAG_MARCAJ = 64        # isMarker
_FLAG_ASCUNS = 512       # isInvisible


def _cheieServiciu(ref):
	f = getattr(ref, "toCompareString", None) or getattr(ref, "toString", None)
	try:
		return f() if callable(f) else ""
	except Exception:
		return ""


def _numeServiciu(ref, centru):
	nume = ""
	try:
		nume = ref.getName() or ""
		if not nume:
			info = centru.info(ref)
			nume = (info.getName(ref) if info is not None else "") or ""
	except Exception:
		pass
	# semnele de evidentiere din numele de canal (0x86/0x87, in UTF-8 C2 86 / C2 87)
	for semn in ("\xc2\x86", "\xc2\x87", "\x86", "\x87"):
		nume = nume.replace(semn, "")
	return " ".join(nume.split())


def _randuriServicii(nume, comp):
	"""Lista de canale sau de buchete (Components/ServiceList: eListbox cu eListboxServiceContent, fara lista Python):
	numele din radacina ei, cu randul ales, fara referinte. None cand comp nu e o lista de servicii."""
	f = getattr(comp, "getRootServices", None)
	if not callable(f) or not callable(getattr(comp, "getCurrent", None)):
		return None
	try:
		from enigma import eServiceCenter, eServiceReference
		centru = eServiceCenter.getInstance()
		root = getattr(comp, "getRoot", lambda: None)()
		adaugate = getattr(comp, "hdsAdaugate", None)
		if root is not None and "FROM SATELLITES" in (root.getPath() or "") and isinstance(adaugate, list):
			# Satelitii sunt numiti si grupati pe TV; recitirea radacinii da dosare brute fara nume.
			refs = list(adaugate)
		else:
			refs = [eServiceReference(s) for s in f()]
		curent = comp.getCurrent()
		ales_cheie = _cheieServiciu(curent) if curent is not None and curent.valid() else ""
	except Exception as e:
		_jurnal("lista de canale: %s" % e)
		return None
	randuri = []
	ales = None
	for ref in refs:
		flags = getattr(ref, "flags", 0) or 0
		if flags & _FLAG_ASCUNS:
			continue
		n = _numeServiciu(ref, centru) or "(fără nume)"
		if flags & _FLAG_MARCAJ:
			n = "--- %s ---" % n
		elif (flags & _FLAG_DOSAR) == _FLAG_DOSAR:
			n += " (buchet)"
		if ales is None and ales_cheie and _cheieServiciu(ref) == ales_cheie:
			ales = len(randuri)
		randuri.append(n)
	if not randuri:
		return ['Lista "%s": goală' % nume]
	n = len(randuri)
	inceput = 0
	if ales is not None and ales >= RANDURI_LISTA // 3:
		inceput = max(0, min(ales - RANDURI_LISTA // 3, n - RANDURI_LISTA))
	sfarsit = min(n, inceput + RANDURI_LISTA)
	rez = ['Lista "%s" (rândul %s din %d):' % (nume, (ales + 1) if ales is not None else "?", n)]
	for i in range(inceput, sfarsit):
		rez.append("%s [%d] %s" % (">" if i == ales else " ", i + 1, randuri[i]))
	if sfarsit < n:
		rez.append("  ... încă %d rânduri" % (n - sfarsit))
	return rez


def textEcran(ecrane, mod_ascii=False, ssh_deschis=False):
	"""Textul ecranului de sus, pentru echipa: stiva (clasele si titlurile), listele cu randul ales, setarile
	"eticheta = valoare", textele si tastele colorate, la fel cum se vad pe televizor. `ssh_deschis` ramane in
	semnatura pentru apelurile de dinainte (nu mai schimba nimic)."""
	if not ecrane:
		return "(niciun ecran deschis)"
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
		if r is None:
			r = _randuriServicii(nume, comp)
		if r is not None:
			liste.extend(r)
			continue
		if _componentaSecreta(comp, nume) or (getattr(sus, "hdsCampSecret", False) and nume in ("text", "input")):
			texte.append("  %s: [ascuns]" % nume)
			continue
		t = _text(comp)
		if t is None or not t.strip():
			continue
		t = mascheazaSecrete(t)
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
	return mascheazaSecrete(text)


def _instanteComponenta(ecran, comp):
	instanta = getattr(comp, "instance", None)
	if instanta is not None:
		return [instanta]
	return [r.instance for r in getattr(ecran, "renderer", ())
		if getattr(r, "source", None) is comp and getattr(r, "instance", None) is not None]


def _randSecret(rand):
	if isinstance(rand, (tuple, list)) and len(rand) >= 2 and _esteElement(rand[1]):
		return campSecret(rand[1], rand[0], cont=True) or _textCuSecret(str(rand[1].getText()))
	if _textCuSecret(_textRand(rand)):
		return True
	# Listele multi-content pot avea adrese lungi pe care rezumatul textului le omite.
	if isinstance(rand, (tuple, list)):
		return any(_randSecret(x) for x in rand if isinstance(x, (str, tuple, list)))
	return isinstance(rand, str) and _textCuSecret(rand)


def _dreptunghi(instanta):
	p = instanta.getAbsolutePosition()
	s = instanta.size()
	return p.x(), p.y(), s.width(), s.height()


def dreptunghiuriSecrete(ecrane):
	"""Zonele credentialelor din OSD. None refuza captura cand pozitia nu poate fi aflata sigur."""
	rez = []
	for ecran in ecrane:
		if getattr(ecran, "shown", True) is False:
			continue
		try:
			componente = list(ecran.items())
		except Exception:
			continue
		for nume, comp in componente:
			lista = getattr(comp, "list", None)
			secrete = [i for i, rand in enumerate(lista or ()) if _randSecret(rand)] \
				if isinstance(lista, (tuple, list)) else []
			secret = (_componentaSecreta(comp, nume)
				or (getattr(ecran, "hdsCampSecret", False) and nume in ("text", "input")))
			text = _text(comp)
			if text and mascheazaSecrete(text) != text:
				secret = True
			if not secret and not secrete:
				continue
			instante = _instanteComponenta(ecran, comp)
			if not instante:
				return None
			for instanta in instante:
				try:
					x, y, latime, inaltime = _dreptunghi(instanta)
					if secrete and not secret:
						sus = instanta.getTopIndex()
						rand_inaltime = instanta.getItemHeight()
						if rand_inaltime <= 0:
							return None
						for i in secrete:
							pozitie = (i - sus) * rand_inaltime
							if 0 <= pozitie < inaltime:
								# Numai randul cu datele contului; restul meniului ramane vizibil.
								rez.append((x, y + pozitie, latime, min(rand_inaltime, inaltime - pozitie)))
					else:
						rez.append((x, y, latime, inaltime))
				except Exception:
					return None
	return rez


def navigatorExternPeEcran():
	try:
		from Plugins.Extensions.HdsNavigator import lansator
	except ImportError:
		return False     # imaginea fara navigator: nu are ce pagina sa fie pe ecran
	navigator = lansator.activ()
	return navigator is not None and navigator.stare == lansator.ARATAT


def curataCapturaEchipa(octeti, ecrane, marime):
	"""Curata numai copia din RAM trimisa echipei. Nu modifica framebuffer-ul si nu pastreaza captura pe disc."""
	# Pagina nativa e desenata de alt proces. OSD nu poate afla sigur unde ii sunt conturile.
	if navigatorExternPeEcran():
		return None
	zone = dreptunghiuriSecrete(ecrane)
	if zone is None:
		return None
	if not zone:
		return octeti
	try:
		import io
		import math
		from PIL import Image, ImageDraw
		with Image.open(io.BytesIO(octeti)) as sursa:
			imagine = sursa.convert("RGB")
		latime, inaltime = marime
		if latime <= 0 or inaltime <= 0:
			return None
		sx, sy = imagine.width / float(latime), imagine.height / float(inaltime)
		desen = ImageDraw.Draw(imagine)
		for x, y, w, h in zone:
			if w <= 0 or h <= 0:
				return None
			# Acoperim si doua blocuri JPEG MCU de 16 pixeli, ca nici contururile cromatice sa nu ramana.
			x0, y0 = max(0, math.floor(x * sx) - 32), max(0, math.floor(y * sy) - 32)
			x1, y1 = min(imagine.width, math.ceil((x + w) * sx) + 32), min(imagine.height, math.ceil((y + h) * sy) + 32)
			if x1 > x0 and y1 > y0:
				desen.rectangle((x0, y0, x1 - 1, y1 - 1), fill=(20, 28, 40))
		iesire = io.BytesIO()
		imagine.save(iesire, format="PNG")
		return iesire.getvalue()
	except Exception:
		return None


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
	"""Tastele unei cereri, apasate pe rand (pas() la fiecare tic de PAUZA_MS, pe firul enigma2), ca de pe telecomanda
	omului, pe orice ecran (fara ecrane private)."""

	def __init__(self, taste, ecrane, apasa=apasaTasta, ssh_deschis=None):
		self.taste = list(taste)
		self.ecrane = ecrane            # functie: stiva de acum
		self.apasa = apasa
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
		self.apasa(TASTE[nume], lung)
		self.trimise.append(nume + (SUFIX_LUNG if lung else ""))
		return bool(self.taste)


# ---------------------------------------------------------------- scrierea textului

def scrieText(ecrane, text, mod_ascii, scrie, ssh_deschis=False):
	"""(cod, mesaj): scrie text in campul deschis pe ecranul de sus. scrie(text) -> rezultatul lui
	HdsMouseEcran.MouseEcran.text (semnele, prin actiunea gotAsciiCode a ecranului). Refuzat numai cand nu e niciun camp
	de text deschis."""
	if not ecrane:
		return 1, "(niciun ecran deschis)"
	if ecranCuCampSecret(ecrane[-1]):
		return 1, TEXT_OPRESTE_SECRET
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
	r"name|ssid|wpa|wlan|hdswebcontrol|hds_beta|mount|nfs|cifs|smb|iptv)")
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
	if _elementParola(el):
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

# Instalarea accepta nume opkg; prezenta in feedul nostru se verifica separat.
PACHET_INSTALARE = re.compile(r"^[a-z0-9][a-z0-9+.-]{0,255}\Z")
# Dezinstalarea ramane numai pentru pluginuri si module.
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
						gazda = urlsplit(m.group(2)).hostname
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
	"""Transponderele din lamedb, cu numele canalelor grupate dupa namespace, TSID si ONID."""
	canale = {}
	linii = (text_lamedb or "").splitlines()
	try:
		i = linii.index("services") + 1
	except ValueError:
		i = len(linii)
	while i + 2 < len(linii) and linii[i].strip() != "end":
		cheie = linii[i].strip().split(":")
		nume = " ".join(linii[i + 1].split())[:200]
		i += 3
		try:
			tp = tuple(int(v, 16) for v in cheie[1:4])
			if len(tp) == 3 and nume:
				canale.setdefault(tp, []).append(nume)
		except ValueError:
			continue
	randuri = []
	sectiune = False
	cap = None
	ns = namespace.lower().lstrip("0") if namespace else None
	for rand in linii:
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
		try:
			nume = canale.get(tuple(int(v, 16) for v in cap.split(":")), [])
		except ValueError:
			nume = []
		if nume:
			randuri[-1] += "  | Canale: " + ", ".join(nume)
		if len(randuri) >= maxim:
			randuri.append("... (taiat la %d)" % maxim)
			break
	return "\n".join(randuri) or "(niciun transponder)"
