# Modificat de moneasoftware.com si hdsatelit.com, 2026
from enigma import eServiceCenter, eServiceReference, pNavigation, getBestPlayableServiceReference, iPlayableService
from Components.ParentalControl import parentalControl
from Tools.BoundFunction import boundFunction
from Tools.DreamboxHardware import setFPWakeuptime, getFPWakeuptime, getFPWasTimerWakeup, clearFPWasTimerWakeup
from time import time, monotonic as _monoton
import RecordTimer
import SleepTimer
import Screens.Standby
import NavigationInstance
import ServiceReference
import sys
import threading

# masurarea zap-ului (Components/HdsMasuraZap.py): pasii lui playService si fiecare ascultator, cateva secunde dupa
# fiecare zap, scrisi intr-un fisier din /tmp; fara modul (probele de pe PC), nimic
try:
	from Components.HdsMasuraZap import masura as _masura
except Exception:
	_masura = None

# fluxurile de pe internet (4097, 5001, 5002: Radio online, IPTV) in hds-zap.log, pornirea si oprirea cu motivul
# (Components/HdsJurnalZapFlux.py; TODO 12.11 20:36); fara modul (probele de pe PC), nimic
try:
	from Components.HdsJurnalZapFlux import eveniment as _jurnalFlux
except Exception:
	_jurnalFlux = None

# primul canal din tuner dupa un player (flux de pe internet, film) cu sunet si fara imagine: pornit din nou singur, o data
# (Components/HdsImagineDupaPlayer.py; AX HD51, forum 676); fara modul (probele de pe PC), nimic
try:
	from Components.HdsImagineDupaPlayer import eveniment as _imagineDupaPlayer
except Exception:
	_imagineDupaPlayer = None

# ce a spus driverul la pornire ramane pentru pluginuri (Tools/StbHardware.py); fara modul (probele de pe PC), nimic
try:
	from Tools.StbHardware import rememberFPWasTimerWakeup
except ImportError:
	rememberFPWasTimerWakeup = lambda wasTimerWakeup: None

# acelasi serviciu cerut din nou dupa o acordare cazuta (Navigation._hdsReiaCazut) porneste din nou cel mult o data la
# atatea secunde
REIA_MIN_S = 1.0

# IPF1 (0.7.9, ZGEMMA H8.2H Plus): evBuffering (GST_MESSAGE_BUFFERING din servicemp3, la fiecare schimbare a tamponului) vine la IPTV de
# 25-1000 de ori pe secunda (masurat pe receptor cu un contor aici: 992/s pe |RX| Cute Baby Animals, 4 Mb/s). Fiecare trecea prin
# toti ascultatorii (Navigation.event, ServiceEventTracker, jurnalul fluxului): 0,7-1 s din fiecare secunda a firului principal,
# deci tastele, pagina web si bataia paznicului asteptau 4-120 s (paznicul a repornit interfata dupa 125 s fara bataie). Acum
# ajunge la ascultatori cel mult un evBuffering la RAR_TAMPON_S; cele dintre ele se aduna intr-unul singur, trimis la sfarsitul
# ferestrei (ascultatorii citesc starea tamponului din serviciu, deci il vad pe ultimul). Celelalte evenimente trec ca inainte.
RAR_TAMPON_S = 0.5  # Eduard 23.11.2026: 2 pe secunda (IPF1 pusese 5)
_EV_TAMPON = getattr(iPlayableService, "evBuffering", None)
_EV_SERVICIU_NOU = tuple(e for e in (getattr(iPlayableService, "evStart", None), getattr(iPlayableService, "evEnd", None)) if e is not None)

