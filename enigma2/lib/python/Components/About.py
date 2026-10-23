# Modificat de moneasoftware.com si hdsatelit.com, 2026
import os
import re

try:
	from Tools.Directories import resolveFilename, SCOPE_SYSETC
except ImportError:
	SCOPE_SYSETC = 0
	def resolveFilename(scope, filename):
		return os.path.join("/etc", filename)

try:
	from enigma import getEnigmaVersionString
except ImportError:
	def getEnigmaVersionString():
		return "HD Satelit"

try:
	_
except NameError:
	def _(text):
		return text

# singura forma primita de la getEnigmaVersionString() din executabil: versiunea din AC_INIT si data, „0.1.5 2026-10-01”
_VERSIUNE_NUCLEU = re.compile(r"^\d+\.\d+\.\d+ \d{4}-\d{2}-\d{2}$")
# regulile modelului pentru care e construita imaginea (aceleasi ca in Components/HdsPazaModel.py)
FISIER_REGULI_MODEL = "/etc/hdsatelit-model"

class About:
	def __init__(self):
		pass

	def getVersionString(self):
		return self.getImageVersionString()

	def getImageVersionString(self):
		try:
			# „with" fiindca vechiul file.close() statea DUPA return, deci nu se executa niciodata pe drumul bun
			with open(resolveFilename(SCOPE_SYSETC, 'image-version'), 'r') as file:
				lines = file.readlines()
			for x in lines:
				splitted = x.split('=')
				if splitted[0] == "version":
					#     YYYY MM DD hh mm
					#0120 2005 11 29 01 16
					#0123 4567 89 01 23 45
					version = splitted[1]
					image_type = version[0] # 0 = release, 1 = experimental
					major = version[1]
					minor = version[2]
					revision = version[3]
					year = version[4:8]
					month = version[8:10]
					day = version[10:12]
					# 19 cifre (Makefile.am): o parte a versiunii are doua cifre, deci fiecare parte sta pe doua
					# cifre, 0000310... = 0.3.10 (aceeasi regula ca HdsJurnalVersiuni.desparte_build)
					lung = version.strip()
					if len(lung) == 19 and lung.isdigit() and lung.isascii():
						major, minor, revision = str(int(lung[1:3])), str(int(lung[3:5])), str(int(lung[5:7]))
						year, month, day = lung[7:11], lung[11:13], lung[13:15]
					date = '-'.join((year, month, day))
					if image_type == '0':
						version = '.'.join((major, minor, revision))
						return ' '.join((version, date))
					else:
						image_type = "Experimental"
						return ' '.join((image_type, date))
		except IOError:
			pass

		return "unavailable"

	def getEnigmaVersionString(self):
		"""Versiunea si data executabilului, „x.y.z AAAA-LL-ZZ”. Se primeste numai forma aceasta, verificata intreaga:
		un executabil care intoarce altceva (data lipita de numele ramurii din care s-a construit, rezerva de import,
		„(no branch)” fara dosarul .git) nu ajunge pe ecran; atunci randul arata versiunea imaginii din
		/etc/image-version, aceeasi forma."""
		try:
			ver = str(getEnigmaVersionString() or "").strip()
			if _VERSIUNE_NUCLEU.match(ver):
				return ver
		except Exception:
			pass
		return self.getImageVersionString()

	def getKernelVersionString(self):
		# fara comanda externa: numele versiunii vine direct din os.uname()
		try:
			return os.uname().release.split('-')[0]
		except Exception:
			return _("unknown")

	def _readFile(self, path):
		try:
			with open(path) as f:
				return f.read().strip()
		except (IOError, OSError):
			return ""

	def valoareDinReguli(self, cheie):
		"""O valoare din regulile modelului (/etc/hdsatelit-model, scrise la construirea imaginii): „model” (de exemplu
		„Amiko Viper 4K V20”) sau „machinebuild” („viper4kv20”). Primul rand cu cheia; numai litere, cifre, spatii si
		. _ - + ( ), cel mult 60 de caractere; "" cand fisierul sau cheia lipseste (emulatorul, alta imagine)."""
		for rand in self._readFile(FISIER_REGULI_MODEL).splitlines():
			rand = rand.strip()
			if rand.startswith("#") or "=" not in rand:
				continue
			k, sep, v = rand.partition("=")
			if k.strip() == cheie:
				return "".join(ch for ch in v.strip() if ch.isalnum() or ch in " ._-+()").strip()[:60]
		return ""

	def _esteViper4kV20(self):
		"""Semnalul real folosit deja in getReceiverName() -- extras separat ca sa poata fi
		refolosit si de getBrand()/getModel(), fara sa se duplice logica de detectie in mai multe locuri."""
		boxtype = self._readFile("/proc/stb/info/boxtype").lower()
		hostname = self._readFile("/etc/hostname").lower()
		return boxtype == "u57" or "viper4k" in hostname

	def getBrand(self):
		"""Marca receptorului, separat de model (inainte era scris "Amiko" neconditionat in
		Components/SystemInfo.py -- pe un al doilea receptor, non-Amiko, ar fi aratat gresit peste tot unde
		SystemInfo["brand"]/["displaybrand"] e citit). Acelasi semnal ca getReceiverName(): intai
		/etc/image-version (marca_masina), apoi maparea boxtype/hostname deja validata. Sir gol (nu o marca
		ghicita) cand hardware-ul nu e recunoscut."""
		try:
			with open(resolveFilename(SCOPE_SYSETC, 'image-version'), 'r') as f:
				for line in f:
					k, sep, v = line.partition("=")
					if k.strip().lower() == "machine_brand" and v.strip():
						return v.strip()
		except (IOError, OSError):
			pass
		if self._esteViper4kV20():
			return "Amiko"
		return ""

	def getModel(self):
		"""Modelul receptorului, fara marca (inainte era scris "Viper 4K" neconditionat in
		Components/SystemInfo.py). Acelasi semnal ca getBrand()/getReceiverName()."""
		try:
			with open(resolveFilename(SCOPE_SYSETC, 'image-version'), 'r') as f:
				for line in f:
					k, sep, v = line.partition("=")
					if k.strip().lower() in ("machine_name", "model") and v.strip():
						return v.strip()
		except (IOError, OSError):
			pass
		if self._esteViper4kV20():
			return "Viper 4K"
		return self._readFile("/proc/stb/info/boxtype") or ""

	def getReceiverName(self):
		# 1. Verificam intai /etc/image-version pentru marca si model specifice
		brand = ""
		model = ""
		try:
			with open(resolveFilename(SCOPE_SYSETC, 'image-version'), 'r') as f:
				for line in f:
					k, sep, v = line.partition("=")
					k = k.strip().lower()
					v = v.strip()
					if k == "machine_brand":
						brand = v
					elif k in ("machine_name", "model"):
						model = v
		except (IOError, OSError):
			pass

		if brand and model:
			if model.lower().startswith(brand.lower()):
				return model
			return "%s %s" % (brand, model)
		elif model:
			return model

		# 2. Numele din regulile modelului (acelasi pe V20; pe un alt model din familie, numele lui)
		model = self.valoareDinReguli("model")
		if model:
			return model

		# 3. Mapari specifice pe baza de boxtype si hostname (rezerva, fara reguli)
		if self._esteViper4kV20():
			return "Amiko Viper 4K V20"

		# 4. Alte receptoare STB (/proc/stb/info), ignorand valorile stub de compatibilitate
		for path in ("/proc/stb/info/boxtype", "/proc/stb/info/model", "/proc/stb/info/vumodel"):
			name = self._readFile(path)
			if name and name.lower() not in ("dm8000", "ultimo", "unknown", "none"):
				return name

		# 4. Detectie emulator PC (lipsa /proc/stb sau arhitectura x86_64)
		if not os.path.exists("/proc/stb") or os.uname().machine in ("x86_64", "i686", "amd64"):
			return "Receptor Virtual HD Satelit (Emulator PC)"

		return self._readFile("/etc/hostname") or "HD Satelit"

	def getChipset(self):
		cs = self._readFile("/proc/stb/info/chipset")
		if cs:
			if cs.lower() in ("3798mv200", "hi3798mv200"):
				return "HiSilicon Hi3798MV200 (15000 DMIPS)"
			return cs
		if not os.path.exists("/proc/stb") or os.uname().machine in ("x86_64", "i686", "amd64"):
			return "Virtual / Software (Emulator PC %s)" % os.uname().machine
		return "Nespecificat"

	def getCPUInfo(self):
		# (model, numar de nuclee); cheile difera intre x86, ARM si MIPS
		model = ""
		cores = 0
		cpu_text = self._readFile("/proc/cpuinfo")
		for line in cpu_text.splitlines():
			key, sep, value = line.partition(":")
			key = key.strip().lower()
			val = value.strip()
			if key == "processor" and val.isdigit():
				cores += 1
			elif not model:
				if key in ("model name", "system type", "cpu model"):
					model = val
				elif key == "processor" and not val.isdigit():
					model = val
				elif key == "hardware" and val and val.lower() != "bigfish":
					model = val

		# Identificare chipset STB (HiSilicon etc.)
		chipset = self._readFile("/proc/stb/info/chipset")
		if chipset:
			if chipset.lower() == "3798mv200":
				chipset_name = "HiSilicon Hi3798MV200"
			else:
				chipset_name = chipset
			if model and "hisilicon" not in model.lower():
				model = "%s (%s)" % (model, chipset_name)
			elif not model:
				model = chipset_name

		if not model:
			model = _("ARMv7 Processor") if cores else _("unknown")

		return (model, max(cores, 1))

	def getRAMInfo(self):
		# (total MB, disponibil MB)
		values = {}
		for line in self._readFile("/proc/meminfo").splitlines():
			key, sep, value = line.partition(":")
			parts = value.split()
			if parts and parts[0].isdigit():
				values[key.strip()] = int(parts[0]) // 1024
		available = values.get("MemAvailable", values.get("MemFree", 0))
		return (values.get("MemTotal", 0), available)

	def getStorageInfo(self, path="/"):
		# (total MB, liber MB, ocupat MB) pentru sistemul de fisiere din path
		try:
			s = os.statvfs(path)
		except OSError:
			return (0, 0, 0)
		total = s.f_blocks * s.f_frsize // (1024 * 1024)
		free = s.f_bavail * s.f_frsize // (1024 * 1024)
		return (total, free, max(total - free, 0))

	def formatSize(self, megabytes):
		# sub 1024 MB in MB, peste in GB cu o zecimala
		if megabytes < 0:
			return _("unknown")
		if megabytes < 1024:
			return _("%d MB") % megabytes
		return _("%.1f GB") % (megabytes / 1024.0)

	def getUptimeString(self):
		try:
			seconds = int(float(self._readFile("/proc/uptime").split()[0]))
		except (IndexError, ValueError):
			return _("unknown")
		days, rest = divmod(seconds, 86400)
		hours, rest = divmod(rest, 3600)
		minutes = rest // 60
		if days:
			return _("%d days, %d h %d min") % (days, hours, minutes)
		return _("%d h %d min") % (hours, minutes)

about = About()
