import os
import tempfile
import unittest
from unittest.mock import patch
from ..ScriptCollection.GeneralUtilities import GeneralUtilities
from ..ScriptCollection.ScriptCollectionCore import ScriptCollectionCore
from ..ScriptCollection.TFCPS.ContainerBuildEnvironment import ContainerBuildEnvironment
from ..ScriptCollection.TFCPS.TFCPS_Tools_General import TFCPS_Tools_General
from ..ScriptCollection.TFCPS.TFCPS_CodeUnit_BuildCodeUnits import TFCPS_CodeUnit_BuildCodeUnits
from .test_TFCPS_Other import create_build_codeunits_for_folder, isolated_scriptcollection_configuration, write_environment_variables_configuration_file, write_product_information_file


CERTIFICATE_CONTENT: str = "-----BEGIN CERTIFICATE-----\nMIIBexample\n-----END CERTIFICATE-----\n"


class RecordedContainerStart:
    """What a container-start of scbuildcodeunits -c gave docker: its arguments and the environment of the docker-client."""
    docker_arguments: list[str] = None
    docker_client_environment: dict[str, str] = None
    executed_host_scripts: list[str] = None

    def __init__(self):
        self.docker_arguments = None
        self.docker_client_environment = None
        self.executed_host_scripts = []

    def get_values_of(self, option: str) -> set[str]:
        return {self.docker_arguments[index+1] for index, argument in enumerate(self.docker_arguments) if argument == option}


def get_environment_without_trusted_root_cas() -> dict[str, str]:
    """Returns the environment of the current process without the TrustedRootCA-variables of the machine which runs the test, which would
    otherwise be collected too and make the test depend on the machine."""
    return {name: value for name, value in os.environ.items() if not name.lower().startswith("trustedrootca_")}


def create_container_build_environment(repository: str) -> ContainerBuildEnvironment:
    sc = ScriptCollectionCore()
    return ContainerBuildEnvironment(sc, TFCPS_Tools_General(sc), repository)


def write_build_environment_of_host(configuration_folder: str, certificate_folder: str) -> str:
    """Writes every part of the configuration of a host which a build-container gets and returns the file of the declared root-CA.
    Everything is declared in the configuration-file and not in the environment, because on Windows the name of an environment-variable
    is uppercased, which would make the name of the root-CA in the container depend on the operating-system which runs the test."""
    certificate_file = os.path.join(certificate_folder, "MyFileCA.pem")
    GeneralUtilities.write_text_to_file(certificate_file, CERTIFICATE_CONTENT)
    write_environment_variables_configuration_file(configuration_folder, [
        "MyRequiredVariable;literal;MyRequiredValue",
        "TrustedRootCA_MyInlineCA_ContentBase64;literal;bXlDZXJ0aWZpY2F0ZQ==",
        f"TrustedRootCA_MyFileCA_Path;literal;{certificate_file}",
    ])
    GeneralUtilities.ensure_directory_exists(os.path.join(configuration_folder, "TFCPS", "CustomScriptsForContainer"))
    return certificate_file


def start_build_container(build_codeunits: TFCPS_CodeUnit_BuildCodeUnits, repository: str, update_dependencies: bool = False) -> RecordedContainerStart:
    """Runs scbuildcodeunits -c (or scupdatedependencies in a container) up to the start of the container (on a host, not in a container)
    and records what docker would get."""
    recorded = RecordedContainerStart()

    def run_program(program: str, arguments: list[str], *_, **keyword_arguments) -> tuple[int, str, str, int]:
        if program == "docker":
            recorded.docker_arguments = arguments
            recorded.docker_client_environment = keyword_arguments.get("env_vars")
        return (0, "", "", 0)

    def run_custom_script_if_available(script_file: str, _: list[str]) -> None:
        recorded.executed_host_scripts.append(os.path.basename(script_file))

    tools = build_codeunits.tfcps_tools_general
    with patch.object(build_codeunits.sc, "run_program_argsasarray", side_effect=run_program), patch.object(build_codeunits.sc, "docker_pull"), patch.object(tools, "run_custom_script_if_available", side_effect=run_custom_script_if_available), patch.object(tools.oci_image_manager, "get_registry_address_for_image_with_default_tag", return_value="example/scbuilder:v1.0.0"), patch.object(build_codeunits, "_TFCPS_CodeUnit_BuildCodeUnits__is_running_in_container", return_value=False):
        if update_dependencies:
            build_codeunits.update_dependencies_in_container(repository)
        else:
            build_codeunits.build_codeunits_in_container(repository)
    return recorded