# TODO: remove pNavgation, eNavigation and rewrite this stuff in python.
class Navigation:
	# Punctele de extensie ale zap-ului si ale inregistrarii (atribute de clasa; Hds/DabT2 pune aici DAB+ si DVB-T2).
	# playServiceExtensions: f(nav, playref, event, infobar) -> (playref, asincron) sau numai playref. Se cheama dupa
	# oprirea serviciului vechi (tunerul si playerul sunt liberi), inainte de pornirea playerului. asincron=True: extensia
	# porneste singura serviciul mai tarziu (nav.playService(ref, forceRestart=True)), deci playerul nu porneste acum,
	# iar getCurrentlyPlayingServiceReference() da referinta ceruta. Prima extensie care schimba referinta sau o ia
	# asincron le opreste pe celelalte. O extensie care arunca exceptie e sarita (un rand in jurnal), zap-ul merge.
	# recordServiceExtensions: f(nav, ref) -> ref (None = neschimbata), inainte de pnav.recordService; in cadrul care
	# le cheama variabila locala `simulate` spune daca e doar o verificare.
	playServiceExtensions = []
	recordServiceExtensions = []
	# playServiceUltima: f(nav, playref, event, infobar), ca extensiile, chemata ULTIMA, numai cand nicio extensie n-a
	# schimbat referinta si n-a luat-o asincron (transmisia in browser, releele DAB+ / DVB-T2 si fluxurile 8001 cerute din
	# retea si-au lasat deja tunerul in extensiile lor). O pune numai tunerul de rezerva din retea
	# (Components/HdsTunerRezerva.py), cat e ales; None = nimic.
	playServiceUltima = None
	# grupFaraTuner: f(nav, grup, liber, inregistrare), chemate pe rand (celMaiBunDinGrup) numai cand niciuna dintre
	# alternativele unui grup n-are tuner si nu e o verificare (simulate). O extensie poate elibera tunere, oprindu-se cand
	# liber() spune ca o alternativa are tuner; inregistrare: False la zap, True la o inregistrare (televizorul ruleaza
	# mai departe). Prima care elibereaza un tuner le opreste pe celelalte. Ordinea: cele care isi dau oricum tunerul
	# canalului ales, puse la inceput: releele DAB+ / DVB-T2 (Hds/DabT2/pornire.py), Stream Relay
	# (Components/HdsStreamRelay.py) si cautarea DVB-T2 / DAB+ prin satelit care tine tunerul pana la alegere
	# (Screens/ScanerSatelit.py); apoi fluxurile 8001 cerute din retea (Hds/DabT2/server8001.py), transmisia din browser (Components/HdsTransmisie.py)
	# si transcodarea (HdsWebControl/flux_transcodare_web.py), puse la coada. Alternativele DVB: nav.alternativeDvb(grup).
	grupFaraTuner = []
	# grupFaraTunerUltima: f(nav, grup) -> alternativa sau None, chemata ULTIMA, numai la zap, cand nici dupa extensiile de
	# mai sus nu e nicio alternativa libera: alternativa pe care o reda altfel (playServiceUltima o ia apoi, ca la orice
	# canal). O pune numai tunerul de rezerva din retea (Components/HdsTunerRezerva.py, dupa prioritatea tipurilor de
	# tuner), cat e ales; None = nimic.
	grupFaraTunerUltima = None
	# hdsRefDinainteDeZap: serviciul redat inainte de zap, pus de _extensiiZap numai cat ruleaza extensiile (oprirea lui
	# trimite evEnd, care goleste currentlyPlayingServiceReference): asa afla o extensie de pe ce canal pleaca televizorul
	# (Hds/DabT2/server8001.la_zap: sesiunile releului de pe receptor ale canalului vechi). None in afara extensiilor.
	hdsRefDinainteDeZap = None
	# hdsCazutLa: ora (ceasul monoton) la care acordarea serviciului redat a cazut (evTuneFailed: tuner ocupat, fara semnal,
	# fara PAT/PMT), fara evTunedIn / evUpdatedInfo dupa ea, deci redarea n-a pornit; None altfel. Cat e pusa, cererea de a
	# porni acelasi serviciu (OK in lista de canale, zap din web) il porneste din nou, nu se ignora (_hdsReiaCazut).
	hdsCazutLa = None
	_hdsReluatLa = None

	def __init__(self, nextRecordTimerAfterEventActionAuto=False):
		if NavigationInstance.instance is not None:
			raise NavigationInstance.instance
		
		NavigationInstance.instance = self
		self.ServiceHandler = eServiceCenter.getInstance()
		# pluginurile straine (M3UIPTV) citesc canalul cerut la ultimul zap, inainte ca un plugin sa-l inlocuiasca cu altul
		self.originalPlayingServiceReference = None
		
		import Navigation as Nav
		Nav.navcore = self
		
		self.pnav = pNavigation()
		self._tamponLa = None        # cand a ajuns ultimul evBuffering la ascultatori (RAR_TAMPON_S)
		self._tamponCeas = None      # eTimer: evBuffering amanat ajunge dupa fereastra
		self._tamponAmanat = False
		self.pnav.m_event.get().append(self.dispatchEvent)
		self.pnav.m_record_event.get().append(self.dispatchRecordEvent)
		self.event = [ ]
		self.record_event = [ ]
		self.currentlyPlayingServiceReference = None
		self.currentlyPlayingService = None
		self.RecordTimer = RecordTimer.RecordTimer()
		wasTimerWakeup = getFPWasTimerWakeup()
		rememberFPWasTimerWakeup(wasTimerWakeup)
		if wasTimerWakeup:
			clearFPWasTimerWakeup()
			if getFPWasTimerWakeup(): # sanity check to detect if the FP driver is working correct!
				print("buggy fp driver detected!!! please update drivers.... ignore timer wakeup!")
			elif nextRecordTimerAfterEventActionAuto and (len(self.getRecordings()) or abs(self.RecordTimer.getNextRecordingTime() - time()) <= 360):
				if not Screens.Standby.inTryQuitMainloop: # not a shutdown messagebox is open
					RecordTimer.RecordTimerEntry.TryQuitMainloop(False) # start shutdown handling
		self.SleepTimer = SleepTimer.SleepTimer()
		# tunerul de rezerva din retea: legatura la zap, daca e ales (setarile se fac inainte de navigatie)
		try:
			from Components import HdsTunerRezerva
			HdsTunerRezerva.leagaZap(Navigation)
			HdsTunerRezerva.leagaEvenimente(self)
		except Exception as e:
			print("[Navigation] tunerul de rezerva:", e)

	def dispatchEvent(self, i):
		if i == _EV_TAMPON and _EV_TAMPON is not None:
			if self._tamponAmana():
				return
		elif i in _EV_SERVICIU_NOU:
			# alt serviciu (sau niciunul): evBuffering amanat al celui vechi nu mai ajunge, iar primul al celui nou trece pe loc
			if self._tamponAmanat:
				self._tamponCeas.stop()
				self._tamponAmanat = False
			self._tamponLa = None
		self._dispatch(i)

	def _tamponAmana(self):
		"""True cand evBuffering asteapta (RAR_TAMPON_S); unul singur ajunge la sfarsitul ferestrei, cu starea de atunci."""
		acum = _monoton()
		if self._tamponLa is None or acum - self._tamponLa >= RAR_TAMPON_S:
			self._tamponLa = acum
			return False
		if not self._tamponAmanat:
			try:
				if self._tamponCeas is None:
					from enigma import eTimer
					self._tamponCeas = eTimer()
					self._tamponCeas.callback.append(self._tamponDupa)
				self._tamponCeas.start(max(1, int((self._tamponLa + RAR_TAMPON_S - acum) * 1000)), True)
				self._tamponAmanat = True
			except Exception as e:
				print("[Navigation] evBuffering amanat:", e)
				return False
		return True

	def _tamponDupa(self):
		self._tamponAmanat = False
		self._tamponLa = _monoton()
		self._dispatch(_EV_TAMPON)

	def _dispatch(self, i):
		# hdsCazutLa dupa evenimentul serviciului redat. La un canal pornit pe un tuner ocupat (allocate Channel: res -6)
		# evTuneFailed vine chiar din pnav.playService, dupa evStart; dupa o acordare buna vin evTunedIn si, cu PMT-ul,
		# evUpdatedInfo
		P = iPlayableService
		if i == getattr(P, "evTuneFailed", None):
			self.hdsCazutLa = _monoton()
		elif i in (getattr(P, "evTunedIn", None), getattr(P, "evUpdatedInfo", None), getattr(P, "evEnd", None)):
			self.hdsCazutLa = None
		m = _masura
		# un plugin extern cazut intr-un ascultator nu mai opreste ceilalti ascultatori (HdsPluginExtern.ascultatorCazut)
		if m is not None and m.activ():
			t = _monoton()
			for x in self.event:
				a = _monoton()
				try:
					x(i)
				except Exception:
					if not _pluginCazut(x, i):
						raise
				m.ascultator(i, x, _monoton() - a)
			m.eveniment(i, t, _monoton() - t)
		else:
			for x in self.event:
				try:
					x(i)
				except Exception:
					if not _pluginCazut(x, i):
						raise
		if _jurnalFlux is not None:
			_jurnalFlux(self, i)
		if _imagineDupaPlayer is not None:
			_imagineDupaPlayer(self, i)
		if i == iPlayableService.evEnd:
			self.currentlyPlayingServiceReference = None
			self.currentlyPlayingService = None

	def dispatchRecordEvent(self, rec_service, event):
