import os
from ScriptCollection.GeneralUtilities import VersionEchelon
from ScriptCollection.TFCPS.TFCPS_Generic import TFCPS_Generic_CLI, TFCPS_Generic_Functions


def update_dependencies():
    t: TFCPS_Generic_Functions = TFCPS_Generic_CLI.parse(__file__)
    t.tfcps_Tools_General.update_dependencies_of_package_json_file(os.path.join(t.repository_folder, "package.json"), VersionEchelon.LatestVersion)


if __name__ == "__main__":
    update_dependencies()
