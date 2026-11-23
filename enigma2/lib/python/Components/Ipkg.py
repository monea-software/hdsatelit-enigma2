# Modificat de moneasoftware.com si hdsatelit.com, 2026
import codecs
import os
import re
import time

from enigma import eConsoleAppContainer

# HDSatelit: opkg is always started with a list of arguments (execvp), never through /bin/sh.
# Before, the command was one string ("opkg install " + name) run by /bin/sh -c, and the names came from opkg
# output, package lists and .xml files of packages: a name like "x; rm -rf /" was a shell command.
# Now every package is checked before it becomes an argument: a package name must match the opkg pattern
# (lower case letters, digits, + - ., never a leading '-'), a package file must be an existing .ipk with an
# absolute path inside the places packages are installed from. Anything else is refused with EVENT_ERROR.

# \Z, not $: $ also matches before a trailing newline
_PACKAGE_NAME = re.compile(r'^[a-z0-9][a-z0-9+.\-]{0,120}\Z')
# where a package file may be installed from: removable and network storage, /tmp (downloads), the defaults of
# the image (DreamInfoHandler)
# HDSatelit 0.6.20: the real path is checked, and the system mounts sticks and disks in /run/media/<label>-<device>
# (/media/hdd and /hdd lead there, Components/Harddisk.py) while /tmp leads to /var/volatile/tmp
PACKAGE_FILE_ROOTS = ('/media/', '/hdd/', '/mnt/', '/autofs/', '/tmp/', '/run/media/', '/var/volatile/tmp/',
	'/usr/share/enigma2/')
_COMMANDS = ('update', 'upgrade', 'install', 'remove', 'list', 'list_installed', 'list-installed', 'list-upgradable')
# HDSatelit 0.6.8: --download-only, packages from foreign sources are downloaded and read before they are installed
# (Components/HdsExtensiiLucru.py, packages made only for Python 2)
# --force-overwrite and --force-reinstall: only for skins (enigma2-plugin-skins-*), as in OE-Alliance (HdsExtensiiLucru.optiuniTema)
_OPTIONS = ('--autoremove', '--noaction', '--force-depends', '--download-only', '--force-overwrite', '--force-reinstall',
	'--force-downgrade')
# HDSatelit 0.7.5: the packages of the image skin (HDSatelit) are never removed from the image (the skin list and the
# web page /skin cannot delete it, and the receiver falls back to it when the skin on screen is deleted)
PROTECTED_REMOVE = frozenset(('hdsatelit-skin', 'enigma2', 'enigma2-hdsatelit'))
_PROGRAMS = ('/usr/bin/opkg', '/bin/opkg', '/usr/sbin/opkg', '/usr/local/bin/opkg')


def opkgProgram():
	"""the full path of opkg, or None when the receiver has none"""
	for program in _PROGRAMS:
		if os.path.isfile(program) and os.access(program, os.X_OK):
			return program
	return None


def isPackageName(name):
	return isinstance(name, str) and _PACKAGE_NAME.match(name) is not None


def packageFile(path, roots = PACKAGE_FILE_ROOTS):
	"""the real path of an .ipk file that may be installed, else None"""
	if not isinstance(path, str) or not path.startswith('/') or not path.lower().endswith('.ipk'):
		return None
	if any(ord(c) < 32 or c == '\x7f' for c in path):
		return None
	try:
		# a file name that is not UTF-8 (a FAT stick mounted without utf8) holds surrogates: it cannot become an
		# argument (the conversion to a C string fails half way through starting opkg)
		path.encode('utf-8')
	except UnicodeEncodeError:
		return None
	real = os.path.realpath(path)
	if not real.lower().endswith('.ipk') or not os.path.isfile(real):
		return None
	if roots and not any(real.startswith(root) for root in roots):
		return None
	return real


def packageArgument(package, roots = PACKAGE_FILE_ROOTS):
	"""a package name or the real path of a package file, as one argument for opkg; None when refused"""
	if isPackageName(package):
		return package
	return packageFile(package, roots)


