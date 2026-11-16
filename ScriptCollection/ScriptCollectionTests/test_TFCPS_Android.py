import unittest
from ..ScriptCollection.TFCPS.Android.TFCPS_CodeUnitSpecific_Android import TFCPS_CodeUnitSpecific_Android_Functions


BUILD_FILE_CONTENT: str = """plugins {
    id 'com.android.application' version '9.1.0'
    id("org.cyclonedx.bom") version("3.6.1")
}

android {
    defaultConfig {
        versionCode 1
        versionName "0.1.0"
    }
}

dependencies {
    testImplementation 'junit:junit:4.13.2'
    testImplementation "org.json:json:20260814"
}
"""


class TFCPS_AndroidTests(unittest.TestCase):

    def test_get_version_code(self) -> None:
        self.assertEqual(1002003, TFCPS_CodeUnitSpecific_Android_Functions.get_version_code("1.2.3"))
        self.assertEqual(1, TFCPS_CodeUnitSpecific_Android_Functions.get_version_code("0.0.1"))

    def test_get_version_code_rejects_too_large_parts(self) -> None:
        with self.assertRaises(Exception):
            TFCPS_CodeUnitSpecific_Android_Functions.get_version_code("1.1000.0")
        with self.assertRaises(Exception):
            TFCPS_CodeUnitSpecific_Android_Functions.get_version_code("2101.0.0")

    def test_get_version_code_rejects_invalid_version(self) -> None:
        with self.assertRaises(Exception):
            TFCPS_CodeUnitSpecific_Android_Functions.get_version_code("1.2")

    def test_set_version_in_build_file_content(self) -> None:
        # act
        result = TFCPS_CodeUnitSpecific_Android_Functions.set_version_in_build_file_content(BUILD_FILE_CONTENT, "2.3.4")

        # assert
        self.assertIn("versionCode 2003004\n", result)
        self.assertIn('versionName "2.3.4"\n', result)
        self.assertNotIn("0.1.0", result)

    def test_set_version_in_build_file_content_with_kotlin_assignment_syntax(self) -> None:
        # arrange
        content = 'versionCode = 5\nversionName = "1.0.0"\n'

        # act
        result = TFCPS_CodeUnitSpecific_Android_Functions.set_version_in_build_file_content(content, "1.0.1")

        # assert
        self.assertEqual('versionCode = 1000001\nversionName = "1.0.1"\n', result)

    def test_set_version_in_build_file_content_requires_exactly_one_version(self) -> None:
        with self.assertRaises(Exception):
            TFCPS_CodeUnitSpecific_Android_Functions.set_version_in_build_file_content('versionName "1.0.0"\n', "1.0.1")

    def test_get_dependencies_from_build_file_content(self) -> None:
        # act
        result = {dependency.dependencyname: dependency.current_version for dependency in TFCPS_CodeUnitSpecific_Android_Functions.get_dependencies_from_build_file_content(BUILD_FILE_CONTENT)}

        # assert
        self.assertEqual({
            "junit:junit": "4.13.2",
            "org.json:json": "20260814",
            "com.android.application": "9.1.0",
            "org.cyclonedx.bom": "3.6.1",
        }, result)

    def test_set_dependency_version_of_dependency(self) -> None:
        # act
        result = TFCPS_CodeUnitSpecific_Android_Functions.set_dependency_version_in_build_file_content(BUILD_FILE_CONTENT, "junit:junit", "4.14.0")

        # assert
        self.assertIn("testImplementation 'junit:junit:4.14.0'", result)
        self.assertIn('testImplementation "org.json:json:20260814"', result)

    def test_set_dependency_version_of_plugin(self) -> None:
        # act
        result = TFCPS_CodeUnitSpecific_Android_Functions.set_dependency_version_in_build_file_content(BUILD_FILE_CONTENT, "org.cyclonedx.bom", "3.7.0")

        # assert
        self.assertIn('id("org.cyclonedx.bom") version("3.7.0")', result)
        self.assertIn("id 'com.android.application' version '9.1.0'", result)

    def test_get_group_and_artifact_of_dependency(self) -> None:
        self.assertEqual(("junit", "junit"), TFCPS_CodeUnitSpecific_Android_Functions.get_group_and_artifact_of_dependency("junit:junit"))
        self.assertEqual(("com.android.application", "com.android.application.gradle.plugin"), TFCPS_CodeUnitSpecific_Android_Functions.get_group_and_artifact_of_dependency("com.android.application"))

    def test_normalize_released_version(self) -> None:
        self.assertEqual("1.2.3", TFCPS_CodeUnitSpecific_Android_Functions.normalize_released_version("1.2.3"))
        self.assertEqual("1.2.0", TFCPS_CodeUnitSpecific_Android_Functions.normalize_released_version("1.2"))
        self.assertIsNone(TFCPS_CodeUnitSpecific_Android_Functions.normalize_released_version("1.2.0-alpha01"))
        self.assertIsNone(TFCPS_CodeUnitSpecific_Android_Functions.normalize_released_version("20260814"))

    def test_get_script_which_preserves_exit_code(self) -> None:
        # act
        result = TFCPS_CodeUnitSpecific_Android_Functions.get_script_which_preserves_exit_code(["gradlew", "--console=plain", "verifyRoborazziDebug"], "build/outputs/roborazzi-comparison", "GradleExitCode.txt")

        # assert
        self.assertEqual("mkdir -p build/outputs/roborazzi-comparison; bash gradlew --console=plain verifyRoborazziDebug; echo $? > build/outputs/roborazzi-comparison/GradleExitCode.txt", result)
