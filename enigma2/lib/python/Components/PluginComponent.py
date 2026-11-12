# Modificat de moneasoftware.com si hdsatelit.com, 2026
from os import path as os_path, listdir as os_listdir
from re import compile as re_compile, sub as re_sub
from time import monotonic
from traceback import print_exc
from sys import modules as sys_modules, stdout

from Tools.Directories import fileExists
from Tools.Import import my_import
from Plugins.Plugin import PluginDescriptor
import keymapparser

# HDSatelit: un modul .so (sau o biblioteca prin ctypes) legat de alt Python nu se mai incarca in enigma2; importul lui
# da un ImportError (Components/HdsAltPython.py), nu o cadere mai tarziu in libpython-ul celuilalt Python
try:
	from Components import HdsAltPython
	HdsAltPython.pazeste()
except Exception as _exc:
	HdsAltPython = None
	print("[PluginComponent] the guard for modules of another Python is not set:", _exc)


def _pluginPermis(categorie, nume):
	"""HDSatelit: in the safe mode started by enigma2.sh (HDS_MOD_SIGUR=1, Components/HdsModSigur.py) only the plugins
	that came with the image are loaded; the others stay installed. Outside safe mode nothing is imported here."""
	from os import environ
	if environ.get("HDS_MOD_SIGUR") != "1":
		return True
	try:
		from Components import HdsModSigur
		return HdsModSigur.pluginPermis(categorie, nume)
	except Exception as exc:
		print("[PluginComponent] safe mode check failed, plugin %s/%s loaded: %s" % (categorie, nume, exc))
		return True


def numeFisierePlugin():
	"""Fisierele care fac dintr-un dosar un plugin: plugin.py, plugin.pyc, plugin.pyo si plugin compilat ca modul nativ (plugin.so,
	plugin.cpython-314-<arh>.so, plugin.abi3.so: Cython, cum vin unele pluginuri externe, de pilda WireGuard VPN 16.2). Fara modulele
	native, un asemenea plugin era sarit pe tacute: instalat, dar in nicio lista si fara motiv."""
	try:
		from importlib.machinery import EXTENSION_SUFFIXES
	except ImportError:
		EXTENSION_SUFFIXES = [".so"]
	nume = ["plugin.pyc", "plugin.pyo", "plugin.py"]
	nume.extend("plugin" + s for s in EXTENSION_SUFFIXES if ("plugin" + s) not in nume)
	if "plugin.so" not in nume:
		nume.append("plugin.so")
	return tuple(nume)


_FISIERE_PLUGIN = numeFisierePlugin()


def areFisierPlugin(dosar):
	"""Dosarul are un plugin de incarcat (oricare din numeFisierePlugin)."""
	for n in _FISIERE_PLUGIN:
		if fileExists(dosar + "/" + n):
			return True
	return False


# mesajul Python pentru un modul lipsa
_MODUL_LIPSA = re_compile(r"No module named '([^']+)'")


def motivOm(mesaj):
	"""Mesajul tehnic al unei erori, pe intelesul omului: No module named 'six' -> Lipseste modulul six. Restul ramane cum
	e, numai primul rand. Numele modulului nu e neaparat numele pachetului opkg, deci nu ghicim ce e de instalat."""
	gasit = _MODUL_LIPSA.search(mesaj or "")
	if gasit:
		return _("Lipsește modulul %s") % gasit.group(1)
	return ((mesaj or "").splitlines() or [""])[0]


def _textEroare(exc):
	return str(exc) or type(exc).__name__


def _raporteazaIncarcare(categorie, nume, exc, etapa):
	"""Lista continua chiar daca raportorul nu poate porni."""
	try:
		from Components import HdsPluginExtern
		HdsPluginExtern.raporteazaIncarcare(categorie, nume, type(exc), exc,
			exc.__traceback__, etapa=etapa)
	except Exception as e:
		print("[PluginComponent] raportul incarcarii %s/%s: %s" % (
			categorie, nume, e))


def _modulLipsa(exc):
	"""numele modulului dintr-un ModuleNotFoundError (None pentru orice alta eroare)"""
	if isinstance(exc, ImportError) and getattr(exc, "name", None) and _MODUL_LIPSA.search(str(exc)):
		return exc.name
	return None


