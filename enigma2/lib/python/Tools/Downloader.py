# Modificat de moneasoftware.com si hdsatelit.com, 2026
from twisted.internet import reactor, defer
from twisted.python import failure

class downloadWithProgress:
	"""start() da un Deferred. Merge prin DownloadWithProgress: pe Python 3 si cu twisted de acum drumul vechi nu mai descarca (client._parse nu mai exista, status e in octeti)."""
	def __init__(self, url, outputfile, contextFactory=None, *args, **kwargs):
		self.lucru = DownloadWithProgress(url.decode("utf-8") if isinstance(url, bytes) else url, outputfile)
		self.deferred = defer.Deferred()
		self.lucru.addEnd(self.deferred.callback)
		self.lucru.addError(lambda e: self.deferred.errback(failure.Failure(e)))

	def start(self):
		self.lucru.start()
		return self.deferred

	def stop(self):
		self.lucru.stop()

	def addProgress(self, progress_callback):
		self.lucru.addProgress(progress_callback)


class DownloadWithProgress:
	"""Forma ceruta de pluginuri: addProgress, addEnd, addError, setAgent, start, stop. Descarcarea merge pe un fir, callback-urile pe firul principal."""
	def __init__(self, url, outputFile):
		self.url = url
		self.outputFile = outputFile
		self.userAgent = "Enigma2"
		self.progressCallback = None
		self.endCallback = None
		self.errorCallback = None
		self.stopFlag = False
		self.progress = 0
		self.totalSize = 0

	def setAgent(self, userAgent):
		self.userAgent = userAgent

	def addProgress(self, progressCallback):
		self.progressCallback = progressCallback

	def addEnd(self, endCallback):
		self.endCallback = endCallback

	def addError(self, errorCallback):
		self.errorCallback = errorCallback

	def start(self):
		reactor.callInThread(self._lucreaza)
		return self

	def stop(self):
		self.stopFlag = True

	def _lucreaza(self):
		from urllib.request import Request, urlopen
		try:
			with urlopen(Request(self.url, None, {"User-agent": self.userAgent}), timeout=30) as sursa, open(self.outputFile, "wb") as tinta:
				self.totalSize = int(sursa.headers.get("Content-Length", 0) or 0)
				while not self.stopFlag:
					bucata = sursa.read(65536)
					if not bucata:
						break
					tinta.write(bucata)
					self.progress += len(bucata)
					if self.progressCallback:
						reactor.callFromThread(self.progressCallback, self.progress, self.totalSize)
			if self.stopFlag:
				return
			if self.endCallback:
				reactor.callFromThread(self.endCallback, self.outputFile)
		except Exception as e:
			if self.errorCallback:
				reactor.callFromThread(self.errorCallback, e)
