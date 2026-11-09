# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com & hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
# Galeria aprobata. Se apeleaza pe un fir de lucru, fara comenzi pe receptor.

from __future__ import absolute_import

import base64
import hashlib
import json
import os
import re
import shutil
import ssl
import tempfile
import threading
import time
from urllib.error import URLError
from urllib.parse import parse_qsl, quote, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener


API_URL = "https://stb.hdsatelit.com/api/galerie/v1/"
CALE_DATE = "/etc/enigma2/hdsatelit/sigle-pornire"
CALE_CACHE = "/tmp/hds-galerie-sigle"
TARGETS = {
	"bootlogo": "/usr/share/bootlogo.mvi",
	"backdrop": "/usr/share/backdrop.mvi",
	"radio": "/usr/share/enigma2/radio.mvi",
}
ORIGINALS = {
	"bootlogo": "/usr/share/hdsatelit/ecrane-pornire/grila.mvi",
	"backdrop": "/usr/share/hdsatelit/ecrane-pornire/grila.mvi",
	"radio": "/usr/share/enigma2/sigle-pornire/radio.mvi",
}
ROLES = ("bootlogo", "backdrop", "radio")
RESOLUTIONS = {"1280x720": (1280, 720), "1920x1080": (1920, 1080)}
MAX_MVI = 8 * 1024 * 1024
MAX_JSON = 1024 * 1024
MAX_PREVIEW = 512 * 1024
MAX_ITEMS = 300
MIN_FREE = 20 * 1024 * 1024
TIMEOUT = 12
TOTAL_TIMEOUT = 45
LOCK = threading.RLock()
_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_SHA = re.compile(r"^[a-f0-9]{64}$")
_CATALOG = None
_CATALOG_TIME = 0
_CATALOG_MORE = False
_PREVIEWS = {}
_STATS = None
_CONTRIBUTORS = None
_CONTRIBUTOR_CATALOG = None
_ANNOUNCE_LOCK = threading.RLock()
_ANNOUNCING = set()
_ANNOUNCE_STARTED = False
# Siglele private ale omului (08.11.2026): cele care nu se pot publica (sigla altei firme, poza gasita pe alte site-uri,
# hotararea echipei) raman ale autorului si le vede numai el, pe receptorul legat de contul lui. Dovada receptorului e
# jetonul de forum de la serverul testerilor (Components/HdsForumReceptor.jeton), trimis in X-HDS-Jeton. Lista sta numai
# in memorie; fara legare, fara retea sau la orice esec nu apare nimic si nu se strica nimic.
MOTIVE_PRIVATE = ("marca", "internet", "echipa")
PAUZA_PRIVATE = 600
_PRIVATE = None
_PRIVATE_CTX = None
_PRIVATE_PAUZA = 0


def receiverId():
	"""Numar aleator local, fara date despre receptor sau cont."""
	path = os.path.join(os.path.dirname(CALE_DATE), "galerie-receptor.id")
	with _ANNOUNCE_LOCK:
		try:
			value = _read(path, 33).decode("ascii").strip()
			if not re.fullmatch(r"[a-f0-9]{32}", value):
				raise ValueError("receptor")
			os.chmod(path, 0o600)
			return value
		except FileNotFoundError:
			pass
		os.makedirs(os.path.dirname(path), exist_ok=True)
		value = os.urandom(16).hex()
		try:
			fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
		except FileExistsError:
			return receiverId()
		with os.fdopen(fd, "wb") as output:
			output.write(value.encode("ascii"))
			output.flush()
			os.fsync(output.fileno())
		os.chmod(path, 0o600)
		_sync(os.path.dirname(path))
		return value


def _announcements():
	path = os.path.join(os.path.dirname(CALE_DATE), "galerie-descarcari.json")
	try:
		value = json.loads(_read(path, MAX_JSON).decode("ascii"))
	except FileNotFoundError:
		return path, {}
	if not isinstance(value, dict) or value.get("v") != 1 or not isinstance(value.get("items"), dict):
		raise ValueError("anunturi")
	for id_, entry in value["items"].items():
		if (not _id(id_) or not isinstance(entry, dict) or
			type(entry.get("tries")) is not int or entry["tries"] not in (1, 2) or
			type(entry.get("done")) is not bool):
			raise ValueError("anunturi")
	return path, value["items"]


def _postDownload(id_, receiver):
	"""POST fara cont, corp gol si cel mult 10 secunde de asteptare."""
	url = _url(API_URL + "descarcari/" + id_)
	opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()), _NoRedirect())
	request = Request(url, data=b"", headers={"X-HDS-Receptor": receiver,
		"User-Agent": "HDSatelit-Galerie/1", "Accept-Encoding": "identity"}, method="POST")
	with opener.open(request, timeout=10) as response:
		if response.getcode() != 200 or response.geturl() != url:
			raise ValueError("anunt")
		# Serverul nu trimite v la POST. Nu folosim cititorul catalogului.
		data = response.read(4097)
		if len(data) > 4096:
			raise ValueError("anunt")
		value = json.loads(data.decode("utf-8"))
		if not isinstance(value, dict) or value.get("ok") is not True or value.get("id") != id_:
			raise ValueError("anunt")


def _sendAnnouncements(ids):
	for id_ in ids:
		try:
			_postDownload(id_, receiverId())
			with _ANNOUNCE_LOCK:
				path, items = _announcements()
				if id_ in items:
					items[id_]["done"] = True
					_atomic(path, _encoded({"v": 1, "items": items}))
		except Exception:
			pass
		finally:
			with _ANNOUNCE_LOCK:
				_ANNOUNCING.discard(id_)


