# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .config import config, ConfigSlider, ConfigSelection, ConfigYesNo, \
	ConfigEnableDisable, ConfigSubsection, ConfigBoolean, ConfigSelectionNumber, ConfigNothing, NoSave
from enigma import eAVSwitch, getDesktop
from .SystemInfo import SystemInfo
from os import path as os_path
import os

# Sunetul spre televizor. Driverul u57 are pentru sunet numai /proc/stb/audio/ac3 si dts, fiecare cu
# "downmix passthrough" in *_choices; showiframe le citeste cand porneste sunetul. Comutatorul apare numai cand lista
# driverului are "downmix", implicit Da (downmix), scris la fiecare pornire, deci driverul primeste de la inceput o
# valoare stiuta (stereo, pe care o poate reda orice televizor). Scrierea (writeAudioChoice): numai o valoare din lista
# *_choices a driverului, fara "\n"; o eroare de scriere se prinde si se scrie in jurnal. Intarzierile generale AC3 / PCM se arata numai cand
# exista fisierele lor (pe u57 lipsesc, deci reglajul nu ar avea efect). HDS_PROBA_STB_AUDIO = alt dosar, numai pentru
# probele de pe PC (teste, emulator), ca HDS_PROBA_MOUNTS din Harddisk.py.
# „Ieșirea sunetului” (Components/HdsSunet.py): pe Manual randurile AC3 / DTS downmix scriu ca mai sus; pe Automat
# comutatoarele le pune HdsSunet dupa ce anunta televizorul, iar randurile raman setarile pentru Manual (o schimbare
# de mana a lor trece iesirea pe Manual). Fara HdsSunet (modul lipsa) totul merge ca pe Manual.
STB_AUDIO = "/proc/stb/audio/"
AUDIO_CHOICES = {}   # nume -> lista driverului (*_choices), citita o data, in InitAVSwitch
# nodurile pe care toggleAC3Downmix tocmai le-a scris: notificatorul setarii nu le mai scrie a doua oara
AUDIO_WRITTEN_BY_KEY = set()


def audioRoot():
	return os.environ.get("HDS_PROBA_STB_AUDIO") or STB_AUDIO


def _hdsSunet():
	"""Components.HdsSunet sau None (modul lipsa sau stricat: sunetul merge ca pe Manual)."""
	try:
		from Components import HdsSunet
		return HdsSunet
	except ImportError:
		return None
	except Exception as err:
		print("[AVSwitch] Components/HdsSunet.py nu se poate incarca: %s" % err)
		return None


def _scrieDinRand(name, element):
	"""Notificatorii randurilor AC3 / DTS downmix: True cand valoarea randului se scrie acum in driver (Manual);
	pe Automat comutatorul e al lui HdsSunet, iar o schimbare de mana trece iesirea pe Manual, care scrie tot."""
	sunet = _hdsSunet()
	if sunet is None:
		return True
	try:
		return sunet.laSchimbareDeMana(name, element)
	except Exception as err:
		print("[AVSwitch] iesirea sunetului: %s" % err)
		return True


def _downmixEfectiv(name, element):
	"""Ce face acum comutatorul (True = downmix): pe Automat din driver, altfel valoarea randului."""
	sunet = _hdsSunet()
	if sunet is not None:
		try:
			if sunet.automat():
				valoare = sunet.efectiv(name)
				if valoare in ("downmix", "passthrough"):
					return valoare == "downmix"
		except Exception as err:
			print("[AVSwitch] iesirea sunetului: %s" % err)
	return bool(element.value)


def _randDownmix(name):
	"""config.av.downmix_<name> sau None (ConfigSubsection da KeyError, nu AttributeError, pentru un nume lipsa)."""
	try:
		return getattr(config.av, "downmix_" + name)
	except (KeyError, AttributeError):
		return None


def downmixAcum(name):
	"""Pentru ecranele care arata AC3 / DTS downmix (ecranul AUDIO, bara): True daca sunetul `name` („ac3”, „dts”) se
	face acum stereo in receptor, False daca pleaca neschimbat, None fara comutator. Pe „Ieșirea sunetului: Automat”
	randul salvat doarme, deci se citeste ce face driverul."""
	element = _randDownmix(name)
	if element is None:
		return None
	return _downmixEfectiv(name, element)