def opkgArguments(command, packages = (), options = (), roots = PACKAGE_FILE_ROOTS):
	"""the arguments for opkg (without the program), or None when the command, an option or a package is refused"""
	if command not in _COMMANDS:
		return None
	if isinstance(packages, str):
		packages = (packages,)
	arguments = [command]
	for option in options:
		if option not in _OPTIONS:
			return None
		arguments.append(option)
	for package in packages:
		if command == 'remove' and package in PROTECTED_REMOVE:
			print("[Ipkg] package of the image refused for remove: %r" % (package,))
			return None
		argument = packageArgument(package, roots)
		if argument is None:
			print("[Ipkg] package refused: %r" % (package,))
			return None
		arguments.append(argument)
	if command in ('install', 'remove') and len(arguments) == 1 + len(options):
		return None
	return arguments


def splitPackages(package):
	"""args['package'] of the callers: one package file (the path may hold spaces) or names separated by spaces"""
	if isinstance(package, (list, tuple)):
		return list(package)
	package = package or ''
	if package.startswith('/') and packageFile(package) is not None:
		return [package]
	return package.split()


def _pycInainte(arguments):
	"""HDSatelit 0.7.5: before an opkg remove, the .py files of the packages (Components/HdsPycRamase.py)"""
	try:
		from Components import HdsPycRamase
		return HdsPycRamase.instantaneu(arguments)
	except Exception as e:
		print("[Ipkg] HdsPycRamase:", e)
		return None


def _pycDupa(stare):
	"""after opkg: the .pyc written at runtime and the empty directories of the removed packages are deleted"""
	try:
		from Components import HdsPycRamase
		HdsPycRamase.curata(stare)
	except Exception as e:
		print("[Ipkg] HdsPycRamase:", e)


def _reap(pid):
	"""waitpid for a child just killed with SIGKILL, at most ~0.2 s (a child stuck in the kernel is left alone)"""
	if pid is None or pid <= 0:
		return
	for _i in range(20):
		try:
			if os.waitpid(pid, os.WNOHANG)[0]:
				return
		except OSError:
			return
		time.sleep(0.01)


def _pachete():
	"""The package reader, also when this module is loaded alone by PC tools."""
	try:
		from Components import HdsPachete
	except ImportError:
		import HdsPachete
	return HdsPachete


