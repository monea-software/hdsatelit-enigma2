# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsReteaUnealta.py: procesul copil al locurilor din retea (Components/HdsStocareRetea.py). Ruleaza separat de enigma2,
# pornit numai la cererea omului, cu datele pe intrarea standard (JSON), niciodata pe linia de comanda: parola nu apare
# in lista proceselor, in jurnal sau in /proc/mounts.
#
#   monteaza     SMB (cifs) sau NFS prin mount(2), din ctypes: intai o legatura TCP scurta spre server (un server
#                oprit da raspunsul in cateva secunde, nu dupa termenele nucleului), apoi dialectele pe rand (SMB 3.0,
#                2.1, 2.0; NFS 3, apoi 4). Raspunsul: {"ok", "vers", "errno", "cod"}.
#   demonteaza   umount2 cu MNT_DETACH (nu asteapta un server oprit), apoi dosarul gol sters.
#   viteza       scrie si citeste un fisier de proba pe locul montat (cu fsync), il sterge: MB/s la scriere.
#   punte        o punte HTTP numai pe 127.0.0.1 (port ales de sistem, scris pe primul rand al iesirii) spre un film de pe
#                FTP, FTPS sau WebDAV: playerul cere http://127.0.0.1:<port>/<jeton>/<n>/<nume>, puntea face cererea la
#                server cu parola, cu salturile (Range) traduse in REST (FTP) sau Range (WebDAV). Se opreste cand se inchide
#                intrarea standard (enigma2 a oprit-o sau a cazut) sau dupa ce nu mai e cerut nimic MINUTE_INACTIV minute.
#
# Procesul copil e pornit cu termen (HdsStocareRetea); un mount(2) blocat de un server care nu raspunde ramane aici, nu
# in enigma2.

import errno
import json
import os
import socket
import sys
import threading
import time

TERMEN_TCP_S = 4.0
MINUTE_INACTIV = 360     # un film lasat pe pauza ore intregi; enigma2 o opreste oricum la iesirea din film
BUCATA = 256 * 1024
MARIME_PROBA = 24 * 1024 * 1024
NUME_PROBA = ".hdsatelit-proba-viteza"

MS_RDONLY = 1
MS_NOSUID = 2
MS_NODEV = 4
MS_NOEXEC = 8
MNT_DETACH = 2

# dialectele incercate, in ordine (nucleul 4.4 porneste altfel cu SMB1)
VERSIUNI_SMB = ("3.0", "2.1", "2.0")
VERSIUNI_NFS = ("3", "4")
# erori dupa care se incearca dialectul urmator (serverul nu il stie)
ERORI_DIALECT = (errno.EOPNOTSUPP, errno.EPROTONOSUPPORT, errno.EINVAL, errno.EIO, errno.ECONNRESET,
	getattr(errno, "EPROTO", 71), getattr(errno, "ENOSYS", 38))
ERORI_SERVER = (errno.EHOSTDOWN, errno.EHOSTUNREACH, errno.ECONNREFUSED, errno.ETIMEDOUT, errno.ENETUNREACH,
	errno.ECONNABORTED)


def scrieRaspuns(date):
	sys.stdout.write(json.dumps(date, ensure_ascii=True) + "\n")
	sys.stdout.flush()


def codEroare(nr):
	"""errno -> codul mesajului (HdsStocareRetea.textEroare)."""
	if nr in (errno.EACCES, errno.EPERM, getattr(errno, "EKEYREJECTED", 129), getattr(errno, "ENOKEY", 126)):
		return "acces"
	if nr in ERORI_SERVER:
		return "server"
	if nr in (errno.ENOENT, errno.ENOTDIR, getattr(errno, "ESTALE", 116)):
		return "dosar"
	if nr in (errno.ENODEV, errno.ENXIO):
		return "nesuportat"
	if nr == errno.EBUSY:
		return "ocupat"
	if nr in ERORI_DIALECT:
		return "dialect"
	if nr in (errno.ENOSPC, errno.EDQUOT if hasattr(errno, "EDQUOT") else errno.ENOSPC):
		return "plin"
	if nr == errno.EROFS:
		return "citire"
	return "alta"


# ------------------------------------------------------------------ optiunile montarii (fara parola in nimic afisat)

def _virgule(text):
	# in optiunile cifs o virgula din valoare se scrie de doua ori
	return (text or u"").replace(u",", u",,")


