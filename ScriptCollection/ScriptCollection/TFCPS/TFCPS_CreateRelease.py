import os
from ..GeneralUtilities import GeneralUtilities
from ..ScriptCollectionCore import ScriptCollectionCore
from ..SCLog import LogLevel
from .TFCPS_Tools_General import TFCPS_Tools_General
from .TFCPS_MergeToMain import TFCPS_MergeToMain,MergeToMainConfiguration
from .TFCPS_MergeToStable import TFCPS_MergeToStable,MergeToStableConfiguration
 

class TFCPS_CreateReleaseConfiguration:
    
    product_name: str = None
    branch_to_be_released:str = None
    additional_arguments_file:str = None
    log_level:LogLevel = None
    main_branch:str = None
    stable_branch:str = None
    build_repository:str = None
    repository:str = None
    reference_repository:str = None
    common_remote_name:str = None
    build_repo_main_branch_name:str = None
    reference_repo_main_branch_name:str = None
    reference_remote_name:str = None
    build_repo_remote_name:str = None
    artifacts_target_folder:str = None
    common_remote_url:str = None
    
    def __init__(self, current_file: str, product_name: str,branch_to_be_released:str,log_level:LogLevel,additional_arguments_file:str,main_branch:str,stable_branch:str,common_remote_name:str,build_repo_main_branch_name:str,reference_repo_main_branch_name:str,reference_remote_name:str,build_repo_remote_name:str,artifacts_target_folder:str,common_remote_url:str):
        self.product_name = product_name
        self.branch_to_be_released=branch_to_be_released
        self.additional_arguments_file=additional_arguments_file
        self.log_level=log_level
        self.main_branch=main_branch
        self.stable_branch=stable_branch
        self.build_repository=ScriptCollectionCore().search_repository_folder(current_file)
        self.repository=os.path.join(self.build_repository,"Submodules",product_name)
        self.reference_repository=os.path.join(self.build_repository,"Submodules",product_name+"Reference")
        self.common_remote_name=common_remote_name
        self.build_repo_main_branch_name=build_repo_main_branch_name
        self.reference_repo_main_branch_name=reference_repo_main_branch_name
        self.reference_remote_name=reference_remote_name
        self.build_repo_remote_name=build_repo_remote_name
        self.artifacts_target_folder=artifacts_target_folder
        self.common_remote_url=common_remote_url

class TFCPS_CreateRelease:

    sc:ScriptCollectionCore = None
    tFCPS_Tools_General:TFCPS_Tools_General = None

    def __init__(self):
        self.sc=ScriptCollectionCore()
        self.tFCPS_Tools_General=TFCPS_Tools_General(self.sc)

    @GeneralUtilities.check_arguments
    def do_release(self,tfcps_CreateReleaseConfiguration:TFCPS_CreateReleaseConfiguration)->bool:
        self.sc.log.loglevel=tfcps_CreateReleaseConfiguration.log_level
        return self.sc.do_and_log_task(f"Release {tfcps_CreateReleaseConfiguration.product_name}",lambda : self.__do(tfcps_CreateReleaseConfiguration))

    @GeneralUtilities.check_arguments
    def __do(self,tfcps_CreateReleaseConfiguration:TFCPS_CreateReleaseConfiguration)->bool:
        self.sc.log.log("Do checks...",LogLevel.Information)

        self.sc.assert_is_git_repository(tfcps_CreateReleaseConfiguration.build_repository)
        self.sc.assert_no_uncommitted_changes(tfcps_CreateReleaseConfiguration.build_repository)

        self.sc.assert_is_git_repository(tfcps_CreateReleaseConfiguration.repository)
        self.sc.assert_no_uncommitted_changes(tfcps_CreateReleaseConfiguration.repository)

        self.sc.assert_is_git_repository(tfcps_CreateReleaseConfiguration.reference_repository)
        self.sc.assert_no_uncommitted_changes(tfcps_CreateReleaseConfiguration.reference_repository)

        release_was_done:bool=False
        
        branch_to_be_released_commit_id = self.sc.git_get_commit_id(tfcps_CreateReleaseConfiguration.repository, tfcps_CreateReleaseConfiguration.branch_to_be_released)
        main_branch_commit_id = self.sc.git_get_commit_id(tfcps_CreateReleaseConfiguration.repository, tfcps_CreateReleaseConfiguration.main_branch)
        if branch_to_be_released_commit_id == main_branch_commit_id:
            self.sc.log.log("Merge to main-branch will not be done because there are no changed which can be merged.")
        else:
            self.sc.log.log("Merge to main-branch...",LogLevel.Information)
            mergeToMainConfiguration:MergeToMainConfiguration=MergeToMainConfiguration(tfcps_CreateReleaseConfiguration.current_file,tfcps_CreateReleaseConfiguration.product_name,tfcps_CreateReleaseConfiguration.product_name,tfcps_CreateReleaseConfiguration.branch_to_be_released,tfcps_CreateReleaseConfiguration.log_level,tfcps_CreateReleaseConfiguration.additional_arguments_file,tfcps_CreateReleaseConfiguration.main_branch,tfcps_CreateReleaseConfiguration.common_remote_name,tfcps_CreateReleaseConfiguration.build_repository)
            tFCPS_MergeToMain:TFCPS_MergeToMain=TFCPS_MergeToMain(mergeToMainConfiguration)
            tFCPS_MergeToMain.merge_to_main_branch()

        main_branch_commit_id = self.sc.git_get_commit_id(tfcps_CreateReleaseConfiguration.repository, tfcps_CreateReleaseConfiguration.main_branch)
        stable_branch_commit_id = self.sc.git_get_commit_id(tfcps_CreateReleaseConfiguration.repository, tfcps_CreateReleaseConfiguration.stable_branch)
        if main_branch_commit_id == stable_branch_commit_id:
            self.sc.log.log("Merge to stable-branch will not be done because there are no changed which can be released.")
        else:
            self.sc.log.log("Merge to stable-branch...",LogLevel.Information) 
            mergeToStableConfiguration:MergeToStableConfiguration=MergeToStableConfiguration(tfcps_CreateReleaseConfiguration.log_level,tfcps_CreateReleaseConfiguration.main_branch,tfcps_CreateReleaseConfiguration.stable_branch,tfcps_CreateReleaseConfiguration.repository,tfcps_CreateReleaseConfiguration.build_repository,tfcps_CreateReleaseConfiguration.common_remote_name,tfcps_CreateReleaseConfiguration.build_repo_main_branch_name,tfcps_CreateReleaseConfiguration.reference_repo_main_branch_name,tfcps_CreateReleaseConfiguration.reference_remote_name,tfcps_CreateReleaseConfiguration.build_repo_remote_name,tfcps_CreateReleaseConfiguration.artifacts_target_folder,tfcps_CreateReleaseConfiguration.common_remote_url,tfcps_CreateReleaseConfiguration.additional_arguments_file)
            tFCPS_MergeToStable:TFCPS_MergeToStable=TFCPS_MergeToStable(mergeToStableConfiguration)
            tFCPS_MergeToStable.merge_to_stable_branch()
            
            release_was_done=True

        return release_was_done
