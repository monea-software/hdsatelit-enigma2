# Modificat de moneasoftware.com si hdsatelit.com, 2026
import codecs

from enigma import eConsoleAppContainer
from Screens.Screen import Screen
from Components.ActionMap import ActionMap
from Components.ScrollLabel import ScrollLabel
from Components.Console import PregatireInstalare, instalareExterna, eroareSalvareInstalare

class Console(Screen):
	# cmdlist entries (HDSatelit):
	#  - a string is a whole shell command line, run with /bin/sh -c (pipes, redirections); only for constant text,
	#    never with file, package or interface names pasted in
	#  - a list or tuple is an argument list [program, arg1, ...], run with execvp and no shell; the program is
	#    searched in PATH and is also argv[0]. Use this whenever a part of the command is not a constant.
	#TODO move this to skin.xml
	skin = """
		<screen position="100,100" size="550,400" title="Command execution..." >
			<widget name="text" position="0,0" size="550,400" font="Console;14" />
		</screen>"""
		
	def __init__(self, session, title = "Console", cmdlist = None, finishedCallback = None, closeOnSuccess = False,
			cmdList = None, showScripts = True, windowTitle = None, installation = False, **altele):
		# HDSatelit: numele din alte imagini (pluginurile scrise pentru ele): cmdList = cmdlist, windowTitle = titlul;
		# showScripts se tine (la noi comenzile se arata oricum)
		if altele:
			print("[Console] argumente necunoscute, ignorate: %s" % ", ".join(sorted(altele)))
		if cmdList is not None and cmdlist is None:
			cmdlist = cmdList
		if windowTitle:
			title = windowTitle
		if isinstance(cmdlist, str):
			cmdlist = [cmdlist]
		self.showScripts = showScripts
		self.installation = installation
		self.instalare = None
		self._inchisa = False
		self._salvareEsuata = False
		self._generatie = 0
		Screen.__init__(self, session)

		self.finishedCallback = finishedCallback
		self.closeOnSuccess = closeOnSuccess

		self["text"] = ScrollLabel("")
		self["actions"] = ActionMap(["WizardActions", "DirectionActions"], 
		{
			"ok": self.cancel,
			"back": self.cancel,
			"up": self["text"].pageUp,
			"down": self["text"].pageDown
		}, -1)
		
		self.cmdlist = cmdlist
		self.cmdList = cmdlist  # numele din alte imagini
		self.newtitle = title
		
		self.onShown.append(self.updateTitle)
		
		self.container = eConsoleAppContainer()
		# the output comes as bytes: decoded as it comes, a character cut between two reads waits for its end
		self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
		self.run = 0
		self.container.appClosed.append(self.runFinished)
		self.container.dataAvail.append(self.dataAvail)
		self.onLayoutFinish.append(self.startRun) # dont start before gui is finished
		self.onClose.append(self._inchideConsola)

	def updateTitle(self):
		self.setTitle(self.newtitle)

	def startRun(self):
		self["text"].setText(_("Execution Progress:") + "\n\n")
		if self.executeCommand(self.cmdlist[self.run]): #start of container application failed...
			self.runFinished(-1) # so we must call runFinished manual

	def executeCommand(self, cmd):
		if getattr(self, "_inchisa", True):
			return 0
		if isinstance(cmd, (list, tuple)):
			cmd = tuple(cmd)
		self._generatie += 1
		generatie = self._generatie
		if self.instalare is not None and self.instalare.stare == "salvare":
			self.instalare.anuleaza()
		if self.installation or instalareExterna(cmd):
			def gata(ok):
				if getattr(self, "_inchisa", True) or generatie != self._generatie:
					return
				if not ok:
					self._salvareEsuata = True
					self.dataAvail("\n" + eroareSalvareInstalare() + "\n")
					return
				if self._executa(cmd):
					self.runFinished(-1)
			self.instalare = PregatireInstalare(gata)
			self.instalare.porneste()
			return 0
		return self._executa(cmd)

	def _executa(self, cmd):
		try:
			# inside the try: the log (ePythonOutput) refuses a str with surrogates too
			print("Console: executing in run", self.run, " the command:", cmd)
			if isinstance(cmd, str):
				return self.container.execute(cmd)
			cmd = [str(x) for x in cmd]
			if not cmd:
				return -1
			return self.container.execute(cmd[0], *cmd)
		except (TypeError, ValueError) as e:
			# a file name that is not UTF-8 or a zero byte: counted as a failed start; an exception here would
			# come out of runFinished, which is called from C++, and stop enigma2
			print("Console: command refused:", e)
			return -1

	def runFinished(self, retval):
		if getattr(self, "_inchisa", True) or self._salvareEsuata:
			return
		# a cut character left at the end of a command is shown (as U+FFFD), not glued to the next command
		self.dataAvail(self._decoder.decode(b"", True))
		self.run += 1
		if self.run != len(self.cmdlist):
			if self.executeCommand(self.cmdlist[self.run]): #start of container application failed...
				self.runFinished(-1) # so we must call runFinished manual
		else:
			str = self["text"].getText()
			str += _("Execution finished!!");
			self["text"].setText(str)
			self["text"].lastPage()
			callback, closeOnSuccess = self.finishedCallback, self.closeOnSuccess
			if callback is not None:
				callback()
			if not retval and closeOnSuccess and not getattr(self, "_inchisa", True):
				self.cancel()

	def cancel(self):
		if self._salvareEsuata or (self.instalare is not None and self.instalare.stare == "salvare") or self.run == len(self.cmdlist):
			self.close()

	def _inchideConsola(self):
		self._inchisa = True
		if self.instalare is not None:
			self.instalare.anuleaza()
		for signal, callback in ((self.container.appClosed, self.runFinished), (self.container.dataAvail, self.dataAvail)):
			if callback in signal:
				signal.remove(callback)

	# numele din alte imagini ale tastelor (subclasele pluginurilor le cheama)
	def keyCancel(self):
		self.cancel()

	def keyPageUp(self):
		self["text"].pageUp()

	def keyPageDown(self):
		self["text"].pageDown()

	def dataAvail(self, data):
		if getattr(self, "_inchisa", True):
			return
		if isinstance(data, bytes):
			data = self._decoder.decode(data)
		if data:
			self["text"].setText(self["text"].getText() + data)