def setDownmix(name, downmix):
	"""AC3 / DTS downmix schimbat de om dintr-un ecran (ecranul AUDIO, bara): valoarea se pune (notificatorul o scrie),
	„Ieșirea sunetului” trece pe Manual daca era pe Automat (o singura scriere in driver, cu valoarea noua) si totul se
	salveaza. False fara comutator."""
	element = _randDownmix(name)
	if element is None:
		return False
	element.value = bool(downmix)
	sunet = _hdsSunet()
	if sunet is not None:
		try:
			sunet.treciPeManual()
		except Exception as err:
			print("[AVSwitch] iesirea sunetului: %s" % err)
	element.save()
	return True


def readAudioChoices(name, root=None):
	"""lista din /proc/stb/audio/<name>_choices; [] cand fisierul lipseste sau nu se poate citi"""
	try:
		with open(os.path.join(root or audioRoot(), name + "_choices")) as f:
			return f.read().split()
	except (IOError, OSError):
		return []


def writeAudioChoice(name, value, root=None):
	"""scrie `value` in /proc/stb/audio/<name> numai daca e in lista driverului; True daca scrierea a mers"""
	choices = AUDIO_CHOICES.get(name) or []
	if value not in choices:
		print("[AVSwitch] %s: %s is not in %s_choices (%s), nothing written" % (name, value, name, " ".join(choices)))
		return False
	path = os.path.join(root or audioRoot(), name)
	try:
		with open(path, "w") as f:
			f.write(value)
	except (IOError, OSError) as err:
		print("[AVSwitch] writing %s to %s failed: %s" % (value, path, err))
		return False
	print("[AVSwitch] %s = %s" % (path, value))
	return True


def toggleAC3Downmix():
	"""tasta AUDIO tinuta: comuta AC3 downmix; se si salveaza, ca
	randul din ecranul tastei AUDIO. Intoarce noua valoare (True = downmix) sau None cand receptorul nu are comutatorul
	sau cand scrierea in driver nu a mers (intai se scrie, apoi se schimba setarea;
	altfel mesajul barei anunta o schimbare pe care driverul nu a primit-o, iar setarea salvata nu mai spune adevarul).
	O singura scriere in /proc/stb/audio/ac3 la o apasare: schimbarea setarii nu mai trece si prin notificatorul din
	InitAVSwitch (inainte se scria de doua ori aceeasi valoare, iar showiframe poate reactiona la fiecare scriere).
	Pe „Ieșirea sunetului: Automat” se comuta fata de ce face acum driverul, iar iesirea trece pe Manual (tasta e o
	alegere de mana)."""
	if not SystemInfo.get("CanDownmixAC3"):
		return None
	element = config.av.downmix_ac3
	downmix = not _downmixEfectiv("ac3", element)
	if not writeAudioChoice("ac3", downmix and "downmix" or "passthrough"):
		return None
	AUDIO_WRITTEN_BY_KEY.add("ac3")
	try:
		element.value = downmix
	finally:
		AUDIO_WRITTEN_BY_KEY.discard("ac3")
	element.save()
	sunet = _hdsSunet()
	if sunet is not None:
		try:
			sunet.treciPeManual()
		except Exception as err:
			print("[AVSwitch] iesirea sunetului: %s" % err)
	return downmix

