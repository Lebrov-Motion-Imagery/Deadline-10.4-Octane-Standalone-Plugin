----------------------------------------------------------------------------------------------------
-- Renders all the available render targets of the loaded project.
--
-- @author      Mark Basset, Octane dev team and others (updated for 2026.1 API)
-- @description Batch rendering for Octane 2026.1 (Deadline integration)
-- @version     0.51
-- @script-id   OctaneRender batch rendering

-- Common code for the render scripts. The script is shipped with Octane. 
require("octane_render_utils_lua")

----------------------------------------------------------------------------------------------------
-- Logging function that flushes output immediately for Deadline worker log capture
-- This ensures all print statements appear in the Deadline worker log
local function log(msg)
    print(msg)
    io.stdout:flush()
end

-- Global table with our settings. All global variables should be here to keep an overview.
local gSettings =
{
    -- absolute path of the current project
    projectPath             = octane.project.getCurrentProject(),
    -- the copied scene graph
    sceneGraph              = nil,
    -- list of render target nodes in the current project together with their enable state
    -- and export file format
    renderTargets           = {},
    fileFormat              = nil,
    -- absolute path to the output directory of the rendered images
    outputDirectory         = nil,
    -- true to override the max samples/px
    overrideMaxSamples      = false,
    -- max samples/px
    maxSamples              = 1000,
    -- filename template for the output files
    template                = "%n_%p_%f_%s.%e",
    -- true if the rendering was cancelled
    cancelled               = false,
    -- handle for the progress update function (takes value and text)
    progress                = nil,
    -- handle for the batch render function
    batchRender             = nil,
    -- handle for the window
    window                  = nil,
    -- set to true to show the debug outlines of the groups
    showGrpOutlines         = false,
    -- framerate
    fps                     = nil,
    -- delta value between 2 animation frames (1 / fps)
    dT                      = nil,
    -- frame number where we start rendering
    startFrame              = nil,
    -- frame number where we finish rendering (inclusive)
    endFrame                = nil,
    -- start time of the animation (s)
    startTime               = nil,
    -- end time of the animation (s)
    endTime                 = nil,
    -- true if we use custom file numbering
    useFileNumbering        = false,
    -- frame number from which we start number files
    fileNumber              = 0,
    -- skip existing files
    skipExisting            = false,
    -- save all enabled render passes
    saveAllPasses           = true,
    -- save the render passes as a layered exr
    saveMultiLayerExr       = false,
    -- save additional deep image output
    saveDeepImage           = false,
    -- openExr compression Type
    exrCompressionType      = octane.exrCompressionType.ZIP,
    -- openExr compression factor used for DWA
    exrCompressionLevel     = 45,
    -- TIFF compression type
    tiffCompressionType     = octane.tiffCompressionType.LZW,
    -- JPEG quality [1..100]
    jpegQuality             = 75,
    -- generate Composite Project for photoshop
    generateCompositePrj    = false,
    -- how many sub frames to render
    subFrameCount           = nil,
    -- saves denoiser output as main passes if enabled
    saveDeBeautyAsMain      = true,
    -- use premultiplied alpha when saving exr or tiff
    premultipliedAlpha      = true,
    -- image save format (string key like "PNG_8", "EXR_16", etc.)
    imageSaveFormat         = "PNG_8",
    -- color space (string key like "SRGB", "LINEAR_SRGB", etc.)
    colorSpace              = "LINEAR_SRGB",
    -- OCIO color space name
    ocioColorSpaceName      = "",
    -- OCIO look name
    ocioLookName            = "",
    -- force tone mapping
    forceToneMapping        = false,
    -- optional render target name to render (blank means use default behavior)
    selectedRenderTarget    = "",
}

-- Track last reported progress to avoid spamming the log
local lastReportedProgress = -1

local function trimString(value)
    if type(value) ~= "string" then
        return value
    end
    return value:gsub("^%s+", ""):gsub("%s+$", "")
end

