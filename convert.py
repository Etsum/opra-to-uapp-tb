#!/usr/bin/env python3
"""
OPRA to UAPP PEQ Converter

Converts parametric EQ presets from the OPRA database into XML preset files
compatible with USB Audio Player Pro (UAPP) / Toneboosters PEQ.

Usage:
    python convert.py <opra_database_dir> [--output <output_dir>] [--verbose]

The OPRA database directory should contain:
    database/vendors/<vendor>/products/<product>/eq/<eq_slug>/info.json
"""

import argparse
import json
import math
import os
import sys
import xml.etree.ElementTree as ET
from xml.dom import minidom
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


# =============================================================================
# Constants
# =============================================================================

F_MIN = 16
F_MAX = 20000
Q_MIN = 0.1
Q_MAX = 10.0
GAIN_RANGE = 39.9  # Toneboosters native range
GAIN_OFFSET = 20.0

# UAPP/Toneboosters filter type constants (normalised slider positions)
FILTER_TYPE_LOW_SHELF = "0.071428575"   # 1/14
FILTER_TYPE_PEAK_DIP = "0.21428572"     # 3/14 (analog bell)
FILTER_TYPE_HIGH_SHELF = "0.2857143"    # 4/14

# Default values for disabled/empty filter slots
DEFAULT_F = 0.9282573       # ~16kHz normalised
DEFAULT_GAIN = 0.5          # 0 dB
DEFAULT_Q = 0.39434525      # ~0.71 normalised
DEFAULT_TYPE = FILTER_TYPE_PEAK_DIP

MAX_BANDS = 10


# =============================================================================
# Data classes
# =============================================================================

@dataclass
class Band:
    band_type: str      # "low_shelf", "peak_dip", "high_shelf"
    frequency: float    # Hz
    gain_db: float      # dB
    q: float


@dataclass
class EQPreset:
    name: str
    author: str
    details: str
    gain_db: float      # preamp gain in dB
    bands: list         # list of Band


# =============================================================================
# Normalisation functions
# =============================================================================

def normalise_frequency(f_hz: float) -> float:
    """Normalise frequency (Hz) to 0-1 range using cube root scaling."""
    f_clamped = max(F_MIN, min(F_MAX, f_hz))
    return round(((f_clamped - F_MIN) / (F_MAX - F_MIN)) ** (1.0 / 3.0), 9)


def normalise_gain(gain_db: float) -> float:
    """Normalise gain (dB) to 0-1 range using linear scaling."""
    return round((gain_db + GAIN_OFFSET) / GAIN_RANGE, 9)


def normalise_q(q: float) -> float:
    """Normalise Q factor to 0-1 range using cube root scaling."""
    q_clamped = max(Q_MIN, min(Q_MAX, q))
    return round(((q_clamped - Q_MIN) / (Q_MAX - Q_MIN)) ** (1.0 / 3.0), 9)


def filter_type_value(band_type: str) -> str:
    """Map OPRA band type to UAPP filter type constant."""
    mapping = {
        "low_shelf": FILTER_TYPE_LOW_SHELF,
        "peak_dip": FILTER_TYPE_PEAK_DIP,
        "high_shelf": FILTER_TYPE_HIGH_SHELF,
    }
    return mapping.get(band_type, FILTER_TYPE_PEAK_DIP)


# =============================================================================
# XML generation
# =============================================================================

