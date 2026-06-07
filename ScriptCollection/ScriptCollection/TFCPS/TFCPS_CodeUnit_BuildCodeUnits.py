import os
import json
from datetime import datetime, timedelta,timezone
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
    __use_cache:bool
    __is_pre_merge:bool
    __assert_no_new_changes:bool

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
        self.sc.log.log(f"Start building codeunits at {GeneralUtilities.datetime_to_string_for_readable_entry(start_time,False)}. (Target environment-type: {self.target_environment_type})")
        if self.__assert_no_new_changes:
            self.sc.assert_no_uncommitted_changes(self.repository,"Can not build codeunit: There are uncommitted changes in the repository.")

        #check if changelog exists
        changelog_file=os.path.join(self.repository,"Other","Resources","Changelog",f"v{self.tfcps_tools_general.get_version_of_project(self.repository)}.md")
        GeneralUtilities.assert_file_exists(changelog_file,f"Changelogfile \"{changelog_file}\" does not exist. Try to create it for example using \"sccreatechangelogentry -m ...\".") 
        
        #run prepare-script
        self.run_prepare_script()

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
        self.__search_for_vulnerabilities()
        self.search_for_secrets()
        if self.is_pre_merge():
            self.__translate()
            self.__collect_metrics()
            self.__generate_loc_diagram()

        if self.__assert_no_new_changes:
            self.sc.assert_no_uncommitted_changes(self.repository,"There are new uncommitted changes in the repository.")

        end_time:datetime=GeneralUtilities.get_now()
        duration=end_time-start_time
        self.sc.log.log(f"Finished building codeunits at {GeneralUtilities.datetime_to_string_for_readable_entry(end_time,False)}. (Duration: {GeneralUtilities.timedelta_to_simple_string(duration)})")
        self.sc.log.log(GeneralUtilities.get_line())

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
    def build_codeunits_in_container(self) -> None:
        raise ValueError("Not implemented.")

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
        if os.path.isdir(os.path.join(self.repository, ".git")):
            scan_args = ["git", "/repo"]
        if os.path.isfile(os.path.join(self.repository, ".git")):
            self.sc.log.log("Repository is a Git submodule (.git is a file); scanning working tree only (no history).", LogLevel.Warning)
            scan_args = ["dir", "/repo"] #usually the git-scan should be used here too but this does not work in a submodule yet, see https://github.com/betterleaks/betterleaks/issues/170
        else:
            scan_args = ["dir", "/repo"]
        args = ["run", "--rm", "-v", f"{self.repository}:/repo", image] + scan_args
        result = self.sc.run_program_argsasarray("docker", args, throw_exception_if_exitcode_is_not_zero=False, print_live_output=self.sc.log.loglevel==LogLevel.Debug)
        if result[0] != 0:
            for line in GeneralUtilities.string_to_lines(result[1]):
                self.sc.log.log(line, LogLevel.Information)
            for line in GeneralUtilities.string_to_lines(result[2]):
                self.sc.log.log(line, LogLevel.Error)
            raise ValueError(f"Found unignored secret findings (exit code {result[0]}). See {os.path.join(self.repository, '.betterleaks.toml')} to ignore known false positives.")

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
