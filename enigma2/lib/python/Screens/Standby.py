# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.config import config
from Components.AVSwitch import AVSwitch
from Components.SystemInfo import SystemInfo
from GlobalActions import globalActionMap
from enigma import eDVBVolumecontrol
import os

inStandby = None

# comutarea SCART / AUX / ENCODER numai unde driverul are intrarea (pe u57 nu exista: fara rand de eroare in jurnal)
_ARE_AVS = os.path.exists("/proc/stb/avs/0/input")


def _standbyTv(functie):
	"""Iesirea HDMI si televizorul (Components/HdsStandbyTv.py); o eroare nu opreste standby-ul."""
	try:
		from Components import HdsStandbyTv
		getattr(HdsStandbyTv, functie)()
	except Exception as e:
		print("[Standby] HdsStandbyTv.%s: %r" % (functie, e))

def stergeStandbyDinCoada():
	"""HDSatelit 0.7.4: scoate din coada notificarilor cererile de standby inca nedeschise (cerute din web, de un
	temporizator sau de un plugin cat o fereastra era deschisa pe televizor). Chemata la iesirea din standby, pe orice
	cale, si de web la trezire: altfel o cerere veche porneste standby-ul mult mai tarziu, cand se inchide fereastra
	(.114, 11.11.2026: un OK dupa 12 minute). Intoarce cate cereri a scos."""
	try:
		from Tools import Notifications
		vechi = [n for n in Notifications.notifications if n[1] is Standby]
		for n in vechi:
			if n in Notifications.notifications:
				Notifications.notifications.remove(n)
	except Exception as e:
		print("[Standby] coada notificarilor: %r" % e)
		return 0
	if vechi:
		print("[Standby] %d cereri de standby scoase din coada" % len(vechi))
	return len(vechi)


class Standby(Screen):
	def Power(self):
		print("leave standby")
		self.close(True)

	def setMute(self):
		if (eDVBVolumecontrol.getInstance().isMuted()):
			self.wasMuted = 1
			print("mute already active")
		else:	
			self.wasMuted = 0
			eDVBVolumecontrol.getInstance().volumeToggleMute()

	def leaveMute(self):
		if self.wasMuted == 0:
			eDVBVolumecontrol.getInstance().volumeToggleMute()

	def __init__(self, session):
		Screen.__init__(self, session)
		self.avswitch = AVSwitch()

		print("enter standby")

		self["actions"] = ActionMap( [ "StandbyActions" ],
		{
			"power": self.Power
		}, -1)

		globalActionMap.setEnabled(False)

		#mute adc
		self.setMute()

		self.paused_service = None
		self.prev_running_service = None
		if self.session.current_dialog:
			if self.session.current_dialog.ALLOW_SUSPEND == Screen.SUSPEND_STOPS:
				#get currently playing service reference
				self.prev_running_service = self.session.nav.getCurrentlyPlayingServiceReference()
				#stop actual played dvb-service
				self.session.nav.stopService()
			elif self.session.current_dialog.ALLOW_SUSPEND == Screen.SUSPEND_PAUSES:
				self.paused_service = self.session.current_dialog
				self.paused_service.pauseService()

		#set input to vcr scart
		if _ARE_AVS:
			if SystemInfo["ScartSwitch"]:
				self.avswitch.setInput("SCART")
			else:
				self.avswitch.setInput("AUX")
		self.onFirstExecBegin.append(self.__onFirstExecBegin)
		self.onClose.append(self.__onClose)

	def __onClose(self):
		global inStandby
		inStandby = None
		# o cerere de standby pusa in coada inainte de standby (o fereastra era deschisa) nu mai porneste dupa trezire
		stergeStandbyDinCoada()
		# iesirea HDMI pornita inaintea canalului (pornirile se suprapun), dupa inStandby = None (privirea culorilor
		# HDMI nu mai vede standby-ul); la orice iesire: tasta, web, temporizator
		_standbyTv("laIesire")
		if _ARE_AVS:
			self.avswitch.setInput("ENCODER")
		# Scoatem mutul dupa pornirea HDMI, inaintea reluarii canalului.
		# Driverul poate pierde unmute trimis cat iesirea este oprita.
		self.leaveMute()
		if self.prev_running_service:
			self.session.nav.playService(self.prev_running_service)
		elif self.paused_service:
			self.paused_service.unPauseService()
		self.session.screen["Standby"].boolean = False
		globalActionMap.setEnabled(True)

	def __onFirstExecBegin(self):
		global inStandby
		inStandby = self
		# iesirea HDMI oprita (si CEC catre televizor) dupa ce inStandby e pus, inaintea anuntului catre afisaj
		_standbyTv("laIntrare")
		self.session.screen["Standby"].boolean = True
		config.misc.standbyCounter.value += 1

	def createSummary(self):
		return StandbySummary