def optiuniSmb(ip, utilizator, parola, domeniu, versiune, extra=u""):
	"""Sirul de optiuni pentru mount(2) cifs. Fara utilizator: oaspete (user= gol, nucleul face o sesiune nula)."""
	o = [u"ip=" + ip, u"vers=" + versiune, u"iocharset=utf8", u"uid=0", u"gid=0", u"file_mode=0664",
		u"dir_mode=0775", u"noserverino", u"nounix", u"soft", u"actimeo=1"]
	if utilizator:
		o.append(u"user=" + _virgule(utilizator))
		o.append(u"pass=" + _virgule(parola or u""))
		if domeniu:
			o.append(u"domain=" + _virgule(domeniu))
	else:
		o.append(u"user=")
		o.append(u"pass=")
	if extra:
		o.append(extra)
	return u",".join(o)


def optiuniNfs(ip, versiune, client_ip=u"", extra=u""):
	o = [u"addr=" + ip, u"vers=" + versiune, u"proto=tcp", u"soft", u"timeo=100", u"retrans=2", u"nosharecache"]
	if versiune == "3":
		o.append(u"nolock")
	elif client_ip:
		o.append(u"clientaddr=" + client_ip)
	if extra:
		o.append(extra)
	return u",".join(o)


def sursaSmb(gazda, dosar):
	parti = [p for p in (dosar or u"").replace(u"\\", u"/").split(u"/") if p]
	return u"//" + gazda + u"/" + u"/".join(parti)


def sursaNfs(gazda, dosar):
	return gazda + u":/" + (dosar or u"").replace(u"\\", u"/").strip(u"/")


def ipGazda(gazda):
	"""Adresa IPv4 a gazdei (nume sau adresa)."""
	return socket.getaddrinfo(gazda, None, socket.AF_INET, socket.SOCK_STREAM)[0][4][0]


def ipSpre(ip):
	"""Adresa receptorului pe drumul spre ip (NFSv4 o cere ca adresa de intoarcere)."""
	s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	try:
		s.connect((ip, 9))
		return s.getsockname()[0]
	finally:
		s.close()


def ajunge(ip, port, termen=TERMEN_TCP_S):
	"""None daca serverul raspunde pe port, altfel errno."""
	s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	s.settimeout(termen)
	try:
		s.connect((ip, port))
		return None
	except socket.timeout:
		return errno.ETIMEDOUT
	except OSError as e:
		return e.errno or errno.EHOSTUNREACH
	finally:
		s.close()


# ------------------------------------------------------------------ mount(2) / umount2(2)

def _libc():
	import ctypes
	import ctypes.util
	nume = ctypes.util.find_library("c") or "libc.so.6"
	libc = ctypes.CDLL(nume, use_errno=True)
	libc.mount.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_ulong, ctypes.c_char_p)
	libc.umount2.argtypes = (ctypes.c_char_p, ctypes.c_int)
	return libc


def _monteaza(libc, sursa, punct, fel, steaguri, optiuni):
	import ctypes
	r = libc.mount(sursa.encode("utf-8"), punct.encode("utf-8"), fel.encode("ascii"), steaguri,
		optiuni.encode("utf-8"))
	return 0 if r == 0 else (ctypes.get_errno() or errno.EIO)


