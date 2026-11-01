# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsJurnalTuner.py: partea Python a jurnalului tunerelor (/home/root/logs/hds-tuner.log, Components/HdsJurnal.py).
# configurare(nimmanager): chemat la sfarsitul lui SecConfigure.update() (la pornire si dupa fiecare salvare a setarilor
# tunerelor); scrie cate un rand [configurare] pe tuner, numai cand s-a schimbat fata de ultima data: tipul din
# /proc/bus/nim_sockets, tipurile pe care le poate (tunerele combinate) si tipul ales, modul (simplu, avansat, legat,
# acelasi cu, nefolosit), DiSEqC-ul si pozitiile sateliilor (modul simplu), LNB-urile si Unicable/JESS cu UB-ul (modul
# avansat), alimentarea antenei terestre. Numai date tehnice. Orice greseala de aici nu opreste configurarea.

from Components import HdsJurnal

_ultim = {}


def _poz(orbital):
	try:
		o = int(orbital)
	except (TypeError, ValueError):
		return "?"
	if o > 1800:
		return "%.1fW" % ((3600 - o) / 10.0)
	return "%.1fE" % (o / 10.0)


def _val(obj, nume, implicit=None):
	try:
		return getattr(obj, nume).value
	except Exception:
		return implicit


def _satelit(slot, nim):
	mod = _val(nim, "configMode", "?")
	parti = ["mod %s" % mod]
	if mod in ("equal", "loopthrough", "satposdepends"):
		parti.append("legat de %s" % chr(65 + int(_val(nim, "connectedTo", 0) or 0)))
	elif mod == "simple":
		dm = _val(nim, "diseqcMode", "?")
		parti.append("diseqc %s" % dm)
		if dm == "positioner":
			parti.append("motor")
		else:
			poz = []
			for k in ("diseqcA", "diseqcB", "diseqcC", "diseqcD"):
				try:
					p = getattr(nim, k).orbital_position
				except Exception:
					continue
				if p not in (None, 3601, 3602, 3603):
					poz.append(_poz(p))
				if dm in ("single",) or (dm in ("toneburst_a_b", "diseqc_a_b") and k == "diseqcB"):
					break
			if poz:
				parti.append("sateliti " + ",".join(poz))
	elif mod == "advanced":
		lnb = []
		try:
			for i in sorted(nim.advanced.lnb.keys())[:8]:
				l = nim.advanced.lnb[i]
				lof = _val(l, "lof", "?")
				if lof == "unicable":
					fel = _val(l, "unicable", "?")
					ub = None
					for c in ("scrList", "unicableSCR", "scr"):
						ub = _val(l, c)
						if ub is not None:
							break
					lnb.append("%d:unicable(%s%s)" % (i, fel, (" UB%s" % ub) if ub is not None else ""))
				elif lof not in (None, "?"):
					lnb.append("%d:%s" % (i, lof))
		except Exception:
			pass
		sateliti = 0
		try:
			for s in nim.advanced.sat.keys():
				if int(_val(nim.advanced.sat[s], "lnb", 0) or 0) > 0:
					sateliti += 1
		except Exception:
			pass
		parti.append("lnb %s" % (" ".join(lnb) if lnb else "-"))
		parti.append("pozitii folosite %d" % sateliti)
	return parti


def randTuner(slot):
	"""Textul randului [configurare] pentru un tuner (NIM din NimManager)."""
	nim = slot.config
	tipuri = []
	try:
		tipuri = sorted(set(slot.getMultiTypeList().values())) if slot.isMultiType() else []
	except Exception:
		tipuri = []
	parti = ["%s %s tip %s" % (chr(65 + slot.slot), '"%s"' % (slot.description or "?"), slot.type or "gol")]
	if tipuri:
		parti.append("poate %s ales %s" % ("/".join(tipuri), slot.getType() or "?"))
	if getattr(slot, "multistream", False):
		parti.append("multistream")
	try:
		if slot.isCompatible("DVB-S"):
			parti += _satelit(slot, nim)
		else:
			parti.append("mod %s" % _val(nim, "configMode", "?"))
			if slot.isCompatible("DVB-T"):
				parti.append("5V %s" % ("da" if _val(nim, "terrestrial_5V", False) else "nu"))
	except Exception as e:
		parti.append("(setarile necitite: %s)" % type(e).__name__)
	return " | ".join(parti)


def configurare(nimmanager):
	try:
		for slot in nimmanager.nim_slots:
			if slot.type is None:
				continue
			text = randTuner(slot)
			if _ultim.get(slot.slot) == text:
				continue
			_ultim[slot.slot] = text
			HdsJurnal.info("tuner", "configurare", text)
	except Exception as e:
		HdsJurnal.avert("tuner", "configurare", "setarile tunerelor necitite: %s" % type(e).__name__)
