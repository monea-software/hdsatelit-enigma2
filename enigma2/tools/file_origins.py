#!/usr/bin/env python3
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""file_origins.py: writes FILES.md, the list of the files of this tree sorted by origin.

Every file of a commit (HEAD by default) is put in one of four groups, compared with the enigma2 base
(Dream Multimedia, commit 75d5fba59 of 14 September 2011):
  1. unchanged from the base;
  2. modified from the base (renames included, git diff -M);
  3. added from other sources, with the origin stated in the file header or in the table below,
     or "origin not recorded";
  4. added by HD Satelit / Monea Software: text files whose header carries our copyright line,
     and the pictures, fonts, data and build files of the folders listed as ours in the table below.
The files removed from the base are listed too.

Everything is read from git (ls-tree, diff -M, cat-file) for the given commit, never from the files
on disk, so the list describes exactly what is committed. FILES.md is always listed (as generated), even
before it is committed, so generating it on HEAD and committing it gives a FILES.md that is up to date.

Run it at the root of the repository (Python 3, no other dependency):
  python3 tools/file_origins.py              writes FILES.md for HEAD
  python3 tools/file_origins.py --check      exits with code 1 when the committed FILES.md is not up to date
                                             (--verifica is the same option)
  options: --repo DIR, --rev COMMIT, --base COMMIT, --output FILE