def _launchAnnouncements(ids):
	if ids:
		_ANNOUNCING.update(ids)
		thread = threading.Thread(target=_sendAnnouncements, args=(ids,), name="HdsGalerieDescarcari")
		thread.daemon = True
		try:
			thread.start()
		except Exception:
			_ANNOUNCING.difference_update(ids)
			raise


def announceDownload(id_):
	"""Chemata numai dupa punerea reusita. Esecul ramane nevazut."""
	try:
		if not _id(id_):
			return
		with _ANNOUNCE_LOCK:
			path, items = _announcements()
			if id_ in items:
				return
			items[id_] = {"tries": 1, "done": False}
			_atomic(path, _encoded({"v": 1, "items": items}))
			_launchAnnouncements([id_])
	except Exception:
		pass


def startupAnnouncements():
	"""O singura reincercare la pornire, apoi sigla ramane tinuta minte."""
	global _ANNOUNCE_STARTED
	try:
		with _ANNOUNCE_LOCK:
			if _ANNOUNCE_STARTED:
				return
			_ANNOUNCE_STARTED = True
			path, items = _announcements()
			ids = [id_ for id_, e in items.items() if not e["done"] and
				e["tries"] == 1 and id_ not in _ANNOUNCING]
			if ids:
				for id_ in ids:
					items[id_]["tries"] = 2
				_atomic(path, _encoded({"v": 1, "items": items}))
				_launchAnnouncements(ids)
	except Exception:
		pass


def stats(online=False):
	"""Numerele se citesc numai pe firul de retea; fara retea nu le aratam."""
	global _STATS
	with LOCK:
		if not online:
			return dict(_STATS) if _STATS is not None else None
	try:
		counts = _json(API_URL + "stats").get("counts")
		if not isinstance(counts, dict):
			raise ValueError("numere")
		clean = {}
		for id_, entry in counts.items():
			if (not _id(id_) or not isinstance(entry, dict) or
				any(type(entry.get(k)) is not int or entry[k] < 0 for k in ("likes", "downloads"))):
				raise ValueError("numere")
			clean[id_] = {k: entry[k] for k in ("likes", "downloads")}
		with LOCK:
			_STATS = clean
		return dict(clean)
	except Exception:
		with LOCK:
			_STATS = None
		return None


def contributors(online=False):
	"""Ordinea si XP-ul vin de la server. La esec uitam clasamentul."""
	global _CONTRIBUTORS
	with LOCK:
		if not online:
			return [dict(i) for i in _CONTRIBUTORS] if _CONTRIBUTORS is not None else None
	try:
		items = _json(API_URL + "contributori").get("items")
		if not isinstance(items, list) or len(items) > 10000:
			raise ValueError("contributori")
		clean, seen = [], set()
		for item in items:
			person = _contributor(item)
			if (person is None or person["id"] in seen or
				any(type(item.get(k)) is not int or item[k] < 0 for k in ("sigle", "likes", "xp"))):
				raise ValueError("contributori")
			seen.add(person["id"])
			if item["sigle"]:
				clean.append(dict(person, **{k: item[k] for k in ("sigle", "likes", "xp")}))
		with LOCK:
			_CONTRIBUTORS = clean
		return [dict(i) for i in clean]
	except Exception:
		with LOCK:
			_CONTRIBUTORS = None
		return None


class GalleryError(Exception):
	pass


def _forumReceptor():
	"""Modulul care tine jetonul de forum al receptorului (separat, ca probele sa-l poata inlocui)."""
	from Components import HdsForumReceptor
	return HdsForumReceptor


def contextPrivat():
	"""Pe firul interfetei (enigma2): ce trebuie firului de lucru ca sa ceara jetonul de forum, sau None daca receptorul
	nu e beta tester inscris (atunci nu se cere nimic serverului testerilor). Nu porneste reteaua."""
	try:
		ctx = _forumReceptor()._context()
	except Exception:
		return None
	return ctx if isinstance(ctx, dict) and ctx.get("inscris") else None


def _jetonForum(ctx):
	"""Pe firul de lucru: jetonul de forum (tinut o ora in memorie de HdsForumReceptor), dovada receptorului."""
	if not isinstance(ctx, dict) or not ctx.get("inscris"):
		raise GalleryError("Receptorul nu este legat de un cont.")
	try:
		jeton = _forumReceptor().jeton(ctx)
	except Exception as error:
		raise GalleryError("Receptorul nu are acum dovada pentru siglele private.") from error
	if (not isinstance(jeton, str) or not jeton.startswith("v1.") or len(jeton) > 1200 or
		any(ord(c) <= 32 or ord(c) > 126 for c in jeton)):
		raise GalleryError("Receptorul nu are acum dovada pentru siglele private.")
	return jeton


def _antetPrivat():
	with LOCK:
		ctx = _PRIVATE_CTX
	return {"X-HDS-Jeton": _jetonForum(ctx)}


def _privata(id_):
	"""Sigla privata din memorie, sau None."""
	with LOCK:
		return next((dict(i) for i in (_PRIVATE or []) if i["id"] == id_), None)


