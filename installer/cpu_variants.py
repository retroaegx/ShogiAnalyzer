"""Select only native binaries and instruction sets known to be supported."""
from pathlib import Path
import struct


def binary_target(path: Path) -> tuple[str, set[str]]:
    try:
        with path.open('rb') as source:
            header = source.read(64)
            if header.startswith(b'MZ') and len(header) >= 64:
                source.seek(int.from_bytes(header[60:64], 'little'))
                pe = source.read(6)
                arch = {0x8664:'amd64', 0xaa64:'arm64', 0x14c:'x86'}.get(int.from_bytes(pe[4:6], 'little'))
                return ('windows', {arch}) if pe[:4] == b'PE\x00\x00' and arch else ('', set())
            if header.startswith(b'\x7fELF'):
                endian = 'little' if header[5] == 1 else 'big'
                arch = {62:'amd64', 183:'arm64', 3:'x86'}.get(int.from_bytes(header[18:20], endian))
                return 'linux', {arch} if arch else set()
            # Thin and universal Mach-O executables.
            magic = header[:4]
            thin = {b'\xcf\xfa\xed\xfe':'<', b'\xfe\xed\xfa\xcf':'>', b'\xce\xfa\xed\xfe':'<', b'\xfe\xed\xfa\xce':'>'}
            cpu = {0x01000007:'amd64', 0x0100000c:'arm64'}
            if magic in thin:
                arch = cpu.get(struct.unpack(thin[magic] + 'I', header[4:8])[0])
                return 'darwin', {arch} if arch else set()
            fat = {b'\xca\xfe\xba\xbe':('>',20), b'\xbe\xba\xfe\xca':('<',20),
                b'\xca\xfe\xba\xbf':('>',32), b'\xbf\xba\xfe\xca':('<',32)}
            if magic in fat:
                endian, stride = fat[magic]
                count = min(struct.unpack(endian + 'I', header[4:8])[0], 32)
                source.seek(8)
                entries = source.read(stride * count)
                return 'darwin', {cpu[value] for offset in range(0, len(entries), stride)
                    if len(entries[offset:offset+4]) == 4 and (value := struct.unpack(endian+'I', entries[offset:offset+4])[0]) in cpu}
    except (OSError, ValueError, IndexError, struct.error):
        pass
    return '', set()


def instruction_score(name: str, flags: set[str], arch: str) -> int | None:
    normalized = {f.lower().replace('_','').replace('.','') for f in flags}
    if arch == 'amd64':
        normalized.add('sse2')  # x86-64 architectural baseline
    n = name.lower().replace('_','').replace('.','').replace('-','')
    variants = [('avx512vnni', {'avx512f','avx512vnni'}, 80), ('avx512', {'avx512f','avx512bw','avx512dq','avx512vl'}, 70),
        ('avxvnni', {'avx2','avxvnni'}, 60), ('avx2', {'avx2'}, 50), ('avx', {'avx'}, 40),
        ('sse42', {'sse42'}, 30), ('sse41', {'sse41'}, 20), ('ssse3', {'ssse3'}, 10), ('sse2', {'sse2'}, 5)]
    for token, needs, score in variants:
        if token in n:
            return score if needs <= normalized and arch == 'amd64' else None
    if 'zen' in n:  # do not guess vendor-specific requirements
        return None
    return 0


def choose_engine(root: Path, os_key: str, arch: str, flags: set[str], type_hint: str = '') -> Path | None:
    candidates = []
    for path in root.rglob('*'):
        if not path.is_file() or (os_key == 'windows' and path.suffix.lower() != '.exe'):
            continue
        if type_hint and type_hint.lower() not in path.name.lower():
            continue
        target, arches = binary_target(path)
        if target != os_key or arch not in arches:
            continue
        score = instruction_score(path.name, flags, arch)
        if score is not None:
            candidates.append((score, path))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], str(item[1]).lower()))
    selected = candidates[0][1]
    if os_key != 'windows':
        selected.chmod(selected.stat().st_mode | 0o111)
    return selected
