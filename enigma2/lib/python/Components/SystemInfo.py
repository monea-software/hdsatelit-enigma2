# Modificat de moneasoftware.com si hdsatelit.com, 2026
import os

try:
	from enigma import eDVBResourceManager
	_can_measure = eDVBResourceManager.getInstance().canMeasureFrontendInputPower()
except Exception:
	_can_measure = False

from Tools.Directories import fileExists, resolveFilename, SCOPE_PLUGINS
from Tools.HardwareInfo import HardwareInfo, getModelName

SystemInfo = { }

#FIXMEE...
def getNumVideoDecoders():
	idx = 0
	while fileExists("/dev/dvb/adapter0/video%d"%(idx), 'f'):
		idx += 1
	return idx

SystemInfo["NumVideoDecoders"] = getNumVideoDecoders()
SystemInfo["CanMeasureFrontendInputPower"] = _can_measure


def countFrontpanelLEDs():
	leds = 0
	if fileExists("/proc/stb/fp/led_set_pattern"):
		leds += 1

	while fileExists("/proc/stb/fp/led%d_pattern" % leds):
		leds += 1

	return leds

SystemInfo["NumFrontpanelLEDs"] = countFrontpanelLEDs()
SystemInfo["FrontpanelDisplay"] = fileExists("/dev/dbox/oled0") or fileExists("/dev/dbox/lcd0")
SystemInfo["FrontpanelDisplayGrayscale"] = fileExists("/dev/dbox/oled0")
# Pluginurile pot intreba inainte de InitLcd. Citim instanta deja creata de
# Enigma2; detectia nu deschide din Python un alt dispozitiv.
try:
	from enigma import eDBoxLCD
	_afisaj_nativ = eDBoxLCD.getInstance()
	SystemInfo["Display"] = bool(_afisaj_nativ is not None and _afisaj_nativ.detected())
except Exception:
	SystemInfo["Display"] = False
SystemInfo["DeepstandbySupport"] = HardwareInfo().get_device_name() != "dm800"
# Functiile producatorului apar numai cu pachetul pus in imaginea modelului.
def _functieImagine(nume):
	try:
		from Components.HdsFunctiiImagine import disponibil
		return disponibil(nume)
	except Exception as eroare:
		print("[SystemInfo] HdsFunctiiImagine (%s): %r" % (nume, eroare))
		return False


SystemInfo["HdsVfdProducator"] = _functieImagine("afisaj")
SystemInfo["HdsCodTelecomanda"] = _functieImagine("telecomanda")
# Receptoarele imaginii nu au codor H.265. Decodarea H.265 nu inseamna codare.
SystemInfo["HasH265Encoder"] = False


try:
	_device_name = getModelName()
except Exception:
	_device_name = ""

SystemInfo["model"] = _device_name or "viper4k"
SystemInfo["boxtype"] = _device_name or "viper4k"

# Marca/model/familie SoC/kernel de afisare (inainte scrise fix "Amiko"/"Viper 4K"/"hisilicon"/
# "4.4.35", neconditionat -- pe un al doilea receptor, cu alta marca/SoC/arhitectura, ar fi aratat gresit
# peste tot unde aceste chei SystemInfo sunt citite, inclusiv SystemInfo["ArchIsARM"], folosit de cod
# stock Enigma2 pentru logica UI conditionata de arhitectura (ARM vs MIPS). Detectie reala, acelasi tipar
# deja folosit la HdsStartWizard/BoxInfo (Components.About, about.getReceiverName()/getChipset()) --
# fara import circular, About.py nu importa SystemInfo.
try:
	from Components.About import about as _about
	_marca = _about.getBrand()
	_modelul = _about.getModel()
	_chipset_text = _about.getChipset() or ""
	_kernel_text = _about.getKernelVersionString()
	# numele de constructie din regulile modelului (/etc/hdsatelit-model), rezerva cand driverul nu da un nume
	_about_mb = _about.valoareDinReguli("machinebuild")
except Exception:
	_marca = ""
	_modelul = ""
	_chipset_text = ""
	_kernel_text = ""
	_about_mb = ""

SystemInfo["brand"] = _marca
SystemInfo["displaybrand"] = _marca or "HD Satelit"
SystemInfo["displaymodel"] = _modelul or "HD Satelit"
SystemInfo["distro"] = "hdsatelit"
SystemInfo["displaydistro"] = "HD Satelit"
SystemInfo["displaytype"] = ""
# masina pentru pluginuri (machinebuild, model, boxtype): intai cea din regulile imaginii (/etc/hdsatelit-model:
# viper4kv20, viper4kv30, viper4kv40...), fiindca driverul placii scrie in /proc/stb/info/model un nume vechi de
# Dreambox ("dm8000"), iar un plugin ar crede ca ruleaza pe alt receptor.
# Numele brut din HardwareInfo ramane pentru consumatorii hardware.
SystemInfo["machinebuild"] = _device_name or _about_mb or "unknown"
SystemInfo["model"] = SystemInfo["machinebuild"]
SystemInfo["boxtype"] = SystemInfo["machinebuild"]
SystemInfo["socfamily"] = "hisilicon" if "hisilicon" in _chipset_text.lower() else ""
try:
	_arhitectura = os.uname().machine.lower()