On Windows use "py -3" instead of "python3". It is run, and FILES.md committed, before every version tag.
"""

import argparse
import fnmatch
import os
import posixpath
import re
import subprocess
import sys

BASE = "75d5fba59"
OUTPUT = "FILES.md"
HEADER_LINES = 40
HASH_LEN = 9

OURS = "ours"
OTHER = "other"

# Code files: a header is expected; they go to group 4 only with our copyright line.
CODE_EXT = {
	".py", ".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".js", ".mjs", ".cjs", ".css", ".html", ".htm",
	".sh", ".php", ".pl", ".m4", ".i",
}

# Our copyright line, in the first HEADER_LINES lines of a text file.
OUR_COPYRIGHT = re.compile(r"copyright\b.*\b(moneasoftware\.com|monea software|monea eduard)", re.I)
OUR_NOTICE = re.compile(r"^\W*HD Satelit \([^)]*moneasoftware\.com[^)]*\)", re.I)
YEAR = re.compile(r"\b20\d\d\b")
MODIFIED_BY_US = re.compile(r"modificat\b.*moneasoftware\.com", re.I)
NAMES_US = re.compile(r"moneasoftware|monea software|monea eduard|hdsatelit|hd satelit", re.I)

# Origins written in the headers (the headers of this tree are in Romanian).
AUTO_ORIGINS = [
	(re.compile(r"din sursele GPL[\w.-]* enigma2 \(OE-Alliance\),? commitul ([0-9a-f]{7,40})", re.I),
		"enigma2 (OE-Alliance), commit {0}"),
	(re.compile(r"din sursele GPL[\w.-]* ale unui enigma2 public \(commitul ([0-9a-f]{7,40})", re.I),
		"a public enigma2 tree, commit {0}"),
	(re.compile(r"dupa enigma2 OE-Alliance, ([\w./-]+)", re.I),
		"based on enigma2 (OE-Alliance), {0}"),
]
CREDIT = re.compile(
	r"\bcopyright\b|\(c\)\s*\d|\(c\)\s+[A-Z]|©|coded by|\bauthors?\s*:|written by|based on|taken from|copied from|"
	r"\bluat din\b|\bpreluat din\b|\bdin sursele\b", re.I)
LICENSES = [
	(re.compile(r"GPL-2\.0-only", re.I), "GPL-2.0-only"),
	(re.compile(r"GPL-2\.0-or-later|either version 2 of the License, or|any later version", re.I), "GPL-2.0-or-later"),
	(re.compile(r"\bLGPL|Lesser General Public", re.I), "LGPL"),
	(re.compile(r"\bGPL\b|GPLv2|GPL-2\.0|General Public License", re.I), "GPL-2.0"),
	(re.compile(r"\bMIT License\b|\bLicenta: MIT\b", re.I), "MIT"),
	(re.compile(r"Apache License|Apache-2\.0|Apache 2\.0", re.I), "Apache-2.0"),
	(re.compile(r"NonCommercial-ShareAlike|BY-NC-SA", re.I), "CC BY-NC-SA 3.0"),
	(re.compile(r"Creative Commons Attribution 4\.0|CC BY 4\.0", re.I), "CC BY 4.0"),
	(re.compile(r"Open Font License", re.I), "OFL-1.1"),
]

OFL_HDS = ("Open Sans; Noto Sans Arabic, Hebrew and Thai (static instances, subsets); SIL Open Font License 1.1"
	" (OFL.txt in the same folder)")

# First match wins. Rules marked OURS never apply to code files (they need our copyright line).
RULES = [
	# This list and the documentation of the tree.
	("FILES.md", OURS, "this list, written by tools/file_origins.py"),
	("README.md", OURS, "documentation of this tree"),
	("*/README.md", OURS, "documentation of this tree"),
	("doc/modules/*", OURS, "documentation of this tree"),
	("CREDITS", OURS, "documentation of this tree"),
	("doc/REMOVED-FILES", OURS, "documentation of this tree"),
	(".gitattributes", OURS, "repository settings"),
	("*/LICENSE", OTHER, "text of the GNU General Public License, version 2 (Free Software Foundation)"),
	("LICENSE.original-2011", OTHER, "the license of the 2011 enigma2 source (Dream Multimedia), kept unchanged"),
	# Fonts.
	("data/fonts/Hds*.ttf", OTHER, OFL_HDS),
	("HDSatelit/fonts/Hds*.ttf", OTHER, OFL_HDS),
	("*/OFL.txt", OTHER, "text of the SIL Open Font License 1.1, with the copyright lines of the fonts next to it"),
	("data/fonts/AtkinsonHyperlegible*", OTHER, "Atkinson Hyperlegible, Braille Institute of America; SIL Open Font License 1.1"),
	("data/fonts/Barlow*", OTHER, "Barlow, The Barlow Project Authors; SIL Open Font License 1.1"),
	("data/fonts/PT_Sans*", OTHER, "PT Sans, ParaType Ltd.; SIL Open Font License 1.1"),
	("data/fonts/DejaVuSansMono-Bold.*", OTHER, "DejaVu Sans Mono Bold 2.35, only the line gap changed;"
		" Bitstream Vera and Arev licenses (DejaVuSansMono-Bold.license)"),
	("data/fonts/tuxtxt.license", OTHER, "license of tuxtxt.ttf (Bitstream Vera Sans Mono Bold 1.10)"),
	("data/fonts/enigma2icons.*", OTHER, "icon font built by HD Satelit from Google Material Symbols;"
		" Apache License 2.0 (enigma2icons.license)"),
	("HDSatelit/afisaj-color/fonturi/Noto*.ttf", OTHER, "Noto Sans, The Noto Project Authors; SIL Open Font License 1.1"),
	# Icons.
	("HDSatelit/meniu/alb/*", OTHER, "menu icons made from Google Material Symbols (Apache License 2.0),"
		" in the colors of the HDSatelit theme"),
	("HDSatelit/meniu/deschis/*", OTHER, "menu icons made from Google Material Symbols (Apache License 2.0),"
		" in the colors of the HDSatelit theme"),
	("HDSatelit/meniu/inchis/*", OTHER, "menu icons made from Google Material Symbols (Apache License 2.0),"
		" in the colors of the HDSatelit theme"),
	# Web interface: players and decoders.
	("lib/python/Plugins/Extensions/HdsWebControl/mpegts.js", OTHER, "mpegts.js 1.8.0 (github.com/xqq/mpegts.js),"
		" Apache License 2.0; changed by HD Satelit (header and mpegts-licenta.txt)"),
	("lib/python/Plugins/Extensions/HdsWebControl/mpegts-licenta.txt", OTHER, "license and list of changes of mpegts.js"),
	("lib/python/Plugins/Extensions/HdsWebControl/tv-wasm/hdsdec.*", OTHER, "decoder built by HD Satelit from"
		" FFmpeg 8.1.3 (LGPL-2.1-or-later) with Emscripten; licenses in tv-wasm/*-licenta.txt"),
	("lib/python/Plugins/Extensions/HdsWebControl/tv-wasm/*-licenta.txt", OTHER, "license text of the component"
		" named in the file name, built into hdsdec.wasm"),
	# SoftCSA (descrambling in software).
	("lib/dvb/cahandler.*", OTHER, "SoftCSA code by WXbet and Betacentauri (authors named in the header),"
		" GPL-2.0-only; changed by HD Satelit"),
	("lib/dvb/csa*", OTHER, "SoftCSA code by WXbet and Betacentauri (authors named in the header),"
		" GPL-2.0-only; changed by HD Satelit"),
	("lib/dvb/cwhandler.*", OTHER, "SoftCSA code by WXbet and Betacentauri (authors named in the header),"
		" GPL-2.0-only; changed by HD Satelit"),
	("lib/service/iservicescrambled.h", OTHER, "SoftCSA code by WXbet and Betacentauri (authors named in the header),"
		" GPL-2.0-only; changed by HD Satelit"),
	("lib/service/servicedvbsoftdecoder.*", OTHER, "SoftCSA code by WXbet and Betacentauri (authors named in the header),"
		" GPL-2.0-only; changed by HD Satelit"),
	# Single files.
	("lib/python/Components/HdsChromeOS.py", OTHER, "taken from inputstreamhelper (script.module.inputstreamhelper,"
		" lib/inputstreamhelper/widevine/arm_chromeos.py), MIT License (header)"),
	("lib/python/Components/HdsLocuriDate.py", OTHER, "generated by HD Satelit; city data from GeoNames (geonames.org),"
		" CC BY 4.0 (header)"),
	("lib/python/Components/Renderer/BoxLogo.py", OTHER, "e2-boxlogos (github.com/DimitarCC/e2-boxlogos) by DimitarCC,"
		" commit 45a845077cfb, GPL-2.0; changed by HD Satelit (header)"),
	("m4/mm-ax_cxx_compile_stdcxx.m4", OTHER, "GNU Autoconf Archive, ax_cxx_compile_stdcxx (license in the header)"),
	("data/hds-locuri.tsv.gz", OTHER, "generated by HD Satelit; city data from GeoNames (geonames.org), CC BY 4.0"
		" (source in the first lines of the file)"),
	("data/hds-producatori-mac.txt.gz", OTHER, "Wireshark manuf list, made from the public IEEE registries;"
		" GPL-2.0-or-later (source in the first lines of the file)"),
	("data/countries/uz.png", OTHER, "flag of Uzbekistan drawn by HD Satelit; the shine taken from data/countries/ua.png"
		" of the enigma2 base (Dream Multimedia)"),
	("data/countries/al.png", OTHER, "flag of Albania drawn by HD Satelit; the shine taken from data/countries/ua.png"
		" of the enigma2 base (Dream Multimedia)"),
	("data/countries/bg.png", OTHER, "flag of Bulgaria drawn by HD Satelit; the shine taken from data/countries/ru.png"
		" of the enigma2 base (Dream Multimedia)"),
	("data/skin_default/buttons/vkey_icon.png", OTHER, "copy of data/skin_default/vkey_icon.png of the enigma2 base"
		" (Dream Multimedia), unchanged"),
	("data/skin_default/icons/expandable.png", OURS, "icon drawn by HD Satelit"),
	("data/skin_default/icons/expanded.png", OURS, "icon drawn by HD Satelit"),
	("data/skin_default/icons/timer_rec.png", OURS, "icon drawn by HD Satelit"),
	("data/skin_default/icons/timer_zap.png", OURS, "icon drawn by HD Satelit"),
	# Folders of ours: pictures, fonts, data and build files (not code).
	("HDSatelit/*", OURS, "HDSatelit theme"),
	("pluginuri-feed/*", OURS, "plugins of the HD Satelit feed"),
	("lib/python/Hds/*", OURS, "HD Satelit modules"),
	("lib/python/Plugins/Extensions/Hds*", OURS, "HD Satelit plugins"),
	("lib/python/Plugins/SystemPlugins/Hds*", OURS, "HD Satelit plugins"),
	("*Makefile.am", OURS, "build file of this tree"),
	("data/hds*", OURS, "data of the image"),
	("data/*.json", OURS, "data of the image"),
	("data/asistenta/*", OURS, "data of the image"),
	("data/vremea/*", OURS, "data of the image"),
	("data/sigle-pornire/*", OURS, "data of the image"),
	("data/skin_default/spinner/*", OURS, "data of the image"),
	("data/skin_default/hds_rc*", OURS, "data of the image"),
	("data/skin_default/picon_lista_*", OURS, "data of the image"),
	("data/telecomanda-viper.*", OURS, "data of the image"),
	("data/black.mvi", OURS, "data of the image"),
	("data/softcsa", OURS, "data of the image"),
]

NOT_RECORDED = "origin not recorded"


def git(repo, *args):
	cmd = ["git", "-C", repo, "-c", "core.quotepath=off"] + list(args)
	return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout


def ls_tree(repo, rev):
	"""path -> (type, sha) for every file of rev."""
	files = {}
	for rec in git(repo, "ls-tree", "-r", "-z", "--full-tree", rev).split(b"\0"):
		if not rec:
			continue
		meta, path = rec.split(b"\t", 1)
		_mode, kind, sha = meta.decode().split()
		files[path.decode("utf-8", "surrogateescape")] = (kind, sha)
	return files


def diff_base(repo, base, rev):
	"""(added, modified {new: old or None}, removed) between base and rev, with renames."""
	out = git(repo, "diff", "-M", "-l0", "--no-ext-diff", "--no-textconv", "--name-status", "-z", base, rev)
	tok = [t.decode("utf-8", "surrogateescape") for t in out.split(b"\0")]
	added, removed, modified = set(), set(), {}
	i = 0
	while i < len(tok) - 1:
		status = tok[i]
		if not status:
			i += 1
			continue
		if status[0] in "RC":
			old, new = tok[i + 1], tok[i + 2]
			i += 3
			if status[0] == "R":
				modified[new] = old
			else:
				added.add(new)
			continue
		path = tok[i + 1]
		i += 2
		if status[0] == "A":
			added.add(path)
		elif status[0] == "D":
			removed.add(path)
		else:
			modified[path] = None
	return added, modified, removed


class Blobs(object):
	def __init__(self, repo):
		self.proc = subprocess.Popen(["git", "-C", repo, "cat-file", "--batch"], stdin=subprocess.PIPE,
			stdout=subprocess.PIPE)

	def read(self, sha):
		self.proc.stdin.write((sha + "\n").encode())
		self.proc.stdin.flush()
		head = self.proc.stdout.readline().split()
		size = int(head[2])
		data = self.proc.stdout.read(size)
		self.proc.stdout.read(1)
		return data

	def close(self):
		self.proc.stdin.close()
		self.proc.stdout.close()
		self.proc.wait()


def is_code(path, data):
	name = posixpath.basename(path)
	root, ext = posixpath.splitext(name)
	ext = ext.lower()
	if ext in CODE_EXT:
		return True
	if ext == ".in" and posixpath.splitext(root)[1].lower() in CODE_EXT:
		return True
	return ext == "" and data[:2] == b"#!"


def header_lines(data):
	if b"\0" in data[:8000]:
		return None
	return data.decode("utf-8", "replace").splitlines()[:HEADER_LINES]


def licenses_named(text):
	found = []
	for rx, name in LICENSES:
		if rx.search(text) and name not in found:
			found.append(name)
	if "GPL-2.0" in found and ("GPL-2.0-only" in found or "GPL-2.0-or-later" in found):
		found.remove("GPL-2.0")
	if "LGPL" in found and "GPL-2.0" in found:
		rest = re.sub(r"LGPL|Lesser General Public", "", text, flags=re.I)
		if not re.search(r"\bGPL\b|GPLv2|GPL-2\.0|General Public License", rest, re.I):
			found.remove("GPL-2.0")
	return found


def match_rule(path, code):
	for pattern, kind, note in RULES:
		if fnmatch.fnmatchcase(path, pattern):
			if kind == OURS and code:
				continue
			return kind, note
	return None


def classify_added(path, data):
	"""(group, note) for an added file: group is OURS or OTHER; note says why."""
	if path == OUTPUT:
		# FILES.md quotes the copyright line in its text: it is sorted by its name, never by its header.
		return OURS, "this list, written by tools/file_origins.py"
	code = is_code(path, data)
	lines = header_lines(data)
	if lines is not None:
		for line in lines:
			if OUR_COPYRIGHT.search(line) or (OUR_NOTICE.search(line) and YEAR.search(line)):
				return OURS, "copyright"
	rule = match_rule(path, code)
	if rule is not None:
		return rule
	if lines is None:
		return OTHER, NOT_RECORDED
	text = "\n".join(lines)
	modified = bool(MODIFIED_BY_US.search(text))
	notes = []
	for rx, fmt in AUTO_ORIGINS:
		m = rx.search(text)
		if m:
			value = m.group(1)
			if re.match(r"^[0-9a-f]{13,40}$", value):
				value = value[:12]
			notes.append(fmt.format(value))
			break
	if not notes:
		credits = [l for l in lines if CREDIT.search(l) and not NAMES_US.search(l)]
		if credits:
			notes.append("origin stated in the file header")
		elif modified:
			notes.append(NOT_RECORDED + " (the header says only that HD Satelit changed it)")
		else:
			notes.append(NOT_RECORDED)
	elif modified:
		notes.append("changed by HD Satelit")
	names = licenses_named(text)
	if names:
		notes.append("license named in the header: " + ", ".join(names))
	return OTHER, "; ".join(notes)


def folder(path):
	d = posixpath.dirname(path)
	return d + "/" if d else "./"


def by_folder(paths):
	groups = {}
	for p in sorted(paths):
		groups.setdefault(folder(p), []).append(posixpath.basename(p))
	return sorted(groups.items())


def names(files):
	return ", ".join("`%s`" % f for f in files)


def build(repo, rev, base):
	tree = ls_tree(repo, rev)
	added, modified, removed = diff_base(repo, base, rev)
	blobs = Blobs(repo)
	unchanged = sorted(p for p in tree if p not in added and p not in modified)
	ours_code, ours_res, other = [], [], []
	uncertain = 0
	for path in sorted(added):
		kind, sha = tree.get(path, ("blob", None))
		data = blobs.read(sha) if (kind == "blob" and sha) else b"\0"
		group, note = classify_added(path, data)
		if group == OURS and note == "copyright":
			ours_code.append(path)
		elif group == OURS:
			ours_res.append((path, note))
		else:
			other.append((path, note))
			if note.startswith(NOT_RECORDED):
				uncertain += 1
	blobs.close()
	if OUTPUT not in tree:
		# FILES.md is always listed, so that the committed list describes the commit that holds it.
		ours_res.append((OUTPUT, "this list, written by tools/file_origins.py"))
		ours_res.sort()
	total = len(unchanged) + len(modified) + len(other) + len(ours_code) + len(ours_res)

	out = []
	w = out.append
	w("# Files of the HD Satelit enigma2 tree, by origin")
	w("")
	w("This list puts every file of this source tree in one group, by where it comes from. The base is enigma2 as")
	w("published by Dream Multimedia: git commit 75d5fba59 of 14 September 2011 (\"Merge branch")
	w("'bug_747_cancel_waiting_tasks'\"). Every commit after it is by HD Satelit / Monea Software; the files they took")
	w("from other projects are in group 3, with their source. The list is generated from git only (git ls-tree,")
	w("git diff -M, the file headers as committed), never from the files on disk. The commit it describes is not")
	w("written here, so the list does not change by itself.")
	w("")
	w("To regenerate it, at the root of the repository: `python3 tools/file_origins.py` (on Windows:")
	w("`py -3 tools/file_origins.py`); `--check` exits with code 1 when FILES.md is not up to date. It is regenerated")
	w("and committed before every version tag, so the published source always carries the list of its own files.")
	w("Regenerating it needs the git repository of the image, with its history back to the base commit; a published")
	w("source tree is only a copy of the files and cannot regenerate the list, but every path can be checked in it.")
	w("")
	w("## Counts")
	w("")
	w("| Group | Files |")
	w("|---|---:|")
	w("| 1. Unchanged from the enigma2 base | %d |" % len(unchanged))
	w("| 2. Modified from the enigma2 base | %d |" % len(modified))
	w("| 3. Added from other sources | %d |" % len(other))
	w("| 4. Added by HD Satelit / Monea Software | %d |" % (len(ours_code) + len(ours_res)))
	w("| Total files in this tree | %d |" % total)
	w("| Removed from the enigma2 base | %d |" % len(removed))
	w("")
	w("Group 3 holds %d files with \"%s\"; group 4 holds %d source files with our copyright line and %d pictures,"
		% (uncertain, NOT_RECORDED, len(ours_code), len(ours_res)))
	w("fonts, data, build and documentation files.")
	w("")
	w("## How the added files are sorted")
	w("")
	w("- A text file goes to group 4 when one of its first %d lines is our copyright line: a line with" % HEADER_LINES)
	w("  \"Copyright\" and moneasoftware.com or Monea Software, or a line that starts with \"HD Satelit")
	w("  (moneasoftware.com ...)\" and has a year. A line that says only that the file was changed by moneasoftware.com")
	w("  is not a copyright line: such files stay in group 3.")
	w("- Pictures, fonts, data, build and documentation files carry no header. They are sorted by folder, using the")
	w("  table in `tools/file_origins.py`, written from the commits that added them: the folders created by HD Satelit")
	w("  (the HDSatelit theme, the feed plugins, the Hds modules and plugins, the image data) go to group 4; fonts and")
	w("  icons from other projects go to group 3 with their source; anything else is \"%s\". A code file" % NOT_RECORDED)
	w("  never goes to group 4 because of its folder. No commit of this repository is written here, so the list")
	w("  depends only on the files of the tree.")
	w("- Every file of group 3 has its origin: the source named in its header (the headers of this tree are in")
	w("  Romanian; \"Luat din sursele GPL enigma2 (OE-Alliance), commitul ...\" means taken from the GPL enigma2")
	w("  sources of OE-Alliance at that commit), or the source from the table. The licenses named in the header are")
	w("  given next to it. \"%s\" means that neither the header nor the table says where the file" % NOT_RECORDED)
	w("  comes from.")
	w("")
	w("## 1. Unchanged from the enigma2 base (%d)" % len(unchanged))
	w("")
	for d, files in by_folder(unchanged):
		w("- **`%s`** (%d): %s" % (d, len(files), names(files)))
	w("")
	w("## 2. Modified from the enigma2 base (%d)" % len(modified))
	w("")
	for d, files in by_folder(modified):
		shown = []
		for f in files:
			p = f if d == "./" else d + f
			old = modified.get(p)
			shown.append("`%s` (renamed from `%s`)" % (f, old) if old else "`%s`" % f)
		w("- **`%s`** (%d): %s" % (d, len(files), ", ".join(shown)))
	w("")
	w("## 3. Added from other sources (%d)" % len(other))
	w("")
	groups = {}
	for p, note in other:
		groups.setdefault(folder(p), []).append((posixpath.basename(p), note))
	for d in sorted(groups):
		w("### `%s`" % d)
		w("")
		bynote = {}
		order = []
		for f, note in groups[d]:
			if note not in bynote:
				bynote[note] = []
				order.append(note)
			bynote[note].append(f)
		for note in order:
			w("- %s: %s." % (names(bynote[note]), note))
		w("")
	w("## 4. Added by HD Satelit / Monea Software (%d)" % (len(ours_code) + len(ours_res)))
	w("")
	w("### Source files with our copyright line (%d)" % len(ours_code))
	w("")
	for d, files in by_folder(ours_code):
		w("- **`%s`** (%d): %s" % (d, len(files), names(files)))
	w("")
	w("### Pictures, fonts, data, build and documentation files of our folders (%d)" % len(ours_res))
	w("")
	res_groups = {}
	for p, note in ours_res:
		res_groups.setdefault(folder(p), []).append(p)
	for d in sorted(res_groups):
		paths = res_groups[d]
		files = [posixpath.basename(p) for p in paths]
		w("- **`%s`** (%d): %s" % (d, len(files), names(files)))
	w("")
	w("## Removed from the enigma2 base (%d)" % len(removed))
	w("")
	w("Why they were removed: `doc/REMOVED-FILES`.")
	w("")
	for d, files in by_folder(removed):
		w("- **`%s`** (%d): %s" % (d, len(files), names(files)))
	text = "\n".join(out) + "\n"
	listed = set(tree) | {OUTPUT}
	stats = {
		"unchanged": len(unchanged), "modified": len(modified), "other": len(other),
		"ours_code": len(ours_code), "ours_res": len(ours_res), "removed": len(removed),
		"not_recorded": uncertain, "total": total, "tree": len(listed),
	}
	return text, stats


def main(argv=None):
	ap = argparse.ArgumentParser(description="Write FILES.md, the files of this tree sorted by origin.")
	ap.add_argument("--repo", default=None, help="repository (default: the one holding this script)")
	ap.add_argument("--rev", default="HEAD", help="commit to describe (default: HEAD)")
	ap.add_argument("--base", default=BASE, help="enigma2 base commit (default: %s)" % BASE)
	ap.add_argument("--output", default=None, help="file to write (default: FILES.md at the root)")
	ap.add_argument("--check", "--verifica", action="store_true", dest="check",
		help="compare with the FILES.md committed in --rev; exit code 1 when it differs")
	args = ap.parse_args(argv)
	repo = args.repo or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
	try:
		repo = git(repo, "rev-parse", "--show-toplevel").decode().strip()
	except (OSError, subprocess.CalledProcessError):
		sys.stderr.write("file_origins: %s is not a git repository; the list is made from the git repository of the"
			" image, with its history back to the base commit\n" % repo)
		return 2
	for rev in (args.base, args.rev):
		try:
			git(repo, "cat-file", "-e", rev + "^{commit}")
		except subprocess.CalledProcessError:
			sys.stderr.write("file_origins: commit %s is not in %s; the list needs the history of the image back to"
				" the enigma2 base commit %s (a published source tree is only a copy of the files)\n"
				% (rev, repo, args.base))
			return 2
	text, stats = build(repo, args.rev, args.base)
	if stats["total"] != stats["tree"]:
		sys.stderr.write("file_origins: %d files listed, %d in the tree\n" % (stats["total"], stats["tree"]))
		return 2
	if args.check:
		try:
			committed = git(repo, "show", "%s:%s" % (args.rev, OUTPUT)).decode("utf-8")
		except subprocess.CalledProcessError:
			committed = None
		if committed != text:
			sys.stderr.write("file_origins: %s in %s is not up to date; run python3 tools/file_origins.py and commit it\n"
				% (OUTPUT, args.rev))
			return 1
		print("file_origins: %s is up to date" % OUTPUT)
		return 0
	output = args.output or os.path.join(repo, OUTPUT)
	with open(output, "w", encoding="utf-8", newline="\n") as f:
		f.write(text)
	print("file_origins: %s written: %d unchanged, %d modified, %d from other sources (%d origin not recorded),"
		" %d ours (%d with our copyright line, %d other files), %d removed, %d in total"
		% (output, stats["unchanged"], stats["modified"], stats["other"], stats["not_recorded"],
			stats["ours_code"] + stats["ours_res"], stats["ours_code"], stats["ours_res"], stats["removed"],
			stats["total"]))
	return 0


if __name__ == "__main__":
	sys.exit(main())
