# Modificat de moneasoftware.com si hdsatelit.com, 2026
# Proba completa este scrisa inainte de ecranul fatal si de SIGKILL, inclusiv la importuri.
try:
	from Components.HdsPaznic import instaleazaExceptii, scrieExceptie
	instaleazaExceptii()
except Exception as e:
	print("[mytest] pastrarea exceptiei:", e)

import eConsoleImpl
import eBaseImpl
import enigma
enigma.eTimer = eBaseImpl.eTimer
enigma.eSocketNotifier = eBaseImpl.eSocketNotifier
enigma.eConsoleAppContainer = eConsoleImpl.eConsoleAppContainer
# Jurnalul obisnuit al interfetei ramane pe receptor, cu scrieri grupate.
try:
	from Tools import HdsJurnalInterfata
	HdsJurnalInterfata.porneste()
except Exception as e:
	print("[mytest] jurnalul interfetei:", type(e).__name__)

# HDSatelit: functiile mici din enigma ale altor imagini (getBoxType, checkInternetAccess...), facute in Python, pentru pluginurile
# lor (Components/HdsEnigmaCompat.py); ce exista deja nu se schimba
try:
	from Components import HdsEnigmaCompat
	HdsEnigmaCompat.completeaza(enigma)
except Exception as e:
	print("[mytest] numele enigma pentru pluginuri:", e)

# HDSatelit: stivele Python in /tmp/enigma2-stive.txt, cerute de hds-watchdog inainte de SIGTERM-ul unei interfete care nu
# mai raspunde (si la o pornire fara nicio bataie); copia ramane in /home/root/logs (enigma2-stive-*.txt): un blocaj lasa
# urma lui, nu numai lipsa bataii. Fisierul se goleste la fiecare pornire si se scrie numai la coada.
# 0.7.7: stivele tuturor firelor le scrie intai un fir al imaginii, citite din Python (Components/HdsPaznic.py,
# StiveLaCerere), la cererea paznicului pe o teava. faulthandler ramane pentru interfata care tine lacatul Python:
# SIGRTMIN+7 numai firul care primeste semnalul (firul principal), SIGRTMIN+9 toate firele (paznicul il trimite numai
# inaintea opririi, cand firul cererilor n-a putut raspunde, deci niciun alt fir nu ruleaza cod Python). Toate firele
# citite din semnal cat alt fir rula cod Python au oprit enigma2 (SIGSEGV in libpython, 1 din ~318 pe receptorul de proba).
try:
	import faulthandler
	import signal
	open("/tmp/enigma2-stive.txt", "w").close()
	_hdsStive = open("/tmp/enigma2-stive.txt", "a")
	faulthandler.register(signal.SIGRTMIN + 7, file=_hdsStive, all_threads=False, chain=False)
	faulthandler.register(signal.SIGRTMIN + 9, file=_hdsStive, all_threads=True, chain=False)
	try:
		from Components.HdsPaznic import pornesteStiveLaCerere
		pornesteStiveLaCerere(_hdsStive)
	except Exception as e:
		print("[mytest] stivele la cererea paznicului:", e)
except Exception as e:
	print("[mytest] stivele la semnal:", e)

# HDSatelit 0.7.4: la o oprire cu SIGABRT (abort: exceptie C++ neprinsa, eroare glibc) sau SIGFPE, stiva Python a tuturor
# firelor (si, cu Python 3.14, stiva C cu numele functiilor C++) in /home/root/logs/enigma2-stiva-semnal.txt; apoi semnalul merge
# la manerul de dinainte (bsod.cpp, pus inainte de mytest.py: jurnalul caderii se scrie ca pana acum). Pana acum o oprire cu
# semnalul 6 lasa numai registrele, fara functia care a chemat C++-ul (rapoartele 898941 Ustym 4K PRO si 503916 SF8008, 0.7.3).
# SIGSEGV, SIGBUS si SIGILL raman numai la bsod.cpp, neschimbate: dupa faulthandler semnalul se trimite din nou din libc, iar
# bsod.cpp ar vedea PC-ul in libc, nu in biblioteca cazuta (enigma2.sh ia din el dovada caderilor placii 2D, „hiaccel”).
# Raportul pornirii ia fisierul daca e din ultimele 10 minute (tools/hds-raport.sh). Fisierul se goleste la fiecare pornire,
# dupa ce o stiva ramasa de la caderea de dinainte e mutata in enigma2-stiva-semnal.1.txt (pe care raportul il ia la fel).
try:
	import ctypes as _hdsC
	import faulthandler
	import os as _hdsOs
	import signal as _hdsSemnal
	_hdsLibc = _hdsC.CDLL(None)
	_hdsManere = []
	for _hdsS in (_hdsSemnal.SIGSEGV, _hdsSemnal.SIGBUS, _hdsSemnal.SIGILL):
		_hdsB = _hdsC.create_string_buffer(512)		# struct sigaction (manerul bsod.cpp), tinut ca octeti
		if _hdsLibc.sigaction(int(_hdsS), None, _hdsB) != 0:
			raise OSError("sigaction %d" % int(_hdsS))
		_hdsManere.append((int(_hdsS), _hdsB))
	_hdsOs.makedirs("/home/root/logs", exist_ok=True)
	# 0.7.5: stiva scrisa la caderea de dinainte nu se mai pierde la pornirea urmatoare. Paznicul reporneste interfata in
	# cateva secunde, iar raportul trimis dupa caderile repetate gasea mereu fisierul gol (rapoartele 0.7.4 de pe Ustym 4K PRO
	# si SF8008, CER 1082): o stiva nevida se muta in enigma2-stiva-semnal.1.txt, cu ora ei, inainte de golire.
	try:
		_hdsCaleStiva = "/home/root/logs/enigma2-stiva-semnal.txt"
		if not _hdsOs.path.islink(_hdsCaleStiva) and _hdsOs.path.getsize(_hdsCaleStiva) > 0:
			_hdsOs.replace(_hdsCaleStiva, "/home/root/logs/enigma2-stiva-semnal.1.txt")
	except OSError:
		pass
	_hdsStivaSemnal = open("/home/root/logs/enigma2-stiva-semnal.txt", "w")
	faulthandler.enable(file=_hdsStivaSemnal, all_threads=True)
	for _hdsS, _hdsB in _hdsManere:
		_hdsLibc.sigaction(_hdsS, _hdsB, None)
except Exception as e:
	print("[mytest] stiva la cadere:", e)

from Tools.Profile import profile, profile_final

profile("PYTHON_START")

# HDSatelit: randul „HD Satelit <versiune> · moneasoftware.com & hdsatelit.com” peste poza de pornire, cat se
# incarca interfata (Components/HdsSemnaturaPornire.py). Pornirea nu depinde de el.
try:
	from Components import HdsSemnaturaPornire
	HdsSemnaturaPornire.arata()
except Exception as e:
	print("[mytest] semnatura de pornire:", e)

from enigma import runMainloop, eDVBDB, eTimer, quitMainloop, \
	getDesktop, ePythonConfigQuery, eAVSwitch, eServiceEvent, \
	eEPGCache
from tools import *

profile("LANGUAGE")

from Components.Language import language

# limba ghidului: limba meniului sau cea aleasa, plus limba a doua (Components/HdsLimbaEpg.py, 0.7.4); fara modul, ca inainte
try:
	from Components import HdsLimbaEpg
	HdsLimbaEpg.porneste()
except Exception as e:
	print("[mytest] limba ghidului:", type(e).__name__, e)

	def setEPGLanguage():
		print("language set to", language.getLanguage())
		eServiceEvent.setEPGLanguage(language.getLanguage())

	language.addCallback(setEPGLanguage)

from traceback import print_exc
profile("LOAD:InfoBar")
import Screens.InfoBar
from Screens.SimpleSummary import SimpleSummary

from sys import stdout, exc_info

profile("Bouquets")
eDVBDB.getInstance().reloadBouquets()

profile("ParentalControl")
from Components.ParentalControl import InitParentalControl
InitParentalControl()

profile("LOAD:Navigation")
from Navigation import Navigation

profile("LOAD:skin")
from skin import readSkin

profile("LOAD:Tools")
from Tools.Directories import InitFallbackFiles, resolveFilename, SCOPE_PLUGINS, SCOPE_CURRENT_SKIN
from Components.config import config, configfile, ConfigText, ConfigYesNo, ConfigInteger, NoSave
InitFallbackFiles()

profile("config.misc")

config.misc.radiopic = ConfigText(default = resolveFilename(SCOPE_CURRENT_SKIN, "radio.mvi"))
config.misc.isNextRecordTimerAfterEventActionAuto = ConfigYesNo(default=False)
config.misc.useTransponderTime = ConfigYesNo(default=True)
config.misc.startCounter = ConfigInteger(default=0) # number of e2 starts...
config.misc.standbyCounter = NoSave(ConfigInteger(default=0)) # number of standby
# HDSatelit: ghidul pe memoria interna (Components/HdsEpgSalvare.py), nu pe
# /hdd/epg.dat: fara stick sau disc in /media/hdd nu se scria niciodata, deci se pierdea la fiecare repornire
try:
	from Components import HdsEpgSalvare
except Exception as e:
	print("[mytest] ghidul:", e)
	HdsEpgSalvare = None
config.misc.epgcache_filename = ConfigText(default = HdsEpgSalvare.CALE if HdsEpgSalvare else "/home/root/epg.dat")
# HDSatelit 0.7.5: locul ghidului ales de om (memoria interna sau un stick/disc din /media), inainte de pluginuri,
# ca ele sa vada calea efectiva (Components/HdsEpgSalvare.py)
if HdsEpgSalvare:
	try:
		HdsEpgSalvare.creeaza_setarea(config.misc.epgcache_filename)
	except Exception as e:
		print("[mytest] locul ghidului:", e)
