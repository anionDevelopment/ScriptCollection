import io
import os
import stat
import uuid
import zipfile
from dataclasses import dataclass
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from .GeneralUtilities import GeneralUtilities
from .ScriptCollectionCore import ScriptCollectionCore


@dataclass(frozen=True)
class EncryptedContainerDefinition:
    """One line of "<repository>/.ScriptCollection/EncryptedFolders.csv" with resolved absolute paths."""
    name: str
    container_file: str
    target_folder: str
    target_folder_relative: str


class EncryptedContainerInRepository:
    """Manages encrypted containers in a folder (usually a git-repository).
    A container is a file which contains the content (files and folders) of a target-folder in encrypted form.
    The containers are defined in "<folder>/.ScriptCollection/EncryptedFolders.csv" with the columns "Name;File;Target".
    The target-folder is intended to be git-ignored, so that sensitive data are always either encrypted (in the container-file) or git-ignored (in the target-folder).

    Container-format: magic-bytes, format-version, scrypt-salt, AES-GCM-nonce and the AES-256-GCM-encrypted zip-archive of the target-folder.
    The header is used as associated data, so it is authenticated too. The zip-archive is created deterministically (sorted entries, fixed timestamps)."""

    __magic_bytes: bytes = b"SCENCCONTAINER"
    __format_version: bytes = bytes([1])
    __salt_length: int = 16
    __nonce_length: int = 12
    __key_length: int = 32
    __scrypt_n: int = 2**16
    __scrypt_r: int = 8
    __scrypt_p: int = 1
    __fixed_zip_timestamp: tuple = (1980, 1, 1, 0, 0, 0)
    __definition_file_relative: str = ".ScriptCollection/EncryptedFolders.csv"

    def __init__(self, sc: ScriptCollectionCore):
        self.__sc = sc

    @GeneralUtilities.check_arguments
    def initialize(self, repository_folder: str, name: str, password: str) -> None:
        """Creates the container-file as encrypted empty container. Throws an exception if the container-file already exists."""
        definition = self.__get_definition(repository_folder, name)
        if os.path.exists(definition.container_file):
            raise ValueError(f"Container-file \"{definition.container_file}\" already exists.")
        self.__write_container_file(definition.container_file, self.__create_zip_archive({}), password)
        self.__sc.log.log(f"Initialized encrypted empty container \"{name}\" in \"{definition.container_file}\".")

    @GeneralUtilities.check_arguments
    def decrypt(self, repository_folder: str, name: str, password: str) -> None:
        """Decrypts the container-file into the target-folder.
        Throws an exception if the target-folder already has content. If the repository-folder is a git-repository then it is ensured that the target-folder is git-ignored before anything is written into it."""
        definition = self.__get_definition(repository_folder, name)
        if not os.path.isfile(definition.container_file):
            raise ValueError(f"Container-file \"{definition.container_file}\" does not exist. It can be initialized using \"scinitencryptedcontainerinrepo\".")
        if os.path.isdir(definition.target_folder) and len(os.listdir(definition.target_folder)) > 0:
            raise ValueError(f"Target-folder \"{definition.target_folder}\" is not empty.")
        if os.path.exists(definition.target_folder) and not os.path.isdir(definition.target_folder):
            raise ValueError(f"Target \"{definition.target_folder}\" exists but is not a folder.")
        entries = self.__read_zip_archive(self.__read_container_file(definition.container_file, password))
        GeneralUtilities.ensure_directory_exists(definition.target_folder)
        self.__ensure_target_folder_is_git_ignored(repository_folder, definition)
        self.__write_entries_to_folder(entries, definition.target_folder)
        self.__sc.log.log(f"Decrypted container \"{name}\" into \"{definition.target_folder}\".")

    @GeneralUtilities.check_arguments
    def encrypt(self, repository_folder: str, name: str, password: str) -> None:
        """Encrypts the content of the target-folder into the container-file and deletes the content of the target-folder afterwards.
        If the container-file already exists, it must be decryptable with the given password. If its content is equal to the content of the target-folder, the container-file remains unchanged."""
        definition = self.__get_definition(repository_folder, name)
        if not os.path.isdir(definition.target_folder):
            raise ValueError(f"Target-folder \"{definition.target_folder}\" does not exist.")
        entries = self.__read_entries_from_folder(definition.target_folder)
        container_must_be_written = True
        if os.path.isfile(definition.container_file):
            existing_entries = self.__read_zip_archive(self.__read_container_file(definition.container_file, password))
            container_must_be_written = existing_entries != entries
        if container_must_be_written:
            self.__write_container_file(definition.container_file, self.__create_zip_archive(entries), password)
        written_entries = self.__read_zip_archive(self.__read_container_file(definition.container_file, password))
        if written_entries != entries:
            raise ValueError(f"Verification of container-file \"{definition.container_file}\" failed. The content of the target-folder \"{definition.target_folder}\" will not be deleted.")
        GeneralUtilities.ensure_folder_exists_and_is_empty(definition.target_folder)
        if container_must_be_written:
            self.__sc.log.log(f"Encrypted \"{definition.target_folder}\" into container \"{name}\".")
        else:
            self.__sc.log.log(f"Content of \"{definition.target_folder}\" is unchanged, so container \"{name}\" remains unchanged.")

    def __get_definition(self, repository_folder: str, name: str) -> EncryptedContainerDefinition:
        if not os.path.isdir(repository_folder):
            raise ValueError(f"Folder \"{repository_folder}\" does not exist.")
        repository_folder = os.path.abspath(repository_folder)
        definition_file = os.path.join(repository_folder, self.__definition_file_relative)
        if not os.path.isfile(definition_file):
            raise ValueError(f"Definition-file \"{definition_file}\" does not exist.")
        matching_lines: list[list[str]] = []
        for line in GeneralUtilities.read_csv_file(definition_file, True):
            if len(line) != 3:
                raise ValueError(f"Definition-file \"{definition_file}\" contains a line which does not have exactly 3 columns (Name;File;Target): \"{';'.join(line)}\".")
            if line[0] == name:
                matching_lines.append(line)
        if len(matching_lines) == 0:
            raise ValueError(f"Definition-file \"{definition_file}\" does not contain a container with name \"{name}\".")
        if len(matching_lines) > 1:
            raise ValueError(f"Definition-file \"{definition_file}\" contains the name \"{name}\" more than once.")
        file_relative = matching_lines[0][1]
        target_relative = matching_lines[0][2]
        container_file = self.__resolve_path_inside_repository(repository_folder, file_relative, "File")
        target_folder = self.__resolve_path_inside_repository(repository_folder, target_relative, "Target")
        if self.__is_inside(container_file, target_folder):
            raise ValueError(f"File \"{file_relative}\" must not be located inside of target \"{target_relative}\".")
        if self.__is_inside(definition_file, target_folder):
            raise ValueError(f"Target \"{target_relative}\" must not contain the definition-file \"{self.__definition_file_relative}\".")
        if self.__is_inside(os.path.join(repository_folder, ".git"), target_folder):
            raise ValueError(f"Target \"{target_relative}\" must not contain the \".git\"-folder.")
        return EncryptedContainerDefinition(name, container_file, target_folder, os.path.relpath(target_folder, repository_folder).replace("\\", "/"))

    def __resolve_path_inside_repository(self, repository_folder: str, relative_path: str, column_name: str) -> str:
        if not GeneralUtilities.string_has_content(relative_path):
            raise ValueError(f"Column \"{column_name}\" must not be empty.")
        if os.path.isabs(relative_path) or relative_path.startswith("/") or relative_path.startswith("\\"):
            raise ValueError(f"{column_name} \"{relative_path}\" must be a relative path.")
        absolute_path = os.path.abspath(os.path.join(repository_folder, relative_path))
        if absolute_path == repository_folder or not self.__is_inside(absolute_path, repository_folder):
            raise ValueError(f"{column_name} \"{relative_path}\" must be located in a subfolder of \"{repository_folder}\".")
        return absolute_path

    def __is_inside(self, path: str, folder: str) -> bool:
        path = os.path.normcase(os.path.abspath(path))
        folder = os.path.normcase(os.path.abspath(folder))
        return path == folder or path.startswith(folder.rstrip(os.sep)+os.sep)

    def __ensure_target_folder_is_git_ignored(self, repository_folder: str, definition: EncryptedContainerDefinition) -> None:
        if not self.__sc.is_git_repository(repository_folder):
            return
        if self.__sc.file_is_git_ignored(definition.target_folder_relative, repository_folder):
            return
        self.__sc.ensure_line_is_in_gitignore(repository_folder, f"/{definition.target_folder_relative}/")
        if not self.__sc.file_is_git_ignored(definition.target_folder_relative, repository_folder):
            raise ValueError(f"Target \"{definition.target_folder_relative}\" is still not git-ignored after adding it to \"{os.path.join(repository_folder, '.gitignore')}\" (maybe a negating pattern is present).")

    def __is_link(self, path: str) -> bool:
        if os.path.islink(path):
            return True
        # "st_file_attributes" is only available on windows. It is required to detect junctions and other reparse-points which are not detected by "os.path.islink".
        file_attributes = getattr(os.lstat(path), "st_file_attributes", 0)
        return (file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT) != 0

    def __read_entries_from_folder(self, folder: str) -> dict[str, bytes]:
        """Returns a dictionary with the relative paths (separated by "/") as keys. Folders end with "/" and have None as value."""
        result: dict[str, bytes] = {}
        for current_folder, subfolders, files in os.walk(folder):
            for item in subfolders+files:
                item_path = os.path.join(current_folder, item)
                if self.__is_link(item_path):
                    raise ValueError(f"\"{item_path}\" is a link. Links are not supported.")
            for subfolder in subfolders:
                result[os.path.relpath(os.path.join(current_folder, subfolder), folder).replace("\\", "/")+"/"] = None
            for file in files:
                file_path = os.path.join(current_folder, file)
                if os.lstat(file_path).st_nlink > 1:
                    raise ValueError(f"\"{file_path}\" is a hardlink. Links are not supported.")
                with open(file_path, "rb") as file_object:
                    result[os.path.relpath(file_path, folder).replace("\\", "/")] = file_object.read()
        return result

    def __write_entries_to_folder(self, entries: dict[str, bytes], folder: str) -> None:
        for entry_name in sorted(entries.keys()):
            target_path = os.path.abspath(os.path.join(folder, entry_name.rstrip("/")))
            if os.path.isabs(entry_name) or ".." in entry_name.split("/") or not self.__is_inside(target_path, folder) or target_path == os.path.abspath(folder):
                raise ValueError(f"Container contains an invalid entry \"{entry_name}\".")
            if entry_name.endswith("/"):
                GeneralUtilities.ensure_directory_exists(target_path)
            else:
                GeneralUtilities.ensure_directory_exists(os.path.dirname(target_path))
                with open(target_path, "wb") as file_object:
                    file_object.write(entries[entry_name])

    def __create_zip_archive(self, entries: dict[str, bytes]) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for entry_name in sorted(entries.keys()):
                zip_info = zipfile.ZipInfo(entry_name, self.__fixed_zip_timestamp)
                if entry_name.endswith("/"):
                    zip_info.external_attr = (0o40755 << 16) | 0x10
                    archive.writestr(zip_info, b"")
                else:
                    zip_info.external_attr = 0o100644 << 16
                    zip_info.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(zip_info, entries[entry_name])
        return buffer.getvalue()

    def __read_zip_archive(self, archive_content: bytes) -> dict[str, bytes]:
        result: dict[str, bytes] = {}
        with zipfile.ZipFile(io.BytesIO(archive_content), "r") as archive:
            for zip_info in archive.infolist():
                result[zip_info.filename] = None if zip_info.filename.endswith("/") else archive.read(zip_info)
        return result

    def __get_header(self, salt: bytes) -> bytes:
        return self.__magic_bytes+self.__format_version+salt

    def __derive_key(self, password: str, salt: bytes) -> bytes:
        return Scrypt(salt=salt, length=self.__key_length, n=self.__scrypt_n, r=self.__scrypt_r, p=self.__scrypt_p).derive(password.encode("utf-8"))

    def __write_container_file(self, container_file: str, plaintext: bytes, password: str) -> None:
        if not GeneralUtilities.string_has_content(password):
            raise ValueError("Password must not be empty.")
        salt = os.urandom(self.__salt_length)
        nonce = os.urandom(self.__nonce_length)
        header = self.__get_header(salt)
        ciphertext = AESGCM(self.__derive_key(password, salt)).encrypt(nonce, plaintext, header)
        GeneralUtilities.ensure_directory_exists(os.path.dirname(container_file))
        temporary_file = f"{container_file}.{uuid.uuid4()}.tmp"
        with open(temporary_file, "wb") as file_object:
            file_object.write(header+nonce+ciphertext)
        os.replace(temporary_file, container_file)

    def __read_container_file(self, container_file: str, password: str) -> bytes:
        with open(container_file, "rb") as file_object:
            content = file_object.read()
        header_length = len(self.__magic_bytes)+len(self.__format_version)+self.__salt_length
        if len(content) < header_length+self.__nonce_length or not content.startswith(self.__magic_bytes):
            raise ValueError(f"\"{container_file}\" is not an encrypted container.")
        if content[len(self.__magic_bytes):len(self.__magic_bytes)+len(self.__format_version)] != self.__format_version:
            raise ValueError(f"\"{container_file}\" has an unsupported container-format-version.")
        header = content[:header_length]
        salt = header[-self.__salt_length:]
        nonce = content[header_length:header_length+self.__nonce_length]
        ciphertext = content[header_length+self.__nonce_length:]
        try:
            return AESGCM(self.__derive_key(password, salt)).decrypt(nonce, ciphertext, header)
        except InvalidTag as exception:
            raise ValueError(f"\"{container_file}\" can not be decrypted: the password is wrong or the file is corrupted.") from exception
