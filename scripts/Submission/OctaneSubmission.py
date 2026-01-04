from __future__ import absolute_import
import re
import imp
import os
import traceback
from typing import Any, List

from System import *
from System.Collections.Specialized import StringCollection
from System.IO import Path, StreamWriter, File, Directory
from System.Text import Encoding

from Deadline.Scripting import RepositoryUtils, FrameUtils, ClientUtils, PathUtils, StringUtils
from DeadlineUI.Controls.Scripting.DeadlineScriptDialog import DeadlineScriptDialog

from ThinkboxUI.Controls.Scripting.RangeControl import RangeControl
from ThinkboxUI.Controls.Scripting.FileBrowserControl import FileBrowserControl
from ThinkboxUI.Controls.Scripting.CheckBoxControl import CheckBoxControl
from ThinkboxUI.Controls.Scripting.ComboControl import ComboControl
from ThinkboxUI.Controls.Scripting.ButtonControl import ButtonControl

try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET  # type: ignore

# For Integration UI
imp.load_source('IntegrationUI',
                RepositoryUtils.GetRepositoryFilePath("submission/Integration/Main/IntegrationUI.py", True))
import IntegrationUI

########################################################################
## Globals
########################################################################
scriptDialog = None  # type: DeadlineScriptDialog
settings = None
integration_dialog = None
ProjectManagementOptions = ["Shotgun", "FTrack"]
DraftRequested = False
isOrbxFile = False
formatOptionsV3 = ["png8", "png16", "exr", "exrtonemapped"]
formatOptionsV4 = ["PNG (8-bit)", "PNG (16-bit)", "EXR (16-bit) Untonemapped", "EXR (16-bit) Tonemapped",
                   "EXR (32-bit) Untonemapped", "EXR (32-bit) Tonemapped"]
# Format options for Octane 2020+ (new API naming convention)
formatOptionsV2020 = ["PNG_8", "PNG_16", "EXR_16", "EXR_32", "TIFF_8", "TIFF_16", "JPEG"]
selectedFormatOptionsIndexV3 = 2
selectedFormatOptionsIndexV4 = 2
selectedFormatOptionsIndexV2020 = 2  # Default to EXR_16

# Color space options for Octane 2020+
colorSpaceOptions = ["SRGB", "LINEAR_SRGB", "ACES2065_1", "ACESCG", "OCIO"]
defaultColorSpaceIndex = 1  # LINEAR_SRGB

# Compression options are not available for Octane V3 and below
compressionOptions = ["Uncompressed", "RLE (lossless)", "ZIPS (lossless)", "ZIP (lossless)", "PIZ (lossless)",
                      "PXR24 (lossy)", "B44 (lossy)", "B44A (lossy)", "DWAA (lossy)", "DWAB (lossy)"]
defaultCompressionIndex = 2
currentVersion = 1