def _faraDescriptoriGoi(plugins, nume):
	"""HDSatelit: Plugins() poate intoarce None sau o lista cu None, la pluginurile scrise pentru alte imagini acesta e semnul
	"nicio intrare pe acest aparat" (de pilda un ceas pentru un afisaj pe care receptorul nu-l are). Pe 0.7.0 un None ajungea la
	p.path = path si interfata cadea la fiecare pornire (5 caderi, apoi modul sigur). Acum None se sare, cu un
	rand in jurnal; pluginul ramane incarcat, cu descriptorii lui adevarati (sau fara niciunul)."""
	bune = [p for p in plugins if p is not None]
	if len(bune) != len(plugins):
		print("[PluginComponent] %s: Plugins() a dat %d intrari goale (None), sarite; raman %d" % (nume, len(plugins) - len(bune), len(bune)))
	return bune


# versiunea celuilalt Python din mesajul pastrat in erori (Components/HdsAltPython.AltPython)
_ALT_PYTHON = re_compile(r"built for Python (\d+\.\d+), this image has Python (\d+\.\d+)")


def _altPython(exc):
	"""Exceptia cu modulul legat de alt Python (ea sau una din lantul ei), cand importul pluginului a cazut pe el;
	altfel None."""
	try:
		return HdsAltPython.exceptieDinLant(exc) if HdsAltPython is not None else None
	except Exception:
		return None


def _raporteazaAltPython(categorie, nume, exc):
	"""Raportul pluginurilor externe (Components/HdsPluginExtern), fara mesaj pe ecran: lista pluginurilor care nu s-au
	incarcat il arata deja. Nu arunca."""
	try:
		from Components import HdsPluginExtern
		HdsPluginExtern.raporteazaRefuz(categorie, nume, exc)
	except Exception as e:
		print("[PluginComponent] report for %s/%s: %r" % (categorie, nume, e))


def _importaPlugin(categorie, nume, path):
	"""HDSatelit: importul pluginului; unul care cade numai fiindca e scris in Python 2 se traduce in Python 3 o data, apoi se
	importa din nou (Components/HdsPython2Traducere.py). La fel unul care s-a incarcat, dar are cod de Python 2 in functii (se
	vede din sursa, o data pe versiunea fisierelor). Exceptia aruncata e a celui de-al doilea import cand pluginul tradus tot
	cade, ModuleNotFoundError('fissix') cand lipseste traducatorul (Components/HdsModuleLipsa.py il aduce din feed) sau
	Python2Netradus (mesajul pentru om); altfel exceptia primului import."""
	modul = ".".join(["Plugins", categorie, nume, "plugin"])
	try:
		plugin = my_import(modul)
	except Exception as exc:
		try:
			from Components import HdsPython2Traducere
		except Exception as e:
			print("[PluginComponent] traducatorul Python 2:", e)
			raise exc
		plugin = HdsPython2Traducere.incearca(categorie, nume, path, exc, lambda: my_import(modul))
		if plugin is None:
			raise
		return plugin
	# s-a incarcat; codul de Python 2 din functii (cade abia la deschidere) se cauta in sursa o data pe versiunea fisierelor
	try:
		from Components import HdsPython2Traducere
	except Exception as e:
		print("[PluginComponent] traducatorul Python 2:", e)
		return plugin
	return HdsPython2Traducere.dupaImport(categorie, nume, path, plugin, lambda: my_import(modul))


def _verificaDescriptor(p):
	"""ce a intors Plugins(): descriptorul trebuie sa se poata pune in liste (getPlugins le sorteaza dupa weight)"""
	if not isinstance(p, PluginDescriptor):
		raise TypeError("Plugins() returned %s" % type(p).__name__)
	if not isinstance(getattr(p, "weight", 0), (int, float)):
		raise TypeError("weight must be a number: %r" % (p.weight,))