# HDSatelit: programul de beta testeri (Components/HdsBetaTester.py): contorul orei, intrebarea, trimiterea
try:
	from Components import HdsBetaTester
except Exception as e:
	print("[mytest] beta tester:", e)
	HdsBetaTester = None
# HDSatelit 0.7.6 (NBM): un plugin strain care deschide un ecran cand nu e niciun ecran modal (de pilda NeoBoot, chiar dupa
# ce si-a inchis fereastra) nu mai cade; ecranul se deschide dupa o clipa (Components/HdsDeschidereAmanata.py)
try:
	from Components import HdsDeschidereAmanata
except Exception as e:
	print("[mytest] deschiderea amanata:", e)
	HdsDeschidereAmanata = None

def setEPGCachePath(configElement):
	# HDSatelit: locul il alege setarea „Unde se păstrează ghidul TV” (config.misc.hds_epg_loc); prima chemare pune
	# ghidul acolo (cu mutarea celui vechi de pe /hdd/epg.dat), apoi o cale schimbata de un plugin trece in setare
	if HdsEpgSalvare and hasattr(config.misc, "hds_epg_loc"):
		HdsEpgSalvare.la_calea_ghidului(configElement)
		return
	if HdsEpgSalvare:
		HdsEpgSalvare.muta_vechiul(configElement.value)
	eEPGCache.getInstance().setCacheFile(configElement.value)


#demo code for use of standby enter leave callbacks
#def leaveStandby():
#	print "!!!!!!!!!!!!!!!!!leave standby"

#def standbyCountChanged(configElement):
#	print "!!!!!!!!!!!!!!!!!enter standby num", configElement.value
#	from Screens.Standby import inStandby
#	inStandby.onClose.append(leaveStandby)

#config.misc.standbyCounter.addNotifier(standbyCountChanged, initial_call = False)
####################################################

def useTransponderTimeChanged(configElement):
	enigma.eDVBLocalTimeHandler.getInstance().setUseDVBTime(configElement.value)
config.misc.useTransponderTime.addNotifier(useTransponderTimeChanged)

profile("Twisted")
try:
	import twisted.python.runtime
	# Pastram firele active pentru utilizatorii Twisted de la pornire.
	# e2reactor merge si daca baza fusese incarcata deja fara fire.
	twisted.python.runtime.platform.supportsThreads = lambda: True

	import e2reactor
	e2reactor.install()

	from twisted.internet import reactor

	# HDSatelit: adresa data ca text la getPage, downloadPage, putChild (pluginuri trecute de pe Python 2) se face octeti
	# (Components/HdsEnigmaCompat.py)
	try:
		from Components import HdsEnigmaCompat
		HdsEnigmaCompat.completeazaTwisted()
	except Exception as e:
		print("[mytest] twisted pentru pluginuri:", e)

	def runReactor():
		reactor.run(installSignalHandlers=False)
except ImportError:
	print("twisted not available")
	def runReactor():
		runMainloop()

profile("LOAD:Plugin")

# initialize autorun plugins and plugin menu entries
from Components.PluginComponent import plugins

profile("LOAD:Wizard")
from Screens.Wizard import wizardManager
from Screens.DefaultWizard import *
from Screens.StartWizard import *
import Screens.Rc
from Tools.BoundFunction import boundFunction
from Plugins.Plugin import PluginDescriptor

profile("misc")
had = dict()

def dump(dir, p = ""):
	if isinstance(dir, dict):
		for (entry, val) in list(dir.items()):
			dump(val, p + "(dict)/" + entry)
	if hasattr(dir, "__dict__"):
		for name, value in list(dir.__dict__.items()):
			if str(value) not in had:
				had[str(value)] = 1
				dump(value, p + "/" + str(name))
			else:
				print(p + "/" + str(name) + ":" + str(dir.__class__) + "(cycle)")
	else:
		print(p + ":" + str(dir))

# + ":" + str(dir.__class__)

# display

profile("LOAD:ScreenGlobals")
from Screens.Globals import Globals
from Screens.SessionGlobals import SessionGlobals
from Screens.Screen import Screen

profile("Screen")
Screen.global_screen = Globals()

# Session.open:
# * push current active dialog ('current_dialog') onto stack
# * call execEnd for this dialog
#   * clear in_exec flag
#   * hide screen
# * instantiate new dialog into 'current_dialog'
#   * create screens, components
#   * read, apply skin
#   * create GUI for screen
# * call execBegin for new dialog
#   * set in_exec
#   * show gui screen
#   * call components' / screen's onExecBegin
# ... screen is active, until it calls 'close'...
# Session.close:
# * assert in_exec
# * save return value
# * start deferred close handler ('onClose')
# * execEnd
#   * clear in_exec
#   * hide screen
# .. a moment later:
# Session.doClose:
# * destroy screen

class Session:
	def __init__(self, desktop = None, summary_desktop = None, navigation = None):
		self.desktop = desktop
		self.summary_desktop = summary_desktop
		self.nav = navigation
		self.delay_timer = eTimer()
		self.delay_timer.callback.append(self.processDelay)

		self.current_dialog = None

		self.dialog_stack = [ ]
		self.summary_stack = [ ]
		self.summary = None

		self.in_exec = False
		self.screen_error_count = 0
		self.last_screen_error_time = 0

		self.screen = SessionGlobals(self)

		# HDSatelit 0.7.5 (PRN): un plugin care tine pornirea (o actualizare din retea la sessionstart) intra in randul
		# pornirii din jurnalul paznicului (Components/HdsPaznic.pasPornire)
		from time import monotonic as _ceas
		for p in plugins.getPlugins(PluginDescriptor.WHERE_SESSIONSTART):
			t0 = _ceas()
			p(reason=0, session=self)
			try:
				from Components import HdsPaznic
				HdsPaznic.pasPornire("sessionstart", (p.path or "").rstrip("/").rsplit("/", 1)[-1] or p.name, _ceas() - t0)
			except Exception:
				pass

	def processDelay(self):
		try:
			self.processDelayHds()
		finally:
			# HDSatelit 0.7.4: desenul tinut de Session.close (animatia ferestrelor) merge mai departe
			if HdsAnimatiiFerestre is not None:
				HdsAnimatiiFerestre.dupaInchidere()

	def processDelayHds(self):
		# HDSatelit 0.7.7 (DLG): un ecran ajuns de doua ori in stiva (deschis inainte de garda din execDialog, de un plugin)
		# n-are callback la a doua inchidere: era AttributeError si interfata se oprea. Se trece mai departe, cu rand in jurnal,
		# iar popCurrent aduce ecranul de dedesubt, ca la o inchidere obisnuita.
		callback = getattr(self.current_dialog, "callback", None)

		retval = getattr(self.current_dialog, "returnValue", ())

		if self.current_dialog is None:
			print("[Session] inchidere fara ecran curent")
		elif self.current_dialog.isTmp:
			self.current_dialog.doClose()
