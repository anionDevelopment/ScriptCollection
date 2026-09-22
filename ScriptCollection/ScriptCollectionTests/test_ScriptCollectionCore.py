import os
import sys
import time
from typing import NoReturn
import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile
import uuid
import xml.etree.ElementTree as ET
from ..ScriptCollection.GeneralUtilities import GeneralUtilities
from ..ScriptCollection.ScriptCollectionCore import ScriptCollectionCore


class ScriptCollectionCoreTests(unittest.TestCase):

    encoding = "utf-8"
    testfileprefix = "testfile_"
    svg_namespace = "http://www.w3.org/2000/svg"

    def test_get_docker_registry_credentials_from_environment_variables_returns_empty_list_when_nothing_is_declared(self) -> None:
        with tempfile.TemporaryDirectory() as configuration_folder:
            # arrange
            sc = ScriptCollectionCore()
            #the configuration-folder is isolated from the real one of the machine which runs this test, and the environment is
            #cleared, so that registries which are declared for real on this machine (for example the ones of the developer who runs
            #this test) do not leak into this test and make it non-deterministic.
            setattr(sc, "get_scriptcollection_configuration_folder", lambda: configuration_folder)
            with patch.dict(os.environ, {}, clear=True):

                # act
                actual_result = sc.get_docker_registry_credentials_from_environment_variables()

                # assert
                assert not actual_result

    def test_get_docker_registry_credentials_from_environment_variables_returns_declared_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as configuration_folder:
            # arrange
            sc = ScriptCollectionCore()
            setattr(sc, "get_scriptcollection_configuration_folder", lambda: configuration_folder)
            declarations = {
                "OCIRegistry_MyRegistry_Address": "https://myregistry.example.com",
                "OCIRegistry_MyRegistry_Username": "MyUser",
                "OCIRegistry_MyRegistry_Password": "MyPassword",
                "OCIRegistry_MyOtherRegistry_Address": "myotherregistry.example.com",
                "OCIRegistry_MyOtherRegistry_Username": "MyOtherUser",
                "OCIRegistry_MyOtherRegistry_Password": "MyOtherPassword",
            }
            with patch.dict(os.environ, declarations, clear=True):

                # act
                actual_result = sc.get_docker_registry_credentials_from_environment_variables()

                # assert
                #the scheme is removed because docker expects the address of a registry without it.
                assert actual_result == [("myotherregistry.example.com", "MyOtherUser", "MyOtherPassword"), ("myregistry.example.com", "MyUser", "MyPassword")]

    def test_get_docker_registry_credentials_from_environment_variables_skips_a_registry_whose_values_can_not_be_resolved(self) -> None:
        with tempfile.TemporaryDirectory() as configuration_folder:
            # arrange
            sc = ScriptCollectionCore()
            setattr(sc, "get_scriptcollection_configuration_folder", lambda: configuration_folder)
            declarations = {
                "OCIRegistry_IncompleteRegistry_Address": "incompleteregistry.example.com",
                "OCIRegistry_IncompleteRegistry_Username": "MyUser",
                "OCIRegistry_UsableRegistry_Address": "usableregistry.example.com",
                "OCIRegistry_UsableRegistry_Username": "MyOtherUser",
                "OCIRegistry_UsableRegistry_Password": "MyOtherPassword",
            }
            with patch.dict(os.environ, declarations, clear=True):

                # act
                actual_result = sc.get_docker_registry_credentials_from_environment_variables()

                # assert
                #the registries are machine-wide, so a declaration which can not be resolved here (its password is missing) must not break
                #a build which does not even need that registry; it is skipped with a warning and its images fall back to the upstream-registry.
                assert actual_result == [("usableregistry.example.com", "MyOtherUser", "MyOtherPassword")]

    def test_resolve_environment_variables_falls_back_to_the_environment_when_the_configured_source_is_not_available(self) -> None:
        with tempfile.TemporaryDirectory() as configuration_folder:
            # arrange
            #this is the situation inside a build-container: it gets the configuration-file of the host mounted, but not the secret-file
            #which an entry of that file points to (that file only exists on the host). The host resolved the value before it started the
            #container and forwarded it by name, so the environment is the remaining source.
            sc = ScriptCollectionCore()
            setattr(sc, "get_scriptcollection_configuration_folder", lambda: configuration_folder)
            ScriptCollectionCoreTests.__write_environment_variables_configuration_file(os.path.join(configuration_folder, "TFCPS", "EnvironmentVariables.csv"), [
                "MyVariable;file;~/.pp/ASecretFileWhichOnlyExistsOnTheHost.txt",
            ])
            with patch.dict(os.environ, {"MyVariable": "TheValueForwardedByTheHost"}, clear=True):

                # act
                actual_result = sc.resolve_environment_variables(["MyVariable"], "a test")

                # assert
                assert actual_result == {"MyVariable": "TheValueForwardedByTheHost"}

    def test_resolve_environment_variables_throws_exception_when_neither_the_configured_source_nor_the_environment_is_available(self) -> None:
        with tempfile.TemporaryDirectory() as configuration_folder:
            # arrange
            sc = ScriptCollectionCore()
            setattr(sc, "get_scriptcollection_configuration_folder", lambda: configuration_folder)
            ScriptCollectionCoreTests.__write_environment_variables_configuration_file(os.path.join(configuration_folder, "TFCPS", "EnvironmentVariables.csv"), [
                "MyVariable;file;~/.pp/ASecretFileWhichDoesNotExistAnywhere.txt",
            ])
            with patch.dict(os.environ, {}, clear=True):

                # act & assert
                #the fallback must not hide a value which is really unavailable: then the resolution still fails.
                with self.assertRaises(ValueError):
                    sc.resolve_environment_variables(["MyVariable"], "a test")

    def test_get_docker_registry_credentials_from_environment_variables_resolves_a_secret_file_relative_to_the_configuration_file(self) -> None:
        with tempfile.TemporaryDirectory() as configuration_folder:
            # arrange
            #this is what a build inside a container does: it reads the configuration-file which the host mounted, so a 'file'-value with a
            #relative path (the recommended form) must resolve against the folder of that file and not against the host-path it came from.
            sc = ScriptCollectionCore()
            setattr(sc, "get_scriptcollection_configuration_folder", lambda: configuration_folder)
            ScriptCollectionCoreTests.__write_environment_variables_configuration_file(os.path.join(configuration_folder, "TFCPS", "EnvironmentVariables.csv"), [
                "OCIRegistry_MyRegistry_Address;literal;myregistry.example.com",
                "OCIRegistry_MyRegistry_Username;literal;MyUser",
                "OCIRegistry_MyRegistry_Password;file;Secrets/MyRegistryToken.txt",
            ])
            secret_file = os.path.join(configuration_folder, "TFCPS", "Secrets", "MyRegistryToken.txt")
            GeneralUtilities.ensure_directory_exists(os.path.dirname(secret_file))
            GeneralUtilities.write_text_to_file(secret_file, "MyTokenFromTheSecretFile\n")
            with patch.dict(os.environ, {}, clear=True):

                # act
                actual_result = sc.get_docker_registry_credentials_from_environment_variables()

                # assert
                assert actual_result == [("myregistry.example.com", "MyUser", "MyTokenFromTheSecretFile")]

    @staticmethod
    def __create_scriptcollectioncore_for_registry_login(configuration_folder: str, mounted_environment_variables_file: str) -> tuple[ScriptCollectionCore, list[str]]:
        """Returns a ScriptCollectionCore which reads its machine-wide configuration from the given folder instead of from the
        configuration-folder of the user who runs the test, and which looks for the environment-variables-configuration-file mounted by
        the host at the given path instead of at the path a real build-container has.
        The program-calls are collected instead of being executed, because a testcase must not depend on an installed docker.
        Returns the instance and the list of the collected calls (as the arguments the docker-client was called with)."""
        result = ScriptCollectionCore()
        setattr(result, "get_scriptcollection_configuration_folder", lambda: configuration_folder)
        setattr(result, "get_environment_variables_file_in_container", lambda: mounted_environment_variables_file)
        executed_calls: list[str] = []

        def run_program(program: str, arguments: str, *args, **kwargs) -> tuple[int, str, str, int]:
            executed_calls.append(f"{program} {arguments}")
            return (0, GeneralUtilities.empty_string, GeneralUtilities.empty_string, 0)
        setattr(result, "run_program", run_program)
        return (result, executed_calls)

    @staticmethod
    def __write_environment_variables_configuration_file(file: str, lines: list[str]) -> None:
        GeneralUtilities.ensure_directory_exists(os.path.dirname(file))
        GeneralUtilities.write_lines_to_file(file, ["EnvVariableName;Kind;Value"]+lines)

    def test_login_uses_the_environment_variables_configuration_file_of_the_configuration_folder_when_nothing_is_mounted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_folder:
            # arrange
            sc, executed_calls = ScriptCollectionCoreTests.__create_scriptcollectioncore_for_registry_login(temporary_folder, os.path.join(temporary_folder, "NotMounted.csv"))
            ScriptCollectionCoreTests.__write_environment_variables_configuration_file(os.path.join(temporary_folder, "TFCPS", "EnvironmentVariables.csv"), [
                "OCIRegistry_MyRegistry_Address;literal;myregistry.example.com",
                "OCIRegistry_MyRegistry_Username;literal;MyUser",
                "OCIRegistry_MyRegistry_Password;literal;MyPassword",
            ])
            #cleared so that registries which are declared in the real environment do not leak into this test.
            with patch.dict(os.environ, {}, clear=True):

                # act
                sc.login_to_defined_docker_registries()

                # assert
                assert executed_calls == ["docker login myregistry.example.com -u MyUser -p MyPassword"]

    def test_login_uses_the_environment_variables_configuration_file_which_was_mounted_into_the_container(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_folder:
            # arrange
            mounted_file = os.path.join(temporary_folder, "Mounted.csv")
            ScriptCollectionCoreTests.__write_environment_variables_configuration_file(mounted_file, [
                "OCIRegistry_MountedRegistry_Address;literal;mountedregistry.example.com",
                "OCIRegistry_MountedRegistry_Username;literal;MountedUser",
                "OCIRegistry_MountedRegistry_Password;literal;MountedPassword",
            ])
            sc, executed_calls = ScriptCollectionCoreTests.__create_scriptcollectioncore_for_registry_login(temporary_folder, mounted_file)
            ScriptCollectionCoreTests.__write_environment_variables_configuration_file(os.path.join(temporary_folder, "TFCPS", "EnvironmentVariables.csv"), [
                "OCIRegistry_MyRegistry_Address;literal;myregistry.example.com",
                "OCIRegistry_MyRegistry_Username;literal;MyUser",
                "OCIRegistry_MyRegistry_Password;literal;MyPassword",
            ])
            with patch.dict(os.environ, {}, clear=True):

                # act
                sc.login_to_defined_docker_registries()

                # assert
                #the file of the configuration-folder is not used in addition: inside a container that folder belongs to the
                #container-user and therefore never contains the configuration of the machine on which the build was started.
                assert executed_calls == ["docker login mountedregistry.example.com -u MountedUser -p MountedPassword"]

    def test_login_uses_the_credentials_of_the_file_and_of_the_environment_together(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_folder:
            # arrange
            sc, executed_calls = ScriptCollectionCoreTests.__create_scriptcollectioncore_for_registry_login(temporary_folder, os.path.join(temporary_folder, "NotMounted.csv"))
            ScriptCollectionCoreTests.__write_environment_variables_configuration_file(os.path.join(temporary_folder, "TFCPS", "EnvironmentVariables.csv"), [
                "OCIRegistry_MyRegistry_Address;literal;myregistry.example.com",
                "OCIRegistry_MyRegistry_Username;literal;MyUser",
                "OCIRegistry_MyRegistry_Password;literal;MyPassword",
            ])
            declarations = {
                "OCIRegistry_MyOtherRegistry_Address": "myotherregistry.example.com",
                "OCIRegistry_MyOtherRegistry_Username": "MyOtherUser",
                "OCIRegistry_MyOtherRegistry_Password": "MyOtherPassword",
            }
            with patch.dict(os.environ, declarations, clear=True):

                # act
                sc.login_to_defined_docker_registries()

                # assert
                #a registry which is declared only in the file and a registry which is declared only in the environment are both used;
                #sorted alphabetically by address, which is what makes the log-output deterministic.
                assert executed_calls == ["docker login myotherregistry.example.com -u MyOtherUser -p MyOtherPassword", "docker login myregistry.example.com -u MyUser -p MyPassword"]

    def test_login_prefers_the_file_over_the_environment_for_the_same_registry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_folder:
            # arrange
            sc, executed_calls = ScriptCollectionCoreTests.__create_scriptcollectioncore_for_registry_login(temporary_folder, os.path.join(temporary_folder, "NotMounted.csv"))
            ScriptCollectionCoreTests.__write_environment_variables_configuration_file(os.path.join(temporary_folder, "TFCPS", "EnvironmentVariables.csv"), [
                "OCIRegistry_MyRegistry_Address;literal;myregistry.example.com",
                "OCIRegistry_MyRegistry_Username;literal;FileUser",
                "OCIRegistry_MyRegistry_Password;literal;FilePassword",
            ])
            declarations = {
                "OCIRegistry_MyRegistry_Address": "myregistry.example.com",
                "OCIRegistry_MyRegistry_Username": "EnvironmentUser",
                "OCIRegistry_MyRegistry_Password": "EnvironmentPassword",
            }
            with patch.dict(os.environ, declarations, clear=True):

                # act
                sc.login_to_defined_docker_registries()

                # assert
                #the configuration-file has precedence, consistent with every other value resolved through resolve_environment_variables.
                assert executed_calls == ["docker login myregistry.example.com -u FileUser -p FilePassword"]

    def test_login_is_only_executed_once_per_instance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_folder:
            # arrange
            sc, executed_calls = ScriptCollectionCoreTests.__create_scriptcollectioncore_for_registry_login(temporary_folder, os.path.join(temporary_folder, "NotMounted.csv"))
            ScriptCollectionCoreTests.__write_environment_variables_configuration_file(os.path.join(temporary_folder, "TFCPS", "EnvironmentVariables.csv"), [
                "OCIRegistry_MyRegistry_Address;literal;myregistry.example.com",
                "OCIRegistry_MyRegistry_Username;literal;MyUser",
                "OCIRegistry_MyRegistry_Password;literal;MyPassword",
            ])
            with patch.dict(os.environ, {}, clear=True):

                # act
                sc.login_to_defined_docker_registries()
                sc.login_to_defined_docker_registries()

                # assert
                #the credentials do not change while a process runs and everything which accesses a registry ensures the login, so
                #without this the same login would be executed over and over again.
                assert executed_calls == ["docker login myregistry.example.com -u MyUser -p MyPassword"]

    def test_export_filemetadata(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        tests_folder = tempfile.gettempdir()+os.path.sep+str(uuid.uuid4())
        try:
            GeneralUtilities.ensure_directory_exists(tests_folder)
            target_file = os.path.join(tests_folder, "test.csv")
            assert not os.path.isfile(target_file)
            dir_path = os.path.dirname(os.path.realpath(__file__))
            folder_for_export = GeneralUtilities.resolve_relative_path("../Other/Reference", dir_path)

            # act
            sc.export_filemetadata(folder_for_export, target_file)

            # assert
            assert os.path.isfile(target_file)
            # TODO add more assertions
        finally:
            GeneralUtilities.ensure_directory_does_not_exist(tests_folder)

    def test_ls_for_folder_content(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        tests_folder = tempfile.gettempdir()+os.path.sep+str(uuid.uuid4())
        try:
            GeneralUtilities.ensure_directory_exists(tests_folder)
            filename1 = "test1.csv"
            target_file1 = os.path.join(tests_folder, filename1)
            filename2 = "test2.csv"
            target_file2 = os.path.join(tests_folder, filename2)
            GeneralUtilities.ensure_file_exists(target_file1)
            GeneralUtilities.ensure_file_exists(target_file2)

            # act
            lines: list[str] = sc.run_ls_for_folder_content(tests_folder)

            # assert
            assert len(lines) == 2
            assert filename1 in lines[0]
            assert filename2 in lines[1]
        finally:
            GeneralUtilities.ensure_directory_does_not_exist(tests_folder)

    def test_ls_for_folder(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        tests_folder = tempfile.gettempdir()+os.path.sep+str(uuid.uuid4())
        try:
            GeneralUtilities.ensure_directory_exists(tests_folder)
            filename1 = "test1.csv"
            target_file = os.path.join(tests_folder, filename1)
            filename2 = "test2.csv"
            target_file = os.path.join(tests_folder, filename2)
            GeneralUtilities.ensure_file_exists(target_file)

            # act
            line: str = sc.run_ls_for_folder(tests_folder)

            # assert
            assert filename1 not in line
            assert filename2 not in line
            assert os.path.basename(tests_folder) in line
        finally:
            GeneralUtilities.ensure_directory_does_not_exist(tests_folder)

    def test_run_command_in_folder_rejects_path_traversal(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        base_folder = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
        try:
            GeneralUtilities.ensure_directory_exists(base_folder)
            # actual_folder textually starts with base_folder but climbs out of it via "..".
            escaping_actual_folder = os.path.join(base_folder, "..", "..", "..", "OtherProject")

            # act & assert
            # The path-traversal must be detected and rejected before any command is executed.
            with self.assertRaises(ValueError):
                sc.run_command_in_folder(base_folder, "echo", "", escaping_actual_folder)
        finally:
            GeneralUtilities.ensure_directory_does_not_exist(base_folder)

    def test_run_command_in_folder_rejects_sibling_with_shared_prefix(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        unique = str(uuid.uuid4())
        base_folder = os.path.join(tempfile.gettempdir(), unique)
        # sibling-folder whose path shares the textual prefix of base_folder but is not inside it.
        sibling_folder = base_folder + "_evil"
        try:
            GeneralUtilities.ensure_directory_exists(base_folder)
            GeneralUtilities.ensure_directory_exists(sibling_folder)

            # act & assert
            with self.assertRaises(ValueError):
                sc.run_command_in_folder(base_folder, "echo", "", sibling_folder)
        finally:
            GeneralUtilities.ensure_directory_does_not_exist(base_folder)
            GeneralUtilities.ensure_directory_does_not_exist(sibling_folder)

    def test_run_command_in_folder_rejects_excluded_subfolder(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        base_folder = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
        try:
            excluded_subfolder = os.path.join(base_folder, ".git")
            GeneralUtilities.ensure_directory_exists(excluded_subfolder)

            # act & assert
            # ".git" lies inside base_folder but is explicitly excluded, so it must be rejected.
            with self.assertRaises(ValueError):
                sc.run_command_in_folder(base_folder, "echo", "", excluded_subfolder, [".git", ".claude"])
        finally:
            GeneralUtilities.ensure_directory_does_not_exist(base_folder)

    def test_run_command_in_folder_supports_absolute_excluded_folder(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        base_folder = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
        try:
            absolute_excluded_folder = os.path.join(base_folder, ".git")
            GeneralUtilities.ensure_directory_exists(absolute_excluded_folder)

            # act & assert
            # An excluded folder may also be given as an absolute path (it is resolved against base_folder, which is a
            # no-op for an already-absolute path), so a folder inside it must be rejected.
            with self.assertRaises(ValueError):
                sc.run_command_in_folder(base_folder, "echo", "", absolute_excluded_folder, [absolute_excluded_folder])
        finally:
            GeneralUtilities.ensure_directory_does_not_exist(base_folder)

    def test_path_is_allowed_within_base_folder(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        base_folder = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))

        # act & assert
        # base_folder itself is allowed.
        assert sc.path_is_allowed_within_base_folder(base_folder, base_folder, [".git", ".claude"])
        # A path inside base_folder that is not inside any excluded folder is allowed.
        assert sc.path_is_allowed_within_base_folder(os.path.join(base_folder, "src", "main.py"), base_folder, [".git", ".claude"])
        # A path inside an excluded folder is not allowed.
        assert not sc.path_is_allowed_within_base_folder(os.path.join(base_folder, ".git", "config"), base_folder, [".git", ".claude"])
        # A ".."-trick that resolves back into an excluded folder is not allowed.
        assert not sc.path_is_allowed_within_base_folder(os.path.join(base_folder, ".claude", "..", ".claude", "x"), base_folder, [".claude"])
        # A path outside base_folder is not allowed.
        assert not sc.path_is_allowed_within_base_folder(os.path.join(tempfile.gettempdir(), str(uuid.uuid4())), base_folder, [])
        # An absolute excluded folder is supported (resolved against base_folder, which is a no-op for absolute paths).
        assert not sc.path_is_allowed_within_base_folder(os.path.join(base_folder, ".git", "x"), base_folder, [os.path.join(base_folder, ".git")])

    def test_git_commit_is_ancestor(self) -> None:
        sc = ScriptCollectionCore()
        folder_of_this_file = os.path.dirname(__file__)
        repository = GeneralUtilities.resolve_relative_path("../..", folder_of_this_file)
        assert sc.git_commit_is_ancestor(repository, "d64bc41f9d818d665993758fcdf38477e7086c3f", "c5f8e93bd6f237297d8a75faba8ff5aa6eeb5c08")
        assert not sc.git_commit_is_ancestor(repository, "c5f8e93bd6f237297d8a75faba8ff5aa6eeb5c08", "d64bc41f9d818d665993758fcdf38477e7086c3f")

    def test_rename_git_repositories(self) -> None:
        # arrange
        folder = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
        try:
            GeneralUtilities.ensure_directory_exists(folder)
            sc = ScriptCollectionCore()

            # folder
            # +-- a (folder)
            # |  +-- b1 (folder)
            # |  |   +-- .git (file)
            # |  +-- b2 (folder)
            # |      +-- .git (folder)
            # |          +-- head  (file)
            # +-- .git (folder)
            # |   +-- head (file)
            # +-- c
            #     +-- d1.gitd2.gitd3 (folder)
            # |       +-- head (file)

            folder_a = os.path.join(folder, "a")  # item 1
            folder_a_b1 = os.path.join(folder_a, "b1")  # item 2
            file_a_b1_git = os.path.join(folder_a_b1, ".git")  # item 3
            folder_a_b2 = os.path.join(folder_a, "b2")  # item 4
            folder_a_b2_git = os.path.join(folder_a_b2, ".git")  # item 5
            file_a_b2_git_head = os.path.join(folder_a_b2_git, "head")  # item 6
            folder_git = os.path.join(folder, ".git")  # item 7
            file_git_head = os.path.join(folder_git, "head")  # item 8
            folder_c = os.path.join(folder, "c")  # item 9
            folder_d = os.path.join(folder_c, "d.gitd.gitd")  # item 10
            file_c_d_head = os.path.join(folder_d, "head")  # item 11

            GeneralUtilities.ensure_directory_exists(folder_a)  # item 1
            GeneralUtilities.ensure_directory_exists(folder_a_b1)  # item 2
            GeneralUtilities.ensure_file_exists(file_a_b1_git)  # item 3
            GeneralUtilities.ensure_directory_exists(folder_a_b2)  # item 4
            GeneralUtilities.ensure_directory_exists(folder_a_b2_git)  # item 5
            GeneralUtilities.ensure_file_exists(file_a_b2_git_head)  # item 6
            GeneralUtilities.ensure_directory_exists(folder_git)  # item 7
            GeneralUtilities.ensure_file_exists(file_git_head)  # item 8
            GeneralUtilities.ensure_directory_exists(folder_c)  # item 9
            GeneralUtilities.ensure_directory_exists(folder_d)  # item 10
            GeneralUtilities.ensure_file_exists(file_c_d_head)  # item 11

            # act
            renamed_items = sc.escape_git_repositories_in_folder(folder)

            # assert
            assert os.path.isdir(folder_a)  # item 1
            assert os.path.isdir(folder_a_b1)  # item 2
            assert not os.path.isfile(file_a_b1_git)  # item 3
            assert os.path.isfile(file_a_b1_git+"x")  # item 3
            assert os.path.isdir(folder_a_b2)  # item 4
            assert not os.path.isdir(folder_a_b2_git)  # item 5
            assert os.path.isdir(folder_a_b2_git+"x")  # item 5
            assert not os.path.isfile(file_a_b2_git_head)  # item 6
            assert os.path.isfile(os.path.join(folder_a_b2_git+"x", "head"))  # item 6
            assert not os.path.isdir(folder_git)  # item 7
            assert os.path.isdir(folder_git+"x")  # item 7
            assert not os.path.isfile(file_git_head)  # item 8
            assert os.path.isfile(os.path.join(folder_git+"x", "head"))  # item 8
            assert os.path.isdir(folder_c)  # item 9
            assert not os.path.isdir(folder_d)  # item 10
            assert os.path.isdir(os.path.join(folder_c, "d.gitxd.gitxd"))  # item 10
            assert not os.path.isfile(file_c_d_head)  # item 11
            assert os.path.isfile(os.path.join(folder_c, "d.gitxd.gitxd", "head"))  # item 11

            # act
            sc.deescape_git_repositories_in_folder(renamed_items)

            # assert
            assert os.path.isdir(folder_a)  # item 1
            assert os.path.isdir(folder_a_b1)  # item 2
            assert os.path.isfile(file_a_b1_git)  # item 3
            assert not os.path.isfile(file_a_b1_git+"x")  # item 3
            assert os.path.isdir(folder_a_b2)  # item 4
            assert os.path.isdir(folder_a_b2_git)  # item 5
            assert not os.path.isdir(folder_a_b2_git+"x")  # item 5
            assert os.path.isfile(file_a_b2_git_head)  # item 6
            assert not os.path.isfile(os.path.join(folder_a_b2_git+"x", "head"))  # item 6
            assert os.path.isdir(folder_git)  # item 7
            assert not os.path.isdir(folder_git+"x")  # item 7
            assert os.path.isfile(file_git_head)  # item 8
            assert not os.path.isfile(os.path.join(folder_git+"x", "head"))  # item 8
            assert os.path.isdir(folder_c)  # item 9
            assert os.path.isdir(folder_d)  # item 10
            assert not os.path.isdir(os.path.join(folder_c, "d.gitxd.gitxd"))  # item 10
            assert os.path.isfile(file_c_d_head)  # item 11
            assert not os.path.isfile(os.path.join(folder_c, "d.gitxd.gitxd", "head"))  # item 11

        finally:
            GeneralUtilities.ensure_directory_exists(folder)

    def __create_git_repository_with_one_commit(self, folder: str) -> str:
        sc = ScriptCollectionCore()
        GeneralUtilities.ensure_directory_exists(folder)
        sc.run_program_argsasarray("git", ["init", "--initial-branch", "main"], folder)
        sc.run_program_argsasarray("git", ["config", "user.name", "Testuser"], folder)
        sc.run_program_argsasarray("git", ["config", "user.email", "testuser@example.com"], folder)
        GeneralUtilities.ensure_file_exists(os.path.join(folder, "File.txt"))
        sc.run_program_argsasarray("git", ["add", "."], folder)
        sc.run_program_argsasarray("git", ["commit", "-m", "Initial commit"], folder)
        return sc.run_program_argsasarray("git", ["rev-parse", "HEAD"], folder)[1].strip()

    def test_ensure_branch_is_checked_out_checks_out_the_branch_of_the_pipeline_when_the_repository_is_in_a_detached_head_state(self) -> None:
        # arrange
        folder = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
        try:
            sc = ScriptCollectionCore()
            commit_id = self.__create_git_repository_with_one_commit(folder)
            sc.run_program_argsasarray("git", ["checkout", "--detach", commit_id], folder)
            #the environment is not cleared because the called git-commands require the environment of the testrunner.
            with patch.dict(os.environ, {"CI_COMMIT_REF_NAME": "other/maintenance"}):

                # act
                sc._ScriptCollectionCore__ensure_branch_is_checked_out(folder, "CI_COMMIT_REF_NAME")

                # assert
                assert "other/maintenance" == sc.run_program_argsasarray("git", ["symbolic-ref", "--short", "HEAD"], folder)[1].strip()
                assert commit_id == sc.run_program_argsasarray("git", ["rev-parse", "HEAD"], folder)[1].strip()
        finally:
            GeneralUtilities.ensure_directory_does_not_exist(folder)

    def test_ensure_branch_is_checked_out_checks_out_the_branch_of_the_pipeline_when_that_branch_already_exists(self) -> None:
        # arrange
        folder = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
        try:
            sc = ScriptCollectionCore()
            #this is the situation in which the runner reuses the build-directory of a previous pipeline-run of the same branch.
            commit_id = self.__create_git_repository_with_one_commit(folder)
            sc.run_program_argsasarray("git", ["checkout", "--detach", commit_id], folder)
            with patch.dict(os.environ, {"CI_COMMIT_REF_NAME": "main"}):

                # act
                sc._ScriptCollectionCore__ensure_branch_is_checked_out(folder, "CI_COMMIT_REF_NAME")

                # assert
                assert "main" == sc.run_program_argsasarray("git", ["symbolic-ref", "--short", "HEAD"], folder)[1].strip()
                assert commit_id == sc.run_program_argsasarray("git", ["rev-parse", "HEAD"], folder)[1].strip()
        finally:
            GeneralUtilities.ensure_directory_does_not_exist(folder)

    def test_ensure_branch_is_checked_out_throws_exception_when_the_branchname_is_not_available_in_the_environment(self) -> None:
        # arrange
        folder = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
        try:
            sc = ScriptCollectionCore()
            self.__create_git_repository_with_one_commit(folder)
            with patch.dict(os.environ, {}):
                os.environ.pop("CI_COMMIT_REF_NAME", None)

                # act and assert
                with self.assertRaises(ValueError):
                    sc._ScriptCollectionCore__ensure_branch_is_checked_out(folder, "CI_COMMIT_REF_NAME")
        finally:
            GeneralUtilities.ensure_directory_does_not_exist(folder)

    def test_to_list_none(self):
        # arrange
        testinput = None
        expected = []

        # act
        actual = GeneralUtilities.to_list(testinput, ",")

        # assert
        assert expected == actual

    def test_to_list_empty(self):
        # arrange
        testinput = "   "
        expected = []

        # act
        actual = GeneralUtilities.to_list(testinput, ",")

        # assert
        assert expected == actual

    def test_to_list_one_item(self):
        # arrange
        testinput = " a "
        expected = ["a"]

        # act
        actual = GeneralUtilities.to_list(testinput, ",")

        # assert
        assert expected == actual

    def test_to_list_multiple_items(self):
        # arrange
        testinput = " a , b , c "
        expected = ["a", "b", "c"]

        # act
        actual = GeneralUtilities.to_list(testinput, ",")

        # assert
        assert expected == actual

    def test_get_advanced_errormessage_for_os_error_FileNotFoundError(self):
        # arrange
        filename = "somefile.txt"
        exception = FileNotFoundError()
        exception.filename = filename
        assert isinstance(exception, OSError)
        expected = f"Related path(s): {filename}"

        # act
        actual = GeneralUtilities.get_advanced_errormessage_for_os_error(exception)

        # assert
        assert expected == actual

    def test_get_advanced_errormessage_for_os_error_NotADirectoryError(self):
        # arrange
        filename = "somedirectory"
        exception = NotADirectoryError()
        exception.filename = filename
        assert isinstance(exception, OSError)
        expected = f"Related path(s): {filename}"

        # act
        actual = GeneralUtilities.get_advanced_errormessage_for_os_error(exception)

        # assert
        assert expected == actual

    def test_sc_organize_lines_in_file_test_basic(self) -> None:
        # arrange
        testfile = ScriptCollectionCoreTests.testfileprefix+"test_sc_organize_lines_in_file_test_basic.txt"
        try:
            example_input = ["line1", "line2", "line3"]
            expected_output = ["line1", "line2", "line3"]
            GeneralUtilities.write_lines_to_file(testfile, example_input)

            # act
            ScriptCollectionCore().organize_lines_in_file(testfile, ScriptCollectionCoreTests.encoding, True, True, True, True)
            # arguments: sort ,remove_duplicated_lines, ignore_first_line, remove_empty_lines, ignored_character

            # assert
            assert expected_output == GeneralUtilities.read_lines_from_file(testfile)
        finally:
            os.remove(testfile)

    def test_sc_organize_lines_in_file_test_emptylineandignorefirstline(self) -> None:
        # arrange
        testfile = ScriptCollectionCoreTests.testfileprefix+"test_sc_organize_lines_in_file_test_emptylineandignorefirstline.txt"
        try:
            example_input = ["line1", GeneralUtilities.empty_string, "line3"]
            expected_output = ["line1", "line3"]
            GeneralUtilities.ensure_file_exists(testfile)
            GeneralUtilities.write_lines_to_file(testfile, example_input)

            # act
            ScriptCollectionCore().organize_lines_in_file(testfile, ScriptCollectionCoreTests. encoding, True, True, True, True)
            # arguments: sort ,remove_duplicated_lines, ignore_first_line, remove_empty_lines, ignored_character

            # assert
            assert expected_output == GeneralUtilities.read_lines_from_file(testfile)
        finally:
            os.remove(testfile)

    def test_sc_organize_lines_in_file_test_emptyline(self) -> None:
        # arrange
        testfile = ScriptCollectionCoreTests.testfileprefix+"test_sc_organize_lines_in_file_test_emptyline.txt"
        try:
            example_input = ["line1", GeneralUtilities.empty_string, "line3"]
            expected_output = ["line1", "line3"]
            GeneralUtilities.ensure_file_exists(testfile)
            GeneralUtilities.write_lines_to_file(testfile, example_input)

            # act
            ScriptCollectionCore().organize_lines_in_file(testfile, ScriptCollectionCoreTests.encoding, True, True, False, True, [])
            # arguments: sort ,remove_duplicated_lines, ignore_first_line, remove_empty_lines, ignored_character

            # assert
            assert expected_output == GeneralUtilities. read_lines_from_file(testfile)
        finally:
            os.remove(testfile)

    def test_sc_organize_lines_in_file_with_ignored_character(self) -> None:
        # arrange
        testfile = ScriptCollectionCoreTests.testfileprefix+"test_sc_organize_lines_in_file_test_emptyline.txt"
        try:
            example_input = ["line5", " line4", "line3", "#line2", "# line6", "line7", "line1"]
            expected_output = ["line1", "#line2", "line3", " line4", "line5", "# line6", "line7"]
            GeneralUtilities.write_lines_to_file(testfile, example_input)

            # act
            ScriptCollectionCore().organize_lines_in_file(testfile,  ScriptCollectionCoreTests.encoding, True, True, False, True, ["#", " "])
            # arguments: sort ,remove_duplicated_lines, ignore_first_line, remove_empty_lines, ignored_character

            # assert
            assert expected_output == GeneralUtilities.read_lines_from_file(testfile)
        finally:
            os.remove(testfile)

    def test_simple_program_call_is_mockable(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        sc.mock_program_calls = True
        sc.register_mock_program_call("p", "a1", "/tmp", 0, "out 1", "err 1", 40)
        sc.register_mock_program_call("p", "a2", "/tmp", 0, "out 2", "err 2", 44)

        # act
        result1 = sc.run_program("p", "a1", "/tmp")
        result2 = sc.run_program("p", "a2", "/tmp")

        # assert
        assert result1 == (0, "out 1", "err 1", 40)
        assert result2 == (0, "out 2", "err 2", 44)
        sc.verify_no_pending_mock_program_calls()

    def test_simple_program_call(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        dir_path = os.path.dirname(os.path.realpath(__file__))

        # act
        (exit_code, stdout, stderr, _3) = sc.run_program("git", "rev-parse HEAD", dir_path)

        # assert
        assert exit_code == 0
        assert len(stdout) == 40
        assert stderr == GeneralUtilities.empty_string

    def test_file_is_git_ignored_1(self) -> None:

        # arrange
        sc = ScriptCollectionCore()
        repository = str(Path(__file__).parent.parent.parent.absolute())

        # act
        result = sc.file_is_git_ignored(os.path.join("ScriptCollection", "pyproject.toml"), repository)

        # assert
        assert result is False

    def test_file_is_git_ignored_2(self) -> None:

        # arrange
        sc = ScriptCollectionCore()
        repository = str(Path(__file__).parent.parent.parent.absolute())

        # act
        result = sc.file_is_git_ignored(os.path.join("ScriptCollection", "ScriptCollection.egg-info", "entry_points.txt"), repository)

        # assert
        assert result is True

    def test_file_is_git_ignored_3(self) -> NoReturn:
        tests_folder = tempfile.gettempdir()+os.path.sep+str(uuid.uuid4())
        GeneralUtilities.ensure_directory_exists(tests_folder)
        sc = ScriptCollectionCore()
        sc.run_program("git", "init", tests_folder)

        ignored_logfolder_name = "logfolder"
        ignored_logfolder = tests_folder+os.path.sep+ignored_logfolder_name
        GeneralUtilities.ensure_directory_exists(ignored_logfolder)

        gitignore_file = tests_folder+os.path.sep+".gitignore"
        GeneralUtilities.ensure_file_exists(gitignore_file)
        GeneralUtilities.write_lines_to_file(gitignore_file, [ignored_logfolder_name+"/**", "!"+ignored_logfolder_name+"/.gitkeep"])

        gitkeep_file = ignored_logfolder+os.path.sep+".gitkeep"
        GeneralUtilities.ensure_file_exists(gitkeep_file)

        log_file = ignored_logfolder+os.path.sep+"logfile.log"
        GeneralUtilities.ensure_file_exists(log_file)

        assert not sc.file_is_git_ignored(".gitignore", tests_folder)
        assert not sc.file_is_git_ignored(".gitkeep", tests_folder)
        assert sc.file_is_git_ignored(ignored_logfolder_name+os.path.sep+"logfile.log", tests_folder)

        GeneralUtilities.ensure_directory_does_not_exist(tests_folder)

    def test_program_call_returns_output_although_the_reading_starts_after_the_process_terminated(self) -> None:
        # arrange
        # The reader-threads which transfer the output of a process from its pipes into the internal queues can be
        # scheduled after the process already terminated. This happens in practice with short-running processes on
        # fast systems. The delay below simulates this scheduling-latency deterministically. The output of the
        # process must not get lost in this situation.
        sc = ScriptCollectionCore()
        dir_path = os.path.dirname(os.path.realpath(__file__))
        original_enqueue_output = ScriptCollectionCore._ScriptCollectionCore__enqueue_output

        def delayed_enqueue_output(file, queue) -> None:
            time.sleep(0.3)
            original_enqueue_output(file, queue)

        # act
        with patch.object(ScriptCollectionCore, "_ScriptCollectionCore__enqueue_output", staticmethod(delayed_enqueue_output)):
            (exit_code, stdout, stderr, _3) = sc.run_program("git", "rev-parse HEAD", dir_path)

        # assert
        assert exit_code == 0
        assert len(stdout) == 40
        assert stderr == GeneralUtilities.empty_string

    def test_program_call_with_timeout_raises_timeout_error_if_the_program_does_not_terminate(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        dir_path = os.path.dirname(os.path.realpath(__file__))

        # act & assert
        with self.assertRaises(TimeoutError):
            sc.run_program_argsasarray(sys.executable, ["-c", "import time; time.sleep(60)"], dir_path, timeoutInSeconds=1)

    def test_program_call_with_timeout_returns_the_output_if_the_program_terminates_in_time(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        dir_path = os.path.dirname(os.path.realpath(__file__))

        # act
        (exit_code, stdout, _2, _3) = sc.run_program_argsasarray(sys.executable, ["-c", "print('expected-output')"], dir_path, timeoutInSeconds=60)

        # assert
        assert exit_code == 0
        assert stdout == "expected-output"

    def test_simple_program_call_argsasarray(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        dir_path = os.path.dirname(os.path.realpath(__file__))

        # act
        (exit_code, _, _2, _3) = sc.run_program_argsasarray("git", ["status"], dir_path)

        # assert
        assert exit_code == 0

    def test_format_html_content_trims_whitespace_in_text(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        input_content = "<b>  x  </b>"

        # act
        result = sc.format_html_content(input_content)

        # assert
        assert result == "<b>x</b>"

    def test_format_html_content_collapses_multiline_text(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        input_content = "<b>  \n   x  \n  </b>"

        # act
        result = sc.format_html_content(input_content)

        # assert
        assert result == "<b>x</b>"

    def test_format_html_content_collapses_multiline_text_with_inline_attribute(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        input_content = '<mat-checkbox formControlName="x">Can receive\n            ONVIF-commands.</mat-checkbox>'

        # act
        result = sc.format_html_content(input_content)

        # assert
        assert result == '<mat-checkbox formControlName="x">Can receive ONVIF-commands.</mat-checkbox>'

    def  test_format_html_content_trims_text_in_nested_elements(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        input_content = "<div>\n  <p>  hello   world  </p>\n  <span>  \n    test  \n  </span>\n</div>"

        # act
        result = sc.format_html_content(input_content)

        # assert
        assert result=="""<div>
  <p>hello world</p>
  <span>test</span>
</div>"""

    def test_format_html_content_adds_doctype_when_requested(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        input_content = "<html><body></body></html>"

        # act
        result = sc.format_html_content(input_content, add_html_declaration=True)

        # assert
        assert result.startswith("<!DOCTYPE html>")

    def test_format_html_content_does_not_add_doctype_by_default(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        input_content = "<html><body></body></html>"

        # act
        result = sc.format_html_content(input_content)

        # assert
        assert "DOCTYPE" not in result

    def test_format_html_content_indents_deeply_nested_elements(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        input_content = "<div><section><p>  hello  </p></section></div>"
        expected = "<div>\n  <section>\n    <p>hello</p>\n  </section>\n</div>"

        # act
        result = sc.format_html_content(input_content)

        # assert
        assert result == expected

    def test_format_json_file_indents_content(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        file = os.path.join(tempfile.gettempdir(), str(uuid.uuid4())+".json")
        GeneralUtilities.write_text_to_file(file, '{"a":1,"b":[1,2]}', self.encoding)

        try:
            # act
            sc.format_json_file(file)

            # assert
            assert GeneralUtilities.read_text_from_file(file, self.encoding) == '{\n  "a": 1,\n  "b": [\n    1,\n    2\n  ]\n}\n'
        finally:
            GeneralUtilities.ensure_file_does_not_exist(file)

    def test_format_json_file_keeps_property_order(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        file = os.path.join(tempfile.gettempdir(), str(uuid.uuid4())+".json")
        GeneralUtilities.write_text_to_file(file, '{"b":1,"a":2}', self.encoding)

        try:
            # act
            sc.format_json_file(file)

            # assert
            assert GeneralUtilities.read_text_from_file(file, self.encoding) == '{\n  "b": 1,\n  "a": 2\n}\n'
        finally:
            GeneralUtilities.ensure_file_does_not_exist(file)

    def test_format_json_file_uses_given_indentation(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        file = os.path.join(tempfile.gettempdir(), str(uuid.uuid4())+".json")
        GeneralUtilities.write_text_to_file(file, '{"a":{"b":1}}', self.encoding)

        try:
            # act
            sc.format_json_file(file, 4)

            # assert
            assert GeneralUtilities.read_text_from_file(file, self.encoding) == '{\n    "a": {\n        "b": 1\n    }\n}\n'
        finally:
            GeneralUtilities.ensure_file_does_not_exist(file)

    def test_format_json_file_keeps_non_ascii_characters_and_normalizes_line_endings(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        file = os.path.join(tempfile.gettempdir(), str(uuid.uuid4())+".json")
        GeneralUtilities.write_text_to_file(file, '{\r\n"a":"ä"\r\n}', self.encoding)

        try:
            # act
            sc.format_json_file(file)

            # assert
            assert GeneralUtilities.read_binary_from_file(file) == '{\n  "a": "ä"\n}\n'.encode(self.encoding)
        finally:
            GeneralUtilities.ensure_file_does_not_exist(file)

    def test_format_xml_file_keeps_namespace_of_root_element_as_default_namespace(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        file = os.path.join(tempfile.gettempdir(), str(uuid.uuid4())+".nuspec")
        GeneralUtilities.write_text_to_file(file, '<package xmlns="http://schemas.microsoft.com/packaging/2011/10/nuspec.xsd"><metadata minClientVersion="2.12"><version>1.0.0</version></metadata></package>', self.encoding)

        try:
            # act
            sc.format_xml_file(file)

            # assert
            assert GeneralUtilities.read_text_from_file(file, self.encoding) == "<?xml version='1.0' encoding='utf-8'?>\n<package xmlns=\"http://schemas.microsoft.com/packaging/2011/10/nuspec.xsd\">\n  <metadata minClientVersion=\"2.12\">\n    <version>1.0.0</version>\n  </metadata>\n</package>\n"
        finally:
            GeneralUtilities.ensure_file_does_not_exist(file)

    def test_format_xml_file_replaces_generated_namespace_prefix_by_default_namespace(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        file = os.path.join(tempfile.gettempdir(), str(uuid.uuid4())+".nuspec")
        GeneralUtilities.write_text_to_file(file, '<ns0:package xmlns:ns0="http://schemas.microsoft.com/packaging/2011/10/nuspec.xsd"><ns0:metadata minClientVersion="2.12"><ns0:version>1.0.0</ns0:version></ns0:metadata></ns0:package>', self.encoding)

        try:
            # act
            sc.format_xml_file(file)

            # assert
            assert GeneralUtilities.read_text_from_file(file, self.encoding) == "<?xml version='1.0' encoding='utf-8'?>\n<package xmlns=\"http://schemas.microsoft.com/packaging/2011/10/nuspec.xsd\">\n  <metadata minClientVersion=\"2.12\">\n    <version>1.0.0</version>\n  </metadata>\n</package>\n"
        finally:
            GeneralUtilities.ensure_file_does_not_exist(file)

    def test_format_xml_file_keeps_file_without_namespace_unchanged(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        file = os.path.join(tempfile.gettempdir(), str(uuid.uuid4())+".csproj")
        GeneralUtilities.write_text_to_file(file, '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><Version>1.0.0</Version></PropertyGroup></Project>', self.encoding)

        try:
            # act
            sc.format_xml_file(file, add_xml_declaration=False)

            # assert
            assert GeneralUtilities.read_text_from_file(file, self.encoding) == "<Project Sdk=\"Microsoft.NET.Sdk\">\n  <PropertyGroup>\n    <Version>1.0.0</Version>\n  </PropertyGroup>\n</Project>\n"
        finally:
            GeneralUtilities.ensure_file_does_not_exist(file)

    def test_replace_version_in_nuspec_file_replaces_version_in_prefixed_document(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        file = os.path.join(tempfile.gettempdir(), str(uuid.uuid4())+".nuspec")
        GeneralUtilities.write_text_to_file(file, '<ns0:package xmlns:ns0="http://schemas.microsoft.com/packaging/2011/10/nuspec.xsd"><ns0:metadata><ns0:version>1.0.0</ns0:version></ns0:metadata></ns0:package>', self.encoding)

        try:
            # act
            sc.replace_version_in_nuspec_file(file, "2.3.4")

            # assert
            assert "<ns0:version>2.3.4</ns0:version>" in GeneralUtilities.read_text_from_file(file, self.encoding)
        finally:
            GeneralUtilities.ensure_file_does_not_exist(file)

    def test_update_year_in_copyright_tags_updates_year_in_prefixed_document(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        file = os.path.join(tempfile.gettempdir(), str(uuid.uuid4())+".nuspec")
        GeneralUtilities.write_text_to_file(file, '<ns0:package xmlns:ns0="http://schemas.microsoft.com/packaging/2011/10/nuspec.xsd"><ns0:metadata>\n<ns0:copyright>Copyright © 1999 by Someone</ns0:copyright>\n</ns0:metadata></ns0:package>', self.encoding)

        try:
            # act
            sc.update_year_in_copyright_tags(file)

            # assert
            assert f"<ns0:copyright>Copyright © {GeneralUtilities.get_now().year} by Someone</ns0:copyright>" in GeneralUtilities.read_text_from_file(file, self.encoding)
        finally:
            GeneralUtilities.ensure_file_does_not_exist(file)

    def test_add_tooltips_to_chart_diagram_adds_title_for_datapoints(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        file = os.path.join(tempfile.gettempdir(), str(uuid.uuid4())+".svg")
        content = '<svg xmlns="http://www.w3.org/2000/svg"><path aria-label="Date: 2026-01-01 00:00:00Z; Lines of Code: 42" aria-roledescription="point" d="M0,0"/></svg>'
        GeneralUtilities.write_text_to_file(file, content, self.encoding)

        try:
            # act
            amount_of_tooltips = sc.add_tooltips_to_chart_diagram(file)

            # assert
            assert amount_of_tooltips == 1
            titles = ET.XML(GeneralUtilities.read_text_from_file(file, self.encoding)).findall(f".//{{{self.svg_namespace}}}title")
            assert len(titles) == 1
            assert titles[0].text == "Date: 2026-01-01 00:00:00Z; Lines of Code: 42"
        finally:
            GeneralUtilities.ensure_file_does_not_exist(file)

    def test_add_tooltips_to_chart_diagram_ignores_elements_which_are_no_datapoints(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        file = os.path.join(tempfile.gettempdir(), str(uuid.uuid4())+".svg")
        content = '<svg xmlns="http://www.w3.org/2000/svg"><path aria-label="X-axis titled Date" aria-roledescription="axis" d="M0,0"/><path aria-roledescription="point" d="M0,0"/></svg>'
        GeneralUtilities.write_text_to_file(file, content, self.encoding)

        try:
            # act
            amount_of_tooltips = sc.add_tooltips_to_chart_diagram(file)

            # assert
            assert amount_of_tooltips == 0
            assert len(ET.XML(GeneralUtilities.read_text_from_file(file, self.encoding)).findall(f".//{{{self.svg_namespace}}}title")) == 0
        finally:
            GeneralUtilities.ensure_file_does_not_exist(file)

    xliff2_namespace = "urn:oasis:names:tc:xliff:document:2.0"

    def __write_xliff2_file(self, file: str, target_language: str, source: str, target: str) -> None:
        """An xliff2-file containing the single unit "greeting" with the given source-text, and - if target_language and target are
        given - with the given target-text in the state "translated". Used by the sync_xlf2_files-testcases below."""
        target_language_attribute = GeneralUtilities.empty_string if target_language is None else f' trgLang="{target_language}"'
        segment_content = f"<source>{source}</source>" if target is None else f'<source>{source}</source><target>{target}</target>'
        state_attribute = GeneralUtilities.empty_string if target is None else ' state="translated"'
        content = (
            '<?xml version="1.0" encoding="UTF-8" ?>'
            f'<xliff xmlns="{self.xliff2_namespace}" version="2.0" srcLang="en"{target_language_attribute}>'
            '<file id="flutterl10n" original="app_en.arb">'
            '<unit id="greeting">'
            f'<segment{state_attribute}>{segment_content}</segment>'
            '</unit></file></xliff>'
        )
        GeneralUtilities.write_text_to_file(file, content, self.encoding)

    def __read_segment_of_the_only_unit(self, file: str) -> ET.Element:
        return ET.XML(GeneralUtilities.read_text_from_file(file, self.encoding)).find(f".//{{{self.xliff2_namespace}}}segment")

    def test_sync_xlf2_files_updates_the_source_of_a_translated_unit_whose_source_changed(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        folder = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
        GeneralUtilities.ensure_directory_exists(folder)
        try:
            self.__write_xliff2_file(os.path.join(folder, "messages.xlf"), None, "Hello again", None)
            language_file = os.path.join(folder, "messages.de.xlf")
            self.__write_xliff2_file(language_file, "de", "Hello", "Hallo")

            # act
            sc.sync_xlf2_files("messages", ["de"], folder)

            # assert
            segment = self.__read_segment_of_the_only_unit(language_file)
            assert segment.find(f"{{{self.xliff2_namespace}}}source").text == "Hello again"
            #the translation which was written for the old source-text is not a translation of the new one, so the segment has to be
            #translated again; its target is kept until that happened.
            assert segment.get("state") == "initial"
            assert segment.find(f"{{{self.xliff2_namespace}}}target").text == "Hallo"
        finally:
            GeneralUtilities.ensure_directory_does_not_exist(folder)

    def test_sync_xlf2_files_keeps_a_translated_unit_whose_source_did_not_change(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        folder = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
        GeneralUtilities.ensure_directory_exists(folder)
        try:
            self.__write_xliff2_file(os.path.join(folder, "messages.xlf"), None, "Hello", None)
            language_file = os.path.join(folder, "messages.de.xlf")
            self.__write_xliff2_file(language_file, "de", "Hello", "Hallo")

            # act
            sc.sync_xlf2_files("messages", ["de"], folder)

            # assert
            segment = self.__read_segment_of_the_only_unit(language_file)
            assert segment.find(f"{{{self.xliff2_namespace}}}source").text == "Hello"
            assert segment.get("state") == "translated"
            assert segment.find(f"{{{self.xliff2_namespace}}}target").text == "Hallo"
        finally:
            GeneralUtilities.ensure_directory_does_not_exist(folder)

    def test_translate_xlf_files_in_folder_translates_the_languages_the_service_offers(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        folder = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
        GeneralUtilities.ensure_directory_exists(folder)
        try:
            self.__write_xliff2_file(os.path.join(folder, "messages.de.xlf"), "de", "Hello", None)
            self.__write_xliff2_file(os.path.join(folder, "messages.fr.xlf"), "fr", "Hello", None)

            # act
            with patch.object(ScriptCollectionCore, "get_supported_translation_languages", return_value={"de", "fr"}):
                with patch.object(ScriptCollectionCore, "translate", return_value="Hallo"):
                    sc.translate_xlf_files_in_folder(folder, "en", "https://translation-service.example.com")

            # assert
            for language in ["de", "fr"]:
                segment = self.__read_segment_of_the_only_unit(os.path.join(folder, f"messages.{language}.xlf"))
                assert segment.get("state") == "translated"
        finally:
            GeneralUtilities.ensure_directory_does_not_exist(folder)

    def test_translate_xlf_files_in_folder_leaves_a_language_the_service_does_not_offer_untranslated(self) -> None:
        # arrange
        # A project states which languages it has; a translation-service knows a limited set of them. A language the
        # service does not know keeps its texts in the base-language and must not stop the languages it does know
        # from being translated.
        sc = ScriptCollectionCore()
        folder = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
        GeneralUtilities.ensure_directory_exists(folder)
        try:
            unsupported_file = os.path.join(folder, "messages.tk.xlf")
            supported_file = os.path.join(folder, "messages.de.xlf")
            self.__write_xliff2_file(unsupported_file, "tk", "Hello", None)
            self.__write_xliff2_file(supported_file, "de", "Hello", None)

            # act
            with patch.object(ScriptCollectionCore, "get_supported_translation_languages", return_value={"de"}):
                with patch.object(ScriptCollectionCore, "translate", return_value="Hallo") as translate:
                    sc.translate_xlf_files_in_folder(folder, "en", "https://translation-service.example.com")

            # assert
            assert translate.call_count == 1
            assert self.__read_segment_of_the_only_unit(supported_file).get("state") == "translated"
            untranslated_segment = self.__read_segment_of_the_only_unit(unsupported_file)
            # A segment which was never translated has no state of its own, which is what "initial" means.
            assert untranslated_segment.get("state", "initial") == "initial"
            assert untranslated_segment.find(f"{{{self.xliff2_namespace}}}target") is None
        finally:
            GeneralUtilities.ensure_directory_does_not_exist(folder)

    def test_split_image_address_and_tag_with_tag(self) -> None:
        # act
        result = ScriptCollectionCore.split_image_address_and_tag("myregistry.example.com/debian:12")

        # assert
        assert result == ("myregistry.example.com/debian", "12")

    def test_split_image_address_and_tag_without_tag(self) -> None:
        # act
        result = ScriptCollectionCore.split_image_address_and_tag("myregistry.example.com/debian")

        # assert
        assert result == ("myregistry.example.com/debian", "latest")

    def test_split_image_address_and_tag_with_port_and_tag(self) -> None:
        # act
        result = ScriptCollectionCore.split_image_address_and_tag("myregistry.example.com:5000/debian:12")

        # assert
        assert result == ("myregistry.example.com:5000/debian", "12")

    def test_split_image_address_and_tag_with_port_and_without_tag(self) -> None:
        # act
        result = ScriptCollectionCore.split_image_address_and_tag("myregistry.example.com:5000/debian")

        # assert
        assert result == ("myregistry.example.com:5000/debian", "latest")


# TODO all testcases should be independent of epew
