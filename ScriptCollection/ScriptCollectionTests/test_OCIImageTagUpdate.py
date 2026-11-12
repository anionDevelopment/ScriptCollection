import os
import tempfile
import unittest
from ..ScriptCollection.GeneralUtilities import GeneralUtilities, VersionEcholon
from ..ScriptCollection.OCIImages.OCIImageManager import OCIImageManager
from ..ScriptCollection.OCIImages.ConcreteImageHandlers.ImageHandlerDebian import ImageHandlerDebian
from ..ScriptCollection.OCIImages.ConcreteImageHandlers.ImageHandlerDebianSlim import ImageHandlerDebianSlim
from ..ScriptCollection.OCIImages.ConcreteImageHandlers.ImageHandlerGeneric import ImageHandlerGeneric
from ..ScriptCollection.OCIImages.ConcreteImageHandlers.ImageHandlerGenericV import ImageHandlerGenericV
from ..ScriptCollection.OCIImages.ConcreteImageHandlers.ImageHandlerGitlabCE import ImageHandlerGitlabCE
from .test_OCIImageManager import create_oci_image_manager, create_repository


def replace_registry(oci_image_manager: OCIImageManager, tags_per_registry_address: dict[str, list[str]]) -> list[str]:
    """Replaces the communication with the registries by the given tags, because a testcase must not communicate with a server.
    Returns the list of the registry-addresses which were asked for their tags."""
    asked_registry_addresses: list[str] = []

    def get_tags(registry_address: str) -> list[str]:
        asked_registry_addresses.append(registry_address)
        if registry_address not in tags_per_registry_address:
            raise ValueError(f"Simulated failure of the registry \"{registry_address}\".")
        return tags_per_registry_address[registry_address]
    setattr(oci_image_manager.registry_client, "get_tags", get_tags)
    return asked_registry_addresses


def create_registries_file(folder: str, lines: list[str]) -> str:
    result = os.path.join(folder, "Mounted.csv")
    GeneralUtilities.write_lines_to_file(result, ["ImageName;RegistryAddress"]+lines)
    return result


