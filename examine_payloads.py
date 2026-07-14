#!/usr/bin/env python3
import struct, os

downloaded_dir = r'Coruna-main\downloaded'
for fname in sorted(os.listdir(downloaded_dir)):
    if not fname.endswith('.min.js'):
        continue
    path = os.path.join(downloaded_dir, fname)
    with open(path, 'rb') as f:
        data = f.read()
    
    magic = struct.unpack('<I', data[:4])[0] if len(data) >= 4 else 0
    is_f00dbeef = data[:4] == b'\xef\xbe\x0d\xf0'
    is_0bedf00d = data[:4] == b'\x0d\xf0\xed\x0b'
    is_xz = data[:6] == b'\xfd7zXZ\x00'
    
    print(f'{fname[:40]}: {len(data):7d} bytes | magic=0x{magic:08X} | F00DBEEF={is_f00dbeef} 0BEDF00D={is_0bedf00d} XZ={is_xz}')
