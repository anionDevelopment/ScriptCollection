import json
import os
import re
import tarfile
import tempfile
import tomllib
from ..GeneralUtilities import GeneralUtilities
from ..SCLog import LogLevel
from ..ScriptCollectionCore import ScriptCollectionCore


class TFCPS_OCIImageSecretScan:
    """Scans the OCI-image-artifacts of a repository for secrets.

    This is required in addition to the betterleaks-scan of the repository-content because that scan can not find these secrets:
    betterleaks does not look into archives, so the "*.tar"-files produced by the image-builds are invisible to it, and secrets
    which only exist in the image (build-arguments recorded in the image-history, environment-variables of the image and files
    which are generated or copied during the image-build) are not part of the repository-content at all. An image-artifact is
    published to a registry, so a secret contained in it is readable by everybody who is allowed to pull the image."""

    sc: ScriptCollectionCore = None

    #only the beginning of a file inside a layer is read: keys, tokens and configuration-entries are located at the beginning of small files, so reading more would only cost runtime.
    __maximum_amount_of_bytes_per_file: int = 1024*1024

    #files which are bigger than this are only checked by their name, not by their content, because they are program- or data-files which do not contain configuration.
    __maximum_size_of_file_to_read: int = 4*1024*1024

    #a private key must never be part of an image-artifact, independent of the file it is stored in.
    __private_key_pattern = re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")

    #credentials which are part of an url (for example "https://user:token@my-registry.example.com/simple"), which is the usual way credentials for package-sources leak into an image.
    __credentials_in_url_pattern = re.compile(r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.\-]*)://(?P<user>[^/\s:@]+):(?P<password>[^/\s@]+)@(?P<host>[^/\s]+)")

    #an assignment whose name indicates a secret (for example "NuGetPassword=abc123" in a build-argument recorded in the image-history).
    __secret_assignment_pattern = re.compile(r"(?i)\b(?P<name>[A-Za-z0-9_.\-]*(?:password|passwort|token|secret|apikey|api_key|credential|accesskey|privatekey)[A-Za-z0-9_.\-]*)\s*[=:]\s*(?P<value>[^\s\"']+)")

    #files whose name alone is a reason to look at their content even if the file-extension does not indicate a text-file.
    __sensitive_file_pattern = re.compile(r"(?i)(^|/)(\.npmrc|\.netrc|\.git-credentials|\.pypirc|pip\.conf|nuget\.config|credentials|id_rsa|id_dsa|id_ecdsa|id_ed25519)$|\.(pfx|p12|key|pem|jks|keystore)$")

    #file-extensions which typically contain configuration and therefore may contain credentials.
    __configuration_file_extensions: list[str] = [".conf", ".config", ".cfg", ".env", ".ini", ".json", ".properties", ".sh", ".toml", ".txt", ".xml", ".yaml", ".yml"]

    #values which look like a secret-assignment but obviously are none.
    __placeholder_values: list[str] = ["true", "false", "none", "null", "nil", "empty", "changeme", "unset", "todo"]

    def __init__(self, sc: ScriptCollectionCore):
        self.sc = sc

    @GeneralUtilities.check_arguments
    def search_for_secrets_in_image(self, image: str, repository_for_allowlist: str = None) -> list[str]:
        """Scans the given OCI-image for secrets and returns a human-readable description for every finding.
        'image' is the reference of an image which is already available in the local docker-instance (for example
        'myimage:1.0.0'); it is exported with 'docker save' and the resulting archive is scanned.
        'repository_for_allowlist' is optional: if it is given, the '[[allowlists]]'-entries of its '.betterleaks.toml' are
        applied, so the same allowlist-file applies to the repository-scan and to the image-scan."""
        self.sc.log.log(f"Search for secrets in image \"{image}\"...", LogLevel.Debug)
        temporary_folder: str = tempfile.mkdtemp()
        try:
            image_file: str = os.path.join(temporary_folder, "image.tar")
            #the image is exported instead of being read from the registry-storage directly, because 'docker save' produces a
            #documented archive-format which is independent of the storage-driver and of the used container-engine.
            result = self.sc.run_program_argsasarray("docker", ["save", image, "-o", image_file], throw_exception_if_exitcode_is_not_zero=False, print_live_output=False)
            if result[0] != 0:
                raise ValueError(f"The image '{image}' could not be exported (exit-code {result[0]}: {result[2].strip()}). The image must be available in the local docker-instance to be scanned.")
            findings: list[str] = self.scan_image_artifact(image_file, repository_for_allowlist)
        finally:
            GeneralUtilities.ensure_directory_does_not_exist(temporary_folder)
        return [f"image \"{image}\": {finding}" for finding in findings]

    @GeneralUtilities.check_arguments
    def scan_image_artifact(self, image_file: str, repository_for_allowlist: str = None) -> list[str]:
        """Scans a single image-artifact (a tar-file as produced by 'docker save' or 'docker buildx build --output type=docker')."""
        findings: list[str] = []
        with tarfile.open(image_file, "r") as image_archive:
            for member in image_archive.getmembers():
                if not member.isfile() or member.size == 0:
                    continue
                findings = findings+self.__scan_member_of_image_archive(image_archive, member)
        if repository_for_allowlist is None:
            return findings
        allowlist_patterns: list[re.Pattern] = self.__get_allowlist_patterns(repository_for_allowlist)
        return [finding for finding in findings if not self.__is_allowlisted(finding, allowlist_patterns)]

    @GeneralUtilities.check_arguments
    def __scan_member_of_image_archive(self, image_archive: tarfile.TarFile, member: tarfile.TarInfo) -> list[str]:
        #the members of an image-archive are either the image-metadata (json) or a layer (tar). Which one it is, is decided by
        #the content and not by the filename, because the docker-archive-format and the oci-archive-format use different names.
        member_file = image_archive.extractfile(member)
        if member_file is None:
            return []
        first_byte: bytes = member_file.read(1)
        member_file.seek(0)
        if first_byte in (b"{", b"["):
            return self.__scan_image_metadata(member_file)
        return self.__scan_layer(member_file)

    @GeneralUtilities.check_arguments
    def __scan_image_metadata(self, metadata_file) -> list[str]:
        try:
            metadata = json.loads(metadata_file.read().decode("utf-8", errors="ignore"))
        except ValueError:
            return []
        if not isinstance(metadata, dict):
            return []
        findings: list[str] = []
        #the history contains one entry per instruction of the containerfile. The build-arguments which were in scope are part of
        #the recorded command, which is why a secret passed via "--build-arg" ends up in the metadata of the published image.
        for history_entry in metadata.get("history") or []:
            if isinstance(history_entry, dict):
                findings = findings+[f"image-history: {description}" for description in self.__find_secrets_in_text(str(history_entry.get("created_by") or GeneralUtilities.empty_string), True)]
        configuration = metadata.get("config") or metadata.get("Config") or {}
        if isinstance(configuration, dict):
            for environment_variable in configuration.get("Env") or []:
                findings = findings+[f"image-environment-variable: {description}" for description in self.__find_secrets_in_text(str(environment_variable), True)]
            labels = configuration.get("Labels") or {}
            if isinstance(labels, dict):
                for label_name, label_value in labels.items():
                    findings = findings+[f"image-label: {description}" for description in self.__find_secrets_in_text(f"{label_name}={label_value}", True)]
        return findings

    @GeneralUtilities.check_arguments
    def __scan_layer(self, layer_file) -> list[str]:
        findings: list[str] = []
        try:
            #the layer is read as a stream because a layer can be several gigabytes big and does not have to be kept in memory.
            with tarfile.open(fileobj=layer_file, mode="r|*") as layer:
                for member in layer:
                    if not member.isfile() or member.size == 0:
                        continue
                    if not self.__content_of_member_should_be_checked(member):
                        continue
                    member_file = layer.extractfile(member)
                    if member_file is None:
                        continue
                    content: str = member_file.read(self.__maximum_amount_of_bytes_per_file).decode("utf-8", errors="ignore")
                    findings = findings+[f"file \"{self.__normalize_member_name(member.name)}\" in image-layer: {description}" for description in self.__find_secrets_in_text(content, False)]
        except tarfile.TarError:
            #the member is not a layer (for example a signature- or an index-file). Such members do not contain secrets.
            return []
        return findings

    @GeneralUtilities.check_arguments
    def __content_of_member_should_be_checked(self, member: tarfile.TarInfo) -> bool:
        name: str = self.__normalize_member_name(member.name)
        if os.path.basename(name).startswith(".wh."):
            return False  # a whiteout-file marks a deletion and has no content
        if self.__sensitive_file_pattern.search(name) is not None:
            return True
        if self.__maximum_size_of_file_to_read < member.size:
            return False
        return os.path.splitext(name)[1].lower() in self.__configuration_file_extensions

    @GeneralUtilities.check_arguments
    def __normalize_member_name(self, member_name: str) -> str:
        result: str = member_name.replace("\\", "/")
        if result.startswith("./"):
            result = result[2:]
        return result

    @GeneralUtilities.check_arguments
    def __find_secrets_in_text(self, text: str, check_assignments: bool) -> list[str]:
        """Returns a description for every secret found in the given text. The descriptions never contain the secret itself,
        because they are written to the build-log, which is usually kept and often readable by more people than the secret.

        'check_assignments' enables the name-based heuristic which reports an assignment whose name indicates a secret (for
        example 'NuGetPassword=abc123'). It is only meaningful for the image-metadata, where the amount of values is small and
        every value was set by the build itself. For the content of the files of a layer it must be disabled: a layer contains
        thousands of files of the base-image (translation-resources, sample-configurations, documentation) in which a word like
        'Password' is a label and not a secret, which would drown the real findings in false positives."""
        findings: list[str] = []
        if not GeneralUtilities.string_has_content(text):
            return findings
        if self.__private_key_pattern.search(text) is not None:
            findings.append("contains a private key")
        for match in self.__credentials_in_url_pattern.finditer(text):
            findings.append(f"contains credentials in the url \"{match.group('scheme')}://{match.group('user')}:***@{match.group('host')}\"")
        if check_assignments:
            for match in self.__secret_assignment_pattern.finditer(text):
                if self.__value_is_a_secret(match.group("value")):
                    findings.append(f"contains a value for \"{match.group('name')}\"")
        return findings

    @GeneralUtilities.check_arguments
    def __value_is_a_secret(self, value: str) -> bool:
        value = value.strip().strip("\"'")
        if not GeneralUtilities.string_has_content(value):
            return False
        if value.lower() in self.__placeholder_values:
            return False
        if set(value) == {"*"}:
            return False
        #a reference to a variable (for example "$MyToken", "${MyToken}" or "%MyToken%") is the desired way to handle a secret and therefore not a finding.
        if value.startswith("$") or (value.startswith("%") and value.endswith("%")):
            return False
        return True

    @GeneralUtilities.check_arguments
    def __get_allowlist_patterns(self, repository: str) -> list[re.Pattern]:
        """Reads the allowlisted paths and regexes from '<repository>/.betterleaks.toml' so the image-scan honours the same
        allowlist as the repository-scan instead of requiring a second configuration-file."""
        configuration_file: str = os.path.join(repository, ".betterleaks.toml")
        if not os.path.isfile(configuration_file):
            return []
        try:
            with open(configuration_file, "rb") as file_handle:
                configuration = tomllib.load(file_handle)
        except tomllib.TOMLDecodeError as exception:
            self.sc.log.log_exception(f"'{configuration_file}' could not be parsed, so no allowlist is applied to the image-scan:", exception, LogLevel.Warning)
            return []
        allowlists: list = []
        for key in ("allowlist", "allowlists"):
            value = configuration.get(key)
            if isinstance(value, dict):
                allowlists.append(value)
            elif isinstance(value, list):
                allowlists = allowlists+[entry for entry in value if isinstance(entry, dict)]
        result: list[re.Pattern] = []
        for allowlist in allowlists:
            for key in ("paths", "regexes"):
                for pattern in allowlist.get(key) or []:
                    try:
                        result.append(re.compile(str(pattern)))
                    except re.error as exception:
                        self.sc.log.log_exception(f"The allowlist-entry '{pattern}' of '{configuration_file}' is not a valid regular expression and is therefore ignored:", exception, LogLevel.Warning)
        return result

    @GeneralUtilities.check_arguments
    def __is_allowlisted(self, finding: str, allowlist_patterns: list[re.Pattern]) -> bool:
        return any(pattern.search(finding) is not None for pattern in allowlist_patterns)
