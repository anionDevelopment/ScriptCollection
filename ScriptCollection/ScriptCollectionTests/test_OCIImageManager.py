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


def create_oci_image_manager(configuration_folder: str, mounted_registries_file: str, image_is_available_locally: bool, image_is_available_in_custom_registry: bool) -> tuple[OCIImageManager, list[tuple[str, str]]]:
    """Returns an OCIImageManager which reads its machine-wide configuration from the given folder instead of from the
    configuration-folder of the user who runs the test, and which looks for the file mounted by the host at the given
    path instead of at the path a real build-container has.
    The login to the registries, the lookup in the local image-store and the check whether an image is available in the
    custom registry are replaced by the given answers, because all of them would need a docker-installation (and a
    reachable registry), which a testcase must not depend on.
    Returns the manager and the list of the checks which were done with the replaced check (as image-address and tag),
    so a testcase can also verify which registry was asked and how often."""
    sc = ScriptCollectionCore()
    #Quiet, because the manager logs a warning when an image is taken from its fallback-registry, which is the expected
    #behaviour in some of the tests below and therefore must not appear in the output of the testrun.
    sc.log.loglevel = LogLevel.Quiet
    setattr(sc, "get_global_cache_folder", lambda: configuration_folder)
    setattr(sc, "login_to_defined_docker_registries", lambda: None)
    setattr(sc, "local_docker_image_exists", lambda image, tag: image_is_available_locally)
    availability_checks: list[tuple[str, str]] = []

    def image_is_available_in_registry(image: str, tag: str) -> bool:
        availability_checks.append((image, tag))
        return image_is_available_in_custom_registry
    setattr(sc, "image_is_available_in_registry", image_is_available_in_registry)
    result = OCIImageManager(sc)
    setattr(result, "get_image_registries_file_in_container", lambda: mounted_registries_file)
    return (result, availability_checks)


class OCIImageManagerTests(unittest.TestCase):

    def test_registries_file_of_the_configuration_folder_is_used_when_nothing_is_mounted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_folder:
            # arrange
            oci_image_manager = create_oci_image_manager(temporary_folder, os.path.join(temporary_folder, "NotMounted.csv"), False, True)[0]

            # act
            actual_result = oci_image_manager.get_global_docker_image_registries_file()

            # assert
            self.assertEqual(os.path.join(temporary_folder, "OCIImages", "ImageRegistries.csv"), actual_result)

    def test_registries_file_which_was_mounted_into_the_container_has_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_folder:
            # arrange
            mounted_registries_file = os.path.join(temporary_folder, "Mounted.csv")
            GeneralUtilities.write_lines_to_file(mounted_registries_file, ["ImageName;RegistryAddress"])
            oci_image_manager = create_oci_image_manager(temporary_folder, mounted_registries_file, False, True)[0]

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
            oci_image_manager = create_oci_image_manager(temporary_folder, mounted_registries_file, False, True)[0]

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
            oci_image_manager = create_oci_image_manager(temporary_folder, mounted_registries_file, False, True)[0]

            # act
            actual_result = oci_image_manager.get_registry_address_for_image_with_default_tag(repository, "MariaDB")

            # assert
            self.assertEqual("docker.io/library/mariadb:12.2.2", actual_result)

    def test_fallback_registry_of_the_repository_is_used_when_the_custom_registry_does_not_provide_the_image(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_folder:
            # arrange
            #this is the situation in which the custom registry is defined but can not deliver the image, for example because
            #no credentials for it are available or because it does not contain the image at all.
            repository = create_repository(temporary_folder, ["MariaDB;docker.io/library/mariadb;12.2.2"])
            mounted_registries_file = os.path.join(temporary_folder, "Mounted.csv")
            GeneralUtilities.write_lines_to_file(mounted_registries_file, ["ImageName;RegistryAddress", "MariaDB;myregistry.example.com/mariadb"])
            oci_image_manager, availability_checks = create_oci_image_manager(temporary_folder, mounted_registries_file, False, False)

            # act
            actual_result = oci_image_manager.get_registry_address_for_image_with_default_tag(repository, "MariaDB")

            # assert
            self.assertEqual("docker.io/library/mariadb:12.2.2", actual_result)
            #the availability is checked for the address of the custom registry with the tag which the repository defines.
            self.assertEqual([("myregistry.example.com/mariadb", "12.2.2")], availability_checks)

    def test_availability_of_an_image_in_the_custom_registry_is_only_checked_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_folder:
            # arrange
            repository = create_repository(temporary_folder, ["MariaDB;docker.io/library/mariadb;12.2.2"])
            mounted_registries_file = os.path.join(temporary_folder, "Mounted.csv")
            GeneralUtilities.write_lines_to_file(mounted_registries_file, ["ImageName;RegistryAddress", "MariaDB;myregistry.example.com/mariadb"])
            oci_image_manager, availability_checks = create_oci_image_manager(temporary_folder, mounted_registries_file, False, True)

            # act
            oci_image_manager.get_registry_address_for_image(repository, "MariaDB")
            oci_image_manager.get_registry_address_for_image(repository, "MariaDB")

            # assert
            #the address of an image is resolved several times per build, so the result of the check must be remembered.
            self.assertEqual([("myregistry.example.com/mariadb", "12.2.2")], availability_checks)

    def test_custom_registry_is_used_without_asking_it_when_the_image_is_already_available_locally(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_folder:
            # arrange
            #an image which is already available locally is not downloaded at all, so a build which uses it must not depend
            #on a reachable registry - which is why the custom registry is not asked whether it provides the image.
            repository = create_repository(temporary_folder, ["MariaDB;docker.io/library/mariadb;12.2.2"])
            mounted_registries_file = os.path.join(temporary_folder, "Mounted.csv")
            GeneralUtilities.write_lines_to_file(mounted_registries_file, ["ImageName;RegistryAddress", "MariaDB;myregistry.example.com/mariadb"])
            oci_image_manager, availability_checks = create_oci_image_manager(temporary_folder, mounted_registries_file, True, False)

            # act
            actual_result = oci_image_manager.get_registry_address_for_image_with_default_tag(repository, "MariaDB")

            # assert
            self.assertEqual("myregistry.example.com/mariadb:12.2.2", actual_result)
            self.assertEqual([], availability_checks)

    def test_custom_registry_address_is_returned_without_checking_its_availability(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_folder:
            # arrange
            #the dependency-update asks the custom registry for all tags it has, so it needs the address of that registry
            #even when the image is currently not available there with the tag which is defined at the moment.
            mounted_registries_file = os.path.join(temporary_folder, "Mounted.csv")
            GeneralUtilities.write_lines_to_file(mounted_registries_file, ["ImageName;RegistryAddress", "MariaDB;myregistry.example.com/mariadb"])
            oci_image_manager, availability_checks = create_oci_image_manager(temporary_folder, mounted_registries_file, False, False)

            # act
            actual_result = oci_image_manager.get_custom_registry_address_for_image("MariaDB")

            # assert
            self.assertEqual("myregistry.example.com/mariadb", actual_result)
            self.assertEqual([], availability_checks)
