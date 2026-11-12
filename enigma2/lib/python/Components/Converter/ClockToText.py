# Modificat de moneasoftware.com si hdsatelit.com, 2026
#
# Argumentele: cele de dinainte dau acelasi text (Default "21:05", WithSeconds, InMinutes "%d min", Date, AsLength, Timestamp,
# Format:...). In plus, toate cuvintele pe care le folosesc temele si pluginurile scrise pentru imaginile OE-Alliance: Time,
# TimeShort, Mixed, AsLengthHours, AsLengthSeconds, LongDate, FullDate, ShortDate, ShortFullDate, LongFullDate, Full, DateNoDay...,
# DateShortDay..., DateTime, Display*, VFD*; mai multe cuvinte despartite de "," sau ";" (sau "Parse<c>" la inceput, cu
# despartitorul <c>), "Separator:<text>" intre cele doua ore ale unui interval (sursa da o pereche: inceput, sfarsit), iar
# "NoSpace" si "Proportional" se trec cu vederea. Ceasul e de 24 de ore; zilele si lunile in limba meniului (dataText).
# Un cuvant necunoscut da ora, ca pana acum.
from .Converter import Converter
from time import localtime, strftime
from Components.Element import cached

# Numele zilelor si lunilor (%A %a %B %b %c) in limba meniului, din cataloagele noastre: strftime le da in engleza in orice
# limba (imaginea nu are datele de limba ale glibc). La orice eroare, strftime ca inainte.
try:
	from Tools.HdsNumeData import dataText as _dataText
except Exception:
	_dataText = None


def dataText(format, t):
	if _dataText is not None:
		try:
			return _dataText(format, t)
		except Exception:
			pass
	return strftime(format, t)


def _ora(t):
	return "%02d:%02d" % (t.tm_hour, t.tm_min)


def _oraSecunde(t):
	return "%2d:%02d:%02d" % (t.tm_hour, t.tm_min, t.tm_sec)


def _durata(fel, secunde):
	# AsLength, InMinutes si Timestamp ca pana acum (si cu numere negative); cele noi, goale la negativ
	if fel in ("AsLengthHours", "AsLengthSeconds") and secunde < 0:
		return ""
	if fel == "AsLength":
		return "%d:%02d" % (secunde // 60, secunde % 60)
	if fel == "AsLengthHours":
		return "%d:%02d" % (secunde // 3600, secunde // 60 % 60)
	if fel == "AsLengthSeconds":
		return "%d:%02d:%02d" % (secunde // 3600, secunde // 60 % 60, secunde % 60)
	if fel == "InMinutes":
		return "%d min" % (secunde // 60)
	return str(secunde)  # Timestamp


# cuvintele cu data: formatul strftime (zilele si lunile traduse de dataText)
FORMATE_DATA = {
	"Date": "%A %B %d, %Y",
	"DateNoDay": "%d %B %Y",
	"DateNoDayNoYear": "%d %B",
	"DateNoDayShortMonth": "%d %b %Y",
	"DateNoDayShortMonthNoYear": "%d %b",
	"DateNoYear": "%A %d %B",
	"DateShortDay": "%a %d %B %Y",
	"DateShortDayNoMonthNoYear": "%a %d",
	"DateShortDayShortMonth": "%a %d %b %Y",
	"DateShortDayShortMonthNoYear": "%a %d %b",
	"DateTime": "%A %d %B %Y %H:%M:%S",
	"DateTimeShortDayShortMonthNoSeconds": "%a %d %b %Y %H:%M",
	"DisplayDate": "%d %b",
	"DisplayDayDate": "%a %d %b",
	"Full": "%a %d %b %H:%M",
	"FullDate": "%a %d %B %Y",
	"LongDate": "%A %d %B",
	"LongFullDate": "%a %d %b %Y %H:%M",
	"ShortDate": "%a %d %b",
	"ShortFullDate": "%a %d %b %Y",
	"VFD": "%d.%m %H:%M",
	"VFD08": "%H:%M:%S",
	"VFD12": "%d.%m %H:%M",
	"VFD14": "%d.%m. %H:%M",
	"VFD18": "%a %d.%m %H:%M",
}
ORE = frozenset(("", "Default", "Display", "DisplayTime", "TimeShort", "TimeShortNoMeridiem"))
ORE_SECUNDE = frozenset(("WithSeconds", "Time", "TimeLong", "TimeNoMeridiem", "Mixed", "TimeMixed"))
DURATE = frozenset(("InMinutes", "AsLength", "AsLengthHours", "AsLengthSeconds", "Timestamp"))
IGNORATE = ("NoSpace", "Proportional", "Parse")


class ClockToText(Converter, object):
	DEFAULT = 0
	WITH_SECONDS = 1
	IN_MINUTES = 2
	DATE = 3
	FORMAT = 4
	AS_LENGTH = 5
	TIMESTAMP = 6

	TIPURI = {"WithSeconds": WITH_SECONDS, "InMinutes": IN_MINUTES, "Date": DATE, "AsLength": AS_LENGTH, "Timestamp": TIMESTAMP}

	def __init__(self, type):
		Converter.__init__(self, type)
		self.separator = " - "
		self.fmt_string = ""
		# cuvintele, in ordine: ("Format", sir) sau (cuvant, None); al doilea se foloseste pentru a doua ora a unui interval
		self.cuvinte = []
		text = (type or "").lstrip()
		if text.startswith("Parse") and len(text) > 5:
			parti = text[6:].split(text[5])
		elif text.startswith("Format"):
			# virgula ramane in format ("%d.%m, %H:%M"); mai multe formate numai cu ";"
			parti = text.split(";")
		else:
			parti = text.replace(",", ";").split(";")
		for p in (x.lstrip() for x in parti):
			if p.startswith("Format"):
				self.cuvinte.append(("Format", p[7:]))
			elif p.startswith("Separator"):
				# spatiile din jurul despartitorului raman ("Separator: / ")
				self.separator = p[10:]
			elif p.strip() and not p.startswith(IGNORATE):
				self.cuvinte.append((p.strip(), None))
		if not self.cuvinte:
			self.cuvinte.append(("Default", None))
		primul, sir = self.cuvinte[0]
		if primul == "Format":
			self.type = self.FORMAT
			self.fmt_string = sir
		else:
			self.type = self.TIPURI.get(primul, self.DEFAULT)

	def _text(self, cuvant, time):
		fel, sir = cuvant
		if fel in DURATE:
			return _durata(fel, time)
		t = localtime(time)
		if fel == "Format":
			spos = sir.find('%')
			if spos > 0:
				return str(sir[:spos] + dataText(sir[spos:], t))
			return dataText(sir, t)
		if fel in ORE_SECUNDE:
			return _oraSecunde(t)
		format = FORMATE_DATA.get(fel)
		if format is not None:
			return dataText(format, t)
		return _ora(t)

	@cached
	def getText(self):
		time = self.source.time
		if time is None:
			return ""
		if isinstance(time, tuple):
			# interval (inceput, sfarsit): fiecare ora cu cuvantul ei, ultimul cuvant pentru restul
			n = len(self.cuvinte) - 1
			return self.separator.join(self._text(self.cuvinte[min(i, n)], x) for i, x in enumerate(time) if x is not None)
		return self._text(self.cuvinte[0], time)

	text = property(getText)