except Exception:
	_arhitectura = ""
SystemInfo["architecture"] = _arhitectura
SystemInfo["ArchIsARM"] = int(_arhitectura.startswith(("arm", "aarch64")))
# versiunea bazei de constructie, pentru pluginurile care o arata (interfetele web straine: „OE version”). Era scris fix
# un nume strain cu versiunea 5.5, gresita: imaginea e construita pe baza 6.0 de la 0.7.0. Daca
# /usr/lib/enigma.info are vreodata oe=, valoarea de acolo are intaietate.
SystemInfo["oe"] = "6.0"
try:
	with open("/usr/lib/enigma.info") as _f:
		for _rand in _f:
			if _rand.startswith("oe="):
				_oe = _rand.split("=", 1)[1].strip().strip("'\"")
				if _oe:
					SystemInfo["oe"] = _oe
except (IOError, OSError):
	pass
# versiunea imaginii din /etc/image-version ("0.6.7"), aceeasi ca in Despre; fara numar de constructie separat, ca
# pluginurile care le lipesc ("versiune.constructie") sa arate numai versiunea
try:
	_versiune_imagine = _about.getImageVersionString().split(" ")[0]
except Exception:
	_versiune_imagine = ""
SystemInfo["imageversion"] = _versiune_imagine if _versiune_imagine[:1].isdigit() else ""
SystemInfo["imagebuild"] = ""
SystemInfo["driversdate"] = "2026-09-16"
SystemInfo["kernel"] = _kernel_text or "unknown"

# 0.2.6: panoul skinului HDSatelit (pachetul hdsatelit-skin,
# Plugins/Extensions/HdsSkinSetari) are intrarea lui in Setari > Interfata si aspect (data/menu.xml,
# requires="HdsSkinSetari"); fara pachetul skinului intrarea nu se vede, in loc sa cada la deschidere
SystemInfo["HdsSkinSetari"] = fileExists(resolveFilename(SCOPE_PLUGINS, "Extensions/HdsSkinSetari/ecrane.py"))
# 0.3.2: SystemInfo["HdsSubtitleDownloader"] scos: descarcarea subtitrarilor e in imagine (Components/HdsSubtitrariInternet),
# intrarea hds_descarcare_subtitrari din data/menu.xml nu mai are requires
# VPN-ul (Components/HdsVpn.py) numai cu programele lui in imagine (openvpn sau wg, din 0.4.0; aceleasi cai ca
# HdsVpn.PROGRAM_OPENVPN si HdsVpn.PROGRAM_WG, aceeasi regula ca HdsVpn.disponibil()): fara ele intrarea din meniu
# (data/menu.xml, requires="HdsVpn"), pagina web /vpn, pornirea din mytest.py si prefixul navigatorului lipsesc, iar
# modulul nici nu se incarca
SystemInfo["HdsVpn"] = os.access("/usr/sbin/openvpn", os.X_OK) or os.access("/usr/bin/wg", os.X_OK)
# inregistrarile "Decodează mai târziu" (Components/HdsDecodare.py) numai cu programul de decodare pe receptor (aceeasi
# cale ca HdsDecodare.CALE_PROGRAM): fara el randurile din setup.xml (requires="HdsDecodare") si din /setari lipsesc
SystemInfo["HdsDecodare"] = os.access("/usr/bin/hds-decodare", os.X_OK)
# Radio DAB+ prin USB (data/menu.xml, requires="HdsDabUsb"; 10.11.2026, 0.7.3): randul si pagina din meniul web numai cu
# pluginul DabTerestru instalat (aceeasi cale ca Components/HdsDabUsb.PLUGIN). Pachetele lui nu sunt inca in feed, deci
# randul nu mai duce la un ecran care nu are ce instala; conditia se scoate cand pachetele sunt in feed si probate.
SystemInfo["HdsDabUsb"] = os.path.isfile("/usr/lib/enigma2/python/Plugins/Extensions/DabTerestru/plugin.py") or os.path.isfile("/usr/lib/enigma2/python/Plugins/Extensions/DabTerestru/plugin.pyc")
# Lista imaginilor din meniul de oprire: bootoptions sau kexec deja instalat.
# Aceeasi capacitate arata lista si in interfata web.
try:
	from Components import HdsPornireMultipla as _pornireMultipla
	SystemInfo["HdsMultiboot"] = _pornireMultipla.disponibil()
except Exception as _e:
	print("[SystemInfo] HdsMultiboot: %r" % (_e,))
	SystemInfo["HdsMultiboot"] = False


