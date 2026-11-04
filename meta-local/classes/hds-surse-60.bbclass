# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# NUMAI pe OE-Alliance 6.0 (pregateste-strat-60.sh o pune in stratul 6.0 si adauga INHERIT += "hds-surse-60" dupa
# hds-surse). In 6.0 archiver.bbclass (do_ar_original) arhiveaza o sursa git despachetata din tmpdir/${BP} (in 5.6
# lua tot tmpdir). O sursa git cu subpath= se despacheteaza insa in tmpdir/<numele lui subpath>, iar fara ${BP} tar se
# opreste: asa cadea linux-dinobot pe 6.0, la wireguard (git, subpath=src). Aici create_tarball (aceeasi ca in
# archiver.bbclass din 6.0) ia dosarul despachetat unic cand ${BP} lipseste, deci sursa wireguard intra in arhiva ca
# la 5.6. In rest nimic schimbat.

def create_tarball(d, srcdir, suffix, ar_outdir):
    """
    create the tarball from srcdir (archiver.bbclass din 6.0, plus dosarul unic cand ${BP} lipseste)
    """
    import subprocess

    # Make sure we are only creating a single tarball for gcc sources
    if (d.getVar('SRC_URI') == ""):
        return

    baza = os.path.normpath(srcdir)
    if not os.path.isdir(baza):
        parinte = os.path.dirname(baza)
        intrari = os.listdir(parinte) if os.path.isdir(parinte) else []
        if len(intrari) == 1 and os.path.isdir(os.path.join(parinte, intrari[0])):
            bb.note("hds-surse-60: %s lipseste, arhivez %s" % (os.path.basename(baza), intrari[0]))
            srcdir = os.path.join(parinte, intrari[0], '.')

    # For the kernel archive, srcdir may just be a link to the
    # work-shared location. Use os.path.realpath to make sure
    # that we archive the actual directory and not just the link.
    srcdir = os.path.realpath(srcdir)

    compression_method = d.getVarFlag('ARCHIVER_MODE', 'compression')
    if compression_method == "xz":
        compression_cmd = "xz %s" % d.getVar('XZ_DEFAULTS')
    # To keep compatibility with ARCHIVER_MODE[compression]
    elif compression_method == "gz":
        compression_cmd = "gzip"
    elif compression_method == "bz2":
        compression_cmd = "bzip2"
    else:
        bb.fatal("Unsupported compression_method: %s" % compression_method)

    bb.utils.mkdirhier(ar_outdir)
    if suffix:
        filename = '%s-%s.tar.%s' % (d.getVar('PF'), suffix, compression_method)
    else:
        filename = '%s.tar.%s' % (d.getVar('PF'), compression_method)
    tarname = os.path.join(ar_outdir, filename)

    bb.note('Creating %s' % tarname)
    dirname = os.path.dirname(srcdir)
    basename = os.path.basename(srcdir)
    tar_cmd = ["tar", "--exclude=temp", "--exclude=patches", "--exclude=.pc", '-cf', tarname, basename, '-I', compression_cmd]
    subprocess.check_call(tar_cmd, cwd=dirname)
