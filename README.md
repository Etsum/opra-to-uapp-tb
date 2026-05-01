# OPRA to UAPP PEQ Converter

Converts parametric EQ presets from the [OPRA database](https://github.com/opra-project/OPRA) into XML preset files compatible with [USB Audio Player Pro (UAPP)](https://www.extreamsd.com/index.php/products/usb-audio-player-pro) / Toneboosters PEQ.

## Quick start

Download the latest pre-built presets from the [Releases](../../releases) page — no need to run any code.

## Usage (manual)

```bash
# Clone this repo
git clone https://github.com/YOUR_USER/opra-uapp-converter.git
cd opra-uapp-converter

# Clone the OPRA database
git clone --depth 1 https://github.com/opra-project/OPRA.git opra

# Run the converter
python convert.py opra --output TBEQPresets --verbose
```

The converter requires Python 3.8+ with no external dependencies.

### Options

| Flag | Description |
|------|-------------|
| `-o`, `--output` | Output directory (default: `TBEQPresets`) |
| `-v`, `--verbose` | Show detailed output |
| `--flat` | Put all presets in a single directory instead of vendor/product folders |

### Installing presets on your device

1. Download and extract the presets (from Releases or generated locally)
2. Browse to the preset files you want — they're organised by manufacturer and product
3. Connect your Android device to your computer
4. Copy the `.xml` files to the `UAPP/TBEQPresets` folder on your device
5. In UAPP, go to Parametric EQ settings → ⋮ (three dots) → Presets and select your preset
6. Make sure the PEQ is turned on (speaker icon on the PEQ screen, or the toggle in settings)

## Generating fresh presets via GitHub Actions

This repo includes a GitHub Actions workflow that can be triggered manually:

1. Go to the **Actions** tab
2. Select **Generate UAPP Presets from OPRA**
3. Click **Run workflow**
4. Once complete, a new Release will be created with the preset zip file

## How it works

The converter reads OPRA's `info.json` files for each EQ preset and converts the parametric EQ parameters into UAPP's XML format. The conversion involves:

- **Frequency:** Cube-root scaled normalisation from 16–20,000 Hz to 0–1
- **Gain:** Linear normalisation from ±20 dB to 0–1
- **Q factor:** Cube-root scaled normalisation from 0.1–10 to 0–1
- **Filter type:** Mapped to Toneboosters slider positions (low shelf, peak/dip, high shelf)
- **Bands** are sorted by frequency and up to 10 bands are supported per preset

## Credits

- **[OPRA](https://github.com/opra-project/OPRA)** — Open Profiles for Revealing Audio, the community-maintained EQ database
- **Preset authors** — oratory1990, Crinacle, Rtings, and many other contributors to the OPRA database
- Conversion logic based on analysis of the original [EqConverter](https://github.com/opra-project/OPRA) C# tool

## License

MIT — see [LICENSE](LICENSE).

The EQ data itself is from the OPRA project and is licensed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