#			dump(self.current_dialog)
			del self.current_dialog
		elif hasattr(self.current_dialog, "callback"):
			del self.current_dialog.callback
		else:
			print("[Session] %s inchis a doua oara (era de doua ori in stiva), merg la ecranul de dedesubt" % self.current_dialog.__class__.__name__)

		self.popCurrent()
		if callback is not None:
			callback(*retval)

	def execBegin(self, first=True, do_show = True):
		assert not self.in_exec 
		self.in_exec = True
		c = self.current_dialog

		# when this is an execbegin after a execend of a "higher" dialog,
		# popSummary already did the right thing.
		if first:
			self.pushSummary()
			summary = c.createSummary() or SimpleSummary
			self.summary = self.instantiateSummaryDialog(summary, c)
			self.summary.show()
			c.addSummary(self.summary)

		c.saveKeyboardMode()
		c.execBegin()

		# when execBegin opened a new dialog, don't bother showing the old one.
		if c == self.current_dialog and do_show:
			c.show()

	def execEnd(self, last=True):
		assert self.in_exec
		self.in_exec = False

		self.current_dialog.execEnd()
		self.current_dialog.restoreKeyboardMode()
		self.current_dialog.hide()

		if last:
			self.current_dialog.removeSummary(self.summary)
			self.popSummary()

	def handleScreenCrash(self, screen, error, tb_str):
		import time
		now = time.time()
		if now - getattr(self, "last_screen_error_time", 0) > 30:
			self.screen_error_count = 0
			self.screen_error_tema = False
		self.screen_error_count = getattr(self, "screen_error_count", 0) + 1
		# cu o tema externa: a trecut eroarea prin fisierele ei? (numai atunci o retrag cele trei erori, Components/HdsSkinuri.py)
		try:
			from Components import HdsSkinuri
			if HdsSkinuri.eroareDinTema(tb_str):
				self.screen_error_tema = True
		except Exception as e:
			print("[HDS-SAFE] tema in stiva:", e)
		self.last_screen_error_time = now

		# Salveaza raportul de crash pe disc
		# HDSatelit: in /home/root/logs, ca main/bsod.cpp (CRASH_LOG_DIR); /media/hdd e in RAM
		# (tmpfs de 64 KB) pe Viper 4K V20. hds-watchdog.py pastreaza numai ultimele 5 jurnale.
		try:
			import os as _os
			try:
				_os.makedirs("/home/root/logs", exist_ok=True)
			except OSError:
				pass
			crash_path = "/home/root/logs/enigma2_crash_%d.log" % int(now)
			with open(crash_path, "w", encoding="utf-8", errors="backslashreplace") as f:
				f.write("HD Satelit: raport de eroare, ecran protejat\n")
				f.write("Ecran: %s\n" % str(screen))
				f.write("Eroare: %s\n\n" % str(error))
				f.write(tb_str)
		except Exception as e:
			print("[HDS-SAFE] Eroare scriere crashlog:", e)

		print("[HDS-SAFE] Eroare la deschiderea ecranului %s (%d/3): %s" % (str(screen), self.screen_error_count, str(error)))
		# HDSatelit: un modul Python lipsa din feedul nostru se instaleaza singur (Components/HdsModuleLipsa.py); pluginul din stiva
		try:
			from Components import HdsModuleLipsa
			if HdsModuleLipsa.modulDinEroare(error):
				from Components import HdsPluginExtern
				p = HdsPluginExtern._pluginSiCadru(getattr(error, "__traceback__", None))
				if p:
					HdsModuleLipsa.dinExceptie(error, HdsPluginExtern.PREFIX_PLUGINURI + p[0] + "/" + p[1], p[1])
		except Exception as e:
			print("[HDS-SAFE] modulul lipsa:", e)

		# 0.7.8 (HB7): o actualizare instalata asteapta repornirea interfetei: ecranul a cazut fiindca fisierele noi de pe disc
		# nu se potrivesc cu modulele vechi din memorie; repornirea pe calea sigura (fara inregistrare) il repara
		try:
			from Components.HdsActualizari import reporneste_dupa_ecran_cazut
			if reporneste_dupa_ecran_cazut(self, getattr(screen, "__name__", str(screen))):
				self.screen_error_count = 0
				return
		except Exception as e:
			print("[HDS-SAFE] actualizarea nerepornita:", e)

		if self.screen_error_count >= 3:
			# 0.7.4 (actualizarea ramasa la jumatate, cologno49): cat opkg instaleaza, ecranele pot cadea fiindca fisierele
			# se schimba sub ele; repornirea interfetei ar omori opkg (lib/base/console.cpp) si ar lasa pachete amestecate
			try:
				from Components.HdsActualizari import instalare_in_curs
				instalare = instalare_in_curs()
			except Exception:
				instalare = False
			if instalare:
				print("[HDS-SAFE] 3 erori, dar opkg instaleaza acum: interfata nu se reporneste")
				self.screen_error_count = 0
				return
			print("[HDS-SAFE] 3 erori consecutive in 30 de secunde. Se reporneste interfata GUI...")
			# HDSatelit 0.7.5 (PRN): repornirea ceruta de aici apare si in jurnalul paznicului, cu ecranul cazut
			try:
				from Components import HdsPaznic
				HdsPaznic.jurnalPaznic("cerere de iesire: cod 3 (repornirea interfetei), 3 ecrane cazute in 30 s, ultimul %s"
					% getattr(screen, "__name__", str(screen)))
			except Exception:
				pass
			# cu o tema externa, tema se retrage inainte de repornire: omul revine la tema HD Satelit, fara bucla (Components/HdsSkinuri.py)
			try:
				from Components import HdsSkinuri
				HdsSkinuri.eroriEcrane(getattr(screen, "__name__", str(screen)), getattr(self, "screen_error_tema", False))
			except Exception as e:
				print("[HDS-SAFE] retragerea temei:", e)
			quitMainloop(3)
			return

		# Afiseaza notificare pe ecran fara sa blocheze receptorul
		try:
			from Screens.MessageBox import MessageBox
			s_name = getattr(screen, "__name__", str(screen))
			# 0.7.4 (FAA7MED, forum 588): textul trece prin traducere, altfel omul il vedea in romana pe un receptor in engleza
			msg = _("A apărut o problemă la deschiderea ecranului (%s).\nS-a revenit automat la meniul anterior în deplină siguranță.\nJurnalul de eroare a fost salvat pe disc.") % s_name
			self.open(MessageBox, msg, type=MessageBox.TYPE_WARNING, timeout=6)
		except Exception as e:
			print("[HDS-SAFE] Nu s-a putut afisa MessageBox de avertizare:", e)

	def create(self, screen, arguments, **kwargs):
		# creates an instance of 'screen' (which is a class)
		return screen(self, *arguments, **kwargs)

	def instantiateDialog(self, screen, *arguments, **kwargs):
		return self.doInstantiateDialog(screen, arguments, kwargs, self.desktop)

	def deleteDialog(self, screen):
		screen.hide()
		screen.doClose()

	def instantiateSummaryDialog(self, screen, *arguments, **kwargs):
		return self.doInstantiateDialog(screen, arguments, kwargs, self.summary_desktop)

	def doInstantiateDialog(self, screen, arguments, kwargs, desktop):
		# HDSatelit: zPosition e al ferestrei, nu un argument al constructorului ecranului.
		kwargs = kwargs.copy()
		zPosition = kwargs.pop("zPosition", None)
		# create dialog
		dlg = self.create(screen, arguments, **kwargs)
		if dlg is None:
			return None

		# read skin data
		try:
			readSkin(dlg, None, dlg.skinName, desktop)
			self.puneZPosition(dlg, zPosition)

			# create GUI view of this dialog
			assert desktop is not None

			dlg.setDesktop(desktop)
			dlg.applySkin()
		except Exception:
			# zPosition cerut la deschidere se pune si pe ecranul refacut din rezerva
			dlg.hdsZPosition = zPosition
			self.ecranCuRezerva(dlg, desktop)

		return dlg

	@staticmethod
	def puneZPosition(dlg, zPosition):
		"""zPosition cerut de plugin la deschidere trece inaintea celui din skin"""
		if zPosition is not None:
			dlg.skinAttributes = [(key, value) for key, value in dlg.skinAttributes if key != "zPosition"]
			dlg.skinAttributes.append(("zPosition", str(zPosition)))

	def ecranCuRezerva(self, dlg, desktop):
		"""Ecranul nu s-a putut construi: daca venea din tema externa, acelasi ecran se face din nou cu rezerva (ecranul nostru sau cel
		din cod), fara repornire si fara sa se ruleze iar constructorul lui (InfoBar e unul singur); omul afla din mesajul temei. Altfel
		eroarea merge mai departe, ca pana acum."""
		import skin
		if getattr(dlg, "hdsSursaTema", None) not in skin.dosareSkinStraine:
			raise
		print("[Skin] ecranul %s din tema externa nu s-a putut construi, se foloseste rezerva:" % dlg.__class__.__name__)
		print_exc(file=stdout)
		skin.ecranFaraTema(dlg)
		for r in list(getattr(dlg, "renderer", [])):
			try:
				r.disconnectAll()
			except Exception:
				print_exc(file=stdout)
		try:
			dlg.deleteGUIScreen()
		except Exception:
			print_exc(file=stdout)
		dlg.instance = None
		dlg.onLayoutFinish[:] = [f for f in dlg.onLayoutFinish if callable(f)]
		readSkin(dlg, None, dlg.skinName, desktop)
		self.puneZPosition(dlg, getattr(dlg, "hdsZPosition", None))
		dlg.setDesktop(desktop)
		dlg.applySkin()

	def pushCurrent(self):
		if self.current_dialog is not None:
			self.dialog_stack.append((self.current_dialog, self.current_dialog.shown))
			self.execEnd(last=False)

	def popCurrent(self):
		if self.dialog_stack:
			(self.current_dialog, do_show) = self.dialog_stack.pop()
			self.execBegin(first=False, do_show=do_show)
		else:
			self.current_dialog = None

	def execDialog(self, dialog):
		# HDSatelit 0.7.7 (DLG): un ecran care e deja deschis (ecranul de sus sau unul din stiva) nu se pune inca o data:
		# lista de canale deschisa de doua ori la pornire (o tasta + lantul de pornire) cadea la al doilea EXIT
		if dialog is self.current_dialog or any(d[0] is dialog for d in self.dialog_stack):
			print("[Session] %s e deja deschis, nu-l pun a doua oara in stiva" % dialog.__class__.__name__)
			return
		self.pushCurrent()
		self.current_dialog = dialog
		self.current_dialog.isTmp = False
		self.current_dialog.callback = None # would cause re-entrancy problems.
		# HDSatelit 0.7.4: lista de canale a barei se deschide pe aici; fara animatie (Components/HdsAnimatiiFerestre.py)
		if HdsAnimatiiFerestre is not None:
			HdsAnimatiiFerestre.laDeschidere(self, dialog)
		self.execBegin()

	def openWithCallback(self, callback, screen, *arguments, **kwargs):
		# HDSatelit 0.7.6 (NBM): amanata cu tot cu callback, numai pentru pluginurile straine (Components/HdsDeschidereAmanata.py)
		if self.dialog_stack and not self.in_exec and HdsDeschidereAmanata is not None:
			plugin = HdsDeschidereAmanata.deAmanat(self)
			if plugin:
				return HdsDeschidereAmanata.amana(self, plugin, callback, screen, arguments, kwargs)
		dlg = self.open(screen, *arguments, **kwargs)
		if dlg is not None:
			dlg.callback = callback
		return dlg

	def open(self, screen, *arguments, **kwargs):
		if self.dialog_stack and not self.in_exec:
			# HDSatelit 0.7.6 (NBM): cererea unui plugin strain se deschide cand e iar un ecran modal (open intoarce None);
			# codul imaginii primeste eroarea ca inainte (Components/HdsDeschidereAmanata.py)
			if HdsDeschidereAmanata is not None:
				plugin = HdsDeschidereAmanata.deAmanat(self)
				if plugin:
					return HdsDeschidereAmanata.amana(self, plugin, None, screen, arguments, kwargs)
			raise RuntimeError("modal open are allowed only from a screen which is modal!")
			# ...unless it's the very first screen.

		# HDSatelit 0.7.5 (PRN): cine cere repornirea; codul si ecranele deschise intra in jurnalul paznicului
		if getattr(screen, "__name__", "") == "TryQuitMainloop":
			try:
				from Components import HdsPaznic
				ecrane = [d[0].__class__.__name__ for d in self.dialog_stack if d and d[0] is not None]
				if self.current_dialog is not None:
					ecrane.append(self.current_dialog.__class__.__name__)
				HdsPaznic.cerereIesire(kwargs.get("retvalue", arguments[0] if arguments else 1), ecrane)
			except Exception as e:
				print("[mytest] cererea de iesire:", e)

		self.pushCurrent()
		try:
			try:
				dlg = self.instantiateDialog(screen, *arguments, **kwargs)
			except Exception as e:
				# HDSatelit 0.7.4: bara canalului cazuta dintr-un plugin care i-a schimbat clasele se construieste inca o
				# data, fara schimbarile pluginurilor (Components/HdsPazaBara.py); altfel eroarea merge mai departe ca inainte
				try:
					from Components import HdsPazaBara
					reparat = HdsPazaBara.repara(screen, e)
				except Exception:
					reparat = False
				if not reparat:
					raise
				dlg = self.instantiateDialog(screen, *arguments, **kwargs)
			if dlg is None:
				raise RuntimeError("Ecranul %s nu a putut fi instantiat" % str(screen))
		except Exception as e:
			import traceback
			tb = traceback.format_exc()
			print("[Session.open] Exceptie la crearea dialogului %s:" % str(screen))
			print(tb)
			self.popCurrent()
			self.handleScreenCrash(screen, e, tb)
			return None

		self.current_dialog = dlg
		dlg.isTmp = True
		dlg.callback = None
		# HDSatelit: numaratoarea ecranelor pentru beta testeri (numai cu programul pornit, fara nimic pe disc aici)
		if HdsBetaTester is not None:
			HdsBetaTester.numaraEcran(screen)
		# HDSatelit 0.7.4: animatia ferestrei numai pe ecranele potrivite (Components/HdsAnimatiiFerestre.py)
		if HdsAnimatiiFerestre is not None:
			HdsAnimatiiFerestre.laDeschidere(self, dlg)
		try:
			self.execBegin()
		except Exception:
			# HDSatelit: ecranul a cazut cand pornea (onExecBegin, onShown, show), dupa ce a devenit ecranul curent: cel de
			# dedesubt si-a pierdut tastele, el nu le-a primit. Semnul spune ca poate fi inchis (Components/HdsPluginExtern,
			# numai dupa eroarea unui plugin extern); eroarea merge mai departe ca inainte.
			dlg.hdsDeschidereEsuata = True
			raise
		# HDSatelit 0.7.6 (ASF): fereastra deschisa inaintea InfoBar-ului intra in jurnal (Components/HdsDeschidereAmanata.py)
		if HdsDeschidereAmanata is not None:
			HdsDeschidereAmanata.laDeschidere(self, dlg, screen, arguments, kwargs)
		return dlg

	def close(self, screen, *retval):
		if not self.in_exec:
			print("close after exec!")
			return

		# be sure that the close is for the right dialog!
		# if it's not, you probably closed after another dialog
		# was opened. this can happen if you open a dialog
		# onExecBegin, and forget to do this only once.
		# after close of the top dialog, the underlying will
		# gain focus again (for a short time), thus triggering
		# the onExec, which opens the dialog again, closing the loop.
		assert screen == self.current_dialog

		self.current_dialog.returnValue = retval
		self.delay_timer.start(0, 1)
		if HdsAnimatiiFerestre is not None:
			HdsAnimatiiFerestre.laInchidere(self, screen)
		self.execEnd()

	# HDSatelit 0.7.4 (OE-Alliance): mesajele scurte cerute de pluginuri pe sesiune (FastScan: showError cand o inregistrare e
	# in curs; PiconBrowser: showInfo), cu semnaturile din OE-Alliance; mesajul apare pe loc si pleaca singur (Screens/Toast.py)
	def showInfo(self, text, timeout=4, replaceId=None):
		from Screens.Toast import Toast
		Toast.instance.showToast(text=text, toastType=Toast.TYPE_INFO, timeout=timeout, replaceId=replaceId)

	def showWarning(self, text, timeout=5):
		from Screens.Toast import Toast
		Toast.instance.showToast(text=text, toastType=Toast.TYPE_WARNING, timeout=timeout)

	def showError(self, text, timeout=5):
		from Screens.Toast import Toast
		Toast.instance.showToast(text=text, toastType=Toast.TYPE_ERROR, timeout=timeout)

	def pushSummary(self):
		if self.summary is not None:
			self.summary.hide()
		self.summary_stack.append(self.summary)
		self.summary = None

	def popSummary(self):
		if self.summary is not None:
			self.summary.doClose()
		self.summary = self.summary_stack.pop()
		if self.summary is not None:
			self.summary.show()