def privateCatalog(ctx=None, online=False):
	"""Siglele private ale omului: online=False numai memoria (firul interfetei). Cu online si ctx (din contextPrivat,
	citit pe firul interfetei), pe firul de lucru: jetonul, apoi GET private. Receptor nelegat: lista goala. La esec
	lista se uita si nu se mai incearca PAUZA_PRIVATE secunde (limita jetoanelor pe ora a serverului testerilor)."""
	global _PRIVATE, _PRIVATE_CTX, _PRIVATE_PAUZA
	with LOCK:
		if not online or ctx is None or time.monotonic() < _PRIVATE_PAUZA:
			return [dict(i) for i in (_PRIVATE or [])]
	try:
		value = _json(API_URL + "private", {"X-HDS-Jeton": _jetonForum(ctx)})
		items = value.get("items")
		if not isinstance(items, list) or len(items) > MAX_ITEMS or type(value.get("legat")) is not bool:
			raise GalleryError("Lista siglelor private nu este valida.")
		clean = [_item(item, privat=True) for item in items]
		if len(set(item["id"] for item in clean)) != len(clean):
			raise GalleryError("Lista siglelor private contine sigle repetate.")
		with LOCK:
			_PRIVATE, _PRIVATE_CTX = clean, dict(ctx)
		return [dict(i) for i in clean]
	except Exception as error:
		print("[HdsGalerieSigle] siglele private: %s" % error)
		with LOCK:
			_PRIVATE = None
			_PRIVATE_PAUZA = time.monotonic() + PAUZA_PRIVATE
		return []


def _text(value, maximum):
	if not isinstance(value, str):
		return ""
	return "".join(c for c in value if c >= " " and c != "\x7f")[:maximum].strip()


def _id(value):
	return isinstance(value, str) and bool(_ID.fullmatch(value))


def _contributorId(value):
	return (isinstance(value, str) and 0 < len(value) <= 128 and
		all(c >= " " and c != "\x7f" for c in value))


def _contributor(value):
	"""Contul incarcarii este separat de campul liber al autorului."""
	if not isinstance(value, dict) or not _contributorId(value.get("id")):
		return None
	name = _text(value.get("nume"), 80)
	return {"id": value["id"], "nume": name} if name else None


def _url(url):
	if not isinstance(url, str) or any(ord(c) <= 32 for c in url) or "\\" in url:
		raise GalleryError("Adresa galeriei nu este valida.")
	try:
		parts = urlsplit(url)
		base = urlsplit(API_URL)
	except ValueError as error:
		raise GalleryError("Adresa galeriei nu este valida.") from error
	try:
		pairs = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True)
		query_ok = not parts.query or (parts.path == base.path and pairs and
			len(dict(pairs)) == len(pairs) and
			"&".join(k + "=" + quote(v, safe="") for k, v in pairs) == parts.query and
			all((k == "contributor" and _contributorId(v)) or
				(k == "offset" and re.fullmatch(r"[1-9][0-9]{0,6}", v) and int(v) <= 1000000)
				for k, v in pairs))
		valid = (parts.scheme == "https" and parts.hostname == base.hostname and
			parts.port in (None, 443) and not parts.username and not parts.password and
			query_ok and not parts.fragment and "%" not in parts.path and parts.path.startswith(base.path) and
			all(p not in (".", "..") for p in parts.path.split("/")))
	except ValueError:
		valid = False
	if not valid:
		raise GalleryError("Fisierul nu vine din galeria HD Satelit.")
	return url


class _NoRedirect(HTTPRedirectHandler):
	def redirect_request(self, req, fp, code, msg, headers, newurl):
		raise GalleryError("Galeria a cerut o redirectionare. Incearca mai tarziu.")


def _fetch(url, limit, mime, headers=None):
	"""HTTPS verificat, fara proxy din mediu, redirectionari sau corp nelimitat. headers: numai X-HDS-Jeton (privatele)."""
	_url(url)
	opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()), _NoRedirect())
	antete = {"User-Agent": "HDSatelit-Galerie/1", "Accept-Encoding": "identity"}
	if headers:
		antete.update((k, v) for k, v in headers.items() if k == "X-HDS-Jeton")
	request = Request(url, headers=antete)
	start = time.monotonic()
	try:
		with opener.open(request, timeout=TIMEOUT) as response:
			if response.getcode() != 200 or response.geturl() != url:
				raise GalleryError("Galeria nu a trimis fisierul cerut.")
			if response.headers.get("Content-Encoding", "identity").lower() != "identity":
				raise GalleryError("Galeria a trimis un fisier comprimat neasteptat.")
			type_ = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
			if type_ not in mime:
				raise GalleryError("Galeria a trimis alt tip de fisier.")
			length = response.headers.get("Content-Length")
			if length is not None and (not length.isdigit() or not 0 < int(length) <= limit):
				raise GalleryError("Fisierul din galerie este prea mare sau gol.")
			data = bytearray()
			while True:
				if time.monotonic() - start > TOTAL_TIMEOUT:
					raise GalleryError("Descarcarea a durat prea mult. Incearca din nou.")
				chunk = response.read(min(65536, limit + 1 - len(data)))
				if not chunk:
					break
				data.extend(chunk)
				if len(data) > limit:
					raise GalleryError("Fisierul din galerie este prea mare.")
			if not data or (length is not None and len(data) != int(length)):
				raise GalleryError("Descarcarea nu este intreaga. Incearca din nou.")
			return bytes(data)
	except (URLError, OSError, ValueError) as error:
		raise GalleryError("Nu am putut citi galeria. Verifica internetul si data receptorului.") from error


def _json(url, headers=None):
	try:
		data = (_fetch(url, MAX_JSON, ("application/json",)) if headers is None else
			_fetch(url, MAX_JSON, ("application/json",), headers))
		value = json.loads(data.decode("utf-8"))
	except (ValueError, UnicodeError) as error:
		raise GalleryError("Lista galeriei nu este intreaga.") from error
	if not isinstance(value, dict) or value.get("ok") is not True or value.get("v") != 1:
		raise GalleryError("Galeria nu este disponibila acum.")
	return value


