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
from xml.etree.ElementTree import parse

DOSAR = "/etc/enigma2"


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
		if self.incarcat and not force:
			return
		self.incarcat = True
		try:
			from enigma import eDVBCIInterfaces
			ci = eDVBCIInterfaces.getInstance()
			sloturi = ci.getNumOfSlots() if ci is not None else 0
		except Exception as e:
			print("[CIHelper] fara modul CI: %s" % e)
			return
		for slot in range(sloturi or 0):
			reguli = citesteAlocarea(os.path.join(DOSAR, "ci%d.xml" % slot))
			if reguli is None:
				continue
			try:
				ci.setDescrambleRules(slot, reguli)
				print("[CIHelper] slotul %d: %d canale, %d furnizori, %d CAID" % (slot, len(reguli[0]), len(reguli[1]), len(reguli[2])))
			except Exception as e:
				print("[CIHelper] slotul %d: %s" % (slot, e))


cihelper = _CIHelper()
