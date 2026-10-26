# Modificat de moneasoftware.com si hdsatelit.com, 2026
import eConsoleImpl
import eBaseImpl
import enigma
enigma.eTimer = eBaseImpl.eTimer
enigma.eSocketNotifier = eBaseImpl.eSocketNotifier
enigma.eConsoleAppContainer = eConsoleImpl.eConsoleAppContainer

# HDSatelit: stivele tuturor firelor Python in /tmp/enigma2-stive.txt la semnalul SIGRTMIN+7. hds-watchdog il trimite
# inainte de SIGTERM-ul unei interfete care nu mai raspunde si pastreaza copia in /home/root/logs (enigma2-stive-*.txt):
# un blocaj lasa urma lui, nu numai „fara bataie”. Fisierul se goleste la fiecare pornire.
try:
	import faulthandler
	import signal
	_hdsStive = open("/tmp/enigma2-stive.txt", "w")
	faulthandler.register(signal.SIGRTMIN + 7, file=_hdsStive, all_threads=True, chain=False)
except Exception as e:
	print("[mytest] stivele la semnal:", e)

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

def setEPGCachePath(configElement):
	# un ghid scris de versiunea dinainte pe /hdd/epg.dat trece pe calea noua inainte sa-l citeasca firul ghidului
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
	twisted.python.runtime.platform.supportsThreads = lambda: False

	import e2reactor
	e2reactor.install()

	from twisted.internet import reactor

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

		for p in plugins.getPlugins(PluginDescriptor.WHERE_SESSIONSTART):
			p(reason=0, session=self)

	def processDelay(self):
		callback = self.current_dialog.callback

		retval = self.current_dialog.returnValue

		if self.current_dialog.isTmp:
			self.current_dialog.doClose()
#			dump(self.current_dialog)
			del self.current_dialog
		else:
			del self.current_dialog.callback

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
		self.screen_error_count = getattr(self, "screen_error_count", 0) + 1
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

		if self.screen_error_count >= 3:
			print("[HDS-SAFE] 3 erori consecutive in 30 de secunde. Se reporneste interfata GUI...")
			quitMainloop(3)
			return

		# Afiseaza notificare pe ecran fara sa blocheze receptorul
		try:
			from Screens.MessageBox import MessageBox
			s_name = getattr(screen, "__name__", str(screen))
			msg = "A apărut o problemă la deschiderea ecranului (%s).\nS-a revenit automat la meniul anterior în deplină siguranță.\nJurnalul de eroare a fost salvat pe disc." % s_name
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
		# create dialog
		dlg = self.create(screen, arguments, **kwargs)
		if dlg is None:
			return None

		# read skin data
		readSkin(dlg, None, dlg.skinName, desktop)

		# create GUI view of this dialog
		assert desktop is not None

		dlg.setDesktop(desktop)
		dlg.applySkin()

		return dlg

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
		self.pushCurrent()
		self.current_dialog = dialog
		self.current_dialog.isTmp = False
		self.current_dialog.callback = None # would cause re-entrancy problems.
		self.execBegin()

	def openWithCallback(self, callback, screen, *arguments, **kwargs):
		dlg = self.open(screen, *arguments, **kwargs)
		if dlg is not None:
			dlg.callback = callback
		return dlg

	def open(self, screen, *arguments, **kwargs):
		if self.dialog_stack and not self.in_exec:
			raise RuntimeError("modal open are allowed only from a screen which is modal!")
			# ...unless it's the very first screen.

		self.pushCurrent()
		try:
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
		self.execBegin()
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
		self.execEnd()

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
				menu_screen.setTitle(_("Standby / Restart"))
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