def _metadata(value, expected):
	if not isinstance(value, dict) or value.get("url") != expected:
		raise GalleryError("Adresa fisierului din galerie nu este valida.")
	_url(expected)
	size = value.get("size")
	sha = value.get("sha256")
	if (type(size) is not int or not 4096 <= size <= MAX_MVI or
		not isinstance(sha, str) or not _SHA.fullmatch(sha)):
		raise GalleryError("Datele fisierului din galerie nu sunt valide.")
	return {"url": expected, "size": size, "sha256": sha}


def _item(value, privat=False):
	if not isinstance(value, dict) or not _id(value.get("id")):
		raise GalleryError("Sigla din galerie nu este valida.")
	if privat:
		# numai din GET private (cu jetonul receptorului): starea si codul motivului
		if value.get("state") != "private" or value.get("motiv_privat") not in MOTIVE_PRIVATE:
			raise GalleryError("Sigla privata nu este valida.")
	elif (value.get("approved") is False or value.get("status", "approved") != "approved" or
		value.get("state", "approved") != "approved"):
		raise GalleryError("Sigla nu este aprobata pentru galerie.")
	id_ = value["id"]
	variants = value.get("variants")
	if not isinstance(variants, dict):
		raise GalleryError("Sigla nu are fisiere pentru receptor.")
	clean = {}
	for size in RESOLUTIONS:
		roles = variants.get(size)
		if not isinstance(roles, dict):
			continue
		clean[size] = {}
		for role in ROLES:
			if role in roles:
				url = API_URL + "files/%s/%s/%s.mvi" % (id_, size, role)
				clean[size][role] = _metadata(roles[role], url)
	if not any(clean.values()):
		raise GalleryError("Sigla nu are fisiere pentru receptor.")
	preview = API_URL + "files/%s/preview.jpg" % id_
	if value.get("preview") != preview:
		raise GalleryError("Previzualizarea siglei nu este valida.")
	result = {"id": id_, "title": _text(value.get("title"), 120) or id_,
		"author": _text(value.get("author"), 80), "kind": _text(value.get("kind"), 30),
		"preview": preview, "variants": clean, "contributor": _contributor(value.get("contributor"))}
	if privat:
		# fara numere: o privata nu primeste like-uri si nu se numara
		result.update({"privata": True, "motiv": value["motiv_privat"]})
	elif all(type(value.get(k)) is int and value[k] >= 0 for k in ("likes", "downloads")):
		result.update({k: value[k] for k in ("likes", "downloads")})
	return result


def cachedCatalog(contributor=None):
	"""Numai memoria; citirea de pe firul interfetei nu porneste reteaua."""
	with LOCK:
		if contributor:
			cached = (_CONTRIBUTOR_CATALOG or {}).get(contributor)
			items = cached[0] if cached else None
		else:
			items = _CATALOG
		return {"ok": items is not None, "items": list(items or [])}


def catalog(contributor=None):
	global _CATALOG, _CATALOG_TIME, _CATALOG_MORE, _CONTRIBUTOR_CATALOG
	def result(items, more):
		message = ""
		if more:
			message = ("Se arata cele mai noi %d de sigle. "
				"Galeria completa este pe stb.hdsatelit.com.") % len(items)
		return {"ok": True, "items": list(items), "truncated": more,
			"message": message}
	try:
		if contributor is not None and not _contributorId(contributor):
			raise GalleryError("Lista galeriei este prea mare sau nu este valida.")
		with LOCK:
			cached = (_CONTRIBUTOR_CATALOG or {}).get(contributor)
			if contributor and cached and time.monotonic() - cached[1] < 60:
				return result(cached[0], cached[2])
			if not contributor and _CATALOG is not None and time.monotonic() - _CATALOG_TIME < 60:
				return result(_CATALOG, _CATALOG_MORE)
		clean = []
		offset = 0
		more = False
		for _page in range(3):
			query = ["contributor=" + quote(contributor, safe="")] if contributor else []
			if offset:
				query.append("offset=%d" % offset)
			data = _json(API_URL + ("?" + "&".join(query) if query else ""))
			items = data.get("items")
			if not isinstance(items, list) or len(items) > MAX_ITEMS - len(clean):
				raise GalleryError("Lista galeriei este prea mare sau nu este valida.")
			clean.extend(_item(item) for item in items)
			next_ = data.get("next_offset")
			if next_ is None:
				break
			if not items or type(next_) is not int or not offset < next_ <= 1000000:
				raise GalleryError("Pagina urmatoare a galeriei nu este valida.")
			offset = next_
		else:
			more = True
		if len(set(item["id"] for item in clean)) != len(clean):
			raise GalleryError("Lista galeriei contine sigle repetate.")
		if contributor and any((i.get("contributor") or {}).get("id") != contributor for i in clean):
			raise GalleryError("Galeria a trimis alta sigla.")
		with LOCK:
			if contributor:
				if _CONTRIBUTOR_CATALOG is None:
					_CONTRIBUTOR_CATALOG = {}
				_CONTRIBUTOR_CATALOG[contributor] = (clean, time.monotonic(), more)
				# TV si web pot alege oameni diferiti. Memoria ramane marginita.
				while len(_CONTRIBUTOR_CATALOG) > 4:
					old = min(_CONTRIBUTOR_CATALOG, key=lambda k: _CONTRIBUTOR_CATALOG[k][1])
					del _CONTRIBUTOR_CATALOG[old]
			else:
				_CATALOG, _CATALOG_TIME, _CATALOG_MORE = clean, time.monotonic(), more
		return result(clean, more)
	except GalleryError as error:
		with LOCK:
			if contributor:
				if _CONTRIBUTOR_CATALOG is not None:
					_CONTRIBUTOR_CATALOG.pop(contributor, None)
			else:
				_CATALOG = None
				_CATALOG_TIME = 0
		return {"ok": False, "items": [], "message": str(error)}