########################################################################
## Main Function Called By Deadline
########################################################################
def __main__(*args):
    # type: (*Any) -> None
    global scriptDialog
    global settings
    global ProjectManagementOptions
    global DraftRequested
    global integration_dialog
    global currentVersion

    scriptDialog = DeadlineScriptDialog()
    scriptDialog.SetTitle("Submit Octane Job To Deadline")
    scriptDialog.SetIcon(scriptDialog.GetIcon('Octane'))

    scriptDialog.AddTabControl("Tabs", 0, 0)

    scriptDialog.AddTabPage("Job Options")
    scriptDialog.AddGrid()
    scriptDialog.AddControlToGrid("Separator1", "SeparatorControl", "Job Description", 0, 0, colSpan=2)

    scriptDialog.AddControlToGrid("NameLabel", "LabelControl", "Job Name", 1, 0,
                                  "The name of your job. This is optional, and if left blank, it will default to 'Untitled'.",
                                  False)
    scriptDialog.AddControlToGrid("NameBox", "TextControl", "Untitled", 1, 1)

    scriptDialog.AddControlToGrid("CommentLabel", "LabelControl", "Comment", 2, 0,
                                  "A simple description of your job. This is optional and can be left blank.", False)
    scriptDialog.AddControlToGrid("CommentBox", "TextControl", "", 2, 1)

    scriptDialog.AddControlToGrid("DepartmentLabel", "LabelControl", "Department", 3, 0,
                                  "The department you belong to. This is optional and can be left blank.", False)
    scriptDialog.AddControlToGrid("DepartmentBox", "TextControl", "", 3, 1)
    scriptDialog.EndGrid()

    scriptDialog.AddGrid()
    scriptDialog.AddControlToGrid("Separator2", "SeparatorControl", "Job Options", 0, 0, colSpan=3)

    scriptDialog.AddControlToGrid("PoolLabel", "LabelControl", "Pool", 1, 0,
                                  "The pool that your job will be submitted to.", False)
    scriptDialog.AddControlToGrid("PoolBox", "PoolComboControl", "none", 1, 1)

    scriptDialog.AddControlToGrid("SecondaryPoolLabel", "LabelControl", "Secondary Pool", 2, 0,
                                  "The secondary pool lets you specify a Pool to use if the primary Pool does not have any available Workers.",
                                  False)
    scriptDialog.AddControlToGrid("SecondaryPoolBox", "SecondaryPoolComboControl", "", 2, 1)

    scriptDialog.AddControlToGrid("GroupLabel", "LabelControl", "Group", 3, 0,
                                  "The group that your job will be submitted to.", False)
    scriptDialog.AddControlToGrid("GroupBox", "GroupComboControl", "none", 3, 1)

    scriptDialog.AddControlToGrid("PriorityLabel", "LabelControl", "Priority", 4, 0,
                                  "A job can have a numeric priority ranging from 0 to 100, where 0 is the lowest priority and 100 is the highest priority.",
                                  False)
    scriptDialog.AddRangeControlToGrid("PriorityBox", "RangeControl", RepositoryUtils.GetMaximumPriority() // 2, 0,
                                       RepositoryUtils.GetMaximumPriority(), 0, 1, 4, 1)

    scriptDialog.AddControlToGrid("TaskTimeoutLabel", "LabelControl", "Task Timeout", 5, 0,
                                  "The number of minutes a Worker has to render a task for this job before it requeues it. Specify 0 for no limit.",
                                  False)
    scriptDialog.AddRangeControlToGrid("TaskTimeoutBox", "RangeControl", 0, 0, 1000000, 0, 1, 5, 1)
    scriptDialog.AddSelectionControlToGrid("AutoTimeoutBox", "CheckBoxControl", False, "Enable Auto Task Timeout", 5, 2,
                                           "If the Auto Task Timeout is properly configured in the Repository Options, then enabling this will allow a task timeout to be automatically calculated based on the render times of previous frames for the job. ")

    scriptDialog.AddControlToGrid("ConcurrentTasksLabel", "LabelControl", "Concurrent Tasks", 6, 0,
                                  "The number of tasks that can render concurrently on a single Worker. This is useful if the rendering application only uses one thread to render and your Workers have multiple CPUs.",
                                  False)
    scriptDialog.AddRangeControlToGrid("ConcurrentTasksBox", "RangeControl", 1, 1, 16, 0, 1, 6, 1)
    scriptDialog.AddSelectionControlToGrid("LimitConcurrentTasksBox", "CheckBoxControl", True,
                                           "Limit Tasks To Worker's Task Limit", 6, 2,
                                           "If you limit the tasks to a Worker's task limit, then by default, the Worker won't dequeue more tasks then it has CPUs. This task limit can be overridden for individual Workers by an administrator.")

    scriptDialog.AddControlToGrid("MachineLimitLabel", "LabelControl", "Machine Limit", 7, 0, "", False)
    scriptDialog.AddRangeControlToGrid("MachineLimitBox", "RangeControl", 0, 0, 1000000, 0, 1, 7, 1)
    scriptDialog.AddSelectionControlToGrid("IsBlacklistBox", "CheckBoxControl", False, "Machine List Is A Deny List", 7,
                                           2, "")

    scriptDialog.AddControlToGrid("MachineListLabel", "LabelControl", "Machine List", 8, 0,
                                  "Use the Machine Limit to specify the maximum number of machines that can render your job at one time. Specify 0 for no limit.",
                                  False)
    scriptDialog.AddControlToGrid("MachineListBox", "MachineListControl", "", 8, 1, colSpan=2)

    scriptDialog.AddControlToGrid("LimitGroupLabel", "LabelControl", "Limits", 9, 0,
                                  "The Limits that your job requires.", False)
    scriptDialog.AddControlToGrid("LimitGroupBox", "LimitGroupControl", "", 9, 1, colSpan=2)

    scriptDialog.AddControlToGrid("DependencyLabel", "LabelControl", "Dependencies", 10, 0,
                                  "Specify existing jobs that this job will be dependent on. This job will not start until the specified dependencies finish rendering. ",
                                  False)
    scriptDialog.AddControlToGrid("DependencyBox", "DependencyControl", "", 10, 1, colSpan=2)

    scriptDialog.AddControlToGrid("OnJobCompleteLabel", "LabelControl", "On Job Complete", 11, 0,
                                  "If desired, you can automatically archive or delete the job when it completes. ",
                                  False)
    scriptDialog.AddControlToGrid("OnJobCompleteBox", "OnJobCompleteControl", "Nothing", 11, 1)
    scriptDialog.AddSelectionControlToGrid("SubmitSuspendedBox", "CheckBoxControl", False, "Submit Job As Suspended",
                                           11, 2,
                                           "If enabled, the job will submit in the suspended state. This is useful if you don't want the job to start rendering right away. Just resume it from the Monitor when you want it to render. ")
    scriptDialog.EndGrid()

    scriptDialog.EndTabPage()

    scriptDialog.AddTabPage("Octane Options")

    dialogID = 0
    scriptDialog.AddGrid()
    scriptDialog.AddControlToGrid("Separator3", "SeparatorControl", "Project Options", dialogID, 0, colSpan=4)

    dialogID += 1
    scriptDialog.AddControlToGrid("SceneLabel", "LabelControl", "Octane Scene File", dialogID, 0,
                                  "The scene file to render.", False)
    sceneBox = scriptDialog.AddSelectionControlToGrid("SceneBox", "FileBrowserControl", "",
                                                      "Octane Scene Files (*.ocs);;Octane Package Files (*.orbx)", 1, 1,
                                                      colSpan=3)
    sceneBox.ValueModified.connect(SceneBoxChanged)

    dialogID += 1
    scriptDialog.AddControlToGrid("OutputLabel", "LabelControl", "Output Folder", dialogID, 0,
                                  "Override the output path in the scene.", False)
    scriptDialog.AddSelectionControlToGrid("OutputBox", "FolderBrowserControl", "", "All Files (*)", dialogID, 1,
                                           colSpan=3)

    dialogID += 1
    scriptDialog.AddControlToGrid("Separator4", "SeparatorControl", "Render Options", dialogID, 0, colSpan=4)

    dialogID += 1
    scriptDialog.AddControlToGrid("FilenameTemplateLabel", "LabelControl", "Filename Template", dialogID, 0,
                                  "Template parameters:\n\t%i render target index\n\t%n render target node name\n\t%e file extension\n\t%t timestamp\n\t%f frame number\n\t%F frame number prefixed with 0s\n\t%s sub frame number\n\t%p render pass name\nNote: Parameters ignored in \"Single Frame per OCS File\" mode.")
    scriptDialog.AddControlToGrid("FilenameTemplateBox", "TextControl", "%F.%e", dialogID, 1, colSpan=3)

    dialogID += 1
    scriptDialog.AddControlToGrid("CmdLabel", "LabelControl", "Command Line Args", dialogID, 0,
                                  "Additional command line arguments to use for rendering.", False)
    scriptDialog.AddControlToGrid("CmdBox", "TextControl", "", dialogID, 1, colSpan=4)

    dialogID += 1
    scriptDialog.AddControlToGrid("VersionLabel", "LabelControl", "Version", dialogID, 0,
                                  "The Octane Standalone application version to use.", False)
    versions = ("4", "2019", "2026")
    currentVersion = int(versions[-1])
    versionBox = scriptDialog.AddComboControlToGrid("VersionBox", "ComboControl", "2026", versions, dialogID, 1)
    versionBox.ValueModified.connect(VersionBoxChanged)

    scriptDialog.AddControlToGrid("FileFormatLabel", "LabelControl", "File Format", dialogID, 2,
                                  "What format the output file will be saved as.", False)
    # Initialize with 2020+ format options since default version is 2026
    fileFormatBox = scriptDialog.AddComboControlToGrid("FileFormatBox", "ComboControl",
                                                       formatOptionsV2020[selectedFormatOptionsIndexV2020], formatOptionsV2020,
                                                       dialogID, 3)

    dialogID += 1
    scriptDialog.AddControlToGrid("EXRCompressionLabel", "LabelControl", "EXR Compression", dialogID, 2,
                                  "Select the type of compression to use when saving as an EXR. If blank no compression will be performed.",
                                  False)
    scriptDialog.AddComboControlToGrid("EXRCompressionBox", "ComboControl", compressionOptions[defaultCompressionIndex],
                                       compressionOptions, dialogID, 3)
    fileFormatBox.ValueModified.connect(FileFormatBoxChanged)

    # 2020+ Options Section
    dialogID += 1
    scriptDialog.AddControlToGrid("Separator2020", "SeparatorControl", "Octane 2020+ Options", dialogID, 0, colSpan=4)

    dialogID += 1
    scriptDialog.AddControlToGrid("ColorSpaceLabel", "LabelControl", "Color Space", dialogID, 0,
                                  "Output color space for rendered images. (Octane 2020+ only)", False)
    colorSpaceBox = scriptDialog.AddComboControlToGrid("ColorSpaceBox", "ComboControl", colorSpaceOptions[defaultColorSpaceIndex],
                                                       colorSpaceOptions, dialogID, 1)
    colorSpaceBox.ValueModified.connect(ColorSpaceBoxChanged)
    
    scriptDialog.AddSelectionControlToGrid("PremultipliedAlphaBox", "CheckBoxControl", True,
                                           "Premultiplied Alpha", dialogID, 2,
                                           "Use premultiplied alpha when saving EXR or TIFF files. (Octane 2020+ only)")
    scriptDialog.AddSelectionControlToGrid("ForceToneMappingBox", "CheckBoxControl", False,
                                           "Force Tone Mapping", dialogID, 3,
                                           "Force tone mapping to be applied even for linear color spaces. (Octane 2020+ only)")

    dialogID += 1
    scriptDialog.AddControlToGrid("OcioColorSpaceLabel", "LabelControl", "OCIO Color Space", dialogID, 0,
                                  "The name of the OCIO color space to use (only when Color Space is set to OCIO).", False)
    scriptDialog.AddControlToGrid("OcioColorSpaceBox", "TextControl", "", dialogID, 1)
    scriptDialog.AddControlToGrid("OcioLookLabel", "LabelControl", "OCIO Look", dialogID, 2,
                                  "The name of the OCIO look to apply (only when Color Space is set to OCIO).", False)
    scriptDialog.AddControlToGrid("OcioLookBox", "TextControl", "", dialogID, 3)
    # Initially disable OCIO options
    scriptDialog.SetEnabled("OcioColorSpaceLabel", False)
    scriptDialog.SetEnabled("OcioColorSpaceBox", False)
    scriptDialog.SetEnabled("OcioLookLabel", False)
    scriptDialog.SetEnabled("OcioLookBox", False)

    dialogID += 1
    scriptDialog.AddControlToGrid("TargetOCSLabel", "LabelControl", "Render Target (ocs)", dialogID, 0,
                                  "Select the target to render (ocs files only).", False)
    scriptDialog.AddComboControlToGrid("TargetOCSBox", "ComboControl", "", [""], dialogID, 1)
    scriptDialog.SetEnabled("TargetOCSBox", False)
    scriptDialog.AddControlToGrid("TargetORBXLabel", "LabelControl", "Render Target (orbx)", dialogID, 2,
                                  "The target to render (orbx files only). Leaving this field blank will render all targets.",
                                  False)
    scriptDialog.AddControlToGrid("TargetORBXBox", "TextControl", "", dialogID, 3)
    scriptDialog.SetEnabled("TargetORBXBox", False)

    dialogID += 1
    scriptDialog.AddSelectionControlToGrid("SkipExistingFileBox", "CheckBoxControl", False, "Skip Existing File",
                                           dialogID, 0, "If enabled, existing files will not be overwritten")
    scriptDialog.AddSelectionControlToGrid("SaveLayeredEXRBox", "CheckBoxControl", False,
                                           "Save Layered EXR\n(Only when saved as EXR)", dialogID, 1,
                                           "Save the render passes as a layered EXR")
    scriptDialog.AddSelectionControlToGrid("DeepImageBox", "CheckBoxControl", False,
                                           "Save Deep Image\n(Must be enabled in Kernel too)", dialogID, 2,
                                           "Save additional deep image output.")

    dialogID += 1
    enabledPassesBox = scriptDialog.AddSelectionControlToGrid("SaveAllEnabledPassesBox", "CheckBoxControl", False,
                                                              "Save All Enabled \nPasses", dialogID, 1,
                                                              "If enabled, save all enabled render passes", colSpan=2)
    enabledDenoisedBox = scriptDialog.AddSelectionControlToGrid("SaveDenoisedMainPassIfAvailableBox", "CheckBoxControl", False,
                                                                "Save Denoised Main Pass\n(Must be enabled in Tonemap too)", dialogID, 2,
                                                                "If enabled, save denoised pass.")
    scriptDialog.SetEnabled("SaveLayeredEXRBox", IsAdvancedExrAllowed())
    enabledPassesBox.ValueModified.connect(EnabledPassesBoxChanged)
    enabledDenoisedBox.ValueModified.connect(EnabledDenoisedBoxChanged)

    dialogID += 1
    framePerFileBox = scriptDialog.AddSelectionControlToGrid("FramePerFileBox", "CheckBoxControl", False,
                                                             "\"Single Frame per OCS File\" Mode", dialogID, 0,
                                                             "Enable this mode if you have an animation with one frame per OCS file. Select just one file from the sequence.",
                                                             colSpan=2)
    framePerFileBox.ValueModified.connect(FramePerFileBoxChanged)

    dialogID += 1
    scriptDialog.AddControlToGrid("FramesLabel", "LabelControl", "Frame List", dialogID, 0,
                                  "The list of frames to render.", False)
    scriptDialog.AddControlToGrid("FramesBox", "TextControl", "", dialogID, 1, colSpan=3)

    dialogID += 1
    scriptDialog.AddControlToGrid("ChunkSizeLabel", "LabelControl", "Frames Per Task", dialogID, 0,
                                  "This is the number of frames that will be rendered at a time for each job task.",
                                  False)
    scriptDialog.AddRangeControlToGrid("ChunkSizeBox", "RangeControl", 1, 1, 1000000, 0, 1, dialogID, 1, colSpan=2)
    singleFileBox = scriptDialog.AddSelectionControlToGrid("SingleFileBox", "CheckBoxControl", False,
                                                           "Single Frame Job", dialogID, 3,
                                                           "This should be checked if you're submitting a single Octane file only, as opposed to separate files per frame. ")
    singleFileBox.ValueModified.connect(SingleFileBoxChanged)

    scriptDialog.EndGrid()

    scriptDialog.AddGrid()

    dialogID += 1
    scriptDialog.AddControlToGrid("Separator5", "SeparatorControl", "GPU Options", dialogID, 0, colSpan=2)

    dialogID += 1
    overrideSamplingCheck = scriptDialog.AddSelectionControlToGrid("OverrideSamplingBox", "CheckBoxControl", False,
                                                                   "Override Sampling", dialogID, 0,
                                                                   "Enable to override the Sampling setting in the scene file.",
                                                                   False)
    overrideSamplingCheck.ValueModified.connect(OverrideSamplingChanged)
    scriptDialog.AddRangeControlToGrid("SampleBox", "RangeControl", 10, 0, 100000, 0, 1, dialogID, 1, colSpan=2)
    scriptDialog.SetEnabled("SampleBox", False)

    dialogID += 1
    scriptDialog.AddControlToGrid("GPUsPerTaskLabel", "LabelControl", "GPUs Per Task", dialogID, 0,
                                  "The number of GPUs to use per task. If set to 0, the default number of GPUs will be used, unless 'Select GPU Devices' Id's have been defined.",
                                  False)
    GPUsPerTaskBox = scriptDialog.AddRangeControlToGrid("GPUsPerTaskBox", "RangeControl", 0, 0, 1024, 0, 1, dialogID, 1,
                                                        colSpan=2)
    GPUsPerTaskBox.ValueModified.connect(GPUsPerTaskChanged)

    dialogID += 1
    scriptDialog.AddControlToGrid("GPUsSelectDevicesLabel", "LabelControl", "Select GPU Devices", dialogID, 0,
                                  "A comma separated list of the GPU devices to use specified by device Id. 'GPUs Per Task' will be ignored.",
                                  False)
    GPUsSelectDevicesBox = scriptDialog.AddControlToGrid("GPUsSelectDevicesBox", "TextControl", "", dialogID, 1,
                                                         colSpan=2)
    GPUsSelectDevicesBox.ValueModified.connect(GPUsSelectDevicesChanged)

    # Done setting up dialog

    scriptDialog.EndGrid()
    scriptDialog.EndTabPage()

    integration_dialog = IntegrationUI.IntegrationDialog()
    integration_dialog.AddIntegrationTabs(scriptDialog, "OctaneMonitor", DraftRequested, ProjectManagementOptions,
                                          failOnNoTabs=False)

    scriptDialog.EndTabControl()

    scriptDialog.AddGrid()
    scriptDialog.AddHorizontalSpacerToGrid("HSpacer1", 0, 0)
    submitButton = scriptDialog.AddControlToGrid("SubmitButton", "ButtonControl", "Submit", 0, 1, expand=False)
    submitButton.ValueModified.connect(SubmitButtonPressed)
    closeButton = scriptDialog.AddControlToGrid("CloseButton", "ButtonControl", "Close", 0, 2, expand=False)
    # Make sure all the project management connections are closed properly
    closeButton.ValueModified.connect(integration_dialog.CloseProjectManagementConnections)
    closeButton.ValueModified.connect(scriptDialog.closeEvent)
    scriptDialog.EndGrid()

    settings = (
    "DepartmentBox", "CategoryBox", "PoolBox", "SecondaryPoolBox", "GroupBox", "PriorityBox", "MachineLimitBox",
    "IsBlacklistBox", "MachineListBox", "LimitGroupBox", "SceneBox", "OutputBox", "SampleBox", "FramesBox",
    "FilenameTemplateBox", "FileFormatBox", "CmdBox", "SingleFileBox", "OverrideSamplingBox", "TargetORBXBox",
    "ChunkSizeBox", "VersionBox", "FramePerFileBox", "ColorSpaceBox", "PremultipliedAlphaBox", "ForceToneMappingBox",
    "OcioColorSpaceBox", "OcioLookBox", "EXRCompressionBox")
    scriptDialog.LoadSettings(GetSettingsFilename(), settings)
    scriptDialog.EnabledStickySaving(settings, GetSettingsFilename())
    
    # Initialize UI based on the loaded version
    VersionBoxChanged()

    scriptDialog.ShowDialog(False)