def monteaza(cerere, libc=None, ajunge_fn=None, ip_fn=None):
	"""cerere: {fel: smb|nfs, gazda, dosar, punct, utilizator, parola, domeniu, citire (bool), versiune ('' = pe rand),
	extra}. -> {ok, vers, errno, cod}"""
	fel = cerere.get("fel")
	gazda = (cerere.get("gazda") or u"").strip()
	punct = cerere.get("punct") or u""
	if fel not in ("smb", "nfs") or not gazda or not punct.startswith("/media/net/"):
		return {"ok": False, "cod": "cerere", "errno": errno.EINVAL}
	try:
		ip = (ip_fn or ipGazda)(gazda)
	except (OSError, IndexError, UnicodeError):
		return {"ok": False, "cod": "nume", "errno": errno.EHOSTUNREACH}
	port = int(cerere.get("port") or 0) or (445 if fel == "smb" else 2049)
	nr = (ajunge_fn or ajunge)(ip, port)
	if nr is not None:
		return {"ok": False, "cod": "server", "errno": nr}
	try:
		if not os.path.isdir(punct):
			os.makedirs(punct, 0o755)
	except OSError as e:
		return {"ok": False, "cod": "punct", "errno": e.errno}
	libc = libc or _libc()
	steaguri = MS_NOSUID | MS_NODEV | MS_NOEXEC | (MS_RDONLY if cerere.get("citire") else 0)
	ales = cerere.get("versiune") or u""
	ultima = errno.EIO
	if fel == "smb":
		versiuni = (ales,) if ales else VERSIUNI_SMB
		sursa = sursaSmb(gazda, cerere.get("dosar"))
		for v in versiuni:
			nr = _monteaza(libc, sursa, punct, "cifs", steaguri, optiuniSmb(ip, cerere.get("utilizator"),
				cerere.get("parola"), cerere.get("domeniu"), v, cerere.get("extra") or u""))
			if nr == 0:
				return {"ok": True, "vers": v}
			ultima = nr
			if nr not in ERORI_DIALECT:
				break
	else:
		versiuni = (ales,) if ales else VERSIUNI_NFS
		sursa = sursaNfs(gazda, cerere.get("dosar"))
		try:
			client = ipSpre(ip)
		except OSError:
			client = u""
		grait = None      # prima eroare care spune ceva (dosar, drepturi), nu doar "alta versiune"
		for v in versiuni:
			nr = _monteaza(libc, sursa, punct, "nfs4" if v.startswith("4") else "nfs", steaguri,
				optiuniNfs(ip, v, client, cerere.get("extra") or u""))
			if nr == 0:
				return {"ok": True, "vers": v}
			ultima = nr
			if nr not in ERORI_DIALECT and grait is None:
				grait = nr
			if nr not in ERORI_DIALECT + (errno.EACCES, errno.EPERM, errno.ENOENT):
				break
		if grait is not None:
			ultima = grait
	try:
		os.rmdir(punct)
	except OSError:
		pass
	return {"ok": False, "cod": codEroare(ultima), "errno": ultima}


def demonteaza(cerere, libc=None):
	punct = cerere.get("punct") or u""
	if not punct.startswith("/media/net/") or "/.." in punct:
		return {"ok": False, "cod": "cerere", "errno": errno.EINVAL}
	libc = libc or _libc()
	import ctypes
	r = libc.umount2(punct.encode("utf-8"), MNT_DETACH)
	nr = 0 if r == 0 else (ctypes.get_errno() or errno.EIO)
	if nr not in (0, errno.EINVAL, errno.ENOENT):
		return {"ok": False, "cod": codEroare(nr), "errno": nr}
	try:
		os.rmdir(punct)
	except OSError:
		pass
	return {"ok": True}


def viteza(cerere, marime=MARIME_PROBA):
	"""Scrie `marime` octeti pe loc (cu fsync), ii citeste inapoi, sterge fisierul. -> {ok, scriere (MB/s), citire}."""
	punct = cerere.get("punct") or u""
	if not punct.startswith("/media/net/"):
		return {"ok": False, "cod": "cerere"}
	cale = os.path.join(punct, NUME_PROBA)
	bucata = os.urandom(1024 * 1024)
	try:
		t0 = time.time()
		with open(cale, "wb") as f:
			scris = 0
			while scris < marime:
				f.write(bucata)
				scris += len(bucata)
			f.flush()
			os.fsync(f.fileno())
		t1 = time.time()
		with open(cale, "rb") as f:
			while f.read(BUCATA):
				pass
		t2 = time.time()
	except (OSError, IOError) as e:
		try:
			os.remove(cale)
		except OSError:
			pass
		return {"ok": False, "cod": codEroare(e.errno or errno.EIO), "errno": e.errno}
	try:
		os.remove(cale)
	except OSError:
		pass
	mb = marime / (1024.0 * 1024.0)
	return {"ok": True, "scriere": round(mb / max(t1 - t0, 0.001), 1), "citire": round(mb / max(t2 - t1, 0.001), 1)}


# ------------------------------------------------------------------ puntea HTTP (numai 127.0.0.1)

def _interval(antet, marime):
	"""Range: bytes=a-b -> (inceput, sfarsit inclusiv) sau None (fara Range sau de neinteles)."""
	if not antet or not antet.strip().lower().startswith("bytes="):
		return None
	prima = antet.strip()[6:].split(",")[0].strip()
	a, _sep, b = prima.partition("-")
	try:
		if a == "":
			n = int(b)
			if marime is None or n <= 0:
				return None
			return max(0, marime - n), marime - 1
		inceput = int(a)
		sfarsit = int(b) if b else (marime - 1 if marime is not None else None)
		if marime is not None:
			sfarsit = min(sfarsit, marime - 1)
		return inceput, sfarsit
	except ValueError:
		return None


