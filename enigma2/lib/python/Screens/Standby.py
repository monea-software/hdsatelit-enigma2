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


def _standbyTv(functie, *argumente):
	"""Iesirea HDMI si televizorul (Components/HdsStandbyTv.py); o eroare nu opreste standby-ul."""
	try:
		from Components import HdsStandbyTv
		getattr(HdsStandbyTv, functie)(*argumente)
	except Exception as e:
		print("[Standby] HdsStandbyTv.%s: %r" % (functie, e))

def stergeStandbyDinCoada():
	"""HDSatelit 0.7.4: scoate din coada notificarilor cererile de standby inca nedeschise (cerute din web, de un
	temporizator sau de un plugin cat o fereastra era deschisa pe televizor). Chemata la iesirea din standby, pe orice
	cale, si de web la trezire: altfel o cerere veche porneste standby-ul mult mai tarziu, cand se inchide fereastra
	(receptorul de probe SF8008, 11.11.2026: un OK dupa 12 minute). Intoarce cate cereri a scos."""
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
		# 0.8.0: motivul trezirii (tasta, web, asistenta, CEC) aflat pe loc, din stiva apelului (HdsStandbyTv.laPower)
		_standbyTv("laPower")
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
from time import time, sleep
try:
	from time import monotonic
except ImportError:
	monotonic = time
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
# 0.7.7 (UPD): codul iesirii care a pornit din TryQuitMainloop (close cu True), None pana atunci
iesireCeruta = None
# 0.7.8 (SSO): ora (monotonic) cererii si a lui quitMainloop, pentru pasii iesirii (Components/HdsPaznic.pasIesire)
iesireCerutaLa = None
iesireQuitLa = None
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


# HDSatelit 0.7.7 (OSD; e-mailul 6416, Vu+ Solo SE; TODO 15.11 14:22): textul de pe televizor la iesirea interfetei, ca
# in OE-Alliance (aceeasi clasa, QuitMainloopScreen, cu widgetul „text”, ca temele si pluginurile scrise pentru ea sa-l
# gaseasca). Inainte TryQuitMainloop iesea pe loc, cu ecranul neschimbat, si omul nu stia ce se intampla. Bucla
# principala nu mai apuca sa deseneze o fereastra aratata chiar inainte de quitMainloop, deci desenul se cere pe loc
# (desktop.paint) si se asteapta randarea, cel mult RANDARE_ASTEAPTA_S. La oprire (codul 1) ora desenului merge la
# Components/HdsStandbyTv.laOprire, care opreste HDMI abia dupa ce textul a stat macar o secunda pe ecran. Cat receptorul
# e in standby (televizorul si iesirea HDMI sunt deja stinse) nu se arata nimic; codurile 4 (afisajul din fata) si 5
# (caderea) n-au text. Celelalte coduri pornesc interfata din nou (tools/enigma2.sh.in), deci „Interfața repornește...”.
# Desenul se cere o data si se asteapta randarea; se cere din nou numai la REPICTARE_S (animatia ferestrelor poate tine
# desenul cel mult 100 ms dupa o inchidere): cerut la fiecare pas, ar tine coada randarii mereu ocupata si asteptarea ar
# merge pana la capat. RANDARE_ASTEAPTA_S e numai marginea; iesirea asteapta cat dureaza desenul.
RANDARE_ASTEAPTA_S = 1.5
REPICTARE_S = 0.12


def textIesire(cod):
	"""Textul de pe televizor pentru codul dat lui quitMainloop; "" cand nu se arata nimic."""
	if cod == QUIT_SHUTDOWN:
		return _("Receptorul se oprește...")
	if cod == QUIT_REBOOT:
		return _("Receptorul repornește...")
	if cod in (QUIT_UPGRADE_FP, QUIT_ERROR_RESTART):
		return ""
	return _("Interfața repornește...")


class QuitMainloopScreen(Screen):
	"""Fereastra pe tot ecranul cu textul iesirii (vezi textIesire). Tema o poate desena dupa numele din OE-Alliance."""
	skin = """<screen name="QuitMainloopScreen" position="0,0" size="1920,1080" flags="wfNoBorder" backgroundColor="#000a0e1a" zPosition="120">
		<widget name="text" position="120,440" size="1680,200" font="Regular;54" halign="center" valign="center" foregroundColor="#00f0f6fc" backgroundColor="#000a0e1a" transparent="1" />
	</screen>"""

	def __init__(self, session, retvalue=QUIT_SHUTDOWN):
		Screen.__init__(self, session)
		try:
			from Tools.ScaledSkin import scaledSkin
			self.skin = scaledSkin(QuitMainloopScreen.skin, 1920)   # skinul e scris pe 1920 de pixeli
		except Exception:
			pass
		from Components.Label import Label
		self["text"] = Label(textIesire(retvalue))


