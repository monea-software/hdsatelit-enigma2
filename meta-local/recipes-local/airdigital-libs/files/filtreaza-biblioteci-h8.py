#!/usr/bin/env python3
# Copyright (C) 2026 moneasoftware.com & hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
"""Pastreaza SDK-ul nativ, fara playerul FFmpeg vechi. Numai in D de build."""
from pathlib import Path
import struct
import sys

PREFIXES=('libavcodec.so','libavformat.so','libavutil.so','libavfilter.so',
          'libavdevice.so','libswscale.so','libswresample.so','libpostproc.so',
          'libformat_hi_ext.so','libcodec_hi_ext.so','libssl.so','libcrypto.so','libbluray.so',
          'libdash.so','libdashadp.so')

def forbidden(name):
    return name.startswith(PREFIXES) or 'ffmpeg' in name.lower()

def elf_metadata(data):
    if data[:4]!=b'\x7fELF':
        return None
    if len(data)<52 or data[4:6]!=b'\x01\x01' or struct.unpack_from('<H',data,18)[0]!=40:
        raise RuntimeError('SDK: ELF diferit de ARM32 little endian')
    offset=struct.unpack_from('<I',data,32)[0]
    size,count=struct.unpack_from('<HH',data,46)
    if size<40 or offset+size*count>len(data):
        raise RuntimeError('SDK: antet de sectiuni invalid')
    sections=[struct.unpack_from('<10I',data,offset+i*size) for i in range(count)]
    result={'needed':[],'soname':''}
    for section in sections:
        if section[1]!=6:
            continue
        if section[6]>=len(sections):
            raise RuntimeError('SDK: tabela de siruri lipseste')
        strings=sections[section[6]]
        if strings[4]+strings[5]>len(data) or section[4]+section[5]>len(data) or section[5]%8:
            raise RuntimeError('SDK: sectiune dinamica invalida')
        table=data[strings[4]:strings[4]+strings[5]]
        for pos in range(section[4],section[4]+section[5],8):
            tag,value=struct.unpack_from('<II',data,pos)
            if tag in (1,14):
                if value>=len(table) or b'\0' not in table[value:]:
                    raise RuntimeError('SDK: nume de biblioteca invalid')
                name=table[value:].split(b'\0',1)[0].decode('ascii')
                if tag==1:result['needed'].append(name)
                else:result['soname']=name
    return result

def filter_libraries(folder):
    folder=Path(folder)
    if folder.name!='hisilicon' or len(folder.parents)<3 or folder.parents[2].name!='image' or not folder.is_dir() or folder.is_symlink():
        raise RuntimeError('SDK: accept numai image/usr/lib/hisilicon din build')
    if folder.parents[2].is_symlink() or not folder.resolve().is_relative_to(folder.parents[2].resolve()):
        raise RuntimeError('SDK: o legatura iese din directorul image')
    metadata,links={},{}
    for path in folder.iterdir():
        if path.is_symlink():
            links[path.name]=Path(path.readlink()).name
        elif path.is_file():
            info=elf_metadata(path.read_bytes())
            if info is not None:metadata[path.name]=info
    removed={name for name in set(metadata)|set(links) if forbidden(name)}
    while True:
        bad_names=removed|{info['soname'] for name,info in metadata.items() if name in removed and info['soname']}
        more={name for name,info in metadata.items() if any(forbidden(dep) or dep in bad_names for dep in info['needed'])}
        more|={name for name,target in links.items() if target in bad_names}
        if more<=removed:break
        removed|=more
    for core in ('libhi_msp.so','libhi_common.so'):
        if core not in metadata or core in removed:
            raise RuntimeError('SDK: biblioteca nativa necesara nu poate fi pastrata: '+core)
    # Decidem intreaga selectie inainte de prima stergere; nu urmam legaturi.
    for name in sorted(removed):
        (folder/name).unlink()
    return sorted(removed)

if __name__=='__main__':
    removed=filter_libraries(sys.argv[1])
    print('H8 SDK: biblioteci native pastrate; eliminate: '+', '.join(removed))