class SursaFtp(object):
	"""Un fisier pe FTP sau FTPS (prot_p: datele tot criptate)."""

	def __init__(self, t):
		self.t = t
		self._marime = None

	def _conectare(self):
		import ftplib
		t = self.t
		if t.get("tls"):
			import ssl
			ctx = ssl.create_default_context()
			if t.get("fara_verificare"):
				ctx.check_hostname = False
				ctx.verify_mode = ssl.CERT_NONE
			ftp = ftplib.FTP_TLS(timeout=20, context=ctx)
		else:
			ftp = ftplib.FTP(timeout=20)
		# calea vine ca octetii serverului (text latin-1, Components/HdsStocareRetea._caleFtp)
		ftp.encoding = "latin-1"
		ftp.connect(t["gazda"], int(t.get("port") or 21))
		ftp.login(t.get("utilizator") or "anonymous", t.get("parola") or "")
		if t.get("tls"):
			ftp.prot_p()
		ftp.voidcmd("TYPE I")
		return ftp

	def marime(self):
		if self._marime is None:
			ftp = self._conectare()
			try:
				self._marime = ftp.size(self.t["cale"])
			finally:
				try:
					ftp.quit()
				except Exception:
					ftp.close()
		return self._marime

	def citeste(self, inceput, scrie, cat=None):
		ftp = self._conectare()
		try:
			conn = ftp.transfercmd("RETR " + self.t["cale"], rest=inceput or None)
			ramas = cat
			try:
				while True:
					b = conn.recv(BUCATA if ramas is None else min(BUCATA, ramas))
					if not b:
						break
					scrie(b)
					if ramas is not None:
						ramas -= len(b)
						if ramas <= 0:
							break
			finally:
				conn.close()
		finally:
			try:
				ftp.close()
			except Exception:
				pass


class SursaHttp(object):
	"""Un fisier pe WebDAV (http sau https), cu Basic sau Digest."""

	def __init__(self, t):
		self.t = t
		self._marime = None
		self._provocare = None
		self._nc = 0

	def _cerere(self, metoda, antete):
		import http.client
		from Components import HdsReteaProtocoale as P
		t = self.t
		for _incercare in range(2):
			if t.get("tls"):
				import ssl
				ctx = ssl.create_default_context()
				if t.get("fara_verificare"):
					ctx.check_hostname = False
					ctx.verify_mode = ssl.CERT_NONE
				c = http.client.HTTPSConnection(t["gazda"], int(t.get("port") or 443), timeout=20, context=ctx)
			else:
				c = http.client.HTTPConnection(t["gazda"], int(t.get("port") or 80), timeout=20)
			a = dict(antete)
			a["User-Agent"] = "HDSatelit"
			if t.get("utilizator"):
				if self._provocare:
					self._nc += 1
					d = P.antetDigest(self._provocare, metoda, t["cale"], t["utilizator"], t.get("parola") or "",
						self._nc)
					if d:
						a["Authorization"] = d
				else:
					a["Authorization"] = P.antetBasic(t["utilizator"], t.get("parola") or "")
			c.request(metoda, t["cale"], headers=a)
			r = c.getresponse()
			if r.status == 401 and t.get("utilizator") and self._provocare is None:
				p = P.provocareDigest(r.getheader("WWW-Authenticate") or "")
				r.read()
				c.close()
				if p is None:
					return c, r
				self._provocare = p
				continue
			return c, r
		return c, r

	def marime(self):
		if self._marime is None:
			c, r = self._cerere("HEAD", {})
			try:
				if r.status >= 400:
					raise IOError("HTTP %d" % r.status)
				lung = r.getheader("Content-Length")
				self._marime = int(lung) if lung and lung.isdigit() else None
			finally:
				c.close()
		return self._marime

	def citeste(self, inceput, scrie, cat=None):
		antete = {}
		if inceput or cat is not None:
			antete["Range"] = "bytes=%d-%s" % (inceput, "" if cat is None else inceput + cat - 1)
		c, r = self._cerere("GET", antete)
		try:
			if r.status >= 400:
				raise IOError("HTTP %d" % r.status)
			if inceput and r.status != 206:
				# serverul nu stie Range: se sare citind
				ramas = inceput
				while ramas > 0:
					b = r.read(min(BUCATA, ramas))
					if not b:
						return
					ramas -= len(b)
			while True:
				b = r.read(BUCATA)
				if not b:
					break
				scrie(b)
		finally:
			c.close()


