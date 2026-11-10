# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# CIHelper.py: alocarea modulelor CI pe canale, ceruta de pluginul de alocare CI al altor imagini (06.11.2026, lotul module-lipsa-071).
# Pluginul scrie pentru fiecare slot /etc/enigma2/ci<slot>.xml (<ci><slot><id>, <caid id="0x..."/>, <provider name dvbnamespace/>,
# <service name ref/>) si cheama cihelper.load_ci_assignment() la pornire si load_ci_assignment(force=True) dupa salvare. Aici fisierele
# se citesc si regulile se dau modulului CI prin eDVBCIInterfaces.setDescrambleRules(slot, (servicii, (furnizor, namespace), caid)),
# functia pe care imaginea o are deja (lib/dvb_ci/dvbci.cpp). Un fisier lipsa sau stricat lasa slotul neatins. Nu arunca.
import os
import re
import tempfile
import hashlib
import threading
from xml.etree.ElementTree import parse, fromstring, Element, SubElement, ElementTree

DOSAR = "/etc/enigma2"
MAX_REGULI = 512
_REF_DVB = re.compile(r"1:0:(?:[0-9a-fA-F]{1,8}:){8}\Z")
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\ud800-\udfff]")
_EDITOR_LOCK = threading.RLock()
_neaplicate = {}


class AlocareSchimbata(ValueError):
	pass


class AlocareNeaplicata(RuntimeError):
	def __init__(self, revizie):
		super().__init__("CI")
		self.revizie = revizie


def caidDinText(text):
	"""CAID-ul scris de om este mereu hexazecimal."""
	if not isinstance(text, str) or not re.fullmatch(r"(?:0[xX])?[0-9a-fA-F]{1,4}", text.strip()):
		raise ValueError("CAID")
	numar = int(text.strip(), 16)
	if not 0 < numar <= 0xffff:
		raise ValueError("CAID")
	return numar


def _text(text, maxim=256):
	if not isinstance(text, str) or not text.strip() or len(text) > maxim or _CONTROL.search(text):
		raise ValueError("text")
	return text.strip()


def valideazaAlocarea(reguli):
	"""Aceeasi verificare pentru televizor si web, inainte de scriere."""
	if not isinstance(reguli, dict) or set(reguli) != {"servicii", "furnizori", "caid"}:
		raise ValueError("reguli")
	rezultat = {"servicii": [], "furnizori": [], "caid": []}
	for fel in rezultat:
		if not isinstance(reguli[fel], list) or len(reguli[fel]) > MAX_REGULI:
			raise ValueError("reguli")
	for serviciu in reguli["servicii"]:
		if not isinstance(serviciu, dict) or set(serviciu) != {"ref", "name"}:
			raise ValueError("serviciu")
		ref = _text(serviciu["ref"], 150)
		if not _REF_DVB.fullmatch(ref):
			raise ValueError("serviciu")
		nou = {"ref": ref, "name": _text(serviciu["name"])}
		if not any(s["ref"] == ref for s in rezultat["servicii"]):
			rezultat["servicii"].append(nou)
	for furnizor in reguli["furnizori"]:
		if not isinstance(furnizor, dict) or set(furnizor) != {"name", "namespace"}:
			raise ValueError("furnizor")
		ns = furnizor["namespace"]
		if type(ns) is not int or not 0 <= ns <= 0xffffffff:
			raise ValueError("namespace")
		nou = {"name": _text(furnizor["name"]), "namespace": ns}
		if nou not in rezultat["furnizori"]:
			rezultat["furnizori"].append(nou)
	for caid in reguli["caid"]:
		if type(caid) is not int or not 0 < caid <= 0xffff:
			raise ValueError("CAID")
		if caid not in rezultat["caid"]:
			rezultat["caid"].append(caid)
	return rezultat


def citesteDetalii(slot):
	return citesteEditor(slot)["reguli"]


def citesteEditor(slot):
	"""Regulile si revizia provin din aceeasi citire a fisierului."""
	if type(slot) is not int or not 0 <= slot < 4:
		raise ValueError("slot")
	cale = os.path.join(DOSAR, "ci%d.xml" % slot)
	with _EDITOR_LOCK:
		try:
			with open(cale, "rb") as fisier:
				continut = fisier.read()
		except FileNotFoundError:
			continut = None
		revizie = hashlib.sha256(b"lipsa" if continut is None else continut).hexdigest()
		reguli = _detalii(continut)
		return {"reguli": reguli, "revizie": revizie, "neaplicata": _neaplicate.get(slot) == revizie}


