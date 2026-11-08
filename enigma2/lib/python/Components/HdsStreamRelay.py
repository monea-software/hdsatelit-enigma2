# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsStreamRelay.py: Stream Relay (0.7.0). Canalele alese de om se redau prin releul de flux: un serviciu de pe
# receptor care cere canalul serverului de flux al imaginii (Hds/DabT2/server8001.py, 127.0.0.1:8001), il decodeaza si
# il da mai departe pe portul lui (17999 din fabrica). Televizorul reda atunci fluxul releului, ca un canal (sursa
# eHdsFluxHttp a serviciului DVB, lib/service/hdsfluxhttp.h), cu teletextul, subtitrarile si pistele lui.
#
# LISTA: FISIER (/etc/enigma2/whitelist_streamrelay, numele obisnuit, pe care il citesc si pluginurile si interfetele
# web scrise pentru alte imagini), un canal pe rand, referinta fara nume si fara cale (1:0:19:283D:3FB:1:C00000:0:0:0:).
# Intra numai canalele DVB (tipul 1, fara cale, fara dosar si fara marcaj). Fisierul se citeste la prima cerere si din
# nou cand se schimba (marime, mtime, inod), se scrie dintr-o miscare (temporar + fsync + rename). Un fisier care nu se
# poate citi (alta eroare decat lipsa lui) nu se scrie niciodata peste: lista ramane cea din memorie, numai citire.
# Se pune si se scoate din meniul listei de canale (Adaugă la Stream Relay / Scoate din Stream Relay,
# Screens/ChannelSelection.py) si din lista de canale din web (canale_web.py, butonul de langa stea).
#
# SETARILE (config.misc.acces_streamrelay_*, Components/UsageConfig.py; Meniu > Acces condiționat > Stream Relay, in web
# /setari?id=hds_stream_relay): adresa releului (din ea se ia numai gazda), portul (17999) si intarzierea la trecerea de
# la un canal prin releu la altul (ms). Serverul de flux al imaginii asculta numai pe 127.0.0.1, deci releul trebuie sa
# ruleze pe receptor: o adresa din afara (alt aparat din retea) nu se foloseste, canalul porneste direct (un rand in
# jurnal). Exceptia (0.7.0): cu setarea "Fluxuri pentru alte aparate din rețeaua de acasă"
# (config.misc.hds_fluxuri_retea_acasa) pornita, serverul de flux primeste si adresele private, deci si un releu de pe
# alt aparat din reteaua de acasa (adresa privata, releuInRetea) se foloseste.
#
# IN BROWSER (TV in browser, "Vezi live", playerele externe VLC / Kodi): Components/HdsTransmisie.py ia fluxul unui canal
# din lista tot de la releu (adresaReleu, FluxReleuInTeava), nu direct de la tuner.
#
# ZAP (cost zero fara lista): legatura la Navigation.playServiceExtensions se pune numai cat lista are canale (la
# pornire, numai daca fisierul exista: mytest.py). Pentru un canal din lista:
#  - daca nimic nu asculta la adresa releului (releul oprit), canalul porneste direct, ca fara Stream Relay, iar pe
#    televizor apare de ce (motivReleu, mai jos);
#  - altfel playerul primeste referinta releului (aceeasi, cu spatiul de nume + 1, ca serverul de flux, la care releul
#    cere canalul adevarat, sa nu ia redarea drept acelasi serviciu; calea http://<gazda>:<port>/<referinta>), iar
#    referinta din navigatie ramane cea a canalului: bara, ghidul, sigla si lista de canale vad canalul obisnuit;
#  - de la un canal prin releu la altul, playerul porneste dupa intarzierea din setari (releul elibereaza canalul vechi).
# Serverul de flux da releului canalul criptat, cu PID-urile ECM, fara inscriere la modulul de acces
# (setDecodareMaiTarziu, ca inregistrarile „Decodează mai târziu”): decodarea o face releul.
#
# Pentru pluginurile scrise pentru alte imagini, Screens/InfoBarGenerics.streamrelay da acelasi obiect (releu()):
# checkService(ref), streamrelayChecker(ref) -> (ref, prin_releu), reload(), toggle(nav, ref), data.
#
# DE CE NU RASPUNDE RELEUL (motivReleu, 0.7.1): pe receptor releul il da modulul de acces; cand nu raspunde, textul spune
# cauza vazuta de om, dupa modulele citite ca in ecranul „Module de acces condiționat” (Components/HdsModuleAcces.py,
# toate felurile, fara niciun nume de modul in cod): niciun modul ales; modulul ales nu ruleaza; modulul ruleaza, dar nu
# da releul pe port; altfel (releu pe alt aparat, citire cazuta) adresa si portul. La zap, un canal din lista cu releul
# care nu raspunde porneste direct, ca inainte, iar pe televizor apare o data motivul (mesaj scurt, care se inchide
# singur; acelasi motiv iar numai dupa REPETARE_MESAJ_S). STAREA (stare(), liniiStare()): cate canale are lista, de
# unde se adauga, daca releul raspunde si de ce nu; o arata ecranul setarilor Stream Relay (atributul hdsStare al
# setarilor, Screens/Setup.py), aceeasi pagina in web (setari_web.py) si pagina Acces condiționat din web
# (acces_conditionat_web.py).
#
# Partea de sus a fisierului nu importa nimic din enigma2 (probele de pe PC); legaturile cu enigma2 au importuri tarzii.

