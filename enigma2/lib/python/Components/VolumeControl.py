# Modificat de moneasoftware.com si hdsatelit.com, 2026
from enigma import eDVBVolumecontrol, eTimer
from Tools.Profile import profile
from Screens.Volume import Volume
from Screens.Mute import Mute
from GlobalActions import globalActionMap
from .config import config, ConfigSubsection, ConfigInteger, ConfigYesNo

profile("VolumeControl")


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

		self.volumeDialog = session.instantiateDialog(Volume)
		self.muteDialog = session.instantiateDialog(Mute)

		self.hideVolTimer = eTimer()
		self.hideVolTimer.callback.append(self.volHide)

		vol = config.audio.volume.value
		self.volumeDialog.setValue(vol)
		self._volctrl = None

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

	def volUp(self):
		self.setVolume(+1)

	def volDown(self):
		self.setVolume(-1)

	def setVolume(self, direction):
		if not self.volctrl:
			return
		oldvol = self.volctrl.getVolume()
		pas = self.pas()
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
					self.muteDialog.show()
				self.volumeDialog.setValue(0)
			else:
				self.muteDialog.hide()
				self.volumeDialog.setValue(vol)
			self.mutSave()
