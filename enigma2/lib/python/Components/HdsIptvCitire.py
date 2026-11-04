# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only

import json
import time


class CuInceput(object):

	def __init__(self, inceput, flux):
		self.inceput, self.flux = inceput, flux

	def read(self, n=-1):
		if n < 0:
			a, self.inceput = self.inceput, b""
			return a + self.flux.read()
		a, self.inceput = self.inceput[:n], self.inceput[n:]
		return a + self.flux.read(n - len(a)) if len(a) < n else a

	def read1(self, n=65536):
		if self.inceput:
			a, self.inceput = self.inceput[:n], self.inceput[n:]
			return a
		return getattr(self.flux, "read1", self.flux.read)(n)


class Limitat(object):

	def __init__(self, flux, maxim, secunde=180):
		self.flux, self.ramas = flux, maxim
		self.sfarsit = time.monotonic() + secunde

	def read(self, n=-1):
		if time.monotonic() > self.sfarsit:
			raise ValueError("termen")
		n = min(65536 if n < 0 else n, self.ramas + 1)
		b = getattr(self.flux, "read1", self.flux.read)(n)
		self.ramas -= len(b)
		if self.ramas < 0:
			raise ValueError("marime")
		return b


def randuri(flux, maxim=64 * 1024 * 1024, lungime=8192):
	"""Citire limitata; un rand prea lung se consuma fara acumulare."""
	f = Limitat(flux, maxim)
	tampon = b""
	sari = False
	while True:
		b = f.read(65536)
		if not b:
			if tampon and not sari:
				yield tampon
			return
		parti = b.split(b"\n")
		for i, p in enumerate(parti):
			if not sari:
				tampon += p
				if len(tampon) > lungime:
					tampon, sari = b"", True
			if i < len(parti) - 1:
				if not sari:
					yield tampon
				tampon, sari = b"", False


def listaJson(flux, maxim=64 * 1024 * 1024):
	"""Un singur obiect JSON in memorie, inclusiv la 100.000 de intrari."""
	import codecs
	f = Limitat(flux, maxim)
	utf = codecs.getincrementaldecoder("utf-8-sig")("strict")
	dec = json.JSONDecoder()
	tampon, inceput, gata, dupa = "", False, False, False
	while True:
		b = f.read(16384)
		tampon += utf.decode(b, final=not b)
		while True:
			tampon = tampon.lstrip()
			if not inceput:
				if not tampon:
					break
				if tampon[0] != "[":
					raise ValueError("lista")
				tampon, inceput = tampon[1:], True
				continue
			if gata:
				if tampon:
					raise ValueError("coada")
				break
			if not tampon:
				break
			if tampon[0] == "]":
				tampon, gata = tampon[1:], True
				continue
			if dupa:
				if tampon[0] != ",":
					raise ValueError("separator")
				tampon, dupa = tampon[1:].lstrip(), False
				if not tampon:
					break
			try:
				obj, n = dec.raw_decode(tampon)
			except ValueError:
				break
			yield obj
			tampon, dupa = tampon[n:], True
		if len(tampon) > 1024 * 1024:
			raise ValueError("obiect prea mare")
		if not b:
			if not gata:
				raise ValueError("lista incompleta")
			return