-- Callback function for render progress reporting
-- The callback receives a result table with: samples, maxSamples, renderTime, samplesSec, etc.
local function createRenderCallback()
    return function(result)
        local callbackOk, callbackErr = pcall(function()
            if gSettings.cancelled then
                octane.render.callbackStop()
                return
            end

            -- result.samples = current samples rendered
            -- result.maxSamples = target max samples
            local currentSamples = result and tonumber(result.samples) or nil
            local maxSamples = result and tonumber(result.maxSamples) or nil
            if currentSamples and maxSamples and maxSamples > 0 then
                local progress = (currentSamples / maxSamples) * 100
                -- Only report progress every 5% to avoid log spam
                local progressStep = math.floor(progress / 5) * 5
                if progressStep > lastReportedProgress then
                    lastReportedProgress = progressStep
                    log(string.format("Samples: %.0f/%.0f (%.1f%%)", currentSamples, maxSamples, progress))
                end
            end
        end)
        if not callbackOk then
            -- Never let callback formatting/type issues terminate rendering.
            log("Warning: render callback failed: " .. tostring(callbackErr))
        end
    end
end

-- Reset progress tracking for new frame
local function resetProgressTracking()
    lastReportedProgress = -1
end


local function readAll(file)
    local f = assert(io.open(file, "rb"))
    local content = f:read("*all")
    f:close()
    lines = {}
    for s in content:gmatch("[^\r\n]+") do
        table.insert(lines, s)
    end
    return lines
end


local function findImageSaveFormat(name)
    if not name then return nil end
    
    -- First try direct lookup using Octane's enum (most reliable)
    if octane.imageSaveFormat[name] then
        return octane.imageSaveFormat[name]
    end
    
    -- Map legacy format names to new format names
    local legacyMap =
    {
        ["PNG (8-bit)"] = "PNG_8",
        ["PNG (16-bit)"] = "PNG_16",
        ["EXR (16-bit) Untonemapped"] = "EXR_16",
        ["EXR (16-bit) Tonemapped"] = "EXR_16",
        ["EXR (32-bit) Untonemapped"] = "EXR_32",
        ["EXR (32-bit) Tonemapped"] = "EXR_32",
    }
    
    local mappedName = legacyMap[name]
    if mappedName and octane.imageSaveFormat[mappedName] then
        return octane.imageSaveFormat[mappedName]
    end
    
    return nil
end


local function findColorSpace(name)
    if not name then return nil end
    
    -- Direct lookup using Octane's enum
    if octane.namedColorSpace[name] then
        return octane.namedColorSpace[name]
    end
    
    return nil
end


local function findCompressionType(name)
    local compressionTypes =
    {
        ["Uncompressed"]   = octane.exrCompressionType.NO_COMPRESSION,
        ["RLE (lossless)"] = octane.exrCompressionType.RLE,
        ["ZIPS (lossless)"]= octane.exrCompressionType.ZIPS,
        ["ZIP (lossless)"] = octane.exrCompressionType.ZIP,
        ["PIZ (lossless)"] = octane.exrCompressionType.PIZ,
        ["PXR24 (lossy)"]  = octane.exrCompressionType.PXR24,
        ["B44 (lossy)"]    = octane.exrCompressionType.B44,
        ["B44A (lossy)"]   = octane.exrCompressionType.B44A,
        ["DWAA (lossy)"]   = octane.exrCompressionType.DWAA,
        ["DWAB (lossy)"]   = octane.exrCompressionType.DWAB,
    }
    return compressionTypes[name]
end


local function loadFromDeadline(octane_lua_args)
    local delimiter = '='
    for _, arguement in ipairs(octane_lua_args) do
        local ele = ""..arguement..""
        local mid = string.find(ele, delimiter, 1)
        if mid then
            local key = ele:sub(1, mid-1)
            local val = ele:sub(mid+1, -1)
            if key == 'exrCompressionType' then
                gSettings[key] = findCompressionType(val)
            elseif tonumber(val) ~= nil then
                gSettings[key] = tonumber(val)
            elseif string.lower(val) == 'true' then
                gSettings[key] = true
            elseif string.lower(val) =='false' then
                gSettings[key] = false
            else
                gSettings[key] = val
            end
        end
    end
    
    -- Set overrideMaxSamples if maxSamples is provided and > 0
    if gSettings.maxSamples and gSettings.maxSamples > 0 then
        gSettings.overrideMaxSamples = true
    end
