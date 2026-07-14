#!/usr/bin/env python3
import base64, re, struct

# Read the manifest launcher
with open(r'Coruna-main\other\7a7d99099b035b2c6512b6ebeeea6df1ede70fbb.js', 'r') as f:
    content = f.read()

# Extract the base64 string from window['qbrdr']('...')
match = re.search(r'window\["qbrdr"\]\("(.+?)"\)', content)
if not match:
    match = re.search(r'qbrdr\("(.+?)"', content)

if match:
    b64 = match.group(1)
    print(f'Base64 length: {len(b64)}')
    decoded = base64.b64decode(b64)
    print(f'Decoded length: {len(decoded)} bytes')
    print(f'First 64 bytes hex: {decoded[:64].hex()}')
    
    if len(decoded) >= 4:
        magic = struct.unpack('<I', decoded[:4])[0]
        print(f'Magic: 0x{magic:08X}')
    
    with open('manifest_decoded.bin', 'wb') as f:
        f.write(decoded)
    print('Saved manifest_decoded.bin')
else:
    print('No base64 found, trying raw extraction...')
    # Maybe it's split or formatted differently
    print(content[:500])