profile("Standby,PowerKey")
import Screens.Standby
from Screens.Menu import MainMenu, mdom
from GlobalActions import globalActionMap

class PowerKey:
	""" PowerKey stuff - handles the powerkey press and powerkey release actions"""

	def __init__(self, session):
		self.session = session
		globalActionMap.actions["power_down"]=self.powerdown
		globalActionMap.actions["power_up"]=self.powerup
		globalActionMap.actions["power_long"]=self.powerlong
		globalActionMap.actions["deepstandby"]=self.shutdown # frontpanel long power button press
		self.standbyblocked = 1

	def MenuClosed(self, *val):
		self.session.infobar = None

	def shutdown(self):
		print("PowerOff - Now!")
		if not Screens.Standby.inTryQuitMainloop and self.session.current_dialog and self.session.current_dialog.ALLOW_SUSPEND:
			self.session.open(Screens.Standby.TryQuitMainloop, 1)

	def powerlong(self):
		if Screens.Standby.inTryQuitMainloop or (self.session.current_dialog and not self.session.current_dialog.ALLOW_SUSPEND):
			return
		self.doAction(action = config.usage.on_long_powerpress.value)

	def doAction(self, action):
		self.standbyblocked = 1
		if action == "shutdown":
			self.shutdown()
		elif action == "show_menu":
			print("Show shutdown Menu")
			# HDSatelit: meniul "shutdown" se cauta in tot menu.xml (Components/HdsTasteRapide.cauta_meniu): radacina e
			# <menuxml>, cu meniul principal singur copil, iar cautarea numai printre copiii directi ai radacinii nu-l mai
			# gasea, deci POWER tinut apasat nu deschidea nimic (si nici actiunea scurta, standbyblocked fiind pus mai sus)
			from Components.HdsTasteRapide import cauta_meniu
			x = cauta_meniu(mdom.getroot(), "shutdown")
			if x is not None:
				self.session.infobar = self
				menu_screen = self.session.openWithCallback(self.MenuClosed, MainMenu, x)
				# acelasi nume ca intrarea din meniul principal (menu.xml key="shutdown", text="Power & Restart" = Standby si repornire),
				# ca omul sa recunoasca lista deschisa cu POWER tinut apasat
				menu_screen.setTitle(_("Power & Restart"))
				return
			print("[PowerKey] meniul shutdown lipseste din menu.xml")
		elif action == "standby":
			self.standby()

	def powerdown(self):
		self.standbyblocked = 0

	def powerup(self):
		if self.standbyblocked == 0:
			self.doAction(action = config.usage.on_short_powerpress.value)

	def standby(self):
		if not Screens.Standby.inStandby and self.session.current_dialog and self.session.current_dialog.ALLOW_SUSPEND and self.session.in_exec:
			self.session.open(Screens.Standby.Standby)

profile("Scart")
from Screens.Scart import Scart

class AutoScartControl:
	def __init__(self, session):
		self.force = False
		self.current_vcr_sb = eAVSwitch.getInstance().getVCRSlowBlanking()
		if self.current_vcr_sb and config.av.vcrswitch.value:
			self.scartDialog = session.instantiateDialog(Scart, True)
		else:
			self.scartDialog = session.instantiateDialog(Scart, False)
		config.av.vcrswitch.addNotifier(self.recheckVCRSb)
		eAVSwitch.getInstance().vcr_sb_notifier.get().append(self.VCRSbChanged)

	def recheckVCRSb(self, configElement):
		self.VCRSbChanged(self.current_vcr_sb)

	def VCRSbChanged(self, value):
		#print "vcr sb changed to", value
		self.current_vcr_sb = value
		if config.av.vcrswitch.value or value > 2:
			if value:
				self.scartDialog.showMessageBox()
			else:
				self.scartDialog.switchToTV()

profile("Load:CI")
from enigma import eDVBCIInterfaces
from Screens.Ci import CiHandler

profile("Load:VolumeControl")
from Components.VolumeControl import VolumeControl

# HDSatelit 0.7.8 (SSO, Vu+ Solo SE, e-mailul 6529): cat tine fiecare pas al iesirii interfetei (Components/HdsPaznic.py,
# pasIesire): la sfarsitul procesului un rand in jurnalul paznicului si in hds-interfata.log spune ce a tinut ecranul
# negru. Numai un ceas dupa fiecare pas; nu arunca.
def _pasIesire(nume):
	try:
		from Components import HdsPaznic as _paznicIesire
		_paznicIesire.pasIesire(nume)
	except Exception:
		pass