end


local function loadFromDisk()
    local storage = octane.storage.project
    for k, v in pairs(storage) do
        if k ~= "renderTargets" then 
            gSettings[k] = v
        end
    end
    if not storage.renderTargets then storage.renderTargets = {} end
end


local function storeOnDisk()
    local storage                   = octane.storage.project
    -- saving only if the user has changed the FPS setting.  Otherwise nil. This will allow us
    -- to load proper FPS from the scene for next time.
    if gSettings.fps ~= octane.project.getProjectSettings():getAttribute(octane.A_FRAMES_PER_SECOND) then
        storage.fps                 = gSettings.fps
    else 
        storage.fps                 = nil
    end
    storage.startTime               = gSettings.startTime
    storage.endTime                 = gSettings.endTime
    storage.overrideMaxSamples      = gSettings.overrideMaxSamples
    storage.maxSamples              = gSettings.maxSamples
    storage.useFileNumbering        = gSettings.useFileNumbering
    storage.fileNumber              = gSettings.fileNumber
    storage.fileTemplate            = gSettings.fileTemplate
    storage.outputDirectory         = gSettings.outputDirectory
    storage.template                = gSettings.template
    storage.skipExisting            = gSettings.skipExisting
    storage.saveAllPasses           = gSettings.saveAllPasses
    storage.saveMultiLayerExr       = gSettings.saveMultiLayerExr
    storage.saveDeepImage           = gSettings.saveDeepImage
    storage.exrCompressionType      = gSettings.exrCompressionType
    storage.generateCompositePrj    = gSettings.generateCompositePrj
    storage.subFrameCount           = gSettings.subFrameCount
    storage.saveDeBeautyAsMain      = gSettings.saveDeBeautyAsMain
    storage.premultipliedAlpha      = gSettings.premultipliedAlpha
    storage.colorSpace              = gSettings.colorSpace
    storage.ocioColorSpaceName      = gSettings.ocioColorSpaceName
    storage.ocioLookName            = gSettings.ocioLookName
    storage.forceToneMapping        = gSettings.forceToneMapping
    local rtSettings = {}
    for _, state in ipairs(gSettings.renderTargets) do
        rtSettings[state.node.name] =
        {
            render          = state.render,
            imageSaveFormat = state.imageSaveFormat
        }
    end
    storage.renderTargets = rtSettings
end


local function cancelRendering()
    gSettings.cancelled = true
    octane.render.callbackStop()
end


local function calcProgressUnit()
    local activeTargets = 0  
    for _, renderTarget in ipairs(gSettings.renderTargets) do
        if renderTarget.render then 
            activeTargets = activeTargets + 1
        end
    end
    return (1 / (activeTargets * (gSettings.endFrame - gSettings.startFrame + 1)))
            / gSettings.subFrameCount
end


-- Build the image export settings table based on the image format
local function getImageExportSettings(renderTarget)
    -- Try using octaneRenderUtils if available
    if octaneRenderUtils and octaneRenderUtils.composeImageExportSettings then
        local success, result = pcall(function()
            return octaneRenderUtils.composeImageExportSettings(renderTarget.imageSaveFormat, gSettings)
        end)
        if success and result then
            return result
        end
        log("Warning: octaneRenderUtils.composeImageExportSettings failed, using manual fallback")
    end
    
    -- Manual fallback: build the export settings table directly
    local exportSettings = {}
    
    -- Check if format is EXR
    local isExr = renderTarget.imageSaveFormat == octane.imageSaveFormat.EXR_16 or
                  renderTarget.imageSaveFormat == octane.imageSaveFormat.EXR_32
    
    if isExr then
        exportSettings.compressionType = gSettings.exrCompressionType or octane.exrCompressionType.ZIP
        exportSettings.compressionLevel = gSettings.exrCompressionLevel or 45
    end
    
    -- JPEG quality
    if renderTarget.imageSaveFormat == octane.imageSaveFormat.JPEG then
        exportSettings.quality = gSettings.jpegQuality or 75
    end
    
    return exportSettings
end


