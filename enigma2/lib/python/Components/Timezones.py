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

	# Fusul dupa internet nu mai e aici (intreba ip-api.com o data, la pornirea interfetei, si suprascria si fusul ales
	# de om): Components/HdsFusTara.py, de la serverul nostru, numai cat config.timezone.automat e Da. Numele vechi ramane
	# pentru cine il cheama: aceeasi aflare, nu alta cerere.
	def autoDetectTimezone(self):
		try:
			from Components import HdsFusTara
			HdsFusTara.porneste()
		except Exception as e:
			print("[Timezones] fusul dupa internet: %r" % (e,))

timezones = Timezones()