def _detalii(continut):
	reguli = {"servicii": [], "furnizori": [], "caid": []}
	if continut is None:
		return reguli
	for nod in fromstring(continut).findall("slot"):
		for serviciu in nod.findall("service"):
			ref = serviciu.get("ref", "")
			reguli["servicii"].append({"ref": ref, "name": serviciu.get("name") or ref})
		for furnizor in nod.findall("provider"):
			reguli["furnizori"].append({"name": furnizor.get("name", ""),
				"namespace": _numar(furnizor.get("dvbnamespace"))})
		for caid in nod.findall("caid"):
			reguli["caid"].append(_numar(caid.get("id")))
	return valideazaAlocarea(reguli)


def _verificaRevizie(slot, revizie):
	if not isinstance(revizie, str) or not re.fullmatch(r"[0-9a-f]{64}", revizie):
		raise ValueError("revizie")
	if citesteEditor(slot)["revizie"] != revizie:
		raise AlocareSchimbata("revizie")


def salveazaEditor(slot, reguli, revizie):
	"""Un editor vechi nu inlocuieste o salvare mai noua TV sau web."""
	with _EDITOR_LOCK:
		_verificaRevizie(slot, revizie)
		salveazaAlocarea(slot, reguli)
		return citesteEditor(slot)


def reaplicaAlocarea(slot, revizie):
	"""Reincearca numai aplicarea starii salvate, fara rescrierea fisierului."""
	with _EDITOR_LOCK:
		_verificaRevizie(slot, revizie)
		if not os.path.isfile(os.path.join(DOSAR, "ci%d.xml" % slot)):
			raise ValueError("reguli")
		_aplicaAlocarea(slot)
		return citesteEditor(slot)


def _aplicaAlocarea(slot):
	try:
		aplicata = cihelper.load_ci_assignment(force=True).get(slot, False)
	except Exception:
		aplicata = False
	if not aplicata:
		revizie = citesteEditor(slot)["revizie"]
		_neaplicate[slot] = revizie
		raise AlocareNeaplicata(revizie)
	_neaplicate.pop(slot, None)


def salveazaAlocarea(slot, reguli):
	"""Scriere atomica, apoi reincarcarea existenta, fara repornire."""
	with _EDITOR_LOCK:
		return _scrieAlocarea(slot, reguli)


def _scrieAlocarea(slot, reguli):
	if type(slot) is not int or not 0 <= slot < 4:
		raise ValueError("slot")
	reguli = valideazaAlocarea(reguli)
	radacina = Element("ci")
	nod = SubElement(radacina, "slot")
	SubElement(nod, "id").text = str(slot)
	for serviciu in reguli["servicii"]:
		SubElement(nod, "service", serviciu)
	for furnizor in reguli["furnizori"]:
		SubElement(nod, "provider", {"name": furnizor["name"], "dvbnamespace": "0x%08X" % furnizor["namespace"]})
	for caid in reguli["caid"]:
		SubElement(nod, "caid", {"id": "0x%04X" % caid})
	fd, temporar = tempfile.mkstemp(prefix=".ci%d-" % slot, suffix=".xml", dir=DOSAR)
	try:
		with os.fdopen(fd, "wb") as fisier:
			ElementTree(radacina).write(fisier, encoding="utf-8", xml_declaration=True)
			fisier.flush()
			os.fsync(fisier.fileno())
		os.replace(temporar, os.path.join(DOSAR, "ci%d.xml" % slot))
	finally:
		if os.path.exists(temporar):
			os.unlink(temporar)
	_aplicaAlocarea(slot)
	return reguli


def _canale():
	from enigma import eServiceCenter, eServiceReference
	centru = eServiceCenter.getInstance()
	cerere = '1:7:1:0:0:0:0:0:0:0: (type == 1) || (type == 2) || (type == 17) || (type == 22) || (type == 25) || (type == 31) || (type == 32) ORDER BY name'
	lista = centru.list(eServiceReference(cerere))
	if lista is not None:
		while True:
			ref = lista.getNext()
			if not ref.valid():
				break
			if _REF_DVB.fullmatch(ref.toString()):
				yield centru, ref


