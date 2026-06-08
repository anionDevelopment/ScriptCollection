import argparse
import os
from ..GeneralUtilities import GeneralUtilities
from ..SCLog import LogLevel
from ..ScriptCollectionCore import ScriptCollectionCore
from .TFCPS_Tools_General import TFCPS_Tools_General
from .TFCPS_CodeUnit_BuildCodeUnits import TFCPS_CodeUnit_BuildCodeUnits
from .TFCPS_Generic import TFCPS_Generic_Functions

class MergeToMainConfiguration:
    product_name: str
    merge_source_branch:str
    additional_arguments_file:str
    log_level:LogLevel
    main_branch:str
    repository_folder:str
    tFCPS_Generic_Functions:TFCPS_Generic_Functions
    common_remote_name:str
    build_repo:str
    sc:ScriptCollectionCore=ScriptCollectionCore()

    def __init__(self, current_file: str,repository:str, product_name: str,merge_source_branch:str,log_level:LogLevel,additional_arguments_file:str,main_branch:str,common_remote_name:str,build_repo:str):
        self.sc.log.loglevel=log_level
        self.repository_folder = repository
        self.product_name = product_name
        self.merge_source_branch=merge_source_branch
        self.additional_arguments_file=additional_arguments_file
        self.log_level=log_level
        self.main_branch=main_branch
        self.common_remote_name=common_remote_name
        self.build_repo=build_repo

class TFCPS_MergeToMain:

    sc:ScriptCollectionCore
    tFCPS_Tools_General:TFCPS_Tools_General
    generic_prepare_new_release_arguments:MergeToMainConfiguration=None

    def __init__(self,generic_prepare_new_release_arguments:MergeToMainConfiguration):
        self.sc=ScriptCollectionCore()
        self.tFCPS_Tools_General=TFCPS_Tools_General(self.sc)
        self.generic_prepare_new_release_arguments=generic_prepare_new_release_arguments

    @GeneralUtilities.check_arguments
    def merge_to_main_branch(self ) -> None:
        self.sc.log.loglevel=self.generic_prepare_new_release_arguments.log_level
        self.sc.log.log("Merge to main-branch...")
        fast_forward_source_branch: bool=True
        source_branch: str=self.generic_prepare_new_release_arguments.merge_source_branch
        target_branch: str=self.generic_prepare_new_release_arguments.main_branch
        self.sc.assert_is_git_repository(self.generic_prepare_new_release_arguments.repository_folder)

        if self.sc.git_get_commit_id(self.generic_prepare_new_release_arguments.repository_folder,source_branch)==self.sc.git_get_commit_id(self.generic_prepare_new_release_arguments.repository_folder,target_branch):
            self.sc.log.log("Source- and target-branch are on the same commit.")
            return

        self.sc.assert_no_uncommitted_changes(self.generic_prepare_new_release_arguments.repository_folder)
        self.sc.git_checkout(self.generic_prepare_new_release_arguments.repository_folder, source_branch)
        self.sc.assert_no_uncommitted_changes(self.generic_prepare_new_release_arguments.repository_folder)

        #premerge-build
        #TODO the premerge-build is now supposed to be in MergeToStable
        try:
            tfcps_CodeUnit_BuildCodeUnits:TFCPS_CodeUnit_BuildCodeUnits=TFCPS_CodeUnit_BuildCodeUnits(self.generic_prepare_new_release_arguments.repository_folder,self.sc.log.loglevel,"QualityCheck",self.generic_prepare_new_release_arguments.additional_arguments_file,False,True,False)
            tfcps_CodeUnit_BuildCodeUnits.build_codeunits()
        except Exception:
            self.sc.log.log(f"Branch {source_branch} is not buildable.",LogLevel.Error)
            self.sc.git_undo_all_changes(self.generic_prepare_new_release_arguments.repository_folder)
            raise
        self.sc.git_commit(self.generic_prepare_new_release_arguments.repository_folder, 'Pre-merge-commit', stage_all_changes=True, no_changes_behavior=0)


        if fast_forward_source_branch:
            self.sc.git_checkout(self.generic_prepare_new_release_arguments.repository_folder, source_branch)
            project_version:str=self.tFCPS_Tools_General.get_version_of_project(self.generic_prepare_new_release_arguments.repository_folder)
            self.sc.git_merge(self.generic_prepare_new_release_arguments.repository_folder, source_branch, target_branch, False, True)
            self.sc.git_merge(self.generic_prepare_new_release_arguments.repository_folder, target_branch, source_branch, True, True)
            self.sc.git_create_tag(self.generic_prepare_new_release_arguments.repository_folder,target_branch,f"v{project_version}")

        self.sc.log.log("Push branches...")
        self.sc.git_push_with_retry(self.generic_prepare_new_release_arguments.repository_folder,self.generic_prepare_new_release_arguments.common_remote_name,source_branch,source_branch)
        self.sc.git_push_with_retry(self.generic_prepare_new_release_arguments.repository_folder,self.generic_prepare_new_release_arguments.common_remote_name,target_branch,target_branch)
        self.sc.git_commit(self.generic_prepare_new_release_arguments.build_repo,"Updated submodule")

class TFCPS_MergeToMain_CLI:

    @staticmethod
    @GeneralUtilities.check_arguments
    def get_with_overwritable_defaults(file:str,default_merge_source_branch:str=None,default_loglevel:LogLevel=None,default_additionalargumentsfile:str=None,default_main_branch:str=None,default_common_remote_name:str=None)->TFCPS_MergeToMain:
        parser = argparse.ArgumentParser()
        verbosity_values = ", ".join(f"{lvl.value}={lvl.name}" for lvl in LogLevel)
        parser.add_argument('-s', '--mergesourcebranch', required=False)
        parser.add_argument('-a', '--additionalargumentsfile', required=False)
        parser.add_argument('-t', '--mainbranch', required=False)
        parser.add_argument('-r', '--commonremotename', required=False)
        parser.add_argument('-v', '--verbosity', required=False, help=f"Sets the loglevel. Possible values: {verbosity_values}")
        args=parser.parse_args()

        sc:ScriptCollectionCore=ScriptCollectionCore()

        build_repo=GeneralUtilities.resolve_relative_path("../../..",file)
        sc.assert_is_git_repository(build_repo)

        default_product_name=TFCPS_Tools_General(sc).get_product_name(build_repo)

        if args.mergesourcebranch is not None: 
            default_merge_source_branch=args.mergesourcebranch#other/next-release
        GeneralUtilities.assert_not_null(default_merge_source_branch,"mergesourcebranch is not set")

        if args.verbosity is not None:
            default_loglevel=LogLevel(int( args.verbosity))
        GeneralUtilities.assert_not_null(default_loglevel,"verbosity is not set")

        if args.additionalargumentsfile is not None:
            default_additionalargumentsfile=args.additionalargumentsfile

        if args.mainbranch is not None: 
            default_main_branch=args.mainbranch#main
        GeneralUtilities.assert_not_null(default_main_branch,"mainbranch is not set")

        if args.commonremotename is not None:
            default_common_remote_name=args.commonremotename
        GeneralUtilities.assert_not_null(default_common_remote_name,"commonremotename is not set")

        repository=os.path.join(build_repo,"Submodules",default_product_name)
        config:MergeToMainConfiguration=MergeToMainConfiguration(file,repository,default_product_name,default_merge_source_branch,default_loglevel,default_additionalargumentsfile,default_main_branch,default_common_remote_name,build_repo)
        tFCPS_MergeToMain:TFCPS_MergeToMain=TFCPS_MergeToMain(config)
        return tFCPS_MergeToMain
