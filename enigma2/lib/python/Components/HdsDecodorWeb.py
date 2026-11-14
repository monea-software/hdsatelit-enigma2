# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""HdsDecodorWeb: decodorul placii dat cu imprumut navigatorului HbbTV, pentru <video> si <audio> HTML5 (video HTML5).

DE CE: filmele aplicatiilor HbbTV 2.0 vin prin elementul <video>. WebKit-ul cu video (stratul oe-build/meta-video, quirk-ul
"hdsdvb" din peticul 0009) le reda prin dvbvideosink si dvbaudiosink, adica pe acelasi decodor ca si canalul. Procesul web
ruleaza ca hdsnav (fara root) si nu poate deschide /dev/dvb/adapter0/video0 si audio0 (root:root 0660); enigma2 ii da dreptul
numai cat tine imprumutul si numai dupa ce a oprit canalul.

PROTOCOLUL (socket UNIX, randuri ASCII de cel mult RAND_MAXIM octeti, terminate cu "\\n"; capatul WebKit: GStreamerHdsDvbDecoder):
  WebKit -> enigma2: "cere"                 decodorul, la crearea primului sink;
                     "fereastra X Y L I"    dreptunghiul elementului, in puncte CSS ale paginii de 1280x720;
                     "gata"                 sink-urile s-au inchis (dispozitivele sunt inchise), imprumutul s-a terminat.
  enigma2 -> WebKit: "ok" (decodorul e al lui) sau "nu <motiv>" (atunci WebKit da MEDIA_ERR_DECODE, fara sa atinga placa).
Un singur client odata; uid-ul lui (SO_PEERCRED) trebuie sa fie cel al lui hdsnav. Legatura inchisa = "gata".

DREPTUL: chgrp hdsnav pe video0 si audio0 cat tine imprumutul (modul ramane 0660), inapoi root la sfarsit. Un descriptor
deja deschis nu se poate lua inapoi, deci la sfarsit (si la iesirea aplicatiei) procesele lui hdsnav care mai tin
dispozitivele deschise primesc SIGKILL (ia_inapoi).

MEMORIA ES (numai HiSilicon cu showiframe, lib/dvb/hdspazavideo.h): fara maparea de 34611200 octeti prima scriere in video0
sau audio0 e un Oops al nucleului; atunci raspunsul e "nu memorie" (verificarea o face Components/HdsHbbtvPornire.Mediu cu
HdsMemorieDriver.mapareEs()).

