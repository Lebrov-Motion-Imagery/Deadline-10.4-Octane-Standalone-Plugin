----------------------------------------------------------------------------------------------------
-- Renders all the available render targets of the loaded project.
--
-- @author      Mark Basset, Octane dev team and others
-- @description Batch rendering for Octane.
-- @version     0.42
-- @script-id   OctaneRender batch rendering

-- Common code for the render scripts. The script is shipped with Octane. 
require("octane_render_utils_lua")

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
    -- generate Composite Project for photoshop
    generateCompositePrj    = false,
    -- how many sub frames to render
    subFrameCount           = nil,
    -- saves denoiser output as main passes if enabled
    saveDeBeautyAsMain      = true
}


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


local function findFileType(name)
    -- common extension for our image output types
    local fileExtensions =
    {
        ["PNG (8-bit)"] = octane.imageSaveType.PNG8,
        ["PNG (16-bit)"] = octane.imageSaveType.PNG16,
        ["EXR (16-bit) Untonemapped"] = octane.imageSaveType.EXR16,
        ["EXR (16-bit) Tonemapped"] = octane.imageSaveType.EXR16TONEMAPPED,
        ["EXR (32-bit) Untonemapped"] = octane.imageSaveType.EXR,
        ["EXR (32-bit) Tonemapped"] = octane.imageSaveType.EXRTONEMAPPED,
    }
    return fileExtensions[name]
end


local function findCompressionType(name)
    local compressionTypes =
    {
        ["Uncompressed"] = octane.exrCompressionType.NO_COMPRESSION,
        ["RLE (lossless)"] = octane.exrCompressionType.RLE,
        ["ZIPS (lossless)"] = octane.exrCompressionType.ZIPS,
        ["ZIP (lossless)"] = octane.exrCompressionType.ZIP,
        ["PIZ (lossless)"] = octane.exrCompressionType.PIZ,
        ["PXR24 (lossy)"] = octane.exrCompressionType.PXR24,
        ["B44 (lossy)"] = octane.exrCompressionType.B44,
        ["B44A (lossy)"] = octane.exrCompressionType.B44A,
        ["DWAA (lossy)"] = octane.exrCompressionType.DWAA,
        ["DWAB (lossy)"] = octane.exrCompressionType.DWAB,
    }
    return compressionTypes[name]
end