-- Build the color space info table for the save functions
local function buildColorSpaceInfo(renderTarget)
    -- Try using octaneRenderUtils if available
    if octaneRenderUtils and octaneRenderUtils.buildColorSpaceInfo then
        local success, result = pcall(function()
            return octaneRenderUtils.buildColorSpaceInfo(
                renderTarget.imageSaveFormat,
                renderTarget.colorSpace,
                renderTarget.ocioColorSpaceName,
                renderTarget.ocioLookName,
                renderTarget.forceToneMapping)
        end)
        if success and result then
            return result
        end
        log("Warning: octaneRenderUtils.buildColorSpaceInfo failed, using manual fallback")
    end
    
    -- Manual fallback: build the color space info table directly
    local colorSpaceInfo = {}
    
    -- Determine if we're using OCIO or a known color space
    if renderTarget.colorSpace == octane.namedColorSpace.OCIO and 
       renderTarget.ocioColorSpaceName and renderTarget.ocioColorSpaceName ~= "" then
        -- OCIO color space mode
        colorSpaceInfo.type = octane.outputColorSpaceType.OCIO_COLOR_SPACE
        colorSpaceInfo.ocioColorSpaceName = renderTarget.ocioColorSpaceName
        colorSpaceInfo.ocioLookName = renderTarget.ocioLookName or ""
        colorSpaceInfo.forceToneMapping = renderTarget.forceToneMapping or false
    else
        -- Known color space mode
        colorSpaceInfo.type = octane.outputColorSpaceType.KNOWN_COLOR_SPACE
        colorSpaceInfo.colorSpace = renderTarget.colorSpace or octane.namedColorSpace.LINEAR_SRGB
        colorSpaceInfo.forceToneMapping = renderTarget.forceToneMapping or false
    end
    
    return colorSpaceInfo
end


local function saveDeepImage(template, renderTargetIx, frameIx, subFrameIx, name, startFileNum)
    assert(template and renderTargetIx and frameIx and subFrameIx and name)

    if gSettings.saveDeepImage and octane.render.canSaveDeepImage() then
        local deepFilename = octaneRenderUtils.createFilename(template, renderTargetIx, frameIx + startFileNum, subFrameIx,
                name, octane.imageSaveFormat.EXR_32, "deep")
        local deepPath = octane.file.join(gSettings.outputDirectory, "deep_"..deepFilename)
        return octane.render.saveDeepImage(deepPath)
    end

    return true
end


local function runRenderWithLogging(renderTargetNode, frameIx, subFrameIx, modeName)
    local targetName = renderTargetNode and renderTargetNode.name or "<nil>"
    log(string.format(
        "Render start begin: frame=%d subFrame=%d target=%s mode=%s",
        frameIx, subFrameIx, tostring(targetName), tostring(modeName)))

    local renderOk, renderErr = pcall(function()
        octane.render.start
        {
            renderTargetNode = renderTargetNode,
            callback = createRenderCallback()
        }
    end)

    if not renderOk then
        error(string.format(
            "render.start failed for target '%s' at frame %d subFrame %d (%s): %s",
            tostring(targetName), frameIx, subFrameIx, tostring(modeName), tostring(renderErr)))
    end

    log(string.format(
        "Render start end: frame=%d subFrame=%d target=%s mode=%s",
        frameIx, subFrameIx, tostring(targetName), tostring(modeName)))
end


