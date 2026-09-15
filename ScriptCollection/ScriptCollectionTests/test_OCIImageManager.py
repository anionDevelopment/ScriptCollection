import os
import tempfile
import unittest
from ..ScriptCollection.GeneralUtilities import GeneralUtilities
from ..ScriptCollection.OCIImages.OCIImageManager import OCIImageManager
from ..ScriptCollection.ScriptCollectionCore import ScriptCollectionCore
from ..ScriptCollection.SCLog import LogLevel


def create_repository(folder: str, image_definition_lines: list[str]) -> str:
    """Creates the minimum of a repository which the OCIImageManager needs: a folder which is recognized as
    git-repository and the image-definition-file of that repository."""
    repository = os.path.join(folder, "Repository")
    GeneralUtilities.ensure_directory_exists(os.path.join(repository, ".git"))
    image_definition_file = os.path.join(repository, ".ScriptCollection", "OCIImages", "ImageDefinition.csv")
    GeneralUtilities.ensure_directory_exists(os.path.dirname(image_definition_file))
    GeneralUtilities.write_lines_to_file(image_definition_file, ["ImageName;UpstreamRegistryAddress;DefaultTag"]+image_definition_lines)
    return repository


def create_oci_image_manager(configuration_folder: str, mounted_registries_file: str) -> OCIImageManager:
    """Returns an OCIImageManager which reads its machine-wide configuration from the given folder instead of from the
    configuration-folder of the user who runs the test, and which looks for the file mounted by the host at the given
    path instead of at the path a real build-container has."""
    sc = ScriptCollectionCore()
    #Quiet, because the manager logs a warning when an image is taken from its fallback-registry, which is the expected
    #behaviour in one of the tests below and therefore must not appear in the output of the testrun.
    sc.log.loglevel = LogLevel.Quiet
    setattr(sc, "get_global_cache_folder", lambda: configuration_folder)
    result = OCIImageManager(sc)
    setattr(result, "get_image_registries_file_in_container", lambda: mounted_registries_file)
    return result


class OCIImageManagerTests(unittest.TestCase):

    def test_registries_file_of_the_configuration_folder_is_used_when_nothing_is_mounted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_folder:
            # arrange
            oci_image_manager = create_oci_image_manager(temporary_folder, os.path.join(temporary_folder, "NotMounted.csv"))

            # act
            actual_result = oci_image_manager.get_global_docker_image_registries_file()

            # assert
            self.assertEqual(os.path.join(temporary_folder, "OCIImages", "ImageRegistries.csv"), actual_result)

    def test_registries_file_which_was_mounted_into_the_container_has_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_folder:
            # arrange
            mounted_registries_file = os.path.join(temporary_folder, "Mounted.csv")
            GeneralUtilities.write_lines_to_file(mounted_registries_file, ["ImageName;RegistryAddress"])
            oci_image_manager = create_oci_image_manager(temporary_folder, mounted_registries_file)

            # act
            actual_result = oci_image_manager.get_global_docker_image_registries_file()

            # assert
            self.assertEqual(mounted_registries_file, actual_result)

    def test_custom_registry_of_the_mounted_registries_file_is_used_instead_of_the_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_folder:
            # arrange
            repository = create_repository(temporary_folder, ["MariaDB;docker.io/library/mariadb;12.2.2"])
            mounted_registries_file = os.path.join(temporary_folder, "Mounted.csv")
            GeneralUtilities.write_lines_to_file(mounted_registries_file, ["ImageName;RegistryAddress", "MariaDB;myregistry.example.com/mariadb"])
            oci_image_manager = create_oci_image_manager(temporary_folder, mounted_registries_file)

            # act
            actual_result = oci_image_manager.get_registry_address_for_image_with_default_tag(repository, "MariaDB")

            # assert
            self.assertEqual("myregistry.example.com/mariadb:12.2.2", actual_result)

    def test_fallback_registry_of_the_repository_is_used_when_no_custom_registry_is_defined(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_folder:
            # arrange
            repository = create_repository(temporary_folder, ["MariaDB;docker.io/library/mariadb;12.2.2"])
            mounted_registries_file = os.path.join(temporary_folder, "Mounted.csv")
            GeneralUtilities.write_lines_to_file(mounted_registries_file, ["ImageName;RegistryAddress", "PostgreSQL;myregistry.example.com/postgres"])
            oci_image_manager = create_oci_image_manager(temporary_folder, mounted_registries_file)

            # act
            actual_result = oci_image_manager.get_registry_address_for_image_with_default_tag(repository, "MariaDB")

            # assert
            self.assertEqual("docker.io/library/mariadb:12.2.2", actual_result)