def runScreenTest():
	config.misc.startCounter.value += 1
	# Queue the startup warning after the main map has recovered.
	keymapWarning = keymapparser.recoveryMessage(_)
	if keymapWarning:
		from Tools import Notifications
		from Screens.MessageBox import MessageBox
		Notifications.AddPopup(keymapWarning, MessageBox.TYPE_WARNING, 20, "keymap_recovery")

	profile("readPluginList")
	# HDSatelit 0.7.4: metodele barei canalului tinute minte inainte de pluginuri (Components/HdsPazaBara.py: un plugin care strica
	# bara nu lasa omul fara ea)
	try:
		from Components import HdsPazaBara
		HdsPazaBara.instantaneu()
	except Exception as e:
		print("[mytest] paza barei:", e)
	plugins.readPluginList(resolveFilename(SCOPE_PLUGINS))
	# pluginurile care nu s-au incarcat se anunta imediat, nu doar in Plugin browser
	if plugins.warnings:
		from Tools import Notifications
		from Screens.MessageBox import MessageBox
		text = _("Some plugins are not available:\n")
		for (pluginname, error) in plugins.warnings:
			text += _("%s (%s)\n") % (pluginname, error)
		Notifications.AddPopup(text, MessageBox.TYPE_WARNING, 20, "plugin_load_warnings")
	# erorile din skin nu opresc receptorul; se anunta o data, detaliile sunt in jurnal
	import skin
	# cu o tema externa, omul afla in cuvinte simple ce nu merge (Components/HdsTemaExterna.py); randurile raman in jurnal
	if skin.warnings and not skin.altSkinActiv():
		from Tools import Notifications
		from Screens.MessageBox import MessageBox
		text = _("The skin has errors, the receiver keeps working:\n")
		# short lines so they fit the message window; the full text is in the log
		text += "\n".join((w if len(w) <= 70 else w[:67] + "...") for w in skin.warnings[:5])
		if len(skin.warnings) > 5:
			text += "\n" + _("and %d more, see the log") % (len(skin.warnings) - 5)
		Notifications.AddPopup(text, MessageBox.TYPE_WARNING, 20, "skin_warnings")

	profile("Init:Session")
	nav = Navigation(config.misc.isNextRecordTimerAfterEventActionAuto.value)
	session = Session(desktop = getDesktop(0), summary_desktop = getDesktop(1), navigation = nav)
	from Components import HdsJurnalAfisaj
	HdsJurnalAfisaj.leagaSesiune(session)

	CiHandler.setSession(session)

	# HDSatelit: DAB+ si DVB-T2 din satelit (Hds/DabT2/imagine.py): extensiile de zap si de inregistrare in
	# Navigation, captura pe tasta. Releele pornesc abia la zap pe un post al nostru; pornirea receptorului nu
	# depinde de ele: orice eroare ramane in jurnal.
	try:
		from Hds.DabT2 import imagine as HdsDabT2
		HdsDabT2.porneste(session)
	except Exception as e:
		print("[mytest] DAB+ si DVB-T2:", e)

	# HDSatelit 0.7.0: Stream Relay (Components/HdsStreamRelay.py): legatura la zap numai cand lista canalelor exista si
	# are canale, sau (0.7.4) cand trecerea singura a canalelor cu ICAM e pornita (config.misc.hds_streamrelay_icam);
	# fara amandoua nici modulul nu se incarca (nimic schimbat la zap). Dupa DAB+/DVB-T2, ca extensia lor de zap sa
	# ramana inaintea celei a releului.
	try:
		from os.path import isfile as _esteFisier
		if _esteFisier("/etc/enigma2/whitelist_streamrelay") or config.misc.hds_streamrelay_icam.value:
			from Components import HdsStreamRelay
			HdsStreamRelay.porneste()
	except Exception as e:
		print("[mytest] Stream Relay:", e)

	# HDSatelit 0.7.0: televiziunea prin internet (Components/HdsIptvLucru.py): adresa locala si improspatarea zilnica, numai
	# daca omul are surse; fara ele nu ramane nimic pornit.
	try:
		from Components import HdsIptvLucru
		HdsIptvLucru.porneste()
	except Exception as e:
		print("[mytest] IPTV:", e)

	# HDSatelit: copia setarilor (Components/HdsCopieSetari.py). Dupa o punere la loc facuta de enigma2.sh, mesajul scurt
	# cu ce s-a pus intra in coada de notificari INAINTEA lui „Ce e nou” (coada se deschide in ordine): cand reteaua din
	# copie intra numai la pornirea receptorului, mesajul spune ca receptorul reporneste o data si o face singur dupa
	# 15 s, fara sa astepte inchiderea altui ecran; „Ce e nou” vine dupa repornire. Tot aici, ceasul copiei automate
	# zilnice. Pornirea receptorului nu depinde de ele: orice eroare ramane doar in jurnal.
	try:
		from Components import HdsCopieSetari
		HdsCopieSetari.porneste(session)
	except Exception as e:
		print("[mytest] copia setarilor:", e)

	# Jurnalul de versiuni (Screens/HdsJurnalVersiuni.py): la prima pornire dupa o actualizare, ecranul „Ce e
	# nou" se pune in coada de notificari, deci il deschide interfata dupa ce a pornit, nu se aseaza peste
	# asistentul de pornire. NU se pune in screensToRun: ecranele de acolo se deschid INAINTEA interfetei, pe
	# fundal negru, iar runNextScreen() de mai jos cheama quitMainloop() daca un asemenea ecran se inchide cu
	# o valoare de intoarcere. Pornirea receptorului nu depinde de el: orice eroare ramane doar in jurnal.
	try:
		from Screens.HdsJurnalVersiuni import arata_la_pornire
		arata_la_pornire(session)
	except Exception as e:
		print("[mytest] jurnalul de versiuni:", e)

	# HDSatelit 0.7.5: o singura data (prima pornire dupa asistent sau dupa actualizarea la 0.7.5), un mesaj scurt ca
	# setarile se pot cauta dupa nume (Components/HdsCautaSetariAnunt.py). Intra in coada DUPA „Ce e nou”; inchis cu OK
	# nu mai apare. Pornirea receptorului nu depinde de el: orice eroare ramane doar in jurnal.
	try:
		from Components import HdsCautaSetariAnunt
		HdsCautaSetariAnunt.porneste(session)
	except Exception as e:
		print("[mytest] mesajul despre Caută setări:", e)

	# HDSatelit 0.7.5: lista de canale orfana (asistenta 289712). Cand bouquets.tv are numai buchetele imaginii, dar pe
	# disc sunt buchetele omului nelegate (bouquets.tv refacut gol de nucleu), o singura intrebare cu OK le pune inapoi
	# (Components/HdsBucheteOrfane.py). Pe un receptor sanatos citeste numai cele doua radacini; orice eroare, in jurnal.
	try:
		from Components import HdsBucheteOrfane
		HdsBucheteOrfane.porneste(session)
	except Exception as e:
		print("[mytest] listele de canale nelegate:", e)

	# HDSatelit: tasta HELP pe orice ecran deschide pagina lui de ajutor, fara internet (Components/HdsAjutor.py; datele
	# in pachetul hdsatelit-ajutor). Numai legarea tastei: nimic citit de pe disc pana la prima apasare.
	try:
		from Components import HdsAjutor
		HdsAjutor.porneste(session)
	except Exception as e:
		print("[mytest] ajutorul:", e)
	# HDSatelit: tasta de captura (a treia tasta cu desen de ecran de pe telecomanda, Print Screen pe o tastatura USB) pe
	# orice ecran (Components/HdsCapturi.py): numai legarea tastelor, nimic citit de pe disc pana la prima apasare.
	try:
		from Components import HdsCapturi
		HdsCapturi.porneste(session)
	except Exception as e:
		print("[mytest] captura:", e)

	# HDSatelit: ceasul (NTP la pornire si periodic, in afara firului principal,
	# fara sa astepte reteaua; ora din transponder ca rezerva; fake-hwclock salvat periodic) si bataia pentru paznicul
	# receptorului (hds-watchdog.py nu mai reporneste interfata in timpul unei scanari sau al unei rotiri de antena).
	# Pornirea receptorului nu depinde de ele: orice eroare ramane doar in jurnal.
	try:
		from Components import HdsCeas
		HdsCeas.porneste()
	except Exception as e:
		print("[mytest] ceasul:", e)
	try:
		from Components import HdsPaznic
		HdsPaznic.porneste()
	except Exception as e:
		print("[mytest] bataia pentru paznic:", e)
	# HDSatelit: semnul „$" din lista de canale ia si ce stie baza canalelor (Components/HdsSemneBaza.py): o trecere la
	# 30 s dupa pornire, steagul 1024 pe canalele codate in baza. Pornirea nu depinde de ea.
	try:
		from Components import HdsSemneBaza
		HdsSemneBaza.porneste()
	except Exception as e:
		print("[mytest] semnele din baza canalelor:", e)
	# HDSatelit: al doilea tuner de satelit porneste singur daca are semnal (Components/HdsTunerB.py): o proba in fundal
	# la 90 s dupa pornire, a doua in standby; nimic pe ecran. Fara al doilea tuner sau cu el ales de om nu face nimic.
	try:
		from Components import HdsTunerB
		HdsTunerB.porneste(session)
	except Exception as e:
		print("[mytest] tunerul B:", e)
	# HDSatelit: Vu+ 4K cu FBC (Components/HdsFbcMutare.py): dupa 0.7.4, cand A e neconfigurat, B configurat si antena e
	# dovedit in mufa A, setarile lui B trec singure pe A, o singura data. Fara FBC nu face nimic. Pornirea nu depinde de ea.
	try:
		from Components import HdsFbcMutare
		HdsFbcMutare.porneste(session)
	except Exception as e:
		print("[mytest] mutarea FBC:", e)
	# HDSatelit: tunere FBC fara sincronizare de la pornirea receptorului (Components/HdsFbcFaraSincron.py, UFB8): o
	# singura data, oferta de repornire completa. Fara FBC nu face nimic. Pornirea nu depinde de ea.
	try:
		from Components import HdsFbcFaraSincron
		HdsFbcFaraSincron.porneste(session)
	except Exception as e:
		print("[mytest] FBC fara sincronizare:", e)
	# HDSatelit: „Jurnal detaliat” (Components/HdsJurnale.py): enigma2-debug.log tinut sub 8 MB (un stat() la 5 minute).
	try:
		from Components import HdsJurnale
		HdsJurnale.porneste()
	except Exception as e:
		print("[mytest] paza jurnalului detaliat:", e)
	# HDSatelit: swap-ul gasit porneste singur (Components/HdsSwap.py, 0.7.4): la 20 s si la 90 s, pe un fir, daca nu e
	# niciun swap pornit, partitia de swap de pe un stick sau un disc (intai cel al imaginii, ca la chkroot) sau
	# swapfile.hds facut din ecran; numai swapon. Pornirea nu depinde de el.
	try:
		from Components import HdsSwap
		HdsSwap.porneste()
	except Exception as e:
		print("[mytest] pornirea swap-ului:", e)
	# HDSatelit: legatura cu routerul si cu internetul (Components/HdsStareRetea.py): pictograma din bare si din web,
	# mesajul din mijlocul ecranului la pierderea internetului. Citirea pasiva la 3 s pe firul enigma2, verificarea DNS
	# pe firul ei. Pornirea nu depinde de ea.
	try:
		from Components import HdsStareRetea
		HdsStareRetea.porneste(session)
	except Exception as e:
		print("[mytest] starea retelei:", e)
	# HDSatelit: trecerea singura pe alta retea cand se pierde internetul, si inapoi (Components/HdsComutareRetea.py),
	# dupa raspunsurile verificarii de mai sus. Fara a doua retea nu face nimic. Pornirea nu depinde de ea.
	try:
		from Components import HdsComutareRetea
		HdsComutareRetea.porneste(session)
	except Exception as e:
		print("[mytest] trecerea pe alta retea:", e)
	# HDSatelit: feedul pluginurilor externe (Components/HdsPluginuriExterne.py, 0.6.6): /etc/opkg/hds-pluginuri-externe.conf
	# pe arhitectura procesorului, pus si dupa o actualizare prin pachete; numai un fisier mic, fara retea
	try:
		from Components import HdsPluginuriExterne
		HdsPluginuriExterne.porneste()
	except Exception as e:
		print("[mytest] feedul pluginurilor externe:", e)
	# HDSatelit: actualizarile prin pachete (Components/HdsActualizari.py): config-ul si verificarea zilnica (la 5
	# minute dupa pornire, apoi o data pe zi; numai anunta, nu instaleaza nimic). Pornirea nu depinde de ea.
	try:
		from Components import HdsParteaDoua
		from Components.SystemInfo import SystemInfo as infoSistem
		infoSistem["HdsParteaDoua"] = bool(HdsParteaDoua.citesteConf()) and HdsParteaDoua.radacinaNand()
	except Exception as e:
		print("[mytest] profilul partii a doua:", e)
	try:
		from Components import HdsActualizari
		HdsActualizari.porneste()
	except Exception as e:
		print("[mytest] actualizarile prin pachete:", e)
	# HDSatelit: imaginea completa de pe internet (Components/HdsImagineOnline.py): fereastra singura pentru o versiune noua,
	# actualizarea din standby si verificarea de dupa o scriere. Pornirea nu depinde de ea.
	try:
		from Components import HdsImagineOnline
		HdsImagineOnline.porneste(session)
	except Exception as e:
		print("[mytest] imaginea de pe internet:", e)
	# HDSatelit: VPN-ul (Components/HdsVpn.py), numai cu programele lui in imagine (SystemInfo["HdsVpn"]): urmareste un
	# VPN care merge (repornirea interfetei nu il opreste) si il porneste cand omul a cerut asta la pornirea
	# receptorului. Pornirea receptorului nu depinde de el.
	try:
		from Components.SystemInfo import SystemInfo as infoSistem   # alt nume: runScreenTest nu are SystemInfo local
		if infoSistem.get("HdsVpn"):
			from Components import HdsVpn
			HdsVpn.porneste()
	except Exception as e:
		print("[mytest] VPN-ul:", e)
	# HDSatelit: Asistenta de la distanta (Components/HdsAsistenta.py, Screens/HdsAsistentaSemn.py): oprita din
	# fabrica, nu porneste nimic de aici. Pune SystemInfo["HdsAsistenta"] (randul din Setari, requires=, se vede numai cand
	# e disponibila), pregateste semnul de pe ecran si reia o sesiune ramasa dupa o repornire a interfetei (fisierul
	# de stare exista numai daca omul a pornit asistenta in aceasta pornire). Pornirea nu depinde de ea.
	try:
		from Components import HdsAsistenta as _asist
		from Components.SystemInfo import SystemInfo as infoSistem
		infoSistem["HdsAsistenta"] = _asist.disponibil()
		from Screens import HdsAsistentaSemn
		HdsAsistentaSemn.instaleaza(session)
	except Exception as e:
		print("[mytest] asistenta de la distanta:", e)
	# HDSatelit: modul procesorului si paza de caldura (Components/HdsProcesor.py); fara cpufreq nu face nimic
	try:
		from Components import HdsProcesor
		HdsProcesor.porneste()
	except Exception as e:
		print("[mytest] procesorul:", e)
	# HDSatelit: raportul de procesor (Components/HdsProcesorRaport.py): firul principal peste 80% dintr-un nucleu
	# neintrerupt 2 minute -> o fereastra de 10 s culeasa si trimisa singura prin canalul rapoartelor de pornire, o data
	# pe pornire; omul nu face nimic. Un fir care masoara la 10 s; pornirea nu depinde de el.
	try:
		from Components import HdsProcesorRaport
		HdsProcesorRaport.porneste()
	except Exception as e:
		print("[mytest] raportul de procesor:", e)
	# HDSatelit: locurile din retea (Components/HdsStocareRetea.py): numai cele la care omul a ales "Montat si dupa
	# repornire" se monteaza in fundal, la 30 s dupa pornire, intr-un proces copil cu termen; nimic altceva nu se cauta
	# si nu se monteaza singur. Pornirea nu depinde de ele.
	try:
		from Components import HdsStocareRetea
		HdsStocareRetea.laPornire()
	except Exception as e:
		print("[mytest] locurile din retea:", e)
	# HDSatelit: afisajul din fata (4 cifre): lista de rotire, mesajele scurte si asteptarea (Components/HdsAfisaj.py); fara afisaj
	# nu face nimic
	try:
		from Components import HdsAfisaj
		HdsAfisaj.porneste(session)
	except Exception as e:
		print("[mytest] afisajul din fata:", e)
	# HDSatelit: iesirea HDMI lasata oprita de un enigma2 iesit in standby se porneste; nodul CEC dupa setari
	# (Components/HdsStandbyTv.py); fara /proc/stb/hdmi/output nu face nimic
	try:
		from Components import HdsStandbyTv
		HdsStandbyTv.porneste(session)
	except Exception as e:
		print("[mytest] standby si televizorul:", e)
	# HDSatelit: egalizatorul din procesor (Components/HdsEgalizator.py): setarile in motor si legatura la pornirea
	# serviciilor, inaintea primului serviciu
	try:
		from Components import HdsEgalizator
		HdsEgalizator.porneste()
	except Exception as e:
		print("[mytest] egalizatorul:", e)
	# HDSatelit: calitatea imaginii (Components/HdsCalitateImagine.py): iesirea HDR scrisa inaintea primului canal si
	# profilurile blocului de calitate la fiecare canal; fara /proc/msp/pq meniul nu se arata si nu se scrie nimic
	try:
		from Components import HdsCalitateImagine
		HdsCalitateImagine.porneste(session)
	except Exception as e:
		print("[mytest] calitatea imaginii:", e)
	# HDSatelit: poza canalului la schimbare (Components/HdsUltimaImagine.py, proba de concept, oprita din fabrica): cu
	# setarea pornita, la zap se arata ultima imagine a canalului nou pana vine imaginea vie; pozele numai in /tmp
	try:
		from Components import HdsUltimaImagine
		HdsUltimaImagine.porneste(session)
	except Exception as e:
		print("[mytest] poza canalului:", e)
	# HDSatelit: prima imagine rapida (Components/HdsPrimaImagine.py): pe receptoarele HiSilicon cu libreader, dupa zap
	# bQuickOutput = 1 scris in /proc/msp/syncNN (numai scrieri, pe un fir), ca primul cadru sa apara cum e decodat
	try:
		from Components import HdsPrimaImagine
		HdsPrimaImagine.porneste(session)
	except Exception as e:
		print("[mytest] prima imagine rapida:", e)
	# HDSatelit: HbbTV (Components/HdsHbbtvPornire.py, etapele H4 si H6): fereastra video lasata mica de o aplicatie
	# HbbTV inainte de o cadere a interfetei se pune pe tot ecranul, iar pornirea automata a aplicatiilor (setarea din
	# Setari navigator web, oprita din fabrica) asculta canalul redat. Pornirea receptorului nu depinde de ele.
	try:
		from Components import HdsHbbtvPornire
		HdsHbbtvPornire.porneste(session)
	except Exception as e:
		print("[mytest] HbbTV:", e)

	# HDSatelit: paza de model (Components/HdsPazaModel.py). Pe alt receptor decat cel pentru care e construita
	# imaginea, garda din enigma2.sh a oprit tot ce scrie pe partitii; interfata arata numai ecranul diagnosticului
	# (Screens/HdsPazaModel.py, codurile din Components/HdsDiagnostic.py), fara asistent si fara InfoBar. Fara fisierul
	# de reguli (emulatorul, alta imagine) nu se schimba nimic. Cand pornirea reuseste nu se arata nimic in plus (nici
	# pe un model neconfirmat): datele raman in Meniu > Informatii despre sistem > Diagnosticul pornirii si in /paza-model.
	try:
		from Components import HdsPazaModel
		paza_model = HdsPazaModel.inPaza()
	except Exception as e:
		print("[mytest] paza de model:", e)
		# A failed import or a code error does not identify another receiver.
		try:
			paza_model = HdsPazaModel.inchisLaEroare()
		except Exception:
			paza_model = False
	if paza_model:
		from Screens.HdsPazaModel import HdsPazaModel as EcranPazaModel
		screensToRun = [(0, EcranPazaModel)]
	else:
		screensToRun = [ p.fnc for p in plugins.getPlugins(PluginDescriptor.WHERE_WIZARD) ]

		profile("wizards")
		screensToRun += wizardManager.getWizards()

		# The wizard handles first boot after language selection; this handles upgrades.
		if HdsBetaTester is not None and HdsBetaTester.acordTestNecesar() and not config.misc.firstrun.value:
			from Screens.HdsBetaTester import HdsBetaConditii
			screensToRun.append((11, HdsBetaConditii))

		screensToRun.append((100, Screens.InfoBar.InfoBar))

		# HDSatelit: modul sigur (Components/HdsModSigur.py). Dupa 5 opriri neasteptate in 10 minute enigma2.sh porneste
		# interfata cu HDS_MOD_SIGUR=1: pluginurile din afara imaginii nu s-au incarcat mai sus, iar mesajul modului sigur
		# (Screens/HdsModSigur.py) se deschide primul, inaintea vrajitorilor (6, 10) si a InfoBar-ului. Prioritatea 1 e numai
		# a lui: sort() compara clasele la prioritati egale. In afara modului sigur porneste() programeaza copia setarilor
		# peste 10 minute si nu pune nimic in lista. Pornirea receptorului nu depinde de el: orice eroare ramane in jurnal.
		try:
			from Components import HdsModSigur
			ecran_mod_sigur = HdsModSigur.porneste()
		except Exception as e:
			print("[mytest] modul sigur:", e)
			ecran_mod_sigur = None
		if ecran_mod_sigur is not None:
			screensToRun.append((1, ecran_mod_sigur))

	screensToRun.sort()
	print("[mytest] screensToRun:", [(s[0], getattr(s[1], "__name__", str(s[1]))) for s in screensToRun])

	ePythonConfigQuery.setQueryFunc(configfile.getResolvedKey)