#		print "record_event", rec_service, event
		for x in self.record_event:
			x(rec_service, event)

	def hdsAcordareCazuta(self):
		"""True cand acordarea serviciului redat a cazut si redarea n-a pornit (hdsCazutLa): lista de canale porneste
		atunci din nou canalul ales chiar daca e cel care ruleaza (Screens/ChannelSelection.zap)."""
		return self.hdsCazutLa is not None

	def _hdsReiaCazut(self):
		"""Cererea de a porni serviciul care ruleaza deja se ignora, ca pana acum, afara de cazul in care acordarea lui a
		cazut (hdsCazutLa): atunci porneste din nou (OK pe canalul ramas negru dupa un tuner ocupat sau o acordare fara
		semnal), cel mult o data la REIA_MIN_S, ca un ascultator care cere acelasi canal la fiecare cadere sa nu-l
		porneasca in bucla. -> True cand porneste din nou (forceRestart)."""
		acum = _monoton()
		if self.hdsCazutLa is None or (self._hdsReluatLa is not None and acum - self._hdsReluatLa < REIA_MIN_S):
			return False
		self._hdsReluatLa = acum
		self.hdsCazutLa = None
		print("[Navigation] acordarea serviciului care ruleaza a cazut: il pornesc din nou")
		return True

	def playService(self, ref, checkParentalControl = True, forceRestart = False, adjust = True):
		# O repetare cat resolverul lucreaza nu porneste aceeasi cerere de doua ori.
		if ref and not forceRestart and ref == getattr(self, "_hdsChannelZapCerere", None):
			return 0
		self._hdsChannelZapCerere = None
		runner = getattr(self, "_hdsChannelZapRunner", None)
		if runner is not None:
			runner.anuleaza()
		# Invalideaza inlocuirea intarziata si dupa A -> B -> A sau reincercare.
		self.hdsGeneratieZap = getattr(self, "hdsGeneratieZap", 0) + 1
		# Keep only origin metadata across delayed starts, never caller frames.
		from sys import modules
		radio = modules.get("Components.HdsRadioMeniu")
		origine = getattr(radio, "origine_redare_radio", None)
		self._hdsRadioOrigine = None
		if origine is not None:
			try:
				self._hdsRadioOrigine = (self.hdsGeneratieZap, origine(self))
			except Exception:
				pass
		# MerlinMusicPlayer cere adjust=False. Zap-ul nostru nu muta selectia listei de canale,
		# argumentul este acceptat fara o actiune suplimentara asupra listei.
		self.originalPlayingServiceReference = ref
		m = _masura
		oldref = self.currentlyPlayingServiceReference
		if m is None or not ref or (oldref and ref == oldref and not forceRestart):
			return self._playService(ref, checkParentalControl, forceRestart)
		m.incepe(_refText(ref))
		t = _monoton()
		try:
			return self._playService(ref, checkParentalControl, forceRestart)
		finally:
			m.pas("playService", t, _monoton() - t)

	def _playService(self, ref, checkParentalControl, forceRestart):
		oldref = self.currentlyPlayingServiceReference
		redirectionat = getattr(self, "_hdsChannelZapRedirectionat", None)
		if ref and oldref and not forceRestart and (ref == oldref or (redirectionat and ref == redirectionat[0] and
				oldref == redirectionat[1])) and self._hdsReiaCazut():
			forceRestart = True
		if ref and oldref and redirectionat and not forceRestart and ref == redirectionat[0] and oldref == redirectionat[1]:
			return 0
		if ref and oldref and ref == oldref and not forceRestart:
			print("ignore request to play already running service(1)")
			return 0
		# adresa unui flux poate avea cont si parola: in jurnal numai referinta, fara cale
		print("playing", ref and (":".join(ref.toString().split(":")[:10]) + ":[flux]" if "://" in ref.getPath() else ref.toString()))
		if ref is None:
			self.stopService()
			return 0
		if not checkParentalControl or parentalControl.isServicePlayable(ref, boundFunction(self.playService, checkParentalControl = False)):
			if ref.flags & eServiceReference.isGroup:
				if not oldref:
					oldref = eServiceReference()
				playref = self.celMaiBunDinGrup(ref, oldref)
				print("playref", playref)
				if playref and oldref and playref == oldref and not forceRestart and self._hdsReiaCazut():
					forceRestart = True
				if playref and oldref and playref == oldref and not forceRestart:
					print("ignore request to play already running service(2)")
					return 0
				if not playref or (checkParentalControl and not parentalControl.isServicePlayable(playref, boundFunction(self.playService, checkParentalControl = False))):
					self.stopService()
					return 0
			else:
				playref = ref
			rez = self._pluginuriChannelZap(ref, playref)
			if rez is not None:
				return rez
			return self._redaChannelZap(ref, playref)
		else:
			self.stopService()
		return 1

	def _redaChannelZap(self, ref, playref, redirectionat=False, generatie=None):
		extensii = bool(self.pnav and (Navigation.playServiceExtensions or Navigation.playServiceUltima))
		if extensii:
			playref, asincron = self._extensiiZap(playref)
			if asincron or (generatie is not None and generatie != self.hdsGeneratieZap):
				return 0
		if self.pnav:
			t = _monoton()
			self.hdsCazutLa = None      # o acordare noua; evTuneFailed de acum il pune din nou
			rez = self.pnav.playService(playref)
			if _masura is not None:
				_masura.pas("pnav.playService", t, _monoton() - t)
			if generatie is not None and generatie != self.hdsGeneratieZap:
				return 0
			if not rez:
				self.currentlyPlayingServiceReference = playref
				self._hdsChannelZapRedirectionat = (ref, playref) if redirectionat else None
				self._hdsNumarCanal(ref)
				return 0
		if extensii:
			self.currentlyPlayingServiceReference = None
		return 1

	def _pluginuriChannelZap(self, ref, service):
		"""Resolver pe fir separat; referintele si playerul raman pe principal."""
		try:
			from Components.PluginComponent import plugins
			from Plugins.Plugin import PluginDescriptor
			ascultatori = plugins.getPlugins(PluginDescriptor.WHERE_CHANNEL_ZAP)
		except ImportError:
			return None
		if not ascultatori:
			return None
		from Components.HdsEnigmaCompat import ChannelZapRunner
		runner = getattr(self, "_hdsChannelZapRunner", None)
		if runner is None:
			runner = self._hdsChannelZapRunner = ChannelZapRunner()
		infobar = getattr(getattr(sys.modules.get("Screens.InfoBar"), "InfoBar", None), "instance", None)
		session = getattr(infobar, "session", None)
		generatie = self.hdsGeneratieZap
		self._hdsChannelZapCerere = ref

		def continua(url):
			if generatie != self.hdsGeneratieZap or not self.pnav:
				return 0
			self._hdsChannelZapCerere = None
			nou = service
			if url:
				try:
					nou = eServiceReference(service.toString())
					nou.setPath(url)
				except Exception:
					print("[Navigation] adresa resolverului de zap nu a fost acceptata")
					nou = service
			return self._redaChannelZap(ref, nou, nou is not service, generatie)

		# Descriptorul obisnuit tipareste exceptia si o trimite raportorului.
		# Aici chemam numai functia: eroarea resolverului poate contine date private.
		return runner.porneste([plugin.fnc for plugin in ascultatori], session, service, continua)

	def celMaiBunDinGrup(self, ref, ignore, simulate=False, inregistrare=False):
		"""Alternativa grupului `ref` care se poate reda acum (getBestPlayableServiceReference, cu aceleasi argumente pe
		care le dadea zap-ul, inregistrarea sau temporizatorul), sau None. Cand nu e niciuna si nu e o verificare
		(simulate), extensiile grupFaraTuner pot elibera tunere; dupa fiecare se intreaba din nou. Fara extensii, ca
		inainte. O extensie care arunca e sarita (un rand in jurnal). La zap, cand tot nu e nicio alternativa libera,
		grupFaraTunerUltima poate da alternativa pe care o reda altfel (tunerul de rezerva din retea)."""
		playref = getBestPlayableServiceReference(ref, ignore, simulate)
		ultima = None if inregistrare else Navigation.grupFaraTunerUltima
		if playref or simulate or not (Navigation.grupFaraTuner or ultima):
			return playref
		liber = lambda: bool(getBestPlayableServiceReference(ref, ignore))
		for f in list(Navigation.grupFaraTuner):
			try:
				f(self, ref, liber, inregistrare)
			except Exception as e:
				print("[Navigation] extensia grupului fara tuner %s a cazut: %s" % (getattr(f, "__name__", "?"), e))
				continue
			playref = getBestPlayableServiceReference(ref, ignore)
			if playref:
				return playref
		if ultima is not None:
			try:
				return ultima(self, ref) or None
			except Exception as e:
				print("[Navigation] ultima extensie a grupului fara tuner a cazut: %s" % e)
		return None

	def alternativeDvb(self, grup):
		"""Textele alternativelor DVB ale grupului `grup` (canalele de tip 1 fara cale, care cer un tuner), in ordinea din
		grup; [] daca lista nu se poate citi. Pentru extensiile grupFaraTuner si grupFaraTunerUltima."""
		try:
			lista = self.ServiceHandler.list(grup)
			texte = (lista and lista.getContent("S")) or []
		except Exception as e:
			print("[Navigation] alternativele grupului: %s" % e)
			return []
		rez = []
		for t in texte:
			p = str(t or "").split(":")
			if len(p) < 10 or p[0] != "1" or (len(p) > 10 and p[10].strip()):
				continue
			try:
				# fara dosare si marcaje (1, 2, 64), cu numarul serviciului (ca server8001._ref_dvb_fara_cale)
				if int(p[1] or "0") & (1 | 2 | 64) == 0 and int(p[3] or "0", 16) != 0:
					rez.append(t)
			except ValueError:
				continue
		return rez

	def _hdsNumarCanal(self, ref):
		"""Numarul canalului ca in lista de canale (HdsInfo.numar_in_lista: buchetul, reteaua de cablu, locul unei
		extensii), pus in referinta ceruta (getChannelNum), pe care temele facute pentru OE-Alliance o citesc prin
		session.CurrentService.serviceref (numarul dinaintea numelui, convertoarele ServiceNumber). Cand lista nu stie
		canalul (zap din ghid, din alt buchet) ramane numarul dat de nucleu la incarcarea buchetelor
		(eDVBDB::renumberBouquet). Niciodata o exceptie: zap-ul nu depinde de numar."""
		try:
			from Components.Converter.HdsInfo import numar_in_lista
			n = numar_in_lista(ref)
			if n > 0 and n != ref.getChannelNum():
				ref.setChannelNum(n)
		except Exception as e:
			print("[Navigation] numarul canalului:", e)

	def _extensiiZap(self, playref):
		"""Serviciul vechi se opreste, referinta curenta devine cea ceruta (extensiile care pornesc singure serviciul o
		compara mai tarziu), apoi extensiile pe rand; cat ruleaza ele, hdsRefDinainteDeZap e serviciul de dinainte.
		-> (playref, asincron)."""
		self.hdsRefDinainteDeZap = self.currentlyPlayingServiceReference
		t = _monoton()
		self.pnav.stopService()
		if _masura is not None:
			_masura.pas("oprire", t, _monoton() - t)
		self.hdsCazutLa = None
		self.currentlyPlayingServiceReference = playref
		infobar = getattr(getattr(sys.modules.get("Screens.InfoBar"), "InfoBar", None), "instance", None)
		t = _monoton()
		try:
			return self._extensiiPeRand(playref, infobar)
		finally:
			self.hdsRefDinainteDeZap = None
			if _masura is not None:
				_masura.pas("extensii", t, _monoton() - t)

	def _extensiiPeRand(self, playref, infobar):
		for f in list(Navigation.playServiceExtensions):
			try:
				rez = f(self, playref, None, infobar)
			except Exception as e:
				print("[Navigation] extensia de zap %s a cazut: %s" % (getattr(f, "__name__", "?"), e))
				continue
			if isinstance(rez, tuple):
				nou, asincron = rez[0], bool(rez[1]) if len(rez) > 1 else False
			else:
				nou, asincron = rez, False
			schimbat = nou is not None and nou is not playref and _refText(nou) != _refText(playref)
			if schimbat:
				playref = nou
				self.currentlyPlayingServiceReference = playref
			if asincron or schimbat:
				return playref, asincron
		f = Navigation.playServiceUltima
		if f is not None:
			try:
				rez = f(self, playref, None, infobar)
			except Exception as e:
				print("[Navigation] ultima extensie de zap a cazut: %s" % e)
				return playref, False
			if isinstance(rez, tuple):
				nou, asincron = rez[0], bool(rez[1]) if len(rez) > 1 else False
			else:
				nou, asincron = rez, False
			if nou is not None and nou is not playref and _refText(nou) != _refText(playref):
				playref = nou
				self.currentlyPlayingServiceReference = playref
			return playref, asincron
		return playref, False
	
	def getCurrentlyPlayingServiceReference(self):
		return self.currentlyPlayingServiceReference

	# numele din celelalte imagini; aici un grup nu se tine separat de serviciul redat
	def getCurrentlyPlayingServiceOrGroup(self):
		return self.currentlyPlayingServiceReference

	def getCurrentServiceReferenceOriginal(self):
		# ca in OE-Alliance: referinta ceruta (grupul, cu numarul canalului din buchet), pusa la inceputul lui playService,
		# deci buna si la evStart; altfel cea redata
		return self.originalPlayingServiceReference or self.currentlyPlayingServiceReference

	def wasTimerWakeup(self):
		# ce a spus driverul la pornire, retinut inainte ca __init__ sa stearga semnul (Tools/StbHardware.py)
		try:
			from Tools.StbHardware import getFPWasTimerWakeup as citita
		except ImportError:
			from Tools.DreamboxHardware import getFPWasTimerWakeup as citita
		return bool(citita())
	
	def recordService(self, ref, simulate=False):
		# EPG (0.7.7, asistenta 058499): o inregistrare simulata (EPGImport verifica asa fiecare canal din
		# rytec.channels.xml, 10.431 intr-un import; TimerSanityCheck, PiP) nu mai scrie un rand cand reuseste: randul de
		# pe fiecare canal umplea hds-interfata.log (2 MB in 9 s) si il rotea. Le numara _simulate, care scrie un singur
		# rand dupa rafala. Inregistrarea adevarata scrie referinta ca text si cand vine ca eServiceReference (inainte, numai
		# ServiceReference dadea textul; eServiceReference dadea obiectul SWIG); esecul se scrie la amandoua.
		service = None
		if isinstance(ref, ServiceReference.ServiceReference):
			ref = ref.ref
		if not simulate:
			print("recording service: %s" % _refText(ref))
		if ref:
			if ref.flags & eServiceReference.isGroup:
				ref = self.celMaiBunDinGrup(ref, eServiceReference(), simulate, True)
			if ref and Navigation.recordServiceExtensions:
				ref = self._extensiiInregistrare(ref, simulate)
			service = ref and self.pnav and self.pnav.recordService(ref, simulate)
			if simulate:
				_simulate.noteaza(service is not None)
			if service is None:
				if simulate:
					print("record returned non-zero (simulat): %s" % _refText(ref))
				else:
					print("record returned non-zero")
		return service

	def _extensiiInregistrare(self, ref, simulate):
		"""Extensiile inregistrarii, pe rand. `simulate` ramane variabila locala a acestui cadru (o extensie care cedeaza
		tunerul unei inregistrari adevarate o citeste de aici)."""
		for f in list(Navigation.recordServiceExtensions):
			try:
				rez = f(self, ref)
			except Exception as e:
				print("[Navigation] extensia de inregistrare %s a cazut: %s" % (getattr(f, "__name__", "?"), e))
				continue
			if rez is not None:
				ref = rez
		return ref

	def stopRecordService(self, service):
		ret = self.pnav and self.pnav.stopRecordService(service)
		return ret

	def getRecordings(self, simulate=False):
		return self.pnav and self.pnav.getRecordings(simulate)

	def getCurrentService(self):
		if not self.currentlyPlayingService:
			self.currentlyPlayingService = self.pnav and self.pnav.getCurrentService()
		return self.currentlyPlayingService

	def stopService(self):
		self._hdsChannelZapCerere = None
		runner = getattr(self, "_hdsChannelZapRunner", None)
		if runner is not None:
			runner.anuleaza()
		self.hdsGeneratieZap = getattr(self, "hdsGeneratieZap", 0) + 1
		print("stopService")
		if self.pnav:
			self.pnav.stopService()
		# evEnd le goleste numai daca rula un player; dupa un zap luat asincron de o extensie nu rula niciunul
		self.currentlyPlayingServiceReference = None
		self.originalPlayingServiceReference = None
		self.currentlyPlayingService = None
		self.hdsCazutLa = None

	def pause(self, p):
		return self.pnav and self.pnav.pause(p)

	def shutdown(self):
		self.RecordTimer.shutdown()
		self.ServiceHandler = None
		self.pnav = None

	def stopUserServices(self):
		self.stopService()


