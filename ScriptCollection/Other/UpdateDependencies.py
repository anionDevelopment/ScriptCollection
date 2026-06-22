import os
import shutil
from ScriptCollection.GeneralUtilities import GeneralUtilities
from ScriptCollection.TFCPS.Python.TFCPS_CodeUnitSpecific_Python import TFCPS_CodeUnitSpecific_Python_Functions,TFCPS_CodeUnitSpecific_Python_CLI


def sync_bundled_dependency_versions():
    # The default tool-versions are maintained in '<repo>/Other/Resources/Dependencies/<tool>/Version.txt' as single
    # source of truth. Copy them into the package-resources so they are shipped with the wheel and can be read at runtime
    # (e.g. by scdownloadcachabletools in a build-image) via GeneralUtilities._internal_load_resource.
    folder_of_this_file = os.path.dirname(os.path.abspath(__file__))
    relative_paths = [
        "Dependencies/OpenAPIGenerator/Version.txt",
        "Dependencies/JRE/Version.txt",
    ]
    for relative_path in relative_paths:
        source_file = GeneralUtilities.resolve_relative_path(f"../../Other/Resources/{relative_path}", folder_of_this_file)
        target_file = GeneralUtilities.resolve_relative_path(f"../ScriptCollection/Resources/{relative_path}", folder_of_this_file)
        GeneralUtilities.assert_file_exists(source_file)
        GeneralUtilities.ensure_directory_exists(os.path.dirname(target_file))
        shutil.copyfile(source_file, target_file)


def update_dependencies():
    sync_bundled_dependency_versions()
    tf:TFCPS_CodeUnitSpecific_Python_Functions=TFCPS_CodeUnitSpecific_Python_CLI.parse(__file__)
    tf.update_dependencies()


if __name__ == "__main__":
    update_dependencies()
