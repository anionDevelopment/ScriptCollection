import argparse
import os
import shutil
from functools import cmp_to_key
from ..GeneralUtilities import GeneralUtilities
from ..ScriptCollectionCore import ScriptCollectionCore
from ..SCLog import LogLevel
from .TFCPS_Tools_General import TFCPS_Tools_General
from .TFCPS_MergeToMain import TFCPS_MergeToMain
from .TFCPS_CodeUnit_BuildCodeUnits import TFCPS_CodeUnit_BuildCodeUnits
 

class MergeToStableConfiguration:
    log_level:LogLevel
    source_branch:str#main
    target_branch:str#stable
    repository:str
    build_repo:str
    common_remote_name:str
    build_repo_main_branch_name:str
    reference_repo_main_branch_name:str
    reference_remote_name:str
    build_repo_remote_name:str
    artifacts_target_folder:str
    common_remote_url:str
    additional_arguments_file:str

    def __init__(self,loglevel:LogLevel,source_branch:str,target_branch:str,repository:str,build_repo:str,common_remote_name:str,build_repo_main_branch_name:str,reference_repo_main_branch_name:str,reference_remote_name:str,build_repo_remote_name:str,artifacts_target_folder:str,common_remote_url:str,additional_arguments_file:str):
        self.log_level=loglevel
        self.source_branch=source_branch
        self.target_branch=target_branch
        self.repository=repository
        self.build_repo=build_repo
        self.common_remote_name=common_remote_name
        self.build_repo_main_branch_name=build_repo_main_branch_name
        self.reference_repo_main_branch_name=reference_repo_main_branch_name
        self.reference_remote_name=reference_remote_name
        self.build_repo_remote_name=build_repo_remote_name
        self.artifacts_target_folder=artifacts_target_folder
        self.common_remote_url=common_remote_url
        self.additional_arguments_file=additional_arguments_file