def sursaPentru(t):
	return SursaFtp(t) if t.get("fel") in ("ftp", "ftps") else SursaHttp(t)


def puntea(cerere, intrare=None, iesire=None):
	"""Porneste puntea pentru fisierele din cerere["tinte"] (lista), scrie portul si asteapta inchiderea intrarii."""
	import http.server
	import socketserver
	jeton = cerere.get("jeton") or ""
	tinte = [sursaPentru(t) for t in (cerere.get("tinte") or [])]
	ultima = [time.time()]

	class Cerere(http.server.BaseHTTPRequestHandler):
		protocol_version = "HTTP/1.1"

		def log_message(self, *a):
			pass

		def _tinta(self):
			parti = self.path.split("/")
			if len(parti) < 3 or parti[1] != jeton or not jeton:
				return None
			try:
				return tinte[int(parti[2])]
			except (ValueError, IndexError):
				return None

		def _raspunde(self, cu_corp):
			ultima[0] = time.time()
			sursa = self._tinta()
			if sursa is None:
				self.send_error(404)
				return
			try:
				marime = sursa.marime()
			except Exception:
				self.send_error(502)
				return
			interval = _interval(self.headers.get("Range"), marime)
			if interval is not None and marime is not None and interval[0] >= marime:
				self.send_response(416)
				self.send_header("Content-Range", "bytes */%d" % marime)
				self.send_header("Content-Length", "0")
				self.end_headers()
				return
			if interval is not None:
				inceput, sfarsit = interval
				self.send_response(206)
				if sfarsit is not None:
					self.send_header("Content-Length", str(sfarsit - inceput + 1))
					self.send_header("Content-Range", "bytes %d-%d/%s" % (inceput, sfarsit,
						marime if marime is not None else "*"))
				cat = None if sfarsit is None else sfarsit - inceput + 1
			else:
				inceput, cat = 0, None
				self.send_response(200)
				if marime is not None:
					self.send_header("Content-Length", str(marime))
			self.send_header("Accept-Ranges", "bytes")
			self.send_header("Content-Type", "application/octet-stream")
			self.end_headers()
			if not cu_corp:
				return
			try:
				sursa.citeste(inceput, self.wfile.write, cat)
			except (OSError, IOError, EOFError):
				self.close_connection = True
			except Exception:
				self.close_connection = True

		def do_GET(self):
			self._raspunde(True)

		def do_HEAD(self):
			self._raspunde(False)

	class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
		daemon_threads = True
		allow_reuse_address = True

	server = Server(("127.0.0.1", 0), Cerere)
	(iesire or sys.stdout).write(json.dumps({"ok": True, "port": server.server_address[1]}) + "\n")
	(iesire or sys.stdout).flush()

	def paza():
		# intrarea inchisa (enigma2 a oprit puntea sau a cazut) sau nimic cerut de mult: puntea se opreste
		intr = intrare or sys.stdin
		try:
			while intr.readline():
				pass
		except Exception:
			pass
		server.shutdown()

	def inactiv():
		while True:
			time.sleep(30)
			if time.time() - ultima[0] > MINUTE_INACTIV * 60:
				server.shutdown()
				return
	for f in (paza, inactiv):
		fir = threading.Thread(target=f)
		fir.daemon = True
		fir.start()
	server.serve_forever(poll_interval=1.0)
	server.server_close()


def main(argv=None):
	argv = sys.argv[1:] if argv is None else argv
	mod = argv[0] if argv else ""
	try:
		cerere = json.loads(sys.stdin.readline() or "{}")
	except ValueError:
		cerere = {}
	if mod == "punte":
		puntea(cerere)
		return 0
	functii = {"monteaza": monteaza, "demonteaza": demonteaza, "viteza": viteza}
	if mod not in functii:
		scrieRaspuns({"ok": False, "cod": "cerere"})
		return 2
	try:
		scrieRaspuns(functii[mod](cerere))
	except Exception as e:
		scrieRaspuns({"ok": False, "cod": "alta", "detaliu": e.__class__.__name__})
	return 0


if __name__ == "__main__":
	sys.exit(main())