-- The batch rendering function. This will render each frame for each selected render target.
gSettings.batchRender = function()
    -- Interactive render region should not be active when running batch render script.
    local renderRegion = { active = false }
    octane.render.setRenderRegion(renderRegion)

    local lastFrameIx = octaneRenderUtils.calculateLastFrame(gSettings.sceneGraph, gSettings.fps)

    -- create the output directory if it does not exist yet
    if gSettings.outputDirectory 
       and octane.file.isAbsolute(gSettings.outputDirectory)
       and not octane.file.exists(gSettings.outputDirectory) then
        octane.file.createDirectory(gSettings.outputDirectory)
    end

    -- all render targets that need rendering
    local haveMultipleAovFiles = false
    local enabledRenderTargets = {}
    for _, renderTarget in ipairs(gSettings.renderTargets) do
        if renderTarget.render then
            enabledRenderTargets[#enabledRenderTargets + 1] = renderTarget
            if not haveMultipleAovFiles
                and gSettings.saveAllPasses
                and (not octaneRenderUtils.isExrImageSaveFormat(renderTarget.imageSaveFormat) or not gSettings.saveMultiLayerExr)
                and octaneRenderUtils.hasRenderPasses(renderTarget.node)
            then
                haveMultipleAovFiles = true
            end
        end
    end

    -- safety check before we start rendering.
    local errorMsg = octaneRenderUtils.verifyFilenameTemplate(
        gSettings.template,
        #enabledRenderTargets > 1,
        gSettings.startFrame ~= gSettings.endFrame,
        gSettings.subFrameCount > 1,
        haveMultipleAovFiles)
    if errorMsg ~= "" then
        log("Warning: " .. errorMsg)
    end

    -- get start file number
    local startFileNum = octaneRenderUtils.ternaryOperator(gSettings.useFileNumbering, gSettings.fileNumber, 0)

    -- for every frame:
    for frameIx = gSettings.startFrame, gSettings.endFrame do
        -- update the time in the scene
        gSettings.sceneGraph:updateTime(octaneRenderUtils.frameToTime(frameIx, gSettings.fps))
        
        -- for every render target:
        for renderTargetIx, renderTarget in ipairs(enabledRenderTargets) do

            -- override samples/px
            if gSettings.overrideMaxSamples then
                octaneRenderUtils.setMaxSamples(renderTarget.node, gSettings.maxSamples)
            end
 
            -- for every sub-frameIx:
            for subFrameIx = 1, gSettings.subFrameCount do
                if gSettings.subFrameCount > 1 then
                    octaneRenderUtils.setSubFrameInterval(renderTarget.node, subFrameIx,
                            gSettings.subFrameCount)
                end

                -- Log frame start for Deadline status and reset progress tracking
                local totalFrames = gSettings.endFrame - gSettings.startFrame + 1
                local currentFrameNum = frameIx - gSettings.startFrame + 1
                log(string.format("Rendering frame %d of %d (Frame %d)", currentFrameNum, totalFrames, frameIx))
                resetProgressTracking()

                -- 1) save out all the render passes
                if octaneRenderUtils.hasRenderPasses(renderTarget.node) and gSettings.saveAllPasses then
                    -- a) multi-layer EXR
                    if octaneRenderUtils.isExrImageSaveFormat(renderTarget.imageSaveFormat) and gSettings.saveMultiLayerExr then

                        -- create an output path for the image
                        local filename = octaneRenderUtils.createFilename(
                            gSettings.template,
                            renderTargetIx,
                            frameIx + startFileNum,
                            subFrameIx,
                            renderTarget.node.name,
                            renderTarget.imageSaveFormat,
                            "all")
                        local path
                        if gSettings.outputDirectory then
                            path = octane.file.join(gSettings.outputDirectory, filename)
                        else
                            path = string.format("%s [dry-run]", filename)
                        end

                        local skipFrame = gSettings.skipExisting 
                                          and gSettings.outputDirectory
                                          and octane.file.exists(path)

                        -- do the rendering of the image
                        if not skipFrame then
                            runRenderWithLogging(renderTarget.node, frameIx, subFrameIx, "multiLayerExr")
                        end

                        -- cancelled -> bail out and update progress bar
                        if gSettings.cancelled then
                            log("Canceled")
                            return 0
                        end

                        -- save out the multi layer EXR using the new API
                        if gSettings.outputDirectory and path and not skipFrame then
                            log(string.format(
                                "Save begin: frame=%d subFrame=%d target=%s mode=multiLayerExr path=%s",
                                frameIx, subFrameIx, tostring(renderTarget.node.name), tostring(path)))
                            log("Saving multi-layer EXR to: " .. path)
                            local useHalf = renderTarget.imageSaveFormat == octane.imageSaveFormat.EXR_16
                            log("  useHalf (EXR_16): " .. tostring(useHalf))
                            log("  premultipliedAlpha: " .. tostring(gSettings.premultipliedAlpha))
                            
                            local colorSpaceInfo = buildColorSpaceInfo(renderTarget)
                            local exportSettings = getImageExportSettings(renderTarget)
                            
                            -- Debug color space info
                            if colorSpaceInfo then
                                log("  colorSpaceInfo.type: " .. tostring(colorSpaceInfo.type))
                                log("  colorSpaceInfo.colorSpace: " .. tostring(colorSpaceInfo.colorSpace))
                                log("  colorSpaceInfo.forceToneMapping: " .. tostring(colorSpaceInfo.forceToneMapping))
                            else
                                log("  WARNING: colorSpaceInfo is nil!")
                            end
                            
                            -- Debug export settings
                            if exportSettings then
                                log("  exportSettings.compressionType: " .. tostring(exportSettings.compressionType))
                            else
                                log("  WARNING: exportSettings is nil!")
                            end
                            
                            local saveSuccess, saveResultOrError = pcall(function()
                                return octane.render.saveRenderPassesMultiExr3(
                                    path, nil,
                                    useHalf,
                                    colorSpaceInfo,
                                    gSettings.premultipliedAlpha,
                                    exportSettings, nil, false)
                            end)
                            
                            if not saveSuccess then
                                log("ERROR saving EXR: " .. tostring(saveResultOrError))
                                error("failed to save render passes in multi-layer EXR: " .. tostring(saveResultOrError))
                            end
                            
                            if saveResultOrError == false then
                                log("WARNING: saveRenderPassesMultiExr3 returned false")
                            end
                            
                            log("  Successfully saved EXR")
                            log(string.format(
                                "Save end: frame=%d subFrame=%d target=%s mode=multiLayerExr",
                                frameIx, subFrameIx, tostring(renderTarget.node.name)))

                            -- optionally save out the deep image
                            local ok = saveDeepImage(gSettings.template, renderTargetIx, frameIx,
                                    subFrameIx, renderTarget.node.name, startFileNum)
                            if not ok then
                                error("failed to save deep image")
                            end
                        end

                    -- b) each render pass as a discrete file
                    else
                        local renderPassExportObjs = octaneRenderUtils.createDiscreteRenderPassExports(
                            renderTarget.node,
                            gSettings.outputDirectory or "",
                            gSettings.template,
                            renderTargetIx,
                            frameIx + startFileNum,
                            subFrameIx,
                            renderTarget.imageSaveFormat)

                        local path
                        if gSettings.outputDirectory then
                            path = gSettings.outputDirectory
                        else
                            path = "[dry-run]"
                        end

                        -- check if at least 1 file doesn't exist
                        local skipFrame = gSettings.skipExisting
                        if skipFrame then
                            for _, exportObj in ipairs(renderPassExportObjs) do
                                local fullPath = octane.file.join(path, exportObj.exportName)
                                if not octane.file.exists(fullPath) then
                                    skipFrame = false
                                    break
                                end
                            end
                        end

                        -- do the rendering of the image
                        if not skipFrame then
                            runRenderWithLogging(renderTarget.node, frameIx, subFrameIx, "discretePasses")
                        end

                        -- cancelled -> bail out and update progress bar
                        if gSettings.cancelled then
                            log("Canceled")
                            return 0
                        end

                        -- save out the passes as discrete files using the new API
                        if gSettings.outputDirectory and path and not skipFrame then
                            log(string.format(
                                "Save begin: frame=%d subFrame=%d target=%s mode=discretePasses path=%s",
                                frameIx, subFrameIx, tostring(renderTarget.node.name), tostring(path)))
                            local premultipliedAlphaType
                            if octaneRenderUtils.supportsPremultipliedAlpha(renderTarget.imageSaveFormat) and gSettings.premultipliedAlpha then
                                premultipliedAlphaType = octane.premultipliedAlphaType.LINEARIZED
                            else
                                premultipliedAlphaType = octane.premultipliedAlphaType.NONE
                            end
                            local saveOk, saveResultOrError = pcall(function()
                                return octane.render.saveRenderPasses3(path, renderPassExportObjs,
                                        renderTarget.imageSaveFormat, buildColorSpaceInfo(renderTarget),
                                        premultipliedAlphaType, getImageExportSettings(renderTarget),
                                        false, nil)
                            end)
                            if not saveOk then
                                error("failed to save render passes to discrete files: " .. tostring(saveResultOrError))
                            end
                            local ok = saveResultOrError
                            if not ok then
                                error("failed to save render passes to discrete files")
                            end
                            log(string.format(
                                "Save end: frame=%d subFrame=%d target=%s mode=discretePasses",
                                frameIx, subFrameIx, tostring(renderTarget.node.name)))

                            -- optionally save out the deep image
                            ok = saveDeepImage(gSettings.template, renderTargetIx, frameIx,
                                    subFrameIx, renderTarget.node.name, startFileNum)
                            if not ok then
                                error("failed to save deep image")
                            end
                        end
                    end

                -- 2) only save out the beauty pass
                else
                    -- figure out whether we need to save the denoiser output or the main pass.
                    local renderPassId = octane.renderPassId.BEAUTY
                    if octaneRenderUtils.isDenoiserEnabled(renderTarget.node) and gSettings.saveDeBeautyAsMain  then
                        renderPassId = octane.renderPassId.BEAUTY_DENOISER_OUTPUT
                    end

                    -- create an output path for the image
                    local filename = octaneRenderUtils.createFilename(
                        gSettings.template,
                        renderTargetIx,
                        frameIx + startFileNum,
                        subFrameIx,
                        renderTarget.node.name,
                        renderTarget.imageSaveFormat,
                        octaneRenderUtils.getRenderPassName(renderPassId))

                    local path
                    if gSettings.outputDirectory then
                        path = octane.file.join(gSettings.outputDirectory, filename)
                    else
                        path = string.format("%s [dry-run]", filename)
                    end

                    local skipFrame = gSettings.skipExisting 
                                      and gSettings.outputDirectory
                                      and octane.file.exists(path)
                    -- do the rendering of the image
                    if not skipFrame then
                        runRenderWithLogging(renderTarget.node, frameIx, subFrameIx, "beautyPass")
                    end

                    -- cancelled -> bail out and update progress bar
                    if gSettings.cancelled then
                        log("Canceled")
                        return 0
                    end

                    -- save out the image using the new API
                    if gSettings.outputDirectory and path and not skipFrame then
                        log(string.format(
                            "Save begin: frame=%d subFrame=%d target=%s mode=beautyPass path=%s",
                            frameIx, subFrameIx, tostring(renderTarget.node.name), tostring(path)))
                        local premultipliedAlphaType
                        if octaneRenderUtils.supportsPremultipliedAlpha(renderTarget.imageSaveFormat) and gSettings.premultipliedAlpha then
                            premultipliedAlphaType = octane.premultipliedAlphaType.LINEARIZED
                        else
                            premultipliedAlphaType = octane.premultipliedAlphaType.NONE
                        end
                        local saveOk, saveResultOrError = pcall(function()
                            return octane.render.saveRenderPass3(renderPassId, path,
                                    renderTarget.imageSaveFormat, buildColorSpaceInfo(renderTarget),
                                    premultipliedAlphaType, getImageExportSettings(renderTarget), false)
                        end)
                        if not saveOk then
                            error("failed to save image: " .. tostring(saveResultOrError))
                        end
                        local ok = saveResultOrError
                        if not ok then
                            error("failed to save image")
                        end
                        log(string.format(
                            "Save end: frame=%d subFrame=%d target=%s mode=beautyPass",
                            frameIx, subFrameIx, tostring(renderTarget.node.name)))

                        -- optionally save out the deep image
                        ok = saveDeepImage(gSettings.template, renderTargetIx, frameIx,
                                subFrameIx, renderTarget.node.name, startFileNum)
                        if not ok then
                            error("failed to save deep image")
                        end
                    end
                end
            end
        end
        
        -- Frame completed - trigger Deadline progress update
        log(string.format("Frame %d completed", frameIx))
    end