class TFCPS_MergeToStable:

    sc:ScriptCollectionCore
    tFCPS_Tools_General:TFCPS_Tools_General
    createRelease_configuration: MergeToStableConfiguration

    def __init__(self, createRelease_configuration: MergeToStableConfiguration):
        self.sc=ScriptCollectionCore()
        self.tFCPS_Tools_General=TFCPS_Tools_General(self.sc)
        self.createRelease_configuration=createRelease_configuration
 
    @GeneralUtilities.check_arguments
    def merge_to_stable_branch(self):
        self.sc.log.loglevel=self.createRelease_configuration.log_level
        self.sc.log.log("Merge to stable-branch...") 
        product_name:str=os.path.basename(self.createRelease_configuration.repository)

        if self.sc.git_get_commit_id(self.createRelease_configuration.repository,self.createRelease_configuration.source_branch)==self.sc.git_get_commit_id(self.createRelease_configuration.repository,self.createRelease_configuration.target_branch):
            self.sc.log.log("Source- and target-branch are on the same commit.")
            return

        self.sc.assert_is_git_repository(self.createRelease_configuration.repository)
        self.sc.assert_no_uncommitted_changes(self.createRelease_configuration.repository)
        self.sc.git_checkout(self.createRelease_configuration.repository, self.createRelease_configuration.source_branch)
        self.sc.assert_no_uncommitted_changes(self.createRelease_configuration.repository)

        reference_repo=self.createRelease_configuration.repository+"Reference"
        self.sc.assert_is_git_repository(reference_repo)
        self.sc.assert_no_uncommitted_changes(reference_repo)

        self.sc.assert_is_git_repository(self.createRelease_configuration.build_repo)
        self.sc.assert_no_uncommitted_changes(self.createRelease_configuration.build_repo)

        product_version:str=self.tFCPS_Tools_General.get_version_of_project(self.createRelease_configuration.repository)
 
        #TODO do premerge-build instead
        tfcps_CodeUnit_BuildCodeUnits:TFCPS_CodeUnit_BuildCodeUnits=TFCPS_CodeUnit_BuildCodeUnits(self.createRelease_configuration.repository,self.sc.log.loglevel,"Productive",self.createRelease_configuration.additional_arguments_file,False,False,False)
        try:
            tfcps_CodeUnit_BuildCodeUnits.build_codeunits()
        except Exception:
            self.sc.log.log(f"Branch {self.createRelease_configuration.source_branch} is not buildable.",LogLevel.Error)
            self.sc.git_undo_all_changes(self.createRelease_configuration.repository)
            raise

        self.sc.log.log("Release artifacts...")
        repository:str=self.createRelease_configuration.repository
        project_version:str=self.tFCPS_Tools_General.get_version_of_project(repository)
        for codeunit in self.tFCPS_Tools_General.get_codeunits(self.createRelease_configuration.repository):
            self.sc.git_checkout(self.createRelease_configuration.repository, self.createRelease_configuration.source_branch, True,True)
            if self.createRelease_configuration.artifacts_target_folder is not None:
                #export artifacts to local target folder
                self.sc.log.log(f"Export artifacts of codeunit {codeunit} to target-folder...")
                source_folder:str=GeneralUtilities.resolve_relative_path(f"./{codeunit}/Other/Artifacts",self.createRelease_configuration.repository)
                target_folder:str=GeneralUtilities.resolve_relative_path(f"./{product_name}/{product_version}/{codeunit}",self.createRelease_configuration.artifacts_target_folder)
                GeneralUtilities.ensure_directory_exists(target_folder)
                codeunit_version:str=self.tFCPS_Tools_General.get_version_of_codeunit(os.path.join(self.createRelease_configuration.repository,codeunit,f"{codeunit}.codeunit.xml"))
                target_file:str=os.path.join(target_folder,f"{codeunit}.v{codeunit_version}.Artifacts.zip")
                self.sc.create_zip_archive(source_folder,target_file)

            #push artifacts
            push_script:str=os.path.join( self.createRelease_configuration.build_repo,"Scripts","CreateRelease",f"PushArtifacts.{codeunit}.py")
            if os.path.isfile(push_script):
                self.sc.log.log(f"Push artifacts of codeunit {codeunit}...")
                self.sc.run_program(GeneralUtilities.get_python_executable(),os.path.basename(push_script),os.path.dirname(push_script))
            else:
                self.sc.log.log(f"Codeunit {codeunit} does not have artifacts to push. (Scriptfile \"{push_script}\" does not exist.)",LogLevel.Debug)

            # update codeunit-reference
            self.sc.log.log(f"Release artifacts of codeunit {codeunit}...")
            reference_folder:str=os.path.join(reference_repo,"ReferenceContent")
            projectname:str=os.path.basename(repository)
            public_repository_url:str=self.createRelease_configuration.common_remote_url
            main_branch_name:str=self.createRelease_configuration.source_branch
            codeunit_version=self.tFCPS_Tools_General.get_version_of_codeunit(os.path.join(repository,codeunit,f"{codeunit}.codeunit.xml"))
            self.__export_codeunit_reference_content_to_reference_repository(f"v{project_version}", False, reference_folder, repository, codeunit, projectname, codeunit_version, public_repository_url, f"v{project_version}")
            self.__export_codeunit_reference_content_to_reference_repository("Latest", True, reference_folder, repository, codeunit, projectname, codeunit_version, public_repository_url, main_branch_name)

        #TODO set (update/overwrite) project-specific reference in reference_repo
        
        #TODO set (update/overwrite) project-issues in reference_repo

        # Generate reference
        self.__generate_entire_reference(projectname, project_version, reference_folder,reference_repo)

        self.sc.git_commit(reference_repo,f"Added reference for v{project_version}")

        #TODO do this not as fast-forward-merge anymore, because the changes from the premerge-build should be included
        self.sc.git_merge(self.createRelease_configuration.repository, self.createRelease_configuration.source_branch,self.createRelease_configuration.target_branch, True,True,None,True,True)

        self.sc.assert_no_uncommitted_changes(self.createRelease_configuration.repository)
        self.sc.assert_no_uncommitted_changes(reference_repo)
        self.sc.git_commit(self.createRelease_configuration.build_repo,"Updated submodules")

        self.sc.git_push_with_retry(self.createRelease_configuration.repository,self.createRelease_configuration.common_remote_name,self.createRelease_configuration.source_branch,self.createRelease_configuration.source_branch)
        self.sc.git_push_with_retry(self.createRelease_configuration.repository,self.createRelease_configuration.common_remote_name,self.createRelease_configuration.target_branch,self.createRelease_configuration.target_branch)
        self.sc.git_push_with_retry(self.createRelease_configuration.build_repo,self.createRelease_configuration.build_repo_remote_name,self.createRelease_configuration.build_repo_main_branch_name,self.createRelease_configuration.build_repo_main_branch_name)
        self.sc.git_push_with_retry(reference_repo,self.createRelease_configuration.reference_remote_name,self.createRelease_configuration.reference_repo_main_branch_name,self.createRelease_configuration.reference_repo_main_branch_name)

        self.sc.log.log(f"Finishing merging {projectname} v{project_version} to stable...")

    @GeneralUtilities.check_arguments
    def __remove_outdated_version(self,reference_repo:str):
        now = GeneralUtilities.get_now()
        for unsupported_version in self.tFCPS_Tools_General.get_unsupported_versions(self.createRelease_configuration.repository, now):
            unsupported_reference_folder = f"{reference_repo}/ReferenceContent/v{unsupported_version[0]}"
            GeneralUtilities.ensure_directory_does_not_exist(unsupported_reference_folder)

        
    @GeneralUtilities.check_arguments
    def __generate_entire_reference(self, projectname: str, project_version: str, reference_folder: str,reference_repo:str) -> None:
        self.sc.log.log("Remove outdated versions...")
        self.__remove_outdated_version(reference_repo)
        self.sc.log.log("Generate reference...")
        all_available_version_identifier_folders_of_reference: list[str] = list(folder for folder in GeneralUtilities.get_direct_folders_of_folder(reference_folder))
        all_available_version_identifier_folders_of_reference = sorted(all_available_version_identifier_folders_of_reference, key=cmp_to_key(TFCPS_Tools_General.sort_reference_folder))
        reference_versions_html_lines = []
        reference_versions_html_lines.append('    <hr/>')
        for all_available_version_identifier_folder_of_reference in all_available_version_identifier_folders_of_reference:
            version_identifier_of_project = os.path.basename(all_available_version_identifier_folder_of_reference)
            if version_identifier_of_project == "Latest":
                latest_version_hint = f" (v{project_version})"
            else:
                latest_version_hint = GeneralUtilities.empty_string
            reference_versions_html_lines.append(f'    <h2>{version_identifier_of_project}{latest_version_hint}</h2>')
            reference_versions_html_lines.append("    Contained codeunits:<br/>")
            reference_versions_html_lines.append("    <ul>")
            for codeunit_reference_folder in list(folder for folder in GeneralUtilities.get_direct_folders_of_folder(all_available_version_identifier_folder_of_reference)):
                reference_versions_html_lines.append(f'      <li><a href="./{version_identifier_of_project}/{os.path.basename(codeunit_reference_folder)}/index.html">' +
                                                     f'{os.path.basename(codeunit_reference_folder)} {version_identifier_of_project}</a></li>')
            reference_versions_html_lines.append("    </ul>")
            reference_versions_html_lines.append('    <hr/>')
            if version_identifier_of_project == "Latest":
                latest_version_hint = "    <h2>History</h2>"

        design_file = None
        design = "ModestDark"
        if design == "ModestDark":
            design_file = GeneralUtilities.get_modest_dark_url()
        # TODO make designs from customizable sources be available by a customizable name and outsource this to a class-property because this is duplicated code.
        if design_file is None:
            design_html = GeneralUtilities.empty_string
        else:
            design_html = f'<link type="text/css" rel="stylesheet" href="{design_file}" />'

        reference_versions_links_file_content = "    \n".join(reference_versions_html_lines)
        title = f"{projectname}-reference"
        reference_index_file = os.path.join(reference_folder, "index.html")
        reference_index_file_content = f"""<!DOCTYPE html>
<html lang="en">

  <head>
    <meta charset="UTF-8">
    <title>{title}</title>
    {design_html}
  </head>

  <body>
    <h1>{title}</h1>
{reference_versions_links_file_content}
  </body>

</html>
"""  # see https://getbootstrap.com/docs/5.1/getting-started/introduction/
        GeneralUtilities.write_text_to_file(reference_index_file, reference_index_file_content)

    @GeneralUtilities.check_arguments
    def __export_codeunit_reference_content_to_reference_repository(self, project_version_identifier: str, replace_existing_content: bool, target_folder_for_reference_repository: str, repository: str, codeunitname: str, projectname: str, codeunit_version: str, public_repository_url: str, branch: str) -> None:
        codeunit_folder = os.path.join(repository, codeunitname)
        codeunit_file = os.path.join(codeunit_folder, f"{codeunitname}.codeunit.xml")
        codeunit_has_testcases = self.tFCPS_Tools_General.codeunit_has_testable_sourcecode(codeunit_file)
        target_folder = os.path.join(target_folder_for_reference_repository, project_version_identifier, codeunitname)
        if os.path.isdir(target_folder) and not replace_existing_content:
            raise ValueError(f"Folder '{target_folder}' already exists.")
        GeneralUtilities.ensure_directory_does_not_exist(target_folder)
        GeneralUtilities.ensure_directory_exists(target_folder)
        codeunit_version_identifier = "Latest" if project_version_identifier == "Latest" else "v"+codeunit_version
        page_title = f"{codeunitname} {codeunit_version_identifier} codeunit-reference"
        diff_report = f"{repository}/{codeunitname}/Other/Artifacts/DiffReport/DiffReport.html"
        diff_target_folder = os.path.join(target_folder, "DiffReport")
        GeneralUtilities.ensure_directory_exists(diff_target_folder)
        diff_target_file = os.path.join(diff_target_folder, "DiffReport.html")
        title = (f'Reference of codeunit {codeunitname} {codeunit_version_identifier} (contained in project <a href="{public_repository_url}">{projectname}</a> {project_version_identifier})')
        if public_repository_url is None:
            repo_url_html = GeneralUtilities.empty_string
        else:
            repo_url_html = f'<a href="{public_repository_url}/tree/{branch}/{codeunitname}">Source-code</a>'
        if codeunit_has_testcases:
            coverage_report_link = '<a href="./TestCoverageReport/index.html">Test-coverage-report</a><br>'
        else:
            coverage_report_link = GeneralUtilities.empty_string
        index_file_for_reference = os.path.join(target_folder, "index.html")

        design_file = None
        design = "ModestDark"
        if design == "ModestDark":
            design_file = GeneralUtilities.get_modest_dark_url()
        # TODO make designs from customizable sources be available by a customizable name and outsource this to a class-property because this is duplicated code.
        if design_file is None:
            design_html = GeneralUtilities.empty_string
        else:
            design_html = f'<link type="text/css" rel="stylesheet" href="{design_file}" />'

        index_file_content = f"""<!DOCTYPE html>
<html lang="en">

  <head>
    <meta charset="UTF-8">
    <title>{page_title}</title>
    {design_html}
  </head>

  <body>
    <h1>{title}</h1>
    <hr/>
    Available reference-content for {codeunitname}:<br>
    {repo_url_html}<br>
    <!--TODO add artefacts-link: <a href="./x">Artefacts</a><br>-->
    <a href="./Reference/index.html">Reference</a><br>
    <a href="./DiffReport/DiffReport.html">Diff-report</a><br>
    {coverage_report_link}
  </body>

</html>
"""

        GeneralUtilities.ensure_file_exists(index_file_for_reference)
        GeneralUtilities.write_text_to_file(index_file_for_reference, index_file_content)
        other_folder_in_repository = os.path.join(repository, codeunitname, "Other")
        source_generatedreference = os.path.join(other_folder_in_repository, "Artifacts", "Reference")
        target_generatedreference = os.path.join(target_folder, "Reference")
        shutil.copytree(source_generatedreference, target_generatedreference)

        shutil.copyfile(diff_report, diff_target_file)

        if codeunit_has_testcases:
            source_testcoveragereport = os.path.join(other_folder_in_repository, "Artifacts", "TestCoverageReport")
            if os.path.isdir(source_testcoveragereport):  # check, because it is not a mandatory artifact. if the artifact is not available, the user gets already a warning.
                target_testcoveragereport = os.path.join(target_folder, "TestCoverageReport")
                shutil.copytree(source_testcoveragereport, target_testcoveragereport)

