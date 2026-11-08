# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# Pluginurile trimit perechi sursa-destinatie; lucrarile ruleaza prin Task, fara copiere pe firul interfetei.

__all__ = ("copyFiles", "moveFiles")


def _transfer(files, name, move):
	from os import fspath
	from Components.Task import Job, Task, ReturncodePostcondition, job_manager

	# Pastram perechile chiar daca apelantul isi schimba lista dupa intoarcere.
	pairs = tuple((fspath(source), fspath(destination)) for source, destination in files)
	job = Job(name)
	command = "/bin/mv" if move else "/bin/cp"
	for source, destination in pairs:
		task = Task(job, name)
		args = [command]
		if not move:
			args.append("-p")
		args.extend(("--", source, destination))
		task.setCommandline(command, args)
		task.postconditions.append(ReturncodePostcondition())
	job_manager.AddJob(job)
	return job


def copyFiles(files, name):
	"""Programeaza copierea perechilor (sursa, destinatie); intoarce lucrarea Task."""
	return _transfer(files, name, False)


def moveFiles(files, name):
	"""Programeaza mutarea perechilor (sursa, destinatie); intoarce lucrarea Task."""
	return _transfer(files, name, True)