class HdsTextIesire(QuitMainloopScreen):
	"""Aceeasi fereastra cu skinul nostru, cand QuitMainloopScreen din tema aleasa nu se poate pune."""
	def __init__(self, session, retvalue=QUIT_SHUTDOWN):
		QuitMainloopScreen.__init__(self, session, retvalue)
		self.skinName = ["HdsTextIesire"]


_ecranIesire = []     # fereastra tinuta pana la iesire (altfel Python o strica inainte de desen)


def _deseneazaAcum(desktop):
	"""Desenul ferestrelor aratate acum, pe loc, si asteptarea randarii (gRC), cel mult RANDARE_ASTEAPTA_S. True cand
	randarea s-a terminat. paint() poate lasa desenul pentru mai tarziu (animatia ferestrelor tine cel mult 100 ms dupa o
	inchidere), deci se cere din nou, dar numai la REPICTARE_S."""
	capat = monotonic() + RANDARE_ASTEAPTA_S
	urmatorul = 0
	while True:
		try:
			if monotonic() >= urmatorul:
				desktop.paint()
				urmatorul = monotonic() + REPICTARE_S
			sleep(0.01)
			if desktop.captureReady():
				return True
		except Exception as e:
			print("[TryQuitMainloop] desenul textului de iesire: %r" % (e,))
			return False
		if monotonic() >= capat:
			return False


def arataTextIesire(session, cod):
	"""Textul iesirii pe televizor, desenat pe loc (vezi textIesire). Intoarce ora desenului (monotonic) sau None cand nu
	s-a aratat nimic. Nu arunca: iesirea nu depinde de el."""
	text = textIesire(cod)
	if not text or inStandby is not None or session is None:
		return None
	try:
		from enigma import getDesktop
		desktop = getDesktop(0)
	except Exception as e:
		print("[TryQuitMainloop] textul de iesire: %r" % (e,))
		return None
	for nume in ("hdsAnimatieElibereaza", "hdsAnimatieFaraPas"):
		try:
			getattr(desktop, nume)()
		except Exception:
			pass
	ecran = None
	for clasa in (QuitMainloopScreen, HdsTextIesire):
		try:
			ecran = session.instantiateDialog(clasa, retvalue=cod)
			break
		except Exception as e:
			print("[TryQuitMainloop] %s: %r" % (clasa.__name__, e))
	if ecran is None:
		return None
	_ecranIesire.append(ecran)
	try:
		ecran.instance.setAnimationMode(0)
		ecran.show()
	except Exception as e:
		print("[TryQuitMainloop] textul de iesire: %r" % (e,))
		return None
	inceput = monotonic()
	gata = _deseneazaAcum(desktop)
	acum = monotonic()
	print("[TryQuitMainloop] textul de iesire pe ecran (cod %s): %s in %d ms" % (cod,
		"desenat" if gata else "randarea neconfirmata", int((acum - inceput) * 1000)))
	return acum


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
			# HDSatelit 0.7.7 (UPD, dorinelu forum 795 #2668): codul iesirii care chiar porneste acum (si fara intrebare,
			# cand fereastra nu se arata deloc), pentru semnul iesirii (Components/HdsPaznic._codIesireCeruta): dupa o
			# iesire agatata, paznicul o opreste, iar enigma2.sh face tot ce s-a cerut (repornirea receptorului, oprirea)
			global iesireCeruta, iesireCerutaLa, iesireQuitLa
			iesireCeruta = self.retval
			iesireCerutaLa = monotonic()
			# HDSatelit 0.7.7 (OSD): textul iesirii pe televizor („Receptorul se oprește...” si celelalte), desenat pe loc,
			# inainte ca CEC si HDMI sa stinga ecranul
			desenat = arataTextIesire(getattr(self, "session", None), self.retval)
			# HDSatelit: la oprirea completa (nu la repornire) televizorul primeste prin CEC acelasi mesaj ca la intrarea
			# in standby, cand e aleasa „Stinge si televizorul (CEC)” (Components/HdsStandbyTv.py); HDMI se opreste abia
			# dupa ce textul a stat macar o secunda pe ecran
			if self.retval == 1:
				if desenat is None:
					_standbyTv("laOprire")
				else:
					_standbyTv("laOprire", desenat)
			iesireQuitLa = monotonic()
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