import errno
import os
import socket
import threading
import time

FISIER = "/etc/enigma2/whitelist_streamrelay"
PORT_IMPLICIT = 17999
GAZDE_LOCALE = ("127.0.0.1", "localhost")
TERMEN_VERIFICARE_S = 0.3        # cat asteapta verificarea ca releul asculta (pe 127.0.0.1 raspunsul e pe loc)
MAX_CANALE = 2000
MAX_OCTETI = 256 * 1024
# steagurile referintei care nu sunt canale: dosar, coborare, marcaj (eServiceReference)
_FARA_CANAL = 1 | 2 | 64
# mesajul de pe televizor cand releul nu raspunde la zap: cat sta (s) si dupa cat se arata iar acelasi motiv (s)
TIMP_MESAJ_S = 8
REPETARE_MESAJ_S = 600


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele se traduc la folosire."""
	return text


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi pe PC."""
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def ngettext(unu, multe, n):
	"""Pluralul tradus (Components/HdsPlural.ngettext: o Forma, al carei % merge si cand forma pentru 1 n-are numarul,
	in romana „un canal”, „2 canale”); pe PC, forma romaneasca fara traducere."""
	try:
		from Components.HdsPlural import ngettext as plural
		return plural(unu, multe, n)
	except Exception:
		return unu if n == 1 else multe


# acelasi text ca HdsTransmisie.TEXT_RELEU_OPRIT (TV in browser): adresa si portul
TEXT_RELEU_OPRIT = N_("Stream Relay nu răspunde la %s:%d. Verifică adresa și portul din setările Stream Relay.")
TEXT_RELEU_FARA_MODUL = N_("Modulul de acces %s nu rulează, de aceea Stream Relay nu răspunde. Pornește-l din Meniu > Acces condiționat sau din pagina Module de acces condiționat.")
TEXT_RELEU_NICIUN_MODUL = N_("Niciun modul de acces nu e pornit, de aceea Stream Relay nu răspunde. Alege unul în Meniu > Acces condiționat.")
TEXT_RELEU_MODUL_FARA_RELEU = N_("Modulul de acces %s rulează, dar nu dă Stream Relay pe portul %d. Pornește Stream Relay în setările modulului sau pune portul lui în setările Stream Relay.")
TEXT_PORNESTE_DIRECT = N_("Canalul pornește fără Stream Relay.")
TEXT_RELEU_MERGE = N_("Stream Relay răspunde la %s:%d.")
TEXT_LISTA = N_("Lista Stream Relay: %s.")
TEXT_LISTA_GOALA = N_("Lista Stream Relay e goală, deci niciun canal nu trece prin releu.")
TEXT_DE_UNDE = N_("Canalele se adaugă din lista de canale (MENU pe canal > Adaugă la Stream Relay) sau din pagina Canale a interfeței web (butonul SR).")
TEXT_NUMAI_CITIRE = N_("Lista Stream Relay nu se poate citi; rămâne cea de dinainte.")