#	eDVBCIInterfaces.getInstance().setDescrambleRules(0 # Slot Number
#		,(	["1:0:1:24:4:85:C00000:0:0:0:"], #service_list
#			["PREMIERE"], #provider_list,
#			[] #caid_list
#		));

	def runNextScreen(session, screensToRun, *result):
		if result:
			quitMainloop(*result)
			return

		screen = screensToRun[0][1]
		args = screensToRun[0][2:]

		if screensToRun:
			session.openWithCallback(boundFunction(runNextScreen, session, screensToRun[1:]), screen, *args)
		else:
			session.open(screen, *args)
		if screen is Screens.InfoBar.InfoBar:
			# HDSatelit 0.7.6 (ASF, asistenta 222923): ferestrele deschise de pluginuri la sessionstart, ramase sub InfoBar,
			# se aduc deasupra cand InfoBar e ecranul de sus (Components/HdsDeschidereAmanata.py)
			if HdsDeschidereAmanata is not None:
				HdsDeschidereAmanata.dupaInfoBar(session, Screens.InfoBar.InfoBar.instance)
			try:
				from Screens.HdsParteaDoua import pornesteParteaDoua
				pornesteParteaDoua(session)
			except Exception as e:
				print("[mytest] partea a doua:", e)

	config.misc.epgcache_filename.addNotifier(setEPGCachePath)
	# HDSatelit: ghidul se scrie si la intrarea in standby si o data la 6 ore, nu numai la iesire
	if HdsEpgSalvare:
		HdsEpgSalvare.porneste()
	# HDSatelit: lista de canale (PID-urile tinute minte) se scrie si la intrarea in standby (Components/HdsLamedbSalvare.py)
	try:
		from Components import HdsLamedbSalvare
		HdsLamedbSalvare.porneste()
	except Exception as e:
		print("[mytest] lista de canale la standby:", e)
	# HDSatelit: beta testeri: contorul orei (fara standby), intrebarea o singura data dupa o ora, culegerea si
	# trimiterea pe fir, numai cu acordul omului. Pornirea nu depinde de el.
	try:
		if HdsBetaTester is not None:
			HdsBetaTester.porneste(session)
	except Exception as e:
		print("[mytest] beta tester:", e)
	# HDSatelit: jurnalele retelei si ale discurilor (Components/HdsJurnalSistem.py): numai schimbarile, la 30 s
	try:
		from Components import HdsJurnalSistem
		HdsJurnalSistem.porneste()
	except Exception as e:
		print("[mytest] jurnalele retelei si discurilor:", e)
	# HDSatelit 0.7.7 (VAR, asistenta 888733): variantele canalelor (Components/HdsVarianteCanal.py) se citesc pe un fir la un
	# minut dupa pornire si din nou dupa fiecare scriere a lamedb, nu pe firul interfetei la deschiderea listei de canale
	try:
		from Components import HdsVarianteCanal
		HdsVarianteCanal.porneste()
	except Exception as e:
		print("[mytest] variantele canalelor:", e)
	# HDSatelit: rapoartele erorilor din pluginurile externe ramase netrimise (Components/HdsPluginExtern): reincercate
	# la 15 minute, pe un fir; numai cand coada are ceva
	try:
		from Components import HdsPluginExtern
		HdsPluginExtern.porneste()
	except Exception as e:
		print("[mytest] rapoartele pluginurilor externe:", e)
	# HDSatelit: pluginurile cazute la pornire fiindca le lipsea un modul Python din feedul nostru il primesc acum, in fundal, cu un
	# mesaj mic (Components/HdsModuleLipsa.py), dupa ce interfata a pornit
	try:
		from Components import HdsModuleLipsa
		HdsModuleLipsa.porneste(session)
	except Exception as e:
		print("[mytest] modulele lipsa ale pluginurilor:", e)
	# HDSatelit 0.7.4: paznicul porturilor (Components/HdsPorturi.py): la un minut dupa pornire (modulul de acces a pornit
	# si si-a deschis porturile), daca doua servicii cer acelasi port sau un port al receptorului, o intrebare cu
	# "Schimbă portul" si "Nu acum". Pornirea receptorului nu depinde de el.
	try:
		from Components import HdsPorturi
		HdsPorturi.porneste(session)
	except Exception as e:
		print("[mytest] paznicul porturilor:", e)
	# HDSatelit 0.7.7 (OSD, LinuxSat 164182): oprirea automata dupa atatea ore fara nicio tasta, aleasa o data in ecranul
	# Sleep Timer sau in web (Components/HdsOprireAutomata.py); oprita din fabrica, fara ea nu se leaga nimic.
	try:
		from Components import HdsOprireAutomata
		HdsOprireAutomata.porneste(session)
	except Exception as e:
		print("[mytest] oprirea automata:", e)

	runNextScreen(session, screensToRun)

	profile("Init:VolumeControl")
	vol = VolumeControl(session)
	profile("Init:PowerKey")
	power = PowerKey(session)

	# we need session.scart to access it from within menu.xml
	session.scart = AutoScartControl(session)

	profile("RunReactor")
	profile_final()
	runReactor()

	# HDSatelit 0.7.6 (WDG): bucla s-a oprit; semnul pentru hds-watchdog.py, care opreste procesul daca nu iese in 45 s
	try:
		from Components import HdsPaznic
		HdsPaznic.iesireInceputa()
		# HDSatelit 0.7.8 (SSO): ceasul pasilor iesirii, de la cererea omului (Components/HdsPaznic.incepePasiiIesirii)
		HdsPaznic.incepePasiiIesirii()
	except Exception as e:
		print("[mytest] semnul iesirii:", e)
	# Finish profile IO and its main-thread callbacks before final settings saves.
	# This does not restart the reactor or dispatch unrelated events at shutdown.
	from Components import HdsTasteRapide
	HdsTasteRapide.termina_la_iesire()
	# HDSatelit 0.7.8 (ASL): cu asistenta pornita, semnul iesirii (codul cerut) intra in fisierul ei de stare, ca sesiunea
	# reluata la pornire sa spuna de ce a tacut (repornirea interfetei, a receptorului, oprirea); fara semn = cadere.
	# Alt nume la import: un HdsAsistenta local ar ascunde numele in toata functia.
	try:
		from Components import HdsAsistenta as _asistIesire
		_asistIesire.laIesire()
	except Exception as e:
		print("[mytest] asistenta la iesire:", e)
	_pasIesire("asistenta")
	# HDSatelit 0.7.7 (IES): dupa salvari, firele straine non-daemon (un server web, o descarcare a unei teme) nu mai tin
	# procesul viu pana la paza de 45 s: Py_Finalize le asteapta cel mult cateva secunde (Components/HdsPaznic.py)
	try:
		from Components import HdsPaznic
		HdsPaznic.pazaFirelorLaIesire()
	except Exception as e:
		print("[mytest] firele la iesire:", e)
	_pasIesire("paza firelor")

	# oprirea la cerere nu se numara impotriva unei teme externe aflate in proba
	if skin.altSkinActiv():
		try:
			from Components import HdsSkinuri
			HdsSkinuri.iesireCeruta()
		except Exception as e:
			print("[mytest] jurnalul temei la oprire:", e)
		_pasIesire("tema straina")

	# HDSatelit: releele DAB+ si DVB-T2 oprite si tunerul dat inapoi la iesirea enigma2
	try:
		from Hds.DabT2 import imagine as HdsDabT2
		HdsDabT2.opreste()
	except Exception as e:
		print("[mytest] DAB+ si DVB-T2 la oprire:", e)
	_pasIesire("DAB+ si DVB-T2")
	# HDSatelit: ora salvata in fake-hwclock si bataia oprita la iesirea enigma2
	try:
		from Components import HdsCeas
		HdsCeas.laOprire()
	except Exception as e:
		print("[mytest] ceasul la oprire:", e)
	_pasIesire("ceasul")
	# HDSatelit: baza canalelor scrisa la oprire, numai daca s-a schimbat ceva (Components/HdsCulegereCanale.py)
	try:
		from Components import HdsCulegereCanale
		HdsCulegereCanale.la_oprire()
	except Exception as e:
		print("[mytest] baza canalelor la oprire:", e)
	_pasIesire("baza canalelor")
	try:
		from Components import HdsPaznic
		HdsPaznic.opreste()
	except Exception as e:
		print("[mytest] bataia la oprire:", e)
	_pasIesire("bataia")
	# HDSatelit: contorul orei pentru beta testeri scris la iesire (numai cat il mai scrie programul)
	try:
		if HdsBetaTester is not None:
			HdsBetaTester.opreste()
	except Exception as e:
		print("[mytest] beta tester la oprire:", e)
	_pasIesire("beta tester")
	# HDSatelit: plafonul procesorului pus la loc ca la fabricant (numai daca s-a scris ceva in aceasta pornire)
	try:
		from Components import HdsProcesor
		HdsProcesor.laOprire()
	except Exception as e:
		print("[mytest] procesorul la oprire:", e)
	_pasIesire("procesorul")
	# HDSatelit: afisajul din fata ramane gol dupa iesirea interfetei (afara de „UPD” cat se scrie o imagine noua)
	try:
		from Components import HdsAfisaj
		HdsAfisaj.opreste()
	except Exception as e:
		print("[mytest] afisajul la oprire:", e)
	_pasIesire("afisajul")

	config.misc.startCounter.save()

	profile("wakeup")
	from time import time, strftime, localtime
	from Tools.DreamboxHardware import setFPWakeuptime, getFPWakeuptime, setRTCtime
	#get currentTime
	nowTime = time()
	wakeupList = [
		x for x in ((session.nav.RecordTimer.getNextRecordingTime(), 0, session.nav.RecordTimer.isNextRecordAfterEventActionAuto()),
					(session.nav.RecordTimer.getNextZapTime(), 1),
					(plugins.getNextWakeupTime(), 2))
		if x[0] != -1
	]
	wakeupList.sort()
	recordTimerWakeupAuto = False
	if wakeupList:
		from time import strftime
		startTime = wakeupList[0]
		if (startTime[0] - nowTime) < 270: # no time to switch box back on
			wptime = nowTime + 30  # so switch back on in 30 seconds
		else:
			wptime = startTime[0] - 240
		if not config.misc.useTransponderTime.value:
			print("dvb time sync disabled... so set RTC now to current linux time!", strftime("%Y/%m/%d %H:%M", localtime(nowTime)))
			setRTCtime(nowTime)
		print("set wakeup time to", strftime("%Y/%m/%d %H:%M", localtime(wptime)))
		setFPWakeuptime(wptime)
		recordTimerWakeupAuto = startTime[1] == 0 and startTime[2]
	config.misc.isNextRecordTimerAfterEventActionAuto.value = recordTimerWakeupAuto
	config.misc.isNextRecordTimerAfterEventActionAuto.save()
	_pasIesire("ora de trezire")

	profile("stopService")
	session.nav.stopService()
	_pasIesire("oprirea canalului")
	profile("nav shutdown")
	session.nav.shutdown()
	_pasIesire("temporizatoarele")

	profile("configfile.save")
	configfile.save()
	_pasIesire("setarile")

	return 0

