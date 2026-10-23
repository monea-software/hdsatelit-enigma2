# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsDvbILegare: din o lista DVB-I, unde e fiecare canal pe satelit (tripleta DVB si pozitia orbitala din
# DVBSDeliveryParameters) si adresa lui de internet (DASH sau HLS), ca un canal de satelit din lista receptorului sa
# poata fi legat de varianta lui de internet: un singur rand in lista si rezerva cand satelitul nu se receptioneaza.
# Cheia de legare e cea din referinta serviciului: SID:TSID:ONID si spatiul de nume (pozitia in zecimi de grad,
# deplasata cu 16 biti; vestul ca 3600 minus pozitie). Partea de jos a spatiului de nume (frecventa, la unele
# transpondere) nu intra in potrivire.
from __future__ import absolute_import, unicode_literals

import xml.etree.ElementTree as ET

MAX_LISTA = 4 * 1024 * 1024


def _local(tag):
	return tag.split("}")[-1]


def _text(el):
	return (el.text or "").strip() if el is not None else ""


def pozitieZecimi(text):
	"""'19.2' -> 192, '-0.8' sau '0.8W' -> 3592 (vestul ca in referintele receptorului); None daca nu se poate citi"""
	t = (text or "").strip().upper().replace(",", ".")
	vest = t.endswith("W") or t.startswith("-")
	t = t.rstrip("EW").lstrip("+-").strip()
	try:
		z = int(round(float(t) * 10))
	except ValueError:
		return None
	if z < 0 or z > 1800:
		return None
	return (3600 - z) % 3600 if vest else z


def spatiuNume(zecimi):
	return (zecimi & 0xFFFF) << 16


def cheie(sid, tsid, onid, spatiu):
	"""ca in referinta unui serviciu: SID:TSID:ONID:NS, hexazecimal, majuscule, fara zerouri in fata"""
	return "%X:%X:%X:%X" % (sid, tsid, onid, spatiu)


def _url(inst):
	for c in inst.iter():
		n = _local(c.tag)
		if n in ("DASHDeliveryParameters", "OtherDeliveryParameters"):
			for u in c.iter():
				if _local(u.tag) == "URI" and _text(u).startswith(("http://", "https://")):
					return _text(u)
	return ""


def legaturi(xml_bytes):
	"""[{"nume", "sid", "tsid", "onid", "zecimi", "url"}] pentru serviciile care au loc pe satelit; url "" cand nu au
	varianta de internet. [] la orice greseala sau lista suspecta."""
	if not xml_bytes or len(xml_bytes) > MAX_LISTA:
		return []
	cap = xml_bytes[:4096].upper()
	if b"<!DOCTYPE" in cap or b"<!ENTITY" in cap:
		return []
	try:
		rad = ET.fromstring(xml_bytes)
	except Exception:
		return []
	rez = []
	for svc in rad.iter():
		if _local(svc.tag) != "Service":
			continue
		nume = ""
		for c in svc.iter():
			if _local(c.tag) == "ServiceName" and _text(c):
				nume = _text(c)
				break
		sat = []
		url = ""
		for inst in [c for c in svc.iter() if _local(c.tag) == "ServiceInstance"]:
			url = url or _url(inst)
			for d in inst.iter():
				if _local(d.tag) != "DVBSDeliveryParameters":
					continue
				trip = None
				poz = None
				for e in d.iter():
					if _local(e.tag) == "DVBTriplet":
						trip = e
					elif _local(e.tag) == "OrbitalPosition":
						poz = pozitieZecimi(_text(e))
				if trip is None or poz is None:
					continue
				try:
					sat.append((int(trip.get("serviceId")), int(trip.get("tsId")), int(trip.get("origNetId")), poz))
				except (TypeError, ValueError):
					continue
		for sid, tsid, onid, poz in sat:
			rez.append({"nume": nume, "sid": sid, "tsid": tsid, "onid": onid, "zecimi": poz, "url": url})
	return rez