def GPUsPerTaskChanged(*args):
    # type: (*RangeControl) -> None
    global scriptDialog

    perTaskEnabled = (scriptDialog.GetValue("GPUsPerTaskBox") == 0)

    scriptDialog.SetEnabled("GPUsSelectDevicesLabel", perTaskEnabled)
    scriptDialog.SetEnabled("GPUsSelectDevicesBox", perTaskEnabled)


def GPUsSelectDevicesChanged(*args):
    global scriptDialog

    selectDeviceEnabled = (scriptDialog.GetValue("GPUsSelectDevicesBox") == "")

    scriptDialog.SetEnabled("GPUsPerTaskLabel", selectDeviceEnabled)
    scriptDialog.SetEnabled("GPUsPerTaskBox", selectDeviceEnabled)


def GetSettingsFilename():
    # type: () -> str
    return Path.Combine(ClientUtils.GetUsersSettingsDirectory(), "OctaneSettings.ini")


def SceneBoxChanged(*args):
    # type: (*FileBrowserControl) -> None
    global scriptDialog
    filename = scriptDialog.GetValue("SceneBox")

    DetermineFrameRange(filename)
    DetermineRenderTargets(filename)


def DetermineFrameRange(filename):
    # type: (str) -> None
    global scriptDialog
    try:
        if (File.Exists(filename)):
            paddingSize = FrameUtils.GetPaddingSizeFromFilename(filename)
            if paddingSize > 0:
                frameString = "1"
                startFrame = 0
                endFrame = 0
                initFrame = FrameUtils.GetFrameNumberFromFilename(filename)

                startFrame = FrameUtils.GetLowerFrameRange(filename, initFrame, paddingSize)
                endFrame = FrameUtils.GetUpperFrameRange(filename, initFrame, paddingSize)
                if (startFrame != endFrame):
                    frameString = str(startFrame) + "-" + str(endFrame)
                    scriptDialog.SetValue("FramesBox", frameString)
                    scriptDialog.SetValue("SingleFileBox", False)
                else:
                    scriptDialog.SetValue("SingleFileBox", True)
            else:
                scriptDialog.SetValue("SingleFileBox", True)
    except:
        pass


