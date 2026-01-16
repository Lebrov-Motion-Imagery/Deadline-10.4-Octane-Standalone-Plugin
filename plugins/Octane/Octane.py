#!/usr/bin/env python3
from __future__ import absolute_import
import os
import platform
import subprocess

from itertools import chain
from six.moves import range

# Pipes is removed in python3, and its functionality is moved to shlex
try:
    from pipes import quote
except ImportError:
    from shlex import quote # type: ignore

from Deadline.Plugins import DeadlinePlugin, PluginType
from Deadline.Scripting import FileUtils, FrameUtils, PathUtils, RepositoryUtils, StringUtils


def GetDeadlinePlugin():
    return OctanePlugin()


def CleanupDeadlinePlugin(deadlinePlugin):
    deadlinePlugin.Cleanup()


class OctanePlugin(DeadlinePlugin):
    Framecount = 0
    
    # Task progress tracking (for multi-frame tasks)
    CompletedFrames = 0
    TotalFrames = 1
    CurrentFrameSampleProgress = 0.0

    def __init__(self):
        import sys
        if sys.version_info.major == 3:
            super().__init__()
        self.InitializeProcessCallback += self.InitializeProcess
        self.RenderExecutableCallback += self.RenderExecutable
        self.RenderArgumentCallback += self.RenderArgument
        self.PreRenderTasksCallback += self.PreRenderTasks
    
    def PreRenderTasks(self):
        """Initialize task progress tracking before each task starts."""
        self.CompletedFrames = 0
        self.TotalFrames = 1
        self.CurrentFrameSampleProgress = 0.0

    def Cleanup(self):
        for stdoutHandler in self.StdoutHandlers:
            del stdoutHandler.HandleCallback

        del self.InitializeProcessCallback
        del self.RenderExecutableCallback
        del self.RenderArgumentCallback
        del self.PreRenderTasksCallback

    # -------------------------------------------------------------------------
    # Stdout Handler Callbacks
    # -------------------------------------------------------------------------
    def HandleSampleProgress(self):
        """Handles sample progress: 'Samples: X/Y (Z%)'
        
        Calculates overall task progress as:
        (CompletedFrames + current_frame_progress) / TotalFrames * 100
        """
        current_samples = self.GetRegexMatch(1)
        total_samples = self.GetRegexMatch(2)
        progress_str = self.GetRegexMatch(3)
        try:
            frame_progress = float(progress_str) / 100.0  # Convert to 0-1 range
            self.CurrentFrameSampleProgress = frame_progress
            
            # Calculate overall task progress
            task_progress = ((self.CompletedFrames + frame_progress) / self.TotalFrames) * 100.0
            self.SetProgress(task_progress)
            
            # Status shows current frame sample info
            self.SetStatusMessage("Samples: {0}/{1} ({2:.1f}%)".format(
                current_samples, total_samples, float(progress_str)))
        except ValueError:
            pass

    def HandleFrameProgress(self):
        """Handles frame start: 'Rendering frame X of Y (Frame Z)'
        
        Updates TotalFrames from Lua script output and resets per-frame progress.
        """
        current_frame = self.GetRegexMatch(1)
        total_frames = self.GetRegexMatch(2)
        frame_number = self.GetRegexMatch(3)
        
        # Update total frames from the Lua script (more accurate than Deadline's frame list)
        try:
            self.TotalFrames = int(total_frames)
        except ValueError:
            pass
        
        # Reset per-frame sample progress
        self.CurrentFrameSampleProgress = 0.0
        
        self.SetStatusMessage("Frame {0}/{1} (#{2})".format(current_frame, total_frames, frame_number))

    def HandleFrameComplete(self):
        """Handles frame completion: 'Frame X completed'
        
        Increments completed frame count and updates task progress.
        """
        frame_number = self.GetRegexMatch(1)
        self.CompletedFrames += 1
        self.CurrentFrameSampleProgress = 0.0
        
        # Calculate task progress after frame completion
        task_progress = (self.CompletedFrames / self.TotalFrames) * 100.0
        self.SetProgress(task_progress)
        self.LogInfo("Frame {0} completed ({1}/{2})".format(frame_number, self.CompletedFrames, self.TotalFrames))

    def HandleSavingFile(self):
        """Handles file save path output."""
        file_path = self.GetRegexMatch(1)
        self.LogInfo("Saving: {0}".format(file_path))

    def HandleRenderStart(self):
        """Handles render start notification."""
        self.LogInfo("Octane batch render started")
        self.SetStatusMessage("Octane batch render started")

    def HandleRenderComplete(self):
        """Handles render complete notification."""
        self.LogInfo("Octane batch render completed")
        self.SetStatusMessage("Render complete")
        self.SetProgress(100)

    def HandleFrameRange(self):
        """Handles frame range output."""
        start_frame = self.GetRegexMatch(1)
        end_frame = self.GetRegexMatch(2)
        self.LogInfo("Frame range: {0} - {1}".format(start_frame, end_frame))

    def HandleWarning(self):
        """Handles warning messages."""
        warning_msg = self.GetRegexMatch(1)
        self.LogWarning("Octane: {0}".format(warning_msg))

    def HandleError(self):
        """Handles error messages."""
        error_msg = self.GetRegexMatch(1)
        self.LogWarning("Octane Error: {0}".format(error_msg))

    def HandleCanceled(self):
        """Handles render cancellation."""
        self.LogInfo("Octane render was canceled")
        self.SetStatusMessage("Render canceled")

    def InitializeProcess(self):
        self.PluginType = PluginType.Simple
        self.StdoutHandling = True
        self.PopupHandling = True
        self.UseProcessTree = True
        self.HideDosWindow = False
        self.CreateNewConsole = True

        framePerFileMode = self.GetBooleanPluginInfoEntryWithDefault("FramePerFileMode", False)
        if framePerFileMode:
            self.SingleFramesOnly = True
        else:
            self.SingleFramesOnly = False

        # Add stdout handlers to capture Lua script output and progress
        # Sample progress pattern: "Samples: X/Y (Z%)" - updates task progress bar
        self.AddStdoutHandlerCallback(r"Samples: (\d+)/(\d+) \((\d+\.?\d*)%\)").HandleCallback += self.HandleSampleProgress
        # Frame progress pattern: "Rendering frame X of Y (Frame Z)"
        self.AddStdoutHandlerCallback(r"Rendering frame (\d+) of (\d+) \(Frame (\d+)\)").HandleCallback += self.HandleFrameProgress
        # Frame completion pattern: "Frame X completed"
        self.AddStdoutHandlerCallback(r"Frame (\d+) completed").HandleCallback += self.HandleFrameComplete
        
        # Frame saving patterns (informational only)
        self.AddStdoutHandlerCallback(r"Saving multi-layer EXR to: (.*)").HandleCallback += self.HandleSavingFile
        self.AddStdoutHandlerCallback(r"Saving.*to: (.*)").HandleCallback += self.HandleSavingFile
        
        # Status patterns
        self.AddStdoutHandlerCallback(r"Starting batch render").HandleCallback += self.HandleRenderStart
        self.AddStdoutHandlerCallback(r"^Completed$").HandleCallback += self.HandleRenderComplete
        self.AddStdoutHandlerCallback(r"Frame range: (\d+) - (\d+)").HandleCallback += self.HandleFrameRange
        
        # Warning patterns
        self.AddStdoutHandlerCallback(r"Warning: (.*)").HandleCallback += self.HandleWarning
        self.AddStdoutHandlerCallback(r"WARNING: (.*)").HandleCallback += self.HandleWarning
        
        # Error patterns  
        self.AddStdoutHandlerCallback(r"ERROR.*: (.*)").HandleCallback += self.HandleError
        self.AddStdoutHandlerCallback(r"error: (.*)").HandleCallback += self.HandleError
        self.AddStdoutHandlerCallback(r"failed to (.*)").HandleCallback += self.HandleError
        
        # Canceled pattern
        self.AddStdoutHandlerCallback(r"^Canceled$").HandleCallback += self.HandleCanceled

    def RenderExecutable(self):
        version = self.GetPluginInfoEntryWithDefault("Version", "4").strip()
        return self.GetRenderExecutable( "Octane_RenderExecutable{0}".format(version), "Octane " + version )

    @staticmethod
    def quote_cmdline_args(cmdline):
        """
        A helper function used to quote commandline arguments as needed on a case-by-case basis (args with spaces, escape characters, etc.)

        :param cmdline: The list of commandline arguments
        :return: a string composed of the commandline arguments, quoted properly
        """
        if platform.system() == 'Windows':
            return subprocess.list2cmdline(cmdline)
        else:
            return " ".join(quote(arg) for arg in cmdline)

    def RenderArgument(self):
        """
        Builds up the commandline render arguments as a list which then gets transformed into string

        :return: a string of commandline arguments
        """
        scene_file = self.GetPluginInfoEntry("SceneFile")
        scene_file = PathUtils.ToPlatformIndependentPath(RepositoryUtils.CheckPathMapping(scene_file))

        render_args = ['--no-gui']

        frame_per_file_mode = self.GetBooleanPluginInfoEntryWithDefault("FramePerFileMode", False)
        if frame_per_file_mode:
            # Octane 1 workflow that's still supported in 2 and onward.
            temp_render_args, scene_file = self.get_frame_per_file_render_arguments()
            render_args.extend(temp_render_args)
        else:
            render_args.extend(self.get_script_render_arguments())

        additional_args = self.GetPluginInfoEntryWithDefault("AdditionalArgs", "").strip()
        if additional_args:
            render_args.append(additional_args)

        render_args.extend(self.get_gpu_render_arguments())
        render_args.append(scene_file)

        return self.quote_cmdline_args(render_args)

    def get_script_render_arguments_3(self):
        """
        Generates the render arguments for the octane lua script workflow. Octane 2 and 3.

        :return: a list of commandline arguments
        """
        output_folder = self.GetPluginInfoEntryWithDefault("OutputFolder", "")
        output_folder = PathUtils.ToPlatformIndependentPath(RepositoryUtils.CheckPathMapping(output_folder))

        lua_script = os.path.join(self.GetPluginDirectory(), "DeadlineOctane3.lua")
        filename_template = self.GetPluginInfoEntryWithDefault("FilenameTemplate", "")
        file_format = self.GetPluginInfoEntryWithDefault("FileFormat", "png8")

        render_target_ocs = self.GetPluginInfoEntryWithDefault("RenderTargetOCS", "")
        render_target_orbx = self.GetPluginInfoEntryWithDefault("RenderTargetORBX", "")
        render_target = ""
        if render_target_ocs:
            render_target = render_target_ocs
        elif render_target_orbx:
            render_target = render_target_orbx

        render_args = [
            '-q',
            '--script', lua_script,
            '-a', filename_template,
            '-a', output_folder,
            '-a', file_format,
            '-a', str(self.GetStartFrame()),
            '-a', str(self.GetEndFrame()),
            '-a', render_target,
            '--stop-after-script',
        ]

        sample = self.GetIntegerPluginInfoEntryWithDefault("OverrideSampling", 0)
        if sample > 0:
            render_args.extend(['-s', str(sample)])

        if render_target:
            render_args.extend(['-t', render_target])

        return render_args

    def get_script_render_arguments_4(self):
        """
        Generates the render arguments for the octane lua script workflow. Octane 4.

        :return: a list of commandline arguments
        """
        output_folder = self.GetPluginInfoEntryWithDefault("OutputFolder", "")
        output_folder = PathUtils.ToPlatformIndependentPath(RepositoryUtils.CheckPathMapping(output_folder))

        lua_script = os.path.join(self.GetPluginDirectory(), "DeadlineOctane4.lua")

        render_target_ocs = self.GetPluginInfoEntryWithDefault("RenderTargetOCS", "")
        render_target_orbx = self.GetPluginInfoEntryWithDefault("RenderTargetORBX", "")
        render_target = ""

        if render_target_ocs:
            render_target = render_target_ocs
        elif render_target_orbx:
            render_target = render_target_orbx

        octane_args = {
            ## absolute path of the current project
            "projectPath": "nil",
            ## the copied scene graph
            # "sceneGraph": "nil",
            "fileFormat": self.GetPluginInfoEntryWithDefault("FileFormat", "EXR (16-bit) Untonemapped"),
            ## absolute path to the output directory of the rendered images
            "outputDirectory": output_folder,
            ## max samples/px
            "maxSamples": self.GetIntegerPluginInfoEntryWithDefault("OverrideSampling", 0),
            ## filename template for the output files
            "template": self.GetPluginInfoEntryWithDefault("FilenameTemplate", "%n_%p_%f_%s.%e"),
            ## start frame of the animation (s)
            "startFrame": str(self.GetStartFrame()),
            ## end frame of the animation (s)
            "endFrame": str(self.GetEndFrame()),
            ## openExr compression Type
            "exrCompressionType": self.GetPluginInfoEntryWithDefault("ExrCompressionType", "ZIP (lossless)"),
            ## skip existing files
            "skipExisting": self.GetBooleanPluginInfoEntryWithDefault("SkipExisting", False),
            ## save all enabled render passes
            "saveAllPasses": self.GetBooleanPluginInfoEntryWithDefault("SaveAllPasses", False),
            ## save the render passes as a layered exr
            "saveMultiLayerExr": self.GetBooleanPluginInfoEntryWithDefault("SaveLayeredEXRBox", False),
            ## save additional deep image output
            "saveDeepImage": self.GetBooleanPluginInfoEntryWithDefault("SaveDeepImage", False),
            ## generate Composite Project for photoshop
            "generateCompositePrj": self.GetBooleanPluginInfoEntryWithDefault("GenerateCompositeProjectFile", False),
            ## saves denoiser output as main passes if enabled
            "saveDeBeautyAsMain": self.GetBooleanPluginInfoEntryWithDefault("SaveDenoisedMainPass", False),
        }

        octane_lua_args_filename = os.path.join(self.GetPluginDirectory(), "octane_lua_args.txt")
        delimiter = '='
        with open(octane_lua_args_filename, 'w') as the_file:
            for key, val in octane_args.items():
                if delimiter in key or (isinstance(val, str) and delimiter in val):
                    raise ValueError(
                        "The delimiter({delimiter}) cannot be part of the key({key}) or value({val})".format(
                            delimiter=delimiter, key=key, val=val))
                if isinstance(val, bool):
                    # Lua expects bools to be lowercase
                    val = str(val).lower()
                the_file.write('{key}{delimiter}{val}\n'.format(key=key, delimiter=delimiter, val=val))

        # Apply Deadline path mapping to any paths written into the Lua args file.
        # This ensures output directories are mapped on the worker.
        try:
            RepositoryUtils.CheckPathMappingInFileAndReplace(
                octane_lua_args_filename, octane_lua_args_filename, [], []
            )
        except Exception as e:
            self.LogWarning("Failed to apply path mapping to Lua args file: {0}".format(e))

        render_args = [
            '-q',
            '--script', lua_script,
            '-a', octane_lua_args_filename,
            '--stop-after-script',
        ]
        sample = self.GetIntegerPluginInfoEntryWithDefault("OverrideSampling", 0)
        if sample > 0:
            render_args.extend(['-s', str(sample)])

        if render_target:
            render_args.extend(['-t', render_target])
        return render_args

    def get_script_render_arguments_2026(self):
        """
        Generates the render arguments for the octane lua script workflow. Octane 2026.1.
        Uses updated API with imageSaveFormat, saveRenderPassesMultiExr3, etc.

        :return: a list of commandline arguments
        """
        output_folder = self.GetPluginInfoEntryWithDefault("OutputFolder", "")
        output_folder = PathUtils.ToPlatformIndependentPath(RepositoryUtils.CheckPathMapping(output_folder))

        lua_script = os.path.join(self.GetPluginDirectory(), "DeadlineOctane2026.1.lua")

        render_target_ocs = self.GetPluginInfoEntryWithDefault("RenderTargetOCS", "")
        render_target_orbx = self.GetPluginInfoEntryWithDefault("RenderTargetORBX", "")
        render_target = ""

        if render_target_ocs:
            render_target = render_target_ocs
        elif render_target_orbx:
            render_target = render_target_orbx

        # Map old file format names to new format names for 2026.1 API
        file_format = self.GetPluginInfoEntryWithDefault("FileFormat", "EXR_16")
        file_format_map = {
            "png8": "PNG_8",
            "png16": "PNG_16",
            "exr": "EXR_32",
            "exrtonemapped": "EXR_32",
            "PNG (8-bit)": "PNG_8",
            "PNG (16-bit)": "PNG_16",
            "EXR (16-bit) Untonemapped": "EXR_16",
            "EXR (16-bit) Tonemapped": "EXR_16",
            "EXR (32-bit) Untonemapped": "EXR_32",
            "EXR (32-bit) Tonemapped": "EXR_32",
        }
        # Convert old format names to new ones, or keep as-is if already in new format
        file_format = file_format_map.get(file_format, file_format)

        # Determine if tone mapping should be forced based on old format name
        original_format = self.GetPluginInfoEntryWithDefault("FileFormat", "EXR_16")
        force_tone_mapping = "Tonemapped" in original_format or "tonemapped" in original_format

        octane_args = {
            ## absolute path of the current project
            "projectPath": "nil",
            ## image save format (new API format names)
            "fileFormat": file_format,
            "imageSaveFormat": file_format,
            ## absolute path to the output directory of the rendered images
            "outputDirectory": output_folder,
            ## max samples/px
            "maxSamples": self.GetIntegerPluginInfoEntryWithDefault("OverrideSampling", 0),
            ## filename template for the output files
            "template": self.GetPluginInfoEntryWithDefault("FilenameTemplate", "%n_%p_%f_%s.%e"),
            ## start frame of the animation
            "startFrame": str(self.GetStartFrame()),
            ## end frame of the animation
            "endFrame": str(self.GetEndFrame()),
            ## openExr compression Type
            "exrCompressionType": self.GetPluginInfoEntryWithDefault("ExrCompressionType", "ZIP (lossless)"),
            ## openExr compression level (for DWA compression)
            "exrCompressionLevel": self.GetIntegerPluginInfoEntryWithDefault("ExrCompressionLevel", 45),
            ## JPEG quality
            "jpegQuality": self.GetIntegerPluginInfoEntryWithDefault("JpegQuality", 75),
            ## skip existing files
            "skipExisting": self.GetBooleanPluginInfoEntryWithDefault("SkipExisting", False),
            ## save all enabled render passes
            "saveAllPasses": self.GetBooleanPluginInfoEntryWithDefault("SaveAllPasses", False),
            ## save the render passes as a layered exr
            "saveMultiLayerExr": self.GetBooleanPluginInfoEntryWithDefault("SaveLayeredEXRBox", False),
            ## save additional deep image output
            "saveDeepImage": self.GetBooleanPluginInfoEntryWithDefault("SaveDeepImage", False),
            ## generate Composite Project for photoshop
            "generateCompositePrj": self.GetBooleanPluginInfoEntryWithDefault("GenerateCompositeProjectFile", False),
            ## saves denoiser output as main passes if enabled
            "saveDeBeautyAsMain": self.GetBooleanPluginInfoEntryWithDefault("SaveDenoisedMainPass", False),
            ## use premultiplied alpha when saving exr or tiff
            "premultipliedAlpha": self.GetBooleanPluginInfoEntryWithDefault("PremultipliedAlpha", True),
            ## color space (SRGB, LINEAR_SRGB, ACES2065_1, ACESCG, OCIO)
            "colorSpace": self.GetPluginInfoEntryWithDefault("ColorSpace", "LINEAR_SRGB"),
            ## OCIO color space name (if using OCIO)
            "ocioColorSpaceName": self.GetPluginInfoEntryWithDefault("OcioColorSpaceName", ""),
            ## OCIO look name (if using OCIO)
            "ocioLookName": self.GetPluginInfoEntryWithDefault("OcioLookName", ""),
            ## force tone mapping
            "forceToneMapping": self.GetBooleanPluginInfoEntryWithDefault("ForceToneMapping", force_tone_mapping),
        }

        octane_lua_args_filename = os.path.join(self.GetPluginDirectory(), "octane_lua_args.txt")
        delimiter = '='
        with open(octane_lua_args_filename, 'w') as the_file:
            for key, val in octane_args.items():
                if delimiter in key or (isinstance(val, str) and delimiter in val):
                    raise ValueError(
                        "The delimiter({delimiter}) cannot be part of the key({key}) or value({val})".format(
                            delimiter=delimiter, key=key, val=val))
                if isinstance(val, bool):
                    # Lua expects bools to be lowercase
                    val = str(val).lower()
                the_file.write('{key}{delimiter}{val}\n'.format(key=key, delimiter=delimiter, val=val))

        # Apply Deadline path mapping to any paths written into the Lua args file.
        # This ensures output directories are mapped on the worker.
        try:
            RepositoryUtils.CheckPathMappingInFileAndReplace(
                octane_lua_args_filename, octane_lua_args_filename, [], []
            )
        except Exception as e:
            self.LogWarning("Failed to apply path mapping to Lua args file: {0}".format(e))

        render_args = [
            '-q',
            '--script', lua_script,
            '-a', octane_lua_args_filename,
            '--stop-after-script',
        ]
        sample = self.GetIntegerPluginInfoEntryWithDefault("OverrideSampling", 0)
        if sample > 0:
            render_args.extend(['-s', str(sample)])

        if render_target:
            render_args.extend(['-t', render_target])
        return render_args

    def get_script_render_arguments(self):
        """
        Generates the render arguments for the octane lua script workflow. Octane 2 and later.

        :return: a list of commandline arguments
        """
        version = self.GetPluginInfoEntryWithDefault("Version", "4")
        # Handle version strings like "2026" or "2026.1"
        version_int = int(version.split('.')[0]) if '.' in version else int(version)
        if version_int <= 3:
            return self.get_script_render_arguments_3()
        elif version_int >= 2020:
            # Octane 2020 and later (including 2021, 2023, 2026) use new API
            return self.get_script_render_arguments_2026()
        else:
            return self.get_script_render_arguments_4()

    def get_frame_per_file_render_arguments(self):
        """
        Generates the render arguments for when FramePerFile mode is set to True.
        This means that each output frame has an associated scene file with the same frame number.
        This is mostly used in Octane 1 before .orbx was a thing.

        :return: a list of commandline arguments, and the scene file
        """
        render_args = ['-e', '-q']

        sceneFile = self.GetPluginInfoEntry("SceneFile")
        sceneFile = PathUtils.ToPlatformIndependentPath(RepositoryUtils.CheckPathMapping(sceneFile))
        outputFile = self.CreateOutputFile()

        paddingSize = 0
        if not self.GetBooleanPluginInfoEntryWithDefault("SingleFile", True):
            currPadding = FrameUtils.GetFrameStringFromFilename(sceneFile)
            paddingSize = len(currPadding)

            if paddingSize > 0:
                newPadding = StringUtils.ToZeroPaddedString(self.GetStartFrame(), paddingSize, False)
                sceneFile = FrameUtils.SubstituteFrameNumber(sceneFile, newPadding)

        # Build the new output file name.
        if outputFile:
            outputFile = PathUtils.ToPlatformIndependentPath(RepositoryUtils.CheckPathMapping(outputFile))

            # Add padding to output file if necessary.
            if paddingSize > 0:
                outputFile = FrameUtils.SubstituteFrameNumber(outputFile, newPadding)
                outputPath = os.path.dirname(outputFile)
                outputFileName, outputExtension = os.path.splitext(outputFile)

                outputFile = os.path.join(outputPath, outputFileName + newPadding + outputExtension)

            render_args.extend(['-o', outputFile])

        sample = self.GetIntegerPluginInfoEntryWithDefault("OverrideSampling", 0)
        if sample > 0:
            render_args.extend(['-s', str(sample)])

        render_target = self.GetPluginInfoEntryWithDefault("RenderTargetOCS", "")
        if render_target:
            render_args.extend(['-t', render_target])

        return render_args, sceneFile

    def get_gpu_render_arguments(self):
        """
        Determines which gpus to use for the render and creates the corresponding commandline arguments.

        ie. Using GPUs 0, 2, and 3 would look like:
        commandline args: -g 0 -g 2 -g 3
        python list: ['-g', '0', '-g', '2', '-g', '3']

        :return: A list containing the gpu commandline arguments
        """
        result_gpus = []
        gpus_per_task = self.GetIntegerPluginInfoEntryWithDefault("GPUsPerTask", 0)
        gpus_select_devices = self.GetPluginInfoEntryWithDefault("GPUsSelectDevices", "")

        use_select_devices = gpus_select_devices and gpus_per_task == 0
        use_gpus_per_task = not use_select_devices and gpus_per_task > 0

        if self.OverrideGpuAffinity():
            # Ensure the gpu entries are all stringify'd to match other workflows
            override_gpus = [str(gpu) for gpu in self.GpuAffinity()]
            if use_select_devices:
                gpus = gpus_select_devices.split(",")
                not_found_gpus = []
                for gpu in gpus:
                    if gpu in override_gpus:
                        result_gpus.append(gpu)
                    else:
                        not_found_gpus.append(gpu)

                if len(not_found_gpus) > 0:
                    self.LogWarning("The Worker is overriding its GPU affinity and the following GPUs do not match the Workers affinity so they will not be used: {0}".format(",".join(not_found_gpus)))
                if len(result_gpus) == 0:
                    self.FailRender("The Worker does not have affinity for any of the GPUs specified in the job.")
            elif use_gpus_per_task:
                if gpus_per_task > len(override_gpus):
                    self.LogWarning("The Worker is overriding its GPU affinity and the Worker only has affinity for {0} Workers of the {1} requested.").format(str(len(override_gpus)), str(gpus_per_task))
                    result_gpus = override_gpus
                else:
                    result_gpus = list(override_gpus)[:gpus_per_task]
            else:
                result_gpus = override_gpus

            self.LogInfo("The Worker is overriding the GPUs to render using so the following GPUs will be used: {0}".format(",".join(result_gpus)))

        elif use_select_devices:
            self.LogInfo("Specific GPUs specified, so the following GPUs will be used: {0}".format(gpus_select_devices))
            result_gpus = gpus_select_devices.split(",")

        elif use_gpus_per_task:
            for i in range((self.GetThreadNumber() * gpus_per_task),
                           (self.GetThreadNumber() * gpus_per_task) + gpus_per_task):
                result_gpus.append(str(i))
            self.LogInfo("GPUs per task is greater than 0, so the following GPUs will be used: {0}".format(
                ",".join(result_gpus)))

        # input:  ['0', '2', '3']
        # output: ['-g', '0', '-g', '2', '-g', '3']
        return list(chain.from_iterable(('-g', gpu) for gpu in result_gpus))

    def CreateOutputFile(self):
        outputFile = self.GetPluginInfoEntryWithDefault("OutputFolder", "")

        if outputFile[-1:] != "\\":
            outputFile += "\\"

        fileFormat = self.GetPluginInfoEntryWithDefault("FileFormat", "png8")

        if fileFormat in ("png8", "png16"):
            fileFormat = "png"
        elif fileFormat == "exrtonemapped":
            fileFormat = "exr"

        filenameTemplate = self.GetPluginInfoEntryWithDefault("FilenameTemplate", "")
        filenameTemplate = filenameTemplate.replace("%e", fileFormat)
        outputFile += filenameTemplate

        return outputFile
