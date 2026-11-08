# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# International.py: pluginurile intreaba de aici limba si tara; aici raspunde Components.Language.
from Components.Language import language

_ALPHA3 = {"AT": "AUT", "BE": "BEL", "BG": "BGR", "BR": "BRA", "CA": "CAN", "CH": "CHE", "CZ": "CZE", "DE": "DEU", "DK": "DNK", "EE": "EST", "EN": "GBR", "ES": "ESP", "FI": "FIN", "FR": "FRA", "GB": "GBR", "GR": "GRC",
	"HR": "HRV", "HU": "HUN", "IE": "IRL", "IT": "ITA", "LT": "LTU", "LV": "LVA", "MD": "MDA", "NL": "NLD", "NO": "NOR", "PL": "POL", "PT": "PRT", "RO": "ROU", "RS": "SRB", "RU": "RUS", "SE": "SWE", "SI": "SVN", "SK": "SVK",
	"TR": "TUR", "UA": "UKR", "US": "USA"}


class International:
	def addCallback(self, functie):
		language.addCallback(functie)

	def getLocale(self):
		return language.getLanguage()

	def getLanguage(self, locale=None):
		return (locale or language.getLanguage()).split("_")[0]

	def getCountry(self, locale=None):
		parti = (locale or language.getLanguage()).split("_")
		return parti[1] if len(parti) > 1 else ""

	def getCountryAlpha3(self, country=None):
		return _ALPHA3.get((country or self.getCountry()).upper(), "")

	def getCountryTranslated(self, country=None):
		return country or self.getCountry()

	def getLanguageTranslated(self, lang=None):
		return lang or self.getLanguage()


international = International()
