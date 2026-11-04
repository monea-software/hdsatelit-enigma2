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
#  - daca nimic nu asculta la adresa releului (releul oprit), canalul porneste direct, ca fara Stream Relay;
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
# Partea de sus a fisierului nu importa nimic din enigma2 (probele de pe PC); legaturile cu enigma2 au importuri tarzii.

import errno
import os
import socket
import threading

FISIER = "/etc/enigma2/whitelist_streamrelay"
PORT_IMPLICIT = 17999
GAZDE_LOCALE = ("127.0.0.1", "localhost")
TERMEN_VERIFICARE_S = 0.3        # cat asteapta verificarea ca releul asculta (pe 127.0.0.1 raspunsul e pe loc)
MAX_CANALE = 2000
MAX_OCTETI = 256 * 1024
# steagurile referintei care nu sunt canale: dosar, coborare, marcaj (eServiceReference)
_FARA_CANAL = 1 | 2 | 64


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


# ------------------------------------------------------------------ lista

class Releu(object):
	"""Lista canalelor si legatura la zap. Un singur obiect pe proces (releu())."""

	def __init__(self, fisier=FISIER, extensii=None, configurare=None):
		self.fisier = fisier
		self._extensii = extensii      # lista Navigation.playServiceExtensions (probele dau una a lor)
		self._configurare = configurare  # (gazda, port, intarziere_ms) pentru probe; altfel din config
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
			return playref
		if vechi and intarziere > 0:
			self._asteapta = (nav, playref, text)
			self._pornesteCeas(intarziere)
			return playref, True
		if self._reda(nav, text):
			self._prinReleu = True
			return playref, True
		return playref

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