end


---------------------------------------------------------------------------------------------------
-- Main script

-- create a copy of the original project
gSettings.sceneGraph = octane.nodegraph.createRootGraph("Project Copy")
gSettings.sceneGraph:copyFromGraph(octane.project.getSceneGraph())


octane_lua_args = readAll(arg[1])
loadFromDeadline(octane_lua_args)

-- find out the time settings for this scene (if not loaded from disk)
local interval          = gSettings.sceneGraph:getAnimationTimeSpan()
gSettings.fps           = gSettings.fps or octane.project.getProjectSettings():getAttribute(octane.A_FRAMES_PER_SECOND)
gSettings.dT            = 1 / gSettings.fps
gSettings.startTime     = gSettings.startTime or interval[1]
gSettings.endTime       = gSettings.endTime or interval[2]
-- When start and end time are loaded from disk, make sure they make sense for the current animation.
gSettings.startTime     = math.max(gSettings.startTime, interval[1])
gSettings.endTime       = math.min(gSettings.endTime, interval[2])
if not gSettings.startFrame and not gSettings.endFrame then
    gSettings.startFrame, gSettings.endFrame = octaneRenderUtils.timespanToFrames(gSettings.startTime, gSettings.endTime, gSettings.fps)
end
gSettings.subFrameCount = gSettings.subFrameCount or 1
gSettings.fileNumber    = gSettings.fileNumber or 0