class AVSwitch:
	def setInput(self, input):
		INPUT = { "ENCODER": 0, "SCART": 1, "AUX": 2 }
		eAVSwitch.getInstance().setInput(INPUT[input])

	def setColorFormat(self, value):
		eAVSwitch.getInstance().setColorFormat(value)

	def setAspectRatio(self, value):
		eAVSwitch.getInstance().setAspectRatio(value)

	def setSystem(self, value):
		eAVSwitch.getInstance().setVideomode(value)

	def getOutputAspect(self):
		valstr = config.av.aspectratio.value
		if valstr in ("4_3_letterbox", "4_3_panscan"): # 4:3
			return (4,3)
		elif valstr == "16_9": # auto ... 4:3 or 16:9
			try:
				aspect_str = open("/proc/stb/vmpeg/0/aspect", "r").read()
				if aspect_str == "1": # 4:3
					return (4,3)
			except IOError:
				pass
		elif valstr in ("16_9_always", "16_9_letterbox"): # 16:9
			pass
		elif valstr in ("16_10_letterbox", "16_10_panscan"): # 16:10
			return (16,10)
		return (16,9)

	def getFramebufferScale(self):
		aspect = self.getOutputAspect()
		fb_size = getDesktop(0).size()
		return (aspect[0] * fb_size.height(), aspect[1] * fb_size.width())

	def getAspectRatioSetting(self):
		valstr = config.av.aspectratio.value
		if valstr == "4_3_letterbox":
			val = 0
		elif valstr == "4_3_panscan":
			val = 1
		elif valstr == "16_9":
			val = 2
		elif valstr == "16_9_always":
			val = 3
		elif valstr == "16_10_letterbox":
			val = 4
		elif valstr == "16_10_panscan":
			val = 5
		elif valstr == "16_9_letterbox":
			val = 6
		return val

	def setAspectWSS(self, aspect=None):
		if not config.av.wss.value:
			value = 2 # auto(4:3_off)
		else:
			value = 1 # auto
		eAVSwitch.getInstance().setWSS(value)