class _SemnRecitire:
	"""HDSatelit: the plugin list read again while the interface runs (a plugin asks for it, the list after an install), on the main
	thread. A plugin that was not imported yet can stay long in its import (a large file compiled for the first time, a disk enumerated
	at import), the heartbeat stops and the watchdog (Components/HdsPaznic.py) would take that for a hang. The busy sign tells it to
	wait, with a limit: HdsPaznic.DURATA_PLUGINURI_S for one plugin and TOTAL_PLUGINURI_S for the whole read, so a plugin that never
	returns is still stopped, and the watchdog log names it. The reason is pluginuri:<folder>. Never raises."""

	def __init__(self):
		self.paznic = None
		try:
			from Components import HdsPaznic
			self.paznic = HdsPaznic
			self.inceput = monotonic()
			HdsPaznic.ocupat(HdsPaznic.CHEIE_PLUGINURI, HdsPaznic.MOTIV_PLUGINURI, min(HdsPaznic.DURATA_PLUGINURI_S, HdsPaznic.TOTAL_PLUGINURI_S))
		except Exception as exc:
			print("[PluginComponent] busy sign:", exc)

	def plugin(self, categorie, nume):
		"""Before the import of one plugin; one already imported comes back at once and changes nothing."""
		if self.paznic is None or ".".join(["Plugins", categorie, nume, "plugin"]) in sys_modules:
			return
		try:
			ramas = self.paznic.TOTAL_PLUGINURI_S - (monotonic() - self.inceput)
			if ramas > 0:
				motiv = "%s:%s" % (self.paznic.MOTIV_PLUGINURI, re_sub(r"[^A-Za-z0-9_.-]", "", nume))
				self.paznic.ocupat(self.paznic.CHEIE_PLUGINURI, motiv, min(self.paznic.DURATA_PLUGINURI_S, ramas))
		except Exception as exc:
			print("[PluginComponent] busy sign:", exc)

	def gata(self):
		if self.paznic is not None:
			self.paznic.liber(self.paznic.CHEIE_PLUGINURI)


