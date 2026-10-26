# Modificat de moneasoftware.com si hdsatelit.com, 2026
import os

try:
	from enigma import eDVBResourceManager
	_can_measure = eDVBResourceManager.getInstance().canMeasureFrontendInputPower()
except Exception:
	_can_measure = False

from Tools.Directories import fileExists, resolveFilename, SCOPE_PLUGINS
from Tools.HardwareInfo import HardwareInfo

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
SystemInfo["DeepstandbySupport"] = HardwareInfo().get_device_name() != "dm800"


try:
	_device_name = HardwareInfo().get_device_name()
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
# Dreambox ("dm8000"), iar un plugin care se uita la masina ar crede ca ruleaza pe alt receptor. HardwareInfo ramane
# cum il da driverul: NimManager isi alege dupa el pragul de curent al motorului antenei.
SystemInfo["machinebuild"] = _about_mb or _device_name or "viper4k"
SystemInfo["model"] = SystemInfo["machinebuild"]
SystemInfo["boxtype"] = SystemInfo["machinebuild"]
SystemInfo["socfamily"] = "hisilicon" if "hisilicon" in _chipset_text.lower() else ""
try:
	SystemInfo["ArchIsARM"] = 1 if os.uname().machine.lower().startswith(("arm", "aarch64")) else 0
except Exception:
	SystemInfo["ArchIsARM"] = 0
SystemInfo["oe"] = "OE-Alliance 5.5"
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
