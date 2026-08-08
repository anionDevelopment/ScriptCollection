from pathlib import Path
from ScriptCollection.GeneralUtilities import GeneralUtilities
from ScriptCollection.ScriptCollectionCore import ScriptCollectionCore
from ScriptCollection.TFCPS.TFCPS_Tools_General import TFCPS_Tools_General
from ScriptCollection.TFCPS.TFCPS_Generic import TFCPS_Generic_CLI,TFCPS_Generic_Functions


def prepare_build_codeunits():
    tfcps_Generic_Functions:TFCPS_Generic_Functions=TFCPS_Generic_CLI.parse(__file__)
    t = TFCPS_Tools_General(ScriptCollectionCore())
    current_file = str(Path(__file__).absolute())
    repository_folder = GeneralUtilities.resolve_relative_path( "../../..", current_file)
    t.generate_tasksfile_from_workspace_file(repository_folder)
    t.generate_codeunits_overview_diagram(repository_folder)
    t.generate_svg_files_from_plantuml_files_for_repository(repository_folder,tfcps_Generic_Functions.use_cache())
 

if __name__ == "__main__":
    prepare_build_codeunits()