class BoxInfoClass:
	def getItem(self, key, default=None):
		val = SystemInfo.get(key)
		if val is not None:
			return val
		if default is not None:
			return default
		if key == "ArchIsARM":
			return 1
		if key in ("model", "displaytype", "boxtype", "brand", "displaybrand", "displaymodel", "machinebuild", "socfamily", "distro", "displaydistro", "oe", "imageversion", "imagebuild", "driversdate", "kernel"):
			return ""
		return default


	def get(self, key, default=None):
		return self.getItem(key, default)

	def setItem(self, key, value):
		SystemInfo[key] = value

	def keys(self):
		return SystemInfo.keys()

	def items(self):
		return SystemInfo.items()

	def __getitem__(self, key):
		return self.getItem(key)

	def __contains__(self, key):
		return key in SystemInfo


BoxInfo = BoxInfoClass()

# numele cerute de pluginuri
def getBoxDisplayName():
	return (BoxInfo.getItem("displaybrand") or BoxInfo.getItem("brand") or "", BoxInfo.getItem("displaymodel") or BoxInfo.getItem("model") or "")


def getBoxType():
	return BoxInfo.getItem("model") or ""


def getMachineName():
	return BoxInfo.getItem("displaymodel") or BoxInfo.getItem("model") or ""


MODEL = BoxInfo.getItem("model")
DISPLAYBRAND = BoxInfo.getItem("displaybrand") or BoxInfo.getItem("brand") or ""

# Tipul imaginii este acelasi pe care il arata pagina Despre.
try:
	IMAGETYPE = _about.getImageTypeString()
except (AttributeError, NameError):
	IMAGETYPE = ""
SystemInfo.setdefault("imagetype", IMAGETYPE)


# ---------------------------------------------------------------------------------------------------------------------
# Compatibilitatea cu pluginurile si skin-urile scrise pentru celelalte imagini Enigma2 (OEA4, 11.11.2026). Numai ADAUGA:
# o cheie care are deja o valoare mai sus ramane neschimbata (proba teste/test_systeminfo_boxinfo_oea_074.py compara
# dict-ul de dinainte de bloc cu cel de dupa). Pluginurile citesc SystemInfo["Cheie"] fara paza, deci o cheie lipsa le
# opreste cu KeyError; aici primesc valoarea placii sau, unde imaginea nu are functia, False.
# /usr/lib/enigma.info ramane intentionat mic (hdsatelit-image.bb), deci cheile placii vin din Components/HdsBoxInfoModele.py
# (generat din conf-urile masinilor) si din ce se vede pe receptor (/proc, /dev, /etc/init.d).
def _oeaFisier(cale):
	return os.path.isfile(cale)


def _oeaAcces(cale):
	try:
		return os.access(cale, os.R_OK)
	except Exception:
		return False


def _oeaRand(cale, implicit=""):
	try:
		with open(cale) as f:
			return f.readline().strip()
	except Exception:
		return implicit


def _oeaPune(cheie, valoare):
	"""Pune cheia numai cand lipseste sau e goala ("" sau None); False/0 puse de noi raman."""
	if SystemInfo.get(cheie) in (None, ""):
		SystemInfo[cheie] = valoare


def _oeaPlugin(nume):
	for fel in ("Extensions", "SystemPlugins"):
		for ext in (".py", ".pyc"):
			if os.path.isfile("/usr/lib/enigma2/python/Plugins/%s/%s/plugin%s" % (fel, nume, ext)):
				return True
	return False


_oeaChei = set(SystemInfo.keys())  # cheile noastre, de dinainte de strat

# 1. Fisierele de informatii standard (/usr/lib/enigma.info, /usr/lib/enigma.conf): cheile lor numai unde lipsesc.
_oeaInfo, _oeaConf = [], []
for _cale, _lista in (("/usr/lib/enigma.info", _oeaInfo), ("/usr/lib/enigma.conf", _oeaConf)):
	try:
		with open(_cale) as _f:
			_randuri = [_r.rstrip("\n") for _r in _f]
	except (IOError, OSError):
		continue
	if _lista is _oeaInfo:
		_date = [_r for _r in _randuri if not _r.startswith("checksum")]
		_suma = [_r.split("=", 1)[1].strip() for _r in _randuri if _r.startswith("checksum") and "=" in _r]
		try:
			import hashlib as _hashlib
			SystemInfo.setdefault("checksumerror", not _suma or _hashlib.md5(("\n".join(_date + [""])).encode("utf-8", "ignore")).hexdigest() != _suma[0])
		except Exception:
			pass
	for _r in _randuri:
		if _r.startswith(("#", "checksum")) or "=" not in _r:
			continue
		_k, _v = (_x.strip() for _x in _r.split("=", 1))
		if not _k:
			continue
		_lista.append(_k)
		try:
			from ast import literal_eval as _literal
			_v = _literal(_v)
		except Exception:
			pass
		if _lista is _oeaConf and _k not in _oeaChei:
			SystemInfo[_k] = _v  # enigma.conf = suprascrierea omului, ca in celelalte imagini Enigma2; numai peste cheile stratului
		else:
			_oeaPune(_k, _v)
_oeaInfo.sort()
_oeaConf.sort()
SystemInfo.setdefault("checksumerror", False)
SystemInfo.setdefault("overrideactive", bool(_oeaConf))