def tabel(lista_legaturi):
	"""{cheie fara partea de jos a spatiului de nume: legatura}, numai cele cu varianta de internet"""
	return dict((cheie(l["sid"], l["tsid"], l["onid"], spatiuNume(l["zecimi"])), l) for l in lista_legaturi if l["url"])


def cautaRef(ref, tab):
	"""legatura pentru o referinta de serviciu ('1:0:19:283D:3FB:1:C00000:0:0:0:') sau None"""
	p = (ref or "").split(":")
	if len(p) < 7:
		return None
	try:
		sid, tsid, onid, ns = (int(x, 16) for x in p[3:7])
	except ValueError:
		return None
	return tab.get(cheie(sid, tsid, onid, ns & 0xFFFF0000))


def _radacina(xml_bytes):
	if not xml_bytes or len(xml_bytes) > MAX_LISTA:
		return None
	cap = xml_bytes[:4096].upper()
	if b"<!DOCTYPE" in cap or b"<!ENTITY" in cap:
		return None
	try:
		return ET.fromstring(xml_bytes)
	except Exception:
		return None


def _tabelLcn(rad, regiune):
	"""tabelul LCN pentru regiune: cel cu TargetRegion = regiune; altfel primul fara TargetRegion; altfel primul"""
	tabele = [t for t in rad.iter() if _local(t.tag) == "LCNTable"]
	if not tabele:
		return None

	def regiuni_tinta(t):
		return [_text(c) for c in list(t) if _local(c.tag) == "TargetRegion" and _text(c)]

	if regiune:
		for t in tabele:
			if regiune in regiuni_tinta(t):
				return t
	for t in tabele:
		if not regiuni_tinta(t):
			return t
	return tabele[0]


def regiuni(xml_bytes):
	"""[{"id", "nume", "nivel", "alegere"}] din RegionList, in ordinea din lista (regiunile copil dupa parinte, nivel
	0 = de sus); "alegere" False pentru regiunile cu selectable="false" (grupuri). Numai regiunile care au un tabel LCN
	al lor schimba numerotarea. [] cand lista nu are regiuni sau la orice greseala."""
	rad = _radacina(xml_bytes)
	if rad is None:
		return []
	rez = []

	def adauga(el, nivel):
		for r in list(el):
			if _local(r.tag) != "Region":
				continue
			rid = (r.get("regionID") or "").strip()
			nume = ""
			for c in list(r):
				if _local(c.tag) == "RegionName" and _text(c):
					nume = _text(c)
					break
			if rid:
				rez.append({"id": rid, "nume": nume or rid, "nivel": nivel,
					"alegere": (r.get("selectable") or "true").strip().lower() != "false"})
			adauga(r, nivel + 1)

	for lista in rad.iter():
		if _local(lista.tag) == "RegionList":
			adauga(lista, 0)
			break
	return rez


def numerotare(xml_bytes, regiune=""):
	"""{nume serviciu: numar} din tabelul LCN al listei (cel al regiunii alese, altfel primul fara regiune; numarul
	legat prin UniqueIdentifier), ca lista DVB-I sa vina in ordinea data de televiziuni. {} la orice greseala."""
	rad = _radacina(xml_bytes)
	if rad is None:
		return {}
	nume_dupa_id = {}
	for svc in rad.iter():
		if _local(svc.tag) != "Service":
			continue
		uid = ""
		nume = ""
		for c in list(svc):
			if _local(c.tag) == "UniqueIdentifier":
				uid = _text(c)
		for c in svc.iter():
			if _local(c.tag) == "ServiceName" and _text(c):
				nume = _text(c)
				break
		if uid and nume:
			nume_dupa_id[uid] = nume
	rez = {}
	tab = _tabelLcn(rad, regiune)
	if tab is None:
		return rez
	for l in tab.iter():
		if _local(l.tag) != "LCN":
			continue
		nume = nume_dupa_id.get(l.get("serviceRef") or "")
		try:
			n = int(l.get("channelNumber"))
		except (TypeError, ValueError):
			continue
		if nume and nume not in rez:
			rez[nume] = n
	return rez
