import argparse
from ..SCLog import  LogLevel
from ..ScriptCollectionCore import GeneralUtilities
from ..ScriptCollectionCore import ScriptCollectionCore
from .TFCPS_Tools_General import TFCPS_Tools_General

class TFCPS_PreBuildCodeunitsScriptConfiguration:
    targetenvironmenttype:str = None
    additionalargumentsfile:str = None
    verbosity:LogLevel = None
    use_cache:str = None
    repository_folder:str=None
    sc:ScriptCollectionCore=None
    tfcps_Tools_General:TFCPS_Tools_General = None

    def __init__(self,script_file:str,targetenvironmenttype:str,additionalargumentsfile:str,verbosity:LogLevel,use_cache:bool):
        self.targetenvironmenttype=targetenvironmenttype
        self.additionalargumentsfile=additionalargumentsfile
        self.verbosity=verbosity
        self.use_cache=use_cache
        self.sc=ScriptCollectionCore()
        self.sc.log.loglevel=self.verbosity
        self.repository_folder=ScriptCollectionCore().search_repository_folder(script_file)
        self.tfcps_Tools_General=TFCPS_Tools_General(self.sc)

class TFCPS_PreBuildCodeunitsScript:
    configuration:TFCPS_PreBuildCodeunitsScriptConfiguration = None

    def __init__(self,configuration:TFCPS_PreBuildCodeunitsScriptConfiguration):
        self.configuration=configuration

    @GeneralUtilities.check_arguments
    def pre_merge(self):
        pass#TODO

class TFCPS_PreBuildCodeunitsScript_CLI():

    @staticmethod
    @GeneralUtilities.check_arguments
    def parse(script_file:str)->argparse.ArgumentParser:
        parser = argparse.ArgumentParser()
        verbosity_values = ", ".join(f"{lvl.value}={lvl.name}" for lvl in LogLevel)
        parser.add_argument('-e', '--targetenvironmenttype', required=False, default="QualityCheck")
        parser.add_argument('-a', '--additionalargumentsfile', required=False, default=None)
        parser.add_argument('-v', '--verbosity', required=False, default=3, help=f"Sets the loglevel. Possible values: {verbosity_values}")
        parser.add_argument('-c', '--nocache',  action='store_true', required=False, default=False)
        args=parser.parse_args()
        return TFCPS_PreBuildCodeunitsScript(TFCPS_PreBuildCodeunitsScriptConfiguration(script_file,args.targetenvironmenttype,args.additionalargumentsfile,LogLevel(int(args.verbosity)),not args.nocache))
