# Octane Standalone Plugin for AWS Thinkbox Deadline

A community-maintained render plugin for submitting Octane Standalone render jobs to AWS Thinkbox Deadline 10.4.

## Supported Versions

| Octane Standalone | Deadline | Status |
|-------------------|----------|--------|
| 2026.1 | 10.4 | Tested |
| 2019.x | 10.4 | Legacy (uses v4 Lua script) |
| 4.x | 10.4 | Legacy |

## Features

### Octane 2026.1 Specific
- Updated Lua API support (`saveRenderPassesMultiExr3`, `saveRenderPasses3`, `saveRenderPass3`)
- Color space output options:
  - SRGB
  - LINEAR_SRGB
  - ACES2065_1
  - ACESCG
  - OCIO (with custom color space and look names)
- Premultiplied alpha support for EXR/TIFF
- Force tone mapping option for linear color spaces
- EXR compression options (ZIP, PIZ, DWAA, DWAB, RLE, etc.)
- JPEG quality control
- DWA compression level control

### General Features
- Multi-layer EXR export with all render passes
- Individual render pass export
- Deep image output
- Skip existing files option
- Denoised main pass saving
- Composite project file generation (Photoshop)
- Sample override
- GPU device selection
- Real-time task progress tracking (sample-based)

## Installation

### Prerequisites
- AWS Thinkbox Deadline 10.4 installed and configured
- Octane Standalone 2026.1 (or 4.x/2019.x for legacy support)

### Steps

1. **Backup existing files** (recommended)
   ```
   <Deadline Repository>/plugins/Octane/
   <Deadline Repository>/scripts/Submission/OctaneSubmission.py
   ```

2. **Copy plugin files**
   - Copy the contents of `plugins/Octane/` to:
     ```
     <Deadline Repository>/plugins/Octane/
     ```
   - Copy `scripts/Submission/OctaneSubmission.py` to:
     ```
     <Deadline Repository>/scripts/Submission/
     ```

3. **Configure executable paths**
   - Open Deadline Monitor
   - Go to `Tools` > `Configure Plugins`
   - Select `Octane` from the plugin list
   - Set the executable path for your Octane version:
     - **Octane 2026**: Path to `octane.exe` (e.g., `C:\Program Files\OTOY\OctaneRender Enterprise 2026.1\octane.exe`)
     - **Octane 2019**: Path to older version if needed
     - **Octane 4**: Path to v4 if needed

4. **Restart Deadline services** (if needed)
   - Restart the Deadline Repository service
   - Restart any running Deadline Workers

## Usage

### Submitting a Job

1. Open Deadline Monitor
2. Go to `Submit` > `Octane`
3. Configure job settings:
   - Select your `.ocs` or `.orbx` scene file
   - Set output folder
   - Choose Octane version (4, 2019, or 2026)
   - Configure frame range
   - Set output format and options

### Output Format Options (2026.1)

| Format | Description |
|--------|-------------|
| PNG_8 | 8-bit PNG |
| PNG_16 | 16-bit PNG |
| EXR_16 | 16-bit OpenEXR (half float) |
| EXR_32 | 32-bit OpenEXR (full float) |
| TIFF_8 | 8-bit TIFF |
| TIFF_16 | 16-bit TIFF |
| JPEG | JPEG with quality control |

### Color Space Options (2026.1)

- **SRGB**: Standard sRGB color space
- **LINEAR_SRGB**: Linear sRGB (recommended for compositing)
- **ACES2065_1**: ACES 2065-1 color space
- **ACESCG**: ACEScg color space
- **OCIO**: Custom OCIO color space (requires color space name)

## File Structure

```
plugins/
  Octane/
    DeadlineOctane4.lua      # Lua script for Octane 4/2019
    DeadlineOctane2026.1.lua # Lua script for Octane 2026.1
    Octane.ico               # Plugin icon
    Octane.options           # Plugin options definition
    Octane.param             # Plugin parameters (executable paths)
    Octane.py                # Main plugin Python script
scripts/
  Submission/
    OctaneSubmission.py      # Submission dialog script
```

## Troubleshooting

### Common Issues

**"No render targets in this project"**
- Ensure your scene file contains at least one render target node

**Progress bar not updating**
- The plugin reports progress based on sample count
- Progress updates every 5% to avoid log spam

**EXR files not saving**
- Check that the output directory exists and is writable
- Verify the filename template contains `%f` for frame numbers

### Logs

Check the Deadline Worker log for detailed output:
- Sample progress: `Samples: X/Y (Z%)`
- Frame progress: `Rendering frame X of Y (Frame Z)`
- Frame completion: `Frame X completed`

## License

MIT License

This is an unofficial community modification of the Octane plugin for AWS Thinkbox Deadline.

**Attribution**: Based on the original Octane plugin included with AWS Thinkbox Deadline.

**Disclaimer**: This project is not affiliated with, endorsed by, or sponsored by AWS, Thinkbox, or OTOY Inc. Use at your own risk.

## Contributing

Contributions are welcome! Please submit issues and pull requests to the GitHub repository.

## Changelog

### Deadline-10.4_Octane-2026.1
- Initial release with Octane 2026.1 API support
- Added color space options (SRGB, LINEAR_SRGB, ACES, OCIO)
- Added premultiplied alpha support
- Added EXR compression options
- Real-time sample-based progress tracking
- Updated save functions to v3 API (`saveRenderPassesMultiExr3`, etc.)




