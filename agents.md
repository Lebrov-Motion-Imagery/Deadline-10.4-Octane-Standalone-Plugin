# AI Agent Guidelines - Deadline Octane Plugin

## Project Structure

```
├── plugins/
│   └── Octane/
│       ├── Octane.py              # Main plugin (process management, stdout handlers)
│       ├── Octane.options         # UI configuration for job settings
│       ├── Octane.param           # System config (executable paths)
│       ├── DeadlineOctane4.lua    # Render script for Octane 4/2019
│       ├── DeadlineOctane2026.1.lua  # Render script for Octane 2026.1
│       └── Octane.ico             # Plugin icon
├── scripts/
│   └── Submission/
│       └── OctaneSubmission.py    # Job submission dialog
├── README.md                      # Installation instructions
└── LICENSE                        # MIT License
```

## Key Files Reference

### `Octane.py`
- `RenderExecutable()` - Returns path to Octane executable
- `RenderArgument()` - Builds command-line arguments including Lua script path
- `PreRenderTasks()` - Initializes progress tracking variables
- `HandleSampleProgress()` - Parses "Samples: X/Y (Z%)" from stdout
- `HandleFrameComplete()` - Parses "Frame X completed" from stdout

### `DeadlineOctane2026.1.lua`
- `gSettings` table - All render parameters from command line
- `batchRender()` - Main render loop
- `saveRenderTarget()` - Handles different save modes (single, multi-layer, passes)
- `createRenderCallback()` - Progress reporting during render
- `log(msg)` - Output to Deadline worker log with flush

### `Octane.options`
- Defines UI controls shown in Deadline Monitor
- Each option maps to a plugin info entry
- Supports conditional visibility via `Global#` prefix

## Octane 2026.1 API Notes

### Image Save Formats
```lua
octane.imageSaveFormat.PNG_8   -- 0
octane.imageSaveFormat.PNG_16  -- 1
octane.imageSaveFormat.EXR_16  -- 2
octane.imageSaveFormat.EXR_32  -- 3
octane.imageSaveFormat.TIFF_8  -- 4
octane.imageSaveFormat.TIFF_16 -- 5
octane.imageSaveFormat.JPEG    -- 6
```

### Color Spaces
```lua
octane.namedColorSpace.LINEAR_SRGB  -- 2
octane.namedColorSpace.SRGB         -- 3
octane.namedColorSpace.ACESCG       -- 4
```

### Save Functions (v3 API)
```lua
octane.render.saveRenderPass3(renderTarget, passId, filename, imageSettings)
octane.render.saveRenderPasses3(renderTarget, directoryPath, imageSettings)
octane.render.saveRenderPassesMultiExr3(renderTarget, filename, imageSettings)
```

### Image Settings Structure
```lua
{
    imageSaveFormat = octane.imageSaveFormat.EXR_16,
    colorSpaceInfo = { type, colorSpace, ocioColorSpaceName, ocioLookName, forceToneMapping },
    premultipliedAlphaType = octane.premultipliedAlphaType.KEEP/ADD/REMOVE,
    formatOptions = { exrCompressionType, exrCompressionLevel, jpegQuality, ... }
}
```

## Common Modifications

### Add New UI Option
1. `Octane.options` - Add control definition
2. `OctaneSubmission.py` - Add widget and sticky settings
3. `Octane.py` - Read with `GetPluginInfoEntry()`
4. Lua script - Parse from command line and use

### Update Progress Reporting
- Lua: Use `log(string.format(...))` with specific patterns
- Python: Add `AddStdoutHandlerCallback(regex)` to match pattern
- Handler method: Call `SetProgress()` and `SetStatusMessage()`

### Support New Octane Version
1. Copy latest Lua script as template
2. Review Octane changelog for API changes
3. Update `octane.*` calls to new API
4. Add version to options/param/submission files



