# Modificat de moneasoftware.com si hdsatelit.com, 2026
import re


def _modelToken(valoare):
	"""Un nume ASCII intreg, fara spatii sau markup."""
	v = valoare.strip()
	return v if re.fullmatch(r"[A-Za-z0-9_.-]{1,40}", v) else ""


def getModelName(radacina=""):
	"""Modelul imaginii, apoi al placii. Radacina se schimba numai la probe."""
	def citeste(cale):
		try:
			with open(radacina + cale, "r", encoding="utf-8", errors="replace") as f:
				return f.read(64 * 1024)
		except (IOError, OSError):
			return ""

	for rand in citeste("/etc/hdsatelit-model").splitlines():
		cheie, sep, valoare = rand.partition("=")
		if sep and cheie.strip() == "machinebuild":
			model = _modelToken(valoare)
			if model:
				return model
			break
	# Unele drivere lasa un nume Dreambox in model, indiferent de placa.
	for cale in ("boxtype", "vumodel", "hwmodel", "gbmodel", "model"):
		randuri = citeste("/proc/stb/info/" + cale).splitlines()
		model = _modelToken(randuri[0]) if randuri else ""
		if cale == "vumodel" and model and not model.startswith("vu"):
			model = _modelToken("vu" + model)
		if model:
			return model
	info = citeste("/usr/lib/enigma.info").splitlines()
	for cautata in ("machinebuild", "model"):
		for rand in info:
			cheie, sep, valoare = rand.partition("=")
			if sep and cheie.strip() == cautata:
				model = _modelToken(valoare.strip().strip("'\""))
				if model:
					return model
				break
	return "unknown"


class HardwareInfo:
	device_name = None

	def __init__(self):
		if HardwareInfo.device_name is not None:
#			print "using cached result"
			return

		HardwareInfo.device_name = "unknown"
		try:
			file = open("/proc/stb/info/model", "r")
			HardwareInfo.device_name = file.readline().strip()
			file.close()
		except:
			print("----------------")
			print("you should upgrade to new drivers for the hardware detection to work properly")
			print("----------------")
			print("fallback to detect hardware via /proc/cpuinfo!!")
			try:
				rd = open("/proc/cpuinfo", "r").read()
				if rd.find("Brcm4380 V4.2") != -1:
					HardwareInfo.device_name = "dm8000"
					print("dm8000 detected!")
				elif rd.find("Brcm7401 V0.0") != -1:
					HardwareInfo.device_name = "dm800"
					print("dm800 detected!")
				elif rd.find("MIPS 4KEc V4.8") != -1:
					HardwareInfo.device_name = "dm7025"
					print("dm7025 detected!")
			except:
				pass

	def get_device_model(self):
		return HardwareInfo.device_name

	def get_device_version(self):
		return ""

	def get_device_revision(self):
		return ""

	def get_device_name(self):
		return HardwareInfo.device_name

	def has_hdmi(self):
		"""Receptoarele imaginii au HDMI; o valoare explicita din BoxInfo are prioritate."""
		from Components.SystemInfo import BoxInfo
		return bool(BoxInfo.getItem("hdmi", True))