def runScreenTest():
	config.misc.startCounter.value += 1

	profile("readPluginList")
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
	if skin.warnings:
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

	CiHandler.setSession(session)

	# HDSatelit: DAB+ si DVB-T2 din satelit (Hds/DabT2/imagine.py): extensiile de zap si de inregistrare in
	# Navigation, captura pe tasta. Releele pornesc abia la zap pe un post al nostru; pornirea receptorului nu
	# depinde de ele: orice eroare ramane in jurnal.
	try:
		from Hds.DabT2 import imagine as HdsDabT2
		HdsDabT2.porneste(session)
	except Exception as e:
		print("[mytest] DAB+ si DVB-T2:", e)

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
		from Components import HdsActualizari
		HdsActualizari.porneste()
	except Exception as e:
		print("[mytest] actualizarile prin pachete:", e)
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
	# HDSatelit: modul procesorului si paza de caldura (Components/HdsProcesor.py); fara cpufreq nu face nimic
	try:
		from Components import HdsProcesor
		HdsProcesor.porneste()
	except Exception as e:
		print("[mytest] procesorul:", e)
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
	# HDSatelit: HbbTV (Components/HdsHbbtvPornire.py, etapele H4 si H6): fereastra video lasata mica de o aplicatie
	# HbbTV inainte de o cadere a interfetei se pune pe tot ecranul, iar pornirea automata a aplicatiilor (setarea din
	# Setari navigator web, oprita din fabrica) asculta canalul redat. Pornirea receptorului nu depinde de ele.
	try:
		from Components import HdsHbbtvPornire
		HdsHbbtvPornire.porneste(session)
	except Exception as e:
		print("[mytest] HbbTV:", e)

	# HDSatelit: paza de model (Components/HdsPazaModel.py). Pe alt receptor decat cel pentru care e construita
	# imaginea, garda din enigma2.sh a oprit tot ce scrie pe partitii; interfata arata numai mesajul
	# (Screens/HdsPazaModel.py), fara asistent si fara InfoBar. Fara fisierul de reguli (emulatorul, alta imagine) nu
	# se schimba nimic.
	try:
		from Components import HdsPazaModel
		paza_model = HdsPazaModel.inPaza()
	except Exception as e:
		print("[mytest] paza de model:", e)
		paza_model = False
	if paza_model:
		from Screens.HdsPazaModel import HdsPazaModel as EcranPazaModel
		screensToRun = [(0, EcranPazaModel)]
	else:
		screensToRun = [ p.fnc for p in plugins.getPlugins(PluginDescriptor.WHERE_WIZARD) ]
		# HDSatelit: un model neconfirmat (treapta a doua a pazei, regulile cu confirmat=nu) a trecut paza: interfata
		# porneste, iar o nota arata ca software-ul e pentru testeri si ce valori citite difera de cele asteptate
		try:
			from Components import HdsPazaModel
			nota_model = HdsPazaModel.notaNeconfirmat()
			if nota_model:
				from Tools import Notifications
				from Screens.MessageBox import MessageBox
				Notifications.AddNotification(MessageBox, nota_model, type=MessageBox.TYPE_INFO, timeout=30)
		except Exception as e:
			print("[mytest] paza de model, nota:", e)

		profile("wizards")
		screensToRun += wizardManager.getWizards()

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

	# HDSatelit: releele DAB+ si DVB-T2 oprite si tunerul dat inapoi la iesirea enigma2
	try:
		from Hds.DabT2 import imagine as HdsDabT2
		HdsDabT2.opreste()
	except Exception as e:
		print("[mytest] DAB+ si DVB-T2 la oprire:", e)
	# HDSatelit: ora salvata in fake-hwclock si bataia oprita la iesirea enigma2
	try:
		from Components import HdsCeas
		HdsCeas.laOprire()
	except Exception as e:
		print("[mytest] ceasul la oprire:", e)
	# HDSatelit: baza canalelor scrisa la oprire, numai daca s-a schimbat ceva (Components/HdsCulegereCanale.py)
	try:
		from Components import HdsCulegereCanale
		HdsCulegereCanale.la_oprire()
	except Exception as e:
		print("[mytest] baza canalelor la oprire:", e)
	try:
		from Components import HdsPaznic
		HdsPaznic.opreste()
	except Exception as e:
		print("[mytest] bataia la oprire:", e)
	# HDSatelit: plafonul procesorului pus la loc ca la fabricant (numai daca s-a scris ceva in aceasta pornire)
	try:
		from Components import HdsProcesor
		HdsProcesor.laOprire()
	except Exception as e:
		print("[mytest] procesorul la oprire:", e)
	# HDSatelit: afisajul din fata ramane gol dupa iesirea interfetei (afara de „UPD” cat se scrie o imagine noua)
	try:
		from Components import HdsAfisaj
		HdsAfisaj.opreste()
	except Exception as e:
		print("[mytest] afisajul la oprire:", e)

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

	profile("stopService")
	session.nav.stopService()
	profile("nav shutdown")
	session.nav.shutdown()

	profile("configfile.save")
	configfile.save()

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
try:
	from Components import HdsSemnaturaPornire
	HdsSemnaturaPornire.arata()
	HdsSemnaturaPornire.ascundeLaPrimulDesen()
except Exception as e:
	print("[mytest] semnatura de pornire:", e)
try:
	from Components import HdsEcranePornire
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

profile("keymapparser")
import keymapparser
keymapparser.readKeymap(config.usage.keymap.value)

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

	from Components.ParentalControl import parentalControl
	parentalControl.save()
except:
	print('EXCEPTION IN PYTHON STARTUP CODE:')
	print('-'*60)
	print_exc(file=stdout)
	quitMainloop(5)
	print('-'*60)