def DetermineRenderTargets(filename):
    # type: (str) -> None
    global isOrbxFile
    targetList = []  # type: List
    framePerFileMode = scriptDialog.GetValue("FramePerFileBox")

    if filename[-5:] == ".orbx":
        isOrbxFile = True
    else:
        isOrbxFile = False

        try:
            if File.Exists(filename):
                ocsGraph = ET.parse(filename)
                ocsRoot = ocsGraph.getroot()

                if ocsRoot.tag == "OCS2":
                    renderTargets = ocsRoot.findall("./graph/node")
                    for node in renderTargets:
                        nodeType = node.attrib.get("type", "")
                        nodeName = node.attrib.get("name", "")
                        if nodeType == "56" and nodeName != "":
                            targetList.append(nodeName)

                else:
                    renderTargets = ocsRoot.findall("./Node/childgraph/NodeGraph/nodes/*")
                    for node in renderTargets:
                        typename = node.find("typename").text  # type: ignore
                        if typename == "rendertarget":
                            renderTarget = node.find("name").text  # type: ignore
                            targetList.append(renderTarget)
        except:
            ClientUtils.LogText("Error parsing Octane scene file: " + traceback.format_exc())

    if isOrbxFile and not framePerFileMode:
        scriptDialog.SetItems("TargetOCSBox", [""])
        scriptDialog.SetEnabled("TargetOCSBox", False)
        scriptDialog.SetEnabled("TargetOCSLabel", False)
        scriptDialog.SetEnabled("TargetORBXBox", True)
        scriptDialog.SetEnabled("TargetORBXLabel", True)
    elif len(targetList) > 0:
        scriptDialog.SetItems("TargetOCSBox", targetList)
        scriptDialog.SetEnabled("TargetOCSBox", True)
        scriptDialog.SetEnabled("TargetOCSLabel", True)
        scriptDialog.SetItems("TargetORBXBox", "")
        scriptDialog.SetEnabled("TargetORBXBox", False)
        scriptDialog.SetEnabled("TargetORBXLabel", False)
    else:
        scriptDialog.SetItems("TargetOCSBox", [""])
        scriptDialog.SetEnabled("TargetOCSBox", False)
        scriptDialog.SetEnabled("TargetOCSLabel", False)
        scriptDialog.SetItems("TargetORBXBox", "")
        scriptDialog.SetEnabled("TargetORBXBox", False)
        scriptDialog.SetEnabled("TargetORBXLabel", False)