# 2. Valorile placii (platform, mediaservice, rcname, displaytype, mtd*, kernelfile, hdmi, ci...) pe machinebuild.
try:
	from Components.HdsBoxInfoModele import valori as _valoriPlaca
	for _k, _v in _valoriPlaca(SystemInfo.get("machinebuild")).items():
		if _k != "machine_features":
			_oeaPune(_k, _v)
except Exception as _e:
	print("[SystemInfo] HdsBoxInfoModele: %r" % (_e,))

# 3. Numele imaginii in forma standard: tot ale noastre.
_oeaPune("imgversion", SystemInfo.get("imageversion", ""))
_oeaPune("developername", SystemInfo.get("distro", ""))
_oeaPune("imglanguage", "multilang")
try:
	import sys as _sys
	_oeaPune("python", "%d.%d" % _sys.version_info[:2])
except Exception:
	pass
for _k, _v in (("hdmi", False), ("yuv", False), ("rca", False), ("avjack", False), ("scart", False), ("scartyuv", False),
		("noscartswitch", False), ("dvi", False), ("svideo", False), ("minitv", False), ("hdmihdin", False), ("hdmifhdin", False),
		("wol", False), ("wwol", False), ("ci", False), ("transcoding", False), ("multitranscoding", False), ("fhdskin", True),
		("wqhdskin", False), ("e2egl", False), ("smallflash", False), ("middleflash", False), ("multilib", False),
		("vfdsymbol", False), ("kexecmb", False), ("chkrootmb", False), ("hasUBIMB", False), ("dboxlcd", False),
		("singlecore", False), ("rctype", 0), ("rcidnum", 2), ("hdmistandbymode", 0), ("timerwakeupmode", 0)):
	SystemInfo.setdefault(_k, _v)  # emulatorul si un receptor necunoscut: valorile implicite standard
SystemInfo.setdefault("platform", SystemInfo.get("model", ""))
SystemInfo.setdefault("mediaservice", "servicegstreamer")
SystemInfo.setdefault("rcname", "")
# OE-Alliance (OEA10): numele modelului telecomenzii (dosarul pozei ei) sub numele cerut de RemoteControlSelection si de alte pluginuri
SystemInfo.setdefault("rc_model", SystemInfo.get("rcname") or "dmm1")
SystemInfo.setdefault("mtdblack", "mtd")
SystemInfo.setdefault("compiledate", "")
for _k in ("mtdkernel", "mtdrootfs", "mtdbootfs", "kernelfile", "rootfile", "imagedir", "imagefs", "mkubifs", "ubinize", "fpu", "blindscanbinary"):
	SystemInfo.setdefault(_k, "")


# 4. Functiile de modul cerute de pluginuri (aceleasi nume si valori intoarse ca in celelalte imagini Enigma2; codul e al nostru).
SOFTCAM = "/etc/init.d/softcam"
NOEMU = "/etc/enigma2/noemu"
DEGREE = "°"


def getBoxName():
	"""Numele scurt al receptorului folosit de pluginuri la cautari (familia, unde mai multe modele au aceeasi placa)."""
	nume = SystemInfo.get("machinebuild") or ""
	for familie in ("sf8008m", "sf8008", "ustym4kpro"):
		if nume.startswith(familie):
			return familie
	return nume


def getChipsetString():
	cip = _oeaRand("/proc/stb/info/chipset", "")
	if not cip:
		return "Undefined"
	return cip.lower().replace("brcm", "").replace("bcm", "").replace("sti", "")


def getKernelVersion():
	return SystemInfo.get("kernel", "")


def getDemodVersion():
	return _oeaRand("/proc/stb/info/nim_firmware_version", "") or None


def getRCFile(ext):
	baza = "/usr/share/enigma2/hardware/"
	cale = baza + "%s.%s" % (SystemInfo.get("rcname") or "dmm1", ext)
	return cale if os.path.isfile(cale) else baza + "dmm1.%s" % ext


def _listaInit():
	try:
		return os.listdir("/etc/init.d")
	except OSError:
		return []


def hasInitCam():
	return any(x.startswith("softcam.") and not x.endswith("None") for x in _listaInit())


def hasInitCardServer():
	return any(x.startswith("cardserver.") and not x.endswith("None") for x in _listaInit())


def hasSoftcamEmu():
	if os.path.isfile(NOEMU):
		return False
	try:
		return any(x.endswith(".emu") for x in os.listdir("/etc"))
	except OSError:
		return False


def hasSoftcam():
	if os.path.isfile(NOEMU):
		return False
	return any(x.startswith(("softcam.", "cardserver.")) and not x.endswith("None") for x in _listaInit())


def getCurrentSoftcam():
	try:
		return os.readlink(SOFTCAM).replace("softcam.", "") if os.path.islink(SOFTCAM) else "None"
	except OSError:
		return "None"


def getSysSoftcam():
	cam = os.path.basename(getCurrentSoftcam()).lower()
	for nume in ("oscam", "ncam", "cccam"):
		if cam.startswith(nume):
			return nume
	return ""


