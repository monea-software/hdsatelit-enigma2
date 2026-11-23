# Modificat de moneasoftware.com si hdsatelit.com, 2026
from enigma import eConsoleAppContainer
from Tools.BoundFunction import boundFunction


def instalareExterna(cmd, argv0=False):
	"""Recognize executed installer.sh, not a diagnostic mentioning its name.

	Other installer names use the explicit installation=True API. This is not a
	shell parser or a security boundary; the shell still receives the original.
	"""
	import posixpath
	import shlex
	from urllib.parse import urlsplit
	try:
		shell = isinstance(cmd, str)
		if shell:
			lex = shlex.shlex(cmd, posix=True, punctuation_chars="|;&<>")
			lex.whitespace_split = True
			args = list(lex)
		else:
			args = list(cmd)
			# Components passes [program, argv0, arguments]; Screens passes normal argv.
			if argv0 and len(args) > 1:
				args = args[:1] + args[2:]
		if not args or not all(isinstance(a, str) for a in args):
			return False
		program = posixpath.basename(args[0])
		if program in ("sh", "bash") and len(args) == 3 and args[1] == "-c":
			return instalareExterna(args[2])
		if program == "installer.sh":
			return True
		if program in ("sh", "bash") and len(args) > 1 and posixpath.basename(args[1]) == "installer.sh":
			return True
		if shell and program in ("wget", "curl") and "|" in args:
			pipe = args.index("|")
			right = args[pipe + 1:]
			if right and posixpath.basename(right[0]) in ("sh", "bash") and all(a in ("-s", "-", "--") for a in right[1:]):
				return any(urlsplit(a).scheme in ("http", "https") and
					posixpath.basename(urlsplit(a).path) == "installer.sh" for a in args[1:pipe])
	except (TypeError, ValueError):
		pass
	return False


def eroareSalvareInstalare():
	return _("Setările nu au putut fi salvate și verificate. Instalatorul nu a pornit.")


def _fotografieInstalare(C):
	"""Main only: serialize current values without invoking save notifiers or IO."""
	from copy import copy, deepcopy
	from Components.HdsProcesor import _clasaSetare
	ConfigModProcesor = _clasaSetare()
	elemente = []
	def copia(el):
		if isinstance(el, C.ConfigElement):
			nou = copy(el)
			nou.callNotifiersOnSaveAndCancel = False
			if isinstance(el, ConfigModProcesor):
				# This pure save also preserves a temporarily unavailable CPU choice.
				nou.save()
			elif isinstance(el, C.ConfigLocations):
				C.ConfigLocations.save(nou)
			elif isinstance(el, C.ConfigSelectionNumber):
				C.ConfigSelectionNumber.save(nou)
			elif isinstance(el, C.ConfigDictionarySet):
				values = {k: v for k, v in el.dirs.items() if not isinstance(v, (dict, list, tuple, str)) or v}
				nou.saved_value = None if el.save_disabled else el.tostring(values)
			else:
				C.ConfigElement.save(nou)
			elemente.append((el, nou.saved_value))
			return nou.saved_value
		if isinstance(el, C.ConfigSubsection):
			result = deepcopy(el.content.stored_values)
		elif isinstance(el, (C.ConfigSubList, C.ConfigSubDict)):
			result = {}
		else:
			raise TypeError("Unsupported configuration node")
		for key, child in el.dict().items():
			value = copia(child)
			key = str(key)
			if value is None:
				result.pop(key, None)
			else:
				result[key] = value
		return result
	parts = []
	C.config.pickle_this("config", copia(C.config), parts)
	return ''.join(parts), elemente


