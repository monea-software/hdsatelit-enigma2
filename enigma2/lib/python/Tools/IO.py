# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# Pluginul salveaza certificatul si cheia ca octeti; inlocuirea fisierului se face dupa scrierea intreaga.
import os
import tempfile


def saveFile(filename, data):
	"""Scrie octeti sau text UTF-8, cu drepturi 0600. Intoarce None; erorile OSError ajung la apelant."""
	filename = os.path.abspath(os.fspath(filename))
	if isinstance(data, str):
		data = data.encode("utf-8")
	fd, temporary = tempfile.mkstemp(prefix=".hds-", dir=os.path.dirname(filename))
	try:
		with os.fdopen(fd, "wb") as stream:
			fd = None
			stream.write(data)
			stream.flush()
			os.fsync(stream.fileno())
		os.replace(temporary, filename)
	finally:
		if fd is not None:
			os.close(fd)
		try:
			os.unlink(temporary)
		except OSError:
			pass


__all__ = ["saveFile"]