def _detail(id_):
	if not _id(id_):
		raise GalleryError("Sigla ceruta nu exista.")
	data = _json(API_URL + "items/" + id_)
	item = _item(data.get("item"))
	if item["id"] != id_:
		raise GalleryError("Galeria a trimis alta sigla.")
	return item


def resolution(width=1920, height=1080):
	try:
		return "1920x1080" if int(width) >= 1920 and int(height) >= 1080 else "1280x720"
	except (ValueError, TypeError):
		return "1920x1080"


def _mpeg2(data, size):
	"""Flux MPEG-2 elementar, dimensiuni HD si numai cadre I, fara decodor extern."""
	if size not in RESOLUTIONS or not 4096 <= len(data) <= MAX_MVI or data[:4] != b"\x00\x00\x01\xb3":
		raise GalleryError("Fisierul nu este un ecran MPEG-2 HD intreg.")
	expected = RESOLUTIONS[size]
	position = 0
	sequence = False
	extension = False
	picture = False
	slices = 0
	steps = 0
	while position >= 0:
		steps += 1
		if steps > 100000 or position + 4 > len(data):
			raise GalleryError("Fisierul MPEG-2 nu este intreg.")
		code = data[position + 3]
		payload = position + 4
		if code == 0xb3:
			if payload + 8 > len(data):
				raise GalleryError("Antetul MPEG-2 nu este intreg.")
			width = (data[payload] << 4) | (data[payload + 1] >> 4)
			height = ((data[payload + 1] & 15) << 8) | data[payload + 2]
			if (width, height) != expected or (data[payload + 3] & 15) not in range(1, 9):
				raise GalleryError("Fisierul nu are rezolutia aleasa.")
			sequence = True
		elif code == 0xb5:
			if payload >= len(data):
				raise GalleryError("Antetul MPEG-2 nu este intreg.")
			if data[payload] >> 4 == 1:
				if payload + 6 > len(data) or not sequence:
					raise GalleryError("Antetul MPEG-2 nu este intreg.")
				bits = int.from_bytes(data[payload:payload + 6], "big")
				if ((bits >> 31) & 3) or ((bits >> 29) & 3):
					raise GalleryError("Fisierul nu are rezolutia aleasa.")
				extension = True
		elif code == 0:
			if payload + 4 > len(data) or not extension or ((data[payload + 1] >> 3) & 7) != 1:
				raise GalleryError("Fisierul nu este un cadru I MPEG-2.")
			picture = True
		elif 1 <= code <= 0xaf:
			if not picture or payload + 2 > len(data):
				raise GalleryError("Fisierul MPEG-2 nu este intreg.")
			slices += 1
		elif code not in (0xb2, 0xb7, 0xb8):
			raise GalleryError("Fisierul nu este un flux MPEG-2 pentru receptor.")
		position = data.find(b"\x00\x00\x01", payload)
	if not (sequence and extension and picture and slices):
		raise GalleryError("Fisierul nu contine un ecran MPEG-2 intreg.")
	return expected


def _sync(directory):
	try:
		fd = os.open(directory or ".", os.O_RDONLY)
	except OSError:
		return
	try:
		os.fsync(fd)
	except OSError:
		pass
	finally:
		os.close(fd)


def _atomic(path, data):
	"""Scrie alaturi si verifica inainte de inlocuire."""
	directory = os.path.dirname(path)
	os.makedirs(directory, exist_ok=True)
	fd, temporary = tempfile.mkstemp(prefix=".hds-sigla-", dir=directory)
	try:
		with os.fdopen(fd, "wb") as output:
			output.write(data)
			output.flush()
			os.fsync(output.fileno())
		os.chmod(temporary, 0o644)
		if _read(temporary, len(data) + 1) != data:
			raise GalleryError("Copia siglei nu este intreaga.")
		os.replace(temporary, path)
		_sync(directory)
	finally:
		if os.path.exists(temporary):
			os.unlink(temporary)


def _read(path, limit=MAX_MVI):
	if os.path.islink(path):
		raise GalleryError("Calea siglei nu este sigura.")
	with open(path, "rb") as source:
		data = source.read(limit + 1)
	if len(data) > limit:
		raise GalleryError("Fisierul siglei este prea mare.")
	return data


def _path(name):
	return os.path.join(CALE_DATE, name)


def _encoded(value):
	return json.dumps(value, ensure_ascii=True, sort_keys=True).encode("ascii")


def _state():
	try:
		value = json.loads(_read(_path("alegeri.json"), 65536).decode("utf-8"))
	except FileNotFoundError:
		return {"v": 1, "roles": {}}
	except (ValueError, UnicodeError) as error:
		raise GalleryError("Alegerea salvata nu este intreaga. Pune inapoi sigla HD Satelit.") from error
	_validate_state(value)
	return value


def _validate_state(value):
	if not isinstance(value, dict) or value.get("v") != 1 or not isinstance(value.get("roles"), dict):
		raise GalleryError("Alegerea salvata nu este valida.")
	for role, item in value["roles"].items():
		if role not in ROLES or not isinstance(item, dict) or not _id(item.get("id")):
			raise GalleryError("Alegerea salvata nu este valida.")
		if item.get("resolution") not in RESOLUTIONS:
			raise GalleryError("Rezolutia salvata nu este valida.")
		if not isinstance(item.get("sha256"), str) or not _SHA.fullmatch(item["sha256"]):
			raise GalleryError("Rezumatul siglei salvate nu este valid.")
		if type(item.get("size")) is not int or not 4096 <= item["size"] <= MAX_MVI:
			raise GalleryError("Marimea siglei salvate nu este valida.")


