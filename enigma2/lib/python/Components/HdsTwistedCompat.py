# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com & hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
"""Nume Twisted vechi cerute de pluginurile externe. Nu schimba API-ul modern."""
from collections import namedtuple
from io import BytesIO
import os
from types import SimpleNamespace
from urllib.parse import urlunparse

from twisted.internet import defer, protocol
from twisted.python.failure import Failure
from twisted.web import client, error
from twisted.web.http_headers import Headers
from twisted.web.iweb import IPolicyForHTTPS

_Adresa = namedtuple("AdresaPlugin", "scheme host port path")


def _octeti(valoare):
	return valoare.encode("utf-8") if isinstance(valoare, str) else valoare


def _parse(url, defaultPort=None):
	# URI ramane parserul Twisted; forma veche pastreaza si fragmentul in cale.
	uri = client.URI.fromBytes(_octeti(url), defaultPort)
	if uri.netloc.count(b":") > 1:
		raise ValueError("Adresa veche nu accepta mai multe separatoare de port")
	gazda = uri.netloc.partition(b":")[0]
	port = uri.port
	if defaultPort is None and uri.scheme == b"wss":
		# URI modern stie si wss; contractul vechi avea 443 numai pentru https.
		try:
			port = int(uri.netloc.partition(b":")[2])
		except ValueError:
			port = 80
	parti = (uri.path, uri.params, uri.query, uri.fragment)
	cale = urlunparse(("", "") + tuple(p.decode("latin-1") for p in parti)).encode("latin-1") or b"/"
	if isinstance(url, str):
		return _Adresa(uri.scheme.decode("utf-8"), gazda.decode("utf-8"), port,
			cale.decode("utf-8"))
	return _Adresa(uri.scheme, gazda, port, cale)


class _Scriere(protocol.Protocol):
	def __init__(self, fisier):
		self.fisier = fisier
		self.oprit = False
		self.deferred = defer.Deferred(self._opreste)

	def _opreste(self, rezultat):
		self.oprit = True
		try:
			self.fisier.close()
		except Exception:
			pass
		if self.transport is not None:
			self.transport.abortConnection()

	def dataReceived(self, date):
		if not self.deferred.called and not self.oprit:
			try:
				self.fisier.write(date)
			except Exception:
				motiv = Failure()
				self._opreste(self.deferred)
				self.deferred.errback(motiv)

	def connectionLost(self, motiv):
		if self.deferred.called or self.oprit:
			return
		try:
			self.fisier.close()
		except Exception:
			self.deferred.errback()
			return
		if motiv.check(client.ResponseDone, client.PotentialDataLoss):
			self.deferred.callback(None)
		else:
			self.deferred.errback(motiv)


def _primeste(raspuns, fisier):
	if not 200 <= raspuns.code < 300:
		def eroare(corp):
			raise error.Error(str(raspuns.code).encode("ascii"), raspuns.phrase, corp)
		return client.readBody(raspuns).addCallback(eroare)
	if fisier is None:
		return client.readBody(raspuns)
	try:
		tinta = open(fisier, "wb") if isinstance(fisier, (str, bytes, os.PathLike)) else fisier
	except Exception:
		# Consumam raspunsul si cand tinta nu poate fi deschisa.
		client.readBody(raspuns).addErrback(lambda motiv: None)
		return defer.fail()
	scriere = _Scriere(tinta)
	raspuns.deliverBody(scriere)
	return scriere.deferred


def _cerere(url, fisier=None, method=b"GET", postdata=None, headers=None,
		agent=b"HDSatelit plugin HTTP", timeout=0, cookies=None,
		followRedirect=True, redirectLimit=20, afterFoundGet=False, contextFactory=None):
	from twisted.internet import reactor
	try:
		antete = Headers()
		for nume, valori in (headers or {}).items():
			if not isinstance(valori, (list, tuple)):
				valori = [valori]
			antete.setRawHeaders(_octeti(nume), [_octeti(v) for v in valori])
		if not antete.hasHeader(b"User-Agent"):
			antete.setRawHeaders(b"User-Agent", [_octeti(agent)])
		if cookies and not antete.hasHeader(b"Cookie"):
			valoare = b"; ".join(_octeti(k) + b"=" + _octeti(v) for k, v in cookies.items())
			antete.setRawHeaders(b"Cookie", [valoare])
		optiuni = {}
		if contextFactory is not None:
			politica = contextFactory
			if not IPolicyForHTTPS.providedBy(politica):
				politica = SimpleNamespace(getContext=lambda host, port: contextFactory.getContext())
			optiuni["contextFactory"] = politica
		conexiune = client.Agent(reactor, **optiuni)
		if followRedirect:
			clasa = client.BrowserLikeRedirectAgent if afterFoundGet else client.RedirectAgent
			conexiune = clasa(conexiune, redirectLimit=redirectLimit)
		corp = client.FileBodyProducer(BytesIO(_octeti(postdata))) if postdata is not None else None
		rezultat = conexiune.request(_octeti(method), _octeti(url), antete, corp)
		rezultat.addCallback(_primeste, fisier)
		if timeout:
			def expirat(valoare, durata):
				return Failure(defer.TimeoutError("Descarcarea a depasit %s secunde" % durata))
			rezultat.addTimeout(timeout, reactor, onTimeoutCancel=expirat)
		return rezultat
	except Exception:
		return defer.fail()


def getPage(url, *args, contextFactory=None, **kwargs):
	return _cerere(url, None, *args, contextFactory=contextFactory, **kwargs)


def downloadPage(url, file, method=b"GET", postdata=None, headers=None,
		agent=b"HDSatelit plugin HTTP", supportPartial=0, timeout=0, cookies=None,
		followRedirect=True, redirectLimit=20, afterFoundGet=False, contextFactory=None):
	if supportPartial:
		return defer.fail(NotImplementedError("Reluarea partiala nu este disponibila"))
	rezultat = _cerere(url, file, method=method, postdata=postdata, headers=headers,
		agent=agent, timeout=timeout, cookies=cookies, followRedirect=followRedirect,
		redirectLimit=redirectLimit, afterFoundGet=afterFoundGet, contextFactory=contextFactory)
	if hasattr(file, "close"):
		def inchide(motiv):
			try:
				file.close()
			except Exception:
				pass
			return motiv
		rezultat.addErrback(inchide)
	return rezultat


def completeaza():
	"""Pune numai numele disparute. Agent, URI si functiile existente raman intacte."""
	puse = []
	for nume in ("_parse", "getPage", "downloadPage"):
		if not hasattr(client, nume):
			functie = globals()[nume]
			if nume != "_parse":
				functie._textOcteti = True
			setattr(client, nume, functie)
			puse.append(nume)
	return puse
