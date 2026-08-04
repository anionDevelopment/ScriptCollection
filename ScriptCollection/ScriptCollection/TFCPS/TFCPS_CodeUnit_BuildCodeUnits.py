import os
import json
import re
import socket
from datetime import datetime, timedelta,timezone
import xmlschema
import yaml
from packaging.version import Version
from ..GeneralUtilities import GeneralUtilities
from ..ScriptCollectionCore import ScriptCollectionCore
from ..SCLog import  LogLevel
from .TFCPS_BuildCodeUnitsHook import TFCPS_BuildCodeUnitsHook
from .TFCPS_CodeUnit_BuildCodeUnit import TFCPS_CodeUnit_BuildCodeUnit
from .TFCPS_OCIImageSecretScan import TFCPS_OCIImageSecretScan
from .TFCPS_Tools_General import TFCPS_Tools_General


class TFCPS_UpdateDependenciesHook(TFCPS_BuildCodeUnitsHook):
    """Updates the dependencies of the repository and of its codeunits while the codeunits are built.
    The dependency-update is implemented as a hook of the regular codeunit-build (and not as an own reduced build-process, which is how
    it was implemented before) so that it runs with exactly the same preparation as a normal build: the required environment-variables
    are set, the custom pre-codeunit-build-script runs and therefore the package-sources which are needed to resolve the dependencies of
    a codeunit are available. Without that preparation an update fails as soon as a codeunit has a dependency which is not available on a
    public package-source - which was the case for an update inside a build-container."""

    __sc: ScriptCollectionCore = None
    __tfcps_tools_general: TFCPS_Tools_General = None

    def __init__(self, sc: ScriptCollectionCore, tfcps_tools_general: TFCPS_Tools_General):
        self.__sc = sc
        self.__tfcps_tools_general = tfcps_tools_general

    @GeneralUtilities.check_arguments
    def run_after_preparation(self, repository: str) -> None:
        update_dependencies_script_folder: str = os.path.join(repository, "Other", "Scripts")
        if os.path.isfile(os.path.join(update_dependencies_script_folder, "UpdateDependencies.py")):
            self.__sc.log.log("Update dependencies of the repository...")
            self.__sc.run_program(GeneralUtilities.get_python_executable(), "UpdateDependencies.py", update_dependencies_script_folder)

    @GeneralUtilities.check_arguments
    def run_after_codeunit_was_built(self, codeunit_build: TFCPS_CodeUnit_BuildCodeUnit) -> None:
        codeunit_name: str = codeunit_build.codeunit_name
        codeunit_folder: str = codeunit_build.codeunit_folder
        repository: str = codeunit_build.repository_folder
        if not self.__tfcps_tools_general.codeunit_has_updatable_dependencies(os.path.join(codeunit_folder, f"{codeunit_name}.codeunit.xml")):
            return
        self.__sc.log.log(f"Update dependencies of codeunit {codeunit_name}...")
        self.__sc.run_program(GeneralUtilities.get_python_executable(), "UpdateDependencies.py", os.path.join(codeunit_folder, "Other"))
        if self.__sc.git_repository_has_uncommitted_changes(repository):
            #the update changed something, so it has to be verified that the codeunit is still buildable with the updated dependencies.
            self.__sc.log.log(f"Build codeunit {codeunit_name} again to verify it is still buildable with the updated dependencies...")
            codeunit_build.build_codeunit()