Partea de sus nu importa enigma: se probeaza pe PC (teste/test_hbbtv_video_a_075.py)."""

from __future__ import absolute_import

import errno
import os
import signal
import socket
import struct

DOSAR = "/tmp/hds-decodor"
CALE_SOCKET = DOSAR + "/sock"
DISPOZITIVE = ("/dev/dvb/adapter0/video0", "/dev/dvb/adapter0/audio0")
RAND_MAXIM = 64
TAMPON_MAXIM = 4 * RAND_MAXIM
CERE, FEREASTRA, GATA, INCHIS = "cere", "fereastra", "gata", "inchis"
# mediul navigatorului cu decodor (lansator.py, modul HbbTV): quirk-ul, gaura, limita decodarii, filmele fara cache pe disc si
# plafonul tampoanelor Media Source Extensions (receptorul are ~400 MB liberi; WebKit le tine in memorie)
MEDIU_NAVIGATOR = (("WEBKIT_GST_QUIRKS", "hdsdvb"), ("WEBKIT_GST_HOLE_PUNCH_QUIRK", "hdsdvb"),
	("WEBKIT_GST_VIDEO_DECODING_LIMIT", "1920x1080@60"), ("WPE_SHELL_DISABLE_MEDIA_DISK_CACHE", "1"),
	("MSE_MAX_BUFFER_SIZE", "video:30M,audio:4M,text:1M"))


BIBLIOTECA_WEBKIT = "/usr/lib/libWPEWebKit-2.0.so.1"
SEMN_QUIRK = b"HDS_DECODOR"          # numele variabilei citite de quirk-ul hdsdvb (peticul 0009 al WebKit-ului)
CALE_ENV = "/usr/bin/env"
_cache_video = {}


def _jurnal(text):
	print("[HdsDecodorWeb] %s" % text)


def webkit_cu_video(cale=BIBLIOTECA_WEBKIT, env=CALE_ENV, numai_stiut=False):
	"""True numai cand WebKit-ul instalat are quirk-ul hdsdvb (video HTML5 pe placa) si /usr/bin/env exista. Fara ele
	imprumutul nu porneste deloc, deci imaginile cu WebKit-ul fara video pornesc navigatorul HbbTV ca pana acum. Cautarea
	in biblioteca (~60 MB, mmap; ~0,9 s pe Viper 4K V20) se face o data pentru fiecare fisier (dispozitiv, inod, marime,
	data), pe un fir separat la pornirea enigma2 (cauta_in_fundal). numai_stiut=True (firul enigma2): fara cautare, False
	cat raspunsul nu e stiut inca."""
	import mmap
	try:
		if not os.path.exists(env):
			return False
		reala = os.path.realpath(cale)
		st = os.stat(reala)
		cheie = (reala, st.st_dev, st.st_ino, st.st_size, int(st.st_mtime))
		if cheie not in _cache_video and numai_stiut:
			# alt fisier decat cel cautat la pornire (actualizare, montare peste el): cautarea pleaca acum pe firul ei,
			# urmatoarea aplicatie are raspunsul
			cauta_in_fundal(cale, env)
			return False
		if cheie not in _cache_video:
			with open(reala, "rb") as f:
				m = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
				try:
					_cache_video.clear()
					_cache_video[cheie] = m.find(SEMN_QUIRK) >= 0
				finally:
					m.close()
		return _cache_video[cheie]
	except (OSError, ValueError) as e:
		_jurnal("WebKit: %s" % e)
		return False


def cauta_in_fundal(cale=BIBLIOTECA_WEBKIT, env=CALE_ENV):
	"""webkit_cu_video() pe un fir separat (la pornirea enigma2), ca firul enigma2 sa gaseasca raspunsul gata."""
	import threading
	t = threading.Thread(target=webkit_cu_video, args=(cale, env), name="HdsDecodorWeb")
	t.daemon = True
	t.start()
	return t


def citeste_rand(rand):
	"""Un rand de la WebKit -> (comanda, argumente) sau None (rand gresit: se ignora). argumente: () sau, la fereastra, cele
	4 texte (le verifica HdsHbbtvPornire.fereastra_valida)."""
	if isinstance(rand, bytes):
		if len(rand) > RAND_MAXIM:
			return None
		try:
			rand = rand.decode("ascii")
		except UnicodeError:
			return None
	if not isinstance(rand, str) or len(rand) > RAND_MAXIM:
		return None
	p = rand.strip().split(" ")
	if p == [CERE] or p == [GATA]:
		return p[0], ()
	if len(p) == 5 and p[0] == FEREASTRA and all(x for x in p[1:]):
		return FEREASTRA, tuple(p[1:])
	return None


def mediu_navigator(cale_socket):
	"""Prefixul "/usr/bin/env VAR=..." al navigatorului cu decodor, sau [] cand calea nu e buna."""
	if not isinstance(cale_socket, str) or not cale_socket.startswith("/tmp/") or len(cale_socket) > 100 or \
			any(c in cale_socket for c in " \t\r\n=\"'\\"):
		return []
	return ["/usr/bin/env", "HDS_DECODOR=" + cale_socket] + ["%s=%s" % kv for kv in MEDIU_NAVIGATOR]


def da_drept(da, gid, dispozitive=DISPOZITIVE, chown=None):
	"""da=True: grupul dispozitivelor devine gid (hdsnav); False: inapoi root. -> True daca toate s-au schimbat. La un
	esec cand se da, cele schimbate se pun inapoi (nimic pe jumatate)."""
	chown = chown or os.chown
	facute = []
	for d in dispozitive:
		try:
			chown(d, -1, gid if da else 0)
			facute.append(d)
		except OSError as e:
			_jurnal("grupul %s: %s" % (d, e))
			if da:
				for f in facute:
					try:
						chown(f, -1, 0)
					except OSError:
						pass
				return False
	return len(facute) == len(dispozitive)


def procese_cu_dispozitive(uid, dispozitive=DISPOZITIVE, proc="/proc", listdir=None, readlink=None, uid_proces=None):
	"""PID-urile proceselor cu uid-ul dat care tin deschis unul din dispozitive (/proc/<pid>/fd/*)."""
	listdir = listdir or os.listdir
	readlink = readlink or os.readlink
	uid_proces = uid_proces or (lambda cale: os.stat(cale).st_uid)
	tinte = set(dispozitive)
	rez = []
	try:
		pids = [p for p in listdir(proc) if p.isdigit()]
	except OSError:
		return rez
	for pid in pids:
		baza = proc + "/" + pid
		try:
			if uid_proces(baza) != uid:
				continue
			for fd in listdir(baza + "/fd"):
				try:
					if readlink(baza + "/fd/" + fd) in tinte:
						rez.append(int(pid))
						break
				except OSError:
					continue
		except OSError:
			continue
	return rez


def ia_inapoi(uid, dispozitive=DISPOZITIVE, chown=None, omoara=None, **cautare):
	"""Sfarsitul imprumutului (si iesirea aplicatiei): grupul inapoi root, apoi procesele lui uid care mai tin
	dispozitivele deschise primesc SIGKILL. -> PID-urile oprite."""
	omoara = omoara or os.kill
	da_drept(False, 0, dispozitive, chown)
	if uid is None:
		return []
	pids = procese_cu_dispozitive(uid, dispozitive, **cautare)
	for p in pids:
		try:
			omoara(p, getattr(signal, "SIGKILL", 9))
			_jurnal("procesul %d tinea decodorul dupa imprumut: oprit" % p)
		except OSError as e:
			_jurnal("procesul %d: %s" % (p, e))
	return pids


def uid_client(conexiune):
	"""uid-ul procesului de la celalalt capat (SO_PEERCRED: struct ucred = pid, uid, gid), sau None."""
	try:
		date = conexiune.getsockopt(socket.SOL_SOCKET, getattr(socket, "SO_PEERCRED", 17), struct.calcsize("3i"))
		return struct.unpack("3i", date)[1]
	except (OSError, AttributeError, struct.error):
		return None


class Ascultator(object):
	"""Ce afla enigma2 (Components/HdsHbbtvPornire.Controlor). Metodele sunt chemate pe firul enigma2."""

	def laDecodorCere(self):
		"""-> True (decodorul e dat: canalul oprit, dreptul dat) sau motivul refuzului (un cuvant)."""
		return "nefacut"

	def laDecodorFereastra(self, argumente):
		"""Dreptunghiul elementului (cele 4 texte, inca neverificate)."""

	def laDecodorGata(self):
		"""Imprumutul s-a terminat (gata sau legatura inchisa)."""


class Server(object):
	"""Serverul imprumutului. notificator(fd, functie) -> obiect cu stop() (in enigma2 eSocketNotifier, vezi Mediu);
	uid_permis: uid-ul lui hdsnav; gid_dosar: grupul dosarului si al socketului (hdsnav)."""

	def __init__(self, asculta, notificator, uid_permis, gid_dosar=None, cale=CALE_SOCKET, fabrica=None, uid_peer=None,
			chown=None):
		self.a = asculta
		self.notificator = notificator
		self.uid_permis = uid_permis
		self.gid_dosar = gid_dosar
		self.cale = cale
		self.fabrica = fabrica or (lambda: socket.socket(socket.AF_UNIX, socket.SOCK_STREAM))
		self.uid_peer = uid_peer or uid_client
		self.chown = chown              # None: os.chown, luat la chemare (pe PC os.chown nu exista)
		self._s = self._ns = None
		self._c = self._nc = None
		self._buf = b""
		self.imprumutat = False

	def porneste(self):
		"""Dosarul (root:hdsnav 0750), socketul (0660) si ascultarea. -> calea socketului sau None."""
		try:
			d = os.path.dirname(self.cale)
			if not os.path.isdir(d):
				os.makedirs(d, 0o750)
			os.chmod(d, 0o750)
			if self.gid_dosar is not None:
				(self.chown or os.chown)(d, 0, self.gid_dosar)
			try:
				os.unlink(self.cale)
			except OSError as e:
				if e.errno != errno.ENOENT:
					raise
			s = self.fabrica()
			s.bind(self.cale)
			os.chmod(self.cale, 0o660)
			if self.gid_dosar is not None:
				(self.chown or os.chown)(self.cale, 0, self.gid_dosar)
			s.listen(1)
			s.setblocking(False)
		except (OSError, socket.error) as e:
			_jurnal("serverul nu porneste: %s" % e)
			return None
		self._s = s
		self._ns = self.notificator(s.fileno(), self._laConectare)
		return self.cale

	def opreste(self):
		self._inchideClientul(anunta=False)
		if self._ns is not None:
			self._ns.stop()
			self._ns = None
		if self._s is not None:
			try:
				self._s.close()
			except (OSError, socket.error):
				pass
			self._s = None
			try:
				os.unlink(self.cale)
			except OSError:
				pass

	def _scrie(self, conexiune, text):
		try:
			conexiune.send((text + "\n").encode("ascii"))
		except (OSError, socket.error):
			pass

	def _laConectare(self, *_):
		try:
			c, _adr = self._s.accept()
		except (OSError, socket.error, AttributeError):
			return
		uid = self.uid_peer(c)
		if uid is None or uid != self.uid_permis:
			_jurnal("legatura refuzata (uid %s)" % uid)
			self._scrie(c, "nu utilizator")
			c.close()
			return
		if self._c is not None:
			self._scrie(c, "nu ocupat")
			c.close()
			return
		c.setblocking(False)
		self._c, self._buf = c, b""
		self._nc = self.notificator(c.fileno(), self._laDate)

	def _laDate(self, *_):
		c = self._c
		if c is None:
			return
		try:
			date = c.recv(256)
		except (OSError, socket.error) as e:
			if getattr(e, "errno", None) in (errno.EAGAIN, errno.EWOULDBLOCK):
				return
			date = b""
		if not date:
			self._inchideClientul()
			return
		self._buf += date
		while b"\n" in self._buf and self._c is not None:
			rand, self._buf = self._buf.split(b"\n", 1)
			self._comanda(rand)
		if len(self._buf) > TAMPON_MAXIM:
			_jurnal("rand prea lung: legatura inchisa")
			self._inchideClientul()

	def _comanda(self, rand):
		c = citeste_rand(rand)
		if c is None:
			_jurnal("rand gresit, ignorat")
			return
		cmd, arg = c
		if cmd == CERE:
			if self.imprumutat:
				self._scrie(self._c, "nu ocupat")
				return
			r = self.a.laDecodorCere()
			if r is True:
				self.imprumutat = True
				self._scrie(self._c, "ok")
			else:
				self._scrie(self._c, "nu %s" % (r if isinstance(r, str) and r.isalpha() else "refuzat"))
		elif cmd == FEREASTRA:
			if self.imprumutat:
				self.a.laDecodorFereastra(arg)
		elif cmd == GATA:
			self._inchideClientul()

	def _inchideClientul(self, anunta=True):
		c, self._c = self._c, None
		if self._nc is not None:
			self._nc.stop()
			self._nc = None
		if c is not None:
			try:
				c.close()
			except (OSError, socket.error):
				pass
		era = self.imprumutat
		self.imprumutat = False
		self._buf = b""
		if era and anunta:
			self.a.laDecodorGata()