def OverrideSamplingChanged(*args):
    # type: (*CheckBoxControl) -> None
    global scriptDialog

    enabled = scriptDialog.GetValue("OverrideSamplingBox")
    scriptDialog.SetEnabled("SampleBox", enabled)


def SingleFileBoxChanged(*args):
    # type: (*CheckBoxControl) -> None
    global scriptDialog
    singleFileChecked = scriptDialog.GetValue("SingleFileBox")
    framePerFileMode = scriptDialog.GetValue("FramePerFileBox")

    enabled = not singleFileChecked
    scriptDialog.SetEnabled("FramesLabel", enabled)
    scriptDialog.SetEnabled("FramesBox", enabled)

    if framePerFileMode:
        scriptDialog.SetEnabled("ChunkSizeLabel", False)
        scriptDialog.SetEnabled("ChunkSizeBox", False)
    else:
        scriptDialog.SetEnabled("ChunkSizeLabel", enabled)
        scriptDialog.SetEnabled("ChunkSizeBox", enabled)


def FramePerFileBoxChanged(*args):
    # type: (*CheckBoxControl) -> None
    global scriptDialog
    framePerFileMode = scriptDialog.GetValue("FramePerFileBox")
    filename = scriptDialog.GetValue("SceneBox")
    enabled = not framePerFileMode
    singleFileChecked = scriptDialog.GetValue("SingleFileBox")

    DetermineRenderTargets(filename)

    if not singleFileChecked:
        scriptDialog.SetEnabled("ChunkSizeLabel", enabled)
        scriptDialog.SetEnabled("ChunkSizeBox", enabled)


def VersionBoxChanged(*args):
    # type: (*ComboControl) -> None
    global scriptDialog
    global currentVersion
    global selectedFormatOptionsIndexV3
    global selectedFormatOptionsIndexV4
    global selectedFormatOptionsIndexV2020

    version = int(scriptDialog.GetValue("VersionBox"))

    scriptDialog.SetValue("FramePerFileBox", version == 1)
    scriptDialog.SetEnabled("FramePerFileBox", version != 1)

    # Determine version categories
    prev_is_v3 = currentVersion < 4
    prev_is_v4 = 4 <= currentVersion < 2020
    prev_is_v2020 = currentVersion >= 2020
    
    new_is_v3 = version < 4
    new_is_v4 = 4 <= version < 2020
    new_is_v2020 = version >= 2020

    # Save current format selection before switching
    currentFormat = scriptDialog.GetValue("FileFormatBox")
    if prev_is_v3 and currentFormat in formatOptionsV3:
        selectedFormatOptionsIndexV3 = formatOptionsV3.index(currentFormat)
    elif prev_is_v4 and currentFormat in formatOptionsV4:
        selectedFormatOptionsIndexV4 = formatOptionsV4.index(currentFormat)
    elif prev_is_v2020 and currentFormat in formatOptionsV2020:
        selectedFormatOptionsIndexV2020 = formatOptionsV2020.index(currentFormat)

    currentVersion = version

    # Check if staying in same version category
    if (prev_is_v3 and new_is_v3) or (prev_is_v4 and new_is_v4) or (prev_is_v2020 and new_is_v2020):
        return

    if new_is_v2020:
        SetUIForV2020()
    elif new_is_v4:
        SetUIForV4()
    else:
        SetUIForV3()