def _scrieInstalare(cale, data, scrie):
	"""Worker only: stage and verify before replacing the user's settings."""
	import os
	import tempfile
	target = os.path.realpath(cale)
	folder = os.path.dirname(target) or "."
	fd, stage = tempfile.mkstemp(prefix=".settings-install-", dir=folder)
	os.close(fd)
	try:
		try:
			old = os.stat(target)
		except FileNotFoundError:
			old = None
		if not scrie(stage, data):
			raise OSError("Settings write failed")
		with open(stage, "rb") as f:
			if f.read() != data:
				raise OSError("Incomplete settings write")
		if old is not None:
			os.chmod(stage, old.st_mode & 0o7777)
			if hasattr(os, "chown"):
				os.chown(stage, old.st_uid, old.st_gid)
		with open(stage, "r+b") as f:
			os.fsync(f.fileno())
		if os.path.realpath(cale) != target:
			raise OSError("Settings target changed")
		os.replace(stage, target)
		if os.name == "posix":
			fd = os.open(folder, os.O_RDONLY)
			try:
				os.fsync(fd)
			finally:
				os.close(fd)
		with open(cale, "rb") as f:
			if f.read() != data:
				raise OSError("Settings verification failed")
	finally:
		for name in (stage, stage + ".nou"):
			try:
				os.unlink(name)
			except FileNotFoundError:
				pass


def _scrieCereriInstalare(cereri, scrie, canalDinBaza, octeti):
	"""Worker: queued saves use the same checked atomic writer."""
	for filename, data, canal in cereri:
		if canal:
			try:
				with open(filename, "rb") as f:
					base = f.read().decode("utf-8", "surrogateescape")
			except FileNotFoundError:
				base = ""
			data = octeti(canalDinBaza(data.decode("utf-8", "surrogateescape"), base))
		_scrieInstalare(filename, data, scrie)


class PregatireInstalare:
	"""One shared operation for Console callers and the mirrored screen.

	Call on main; completion returns there. Closing cancels launch, never disk IO.
	No attempt is made to catch an external SIGKILL after the child starts.
	"""
	def __init__(self, la_gata):
		self.stare = "salvare"
		self.eroare = ""
		self.anulata = False
		self._gata = la_gata
		self._tranzactie = None

	def anuleaza(self):
		self.anulata = True

	def porneste(self):
		from Components import config as C
		self._config = C
		try:
			self._tranzactie = C.TranzactieSetari()
			self._salveaza()
		except Exception:
			self._esec(None)

	def _salveaza(self):
		try:
			from twisted.internet.threads import deferToThread
			C = self._config
			self._cale = C.configfile.CONFIG_FILE
			self._text, _ = _fotografieInstalare(C)
			deferToThread(self._tranzactie.ruleaza, _scrieInstalare,
				self._cale, C._octetiSetari(self._text), C._scrieSigur).addCallbacks(self._verificat, self._esec)
		except Exception:
			self._esec(None)

	def _verificat(self, _):
		from twisted.internet.threads import deferToThread
		C = self._config
		try:
			# A value can change while the disk is blocked. Never launch on that old snapshot.
			text, elemente = _fotografieInstalare(C)
			if text != self._text or C.configfile.CONFIG_FILE != self._cale:
				self._salveaza()
				return
			for el, saved in elemente:
				el.saved_value = saved
			cereri = self._tranzactie.preia()
			if cereri:
				deferToThread(self._tranzactie.ruleaza, _scrieCereriInstalare, cereri,
					C._scrieSigur, C._canalDinBaza, C._octetiSetari).addCallbacks(lambda _: self._salveaza(), self._esec)
				return
			if not self._tranzactie.inchide():
				raise RuntimeError("Settings reservation not released")
			C.configfile._scris = self._text
			self.stare = "anulata" if self.anulata else "gata"
		except Exception:
			self._esec(None)
			return
		self._gata(not self.anulata)

	def _esec(self, _):
		if self.stare != "salvare":
			return
		if self._tranzactie is not None:
			self._tranzactie.inchide(fortat=True)
		self._config.configfile._scris = None
		self.stare = "eroare"
		self.eroare = eroareSalvareInstalare()
		self._gata(False)


