import os
import sys
import tempfile
from ..GeneralUtilities import GeneralUtilities
from ..SCLog import LogLevel
from ..ScriptCollectionCore import ScriptCollectionCore


class TFCPS_CodeSpellCheck:
    """Searches for typos in a repository using codespell.

    codespell does not evaluate ".gitignore", so when it searches a folder recursively it also checks git-ignored content like
    "node_modules", "bin", "obj" or the artifacts-folders of the codeunits, which costs a lot of runtime and only produces findings
    which can not be fixed. Because of that only the files which are not git-ignored are checked.
    A repository can contain a lot of files (for example 100000) and the length of a command-line is limited (on Windows to 32767
    characters), so the files are not passed as command-line-arguments but are written into a file-list which is passed to codespell
    using "@<file-list>" (codespell reads additional arguments from this file, one argument per line). This way codespell is called only once."""

    sc: ScriptCollectionCore = None

    codespell_exitcode_for_found_typos: int = 65

    def __init__(self, sc: ScriptCollectionCore):
        self.sc = sc

    @GeneralUtilities.check_arguments
    def search_for_typos(self, repository_folder: str) -> list[str]:
        """Returns the findings of codespell for all files of the repository which are not git-ignored.
        codespell runs in the repository-folder, so an optional "<repository>/.codespellrc" is used automatically.
        Folders (relative to the repository-root, one per line) which should be ignored additionally (for example because they contain
        committed files which should not be checked) can be defined in the optional file "<repository>/.ScriptCollection/CodeSpellIgnore.txt"."""
        files: list[str] = self.get_files_to_check(repository_folder)
        if len(files) == 0:
            return []
        self.sc.log.log(f"Check {len(files)} file(s) using codespell...", LogLevel.Debug)
        (file_descriptor, file_list) = tempfile.mkstemp(prefix="CodeSpellFileList_", suffix=".txt")
        try:
            # codespell reads the file-list using the filesystem-encoding, so it is written using the same encoding.
            with os.fdopen(file_descriptor, "w", encoding=sys.getfilesystemencoding(), errors=sys.getfilesystemencodeerrors(), newline="\n") as file_list_stream:
                file_list_stream.write("\n".join(files) + "\n")
            # "--check-hidden" is required because codespell would skip hidden files (like ".gitignore") otherwise, even if they are passed explicitly.
            arguments: list[str] = ["--check-hidden"] + self.get_skip_arguments(repository_folder) + [f"@{file_list}"]
            (exit_code, stdout, stderr, _) = self.sc.run_program_argsasarray("codespell", arguments, repository_folder, throw_exception_if_exitcode_is_not_zero=False)
        finally:
            GeneralUtilities.ensure_file_does_not_exist(file_list)
        if exit_code not in (0, TFCPS_CodeSpellCheck.codespell_exitcode_for_found_typos):
            raise ValueError(f"codespell failed with exit-code {exit_code}: {stderr}")
        return [line for line in GeneralUtilities.string_to_lines(stdout) if GeneralUtilities.string_has_content(line)]

    @GeneralUtilities.check_arguments
    def get_files_to_check(self, repository_folder: str) -> list[str]:
        """Returns the files (relative to the repository-folder and with the prefix "./") which are not git-ignored.
        Hidden files and files inside hidden folders (for example ".github") are included too. Only the content of ".git"-folders is always excluded.
        The prefix "./" is used because the skip-patterns of codespell (for example in ".codespellrc") are usually written in this form.
        Additionally it ensures that no entry of the file-list starts with "-" or "@", so that codespell does not interpret a file as option or as another file-list."""
        result: list[str] = []
        for absolute_path in self.sc.get_not_git_ignored_files_of_folder(repository_folder):
            relative_path: str = os.path.relpath(absolute_path, repository_folder).replace("\\", "/")
            if ".git" in relative_path.split("/"):
                continue
            result.append(f"./{relative_path}")
        return result

    @GeneralUtilities.check_arguments
    def get_skip_arguments(self, repository_folder: str) -> list[str]:
        """Returns the "--skip"-argument for codespell based on the optional file "<repository>/.ScriptCollection/CodeSpellIgnore.txt"."""
        ignore_file = os.path.join(repository_folder, ".ScriptCollection", "CodeSpellIgnore.txt")
        if not os.path.isfile(ignore_file):
            return []
        skip_patterns: list[str] = []
        for line in GeneralUtilities.string_to_lines(GeneralUtilities.read_text_from_file(ignore_file)):
            folder = line.strip().replace("\\", "/").strip("/")
            if folder.startswith("./"):
                folder = folder[2:]
            if folder != "" and not folder.startswith("#"):
                skip_patterns.append(f"./{folder}")
                skip_patterns.append(f"./{folder}/*")
        if len(skip_patterns) == 0:
            return []
        return ["--skip=" + ",".join(skip_patterns)]
