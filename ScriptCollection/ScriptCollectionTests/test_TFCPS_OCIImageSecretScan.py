import io
import json
import os
import tarfile
import tempfile
import unittest
from ..ScriptCollection.GeneralUtilities import GeneralUtilities
from ..ScriptCollection.ScriptCollectionCore import ScriptCollectionCore
from ..ScriptCollection.TFCPS.TFCPS_OCIImageSecretScan import TFCPS_OCIImageSecretScan


def create_layer(files: dict[str, str]) -> bytes:
    """Creates the content of an image-layer (a tar-file) which contains the given files."""
    layer_stream = io.BytesIO()
    with tarfile.open(fileobj=layer_stream, mode="w") as layer:
        for file_name, file_content in files.items():
            content = file_content.encode("utf-8")
            member = tarfile.TarInfo(file_name)
            member.size = len(content)
            layer.addfile(member, io.BytesIO(content))
    return layer_stream.getvalue()


def create_image_artifact(image_file: str, metadata: dict, layers: list[dict[str, str]]) -> None:
    """Creates an image-artifact in the same shape as the tar-file produced by 'docker save'."""
    with tarfile.open(image_file, "w") as image_archive:
        metadata_content = json.dumps(metadata).encode("utf-8")
        metadata_member = tarfile.TarInfo("blobs/sha256/configuration")
        metadata_member.size = len(metadata_content)
        image_archive.addfile(metadata_member, io.BytesIO(metadata_content))
        for index, layer_files in enumerate(layers):
            layer_content = create_layer(layer_files)
            layer_member = tarfile.TarInfo(f"blobs/sha256/layer{index}")
            layer_member.size = len(layer_content)
            image_archive.addfile(layer_member, io.BytesIO(layer_content))


def create_metadata(created_by_entries: list[str], environment_variables: list[str] = None) -> dict:
    return {
        "history": [{"created_by": created_by} for created_by in created_by_entries],
        "config": {"Env": environment_variables or []},
    }


class TFCPS_OCIImageSecretScanTests(unittest.TestCase):

    def __scan(self, metadata: dict, layers: list[dict[str, str]]) -> list[str]:
        scan = TFCPS_OCIImageSecretScan(ScriptCollectionCore())
        with tempfile.TemporaryDirectory() as temporary_folder:
            image_file = os.path.join(temporary_folder, "image.tar")
            create_image_artifact(image_file, metadata, layers)
            return scan.scan_image_artifact(image_file)

    def test_scan_image_artifact_finds_credentials_in_url_in_image_history(self) -> None:
        # arrange
        metadata = create_metadata(["RUN |1 PipIndexUrlArguments=--index-url https://buildagent:s3cr3t@pypi.example.com/simple /bin/sh -c pip install -r requirements.txt"])

        # act
        actual_result = self.__scan(metadata, [])

        # assert
        assert len(actual_result) == 1
        assert "image-history" in actual_result[0]
        assert "https://buildagent:***@pypi.example.com" in actual_result[0]
        assert "s3cr3t" not in actual_result[0]

    def test_scan_image_artifact_finds_secret_assignment_in_image_history(self) -> None:
        # arrange
        metadata = create_metadata(["RUN |2 NuGetPassword=abc123def456 DotNetRuntime=linux-x64 /bin/sh -c dotnet restore"])

        # act
        actual_result = self.__scan(metadata, [])

        # assert
        assert len(actual_result) == 1
        assert "NuGetPassword" in actual_result[0]
        assert "abc123def456" not in actual_result[0]

    def test_scan_image_artifact_finds_secret_in_environment_variable_of_image(self) -> None:
        # arrange
        metadata = create_metadata([], ["PATH=/usr/bin", "MyAccessToken=abc123def456"])

        # act
        actual_result = self.__scan(metadata, [])

        # assert
        assert len(actual_result) == 1
        assert "image-environment-variable" in actual_result[0]
        assert "MyAccessToken" in actual_result[0]
        
    def test_scan_image_artifact_finds_credentials_in_configuration_file_in_layer(self) -> None:
        # arrange
        layer = {"root/.config/pip/pip.conf": "[global]\nindex-url = https://buildagent:s3cr3t@pypi.example.com/simple\n"}

        # act
        actual_result = self.__scan(create_metadata([]), [layer])

        # assert
        assert len(actual_result) == 1
        assert "pip.conf" in actual_result[0]

    def test_scan_image_artifact_does_not_report_secret_like_words_in_files_of_the_base_image(self) -> None:
        # arrange
        #the name-based heuristic must not be applied to the content of the files of a layer: a base-image contains thousands of
        #translation-resources and sample-configurations in which a word like "Password" is a label and not a secret.
        layers = [{
            "usr/lib/libreoffice/share/wizards/resources_en_US.properties": "Password=Password\nPasswordTitle=Enter the password\n",
            "etc/ImageMagick-7/delegates.xml": "<delegate decode=\"pdf\" command=\"gs -sPDFPassword=%%o\"/>\n",
        }]

        # act
        actual_result = self.__scan(create_metadata([]), layers)

        # assert
        assert not actual_result

    def test_scan_image_artifact_returns_nothing_for_an_image_without_secrets(self) -> None:
        # arrange
        metadata = create_metadata(["RUN |2 CodeUnitVersion=1.1.1 DotNetRuntime=linux-x64 /bin/sh -c apt-get update"], ["PATH=/usr/bin", "ISRUNNINGINCONTAINER=true"])
        layers = [{"etc/ssl/certs/ca.pem": "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n", "Workspace/Application/appsettings.json": "{\"Logging\":{\"LogLevel\":\"Information\"}}"}]

        # act
        actual_result = self.__scan(metadata, layers)

        # assert
        assert not actual_result

    def test_scan_image_artifact_ignores_a_reference_to_a_variable_as_value(self) -> None:
        # arrange
        metadata = create_metadata(["RUN /bin/sh -c echo \"MyToken=$MyToken\""], ["MyPassword=${MyPasswordVariable}"])

        # act
        actual_result = self.__scan(metadata, [])

        # assert
        assert not actual_result

    def test_scan_image_artifact_applies_the_betterleaks_allowlist(self) -> None:
        # arrange
        scan = TFCPS_OCIImageSecretScan(ScriptCollectionCore())
        layer = {"Workspace/Other/Certificates/DevelopmentCertificate.key": "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBg\n-----END PRIVATE KEY-----\n"}
        with tempfile.TemporaryDirectory() as repository:
            image_file = os.path.join(repository, "image.tar")
            create_image_artifact(image_file, create_metadata([]), [layer])

            # act
            result_without_allowlist = scan.scan_image_artifact(image_file, repository)
            GeneralUtilities.write_text_to_file(os.path.join(repository, ".betterleaks.toml"), """[[allowlists]]
description = "Development-certificate"
paths = ['''Workspace/Other/Certificates/''']
""")
            result_with_allowlist = scan.scan_image_artifact(image_file, repository)

            # assert
            assert len(result_without_allowlist) == 1
            assert not result_with_allowlist
