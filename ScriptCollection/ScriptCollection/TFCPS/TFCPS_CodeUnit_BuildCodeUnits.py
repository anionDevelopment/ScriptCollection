import os
import json
import re
import socket
from datetime import datetime, timedelta,timezone
import xmlschema
import yaml
from ..GeneralUtilities import GeneralUtilities
from ..ScriptCollectionCore import ScriptCollectionCore
from ..SCLog import  LogLevel
from .TFCPS_CodeUnit_BuildCodeUnit import TFCPS_CodeUnit_BuildCodeUnit
from .TFCPS_Tools_General import TFCPS_Tools_General

class TFCPS_CodeUnit_BuildCodeUnits:
    repository:str=None
    tfcps_tools_general:TFCPS_Tools_General=None 
    sc:ScriptCollectionCore=None
    target_environment_type:str=None
    additionalargumentsfile:str=None
    __use_cache:bool = None
    __is_pre_merge:bool = None
    __assert_no_new_changes:bool = None

    def __init__(self,repository:str,loglevel:LogLevel,target_environment_type:str,additionalargumentsfile:str,use_cache:bool,is_pre_merge:bool,assertnonewchanges:bool):
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

    @GeneralUtilities.check_arguments
    def build_codeunits(self) -> None:
        self.sc.log.log(GeneralUtilities.get_line())
        start_time:datetime=GeneralUtilities.get_now()

        if self.is_pre_merge():
            GeneralUtilities.assert_condition(not self.__assert_no_new_changes,f"A pre-merge build can not be done with the assert-no-new-changes-option.")
        ready_to_merge_file=os.path.join(self.repository,".ScriptCollection",".IsReadyToMerge")
        GeneralUtilities.ensure_file_does_not_exist(ready_to_merge_file)

        self.sc.log.log(f"Start building codeunits at {GeneralUtilities.datetime_to_string_for_readable_entry(start_time,False)}. (Target environment-type: {self.target_environment_type})")
        if self.__assert_no_new_changes:
            self.sc.assert_no_uncommitted_changes(self.repository,"Can not build codeunit: There are uncommitted changes in the repository.")

        product_information_file = os.path.join(self.repository, ".ScriptCollection", "ProductInformation.xml")
        try:
            xmlschema.validate(product_information_file, "https://projects.aniondev.de/PublicProjects/Common/ProjectTemplates/-/raw/main/Conventions/RepositoryStructure/CommonProjectStructure/projectinformation.xsd")
        except Exception as exception:
            self.sc.log.log_exception(f"'{product_information_file}' could not be validated against the XSD:", exception, LogLevel.Warning)

        #run prepare-script
        self.run_prepare_script()

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
            tFCPS_CodeUnit_BuildCodeUnit:TFCPS_CodeUnit_BuildCodeUnit = TFCPS_CodeUnit_BuildCodeUnit(os.path.join(self.repository,codeunit_name),self.sc.log.loglevel,self.target_environment_type,self.additionalargumentsfile,self.use_cache(),self.is_pre_merge())
            self.sc.log.log(GeneralUtilities.get_line())
            tFCPS_CodeUnit_BuildCodeUnit.build_codeunit()

        self.sc.log.log(GeneralUtilities.get_line())

        self.search_for_secrets()
        self.__search_for_vulnerabilities()
        self.__normalize_md_and_txt_line_endings()

        if self.is_pre_merge():
            self.__translate()
            self.__collect_metrics()
            self.__generate_loc_diagram()
            GeneralUtilities.ensure_file_does_not_exist(ready_to_merge_file)
        else:
            if self.is_working_branch():
                GeneralUtilities.ensure_file_exists(ready_to_merge_file)

        if self.__assert_no_new_changes:
            self.sc.assert_no_uncommitted_changes(self.repository,"There are new uncommitted changes in the repository.")

        end_time:datetime=GeneralUtilities.get_now()
        duration=end_time-start_time
        self.sc.log.log(f"Finished building codeunits at {GeneralUtilities.datetime_to_string_for_readable_entry(end_time,False)}. (Duration: {GeneralUtilities.timedelta_to_simple_string(duration)})")
        self.sc.log.log(GeneralUtilities.get_line())

    @GeneralUtilities.check_arguments
    def __normalize_md_and_txt_line_endings(self) -> None:
        #TODO add option do define exceptions (means: files which should not be normalized).
        for text_file_extension in [".txt", ".md"]:
            for text_file in self.sc.get_not_git_ignored_files_of_folder(self.repository, text_file_extension):
                self.sc.normalize_line_endings(text_file)

    @GeneralUtilities.check_arguments
    def is_working_branch(self)->bool:
        if self.sc.git_repository_has_uncommitted_changes(self.repository):
            return True
        if self.sc.git_get_current_branch_name(self.repository) != "main":
            return True
        return False

    @GeneralUtilities.check_arguments
    def run_prepare_script(self):
        args=["--repository",self.repository,"--targetenvironmenttype",self.target_environment_type,"--verbosity",str(int(self.sc.log.loglevel))]
        if GeneralUtilities.string_has_content(self.additionalargumentsfile):
            args=args+["--additionalargumentsfile", self.additionalargumentsfile]
        if not self.__use_cache:
            if self.sc.git_repository_has_uncommitted_changes(self.repository):
                self.sc.log.log("No-cache-option can not be applied because there are uncommited changes in the repository.",LogLevel.Warning)
            else:
                args=args+["--nocache"]

        if  os.path.isfile( os.path.join( GeneralUtilities.get_scriptcollection_configuration_folder(),"TFCPS","CustomPreCodeUnitBuildScript.py")):
            self.sc.log.log("Run custom pre-codeunitbuild script...")
            self.sc.run_program_argsasarray(GeneralUtilities.get_python_executable(),["CustomPreCodeUnitBuildScript.py"]+args, os.path.join( GeneralUtilities.get_scriptcollection_configuration_folder(),"TFCPS"),print_live_output=True)

        if  os.path.isfile( os.path.join(self.repository,"Other","Scripts","PrepareBuildCodeunits.py")):
            self.sc.log.log("Prepare build codeunits...")
            self.sc.run_program_argsasarray(GeneralUtilities.get_python_executable(),["PrepareBuildCodeunits.py"]+args, os.path.join(self.repository,"Other","Scripts"),print_live_output=True)

    @GeneralUtilities.check_arguments
    def build_codeunits_in_container(self) -> tuple[bool, str]:
        container_repository_folder = "/Workspace/Repository"
        image = self.tfcps_tools_general.oci_image_manager.get_registry_address_for_image_with_default_tag(self.repository, "SCBuilder")

        #build the scbuildcodeunits-arguments based on the current state (analogous to the arguments accepted by the scbuildcodeunits-executable). each token must be a separate argument because run_program_argsasarray passes every list-element verbatim and does not split on spaces.
        scbuildcodeunits_arguments = ["scbuildcodeunits", "-r", container_repository_folder, "-v", "4"]
        if not self.__use_cache:
            scbuildcodeunits_arguments.append("-c")
        if self.__is_pre_merge:
            scbuildcodeunits_arguments.append("-p")
        if self.__assert_no_new_changes:
            scbuildcodeunits_arguments.append("-u")
        if GeneralUtilities.string_has_content(self.additionalargumentsfile):
            scbuildcodeunits_arguments += ["-a", self.__translate_path_into_container(self.additionalargumentsfile, container_repository_folder)]

        #run scbuildcodeunits inside the SCBuilder-image. the repository is mounted into the container and the docker-socket is forwarded because codeunit-builds often start containers (for example local test-services).
        docker_arguments = [
            "run", "--rm",
            "-v", f"{self.repository}:{container_repository_folder}",
            "-v", "/var/run/docker.sock:/var/run/docker.sock",
            "-w", container_repository_folder,
            image,
        ] + scbuildcodeunits_arguments
        self.sc.log.log(f"Build codeunits in container using image \"{image}\"...")
        # the exitcode is evaluated by the caller (returned as part of the result-tuple), so the program-runner must not raise on a non-zero exitcode here.
        result=self.sc.run_program_argsasarray("docker", docker_arguments, throw_exception_if_exitcode_is_not_zero=False, print_live_output=True)
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
            "title": "Date"
        },
        "y": {
            "field": "LinesOfCode",
            "type": "quantitative",
            "title": "Lines of Code"
        },
        "tooltip": [
            {
                "field": "Version",
                "type": "ordinal"
            },
            {
                "field": "LinesOfCode",
                "type": "quantitative"
            },
            {
                "field": "Timestamp",
                "type": "temporal"
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
        self.sc.format_xml_file(diagram_svg_file)

    @GeneralUtilities.check_arguments
    def __search_for_vulnerabilities(self):
        pass#TODO

    @GeneralUtilities.check_arguments
    def search_for_secrets(self) -> None:
        self.sc.log.log("Search for secrets...")
        try:
            image = self.tfcps_tools_general.oci_image_manager.get_registry_address_for_image_with_default_tag(self.repository, "Betterleaks")
        except Exception:
            image="ghcr.io/betterleaks/betterleaks:latest"
        config_file = os.path.join(self.repository, ".betterleaks.toml")
        running_in_container = os.path.exists("/.dockerenv") or self.sc.is_running_in_build_container()
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
        args = ["run", "--rm"] + mount_arguments + [image] + scan_args
        result = self.sc.run_program_argsasarray("docker", args, throw_exception_if_exitcode_is_not_zero=False, print_live_output=self.sc.log.loglevel==LogLevel.Debug)
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
    def update_dependencies(self) -> None:
        repository=self.repository
        self.sc.log.log("Update dependencies...")
        self.update_year_in_license_file()
        self.sc.assert_is_git_repository(repository)
        self.sc.assert_no_uncommitted_changes(repository)
        self.run_prepare_script()
        if os.path.isfile(os.path.join(repository,"Other","Scripts","UpdateDependencies.py")):
            self.sc.run_program(GeneralUtilities.get_python_executable(),"UpdateDependencies.py",os.path.join(repository,"Other","Scripts"))
        codeunits:list[str]=self.tfcps_tools_general.get_codeunits(repository)   
        for codeunit_name in codeunits:
            self.sc.log.log(f"Update dependencies of codeunit {codeunit_name}...")
            codeunit_folder=os.path.join(repository,codeunit_name)
            tFCPS_CodeUnit_BuildCodeUnit:TFCPS_CodeUnit_BuildCodeUnit = TFCPS_CodeUnit_BuildCodeUnit(codeunit_folder,self.sc.log.loglevel,"QualityCheck",None,True,False)
            tFCPS_CodeUnit_BuildCodeUnit.build_codeunit()#ensure requirements for updating are there (some programming-languages needs this)
            if self.tfcps_tools_general.codeunit_has_updatable_dependencies(os.path.join(codeunit_folder,f"{codeunit_name}.codeunit.xml")):
                self.sc.run_program(GeneralUtilities.get_python_executable(),"UpdateDependencies.py",os.path.join(codeunit_folder,"Other"))
            tFCPS_CodeUnit_BuildCodeUnit.build_codeunit()#check if codeunit is still buildable
        if self.sc.git_repository_has_uncommitted_changes(repository):
            changelog_folder = os.path.join(repository, "Other", "Resources", "Changelog")
            project_version:str=self.tfcps_tools_general.get_version_of_project(repository)
            changelog_file = os.path.join(changelog_folder, f"v{project_version}.md")
            if not os.path.isfile(changelog_file):
                self.__ensure_changelog_file_is_added(repository, project_version)
            t=TFCPS_CodeUnit_BuildCodeUnits(repository,self.sc.log.loglevel,"QualityCheck",None,True,False,False)
            t.build_codeunits()#check codeunits are buildable at all
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