class StandbySummary(Screen):
	skin = """
	<screen position="0,0" size="132,64">
		<widget source="global.CurrentTime" render="Label" position="0,0" size="132,64" font="Regular;40" halign="center">
			<convert type="ClockToText" />
		</widget>
		<widget source="session.RecordState" render="FixedLabel" text=" " position="0,0" size="132,64" zPosition="1" >
			<convert type="ConfigEntryTest">config.usage.blinking_display_clock_during_recording,True,CheckSourceBoolean</convert>
			<convert type="ConditionalShowHide">Blink</convert>
		</widget>
	</screen>"""

from enigma import quitMainloop, iRecordableService
from Screens.MessageBox import MessageBox
from time import time
from Components.Task import job_manager

inTryQuitMainloop = False

# HDSatelit: numele codurilor de iesire cerute de pluginurile altor imagini (TryQuitMainloop(session, QUIT_RESTART)); aceleasi valori
# ca in tools/enigma2.sh.in (1 oprire, 2 repornirea receptorului, 3 repornirea interfetei)
QUIT_SHUTDOWN = 1
QUIT_REBOOT = 2
QUIT_RESTART = 3
# restul numelor din alte imagini, cu numerele lor: pluginurile se incarca fara eroare. Scriptul nostru de pornire
# (tools/enigma2.sh.in) face 1 oprire, 2 repornire, 4 actualizarea afisajului din fata; 5 il ia drept cadere;
# celelalte coduri pornesc interfata din nou (ca 3)
QUIT_UPGRADE_FP = 4
QUIT_ERROR_RESTART = 5
QUIT_DEBUG_RESTART = 6
QUIT_KODI = 15
QUIT_MAINT = 16
QUIT_RETROGAMING = 17
QUIT_UPGRADE_PROGRAM = 42
QUIT_IMAGE_RESTORE = 43
QUIT_UPGRADE_FRONTPANEL = 44
QUIT_WOLSHUTDOWN = 45
quitMainloopCode = 1
TVinStandby = None

# HDSatelit (0.7.4, LinuxSat 164125 #969426): cat ruleaza opkg (o actualizare din meniu sau o extensie se instaleaza),
# iesirea enigma2 l-ar opri la jumatate: eConsoleAppContainer ii trimite SIGKILL la distrugere (lib/base/console.cpp),
# status-ul opkg ramane pe versiunea veche, fisierele raman amestecate si interfata nu mai porneste. Atunci TryQuitMainloop
# nu iese: spune pe televizor ca asteapta, verifica la PAS_INSTALARE_MS si face ce s-a cerut (oprire, repornire) singur,
# dupa ce opkg a terminat si nu se inregistreaza nimic. OK sau EXIT renunta. Codul 4 (afisajul din fata) nu asteapta.
# asteaptaInstalarea: o asemenea fereastra e pe ecran (pagina web a actualizarilor o arata).
PAS_INSTALARE_MS = 2000
asteaptaInstalarea = False


def _instalareInCurs():
	"""True cat ruleaza opkg sau cat se instaleaza o actualizare (Components/HdsActualizari.instalare_in_curs)"""
	try:
		from Components.HdsActualizari import instalare_in_curs
		return instalare_in_curs()
	except Exception as e:
		print("[TryQuitMainloop] instalarea in curs: %r" % (e,))
		return False


def _textInstalare(retvalue):
	if retvalue == QUIT_SHUTDOWN:
		return _("Se instalează pachete software. Receptorul se oprește singur după ce se termină instalarea.") + "\n" + \
			_("OK sau EXIT: renunți.")
	if retvalue == QUIT_REBOOT:
		return _("Se instalează pachete software. Receptorul repornește singur după ce se termină instalarea.") + "\n" + \
			_("OK sau EXIT: renunți.")
	return _("Se instalează pachete software. Interfața repornește singură după ce se termină instalarea.") + "\n" + \
		_("OK sau EXIT: renunți.")


