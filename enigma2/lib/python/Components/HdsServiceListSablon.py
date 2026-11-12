# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsServiceListSablon.py (0.7.4): randul listei de canale desenat dupa sablonul temei, forma standardului OE-Alliance
# (documentatia pentru dezvoltatori: advanced/channel-templates, channel-styles, template-reference):
#   <template component="serviceList" name="..." fonts="Regular;28,Regular;23">
#     <mode name="services|bouquets|other" itemHeight="..."> <rectangle/> <panel layout="horizontal"> <pixmap index="Picon"/>
#       <text index="Number"/> <text index="ServiceName"/> <text index="Title1"/> <progress index="Progress"/> ...
# Se foloseste NUMAI cu o tema straina si numai cand config.channelSelection.screenStyle si widgetStyle aleg un sablon (din
# fabrica, ca si acolo, lista e cea clasica; alegerea o face pluginul de setari al temei). Lista ramane cea din C++
# (lib/service/listboxservice.cpp: navigarea, marcajele, mutarea, numerotarea cu semnele numerotate si numerele operatorului);
# aici se face numai continutul fiecarui rand desenat: setTemplateBuildFunc(functie(serviciu, steaguri, numar)).
# Parserul sabloanelor e cel al listelor cu sabloane XML (Components/Converter/XmlMultiContent.py).
from time import time

from enigma import eServiceCenter, eServiceReference, eEPGCache, iServiceInformation

from Components.Converter.XmlMultiContent import XmlMultiContent, umpleRand

# coloanele randului virtual al unui canal (numele din template-reference); sablonul le cere dupa nume
CAMPURI = ("ServiceName", "EntryName", "MarkerName", "FolderName", "Number", "Picon", "ServiceTypeImage", "CryptoImage",
	"RecordingIndicator", "FolderImage", "MarkerImage", "IsInBouquetImage", "ServiceResolutionImage", "Progress",
	"ProgressText", "Remain", "RemainDuration", "Elapsed", "ElapsedDuration", "ElapsedRemainDuration", "ServiceTypeName",
	"ProviderName")
EVENIMENT = ("Title", "ShortDescription", "ExtendedDescription", "Description", "StartTime", "EndTime", "StartEndTime",
	"Duration", "StartTimeDuration", "StartTimeEndTimeDuration", "Image", "ImageOrPicon")
SUFIXE = ("1", "2", "3", "P")
INDEX = {}
for _c in CAMPURI:
	INDEX[_c] = len(INDEX)
for _s in SUFIXE:
	for _c in EVENIMENT:
		INDEX[_c + _s] = len(INDEX)
COLOANE = len(INDEX)

# steagurile randului, ca in lib/service/listboxservice.h (row*)
SELECTAT, MARCAT, SEMN, SEMN_NUMEROTAT, CANAL, DOSAR, INREGISTRAT, TRANSMIS, INDISPONIBIL = 1, 2, 4, 8, 16, 32, 64, 128, 256

TTL_EPG = 30


def _ora(t):
	try:
		from time import localtime, strftime
		return strftime("%H:%M", localtime(t))
	except Exception:
		return ""


def _minute(sec):
	return "%d min" % max(0, int(round(sec / 60.0)))


def felulListei(root):
	"""modul sablonului pentru o radacina: "other" (o lista de dosare: buchetele, satelitii, furnizorii), "bouquets" (un
	buchet al omului) sau "services" (toate canalele, canalele unui satelit / furnizor)"""
	cale = root.getPath() if root is not None else ""
	if "FROM BOUQUET \"bouquets." in cale or "FROM BOUQUET 'bouquets." in cale:
		return "other"
	if ("FROM SATELLITES" in cale or "FROM PROVIDERS" in cale) and "satellitePosition ==" not in cale and "provider ==" not in cale:
		return "other"
	if "userbouquet." in cale or "FROM BOUQUET" in cale:
		return "bouquets"
	return "services"


def sablonAles():
	"""(elementul <template component="serviceList">, numele ecranului ales) cand tema straina aleasa si setarile cer
	lista dupa sablon; altfel (None, None)"""
	try:
		import skin
		from Components.config import config
		if not getattr(skin, "dosareSkinStraine", None):
			return None, None
		cs = getattr(config, "channelSelection", None)
		if cs is None or not cs.screenStyle.value or not cs.widgetStyle.value:
			return None, None
		return skin.componentTemplates.get("serviceList", cs.widgetStyle.value), cs.screenStyle.value
	except Exception as e:
		print("[HdsServiceListSablon] alegerea sablonului: %s" % e)
		return None, None