def InitAVSwitch():
	config.av = ConfigSubsection()
	config.av.yuvenabled = ConfigBoolean(default=False)
	colorformat_choices = {"cvbs": _("CVBS"), "rgb": _("RGB"), "svideo": _("S-Video")}
	
	# when YUV is not enabled, don't let the user select it
	if config.av.yuvenabled.value:
		colorformat_choices["yuv"] = _("YPbPr")

	config.av.colorformat = ConfigSelection(choices=colorformat_choices, default="rgb")
	# implicit 16:9 (televizor lat), nu 4:3 Letterbox (cu 4:3 /proc/stb/video/aspect ramanea 4:3 pe un televizor lat).
	# "16_9_always" scrie aspect "16:9" si policy "panscan" (lib/driver/avswitch.cpp); pe aceste drivere HiSilicon
	# "panscan" arata emisiunile 4:3 cu benzi negre in lateral, nedeformate (driverul inverseaza numele: panscan face
	# de fapt pillarbox), iar "letterbox" le-ar taia sus si jos. "16_9" ar scrie aspect "any", netestat pe HiSilicon. O alegere salvata
	# de utilizator ramane (4:3 Letterbox, fostul implicit, nu se salva, deci nu exista in setari).
	config.av.aspectratio = ConfigSelection(choices={
			"4_3_letterbox": _("4:3 Letterbox"),
			"4_3_panscan": _("4:3 PanScan"), 
			"16_9": _("16:9"), 
			"16_9_always": _("16:9 always"),
			"16_10_letterbox": _("16:10 Letterbox"),
			"16_10_panscan": _("16:10 PanScan"), 
			"16_9_letterbox": _("16:9 Letterbox")},
			default = "16_9_always")

	config.av.aspect = ConfigSelection(choices={
			"4_3": _("4:3"),
			"16_9": _("16:9"), 
			"16_10": _("16:10"),
			"auto": _("Automatic")},
			default = "auto")
	config.av.policy_169 = ConfigSelection(choices={
				# TRANSLATORS: (aspect ratio policy: black bars on top/bottom) in doubt, keep english term.
			"letterbox": _("Letterbox"), 
				# TRANSLATORS: (aspect ratio policy: cropped content on left/right) in doubt, keep english term
			"panscan": _("Pan&Scan"),  
				# TRANSLATORS: (aspect ratio policy: display as fullscreen, even if this breaks the aspect)
			"scale": _("Just Scale")},
			default = "letterbox")
	config.av.policy_43 = ConfigSelection(choices={
				# TRANSLATORS: (aspect ratio policy: black bars on left/right) in doubt, keep english term.
			"pillarbox": _("Pillarbox"), 
				# TRANSLATORS: (aspect ratio policy: cropped content on left/right) in doubt, keep english term
			"panscan": _("Pan&Scan"),  
				# TRANSLATORS: (aspect ratio policy: display as fullscreen, with stretching the left/right)
			"nonlinear": _("Nonlinear"),  
				# TRANSLATORS: (aspect ratio policy: display as fullscreen, even if this breaks the aspect)
			"scale": _("Just Scale")},
			default = "pillarbox")
	config.av.tvsystem = ConfigSelection(choices = {"pal": _("PAL"), "ntsc": _("NTSC"), "multinorm": _("multinorm")}, default="pal")
	config.av.wss = ConfigEnableDisable(default = True)
	config.av.defaultac3 = ConfigYesNo(default = False)
	config.av.generalAC3delay = ConfigSelectionNumber(-1000, 1000, 25, default = 0)
	config.av.generalPCMdelay = ConfigSelectionNumber(-1000, 1000, 25, default = 0)
	config.av.vcrswitch = ConfigEnableDisable(default = False)

	iAVSwitch = AVSwitch()

	def setColorFormat(configElement):
		map = {"cvbs": 0, "rgb": 1, "svideo": 2, "yuv": 3}
		iAVSwitch.setColorFormat(map[configElement.value])

	def setAspectRatio(configElement):
		map = {"4_3_letterbox": 0, "4_3_panscan": 1, "16_9": 2, "16_9_always": 3, "16_10_letterbox": 4, "16_10_panscan": 5, "16_9_letterbox" : 6}
		iAVSwitch.setAspectRatio(map[configElement.value])

	def setSystem(configElement):
		map = {"pal": 0, "ntsc": 1, "multinorm" : 2}
		iAVSwitch.setSystem(map[configElement.value])

	def setWSS(configElement):
		iAVSwitch.setAspectWSS()

	# this will call the "setup-val" initial
	config.av.colorformat.addNotifier(setColorFormat)
	config.av.aspectratio.addNotifier(setAspectRatio)
	# HD drivers list their modes; writing "pal" there at every start would force 576i50 (Video setup handles them)
	if not os_path.exists("/proc/stb/video/videomode_choices"):
		config.av.tvsystem.addNotifier(setSystem)
	# randurile din Setari A/V care nu pot schimba nimic pe acest receptor se ascund (data/setup.xml, requires=):
	# „TV System” cand driverul isi listeaza modurile (notificatorul de mai sus nu se pune), „Color Format” fara
	# /proc/stb/avs/0/colorformat (lib/driver/avswitch.cpp scrie numai acolo; pe u57 lipseste tot /proc/stb/avs).
	# WSS ramane: /proc/stb/denc/0/wss exista pentru iesirea analogica (CVBS).
	SystemInfo["HdsSistemTv"] = not os_path.exists("/proc/stb/video/videomode_choices")
	SystemInfo["HdsFormatCuloareAnalog"] = os_path.exists("/proc/stb/avs/0/colorformat")
	config.av.wss.addNotifier(setWSS)

	iAVSwitch.setInput("ENCODER") # init on startup
	SystemInfo["ScartSwitch"] = eAVSwitch.getInstance().haveScartSwitch()

	# sunetul (vezi comentariul de la inceputul fisierului); cheile SystemInfo exista mereu, True sau False
	root = audioRoot()
	for name in ("ac3", "dts"):
		AUDIO_CHOICES[name] = readAudioChoices(name, root)

	# „Ieșirea sunetului” se face inaintea randurilor AC3 / DTS: notificatorii lor o citesc chiar la prima chemare
	# (pe Automat nu scriu valoarea randului la pornire; o scrie HdsSunet.porneste, o singura data)
	sunet = _hdsSunet()
	if sunet is not None:
		try:
			sunet.initConfig()
		except Exception as err:
			print("[AVSwitch] iesirea sunetului: %s" % err)
			sunet = None

	can_downmix = "downmix" in AUDIO_CHOICES["ac3"]
	SystemInfo["CanDownmixAC3"] = can_downmix
	if can_downmix:
		def setAC3Downmix(configElement):
			if "ac3" in AUDIO_WRITTEN_BY_KEY:
				return      # tasta AUDIO tinuta a scris deja valoarea (toggleAC3Downmix)
			if _scrieDinRand("ac3", configElement):
				writeAudioChoice("ac3", configElement.value and "downmix" or "passthrough")
		config.av.downmix_ac3 = ConfigYesNo(default = True)
		config.av.downmix_ac3.addNotifier(setAC3Downmix)

	# DTS: pe receptor /proc/stb/audio/dts ramanea gol sub HDSatelit; televizorul de proba nu stie DTS, deci implicitul
	# (downmix, stereo) e singurul cu sunet acolo
	can_downmix_dts = "downmix" in AUDIO_CHOICES["dts"]
	SystemInfo["CanDownmixDTS"] = can_downmix_dts
	if can_downmix_dts:
		def setDTSDownmix(configElement):
			if _scrieDinRand("dts", configElement):
				writeAudioChoice("dts", configElement.value and "downmix" or "passthrough")
		config.av.downmix_dts = ConfigYesNo(default = True)
		config.av.downmix_dts.addNotifier(setDTSDownmix)

	if sunet is not None:
		try:
			sunet.porneste()
		except Exception as err:
			print("[AVSwitch] iesirea sunetului: %s" % err)

	# volumul si intarzierea sunetului (Components/HdsSetariSunet.py): pasul volumului, volumul pe canal, volumul egal
	# (AVC) si intarzierea pe HDMI si pe optic, prin placa de sunet; dupa iesirea sunetului, ale carei schimbari le asculta
	try:
		from Components import HdsSetariSunet
		HdsSetariSunet.initConfig()
		HdsSetariSunet.porneste()
	except Exception as err:
		print("[AVSwitch] volumul si intarzierea sunetului: %s" % err)

	# intarzierile generale se scriu din C++ (lib/dvb/decoder.cpp, setHwAC3Delay / setHwPCMDelay) la pornirea canalului
	SystemInfo["CanAC3Delay"] = os_path.exists(os.path.join(root, "audio_delay_bitstream"))
	SystemInfo["CanPCMDelay"] = os_path.exists(os.path.join(root, "audio_delay_pcm"))

	try:
		can_osd_alpha = open("/proc/stb/video/alpha", "r") and True or False
	except:
		can_osd_alpha = False

	SystemInfo["CanChangeOsdAlpha"] = can_osd_alpha

	def setAlpha(config):
		open("/proc/stb/video/alpha", "w").write(str(config.value))

	if can_osd_alpha:
		config.av.osd_alpha = ConfigSlider(default=255, limits=(0,255))
		config.av.osd_alpha.addNotifier(setAlpha)

	# HDSatelit: config.av.scaler_sharpness era deja scris mai jos, complet functional
	# (verificat REAL pe receptorul fizic: /proc/stb/vmpeg/0/pep_scaler_sharpness exista pe u57), dar
	# nu avea niciun "requires" in SystemInfo, deci setup.xml nu putea sa-l arate userului -- cod mort,
	# Reparat aici, la sursa flag-ului.
	SystemInfo["CanScalerSharpness"] = os_path.exists("/proc/stb/vmpeg/0/pep_scaler_sharpness")
	if os_path.exists("/proc/stb/vmpeg/0/pep_scaler_sharpness"):
		def setScaler_sharpness(config):
			myval = int(config.value)
			try:
				print("--> setting scaler_sharpness to: %0.8X" % myval)
				open("/proc/stb/vmpeg/0/pep_scaler_sharpness", "w").write("%0.8X" % myval)
				open("/proc/stb/vmpeg/0/pep_apply", "w").write("1")
			except IOError:
				print("couldn't write pep_scaler_sharpness")

		config.av.scaler_sharpness = ConfigSlider(default=13, limits=(0,26))
		config.av.scaler_sharpness.addNotifier(setScaler_sharpness)
	else:
		config.av.scaler_sharpness = NoSave(ConfigNothing())

