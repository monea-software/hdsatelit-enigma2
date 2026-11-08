# Modificat de moneasoftware.com si hdsatelit.com, 2026
import gettext
import os

from Tools.Directories import SCOPE_LANGUAGE, resolveFilename

from . import language_cache

# Limbile din lista de limbi (pe televizor, in asistentul de pornire si in interfata web): numai cele traduse complet,
# cu toate textele HD Satelit. Celelalte raman mai jos, cu catalogul lor (po/Makefile.am), dar nu se arata; o limba
# tradusa complet se aduce inapoi scriindu-i codul aici, intr-un singur loc.
LIMBI_COMPLETE = ("ro_RO", "en_EN", "de_DE", "fr_FR", "es_ES", "it_IT", "hu_HU", "cs_CZ", "pl_PL", "pt_PT", "nl_NL",
	"ru_RU", "tr_TR",
	"sk_SK", "hr_HR", "sr_YU", "sl_SI", "el_GR", "sv_SE", "da_DK", "no_NO", "fi_FI", "et_EE", "lt_LT", "lv_LV",
	"ca_AD", "is_IS", "fy_x-FY", "uk_UA", "ar_AE")
# Limba meniurilor cand cea salvata (config.osd.language) e ascunsa sau necunoscuta, ca in Converter/HdsLang.py
# (limba necunoscuta: engleza). Valoarea salvata nu se schimba: tara si limba pistelor o folosesc mai departe, iar cand
# limba ei intra in LIMBI_COMPLETE, meniurile revin singure in ea.
LIMBA_REZERVA = "en_EN"

def _puneNgettext(sursa):
	"""ngettext si pgettext pe langa _, ca in celelalte imagini: pluginurile le cheama fara sa le importe"""
	import builtins
	for nume in ("ngettext", "pgettext"):
		functie = getattr(sursa, nume, None)
		if functie is not None:
			setattr(builtins, nume, functie)

def cataloageDisponibile():
	"""Limbile („tr”, „ro” ...) care au catalogul (po/<lang>/LC_MESSAGES/enigma2.mo) pe receptor, sau None cand dosarul
	nu are niciun catalog (pe PC, in probe): atunci nu se filtreaza nimic."""
	try:
		baza = resolveFilename(SCOPE_LANGUAGE, "")
		gasite = set(n for n in os.listdir(baza) if os.path.isfile(os.path.join(baza, n, "LC_MESSAGES", "enigma2.mo")))
	except Exception:
		return None
	return gasite or None


def areCatalog(lang, cataloage=None):
	"""True cand catalogul limbii e pe receptor (sau cand nu se poate sti). Pe receptoarele cu memorie mica (Vu+ Solo SE)
	fiecare limba e un pachet separat in feed (enigma2-hdsatelit-po-<limba>): o limba fara catalog nu se arata in liste
	si nu se activeaza. Defectul gasit pe 07.11.2026 (primul Solo SE, Ozgur): turca aleasa fara catalog lasa traducerea
	goala, deci textele HD Satelit ieseau in romana (cheile), cele de baza in engleza, iar tema in turca."""
	if cataloage is None:
		cataloage = cataloageDisponibile()
	return cataloage is None or lang in cataloage


def limbaInterfata():
	"""Limba in care sunt textele interfetei acum („en_EN” cand cea salvata nu are catalog sau e ascunsa), "" inainte de
	prima activare. Tema (Converter/HdsCommon), separatorul zecimal (HdsGrade) si fontul (HdsFontInterfata) o folosesc pe
	ea, nu config.osd.language, ca tot ecranul sa fie in aceeasi limba; config.osd.language ramane alegerea omului
	(limba pistelor, a subtitrarilor, tara)."""
	try:
		a = language.activeLanguage
	except NameError:
		return ""
	return a if isinstance(a, str) else ""