def getSoftcams():
	cams = sorted(x.replace("softcam.", "") for x in _listaInit() if x.startswith("softcam."))
	if "None" in cams:
		cams.remove("None")
		cams.insert(0, "None")
	return cams


def updateSysSoftCam():
	SystemInfo["ShowOscamInfo"] = getSysSoftcam() in ("oscam", "ncam")
	SystemInfo["ShowCCCamInfo"] = getSysSoftcam() == "cccam"
	SystemInfo["HasSoftcamEmu"] = hasSoftcamEmu()
	SystemInfo["Softcams"] = getSoftcams()
	SystemInfo["CurrentSoftcam"] = getCurrentSoftcam()


def getWakeOnLANType(fisier):
	valoare = _oeaRand(fisier, "") if fisier else ""
	for perechi in (("off", "on"), ("0", "1")):
		if valoare in perechi:
			return perechi
	return ("disable", "enable")


class VideoCodec:
	"""Numele codecului dupa tipul fluxului video (iServiceInformation.sVideoType)."""
	NAMES = ("MPEG2", "AVC", "H263", "VC1", "MPEG4-VC", "VC1-SM", "MPEG1", "HEVC", "VP8", "VP9", "XVID", "N/A 11", "N/A 12",
		"DIVX 3.11", "DIVX 4", "DIVX 5", "AVS", "N/A 17", "VP6", "N/A 19", "N/A 20", "SPARK")
	EXTRA_NAMES = {40: "AVS2"}

	@staticmethod
	def getName(videoType, default="N/A"):
		return VideoCodec.NAMES[videoType] if 0 <= videoType < len(VideoCodec.NAMES) else VideoCodec.EXTRA_NAMES.get(videoType, default)


# 5. Cheile vazute pe receptor (/proc/stb, /dev, pluginuri, servicii). Fara citiri pe /proc/stb/video/zapmode (SF8008).
try:
	from enigma import eGetEnigmaDebugLvl as _nivel
	_nivelJurnal = int(_nivel())
except Exception:
	_nivelJurnal = 0
try:
	from enigma import eDVBCIInterfaces as _ci
	_sloturiCi = int(_ci.getInstance().getNumOfSlots())
except Exception:
	try:
		_sloturiCi = len([x for x in os.listdir("/dev") if x.startswith("ci") and x[2:].isdigit()])
	except OSError:
		_sloturiCi = 0
try:
	from enigma import eDVBCSAEngine as _csa
	_softCsa = bool(_csa.isAvailable())
except Exception:
	_softCsa = False
_cmdline = _oeaRand("/proc/cmdline", "")
_arh = SystemInfo.get("architecture") or ""
_soc = SystemInfo.get("socfamily") or ""
_tipAfisaj = SystemInfo.get("displaytype") or ""
_mb = SystemInfo.get("machinebuild") or ""
_multiboot = bool(SystemInfo.get("HdsMultiboot"))
_afisajFata = bool(SystemInfo.get("FrontpanelDisplay"))
try:
	_bpp = int(_oeaRand("/proc/stb/lcd/bpp", "0") or "0", 16)
except ValueError:
	_bpp = 0