class PluginComponent:
	firstRun = True
	restartRequired = False
	
	def __init__(self):
		self.plugins = {}
		self.pluginList = [ ]
		self.installedPluginList = [ ]
		# de ce nu se poate deschide un plugin. Spre deosebire de warnings (coada ferestrelor de avertisment), acestea raman
		# dupa ce fereastra s-a inchis: erori, eroriTaste si amanate se refac la fiecare readPluginList
		self.erori = {}             # 'categorie/nume' -> {nume, path, fel, mesaj}; fel: import plugins fara_plugins descriptor mod_sigur alt_python
		self.eroriTaste = {}        # calea pluginului -> keymap.xml stricat; pluginul ramane in liste
		self.eroriDeschidere = {}   # calea pluginului -> ultima deschidere cazuta, pana la urmatoarea reusita (Plugins/Plugin.py)
		self.amanate = {}           # calea pluginului -> descriptorul care asteapta repornirea interfetei
		self.amanateToate = {}      # calea pluginului -> toti descriptorii lui amanati (activeazaAcum)
		self.setPluginPrefix("Plugins.")
		self.resetWarnings()

	def setPluginPrefix(self, prefix):
		self.prefix = prefix

	def addPlugin(self, plugin):
		if self.firstRun or plugin.needsRestart is False:
			self.pluginList.append(plugin)
			for x in plugin.where:
				self.plugins.setdefault(x, []).append(plugin)
				if x == PluginDescriptor.WHERE_AUTOSTART:
					plugin(reason=0)
		else:
			self.restartRequired = True
			# numele aratat e al descriptorului cu ecran, cand pluginul are si altii (de fundal, de pilda)
			if plugin.path and (plugin.path not in self.amanate or self._areEcran(plugin)):
				self.amanate[plugin.path] = plugin
			if plugin.path:
				self.amanateToate.setdefault(plugin.path, []).append(plugin)

	def activeazaAcum(self, cai, session=None):
		"""HDSatelit: pluginurile din cai (nu s-au putut incarca la pornire fiindca le lipsea un modul, Components/HdsModuleLipsa.py,
		iar acum s-au incarcat) intra in liste fara repornirea interfetei, ca la pornire: AUTOSTART din addPlugin, apoi SESSIONSTART cu
		sesiunea. Nimic din ele nu rulase inainte, deci e acelasi drum ca la pornire, numai mai tarziu. Intoarce caile pornite."""
		pornite = []
		for cale in cai:
			descriptori = self.amanateToate.pop(cale, [])
			if not descriptori:
				continue
			self.amanate.pop(cale, None)
			for p in descriptori:
				p.needsRestart = False
				if p in self.pluginList:
					continue
				try:
					self.addPlugin(p)
				except Exception as exc:
					print("[PluginComponent] %s: pornirea (AUTOSTART) a cazut: %s" % (cale, exc))
			if session is not None:
				for p in descriptori:
					if PluginDescriptor.WHERE_SESSIONSTART in p.where:
						try:
							p(reason=0, session=session)
						except Exception as exc:
							print("[PluginComponent] %s: pornirea (SESSIONSTART) a cazut: %s" % (cale, exc))
			pornite.append(cale)
		self.restartRequired = bool(self.amanate)
		return pornite
				
	def _areEcran(self, plugin):
		return PluginDescriptor.WHERE_EXTENSIONSMENU in plugin.where or PluginDescriptor.WHERE_PLUGINMENU in plugin.where

	def removePlugin(self, plugin):
		self.pluginList.remove(plugin)
		self.eroriDeschidere.pop(plugin.path, None)
		for x in plugin.where:
			self.plugins[x].remove(plugin)
			if x == PluginDescriptor.WHERE_AUTOSTART:
				plugin(reason=1)

	def readPluginList(self, directory):
		"""enumerates plugins"""
		# HDSatelit: the known heavy steps of some plugins (JediMakerXtream, Bouquet Maker Xtream) run on a worker
		# thread; the hook is in place before any plugin module is imported (Components/HdsFirPluginuri.py)
		try:
			from Components import HdsFirPluginuri
			HdsFirPluginuri.instaleaza()
		except Exception as exc:
			print("[PluginComponent] HdsFirPluginuri:", exc)
		# HDSatelit: bugetul verificarii din sursa a pluginurilor Python 2 pentru aceasta citire (Components/HdsPython2Traducere.py)
		try:
			from Components import HdsPython2Traducere
			HdsPython2Traducere.incepeCitirea()
		except Exception as exc:
			print("[PluginComponent] HdsPython2Traducere:", exc)
		# the first read is the start of the interface, before the first heartbeat
		semn = None if self.firstRun else _SemnRecitire()
		try:
			self._citesteLista(directory, semn)
		finally:
			if semn is not None:
				semn.gata()
		# HDSatelit: un plugin cazut la import pe un modul Python din feedul nostru il primeste singur (Components/HdsModuleLipsa.py)
		try:
			from Components import HdsModuleLipsa
			HdsModuleLipsa.dupaCitire(self)
		except Exception as exc:
			print("[PluginComponent] modulele lipsa:", exc)

	def _citesteLista(self, directory, semn):
		categories = os_listdir(directory)

		new_plugins = [ ]
		self.erori = {}
		self.eroriTaste = {}
		self.amanate = {}
		self.amanateToate = {}

		for c in categories:
			directory_category = directory + c
			if not os_path.isdir(directory_category):
				continue
			for pluginname in os_listdir(directory_category):
				path = directory_category + "/" + pluginname
				if os_path.isdir(path):
					if areFisierPlugin(path):
						if not _pluginPermis(c, pluginname):
							self._puneEroare(c, pluginname, path, "mod_sigur")
							continue
						etapa = "import"
						if semn is not None:
							semn.plugin(c, pluginname)
						try:
							plugin = _importaPlugin(c, pluginname, path)

							if "Plugins" not in plugin.__dict__:
								print("Plugin %s doesn't have 'Plugin'-call." % (pluginname))
								self._puneEroare(c, pluginname, path, "fara_plugins")
								try:
									raise RuntimeError("Pluginul nu are functia Plugins")
								except RuntimeError as exc:
									_raporteazaIncarcare(c, pluginname, exc, "fara_plugins")
								continue

							etapa = "plugins"
							plugins = plugin.Plugins(path=path)

							# allow single entry not to be a list
							if not isinstance(plugins, list):
								plugins = [ plugins ]
							plugins = _faraDescriptoriGoi(plugins, c + "/" + pluginname)

							etapa = "descriptor"
							for p in plugins:
								_verificaDescriptor(p)
								p.path = path
								p.updateIcon(path)
						except Exception as exc:
							print("Plugin ", c + "/" + pluginname, "failed to load:", exc)
							print_exc(file=stdout)
							print("skipping plugin.")
							alt = _altPython(exc)
							if alt is not None:
								# un modul al pluginului e facut pentru alt Python: nu s-a incarcat, interfata merge mai departe
								self._puneEroare(c, pluginname, path, "alt_python", _textEroare(alt))
								self.warnings.append((c + "/" + pluginname, self._motiv(self.erori[c + "/" + pluginname])))
								_raporteazaAltPython(c, pluginname, alt)
								continue
							self.warnings.append( (c + "/" + pluginname, str(exc)) )
							self._puneEroare(c, pluginname, path, etapa, _textEroare(exc), _modulLipsa(exc))
							python2 = getattr(exc, "python2", None)
							if python2 is not None:
								# scris in Python 2 si netradus: textul pentru om in lista pluginurilor care nu se deschid
								self.erori[c + "/" + pluginname]["python2"] = str(exc).split(" (", 1)[0]
							# raportul spune eroarea pluginului (cea de dinaintea traducerii), nu motivul nostru (netradus, motor lipsa)
							raport = exc
							if (python2 is not None or _modulLipsa(exc) == "fissix") and exc.__cause__ is not None:
								raport = exc.__cause__
							_raporteazaIncarcare(c, pluginname, raport, etapa)
							continue

						new_plugins.extend(plugins)

						if fileExists(path + "/keymap.xml"):
							try:
								keymapparser.readKeymap(path + "/keymap.xml")
							except Exception as exc:
								print("keymap for plugin %s/%s failed to load: " % (c, pluginname), exc)
								self.warnings.append( (c + "/" + pluginname, str(exc)) )
								self.eroriTaste[path] = _textEroare(exc)
								_raporteazaIncarcare(c, pluginname, exc, "keymap")

		# build a diff between the old list of plugins and the new one
		# internally, the "fnc" argument will be compared with __eq__
		plugins_added = [p for p in new_plugins if p not in self.pluginList]
		plugins_removed = [p for p in self.pluginList if not p.internal and p not in new_plugins]
		
		#ignore already installed but reloaded plugins
		for p in plugins_removed: 
			for pa in plugins_added:
				if pa.path == p.path and pa.where == p.where:
					pa.needsRestart = False

		for p in plugins_removed:
			self.removePlugin(p)

		for p in plugins_added:
			if self.firstRun or p.needsRestart is False:
				self.addPlugin(p)
			else:
				for installed_plugin in self.installedPluginList:
					if installed_plugin.path == p.path:
						if installed_plugin.where == p.where:
							p.needsRestart = False
				self.addPlugin(p)
						
		if self.firstRun:
			self.firstRun = False
			self.installedPluginList = self.pluginList

	def getPlugins(self, where):
		"""Get list of plugins in a specific category"""

		if not isinstance(where, list):
			where = [ where ]
		res = [ ]

		for x in where:
			res.extend(self.plugins.get(x, [ ]))
		res.sort(key=lambda x:x.weight)
		return res

	def pluginuriDeDeschis(self):
		"""Inventarul comun al pluginurilor cu ecran, acelasi in orice lista (tasta albastra, Extensii, pagina web):
		WHERE_EXTENSIONSMENU si WHERE_PLUGINMENU, fara dubluri. PluginDescriptor.__eq__ compara fnc: aceeasi actiune apare o
		data, iar doua functii ale aceluiasi plugin raman amandoua. WHERE_EXTENSIONSMENU primul, ca aceeasi actiune sa-si
		pastreze numele de acolo."""
		res = [ ]
		for x in (PluginDescriptor.WHERE_EXTENSIONSMENU, PluginDescriptor.WHERE_PLUGINMENU):
			for p in self.plugins.get(x, [ ]):
				if p not in res:
					res.append(p)
		res.sort(key=lambda x:x.weight)
		return res

	def _puneEroare(self, categorie, nume, cale, fel, mesaj="", modul=None):
		self.erori[categorie + "/" + nume] = {"nume": nume, "path": cale, "fel": fel, "mesaj": mesaj}
		if modul:
			# modulul Python care lipseste (ModuleNotFoundError.name): Components/HdsModuleLipsa.py il poate aduce din feed
			self.erori[categorie + "/" + nume]["modul"] = modul

	def _motiv(self, eroare):
		fel = eroare["fel"]
		if fel == "mod_sigur":
			return _("Oprit în modul sigur")
		if fel == "fara_plugins":
			return _("Nu s-a încărcat: %s") % _("Nu are funcția Plugins")
		if fel == "descriptor":
			return _("Nu s-a încărcat: %s") % _("Descriere greșită a pluginului")
		if eroare.get("modul") == "fissix":
			# motorul traducerii (python3-fissix, adus de HdsModuleLipsa cu harta): textul despre Python 2, nu "Lipsește modulul fissix"
			return _("Nu s-a încărcat: %s") % _("scris pentru Python 2; traducătorul nu e instalat încă")
		if eroare.get("modul"):
			try:
				from Components import HdsModuleLipsa
				text = HdsModuleLipsa.textStare(eroare["modul"])
				if text:
					return text
			except Exception as exc:
				print("[PluginComponent] starea modulului lipsa:", exc)
		if fel == "alt_python":
			m = _ALT_PYTHON.search(eroare["mesaj"] or "")
			if m:
				return _("Nu s-a încărcat: %s") % (_("făcut pentru Python %s, imaginea are Python %s") % m.groups())
		if eroare.get("python2"):
			return _("Nu s-a încărcat: %s") % eroare["python2"]
		try:
			from Components import HdsPython2Traducere
			if HdsPython2Traducere.eTradus(eroare["path"]):
				return _("Tradus din Python 2; nu s-a încărcat: %s") % motivOm(eroare["mesaj"])
		except Exception as exc:
			print("[PluginComponent] starea traducerii:", exc)
		return _("Nu s-a încărcat: %s") % motivOm(eroare["mesaj"])

	def indisponibile(self):
		"""[{nume, path, fel, mesaj, motiv}], dupa nume: ce e pe receptor si nu se poate deschide acum. motiv = textul scurt
		pentru om, mesaj = textul tehnic ('' cand nu e). fel: cele din erori si repornire (plugin amanat)."""
		rez = [dict(e, motiv=self._motiv(e)) for e in self.erori.values()]
		for cale, p in self.amanate.items():
			rez.append({"nume": p.name or cale.rsplit("/", 1)[-1], "path": cale, "fel": "repornire", "mesaj": "",
				"motiv": _("Necesită repornirea interfeței")})
		rez.sort(key=lambda e: str(e["nume"]).lower())
		return rez

	def textMotiv(self, e):
		"""textul ferestrei de la OK pe un rand din indisponibile(): numele, motivul, apoi textul tehnic"""
		return "\n".join(x for x in (e["nume"], e["motiv"], e["mesaj"]) if x)

	def getPluginsForMenu(self, menuid):
		res = [ ]
		for p in self.getPlugins(PluginDescriptor.WHERE_MENU):
			res += p(menuid) or []
		return res

	def reloadPlugins(self, dummy=False):
		"""Numele cerut de pluginuri: lista citita din nou."""
		from Tools.Directories import resolveFilename, SCOPE_PLUGINS
		self.clearPluginList()
		self.readPluginList(resolveFilename(SCOPE_PLUGINS))

	def clearPluginList(self):
		self.pluginList = []
		self.plugins = {}

	def shutdown(self):
		for p in self.pluginList[:]:
			self.removePlugin(p)

	def resetWarnings(self):
		self.warnings = [ ]

	def getNextWakeupTime(self):
		wakeup = -1
		for p in self.pluginList:
			current = p.getWakeupTime()
			if current > -1 and (wakeup > current or wakeup == -1):
				wakeup = current
		return int(wakeup)

plugins = PluginComponent()