profile("Init:skin")
# HDSatelit: fonturile Google descarcate de utilizator din ecranul HdsFonturi se dau
# lui enigma2 AICI, inainte de incarcarea skinului, ca un skin_user.xml sa le poata folosi.
# Modulul verifica fiecare fisier inainte de addFont -- addFont pe ceva ce nu e font face eFatal
# si opreste receptorul (lib/gdi/font.cpp:133). Un fisier stricat e sarit cu o linie in jurnal.
profile("Init:fonturiGoogle")
try:
	from Components.HdsFonturiGoogle import inregistreazaLaPornire
	inregistreazaLaPornire()
except Exception as _eroare_fonturi:
	print("[HdsFonturiGoogle] nu s-a putut porni: %s" % _eroare_fonturi)

import skin
skin.loadSkinData(getDesktop(0))

# HDSatelit: skinul a schimbat rezolutia OSD-ului si a sters semnatura: se deseneaza din nou, iar la primul pas al
# buclei principale locul ei se redeseneaza. Ecranul de pornire ales se pune din nou daca o actualizare l-a
# inlocuit, iar ecranele sterse de om din galerie se sterg din nou (pe un fir separat). Pornirea nu depinde de ele.
# 0.7.7 (OSD, e-mailul 6416): intai „Enigma2 pornește...” in coltul din dreapta jos (desenul lui poate sterge capsula,
# deci semnatura vine dupa); pleaca odata cu semnatura, la primul pas al buclei.
try:
	from Components import HdsSemnaturaPornire
	HdsSemnaturaPornire.arataColt()
	HdsSemnaturaPornire.arata()
	HdsSemnaturaPornire.ascundeLaPrimulDesen()