class TryQuitMainloop(MessageBox):
	def __init__(self, session, retvalue=1, timeout=-1, default_yes = True):
		self.retval=retvalue
		self._ceasInstalare = None
		if retvalue != 4 and _instalareInCurs():
			self.__asteaptaInstalarea(session, retvalue)
			return
		recordings = session.nav.getRecordings()
		jobs = len(job_manager.getPendingJobs())
		self.connected = False
		reason = ""
		next_rec_time = -1
		if not recordings:
			next_rec_time = session.nav.RecordTimer.getNextRecordingTime()	
		if recordings or (next_rec_time > 0 and (next_rec_time - time()) < 360):
			reason = _("Recording(s) are in progress or coming up in few seconds!") + '\n'
		if jobs:
			if jobs == 1:
				job = job_manager.getPendingJobs()[0]
				reason += "%s: %s (%d%%)\n" % (job.getStatustext(), job.name, int(100*job.progress/float(job.end)))
			else:
				reason += (_("%d jobs are running in the background!") % jobs) + '\n'
		if reason:
			if retvalue == 1:
				MessageBox.__init__(self, session, reason+_("Really shutdown now?"), type = MessageBox.TYPE_YESNO, timeout = timeout, default = default_yes)
			elif retvalue == 2:
				MessageBox.__init__(self, session, reason+_("Really reboot now?"), type = MessageBox.TYPE_YESNO, timeout = timeout, default = default_yes)
			elif retvalue == 4:
				pass
			else:
				MessageBox.__init__(self, session, reason+_("Really restart now?"), type = MessageBox.TYPE_YESNO, timeout = timeout, default = default_yes)
			self.skinName = "MessageBox"
			session.nav.record_event.append(self.getRecordEvent)
			self.connected = True
			self.onShow.append(self.__onShow)
			self.onHide.append(self.__onHide)
		else:
			self.skin = """<screen position="0,0" size="0,0"/>"""
			Screen.__init__(self, session)
			self.close(True)

	def getRecordEvent(self, recservice, event):
		if event == iRecordableService.evEnd:
			recordings = self.session.nav.getRecordings()
			if not recordings: # no more recordings exist
				rec_time = self.session.nav.RecordTimer.getNextRecordingTime()
				if rec_time > 0 and (rec_time - time()) < 360:
					self.initTimeout(360) # wait for next starting timer
					self.startTimer()
				else:
					self.close(True) # immediate shutdown
		elif event == iRecordableService.evStart:
			self.stopTimer()

	# HDSatelit: fereastra de asteptare cat ruleaza opkg (vezi PAS_INSTALARE_MS)
	def __asteaptaInstalarea(self, session, retvalue):
		global asteaptaInstalarea
		self.connected = False
		self._instalareGata = False
		MessageBox.__init__(self, session, _textInstalare(retvalue), type=MessageBox.TYPE_INFO, timeout=-1)
		self.skinName = "MessageBox"
		from enigma import eTimer
		self._ceasInstalare = eTimer()
		try:
			self._legaturaInstalare = self._ceasInstalare.timeout.connect(self.__verificaInstalarea)
		except AttributeError:
			self._ceasInstalare.callback.append(self.__verificaInstalarea)
		self._ceasInstalare.start(PAS_INSTALARE_MS, False)
		asteaptaInstalarea = True
		self.onShow.append(self.__onShow)
		self.onHide.append(self.__onHide)
		print("[TryQuitMainloop] se instaleaza pachete: codul %s asteapta sfarsitul instalarii" % retvalue)

	def __verificaInstalarea(self):
		if self._ceasInstalare is None or _instalareInCurs():
			return
		try:
			if self.session.nav.getRecordings():
				return
		except Exception:
			pass
		print("[TryQuitMainloop] instalarea s-a terminat: codul %s" % self.retval)
		self._instalareGata = True
		self.close(True)

	def close(self, value):
		global asteaptaInstalarea
		# getattr: o clasa straina facuta din TryQuitMainloop, cu __init__ propriu, nu are campul
		if getattr(self, "_ceasInstalare", None) is not None:
			self._ceasInstalare.stop()
			self._ceasInstalare = None
			asteaptaInstalarea = False
			if not self._instalareGata:
				# OK sau EXIT pe fereastra de asteptare: omul renunta, ca la Nu pe intrebare
				print("[TryQuitMainloop] asteptarea instalarii oprita de om: codul %s nu se mai face" % self.retval)
				value = False
		if self.connected:
			self.conntected=False
			self.session.nav.record_event.remove(self.getRecordEvent)
		if value:
			# HDSatelit: canalul la care te uitai, in fisierul lui mic, inainte de oprire sau repornire, oricat a stat pe
			# ecran (settings il scrie enigma2 la iesirea curata; Components/HdsCanalTinut.py)
			try:
				from Components.HdsCanalTinut import scrie_acum
				scrie_acum()
			except Exception as e:
				print("[TryQuitMainloop] canalul tinut minte: %r" % (e,))
			# HDSatelit: la oprirea completa (nu la repornire) televizorul primeste prin CEC acelasi mesaj ca la intrarea
			# in standby, cand e aleasa „Stinge si televizorul (CEC)” (Components/HdsStandbyTv.py)
			if self.retval == 1:
				_standbyTv("laOprire")
			quitMainloop(self.retval)
		else:
			MessageBox.close(self, True)

	def __onShow(self):
		global inTryQuitMainloop, quitMainloopCode
		inTryQuitMainloop = True
		# Alte imagini: codul iesirii cerute, citit de pluginuri (Screens.Standby.quitMainloopCode)
		quitMainloopCode = getattr(self, "retval", quitMainloopCode)

	def __onHide(self):
		global inTryQuitMainloop
		inTryQuitMainloop = False