def _target(role):
	if role not in ROLES:
		raise GalleryError("Alege pornire, asteptare sau radio.")
	path = TARGETS[role]
	if os.path.islink(path) or os.path.realpath(path) != os.path.abspath(path):
		raise GalleryError("Calea locala a siglei nu este sigura.")
	if role == "bootlogo" and not os.path.isfile(path):
		raise GalleryError("Receptorul nu are un fisier pentru sigla timpurie. Alege imaginea de pornire.")
	return path


def configureRadio(path):
	"""Calea citita local din configuratia imaginii, niciodata dintr-o cerere web."""
	if not isinstance(path, str) or not path.startswith("/usr/share/enigma2/") or not path.endswith(".mvi"):
		raise GalleryError("Calea locala a fundalului radio nu este valida.")
	if os.path.realpath(path) != path or os.path.islink(path):
		raise GalleryError("Calea locala a fundalului radio nu este sigura.")
	with LOCK:
		TARGETS["radio"] = path


def _checked(data, meta):
	if len(data) != meta["size"] or hashlib.sha256(data).hexdigest() != meta["sha256"]:
		raise GalleryError("Fisierul descarcat nu este intreg. Incearca din nou.")
	return data


def _recover():
	"""O intrerupere revine la fisierul si alegerea de dinaintea schimbarii."""
	journal = _path("tranzactie.json")
	try:
		value = json.loads(_read(journal, 131072).decode("utf-8"))
	except FileNotFoundError:
		return
	except (ValueError, UnicodeError) as error:
		raise GalleryError("Schimbarea intrerupta nu poate fi refacuta automat.") from error
	if not isinstance(value, dict) or value.get("v") != 1 or value.get("role") not in ROLES:
		raise GalleryError("Schimbarea intrerupta nu este valida.")
	_validate_state(value.get("state"))
	state_bytes = _encoded(value["state"])
	if "state_raw" in value:
		try:
			if not isinstance(value["state_raw"], str):
				raise ValueError("state_raw")
			state_bytes = base64.b64decode(value["state_raw"], validate=True)
			if len(state_bytes) > 65536:
				raise ValueError("state_raw")
		except (ValueError, UnicodeError) as error:
			raise GalleryError("Copia alegerii anterioare nu este valida.") from error
	target = _target(value["role"])
	if value.get("target") != target:
		raise GalleryError("Fundalul local s-a schimbat. Nu am atins fisierele.")
	previous = value.get("previous")
	if previous is not None:
		if (not isinstance(previous, dict) or type(previous.get("size")) is not int or
			not 0 <= previous["size"] <= MAX_MVI or not isinstance(previous.get("sha256"), str) or
			not _SHA.fullmatch(previous["sha256"])):
			raise GalleryError("Copia de siguranta nu este valida.")
		_atomic(target, _checked(_read(_path("precedenta.mvi")), previous))
	elif os.path.exists(target):
		os.unlink(target)
		_sync(os.path.dirname(target))
	_atomic(_path("alegeri.json"), state_bytes)
	os.unlink(journal)
	_sync(CALE_DATE)


def _transaction(role, data, state, old_state_bytes=None):
	target = _target(role)
	old_state = _state() if old_state_bytes is None else {"v": 1, "roles": {}}
	previous = None
	if os.path.exists(target):
		old_data = _read(target)
		previous = {"size": len(old_data), "sha256": hashlib.sha256(old_data).hexdigest()}
		_atomic(_path("precedenta.mvi"), old_data)
	journal = _path("tranzactie.json")
	entry = {"v": 1, "role": role, "target": target, "previous": previous, "state": old_state}
	if old_state_bytes is not None:
		entry["state_raw"] = base64.b64encode(old_state_bytes).decode("ascii")
	_atomic(journal, _encoded(entry))
	try:
		_atomic(target, data)
		_atomic(_path("alegeri.json"), _encoded(state))
		os.unlink(journal)
		_sync(CALE_DATE)
	except Exception:
		_recover()
		raise


def _cleanup(state):
	keep = set(item["sha256"] + ".mvi" for item in state["roles"].values())
	try:
		keep.update(item["sha256"] + ".mvi" for item in downloaded())
	except (OSError, GalleryError):
		return
	directory = _path("alese")
	try:
		for name in os.listdir(directory):
			if re.fullmatch(r"[a-f0-9]{64}\.mvi", name) and name not in keep:
				try:
					os.unlink(os.path.join(directory, name))
				except OSError:
					pass
	except OSError:
		pass


def downloaded():
	"""Siglele pastrate pe receptor, inclusiv alegerea din versiunea veche."""
	with LOCK:
		try:
			value = json.loads(_read(_path("descarcate.json"), MAX_JSON).decode("utf-8"))
		except FileNotFoundError:
			value = {"v": 1, "items": []}
		except (ValueError, UnicodeError) as error:
			raise GalleryError("Lista siglelor descarcate nu este intreaga.") from error
		if (not isinstance(value, dict) or value.get("v") != 1 or
			not isinstance(value.get("items"), list) or len(value["items"]) > MAX_ITEMS):
			raise GalleryError("Lista siglelor descarcate nu este valida.")
		items = value["items"]
		for item in items:
			if not isinstance(item, dict) or item.get("role") not in ROLES:
				raise GalleryError("Sigla descarcata nu este valida.")
			_validate_state({"v": 1, "roles": {item["role"]: item}})
		for role, item in _state()["roles"].items():
			if item.get("source") == "factory":
				continue
			if not any(i["id"] == item["id"] and i["role"] == role and
					i["resolution"] == item["resolution"] for i in items):
				items.append(dict(item, role=role))
		return items