def SetUIForV3():
    # type: () -> None
    scriptDialog.SetEnabled("SaveAllEnabledPassesBox", False)
    scriptDialog.SetEnabled("SaveDenoisedMainPassIfAvailableBox", False)

    scriptDialog.SetEnabled("SkipExistingFileBox", False)
    scriptDialog.SetEnabled("DeepImageBox", False)

    scriptDialog.SetItems("FileFormatBox", formatOptionsV3)
    scriptDialog.SetValue("FileFormatBox", formatOptionsV3[selectedFormatOptionsIndexV3])

    scriptDialog.SetEnabled("SaveLayeredEXRBox", False)
    scriptDialog.SetEnabled("EXRCompressionBox", False)
    scriptDialog.SetEnabled("EXRCompressionLabel", False)

    # Disable 2020+ options
    SetV2020OptionsEnabled(False)


def SetUIForV4():
    # type: () -> None
    # Switching from V3 to V4. In V3 both this options are disabled, so we want to know if we should enable the first, the second, or both options.
    # We can have 3 scenarios:
    # 1. If SaveAllEnabledPassesBox was checked: SaveAllEnabledPassesBox becomes enabled and remains checked.
    #    It also means, that SaveDenoisedMainPassIfAvailableBox was unchecked, so it remains disabled.
    # 2. If SaveDenoisedMainPassIfAvailableBox was checked: SaveDenoisedMainPassIfAvailableBox becomes enabled and remains checked.
    #    It also means, that SaveAllEnabledPassesBox was unchecked and remains disabled.s
    # 3. If both were not checked: both become enabled and remain unchecked, so the user can choose one of them.
    # This helps to avoid circular dependency between EnabledPassesBoxChanged and EnabledDenoisedBoxChanged.
    # Also, it helps to save the values selected by the user even after switching to older versions.
    # NOTE: We can't use scriptDialog.SetEnabled("SaveAllEnabledPassesBox", scriptDialog.GetValue("SaveAllEnabledPassesBox"))
    #       because if both options were not checked, they will remain disabled even for V4 as well.
    scriptDialog.SetEnabled("SaveAllEnabledPassesBox", not scriptDialog.GetValue("SaveDenoisedMainPassIfAvailableBox"))
    scriptDialog.SetEnabled("SaveDenoisedMainPassIfAvailableBox", not scriptDialog.GetValue("SaveAllEnabledPassesBox"))

    scriptDialog.SetEnabled("SkipExistingFileBox", True)
    scriptDialog.SetEnabled("DeepImageBox", True)

    scriptDialog.SetItems("FileFormatBox", formatOptionsV4)
    scriptDialog.SetValue("FileFormatBox", formatOptionsV4[selectedFormatOptionsIndexV4])

    advancedExrAllowed = IsAdvancedExrAllowed()
    scriptDialog.SetEnabled("SaveLayeredEXRBox", advancedExrAllowed)
    scriptDialog.SetEnabled("EXRCompressionBox", advancedExrAllowed)
    scriptDialog.SetEnabled("EXRCompressionLabel", advancedExrAllowed)

    # Disable 2020+ options
    SetV2020OptionsEnabled(False)


def SetUIForV2020():
    # type: () -> None
    # Enable all V4 options plus 2020+ specific options
    scriptDialog.SetEnabled("SaveAllEnabledPassesBox", not scriptDialog.GetValue("SaveDenoisedMainPassIfAvailableBox"))
    scriptDialog.SetEnabled("SaveDenoisedMainPassIfAvailableBox", not scriptDialog.GetValue("SaveAllEnabledPassesBox"))

    scriptDialog.SetEnabled("SkipExistingFileBox", True)
    scriptDialog.SetEnabled("DeepImageBox", True)

    # Use new format options for 2020+
    scriptDialog.SetItems("FileFormatBox", formatOptionsV2020)
    scriptDialog.SetValue("FileFormatBox", formatOptionsV2020[selectedFormatOptionsIndexV2020])

    advancedExrAllowed = IsAdvancedExrAllowed()
    scriptDialog.SetEnabled("SaveLayeredEXRBox", advancedExrAllowed)
    scriptDialog.SetEnabled("EXRCompressionBox", advancedExrAllowed)
    scriptDialog.SetEnabled("EXRCompressionLabel", advancedExrAllowed)

    # Enable 2020+ options
    SetV2020OptionsEnabled(True)


def SetV2020OptionsEnabled(enabled):
    # type: (bool) -> None
    """Enable or disable 2020+ specific options"""
    scriptDialog.SetEnabled("Separator2020", enabled)
    scriptDialog.SetEnabled("ColorSpaceLabel", enabled)
    scriptDialog.SetEnabled("ColorSpaceBox", enabled)
    scriptDialog.SetEnabled("PremultipliedAlphaBox", enabled)
    scriptDialog.SetEnabled("ForceToneMappingBox", enabled)
    
    # OCIO options depend on ColorSpace selection
    if enabled:
        isOcio = scriptDialog.GetValue("ColorSpaceBox") == "OCIO"
        scriptDialog.SetEnabled("OcioColorSpaceLabel", isOcio)
        scriptDialog.SetEnabled("OcioColorSpaceBox", isOcio)
        scriptDialog.SetEnabled("OcioLookLabel", isOcio)
        scriptDialog.SetEnabled("OcioLookBox", isOcio)
    else:
        scriptDialog.SetEnabled("OcioColorSpaceLabel", False)
        scriptDialog.SetEnabled("OcioColorSpaceBox", False)
        scriptDialog.SetEnabled("OcioLookLabel", False)
        scriptDialog.SetEnabled("OcioLookBox", False)