class Language:
	def __init__(self):
		gettext.install('enigma2', resolveFilename(SCOPE_LANGUAGE, ""))
		_puneNgettext(gettext)
		self.activeLanguage = 0
		self.lang = {}
		self.langlist = []
		# toate limbile cu catalog, si cele ascunse (pentru language_cache.py, precalcLanguageList)
		self.toate = {}
		self.toatelist = []
		# limbile cu catalog pe receptor (o singura citire a dosarului po; None = nu se filtreaza)
		self.cataloage = cataloageDisponibile()
		# FIXME make list dynamically
		# name, iso-639 language, iso-3166 country. Please don't mix language&country!
		# also, see "precalcLanguageList" below on how to re-create the language cache after you added a language
		self.addLanguage(_("English"), "en", "EN")
		self.addLanguage(_("German"), "de", "DE")
		self.addLanguage(_("Arabic"), "ar", "AE")
		self.addLanguage(_("Catalan"), "ca", "AD")
		self.addLanguage(_("Croatian"), "hr", "HR")
		self.addLanguage(_("Czech"), "cs", "CZ")
		self.addLanguage(_("Danish"), "da", "DK")
		self.addLanguage(_("Dutch"), "nl", "NL")
		self.addLanguage(_("Estonian"), "et", "EE")
		self.addLanguage(_("Finnish"), "fi", "FI")
		self.addLanguage(_("French"), "fr", "FR")
		self.addLanguage(_("Greek"), "el", "GR")
		self.addLanguage(_("Hungarian"), "hu", "HU")
		self.addLanguage(_("Lithuanian"), "lt", "LT")
		self.addLanguage(_("Latvian"), "lv", "LV")
		self.addLanguage(_("Icelandic"), "is", "IS")
		self.addLanguage(_("Italian"), "it", "IT")
		self.addLanguage(_("Norwegian"), "no", "NO")
		self.addLanguage(_("Polish"), "pl", "PL")
		self.addLanguage(_("Portuguese"), "pt", "PT")
		self.addLanguage(_("Romanian"), "ro", "RO")
		self.addLanguage(_("Russian"), "ru", "RU")
		self.addLanguage(_("Serbian"), "sr", "YU")
		self.addLanguage(_("Slovakian"), "sk", "SK")
		self.addLanguage(_("Slovenian"), "sl", "SI")
		self.addLanguage(_("Spanish"), "es", "ES")
		self.addLanguage(_("Swedish"), "sv", "SE")
		self.addLanguage(_("Turkish"), "tr", "TR")
		self.addLanguage(_("Ukrainian"), "uk", "UA")
		self.addLanguage(_("Frisian"), "fy", "x-FY") # there is no separate country for frisian

		self.callbacks = []

	def addLanguage(self, name, lang, country):
		try:
			cheie = str(lang + "_" + country)
			self.toate[cheie] = ((_(name), lang, country))
			self.toatelist.append(cheie)
			# numai limbile traduse complet si cu catalogul pe receptor (areCatalog)
			if cheie in LIMBI_COMPLETE and areCatalog(lang, self.cataloage):
				self.lang[cheie] = self.toate[cheie]
				self.langlist.append(cheie)
		except:
			print("Language " + str(name) + " not found")

	def activateLanguage(self, index):
		if index not in self.lang:
			# limba ascunsa (nu e in LIMBI_COMPLETE), fara catalog pe receptor sau necunoscuta: meniurile in limba de
			# rezerva (sau in prima limba cu catalog, daca nici ea nu e), toate, nu jumatate in cheile textelor
			rezerva = LIMBA_REZERVA if LIMBA_REZERVA in self.lang else (self.langlist[0] if self.langlist else LIMBA_REZERVA)
			print("[Language] limba %r nu e in lista (ascunsa sau fara catalog), meniurile sunt in %s" % (index, rezerva))
			index = rezerva
		self._activeaza(index)

	def _activeaza(self, index):
		try:
			lang = self.toate[index]
			print("Activating language " + lang[0])
			catalog = gettext.translation('enigma2', resolveFilename(SCOPE_LANGUAGE, ""), languages=[lang[1]])
			catalog.install()
			_puneNgettext(catalog)
			self.activeLanguage = index
			for x in self.callbacks:
				x()
		except:
			print("Selected language does not exist!")

	def activateLanguageIndex(self, index):
		if index < len(self.langlist):
			self.activateLanguage(self.langlist[index])

	def getLanguageList(self, suplimentare=False):
		# Un catalog nou de pe stick apare fara a salva o limba inexistenta.
		self.cataloage = cataloageDisponibile()
		self.langlist = [x for x in self.toatelist if x in LIMBI_COMPLETE and
			areCatalog(self.toate[x][1], self.cataloage)]
		self.lang = {x: self.toate[x] for x in self.langlist}
		if suplimentare:
			try:
				from Components import HdsParteaDoua as P
				if P.citesteConf() and P.radacinaNand():
					return [(x, self.toate[x]) for x in self.toatelist if x in LIMBI_COMPLETE]
			except (ImportError, OSError):
				pass
		return [(x, self.lang[x]) for x in self.langlist]

	def getActiveLanguage(self):
		return self.activeLanguage
	
	def getActiveLanguageIndex(self):
		idx = 0
		for x in self.langlist:
			if x == self.activeLanguage:
				return idx
			idx += 1
		return None			

	def getLanguage(self):
		try:
			return str(self.lang[self.activeLanguage][1]) + "_" + str(self.lang[self.activeLanguage][2])
		except:
			return ''

	def addCallback(self, callback):
		self.callbacks.append(callback)

	def precalcLanguageList(self):
		# excuse me for those T1, T2 hacks please. The goal was to keep the language_cache.py as small as possible, *and* 
		# don't duplicate these strings.
		T1 = _("Please use the UP and DOWN keys to select your language. Afterwards press the OK button.")
		T2 = _("Language selection")
		l = open("language_cache.py", "w", encoding="utf-8")
		print("# -*- coding: UTF-8 -*-", file=l)
		print("LANG_TEXT = {", file=l)
		# toate limbile, si cele ascunse: o limba adusa inapoi in LIMBI_COMPLETE isi are deja numele
		for language in self.toatelist:
			self._activeaza(language)
			print('"%s": {' % language, file=l)
			for name, lang, country in list(self.toate.values()):
				print('\t"%s_%s": "%s",' % (lang, country, _(name)), file=l)

			print('\t"T1": "%s",' % (_(T1)), file=l)
			print('\t"T2": "%s",' % (_(T2)), file=l)
			print('},', file=l)
		print("}", file=l)

language = Language()
