# Modificat de moneasoftware.com si hdsatelit.com, 2026
from xml.sax import make_parser
from xml.sax.handler import ContentHandler

from os import environ, unlink, symlink
import time

class Timezones:
	class parseTimezones(ContentHandler):
		def __init__(self, timezones):
			self.isPointsElement, self.isReboundsElement = 0, 0
			self.timezones = timezones
	
		def startElement(self, name, attrs):
			if (name == "zone"):
				self.timezones.append((attrs.get('name',""), attrs.get('zone',"")))
	
	def __init__(self):
		self.timezones = []
		
		self.readTimezonesFromFile()

	def readTimezonesFromFile(self):
		parser = make_parser()
		
		try:
			timezonesHandler = self.parseTimezones(self.timezones)
			parser.setContentHandler(timezonesHandler)
			parser.parse('/etc/timezone.xml')
		except:
			pass
		
		if len(self.timezones) == 0:
			self.timezones = [("UTC", "UTC")]
		
	def activateTimezone(self, index):
		if len(self.timezones) <= index:
			return
		
		environ['TZ'] = self.timezones[index][1]
		try:
			unlink("/etc/localtime")
		except OSError:
			pass
		try:
			symlink("/usr/share/zoneinfo/%s" %(self.timezones[index][1]), "/etc/localtime")
		except OSError:
			pass
		try:
			time.tzset()
		except:
			from enigma import e_tzset
			e_tzset()
		
	def getTimezoneList(self):
		return [ str(x[0]) for x in self.timezones ]

	def getDefaultTimezone(self):
		# Implicit Romania (Bucuresti) sau Berlin / Europa Centrala
		preferate = ("Europe/Bucharest", "Europe/Berlin", "Europe/Rome", "Europe/Paris", "Europe/Athens")
		for pref in preferate:
			for (a, b) in self.timezones:
				if b == pref:
					return a
		# Daca nu gaseste exact, cauta orice zona europeana
		for (a, b) in self.timezones:
			if b.startswith("Europe/"):
				return a
		# Niciodata Samoa / Pago Pago: cauta UTC sau primul
		for (a, b) in self.timezones:
			if b == "UTC":
				return a
		return self.timezones[0][0]

	def autoDetectTimezone(self):
		"""Detecteaza fusul orar prin IP/GeoIP daca exista conexiune internet (timeout scurt, fara blocaj)."""
		import threading
		def _worker():
			try:
				import json
				try:
					from urllib.request import urlopen, Request
				except ImportError:
					from urllib2 import urlopen, Request
				req = Request("http://ip-api.com/json/?fields=timezone", headers={"User-Agent": "HDSatelit-E2"})
				resp = urlopen(req, timeout=2.5)
				data = json.loads(resp.read().decode("utf-8"))
				tz_name = data.get("timezone")
				if tz_name:
					for idx, (a, b) in enumerate(self.timezones):
						if b == tz_name:
							print("[Timezones] GeoIP a detectat fusul orar: %s (%s)" % (b, a))
							from Components.config import config
							# HDSatelit: hasattr(config, ...) NU e sigur -- ConfigSubsection.__getattr__
							# arunca KeyError (nu AttributeError) pentru o cheie lipsa, iar hasattr() din Python 3
							# prinde doar AttributeError.
							if "timezone" in config.content.items and "val" in config.timezone.content.items:
								config.timezone.val.value = a
								config.timezone.val.save()
							self.activateTimezone(idx)
							break
			except Exception as e:
				pass
		t = threading.Thread(target=_worker)
		t.daemon = True
		t.start()

timezones = Timezones()