def ColorSpaceBoxChanged(*args):
    # type: (*ComboControl) -> None
    global scriptDialog
    isOcio = scriptDialog.GetValue("ColorSpaceBox") == "OCIO"
    isV2020Plus = currentVersion >= 2020
    
    scriptDialog.SetEnabled("OcioColorSpaceLabel", isOcio and isV2020Plus)
    scriptDialog.SetEnabled("OcioColorSpaceBox", isOcio and isV2020Plus)
    scriptDialog.SetEnabled("OcioLookLabel", isOcio and isV2020Plus)
    scriptDialog.SetEnabled("OcioLookBox", isOcio and isV2020Plus)


def EnabledPassesBoxChanged(*args):
    # type: (*CheckBoxControl) -> None
    global scriptDialog
    enabledBoxChecked = scriptDialog.GetValue("SaveAllEnabledPassesBox")
    scriptDialog.SetEnabled("SaveDenoisedMainPassIfAvailableBox", not enabledBoxChecked)


def EnabledDenoisedBoxChanged(*args):
    global scriptDialog
    enabledBoxChecked = scriptDialog.GetValue("SaveDenoisedMainPassIfAvailableBox")
    scriptDialog.SetEnabled("SaveAllEnabledPassesBox", not enabledBoxChecked)


def FileFormatBoxChanged(*args):
    # type: (*ComboControl) -> None
    global scriptDialog

    enable = IsAdvancedExrAllowed()
    scriptDialog.SetEnabled("SaveLayeredEXRBox", enable)
    scriptDialog.SetEnabled("EXRCompressionLabel", enable)
    scriptDialog.SetEnabled("EXRCompressionBox", enable)


def IsAdvancedExrAllowed():
    # type: () -> bool
    formatValue = scriptDialog.GetValue("FileFormatBox")
    isFormatEXR = formatValue[:3].lower() == 'exr' or formatValue.startswith("EXR_")
    return isFormatEXR and currentVersion >= 4