def localPath(item):
	"""Calea copiei verificate la descarcare; nu foloseste numele autorului."""
	sha = item.get("sha256")
	if not isinstance(sha, str) or not _SHA.fullmatch(sha):
		return None
	path = _path(os.path.join("alese", sha + ".mvi"))
	return path if os.path.isfile(path) and not os.path.islink(path) else None


def _preserveDownloads():
	"""Pastreaza si alegerile facute inainte sa existe lista descarcarilor."""
	items = downloaded()
	if len(items) > MAX_ITEMS:
		raise GalleryError("Lista siglelor descarcate este plina.")
	path = _path("descarcate.json")
	data = _encoded({"v": 1, "items": items})
	try:
		if _read(path, MAX_JSON) == data:
			return
	except FileNotFoundError:
		pass
	_atomic(path, data)


def localPreview(id_):
	if not _id(id_):
		return None
	for directory in (_path("previzualizari"), CALE_CACHE):
		path = os.path.join(directory, id_ + ".jpg")
		if os.path.isfile(path) and not os.path.islink(path):
			return path
	return None


def install(id_, role="backdrop", resolution="1920x1080"):
	try:
		if not _id(id_) or role not in ROLES or resolution not in RESOLUTIONS:
			raise GalleryError("Alege rolul siglei si rezolutia 720p sau 1080p.")
		with LOCK:
			_recover()
			_target(role)
			cached = next((i for i in downloaded() if i["id"] == id_ and
				i["role"] == role and i["resolution"] == resolution and localPath(i)), None)
			if cached:
				data = _checked(_read(localPath(cached)), cached)
		privata = None if cached else _privata(id_)
		if cached:
			item, meta = cached, cached
		elif privata is not None:
			# sigla privata a omului: aceleasi adrese, cu jetonul receptorului
			item = privata
			meta = item["variants"].get(resolution, {}).get(role)
			if meta is None:
				raise GalleryError("Sigla nu are varianta aleasa. Alege alta rezolutie.")
			data = _checked(_fetch(meta["url"], meta["size"],
				("video/mpeg", "application/octet-stream"), _antetPrivat()), meta)
		else:
			item = _detail(id_)
			meta = item["variants"].get(resolution, {}).get(role)
			if meta is None:
				raise GalleryError("Sigla nu are varianta aleasa. Alege alta rezolutie.")
			data = _checked(_fetch(meta["url"], meta["size"],
				("video/mpeg", "application/octet-stream")), meta)
		_mpeg2(data, resolution)
		with LOCK:
			_recover()
			target = _target(role)
			os.makedirs(CALE_DATE, exist_ok=True)
			if shutil.disk_usage(CALE_DATE).free < MIN_FREE + len(data) * 3:
				raise GalleryError("Nu mai este loc in memoria receptorului.")
			state = _state()
			record = {"id": id_, "title": item["title"], "author": item["author"],
				"resolution": resolution, "sha256": meta["sha256"], "size": meta["size"],
				"contributor": item.get("contributor")}
			if item.get("privata"):
				# tinut minte pe receptor: si fara retea lista o arata marcata privata
				record.update({"privata": True, "motiv": item.get("motiv")})
			try:
				already = state["roles"].get(role) == record and _read(target) == data
			except FileNotFoundError:
				already = False
			if not already:
				_atomic(_path(os.path.join("alese", meta["sha256"] + ".mvi")), data)
				items = downloaded()
				items = [i for i in items if not (i["id"] == id_ and
					i["role"] == role and i["resolution"] == resolution)]
				if len(items) >= MAX_ITEMS:
					raise GalleryError("Lista siglelor descarcate este plina.")
				items.append(dict(record, role=role))
				_atomic(_path("descarcate.json"), _encoded({"v": 1, "items": items}))
				preview_path = localPreview(id_)
				if preview_path:
					try:
						image = _read(preview_path, MAX_PREVIEW)
						_jpeg(image)
						_atomic(_path(os.path.join("previzualizari", id_ + ".jpg")), image)
					except (OSError, GalleryError):
						pass
				state["roles"][role] = record
				_transaction(role, data, state)
				_cleanup(state)
		if not item.get("privata"):
			# o privata nu se numara (serverul ar raspunde 404, iar anuntul s-ar reincerca la pornire)
			announceDownload(id_)
		return {"ok": True, "id": id_, "role": role, "resolution": resolution,
			"message": "Sigla a fost pusa. Se vede la urmatoarea pornire sau deschidere a radioului."}
	except (GalleryError, OSError) as error:
		return {"ok": False, "message": str(error)}


def _factory(role):
	source = ORIGINALS[role]
	if role in ("bootlogo", "backdrop"):
		try:
			from Components import HdsEcranePornire
			source = HdsEcranePornire.caleEcran("galerie", HdsEcranePornire.implicit()) or source
		except ImportError:
			pass
	data = _read(source)
	# Fisierele instalate de imagine sunt de incredere, dar nu se pune o copie trunchiata.
	if len(data) < 4096 or data[:4] != b"\x00\x00\x01\xb3":
		raise GalleryError("Sigla HD Satelit lipseste sau nu este intreaga.")
	return data