for _k, _v in (
	("DebugLevel", _nivelJurnal),
	("InDebugMode", _nivelJurnal >= 4),
	("KernelVersion", SystemInfo.get("kernel", "")),
	("RemoteEnable", False),
	("RemoteRepeat", 100),
	("RemoteDelay", 700),
	("HDMI-PreEmphasis", _oeaFisier("/proc/stb/hdmi/preemphasis")),
	("12V_Output", False),
	("3DMode", _oeaAcces("/proc/stb/fb/3dmode") or _oeaAcces("/proc/stb/fb/primary/3d")),
	("3DZNorm", _oeaAcces("/proc/stb/fb/znorm") or _oeaAcces("/proc/stb/fb/primary/zoffset")),
	("7segment", _tipAfisaj == "7segment"),
	("AmlogicFamily", _soc.startswith(("aml", "meson")) or os.path.exists("/proc/device-tree/amlogic-dt-id")),
	("ArchIsARM64", _arh == "aarch64" or "64" in _arh),
	("Blindscan", _oeaPlugin("Blindscan")),
	("Satfinder", _oeaPlugin("Satfinder")),
	("BoxName", getBoxName()),
	("canMultiBoot", _multiboot),
	("HasNewNativeMultiboot", os.path.exists("/.newMB")),
	("HasKexecMultiboot", "kexec=1" in _cmdline),
	("cankexec", False),
	("HasChkrootMultiboot", False),
	("canchkroot", False),
	("CanNotDoSimultaneousTranscodeAndPIP", _mb in ("vusolo4k",)),
	("canRecovery", ("usb_update.bin", "none") if _mb in ("sf8008", "sf8008m", "ustym4kpro", "viper4k", "gbtrio4k") else False),
	("CanUse3DModeChoices", _oeaFisier("/proc/stb/fb/3dmode_choices")),
	("ChipsetString", getChipsetString()),
	("CIPlusHelper", os.path.exists("/usr/bin/ciplushelper")),
	("DefaultDisplayBrightness", 5),
	("DNSCrypt", _oeaFisier("/usr/bin/dnscrypt-proxy")),
	("FBLCDDisplay", _oeaAcces("/proc/stb/fb/sd_detach")),
	("Fan", _oeaAcces("/proc/stb/fp/fan")),
	("ForceLNBPowerChanged", _oeaAcces("/proc/stb/frontend/fbc/force_lnbon")),
	("ForceToneBurstChanged", _oeaAcces("/proc/stb/frontend/fbc/force_toneburst")),
	("GBWOL", _oeaFisier("/usr/bin/gigablue_wol")),
	("grautec", _oeaFisier("/tmp/usbtft")),
	("GraphicLCD", False),
	("HasExternalPIP", _oeaAcces("/proc/stb/vmpeg/1/external")),
	("HasFullHDSkinSupport", True),
	("HasHiSi", os.path.exists("/proc/hisi")),
	("hasPIPVisibleProc", _oeaAcces("/proc/stb/vmpeg/1/visible")),
	("HasGPT", False),
	("HasMMC", "root=/dev/mmcblk" in _cmdline or (_multiboot and "root=/dev/sda" in _cmdline)),
	("HasSDmmc", False),
	("HasSDswap", False),
	("HaveCISSL", _oeaAcces("/etc/ssl/certs/customer.pem") and _oeaAcces("/etc/ssl/certs/device.pem")),
	("HaveID", _oeaAcces("/etc/.id")),
	("HAVEINITCAM", hasInitCam()),
	("HAVEINITCARDSERVER", hasInitCardServer()),
	("HasSoftCSA", _softCsa),
	("HaveTouchSensor", False),
	("HDMICEC", os.path.exists("/dev/hdmi_cec") or os.path.exists("/dev/cec") or os.path.exists("/dev/misc/hdmi_cec0")),
	("HiSilicon", _soc.startswith("hisi") or os.path.exists("/proc/hisi") or os.path.exists("/usr/bin/hihalt") or os.path.exists("/usr/lib/hisilicon")),
	("LcdDisplay", os.path.exists("/dev/dbox/lcd0")),
	("LcdLiveTV", _oeaAcces("/proc/stb/fb/sd_detach") or _oeaAcces("/proc/stb/lcd/live_enable")),
	("LcdLiveTVPiP", _oeaAcces("/proc/stb/lcd/live_decoder")),
	("LCDMiniTV", os.path.exists("/proc/stb/lcd/mode")),
	("LCDSKIN", os.path.exists("/usr/share/enigma2/display")),
	("LEDButtons", False),
	("LEDColorControl", os.path.exists("/proc/stb/fp/led_color")),
	("LEDPowerColor", os.path.exists("/proc/stb/fp/ledpowercolor")),
	("LEDStandbyColor", os.path.exists("/proc/stb/fp/ledstandbycolor")),
	("LEDSuspendColor", os.path.exists("/proc/stb/fp/ledsuspendledcolor")),
	("MiddleFlash", bool(SystemInfo.get("middleflash")) and not SystemInfo.get("smallflash")),
	("MiniTV", _oeaAcces("/proc/stb/fb/sd_detach") or _oeaAcces("/proc/stb/lcd/live_enable")),
	("OledDisplay", os.path.exists("/dev/dbox/oled0")),
	("Power4x7On", os.path.exists("/proc/stb/fp/power4x7on")),
	("Power4x7Standby", os.path.exists("/proc/stb/fp/power4x7standby")),
	("Power4x7Suspend", os.path.exists("/proc/stb/fp/power4x7suspend")),
	("PowerLed", os.path.exists("/proc/stb/power/powerled")),
	("PowerLed2", os.path.exists("/proc/stb/power/powerled2")),
	("RecoveryMode", _oeaAcces("/proc/stb/fp/boot_mode")),
	("SmallFlash", bool(SystemInfo.get("smallflash"))),
	("SmallBoxWizard", os.path.exists("/etc/smallbox-wizard.done")),
	("SoftCam", hasSoftcam()),
	("StandbyPowerLed", os.path.exists("/proc/stb/power/standbyled")),
	("STi", _soc.startswith("sti")),
	("SuspendPowerLed", os.path.exists("/proc/stb/power/suspendled")),
	("VideoDestinationConfigurable", os.path.exists("/proc/stb/vmpeg/0/dst_left") or os.path.exists("/sys/class/video/axis")),
	("XcoreVFD", False),
	("DisplaySetup", True),
	("DM9X0", False),
	("dFlash", os.path.exists("/usr/lib/enigma2/python/Plugins/Extensions/dFlash")),
	("CommonInterface", _sloturiCi),
	("CommonInterfaceCIDelay", _oeaAcces("/proc/stb/tsmux/rmx_delay")),
	("inadyn", os.path.exists("/etc/init.d/inadyn-mt")),
	("minidlna", os.path.exists("/etc/init.d/minidlna")),
	("ushare", os.path.exists("/etc/init.d/ushare")),
	("nfsserver", os.path.exists("/etc/init.d/nfsserver")),
	("samba", os.path.exists("/etc/init.d/samba")),
	("zerotier", os.path.exists("/etc/init.d/zerotier")),
	("AISubs", os.path.exists("/etc/init.d/aisocket")),
	("CanDescrambleInStandby", any(x in _oeaRand("/proc/stb/tsmux/ci0_input_choices", "") for x in ("PVR", "DVR0"))),
	("CanOfflineDecode", False),
	("OScamInstalled", False),
	("InfoBarEpg", False),
	("CanRefreshTemplates", False),
	("HasRTLSDR", False),
	("HasDABSettings", False),
	("CanScanDAB", False),
	("RfModulator", False),
	("Harddisk", False),
	("ScartSwitch", False),
	("CanChangeOsdAlpha", False),
	("CanChangeOsdPosition", _oeaAcces("/proc/stb/fb/dst_left")),
	("CanChangeOsdPositionAML", False),
	("OSD3DCalibration", _oeaAcces("/proc/stb/fb/3dmode")),
	# starea redarii, schimbata de ecrane la standard; aici numai valoarea de pornire
	("SeekStatePlay", False),
	("StatePlayPause", False),
	("StandbyState", False),
	("FastChannelChange", False),
	("FCCactive", False),
):
	SystemInfo.setdefault(_k, _v)
