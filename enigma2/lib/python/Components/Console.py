# Modificat de moneasoftware.com si hdsatelit.com, 2026
from enigma import eConsoleAppContainer
from Tools.BoundFunction import boundFunction

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

	def ePopen(self, cmd, callback=None, extra_args=[], log=True):
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
		if isinstance(cmd, str): # until .execute supports a better api
			cmd = [cmd]
		retval = self.appContainers[name].execute(*cmd)
		if retval:
			self.finishedCB(name, retval)

	def eBatch(self, cmds, callback, extra_args=[], debug=False):
		self.debug = debug
		cmd = cmds.pop(0)
		self.ePopen(cmd, self.eBatchCB, [cmds, callback, extra_args])

	def eBatchCB(self, data, retval, _extra_args):
		(cmds, callback, extra_args) = _extra_args
		if self.debug:
			if isinstance(data, bytes):
				data = data.decode("utf-8", "replace")
			print('[eBatch] retval=%s, cmds left=%d, data:\n%s' % (retval, len(cmds), data))
		if len(cmds):
			cmd = cmds.pop(0)
			self.ePopen(cmd, self.eBatchCB, [cmds, callback, extra_args])
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
		if self.callbacks[name]:
			self.callbacks[name](data,retval,extra_args)
		del self.callbacks[name]

	def kill(self,name):
		if name in self.appContainers:
			print("[Console] killing: ",self.appContainers[name])
			self.appContainers[name].kill()

	def killAll(self):
		for name in self.appContainers:
			self.kill(name)