-- fetch all the render target nodes
local renderTargetNodes = gSettings.sceneGraph:findNodes(octane.NT_RENDERTARGET, true)
-- if no render targets are found -> error out
if #renderTargetNodes == 0 then
    error("No render targets in this project.")
end

-- sort render target nodes by name
octaneRenderUtils.alphanumsort(renderTargetNodes, function(node) return node.name end)

-- Resolve the image save format from the settings
log("Resolving image format from: fileFormat=" .. tostring(gSettings.fileFormat) .. ", imageSaveFormat=" .. tostring(gSettings.imageSaveFormat))
local resolvedImageSaveFormat = findImageSaveFormat(gSettings.fileFormat) or findImageSaveFormat(gSettings.imageSaveFormat) or octane.imageSaveFormat.PNG_8
log("Resolved image format: " .. tostring(resolvedImageSaveFormat))

-- Resolve the color space from the settings
log("Resolving color space from: " .. tostring(gSettings.colorSpace))
local resolvedColorSpace = findColorSpace(gSettings.colorSpace) or octane.namedColorSpace.LINEAR_SRGB
log("Resolved color space: " .. tostring(resolvedColorSpace))

-- initialize the state for the render targets, and load settings per render target
for _, node in ipairs(renderTargetNodes) do
    -- defaults
    local state =
    {
        node              = node,
        render            = true,
        imageSaveFormat   = resolvedImageSaveFormat,
        colorSpace        = resolvedColorSpace,
        ocioColorSpaceName = gSettings.ocioColorSpaceName or "",
        ocioLookName       = gSettings.ocioLookName or "",
        forceToneMapping   = gSettings.forceToneMapping or false,
    }
    table.insert(gSettings.renderTargets, state)
