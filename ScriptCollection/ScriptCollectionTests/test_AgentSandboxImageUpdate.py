import os
import tempfile
import unittest
from ..ScriptCollection.GeneralUtilities import GeneralUtilities
from .test_TFCPS_Other import create_build_codeunits_for_folder


class AgentSandboxImageUpdateTests(unittest.TestCase):

    def __update(self, configuration_lines: list[str], image_definition_lines: list[str]) -> list[str]:
        # Runs the step of the build which lets the images of the agent-sandbox follow the image-definition-file and returns the resulting configuration-file.
        with tempfile.TemporaryDirectory() as repository:
            GeneralUtilities.ensure_directory_exists(os.path.join(repository, ".ScriptCollection", "OCIImages"))
            GeneralUtilities.write_lines_to_file(os.path.join(repository, ".ScriptCollection", "OCIImages", "ImageDefinition.csv"), ["ImageName;UpstreamRegistryAddress;DefaultTag"] + image_definition_lines)
            configuration_file = os.path.join(repository, ".ScriptCollection", "AgentSandboxConfiguration.ini")
            GeneralUtilities.write_lines_to_file(configuration_file, configuration_lines)
            build_codeunits = create_build_codeunits_for_folder(repository)
            build_codeunits._TFCPS_CodeUnit_BuildCodeUnits__update_agent_images(repository)  # pylint: disable=protected-access
            return GeneralUtilities.read_lines_from_file(configuration_file)

    def test_image_and_egress_proxy_image_get_their_own_image(self) -> None:
        # act
        result = self.__update(["[AgentSandboxConfiguration]", "codingagent = claude", "image = aniondev/scbuilder:v1.0.0", "drop_capabilities = true", "egress_proxy_image = ubuntu/squid:old", "[AllowedDomains]", "api.example.com = API of the agent"],
                               ["SCBuilder;aniondev/scbuilder;v2.0.0", "Squid;ubuntu/squid;7.2-26.04_edge"])

        # assert
        self.assertEqual(["[AgentSandboxConfiguration]", "codingagent = claude", "image = aniondev/scbuilder:v2.0.0", "drop_capabilities = true", "egress_proxy_image = ubuntu/squid:7.2-26.04_edge", "[AllowedDomains]", "api.example.com = API of the agent"], result)

    def test_missing_egress_proxy_image_is_added_to_the_section_of_the_sandbox(self) -> None:
        # act
        result = self.__update(["[AgentSandboxConfiguration]", "codingagent = claude", "image = aniondev/scbuilder:v2.0.0", "drop_capabilities = true"],
                               ["SCBuilder;aniondev/scbuilder;v2.0.0", "Squid;ubuntu/squid;7.2-26.04_edge"])

        # assert
        self.assertEqual(["[AgentSandboxConfiguration]", "egress_proxy_image = ubuntu/squid:7.2-26.04_edge", "codingagent = claude", "image = aniondev/scbuilder:v2.0.0", "drop_capabilities = true"], result)
        self.assertEqual(1, len([line for line in result if line.startswith("image =")]))

    def test_nothing_is_changed_for_an_image_which_is_not_defined(self) -> None:
        # act
        result = self.__update(["[AgentSandboxConfiguration]", "image = aniondev/scbuilder:v2.0.0"], ["SCBuilder;aniondev/scbuilder;v2.0.0"])

        # assert
        self.assertEqual(["[AgentSandboxConfiguration]", "image = aniondev/scbuilder:v2.0.0"], result)