class TFCPS_CodeUnit_BuildCodeUnits:
    repository:str=None
    tfcps_tools_general:TFCPS_Tools_General=None 
    sc:ScriptCollectionCore=None
    target_environment_type:str=None
    additionalargumentsfile:str=None
    __use_cache:bool = None
    __is_pre_merge:bool = None
    __assert_no_new_changes:bool = None
    __add_ready_to_merge_flag:bool = None
    __fast_lane:bool = None

    def __init__(self,repository:str,loglevel:LogLevel,target_environment_type:str,additionalargumentsfile:str,use_cache:bool,is_pre_merge:bool,assertnonewchanges:bool,add_ready_to_merge_flag:bool=False,fast_lane:bool=False):
        self.sc=ScriptCollectionCore()
        self.sc.log.loglevel=loglevel
        self.__use_cache=use_cache
        self.sc.assert_is_git_repository(repository)
        self.repository=repository
        self.tfcps_tools_general:TFCPS_Tools_General=TFCPS_Tools_General(self.sc)
        allowed_target_environment_types=["Development","QualityCheck","Productive"]
        GeneralUtilities.assert_condition(target_environment_type in allowed_target_environment_types,"Unknown target-environment-type. Allowed values are: "+", ".join(allowed_target_environment_types))
        self.target_environment_type=target_environment_type
        self.additionalargumentsfile=additionalargumentsfile
        self.__is_pre_merge=is_pre_merge
        self.__assert_no_new_changes=assertnonewchanges
        self.__add_ready_to_merge_flag=add_ready_to_merge_flag
        self.__fast_lane=fast_lane

    @GeneralUtilities.check_arguments
    def build_codeunits(self, hook: TFCPS_BuildCodeUnitsHook = None) -> None:
        """Builds all codeunits of the repository. The optional hook allows a caller inside ScriptCollection to run additional actions
        between the regular build-steps (see TFCPS_BuildCodeUnitsHook); a caller which only wants to build passes nothing."""
        if hook is None:
            hook = TFCPS_BuildCodeUnitsHook()
        self.sc.log.log(GeneralUtilities.get_line())
        start_time:datetime=GeneralUtilities.get_now()
        ready_to_merge_file=os.path.join(self.repository,".ScriptCollection",".IsReadyToMerge")
        error_occurred=False
        try:
            if self.__fast_lane:
                current_branch_name = self.sc.git_get_current_branch_name(self.repository)
                GeneralUtilities.assert_condition(self.sc.is_fix_branch(current_branch_name), f"Fastlane-builds are only allowed on branches whose name starts with 'fix/', but the current branch is '{current_branch_name}'.")

            #assert that the product-information-file exists
            product_information_file = os.path.join(self.repository, ".ScriptCollection", "ProductInformation.xml")
            GeneralUtilities.assert_file_exists(product_information_file, f"The file '{product_information_file}' does not exist.")

            #when the build runs inside a container, ensure the used SCBuilder-image is at least the version required by this repository (defined in .ScriptCollection/OCIImages/ImageDefinition.csv)
            if self.sc.is_runnning_in_container():
                scbuilder_version_environment_value = os.environ.get("SCBuilderVersion")
                GeneralUtilities.assert_condition(GeneralUtilities.string_has_content(scbuilder_version_environment_value), "The environment-variable 'SCBuilderVersion' is not set although the build runs inside a container (environment-variable 'ISRUNNINGINCONTAINER' is 'true').")
                required_scbuilder_version = Version(self.tfcps_tools_general.oci_image_manager.get_tag_for_image(self.repository, "SCBuilder"))
                version_match = re.search(r"\d+(\.\d+)+", scbuilder_version_environment_value)
                GeneralUtilities.assert_condition(version_match is not None, f"The environment-variable 'SCBuilderVersion' (value: '{scbuilder_version_environment_value}') does not contain a version-string.")
                actual_scbuilder_version = Version(version_match.group(0))
                GeneralUtilities.assert_condition(actual_scbuilder_version >= required_scbuilder_version, f"The used SCBuilder-version {actual_scbuilder_version} is older than the version {required_scbuilder_version} required by '{self.tfcps_tools_general.get_product_name(self.repository)}' (defined in .ScriptCollection/OCIImages/ImageDefinition.csv). Please update to a newer SCBuilder-image.")
            
            if self.is_pre_merge():
                GeneralUtilities.assert_condition(not self.__assert_no_new_changes,f"A pre-merge build can not be done with the assert-no-new-changes-option.")

            self.sc.git_set_local_configuration_value(self.repository, "core.autocrlf", "false")

            #ensure the artifacts-folder of the repository is git-ignored so build-results never show up as uncommitted changes
            self.sc.ensure_line_is_in_gitignore(self.repository, "Other/Resources/Artifacts")

            #ensure <repo>/.ScriptCollection/.gitignore is set up (ignores the cache-folder so cache-files never show up as uncommitted changes)
            self.sc.ensure_scriptcollection_gitignore_is_setup(self.repository)

            self.sc.log.log(f"Start building codeunits at {GeneralUtilities.datetime_to_string_for_readable_entry(start_time,False)}. (Target environment-type: {self.target_environment_type})")

            self.tfcps_tools_general.ensure_required_environment_variables_are_set(self.repository)

            self.__run_custom_pre_codeunit_build_script()

            if self.__assert_no_new_changes:
                self.sc.assert_no_uncommitted_changes(self.repository,"Can not build codeunit: There are uncommitted changes in the repository.")

            try:
                xmlschema.validate(product_information_file, "https://projects.aniondev.de/PublicProjects/Common/ProjectTemplates/-/raw/main/Conventions/RepositoryStructure/CommonProjectStructure/productinformation.xsd")
            except Exception as exception:
                self.sc.log.log_exception(f"'{product_information_file}' could not be validated against the XSD:", exception, LogLevel.Warning)

            #run prepare-script
            self.run_prepare_script()

            hook.run_after_preparation(self.repository)

            #check if changelog exists
            changelog_file=os.path.join(self.repository,"Other","Resources","Changelog",f"v{self.tfcps_tools_general.get_version_of_project(self.repository)}.md")
            GeneralUtilities.assert_file_exists(changelog_file,f"Changelogfile \"{changelog_file}\" does not exist. Try to create it for example using \"sccreatechangelogentry -m ...\".") 

            #mark current version as supported
            now = GeneralUtilities.get_now()
            project_version:str=self.tfcps_tools_general.get_version_of_project(self.repository)
            if not self.tfcps_tools_general.suport_information_exists(self.repository, project_version):
                amount_of_years_for_support:int=1
                support_time = timedelta(days=365*amount_of_years_for_support+30*3+1) 
                until = now + support_time
                until_day = datetime(until.year, until.month, until.day, 0, 0, 0)
                from_day = datetime(now.year, now.month, now.day, 0, 0, 0)
                self.tfcps_tools_general.mark_current_version_as_supported(self.repository,project_version,from_day,until_day)

            codeunits:list[str]=self.tfcps_tools_general.get_codeunits(self.repository)
            GeneralUtilities.assert_condition(0<len(codeunits),f"No codeunits found in repository {self.repository}.")
            self.sc.log.log("Codeunits will be built in the following order:")
            for codeunit_name in codeunits:
                self.sc.log.log(f"  - {codeunit_name}")
            for codeunit_name in codeunits:
                tFCPS_CodeUnit_BuildCodeUnit:TFCPS_CodeUnit_BuildCodeUnit = TFCPS_CodeUnit_BuildCodeUnit(os.path.join(self.repository,codeunit_name),self.sc.log.loglevel,self.target_environment_type,self.additionalargumentsfile,self.use_cache(),self.is_pre_merge(),self.__fast_lane)
                self.sc.log.log(GeneralUtilities.get_line())
                tFCPS_CodeUnit_BuildCodeUnit.build_codeunit()
                hook.run_after_codeunit_was_built(tFCPS_CodeUnit_BuildCodeUnit)

            self.sc.log.log(GeneralUtilities.get_line())

            self.search_for_secrets()
            self.__normalize_line_endings_of_common_files()
            self.tfcps_tools_general.generate_svg_files_from_plantuml_files_for_repository(self.repository, self.use_cache())

            if self.is_pre_merge():
                self.__translate()
                self.__collect_metrics()
                self.__generate_loc_diagram()

        except Exception:
            error_occurred=True
            raise
        finally:
            if error_occurred:
                GeneralUtilities.ensure_file_does_not_exist(ready_to_merge_file)
            else:
                if self.is_pre_merge():
                    GeneralUtilities.ensure_file_does_not_exist(ready_to_merge_file)#ensure it does not exist because the flag is not supposed to be on the main branch
                else:
                    if self.is_working_branch():
                        if self.add_ready_to_merge_flag():
                            GeneralUtilities.ensure_file_exists(ready_to_merge_file)


        if self.__assert_no_new_changes:
            self.sc.assert_no_uncommitted_changes(self.repository,"There are new uncommitted changes in the repository.")

        self.__create_artifacts_archive(codeunits)

        end_time:datetime=GeneralUtilities.get_now()
        duration=end_time-start_time
        self.sc.log.log(f"Finished building codeunits at {GeneralUtilities.datetime_to_string_for_readable_entry(end_time,False)}. (Duration: {GeneralUtilities.timedelta_to_simple_string(duration)})")
        self.sc.log.log(GeneralUtilities.get_line())

    @GeneralUtilities.check_arguments
    def __create_artifacts_archive(self, codeunits:list[str]) -> str:
        product_name:str=self.tfcps_tools_general.get_product_name(self.repository)
        product_version:str=self.tfcps_tools_general.get_version_of_project(self.repository)
        target_folder:str=os.path.join(self.repository,"Other","Resources","Artifacts")
        target_file_zip:str=os.path.join(target_folder,f"{product_name}_Artifacts_v{product_version}.zip")
        target_file_infotxt:str=os.path.join(target_folder,f"{product_name}_Artifacts_v{product_version}.information.txt")

        artifacts_folders:dict[str,str]={}
        for codeunit_name in codeunits:
            artifacts_folder = os.path.join(self.repository, codeunit_name, "Other", "Artifacts")
            GeneralUtilities.assert_folder_exists(artifacts_folder,f"The artifacts-folder '{artifacts_folder}' of codeunit '{codeunit_name}' does not exist.")
            artifacts_folders[codeunit_name]=artifacts_folder

        GeneralUtilities.ensure_directory_exists(target_folder)
        GeneralUtilities.ensure_file_does_not_exist(target_file_zip)#ensure the archive of a previous build gets replaced
        self.sc.create_zip_archive_of_folders(artifacts_folders,target_file_zip)

        hash_of_zip_file:str=GeneralUtilities.get_sha256_of_file(target_file_zip)
        creation_timestamp:datetime=GeneralUtilities.get_now()
        GeneralUtilities.ensure_file_does_not_exist(target_file_infotxt)
        GeneralUtilities.ensure_file_exists(target_file_infotxt)
        information_lines:list[str]=[
            f"Product: {product_name}",
            f"Version: {product_version}",
            f"Artifacts-archive-hash: {hash_of_zip_file}",
            f"Creation-timestamp: {GeneralUtilities.datetime_to_string_for_readable_entry(creation_timestamp,False)}",
        ]
        GeneralUtilities.write_lines_to_file(target_file_infotxt,information_lines)
        normalized_relative_path=GeneralUtilities.normalize_path(os.path.relpath(target_file_zip, self.repository).replace("\\","/"))
        self.sc.log.log(f"Created artifacts-archive \"{normalized_relative_path}\":")
        for information_line in information_lines:
            self.sc.log.log(f"  {information_line}")

    @GeneralUtilities.check_arguments
    def __normalize_line_endings_of_common_files(self) -> None:
        #TODO add option to define exceptions (means: files which should not be normalized).
        self.sc.format_xml_file(os.path.join(self.repository, ".ScriptCollection", "ProductInformation.xml"))
        for codeunit in self.tfcps_tools_general.get_codeunits(self.repository):
            self.sc.format_xml_file(os.path.join(self.repository, codeunit, f"{codeunit}.codeunit.xml"))
        workspace_file = os.path.join(self.repository, f"{self.tfcps_tools_general.get_product_name(self.repository)}.code-workspace")
        if os.path.isfile(workspace_file):
            self.sc.format_json_file(workspace_file)
        self.sc.normalize_line_endings_of_files_in_folder(self.repository, ["txt", "md", "json", "xml", "csv", "yml", "yaml", "toml","gitignore", "gitattributes", "code-workspace"])

    @GeneralUtilities.check_arguments
    def is_working_branch(self)->bool:
        if self.sc.git_repository_has_uncommitted_changes(self.repository):
            return True
        if self.sc.git_get_current_branch_name(self.repository) != "main":
            return True
        return False

    @GeneralUtilities.check_arguments
    def __get_build_arguments(self, repository: str) -> list[str]:
        """Returns the arguments which describe the current build. They are passed to every script which is called by this build
        (the prepare-script of the repository as well as the optional user-specific custom scripts), so such a script can behave
        differently depending on the repository and the target-environment-type it is called for."""
        result: list[str] = ["--repository", repository, "--targetenvironmenttype", self.target_environment_type, "--verbosity", str(int(self.sc.log.loglevel))]
        if GeneralUtilities.string_has_content(self.additionalargumentsfile):
            result = result+["--additionalargumentsfile", self.additionalargumentsfile]
        if not self.__use_cache:
            if self.sc.git_repository_has_uncommitted_changes(repository):
                self.sc.log.log("No-cache-option can not be applied because there are uncommited changes in the repository.", LogLevel.Warning)
            else:
                result = result+["--nocache"]
        return result

    @GeneralUtilities.check_arguments
    def __run_custom_pre_codeunit_build_script(self) -> None:
        """Runs the optional user-specific script which prepares this machine for a codeunit-build. The script is located in
        '~/.ScriptCollection/TFCPS', so it is outside of any repository and is not part of a product's sourcecode.
        Which script is used depends on where the build runs, because both cases need different preparation-steps:
        - build directly on the host ('scbuildcodeunits'): 'CustomPreCodeUnitBuildScript.py'
        - build inside the container ('scbuildcodeunitsc' or a build-pipeline): 'CustomPreCodeUnitBuildScriptInContainer.py', located in
          the folder returned by TFCPS_Tools_General.get_custom_scripts_folder_for_container(). It is searched in the folder into which
          'scbuildcodeunitsc' mounts that whole folder and - if it is not there - directly in the configuration-folder, because a
          build-runner usually gets the whole configuration-folder mounted instead (see the article 'Build-runner-configuration'). The
          script which the host itself runs before it starts the container is 'CustomPreCodeUnitBuildScriptForContainer.py' and is
          therefore run there and not here."""
        if self.sc.is_runnning_in_container():
            script_file: str = os.path.join(self.tfcps_tools_general.get_folder_of_custom_scripts_in_container(), "CustomPreCodeUnitBuildScriptInContainer.py")
            if not os.path.isfile(script_file):
                script_file = os.path.join(self.tfcps_tools_general.get_custom_scripts_folder_for_container(), "CustomPreCodeUnitBuildScriptInContainer.py")
        else:
            script_file: str = self.tfcps_tools_general.get_custom_script_file("CustomPreCodeUnitBuildScript.py")
        self.tfcps_tools_general.run_custom_script_if_available(script_file, self.__get_build_arguments(self.repository))

    @GeneralUtilities.check_arguments
    def run_prepare_script(self):
        args = self.__get_build_arguments(self.repository)
        if  os.path.isfile( os.path.join(self.repository,"Other","Scripts","PrepareBuildCodeunits.py")):
            self.sc.log.log("Prepare build codeunits...")
            self.sc.run_program_argsasarray(GeneralUtilities.get_python_executable(),["PrepareBuildCodeunits.py"]+args, os.path.join(self.repository,"Other","Scripts"),print_live_output=True)

    @GeneralUtilities.check_arguments
    def build_codeunits_in_container(self,base_mount_folder:str) -> tuple[bool, str]:
        #base_mount_folder is assumed to be an absolute path set correctly by the caller (see BuildCodeUnitsC in Executables.py, which defaults it to the repository itself).
        #it may be the repository itself or any parent-folder of it, which allows the caller to mount not only the repository but the whole surrounding folder-structure into the container.
        normalized_base_mount_folder = os.path.normpath(base_mount_folder)
        normalized_repository = os.path.normpath(self.repository)
        relative_repository_path = os.path.relpath(normalized_repository, normalized_base_mount_folder).replace(os.sep, "/")
        GeneralUtilities.assert_condition(relative_repository_path == "." or not relative_repository_path.startswith(".."), f"The repository '{self.repository}' is not located inside the base-mount-folder '{base_mount_folder}'.")
        container_base_mount_folder = f"/Workspace/Project/{os.path.basename(normalized_base_mount_folder)}"
        container_repository_folder = container_base_mount_folder if relative_repository_path == "." else f"{container_base_mount_folder}/{relative_repository_path}"
        image = self.tfcps_tools_general.oci_image_manager.get_registry_address_for_image_with_default_tag(self.repository, "SCBuilder")

        #build the scbuildcodeunits-arguments based on the current state (analogous to the arguments accepted by the scbuildcodeunits-executable). each token must be a separate argument because run_program_argsasarray passes every list-element verbatim and does not split on spaces.
        scbuildcodeunits_arguments = ["scbuildcodeunits", "-r", container_repository_folder, "-v", "4"]
        if not self.__use_cache:
            scbuildcodeunits_arguments.append("-c")
        if self.__is_pre_merge:
            scbuildcodeunits_arguments.append("-p")
        if self.__assert_no_new_changes:
            scbuildcodeunits_arguments.append("-u")
        if self.__add_ready_to_merge_flag:
            scbuildcodeunits_arguments.append("-m")
        if self.__fast_lane:
            scbuildcodeunits_arguments.append("-f")
        if GeneralUtilities.string_has_content(self.additionalargumentsfile):
            scbuildcodeunits_arguments += ["-a", self.__translate_path_into_container(self.additionalargumentsfile, container_repository_folder)]

        update_scriptcollection=True
        update_argument:str=""
        if update_scriptcollection:
            update_argument="pip3 install scriptcollection --upgrade && "
        scbuildcodeunits_arguments=["bash","-c", f"{update_argument}scshowversion && "+" ".join(scbuildcodeunits_arguments)]

        #run the optional user-specific script which prepares this host for a container-build (for example to log in to the registry the image is pulled from).
        #it runs before the environment-variables are resolved, so it can also create the files their values are read from.
        self.tfcps_tools_general.run_custom_script_if_available(self.tfcps_tools_general.get_custom_script_file("CustomPreCodeUnitBuildScriptForContainer.py"), self.__get_build_arguments(self.repository))

        #mount the optional user-specific scripts which prepare the container itself. the whole folder (not only the pre-codeunit-build-hook
        #itself) is mounted, so the hook can start a sibling script placed next to it (for example to keep the hook independent of a
        #package it only installs, while the actual preparation-logic which needs that package lives in the sibling script; see
        #get_custom_scripts_folder_for_container). The mount is writable (not read-only) because the scripts in that folder also use it as
        #their own download-cache-folder. The build inside the container runs the hook (see __run_custom_pre_codeunit_build_script); if the
        #folder does not exist on the host nothing is mounted and nothing is run.
        mount_arguments: list[str] = []
        custom_scripts_folder_for_inside_the_container: str = self.tfcps_tools_general.get_custom_scripts_folder_for_container()
        if os.path.isdir(custom_scripts_folder_for_inside_the_container):
            mount_arguments += ["-v", f"{custom_scripts_folder_for_inside_the_container}:{self.tfcps_tools_general.get_folder_of_custom_scripts_in_container()}"]

        #pass the environment-variables which are declared as required in <repository>/.ScriptCollection/ProductInformation.xml into the container
        #so they do not have to be specified explicitly on every scbuildcodeunits-call. Their values are resolved from the user-specific
        #configuration-file (see TFCPS_Tools_General.get_environment_variables_configuration_file), which only exists on the host.
        #only the names are passed as arguments; the values are given to the docker-client through its own environment, because arguments
        #are written to the log and are visible in the process-list of this host, which must not happen for a value which is typically a secret.
        required_environment_variables: dict[str, str] = self.tfcps_tools_general.get_required_environment_variables(self.repository)
        env_arguments: list[str] = []
        for env_variable_name in required_environment_variables:
            env_arguments += ["-e", env_variable_name]

        #run scbuildcodeunits inside the SCBuilder-image. base_mount_folder is mounted into the container (covering the repository and, for submodules, its real gitdir) and the docker-socket is forwarded because codeunit-builds often start containers (for example local test-services).
        docker_arguments = [
            "run", "--rm",
            "-v", f"{base_mount_folder}:{container_base_mount_folder}",
            "-v", "/var/run/docker.sock:/var/run/docker.sock",
            "-w", container_repository_folder,
        ] + mount_arguments + env_arguments + [
            image,
        ] + scbuildcodeunits_arguments
        self.sc.log.log(f"Build codeunits in container using image \"{image}\"...")
        # the exitcode is evaluated by the caller (returned as part of the result-tuple), so the program-runner must not raise on a non-zero exitcode here.
        result=self.sc.run_program_argsasarray("docker", docker_arguments, throw_exception_if_exitcode_is_not_zero=False, print_live_output=True, env_vars=required_environment_variables)
        exit_code:int=result[0]
        stdout:str=result[1] or GeneralUtilities.empty_string
        stderr:str=result[2] or GeneralUtilities.empty_string
        return (exit_code==0,f"{stdout}\n{stderr}")
    
    @GeneralUtilities.check_arguments
    def __translate_path_into_container(self, host_path: str, container_repository_folder: str) -> str:
        normalized_repository = os.path.normpath(self.repository)
        normalized_path = os.path.normpath(host_path)
        if normalized_path.startswith(normalized_repository):
            relative_path = os.path.relpath(normalized_path, normalized_repository).replace(os.sep, "/")
            return f"{container_repository_folder}/{relative_path}"
        return host_path

    @GeneralUtilities.check_arguments
    def __translate(self) -> None:
        for taskfile_name in ("Taskfile.yml", "Taskfile.yaml"):
            taskfile = os.path.join(self.repository, taskfile_name)
            if os.path.isfile(taskfile):
                with open(taskfile, "r", encoding="utf-8") as f:
                    taskfile_content = yaml.safe_load(f)
                if isinstance(taskfile_content.get("tasks"), dict) and "Translate" in taskfile_content["tasks"]:
                    self.sc.run_program("task", "Translate", self.repository, print_live_output=self.sc.log.loglevel == LogLevel.Debug)
                break

    @GeneralUtilities.check_arguments
    def __collect_metrics(self) -> None:
        project_version: str=self.tfcps_tools_general.get_version_of_project(self.repository)
        self.sc.log.log("Collect metrics...")
        loc = self.sc.get_lines_of_code_with_default_excluded_patterns(self.repository)
        loc_metric_folder = os.path.join(self.repository, "Other", "Metrics")
        GeneralUtilities.ensure_directory_exists(loc_metric_folder)
        loc_metric_file = os.path.join(loc_metric_folder, "RepositoryStatisticsPerCommit.csv")
        GeneralUtilities.ensure_file_exists(loc_metric_file)

        #remove legacy metrics-file. the following 2 lines should be removed after 2026-12-31
        legacy_metrics_file = os.path.join(loc_metric_folder, "LinesOfCode.csv")
        GeneralUtilities.ensure_file_does_not_exist(legacy_metrics_file)

        old_lines = GeneralUtilities.read_nonempty_lines_from_file(loc_metric_file)
        header_line="Version;Timestamp;LinesOfCode"
        new_lines = [header_line]
        current_version_string=f"v{project_version}"
        for old_line in old_lines:
            if not old_line.startswith(current_version_string+";") and old_line!=header_line:
                new_lines.append(old_line)
        c_date:datetime=GeneralUtilities.get_now().astimezone(timezone.utc)
        commit_date=GeneralUtilities.datetime_to_string_for_logfile_entry(c_date,False)
        new_lines.append(f"{current_version_string};{commit_date};{loc}")
        GeneralUtilities.write_lines_to_file(loc_metric_file, new_lines)


    @GeneralUtilities.check_arguments
    def __generate_loc_diagram(self):
        self.sc.log.log("Generate LoC-diagram...")
        loc_metric_folder = os.path.join(self.repository, "Other", "Metrics")
        GeneralUtilities.ensure_directory_exists(loc_metric_folder)
        loc_metric_file = os.path.join(loc_metric_folder, "RepositoryStatisticsPerCommit.csv")
        GeneralUtilities.ensure_file_exists(loc_metric_file)

        filenamebase="LoC-Diagram"

        diagram_definition_folder=os.path.join(self.repository, "Other", "Reference","Technical","Diagrams")
        GeneralUtilities.ensure_directory_exists(diagram_definition_folder)

        diagram_definition_file=os.path.join(diagram_definition_folder,f"{filenamebase}.json")
        GeneralUtilities.ensure_file_exists(diagram_definition_file)
        GeneralUtilities.write_text_to_file(diagram_definition_file,GeneralUtilities.empty_string)

        loc_data_file=os.path.join(diagram_definition_folder,f"{filenamebase}.csv")
        GeneralUtilities.ensure_file_exists(loc_data_file)
        csv_lines=[]
        for line in GeneralUtilities.read_lines_from_file(loc_metric_file):
            if GeneralUtilities.string_has_content(line):
                splitted=line.split(";")
                v=splitted[0]
                t=splitted[1]
                loc=splitted[2]
                csv_lines.append(f"{v},{t},{loc}")
        GeneralUtilities.write_lines_to_file(loc_data_file,csv_lines)
        self.sc.normalize_line_endings(loc_data_file)  # ensure the generated LoC-diagram-csv always uses LF line-endings
        diagram_json = {
    "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
    "description": "Lines of Code over time",
    "width": 800,
    "height": 400,
    "data": {
        "url": f"./{filenamebase}.csv",
        "format": {
            "type": "csv"
        }
    },
    "mark": {
        "type": "line",
        "point": True
    },
    "encoding": {
        "x": {
            "field": "Timestamp",
            "type": "temporal",
            "title": "Date",
            "scale": {
                "type": "utc"#render the ticks in utc so the diagram looks the same independent of the timezone of the machine which builds it
            },
            "axis": {
                "format": "%Y-%m-%d %H:%M:%S (UTC)",#everything which is not a format-specifier starting with a percent-sign is taken literally
                "labelAngle": -45,#the timestamps are too long to be displayed horizontally next to each other
                "labelLimit": 250,#without this the labels would be truncated with an ellipsis because they are longer than the default-limit of 180 pixels
                "tickCount": 8
            }
        },
        "y": {
            "field": "LinesOfCode",
            "type": "quantitative",
            "title": "Lines of Code"
        },
        #the timestamp and the lines of code are not listed here although they are part of the tooltip: the fields which are encoded
        #as x respectively as y are always part of the generated tooltip anyway, so listing them again would show them twice.
        "tooltip": [
            {
                "field": "Version",
                "type": "ordinal"
            }
        ]
    }
}

        with open(diagram_definition_file, "w", encoding="utf-8") as f:
            json.dump(
                diagram_json,
                f,
                indent=2,
                sort_keys=False,
                ensure_ascii=False
            )
        diagram_svg_file=os.path.join(self.repository,"Other","Reference","Technical","Diagrams",f"{filenamebase}.svg")
        GeneralUtilities.ensure_file_exists(diagram_svg_file)
        GeneralUtilities.assert_condition(not self.sc.file_is_git_ignored(f"Other/Reference/Technical/Diagrams/{filenamebase}.svg",self.repository),f"Other/Reference/Technical/Diagrams/{filenamebase}.svg must not be git-ignored")#because it should be referencable in markdown-files and viewable without building the codeunits.
        self.sc.generate_chart_diagram(diagram_definition_file,os.path.basename(diagram_svg_file))
        self.sc.add_tooltips_to_chart_diagram(diagram_svg_file)#so the exact values of a data-point are visible when the svg-file is opened directly in a browser
        self.sc.format_xml_file(diagram_svg_file)

    @GeneralUtilities.check_arguments
    def search_for_secrets(self) -> None:
        self.sc.log.log("Search for secrets...")
        self.__search_for_secrets_in_repository()
        self.__search_for_secrets_in_oci_images()

    @GeneralUtilities.check_arguments
    def __search_for_secrets_in_oci_images(self) -> None:
        #the repository-scan above can not find secrets which are only contained in a built image (build-arguments recorded in the
        #image-history, environment-variables of the image and files which are generated during the image-build), and betterleaks
        #does not look into the "*.tar"-files the image-builds produce. Since these images get published, they are scanned separately.
        scan: TFCPS_OCIImageSecretScan = TFCPS_OCIImageSecretScan(self.sc)
        findings: list[str] = []
        for image in self.__get_oci_images_of_repository():
            findings = findings+scan.search_for_secrets_in_image(image, self.repository)
        if 0 < len(findings):
            for finding in findings:
                self.sc.log.log(finding, LogLevel.Error)
            raise ValueError(f"Found {len(findings)} secret-finding(s) in the built OCI-image(s). A secret which is part of an image is readable by everybody who is allowed to pull that image. See {os.path.join(self.repository, '.betterleaks.toml')} to ignore known false positives.")

    @GeneralUtilities.check_arguments
    def __get_oci_images_of_repository(self) -> list[str]:
        """Returns the references of the images which were built by the codeunits of this repository. A codeunit builds an image
        exactly if it has an OCI-image-artifacts-folder; the built image is loaded into the local docker-instance by the
        codeunit-build, tagged with the lowercase codeunit-name and the codeunit-version."""
        result: list[str] = []
        for codeunit_name in self.tfcps_tools_general.get_codeunits(self.repository):
            codeunit_folder: str = os.path.join(self.repository, codeunit_name)
            if not os.path.isdir(os.path.join(codeunit_folder, "Other", "Artifacts", "BuildResult_OCIImage")):
                continue
            codeunit_version: str = self.tfcps_tools_general.get_version_of_codeunit(os.path.join(codeunit_folder, f"{codeunit_name}.codeunit.xml"))
            result.append(f"{codeunit_name}:{codeunit_version}".lower())
        return result

    @GeneralUtilities.check_arguments
    def __search_for_secrets_in_repository(self) -> None:
        try:
            image = self.tfcps_tools_general.oci_image_manager.get_registry_address_for_image_with_default_tag(self.repository, "Betterleaks")
        except Exception:
            image="ghcr.io/betterleaks/betterleaks:latest"
        config_file = os.path.join(self.repository, ".betterleaks.toml")
        #the filesystem-marker is checked in addition to the convention-based environment-variable (which the rest of this class uses as well),
        #because a wrong result here does not only change a message but makes the scan analyse the wrong folder.
        running_in_container = os.path.exists("/.dockerenv") or self.sc.is_runnning_in_container()
        if running_in_container:
            # We run inside the build-container with the docker-socket forwarded to the host-daemon.
            # A bind-mount of our in-container repository-path (e.g. "/__w/<repo>/<repo>" on a
            # GitHub-runner or "/Workspace/Repository" when the pipeline is run locally) would be
            # resolved by the host-daemon, where that path does not exist or points to unrelated
            # data (for example test-service-volumes written there by other sibling-containers).
            # The sibling betterleaks-container would then scan the wrong directory - without the
            # repository-content and without ".betterleaks.toml", which causes false positives.
            # Sharing our own volumes instead exposes the repository to betterleaks at the same path.
            mount_arguments = ["--volumes-from", self.__get_own_container_id()]
            repository_in_scan_container = self.repository
        else:
            # Running directly on the host: a normal bind-mount works because the path is resolved
            # on the same filesystem the docker-daemon uses.
            mount_arguments = ["-v", f"{self.repository}:/repo"]
            repository_in_scan_container = "/repo"
        scan_args = ["dir", repository_in_scan_container, "-v"]
        if os.path.isfile(config_file):
            # Pass the config explicitly instead of relying on auto-detection, because betterleaks
            # silently falls back to the default ruleset when it does not find the config at the
            # scan-root, which results in false positives.
            scan_args = scan_args + ["-c", f"{repository_in_scan_container}/.betterleaks.toml"]
        else:
            self.sc.log.log(f"No betterleaks-config found at '{config_file}'; scanning with default ruleset only.", LogLevel.Warning)
        # Verify that the docker-daemon is reachable before running the scan. The scan runs betterleaks via "docker run",
        # and "docker run" returns exit-code 1 both when the daemon is unreachable and when betterleaks actually finds
        # secrets. Without this pre-check an unreachable daemon (e.g. the socket is not forwarded into a build-container)
        # would be misreported below as "found secrets", which is a misleading infrastructure-error. "docker version
        # --format {{.Server.Version}}" queries the daemon (the server-part) and exits non-zero exactly when it can not
        # be reached, so it distinguishes "docker not available" from a real scan-result.
        daemon_check = self.sc.run_program_argsasarray("docker", ["version", "--format", "{{.Server.Version}}"], throw_exception_if_exitcode_is_not_zero=False, print_live_output=False)
        if daemon_check[0] != 0:
            raise ValueError(f"The secret-scan can not be performed because the docker-daemon is not reachable (exit-code {daemon_check[0]}: {daemon_check[2].strip()}). The scan runs betterleaks via 'docker run', which requires a running docker-daemon (inside a build-container its socket must be forwarded to the host-daemon). This is an infrastructure-problem, not a secret-finding in the repository.")
        args = ["run", "--rm"] + mount_arguments + [image] + scan_args
        result = self.sc.run_program_argsasarray("docker", args, throw_exception_if_exitcode_is_not_zero=False, print_live_output=self.sc.log.loglevel==LogLevel.Debug,print_errors_as_information=True)
        if result[0] != 0:
            for line in GeneralUtilities.string_to_lines(result[1]):
                self.sc.log.log(line, LogLevel.Information)
            for line in GeneralUtilities.string_to_lines(result[2]):
                self.sc.log.log(line, LogLevel.Error)
            raise ValueError(f"Found unignored secret findings (exit code {result[0]}). See {os.path.join(self.repository, '.betterleaks.toml')} to ignore known false positives.")

    @GeneralUtilities.check_arguments
    def __get_own_container_id(self) -> str:
        # Determine the id of the container this process runs in so its volumes can be shared with
        # sibling-containers via "docker run --volumes-from".
        # In mountinfo the own container-id only appears reliably in the source-path of the
        # "/etc/hostname"/"/etc/hosts"/"/etc/resolv.conf"-mounts (".../containers/<id>/..."). A plain
        # 64-hex-match there would also hit overlay-layer-hashes (which are not containers), so the
        # "containers/"-prefix must be matched explicitly.
        try:
            with open("/proc/self/mountinfo", "r", encoding="utf-8") as file_handle:
                match = re.search(r"/containers/([0-9a-f]{64})/", file_handle.read())
                if match is not None:
                    return match.group(1)
        except Exception:
            pass
        # cgroup (v1): the container-id is part of the cgroup-path; here a plain 64-hex-match is safe.
        try:
            with open("/proc/self/cgroup", "r", encoding="utf-8") as file_handle:
                match = re.search(r"[0-9a-f]{64}", file_handle.read())
                if match is not None:
                    return match.group(0)
        except Exception:
            pass
        # Fallback: the hostname equals the short container-id for containers started without an
        # explicit hostname.
        return socket.gethostname()

    @GeneralUtilities.check_arguments
    def use_cache(self) -> bool:
        return self.__use_cache


    @GeneralUtilities.check_arguments
    def is_pre_merge(self) -> bool:
        return self.__is_pre_merge

    @GeneralUtilities.check_arguments
    def add_ready_to_merge_flag(self) -> bool:
        if self.__add_ready_to_merge_flag:
            return True
        if self.sc.git_get_current_branch_name(self.repository)=="other/maintenance":
            return True
        return False

    @GeneralUtilities.check_arguments
    def update_dependencies(self) -> None:
        repository=self.repository
        self.sc.log.log("Update dependencies for product...")
        self.update_year_in_license_file()
        self.sc.assert_is_git_repository(repository)
        self.sc.assert_no_uncommitted_changes(repository)
        #the update is done while the codeunits are built regularly (see TFCPS_UpdateDependenciesHook): a codeunit is built before its
        #dependencies are updated (some programming-languages need that) and again afterwards if the update changed something. Using the
        #regular build means the update also gets all preparation-steps of a build - especially the package-sources which are required to
        #resolve dependencies which are not available on a public package-source.
        self.build_codeunits(TFCPS_UpdateDependenciesHook(self.sc, self.tfcps_tools_general))
        if self.sc.git_repository_has_uncommitted_changes(repository):
            changelog_folder = os.path.join(repository, "Other", "Resources", "Changelog")
            project_version:str=self.tfcps_tools_general.get_version_of_project(repository)
            changelog_file = os.path.join(changelog_folder, f"v{project_version}.md")
            if not os.path.isfile(changelog_file):
                self.__ensure_changelog_file_is_added(repository, project_version)
            self.build_codeunits()#check the codeunits are buildable at all with all updates together
            self.sc.git_commit(repository, "Updated dependencies", stage_all_changes=True)

    @GeneralUtilities.check_arguments
    def __ensure_changelog_file_is_added(self, repository_folder: str, version_of_project: str):
        changelog_file = os.path.join(repository_folder, "Other", "Resources", "Changelog", f"v{version_of_project}.md")
        if not os.path.isfile(changelog_file):
            GeneralUtilities.ensure_file_exists(changelog_file)
            GeneralUtilities.write_text_to_file(changelog_file, """# Release notes

## Changes

- Updated dependencies.
""")

    @GeneralUtilities.check_arguments
    def update_year_in_license_file(self) -> None:
        self.sc.update_year_in_first_line_of_file(os.path.join(self.repository, "License.txt"))
