import base64
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
import requests
from ..GeneralUtilities import GeneralUtilities
from ..ScriptCollectionCore import ScriptCollectionCore
from ..SCLog import LogLevel
from .TFCPS_CodeSpellCheck import TFCPS_CodeSpellCheck
from .TFCPS_FindingsSorter import TFCPS_FindingsSorter


class TFCPS_ProjectLinting:
    """Contains the linting-tasks which affect the whole repository (for example typos, the findings-list, the openspec-specifications
    and the security.txt-file) and not only a single codeunit."""

    sc: ScriptCollectionCore = None

    def __init__(self, sc: ScriptCollectionCore):
        self.sc = sc

    @GeneralUtilities.check_arguments
    def do_project_linting(self, repository_folder: str) -> None:
        """Does the linting-tasks which affect the whole repository and not only a single codeunit. Every finding is only reported as
        warning and does not let the caller fail."""
        self.sc.log.log("Do project-linting...")
        self.__run_codespell(repository_folder)
        self.__sort_findings(repository_folder)
        self.__validate_openspec(repository_folder)
        self.__check_security_txt_file(repository_folder)

    @GeneralUtilities.check_arguments
    def __run_codespell(self, repository_folder: str) -> None:
        """Searches for typos in the repository using codespell. Findings are only reported as warnings and do not let the build fail.
        Only files which are not git-ignored are checked. See TFCPS_CodeSpellCheck for details."""
        try:
            self.sc.log.log("Search for typos using codespell...",LogLevel.Debug)
            findings: list[str] = TFCPS_CodeSpellCheck(self.sc).search_for_typos(repository_folder)
            for finding in findings:
                self.sc.log.log(f"Possible typo: {finding}", LogLevel.Warning)
            if 0 < len(findings):
                self.sc.log.log(f"codespell found {len(findings)} possible typo(s). It is recommended to fix them by running \"codespell -w\" in the repository-folder. Known false positives can be ignored using the file \".codespellrc\" in the repository-folder.", LogLevel.Warning)
        except Exception as e:
            self.sc.log.log(f"An error occurred while running codespell: {e}", LogLevel.Warning)

    @GeneralUtilities.check_arguments
    def __sort_findings(self, repository_folder: str) -> None:
        self.sc.log.log("Sort findings...",LogLevel.Debug)
        TFCPS_FindingsSorter().sort_findings(repository_folder)

    @GeneralUtilities.check_arguments
    def __validate_openspec(self,repository:str) -> None:
        openspec_configuration_file: str = os.path.join(repository, "openspec", "config.yaml")
        if os.path.isfile(openspec_configuration_file):
            self.sc.log.log("Validate openspec-specifications...")
            try:
                self.sc.run_with_epew("openspec", "validate --all --strict", repository)
            except Exception as e:
                self.sc.log.log_exception(f"Openspec validation failed.",e,LogLevel.Warning)

    @GeneralUtilities.check_arguments
    def __check_security_txt_file(self, repository_folder: str) -> None:
        """Checks the file '<repository>/.well-known/security.txt' (see RFC 9116). Every failed check is only reported as warning and does
        not let the build fail. The URLs of the file are only checked if an internet-connection is available."""
        security_txt_file: str = os.path.join(repository_folder, ".well-known", "security.txt")
        if not os.path.isfile(security_txt_file):
            self.sc.log.log(f"The file '{security_txt_file}' does not exist.", LogLevel.Warning)
            return
        self.sc.log.log("Check security.txt-file...", LogLevel.Debug)
        fields: dict[str, list[str]] = TFCPS_ProjectLinting.__get_security_txt_fields(security_txt_file)
        internet_connection_is_available: bool = GeneralUtilities.internet_connection_is_available()
        self.__check_security_txt_signature(security_txt_file, fields, internet_connection_is_available)
        self.__check_security_txt_expiration(security_txt_file, fields, GeneralUtilities.get_now())
        if internet_connection_is_available:
            self.__check_security_txt_urls_are_reachable(security_txt_file, fields, "Canonical")
            self.__check_security_txt_urls_are_reachable(security_txt_file, fields, "Encryption")
        else:
            self.sc.log.log(f"The URLs of '{security_txt_file}' are not checked because no internet-connection is available.", LogLevel.Debug)

    @staticmethod
    @GeneralUtilities.check_arguments
    def __get_security_txt_fields(security_txt_file: str) -> dict[str, list[str]]:
        """Returns the values of the fields of the given security.txt-file, grouped by the lowercase field-name (field-names are
        case-insensitive according to RFC 9116). A field can occur multiple times, so every field-name maps to a list of values.
        Comments and the lines of the PGP-envelope are ignored."""
        result: dict[str, list[str]] = {}
        for line in GeneralUtilities.read_lines_from_file(security_txt_file):
            match = re.match(r"^([A-Za-z0-9-]+):\s*(.*?)\s*$", line)
            if match is not None:
                result.setdefault(match.group(1).lower(), []).append(match.group(2))
        return result

    @GeneralUtilities.check_arguments
    def __check_security_txt_signature(self, security_txt_file: str, fields: dict[str, list[str]], internet_connection_is_available: bool) -> None:
        """Checks whether the given security.txt-file has a PGP-signature and whether it is valid.
        Only the validity of the signature is checked and not whether the key of the signer is trusted. Therefore the signature is
        verified with gpgv against a temporary keyring which only contains the public key which is downloaded from the first
        http(s)-URL of the 'Encryption'-field. This way the result does not depend on the keyring of the current user, so the check
        works the same way in a build-pipeline. Without internet-connection the public key can not be downloaded, so the signature
        can not be verified then."""
        if "-----BEGIN PGP SIGNED MESSAGE-----" not in GeneralUtilities.read_text_from_file(security_txt_file):
            self.sc.log.log(f"The file '{security_txt_file}' is not signed.", LogLevel.Warning)
            return
        if not GeneralUtilities.tool_is_available("gpgv"):
            self.sc.log.log(f"The signature of '{security_txt_file}' can not be verified because gpgv is not available.", LogLevel.Warning)
            return
        if not internet_connection_is_available:
            self.sc.log.log(f"The signature of '{security_txt_file}' can not be verified because the public key can not be downloaded without internet-connection.", LogLevel.Warning)
            return
        key_urls: list[str] = [url for url in fields.get("encryption", []) if url.lower().startswith(("https://", "http://"))]
        if len(key_urls) == 0:
            self.sc.log.log(f"The signature of '{security_txt_file}' can not be verified because the file does not contain an 'Encryption'-field with an http(s)-URL of the public key.", LogLevel.Warning)
            return
        key_url: str = key_urls[0]
        public_key: bytes = self.__download_pgp_public_key(security_txt_file, key_url)
        if public_key is None:
            return
        with tempfile.TemporaryDirectory() as keyring_folder:
            keyring_file: str = os.path.join(keyring_folder, "PublicKey.gpg")
            with open(keyring_file, "wb") as keyring_file_stream:
                keyring_file_stream.write(public_key)
            # The keyring-file is passed as path relative to the working-directory with a leading "./": gpgv searches a path without
            # a slash in its home-folder, and the gpgv of git-for-windows does not accept an absolute windows-path as keyring.
            exit_code, _, stderr, _ = self.sc.run_program_argsasarray("gpgv", ["--keyring", f"./{os.path.basename(keyring_file)}", os.path.abspath(security_txt_file)], keyring_folder, throw_exception_if_exitcode_is_not_zero=False)
        if exit_code != 0:
            self.sc.log.log(f"The signature of '{security_txt_file}' is not valid for the public key from '{key_url}' (exitcode of gpgv: {exit_code}). StdErr: '{stderr}'", LogLevel.Warning)

    @GeneralUtilities.check_arguments
    def __download_pgp_public_key(self, security_txt_file: str, key_url: str) -> bytes:
        """Returns the binary content of the PGP-public-key which is downloaded from the given URL to verify the signature of the given
        security.txt-file, or None (after logging a warning which explains why) if it can not be downloaded or if the downloaded
        content does not contain a PGP-public-key-block."""
        try:
            response = requests.get(key_url, timeout=30, allow_redirects=True)
        except requests.RequestException as exception:
            self.sc.log.log(f"The signature of '{security_txt_file}' can not be verified because the public key can not be downloaded from '{key_url}': {exception}", LogLevel.Warning)
            return None
        if not response.ok:
            self.sc.log.log(f"The signature of '{security_txt_file}' can not be verified because the public key can not be downloaded from '{key_url}' (HTTP-status {response.status_code}).", LogLevel.Warning)
            return None
        public_key: bytes = TFCPS_ProjectLinting.__dearmor_pgp_public_key(response.text)
        if public_key is None:
            self.sc.log.log(f"The signature of '{security_txt_file}' can not be verified because '{key_url}' does not contain a PGP-public-key-block.", LogLevel.Warning)
        return public_key

    @staticmethod
    @GeneralUtilities.check_arguments
    def __dearmor_pgp_public_key(armored_content: str) -> bytes:
        """Returns the binary content of the first ASCII-armored PGP-public-key-block of the given content (the format which gpgv
        expects for a keyring-file), or None if the content does not contain such a block. The armor-headers (for example 'Comment:')
        and the checksum-line (which starts with '=') are not part of the binary content."""
        match = re.search(r"-----BEGIN PGP PUBLIC KEY BLOCK-----\r?\n(.*?)-----END PGP PUBLIC KEY BLOCK-----", armored_content, re.DOTALL)
        if match is None:
            return None
        lines: list[str] = [line.strip() for line in match.group(1).splitlines()]
        if GeneralUtilities.empty_string in lines:
            lines = lines[lines.index(GeneralUtilities.empty_string)+1:]  # the armor-headers end with the first empty line
        return base64.b64decode("".join(line for line in lines if GeneralUtilities.string_has_content(line) and not line.startswith("=")))

    @GeneralUtilities.check_arguments
    def __check_security_txt_expiration(self, security_txt_file: str, fields: dict[str, list[str]], now: datetime) -> None:
        """Checks whether the given security.txt-file contains exactly one 'Expires'-field (RFC 9116 does not allow more than one) whose
        value is not expired and which is valid for at least the next 3 months. A value without timezone is treated as UTC."""
        expires_values: list[str] = fields.get("expires", [])
        if len(expires_values) == 0:
            self.sc.log.log(f"The file '{security_txt_file}' does not contain an 'Expires'-field.", LogLevel.Warning)
            return
        if 1 < len(expires_values):
            self.sc.log.log(f"The file '{security_txt_file}' contains more than one 'Expires'-field.", LogLevel.Warning)
            return
        try:
            expires: datetime = datetime.fromisoformat(expires_values[0])
        except ValueError:
            self.sc.log.log(f"The 'Expires'-value '{expires_values[0]}' of '{security_txt_file}' is not a valid timestamp.", LogLevel.Warning)
            return
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= now:
            self.sc.log.log(f"The file '{security_txt_file}' is expired since {expires_values[0]}.", LogLevel.Warning)
        elif expires - now < timedelta(days=30*3):
            self.sc.log.log(f"The file '{security_txt_file}' expires within the next 3 months ({expires_values[0]}).", LogLevel.Warning)

    @GeneralUtilities.check_arguments
    def __check_security_txt_urls_are_reachable(self, security_txt_file: str, fields: dict[str, list[str]], field_name: str) -> None:
        """Checks whether the URLs of the given field of the given security.txt-file are reachable. Values which are no http(s)-URL (for
        example an 'openpgp4fpr:'-URI in the 'Encryption'-field) can not be requested and are therefore not checked."""
        urls: list[str] = fields.get(field_name.lower(), [])
        if len(urls) == 0:
            self.sc.log.log(f"The file '{security_txt_file}' does not contain a '{field_name}'-field.", LogLevel.Warning)
            return
        for url in urls:
            if not url.lower().startswith(("https://", "http://")):
                self.sc.log.log(f"The {field_name}-value '{url}' of '{security_txt_file}' is not checked because it is not an http(s)-URL.", LogLevel.Debug)
                continue
            try:
                with requests.get(url, timeout=30, stream=True, allow_redirects=True) as response:
                    if not response.ok:
                        self.sc.log.log(f"The {field_name}-URL '{url}' of '{security_txt_file}' is not reachable (HTTP-status {response.status_code}).", LogLevel.Warning)
            except requests.RequestException as exception:
                self.sc.log.log(f"The {field_name}-URL '{url}' of '{security_txt_file}' is not reachable: {exception}", LogLevel.Warning)