class ContainerBuildEnvironmentTests(unittest.TestCase):

    def test_build_container_gets_the_whole_build_environment_of_the_host(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as repository, tempfile.TemporaryDirectory() as configuration_folder, tempfile.TemporaryDirectory() as certificate_folder:
            write_product_information_file(repository, ["MyRequiredVariable"])
            certificate_file = write_build_environment_of_host(configuration_folder, certificate_folder)
            with isolated_scriptcollection_configuration(configuration_folder), patch.dict(os.environ, get_environment_without_trusted_root_cas(), clear=True):
                build_codeunits = create_build_codeunits_for_folder(repository)
                tfcps_folder = build_codeunits.sc.get_tfcps_configuration_folder()
                image_registries_file = build_codeunits.tfcps_tools_general.oci_image_manager.get_image_registries_file_in_configuration_folder()

                # act
                recorded = start_build_container(build_codeunits, repository)

                # assert
                #this is the behavior of scbuildcodeunits -c which must not change when the preparation is shared with scrais.
                self.assertEqual(["run", "--rm"], recorded.docker_arguments[0:2])
                self.assertEqual({
                    f"{repository}:/Workspace/Project/{os.path.basename(repository)}",
                    "/var/run/docker.sock:/var/run/docker.sock",
                    f"{os.path.join(tfcps_folder, 'CustomScriptsForContainer')}:/Workspace/CustomScripts",
                    f"{image_registries_file}:/Workspace/ScriptCollectionConfiguration/OCIImages/ImageRegistries.csv:ro",
                    f"{tfcps_folder}:/Workspace/ScriptCollectionConfiguration/TFCPS:ro",
                    f"{certificate_file}:/Workspace/RootCAs/MyFileCA.crt:ro",
                }, recorded.get_values_of("-v"))
                #only the names are arguments, the values are given to the docker-client through its environment.
                self.assertEqual({"MyRequiredVariable", "TrustedRootCA_MyInlineCA_ContentBase64"}, recorded.get_values_of("-e"))
                self.assertEqual({"MyRequiredVariable": "MyRequiredValue", "TrustedRootCA_MyInlineCA_ContentBase64": "bXlDZXJ0aWZpY2F0ZQ=="}, recorded.docker_client_environment)
                self.assertNotIn("MyRequiredValue", " ".join(recorded.docker_arguments))
                self.assertEqual(["CustomPreCodeUnitBuildScriptForContainer.py"], recorded.executed_host_scripts)

    def test_update_dependencies_container_gets_the_same_build_environment_as_the_build_container(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as repository, tempfile.TemporaryDirectory() as configuration_folder, tempfile.TemporaryDirectory() as certificate_folder:
            write_product_information_file(repository, ["MyRequiredVariable"])
            write_build_environment_of_host(configuration_folder, certificate_folder)
            with isolated_scriptcollection_configuration(configuration_folder), patch.dict(os.environ, get_environment_without_trusted_root_cas(), clear=True):
                build_codeunits = create_build_codeunits_for_folder(repository)

                # act
                build_container = start_build_container(build_codeunits, repository)
                update_dependencies_container = start_build_container(build_codeunits, repository, True)

                # assert
                self.assertEqual(build_container.get_values_of("-v"), update_dependencies_container.get_values_of("-v"))
                self.assertEqual(build_container.get_values_of("-e"), update_dependencies_container.get_values_of("-e"))
                self.assertEqual(build_container.docker_client_environment, update_dependencies_container.docker_client_environment)

    def test_build_container_gets_no_optional_parts_which_do_not_exist_on_the_host(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as repository, tempfile.TemporaryDirectory() as configuration_folder:
            write_product_information_file(repository, [])
            with isolated_scriptcollection_configuration(configuration_folder), patch.dict(os.environ, get_environment_without_trusted_root_cas(), clear=True):
                build_codeunits = create_build_codeunits_for_folder(repository)
                #the image-registries-file is created by the function which returns its path, so only the folders can be missing.
                image_registries_file = build_codeunits.tfcps_tools_general.oci_image_manager.get_image_registries_file_in_configuration_folder()

                # act
                recorded = start_build_container(build_codeunits, repository)

                # assert
                self.assertEqual({
                    f"{repository}:/Workspace/Project/{os.path.basename(repository)}",
                    "/var/run/docker.sock:/var/run/docker.sock",
                    f"{image_registries_file}:/Workspace/ScriptCollectionConfiguration/OCIImages/ImageRegistries.csv:ro",
                }, recorded.get_values_of("-v"))
                self.assertEqual(set(), recorded.get_values_of("-e"))

    def test_mounts_have_the_access_mode_of_the_build_container(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as repository, tempfile.TemporaryDirectory() as configuration_folder, tempfile.TemporaryDirectory() as certificate_folder:
            write_product_information_file(repository, ["MyRequiredVariable"])
            certificate_file = write_build_environment_of_host(configuration_folder, certificate_folder)
            with isolated_scriptcollection_configuration(configuration_folder), patch.dict(os.environ, get_environment_without_trusted_root_cas(), clear=True):
                container_build_environment = create_container_build_environment(repository)

                # act
                mounts = container_build_environment.get_mounts()

                # assert
                #only the custom-scripts-folder is writable, because its scripts use it as their own download-cache-folder.
                actual = {mount.target: (mount.source, mount.read_only) for mount in mounts}
                self.assertEqual((os.path.join(configuration_folder, "TFCPS", "CustomScriptsForContainer"), False), (os.path.normpath(actual["/Workspace/CustomScripts"][0]), actual["/Workspace/CustomScripts"][1]))
                self.assertTrue(actual["/Workspace/ScriptCollectionConfiguration/TFCPS"][1])
                self.assertTrue(actual["/Workspace/ScriptCollectionConfiguration/OCIImages/ImageRegistries.csv"][1])
                self.assertEqual((certificate_file, True), actual["/Workspace/RootCAs/MyFileCA.crt"])

    def test_environment_variables_contain_the_required_variables_and_the_inline_root_cas(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as repository, tempfile.TemporaryDirectory() as configuration_folder, tempfile.TemporaryDirectory() as certificate_folder:
            write_product_information_file(repository, ["MyRequiredVariable"])
            write_build_environment_of_host(configuration_folder, certificate_folder)
            with isolated_scriptcollection_configuration(configuration_folder), patch.dict(os.environ, get_environment_without_trusted_root_cas(), clear=True):
                container_build_environment = create_container_build_environment(repository)

                # act
                environment_variables = container_build_environment.get_environment_variables()

                # assert
                #the root-CA which is declared as file is mounted and is therefore not an environment-variable.
                self.assertEqual({"MyRequiredVariable": "MyRequiredValue", "TrustedRootCA_MyInlineCA_ContentBase64": "bXlDZXJ0aWZpY2F0ZQ=="}, environment_variables)

    def test_a_root_ca_name_which_is_declared_twice_is_rejected(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as repository, tempfile.TemporaryDirectory() as configuration_folder, tempfile.TemporaryDirectory() as certificate_folder:
            write_product_information_file(repository, [])
            certificate_file = os.path.join(certificate_folder, "MyCA.pem")
            GeneralUtilities.write_text_to_file(certificate_file, CERTIFICATE_CONTENT)
            write_environment_variables_configuration_file(configuration_folder, [f"TrustedRootCA_MyCA_Path;literal;{certificate_file}", "TrustedRootCA_MyCA_ContentBase64;literal;bXlDZXJ0aWZpY2F0ZQ=="])
            with isolated_scriptcollection_configuration(configuration_folder), patch.dict(os.environ, get_environment_without_trusted_root_cas(), clear=True):
                container_build_environment = create_container_build_environment(repository)

                # act & assert
                #the name becomes the filename in the trust-store, so one of the two certificates would silently replace the other one.
                with self.assertRaises(ValueError):
                    container_build_environment.get_mounts()

    def test_a_root_ca_file_which_is_not_a_certificate_is_rejected(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as repository, tempfile.TemporaryDirectory() as configuration_folder, tempfile.TemporaryDirectory() as certificate_folder:
            write_product_information_file(repository, [])
            certificate_file = os.path.join(certificate_folder, "MyCA.pem")
            GeneralUtilities.write_text_to_file(certificate_file, "not a certificate")
            write_environment_variables_configuration_file(configuration_folder, [f"TrustedRootCA_MyCA_Path;literal;{certificate_file}"])
            with isolated_scriptcollection_configuration(configuration_folder), patch.dict(os.environ, get_environment_without_trusted_root_cas(), clear=True):
                container_build_environment = create_container_build_environment(repository)

                # act & assert
                with self.assertRaises(ValueError):
                    container_build_environment.get_mounts()