# Sunetul si imaginea: la standard aceste chei vin cu setari config.av.* pe care imaginea noastra nu le are (sunetul il
# reglam in ecranele noastre de sunet); True fara setarea lor ar face pluginul sa caute o setare lipsa. Deci False.
for _k in ("CanDownmixAAC", "CanDownmixAACPlus", "CanDownmixDTS", "CanAACTranscode", "CanAC3plusTranscode", "CanAC4",
		"CanDTSHD", "CanTrueHD", "CanWMAPRO", "CanBTAudio", "CanBTAudioDelay", "Can3DSurround", "Can3DSpeaker",
		"CanAutoVolume", "CanPcmMultichannel", "supportPcmMultichannel", "Canaudiosource", "Canedidchecking", "HDRSupport",
		"havecolorspace", "havecolorimetry", "haveboxmode", "havehdmicolordepth", "havedeinterlace", "havesyncmode",
		"haveamlhdrsupport", "havehdmihdrtype", "havehdmihdrosd", "have24hz"):
	SystemInfo.setdefault(_k, False)
# Aceleasi chei, in forma ceruta de unele pluginuri scrise pe aceeasi baza (Videomode, AutoResolution, QuadPiP, panourile de setari)
for _k in ("HasColorimetry", "HasHdrType", "HasQuadpip"):
	SystemInfo.setdefault(_k, False)
SystemInfo.setdefault("MachineBrand", SystemInfo.get("displaybrand", ""))
SystemInfo.setdefault("MBbootdevice", "")
SystemInfo.setdefault("OSDCalibration", bool(SystemInfo.get("CanChangeOsdPosition") or SystemInfo.get("CanChangeOsdAlpha")))
SystemInfo.setdefault("PIPAvailable", (SystemInfo.get("NumVideoDecoders") or 1) > 1)
SystemInfo.setdefault("RCImage", getRCFile("png"))
SystemInfo.setdefault("RCMapping", getRCFile("xml"))
SystemInfo.setdefault("FanPWM", bool(SystemInfo.get("Fan")) and _oeaAcces("/proc/stb/fp/fan_pwm"))
SystemInfo.setdefault("ColorFrontpanelDisplay", bool(_afisajFata and _tipAfisaj not in ("7segment", "textlcd") and (_bpp > 8 or _tipAfisaj.startswith("colorlcd"))))
SystemInfo.setdefault("LCDMiniTVPiP", bool(SystemInfo.get("LCDMiniTV")))
SystemInfo.setdefault("LCDSKINSetup", bool(SystemInfo.get("LCDSKIN")) and _tipAfisaj != "7segment")
SystemInfo.setdefault("HDMIin", bool(SystemInfo.get("hdmifhdin") or SystemInfo.get("hdmihdin")))
SystemInfo.setdefault("HDMIinPiP", bool(SystemInfo.get("HDMIin")))
SystemInfo.setdefault("USETunersetup", bool(SystemInfo.get("ForceLNBPowerChanged") or SystemInfo.get("ForceToneBurstChanged")))
SystemInfo.setdefault("WakeOnLAN", next((x for x in ("/proc/stb/power/wol", "/proc/stb/fp/wol", "/proc/stb/fp/phy_powered") if _oeaAcces(x)), False))
SystemInfo.setdefault("WakeOnLANType", getWakeOnLANType(SystemInfo.get("WakeOnLAN") or ""))
SystemInfo.setdefault("ZapMode", bool(SystemInfo.get("HdsZapMode")))
SystemInfo.setdefault("ConfigDisplay", _afisajFata and _tipAfisaj != "7segment")
SystemInfo.setdefault("dBackup", not SystemInfo.get("dFlash") and os.path.exists("/usr/lib/enigma2/python/Plugins/Extensions/dBackup"))
SystemInfo.setdefault("ImageBackup", not SystemInfo.get("dFlash") and not SystemInfo.get("dBackup"))
SystemInfo.setdefault("servicehisilicon", SystemInfo.get("mediaservice") == "servicehisilicon" and _oeaPlugin("ServiceHisilicon"))
for _slot in range(SystemInfo.get("CommonInterface") or 0):
	SystemInfo.setdefault("CI%dSupportsHighBitrates" % _slot, _oeaAcces("/proc/stb/tsmux/ci%d_tsclk" % _slot))
	SystemInfo.setdefault("CI%dRelevantPidsRoutingSupport" % _slot, _oeaAcces("/proc/stb/tsmux/ci%d_relevant_pids_routing" % _slot))
