# Modificat de moneasoftware.com si hdsatelit.com, 2026
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
PACKAGE_FILE_ROOTS = ('/media/', '/hdd/', '/mnt/', '/autofs/', '/tmp/', '/usr/share/enigma2/')
_COMMANDS = ('update', 'upgrade', 'install', 'remove', 'list', 'list_installed', 'list-installed', 'list-upgradable')
_OPTIONS = ('--autoremove', '--noaction', '--force-depends')
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
		self.setCurrentCommand()

	def setCurrentCommand(self, command = None):
		self.currentCommand = command

	def runCmd(self, arguments):
		"""arguments: the list from opkgArguments(); a string is not accepted any more (it went through the shell)"""
		self.retval = None
		self.cache = None
		program = opkgProgram()
		if not isinstance(arguments, (list, tuple)) or not arguments or program is None:
			print("[Ipkg] not run:", arguments, "(opkg missing)" if program is None else "(refused)")
			self.callCallbacks(self.EVENT_ERROR, None)
			self.retval = -1
			self.callCallbacks(self.EVENT_DONE, -1)
			return
		print("[Ipkg] executing", program, arguments)
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

	def cmdFinished(self, retval):
		try:
			self.cmd.appClosed.remove(self.cmdFinished)
			self.cmd.dataAvail.remove(self.cmdData)
		except ValueError:
			pass
		if self.cache:
			rest, self.cache = self.cache, None
			self.parseLine(rest)
		self.retval = retval
		self.callCallbacks(self.EVENT_DONE, retval)

	def cmdData(self, data):
		if isinstance(data, bytes):
			data = data.decode('utf-8', 'replace')
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
				if mydata != '':
					self.parseLine(mydata)

	def parseLine(self, data):
		self.callCallbacks(self.EVENT_LINE, data)
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
		for callback in self.callbackList[:]:
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
		running = self.cmd.running()
		pid = self.cmd.getPID() if running else -1
		self.cmd.kill()
		if running:
			_reap(pid)
			self.cmdFinished(-1)

	def isRunning(self):
		return self.cmd.running()

	def write(self, what):
		if what:
			# We except unterminated commands
			what += "\n"
			self.cmd.write(what, len(what))
