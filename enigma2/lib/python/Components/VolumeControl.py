# Modificat de moneasoftware.com si hdsatelit.com, 2026
from enigma import eDVBVolumecontrol, eTimer
from Tools.Profile import profile
from Screens.Volume import Volume
from Screens.Mute import Mute
from GlobalActions import globalActionMap
from .config import config, ConfigSubsection, ConfigInteger, ConfigYesNo

profile("VolumeControl")

MUT_Z = 10
# VOL8: bara de volum la mijloc sta peste bara canalului (jos, y 802..1034), sub semnul de mut
VOL_MIJLOC_Z = 9
# a volume key repeat arrives every ~100-200 ms while held; two separate presses are slower than this
REPETARE_S = 0.35


def _setariSunet():
	"""Components/HdsSetariSunet.py (pasul volumului, volumul tinut minte pe canal), sau None: fara el pasul ramane 5."""
	try:
		from Components import HdsSetariSunet
		return HdsSetariSunet
	except Exception as e:
		print("[VolumeControl] Components/HdsSetariSunet.py nu se poate incarca: %s" % e)
		return None


def _inStandby():
	try:
		from Screens.Standby import inStandby
		return inStandby is not None
	except Exception:
		return False


#TODO .. move this to a own .py file
class VolumeControl:
	instance = None
	# HDSatelit 0.8.0 (VLY0): cine vrea sa stie volumul nou dupa VOL+/VOL-/MUTE (fn(nivel, mut, ms)). Cat navigatorul web tine
	# ecranul (aplicatia YouTube si celelalte din Aplicatii) enigma2 nu poate desena (fbClass.lock), deci bara de volum o
	# deseneaza navigatorul (Plugins/Extensions/HdsNavigator/lansator.py); pasii si MUTE raman cei de aici.
	ascultatori = []
	"""Volume control, handles volUp, volDown, volMute actions and display
	a corresponding dialog"""
	def __init__(self, session):
		global globalActionMap
		globalActionMap.actions["volumeUp"]=self.volUp
		globalActionMap.actions["volumeDown"]=self.volDown
		globalActionMap.actions["volumeMute"]=self.volMute

		assert not VolumeControl.instance, "only one VolumeControl instance is allowed!"
		VolumeControl.instance = self

		config.audio = ConfigSubsection()
		config.audio.volume = ConfigInteger(default = 100, limits = (0, 100))
		# HDSatelit: mutul tinut minte separat; volumul salvat ramane nivelul ales si cat sunetul e pe mut. Scris o data,
		# ramane in setari si cand e Nu (save_forced): asa se stie ca volumul salvat e nivelul, nu 0 pentru mut ca inainte
		# (Components/HdsSetariSunet.mutLaPornire il pune la loc la primul canal dupa pornire)
		config.audio.hds_mut = ConfigYesNo(default = False)
		config.audio.hds_mut.save_forced = True

		self.session = session
		self.volumeDialog = self._faVolum()
		# HDSatelit 0.7.7 (OSD, asistenta 906594): semnul de mut deasupra barei canalului (la pornire bara sta pe ecran cat
		# semnul; in tema Pro semnul cade peste caseta ceasului din bara si ramanea ascuns sub ea, proba pe receptor). MUT_Z sub
		# protectia ecranului (20) si sub textul iesirii (120).
		self.muteDialog = session.instantiateDialog(Mute, zPosition=MUT_Z)

		self.hideVolTimer = eTimer()
		self.hideVolTimer.callback.append(self.volHide)
		# HDSatelit: semnul de mut pleaca singur dupa setarea "Cât stă semnul de mut pe ecran" (0 = mereu)
		self.hideMutTimer = eTimer()
		self.hideMutTimer.callback.append(self.mutHide)

		vol = config.audio.volume.value
		self.volumeDialog.setValue(vol)
		self._volctrl = None
		self._ascultaLocul()

	def _faVolum(self):
		"""Fereastra volumului: sus in dreapta ca pana atunci, sau la mijloc (VOL8, Screens/Volume.laMijloc) peste bara canalului."""
		try:
			from Screens.Volume import laMijloc
			mijloc = laMijloc()
		except Exception:
			mijloc = False
		if mijloc:
			return self.session.instantiateDialog(Volume, zPosition=VOL_MIJLOC_Z)
		return self.session.instantiateDialog(Volume)

	def _ascultaLocul(self):
		"""VOL8: "Locul barei de volum" si "Arată numărul lângă bara de volum" (Components/HdsSetariSunet.py) se schimba pe loc,
		de pe televizor sau din web: ferestrele se fac din nou."""
		try:
			c = config.hds_setari_sunet
			c.loc_volum.addNotifier(self.refaFerestrele, initial_call=False)
			c.numar_volum.addNotifier(self.refaFerestrele, initial_call=False)
		except Exception as e:
			print("[VolumeControl] locul barei de volum: %s" % e)

	def refaFerestrele(self, *args):
		"""Bara si semnul de mut din nou, dupa locul si numarul alese; bara se arata cat stau de obicei, ca omul sa vada
		unde e acum, iar semnul de mut ramane pe ecran daca era."""
		# Screen.shown e True si inainte de prima aratare (already_shown False): pe ecran = amandoua
		mutVizibil = bool(getattr(self.muteDialog, "shown", False) and getattr(self.muteDialog, "already_shown", True))
		for d in (self.volumeDialog, self.muteDialog):
			try:
				self.session.deleteDialog(d)
			except Exception as e:
				print("[VolumeControl] fereastra veche: %s" % e)
		self.volumeDialog = self._faVolum()
		self.muteDialog = self.session.instantiateDialog(Mute, zPosition=MUT_Z)
		vc = self.volctrl
		if vc is not None:
			self.volumeDialog.setValue(0 if vc.isMuted() else vc.getVolume())
		else:
			self.volumeDialog.setValue(config.audio.volume.value)
		if mutVizibil:
			self.muteDialog.show()
		self.volumeDialog.show()
		self.hideVolTimer.start(self.afisareMs(), True)

	@property
	def volctrl(self):
		if getattr(self, "_volctrl", None) is None:
			try:
				self._volctrl = eDVBVolumecontrol.getInstance()
			except Exception as e:
				print("[VolumeControl] getInstance error:", e)
				return None
		return self._volctrl

	def volSave(self):
		if not self.volctrl:
			return
		# HDSatelit: nivelul, si cat sunetul e pe mut (inainte se scria 0, iar la pornire nivelul se pierdea); mutul separat
		config.audio.volume.value = self.volctrl.getVolume()
		config.audio.volume.save()
		self.mutSave()
		# HDSatelit: volumul tinut minte pe canalul de acum (cand setarea e pe Da), si cel ajuns la mut (nivelul ramane)
		s = _setariSunet()
		if s is not None:
			try:
				s.laVolumSalvat(self.volctrl.getVolume())
			except Exception as e:
				print("[VolumeControl] volumul canalului: %s" % e)

	def mutSave(self):
		"""HDSatelit: mutul de acum in config.audio.hds_mut, afara de standby (standby-ul pune si scoate singur mutul)."""
		if not self.volctrl or _inStandby():
			return
		config.audio.hds_mut.value = bool(self.volctrl.isMuted())
		config.audio.hds_mut.save()
		s = _setariSunet()
		if s is not None:
			try:
				s.laMutSalvat()
			except Exception as e:
				print("[VolumeControl] mutul: %s" % e)

	def pas(self):
		"""Pasul tastelor de volum (Meniu > Audio & Sound Tracks > Volum și întârziere), 5 fara setare."""
		s = _setariSunet()
		try:
			return s.pasVolum() if s is not None else 5
		except Exception:
			return 5

	def afisareMs(self):
		"""Cat sta bara volumului pe ecran (Meniu > Audio & Sound Tracks > Volum și întârziere), 3000 ms fara setare."""
		s = _setariSunet()
		try:
			return s.afisareVolumMs() if s is not None else 3000
		except Exception:
			return 3000

	def afisareMutMs(self):
		"""Cat sta semnul de mut pe ecran (aceeasi pagina), 0 = mereu; 5000 ms fara setare."""
		s = _setariSunet()
		try:
			return s.afisareMutMs() if s is not None else 5000
		except Exception:
			return 5000

	def arataMut(self, minimMs=0):
		"""Semnul de mut pe ecran, cu ceasul care il ascunde (afara de "Mereu"). minimMs: cel putin atat pe ecran (0.7.7,
		mutul pus la pornire, Components/HdsSetariSunet.MUT_PORNIRE_MIN_MS); "Mereu" ramane mereu."""
		self.muteDialog.show()
		self.hideMutTimer.stop()
		ms = self.afisareMutMs()
		if ms > 0:
			self.hideMutTimer.start(max(ms, minimMs), True)

	def mutHide(self):
		self.muteDialog.hide()

	def volUp(self):
		self.setVolume(+1)

	def volDown(self):
		self.setVolume(-1)

	def pasTinut(self, direction, acum=None):
		"""0.8.0 (tamiciav7): the step for this press. A volume key held down repeats (keymap flags "mr"); a call in the
		same direction within REPETARE_S of the previous one is a repeat and uses "Pasul volumului cât ții tasta apăsată"
		(HdsSetariSunet.pasVolumLung, equal to the normal step by default). The first press keeps the normal step."""
		import time
		acum = time.monotonic() if acum is None else acum
		ultim = getattr(self, "_ultimaApasare", None)
		self._ultimaApasare = (direction, acum)
		tinut = ultim is not None and ultim[0] == direction and 0 <= acum - ultim[1] <= REPETARE_S
		if not tinut:
			return self.pas()
		s = _setariSunet()
		try:
			return s.pasVolumLung() if s is not None else self.pas()
		except Exception:
			return self.pas()

	def setVolume(self, direction):
		if not self.volctrl:
			return
		oldvol = self.volctrl.getVolume()
		pas = self.pasTinut(direction)
		if direction > 0:
			self.volctrl.volumeUp(pas, pas)
		else:
			self.volctrl.volumeDown(pas, pas)
		is_muted = self.volctrl.isMuted()
		vol = self.volctrl.getVolume()
		self.volumeDialog.show()
		if is_muted:
			self.volMute() # unmute
		elif not vol:
			self.volMute(False, True) # mute but dont show mute symbol
		if self.volctrl.isMuted():
			self.volumeDialog.setValue(0)
		else:
			self.volumeDialog.setValue(self.volctrl.getVolume())
		self.volSave()
		self.hideVolTimer.start(self.afisareMs(), True)
		self.anuntaVolum()

	def anuntaVolum(self):
		"""VLY0: volumul de acum (0 cat e pe mut, ca bara), mutul si cat sta bara, la ascultatori; o eroare a unuia nu
		strica volumul."""
		if not VolumeControl.ascultatori or not self.volctrl:
			return
		mut = bool(self.volctrl.isMuted())
		nivel = 0 if mut else int(self.volctrl.getVolume())
		ms = self.afisareMs()
		for f in list(VolumeControl.ascultatori):
			try:
				f(nivel, mut, ms)
			except Exception as e:
				print("[VolumeControl] ascultatorul volumului: %s" % e)

	def volHide(self):
		self.volumeDialog.hide()

	def volMute(self, showMuteSymbol=True, force=False):
		if not self.volctrl:
			return
		vol = self.volctrl.getVolume()
		if vol or force:
			self.volctrl.volumeToggleMute()
			if self.volctrl.isMuted():
				if showMuteSymbol:
					self.arataMut()
				self.volumeDialog.setValue(0)
			else:
				self.hideMutTimer.stop()
				self.muteDialog.hide()
				self.volumeDialog.setValue(vol)
			self.mutSave()
			self.anuntaVolum()