SystemInfo.setdefault("InformationCommitLogs", [])
try:
	updateSysSoftCam()
except Exception as _e:
	print("[SystemInfo] updateSysSoftCam: %r" % (_e,))


# 6. Metodele BoxInfo cerute de pluginuri, pe langa getItem/setItem de mai sus.
def _oeaSetItem(self, item, value, immutable=False):
	SystemInfo[item] = value
	return True


def _oeaDeleteItem(self, item):
	if item in SystemInfo:
		del SystemInfo[item]
		return True
	return False


BoxInfoClass.setItem = _oeaSetItem
BoxInfoClass.setMutableItem = lambda self, item, value: SystemInfo.__setitem__(item, value)
BoxInfoClass.deleteItem = _oeaDeleteItem
BoxInfoClass.getItemsList = lambda self: sorted(SystemInfo.keys())
BoxInfoClass.getEnigmaInfoList = lambda self: list(_oeaInfo)
BoxInfoClass.getEnigmaConfList = lambda self: list(_oeaConf)
BoxInfoClass.getImageVersionString = lambda self: str(SystemInfo.get("imageversion", ""))
BoxInfoClass.getKernelVersionString = lambda self: SystemInfo.get("kernel", "")


def _oeaCpuSerial(self):
	try:
		with open("/proc/cpuinfo") as f:
			for rand in f:
				if rand.startswith("Serial"):
					return rand.split(":", 1)[1].strip()
	except Exception:
		pass
	return "Undefined"


def _oeaUptime(self):
	try:
		secunde = int(float(_oeaRand("/proc/uptime", "0").split()[0]))
	except Exception:
		return "-"
	zile, rest = divmod(secunde, 86400)
	ore, rest = divmod(rest, 3600)
	return ("%d Days " % zile if zile else "") + "%d Hours %d Minutes" % (ore, rest // 60)


def _oeaVersiuneOpkg(self, nume):
	try:
		with open("/var/lib/opkg/info/%s.control" % nume) as f:
			for rand in f:
				if rand.startswith("Version:"):
					return rand[9:].split("+")[0].strip()
	except (IOError, OSError):
		pass
	return "Not Installed"


BoxInfoClass.getCPUSerial = _oeaCpuSerial
BoxInfoClass.getBoxUptime = _oeaUptime
BoxInfoClass.getVersionFromOpkg = _oeaVersiuneOpkg
BoxInfoClass.getCPUArch = lambda self: "ARM64" if SystemInfo.get("ArchIsARM64") else ("ARM" if SystemInfo.get("ArchIsARM") else "Mipsel")
BoxInfoClass.getCPUBrand = lambda self: "HiSilicon" if SystemInfo.get("HiSilicon") else ("Broadcom" if (SystemInfo.get("socfamily") or "").startswith("bcm") else "Undefined")
BoxInfoClass.getFlashType = lambda self: "Small - Tiny image" if SystemInfo.get("SmallFlash") else ("Middle - Lite image" if SystemInfo.get("MiddleFlash") else "Normal - Standard image")

# 7. Numele de modul (citite o data, ca in celelalte imagini Enigma2).
ARCHITECTURE = SystemInfo.get("architecture", "")
BRAND = SystemInfo.get("brand", "")
SOC_FAMILY = SystemInfo.get("socfamily", "")
DISPLAYTYPE = SystemInfo.get("displaytype", "")
MTDROOTFS = SystemInfo.get("mtdrootfs", "")
MTDKERNEL = SystemInfo.get("mtdkernel", "")
DISPLAYMODEL = SystemInfo.get("displaymodel", "")
DISPLAYBRAND = DISPLAYBRAND or SystemInfo.get("displaybrand", "")
MACHINEBUILD = SystemInfo.get("machinebuild", "")
MACHINENAME = DISPLAYMODEL
BOXTYPE = SystemInfo.get("boxtype", "")
CHKROOTMB = SystemInfo.get("chkrootmb", False)
UBIMB = SystemInfo.get("hasUBIMB", False)