def _pluginCazut(ascultator, eveniment):
	"""True cand eroarea luata acum vine dintr-un plugin extern (raportata si scrisa in jurnal): bucla merge mai departe."""
	try:
		from Components.HdsPluginExtern import ascultatorCazut
	except Exception:
		return False
	return ascultatorCazut("Navigation.dispatchEvent(%d) -> %s" % (eveniment, getattr(ascultator, "__qualname__", None) or
		type(ascultator).__name__))


def _refText(ref):
	"""Textul unei referinte (eServiceReference sau sir), pentru comparatii; "" daca nu se poate citi."""
	try:
		return ref.toString()
	except Exception:
		return str(ref)


class _NumaratoareSimulate(object):
	"""Inregistrarile simulate (verificarea canalelor: EPGImport, cronometrele, PiP) numarate, cu un singur rand in jurnal
	dupa fiecare rafala (LINISTE_S secunde fara alta): cate, in cat timp, cate refuzate. EPGImport le cheama de pe firul
	lui twisted, deci numaratoarea are lacat si randul il scrie un threading.Timer (niciun eTimer facut din alt fir)."""

	LINISTE_S = 2.0
	TEXT = "[Navigation] inregistrari simulate (verificarea canalelor: EPGImport, cronometre, PiP): %d in %.1f s, %d refuzate"

	def __init__(self, ceas=None, scrie=None):
		self._ceas = ceas or _monoton
		self._scrie = scrie or print
		self._lacat = threading.Lock()
		self._fir = None
		self._goleste()

	def _goleste(self):
		self.n = 0
		self.refuzate = 0
		self.de_la = self.ultim = 0.0

	def noteaza(self, reusita):
		with self._lacat:
			acum = self._ceas()
			if not self.n:
				self.de_la = acum
			self.n += 1
			if not reusita:
				self.refuzate += 1
			self.ultim = acum
			if self._fir is None:
				self._porneste(self.LINISTE_S)

	def _porneste(self, secunde):
		try:
			fir = threading.Timer(secunde, self.verifica)
			fir.daemon = True
			fir.start()
			self._fir = fir
		except Exception:
			# fara fir (memorie, oprire): randul se scrie la urmatoarea verificare
			self._fir = None

	def verifica(self):
		"""Scrie randul cand rafala s-a terminat; altfel asteapta restul linistii. Intoarce randul scris sau None."""
		with self._lacat:
			self._fir = None
			if not self.n:
				return None
			ramas = self.LINISTE_S - (self._ceas() - self.ultim)
			if ramas > 0:
				self._porneste(ramas)
				return None
			text = self.TEXT % (self.n, max(0.0, self.ultim - self.de_la), self.refuzate)
			self._goleste()
		self._scrie(text)
		return text


_simulate = _NumaratoareSimulate()
