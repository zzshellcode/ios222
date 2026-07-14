#!/usr/bin/env python3
"""
Coruna Exploit Toolkit — Payload Decryption Pipeline
Based on: https://github.com/EliasTekdin/coruna/blob/main/ANALYSIS.md

Steps:
1. fqMaGkN4() → UTF-16LE → 32-byte master key
2. Decrypt manifest: ChaCha20(master_key, nonce=0) → check 0x0BEDF00D → LZMA
3. Parse manifest: 19 entries at 0x120, each 0x64 bytes
4. Download payloads from C2 (or local files)
5. Decrypt each: ChaCha20(per_file_key, nonce=0) → LZMA
6. Parse F00DBEEF containers → extract Mach-O dylibs
"""

import struct
import hashlib
import lzma
import os
import sys

# ============================================================================
# Step 1: fqMaGkN4() → UTF-16LE → 32-byte master key
# ============================================================================

def fqMaGkN4(arr):
    """
    JavaScript: fqMaGkN4([3436285875, 2332907478, ...])
    For each uint32 q:
        b0 = q & 0xFF
        b1 = (q >> 8) & 0xFF
        b2 = (q >> 16) & 0xFF
        b3 = (q >> 24) & 0xFF
        char1 = (b1 << 8) | b0   # low 16 bits, little-endian
        char2 = (b3 << 8) | b2   # high 16 bits, little-endian
    Returns UTF-16LE encoded bytes (32 bytes for 8 uint32s)
    """
    result = []
    for q in arr:
        b0 = q & 0xFF
        b1 = (q >> 8) & 0xFF
        b2 = (q >> 16) & 0xFF
        b3 = (q >> 24) & 0xFF
        char1 = (b1 << 8) | b0
        char2 = (b3 << 8) | b2
        # Pack as UTF-16LE (little-endian)
        result.append(char1 & 0xFF)
        result.append((char1 >> 8) & 0xFF)
        result.append(char2 & 0xFF)
        result.append((char2 >> 8) & 0xFF)
    return bytes(result)

# Master key input from group.html:293
MASTER_KEY_INPUT = [3436285875, 2332907478, 2884495420, 233193687,
                    1144711575, 1605576699, 1942246444, 1994816675]

master_key = fqMaGkN4(MASTER_KEY_INPUT)
print(f"[*] Master key ({len(master_key)} bytes): {master_key.hex()}")
print(f"[*] Expected:              b38fd1ccd6570d8b3ce8edabd740e60d97e93a44fb27b35f2c54c473a37ce676")

# ============================================================================
# Step 2: ChaCha20 (Original DJB variant, 64-bit counter, 64-bit nonce=0)
# ============================================================================

def chacha20_djb(key, counter, nonce, data):
    """
    Original DJB ChaCha20 (NOT IETF RFC 8439)
    - 64-bit block counter
    - 64-bit nonce (all zeros)
    - 20 rounds (10 double-rounds)
    """
    assert len(key) == 32
    assert len(nonce) == 8
    
    def quarter_round(x, a, b, c, d):
        x[a] = (x[a] + x[b]) & 0xFFFFFFFF
        x[d] = ((x[d] ^ x[a]) << 16 | (x[d] ^ x[a]) >> 16) & 0xFFFFFFFF
        x[c] = (x[c] + x[d]) & 0xFFFFFFFF
        x[b] = ((x[b] ^ x[c]) << 12 | (x[b] ^ x[c]) >> 20) & 0xFFFFFFFF
        x[a] = (x[a] + x[b]) & 0xFFFFFFFF
        x[d] = ((x[d] ^ x[a]) << 8 | (x[d] ^ x[a]) >> 24) & 0xFFFFFFFF
        x[c] = (x[c] + x[d]) & 0xFFFFFFFF
        x[b] = ((x[b] ^ x[c]) << 7 | (x[b] ^ x[c]) >> 25) & 0xFFFFFFFF
    
    def chacha20_block(key, counter, nonce):
        # "expand 32-byte k" sigma constant
        state = [
            0x61707865, 0x3320646e, 0x79622d32, 0x6b206574,  # sigma
            *struct.unpack('<8I', key),
            counter & 0xFFFFFFFF, (counter >> 32) & 0xFFFFFFFF,
            *struct.unpack('<2I', nonce),
        ]
        working = list(state)
        
        for _ in range(10):  # 20 rounds = 10 double-rounds
            # Column rounds
            quarter_round(working, 0, 4, 8, 12)
            quarter_round(working, 1, 5, 9, 13)
            quarter_round(working, 2, 6, 10, 14)
            quarter_round(working, 3, 7, 11, 15)
            # Diagonal rounds
            quarter_round(working, 0, 5, 10, 15)
            quarter_round(working, 1, 6, 11, 12)
            quarter_round(working, 2, 7, 8, 13)
            quarter_round(working, 3, 4, 9, 14)
        
        result = [(working[i] + state[i]) & 0xFFFFFFFF for i in range(16)]
        return struct.pack('<16I', *result)
    
    output = bytearray()
    block_count = counter
    for i in range(0, len(data), 64):
        block = chacha20_block(key, block_count, nonce)
        chunk = data[i:i+64]
        output.extend(bytes(a ^ b for a, b in zip(chunk, block)))
        block_count += 1
    return bytes(output)