class TFCPS_MergeToStable_CLI:

    @staticmethod
    @GeneralUtilities.check_arguments
    def get_with_overwritable_defaults(file:str,default_loglevel:LogLevel=None,default_source_branch:str=None,default_additionalargumentsfile:str=None,default_target_branch:str=None,common_remote_name:str=None,build_repo_main_branch_name:str=None,reference_repo_main_branch_name:str=None,reference_remote_name:str=None,build_repo_remote_name:str=None,artifacts_target_folder:str=None,common_remote_url:str=None)->TFCPS_MergeToMain:
        parser = argparse.ArgumentParser()
        verbosity_values = ", ".join(f"{lvl.value}={lvl.name}" for lvl in LogLevel)
        parser.add_argument('-a', '--additionalargumentsfile', required=False, default=None)
        parser.add_argument('-s', '--sourcebranch', required=False)#default="main"
        parser.add_argument('-t', '--targetbranch', required=False)#default="stable"
        parser.add_argument( '--referencerepo', required=False, default=None)
        parser.add_argument( '--commonremotename', required=False, default=None)
        parser.add_argument( '--buildrepomainbranchname', required=False)#default="main"
        parser.add_argument( '--referencerepomainbranchname', required=False)#default="main"
        parser.add_argument( '--referenceremotename', required=False, default=None)
        parser.add_argument( '--buildreporemotename', required=False, default=None)
        parser.add_argument( '--artifactstargetfolder', required=False, default=None)
        parser.add_argument( '--commonremoteurl', required=False, default=None)
        parser.add_argument('-v', '--verbosity', required=False, help=f"Sets the loglevel. Possible values: {verbosity_values}")
        args=parser.parse_args()

        sc:ScriptCollectionCore=ScriptCollectionCore()

        build_repo=GeneralUtilities.resolve_relative_path("../../..",file)
        sc.assert_is_git_repository(build_repo)

        default_product_name=os.path.basename(build_repo)[:-len("Build")]

        if args.verbosity is not None:
            default_loglevel=LogLevel(int( args.verbosity))
        GeneralUtilities.assert_not_null(default_loglevel,"verbosity is not set")

        if args.additionalargumentsfile is not None:
            default_additionalargumentsfile=args.additionalargumentsfile

        if args.sourcebranch is not None:
            default_source_branch=args.sourcebranch
        GeneralUtilities.assert_not_null(default_source_branch,"sourcebranch is not set")

        if args.targetbranch is not None:
            default_target_branch=args.targetbranch
        GeneralUtilities.assert_not_null(default_target_branch,"targetbranch is not set")
        
        if args.commonremotename is not None:
            common_remote_name=args.commonremotename
        GeneralUtilities.assert_not_null(common_remote_name,"commonremotename is not set")

        if args.buildrepomainbranchname is not None:
            build_repo_main_branch_name=args.buildrepomainbranchname
        GeneralUtilities.assert_not_null(build_repo_main_branch_name,"buildrepomainbranchname is not set")

        if args.referencerepomainbranchname is not None:
            reference_repo_main_branch_name=args.referencerepomainbranchname
        GeneralUtilities.assert_not_null(reference_repo_main_branch_name,"referencerepomainbranchname is not set")

        if args.referenceremotename is not None:
            reference_remote_name=args.referenceremotename
        GeneralUtilities.assert_not_null(reference_remote_name,"referenceremotename is not set")

        if args.buildreporemotename is not None:
            build_repo_remote_name=args.buildreporemotename
        GeneralUtilities.assert_not_null(build_repo_remote_name,"buildreporemotename is not set")

        if args.artifactstargetfolder is not None:
            artifacts_target_folder=args.artifactstargetfolder

        if args.commonremoteurl is not None:
            common_remote_url=args.commonremoteurl
        GeneralUtilities.assert_not_null(common_remote_url,"commonremoteurl is not set")

        repository=os.path.join(build_repo,"Submodules",default_product_name)
        config:MergeToStableConfiguration=MergeToStableConfiguration(default_loglevel,default_source_branch,default_target_branch,repository,build_repo,common_remote_name,build_repo_main_branch_name,reference_repo_main_branch_name,reference_remote_name,build_repo_remote_name,artifacts_target_folder,common_remote_url,default_additionalargumentsfile)
        tFCPS_MergeToMain:TFCPS_MergeToStable=TFCPS_MergeToStable(config)
        return tFCPS_MergeToMain