def _jurnal(text):
	print("[HdsStreamRelay] %s" % text)


# ------------------------------------------------------------------ referintele (fara enigma2)

def cheie(ref):
	"""Cheia de lista a unui canal DVB: "1:<steaguri>:<8 campuri hex>:" (hex cu litere mari, fara zerouri in fata),
	sau None pentru ce nu poate intra in Stream Relay (alt tip, cale, dosar, marcaj, referinta stricata). `ref` e o
	eServiceReference sau textul ei."""
	if ref is None:
		return None
	text = ref if isinstance(ref, str) else ref.toString()
	parti = text.split(":")
	if len(parti) < 10:
		return None
	try:
		tip = int(parti[0])
		steaguri = int(parti[1])
		date = [int(x or "0", 16) for x in parti[2:10]]
	except ValueError:
		return None
	if tip != 1 or steaguri & _FARA_CANAL:
		return None
	if len(parti) > 10 and parti[10].strip():
		return None
	if not date[1]:  # fara numarul serviciului (SID) nu e un canal
		return None
	return "1:%d:%s:" % (steaguri, ":".join("%X" % x for x in date))


def gazdaDinAdresa(adresa):
	"""Gazda din adresa scrisa in setari ("http://127.0.0.1:17999", "127.0.0.1", "localhost:17999"); "" daca nu e."""
	a = (adresa or "").strip()
	if "://" in a:
		a = a.split("://", 1)[1]
	a = a.split("/", 1)[0]
	if a.startswith("["):
		return ""
	return a.rsplit(":", 1)[0] if ":" in a else a


def releuInRetea(gazda):
	"""Un releu de pe alt aparat din reteaua de acasa (adresa IPv4 privata), numai cu setarea "Fluxuri pentru alte aparate
	din rețeaua de acasă" pornita (Hds/DabT2/server8001.py: atunci serverul de flux il primeste)."""
	try:
		from Hds.DabT2 import server8001
		return server8001.retea_pornita() and server8001.adresa_privata(gazda)
	except Exception:
		return False


def releuPermis(gazda):
	"""Gazda releului se poate folosi: pe receptor (127.0.0.1, localhost) sau in reteaua de acasa permisa."""
	return gazda in GAZDE_LOCALE or releuInRetea(gazda)


def textReleu(cheie_canal, gazda, port, nume=""):
	"""Textul referintei redate prin releu pentru un canal din lista: spatiul de nume + 1 (camp 7), calea
	http://gazda:port/<cheie> (cu ':' scrise %3a, ca in orice referinta), apoi numele."""
	parti = cheie_canal.split(":")
	parti[6] = "%X" % ((int(parti[6], 16) + 1) & 0xFFFFFFFF)
	cale = "http://%s:%d/%s" % (gazda, port, cheie_canal)
	nume = (nume or "").replace(":", " ").replace("\n", " ")
	return "%s%s:%s" % (":".join(parti[:10]) + ":", cale.replace(":", "%3a"), nume)


# ------------------------------------------------------------------ de ce nu raspunde releul (0.7.1)

