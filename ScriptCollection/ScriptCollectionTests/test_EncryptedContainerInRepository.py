import os
import shutil
import tempfile
import unittest
import uuid
from ..ScriptCollection.GeneralUtilities import GeneralUtilities
from ..ScriptCollection.ScriptCollectionCore import ScriptCollectionCore
from ..ScriptCollection.EncryptedContainerInRepository import EncryptedContainerInRepository


class EncryptedContainerInRepositoryTests(unittest.TestCase):

    __password: str = "test-password"

    def __create_folder(self, initialize_git: bool) -> str:
        folder = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
        self.addCleanup(shutil.rmtree, folder, True)
        GeneralUtilities.ensure_directory_exists(folder)
        if initialize_git:
            ScriptCollectionCore().run_program_argsasarray("git", ["init"], folder)
        return folder

    def __create_initialized_folder(self, target: str, initialize_git: bool) -> str:
        folder = self.__create_folder(initialize_git)
        self.__create_manager().initialize(folder, "Secrets", target, self.__password)
        return folder

    def __create_manager(self) -> EncryptedContainerInRepository:
        return EncryptedContainerInRepository(ScriptCollectionCore())

    def __get_definition_file(self, folder: str) -> str:
        return os.path.join(folder, ".ScriptCollection", "EncryptedFolders.csv")

    def __get_container_file(self, folder: str) -> str:
        return os.path.join(folder, ".ScriptCollection", "SensitiveDataContainer", "Secrets.bin")

    def __write_file(self, file: str, content: str) -> None:
        GeneralUtilities.ensure_directory_exists(os.path.dirname(file))
        GeneralUtilities.write_text_to_file(file, content)

    def __read_file_bytes(self, file: str) -> bytes:
        with open(file, "rb") as file_object:
            return file_object.read()

    def test_initialize_creates_definition_file_and_container_file(self) -> None:
        # arrange
        folder = self.__create_folder(False)
        manager = self.__create_manager()

        # act
        manager.initialize(folder, "Secrets", "Other/Secrets", self.__password)

        # assert
        assert GeneralUtilities.read_lines_from_file(self.__get_definition_file(folder)) == ["Name;Target", "Secrets;Other/Secrets"]
        assert os.path.isfile(self.__get_container_file(folder))

    def test_initialize_appends_line_to_existing_definition_file(self) -> None:
        # arrange
        folder = self.__create_folder(False)
        manager = self.__create_manager()
        manager.initialize(folder, "Secrets1", "Secrets1", self.__password)

        # act
        manager.initialize(folder, "Secrets2", "Other\\Secrets2", self.__password)

        # assert
        assert GeneralUtilities.read_lines_from_file(self.__get_definition_file(folder)) == ["Name;Target", "Secrets1;Secrets1", "Secrets2;Other/Secrets2"]

    def test_initialize_and_decrypt_results_in_empty_target_folder(self) -> None:
        # arrange
        folder = self.__create_initialized_folder("Other/Secrets", False)
        manager = self.__create_manager()

        # act
        manager.decrypt(folder, "Secrets", self.__password)

        # assert
        assert os.path.isdir(os.path.join(folder, "Other", "Secrets"))
        assert len(os.listdir(os.path.join(folder, "Other", "Secrets"))) == 0

    def test_initialize_fails_if_name_is_already_defined(self) -> None:
        # arrange
        folder = self.__create_initialized_folder("Secrets", False)
        manager = self.__create_manager()

        # act & assert
        with self.assertRaises(ValueError):
            manager.initialize(folder, "Secrets", "OtherSecrets", self.__password)
        assert GeneralUtilities.read_lines_from_file(self.__get_definition_file(folder)) == ["Name;Target", "Secrets;Secrets"]

    def test_initialize_fails_if_container_file_exists(self) -> None:
        # arrange
        folder = self.__create_folder(False)
        self.__write_file(self.__get_container_file(folder), "existing")
        manager = self.__create_manager()

        # act & assert
        with self.assertRaises(ValueError):
            manager.initialize(folder, "Secrets", "Secrets", self.__password)
        assert not os.path.exists(self.__get_definition_file(folder))

    def test_encrypt_and_decrypt_roundtrip(self) -> None:
        # arrange
        folder = self.__create_initialized_folder("Secrets", False)
        manager = self.__create_manager()
        manager.decrypt(folder, "Secrets", self.__password)
        target = os.path.join(folder, "Secrets")
        self.__write_file(os.path.join(target, "a.txt"), "content a")
        self.__write_file(os.path.join(target, "Sub", "Sub2", "b.txt"), "content b")
        GeneralUtilities.ensure_directory_exists(os.path.join(target, "EmptyFolder"))

        # act
        manager.encrypt(folder, "Secrets", self.__password)
        target_content_after_encrypt = os.listdir(target)
        manager.decrypt(folder, "Secrets", self.__password)

        # assert
        assert target_content_after_encrypt == []
        assert GeneralUtilities.read_text_from_file(os.path.join(target, "a.txt")) == "content a"
        assert GeneralUtilities.read_text_from_file(os.path.join(target, "Sub", "Sub2", "b.txt")) == "content b"
        assert os.path.isdir(os.path.join(target, "EmptyFolder"))
        assert b"content a" not in self.__read_file_bytes(self.__get_container_file(folder))

    def test_encrypt_keeps_container_file_unchanged_if_content_is_unchanged(self) -> None:
        # arrange
        folder = self.__create_initialized_folder("Secrets", False)
        manager = self.__create_manager()
        manager.decrypt(folder, "Secrets", self.__password)
        self.__write_file(os.path.join(folder, "Secrets", "a.txt"), "content a")
        manager.encrypt(folder, "Secrets", self.__password)
        container_before = self.__read_file_bytes(self.__get_container_file(folder))
        manager.decrypt(folder, "Secrets", self.__password)

        # act
        manager.encrypt(folder, "Secrets", self.__password)

        # assert
        assert self.__read_file_bytes(self.__get_container_file(folder)) == container_before
        assert os.listdir(os.path.join(folder, "Secrets")) == []

    def test_encrypt_changes_container_file_if_content_is_changed(self) -> None:
        # arrange
        folder = self.__create_initialized_folder("Secrets", False)
        manager = self.__create_manager()
        container_before = self.__read_file_bytes(self.__get_container_file(folder))
        manager.decrypt(folder, "Secrets", self.__password)
        self.__write_file(os.path.join(folder, "Secrets", "a.txt"), "content a")

        # act
        manager.encrypt(folder, "Secrets", self.__password)

        # assert
        assert self.__read_file_bytes(self.__get_container_file(folder)) != container_before

    def test_decrypt_with_wrong_password_fails_and_does_not_create_target_folder(self) -> None:
        # arrange
        folder = self.__create_initialized_folder("Secrets", False)
        manager = self.__create_manager()

        # act & assert
        with self.assertRaises(ValueError):
            manager.decrypt(folder, "Secrets", "wrong-password")
        assert not os.path.exists(os.path.join(folder, "Secrets"))

    def test_encrypt_with_wrong_password_fails_and_keeps_target_content(self) -> None:
        # arrange
        folder = self.__create_initialized_folder("Secrets", False)
        manager = self.__create_manager()
        manager.decrypt(folder, "Secrets", self.__password)
        self.__write_file(os.path.join(folder, "Secrets", "a.txt"), "content a")

        # act & assert
        with self.assertRaises(ValueError):
            manager.encrypt(folder, "Secrets", "wrong-password")
        assert os.path.isfile(os.path.join(folder, "Secrets", "a.txt"))

    def test_decrypt_fails_if_target_folder_has_content(self) -> None:
        # arrange
        folder = self.__create_initialized_folder("Secrets", False)
        manager = self.__create_manager()
        self.__write_file(os.path.join(folder, "Secrets", "existing.txt"), "existing")

        # act & assert
        with self.assertRaises(ValueError):
            manager.decrypt(folder, "Secrets", self.__password)
        assert GeneralUtilities.read_text_from_file(os.path.join(folder, "Secrets", "existing.txt")) == "existing"

    def test_decrypt_fails_if_container_file_does_not_exist(self) -> None:
        # arrange
        folder = self.__create_initialized_folder("Secrets", False)
        os.remove(self.__get_container_file(folder))
        manager = self.__create_manager()

        # act & assert
        with self.assertRaises(ValueError):
            manager.decrypt(folder, "Secrets", self.__password)

    def test_decrypt_fails_if_definition_file_does_not_exist(self) -> None:
        # arrange
        folder = self.__create_folder(False)
        manager = self.__create_manager()

        # act & assert
        with self.assertRaises(ValueError):
            manager.decrypt(folder, "Secrets", self.__password)

    def test_encrypt_fails_if_target_folder_does_not_exist(self) -> None:
        # arrange
        folder = self.__create_initialized_folder("Secrets", False)
        manager = self.__create_manager()

        # act & assert
        with self.assertRaises(ValueError):
            manager.encrypt(folder, "Secrets", self.__password)

    def test_decrypt_adds_target_folder_to_gitignore_in_git_repository(self) -> None:
        # arrange
        folder = self.__create_initialized_folder("Other/Secrets", True)
        manager = self.__create_manager()

        # act
        manager.decrypt(folder, "Secrets", self.__password)

        # assert
        assert "/Other/Secrets/" in GeneralUtilities.read_lines_from_file(os.path.join(folder, ".gitignore"))
        assert ScriptCollectionCore().file_is_git_ignored("Other/Secrets", folder)

    def test_decrypt_does_not_change_gitignore_if_target_folder_is_already_ignored(self) -> None:
        # arrange
        folder = self.__create_initialized_folder("Secrets", True)
        GeneralUtilities.write_lines_to_file(os.path.join(folder, ".gitignore"), ["Secrets/"])
        manager = self.__create_manager()

        # act
        manager.decrypt(folder, "Secrets", self.__password)

        # assert
        assert GeneralUtilities.read_lines_from_file(os.path.join(folder, ".gitignore")) == ["Secrets/"]

    def test_decrypt_does_not_create_gitignore_if_folder_is_no_git_repository(self) -> None:
        # arrange
        folder = self.__create_initialized_folder("Secrets", False)
        manager = self.__create_manager()

        # act
        manager.decrypt(folder, "Secrets", self.__password)

        # assert
        assert not os.path.exists(os.path.join(folder, ".gitignore"))

    def test_initialize_rejects_invalid_targets(self) -> None:
        invalid_targets = ["../Secrets", ".", ".ScriptCollection", ".ScriptCollection/SensitiveDataContainer/Plain", "/Secrets", "", "Sec;rets"]
        for invalid_target in invalid_targets:
            with self.subTest(invalid_target):
                # arrange
                folder = self.__create_folder(False)
                manager = self.__create_manager()

                # act & assert
                with self.assertRaises(ValueError):
                    manager.initialize(folder, "Secrets", invalid_target, self.__password)
                assert not os.path.exists(self.__get_definition_file(folder))
                assert not os.path.exists(self.__get_container_file(folder))

    def test_initialize_rejects_invalid_name(self) -> None:
        # arrange
        folder = self.__create_folder(False)
        manager = self.__create_manager()

        # act & assert
        with self.assertRaises(ValueError):
            manager.initialize(folder, "../Secrets", "Secrets", self.__password)

    def test_decrypt_rejects_definition_line_with_wrong_column_count(self) -> None:
        # arrange
        folder = self.__create_folder(False)
        GeneralUtilities.ensure_directory_exists(os.path.dirname(self.__get_definition_file(folder)))
        GeneralUtilities.write_lines_to_file(self.__get_definition_file(folder), ["Name;Target", "Secrets;Secrets;Other"])
        manager = self.__create_manager()

        # act & assert
        with self.assertRaises(ValueError):
            manager.decrypt(folder, "Secrets", self.__password)

    def test_unknown_name_is_rejected(self) -> None:
        # arrange
        folder = self.__create_initialized_folder("Secrets", False)
        manager = self.__create_manager()

        # act & assert
        with self.assertRaises(ValueError):
            manager.decrypt(folder, "Unknown", self.__password)