def SubmitButtonPressed(*args):
    # type: (*ButtonControl) -> None
    global scriptDialog
    global integration_dialog

    errors = ""

    sceneFile = scriptDialog.GetValue("SceneBox")
    if (not File.Exists(sceneFile)):
        scriptDialog.ShowMessageBox("The Octane scene file %s does not exist" % sceneFile, "Error")
        return
    elif (not scriptDialog.GetValue("SceneBox") and PathUtils.IsPathLocal(sceneFile)):
        result = scriptDialog.ShowMessageBox(
            "The Octane scene file %s is local. Are you sure you want to continue?" % sceneFile, "Warning",
            ("Yes", "No"))
        if (result == "No"):
            return

    outputFolder = scriptDialog.GetValue("OutputBox")
    if outputFolder == "":
        errors += "An output folder must be chosen."
    elif (not Directory.Exists(Path.GetDirectoryName(outputFolder))):
        scriptDialog.ShowMessageBox(
            "The directory of the output folder %s does not exist." % Path.GetDirectoryName(outputFolder), "Error")
        return
    elif (PathUtils.IsPathLocal(outputFolder)):
        result = scriptDialog.ShowMessageBox(
            "The output folder %s is local. Are you sure you want to continue?" % outputFolder, "Warning",
            ("Yes", "No"))
        if (result == "No"):
            return

    framePerFile = scriptDialog.GetValue("FramePerFileBox")
    if framePerFile and sceneFile[-5:] == ".orbx":
        errors += "An orbx file cannot be selected in \"Single Frame per OCS File\" mode."

    filenameTemplate = scriptDialog.GetValue("FilenameTemplateBox")
    if ".%e" not in filenameTemplate:
        errors += ("The filename template \"%s\" is invalid! It must contain \".%%e\"." % filenameTemplate)
    elif ("%F" not in filenameTemplate) and ("%f" not in filenameTemplate):
        result = scriptDialog.ShowMessageBox(
            "The filename template does not contain any padding (%F or %f). Are you sure you want to continue?",
            "Warning", ("Yes", "No"))
        if (result == "No"):
            return

    # Check if a valid frame range has been specified.
    frames = scriptDialog.GetValue("FramesBox")
    singleFile = scriptDialog.GetValue("SingleFileBox")
    if (singleFile):
        frames = "0"
    elif (not FrameUtils.FrameRangeValid(frames)):
        errors += (" - Frame range '%s' is not valid.\n" % frames)

    # If Octane and using 'select GPU device Ids' then check device Id syntax is valid
    if scriptDialog.GetValue("GPUsPerTaskBox") == 0 and scriptDialog.GetValue("GPUsSelectDevicesBox") != "":
        regex = re.compile("^(\d{1,2}(,\d{1,2})*)?$")
        validSyntax = regex.match(scriptDialog.GetValue("GPUsSelectDevicesBox"))
        if not validSyntax:
            errors += "'Select GPU Devices' syntax is invalid!\n\nTrailing 'commas' if present, should be removed.\n\nValid Examples: 0 or 2 or 0,1,2 or 0,3,4 etc\n"

        # Check if concurrent threads > 1
        if scriptDialog.GetValue("ConcurrentTasksBox") > 1:
            errors += "If using 'Select GPU Devices', then 'Concurrent Tasks' must be set to 1\n"

    # Check if Integration options are valid.
    if integration_dialog is not None and not integration_dialog.CheckIntegrationSanity():
        return

    if len(errors) > 0:
        scriptDialog.ShowMessageBox(
            "The following errors were found:\n\n" + errors + "\nPlease fix these before submitting the job.", "Error")
        return

    jobName = scriptDialog.GetValue("NameBox")

    # Create job info file.
    jobInfoFilename = Path.Combine(ClientUtils.GetDeadlineTempPath(), "octane_job_info.job")
    writer = StreamWriter(jobInfoFilename, False, Encoding.Unicode)
    writer.WriteLine("Plugin=Octane")
    writer.WriteLine("Name=%s" % jobName)
    writer.WriteLine("Comment=%s" % scriptDialog.GetValue("CommentBox"))
    writer.WriteLine("Department=%s" % scriptDialog.GetValue("DepartmentBox"))
    writer.WriteLine("Pool=%s" % scriptDialog.GetValue("PoolBox"))
    writer.WriteLine("SecondaryPool=%s" % scriptDialog.GetValue("SecondaryPoolBox"))
    writer.WriteLine("Group=%s" % scriptDialog.GetValue("GroupBox"))
    writer.WriteLine("Priority=%s" % scriptDialog.GetValue("PriorityBox"))
    writer.WriteLine("TaskTimeoutMinutes=%s" % scriptDialog.GetValue("TaskTimeoutBox"))
    writer.WriteLine("EnableAutoTimeout=%s" % scriptDialog.GetValue("AutoTimeoutBox"))
    writer.WriteLine("ConcurrentTasks=%s" % scriptDialog.GetValue("ConcurrentTasksBox"))
    writer.WriteLine("LimitConcurrentTasksToNumberOfCpus=%s" % scriptDialog.GetValue("LimitConcurrentTasksBox"))
    writer.WriteLine("Frames=%s" % frames)

    if scriptDialog.GetEnabled("ChunkSizeBox"):
        writer.WriteLine("ChunkSize=%s" % scriptDialog.GetValue("ChunkSizeBox"))

    writer.WriteLine("MachineLimit=%s" % scriptDialog.GetValue("MachineLimitBox"))
    if (bool(scriptDialog.GetValue("IsBlacklistBox"))):
        writer.WriteLine("Blacklist=%s" % scriptDialog.GetValue("MachineListBox"))
    else:
        writer.WriteLine("Whitelist=%s" % scriptDialog.GetValue("MachineListBox"))

    writer.WriteLine("LimitGroups=%s" % scriptDialog.GetValue("LimitGroupBox"))
    writer.WriteLine("JobDependencies=%s" % scriptDialog.GetValue("DependencyBox"))
    writer.WriteLine("OnJobComplete=%s" % scriptDialog.GetValue("OnJobCompleteBox"))

    if (bool(scriptDialog.GetValue("SubmitSuspendedBox"))):
        writer.WriteLine("InitialStatus=Suspended")

    if outputFolder != "":
        writer.WriteLine("OutputDirectory0=%s" % outputFolder)

    # Integration
    extraKVPIndex = 0
    groupBatch = False

    if integration_dialog is not None and integration_dialog.IntegrationProcessingRequested():
        extraKVPIndex = integration_dialog.WriteIntegrationInfo(writer, extraKVPIndex)
        groupBatch = groupBatch or integration_dialog.IntegrationGroupBatchRequested()

    if groupBatch:
        writer.WriteLine("BatchName=%s\n" % (jobName))
    writer.Close()

    # Create plugin info file.
    pluginInfoFilename = Path.Combine(ClientUtils.GetDeadlineTempPath(), "octane_plugin_info.job")
    writer = StreamWriter(pluginInfoFilename, False, Encoding.Unicode)

    writer.WriteLine("SceneFile=%s" % sceneFile)
    writer.WriteLine("Version=%s" % scriptDialog.GetValue("VersionBox"))
    writer.WriteLine("SingleFile=%s" % singleFile)
    writer.WriteLine("FramePerFileMode=%s" % framePerFile)

    if outputFolder != "":
        writer.WriteLine("OutputFolder=%s" % outputFolder)

    writer.WriteLine("FilenameTemplate=%s" % filenameTemplate)
    writer.WriteLine("FileFormat=%s" % scriptDialog.GetValue("FileFormatBox"))

    overrideSampling = scriptDialog.GetValue("OverrideSamplingBox")
    if overrideSampling:
        writer.WriteLine("OverrideSampling=%s" % scriptDialog.GetValue("SampleBox"))

    if isOrbxFile:
        writer.WriteLine("RenderTargetORBX=%s" % scriptDialog.GetValue("TargetORBXBox"))
    else:
        writer.WriteLine("RenderTargetOCS=%s" % scriptDialog.GetValue("TargetOCSBox"))

    # Enumerate the render targets
    pos = 0
    for target in scriptDialog.GetItems("TargetOCSBox"):
        writer.WriteLine("RenderTargetOCS%d=%s" % (pos, target))
        pos += 1

    writer.WriteLine("GPUsPerTask=%s" % scriptDialog.GetValue("GPUsPerTaskBox"))
    writer.WriteLine("GPUsSelectDevices=%s" % scriptDialog.GetValue("GPUsSelectDevicesBox"))

    writer.WriteLine("AdditionalArgs=%s" % scriptDialog.GetValue("CmdBox"))

    writer.WriteLine("SkipExisting=%s" % scriptDialog.GetValue("SkipExistingFileBox"))
    writer.WriteLine("SaveAllPasses=%s" % scriptDialog.GetValue("SaveAllEnabledPassesBox"))

    if scriptDialog.GetValue("SaveAllEnabledPassesBox"):
        writer.WriteLine("SaveDenoisedMainPass=%s" % False)
    else:
        writer.WriteLine("SaveDenoisedMainPass=%s" % scriptDialog.GetValue("SaveDenoisedMainPassIfAvailableBox"))

    writer.WriteLine("SaveLayeredEXRBox=%s" % scriptDialog.GetValue("SaveLayeredEXRBox"))
    writer.WriteLine("SaveDeepImage=%s" % scriptDialog.GetValue("DeepImageBox"))
    writer.WriteLine("ExrCompressionType=%s" % scriptDialog.GetValue("EXRCompressionBox"))

    # Write 2020+ specific options
    version = int(scriptDialog.GetValue("VersionBox"))
    if version >= 2020:
        writer.WriteLine("ColorSpace=%s" % scriptDialog.GetValue("ColorSpaceBox"))
        writer.WriteLine("PremultipliedAlpha=%s" % scriptDialog.GetValue("PremultipliedAlphaBox"))
        writer.WriteLine("ForceToneMapping=%s" % scriptDialog.GetValue("ForceToneMappingBox"))
        writer.WriteLine("OcioColorSpaceName=%s" % scriptDialog.GetValue("OcioColorSpaceBox"))
        writer.WriteLine("OcioLookName=%s" % scriptDialog.GetValue("OcioLookBox"))

    writer.Close()

    # Setup the command line arguments.
    arguments = StringCollection()

    arguments.Add(jobInfoFilename)
    arguments.Add(pluginInfoFilename)

    # Now submit the job.
    results = ClientUtils.ExecuteCommandAndGetOutput(arguments)
    scriptDialog.ShowMessageBox(results, "Submission Results")