# ============================================================================
# Step 3: LZMA Decompression (Apple variant with 0x0BEDF00D header)
# ============================================================================

def decompress_payload(data):
    """
    Decompress a Coruna payload:
    1. Check for 0x0BEDF00D magic header (8 bytes)
    2. Extract expected decompressed size
    3. LZMA decompress the rest
    """
    if len(data) < 8:
        return None
    
    magic = struct.unpack('<I', data[0:4])[0]
    if magic != 0x0BEDF00D:
        print(f"  [!] Bad magic: 0x{magic:08X} (expected 0x0BEDF00D)")
        return None
    
    expected_size = struct.unpack('<I', data[4:8])[0]
    compressed = data[8:]
    
    # Check for XZ/LZMA stream header
    if compressed[:2] == b'\xfd7zXZ':
        # XZ format
        try:
            return lzma.decompress(compressed, format=lzma.FORMAT_XZ)
        except Exception as e:
            print(f"  [!] XZ decompress failed: {e}")
    else:
        # Try raw LZMA
        try:
            return lzma.decompress(compressed, format=lzma.FORMAT_ALONE)
        except Exception as e:
            print(f"  [!] LZMA decompress failed: {e}")
    
    # Try with LZMA2 header
    try:
        # LZMA2 in XZ container
        return lzma.decompress(b'\xfd7zXZ\x00' + compressed)
    except:
        pass
    
    return None

# ============================================================================
# Step 4: Parse F00DBEEF Container
# ============================================================================

def parse_f00dbeef(data):
    """
    Parse F00DBEEF container format:
    0x00: 4 bytes - Magic: 0xF00DBEEF
    0x04: 4 bytes - Entry count (uint32)
    0x08: 16*N bytes - Entry table
      +0x00: 4 bytes - Field 1 (upper 16 bits = segment type)
      +0x04: 4 bytes - Field 2 (flags)
      +0x08: 4 bytes - Data offset
      +0x0C: 4 bytes - Data size
    [data]: Concatenated entry payloads
    """
    if len(data) < 8:
        return None
    
    magic = struct.unpack('<I', data[0:4])[0]
    if magic != 0xF00DBEEF:
        print(f"  [!] Bad F00DBEEF magic: 0x{magic:08X}")
        return None
    
    entry_count = struct.unpack('<I', data[4:8])[0]
    print(f"  [*] Entry count: {entry_count}")
    
    entries = []
    offset = 0x08
    for i in range(entry_count):
        field1, flags, data_offset, data_size = struct.unpack('<4I', data[offset:offset+16])
        segment_type = (field1 >> 16) & 0xFFFF
        entries.append({
            'index': i,
            'segment_type': segment_type,
            'flags': flags,
            'data_offset': data_offset,
            'data_size': data_size,
            'field1': field1,
        })
        offset += 16
    
    return entries

# ============================================================================
# Step 5: Parse Manifest
# ============================================================================

SEGMENT_TYPE_NAMES = {
    0x05: "Data blob (kernel offsets/gadgets)",
    0x07: "Config/metadata",
    0x08: "Main implant (powerd, HTTP C2)",
    0x09: "Kernel/sandbox escape",
    0x0a: "Additional exploit/persistence",
    0x0f: "Persistence (launchd hooks)",
}

