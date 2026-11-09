import unittest
from ..ScriptCollection.TFCPS.DotNet.TFCPS_CodeUnitSpecific_DotNet import TFCPS_CodeUnitSpecific_DotNet_Functions


class DotNetWindowsTargetingTests(unittest.TestCase):

    def test_windows_targeting_is_enabled_for_windows_runtime_on_linux_when_requested(self) -> None:
        # act
        actual_result = TFCPS_CodeUnitSpecific_DotNet_Functions.get_windows_targeting_arguments(["win-x64"], "Linux", True)

        # assert
        self.assertEqual(["-p:EnableWindowsTargeting=true"], actual_result)

    def test_windows_targeting_is_enabled_when_one_of_several_runtimes_is_a_windows_runtime(self) -> None:
        # The restore covers all runtimes at once, so one windows-runtime is enough to require the windows-targeting.
        # act
        actual_result = TFCPS_CodeUnitSpecific_DotNet_Functions.get_windows_targeting_arguments(["linux-x64", "win-arm64"], "Linux", True)

        # assert
        self.assertEqual(["-p:EnableWindowsTargeting=true"], actual_result)

    def test_windows_targeting_is_not_enabled_when_not_requested(self) -> None:
        # act
        actual_result = TFCPS_CodeUnitSpecific_DotNet_Functions.get_windows_targeting_arguments(["win-x64"], "Linux", False)

        # assert
        self.assertEqual([], actual_result)

    def test_windows_targeting_is_not_enabled_on_windows_host(self) -> None:
        # act
        actual_result = TFCPS_CodeUnitSpecific_DotNet_Functions.get_windows_targeting_arguments(["win-x64"], "Windows", True)

        # assert
        self.assertEqual([], actual_result)

    def test_windows_targeting_is_not_enabled_for_non_windows_runtimes(self) -> None:
        # act
        actual_result = TFCPS_CodeUnitSpecific_DotNet_Functions.get_windows_targeting_arguments(["linux-x64", "osx-arm64"], "Linux", True)

        # assert
        self.assertEqual([], actual_result)