def generate_xml(preset: EQPreset) -> str:
    """Generate UAPP-compatible XML string from an EQPreset."""
    # Sort bands by frequency (matching the original converter behaviour)
    sorted_bands = sorted(preset.bands, key=lambda b: b.frequency)

    # Truncate to MAX_BANDS
    if len(sorted_bands) > MAX_BANDS:
        sorted_bands = sorted_bands[:MAX_BANDS]

    # Build values list
    values = []

    for i in range(MAX_BANDS):
        if i < len(sorted_bands):
            band = sorted_bands[i]
            values.append(str(normalise_frequency(band.frequency)))
            values.append(str(normalise_gain(band.gain_db)))
            values.append("1.0")  # on
            values.append(str(normalise_q(band.q)))
            values.append(filter_type_value(band.band_type))
            values.append("0.0")  # unused
        else:
            # Disabled filter slot
            values.append(str(DEFAULT_F))
            values.append(str(DEFAULT_GAIN))
            values.append("0")    # off
            values.append(str(DEFAULT_Q))
            values.append(DEFAULT_TYPE)
            values.append("0.0")

    # Preamp section (6 values at the end)
    # Based on reference XMLs: [0.0, preamp, 0.34, 0.33333334, 0.05, 0.0]
    # Preamp is rounded to 2 decimal places in all reference presets
    preamp_norm = round(normalise_gain(preset.gain_db), 2)
    values.append("0.0")
    values.append(str(preamp_norm))
    values.append("0.34")           # constant across all reference presets
    values.append("0.33333334")
    values.append("0.05")
    values.append("0.0")

    # Build XML manually for exact format matching
    lines = [f'<?xml version="1.0" encoding="ISO-8859-1"?><Preset>']
    lines.append(f'<PresetInfo Name="{escape_xml_attr(preset.name)}" TenBand="1">')

    for i, val in enumerate(values):
        lines.append(f'<Value>{val}</Value>')
        # Add blank line after every 6th value (between filter blocks)
        if (i + 1) % 6 == 0 and i < len(values) - 1:
            lines.append('')

    lines.append('</PresetInfo>')
    lines.append('</Preset>')

    return '\n'.join(lines)


def sanitise_for_latin1(s: str) -> str:
    """Replace characters that can't be encoded in ISO-8859-1 with safe equivalents."""
    # Common Unicode -> ASCII substitutions
    replacements = {
        '\u2022': '-',   # • bullet
        '\u2013': '-',   # – en dash
        '\u2014': '-',   # — em dash
        '\u2018': "'",   # ' left single quote
        '\u2019': "'",   # ' right single quote
        '\u201c': '"',   # " left double quote
        '\u201d': '"',   # " right double quote
        '\u2026': '...',  # … ellipsis
    }
    for char, replacement in replacements.items():
        s = s.replace(char, replacement)
    # Drop any remaining non-Latin-1 characters
    return s.encode('iso-8859-1', errors='replace').decode('iso-8859-1')


def escape_xml_attr(s: str) -> str:
    """Escape special characters for XML attribute values."""
    s = sanitise_for_latin1(s)
    return (s.replace('&', '&amp;')
             .replace('"', '&quot;')
             .replace('<', '&lt;')
             .replace('>', '&gt;'))


# =============================================================================
# OPRA database parsing
# =============================================================================

def load_eq_preset(eq_info_path: Path, vendor_name: str, product_name: str) -> Optional[EQPreset]:
    """Load an EQ preset from an OPRA eq info.json file."""
    try:
        with open(eq_info_path, 'r') as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"  WARNING: Failed to read {eq_info_path}: {e}", file=sys.stderr)
        return None

    if data.get('type') != 'parametric_eq':
        return None

    params = data.get('parameters', {})
    if not params:
        return None

    bands_data = params.get('bands', [])
    if not bands_data:
        return None

    author = data.get('author', 'Unknown')
    details = data.get('details', '')

    # Clean up details field for the preset name
    # Strip common prefixes like "Measured by " to get cleaner names
    # e.g. "Measured by oratory1990" -> "oratory1990"
    clean_details = details
    for prefix in ('Measured by ', 'Based on '):
        if clean_details.startswith(prefix):
            clean_details = clean_details[len(prefix):]
            break

    # Build preset name: "Product - Author - Details" or "Product - Author"
    if clean_details:
        name = f"{product_name} - {author} - {clean_details}"
    else:
        name = f"{product_name} - {author}"

    bands = []
    for band_data in bands_data:
        band_type = band_data.get('type', 'peak_dip')
        if band_type not in ('low_shelf', 'peak_dip', 'high_shelf'):
            # Skip unknown filter types
            continue
        bands.append(Band(
            band_type=band_type,
            frequency=float(band_data.get('frequency', 1000)),
            gain_db=float(band_data.get('gain_db', 0)),
            q=float(band_data.get('q', 1.0)),
        ))

    if not bands:
        return None

    return EQPreset(
        name=name,
        author=author,
        details=details,
        gain_db=float(params.get('gain_db', 0)),
        bands=bands,
    )


