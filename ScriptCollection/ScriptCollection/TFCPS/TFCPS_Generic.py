import argparse
from ..ScriptCollectionCore import ScriptCollectionCore
from ..SCLog import  LogLevel
from .TFCPS_Tools_General import TFCPS_Tools_General

class TFCPS_Generic_Functions:
    script_file:str = None
    repository_folder:str=None
    targetenvironmenttype:str = None
    additionalargumentsfile:str = None
    verbosity:LogLevel = None
    sc:ScriptCollectionCore = None
    tfcps_Tools_General:TFCPS_Tools_General = None
    __use_cache:bool = None
    
    def __init__(self,script_file:str,targetenvironmenttype:str,additionalargumentsfile:str,verbosity:LogLevel,use_cache:bool):
        self.verbosity=verbosity
        self.script_file=script_file
        self.sc=ScriptCollectionCore()
        self.sc.log.loglevel=self.verbosity
        self.tfcps_Tools_General=TFCPS_Tools_General(self.sc)
        self.repository_folder=self.sc.search_repository_folder(script_file)
        self.targetenvironmenttype=targetenvironmenttype
        self.__use_cache=use_cache
        self.additionalargumentsfile=additionalargumentsfile

    def use_cache(self)->bool:
        return self.__use_cache


class TFCPS_Generic_CLI:

    @staticmethod
    def parse(file:str)->TFCPS_Generic_Functions:
        parser = argparse.ArgumentParser()
        verbosity_values = ", ".join(f"{lvl.value}={lvl.name}" for lvl in LogLevel)
        parser.add_argument('-r', '--repository', required=False, default=None)
        parser.add_argument('-e', '--targetenvironmenttype', required=False, default="QualityCheck")
        parser.add_argument('-a', '--additionalargumentsfile', required=False, default=None)
        parser.add_argument('-v', '--verbosity', required=False, default=3, help=f"Sets the loglevel. Possible values: {verbosity_values}")
        parser.add_argument('-c', '--nocache',  action='store_true', required=False, default=False)
        args=parser.parse_args()
        result:TFCPS_Generic_Functions=TFCPS_Generic_Functions(file,args.targetenvironmenttype,args.additionalargumentsfile,LogLevel(int(args.verbosity)),not args.nocache)
        return result 