local function loadFromDeadline(octane_lua_args)
    local delimiter = '='
    for _, arguement in ipairs(octane_lua_args) do
        local ele = ""..arguement..""
        local mid = string.find(ele, delimiter, 1)
        local key = ele:sub(1, mid-1)
        local val =  ele:sub(mid+1, -1)
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
    local rtSettings = {}
    for _, state in ipairs(gSettings.renderTargets) do
        rtSettings[state.node.name] =
        {
            render   = state.render,
            fileType = state.fileType
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


local imageTypeNames =
{
  "PNG (8-bit)",
  "PNG (16-bit)",
  "EXR (16-bit) Untonemapped",
  "EXR (16-bit) Tonemapped",
  "EXR (32-bit) Untonemapped",
  "EXR (32-bit) Tonemapped"
}


local imageTypeIds =
{
    octane.imageSaveType.PNG8,
    octane.imageSaveType.PNG16,
    octane.imageSaveType.EXR16,
    octane.imageSaveType.EXR16TONEMAPPED,
    octane.imageSaveType.EXR,
    octane.imageSaveType.EXRTONEMAPPED,
}


local function imageTypeIdToIx(id)
    for i, v in ipairs(imageTypeIds) do
        if v == id then return i end
    end
end


-- Creates the user interface for the batch render script.
--
-- @return  
--      The created window, the list of input widgets 
local function createGui()
    local inputComponents = {}

    local row = 1

    -- Top-level grid (1 column).
    local layout = octane.gridlayout.create()
    layout:startSetup(-1, -1, 0, 0)
        -- Nested grid with an overview of all the render targets (3 columns).
        layout:startNestedGrid(1, row, 1, row, 0, 0)
        do
            local row = 1
            local tableChildren = {}

            layout:addSpan(octane.gui.create{ type=octane.componentType.TITLE_COMPONENT,
                    text="Render targets" }, 1, row, 3, row)
            row = row + 1

            for index, renderTarget in ipairs(gSettings.renderTargets) do
                local descrLbl = octane.gui.createLabel{ 
                        text=string.format("%5d: %s", index, renderTarget.node.name) }
                layout:add(descrLbl, 1, row)

                local renderChk = octane.gui.createCheckBox{
                    text="render", enable=true, checked=renderTarget.render }
                renderChk.callback = function(box)
                    renderTarget.render = box.checked
                end
                inputComponents[#inputComponents+1] = renderChk
                layout:add(renderChk, 2, row)

                local fileTypeCombo = octane.gui.createComboBox
                {
                    type  = octane.gui.componentType.COMBO_BOX,
                    items = imageTypeNames,
                    selectedIx = imageTypeIdToIx(renderTarget.fileType),
                    callback = function(combo)
                        renderTarget.fileType = imageTypeIds[combo.selectedIx]
                    end
                }
                inputComponents[#inputComponents+1] = fileTypeCombo
                layout:add(fileTypeCombo, 3, row)

                -- add components in the list
                table.insert(tableChildren, descrLbl)
                table.insert(tableChildren, renderChk)
                table.insert(tableChildren, fileTypeCombo)

                row = row + 1
            end

            -- Nested grid with the centered buttons.
            layout:startNestedGrid(1, row, 3, row)
                layout:addEmpty(1, 1)

                local renderAllButton = octane.gui.createButton
                {
                    text     = "Select all",
                    callback = function()
                        for _,renderTarget in ipairs(gSettings.renderTargets) do
                            renderTarget.render = true
                        end
                        for _,child in ipairs(tableChildren) do
                            if child.type == octane.gui.componentType.CHECK_BOX then
                                child.checked = true
                            end
                        end
                    end
                }
                layout:add(renderAllButton, 2, 1)
                layout:setColElasticity(2, 0)
                inputComponents[#inputComponents+1] = renderAllButton

                local renderNoneButton = octane.gui.createButton
                {
                    text = "Select none",
                    callback = function()
                        for _,renderTarget in ipairs(gSettings.renderTargets) do
                            renderTarget.render = false
                        end
                        for _,child in ipairs(tableChildren) do
                            if child.type == octane.gui.componentType.CHECK_BOX then
                                child.checked = false
                            end
                        end
                    end
                }
                layout:add(renderNoneButton, 3, 1)
                layout:setColElasticity(3, 0)
                inputComponents[#inputComponents+1] = renderNoneButton

                layout:addEmpty(4, 1)
            layout:endNestedGrid()

            layout:setElasticityForAllRows(0)
            layout:setColElasticity(2, 0)
        end
        layout:endNestedGrid()
        row = row + 1

        -- Grid with the animation settings (2 columns)
        layout:startNestedGrid(1, row, 1, row, 0)
        do
            local row = 1

            layout:addSpan(octane.gui.create{ type=octane.componentType.TITLE_COMPONENT,
                    text="Animation settings" }, 1, row, 2, row)
            row = row + 1

            local fpsLbl, fpsBox = octane.gui.createParameter(nil, "Framerate :", gSettings.fps, 1, 120, 0.1, false)
            fpsBox.enable = octaneRenderUtils.isAnimatedScene(gSettings.sceneGraph)
            layout:add(fpsLbl, 1, row)
            layout:add(fpsBox, 2, row)
            inputComponents[#inputComponents+1] = fpsBox
            row = row + 1

            startLbl, startBox = octane.gui.createParameter(nil,
                    string.format("Start %s:", octaneRenderUtils.displayTimeAsSeconds() and "time" or "frame"))
            startBox.enable = octaneRenderUtils.isAnimatedScene(gSettings.sceneGraph)
            layout:add(startLbl, 1, row)
            layout:add(startBox, 2, row)
            inputComponents[#inputComponents+1] = startBox
            row = row + 1

            local endLbl, endBox = octane.gui.createParameter(nil,
                    string.format("End %s:", octaneRenderUtils.displayTimeAsSeconds() and "time" or "frame"))
            endBox.enable = octaneRenderUtils.isAnimatedScene(gSettings.sceneGraph)
            layout:add(endLbl, 1, row)
            layout:add(endBox, 2, row)
            inputComponents[#inputComponents+1] = endBox
            row = row + 1

            subFrameLbl, subFrameBox = octane.gui.createParameter(nil,
                    "Subframes:", 1, 1, 10, 1, false)
            subFrameBox.enable = octaneRenderUtils.isAnimatedScene(gSettings.sceneGraph)
            layout:add(subFrameLbl, 1, row)
            layout:add(subFrameBox, 2, row)
            inputComponents[#inputComponents+1] = subFrameBox
            row = row + 1

            -- synchronize the animation sliders
            if octaneRenderUtils.displayTimeAsSeconds() then
                local interval = gSettings.sceneGraph:getAnimationTimeSpan()

                startBox:updateProperties{ step=gSettings.dT, minValue=interval[1],
                        maxValue=interval[2], value=gSettings.startTime }
                endBox:updateProperties{ step=gSettings.dT, minValue=interval[1],
                           maxValue=interval[2], value=gSettings.endTime }
            else
                local firstFrame, lastFrame = octaneRenderUtils.calculateFrameRange(gSettings.sceneGraph,
                        gSettings.fps)
                startBox:updateProperties{ step=1, minValue=firstFrame, maxValue=lastFrame,
                        value=gSettings.startFrame }
                endBox:updateProperties{ step=1, minValue=firstFrame, maxValue=lastFrame,
                       value=gSettings.endFrame }
            end

            -- box callbacks
            local function timeboxCallback(box)
                -- if we change
                if octaneRenderUtils.displayTimeAsSeconds() then
                    gSettings.startTime  = startBox.value 
                    gSettings.endTime    = endBox.value 
                    gSettings.startFrame, gSettings.endFrame = octaneRenderUtils.timespanToFrames(
                            gSettings.startTime, gSettings.endTime, gSettings.fps)
                else
                    gSettings.startFrame = startBox.value
                    gSettings.endFrame   = endBox.value
                    gSettings.startTime  = octaneRenderUtils.frameToTime(gSettings.startFrame, gSettings.fps)
                    gSettings.endTime    = octaneRenderUtils.frameToTime(gSettings.endFrame, gSettings.fps)
                end

                -- make sure start and end don't cross over
                if box == startBox then
                    gSettings.startFrame = math.min(gSettings.startFrame, gSettings.endFrame)
                    startBox.value = math.min(startBox.value, endBox.value)
                else
                    gSettings.endFrame = math.max(gSettings.startFrame, gSettings.endFrame)
                    endBox.value = math.max(startBox.value, endBox.value)
                end
            end

            local function fpsBoxCallback(slider)
                gSettings.fps = fpsBox.value
                gSettings.dT  = 1 / fpsBox.value
                gSettings.startFrame, gSettings.endFrame = octaneRenderUtils.timespanToFrames(
                        gSettings.startTime, gSettings.endTime, gSettings.fps)
                -- fps changed -> update time interval sliders range
                if octaneRenderUtils.displayTimeAsSeconds() then
                    startBox.step = gSettings.dT
                    endBox.step   = gSettings.dT
                else
                    local firstFrame, lastFrame = octaneRenderUtils.calculateFrameRange(gSettings.sceneGraph,
                            gSettings.fps)
                    startBox:updateProperties{
                        minValue = firstFrame,
                        maxValue = lastFrame,
                        value    = gSettings.startFrame }
                    endBox:updateProperties{
                        minValue   = firstFrame,
                        maxValue   = lastFrame,
                        value      = gSettings.endFrame }
                end
            end
            
            local function subFrameBoxCallback(slider)
                if slider == subFrameBox then
                    gSettings.subFrameCount = subFrameBox.value
                end
            end

            startBox.callback    = timeboxCallback 
            endBox.callback      = timeboxCallback 
            fpsBox.callback      = fpsBoxCallback
            subFrameBox.callback = subFrameBoxCallback

            layout:setElasticityForAllRows(0)
            layout:setColElasticity(1, 0)
        end
        layout:endNestedGrid()
        row = row + 1

        -- Nested grid with the output settings (2 columns).
        layout:startNestedGrid(1, row, 1, row, 0)
        do
            local row = 1

            layout:addSpan(octane.gui.create{ type=octane.componentType.TITLE_COMPONENT,
                    text="Output settings" }, 1, row, 2, row)
            row = row + 1

            local fileNbrLbl = octane.gui.createLabel{ text="File numbering:",
                    enable=octaneRenderUtils.isAnimatedScene(gSettings.sceneGraph) }
            layout:add(fileNbrLbl, 1, row)
            layout:startNestedGrid(2, row, 2, row, 0, 0, 0, 0)
            do
                local fileNbrCheck=octane.gui.createCheckBox{ text="Start file numbering at:",
                        checked=gSettings.useFileNumbering,
                        enable=octaneRenderUtils.isAnimatedScene(gSettings.sceneGraph), }
                fileNbrCheck.callback = function(me)
                    gSettings.useFileNumbering = me.checked
                    fileNbrBox.enable          = me.checked
                end
                layout:add(fileNbrCheck, 1, 1)
                inputComponents[#inputComponents+1] = fileNbrCheck

                fileNbrBox=octane.gui.createNumericBox{ minValue=0, maxValue=10000,
                        value=gSettings.fileNumber,
                        enable=octaneRenderUtils.isAnimatedScene(gSettings.sceneGraph) and gSettings.useFileNumbering }
                fileNbrBox.callback = function(me)
                    gSettings.fileNumber = me.value
                end
                layout:add(fileNbrBox, 2, 1)
                inputComponents[#inputComponents+1] = fileNbrBox
            end
            layout:endNestedGrid()
            row = row + 1

            local overrideLbl = octane.gui.createLabel{ text="Override samples/px:" }
            layout:add(overrideLbl, 1, row)
            layout:startNestedGrid(2, row, 2, row, 0, 0, 0, 0)
            do
                local overrideChk = octane.gui.createCheckBox
                {
                    text     = "Samples/px:",
                    checked  = false,
                    tooltip  = "Override max samples in the kernel node",
                    checked  = gSettings.overrideMaxSamples,
                    callback = function(box)
                        if box.checked then
                            maxSamplesBox.enable         = true
                            gSettings.overrideMaxSamples = true
                            gSettings.maxSamples         = maxSamplesBox.value
                        else
                            maxSamplesBox.enable         = false
                            gSettings.overrideMaxSamples = false
                        end
                    end
                }
                layout:add(overrideChk, 1, 1)
                inputComponents[#inputComponents+1] = overrideChk

                maxSamplesBox = octane.gui.createNumericBox
                {
                    value       = gSettings.maxSamples,
                    minValue    = 1,
                    maxValue    = 256000,
                    step        = 1,
                    logarithmic = true,
                    enable      = gSettings.overrideMaxSamples,
                    callback    = function(me)
                        gSettings.maxSamples = me.value
                    end
                }
                layout:add(maxSamplesBox, 2, 1)
                inputComponents[#inputComponents+1] = maxSamplesBox
                
                layout:setColElasticity(1, 0)
            end
            layout:endNestedGrid()
            row = row + 1

            local templateLbl=octane.gui.createLabel{ text="Filename template:" }
            layout:add(templateLbl, 1, row)
            local templateEditor = octane.gui.createTextEditor
            {
                text     = gSettings.template,
                height   = 20,
                tooltip  = 
        -- weirdly indented tooltip docstring
        [[Template parameters:
            %i render target index
            %n render target node name
            %e file extension
            %t timestamp
            %f frame number (always prefixed with 0s)
            %s sub frame number
            %p render pass name
        ]],
                callback = function(editor)
                    gSettings.template = editor.text
                end
            }
            layout:add(templateEditor, 2, row)
            inputComponents[#inputComponents+1] = templateEditor
            row = row + 1

            -- create a button to browse for an output folder
            local outputButton = octane.gui.createButton
            {
                text    = "Output folder...", 
                tooltip = "Specify the folder to receive the rendered output files."
            }
            layout:add(outputButton, 1, row)
            inputComponents[#inputComponents+1] = outputButton

            -- create an editor that will show the chosen file path
            local txtEditorDirectory = octane.gui.createTextEditor
            { 
                text = gSettings.outputDirectory or "",
                height = 20,
                callback = function(me)
                    gSettings.outputDirectory = me.text
                end
            }
            layout:add(txtEditorDirectory, 2, row)
            inputComponents[#inputComponents+1] = txtEditorDirectory
            row = row + 1

            local skipExistingChk = octane.gui.createCheckBox
            { 
                text     = "Skip already existing files",
                checked  = gSettings.skipExisting,
                callback = function(me) 
                    gSettings.skipExisting = me.checked
                end
            }
            layout:addSpan(skipExistingChk, 1, row, 2, row)
            inputComponents[#inputComponents+1] = skipExistingChk
            row = row + 1

            local renderPassesChk = octane.gui.createCheckBox
            { 
                text     = "Save all enabled passes",
                checked  = gSettings.saveAllPasses,
                callback = function(me)
                    generateCompositePrjChk.enable = me.checked
                    saveDeBeautyAsMainChk.enable = not me.checked
                    gSettings.saveAllPasses = me.checked
                end
            }
            layout:addSpan(renderPassesChk, 1, row, 2, row)
            inputComponents[#inputComponents+1] = renderPassesChk
            row = row + 1
            
            saveDeBeautyAsMainChk = octane.gui.createCheckBox
            { 
                text     = "Save denoised main pass if available",
                checked  = gSettings.saveDeBeautyAsMain,
                enable   = not gSettings.saveAllPasses,
                callback = function(me) 
                    gSettings.saveDeBeautyAsMain = me.checked
                end
            }
            layout:addSpan(saveDeBeautyAsMainChk, 1, row, 2, row)
            inputComponents[#inputComponents+1] = saveDeBeautyAsMainChk
            row = row + 1

            local multiLayerExrChk = octane.gui.createCheckBox
            { 
                text     = "Save layered EXR (only when saved as EXR)",
                checked  = gSettings.saveMultiLayerExr,
                callback = function(me)
                    gSettings.saveMultiLayerExr = me.checked
                end
            }
            layout:addSpan(multiLayerExrChk, 1, row, 2, row)
            inputComponents[#inputComponents+1] = multiLayerExrChk
            row = row + 1

            local exrCompressionLbl = octane.gui.createLabel{ text="EXR compression type:",
                    width=120 }
            layout:add(exrCompressionLbl, 1, row)
            local exrCompressionCombo = octane.gui.createComboBox
            {
                type  = octane.gui.componentType.COMBO_BOX,
                items =
                { 
                    "Uncompressed",
                    "RLE (lossless)",
                    "ZIPS (lossless)",
                    "ZIP (lossless)",
                    "PIZ (lossless)",
                    "PXR24 (lossy)",
                    "B44 (lossy)",
                    "B44A (lossy)",
                    "DWAA (lossy)",
                    "DWAB (lossy)",
                },
                selectedIx = gSettings.exrCompressionType,
                callback   = function(combo)
                    local compressionTypes =
                    {
                        octane.exrCompressionType.NO_COMPRESSION,
                        octane.exrCompressionType.RLE,
                        octane.exrCompressionType.ZIPS,
                        octane.exrCompressionType.ZIP,
                        octane.exrCompressionType.PIZ,
                        octane.exrCompressionType.PXR24,
                        octane.exrCompressionType.B44,
                        octane.exrCompressionType.B44A,
                        octane.exrCompressionType.DWAA,
                        octane.exrCompressionType.DWAB,
                    }
                    gSettings.exrCompressionType = compressionTypes[combo.selectedIx]
                end
            }
            layout:add(exrCompressionCombo, 2, row)
            inputComponents[#inputComponents+1] = exrCompressionCombo
            row = row + 1

            local deepImageCheck = octane.gui.createCheckBox
            { 
                text     = "Save additional deep image",
                checked  = gSettings.saveDeepImage,
                width    = txtEditorDirectory.width,
                tooltip  = "Save a deep image (additional to the other saved images). Only works when deep image output is enabled in the kernel.",
                callback = function(me)
                    gSettings.saveDeepImage = me.checked
                end
            }
            layout:addSpan(deepImageCheck, 1, row, 2, row)
            inputComponents[#inputComponents+1] = deepImageCheck
            row = row + 1

            generateCompositePrjChk = octane.gui.createCheckBox
            { 
                text     = "Generate composite project file",
                checked  = gSettings.generateCompositePrj,
                callback = function(me)
                    gSettings.generateCompositePrj= me.checked
                end
            }
            layout:addSpan(generateCompositePrjChk, 1, row, 2, row)
            inputComponents[#inputComponents+1] = generateCompositePrjChk

            -- callback function for the output button
            outputButton.callback = function()
                -- ask the user for an output directory for the results
                local ret = octane.gui.showDialog
                {
                    type            = octane.gui.dialogType.FILE_DIALOG,
                    title           = "Select output directory for the render results",
                    path            = octane.file.getParentDirectory(gSettings.projectPath),
                    browseDirectory = true,
                    save            = false,
                }
                if not ret.result or ret.result == "" then
                    gSettings.outputDirectory = nil  
                else 
                    gSettings.outputDirectory = ret.result
                    txtEditorDirectory.text = gSettings.outputDirectory
                end
            end

            layout:setColElasticity(1, 0)
        end
        layout:endNestedGrid()
        row = row + 1

        local progressBar = octane.gui.createProgressBar{ text = "Render progress" }
        -- the global progress function needs to update the progress bar
        gSettings.progress = function(progress, text)
            progressBar.progress = progress
            progressBar.text     = text
        end
        layout:add(progressBar, 1, row)
        row = row + 1

        layout:startNestedGrid(1, row, 1, row)
        do
            layout:addEmpty(1, 1)

            startButton = octane.gui.createButton
            {
                text    = "Start",
                tooltip = "Start batch processing.",
                callback = function()
                    -- we will hang in this callback until rendering is finished, the only way to stay
                    -- responsive is via the render callback
                    -- clear cancel flag
                    gSettings.cancelled = false
                    -- disable all but the cancel button
                    for _, w in ipairs(inputWidgets) do w.enable = false end
                    cancelButton.enable = true
                    -- do the work (blocks)
                    gSettings.batchRender()
                    -- enable all but the cancel button
                    for _, w in ipairs(inputWidgets) do w.enable = true end
                    saveDeBeautyAsMainChk.enable = not gSettings.saveAllPasses
                    generateCompositePrjChk.enable = gSettings.saveAllPasses
                    cancelButton.enable = false
                    if not gSettings.cancelled then
                        gSettings.progress(101, "Finished")
                    end
                end
            }
            layout:add(startButton, 2, 1)
            inputComponents[#inputComponents+1] = startButton

            cancelButton = octane.gui.createButton
            {
                text     = "Cancel",
                tooltip  = "Cancel batch processing.",
                enable   = false,
                callback = function() cancelRendering() end
            }
            layout:add(cancelButton, 3, 1)
            inputComponents[#inputComponents+1] = cancelButton

            layout:addEmpty(4, 1)

            layout:setElasticityForAllRows(0)
            layout:setColElasticity(2, 0)
            layout:setColElasticity(3, 0)
        end
        layout:endNestedGrid()

        layout:setElasticityForAllRows(0)
    layout:endSetup()

    local window = octane.gui.create
    { 
        type       = octane.gui.componentType.WINDOW,
        text       = "Batch rendering",
        gridLayout = layout,
        width      = math.max(layout.width, 640),
        height     = math.min(layout.height, 800),
        resizable  = true,
        callback   = function()
            -- cancel rendering on close
            cancelRendering()
        end
    }

    return window, inputComponents
end


local function saveDeepImage(template, renderTargetIx, frameIx, subFrameIx, name, startFileNum)
    assert(template and renderTargetIx and frameIx and subFrameIx and name)

    if gSettings.saveDeepImage and octane.render.canSaveDeepImage() then
        local deepFilename = octaneRenderUtils.createFilename(template, renderTargetIx, frameIx + startFileNum, subFrameIx,
                name, octane.imageSaveType.EXR, "deep")
        local deepPath = octane.file.join(gSettings.outputDirectory, "deep_"..deepFilename)
        return octane.render.saveDeepImage(deepPath)
    end

    return true
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
    local enabledRenderTargets = {}
    for _, renderTarget in ipairs(gSettings.renderTargets) do
        if renderTarget.render then
            enabledRenderTargets[#enabledRenderTargets + 1] = renderTarget
        end
    end
    
    -- saftey check before we start rendering.
    for renderTargetIx, renderTarget in ipairs(enabledRenderTargets) do
        if octaneRenderUtils.hasRenderPasses(renderTarget.node) and gSettings.saveAllPasses then
            local isExrFileType = (renderTarget.fileType ~= octane.imageSaveType.PNG8 and 
                    renderTarget.fileType ~= octane.imageSaveType.PNG16)
            
            if isExrFileType == false or gSettings.saveMultiLayerExr == false then
                if not string.match(gSettings.template, "%%p") then
                    octane.gui.showError(
                        "Save all render passes option is enabled for a render target, but %p (render pass name)"..
                        " is missing in the filename template. The file names for all the passes will be same "..
                        " and will be overwriting each other",
                        "Warning")
                end
            end
        end
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

                -- 1) save out all the render passes
                if octaneRenderUtils.hasRenderPasses(renderTarget.node) and gSettings.saveAllPasses then
                    -- a) multi-layer EXR
                    local isExrFileType = (renderTarget.fileType ~= octane.imageSaveType.PNG8 and 
                            renderTarget.fileType ~= octane.imageSaveType.PNG16)

                    if isExrFileType and gSettings.saveMultiLayerExr then

                        local renderPassExportObjs = octaneRenderUtils.createMultiLayerExrExports(
                            renderTarget.node)

                        -- create an output path for the image
                        local filename = octaneRenderUtils.createFilename(gSettings.template, renderTargetIx,
                                frameIx + startFileNum, subFrameIx, renderTarget.node.name, renderTarget.fileType,
                                "all")
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
                            octane.render.start
                            { 
                                renderTargetNode = renderTarget.node,
                                callback         = function()
                                    if gSettings.cancelled then
                                        octane.render.callbackStop()
                                    end
                                end
                            }
                        end

                        local isToneMap = (renderTarget.fileType == octane.imageSaveType.EXRTONEMAPPED or 
                                renderTarget.fileType == octane.imageSaveType.EXR16TONEMAPPED)
                                
                        local saveExrIn16Bit = (renderTarget.fileType == octane.imageSaveType.EXR16 or 
                                renderTarget.fileType == octane.imageSaveType.EXR16TONEMAPPED)

                        -- save out the multi layer EXR
                        if gSettings.outputDirectory and path and not skipFrame then
                            if not octane.render.saveRenderPassesMultiExr(
                                    path, renderPassExportObjs, gSettings.exrCompressionType,
                                    saveExrIn16Bit, nil, false, gSettings.generateCompositePrj, isToneMap) then
                                error("failed to save render passes in multi-layer EXR");
                            end

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
                                renderTarget.node, gSettings.outputDirectory or "",
                                gSettings.template, renderTargetIx, frameIx + startFileNum, subFrameIx,
                                renderTarget.fileType)

                        local path
                        if gSettings.outputDirectory then
                            path = gSettings.outputDirectory
                        else
                            path = "[dry-run]"
                        end

                        -- check if at least 1 file doesn't exits
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
                            octane.render.start
                            { 
                                renderTargetNode = renderTarget.node,
                                callback         = function()
                                    if gSettings.cancelled then
                                        octane.render.callbackStop()
                                    end
                                end
                            }
                        end

                        --composite fileName will be either nil or same as rendered image file name 
                        local compositeFileName = nil
                        if gSettings.generateCompositePrj then
                            compositeFileName = octaneRenderUtils.createFilename(gSettings.template,
                                    renderTargetIx, frameIx + startFileNum, subFrameIx, renderTarget.node.name,
                                    renderTarget.fileType, "all")
                            compositeFileName = octane.file.join(path, compositeFileName)
                        end
                        
                        -- save out the passes as discrete files
                        if gSettings.outputDirectory and path and not skipFrame then
                            local ok = octane.render.saveRenderPasses(path, renderPassExportObjs,
                                    renderTarget.fileType, false, compositeFileName,
                                    nil, gSettings.exrCompressionType)
                            if not ok then
                                error("failed to save render passes to discrete files")
                            end

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
                    local filename = octaneRenderUtils.createFilename(gSettings.template, renderTargetIx,
                            frameIx + startFileNum, subFrameIx, renderTarget.node.name, renderTarget.fileType,
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
                        octane.render.start
                        { 
                            renderTargetNode = renderTarget.node,
                            callback         = function()
                                if gSettings.cancelled then
                                    octane.render.callbackStop()
                                end
                            end
                        }
                    end

                    -- save out the image
                    if gSettings.outputDirectory and path and not skipFrame then
                        local ok = octane.render.saveRenderPass(renderPassId, path, renderTarget.fileType, false,
                                gSettings.exrCompressionType, false)
                        if not ok then
                            error("failed to save image")
                        end

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

-- initialize the state for the render targets, and load settings per render target
for _, node in ipairs(renderTargetNodes) do
    -- defaults
    local state =
    {
        node     = node,
        render   = true,
        fileType = findFileType(gSettings.fileFormat),
    }
    table.insert(gSettings.renderTargets, state)
end
gSettings.batchRender()
-- list of widgets that need to be enabled/disabled when rendering starts
inputWidgets = {}