def parse_manifest(data):
    """
    Parse the decrypted manifest:
    - Magic: 0xF00DBEEF
    - Entries start at offset 0x120
    - Each entry: 0x64 (100) bytes
    - Entry layout:
      0x00: 6 bytes header/padding
      0x06: 2 bytes flags (iOS version / architecture)
      0x08: 32 bytes per-file ChaCha20 key
      0x28: 48 bytes filename (40-char hex hash + ".min.js" + NUL + padding)
    """
    if len(data) < 0x120:
        print("[!] Manifest too small")
        return None
    
    magic = struct.unpack('<I', data[0:4])[0]
    if magic != 0xF00DBEEF:
        print(f"[!] Bad manifest magic: 0x{magic:08X}")
        return None
    
    entries = []
    offset = 0x120
    entry_size = 0x64  # 100 bytes
    
    while offset + entry_size <= len(data):
        entry = data[offset:offset+entry_size]
        
        # Parse entry
        padding = entry[0:6]
        flags = struct.unpack('<H', entry[6:8])[0]
        file_key = entry[8:40]
        filename_raw = entry[40:88]
        
        # Extract filename (null-terminated)
        null_pos = filename_raw.find(b'\x00')
        if null_pos >= 0:
            filename = filename_raw[:null_pos].decode('ascii', errors='replace')
        else:
            filename = filename_raw.decode('ascii', errors='replace')
        
        # Decode flags
        arch = "arm64e" if (flags & 0xF000) == 0xF000 else "arm64"
        
        entries.append({
            'flags': flags,
            'arch': arch,
            'file_key': file_key,
            'filename': filename,
            'offset': offset,
        })
        
        offset += entry_size
    
    return entries

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 70)
    print("Coruna Exploit Toolkit — Payload Decryption Pipeline")
    print("=" * 70)
    
    # --- Step 1: Master Key ---
    print("\n[Step 1] Decoding master key...")
    master_key = fqMaGkN4(MASTER_KEY_INPUT)
    print(f"  Key: {master_key.hex()}")
    
    # --- Step 2: Decrypt manifest ---
    print("\n[Step 2] Decrypting manifest...")
    manifest_file = "downloaded/7a7d99099b035b2c6512b6ebeeea6df1ede70fbb.min.js"
    
    if not os.path.exists(manifest_file):
        # Try to find it
        for root, dirs, files in os.walk("downloaded"):
            for f in files:
                if "7a7d" in f:
                    manifest_file = os.path.join(root, f)
                    break
    
    if os.path.exists(manifest_file):
        print(f"  Found: {manifest_file}")
        with open(manifest_file, 'rb') as f:
            encrypted = f.read()
        
        # ChaCha20 decrypt with master key, nonce=0
        nonce = b'\x00' * 8
        decrypted = chacha20_djb(master_key, 0, nonce, encrypted)
        
        # Check magic and decompress
        if decrypted[:4] == b'\xef\xbe\x0d\xf0':  # 0xF00DBEEF
            print("  [!] Already F00DBEEF format (no LZMA?)")
            manifest_data = decrypted
        elif decrypted[:4] == b'\xfd7zX':
            print("  [*] XZ compressed, decompressing...")
            manifest_data = lzma.decompress(decrypted)
        else:
            print(f"  [*] First 16 bytes: {decrypted[:16].hex()}")
            # Try decompressing anyway
            manifest_data = decompress_payload(decrypted)
            if manifest_data is None:
                print("  [!] Failed to decompress manifest")
                manifest_data = decrypted  # Use as-is
    
    # Check if we have a local manifest
    local_manifest = "payload/7a7d99099b035b2c6512b6ebeeea6df1ede70fbb"
    if os.path.exists(local_manifest):
        print(f"  Using local manifest: {local_manifest}")
        with open(local_manifest, 'rb') as f:
            manifest_data = f.read()
    
    if 'manifest_data' not in dir():
        print("[!] No manifest found. Checking payload/ directory...")
        if os.path.isdir("payload"):
            for f in os.listdir("payload"):
                if "7a7d" in f:
                    manifest_data = open(os.path.join("payload", f), 'rb').read()
                    print(f"  Found: payload/{f}")
                    break
    
    if 'manifest_data' not in dir():
        print("[!] Cannot find manifest. Available files:")
        for root, dirs, files in os.walk("."):
            for f in files:
                if f.endswith(('.bin', '.js')) and ('7a7d' in f or 'payload' in root.lower()):
                    print(f"    {os.path.join(root, f)}")
        return
    
    # --- Step 3: Parse manifest ---
    print(f"\n[Step 3] Parsing manifest ({len(manifest_data)} bytes)...")
    manifest_entries = parse_manifest(manifest_data)
    
    if manifest_entries:
        print(f"  Found {len(manifest_entries)} payload entries:")
        for i, entry in enumerate(manifest_entries):
            print(f"    [{i:2d}] flags=0x{entry['flags']:04X} arch={entry['arch']} "
                  f"key={entry['file_key'][:8].hex()}... file={entry['filename'][:40]}")
    
    # --- Step 4: Parse F00DBEEF in manifest ---
    print("\n[Step 4] Checking for F00DBEEF container in manifest...")
    f00_entries = parse_f00dbeef(manifest_data)
    if f00_entries:
        for entry in f00_entries:
            type_name = SEGMENT_TYPE_NAMES.get(entry['segment_type'], f"Unknown (0x{entry['segment_type']:02x})")
            print(f"    [{entry['index']}] type=0x{entry['segment_type']:02x} ({type_name}) "
                  f"size={entry['data_size']} bytes offset=0x{entry['data_offset']:x}")
    
    # --- Step 5: Decrypt individual payloads ---
    print("\n[Step 5] Decrypting payload files...")
    
    payload_dir = "payload"
    downloaded_dir = "downloaded"
    extracted_dir = "extracted"
    
    for entry in manifest_entries:
        filename = entry['filename']
        file_key = entry['file_key']
        
        # Look for the file
        payload_path = None
        for search_dir in [downloaded_dir, payload_dir, extracted_dir]:
            candidate = os.path.join(search_dir, filename)
            if os.path.exists(candidate):
                payload_path = candidate
                break
            # Try without .min.js extension
            candidate2 = os.path.join(search_dir, filename.replace('.min.js', '.bin'))
            if os.path.exists(candidate2):
                payload_path = candidate2
                break
        
        if payload_path is None:
            print(f"  [!] File not found: {filename}")
            continue
        
        print(f"  [*] Processing: {payload_path}")
        
        with open(payload_path, 'rb') as f:
            encrypted = f.read()
        
        # ChaCha20 decrypt with per-file key
        nonce = b'\x00' * 8
        decrypted = chacha20_djb(file_key, 0, nonce, encrypted)
        
        # Decompress
        decompressed = decompress_payload(decrypted)
        if decompressed is None:
            print(f"    [!] Decompress failed, using raw")
            decompressed = decrypted
        
        # Save decrypted
        out_path = f"decrypted/{filename}.dec"
        os.makedirs("decrypted", exist_ok=True)
        with open(out_path, 'wb') as f:
            f.write(decompressed)
        print(f"    [+] Saved: {out_path} ({len(decompressed)} bytes)")
        
        # Check if it's a F00DBEEF container
        if decompressed[:4] == b'\xef\xbe\x0d\xf0':
            print(f"    [*] F00DBEEF container detected!")
            inner_entries = parse_f00dbeef(decompressed)
            if inner_entries:
                for ie in inner_entries:
                    type_name = SEGMENT_TYPE_NAMES.get(ie['segment_type'], 
                                                        f"Unknown (0x{ie['segment_type']:02x})")
                    # Extract the entry data
                    entry_data = decompressed[ie['data_offset']:ie['data_offset']+ie['data_size']]
                    
                    # Save extracted Mach-O
                    out_file = f"decrypted/{filename}_entry{ie['index']}_type0x{ie['segment_type']:02x}.dylib"
                    with open(out_file, 'wb') as f:
                        f.write(entry_data)
                    print(f"      [+] Extracted: {out_file} ({len(entry_data)} bytes) - {type_name}")
    
    print("\n" + "=" * 70)
    print("Done! Check the 'decrypted/' directory for extracted files.")
    print("=" * 70)

if __name__ == "__main__":
    main()
