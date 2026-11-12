# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .Source import Source
from enigma import eTimer

class FrontendStatus(Source):
	"""Starea tunerului (nivel, calitate, BER, prins) pentru elementele temei legate de ea.

	Pe serviciul redat (service_source, ca sursa globala din SessionGlobals) citeste numai cat se vede ceva legat de ea:
	ceasul porneste la prima aratare (doSuspend(0)) si se opreste la ascunderea ultimului element (doSuspend(1)).
	Inainte pornea din constructor; sursa din SessionGlobals, de care tema HD Satelit nu leaga nimic, nu primea niciodata
	doSuspend(1) (Element incepe suspendat, doSuspend vine numai la schimbare) si cerea starea tunerului la fiecare
	secunda, pentru nimeni (6 cereri pe secunda, pe I2C la Vu+). Cu un tuner dat (frontend_source: ecranele de acordare
	ale pluginurilor, deschise la cerere, care pot citi .snr / .lock direct, fara element legat) ceasul porneste din
	constructor, ca inainte."""
	def __init__(self, service_source = None, frontend_source = None, update_interval = 1000):
		Source.__init__(self)
		self.update_interval = update_interval
		self.service_source = service_source
		self.frontend_source = frontend_source
		self.invalidate()
		self.poll_timer = eTimer()
		self.poll_timer.callback.append(self.updateFrontendStatus)
		self._mereu = frontend_source is not None
		if self._mereu:
			self.poll_timer.start(update_interval, True)

	def invalidate(self):
		self.snr = self.agc = self.ber = self.lock = self.snr_db = None

	def updateFrontendStatus(self):
		status = self.getFrontendStatus()
		if not status:
			self.invalidate()
		else:
			self.snr = status.get("tuner_signal_quality")
			self.snr_db = status.get("tuner_signal_quality_db")
			self.agc = status.get("tuner_signal_power")
			self.ber = status.get("tuner_bit_error_rate")
			self.lock = status.get("tuner_locked")
		self.changed((self.CHANGED_ALL, ))
		if self._mereu or not self.suspended:
			self.poll_timer.start(self.update_interval, True)

	def getFrontendStatus(self):
		if self.frontend_source:
			frontend = self.frontend_source()
			dict = { }
			if frontend:
				frontend.getFrontendStatus(dict)
			return dict
		elif self.service_source:
			service = self.service_source()
			feinfo = service and _feServiciu(service)
			return feinfo and feinfo.getFrontendStatus()
		else:
			return None

	def doSuspend(self, suspended):
		if suspended:
			self.poll_timer.stop()
		else:
			# Element pune starea noua abia dupa doSuspend: ceasul se porneste aici, nu in updateFrontendStatus
			self.updateFrontendStatus()
			self.poll_timer.start(self.update_interval, True)

	def destroy(self):
		self.poll_timer.stop()
		self.poll_timer.callback.remove(self.updateFrontendStatus)
		Source.destroy(self)


def _feServiciu(service):
	"""frontendInfo al serviciului redat; la Stream Relay, al tunerului care tine canalul (Hds.DabT2.server8001)."""
	try:
		from Hds.DabT2.server8001 import frontend_serviciu
	except Exception:
		return service.frontendInfo()
	return frontend_serviciu(service)