class Console(object):
	"""The callback of ePopen gets the whole output as text (UTF-8, a bad byte becomes U+FFFD); Console(binary=True)
	gives it as bytes. eConsoleAppContainer gives bytes, like on the other Python 3 images: they are gathered and
	decoded once, at the end, so a character cut between two reads comes out whole."""

	def __init__(self, binary=False):
		self.appContainers = {}
		self.appResults = {}
		self.callbacks = {}
		self.extra_args = {}
		self.binary = binary
		self._chunks = {}
		self._instalari = {}

	def ePopen(self, cmd, callback=None, extra_args=[], log=True, installation=False):
		if isinstance(cmd, (list, tuple)):
			cmd = tuple(cmd)
		# an argument list (program, argv0, arguments) runs without a shell; its text is the key
		base = cmd if isinstance(cmd, str) else " ".join(cmd)
		name = base
		i = 0
		while name in self.appContainers:
			name = base + '_' + str(i)
			i += 1
		# log=False for commands that carry secrets
		if log:
			print("[ePopen] command:", base)
		self.appResults[name] = b"" if self.binary else ""
		self._chunks[name] = []
		self.extra_args[name] = extra_args
		self.callbacks[name] = callback
		self.appContainers[name] = eConsoleAppContainer()
		self.appContainers[name].dataAvail.append(boundFunction(self.dataAvailCB,name))
		self.appContainers[name].appClosed.append(boundFunction(self.finishedCB,name))
		def porneste(ok=True):
			self._instalari.pop(name, None)
			if not ok:
				if not lucru.anulata:
					self.dataAvailCB(name, eroareSalvareInstalare())
				self.finishedCB(name, -2)
				return
			args = [cmd] if isinstance(cmd, str) else cmd
			retval = self.appContainers[name].execute(*args)
			if retval and name in self.appContainers:
				self.finishedCB(name, retval)
		if installation or instalareExterna(cmd, argv0=True):
			lucru = PregatireInstalare(porneste)
			self._instalari[name] = lucru
			lucru.porneste()
		else:
			porneste()

	def eBatch(self, cmds, callback, extra_args=[], debug=False, installation=False):
		self.debug = debug
		cmd = cmds.pop(0)
		args = [cmds, callback, extra_args] + ([True] if installation else [])
		self.ePopen(cmd, self.eBatchCB, args, installation=installation)

	def eBatchCB(self, data, retval, _extra_args):
		(cmds, callback, extra_args) = _extra_args[:3]
		installation = bool(_extra_args[3:])
		if self.debug:
			if isinstance(data, bytes):
				data = data.decode("utf-8", "replace")
			print('[eBatch] retval=%s, cmds left=%d, data:\n%s' % (retval, len(cmds), data))
		if len(cmds) and retval != -2:
			cmd = cmds.pop(0)
			self.ePopen(cmd, self.eBatchCB, _extra_args, installation=installation)
		else:
			callback(extra_args)

	def dataAvailCB(self, name, data):
		if isinstance(data, str):
			data = data.encode("utf-8", "surrogateescape")
		self._chunks.setdefault(name, []).append(data)

	def finishedCB(self, name, retval):
		del self.appContainers[name].dataAvail[:]
		del self.appContainers[name].appClosed[:]
		data = b"".join(self._chunks.pop(name, ()))
		if not self.binary:
			data = data.decode("utf-8", "replace")
		# the result stays readable under the name of the command after the end (Network reads it)
		self.appResults[name] = data
		extra_args = self.extra_args[name]
		del self.appContainers[name]
		del self.extra_args[name]
		callback = self.callbacks.pop(name)
		if callback:
			callback(data,retval,extra_args)

	def kill(self,name):
		if name in self._instalari:
			self._instalari[name].anuleaza()
			return
		if name in self.appContainers:
			print("[Console] killing: ",self.appContainers[name])
			self.appContainers[name].kill()

	def killAll(self):
		for name in list(self.appContainers):
			self.kill(name)