# HDSatelit 0.8.0 (RBT0; Vu+ Duo 4K Lite, 3 blocaje pe 2 receptoare, STADIU-CEC9): un plugin chema `reboot` direct (in
# forma care face pe loc apelul de sistem) cat enigma2 inca mergea; driverul Vu+ elibera atunci CEC-ul si video-ul de
# sub enigma2 (Oops in nexus) si receptorul ramanea blocat. /sbin/reboot, /sbin/halt si /sbin/poweroff sunt acum
# hds-oprire-curata (reteta hdsatelit-oprire-curata din strat): cu enigma2 pornit scriu CERERE_OPRIRE (cod=2 repornirea,
# cod=1 oprirea; de= cine a cerut) si trimit SIGUSR2 lui enigma2. Aici semnalul porneste aceeasi iesire ca din meniu
# (codul tinut pentru paznic, canalul tinut minte, CEC la oprire, quitMainloop), deci enigma2 se opreste curat, apoi
# tools/enigma2.sh face repornirea sau oprirea ceruta. Fara fereastra de intrebare. Repornirea din meniu nu trece pe aici.
# Semnalul se prinde numai pe firul principal (signal.signal); handlerul Python ruleaza intre doi pasi ai interpretorului,
# iesirea se face apoi dintr-un eTimer, nu din handler.
CERERE_OPRIRE = "/tmp/hds-oprire-ceruta"
_cerereOprire = {"timer": None}


def citesteCerereaDeOprire(cale=None):
	"""(cod, cine) din CERERE_OPRIRE (fisier mic in RAM), sters dupa citire; cod 2 cand lipseste sau nu e 1 / 2."""
	cale = cale or CERERE_OPRIRE
	cod, cine = QUIT_REBOOT, ""
	try:
		with open(cale, "r") as f:
			for rand in f.read(4096).splitlines():
				k, _s, v = rand.partition("=")
				if k == "cod" and v.strip() in ("1", "2"):
					cod = int(v.strip())
				elif k == "de":
					cine = v.strip()[:120]
		os.remove(cale)
	except Exception:
		pass
	return cod, cine


def iesireCerutaDinAfara(cod=None, cine=""):
	"""Iesirea ceruta de hds-oprire-curata: ca TryQuitMainloop.close(True), fara intrebare."""
	global iesireCeruta, iesireCerutaLa, iesireQuitLa
	if cod is None:
		cod, cine = citesteCerereaDeOprire()
	print("[Standby] %s ceruta din afara (%s) cu interfata pornita: enigma2 se opreste intai curat (cod %d)" % (
		"repornirea" if cod == QUIT_REBOOT else "oprirea", cine or "necunoscut", cod))
	try:
		from Components.HdsCanalTinut import scrie_acum
		scrie_acum()
	except Exception as e:
		print("[Standby] canalul tinut minte: %r" % (e,))
	iesireCeruta = cod
	iesireCerutaLa = monotonic()
	# la oprire televizorul primeste prin CEC mesajul de standby, ca la oprirea din meniu (fara textul de pe ecran: aici nu
	# e nicio sesiune la indemana, iar iesirea nu depinde de el)
	if cod == QUIT_SHUTDOWN:
		_standbyTv("laOprire")
	iesireQuitLa = monotonic()
	quitMainloop(cod)


def _laSemnalulDeOprire(semnal=None, cadru=None):
	t = _cerereOprire.get("timer")
	if t is not None:
		t.start(0, True)
	else:
		iesireCerutaDinAfara()


def pornestePrimireaOpririi():
	"""SIGUSR2 -> iesireCerutaDinAfara (pe firul principal, la import). Intoarce True daca semnalul e prins."""
	try:
		import signal
		from enigma import eTimer
		t = eTimer()
		t.callback.append(iesireCerutaDinAfara)
		_cerereOprire["timer"] = t
		signal.signal(signal.SIGUSR2, _laSemnalulDeOprire)
		return True
	except Exception as e:
		print("[Standby] cererea de oprire din afara (SIGUSR2): %r" % (e,))
		return False


pornestePrimireaOpririi()