def _moduleAcces(H=None):
	"""Modulele de acces de pe receptor, ca in ecranul „Module de acces condiționat” (toate felurile):
	{"ruleaza": [sufixele celor care ruleaza], "alese": [sufixele celor alese care nu ruleaza]}, sau None cand nu se
	pot citi sau receptorul n-are niciun fel de module (nu se stie nimic despre ele). `H` e Components.HdsModuleAcces
	(probele dau unul fals)."""
	try:
		if H is None:
			from Components import HdsModuleAcces as H
		ruleaza, alese = [], []
		stari = H.feluri_de_aratat(H.SistemAcces())
		if not stari:
			return None
		for st in stari:
			for e in st.emulatoare:
				if e.pids:
					ruleaza.append(e.sufix)
				elif e.ales:
					alese.append(e.sufix)
		return {"ruleaza": ruleaza, "alese": alese}
	except Exception as e:
		_jurnal("modulele de acces nu se pot citi: %r" % (e,))
		return None


def motivReleu(gazda, port, H=None):
	"""Textul pentru releul care nu raspunde, cu cauza vazuta de om. Pe receptor (127.0.0.1) releul il da modulul de
	acces: niciun modul ales, modulul ales oprit, modulul care ruleaza fara releu pe port; altfel (alt aparat, citire
	cazuta) adresa si portul."""
	if gazda in ("127.0.0.1", "localhost", "::1"):
		m = _moduleAcces(H)
		if m is not None:
			if m["ruleaza"]:
				return _t(TEXT_RELEU_MODUL_FARA_RELEU) % (m["ruleaza"][0], port)
			if m["alese"]:
				return _t(TEXT_RELEU_FARA_MODUL) % m["alese"][0]
			return _t(TEXT_RELEU_NICIUN_MODUL)
	return _t(TEXT_RELEU_OPRIT) % (gazda, port)


def stare(r=None, H=None):
	"""Starea Stream Relay pentru ecranul setarilor si web: {"canale": numarul canalelor din lista, "numai_citire",
	"gazda", "port", "permis" (adresa se foloseste), "asculta" (releul raspunde; None cand lista e goala: nu se
	verifica), "motiv" (de ce nu raspunde, "" altfel), "linii": randurile pentru om}."""
	r = r or releu()
	H = H or getattr(r, "_module", None)
	chei = r.chei()
	gazda, port, _intarziere = r.configurare()
	gazda = "127.0.0.1" if gazda == "localhost" else gazda
	rez = {"canale": len(chei), "numai_citire": r.numaiCitire, "gazda": gazda, "port": port,
		"permis": gazda in GAZDE_LOCALE or releuInRetea(gazda), "asculta": None, "motiv": ""}
	linii = []
	if r.numaiCitire:
		linii.append(_t(TEXT_NUMAI_CITIRE))
	if chei:
		linii.append(_t(TEXT_LISTA) % (ngettext("%d canal", "%d canale", len(chei)) % len(chei)))
		rez["asculta"] = r.asculta(gazda, port)
		if rez["asculta"]:
			linii.append(_t(TEXT_RELEU_MERGE) % (gazda, port))
		else:
			rez["motiv"] = motivReleu(gazda, port, H)
			linii.append(rez["motiv"])
	else:
		linii.append(_t(TEXT_LISTA_GOALA))
	linii.append(_t(TEXT_DE_UNDE))
	rez["linii"] = linii
	return rez


# ultima stare ceruta de ecranul setarilor: (ora, randurile); ecranul o cere la fiecare rand ales si la 3 s, iar un releu
# pe alt aparat care nu raspunde ar tine firul enigma2 TERMEN_VERIFICARE_S la fiecare cerere
_STARE_RECENTA = [None, []]
STARE_RECENTA_S = 2.5


def liniiStare(ceas=time.time):
	"""Randurile starii pentru ecranul setarilor Stream Relay (atributul hdsStare al setarilor, Screens/Setup.py) si
	pagina lui web; aceleasi randuri cel mult STARE_RECENTA_S."""
	acum = ceas()
	cand, linii = _STARE_RECENTA
	if cand is not None and 0 <= acum - cand < STARE_RECENTA_S:
		return list(linii)
	try:
		linii = stare()["linii"]
	except Exception as e:
		_jurnal("starea: %r" % (e,))
		linii = []
	_STARE_RECENTA[0], _STARE_RECENTA[1] = acum, list(linii)
	return linii