def walk_opra_database(database_dir: Path, verbose: bool = False):
    """Walk the OPRA database and yield (vendor_name, product_name, EQPreset) tuples."""
    vendors_dir = database_dir / 'vendors'
    if not vendors_dir.is_dir():
        print(f"ERROR: vendors directory not found at {vendors_dir}", file=sys.stderr)
        return

    for vendor_dir in sorted(vendors_dir.iterdir()):
        if not vendor_dir.is_dir():
            continue

        # Read vendor name
        vendor_info_path = vendor_dir / 'info.json'
        vendor_name = vendor_dir.name
        if vendor_info_path.exists():
            try:
                with open(vendor_info_path) as f:
                    vendor_info = json.load(f)
                vendor_name = vendor_info.get('name', vendor_dir.name)
            except (json.JSONDecodeError, IOError):
                pass

        products_dir = vendor_dir / 'products'
        if not products_dir.is_dir():
            continue

        for product_dir in sorted(products_dir.iterdir()):
            if not product_dir.is_dir():
                continue

            # Read product name
            product_info_path = product_dir / 'info.json'
            product_name = product_dir.name
            if product_info_path.exists():
                try:
                    with open(product_info_path) as f:
                        product_info = json.load(f)
                    product_name = product_info.get('name', product_dir.name)
                except (json.JSONDecodeError, IOError):
                    pass

            eq_dir = product_dir / 'eq'
            if not eq_dir.is_dir():
                continue

            for eq_slug_dir in sorted(eq_dir.iterdir()):
                if not eq_slug_dir.is_dir():
                    continue

                eq_info_path = eq_slug_dir / 'info.json'
                if not eq_info_path.exists():
                    continue

                preset = load_eq_preset(eq_info_path, vendor_name, product_name)
                if preset:
                    if verbose:
                        print(f"  Found: {preset.name} ({len(preset.bands)} bands)")
                    yield vendor_name, product_name, preset


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Convert OPRA EQ presets to UAPP/Toneboosters PEQ XML format'
    )
    parser.add_argument(
        'database_dir',
        help='Path to the OPRA database directory (containing database/vendors/...)'
    )
    parser.add_argument(
        '-o', '--output',
        default='TBEQPresets',
        help='Output directory for XML preset files (default: TBEQPresets)'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    parser.add_argument(
        '--flat',
        action='store_true',
        help='Output all presets in a single directory (no vendor/product folders)'
    )

    args = parser.parse_args()

    database_dir = Path(args.database_dir)

    # The database dir might be the repo root or the database/ subdirectory
    if (database_dir / 'database' / 'vendors').is_dir():
        database_dir = database_dir / 'database'
    elif not (database_dir / 'vendors').is_dir():
        print(f"ERROR: Could not find vendors directory in {database_dir}", file=sys.stderr)
        print("Expected structure: <dir>/database/vendors/ or <dir>/vendors/", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    total = 0
    skipped = 0

    print(f"OPRA to UAPP PEQ Converter")
    print(f"Database: {database_dir}")
    print(f"Output:   {output_dir}")
    print()

    for vendor_name, product_name, preset in walk_opra_database(database_dir, args.verbose):
        # Sanitise names for filesystem
        safe_vendor = sanitise_filename(vendor_name)
        safe_product = sanitise_filename(product_name)
        safe_preset = sanitise_filename(preset.name)

        if args.flat:
            preset_dir = output_dir
        else:
            preset_dir = output_dir / safe_vendor / safe_product
            preset_dir.mkdir(parents=True, exist_ok=True)

        xml_path = preset_dir / f"{safe_preset}.xml"

        xml_content = generate_xml(preset)

        with open(xml_path, 'w', encoding='iso-8859-1') as f:
            f.write(xml_content)

        total += 1
        if args.verbose:
            print(f"  -> {xml_path}")

    print(f"\nDone! Generated {total} preset files in {output_dir}")
    if skipped:
        print(f"  ({skipped} skipped due to errors)")


def sanitise_filename(name: str) -> str:
    """Sanitise a string for use as a filename."""
    # First, apply the same Latin-1 substitutions for common Unicode chars
    result = sanitise_for_latin1(name)
    # Replace characters that are problematic on various filesystems
    bad_chars = '<>:"/\\|?*'
    for c in bad_chars:
        result = result.replace(c, '_')
    # Collapse multiple underscores/spaces
    while '  ' in result:
        result = result.replace('  ', ' ')
    return result.strip()


if __name__ == '__main__':
    main()