end

-- Optional target filtering from Deadline plugin info.
-- This is used for both OCS and ORBX workflows and avoids reliance on CLI -t behavior.
local requestedRenderTarget = trimString(gSettings.selectedRenderTarget or "")
if requestedRenderTarget ~= "" then
    local matched = false
    local availableTargets = {}
    for _, state in ipairs(gSettings.renderTargets) do
        table.insert(availableTargets, state.node.name)
        if state.node.name == requestedRenderTarget then
            state.render = true
            matched = true
        else
            state.render = false
        end
    end

    if not matched then
        error(string.format(
            "Requested render target '%s' was not found. Available targets: %s",
            requestedRenderTarget,
            table.concat(availableTargets, ", ")))
    end

    log("Selected render target: " .. requestedRenderTarget)
end

log("Starting batch render with Octane 2026.1 API")
log("Output directory: " .. (gSettings.outputDirectory or "not set"))
log("Frame range: " .. gSettings.startFrame .. " - " .. gSettings.endFrame)
log("Save all passes: " .. tostring(gSettings.saveAllPasses))
log("Save multi-layer EXR: " .. tostring(gSettings.saveMultiLayerExr))
log("Premultiplied alpha: " .. tostring(gSettings.premultipliedAlpha))

gSettings.batchRender()
log("Completed")