def restore(role="backdrop"):
	try:
		if role not in ROLES:
			raise GalleryError("Alege pornire, asteptare sau radio.")
		with LOCK:
			_target(role)
		data = _factory(role)
		with LOCK:
			_recover()
			old_state_bytes = None
			try:
				state = _state()
			except GalleryError:
				old_state_bytes = _read(_path("alegeri.json"), 65536)
				_atomic(_path("alegeri-nevalide.json"), old_state_bytes)
				state = {"v": 1, "roles": {}}
			if old_state_bytes is None:
				_preserveDownloads()
			width = (data[4] << 4) | (data[5] >> 4)
			height = ((data[5] & 15) << 8) | data[6]
			size = "%dx%d" % (width, height)
			_mpeg2(data, size)
			sha = hashlib.sha256(data).hexdigest()
			_atomic(_path(os.path.join("alese", sha + ".mvi")), data)
			state["roles"][role] = {"id": "hd-satelit", "title": "HD Satelit", "author": "HD Satelit",
				"source": "factory", "resolution": size, "sha256": sha, "size": len(data)}
			_transaction(role, data, state, old_state_bytes)
			_cleanup(state)
		return {"ok": True, "role": role, "message": "Sigla HD Satelit a fost pusa inapoi."}
	except (GalleryError, OSError) as error:
		return {"ok": False, "message": str(error)}


def status():
	available = [role for role in ROLES if role != "bootlogo" or
		(os.path.isfile(TARGETS[role]) and not os.path.islink(TARGETS[role]))]
	try:
		with LOCK:
			state = _state()
		return {"ok": True, "roles": state["roles"], "available_roles": available, "message": ""}
	except (GalleryError, OSError) as error:
		return {"ok": False, "roles": {}, "available_roles": available, "message": str(error)}


def _jpeg(data):
	if len(data) < 128 or data[:3] != b"\xff\xd8\xff" or data[-2:] != b"\xff\xd9":
		raise GalleryError("Previzualizarea nu este un JPG intreg.")
	position = 2
	for _step in range(2000):
		if position + 4 > len(data) or data[position] != 255:
			break
		marker = data[position + 1]
		if marker == 255:
			position += 1
			continue
		length = int.from_bytes(data[position + 2:position + 4], "big")
		if length < 2 or position + length + 2 > len(data):
			break
		if 0xc0 <= marker <= 0xcf and marker not in (0xc4, 0xc8, 0xcc):
			if length < 8:
				break
			height = int.from_bytes(data[position + 5:position + 7], "big")
			width = int.from_bytes(data[position + 7:position + 9], "big")
			if 16 <= width <= 1920 and 16 <= height <= 1080:
				return
			break
		if marker in (0xda, 0xd9):
			break
		position += length + 2
	raise GalleryError("Previzualizarea are o marime nevalida.")


def preview(id_):
	try:
		if not _id(id_):
			raise GalleryError("Sigla ceruta nu exista.")
		path = localPreview(id_)
		if path:
			_jpeg(_read(path, MAX_PREVIEW))
			return {"ok": True, "path": path, "mime": "image/jpeg", "message": ""}
		with LOCK:
			cached = _PREVIEWS.get(id_)
			if cached and time.monotonic() - cached[1] < 300 and os.path.isfile(cached[0]):
				return {"ok": True, "path": cached[0], "mime": "image/jpeg", "message": ""}
		item = _privata(id_)
		if item is not None:
			data = _fetch(item["preview"], MAX_PREVIEW, ("image/jpeg",), _antetPrivat())
		else:
			item = _detail(id_)
			data = _fetch(item["preview"], MAX_PREVIEW, ("image/jpeg",))
		_jpeg(data)
		with LOCK:
			path = os.path.join(CALE_CACHE, id_ + ".jpg")
			_atomic(path, data)
			if any(i["id"] == id_ for i in downloaded()):
				_atomic(_path(os.path.join("previzualizari", id_ + ".jpg")), data)
			_PREVIEWS[id_] = (path, time.monotonic())
			while len(_PREVIEWS) > 16:
				old = min(_PREVIEWS, key=lambda key: _PREVIEWS[key][1])
				old_path, _when = _PREVIEWS.pop(old)
				try:
					os.unlink(old_path)
				except OSError:
					pass
		return {"ok": True, "path": path, "mime": "image/jpeg", "message": ""}
	except (GalleryError, OSError) as error:
		return {"ok": False, "path": None, "message": str(error)}


def managesBackdrop():
	"""Sub LOCK: chiar si o alegere stricata impiedica suprascrierea ei la pornire."""
	try:
		return "backdrop" in _state()["roles"]
	except (GalleryError, OSError):
		return True


def putLocalBackdrop(data):
	"""Sub LOCK: o alegere locala explicita preia fundalul cu revenire la esec."""
	_recover()
	state = _state()
	_preserveDownloads()
	state["roles"].pop("backdrop", None)
	_transaction("backdrop", data, state)
	_cleanup(state)


def startup():
	"""Fara retea: recupereaza o intrerupere si pastreaza alegerea la actualizare."""
	startupAnnouncements()
	with LOCK:
		_recover()
		state = _state()
		for role, item in state["roles"].items():
			if role == "bootlogo" and not os.path.isfile(TARGETS[role]):
				continue
			data = _checked(_read(_path(os.path.join("alese", item["sha256"] + ".mvi"))), item)
			_mpeg2(data, item["resolution"])
			target = _target(role)
			try:
				current = _read(target)
			except FileNotFoundError:
				current = None
			if current != data:
				_transaction(role, data, state)
		_cleanup(state)
	return True