class SablonListaCanale(object):
	"""un <template component="serviceList"> citit pentru o latime de rand si o scara (resolution= al ecranului)"""

	def __init__(self, element, latime, scara=None):
		self.element = element
		self.latime = latime
		self.scara = scara
		self.parser = XmlMultiContent({"dom": None, "scara": scara, "itemWidth": latime})
		self.parser.indexNames = INDEX
		self.parser.dreptunghiPrimPlan = True
		self.fonturi = [self.parser._font(f) for f in (element.get("fonts") or "Regular;20").split(",") if f.strip()]
		self.moduri = {}
		self.culori = {}
		for mod in element.findall("mode"):
			self._citesteMod(mod)
		if not self.moduri:
			self._citesteMod(element, "services")
		self.epg = {}
		self.sigle = {}
		self.poze = {}

	def _citesteMod(self, mod, nume=None):
		nume = nume or mod.get("name", "services")
		try:
			ina = int(mod.get("itemHeight", self.element.get("itemHeight", "50")))
		except ValueError:
			ina = 50
		inaS = XmlMultiContent._ori(ina, self.parser._sy())
		elemente = []
		self.parser._elemente(mod, 0, 0, self.latime, inaS, elemente)
		self.moduri[nume] = (inaS, self.parser._tupluri(elemente))
		self.culori[nume] = dict((k, self.parser._culoare(mod.get(k))) for k in ("foregroundColor", "foregroundColorSelected",
			"recordColor", "recordColorSelected") if mod.get(k))

	def mod(self, nume):
		return self.moduri.get(nume) or self.moduri.get("services") or list(self.moduri.values())[0]

	# --- datele unui canal ---
	def _poza(self, cale):
		p = self.poze.get(cale, False)
		if p is False:
			try:
				from Tools.LoadPixmap import LoadPixmap
				from Tools.Directories import resolveFilename, SCOPE_CURRENT_SKIN
				p = LoadPixmap(resolveFilename(SCOPE_CURRENT_SKIN, cale), cached=True)
			except Exception:
				p = None
			self.poze[cale] = p
		return p

	def _sigla(self, ref):
		s = ref.toString()
		p = self.sigle.get(s, False)
		if p is False:
			p = None
			try:
				from Components.Renderer.Picon import getPiconName
				cale = getPiconName(s)
				if cale:
					from Tools.LoadPixmap import LoadPixmap
					p = LoadPixmap(cale, cached=True)
			except Exception:
				p = None
			if len(self.sigle) > 400:
				self.sigle.clear()
			self.sigle[s] = p
		return p

	def _evenimente(self, ref):
		s = ref.toString()
		acum = time()
		e = self.epg.get(s)
		if e is not None and acum - e[0] < TTL_EPG:
			return e[1]
		ev = []
		try:
			rez = eEPGCache.getInstance().lookupEvent(["BDTSE", (s, 0, -1, 720)]) or []
			ev = [x for x in rez if x and x[0]][:3]
		except Exception as err:
			print("[HdsServiceListSablon] ghidul: %s" % err)
		if len(self.epg) > 400:
			self.epg.clear()
		self.epg[s] = (acum, ev)
		return ev

	@staticmethod
	def _arata(nume):
		"""config.channelSelection.show* (pluginul de setari al temei); fara setare: da"""
		try:
			from Components.config import config
			s = getattr(config.channelSelection, nume, None)
			return True if s is None else bool(s.value)
		except Exception:
			return True

	def date(self, ref, steaguri, numar, nume=None):
		"""randul virtual al canalului (COLOANE valori, in ordinea din INDEX)"""
		r = [None] * COLOANE
		if nume is None:
			try:
				nume = eServiceCenter.getInstance().info(ref).getName(ref) or ""
			except Exception:
				nume = ""
			# semnele de evidentiere din numele canalelor (0x86 / 0x87) nu se arata
			nume = nume.replace("\x86", "").replace("\x87", "")
		dosar = bool(steaguri & DOSAR)
		semn = bool(steaguri & SEMN)
		for c in ("ServiceName", "EntryName"):
			r[INDEX[c]] = nume
		if semn:
			r[INDEX["MarkerName"]] = nume
			r[INDEX["MarkerImage"]] = self._poza("skin_default/icons/marker.png")
		if dosar:
			r[INDEX["FolderName"]] = nume
			r[INDEX["FolderImage"]] = self._poza("skin_default/icons/folder.png")
		r[INDEX["Number"]] = (numar or "") if self._arata("showNumber") else ""
		if steaguri & CANAL:
			sigla = self._sigla(ref) if self._arata("showPicon") else None
			r[INDEX["Picon"]] = sigla
			r[INDEX["ImageOrPicon1"]] = sigla
			if steaguri & INREGISTRAT:
				r[INDEX["RecordingIndicator"]] = self._poza("skin_default/icons/icon_rec.png")
			ev = self._evenimente(ref)
			acum = int(time())
			for i, x in enumerate(ev):
				suf = SUFIXE[i]
				inceput, durata = int(x[0] or 0), int(x[1] or 0)
				titlu, scurt, lung = x[2] or "", x[3] or "", x[4] if len(x) > 4 and x[4] else ""
				r[INDEX["Title" + suf]] = titlu
				r[INDEX["ShortDescription" + suf]] = scurt
				r[INDEX["ExtendedDescription" + suf]] = lung
				r[INDEX["Description" + suf]] = scurt or lung
				r[INDEX["StartTime" + suf]] = _ora(inceput)
				r[INDEX["EndTime" + suf]] = _ora(inceput + durata)
				r[INDEX["StartEndTime" + suf]] = "%s - %s" % (_ora(inceput), _ora(inceput + durata))
				r[INDEX["Duration" + suf]] = _minute(durata)
				r[INDEX["StartTimeDuration" + suf]] = "%s (%s)" % (_ora(inceput), _minute(durata))
				r[INDEX["StartTimeEndTimeDuration" + suf]] = "%s - %s (%s)" % (_ora(inceput), _ora(inceput + durata), _minute(durata))
				if i == 0 and durata > 0 and inceput <= acum < inceput + durata and self._arata("showProgress"):
					trecut = acum - inceput
					pr = max(0, min(100, trecut * 100 // durata))
					r[INDEX["Progress"]] = pr
					r[INDEX["ProgressText"]] = "%d%%" % pr
					r[INDEX["Remain"]] = "+" + _minute(inceput + durata - acum)
					r[INDEX["RemainDuration"]] = "+%s / %s" % (_minute(inceput + durata - acum), _minute(durata))
					r[INDEX["Elapsed"]] = _minute(trecut)
					r[INDEX["ElapsedDuration"]] = "%s / %s" % (_minute(trecut), _minute(durata))
					r[INDEX["ElapsedRemainDuration"]] = "%s / +%s / %s" % (_minute(trecut), _minute(inceput + durata - acum), _minute(durata))
		return tuple(r)

	def rand(self, numeMod, ref, steaguri, numar, nume=None):
		"""intrarea listei pentru un rand ([None, tuplu, ...]); culoarea numelui dupa starea randului"""
		ina, tupluri = self.mod(numeMod)
		culori = self.culori.get(numeMod, {})
		culoare = None
		if steaguri & INDISPONIBIL:
			culoare = 0x00808080
		elif steaguri & INREGISTRAT and not steaguri & SELECTAT:
			culoare = culori.get("recordColor")
		if culoare is not None:
			# culoarea numelui canalului (textele cu index="ServiceName"), inainte de umplere
			nume_i = INDEX["ServiceName"]
			tupluri = [t[:8] + (culoare, culoare) + t[10:] if t[0] == 0 and t[7] == nume_i and not isinstance(t[7], bool) else t
				for t in tupluri]
		rez = umpleRand(tupluri, self.date(ref, steaguri, numar, nume))
		if steaguri & MARCAT:
			# randul marcat (mutarea): un fundal pe tot randul, sub restul
			rez.insert(1, (0, 0, 0, self.latime, ina, 0, 0, "", None, None, MARCAT_FUNDAL, MARCAT_FUNDAL, None, None))
		return rez


MARCAT_FUNDAL = 0x00805a10
