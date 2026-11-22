import base64
import os
import tempfile
import unittest
import zipfile
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

SIGNING_ENVIRONMENT: dict[str, str] = {
    "Android_Signing_Keystore": base64.b64encode(b"content-of-the-keystore").decode("ascii"),
    "Android_Signing_StorePassword": "store-password",
    "Android_Signing_KeyAlias": "upload",
    "Android_Signing_KeyPassword": "key-password",
}


def create_app_bundle(folder: str, signature_files: dict[str, bytes]) -> str:
    """Writes an app-bundle (a zip-file) which contains a manifest and the given signature-files and returns it."""
    app_bundle = os.path.join(folder, "app.aab")
    with zipfile.ZipFile(app_bundle, "w") as archive:
        archive.writestr("base/manifest/AndroidManifest.xml", b"manifest")
        for name, content in signature_files.items():
            archive.writestr(name, content)
    return app_bundle


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

    def test_get_signing_environment_variables_for_runner(self) -> None:
        # act
        result = TFCPS_CodeUnitSpecific_Android_Functions.get_signing_environment_variables_for_runner(SIGNING_ENVIRONMENT)

        # assert
        self.assertEqual({
            "SC_ANDROID_SIGNING_KEYSTORE_BASE64": SIGNING_ENVIRONMENT["Android_Signing_Keystore"],
            "SC_ANDROID_SIGNING_STORE_PASSWORD": "store-password",
            "SC_ANDROID_SIGNING_KEY_ALIAS": "upload",
            "SC_ANDROID_SIGNING_KEY_PASSWORD": "key-password",
        }, result)

    def test_get_signing_environment_variables_for_runner_ignores_the_case_of_the_names(self) -> None:
        # arrange
        environment = {name.upper(): value for name, value in SIGNING_ENVIRONMENT.items()}

        # act
        result = TFCPS_CodeUnitSpecific_Android_Functions.get_signing_environment_variables_for_runner(environment)

        # assert
        self.assertEqual("upload", result["SC_ANDROID_SIGNING_KEY_ALIAS"])

    def test_get_signing_environment_variables_for_runner_removes_line_breaks_of_the_keystore(self) -> None:
        # arrange
        environment = dict(SIGNING_ENVIRONMENT)
        keystore = SIGNING_ENVIRONMENT["Android_Signing_Keystore"]
        environment["Android_Signing_Keystore"] = keystore[:8]+"\n"+keystore[8:]+"\n"

        # act
        result = TFCPS_CodeUnitSpecific_Android_Functions.get_signing_environment_variables_for_runner(environment)

        # assert
        self.assertEqual(keystore, result["SC_ANDROID_SIGNING_KEYSTORE_BASE64"])

    def test_get_signing_environment_variables_for_runner_requires_all_variables(self) -> None:
        # arrange
        environment = dict(SIGNING_ENVIRONMENT)
        del environment["Android_Signing_KeyPassword"]
        environment["Android_Signing_KeyAlias"] = " "

        # act
        with self.assertRaises(ValueError) as raised:
            TFCPS_CodeUnitSpecific_Android_Functions.get_signing_environment_variables_for_runner(environment)

        # assert
        self.assertIn("Android_Signing_KeyAlias, Android_Signing_KeyPassword", str(raised.exception))
        self.assertNotIn("store-password", str(raised.exception))

    def test_get_signing_environment_variables_for_runner_rejects_an_invalid_keystore(self) -> None:
        # arrange
        environment = dict(SIGNING_ENVIRONMENT)
        environment["Android_Signing_Keystore"] = "not base64!"

        # act & assert
        with self.assertRaises(ValueError):
            TFCPS_CodeUnitSpecific_Android_Functions.get_signing_environment_variables_for_runner(environment)

    def test_get_script_which_signs_with_upload_key(self) -> None:
        # act
        result = TFCPS_CodeUnitSpecific_Android_Functions.get_script_which_signs_with_upload_key(["gradlew", "--console=plain", "bundleRelease"])

        # assert
        self.assertEqual("""set -e; keystore_file="$(mktemp)"; trap 'rm -f "$keystore_file"' EXIT; printf '%s' "$SC_ANDROID_SIGNING_KEYSTORE_BASE64" | base64 -d > "$keystore_file"; unset SC_ANDROID_SIGNING_KEYSTORE_BASE64; export SC_ANDROID_SIGNING_STORE_FILE="$keystore_file"; bash gradlew --console=plain bundleRelease""", result)

    def test_app_bundle_without_signature_is_not_signed(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            app_bundle = create_app_bundle(folder, {})

            self.assertFalse(TFCPS_CodeUnitSpecific_Android_Functions.is_signed(app_bundle))
            self.assertFalse(TFCPS_CodeUnitSpecific_Android_Functions.is_signed_with_debug_key(app_bundle))

    def test_app_bundle_signed_with_debug_key(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            app_bundle = create_app_bundle(folder, {"META-INF/ANDROIDD.RSA": b"\x30\x82...\x0c\x0dAndroid Debug\x31..."})

            self.assertTrue(TFCPS_CodeUnitSpecific_Android_Functions.is_signed(app_bundle))
            self.assertTrue(TFCPS_CodeUnitSpecific_Android_Functions.is_signed_with_debug_key(app_bundle))

    def test_app_bundle_signed_with_upload_key(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            app_bundle = create_app_bundle(folder, {"META-INF/UPLOAD.RSA": b"\x30\x82...\x0c\x07Example\x31..."})

            self.assertTrue(TFCPS_CodeUnitSpecific_Android_Functions.is_signed(app_bundle))
            self.assertFalse(TFCPS_CodeUnitSpecific_Android_Functions.is_signed_with_debug_key(app_bundle))