class OCIImageTagUpdateTests(unittest.TestCase):

    def test_handler_is_selected_by_image_name_and_tag_format(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_folder:
            # arrange
            oci_image_manager = create_oci_image_manager(temporary_folder, os.path.join(temporary_folder, "NotMounted.csv"), False, False)[0]

            # act & assert
            self.assertIsInstance(oci_image_manager.get_image_handler("Debian", "13.4-slim"), ImageHandlerDebianSlim)
            self.assertIsInstance(oci_image_manager.get_image_handler("Debian", "13.4"), ImageHandlerDebian)
            self.assertIsInstance(oci_image_manager.get_image_handler("Syft", "v1.41.2"), ImageHandlerGenericV)
            self.assertIsInstance(oci_image_manager.get_image_handler("Playwright", "v1.62.1-noble"), ImageHandlerGenericV)
            self.assertIsInstance(oci_image_manager.get_image_handler("Squid", "7.2-26.04_edge"), ImageHandlerGeneric)
            self.assertIsInstance(oci_image_manager.get_image_handler("GitLabCE", "18.5.1-ce.0"), ImageHandlerGitlabCE)

    def test_no_handler_is_available_for_a_tag_without_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_folder:
            # arrange
            oci_image_manager = create_oci_image_manager(temporary_folder, os.path.join(temporary_folder, "NotMounted.csv"), False, False)[0]

            # act & assert
            with self.assertRaises(ValueError):
                oci_image_manager.get_image_handler("Debian", "trixie-slim")

    def test_only_tags_with_the_same_prefix_suffix_and_amount_of_version_parts_have_the_same_format(self) -> None:
        # arrange
        handler = ImageHandlerGeneric()

        # act & assert
        self.assertTrue(handler.tag_has_same_format("Debian", "13.5-slim", "13.4-slim"))
        self.assertFalse(handler.tag_has_same_format("Debian", "13.5", "13.4-slim"))
        self.assertFalse(handler.tag_has_same_format("Debian", "13-slim", "13.4-slim"))
        self.assertFalse(handler.tag_has_same_format("Syft", "1.42.0", "v1.41.2"))
        self.assertFalse(handler.tag_has_same_format("Squid", "7.3-26.10_edge", "7.2-26.04_edge"))

    def test_latest_tag_with_the_same_format_is_chosen(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_folder:
            # arrange
            oci_image_manager = create_oci_image_manager(temporary_folder, os.path.join(temporary_folder, "NotMounted.csv"), False, False)[0]
            replace_registry(oci_image_manager, {"docker.io/library/debian": ["13.4-slim", "13.10-slim", "13.7-slim", "14", "14.0", "14-slim", "trixie-slim", "latest"]})

            # act
            actual_result = oci_image_manager.get_latest_tag_of_image("Debian", ["docker.io/library/debian"], "13.4-slim", VersionEcholon.LatestVersion)

            # assert
            self.assertEqual("13.10-slim", actual_result)

    def test_current_tag_is_kept_when_the_registry_only_has_older_tags(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_folder:
            # arrange
            oci_image_manager = create_oci_image_manager(temporary_folder, os.path.join(temporary_folder, "NotMounted.csv"), False, False)[0]
            replace_registry(oci_image_manager, {"docker.io/anchore/syft": ["v1.40.0", "v1.39.9"]})

            # act
            actual_result = oci_image_manager.get_latest_tag_of_image("Syft", ["docker.io/anchore/syft"], "v1.41.2", VersionEcholon.LatestVersion)

            # assert
            self.assertEqual("v1.41.2", actual_result)

    def test_latest_patch_does_not_update_the_minor_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_folder:
            # arrange
            oci_image_manager = create_oci_image_manager(temporary_folder, os.path.join(temporary_folder, "NotMounted.csv"), False, False)[0]
            replace_registry(oci_image_manager, {"docker.io/library/mariadb": ["12.2.3", "12.2.5", "12.3.1", "13.0.0"]})

            # act
            actual_result = oci_image_manager.get_latest_tag_of_image("MariaDB", ["docker.io/library/mariadb"], "12.2.2", VersionEcholon.LatestPatch)

            # assert
            self.assertEqual("12.2.5", actual_result)

    def test_default_tags_are_updated_using_the_custom_registry_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_folder:
            # arrange
            repository = create_repository(temporary_folder, ["Debian;docker.io/library/debian;13.4-slim"])
            registries_file = create_registries_file(temporary_folder, ["Debian;myregistry.example.com/debian"])
            oci_image_manager = create_oci_image_manager(temporary_folder, registries_file, False, False)[0]
            asked_registry_addresses = replace_registry(oci_image_manager, {"myregistry.example.com/debian": ["13.4-slim", "13.5-slim"]})

            # act
            oci_image_manager.update_default_tag_for_images_in_image_definitions_file(repository, True)

            # assert
            self.assertEqual(["myregistry.example.com/debian"], asked_registry_addresses)
            self.assertEqual("13.5-slim", oci_image_manager.get_tag_for_image(repository, "Debian"))

    def test_default_tag_is_kept_when_no_custom_registry_is_defined_and_only_the_custom_registry_may_be_used(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_folder:
            # arrange
            repository = create_repository(temporary_folder, ["Squid;ubuntu/squid;7.2-26.04_edge"])
            registries_file = create_registries_file(temporary_folder, [])
            oci_image_manager = create_oci_image_manager(temporary_folder, registries_file, False, False)[0]
            asked_registry_addresses = replace_registry(oci_image_manager, {"ubuntu/squid": ["7.3-26.04_edge"]})

            # act
            oci_image_manager.update_default_tag_for_images_in_image_definitions_file(repository, True)

            # assert
            self.assertEqual([], asked_registry_addresses)
            self.assertEqual("7.2-26.04_edge", oci_image_manager.get_tag_for_image(repository, "Squid"))

    def test_upstream_registry_is_used_too_when_not_only_the_custom_registry_may_be_used(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_folder:
            # arrange
            repository = create_repository(temporary_folder, ["Squid;ubuntu/squid;7.2-26.04_edge"])
            registries_file = create_registries_file(temporary_folder, [])
            oci_image_manager = create_oci_image_manager(temporary_folder, registries_file, False, False)[0]
            replace_registry(oci_image_manager, {"ubuntu/squid": ["7.3-26.04_edge"]})

            # act
            oci_image_manager.update_default_tag_for_images_in_image_definitions_file(repository, False)

            # assert
            self.assertEqual("7.3-26.04_edge", oci_image_manager.get_tag_for_image(repository, "Squid"))

    def test_default_tag_is_kept_when_the_registry_fails_and_the_other_images_are_still_updated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_folder:
            # arrange
            repository = create_repository(temporary_folder, ["Syft;docker.io/anchore/syft;v1.41.2", "PlantUML;plantuml/plantuml;1.2026.8"])
            registries_file = create_registries_file(temporary_folder, ["Syft;myregistry.example.com/syft", "PlantUML;myregistry.example.com/plantuml"])
            oci_image_manager = create_oci_image_manager(temporary_folder, registries_file, False, False)[0]
            replace_registry(oci_image_manager, {"myregistry.example.com/plantuml": ["1.2026.10"]})

            # act
            oci_image_manager.update_default_tag_for_images_in_image_definitions_file(repository, True)

            # assert
            self.assertEqual("v1.41.2", oci_image_manager.get_tag_for_image(repository, "Syft"))
            self.assertEqual("1.2026.10", oci_image_manager.get_tag_for_image(repository, "PlantUML"))