def _anuntaPeTelevizor(text):
	try:
		from Tools import Notifications
		from Screens.MessageBox import MessageBox
		Notifications.AddPopup(text, MessageBox.TYPE_INFO, TIMP_MESAJ_S, "HdsStreamRelay")
	except Exception as e:
		_jurnal("mesajul de pe televizor: %r" % (e,))


# ------------------------------------------------------------------ lista

class Releu(object):
	"""Lista canalelor si legatura la zap. Un singur obiect pe proces (releu())."""

	def __init__(self, fisier=FISIER, extensii=None, configurare=None, anunta=None, module=None, ceas=None):
		self.fisier = fisier
		self._extensii = extensii      # lista Navigation.playServiceExtensions (probele dau una a lor)
		self._configurare = configurare  # (gazda, port, intarziere_ms) pentru probe; altfel din config
		self._anunta = anunta or _anuntaPeTelevizor   # mesajul de pe televizor (probele dau o functie a lor)
		self._module = module          # Components.HdsModuleAcces (probele dau unul fals)
		self._ceasMesaj = ceas or time.time
		self._ultimulMesaj = (None, 0.0)  # (textul, ora) ultimului mesaj despre releul care nu raspunde
		self._chei = []
		self._amprenta = None
		self._citit = False
		self.numaiCitire = False
		self._lacat = threading.Lock()
		self._prinReleu = False         # serviciul pornit de ultimul zap a mers prin releu
		self._ceas = None
		self._asteapta = None           # (nav, playref, text releu) pentru pornirea dupa intarziere

	# ---- fisierul
	def _amprentaFisier(self):
		try:
			s = os.stat(self.fisier)
		except OSError as e:
			if e.errno in (errno.ENOENT, errno.ENOTDIR):
				return "lipseste"
			return None
		return (s.st_size, s.st_mtime_ns, s.st_ino)

	def _citeste(self, fortat=False):
		amprenta = self._amprentaFisier()
		if self._citit and not fortat and amprenta == self._amprenta:
			return
		if amprenta == "lipseste":
			self._chei, self._amprenta, self._citit, self.numaiCitire = [], amprenta, True, False
			return
		try:
			if amprenta is None or amprenta[0] > MAX_OCTETI:
				raise IOError("fisierul nu se poate citi sau e prea mare")
			with open(self.fisier, "r", encoding="utf-8", errors="replace") as f:
				randuri = f.read().splitlines()
		except (IOError, OSError) as e:
			# numai citire: nu se scrie peste un fisier necitit (lista din memorie ramane)
			_jurnal("lista nu se poate citi (%s): ramane cea de dinainte, fara scriere" % e)
			self.numaiCitire, self._citit = True, True
			self._amprenta = amprenta
			return
		chei = []
		vazute = set()
		for r in randuri:
			k = cheie(r.strip())
			if k and k not in vazute and len(chei) < MAX_CANALE:
				vazute.add(k)
				chei.append(k)
		self._chei, self._amprenta, self._citit, self.numaiCitire = chei, amprenta, True, False

	def _scrie(self, chei):
		if self.numaiCitire:
			return False
		nou = self.fisier + ".nou"
		try:
			if not chei:
				try:
					os.remove(self.fisier)
				except OSError as e:
					if e.errno != errno.ENOENT:
						raise
			else:
				with open(nou, "w", encoding="utf-8") as f:
					f.write("".join(k + "\n" for k in chei))
					f.flush()
					os.fsync(f.fileno())
				os.replace(nou, self.fisier)
		except (IOError, OSError) as e:
			_jurnal("lista nu s-a scris: %s" % e)
			try:
				os.remove(nou)
			except OSError:
				pass
			return False
		self._chei = list(chei)
		self._amprenta = self._amprentaFisier()
		return True

	# ---- citirea listei
	def chei(self):
		with self._lacat:
			self._citeste()
			return list(self._chei)

	@property
	def data(self):
		return self.chei()

	def getData(self):
		return self.chei()

	def checkService(self, ref):
		k = cheie(ref)
		return bool(k) and k in self.chei()

	def reload(self):
		with self._lacat:
			self._citeste(fortat=True)
			gol = not self._chei
		self.actualizeazaLegatura(gol)

	# ---- schimbarea listei
	def pune(self, ref, vrea):
		"""Canalul in lista (vrea=True) sau scos. -> (reusit, in_lista). Nu atinge redarea."""
		k = cheie(ref)
		if not k:
			return False, False
		with self._lacat:
			self._citeste()
			chei = list(self._chei)
			if vrea and k not in chei:
				if len(chei) >= MAX_CANALE:
					return False, False
				chei.append(k)
			elif not vrea and k in chei:
				chei.remove(k)
			else:
				return True, vrea
			if not self._scrie(chei):
				return False, k in self._chei
			gol = not self._chei
		self.actualizeazaLegatura(gol)
		return True, vrea

	def toggle(self, nav, service):
		"""Pune sau scoate canalul; daca ruleaza acum pe televizor, il porneste din nou, ca schimbarea sa se vada."""
		ok, in_lista = self.pune(service, not self.checkService(service))
		if ok and nav is not None:
			try:
				acum = nav.getCurrentlyPlayingServiceReference()
				if acum is not None and cheie(acum) == cheie(service):
					nav.playService(acum, forceRestart=True)
			except Exception as e:
				_jurnal("canalul nu s-a pornit din nou: %s" % e)
		return ok, in_lista

	# ---- setarile
	def configurare(self):
		"""(gazda, port, intarziere_ms) din setari."""
		if self._configurare is not None:
			return self._configurare
		try:
			from Components.config import config
			m = config.misc
			gazda = gazdaDinAdresa(m.acces_streamrelay_url.value) or "127.0.0.1"
			port = int(m.acces_streamrelay_port.value or PORT_IMPLICIT)
			intarziere = max(0, int(m.acces_streamrelay_delay.value or 0))
		except Exception as e:
			_jurnal("setarile: %s" % e)
			return "127.0.0.1", PORT_IMPLICIT, 0
		if not 0 < port < 65536:
			port = PORT_IMPLICIT
		return gazda, port, min(intarziere, 5000)

	def asculta(self, gazda, port):
		"""True daca un program asculta la gazda:port (releul pornit)."""
		s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		s.settimeout(TERMEN_VERIFICARE_S)
		try:
			s.connect((gazda, port))
			return True
		except (OSError, socket.timeout):
			return False
		finally:
			s.close()

	def textRedare(self, ref, nume=None):
		"""Textul referintei releului pentru un canal din lista, sau None (nu e in lista, releul nu e pe receptor)."""
		k = cheie(ref)
		if not k or k not in self.chei():
			return None
		gazda, port, _intarziere = self.configurare()
		if gazda not in GAZDE_LOCALE and not releuInRetea(gazda):
			_jurnal("adresa releului %s nu e pe receptor (nici in reteaua de acasa permisa): canalul porneste direct" % gazda)
			return None
		if nume is None:
			nume = _numeCanal(ref)
		return textReleu(k, "127.0.0.1" if gazda == "localhost" else gazda, port, nume)

	def streamrelayChecker(self, playref):
		"""Pentru pluginuri: (referinta releului, True) pentru un canal din lista, altfel (playref, False)."""
		text = self.textRedare(playref)
		if text is None:
			return playref, False
		from enigma import eServiceReference
		return eServiceReference(text), True

	# ---- legatura la zap
	def _lista(self):
		if self._extensii is not None:
			return self._extensii
		try:
			from Navigation import Navigation
		except Exception:
			return None
		return Navigation.playServiceExtensions

	def actualizeazaLegatura(self, gol=None):
		"""Legatura la zap numai cat lista are canale."""
		lista = self._lista()
		if not isinstance(lista, list):
			return
		if gol is None:
			gol = not self.chei()
		if gol:
			while laZap in lista:
				lista.remove(laZap)
			self._prinReleu = False
		elif laZap not in lista:
			lista.append(laZap)

	def _peZap(self, nav, playref):
		"""Extensia de zap: (playref, asincron) sau playref neschimbat."""
		vechi, self._prinReleu = self._prinReleu, False
		self._asteapta = None
		text = self.textRedare(playref)
		if text is None:
			return playref
		gazda, port, intarziere = self.configurare()
		if not self.asculta("127.0.0.1" if gazda == "localhost" else gazda, port):
			_jurnal("releul nu raspunde la %s:%d: canalul porneste direct" % (gazda, port))
			self._mesajReleuOprit("127.0.0.1" if gazda == "localhost" else gazda, port)
			return playref
		if vechi and intarziere > 0:
			self._asteapta = (nav, playref, text)
			self._pornesteCeas(intarziere)
			return playref, True
		if self._reda(nav, text):
			self._prinReleu = True
			return playref, True
		return playref

	def _mesajReleuOprit(self, gazda, port):
		"""Pe televizor, de ce canalul din lista porneste fara releu (motivReleu); acelasi motiv se arata din nou numai
		dupa REPETARE_MESAJ_S, ca zap-urile prin lista sa nu-l aduca la fiecare canal. Nicio eroare nu opreste zap-ul."""
		try:
			motiv = motivReleu(gazda, port, self._module)
			acum = self._ceasMesaj()
			vechi, cand = self._ultimulMesaj
			if motiv == vechi and 0 <= acum - cand < REPETARE_MESAJ_S:
				return
			self._ultimulMesaj = (motiv, acum)
			self._anunta(motiv + " " + _t(TEXT_PORNESTE_DIRECT))
		except Exception as e:
			_jurnal("mesajul releului: %r" % (e,))

	def _reda(self, nav, text):
		from enigma import eServiceReference
		pnav = getattr(nav, "pnav", None)
		if pnav is None:
			return False
		rez = pnav.playService(eServiceReference(text))
		if rez:
			_jurnal("playerul nu porneste prin releu (%s): canalul porneste direct" % rez)
			return False
		return True

	def _pornesteCeas(self, ms):
		if self._ceas is None:
			from enigma import eTimer
			self._ceas = eTimer()
			self._ceas.callback.append(self._dupaIntarziere)
		self._ceas.start(ms, True)

	def _dupaIntarziere(self):
		a, self._asteapta = self._asteapta, None
		if a is None:
			return
		nav, playref, text = a
		# alt zap intre timp: nimic
		acum = nav.getCurrentlyPlayingServiceReference()
		if acum is None or cheie(acum) != cheie(playref):
			return
		if self._reda(nav, text):
			self._prinReleu = True
		else:
			_pornesteDirect(nav, playref)


def _pornesteDirect(nav, playref):
	"""Dupa o pornire prin releu cazuta: canalul direct, fara extensii (playerul de baza)."""
	try:
		nav.pnav.playService(playref)
	except Exception as e:
		_jurnal("canalul nu a pornit: %s" % e)


def _numeCanal(ref):
	try:
		from ServiceReference import ServiceReference
		return ServiceReference(ref).getServiceName() or ""
	except Exception:
		return ""


_RELEU = []


def releu():
	"""Obiectul unic al listei (facut la prima cerere)."""
	if not _RELEU:
		_RELEU.append(Releu())
	return _RELEU[0]


def laZap(nav, playref, event, infobar):
	"""Navigation.playServiceExtensions: pusa numai cat lista are canale."""
	return releu()._peZap(nav, playref)


def porneste():
	"""Din mytest.py, numai cand fisierul listei exista: legatura la zap daca lista are canale."""
	releu().actualizeazaLegatura()


def potrivit(ref):
	"""True daca `ref` e un canal care poate intra in Stream Relay (meniul listei, web)."""
	return cheie(ref) is not None