def alegeriAlocare(fel, text="", de_la=0, cate=100):
	"""Canalele si furnizorii din lista receptorului, cu pagini mici in web."""
	from enigma import iServiceInformation
	if fel not in ("servicii", "furnizori"):
		raise ValueError("fel")
	rezultat, vazute = [], set()
	for centru, ref in _canale():
		info = centru.info(ref)
		if info is None:
			continue
		if fel == "servicii":
			nou = {"ref": ref.toString(), "name": info.getName(ref) or ref.toString()}
			cheie = nou["ref"]
		else:
			nume = info.getInfoString(ref, iServiceInformation.sProvider)
			if not nume:
				continue
			nou = {"name": nume, "namespace": ref.getUnsignedData(4)}
			cheie = (nou["name"], nou["namespace"])
		if cheie not in vazute and text.casefold() in nou["name"].casefold():
			vazute.add(cheie)
			rezultat.append(nou)
			if len(rezultat) > de_la + cate:
				break
	return {"alegeri": rezultat[de_la:de_la + cate], "mai_sunt": len(rezultat) > de_la + cate}


def caidCunoscute(slot):
	"""Operatorii si CAID-urile lor din canalele scanate, plus cele ale modulului."""
	from enigma import eDVBCIInterfaces, iServiceInformation
	gasite = {}
	for centru, ref in _canale():
		info = centru.info(ref)
		if info is None:
			continue
		nume = info.getInfoString(ref, iServiceInformation.sProvider) or ""
		for caid in info.getInfoObject(ref, iServiceInformation.sCAIDs) or []:
			if type(caid) is int and 0 < caid <= 0xffff:
				gasite.setdefault(caid, set()).add(nume)
	ci = eDVBCIInterfaces.getInstance()
	for caid in ci.readCICaIds(slot) or []:
		if type(caid) is int and 0 < caid <= 0xffff:
			gasite.setdefault(caid, set())
	return [{"caid": caid, "name": ", ".join(sorted(n for n in nume if n))}
		for caid, nume in sorted(gasite.items())]


def _numar(text):
	"""0x0b00, 0B00 sau 2816 -> 2816; altfel None"""
	text = (text or "").strip()
	if not text:
		return None
	try:
		if text.lower().startswith("0x"):
			return int(text, 16)
		return int(text)
	except ValueError:
		try:
			return int(text, 16)
		except ValueError:
			return None


def citesteAlocarea(cale):
	"""(servicii, furnizori, caid) din fisierul unui slot, in forma ceruta de setDescrambleRules, sau None (lipsa, stricat)"""
	if not os.path.isfile(cale):
		return None
	try:
		radacina = parse(cale).getroot()
	except Exception as e:
		print("[CIHelper] %s nu se poate citi: %s" % (cale, e))
		return None
	servicii, furnizori, caid = [], [], []
	for slot in radacina.findall("slot"):
		for c in slot.findall("caid"):
			n = _numar(c.get("id"))
			if n is not None and n not in caid:
				caid.append(n)
		for s in slot.findall("service"):
			ref = (s.get("ref") or "").strip()
			if ref and ref not in servicii:
				servicii.append(ref)
		for p in slot.findall("provider"):
			nume = p.get("name") or ""
			ns = _numar(p.get("dvbnamespace"))
			if nume and ns is not None and (nume, ns) not in furnizori:
				furnizori.append((nume, ns))
	return (servicii, furnizori, caid)


class _CIHelper:
	def __init__(self):
		self.incarcat = False

	def load_ci_assignment(self, force=False):
		"""regulile din /etc/enigma2/ci<slot>.xml date fiecarui slot; o singura data, afara de force=True"""
		rezultat = {}
		if self.incarcat and not force:
			return rezultat
		self.incarcat = True
		try:
			from enigma import eDVBCIInterfaces
			ci = eDVBCIInterfaces.getInstance()
			sloturi = ci.getNumOfSlots() if ci is not None else 0
		except Exception as e:
			print("[CIHelper] fara modul CI: %s" % e)
			return rezultat
		for slot in range(sloturi or 0):
			reguli = citesteAlocarea(os.path.join(DOSAR, "ci%d.xml" % slot))
			if reguli is None:
				continue
			try:
				cod = ci.setDescrambleRules(slot, reguli)
				if cod not in (None, 0):
					raise RuntimeError("CI")
				rezultat[slot] = True
				print("[CIHelper] slotul %d: %d canale, %d furnizori, %d CAID" % (slot, len(reguli[0]), len(reguli[1]), len(reguli[2])))
			except Exception as e:
				rezultat[slot] = False
				print("[CIHelper] slotul %d: %s" % (slot, e))
		return rezultat


cihelper = _CIHelper()
