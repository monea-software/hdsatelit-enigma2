# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Explorator privilegiat. Fara acces prin token, aplicatii sau asistenta.

Toate operatiile de disc si verificarea parolei ruleaza in fire limitate.
eTimer livreaza raspunsurile in bucla Enigma2; nu depindem de callFromThread.
Nici parolele, nici continutul, nici exceptiile brute nu sunt jurnalizate.
"""
import hashlib
import hmac
import json
import queue
import secrets
import threading
import time
from urllib.parse import quote, urlsplit

from .fisiere_core import FisiereCore, FisiereError

COOKIE = "hds_fisiere"
SESSION_SECONDS = 1800
CHUNK = 65536
MAX_SAVE_BODY = 6 * 1024 * 1024


def _(text):
    try:
        import builtins
        return builtins._(text)
    except (AttributeError, NameError):
        return text


def verify_password(password):
    """Verifica hash-ul root, niciodata parola pentru aplicatii sau exceptia LAN."""
    if not isinstance(password, str) or not password or len(password) > 256 or "\x00" in password:
        return False
    try:
        import crypt
        with open("/etc/shadow", "r", encoding="utf-8") as source:
            for line in source:
                fields = line.rstrip("\n").split(":")
                if fields[0] != "root":
                    continue
                saved = fields[1]
                if not saved or saved.startswith(("!", "*")):
                    return False
                actual = crypt.crypt(password, saved)
                return bool(actual) and hmac.compare_digest(actual, saved)
    except Exception:
        return False
    return False


class Sessions:
    def __init__(self, clock=time.monotonic, verifier=verify_password):
        self.clock, self.verifier = clock, verifier
        self.sessions, self.failures = {}, {}
        self.lock = threading.RLock()

    @staticmethod
    def key(secret):
        return hashlib.sha256(str(secret).encode("utf-8")).hexdigest()

    def login(self, address, password):
        with self.lock:
            now = self.clock()
            self.sessions = {k: v for k, v in self.sessions.items() if v["expires"] > now}
            self.failures = {k: v for k, v in self.failures.items() if now - v[1] < 300}
            count, since = self.failures.get(address, (0, now))
            if count >= 5:
                raise FisiereError("rate", _("Prea multe parole greșite. Încearcă peste cinci minute."), 429)
            # Rezervam incercarea inaintea crypt: doua fire nu ocolesc limita.
            self.failures[address] = (count + 1, since)
        if not self.verifier(password):
            raise FisiereError("password", _("Parola receptorului nu este corectă sau nu poate fi verificată."), 401)
        with self.lock:
            self.failures.pop(address, None)
            if len(self.sessions) >= 32:
                raise FisiereError("busy", _("Sunt prea multe sesiuni de fișiere deschise."), 503)
            secret = secrets.token_urlsafe(32)
            expires = self.clock() + SESSION_SECONDS
            self.sessions[self.key(secret)] = {"id": self.key(secret), "address": address, "expires": expires}
            return secret, expires

    def get(self, secret, address):
        if not secret or len(str(secret)) > 128:
            return None
        with self.lock:
            value = self.sessions.get(self.key(secret))
            if value and value["expires"] > self.clock() and value["address"] == address:
                return dict(value)
            return None

    def logout(self, secret):
        with self.lock:
            self.sessions.pop(self.key(secret), None)


SESSIONS = Sessions()


def _cookie(request):
    value = request.getCookie(COOKIE.encode("ascii"))
    return value.decode("ascii", "ignore") if isinstance(value, bytes) else value


def _same_origin(request, P):
    origin = P._antet(request, b"origin")
    referer = P._antet(request, b"referer")
    candidate = origin or referer
    if not candidate or candidate == "null":
        return False
    try:
        uri = urlsplit(candidate)
        scheme = "https" if request.isSecure() else "http"
        host = P._antet(request, b"host")
        expected = urlsplit(scheme + "://" + host)
        return (uri.scheme == scheme and uri.hostname == expected.hostname
                and (uri.port or (443 if scheme == "https" else 80)) == (expected.port or (443 if scheme == "https" else 80))
                and uri.username is None and uri.password is None)
    except (ValueError, TypeError, AttributeError):
        return False


def gate(request, P, sessions=SESSIONS, require_login=True, download=False):
    address = P._adresaClient(request)
    # Accesul extern al aplicatiilor nu autorizeaza implicit exploratorul.
    if not P._esteAdresaLocala(address) and not getattr(P, "fisiereAfara", lambda: False)():
        raise FisiereError("network", _("Accesul la fișiere din afara casei este oprit."), 403)
    if P.PARAM_JETON in request.args or P._antet(request, b"authorization"):
        raise FisiereError("browser", _("Fișierele se deschid numai din browser, cu parola receptorului."), 403)
    if request.method not in (b"GET", b"POST"):
        raise FisiereError("method", _("Metoda cererii nu este permisă."), 405)
    if request.method == b"POST" and not P._antet(request, b"origin"):
        raise FisiereError("origin", _("Lipsește originea cererii."), 403)
    if not _same_origin(request, P):
        raise FisiereError("origin", _("Cererea nu vine din pagina receptorului."), 403)
    secret, browser = P._sesiuneDinCerere(request)
    if browser is None:
        raise FisiereError("panel", _("Conectează browserul la panoul receptorului."), 401)
    if not download and not P.obtineAsociere().csrfValid(secret, P._antet(request, b"x-hds-csrf")):
        raise FisiereError("csrf", _("Cererea nu are codul de protecție al panoului."), 403)
    session = sessions.get(_cookie(request), address)
    if require_login and session is None:
        raise FisiereError("login", _("Introdu parola receptorului. Sesiunea de fișiere durează 30 de minute."), 401)
    return session


def _result_error(error):
    if isinstance(error, FisiereError):
        return {"result": False, "message": str(error), "code": error.code}, error.status
    # O exceptie de codec poate contine chiar textul fisierului. Nu o expunem.
    return {"result": False, "message": _("Operația nu a reușit. Verifică fișierul, spațiul și drepturile.")}, 400


class Workers:
    """Nicio coada nelimitata de lucrari, nici cate un fir pentru fiecare cerere."""
    def __init__(self, limit=3):
        self.slots = threading.BoundedSemaphore(limit)

    def start(self, work):
        if not self.slots.acquire(False):
            raise FisiereError("busy", _("Receptorul lucrează deja cu fișiere. Încearcă din nou."), 503)
        def run():
            try:
                work()
            finally:
                self.slots.release()
        thread = threading.Thread(target=run, daemon=True)
        try:
            thread.start()
        except Exception:
            self.slots.release()
            raise


class Service:
    def __init__(self, core=None, sessions=SESSIONS):
        self.core = core or FisiereCore()
        self.sessions = sessions
        self.workers = Workers()
        self.jobs, self.uploads, self.confirmations = {}, {}, {}
        self.lock = threading.RLock()

    def job(self, owner, work):
        with self.lock:
            now = time.monotonic()
            self.jobs = {k: v for k, v in self.jobs.items() if v["state"] == "running" or now - v["created"] < 1800}
            if len(self.jobs) >= 32:
                raise FisiereError("busy", _("Sunt prea multe lucrări în listă. Încearcă mai târziu."), 503)
            ident = secrets.token_urlsafe(18)
            event = threading.Event()
            job = {"id": ident, "owner": owner, "created": now, "state": "running", "bytes": 0, "total": 0, "cancel": event}
            self.jobs[ident] = job
        def progress(*args, **kwargs):
            with self.lock:
                if args and isinstance(args[0], dict):
                    job.update({k: v for k, v in args[0].items() if k in ("bytes", "total", "path", "files")})
                elif args:
                    job["bytes"] = args[0]
                    if len(args) > 1:
                        job["total"] = args[1]
                job.update({k: v for k, v in kwargs.items() if k in ("bytes", "total")})
        def cancelled():
            with self.sessions.lock:
                session = self.sessions.sessions.get(owner)
                expired = not session or session["expires"] <= self.sessions.clock()
            if expired:
                event.set()
            return event.is_set()
        def execute():
            try:
                output = work(progress, cancelled)
                with self.lock:
                    job.update(state="cancelled" if event.is_set() else "done", output=output)
            except Exception as error:
                with self.lock:
                    job.update(state="cancelled" if event.is_set() else "error", error=_result_error(error)[0]["message"])
        try:
            self.workers.start(execute)
        except Exception:
            self.jobs.pop(ident, None)
            raise
        return {"result": True, "job": ident}

    def owned_job(self, owner, ident):
        job = self.jobs.get(ident)
        if not job or job["owner"] != owner:
            raise FisiereError("job", _("Lucrarea nu există în această sesiune."), 404)
        return job


_SERVICE = None


def _service():
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = Service()
    return _SERVICE


def rute(resource, P, service=None, timer_factory=None):
    """Resurse proprii: nu mostenesc poarta care accepta cheia pentru scripturi."""
    from twisted.web.server import NOT_DONE_YET
    S = service or _service()
    def recordings_path():
        try:
            from Components.UsageConfig import defaultMoviePath
            return defaultMoviePath()
        except (ImportError, AttributeError, KeyError):
            return None
    # Citim numai valoarea config pe firul principal; rezolvarea caii e in nucleu.
    S.core.recordings_path = recordings_path()
    timers = set()

    def new_clock():
        # eTimer se ia la prima folosire, nu la construirea panoului: panoul se construieste si fara pagina fisierelor deschisa.
        if timer_factory is not None:
            return timer_factory()
        from enigma import eTimer
        return eTimer()

    def respond(request, body, status=200):
        request.setResponseCode(status)
        request.setHeader(b"content-type", b"application/json; charset=utf-8")
        request.setHeader(b"cache-control", b"no-store")
        request.setHeader(b"x-content-type-options", b"nosniff")
        return json.dumps(body, ensure_ascii=False).encode("utf-8", "replace")

    def timer(callback, delay=40):
        clock = new_clock()
        timers.add(clock)
        def stop():
            clock.stop()
            timers.discard(clock)
        try:
            clock.callback.append(callback)
        except AttributeError:
            clock._hds_connection = clock.timeout.connect(callback)
        clock.start(delay, False)
        return stop

    def maintenance():
        def clean():
            try:
                active = set(S.core.maintenance()["uploads"])
                with S.lock:
                    S.uploads = {k: v for k, v in S.uploads.items() if k in active}
                    now = time.monotonic()
                    S.confirmations = {k: v for k, v in S.confirmations.items() if v["expires"] > now}
            except Exception:
                pass  # nicio exceptie bruta cu date de fisiere in jurnalul general
        try:
            S.workers.start(clean)
        except FisiereError:
            pass  # ocupat; reincearca la urmatorul tic, fara a bloca interfata
    maintenance_started = []

    def start_maintenance():
        # Curatenia de la un minut porneste la prima cerere a paginii, nu la pornirea panoului:
        # pana atunci nu exista incarcari sau confirmari de curatat, iar enigma2 nu are un ceas in plus.
        if not maintenance_started:
            maintenance_started.append(timer(maintenance, 60000))

    def async_response(request, work, after=None):
        box, disconnected = {}, threading.Event()
        def run():
            try:
                box["value"] = work()
            except Exception as error:
                box["error"] = _result_error(error)
        def tick():
            if disconnected.is_set():
                stop()
            elif box:
                stop()
                try:
                    if "error" in box:
                        body, status = box["error"]
                    else:
                        body, status = box["value"], 200
                        if after:
                            body = after(body)
                    request.write(respond(request, body, status))
                    request.finish()
                except Exception:
                    pass
        S.workers.start(run)
        stop = timer(tick)
        request.notifyFinish().addErrback(lambda failure: disconnected.set())
        return NOT_DONE_YET

    def arg(request, name, default=""):
        values = request.args.get(name.encode("ascii"), [default.encode("utf-8")])
        if len(values) != 1:
            raise FisiereError("argument", _("Argument repetat în cerere."))
        return values[0].decode("utf-8", "strict")

    def body(request):
        content_type = (P._antet(request, b"content-type") or "").split(";", 1)[0]
        if content_type != "application/json":
            raise FisiereError("body", _("Se așteaptă date în format JSON."))
        raw = request.content.read(MAX_SAVE_BODY + 1)
        if len(raw) > MAX_SAVE_BODY:
            raise FisiereError("size", _("Corpul cererii este prea mare."), 413)
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise FisiereError("body", _("Datele cererii nu sunt valide."))
        return data

    def set_cookie(request, secret):
        request.addCookie(COOKIE.encode("ascii"), secret.encode("ascii"), path=b"/", httpOnly=True,
                          sameSite="strict", secure=bool(request.isSecure()))

    def download(request, path, session):
        chunks, cancelled = queue.Queue(2), threading.Event()
        metadata = {}
        class Producer:
            paused = False
            def pauseProducing(self):
                self.paused = True
            def resumeProducing(self):
                self.paused = False
            def stopProducing(self):
                cancelled.set()
        producer = Producer()
        def put(item):
            while not cancelled.is_set():
                try:
                    chunks.put(item, timeout=.2)
                    return
                except queue.Full:
                    pass
        def run():
            try:
                stream, size, name = S.core.open_download(path)
                with stream:
                    metadata.update(size=size, name=name)
                    remaining = size
                    while not cancelled.is_set():
                        if remaining == 0:
                            break
                        block = stream.read(CHUNK if remaining is None else min(CHUNK, remaining))
                        if not block:
                            break
                        if remaining is not None:
                            remaining -= len(block)
                        put(block)
                put(None)
            except Exception as error:
                metadata["error"] = _result_error(error)
                put(None)
        started = [False]
        def finish():
            stop()
            cancelled.set()
            try:
                request.unregisterProducer()
                request.finish()
            except Exception:
                pass
        def tick():
            if cancelled.is_set():
                finish()
                return
            try:
                gate(request, P, S.sessions, download=True)
            except FisiereError:
                cancelled.set()
                finish()
                return
            if "error" in metadata:
                if not started[0]:
                    data, code = metadata["error"]
                    request.write(respond(request, data, code))
                finish()
                return
            if "name" not in metadata or producer.paused:
                return
            try:
                if not started[0]:
                    request.setHeader(b"content-type", b"application/octet-stream")
                    if metadata["size"] is not None:
                        request.setHeader(b"content-length", str(metadata["size"]).encode("ascii"))
                    request.setHeader(b"content-disposition", ("attachment; filename*=UTF-8''" + quote(metadata["name"], safe="")).encode("ascii"))
                    request.setHeader(b"cache-control", b"no-store")
                    request.setHeader(b"x-content-type-options", b"nosniff")
                    started[0] = True
                for unused in range(2):
                    try:
                        block = chunks.get_nowait()
                    except queue.Empty:
                        break
                    if block is None:
                        finish()
                        return
                    request.write(block)
            except Exception:
                cancelled.set()
                finish()
        S.workers.start(run)
        request.registerProducer(producer, True)
        stop = timer(tick)
        request.notifyFinish().addErrback(lambda failure: cancelled.set())
        return NOT_DONE_YET

    class Endpoint(resource.Resource):
        isLeaf = True
        def __init__(self, action):
            resource.Resource.__init__(self)
            self.action = action

        def render(self, request):
            try:
                start_maintenance()
                action = self.action
                readonly = action in ("status", "list", "editor", "shortcuts", "job", "download")
                if request.method != (b"GET" if readonly and not (action == "shortcuts" and request.method == b"POST") else b"POST"):
                    raise FisiereError("method", _("Metoda cererii nu este permisă."), 405)
                session = gate(request, P, S.sessions, require_login=action not in ("status", "login"), download=action == "download")
                if action == "status":
                    return respond(request, {"result": True, "autentificat": bool(session), "expira": max(0, int(session["expires"] - S.sessions.clock())) if session else 0,
                                             "local": P._esteAdresaLocala(P._adresaClient(request)), "extern_permis": P.fisiereAfara()})
                if action == "login":
                    data, address = body(request), P._adresaClient(request)
                    old = _cookie(request)
                    def logged(value):
                        secret, expires = value
                        S.sessions.logout(old)
                        set_cookie(request, secret)
                        return {"result": True, "autentificat": True, "expira": SESSION_SECONDS}
                    return async_response(request, lambda: S.sessions.login(address, data.get("parola")), logged)
                owner = session["id"]
                if action == "download":
                    return download(request, arg(request, "cale"), session)
                if action == "list":
                    path, offset = arg(request, "cale", "/"), int(arg(request, "offset", "0"))
                    return async_response(request, lambda: dict(result=True, **S.core.list_directory(path, offset)))
                if action == "editor":
                    path = arg(request, "cale")
                    return async_response(request, lambda: dict(result=True, **S.core.editor_read(path)))
                if action == "job":
                    with S.lock:
                        job = S.owned_job(owner, arg(request, "id"))
                        data = {k: v for k, v in job.items() if k not in ("owner", "cancel", "created")}
                    return respond(request, {"result": True, "job": data})
                if action == "shortcuts" and request.method == b"GET":
                    S.core.recordings_path = recordings_path()
                    return async_response(request, lambda: {"result": True, "items": S.core.shortcuts_list()})
                data = body(request) if action != "upload-chunk" else None
                if action == "access":
                    if not P._esteAdresaLocala(P._adresaClient(request)) or not isinstance(data.get("permis"), bool):
                        raise FisiereError("local", _("Accesul extern se schimbă numai din casă, după introducerea parolei receptorului."), 403)
                    setting = P.config.plugins.hdswebcontrol.fisiere_afara
                    setting.value = data["permis"]
                    setting.save()
                    def save_access():
                        P.configfile.save()
                        return {"result": True, "extern_permis": data["permis"]}
                    return async_response(request, save_access)
                if action == "logout":
                    S.sessions.logout(_cookie(request))
                    for job in list(S.jobs.values()):
                        if job["owner"] == owner:
                            job["cancel"].set()
                    ids = [k for k, v in S.uploads.items() if v["owner"] == owner]
                    def clear():
                        for ident in ids:
                            S.core.abort_upload(ident)
                            S.uploads.pop(ident, None)
                        return {"result": True}
                    set_cookie(request, "")
                    return async_response(request, clear)
                if action == "cancel":
                    S.owned_job(owner, data.get("id"))["cancel"].set()
                    return respond(request, {"result": True})
                if action == "save":
                    return async_response(request, lambda: dict(result=True, **S.core.editor_save(data.get("cale"), data.get("text"), data.get("version"), data.get("format"))))
                if action == "shortcuts":
                    return async_response(request, lambda: {"result": True, "items": S.core.shortcuts_update(**data)})
                if action == "operate":
                    op, items = data.get("action"), data.get("items")
                    if op == "touch":
                        op = "newfile"
                    if op == "delete":
                        if not data.get("cod"):
                            def plan():
                                value = S.core.plan_delete(items)
                                code = secrets.token_urlsafe(24)
                                with S.lock:
                                    now = time.monotonic()
                                    S.confirmations = {k: v for k, v in S.confirmations.items() if v["expires"] > now}
                                    if len(S.confirmations) >= 32:
                                        raise FisiereError("busy", _("Sunt prea multe confirmări în așteptare."), 503)
                                    S.confirmations[code] = {"owner": owner, "items": items, "plan": value, "expires": now + 60}
                                return {"result": True, "confirmare": {"cod": code, "intrebare": _("Ștergi definitiv fișierele alese?"), "detalii": [value.get("warning", "")] + value["paths"]}}
                            return async_response(request, plan)
                        with S.lock:
                            value = S.confirmations.pop(data["cod"], None)
                        if not value or value["owner"] != owner or value["items"] != items or value["expires"] < time.monotonic():
                            raise FisiereError("confirmation", _("Confirmarea a expirat. Cere din nou ștergerea."), 409)
                        return respond(request, S.job(owner, lambda progress, cancelled: S.core.execute_delete(value["plan"]["token"], progress=progress, cancelled=cancelled)))
                    return respond(request, S.job(owner, lambda progress, cancelled: S.core.operate(op, items, destination=data.get("destination"), name=data.get("name"), mode=data.get("mode"), progress=progress, cancelled=cancelled)))
                if action == "upload-start":
                    def start_upload():
                        value = S.core.begin_upload(data.get("cale"), data.get("size"))
                        with S.lock:
                            now = time.monotonic()
                            S.uploads = {k: v for k, v in S.uploads.items() if v["expires"] > now}
                            S.uploads[value["id"]] = {"owner": owner, "expires": now + SESSION_SECONDS}
                        return dict(result=True, **value)
                    return async_response(request, start_upload)
                if action in ("upload-chunk", "upload-commit", "upload-abort"):
                    ident = arg(request, "id") if action == "upload-chunk" else data.get("id")
                    upload = S.uploads.get(ident)
                    if not upload or upload["owner"] != owner or upload["expires"] <= time.monotonic():
                        raise FisiereError("upload", _("Încărcarea nu există în această sesiune."), 404)
                    if action == "upload-chunk":
                        offset = int(arg(request, "offset"))
                        block = request.content.read(CHUNK + 1)
                        if len(block) > CHUNK:
                            raise FisiereError("size", _("Bucata încărcată este prea mare."), 413)
                        def write_upload():
                            value = S.core.write_upload(ident, offset, block)
                            with S.lock:
                                if ident in S.uploads:
                                    S.uploads[ident]["expires"] = time.monotonic() + SESSION_SECONDS
                            return dict(result=True, **value)
                        return async_response(request, write_upload)
                    def finish_upload():
                        try:
                            value = S.core.finish_upload(ident) if action == "upload-commit" else S.core.abort_upload(ident)
                            return dict(result=True, **value)
                        except Exception:
                            S.core.abort_upload(ident)
                            raise
                        finally:
                            S.uploads.pop(ident, None)
                    return async_response(request, finish_upload)
                raise FisiereError("route", _("Operația cerută nu există."), 404)
            except Exception as error:
                data, status = _result_error(error)
                return respond(request, data, status)

    class Page(resource.Resource):
        isLeaf = True
        def render_GET(self, request):
            if (not P._esteAdresaLocala(P._adresaClient(request)) and not P.fisiereAfara()) or P.PARAM_JETON in request.args:
                return respond(request, {"result": False, "message": _("Accesul la fișiere din afara casei este oprit sau cererea nu vine din browser.")}, 403)
            P._anteteHtml(request)
            secret, browser = P._sesiuneDinCerere(request)
            if browser is None:
                return P._PAGINA_ASOCIERE.encode("utf-8")
            from .fisiere_pagina import pagina_text
            return pagina_text(P._STIL_COMUN, P._configPanou(P.csrfPentru(secret), "", browser.get("nume", ""))).encode("utf-8")

    actions = ("status", "login", "logout", "access", "list", "editor", "save", "shortcuts", "operate", "job", "cancel", "upload-start", "upload-chunk", "upload-commit", "upload-abort", "download")
    return {("fisiere-" + action).encode("ascii"): Endpoint(action) for action in actions}, Page()