class IpkgComponent:
	EVENT_INSTALL = 0
	EVENT_DOWNLOAD = 1
	EVENT_INFLATING = 2
	EVENT_CONFIGURING = 3
	EVENT_REMOVE = 4
	EVENT_UPGRADE = 5
	EVENT_LISTITEM = 9
	EVENT_DONE = 10
	EVENT_ERROR = 11
	EVENT_MODIFIED = 12
	EVENT_LINE = 13		# HDSatelit: every line opkg writes (stdout and stderr), for a log

	CMD_INSTALL = 0
	CMD_LIST = 1
	CMD_REMOVE = 2
	CMD_UPDATE = 3
	CMD_UPGRADE = 4

	def __init__(self, ipkg = 'opkg'):
		# the old parameter named the program; only opkg is run, from its full path
		self.ipkg = ipkg
		self.cmd = eConsoleAppContainer()
		self.cache = None
		self.callbackList = []
		self.retval = None
		self.fetchedList = []
		# the output of opkg comes as bytes; decoded as it comes (a character cut between two reads waits for its end)
		self._decoder = None
		# HDSatelit 0.7.5: what opkg remove leaves behind (.pyc, __pycache__) is cleaned at the end, before EVENT_DONE
		self._pycRamase = None
		self._inventarToken = 0
		self._inventar = None
		self._inventarCeas = None
		self._pregatesteInventar = True
		self.setCurrentCommand()

	def setCurrentCommand(self, command = None):
		self.currentCommand = command

	def runCmd(self, arguments):
		"""arguments: the list from opkgArguments(); a string is not accepted any more (it went through the shell)"""
		self._anuleazaInventar()
		_pachete().invalideaza_strofe()
		self.retval = None
		self.cache = None
		program = opkgProgram()
		if not isinstance(arguments, (list, tuple)) or not arguments or program is None:
			print("[Ipkg] not run:", arguments, "(opkg missing)" if program is None else "(refused)")
			token = self._inventarToken
			self.callCallbacks(self.EVENT_ERROR, None)
			if token == self._inventarToken:
				self.retval = -1
				self.callCallbacks(self.EVENT_DONE, -1)
			return
		# Feed updates have ordered guards that may replace a list during EVENT_DONE.
		# Keep that path and read-only/download-only commands as before this repair.
		self._pregatesteInventar = arguments[0] in ('install', 'remove', 'upgrade') and not any(
			optiune in arguments for optiune in ('--download-only', '--noaction'))
		print("[Ipkg] executing", program, arguments)
		self._pycRamase = _pycInainte(arguments)
		self._decoder = codecs.getincrementaldecoder('utf-8')('replace')
		self.cmd.appClosed.append(self.cmdFinished)
		self.cmd.dataAvail.append(self.cmdData)
		if self.cmd.execute(program, 'opkg', *arguments):
			self.cmdFinished(-1)

	def startCmd(self, cmd, args = None):
		args = args or {}
		self.setCurrentCommand(cmd)
		if cmd == self.CMD_UPDATE:
			arguments = opkgArguments('update')
		elif cmd == self.CMD_UPGRADE:
			arguments = opkgArguments('upgrade', args.get('packages', ()), args.get('test_only') and ('--noaction',) or ())
		elif cmd == self.CMD_LIST:
			self.fetchedList = []
			arguments = opkgArguments(args.get('installed_only') and 'list_installed' or 'list')
		elif cmd == self.CMD_INSTALL:
			arguments = opkgArguments('install', splitPackages(args.get('package')))
		elif cmd == self.CMD_REMOVE:
			arguments = opkgArguments('remove', splitPackages(args.get('package')), args.get('autoremove') and ('--autoremove',) or ())
		else:
			arguments = None
		self.runCmd(arguments)

	def cmdFinished(self, retval, oprit = False):
		if self._inventar is not None:
			return
		token = self._inventarToken
		try:
			self.cmd.appClosed.remove(self.cmdFinished)
			self.cmd.dataAvail.remove(self.cmdData)
		except ValueError:
			pass
		if self._decoder is not None:
			rest = self._decoder.decode(b'', True)
			self._decoder = None
			if rest:
				self.cache = (self.cache or '') + rest
		if self.cache:
			rest, self.cache = self.cache, None
			self.parseLine(rest)
		if token != self._inventarToken:
			return
		if oprit or not self._pregatesteInventar:
			self._termina(retval)
			return
		# EVENT_DONE consumers read status and feed lists. Prepare those on a worker,
		# then deliver the same events on the UI thread, with a validated snapshot.
		try:
			HdsPachete = _pachete()
			from enigma import eTimer
			self._inventarCeas = eTimer()
			self._inventarCeas.callback.append(self._verificaInventar)
			self._inventar = (self._inventarToken, retval, HdsPachete.CitireInventar().porneste(), 0)
			self._inventarCeas.start(20, True)
			return
		except Exception:
			self._anuleazaInventar()
			token = self._inventarToken
			self.callCallbacks(self.EVENT_ERROR, None)
			if token != self._inventarToken:
				return
			retval = retval or -1
		self._termina(retval)

	def _anuleazaInventar(self):
		self._inventarToken += 1
		if self._inventar is not None:
			self._inventar[2].anulat = True
		self._inventar = None
		if self._inventarCeas is not None:
			self._inventarCeas.stop()
			self._inventarCeas.callback.remove(self._verificaInventar)
			self._inventarCeas = None

	def _verificaInventar(self):
		pending = self._inventar
		if pending is None:
			return
		token, retval, citire, incercare = pending
		if token != self._inventarToken:
			return
		if not citire.gata:
			self._inventarCeas.start(20, True)
			return
		try:
			if citire.eroare:
				raise OSError('Package inventory could not be read')
			if not citire.verificat:
				citire.verifica()
				self._inventarCeas.start(20, True)
				return
			if not citire.publica():
				if incercare >= 2:
					raise OSError('Package inventory keeps changing')
				HdsPachete = _pachete()
				self._inventar = (token, retval, HdsPachete.CitireInventar().porneste(), incercare + 1)
				self._inventarCeas.start(20, True)
				return
		except Exception:
			self._anuleazaInventar()
			token = self._inventarToken
			self.callCallbacks(self.EVENT_ERROR, None)
			if token == self._inventarToken:
				self._termina(retval or -1)
			return
		self._anuleazaInventar()
		try:
			self._termina(retval)
		finally:
			citire.retrage()

	def _termina(self, retval):
		self.retval = retval
		# before EVENT_DONE: the callers reload the plugin list then (a plugin.pyc left behind would still be a plugin)
		stare, self._pycRamase = getattr(self, '_pycRamase', None), None
		if stare:
			_pycDupa(stare)
		self.callCallbacks(self.EVENT_DONE, retval)

	def cmdData(self, data):
		token = self._inventarToken
		if isinstance(data, bytes):
			if self._decoder is None:
				self._decoder = codecs.getincrementaldecoder('utf-8')('replace')
			data = self._decoder.decode(data)
			if not data:
				return
		if self.cache is None:
			self.cache = data
		else:
			self.cache += data

		if '\n' in data:
			splitcache = self.cache.split('\n')
			if self.cache[-1] == '\n':
				iteration = splitcache
				self.cache = None
			else:
				iteration = splitcache[:-1]
				self.cache = splitcache[-1]
			for mydata in iteration:
				if token != self._inventarToken:
					break
				if mydata != '':
					self.parseLine(mydata)

	def parseLine(self, data):
		token = self._inventarToken
		self.callCallbacks(self.EVENT_LINE, data)
		if token != self._inventarToken:
			return
		if self.currentCommand == self.CMD_LIST:
			item = data.split(' - ', 2)
			self.fetchedList.append(item)
			self.callCallbacks(self.EVENT_LISTITEM, item)
		else:
			try:
				if data.find('Downloading') == 0:
					self.callCallbacks(self.EVENT_DOWNLOAD, data.split(' ', 5)[1].strip())
				elif data.find('Upgrading') == 0:
					self.callCallbacks(self.EVENT_UPGRADE, data.split(' ', 1)[1].split(' ')[0])
				elif data.find('Installing') == 0:
					self.callCallbacks(self.EVENT_INSTALL, data.split(' ', 1)[1].split(' ')[0])
				elif data.find('Removing') == 0:
					self.callCallbacks(self.EVENT_REMOVE, data.split(' ', 1)[1].split(' ')[1])
				elif data.find('Configuring') == 0:
					self.callCallbacks(self.EVENT_CONFIGURING, data.split(' ', 1)[1].split(' ')[0])
				elif data.find('An error occurred') == 0:
					self.callCallbacks(self.EVENT_ERROR, None)
				elif data.find('Failed to download') == 0:
					self.callCallbacks(self.EVENT_ERROR, None)
				elif data.find('ipkg_download: ERROR:') == 0:
					self.callCallbacks(self.EVENT_ERROR, None)
				elif data.find('    Configuration file \'') >= 0:
					# Note: the config file update question doesn't end with a newline, so
					# if we get multiple config file update questions, the next ones
					# don't necessarily start at the beginning of a line
					self.callCallbacks(self.EVENT_MODIFIED, data.split(' \'', 1)[1][:-1])
			except IndexError:
				# a shorter line than expected (another opkg version): only the log gets it
				pass

	def callCallbacks(self, event, param = None):
		token = self._inventarToken
		for callback in self.callbackList[:]:
			if token != self._inventarToken:
				break
			callback(event, param)

	def addCallback(self, callback):
		self.callbackList.append(callback)

	def removeCallback(self, callback):
		if callback in self.callbackList:
			self.callbackList.remove(callback)

	def getFetchedList(self):
		return self.fetchedList

	def stop(self):
		# HDSatelit: eConsoleAppContainer.kill() closes the pipes without appClosed (lib/base/console.cpp), so the
		# callers never got EVENT_DONE and waited for ever (the progress window of HdsExtensii stayed open, every key
		# ignored) and the killed opkg stayed a zombie. Now the end is reported here and the child is reaped.
		pending = self._inventar is not None
		if pending:
			self._anuleazaInventar()
		running = self.cmd.running()
		pid = self.cmd.getPID() if running else -1
		self.cmd.kill()
		if running:
			_reap(pid)
			self.cmdFinished(-1, oprit = True)
		elif pending:
			self._termina(-1)

	def isRunning(self):
		return self.cmd.running() or self._inventar is not None

	def write(self, what):
		if what:
			# We except unterminated commands
			what += "\n"
			self.cmd.write(what, len(what))
