import os
import re
import tempfile
from ...GeneralUtilities import GeneralUtilities,Dependency
from ...SCLog import  LogLevel
from ..TFCPS_CodeUnitSpecific_Base import TFCPS_CodeUnitSpecific_Base,TFCPS_CodeUnitSpecific_Base_CLI

class TFCPS_CodeUnitSpecific_Python_Functions(TFCPS_CodeUnitSpecific_Base):

    def __init__(self,current_file:str,verbosity:LogLevel,targetenvironmenttype:str,use_cache:bool,is_pre_merge:bool):
        super().__init__(current_file, verbosity,targetenvironmenttype,use_cache,is_pre_merge)
 

    @GeneralUtilities.check_arguments
    def build(self) -> None:
        codeunit_folder = self.get_codeunit_folder()
        target_directory = GeneralUtilities.resolve_relative_path("../Artifacts/BuildResult_Wheel", os.path.join(self.get_artifacts_folder()))
        GeneralUtilities.ensure_directory_does_not_exist(os.path.join(self.get_codeunit_folder(),".pytest_cache"))
        GeneralUtilities.ensure_directory_does_not_exist(os.path.join(self.get_codeunit_folder(),"__pycache__"))
        GeneralUtilities.ensure_directory_does_not_exist(os.path.join(self.get_codeunit_folder(),"build"))
        GeneralUtilities.ensure_directory_does_not_exist(os.path.join(self.get_codeunit_folder(),f"{self.get_codeunit_name()}.egg-info"))
        GeneralUtilities.ensure_directory_exists(target_directory)
        self.__check_compilable()
        self._protected_sc.run_program(GeneralUtilities.get_python_executable(), f"-m build --wheel --outdir {target_directory}", codeunit_folder,print_live_output=self.get_verbosity()==LogLevel.Debug)
        self.generate_bom_for_python_project()
        self.copy_source_files_to_output_directory()

    @GeneralUtilities.check_arguments
    def __check_compilable(self) -> None:
        self.__ensure_sourcecode_is_compilable_using_python_compile()
        self.__ensure_sourcecode_has_no_errors_using_pylint()

    @GeneralUtilities.check_arguments
    def __ensure_sourcecode_has_no_errors_using_pylint(self) -> None:
        """Checks the sourcecode which goes into the wheel with pylint and raises when pylint reports a message
        of the category error or fatal.

        This finds the defects which the compile-check can not find, because they are not syntax-errors: a call
        which does not pass an argument for a parameter which has no default-value (E1120), a name which is not
        defined (E0602) and an attribute which the accessed object does not have (E1101), for example.

        Only these two categories are checked: a convention-, refactor- or warning-message is a matter of style
        and belongs to the linting-task, while an error- or a fatal-message means the sourcecode is broken,
        which must not result in a wheel at all."""
        codeunit_name = self.get_codeunit_name()
        # The check runs in an isolated folder which only contains this codeunit, for the same reason as in
        # "linting": otherwise a sibling-codeunit-source-folder of the repository would shadow the installed
        # dependency-package of the same name while pylint resolves the imports, which would result in a
        # false-positive import-error.
        ignored_subfolders = ["Other", "__pycache__", "*.egg-info", "build", "dist", "venv", ".venv", ".pytest_cache", ".git"]
        with tempfile.TemporaryDirectory(dir=GeneralUtilities.get_temp_folder()) as isolation_folder:
            GeneralUtilities.copy_content_of_folder(self.get_codeunit_folder(), os.path.join(isolation_folder, codeunit_name), ignored_glob_patterms=ignored_subfolders)
            pylint_configuration_file = os.path.join(self.get_repository_folder(), ".pylintrc")
            if os.path.isfile(pylint_configuration_file):
                GeneralUtilities.safe_copy(pylint_configuration_file, os.path.join(isolation_folder, ".pylintrc"))
            # "--errors-only" suppresses every message whose category is not error or fatal, so the exitcode of
            # pylint is only unequal to zero when such a message was found.
            (exit_code, stdout, stderr, _) = self._protected_sc.run_program("pylint", f"--errors-only {codeunit_name}/{codeunit_name}", isolation_folder, throw_exception_if_exitcode_is_not_zero=False)
        pylint_exitcode_for_a_usage_error: int = 32
        if exit_code == pylint_exitcode_for_a_usage_error:
            raise ValueError(f"Pylint could not be executed properly, so the sourcecode of the codeunit {codeunit_name} was not checked:\n{stdout}{stderr}")
        if exit_code != 0:
            raise ValueError(f"Pylint reported a message of the category error or fatal in the sourcecode of the codeunit {codeunit_name}, so no wheel was built:\n{stdout}{stderr}")

    @GeneralUtilities.check_arguments
    def __ensure_sourcecode_is_compilable_using_python_compile(self) -> None:
        """Checks every python-file which goes into the wheel and raises when one of them can not be compiled.

        This check exists so that a codeunit whose sourcecode is broken does not result in a wheel at all. It is
        done with the builtin "compile"-function instead of with a linter: "compile" parses the file and reports
        a syntax-error without executing anything of it, so the check needs no further tool and can not have
        side-effects. Importing the modules instead would find more, but it would run the code of every module.
        Everything which is a matter of style belongs to the linting-task and is deliberately not checked here."""
        codeunit_name = self.get_codeunit_name()
        repository_folder = self.get_repository_folder()
        source_folder = os.path.join(self.get_codeunit_folder(), codeunit_name)
        errors: list[str] = []
        for file in GeneralUtilities.get_all_files_of_folder(source_folder):
            if not file.endswith(".py"):
                continue
            if self._protected_sc.file_is_git_ignored(os.path.relpath(file, repository_folder), repository_folder):
                continue
            try:
                # The file is read as "utf-8-sig" so that a byte-order-mark is removed instead of being handed to
                # "compile" as the first character, which would report a syntax-error although python itself
                # accepts a sourcecode-file which starts with a byte-order-mark.
                # The filename is passed so that it appears in the message of a syntax-error.
                compile(GeneralUtilities.read_text_from_file(file, "utf-8-sig"), file, "exec")
            except SyntaxError as exception:
                errors.append(f'"{file}" (line {exception.lineno}): {exception.msg}')
            except ValueError as exception:
                # "compile" raises a ValueError instead of a SyntaxError when the sourcecode contains a
                # null-byte, which is not a syntax-error but makes the file just as unusable.
                errors.append(f'"{file}": {exception}')
        if 0 < len(errors):
            raise ValueError(f"The sourcecode of the codeunit {codeunit_name} can not be compiled, so no wheel was built:\n" + "\n".join(errors))

    @GeneralUtilities.check_arguments
    def generate_bom_for_python_project(self) -> None:
        codeunit_folder: str=self.get_codeunit_folder()
        codeunitname: str=self.get_codeunit_name()
        repository_folder = os.path.dirname(codeunit_folder)
        codeunitversion = self.tfcps_Tools_General.get_version_of_codeunit(self.get_codeunit_file())
        bom_folder = "Other/Artifacts/BOM"
        bom_folder_full = os.path.join(codeunit_folder, bom_folder)
        GeneralUtilities.ensure_directory_exists(bom_folder_full)
        if not os.path.isfile(os.path.join(codeunit_folder, "requirements.txt")):
            raise ValueError(f"Codeunit {codeunitname} does not have a 'requirements.txt'-file.")
        # TODO check that all values from pyproject.cfg are contained in requirements.txt
        result = self._protected_sc.run_program("cyclonedx-py", "requirements", codeunit_folder)
        bom_file_relative_json = f"{bom_folder}/{codeunitname}.{codeunitversion}.bom.json"
        bom_file_relative_xml = f"{bom_folder}/{codeunitname}.{codeunitversion}.bom.xml"
        bom_file_json = os.path.join(codeunit_folder, bom_file_relative_json)
        bom_file_xml = os.path.join(codeunit_folder, bom_file_relative_xml)

        enabled:bool=False
        if enabled:#TODO cyclonedx must be available for all platforms in the global sc-cache-folder
            GeneralUtilities.ensure_file_exists(bom_file_json)
            GeneralUtilities.write_text_to_file(bom_file_json, result[1])
            cyclonedx_exe=self.tfcps_Tools_General.ensure_cyclonedxcli_is_available(not self.use_cache())
            self._protected_sc.run_program(cyclonedx_exe, f"convert --input-file ./{codeunitname}/{bom_file_relative_json} --input-format json --output-file ./{codeunitname}/{bom_file_relative_xml} --output-format xml", repository_folder)
            self._protected_sc.format_xml_file(bom_file_xml)
            GeneralUtilities.ensure_file_does_not_exist(bom_file_json)

    @GeneralUtilities.check_arguments
    def linting(self) -> None:
        codeunitname: str = self.get_codeunit_name()

        repository_folder: str = self.get_repository_folder()
        codeunit_folder = os.path.join(repository_folder, codeunitname)
        errors_found = False
        self._protected_sc.log.log(f"Check for linting-issues in codeunit {codeunitname}.")
        src_folder = os.path.join(codeunit_folder, codeunitname)
        tests_folder = src_folder+"Tests"
        # The codeunit gets linted in an isolated folder which only contains this codeunit. This is required because otherwise sibling-codeunit-source-folders of the repository would shadow the installed dependency-packages of the same name during pylint's import-resolution (pylint adds the repository-folder to sys.path due to the package-nesting), which would result in false-positive import-errors. In the isolated folder the declared (and installed) dependency-codeunits are resolved instead.
        ignored_subfolders = ["Other", "__pycache__", "*.egg-info", "build", "dist", "venv", ".venv", ".pytest_cache", ".git"]
        with tempfile.TemporaryDirectory(dir=GeneralUtilities.get_temp_folder()) as isolation_folder:
            isolated_codeunit_folder = os.path.join(isolation_folder, codeunitname)
            GeneralUtilities.copy_content_of_folder(codeunit_folder, isolated_codeunit_folder, ignored_glob_patterms=ignored_subfolders)
            pylint_configuration_file = os.path.join(repository_folder, ".pylintrc")
            if os.path.isfile(pylint_configuration_file):
                GeneralUtilities.safe_copy(pylint_configuration_file, os.path.join(isolation_folder, ".pylintrc"))
            # TODO check if there are errors in sarif-file
            for file in GeneralUtilities.get_all_files_of_folder(src_folder)+GeneralUtilities.get_all_files_of_folder(tests_folder):
                relative_file_path_in_repository = os.path.relpath(file, repository_folder)
                if file.endswith(".py") and os.path.getsize(file) > 0 and not self._protected_sc.file_is_git_ignored(relative_file_path_in_repository, repository_folder):
                    relative_file_path_in_codeunit = os.path.relpath(file, codeunit_folder)
                    self._protected_sc.log.log(f"Check for linting-issues in {relative_file_path_in_codeunit}.")
                    isolated_file = os.path.join(isolated_codeunit_folder, relative_file_path_in_codeunit)
                    linting_result = self._protected_sc.python_file_has_errors(isolated_file, isolation_folder, display_file=file)
                    if (linting_result[0]):
                        errors_found = True
                        for error in linting_result[1]:
                            self._protected_sc.log.log(error, LogLevel.Warning)
        if errors_found:
            raise ValueError("Linting-issues occurred.")
        else:
            self._protected_sc.log.log("No linting-issues found.")

    @GeneralUtilities.check_arguments
    def do_common_tasks(self,current_codeunit_version:str )-> None:
        self.do_common_tasks_base(current_codeunit_version)
        codeunitname =self.get_codeunit_name()
        codeunit_version = self.tfcps_Tools_General.get_version_of_project(self.get_repository_folder()) 
        self._protected_sc.replace_version_in_ini_file(GeneralUtilities.resolve_relative_path("./pyproject.toml", self.get_codeunit_folder()), codeunit_version)
        self._protected_sc.replace_version_in_python_file(GeneralUtilities.resolve_relative_path(f"./{codeunitname}/{codeunitname}Core.py", self.get_codeunit_folder()), codeunit_version)

    @GeneralUtilities.check_arguments
    def generate_reference(self) -> None:
        self.generate_reference_using_docfx()

    @GeneralUtilities.check_arguments
    def run_testcases(self) -> None:
        codeunitname: str =self.get_codeunit_name()
        repository_folder: str = self.get_repository_folder()
        codeunit_folder = os.path.join(repository_folder, codeunitname)
        self._protected_sc.run_program("coverage", f"run -m pytest -s ./{codeunitname}Tests", codeunit_folder)
        self._protected_sc.run_program("coverage", "xml", codeunit_folder)
        coveragefolder = os.path.join(repository_folder, codeunitname, "Other/Artifacts/TestCoverage")
        GeneralUtilities.ensure_directory_exists(coveragefolder)
        coveragefile = os.path.join(coveragefolder, "TestCoverage.xml")
        GeneralUtilities.ensure_file_does_not_exist(coveragefile)
        os.rename(os.path.join(repository_folder, codeunitname, "coverage.xml"), coveragefile)
        self.tfcps_Tools_General.merge_packages(coveragefile,codeunitname)
        self.run_testcases_common_post_task(repository_folder, codeunitname, True, self.get_type_environment_type())

    @GeneralUtilities.check_arguments
    def get_dependencies(self)->dict[str,set[str]]:
        return GeneralUtilities.merge_dependency_lists([
            self.get_dependencies_from_pyprojecttoml(),
            self.get_dependencies_from_requirementstxt(),
            self.get_dependencies_from_otherrequirementstxt()
        ])

    @GeneralUtilities.check_arguments
    def get_dependencies_from_pyprojecttoml(self)->list[Dependency]:
        setupcfg_file=os.path.join(self.get_codeunit_folder(),"pyproject.toml")
        lines = GeneralUtilities.read_lines_from_file(setupcfg_file)
        result:list[Dependency]=[]
        is_in_dependency_section=False
        for line in lines:
            if line=="dependencies = [":
                is_in_dependency_section=True
            elif line.startswith("    "):
                if is_in_dependency_section:
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#"):
                        continue
                    if stripped.endswith(","):
                        stripped = stripped[:-1].rstrip()
                    if len(stripped) >= 2 and stripped[0] in ('"', "'") and stripped[-1] == stripped[0]:
                        stripped = stripped[1:-1]
                    match = re.match(r"^([A-Za-z0-9_\-\.]+)\s*([<>=!~]+)?\s*(.*)?$", stripped)
                    if match:
                        dep_name = match.group(1)
                        dep_operator = match.group(2) or None#pylint:disable=unused-variable
                        dep_version = match.group(3) or None
                        dep=Dependency(dep_name,dep_version)
                        result.append(dep)
                    else:
                        raise ValueError(f"Unparsable dependency-definition-line: \"{line}\"")
            else:
                is_in_dependency_section=False
        return result

    @GeneralUtilities.check_arguments
    def get_dependencies_from_requirementstxt(self)->list[Dependency]:
        return self.get_dependencies_from_requirementsfile(os.path.join(self.get_codeunit_folder(),"requirements.txt")) 

    @GeneralUtilities.check_arguments
    def get_dependencies_from_otherrequirementstxt(self)->list[Dependency]:
        rfile=os.path.join(self.get_codeunit_folder(),"Other","requirements.txt")
        if os.path.isfile(rfile):
            return self.get_dependencies_from_requirementsfile(rfile) 
        else:
            return []

    @GeneralUtilities.check_arguments
    def get_dependencies_from_requirementsfile(self,file:str)->list[Dependency]:
        lines = GeneralUtilities.read_lines_from_file(file)
        result:list[Dependency]=[]
        for line in lines:
            match = re.match(r"^([A-Za-z0-9_\-]+)\s*([<>=!~]+)?\s*(.*)?$", line)
            if match:
                dep_name = match.group(1)
                dep_operator = match.group(2) or None#pylint:disable=unused-variable
                dep_version = match.group(3) or None
                dep=Dependency(dep_name,dep_version)
                result.append(dep)

        return result
    
    @GeneralUtilities.check_arguments
    def get_available_versions(self,dependencyname:str)->list[str]:
        result=self._protected_sc.run_program("pip3",f"index versions {dependencyname}")
        available_versions_line:str=[line for line in GeneralUtilities.string_to_lines(result[1]) if line.startswith("Available versions: ")][0]
        available_versions=[version_str.strip() for version_str in available_versions_line[len("Available versions: "):].split(",")]
        result=[]
        for v in available_versions:
            if re.match(r"^(\d+)\.(\d+)\.(\d+)$", v) is not None:
                result.append(v)
            elif re.match(r"^(\d+)\.(\d+)$", v) is not None:
                result.append(v+".0")
            elif re.match(r"^(\d+)$", v) is not None:
                result.append(v+".0.0")
        return result
    
    @GeneralUtilities.check_arguments
    def set_dependency_version(self,name:str,new_version:str)->None:
        self.__set_dependency_version_in_pyprojecttoml(name,new_version)
        self.__set_dependency_version_in_requirementstxt(name,new_version)
        self.__set_dependency_version_in_otherrequirementstxt(name,new_version)

    @GeneralUtilities.check_arguments
    def __set_dependency_version_in_pyprojecttoml(self,name:str,new_version:str)->None:
        setupcfg_file=os.path.join(self.get_codeunit_folder(),"pyproject.toml")
        lines=GeneralUtilities.read_lines_from_file(setupcfg_file)
        new_lines:list[str]=[]
        for line in lines:
            match = re.match(r'^(\s*)"(' + re.escape(name) + r')\s*([<>=!~]+)?\s*([^"]*?)"(,?)\s*$', line)
            if match:
                whitespace = match.group(1)
                dep_operator = match.group(3) or ">="
                comma = match.group(5)
                new_line = f'{whitespace}"{name}{dep_operator}{new_version}"{comma}'
                new_lines.append(new_line)
            else:
                new_lines.append(line)
        GeneralUtilities.write_lines_to_file(setupcfg_file,new_lines)

    @GeneralUtilities.check_arguments
    def __set_dependency_version_in_requirementstxt(self,name:str,new_version:str)->None:
        self.__set_dependency_version_in_requirements(name,new_version,os.path.join(self.get_codeunit_folder(),"requirements.txt")) 

    @GeneralUtilities.check_arguments
    def __set_dependency_version_in_otherrequirementstxt(self,name:str,new_version:str)->None:
        rfile=os.path.join(self.get_codeunit_folder(),"Other","requirements.txt")
        if os.path.isfile(rfile):
            self.__set_dependency_version_in_requirements(name,new_version,rfile) 

    @GeneralUtilities.check_arguments
    def __set_dependency_version_in_requirements(self,name:str,new_version:str,requirementsfile:str)->None:
        lines=GeneralUtilities.read_lines_from_file(requirementsfile)
        new_lines:list[str]=[]
        for line in lines:
            match = re.match("^("+re.escape(name)+")\\s*([<>=!~]+)?\\s*(.*)?$", line)
            if match:
                dep_name = match.group(1)#pylint:disable=unused-variable
                dep_operator = match.group(2) or None
                dep_version = match.group(3) or None#pylint:disable=unused-variable
                new_line=name
                if dep_operator is None:
                    dep_operator=">="
                new_line=new_line+dep_operator+new_version
                new_lines.append(new_line)
            else:
                new_lines.append(line)
        GeneralUtilities.write_lines_to_file(requirementsfile,new_lines)
    
class TFCPS_CodeUnitSpecific_Python_CLI:

    @staticmethod
    @GeneralUtilities.check_arguments
    def parse(file:str)->TFCPS_CodeUnitSpecific_Python_Functions:
        parser=TFCPS_CodeUnitSpecific_Base_CLI.get_base_parser()
        #add custom parameter if desired
        args=parser.parse_args()
        result:TFCPS_CodeUnitSpecific_Python_Functions=TFCPS_CodeUnitSpecific_Python_Functions(file,LogLevel(int(args.verbosity)),args.targetenvironmenttype,not args.nocache,args.ispremerge)
        return result