except Exception as e:
	print("[mytest] semnatura de pornire:", e)
try:
	from Components import HdsEcranePornire
	from Components import HdsGalerieSigle
	HdsGalerieSigle.configureRadio(config.misc.radiopic.value)
	HdsEcranePornire.verificaLaPornire()
except Exception as e:
	print("[mytest] ecranul de pornire:", e)

profile("InputDevice")
import Components.InputDevice
Components.InputDevice.InitInputDevices()

# HDSatelit: telecomenzile asociate (ecranul Telecomenzi) se pun in eRCMapper la pornire. Un fisier
# de asocieri stricat se muta deoparte cu un rand in jurnal; telecomanda receptorului merge oricum.
profile("HdsTelecomenzi")
try:
	from Components.HdsTelecomenziDate import porneste as _porneste_telecomenzi
	_porneste_telecomenzi()
except Exception as _eroare_telecomenzi:
	print("[HdsTelecomenzi] asocierile nu s-au incarcat: %s" % _eroare_telecomenzi)

profile("AVSwitch")
import Components.AVSwitch
Components.AVSwitch.InitAVSwitch()
import Components.VideoOutput
Components.VideoOutput.InitVideoOutput()
# HDSatelit: iesirea HDMI si televizorul in standby (Components/HdsStandbyTv.py): config.hds_standby si SystemInfo
# HdsHdmiStandby / HdsCec, inaintea meniurilor (randurile din setup.xml)
try:
	from Components import HdsStandbyTv
	HdsStandbyTv.initConfig()
except Exception as _eroare_standby_tv:
	print("[mytest] standby si televizorul: %s" % _eroare_standby_tv)

# HDSatelit: marginile ecranului salvate (Screens/OSDCalibration.py, Components/HdsMargini.py), puse in driver la
# pornire, dupa iesirea video; cu toate marginile 0 (din fabrica) nu se scrie nimic
profile("OSDCalibration")
try:
	from Screens.OSDCalibration import InitOSDCalibration
	InitOSDCalibration()
except Exception as _eroare_margini:
	print("[mytest] marginile ecranului: %s" % _eroare_margini)

profile("RecordingConfig")
import Components.RecordingConfig
Components.RecordingConfig.InitRecordingConfig()

profile("UsageConfig")
import Components.UsageConfig
Components.UsageConfig.InitUsageConfig()

# HDSatelit 0.7.4: animatia ferestrelor (Components/HdsAnimatiiFerestre.py): setarea, aplicata acum, si ecranele care o primesc
try:
	from Components import HdsAnimatiiFerestre
	HdsAnimatiiFerestre.initConfig()
except Exception as e:
	print("[mytest] animatia ferestrelor:", e)
	HdsAnimatiiFerestre = None

profile("keymapparser")
import keymapparser
keymapparser.readMainKeymap(config.usage.keymap.value)

profile("Network")
import Components.Network
Components.Network.InitNetwork()

profile("LCD")
import Components.Lcd
Components.Lcd.InitLcd()

profile("SetupDevices")
import Components.SetupDevices
Components.SetupDevices.InitSetupDevices()

profile("RFMod")
import Components.RFmod
Components.RFmod.InitRFmod()

profile("Init:CI")
import Screens.Ci
Screens.Ci.InitCiConfig()

#from enigma import dump_malloc_stats
#t = eTimer()
#t.callback.append(dump_malloc_stats)
#t.start(1000)

# first, setup a screen
try:
	runScreenTest()

	plugins.shutdown()
	_pasIesire("pluginurile")

	from Components.ParentalControl import parentalControl
	parentalControl.save()
	_pasIesire("controlul parental")
except:
	print('EXCEPTION IN PYTHON STARTUP CODE:')
	try:
		scrieExceptie(*exc_info())
	except Exception:
		pass
	print('-'*60)
	print_exc(file=stdout)
	quitMainloop(5)
	print('-'*60)
