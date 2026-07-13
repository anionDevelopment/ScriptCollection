from datetime import timedelta, datetime
from functools import cmp_to_key
import ast
import json
import binascii
import filecmp
import hashlib
import multiprocessing
import time
from io import BytesIO
import itertools
import copy
import zipfile
import math
import base64
import os
from html.parser import HTMLParser
from queue import Queue, Empty
from concurrent.futures import ThreadPoolExecutor
import xml.etree.ElementTree as ET
from pathlib import Path
from subprocess import Popen
import re
import shutil
from typing import IO
import fnmatch
import uuid
import io
import requests
import ntplib
import yaml
import qrcode
import pycdlib
import send2trash
from pypdf import PdfReader, PdfWriter
from .GeneralUtilities import GeneralUtilities,Platform
from .ProgramRunnerBase import ProgramRunnerBase
from .ProgramRunnerPopen import ProgramRunnerPopen
from .SCLog import SCLog, LogLevel

version = "4.3.28"
__version__ = version

class VSCodeWorkspaceShellTask:
    label:str = None
    description:str = None  #nullable
    work_dir:str = None  #nullable
    command:str = None
    aliases:list[str] = None
    allow_custom_arguments:bool = None

    def __init__(self,label:str,description:str,work_dir:str,command:str,aliases:list[str],allow_custom_arguments:bool):
        GeneralUtilities.assert_not_null(label,"label")
        self.label=label
        self.description=description
        self.work_dir=work_dir
        GeneralUtilities.assert_not_null(command,"command")
        self.command=command
        GeneralUtilities.assert_not_null(aliases,"aliases")
        self.aliases=aliases
        GeneralUtilities.assert_not_null(allow_custom_arguments,"allow_custom_arguments")
        self.allow_custom_arguments=allow_custom_arguments


    def serialize_for_vscode(self)->str:
        aliases=",".join([f"\"{GeneralUtilities.escape_json_string_value(alias)}\"" for alias in self.aliases])

        cwd:str=None
        if self.work_dir is None:
            cwd=GeneralUtilities.empty_string
        else:
            cwd=f"\"cwd\": \"{GeneralUtilities.escape_json_string_value(self.work_dir)}\""

        desc:str=None
        if self.description is None:
            desc=GeneralUtilities.empty_string
        else:
            desc=f"\"description\": \"{GeneralUtilities.escape_json_string_value(self.description)}\","

        result=f"""        {{
                "label": "{GeneralUtilities.escape_json_string_value(self.label)}",
                "command": "{GeneralUtilities.escape_json_string_value(self.command)}",
                "type": "shell",
                "options": {{
                    {cwd}
                }},
                "aliases": [
                    {aliases}
                ],
                {desc}
                "allowcustomarguments": {str(self.allow_custom_arguments).lower()}
            }}"""
        return result

class VSCodeWorkspaceMariaDBConnection:
    name:str = None
    previewLimit:int=50
    server:str = None
    port:int = None
    database:str = None
    username:str = None
    password:str = None
    
    def __init__(self,name:str,server,port,database,username,password):
        GeneralUtilities.assert_not_null(name,"name")
        self.name=name
        GeneralUtilities.assert_not_null(server,"server")
        self.server=server
        GeneralUtilities.assert_not_null(port,"port")
        self.port=port
        GeneralUtilities.assert_not_null(database,"database")
        self.database=database
        GeneralUtilities.assert_not_null(username,"username")
        self.username=username
        GeneralUtilities.assert_not_null(password,"password")
        self.password=password

    def serialize_for_vscode(self)->str:
        result=f"""        {{
                        "name": "{GeneralUtilities.escape_json_string_value(self.name)}",
                        "mysqlOptions": {{
                            "authProtocol": "default",
                            "enableSsl": "Disabled"
                        }},
                        "previewLimit": {self.previewLimit},
                        "server": "{GeneralUtilities.escape_json_string_value(self.server)}",
                        "port": {self.port},
                        "driver": "MySQL",
                        "database": "{GeneralUtilities.escape_json_string_value(self.database)}",
                        "username": "{GeneralUtilities.escape_json_string_value(self.username)}",
                        "password": "{GeneralUtilities.escape_json_string_value(self.password)}"
                    }}
"""
        return result


class VSCodeWorkspaceMongoDBConnection:
    name:str = None
    connection_string:str = None

    def __init__(self,name:str,connection_string:str):
        GeneralUtilities.assert_not_null(name,"name")
        self.name=name
        GeneralUtilities.assert_not_null(connection_string,"connection_string")
        self.connection_string=connection_string

    def serialize_for_vscode(self)->str:
        result=f"""                    {{
                        "name": "{GeneralUtilities.escape_json_string_value(self.name)}",
                        "connectionString": "{GeneralUtilities.escape_json_string_value(self.connection_string)}"
                    }}
"""
        return result
    
class ProjectServerIssueSummary:
    number:int = None
    title:str = None
    state:str = None  # "open" or "closed"
    tags:list[str] = None  # the labels of the issue

    def __init__(self,number:int,title:str,state:str,tags:list[str]):
        self.number=number
        self.title=title
        self.state=state
        self.tags=tags


class ProjectServerIssueComment:
    author:str = None  #nullable
    body:str = None
    created_at:str = None  #nullable

    def __init__(self,author:str,body:str,created_at:str):
        self.author=author
        self.body=body
        self.created_at=created_at


class ProjectServerIssue:
    summary:ProjectServerIssueSummary = None
    description:str = None  #nullable (the body of the issue)
    comments:list[ProjectServerIssueComment] = None

    def __init__(self,summary:ProjectServerIssueSummary,description:str,comments:list[ProjectServerIssueComment]):
        self.summary=summary
        self.description=description
        self.comments=comments


class ScriptCollectionCore:

    # The purpose of this property is to use it when testing your code which uses scriptcollection for external program-calls.
    # Do not change this value for productive environments.
    mock_program_calls: bool = False#TODO remove this variable. When someone want to mock program-calls then the ProgramRunnerMock can be used instead
    # The purpose of this property is to use it when testing your code which uses scriptcollection for external program-calls.
    execute_program_really_if_no_mock_call_is_defined: bool = False
    __mocked_program_calls: list = None
    program_runner: ProgramRunnerBase = None
    call_program_runner_directly: bool = None
    log: SCLog = None
    # Magic string which can be used inside the arguments of run_command_in_folder. Every occurrence of it will be replaced by the (resolved) actual_folder.
    run_command_in_folder_actual_folder_placeholder: str = "{actual_folder}"
    # Base-url of the GitHub-REST-API. This is an internal constant on purpose and deliberately not exposed as a parameter of the GitHub-functions.
    __github_api_base_url: str = "https://api.github.com"


    def __init__(self):
        self.program_runner = ProgramRunnerPopen()
        self.call_program_runner_directly = None
        self.__mocked_program_calls = list[ScriptCollectionCore.__MockProgramCall]()
        self.log = SCLog(None, LogLevel.Warning, False)
        # in-memory-cache (first level) for the result of __get_next_version_from_gitversion (which performs an expensive clone) keyed by (repository_folder, commit_id, branch_name); a persistent second-level cache-file below the repository is used additionally. the result only depends on the committed state and the branch-name, so this key invalidates itself as soon as a new commit is created or another branch/commit is checked out
        self.__next_gitversion_cache = dict[tuple[str, str, str], str]()

    @staticmethod
    @GeneralUtilities.check_arguments
    def get_scriptcollection_version() -> str:
        return __version__

    @GeneralUtilities.check_arguments
    def get_scriptcollection_configuration_folder(self)->str:
        return GeneralUtilities.get_scriptcollection_configuration_folder()

    def get_global_cache_folder(self)->str:
        result = os.path.join(GeneralUtilities.get_scriptcollection_configuration_folder(), "GlobalCache")
        result=GeneralUtilities.normalize_path(result)
        GeneralUtilities.ensure_directory_exists(result)
        return result

    def __get_docker_registry_credentials_file(self)->str:
        result=os.path.join(self.get_global_cache_folder(),"RegistryCredentials.csv")
        if not os.path.isfile(result):
            GeneralUtilities.ensure_file_exists(result)
            GeneralUtilities.write_lines_to_file(result,["RegistryName;Username;Password"])
        return result

    def __load_credentials_if_required_and_available(self,registry_url:str,registry_username:str,registry_password:str)->tuple[str,str]:
        if registry_url.startswith("https://"):
            registry_url=registry_url[len("https://"):]
        if registry_password is None:
            credential_file=self.__get_docker_registry_credentials_file()
            lines=GeneralUtilities.read_nonempty_lines_from_file(credential_file)[1:]
            for line in lines:
                splitted=line.split(";")
                registry=splitted[0]
                username=splitted[1]
                password=splitted[2]
                if registry_url==registry and (registry_username is None or username==registry_username):
                    registry_username=username
                    registry_password=password
                    break
        else:
            GeneralUtilities.assert_not_null(registry_username)
        return (registry_username,registry_password)

    def __get_docker_registry_credentials(self)->list[tuple[str,str,str]]:
        result=[]
        credential_file=self.__get_docker_registry_credentials_file()
        if os.path.isfile(credential_file):
            lines=GeneralUtilities.read_nonempty_lines_from_file(credential_file)[1:]
            for line in lines:
                splitted=line.split(";")
                registry=splitted[0]
                username=splitted[1]
                password=splitted[2]
                result.append((registry,username,password))
        return result

    def registry_contains_image(self,registry_url:str,image:str,registry_username:str,registry_password:str)->bool:
        """This function assumes that the registry is a custom deployed docker-registry (see https://hub.docker.com/_/registry )"""
        try:
            if "/" in image:
                image=image.rsplit("/", 1)[-1]
            registry_username,registry_password=self.__load_credentials_if_required_and_available(registry_url,registry_username,registry_password)
            catalog_url = f"{registry_url}/v2/_catalog"
            response = requests.get(catalog_url, auth=(registry_username, registry_password),timeout=20)
            response.raise_for_status() # check if statuscode = 200
            data = response.json()
            # expected: {"repositories": ["nginx", "myapp"]}
            images = data.get("repositories", [])
            if not (image in images):
                return False
        
            if self.get_tags_of_images_from_registry(registry_url,image,registry_username,registry_password)<1:
                return False
            
            return True
        except Exception:
            return False
    
    def docker_platform_to_slug(self,platform_value: Platform) -> str:
        if platform_value == Platform.Linux_AMD64:
            return "linux-amd64"
        elif platform_value == Platform.Linux_ARM64:
            return "linux-arm64"
        raise ValueError(f"Unsupported platform: {platform_value}")

    @GeneralUtilities.check_arguments
    def add_image_to_custom_docker_image_registry(
        self,
        remote_hub: str,
        imagename_on_remote_hub: str,
        own_registry_address: str,
        imagename_on_own_registry: str,
        tag: str,
        registry_username: str,
        registry_password: str,
    ) -> None:
        registry_username, registry_password = self.__load_credentials_if_required_and_available(remote_hub, registry_username, registry_password)
        source_address = f"{remote_hub}/{imagename_on_remote_hub}:{tag}"
        target_address = f"{own_registry_address}/{imagename_on_own_registry}:{tag}"
        self.run_program("docker", f"buildx imagetools create --tag {target_address} {source_address}")#this does pull and push for each platform


    def get_tags_of_images_from_registry(self,registry_base_url:str,image:str,registry_username:str,registry_password:str)->list[str]:
        """registry_base_url must be in the format 'https://myregistry.example.com'
        This function assumes that the registry is a custom deployed docker-registry (see https://hub.docker.com/_/registry )"""
        registry_username,registry_password=self.__load_credentials_if_required_and_available(registry_base_url,registry_username,registry_password)
        if "/" in image:
            image=image.rsplit("/", 1)[-1]
        if not self.registry_contains_image(registry_base_url,image,registry_username,registry_password):
            return []
        tags_url = f"{registry_base_url}/v2/{image}/tags/list"
        response = requests.get(tags_url, auth=(registry_username, registry_password),timeout=20)
        response.raise_for_status() # check if statuscode = 200
        data=response.json()
        # expected: {"name":"myapp","tags":["1.2.22","1.2.21","1.2.20"]}
        tags = data.get("tags", [])
        return tags
    
    def registry_contains_image_with_tag(self,registry_url:str,image:str,tag:str,registry_username:str,registry_password:str)->bool:
        """This function assumes that the registry is a custom deployed docker-registry (see https://hub.docker.com/_/registry )"""
        registry_username,registry_password=self.__load_credentials_if_required_and_available(registry_url,registry_username,registry_password)
        if "/" in image:
            image=image.rsplit("/", 1)[-1]
        tags=self.get_tags_of_images_from_registry(registry_url,image,registry_username,registry_password)
        if tags is None:
            return False
        else:
            result = tag in tags 
            return result
    
    def login_to_defined_docker_registries(self)->None:
        registries=self.__get_docker_registry_credentials()
        if len(registries)==0:
            self.log.log("No docker registry credentials defined. Skipping docker login.",LogLevel.Debug)
        else:
            for registry,username,password in registries:
                arg=f"login {registry} -u {username} -p {password}"
                arg_for_log=f"login {registry} -u {username} -p ***"
                self.run_program("docker",arg,arguments_for_log=arg_for_log,print_live_output=self.log.loglevel==LogLevel.Debug)
        

    @GeneralUtilities.check_arguments
    def get_issues_of_github_repository(self, owner: str, repository: str, github_token: str = None) -> list[ProjectServerIssueSummary]:
        """Retrieves all issues (open and closed) of the given GitHub-repository and returns for each issue its number, title, state and tags.
        Use 'get_github_issue_details' to retrieve the full details (description, comments) of a specific issue.
        'github_token' is optional but recommended: without it only public repositories are accessible and a low unauthenticated rate-limit applies.
        This function only returns the retrieved data; it does not modify anything."""
        headers = self.__get_github_api_headers(github_token)
        result: list[ProjectServerIssueSummary] = []
        issues_url = f"{self.__github_api_base_url}/repos/{owner}/{repository}/issues"
        # 'state=all' returns open and closed issues. GitHub returns pull-requests on this endpoint too; they are filtered out below.
        raw_issues = self.__get_all_github_pages(issues_url, {"state": "all", "per_page": "100"}, headers)
        for raw_issue in raw_issues:
            if "pull_request" in raw_issue:  # this entry is a pull-request, not an issue
                continue
            tags = [label["name"] for label in raw_issue.get("labels", [])]
            result.append(ProjectServerIssueSummary(raw_issue["number"], raw_issue["title"], raw_issue["state"], tags))
        return result

    @GeneralUtilities.check_arguments
    def get_github_issue_details(self, owner: str, repository: str, issue_number: int, github_token: str = None) -> ProjectServerIssue:
        """Retrieves the full details of a single issue of the given GitHub-repository:
        title, description (body), comments, state ('open' or 'closed') and tags (labels).
        'github_token' is optional but recommended: without it only public repositories are accessible and a low unauthenticated rate-limit applies.
        This function only returns the retrieved data; it does not modify anything."""
        headers = self.__get_github_api_headers(github_token)
        issue_url = f"{self.__github_api_base_url}/repos/{owner}/{repository}/issues/{issue_number}"
        response = requests.get(issue_url, headers=headers, timeout=30)
        response.raise_for_status()  # check if statuscode = 200
        raw_issue = response.json()
        tags = [label["name"] for label in raw_issue.get("labels", [])]
        summary = ProjectServerIssueSummary(raw_issue["number"], raw_issue["title"], raw_issue["state"], tags)
        comments: list[ProjectServerIssueComment] = []
        if raw_issue.get("comments", 0) > 0:
            raw_comments = self.__get_all_github_pages(raw_issue["comments_url"], {"per_page": "100"}, headers)
            for raw_comment in raw_comments:
                author = raw_comment["user"]["login"] if raw_comment.get("user") is not None else None
                comments.append(ProjectServerIssueComment(author, raw_comment.get("body"), raw_comment.get("created_at")))
        return ProjectServerIssue(summary, raw_issue.get("body"), comments)

    @GeneralUtilities.check_arguments
    def __get_github_api_headers(self, github_token: str) -> dict:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if GeneralUtilities.string_has_content(github_token):
            headers["Authorization"] = f"Bearer {github_token}"
        return headers

    @GeneralUtilities.check_arguments
    def __get_all_github_pages(self, url: str, query_parameters: dict, headers: dict) -> list:
        """Requests all pages of a paginated GitHub-API-endpoint (following the 'Link'-header) and returns the concatenated result-items."""
        result: list = []
        next_url = url
        next_parameters = query_parameters
        while next_url is not None:
            response = requests.get(next_url, params=next_parameters, headers=headers, timeout=30)
            response.raise_for_status()  # check if statuscode = 200
            result.extend(response.json())
            # follow the pagination using the 'Link'-header ( https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api ).
            next_url = None
            next_parameters = None  # the 'next'-url from the Link-header already contains all required query-parameters
            link_header = response.headers.get("Link")
            if link_header is not None:
                for link in link_header.split(","):
                    parts = link.split(";")
                    if len(parts) >= 2 and 'rel="next"' in parts[1]:
                        next_url = parts[0].strip().lstrip("<").rstrip(">")
        return result

    @GeneralUtilities.check_arguments
    def python_file_has_errors(self, file: str, working_directory: str, treat_warnings_as_errors: bool = True, display_file: str = None) -> tuple[bool, list[str]]:
        errors = list()
        if display_file is None:
            display_file = file
        filename = os.path.relpath(file, working_directory)
        if treat_warnings_as_errors:
            errorsonly_argument = GeneralUtilities.empty_string
        else:
            errorsonly_argument = " --errors-only"
        (exit_code, stdout, stderr, _) = self.run_program("pylint", filename + errorsonly_argument, working_directory, throw_exception_if_exitcode_is_not_zero=False)
        if (exit_code != 0):
            errors.append(f"Linting-issues of {display_file}:")
            errors.append(f"Pylint-exitcode: {exit_code}")
            for line in GeneralUtilities.string_to_lines(stdout): 
                errors.append(line)
            for line in GeneralUtilities.string_to_lines(stderr):
                errors.append(line)
            return (True, errors)

        return (False, errors)

    @GeneralUtilities.check_arguments
    def replace_version_in_dockerfile_file(self, dockerfile: str, new_version_value: str) -> None:
        GeneralUtilities.write_text_to_file(dockerfile, re.sub("ARG Version=\"\\d+\\.\\d+\\.\\d+\"", f"ARG Version=\"{new_version_value}\"", GeneralUtilities.read_text_from_file(dockerfile)))

    @GeneralUtilities.check_arguments
    def replace_version_in_python_file(self, file: str, new_version_value: str):
        GeneralUtilities.write_text_to_file(file, re.sub("version = \"\\d+\\.\\d+\\.\\d+\"", f"version = \"{new_version_value}\"", GeneralUtilities.read_text_from_file(file)))

    @GeneralUtilities.check_arguments
    def replace_version_in_ini_file(self, file: str, new_version_value: str):
        GeneralUtilities.write_text_to_file(file, re.sub("version = \\\"?\\d+\\.\\d+\\.\\d+\\\"?", f"version = \"{new_version_value}\"", GeneralUtilities.read_text_from_file(file)))

    @GeneralUtilities.check_arguments
    def replace_version_in_nuspec_file(self, nuspec_file: str, new_version: str) -> None:
        # TODO use XSLT instead
        versionregex = "\\d+\\.\\d+\\.\\d+"
        versiononlyregex = f"^{versionregex}$"
        pattern = re.compile(versiononlyregex)
        if pattern.match(new_version):
            GeneralUtilities.write_text_to_file(nuspec_file, re.sub(f"<version>{versionregex}<\\/version>", f"<version>{new_version}</version>", GeneralUtilities.read_text_from_file(nuspec_file)))
        else:
            raise ValueError(f"Version '{new_version}' does not match version-regex '{versiononlyregex}'")

    @GeneralUtilities.check_arguments
    def replace_version_in_csproj_file(self, csproj_file: str, current_version: str):
        versionregex = "\\d+\\.\\d+\\.\\d+"
        versiononlyregex = f"^{versionregex}$"
        pattern = re.compile(versiononlyregex)
        if pattern.match(current_version):
            for tag in ["Version", "AssemblyVersion", "FileVersion"]:
                GeneralUtilities.write_text_to_file(csproj_file, re.sub(f"<{tag}>{versionregex}(.\\d+)?<\\/{tag}>", f"<{tag}>{current_version}</{tag}>", GeneralUtilities.read_text_from_file(csproj_file)))
        else:
            raise ValueError(f"Version '{current_version}' does not match version-regex '{versiononlyregex}'")

    @GeneralUtilities.check_arguments
    def push_nuget_build_artifact(self, nupkg_file: str, registry_address: str, api_key: str = None):
        nupkg_file_name = os.path.basename(nupkg_file)
        nupkg_file_folder = os.path.dirname(nupkg_file)
        argument = f"nuget push {nupkg_file_name} --force-english-output --source {registry_address}"
        if api_key is not None:
            argument = f"{argument} --api-key {api_key}" 
        self.run_program("dotnet", argument, nupkg_file_folder)

    @GeneralUtilities.check_arguments
    def dotnet_build(self, folder: str, projectname: str, configuration: str):
        self.run_program("dotnet", f"clean -c {configuration}", folder)
        self.run_program("dotnet", f"build {projectname}/{projectname}.csproj -c {configuration}", folder)

    @GeneralUtilities.check_arguments
    def find_file_by_extension(self, folder: str, extension_without_dot: str):
        """This function works platform-independent also for non-local-executions if the ScriptCollection commandline-commands are available as global command on the target-system."""
        result = [file for file in self.list_content(folder, True, False, False) if file.endswith(f".{extension_without_dot}")]
        result_length = len(result)
        if result_length == 0:
            raise FileNotFoundError(f"No file available in folder '{folder}' with extension '{extension_without_dot}'.")
        if result_length == 1:
            return result[0]
        else:
            raise ValueError(f"Multiple values available in folder '{folder}' with extension '{extension_without_dot}'.")

    @GeneralUtilities.check_arguments
    def find_last_file_by_extension(self, folder: str, extension_without_dot: str) -> str:
        files: list[str] = GeneralUtilities.get_direct_files_of_folder(folder)
        possible_results: list[str] = []
        for file in files:
            if file.endswith(f".{extension_without_dot}"):
                possible_results.append(file)
        result_length = len(possible_results)
        if result_length == 0:
            raise FileNotFoundError(f"No file available in folder '{folder}' with extension '{extension_without_dot}'.")
        else:
            return possible_results[-1]

    @GeneralUtilities.check_arguments
    def commit_is_signed_by_key(self, repository_folder: str, revision_identifier: str, key: str) -> bool:
        self.is_git_or_bare_git_repository(repository_folder)
        result = self.run_program("git", f"verify-commit {revision_identifier}", repository_folder, throw_exception_if_exitcode_is_not_zero=False)
        if (result[0] != 0):
            return False
        if (not GeneralUtilities.contains_line(result[1].splitlines(), f"gpg\\:\\ using\\ [A-Za-z0-9]+\\ key\\ [A-Za-z0-9]+{key}")):
            # TODO check whether this works on machines where gpg is installed in another langauge than english
            return False
        if (not GeneralUtilities.contains_line(result[1].splitlines(), "gpg\\:\\ Good\\ signature\\ from")):
            # TODO check whether this works on machines where gpg is installed in another langauge than english
            return False
        return True

    @GeneralUtilities.check_arguments
    def get_parent_commit_ids_of_commit(self, repository_folder: str, commit_id: str) -> str:
        self.is_git_or_bare_git_repository(repository_folder)
        return self.run_program("git", f'log --pretty=%P -n 1 "{commit_id}"', repository_folder, throw_exception_if_exitcode_is_not_zero=True)[1].replace("\r", GeneralUtilities.empty_string).replace("\n", GeneralUtilities.empty_string).split(" ")


    @GeneralUtilities.check_arguments
    def get_commit_ids_between_dates(self, repository_folder: str, since: datetime, until: datetime, ignore_commits_which_are_not_in_history_of_head: bool = True) -> None:
        self.is_git_or_bare_git_repository(repository_folder)
        since_as_string = self.__datetime_to_string_for_git(since)
        until_as_string = self.__datetime_to_string_for_git(until)
        result = filter(lambda line: not GeneralUtilities.string_is_none_or_whitespace(line), self.run_program("git", f'log --since "{since_as_string}" --until "{until_as_string}" --pretty=format:"%H" --no-patch', repository_folder, throw_exception_if_exitcode_is_not_zero=True)[1].split("\n").replace("\r", GeneralUtilities.empty_string))
        if ignore_commits_which_are_not_in_history_of_head:
            result = [commit_id for commit_id in result if self.git_commit_is_ancestor(repository_folder, commit_id)]
        return result

    @GeneralUtilities.check_arguments
    def __datetime_to_string_for_git(self, datetime_object: datetime) -> str:
        return datetime_object.strftime('%Y-%m-%d %H:%M:%S')

    @GeneralUtilities.check_arguments
    def git_commit_is_ancestor(self, repository_folder: str,  ancestor: str, descendant: str = "HEAD") -> bool:
        self.is_git_or_bare_git_repository(repository_folder)
        result = self.run_program_argsasarray("git", ["merge-base", "--is-ancestor", ancestor, descendant], repository_folder, throw_exception_if_exitcode_is_not_zero=False)
        exit_code = result[0]
        if exit_code == 0:
            return True
        elif exit_code == 1:
            return False
        else:
            raise ValueError(f'Can not calculate if {ancestor} is an ancestor of {descendant} in repository {repository_folder}. Outout of "{repository_folder}> git merge-base --is-ancestor {ancestor} {descendant}": Exitcode: {exit_code}; StdOut: {result[1]}; StdErr: {result[2]}.')

    @GeneralUtilities.check_arguments
    def __git_changes_helper(self, repository_folder: str, arguments_as_array: list[str]) -> bool:
        self.assert_is_git_repository(repository_folder)
        lines = GeneralUtilities.string_to_lines(self.run_program_argsasarray("git", arguments_as_array, repository_folder, throw_exception_if_exitcode_is_not_zero=True)[1], False)
        for line in lines:
            if GeneralUtilities.string_has_content(line):
                return True
        return False

    @GeneralUtilities.check_arguments
    def git_repository_has_new_untracked_files(self, repository_folder: str):
        self.assert_is_git_repository(repository_folder)
        return self.__git_changes_helper(repository_folder, ["ls-files", "--exclude-standard", "--others"])

    @GeneralUtilities.check_arguments
    def git_repository_has_unstaged_changes_of_tracked_files(self, repository_folder: str):
        self.assert_is_git_repository(repository_folder)
        return self.__git_changes_helper(repository_folder, ["--no-pager", "diff"])

    @GeneralUtilities.check_arguments
    def git_repository_has_staged_changes(self, repository_folder: str):
        self.assert_is_git_repository(repository_folder)
        return self.__git_changes_helper(repository_folder, ["--no-pager", "diff", "--cached"])

    @GeneralUtilities.check_arguments
    def git_repository_has_uncommitted_changes(self, repository_folder: str) -> bool:
        self.assert_is_git_repository(repository_folder)
        if (self.git_repository_has_unstaged_changes(repository_folder)):
            return True
        if (self.git_repository_has_staged_changes(repository_folder)):
            return True
        return False

    @GeneralUtilities.check_arguments
    def git_repository_has_unstaged_changes(self, repository_folder: str) -> bool:
        self.assert_is_git_repository(repository_folder)
        if (self.git_repository_has_unstaged_changes_of_tracked_files(repository_folder)):
            return True
        if (self.git_repository_has_new_untracked_files(repository_folder)):
            return True
        return False

    @GeneralUtilities.check_arguments
    def git_get_commit_id(self, repository_folder: str, rev: str = "HEAD") -> str:
        self.is_git_or_bare_git_repository(repository_folder)
        # Append "^{commit}" so that annotated tags are dereferenced to the commit they point to instead of returning the SHA of the tag-object itself.
        result: tuple[int, str, str, int] = self.run_program_argsasarray("git", ["rev-parse", "--verify", f"{rev}^{{commit}}"], repository_folder, throw_exception_if_exitcode_is_not_zero=True)
        return result[1].replace('\n', '')

    @GeneralUtilities.check_arguments
    def git_get_commit_date(self, repository_folder: str, rev: str = "HEAD") -> datetime:
        self.is_git_or_bare_git_repository(repository_folder)
        result: tuple[int, str, str, int] = self.run_program_argsasarray("git", ["log","-1","--format=%ci", rev], repository_folder, throw_exception_if_exitcode_is_not_zero=True)
        date_as_string = result[1].replace('\n', '')
        result = datetime.strptime(date_as_string, '%Y-%m-%d %H:%M:%S %z')
        return result

    @GeneralUtilities.check_arguments
    def git_fetch_with_retry(self, folder: str, remotename: str = "--all", amount_of_attempts: int = 5) -> None:
        GeneralUtilities.retry_action(lambda: self.git_fetch(folder, remotename), amount_of_attempts)

    @GeneralUtilities.check_arguments
    def git_fetch(self, folder: str, remotename: str = "--all") -> None:
        self.assert_is_git_repository(folder)
        self.run_program_argsasarray("git", ["fetch", remotename, "--tags", "--prune"], folder, throw_exception_if_exitcode_is_not_zero=True)

    @GeneralUtilities.check_arguments
    def git_fetch_in_bare_repository(self, folder: str, remotename, localbranch: str, remotebranch: str) -> None:
        self.assert_is_git_repository(folder)
        self.run_program_argsasarray("git", ["fetch", remotename, f"{remotebranch}:{localbranch}"], folder, throw_exception_if_exitcode_is_not_zero=True)

    def branch_exists(self, folder: str, branchname: str) -> bool:
        self.assert_is_git_repository(folder)
        result = self.run_program_argsasarray("git", ["rev-parse", "--verify", branchname], folder, throw_exception_if_exitcode_is_not_zero=False)
        return result[0] == 0

    @GeneralUtilities.check_arguments
    def git_remove_branch(self, folder: str, branchname: str) -> None:
        self.assert_is_git_repository(folder)
        self.run_program("git", f"branch -D {branchname}", folder, throw_exception_if_exitcode_is_not_zero=True)

    @GeneralUtilities.check_arguments
    def git_remove_remote_branch(self, folder: str, remotename: str, branchname: str) -> None:
        self.assert_is_git_repository(folder)
        self.run_program_argsasarray("git", ["push", remotename, "--delete", branchname], folder, throw_exception_if_exitcode_is_not_zero=True)

    @GeneralUtilities.check_arguments
    def git_create_branch(self, folder: str, new_branch_name: str, base: str = "HEAD", checkout: bool = True) -> None:
        self.assert_is_git_repository(folder)
        if checkout:
            args = ["checkout", "-b", new_branch_name, base]
        else:
            args = ["branch", new_branch_name, base]
        self.run_program_argsasarray("git", args, folder, throw_exception_if_exitcode_is_not_zero=True)

    @GeneralUtilities.check_arguments
    def git_push_with_retry(self, folder: str, remotename: str, localbranchname: str, remotebranchname: str, forcepush: bool = False, pushalltags: bool = True, verbosity: LogLevel = LogLevel.Quiet, amount_of_attempts: int = 5) -> None:
        GeneralUtilities.retry_action(lambda: self.git_push(folder, remotename, localbranchname, remotebranchname, forcepush, pushalltags, verbosity), amount_of_attempts)

    @GeneralUtilities.check_arguments
    def git_branch_is_pushable(self, folder: str, remote: str, localbranchname: str, remotebranchname: str) -> bool:
        """Fetches remote and returns whether pushing localbranchname to remotebranchname would advance (fast-forward) the remote-branch.
        Returns True if the remote-branch does not exist yet or is strictly behind the local-branch.
        Returns False if the remote-branch already contains the current commit (is equal to the local-branch), is ahead of it or
        diverged from it, in which case a push would do nothing useful and a normal push would even fail with a non-fast-forward-error."""
        self.is_git_or_bare_git_repository(folder)
        self.git_fetch(folder, remote)
        remote_ref = f"{remote}/{remotebranchname}"
        if not self.branch_exists(folder, remote_ref):
            return True
        remote_is_ancestor_of_local = self.git_commit_is_ancestor(folder, remote_ref, localbranchname)
        local_is_ancestor_of_remote = self.git_commit_is_ancestor(folder, localbranchname, remote_ref)
        return remote_is_ancestor_of_local and not local_is_ancestor_of_remote

    @GeneralUtilities.check_arguments
    def git_push(self, folder: str, remotename: str, localbranchname: str, remotebranchname: str, forcepush: bool = False, pushalltags: bool = True, verbosity: LogLevel = LogLevel.Quiet,resurse_submodules:bool=False) -> None:
        self.is_git_or_bare_git_repository(folder)
        if not forcepush and not self.is_bare_git_repository(folder):
            # If the remote-branch already contains the current commit or is ahead of the local-branch there is nothing to push and a
            # normal push would fail with a non-fast-forward-error. In that case do nothing. (Skipped for bare-repositories because
            # git_fetch does not support them.)
            if not self.git_branch_is_pushable(folder, remotename, localbranchname, remotebranchname):
                self.log.log(f"Skip pushing '{localbranchname}' to '{remotebranchname}' on '{remotename}' in '{folder}' because the remote-branch is not behind the local-branch.", LogLevel.Debug)
                return
        argument = ["push"]
        if resurse_submodules:
            argument = argument + ["--recurse-submodules=on-demand"]
        argument = argument + [remotename, f"{localbranchname}:{remotebranchname}"]
        if (forcepush):
            argument.append("--force")
        if (pushalltags):
            argument.append("--tags")
        self.run_program_argsasarray("git", argument, folder, throw_exception_if_exitcode_is_not_zero=True, print_errors_as_information=True)

    @GeneralUtilities.check_arguments
    def git_pull_with_retry(self, folder: str, remote: str, localbranchname: str, remotebranchname: str, force: bool = False, amount_of_attempts: int = 5) -> None:
        GeneralUtilities.retry_action(lambda: self.git_pull(folder, remote, localbranchname, remotebranchname), amount_of_attempts)

    @GeneralUtilities.check_arguments
    def git_branch_is_pullable(self, folder: str, remote: str, localbranchname: str, remotebranchname: str) -> bool:
        """Fetches remote and returns whether pulling remotebranchname into localbranchname would advance (fast-forward) the local-branch.
        Returns True if the local-branch is behind the remote-branch (or equal to it).
        Returns False if the local-branch is ahead of the remote-branch (or diverged from it), in which case a pull would do nothing useful and a normal pull would even fail with a non-fast-forward-error."""
        self.is_git_or_bare_git_repository(folder)
        self.git_fetch(folder, remote)
        return self.git_commit_is_ancestor(folder, localbranchname, f"{remote}/{remotebranchname}")

    @GeneralUtilities.check_arguments
    def git_pull(self, folder: str, remote: str, localbranchname: str, remotebranchname: str, force: bool = False) -> None:
        self.is_git_or_bare_git_repository(folder)
        if not force and not self.is_bare_git_repository(folder):
            # If the local-branch is already up-to-date with or ahead of the remote-branch there is nothing to pull and a normal
            # pull would fail with a non-fast-forward-error. In that case do nothing. (Skipped for bare-repositories because
            # those have no working-tree to update and git_fetch does not support them.)
            if not self.git_branch_is_pullable(folder, remote, localbranchname, remotebranchname):
                self.log.log(f"Skip pulling '{remotebranchname}' from '{remote}' into '{localbranchname}' in '{folder}' because the local-branch is not behind the remote-branch.", LogLevel.Debug)
                return
        argument = f"pull {remote} {remotebranchname}:{localbranchname}"
        if force:
            argument = f"{argument} --force"
        self.run_program("git", argument, folder, throw_exception_if_exitcode_is_not_zero=True)

    @GeneralUtilities.check_arguments
    def git_list_remote_branches(self, folder: str, remote: str, fetch: bool) -> list[str]:
        self.is_git_or_bare_git_repository(folder)
        if fetch:
            self.git_fetch(folder, remote)
        run_program_result = self.run_program("git", f"branch -rl {remote}/*", folder, throw_exception_if_exitcode_is_not_zero=True)
        output = GeneralUtilities.string_to_lines(run_program_result[1])
        result = list[str]()
        for item in output:
            striped_item = item.strip()
            if GeneralUtilities.string_has_content(striped_item):
                branch: str = None
                if " " in striped_item:
                    branch = striped_item.split(" ")[0]
                else:
                    branch = striped_item
                branchname = branch[len(remote)+1:]
                if branchname != "HEAD":
                    result.append(branchname)
        return result

    @GeneralUtilities.check_arguments
    def git_clone(self, clone_target_folder: str, remote_repository_path: str, include_submodules: bool = True, mirror: bool = False) -> None:
        if (os.path.isdir(clone_target_folder)):
            raise ValueError(f"Can not clone repository. Target folder '{clone_target_folder}' already exists as folder.")
        else:
            args = ["clone", remote_repository_path, clone_target_folder]
            if include_submodules:
                args.append("--recurse-submodules")
                args.append("--remote-submodules")
            if mirror:
                args.append("--mirror")
            self.run_program_argsasarray("git", args, os.getcwd(), throw_exception_if_exitcode_is_not_zero=True)

    @GeneralUtilities.check_arguments
    def git_get_all_remote_names(self, directory: str) -> list[str]:
        self.is_git_or_bare_git_repository(directory)
        result = GeneralUtilities.string_to_lines(self.run_program_argsasarray("git", ["remote"], directory, throw_exception_if_exitcode_is_not_zero=True)[1], False)
        return result

    @GeneralUtilities.check_arguments
    def git_get_remote_url(self, directory: str, remote_name: str) -> str:
        self.is_git_or_bare_git_repository(directory)
        result = GeneralUtilities.string_to_lines(self.run_program_argsasarray("git", ["remote", "get-url", remote_name], directory, throw_exception_if_exitcode_is_not_zero=True)[1], False)
        return result[0].replace('\n', '')

    @GeneralUtilities.check_arguments
    def repository_has_remote_with_specific_name(self, directory: str, remote_name: str) -> bool:
        self.is_git_or_bare_git_repository(directory)
        return remote_name in self.git_get_all_remote_names(directory)

    @GeneralUtilities.check_arguments
    def git_add_or_set_remote_address(self, directory: str, remote_name: str, remote_address: str) -> None:
        self.assert_is_git_repository(directory)
        if (self.repository_has_remote_with_specific_name(directory, remote_name)):
            self.run_program_argsasarray("git", ['remote', 'set-url', 'remote_name', remote_address], directory, throw_exception_if_exitcode_is_not_zero=True)
        else:
            self.run_program_argsasarray("git", ['remote', 'add', remote_name, remote_address], directory, throw_exception_if_exitcode_is_not_zero=True)

    @GeneralUtilities.check_arguments
    def git_stage_all_changes(self, directory: str) -> None:
        self.assert_is_git_repository(directory)
        self.run_program_argsasarray("git", ["add", "-A"], directory, throw_exception_if_exitcode_is_not_zero=True)

    @GeneralUtilities.check_arguments
    def git_unstage_all_changes(self, directory: str) -> None:
        self.assert_is_git_repository(directory)
        self.run_program_argsasarray("git", ["reset"], directory, throw_exception_if_exitcode_is_not_zero=True)
        # TODO ensure this will also be done for submodules

    @GeneralUtilities.check_arguments
    def git_stage_file(self, directory: str, file: str) -> None:
        self.assert_is_git_repository(directory)
        self.run_program_argsasarray("git", ['stage', file], directory, throw_exception_if_exitcode_is_not_zero=True)

    @GeneralUtilities.check_arguments
    def git_unstage_file(self, directory: str, file: str) -> None:
        self.assert_is_git_repository(directory)
        self.run_program_argsasarray("git", ['reset', file], directory, throw_exception_if_exitcode_is_not_zero=True)

    @GeneralUtilities.check_arguments
    def git_discard_unstaged_changes_of_file(self, directory: str, file: str) -> None:
        """Caution: This method works really only for 'changed' files yet. So this method does not work properly for new or renamed files."""
        self.assert_is_git_repository(directory)
        self.run_program_argsasarray("git", ['checkout', file], directory, throw_exception_if_exitcode_is_not_zero=True)

    @GeneralUtilities.check_arguments
    def git_discard_all_unstaged_changes(self, directory: str) -> None:
        """Caution: This function executes 'git clean -df'. This can delete files which maybe should not be deleted. Be aware of that."""
        self.assert_is_git_repository(directory)
        self.run_program_argsasarray("git", ['clean', '-df'], directory, throw_exception_if_exitcode_is_not_zero=True)
        self.run_program_argsasarray("git", ['checkout', '.'], directory, throw_exception_if_exitcode_is_not_zero=True)
        # TODO ensure this will also be done for submodules

    @GeneralUtilities.check_arguments
    def git_commit(self, directory: str, message: str = "Saved changes.", author_name: str = None, author_email: str = None, stage_all_changes: bool = True, no_changes_behavior: int = 0,commit_message_body:str=None) -> str:
        """no_changes_behavior=0 => No commit; no_changes_behavior=1 => Commit anyway; no_changes_behavior=2 => Exception"""
        self.assert_is_git_repository(directory)
        author_name = GeneralUtilities.str_none_safe(author_name).strip()
        author_email = GeneralUtilities.str_none_safe(author_email).strip()
        argument = ['commit', '--quiet', '--allow-empty', '--message', message]
        if commit_message_body is not None:
            argument.extend(['--message', commit_message_body])
        if (GeneralUtilities.string_has_content(author_name)):
            argument.append(f'--author="{author_name} <{author_email}>"')
        git_repository_has_uncommitted_changes = self.git_repository_has_uncommitted_changes(directory)

        if git_repository_has_uncommitted_changes:
            do_commit = True
            if stage_all_changes:
                self.git_stage_all_changes(directory)
        else:
            if no_changes_behavior == 0:
                self.log.log(f"Commit '{message}' will not be done because there are no changes to commit in repository '{directory}'", LogLevel.Debug)
                do_commit = False
            elif no_changes_behavior == 1:
                self.log.log(f"There are no changes to commit in repository '{directory}'. Commit '{message}' will be done anyway.", LogLevel.Debug)
                do_commit = True
            elif no_changes_behavior == 2:
                raise RuntimeError(f"There are no changes to commit in repository '{directory}'. Commit '{message}' will not be done.")
            else:
                raise ValueError(f"Unknown value for no_changes_behavior: {GeneralUtilities.str_none_safe(no_changes_behavior)}")

        if do_commit:
            self.log.log(f"Commit changes in '{directory}'", LogLevel.Information)
            self.run_program_argsasarray("git", argument, directory, throw_exception_if_exitcode_is_not_zero=True)

        return self.git_get_commit_id(directory)
    
    def search_repository_folder(self,some_file_in_repository:str)->str:
        current_path:str=os.path.dirname(some_file_in_repository)
        enabled:bool=True
        while enabled:
            try:
                current_path=GeneralUtilities.resolve_relative_path("..",current_path)
                if self.is_git_repository(current_path):
                    return current_path
            except:
                enabled=False
        raise ValueError(f"Can not find git-repository for folder \"{some_file_in_repository}\".")
    

    @GeneralUtilities.check_arguments
    def git_create_tag(self, directory: str, target_for_tag: str, tag: str, sign: bool = False, message: str = None) -> None:
        self.is_git_or_bare_git_repository(directory)
        argument = ["tag", tag, target_for_tag]
        if sign:
            if message is None:
                message = f"Created {target_for_tag}"
            argument.extend(["-s", '-m', message])
        self.run_program_argsasarray("git", argument, directory, throw_exception_if_exitcode_is_not_zero=True)

    @GeneralUtilities.check_arguments
    def git_delete_tag(self, directory: str, tag: str) -> None:
        self.is_git_or_bare_git_repository(directory)
        self.run_program_argsasarray("git", ["tag", "--delete", tag], directory, throw_exception_if_exitcode_is_not_zero=True)

    @GeneralUtilities.check_arguments
    def git_checkout(self, directory: str, rev: str, undo_all_changes_after_checkout: bool = True, assert_no_uncommitted_changes: bool = True) -> None:
        self.assert_is_git_repository(directory)
        if assert_no_uncommitted_changes:
            GeneralUtilities.assert_condition(not self.git_repository_has_uncommitted_changes(directory), f"Repository \"{directory}\" has uncommitted changes.")
        self.run_program_argsasarray("git", ["checkout", rev], directory, throw_exception_if_exitcode_is_not_zero=True)
        self.run_program_argsasarray("git", ["submodule", "update", "--recursive"], directory, throw_exception_if_exitcode_is_not_zero=True)
        commit_id=self.git_get_commit_id(directory,"HEAD")
        self.log.log(f"Checked out {commit_id} in \"{directory}\".", LogLevel.Debug)
        if undo_all_changes_after_checkout:
            self.git_undo_all_changes(directory)

    @GeneralUtilities.check_arguments
    def merge_repository(self, repository_folder: str, remote: str, branch: str):
        GeneralUtilities.assert_condition(not self.git_repository_has_uncommitted_changes(repository_folder),f"Can not merge. There are uncommitted changes in \"{repository_folder}\".")
        is_pullable: bool = self.git_branch_is_pullable(repository_folder, remote, branch, branch)
        if is_pullable:
            self.git_pull(repository_folder, remote, branch, branch)
            uncommitted_changes = self.git_repository_has_uncommitted_changes(repository_folder)
            GeneralUtilities.assert_condition(not uncommitted_changes, f"Pulling remote \"{remote}\" in \"{repository_folder}\" caused new uncommitted files.")
        self.git_checkout(repository_folder, branch)
        self.git_merge(repository_folder, f"{remote}/{branch}", branch)
        self.git_push_with_retry(repository_folder, remote, branch, branch)
        self.git_checkout(repository_folder, branch)
        #TODO opeional: checkfor merge conflicts and if there is one merge conflict print a warning

    @GeneralUtilities.check_arguments
    def git_merge_abort(self, directory: str) -> None:
        self.assert_is_git_repository(directory)
        self.run_program_argsasarray("git", ["merge", "--abort"], directory, throw_exception_if_exitcode_is_not_zero=True)

    @GeneralUtilities.check_arguments
    def git_merge(self, directory: str, sourcebranch: str, targetbranch: str, fastforward: bool = True, commit: bool = True, commit_message: str = None, undo_all_changes_after_checkout: bool = True, assert_no_uncommitted_changes: bool = True) -> str:
        self.assert_is_git_repository(directory)
        self.git_checkout(directory, targetbranch, undo_all_changes_after_checkout, assert_no_uncommitted_changes)
        args = ["merge"]
        if not commit:
            args.append("--no-commit")
        if not fastforward:
            args.append("--no-ff")
        if commit_message is not None:
            args.append("-m")
            args.append(commit_message)
        args.append(sourcebranch)
        self.run_program_argsasarray("git", args, directory, throw_exception_if_exitcode_is_not_zero=True)
        self.run_program_argsasarray("git", ["submodule", "update"], directory, throw_exception_if_exitcode_is_not_zero=True)
        return self.git_get_commit_id(directory)

    @GeneralUtilities.check_arguments
    def git_undo_all_changes(self, directory: str) -> None:
        """Caution: This function executes 'git clean -df'. This can delete files which maybe should not be deleted. Be aware of that."""
        self.assert_is_git_repository(directory)
        self.git_unstage_all_changes(directory)
        self.git_discard_all_unstaged_changes(directory)

    @GeneralUtilities.check_arguments
    def git_fetch_or_clone_all_in_directory(self, source_directory: str, target_directory: str) -> None:
        for subfolder in GeneralUtilities.get_direct_folders_of_folder(source_directory):
            foldername = os.path.basename(subfolder)
            if self.is_git_repository(subfolder):
                source_repository = subfolder
                target_repository = os.path.join(target_directory, foldername)
                if os.path.isdir(target_directory):
                    # fetch
                    self.git_fetch(target_directory)
                else:
                    # clone
                    self.git_clone(target_repository, source_repository, include_submodules=True, mirror=True)

    def get_git_submodules(self, directory: str) -> list[str]:
        self.is_git_or_bare_git_repository(directory)
        e = self.run_program("git", "submodule status", directory)
        result = []
        for submodule_line in GeneralUtilities.string_to_lines(e[1], False, True):
            result.append(submodule_line.split(' ')[1])
        return result

    @GeneralUtilities.check_arguments
    def file_is_git_ignored(self, file_in_repository: str, repositorybasefolder: str) -> None:
        self.is_git_or_bare_git_repository(repositorybasefolder)
        exit_code = self.run_program_argsasarray("git", ['check-ignore', file_in_repository], repositorybasefolder, throw_exception_if_exitcode_is_not_zero=False)[0]
        if (exit_code == 0):
            return True
        if (exit_code == 1):
            return False
        raise ValueError(f"Unable to calculate whether '{file_in_repository}' in repository '{repositorybasefolder}' is ignored due to git-exitcode {exit_code}.")

    @GeneralUtilities.check_arguments
    def get_not_git_ignored_files_of_folder(self, folder: str, file_extension: str = None) -> list[str]:
        """Returns the absolute paths of all files inside 'folder' (which must lie within a git-repository)
        that are not git-ignored, i.e. tracked files and untracked-but-not-ignored files; git-ignored content
        like 'node_modules', 'bin' or 'obj' is excluded. When 'file_extension' is set (e.g. '.cs') only files
        with that extension are returned."""
        if not os.path.isdir(folder):
            return []
        # Run git from within 'folder' so the listing is limited to that subtree. "--cached" lists tracked
        # files, "--others" untracked ones and "--exclude-standard" drops git-ignored files. "core.quotePath=false"
        # keeps non-ascii paths unquoted. The resulting paths are relative to 'folder'.
        lines = GeneralUtilities.string_to_lines(self.run_program_argsasarray("git", ["-c", "core.quotePath=false", "ls-files", "--cached", "--others", "--exclude-standard"], folder, throw_exception_if_exitcode_is_not_zero=True)[1], False)
        result: list[str] = []
        for line in lines:
            if not GeneralUtilities.string_has_content(line):
                continue
            absolute_path = GeneralUtilities.resolve_relative_path(line.strip(), folder)
            if file_extension is not None and not absolute_path.endswith(file_extension):
                continue
            if not os.path.isfile(absolute_path):  # a tracked-but-deleted file would still be listed by "--cached"
                continue
            if absolute_path not in result:
                result.append(absolute_path)
        return result

    @GeneralUtilities.check_arguments
    def git_discard_all_changes(self, repository: str) -> None:
        self.assert_is_git_repository(repository)
        self.run_program_argsasarray("git", ["reset", "HEAD", "."], repository, throw_exception_if_exitcode_is_not_zero=True)
        self.run_program_argsasarray("git", ["checkout", "."], repository, throw_exception_if_exitcode_is_not_zero=True)

    @GeneralUtilities.check_arguments
    def git_get_current_branch_name(self, repository: str) -> str:
        self.assert_is_git_repository(repository)
        result = self.run_program_argsasarray("git", ["rev-parse", "--abbrev-ref", "HEAD"], repository, throw_exception_if_exitcode_is_not_zero=True)
        return result[1].replace("\r", GeneralUtilities.empty_string).replace("\n", GeneralUtilities.empty_string)

    @GeneralUtilities.check_arguments
    def git_get_commitid_of_tag(self, repository: str, tag: str) -> str:
        self.is_git_or_bare_git_repository(repository)
        stdout = self.run_program_argsasarray("git", ["rev-list", "-n", "1", tag], repository)
        result = stdout[1].replace("\r", GeneralUtilities.empty_string).replace("\n", GeneralUtilities.empty_string)
        return result

    @GeneralUtilities.check_arguments
    def git_get_tags(self, repository: str) -> list[str]:
        self.is_git_or_bare_git_repository(repository)
        tags = [line.replace("\r", GeneralUtilities.empty_string) for line in self.run_program_argsasarray(
            "git", ["tag"], repository)[1].split("\n") if len(line) > 0]
        return tags

    @GeneralUtilities.check_arguments
    def git_move_tags_to_another_branch(self, repository: str, tag_source_branch: str, tag_target_branch: str, sign: bool = False, message: str = None) -> None:
        self.is_git_or_bare_git_repository(repository)
        tags = self.git_get_tags(repository)
        tags_count = len(tags)
        counter = 0
        for tag in tags:
            counter = counter+1
            self.log.log(f"Process tag {counter}/{tags_count}.", LogLevel.Information)
            # tag is on source-branch
            if self.git_commit_is_ancestor(repository, tag, tag_source_branch):
                commit_id_old = self.git_get_commit_id(repository, tag)
                commit_date: datetime = self.git_get_commit_date(repository, commit_id_old)
                date_as_string = self.__datetime_to_string_for_git(commit_date)
                search_commit_result = self.run_program_argsasarray("git", ["log", f'--after="{date_as_string}"', f'--before="{date_as_string}"', "--pretty=format:%H", tag_target_branch], repository, throw_exception_if_exitcode_is_not_zero=False)
                if search_commit_result[0] != 0 or not GeneralUtilities.string_has_nonwhitespace_content(search_commit_result[1]):
                    raise ValueError(f"Can not calculate corresponding commit for tag '{tag}'.")
                commit_id_new = search_commit_result[1]
                self.git_delete_tag(repository, tag)
                self.git_create_tag(repository, commit_id_new, tag, sign, message)

    @GeneralUtilities.check_arguments
    def get_current_git_commit_has_tag(self, repository_folder: str) -> bool:
        # Returns whether the currently checked-out commit (HEAD) itself has a tag.
        # "git tag --points-at HEAD" lists all tags (annotated and lightweight) that point exactly at HEAD;
        # this is not the same as "a tag is reachable from HEAD" (for that see get_latest_git_tag/git_repository_has_tags).
        self.is_git_or_bare_git_repository(repository_folder)
        result = self.run_program_argsasarray("git", ["tag", "--points-at", "HEAD"], repository_folder, throw_exception_if_exitcode_is_not_zero=False)
        return result[0] == 0 and GeneralUtilities.string_has_content(result[1])

    @GeneralUtilities.check_arguments
    def git_repository_has_tags(self, repository_folder: str) -> bool:
        # Returns whether the repository contains at least one tag (regardless of the currently checked-out commit).
        self.is_git_or_bare_git_repository(repository_folder)
        result = self.run_program_argsasarray("git", ["tag"], repository_folder, throw_exception_if_exitcode_is_not_zero=False)
        return result[0] == 0 and GeneralUtilities.string_has_content(result[1])

    @GeneralUtilities.check_arguments
    def get_latest_git_tag(self, repository_folder: str) -> str:
        self.is_git_or_bare_git_repository(repository_folder)
        result = self.run_program_argsasarray("git", ["describe", "--tags", "--abbrev=0"], repository_folder)
        result = result[1].replace("\r", GeneralUtilities.empty_string).replace("\n", GeneralUtilities.empty_string)
        return result

    @GeneralUtilities.check_arguments
    def get_staged_or_committed_git_ignored_files(self, repository_folder: str) -> list[str]:
        self.assert_is_git_repository(repository_folder)
        temp_result = self.run_program_argsasarray("git", ["ls-files", "-i", "-c", "--exclude-standard"], repository_folder)
        temp_result = temp_result[1].replace("\r", GeneralUtilities.empty_string)
        result = [line for line in temp_result.split("\n") if len(line) > 0]
        return result

    @GeneralUtilities.check_arguments
    def git_repository_has_commits(self, repository_folder: str) -> bool:
        self.assert_is_git_repository(repository_folder)
        return self.run_program_argsasarray("git", ["rev-parse", "--verify", "HEAD"], repository_folder, throw_exception_if_exitcode_is_not_zero=False)[0] == 0

    @GeneralUtilities.check_arguments
    def run_git_command_in_repository_and_submodules(self, repository_folder: str, arguments: list[str],print_live_output:bool) -> None:
        GeneralUtilities.assert_condition(self.is_git_or_bare_git_repository(repository_folder),f"\"{repository_folder}\" is not a git-repository.")
        self.log.log("Run \"git "+" ".join(arguments)+f"\" in {repository_folder} and its submodules...",LogLevel.Debug)
        self.run_program_argsasarray("git", arguments, repository_folder,print_live_output=print_live_output)
        if not self.is_bare_git_repository(repository_folder) and 0<len(self.get_git_submodules(repository_folder)):
            self.run_program_argsasarray("git", ["submodule", "foreach", "--recursive", "git"]+arguments, repository_folder,print_live_output=print_live_output)

    @GeneralUtilities.check_arguments
    def export_filemetadata(self, folder: str, target_file: str, encoding: str = "utf-8", filter_function=None) -> None:
        folder = GeneralUtilities.resolve_relative_path_from_current_working_directory(folder)
        lines = list()
        path_prefix = len(folder)+1
        items = dict()
        for item in GeneralUtilities.get_all_folders_of_folder(folder):
            items[item] = "d"
        for item in GeneralUtilities.get_all_files_of_folder(folder):
            items[item] = "f"
        for file_or_folder, item_type in items.items():
            truncated_file = file_or_folder[path_prefix:]
            if (filter_function is None or filter_function(folder, truncated_file)):
                owner_and_permisssion = self.get_file_owner_and_file_permission(file_or_folder)
                user = owner_and_permisssion[0]
                permissions = owner_and_permisssion[1]
                lines.append(f"{truncated_file};{item_type};{user};{permissions}")
        lines = sorted(lines, key=str.casefold)
        with open(target_file, "w", encoding=encoding) as file_object:
            file_object.write("\n".join(lines))

    @GeneralUtilities.check_arguments
    def escape_git_repositories_in_folder(self, folder: str) -> dict[str, str]:
        return self.__escape_git_repositories_in_folder_internal(folder, dict[str, str]())

    @GeneralUtilities.check_arguments
    def __escape_git_repositories_in_folder_internal(self, folder: str, renamed_items: dict[str, str]) -> dict[str, str]:
        for file in GeneralUtilities.get_direct_files_of_folder(folder):
            filename = os.path.basename(file)
            if ".git" in filename:
                new_name = filename.replace(".git", ".gitx")
                target = os.path.join(folder, new_name)
                os.rename(file, target)
                renamed_items[target] = file
        for subfolder in GeneralUtilities.get_direct_folders_of_folder(folder):
            foldername = os.path.basename(subfolder)
            if ".git" in foldername:
                new_name = foldername.replace(".git", ".gitx")
                subfolder2 = os.path.join(str(Path(subfolder).parent), new_name)
                os.rename(subfolder, subfolder2)
                renamed_items[subfolder2] = subfolder
            else:
                subfolder2 = subfolder
            self.__escape_git_repositories_in_folder_internal(subfolder2, renamed_items)
        return renamed_items

    @GeneralUtilities.check_arguments
    def deescape_git_repositories_in_folder(self, renamed_items: dict[str, str]):
        for renamed_item, original_name in renamed_items.items():
            os.rename(renamed_item, original_name)

    @GeneralUtilities.check_arguments
    def is_git_repository(self, folder: str) -> bool:
        """This function works platform-independent also for non-local-executions if the ScriptCollection commandline-commands are available as global command on the target-system."""
        folder=folder.replace("\\","/")
        if folder.endswith("/"):
            folder = folder[:-1]
        if not self.is_folder(folder):
            raise ValueError(f"Folder '{folder}' does not exist.")
        git_folder_path = f"{folder}/.git"
        return self.is_folder(git_folder_path) or self.is_file(git_folder_path)

    @GeneralUtilities.check_arguments
    def is_bare_git_repository(self, folder: str) -> bool:
        """This function works platform-independent also for non-local-executions if the ScriptCollection commandline-commands are available as global command on the target-system."""
        if folder.endswith("/") or folder.endswith("\\"):
            folder = folder[:-1]
        if not self.is_folder(folder):
            raise ValueError(f"Folder '{folder}' does not exist.")
        return folder.endswith(".git")

    @GeneralUtilities.check_arguments
    def is_git_or_bare_git_repository(self, folder: str) -> bool:
        """This function works platform-independent also for non-local-executions if the ScriptCollection commandline-commands are available as global command on the target-system."""
        return self.is_git_repository(folder) or self.is_bare_git_repository(folder)

    @GeneralUtilities.check_arguments
    def assert_is_git_repository(self, folder: str) -> str:
        """This function works platform-independent also for non-local-executions if the ScriptCollection commandline-commands are available as global command on the target-system."""
        GeneralUtilities.assert_condition(self.is_git_repository(folder), f"'{folder}' is not a git-repository.")

    @GeneralUtilities.check_arguments
    def convert_git_repository_to_bare_repository(self, repository_folder: str):
        repository_folder = repository_folder.replace("\\", "/")
        self.assert_is_git_repository(repository_folder)
        git_folder = repository_folder + "/.git"
        if not self.is_folder(git_folder):
            raise ValueError(f"Converting '{repository_folder}' to a bare repository not possible. The folder '{git_folder}' does not exist. Converting is currently only supported when the git-folder is a direct folder in a repository and not a reference to another location.")
        target_folder: str = repository_folder + ".git"
        GeneralUtilities.ensure_directory_exists(target_folder)
        GeneralUtilities.move_content_of_folder(git_folder, target_folder)
        GeneralUtilities.ensure_directory_does_not_exist(repository_folder)
        self.run_program_argsasarray("git", ["config", "--bool", "core.bare", "true"], target_folder)

    @GeneralUtilities.check_arguments
    def assert_no_uncommitted_changes(self, repository_folder: str,custom_message:str=None) -> None:
        if self.git_repository_has_uncommitted_changes(repository_folder):
            diff_result = self.run_program("git", "diff HEAD", repository_folder, throw_exception_if_exitcode_is_not_zero=False)
            # "git diff HEAD" only shows changes of tracked files; list the untracked files separately so they are shown here too.
            untracked_files_result = self.run_program_argsasarray("git", ["ls-files", "--exclude-standard", "--others"], repository_folder, throw_exception_if_exitcode_is_not_zero=False)
            GeneralUtilities.write_message_to_stderr(f"Uncommitted changes in '{repository_folder}':")
            if GeneralUtilities.string_has_content(diff_result[1]):
                GeneralUtilities.write_message_to_stderr(diff_result[1])
            if GeneralUtilities.string_has_content(untracked_files_result[1]):
                GeneralUtilities.write_message_to_stderr("Untracked files:")
                GeneralUtilities.write_message_to_stderr(untracked_files_result[1])
            if custom_message:
                raise ValueError(f"Repository '{repository_folder}' has uncommitted changes: "+custom_message)
            else:
                raise ValueError(f"Repository '{repository_folder}' has uncommitted changes.")

    @GeneralUtilities.check_arguments
    def list_content(self, path: str, include_files: bool, include_folder: bool, printonlynamewithoutpath: bool) -> list[str]:
        """This function works platform-independent also for non-local-executions if the ScriptCollection commandline-commands are available as global command on the target-system."""
        result: list[str] = []
        if self.program_runner.will_be_executed_locally():
            if include_files:
                result = result + GeneralUtilities.get_direct_files_of_folder(path)
            if include_folder:
                result = result + GeneralUtilities.get_direct_folders_of_folder(path)
        else:
            arguments = ["--path", path]
            if not include_files:
                arguments = arguments+["--excludefiles"]
            if not include_folder:
                arguments = arguments+["--excludedirectories"]
            if printonlynamewithoutpath:
                arguments = arguments+["--printonlynamewithoutpath"]
            exit_code, stdout, stderr, _ = self.run_program_argsasarray("sclistfoldercontent", arguments)
            if exit_code == 0:
                for line in stdout.split("\n"):
                    normalized_line = line.replace("\r", "")
                    result.append(normalized_line)
            else:
                raise ValueError(f"Fatal error occurrs while checking whether file '{path}' exists. StdErr: '{stderr}'")
        result = [item for item in result if GeneralUtilities.string_has_nonwhitespace_content(item)]
        return result

    @GeneralUtilities.check_arguments
    def is_file(self, path: str) -> bool:
        """This function works platform-independent also for non-local-executions if the ScriptCollection commandline-commands are available as global command on the target-system."""
        if self.program_runner.will_be_executed_locally():
            return os.path.isfile(path)  # works only locally, but much more performant than always running an external program
        else:
            exit_code, _, stderr, _ = self.run_program_argsasarray("scfileexists", ["--path", path], throw_exception_if_exitcode_is_not_zero=False)  # works platform-indepent
            if exit_code == 0:
                return True
            elif exit_code == 1:
                raise ValueError(f"Not calculatable whether file '{path}' exists. StdErr: '{stderr}'")
            elif exit_code == 2:
                return False
            raise ValueError(f"Fatal error occurrs while checking whether file '{path}' exists. StdErr: '{stderr}'")

    @GeneralUtilities.check_arguments
    def get_size(self, path: str) -> int:
        """This function works platform-independent also for non-local-executions if the ScriptCollection commandline-commands are available as global command on the target-system."""
        if self.program_runner.will_be_executed_locally():
            return os.path.getsize(path)  # works only locally, but much more performant than always running an external program
        else:
            exit_code, stdout, stderr, _ = self.run_program_argsasarray("scgetsize", ["--path", path], throw_exception_if_exitcode_is_not_zero=False)  # works platform-indepent
            if exit_code == 0:
                return int(stdout.replace("\r","").replace("\n","").strip())
            else:
                raise ValueError(f"Fatal error occurrs while checking whether file '{path}' exists. StdErr: '{stderr}'")

    @GeneralUtilities.check_arguments
    def is_folder(self, path: str) -> bool:
        """This function works platform-independent also for non-local-executions if the ScriptCollection commandline-commands are available as global command on the target-system."""
        if self.program_runner.will_be_executed_locally():  # works only locally, but much more performant than always running an external program
            return os.path.isdir(path)
        else:
            exit_code, _, stderr, _ = self.run_program_argsasarray("scfolderexists", ["--path", path], throw_exception_if_exitcode_is_not_zero=False)  # works platform-indepent
            if exit_code == 0:
                return True
            elif exit_code == 1:
                raise ValueError(f"Not calculatable whether folder '{path}' exists. StdErr: '{stderr}'")
            elif exit_code == 2:
                return False
            raise ValueError(f"Fatal error occurrs while checking whether folder '{path}' exists. StdErr: '{stderr}'")



    @GeneralUtilities.check_arguments
    def set_file_content(self, path: str, content: str, encoding: str = "utf-8") -> None:
        """This function works platform-independent also for non-local-executions if the ScriptCollection commandline-commands are available as global command on the target-system."""
        if self.program_runner.will_be_executed_locally():
            GeneralUtilities.write_text_to_file(path, content, encoding)
        else:
            content_bytes = content.encode('utf-8')
            base64_bytes = base64.b64encode(content_bytes)
            base64_string = base64_bytes.decode('utf-8')
            self.run_program_argsasarray("scsetfilecontent", ["--path", path, "--argumentisinbase64", "--content", base64_string])  # works platform-indepent

    @GeneralUtilities.check_arguments
    def file_contains_content(self, path: str, content: str, treat_content_as_regex: bool = False, case_sensitive: bool = True, encoding: str = "utf-8") -> bool:
        """Returns True if `content` appears in the file at `path`. With treat_content_as_regex=True
        the search is done via re.search, otherwise plain substring containment is checked."""
        GeneralUtilities.assert_file_exists(path)
        file_content = GeneralUtilities.read_text_from_file(path, encoding)
        if treat_content_as_regex:
            flags = 0 if case_sensitive else re.IGNORECASE
            return re.search(content, file_content, flags) is not None
        if case_sensitive:
            return content in file_content
        return content.lower() in file_content.lower()

    @GeneralUtilities.check_arguments
    def remove(self, path: str) -> None:
        """This function works platform-independent also for non-local-executions if the ScriptCollection commandline-commands are available as global command on the target-system."""
        if self.program_runner.will_be_executed_locally():  # works only locally, but much more performant than always running an external program
            if os.path.isdir(path):
                GeneralUtilities.ensure_directory_does_not_exist(path)
            if os.path.isfile(path):
                GeneralUtilities.ensure_file_does_not_exist(path)
        else:
            if self.is_file(path):
                exit_code, stdout, stderr, _ = self.run_program_argsasarray("scremovefile", ["--path", path], throw_exception_if_exitcode_is_not_zero=False)  # works platform-indepent
                if exit_code != 0:
                    raise ValueError(f"Fatal error occurrs while removing file '{path}'; Exitcode: '{exit_code}'; StdOut: '{stdout}'. StdErr: '{stderr}'")
            if self.is_folder(path):
                exit_code, stdout, stderr, _ = self.run_program_argsasarray("scremovefolder", ["--path", path], throw_exception_if_exitcode_is_not_zero=False)  # works platform-indepent
                if exit_code != 0:
                    raise ValueError(f"Fatal error occurrs while removing folder '{path}'; Exitcode: '{exit_code}'; StdOut: '{stdout}'. StdErr: '{stderr}'")

    @GeneralUtilities.check_arguments
    def rename(self,  source: str, target: str) -> None:
        """This function works platform-independent also for non-local-executions if the ScriptCollection commandline-commands are available as global command on the target-system."""
        if self.program_runner.will_be_executed_locally():  # works only locally, but much more performant than always running an external program
            os.rename(source, target)
        else:
            exit_code, stdout, stderr, _ = self.run_program_argsasarray("screname", ["--source", source, "--target", target], throw_exception_if_exitcode_is_not_zero=False)  # works platform-indepent
            if exit_code != 0:
                raise ValueError(f"Fatal error occurrs while renaming '{source}' to '{target}'; Exitcode: '{exit_code}'; StdOut: '{stdout}'. StdErr: '{stderr}'")

    @GeneralUtilities.check_arguments
    def copy(self, source: str, target: str) -> None:
        """This function works platform-independent also for non-local-executions if the ScriptCollection commandline-commands are available as global command on the target-system."""
        if self.program_runner.will_be_executed_locally():  # works only locally, but much more performant than always running an external program
            if os.path.isfile(target) or os.path.isdir(target):
                raise ValueError(f"Can not copy to '{target}' because the target already exists.")
            if os.path.isfile(source):
                shutil.copyfile(source, target)
            elif os.path.isdir(source):
                GeneralUtilities.ensure_directory_exists(target)
                GeneralUtilities.copy_content_of_folder(source, target)
            else:
                raise ValueError(f"'{source}' can not be copied because the path does not exist.")
        else:
            exit_code, stdout, stderr, _ = self.run_program_argsasarray("sccopy", ["--source", source, "--target", target], throw_exception_if_exitcode_is_not_zero=False)  # works platform-indepent
            if exit_code != 0:
                raise ValueError(f"Fatal error occurrs while copying '{source}' to '{target}'; Exitcode: '{exit_code}'; StdOut: '{stdout}'. StdErr: '{stderr}'")

    @GeneralUtilities.check_arguments
    def get_file_content(self, file: str, encoding: str = "utf-8", from_line: int = None, to_line: int = None) -> str:
        """Returns the content of the file. With from_line and/or to_line (both 1-based and inclusive) the returned
        content can be restricted to a range of lines."""
        content = GeneralUtilities.read_text_from_file(file, encoding)
        if from_line is None and to_line is None:
            return content
        lines = content.splitlines()
        start_index = 0 if from_line is None else max(from_line - 1, 0)
        end_index = len(lines) if to_line is None else min(to_line, len(lines))
        return "\n".join(lines[start_index:end_index])

    @GeneralUtilities.check_arguments
    def create_skill(self, skill_name: str, description: str, repository_folder: str = None, tags: list[str] = None, priority: str = None, triggers: list[str] = None) -> str:
        """Generates a skill-folder ('skills/<skill_name>/' with a lightweight 'skill.json' and a lazy-loaded 'detail.md').
        The skill is created in the given repository-folder, or - if none is given - in the current working-directory when
        that is a git-repository, otherwise in the user's ScriptCollection-configuration-folder. Returns the skill-folder."""
        if tags is None:
            tags = []
        if triggers is None:
            triggers = []
        if priority is None:
            priority = "medium"
        if repository_folder is not None:
            base_folder = repository_folder
        elif self.is_git_repository(os.getcwd()):
            base_folder = os.getcwd()
        else:
            base_folder = GeneralUtilities.get_scriptcollection_configuration_folder()
        skill_folder = os.path.join(base_folder, "skills", skill_name)
        GeneralUtilities.ensure_directory_exists(skill_folder)
        skill_definition = {
            "name": skill_name,
            "description": description,
            "triggers": triggers,
            "tags": tags,
            "priority": priority,
        }
        GeneralUtilities.write_text_to_file(os.path.join(skill_folder, "skill.json"), json.dumps(skill_definition, indent=2))
        detail_file = os.path.join(skill_folder, "detail.md")
        detail_content = f"# {skill_name}\n\n{description}\n\n## Details\n\n<!-- Add the detailed (lazy-loaded) instructions for this skill here. -->\n"
        GeneralUtilities.write_text_to_file(detail_file, detail_content)
        return skill_folder

    @GeneralUtilities.check_arguments
    def create_file(self, path: str, error_if_already_exists: bool, create_necessary_folder: bool) -> None:
        """This function works platform-independent also for non-local-executions if the ScriptCollection commandline-commands are available as global command on the target-system."""
        if self.program_runner.will_be_executed_locally():
            if not os.path.isabs(path):
                path = os.path.join(os.getcwd(), path)

            if os.path.isfile(path) and error_if_already_exists:
                raise ValueError(f"File '{path}' already exists.")

            # TODO maybe it should be checked if there is a folder with the same path which already exists.

            folder = os.path.dirname(path)

            if not os.path.isdir(folder):
                if create_necessary_folder:
                    GeneralUtilities.ensure_directory_exists(folder)  # TODO check if this also create nested folders if required
                else:
                    raise ValueError(f"Folder '{folder}' does not exist.")

            GeneralUtilities.ensure_file_exists(path)
        else:
            arguments = ["--path", path]

            if error_if_already_exists:
                arguments = arguments+["--errorwhenexists"]

            if create_necessary_folder:
                arguments = arguments+["--createnecessaryfolder"]

            exit_code, stdout, stderr, _ = self.run_program_argsasarray("sccreatefile", arguments, throw_exception_if_exitcode_is_not_zero=False)  # works platform-indepent
            if exit_code != 0:
                raise ValueError(f"Fatal error occurrs while create file '{path}'; Exitcode: '{exit_code}'; StdOut: '{stdout}'. StdErr: '{stderr}'")

    @GeneralUtilities.check_arguments
    def create_folder(self, path: str, error_if_already_exists: bool, create_necessary_folder: bool) -> None:
        """This function works platform-independent also for non-local-executions if the ScriptCollection commandline-commands are available as global command on the target-system."""
        if self.program_runner.will_be_executed_locally():
            if not os.path.isabs(path):
                path = os.path.join(os.getcwd(), path)

            if os.path.isdir(path) and error_if_already_exists:
                raise ValueError(f"Folder '{path}' already exists.")

            # TODO maybe it should be checked if there is a file with the same path which already exists.

            folder = os.path.dirname(path)

            if not os.path.isdir(folder):
                if create_necessary_folder:
                    GeneralUtilities.ensure_directory_exists(folder)  # TODO check if this also create nested folders if required
                else:
                    raise ValueError(f"Folder '{folder}' does not exist.")

            GeneralUtilities.ensure_directory_exists(path)
        else:
            arguments = ["--path", path]

            if error_if_already_exists:
                arguments = arguments+["--errorwhenexists"]

            if create_necessary_folder:
                arguments = arguments+["--createnecessaryfolder"]

            exit_code, stdout, stderr, _ = self.run_program_argsasarray("sccreatefolder", arguments, throw_exception_if_exitcode_is_not_zero=False)  # works platform-indepent
            if exit_code != 0:
                raise ValueError(f"Fatal error occurrs while create folder '{path}'; Exitcode: '{exit_code}'; StdOut: '{stdout}'. StdErr: '{stderr}'")

    @GeneralUtilities.check_arguments
    def __sort_fmd(self, line: str):
        splitted: list = line.split(";")
        filetype: str = splitted[1]
        if filetype == "d":
            return -1
        if filetype == "f":
            return 1
        return 0

    @GeneralUtilities.check_arguments
    def restore_filemetadata(self, folder: str, source_file: str, strict=False, encoding: str = "utf-8", create_folder_is_not_exist: bool = True) -> None:
        lines = GeneralUtilities.read_lines_from_file(source_file, encoding)
        lines.sort(key=self.__sort_fmd)
        for line in lines:
            splitted: list = line.split(";")
            full_path_of_file_or_folder: str = os.path.join(folder, splitted[0])
            filetype: str = splitted[1]
            user: str = splitted[2]
            permissions: str = splitted[3]
            if filetype == "d" and create_folder_is_not_exist and not os.path.isdir(full_path_of_file_or_folder):
                GeneralUtilities.ensure_directory_exists(full_path_of_file_or_folder)
            if (filetype == "f" and os.path.isfile(full_path_of_file_or_folder)) or (filetype == "d" and os.path.isdir(full_path_of_file_or_folder)):
                self.set_owner(full_path_of_file_or_folder, user, os.name != 'nt')
                self.set_permission(full_path_of_file_or_folder, permissions)
            else:
                if strict:
                    if filetype == "f":
                        filetype_full = "File"
                    elif filetype == "d":
                        filetype_full = "Directory"
                    else:
                        raise ValueError(f"Unknown filetype: {GeneralUtilities.str_none_safe(filetype)}")
                    raise ValueError(f"{filetype_full} '{full_path_of_file_or_folder}' does not exist")

    @GeneralUtilities.check_arguments
    def __calculate_lengh_in_seconds(self, filename: str, folder: str) -> float:
        argument = ['-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', filename]
        result = self.run_program_argsasarray("ffprobe", argument, folder, throw_exception_if_exitcode_is_not_zero=True)
        return float(result[1].replace('\n', ''))

    @GeneralUtilities.check_arguments
    def __create_thumbnails(self, filename: str, fps: str, folder: str, tempname_for_thumbnails: str) -> list[str]:
        argument = ['-i', filename, '-r', fps, '-vf', 'scale=-1:120', '-vcodec', 'png', f'{tempname_for_thumbnails}-%002d.png']
        self.run_program_argsasarray("ffmpeg", argument, folder, throw_exception_if_exitcode_is_not_zero=True)
        files = GeneralUtilities.get_direct_files_of_folder(folder)
        result: list[str] = []
        regex = "^"+re.escape(tempname_for_thumbnails)+"\\-\\d+\\.png$"
        regex_for_files = re.compile(regex)
        for file in files:
            filename = os.path.basename(file)
            if regex_for_files.match(filename):
                result.append(file)
        GeneralUtilities.assert_condition(0 < len(result), "No thumbnail-files found.")
        return result

    @GeneralUtilities.check_arguments
    def __create_thumbnail(self, outputfilename: str, folder: str, length_in_seconds: float, tempname_for_thumbnails: str, amount_of_images: int) -> None:
        duration = timedelta(seconds=length_in_seconds)
        info = GeneralUtilities.timedelta_to_simple_string(duration)
        next_square_number = GeneralUtilities.get_next_square_number(amount_of_images)
        root = math.sqrt(next_square_number)
        rows: int = root  # 5
        columns: int = root  # math.ceil(amount_of_images/rows)
        argument = ['-title', f'"{outputfilename} ({info})"', '-tile', f'{rows}x{columns}', f'{tempname_for_thumbnails}*.png', f'{outputfilename}.png']
        self.run_program_argsasarray("montage", argument, folder, throw_exception_if_exitcode_is_not_zero=True)

    @GeneralUtilities.check_arguments
    def __create_thumbnail2(self, outputfilename: str, folder: str, length_in_seconds: float, rows: int, columns: int, tempname_for_thumbnails: str, amount_of_images: int) -> None:
        duration = timedelta(seconds=length_in_seconds)
        info = GeneralUtilities.timedelta_to_simple_string(duration)
        argument = ['-title', f'"{outputfilename} ({info})"', '-tile', f'{rows}x{columns}', f'{tempname_for_thumbnails}*.png', f'{outputfilename}.png']
        self.run_program_argsasarray("montage", argument, folder, throw_exception_if_exitcode_is_not_zero=True)

    @GeneralUtilities.check_arguments
    def __roundup(self, x: float, places: int) -> int:
        d = 10 ** places
        if x < 0:
            return math.floor(x * d) / d
        else:
            return math.ceil(x * d) / d

    @GeneralUtilities.check_arguments
    def generate_thumbnail(self, file: str, frames_per_second: float, tempname_for_thumbnails: str = None, hook=None) -> None:
        if tempname_for_thumbnails is None:
            tempname_for_thumbnails = "t_"+str(uuid.uuid4())

        file = GeneralUtilities.resolve_relative_path_from_current_working_directory(file)
        filename = os.path.basename(file)
        folder = os.path.dirname(file)
        filename_without_extension = Path(file).stem
        preview_files: list[str] = []
        try:
            length_in_seconds = self.__calculate_lengh_in_seconds(filename, folder)
            # frames per second, example: frames_per_second="20fps" => 20 frames per second
            frames_per_second = self.__roundup(float(frames_per_second[:-3]), 2)
            frames_per_second_as_string = str(frames_per_second)
            preview_files = self.__create_thumbnails(filename, frames_per_second_as_string, folder, tempname_for_thumbnails)
            if hook is not None:
                hook(file, preview_files)
            actual_amounf_of_previewframes = len(preview_files)
            self.__create_thumbnail(filename_without_extension, folder, length_in_seconds, tempname_for_thumbnails, actual_amounf_of_previewframes)
        finally:
            for thumbnail_to_delete in preview_files:
                os.remove(thumbnail_to_delete)

    @GeneralUtilities.check_arguments
    def generate_thumbnail_by_amount_of_pictures(self, file: str, amount_of_columns: int, amount_of_rows: int, tempname_for_thumbnails: str = None, hook=None) -> None:
        if tempname_for_thumbnails is None:
            tempname_for_thumbnails = "t_"+str(uuid.uuid4())

        file = GeneralUtilities.resolve_relative_path_from_current_working_directory(file)
        filename = os.path.basename(file)
        folder = os.path.dirname(file)
        filename_without_extension = Path(file).stem
        preview_files: list[str] = []
        try:
            length_in_seconds = self.__calculate_lengh_in_seconds(filename, folder)
            amounf_of_previewframes = int(amount_of_columns*amount_of_rows)
            frames_per_second_as_string = f"{amounf_of_previewframes-2}/{length_in_seconds}"
            preview_files = self.__create_thumbnails(filename, frames_per_second_as_string, folder, tempname_for_thumbnails)
            if hook is not None:
                hook(file, preview_files)
            actual_amounf_of_previewframes = len(preview_files)
            self.__create_thumbnail2(filename_without_extension, folder, length_in_seconds, amount_of_rows, amount_of_columns, tempname_for_thumbnails, actual_amounf_of_previewframes)
        finally:
            for thumbnail_to_delete in preview_files:
                os.remove(thumbnail_to_delete)

    @GeneralUtilities.check_arguments
    def extract_pdf_pages(self, file: str, from_page: int, to_page: int, outputfile: str) -> None:
        pdf_reader: PdfReader = PdfReader(file)
        pdf_writer: PdfWriter = PdfWriter()
        start = from_page
        end = to_page
        while start <= end:
            pdf_writer.add_page(pdf_reader.pages[start-1])
            start += 1
        with open(outputfile, 'wb') as out:
            pdf_writer.write(out)

    @GeneralUtilities.check_arguments
    def merge_pdf_files(self, files: list[str], outputfile: str) -> None:
        # TODO add wildcard-option
        pdfFileMerger: PdfWriter = PdfWriter()
        for file in files:
            with open(file, "rb") as f:
                pdfFileMerger.append(f)
        with open(outputfile, "wb") as output:
            pdfFileMerger.write(output)
            pdfFileMerger.close()

    @GeneralUtilities.check_arguments
    def show_missing_files(self, folderA: str, folderB: str):
        for file in GeneralUtilities.get_missing_files(folderA, folderB):
            GeneralUtilities.write_message_to_stdout(file)

    @GeneralUtilities.check_arguments
    def SCCreateEmptyFileWithSpecificSize(self, name: str, size_string: str) -> int:
        if size_string.isdigit():
            size = int(size_string)
        else:
            if len(size_string) >= 3:
                if (size_string.endswith("kb")):
                    size = int(size_string[:-2]) * pow(10, 3)
                elif (size_string.endswith("mb")):
                    size = int(size_string[:-2]) * pow(10, 6)
                elif (size_string.endswith("gb")):
                    size = int(size_string[:-2]) * pow(10, 9)
                elif (size_string.endswith("kib")):
                    size = int(size_string[:-3]) * pow(2, 10)
                elif (size_string.endswith("mib")):
                    size = int(size_string[:-3]) * pow(2, 20)
                elif (size_string.endswith("gib")):
                    size = int(size_string[:-3]) * pow(2, 30)
                else:
                    self.log.log("Wrong format", LogLevel.Error)
                    return 1
            else:
                self.log.log("Wrong format", LogLevel.Error)
                return 1
        with open(name, "wb") as f:
            f.seek(size-1)
            f.write(b"\0")
        return 0

    @GeneralUtilities.check_arguments
    def SCCreateHashOfAllFiles(self, folder: str) -> None:
        for file in GeneralUtilities.absolute_file_paths(folder):
            with open(file+".sha256", "w+", encoding="utf-8") as f:
                f.write(GeneralUtilities.get_sha256_of_file(file))

    @GeneralUtilities.check_arguments
    def SCCreateSimpleMergeWithoutRelease(self, repository: str, sourcebranch: str, targetbranch: str, remotename: str, remove_source_branch: bool) -> None:
        commitid = self.git_merge(repository, sourcebranch, targetbranch, False, True)
        self.git_merge(repository, targetbranch, sourcebranch, True, True)
        created_version = self.get_semver_version_from_gitversion(repository)
        self.git_create_tag(repository, commitid, f"v{created_version}", True)
        self.git_push(repository, remotename, targetbranch, targetbranch, False, True)
        if (GeneralUtilities.string_has_nonwhitespace_content(remotename)):
            self.git_push(repository, remotename, sourcebranch, sourcebranch, False, True)
        if (remove_source_branch):
            self.git_remove_branch(repository, sourcebranch)

    @GeneralUtilities.check_arguments
    def sc_organize_lines_in_file(self, file: str, encoding: str="utf-8", sort: bool = False, remove_duplicated_lines: bool = False, ignore_first_line: bool = False, remove_empty_lines: bool = True, ignored_start_character: list = list()):
        GeneralUtilities.assert_file_exists(file)

        # read file
        lines = GeneralUtilities.read_lines_from_file(file, encoding)
        if (len(lines) == 0):
            return

        # store first line if desired
        if (ignore_first_line):
            first_line = lines.pop(0)

        # remove empty lines if desired
        if remove_empty_lines:
            temp = lines
            lines = []
            for line in temp:
                if (not (GeneralUtilities.string_is_none_or_whitespace(line))):
                    lines.append(line)

        # remove duplicated lines if desired
        if remove_duplicated_lines:
            lines = GeneralUtilities.remove_duplicates(lines)

        # sort lines if desired
        if sort:
            lines = sorted(lines, key=lambda singleline: self.__adapt_line_for_sorting(singleline, ignored_start_character))

        # reinsert first line if required
        if ignore_first_line:
            lines.insert(0, first_line)

        # write result to file
        GeneralUtilities.write_lines_to_file(file, lines, encoding)


    @GeneralUtilities.check_arguments
    def __adapt_line_for_sorting(self, line: str, ignored_start_characters: list):
        result = line.lower()
        while len(result) > 0 and result[0] in ignored_start_characters:
            result = result[1:]
        return result

    @GeneralUtilities.check_arguments
    def SCGenerateSnkFiles(self, outputfolder, keysize=4096, amountofkeys=10) -> int:
        GeneralUtilities.ensure_directory_exists(outputfolder)
        for _ in range(amountofkeys):
            file = os.path.join(outputfolder, str(uuid.uuid4())+".snk")
            argument = f"-k {keysize} {file}"
            self.run_program("sn", argument, outputfolder)

    @GeneralUtilities.check_arguments
    def __merge_files(self, sourcefile: str, targetfile: str) -> None:
        with open(sourcefile, "rb") as f:
            source_data = f.read()
        with open(targetfile, "ab") as fout:
            merge_separator = [0x0A]
            fout.write(bytes(merge_separator))
            fout.write(source_data)

    @GeneralUtilities.check_arguments
    def __process_file(self, file: str, substringInFilename: str, newSubstringInFilename: str, conflictResolveMode: str) -> None:
        new_filename = os.path.join(os.path.dirname(file), os.path.basename(file).replace(substringInFilename, newSubstringInFilename))
        if file != new_filename:
            if os.path.isfile(new_filename):
                if filecmp.cmp(file, new_filename):
                    send2trash.send2trash(file)
                else:
                    if conflictResolveMode == "ignore":
                        pass
                    elif conflictResolveMode == "preservenewest":
                        if (os.path.getmtime(file) - os.path.getmtime(new_filename) > 0):
                            send2trash.send2trash(file)
                        else:
                            send2trash.send2trash(new_filename)
                            os.rename(file, new_filename)
                    elif (conflictResolveMode == "merge"):
                        self.__merge_files(file, new_filename)
                        send2trash.send2trash(file)
                    else:
                        raise ValueError('Unknown conflict resolve mode')
            else:
                os.rename(file, new_filename)

    @GeneralUtilities.check_arguments
    def SCReplaceSubstringsInFilenames(self, folder: str, substringInFilename: str, newSubstringInFilename: str, conflictResolveMode: str) -> None:
        for file in GeneralUtilities.absolute_file_paths(folder):
            self.__process_file(file, substringInFilename, newSubstringInFilename, conflictResolveMode)

    @GeneralUtilities.check_arguments
    def __check_file(self, file: str, searchstring: str) -> None:
        bytes_ascii = bytes(searchstring, "ascii")
        # often called "unicode-encoding"
        bytes_utf16 = bytes(searchstring, "utf-16")
        bytes_utf8 = bytes(searchstring, "utf-8")
        with open(file, mode='rb') as file_object:
            content = file_object.read()
            if bytes_ascii in content:
                GeneralUtilities.write_message_to_stdout(file)
            elif bytes_utf16 in content:
                GeneralUtilities.write_message_to_stdout(file)
            elif bytes_utf8 in content:
                GeneralUtilities.write_message_to_stdout(file)

    @GeneralUtilities.check_arguments
    def SCSearchInFiles(self, folder: str, searchstring: str) -> None:
        for file in GeneralUtilities.absolute_file_paths(folder):
            self.__check_file(file, searchstring)

    @GeneralUtilities.check_arguments
    def get_string_as_qr_code(self,string: str) -> None:
        qr = qrcode.QRCode()
        qr.add_data(string)
        f = io.StringIO()
        qr.print_ascii(out=f)
        f.seek(0)
        return f.read()

    @GeneralUtilities.check_arguments
    def __print_qr_code_by_csv_line(self, displayname: str, website: str, emailaddress: str, key: str, period: str) -> None:
        qrcode_content = f"otpauth://totp/{website}:{emailaddress}?secret={key}&issuer={displayname}&period={period}"
        GeneralUtilities.write_message_to_stdout(f"{displayname} ({emailaddress}):")
        GeneralUtilities.write_message_to_stdout(qrcode_content)
        GeneralUtilities.write_message_to_stdout(self.get_string_as_qr_code(qrcode_content))

    @GeneralUtilities.check_arguments
    def SCShow2FAAsQRCode(self, csvfile: str) -> None:
        lines = GeneralUtilities.read_csv_file(csvfile, True)
        lines.sort(key=lambda items: ''.join(items).lower())
        for line in lines:
            self.__print_qr_code_by_csv_line(line[0], line[1], line[2], line[3], line[4])
            GeneralUtilities.write_message_to_stdout(GeneralUtilities.get_longline())

    @GeneralUtilities.check_arguments
    def SCCalculateBitcoinBlockHash(self, block_version_number: str, previousblockhash: str, transactionsmerkleroot: str, timestamp: str, target: str, nonce: str) -> str:
        # Example-values:
        # block_version_number: "00000020"
        # previousblockhash: "66720b99e07d284bd4fe67ff8c49a5db1dd8514fcdab61000000000000000000"
        # transactionsmerkleroot: "7829844f4c3a41a537b3131ca992643eaa9d093b2383e4cdc060ad7dc5481187"
        # timestamp: "51eb505a"
        # target: "c1910018"
        # nonce: "de19b302"
        header = str(block_version_number + previousblockhash + transactionsmerkleroot + timestamp + target + nonce)
        return binascii.hexlify(hashlib.sha256(hashlib.sha256(binascii.unhexlify(header)).digest()).digest()[::-1]).decode('utf-8')

    @GeneralUtilities.check_arguments
    def SCChangeHashOfProgram(self, inputfile: str) -> None:
        valuetoappend = str(uuid.uuid4())

        outputfile = inputfile + '.modified'

        shutil.copy2(inputfile, outputfile)
        with open(outputfile, 'a', encoding="utf-8") as file:
            # TODO use rcedit for .exe-files instead of appending valuetoappend ( https://github.com/electron/rcedit/ )
            # background: you can retrieve the "original-filename" from the .exe-file like discussed here:
            # https://security.stackexchange.com/questions/210843/ is-it-possible-to-change-original-filename-of-an-exe
            # so removing the original filename with rcedit is probably a better way to make it more difficult to detect the programname.
            # this would obviously also change the hashvalue of the program so appending a whitespace is not required anymore.
            file.write(valuetoappend)

    @GeneralUtilities.check_arguments
    def __adjust_folder_name(self, folder: str) -> str:
        result = os.path.dirname(folder).replace("\\", "/")
        if result == "/":
            return GeneralUtilities.empty_string
        else:
            return result

    @GeneralUtilities.check_arguments
    def __create_iso(self, folder, iso_file) -> None:
        created_directories = []
        files_directory = "FILES"
        iso = pycdlib.PyCdlib()
        iso.new()
        files_directory = files_directory.upper()
        iso.add_directory("/" + files_directory)
        created_directories.append("/" + files_directory)
        for root, _, files in os.walk(folder):
            for file in files:
                full_path = os.path.join(root, file)
                with (open(full_path, "rb").read()) as text_io_wrapper:
                    content = text_io_wrapper
                    path_in_iso = '/' + files_directory + \
                        self.__adjust_folder_name(full_path[len(folder)::1]).upper()
                    if path_in_iso not in created_directories:
                        iso.add_directory(path_in_iso)
                        created_directories.append(path_in_iso)
                    iso.add_fp(BytesIO(content), len(content), path_in_iso + '/' + file.upper() + ';1')
        iso.write(iso_file)
        iso.close()

    @GeneralUtilities.check_arguments
    def SCCreateISOFileWithObfuscatedFiles(self, inputfolder: str, outputfile: str, printtableheadline, createisofile, extensions) -> None:
        if (os.path.isdir(inputfolder)):
            namemappingfile = "name_map.csv"
            files_directory = inputfolder
            files_directory_obf = f"{files_directory}_Obfuscated"
            self.SCObfuscateFilesFolder(
                inputfolder, printtableheadline, namemappingfile, extensions)
            os.rename(namemappingfile, os.path.join(
                files_directory_obf, namemappingfile))
            if createisofile:
                self.__create_iso(files_directory_obf, outputfile)
                shutil.rmtree(files_directory_obf)
        else:
            raise ValueError(f"Directory not found: '{inputfolder}'")

    @GeneralUtilities.check_arguments
    def SCFilenameObfuscator(self, inputfolder: str, printtableheadline, namemappingfile: str, extensions: str) -> None:
        obfuscate_all_files = extensions == "*"
        if (obfuscate_all_files):
            obfuscate_file_extensions = None
        else:
            obfuscate_file_extensions = extensions.split(",")
        if (os.path.isdir(inputfolder)):
            printtableheadline = GeneralUtilities.string_to_boolean(
                printtableheadline)
            files = []
            if not os.path.isfile(namemappingfile):
                with open(namemappingfile, "a", encoding="utf-8"):
                    pass
            if printtableheadline:
                GeneralUtilities.append_line_to_file(
                    namemappingfile, "Original filename;new filename;SHA2-hash of file")
            for file in GeneralUtilities.absolute_file_paths(inputfolder):
                if os.path.isfile(os.path.join(inputfolder, file)):
                    if obfuscate_all_files or self.__extension_matchs(file, obfuscate_file_extensions):
                        files.append(file)
            for file in files:
                hash_value = GeneralUtilities.get_sha256_of_file(file)
                extension = Path(file).suffix
                new_file_name_without_path = str(uuid.uuid4())[0:8] + extension
                new_file_name = os.path.join(
                    os.path.dirname(file), new_file_name_without_path)
                os.rename(file, new_file_name)
                GeneralUtilities.append_line_to_file(namemappingfile, os.path.basename(file) + ";" + new_file_name_without_path + ";" + hash_value)
        else:
            raise ValueError(f"Directory not found: '{inputfolder}'")

    @GeneralUtilities.check_arguments
    def __extension_matchs(self, file: str, obfuscate_file_extensions) -> bool:
        for extension in obfuscate_file_extensions:
            if file.lower().endswith("."+extension.lower()):
                return True
        return False

    @GeneralUtilities.check_arguments
    def SCHealthcheck(self, file: str) -> int:
        lines = GeneralUtilities.read_lines_from_file(file)
        for line in reversed(lines):
            if not GeneralUtilities.string_is_none_or_whitespace(line):
                if "RunningHealthy (" in line:  # TODO use regex
                    GeneralUtilities.write_message_to_stderr(f"Healthy running due to line '{line}' in file '{file}'.")
                    return 0
                else:
                    GeneralUtilities.write_message_to_stderr(f"Not healthy running due to line '{line}' in file '{file}'.")
                    return 1
        GeneralUtilities.write_message_to_stderr(f"No valid line found for healthycheck in file '{file}'.")
        return 2

    @GeneralUtilities.check_arguments
    def SCObfuscateFilesFolder(self, inputfolder: str, printtableheadline, namemappingfile: str, extensions: str) -> None:
        obfuscate_all_files = extensions == "*"
        if (obfuscate_all_files):
            obfuscate_file_extensions = None
        else:
            if "," in extensions:
                obfuscate_file_extensions = extensions.split(",")
            else:
                obfuscate_file_extensions = [extensions]
        newd = inputfolder+"_Obfuscated"
        shutil.copytree(inputfolder, newd)
        inputfolder = newd
        if (os.path.isdir(inputfolder)):
            for file in GeneralUtilities.absolute_file_paths(inputfolder):
                if obfuscate_all_files or self.__extension_matchs(file, obfuscate_file_extensions):
                    self.SCChangeHashOfProgram(file)
                    os.remove(file)
                    os.rename(file + ".modified", file)
            self.SCFilenameObfuscator(inputfolder, printtableheadline, namemappingfile, extensions)
        else:
            raise ValueError(f"Directory not found: '{inputfolder}'")

    @GeneralUtilities.check_arguments
    def get_services_from_yaml_file(self, yaml_file: str) -> list[str]:
        with open(yaml_file, encoding="utf-8") as stream:
            loaded = yaml.safe_load(stream)
            services = loaded["services"]
            result = list(services.keys())
            return result

    @GeneralUtilities.check_arguments
    def kill_docker_container(self, container_name: str) -> None:
        self.run_program("docker", f"container rm -f {container_name}")

    @GeneralUtilities.check_arguments
    def get_latest_apt_package_version_in_debian(self, image: str,package:str) -> str:
        #docker run --rm -it debian bash -c "apt update && apt list -a tor"
        output=self.run_with_epew("docker", f"run --rm -it {image} bash -c \"apt --color=false update && apt --color=false list -a tor\"",os.getcwd(),encode_argument_in_base64=True)
        stdout=output[1]
        version_lines=[line.strip() for line in GeneralUtilities.string_to_lines(stdout) if GeneralUtilities.string_has_nonwhitespace_content(line) and line.startswith(package+"/")]
        GeneralUtilities.assert_condition(0<len(version_lines), f"No version found for package '{package}' in image '{image}'.")
        versions = [version_line.split(" ")[1] for version_line in version_lines]
        def my_comparer(a, b) -> int:
            # return:
            #  -1 → a < b
            #   0 → a = b
            #   1 → a > b
            # dpkg --compare-versions <a> lt <b>  → exit 0 wenn a < b
            def dpkg_compare(op: str) -> bool:
                result = self.run_program_argsasarray("docker", [ "run", "--rm",image, "dpkg", "--compare-versions", a, op, b],throw_exception_if_exitcode_is_not_zero=False)
                GeneralUtilities.assert_condition(result[1]==GeneralUtilities.empty_string)
                GeneralUtilities.assert_condition(result[2]==GeneralUtilities.empty_string)
                return result[0] == 0

            if dpkg_compare("lt"): # a < b
                return -1
            elif dpkg_compare("gt"): # a > b
                return 1
            else:
                return 0
        sorted_versions = sorted(versions, key=cmp_to_key(my_comparer))
        return sorted_versions[-1]

    @GeneralUtilities.check_arguments
    def run_testcases_for_python_project(self, repository_folder: str):
        self.assert_is_git_repository(repository_folder)
        self.run_program("coverage", "run -m pytest", repository_folder)
        self.run_program("coverage", "xml", repository_folder)
        GeneralUtilities.ensure_directory_exists(os.path.join(repository_folder, "Other/TestCoverage"))
        coveragefile = os.path.join(repository_folder, "Other/TestCoverage/TestCoverage.xml")
        GeneralUtilities.ensure_file_does_not_exist(coveragefile)
        os.rename(os.path.join(repository_folder, "coverage.xml"), coveragefile)

    @GeneralUtilities.check_arguments
    def get_file_permission(self, file: str) -> str:
        """This function returns an usual octet-triple, for example "700"."""
        ls_output: str = self.run_ls_for_folder(file)
        return self.__get_file_permission_helper(ls_output)

    @GeneralUtilities.check_arguments
    def __get_file_permission_helper(self, permissions: str) -> str:
        return str(self.__to_octet(permissions[0:3])) + str(self.__to_octet(permissions[3:6]))+str(self.__to_octet(permissions[6:9]))

    @GeneralUtilities.check_arguments
    def __to_octet(self, string: str) -> int:
        return int(self.__to_octet_helper(string[0]) + self.__to_octet_helper(string[1])+self.__to_octet_helper(string[2]), 2)

    @GeneralUtilities.check_arguments
    def __to_octet_helper(self, string: str) -> str:
        if (string == "-"):
            return "0"
        else:
            return "1"

    @GeneralUtilities.check_arguments
    def get_file_owner(self, file: str) -> str:
        """This function returns the user and the group in the format "user:group"."""
        ls_output: str = self.run_ls_for_folder(file)
        return self.__get_file_owner_helper(ls_output)

    @GeneralUtilities.check_arguments
    def __get_file_owner_helper(self, ls_output: str) -> str:
        splitted = ls_output.split()
        return f"{splitted[2]}:{splitted[3]}"

    @GeneralUtilities.check_arguments
    def get_file_owner_and_file_permission(self, file: str) -> str:
        ls_output: str = self.run_ls_for_folder(file)
        return [self.__get_file_owner_helper(ls_output), self.__get_file_permission_helper(ls_output)]

    @GeneralUtilities.check_arguments
    def run_ls_for_folder(self, file_or_folder: str) -> str:
        file_or_folder = file_or_folder.replace("\\", "/")
        GeneralUtilities.assert_condition(os.path.isfile(file_or_folder) or os.path.isdir(file_or_folder), f"Can not execute 'ls -ld' because '{file_or_folder}' does not exist.")
        ls_result = self.run_program_argsasarray("ls", ["-ld", file_or_folder])
        GeneralUtilities.assert_condition(ls_result[0] == 0, f"'ls -ld {file_or_folder}' resulted in exitcode {str(ls_result[0])}. StdErr: {ls_result[2]}")
        GeneralUtilities.assert_condition(not GeneralUtilities.string_is_none_or_whitespace(ls_result[1]), f"'ls -ld' of '{file_or_folder}' had an empty output. StdErr: '{ls_result[2]}'")
        output = ls_result[1]
        result = output.replace("\n", GeneralUtilities.empty_string)
        result = ' '.join(result.split())   # reduce multiple whitespaces to one
        return result

    @GeneralUtilities.check_arguments
    def run_ls_for_folder_content(self, file_or_folder: str) -> list[str]:
        file_or_folder = file_or_folder.replace("\\", "/")
        GeneralUtilities.assert_condition(os.path.isfile(file_or_folder) or os.path.isdir(file_or_folder), f"Can not execute 'ls -la' because '{file_or_folder}' does not exist.")
        ls_result = self.run_program_argsasarray("ls", ["-la", file_or_folder])
        GeneralUtilities.assert_condition(ls_result[0] == 0, f"'ls -la {file_or_folder}' resulted in exitcode {str(ls_result[0])}. StdErr: {ls_result[2]}")
        GeneralUtilities.assert_condition(not GeneralUtilities.string_is_none_or_whitespace(ls_result[1]), f"'ls -la' of '{file_or_folder}' had an empty output. StdErr: '{ls_result[2]}'")
        output = ls_result[1]
        result = output.split("\n")[3:]  # skip the lines with "Total", "." and ".."
        result = [' '.join(line.split()) for line in result]  # reduce multiple whitespaces to one
        return result

    @GeneralUtilities.check_arguments
    def set_permission(self, file_or_folder: str, permissions: str, recursive: bool = False) -> None:
        """This function expects an usual octet-triple, for example "700"."""
        args = []
        if recursive:
            args.append("--recursive")
        args.append(permissions)
        args.append(file_or_folder)
        self.run_program_argsasarray("chmod", args)

    @GeneralUtilities.check_arguments
    def set_owner(self, file_or_folder: str, owner: str, recursive: bool = False, follow_symlinks: bool = False) -> None:
        """This function expects the user and the group in the format "user:group"."""
        args = []
        if recursive:
            args.append("--recursive")
        if follow_symlinks:
            args.append("--no-dereference")
        args.append(owner)
        args.append(file_or_folder)
        self.run_program_argsasarray("chown", args)

    # <run programs>

    @GeneralUtilities.check_arguments
    def __run_program_argsasarray_async_helper(self, program: str, arguments_as_array: list[str] = [], working_directory: str = None, print_errors_as_information: bool = False, log_file: str = None, timeoutInSeconds: int = None, addLogOverhead: bool = False, title: str = None, log_namespace: str = "", arguments_for_log:  list[str] = None, custom_argument: object = None, interactive: bool = False, env_vars: dict = None) -> Popen:
        popen: Popen = self.program_runner.run_program_argsasarray_async_helper(program, arguments_as_array, working_directory, custom_argument, interactive, env_vars)
        return popen

    @staticmethod
    def __enqueue_output(file: IO, queue: Queue):
        for line in iter(file.readline, ''):
            queue.put(line)
        file.close()

    @staticmethod
    def __continue_process_reading(pid: int, p: Popen, q_stdout: Queue, q_stderr: Queue, reading_stdout_last_time_resulted_in_exception: bool, reading_stderr_last_time_resulted_in_exception: bool):
        if p.poll() is None:
            return True

        # if reading_stdout_last_time_resulted_in_exception and reading_stderr_last_time_resulted_in_exception:
        #    return False

        if not q_stdout.empty():
            return True

        if not q_stderr.empty():
            return True

        return False

    @staticmethod
    def __read_popen_pipes(p: Popen, print_live_output: bool, print_errors_as_information: bool, log: SCLog, timeoutInSeconds: int = None) -> tuple[list[str], list[str]]:
        p_id = p.pid
        # "timeoutInSeconds" is the maximal total runtime of the process. None or a non-positive value means "no timeout".
        # Without this the loop below would wait forever for a process which never terminates (e.g. a hanging child-process).
        timeout_enabled: bool = timeoutInSeconds is not None and 0 < timeoutInSeconds
        start_time: float = time.monotonic()
        timed_out: bool = False
        with ThreadPoolExecutor(2) as pool:
            q_stdout = Queue()
            q_stderr = Queue()

            pool.submit(ScriptCollectionCore.__enqueue_output, p.stdout, q_stdout)
            pool.submit(ScriptCollectionCore.__enqueue_output, p.stderr, q_stderr)
            reading_stdout_last_time_resulted_in_exception: bool = False
            reading_stderr_last_time_resulted_in_exception: bool = False

            stdout_result: list[str] = []
            stderr_result: list[str] = []

            while (ScriptCollectionCore.__continue_process_reading(p_id, p, q_stdout, q_stderr, reading_stdout_last_time_resulted_in_exception, reading_stderr_last_time_resulted_in_exception)):
                try:
                    while not q_stdout.empty():
                        out_line: str = q_stdout.get_nowait()
                        out_line = out_line.replace("\r", GeneralUtilities.empty_string).replace("\n", GeneralUtilities.empty_string)
                        if GeneralUtilities.string_has_content(out_line):
                            stdout_result.append(out_line)
                            reading_stdout_last_time_resulted_in_exception = False
                            if print_live_output:
                                loglevel = LogLevel.Information
                                if out_line.startswith("Debug: "):
                                    loglevel = LogLevel.Debug
                                    out_line = out_line[len("Debug: "):]
                                if out_line.startswith("Diagnostic: "):
                                    loglevel = LogLevel.Diagnostic
                                    out_line = out_line[len("Diagnostic: "):]
                                log.log(out_line, loglevel)
                except Empty:
                    reading_stdout_last_time_resulted_in_exception = True

                try:
                    while not q_stderr.empty():
                        err_line: str = q_stderr.get_nowait()
                        err_line = err_line.replace("\r", GeneralUtilities.empty_string).replace("\n", GeneralUtilities.empty_string)
                        if GeneralUtilities.string_has_content(err_line):
                            stderr_result.append(err_line)
                            reading_stderr_last_time_resulted_in_exception = False
                            if print_live_output:
                                loglevel = LogLevel.Error
                                if err_line.startswith("Warning: "):
                                    loglevel = LogLevel.Warning
                                    err_line = err_line[len("Warning: "):]
                                if print_errors_as_information:  # "errors" in "print_errors_as_information" means: all what is written to std-err
                                    loglevel = LogLevel.Information
                                log.log(err_line, loglevel)
                except Empty:
                    reading_stderr_last_time_resulted_in_exception = True

                if timeout_enabled and timeoutInSeconds < (time.monotonic() - start_time):
                    timed_out = True
                    p.kill()  # the process exceeded its timeout; kill it so the reader-threads get EOF and this loop ends.
                    break

                time.sleep(0.01)  # this is required to not finish too early

            if timed_out:
                raise TimeoutError(f"The process with process-id {p_id} did not finish within the configured timeout of {timeoutInSeconds} second(s) and was killed.")
            return (stdout_result, stderr_result)

    @GeneralUtilities.check_arguments
    def run_program_argsasarray(self, program: str, arguments_as_array: list[str] = [], working_directory: str = None, print_errors_as_information: bool = False, log_file: str = None, timeoutInSeconds: int = None, addLogOverhead: bool = False, title: str = None, log_namespace: str = "", arguments_for_log:  list[str] = None, throw_exception_if_exitcode_is_not_zero: bool = True, custom_argument: object = None, interactive: bool = False, print_live_output: bool = False, env_vars: dict = None) -> tuple[int, str, str, int]:
        if self.call_program_runner_directly:
            return self.program_runner.run_program_argsasarray(program, arguments_as_array, working_directory, custom_argument, interactive, env_vars)
        try:
            GeneralUtilities.assert_not_null(arguments_as_array,"arguments_as_array must not be null")
            arguments_as_str = ' '.join(arguments_as_array)
            mock_loader_result = self.__try_load_mock(program, arguments_as_str, working_directory)
            if mock_loader_result[0]:
                return mock_loader_result[1]
            
            if self.program_runner.will_be_executed_locally():
                working_directory = self.__adapt_workingdirectory(working_directory)

            if arguments_for_log is None or len(arguments_for_log)==0:
                arguments_for_log = arguments_as_array

            cmd = f'{GeneralUtilities.str_none_safe(working_directory)}>{program}'
            if 0 < len(arguments_for_log):
                arguments_for_log_as_string: str = ' '.join([f'"{argument_for_log}"' for argument_for_log in arguments_for_log])
                cmd = f'{cmd} {arguments_for_log_as_string}'

            if GeneralUtilities.string_is_none_or_whitespace(title):
                info_for_log = cmd
            else:
                info_for_log = title

            self.log.log(f"Run '{info_for_log}'.", LogLevel.Debug)

            exit_code: int = None
            stdout: str = GeneralUtilities.empty_string
            stderr: str = GeneralUtilities.empty_string
            pid: int = None

            with self.__run_program_argsasarray_async_helper(program, arguments_as_array, working_directory,  print_errors_as_information, log_file, timeoutInSeconds, addLogOverhead, title, log_namespace, arguments_for_log, custom_argument, interactive, env_vars) as process:

                if log_file is not None:
                    GeneralUtilities.ensure_file_exists(log_file)
                pid = process.pid

                outputs: tuple[list[str], list[str]] = ScriptCollectionCore.__read_popen_pipes(process, print_live_output, print_errors_as_information, self.log, timeoutInSeconds)

                for out_line_plain in outputs[0]:
                    if out_line_plain is not None:
                        out_line: str = None
                        if isinstance(out_line_plain, str):
                            out_line = out_line_plain
                        elif isinstance(out_line_plain, bytes):
                            out_line = GeneralUtilities.bytes_to_string(out_line_plain)
                        else:
                            raise ValueError(f"Unknown type of output: {str(type(out_line_plain))}")

                        if out_line is not None and GeneralUtilities.string_has_content(out_line):
                            if out_line.endswith("\n"):
                                out_line = out_line[:-1]
                            if 0 < len(stdout):
                                stdout = stdout+"\n"
                            stdout = stdout+out_line
                            if log_file is not None:
                                GeneralUtilities.append_line_to_file(log_file, out_line)

                for err_line_plain in outputs[1]:
                    if err_line_plain is not None:
                        err_line: str = None
                        if isinstance(err_line_plain, str):
                            err_line = err_line_plain
                        elif isinstance(err_line_plain, bytes):
                            err_line = GeneralUtilities.bytes_to_string(err_line_plain)
                        else:
                            raise ValueError(f"Unknown type of output: {str(type(err_line_plain))}")
                        if err_line is not None and GeneralUtilities.string_has_content(err_line):
                            if err_line.endswith("\n"):
                                err_line = err_line[:-1]
                            if 0 < len(stderr):
                                stderr = stderr+"\n"
                            stderr = stderr+err_line
                            if log_file is not None:
                                GeneralUtilities.append_line_to_file(log_file, err_line)

            exit_code = process.returncode
            GeneralUtilities.assert_condition(exit_code is not None, f"Exitcode of program-run of '{info_for_log}' is None.")

            result_message = f"Program '{info_for_log}' resulted in exitcode {exit_code}."

            self.log.log(result_message, LogLevel.Debug)

            if throw_exception_if_exitcode_is_not_zero and exit_code != 0:
                raise ValueError(f"{result_message} (StdOut: '{stdout}', StdErr: '{stderr}')")

            result = (exit_code, stdout, stderr, pid)
            return result
        except Exception as e:#pylint:disable=unused-variable, try-except-raise
            raise

    # Return-values program_runner: Exitcode, StdOut, StdErr, Pid
    @GeneralUtilities.check_arguments
    def run_program_with_retry(self, program: str, arguments:  str = "", working_directory: str = None,  print_errors_as_information: bool = False, log_file: str = None, timeoutInSeconds: int = None, addLogOverhead: bool = False, title: str = None, log_namespace: str = "", arguments_for_log:  str = None, throw_exception_if_exitcode_is_not_zero: bool = True, custom_argument: object = None, interactive: bool = False, print_live_output: bool = False, amount_of_attempts: int = 5, delay_in_seconds: int = 2, env_vars: dict = None) -> tuple[int, str, str, int]:
        return GeneralUtilities.retry_action(lambda: self.run_program(program, arguments, working_directory, print_errors_as_information, log_file, timeoutInSeconds, addLogOverhead, title, log_namespace,arguments_for_log, throw_exception_if_exitcode_is_not_zero, custom_argument, interactive, print_live_output, env_vars), amount_of_attempts, delay_in_seconds=delay_in_seconds)

    # Return-values program_runner: Exitcode, StdOut, StdErr, Pid
    @GeneralUtilities.check_arguments
    def run_program(self, program: str, arguments:  str = "", working_directory: str = None,  print_errors_as_information: bool = False, log_file: str = None, timeoutInSeconds: int = None, addLogOverhead: bool = False, title: str = None, log_namespace: str = "", arguments_for_log:  str = None, throw_exception_if_exitcode_is_not_zero: bool = True, custom_argument: object = None, interactive: bool = False, print_live_output: bool = False, env_vars: dict = None) -> tuple[int, str, str, int]:
        if self.call_program_runner_directly:
            return self.program_runner.run_program(program, arguments, working_directory, custom_argument, interactive, env_vars)
        return self.run_program_argsasarray(program, GeneralUtilities.arguments_to_array(arguments), working_directory,  print_errors_as_information, log_file, timeoutInSeconds, addLogOverhead, title, log_namespace, GeneralUtilities.arguments_to_array(arguments_for_log), throw_exception_if_exitcode_is_not_zero, custom_argument, interactive, print_live_output, env_vars)

    @GeneralUtilities.check_arguments
    def path_is_allowed_within_base_folder(self, path: str, base_folder: str, excluded_folders: list[str]) -> bool:
        """Returns True if and only if 'path' is located within 'base_folder' (equal to 'base_folder' or a subpath of it)
        AND 'path' is NOT located within any of the 'excluded_folders' (neither equal to nor a subpath of any of them).
        Returns False if 'path' is outside 'base_folder', or if 'path' is equal to or located inside one of the
        'excluded_folders'.
        Path-resolution: a relative 'base_folder' is resolved against the current working-directory; a relative 'path' and
        relative entries of 'excluded_folders' are resolved against 'base_folder'."""
        resolved_base_folder = GeneralUtilities.resolve_relative_path(base_folder, os.getcwd())
        resolved_path = GeneralUtilities.resolve_relative_path(path, resolved_base_folder)
        normalized_base_folder = os.path.normcase(os.path.normpath(resolved_base_folder))
        normalized_path = os.path.normcase(os.path.normpath(resolved_path))
        # 1. path must be equal to or located inside base_folder
        if not (normalized_path == normalized_base_folder or normalized_path.startswith(normalized_base_folder + os.sep)):
            return False
        # 2. path must not be equal to or located inside any excluded folder
        for excluded_folder in excluded_folders:
            resolved_excluded_folder = GeneralUtilities.resolve_relative_path(excluded_folder, resolved_base_folder)
            normalized_excluded_folder = os.path.normcase(os.path.normpath(resolved_excluded_folder))
            if normalized_path == normalized_excluded_folder or normalized_path.startswith(normalized_excluded_folder + os.sep):
                return False
        # 3. path is inside base_folder and not inside any excluded folder
        return True

    @GeneralUtilities.check_arguments
    def run_command_in_folder(self, base_folder: str, command: str, arguments: str, actual_folder: str, excluded_folders: list[str] = None) -> int:
        """Runs the given command with the given arguments in base_folder, but only if actual_folder is allowed according to
        path_is_allowed_within_base_folder, i.e. actual_folder is equal to base_folder or a subfolder of it and is not located
        inside one of the excluded_folders. A relative base_folder is resolved against the current working-directory; a
        relative actual_folder and relative entries of excluded_folders are resolved against base_folder. actual_folder can be
        used in arguments by using the placeholder "{actual_folder}"."""
        if excluded_folders is None:
            excluded_folders = []
        resolved_base_folder = GeneralUtilities.resolve_relative_path(base_folder, os.getcwd())
        resolved_actual_folder = GeneralUtilities.resolve_relative_path(actual_folder, resolved_base_folder)
        if not self.path_is_allowed_within_base_folder(actual_folder, base_folder, excluded_folders):
            raise ValueError(f"The folder '{resolved_actual_folder}' is not allowed: it must be equal to or a subfolder of the base-folder '{resolved_base_folder}' and must not be located inside one of the excluded folders.")
        effective_arguments = arguments.replace(ScriptCollectionCore.run_command_in_folder_actual_folder_placeholder, resolved_actual_folder)
        result = self.run_program(command, effective_arguments, resolved_base_folder,print_live_output=True)
        return result[0]

    # Return-values program_runner: Exitcode, StdOut, StdErr, Pid
    @GeneralUtilities.check_arguments
    def run_program_argsasarray_with_retry(self, program: str, arguments_as_array: list[str] = [], working_directory: str = None,  print_errors_as_information: bool = False, log_file: str = None, timeoutInSeconds: int = None, addLogOverhead: bool = False, title: str = None, log_namespace: str = "", arguments_for_log:  list[str] = None, throw_exception_if_exitcode_is_not_zero: bool = True, custom_argument: object = None, interactive: bool = False, print_live_output: bool = False, amount_of_attempts: int = 5, delay_in_seconds: int = 2, env_vars: dict = None) -> tuple[int, str, str, int]:
        return GeneralUtilities.retry_action(lambda: self.run_program_argsasarray(program, arguments_as_array, working_directory, print_errors_as_information, log_file, timeoutInSeconds, addLogOverhead, title, log_namespace,arguments_for_log, throw_exception_if_exitcode_is_not_zero, custom_argument, interactive, print_live_output, env_vars), amount_of_attempts, delay_in_seconds=delay_in_seconds)


    # Return-values program_runner: Pid
    @GeneralUtilities.check_arguments
    def run_program_argsasarray_async(self, program: str, arguments_as_array: list[str] = [], working_directory: str = None,  print_errors_as_information: bool = False, log_file: str = None, timeoutInSeconds: int = None, addLogOverhead: bool = False, title: str = None, log_namespace: str = "", arguments_for_log:  list[str] = None, custom_argument: object = None, interactive: bool = False, env_vars: dict = None) -> int:
        if self.call_program_runner_directly:
            return self.program_runner.run_program_argsasarray_async(program, arguments_as_array, working_directory, custom_argument, interactive, env_vars)
        mock_loader_result = self.__try_load_mock(program, ' '.join(arguments_as_array), working_directory)
        if mock_loader_result[0]:
            return mock_loader_result[1]
        process: Popen = self.__run_program_argsasarray_async_helper(program, arguments_as_array, working_directory,  print_errors_as_information, log_file, timeoutInSeconds, addLogOverhead, title, log_namespace, arguments_for_log, custom_argument, interactive, env_vars)
        return process.pid

    # Return-values program_runner: Pid
    @GeneralUtilities.check_arguments
    def run_program_async(self, program: str, arguments: str = "",  working_directory: str = None,print_errors_as_information: bool = False, log_file: str = None, timeoutInSeconds: int = None, addLogOverhead: bool = False, title: str = None, log_namespace: str = "", arguments_for_log:  list[str] = None, custom_argument: object = None, interactive: bool = False, env_vars: dict = None) -> int:
        if self.call_program_runner_directly:
            return self.program_runner.run_program_argsasarray_async(program, arguments, working_directory, custom_argument, interactive, env_vars)
        return self.run_program_argsasarray_async(program, GeneralUtilities.arguments_to_array(arguments), working_directory,  print_errors_as_information, log_file, timeoutInSeconds, addLogOverhead, title, log_namespace, arguments_for_log, custom_argument, interactive, env_vars)

    @GeneralUtilities.check_arguments
    def __try_load_mock(self, program: str, arguments: str, working_directory: str) -> tuple[bool, tuple[int, str, str, int]]:
        if self.mock_program_calls:
            try:
                return [True, self.__get_mock_program_call(program, arguments, working_directory)]
            except LookupError:
                if not self.execute_program_really_if_no_mock_call_is_defined:
                    raise
        return [False, None]

    @GeneralUtilities.check_arguments
    def __adapt_workingdirectory(self, workingdirectory: str) -> str:
        result: str = None
        if workingdirectory is None:
            result = os.getcwd()
        else:
            if os.path.isabs(workingdirectory):
                result = workingdirectory
            else:
                result = GeneralUtilities.resolve_relative_path_from_current_working_directory(workingdirectory)
        if not os.path.isdir(result):
            raise ValueError(f"Working-directory '{workingdirectory}' does not exist.")
        return result

    @GeneralUtilities.check_arguments
    def verify_no_pending_mock_program_calls(self):
        if (len(self.__mocked_program_calls) > 0):
            raise AssertionError("The following mock-calls were not called:\n"+",\n    ".join([self.__format_mock_program_call(r) for r in self.__mocked_program_calls]))

    @GeneralUtilities.check_arguments
    def __format_mock_program_call(self, r) -> str:
        r: ScriptCollectionCore.__MockProgramCall = r
        return f"'{r.workingdirectory}>{r.program} {r.argument}' (" \
            f"exitcode: {GeneralUtilities.str_none_safe(str(r.exit_code))}, " \
            f"pid: {GeneralUtilities.str_none_safe(str(r.pid))}, "\
            f"stdout: {GeneralUtilities.str_none_safe(str(r.stdout))}, " \
            f"stderr: {GeneralUtilities.str_none_safe(str(r.stderr))})"

    @GeneralUtilities.check_arguments
    def register_mock_program_call(self, program: str, argument: str, workingdirectory: str, result_exit_code: int, result_stdout: str, result_stderr: str, result_pid: int, amount_of_expected_calls=1):
        "This function is for test-purposes only"
        for _ in itertools.repeat(None, amount_of_expected_calls):
            mock_call = ScriptCollectionCore.__MockProgramCall()
            mock_call.program = program
            mock_call.argument = argument
            mock_call.workingdirectory = workingdirectory
            mock_call.exit_code = result_exit_code
            mock_call.stdout = result_stdout
            mock_call.stderr = result_stderr
            mock_call.pid = result_pid
            self.__mocked_program_calls.append(mock_call)

    @GeneralUtilities.check_arguments
    def __get_mock_program_call(self, program: str, argument: str, workingdirectory: str):
        result: ScriptCollectionCore.__MockProgramCall = None
        for mock_call in self.__mocked_program_calls:
            if ((re.match(mock_call.program, program) is not None)
               and (re.match(mock_call.argument, argument) is not None)
               and (re.match(mock_call.workingdirectory, workingdirectory) is not None)):
                result = mock_call
                break
        if result is None:
            raise LookupError(f"Tried to execute mock-call '{workingdirectory}>{program} {argument}' but no mock-call was defined for that execution")
        else:
            self.__mocked_program_calls.remove(result)
            return (result.exit_code, result.stdout, result.stderr, result.pid)

    @GeneralUtilities.check_arguments
    class __MockProgramCall:
        program: str = None
        argument: str = None
        workingdirectory: str = None
        exit_code: int = None
        stdout: str = None
        stderr: str = None
        pid: int = None

    @GeneralUtilities.check_arguments
    def run_with_epew_with_retry(self, program: str, argument: str = "", working_directory: str = None, print_errors_as_information: bool = False, log_file: str = None, timeoutInSeconds: int = None, addLogOverhead: bool = False, title: str = None, log_namespace: str = "", arguments_for_log:  str =None, throw_exception_if_exitcode_is_not_zero: bool = True, custom_argument: object = None, interactive: bool = False,print_live_output:bool=False,encode_argument_in_base64:bool=False, amount_of_attempts: int = 3, delay_in_seconds: int = 2) -> tuple[int, str, str, int]:
        return GeneralUtilities.retry_action(lambda: self.run_with_epew(program, argument, working_directory, print_errors_as_information, log_file, timeoutInSeconds, addLogOverhead, title, log_namespace,arguments_for_log, throw_exception_if_exitcode_is_not_zero, custom_argument, interactive, print_live_output,encode_argument_in_base64), amount_of_attempts, delay_in_seconds=delay_in_seconds)

    @GeneralUtilities.check_arguments
    def run_with_epew(self, program: str, argument: str = "", working_directory: str = None, print_errors_as_information: bool = False, log_file: str = None, timeoutInSeconds: int = None, addLogOverhead: bool = False, title: str = None, log_namespace: str = "", arguments_for_log:  str =None, throw_exception_if_exitcode_is_not_zero: bool = True, custom_argument: object = None, interactive: bool = False,print_live_output:bool=False,encode_argument_in_base64:bool=False) -> tuple[int, str, str, int]:
        epew_argument:list[str]=["-p",program ,"-w", working_directory]
        if encode_argument_in_base64:
            if arguments_for_log is None:
                argument_escaped=argument.replace("\"", "\\\"")
                arguments_for_log=epew_argument+["-a",f"\"{argument_escaped}\""]
            base64_string = base64.b64encode(argument.encode("utf-8")).decode("utf-8")
            epew_argument=epew_argument+["-a",base64_string,"-b"]
        else:
            epew_argument=epew_argument+["-a",argument]
            if arguments_for_log is None:
                arguments_for_log=epew_argument
        return self.run_program_argsasarray("epew", epew_argument, working_directory, print_errors_as_information, log_file, timeoutInSeconds, addLogOverhead, title, log_namespace, arguments_for_log, throw_exception_if_exitcode_is_not_zero, custom_argument, interactive,print_live_output=print_live_output)


    # </run programs>

    @GeneralUtilities.check_arguments
    def extract_archive_with_7z(self, unzip_program_file: str, zip_file: str, password: str, output_directory: str) -> None:
        password_set = not password is None
        file_name = Path(zip_file).name
        file_folder = os.path.dirname(zip_file)
        argument = "x"
        if password_set:
            argument = f"{argument} -p\"{password}\""
        argument = f"{argument} -o {output_directory}"
        argument = f"{argument} {file_name}"
        return self.run_program(unzip_program_file, argument, file_folder)

    @GeneralUtilities.check_arguments
    def get_internet_time(self) -> datetime:
        response = ntplib.NTPClient().request('pool.ntp.org')
        return datetime.fromtimestamp(response.tx_time)

    @GeneralUtilities.check_arguments
    def system_time_equals_internet_time(self, maximal_tolerance_difference: timedelta) -> bool:
        return abs(GeneralUtilities.get_now() - self.get_internet_time()) < maximal_tolerance_difference

    @GeneralUtilities.check_arguments
    def system_time_equals_internet_time_with_default_tolerance(self) -> bool:
        return self.system_time_equals_internet_time(self.__get_default_tolerance_for_system_time_equals_internet_time())

    @GeneralUtilities.check_arguments
    def check_system_time(self, maximal_tolerance_difference: timedelta):
        if not self.system_time_equals_internet_time(maximal_tolerance_difference):
            raise ValueError("System time may be wrong")

    @GeneralUtilities.check_arguments
    def check_system_time_with_default_tolerance(self) -> None:
        self.check_system_time(self.__get_default_tolerance_for_system_time_equals_internet_time())

    @GeneralUtilities.check_arguments
    def __get_default_tolerance_for_system_time_equals_internet_time(self) -> timedelta:
        return timedelta(hours=0, minutes=0, seconds=3)

    @GeneralUtilities.check_arguments
    def increment_version(self, input_version: str, increment_major: bool, increment_minor: bool, increment_patch: bool) -> str:
        splitted = input_version.split(".")
        GeneralUtilities.assert_condition(len(splitted) == 3, f"Version '{input_version}' does not have the 'major.minor.patch'-pattern.")
        major = int(splitted[0])
        minor = int(splitted[1])
        patch = int(splitted[2])
        if increment_major:
            major = major+1
        if increment_minor:
            minor = minor+1
        if increment_patch:
            patch = patch+1
        return f"{major}.{minor}.{patch}"

    @GeneralUtilities.check_arguments
    def get_semver_version_from_gitversion(self, repository_folder: str) -> str:
        self.assert_is_git_repository(repository_folder)
        if (self.git_repository_has_commits(repository_folder)):
            has_tags=self.git_repository_has_tags(repository_folder)
            if has_tags:
                repo_has_uncommitted_changes=self.git_repository_has_uncommitted_changes(repository_folder)
                current_commit_is_on_tag=self.get_current_git_commit_has_tag(repository_folder)
                current_branch_name:str=self.git_get_current_branch_name(repository_folder)
                latest_version_tag=self.get_latest_git_tag(repository_folder)
                current_version=latest_version_tag[1:]#remove "v"-prefix
                if current_branch_name in ("main", "master", "stable"):
                    GeneralUtilities.assert_condition(not repo_has_uncommitted_changes, f"Repository '{repository_folder}' is on branch '{current_branch_name}' and has uncommitted changes. This is not allowed.")
                    GeneralUtilities.assert_condition(current_commit_is_on_tag, f"Repository '{repository_folder}' does not have a tag. This is not allowed.")
                    result = current_version
                else:
                    if current_commit_is_on_tag and not repo_has_uncommitted_changes:
                        result = current_version
                    else:
                        result = self.get_version_from_gitversion(repository_folder, "MajorMinorPatch")
                        if current_commit_is_on_tag and repo_has_uncommitted_changes:
                            result = self.__get_next_version_from_gitversion(repository_folder, current_branch_name)
            else:
                result = "0.1.0"
        else:
            result = "0.1.0"
        return result

    @GeneralUtilities.check_arguments
    def __get_next_version_from_gitversion(self, repository_folder: str, branch_name: str) -> str:
        """
        Computes the version gitversion would assign to the next commit on the given branch.
        This is needed when the current commit is exactly on a tag but the repository has uncommitted changes:
        gitversion treats a tagged commit as a released version and therefore reports the tag-version itself,
        so its result does not reflect that the uncommitted changes will lead to a new (incremented) version.
        Instead of reimplementing gitversion's increment-logic (which is configured per project in GitVersion.yml
        and would inevitably drift from it), a disposable clone is created in which the branch is reproduced and an
        empty commit is added. Gitversion then computes the increment itself - based on the branch-name/-prefix and
        the repository's own GitVersion.yml - while the original working-directory stays untouched.
        Because the result only depends on the committed state and the branch-name, it is memoized per
        (repository_folder, commit_id, branch_name). The in-memory-cache avoids re-cloning within a single process
        (e. g. the many calls during one scbuildcodeunits-run); a persistent cache-file below the repository additionally
        avoids re-cloning across separate process-invocations.
        """
        commit_id = self.git_get_commit_id(repository_folder)
        cache_key = (repository_folder, commit_id, branch_name)
        if cache_key in self.__next_gitversion_cache:#TODO remove __next_gitversion_cache (disk-cache is enough, transient cache here is unnecessary)
            return self.__next_gitversion_cache[cache_key]
        persisted_result = self.__read_next_version_from_disk_cache(repository_folder, commit_id, branch_name)
        if persisted_result is not None:
            self.__next_gitversion_cache[cache_key] = persisted_result
            return persisted_result
        temp_folder = os.path.join(GeneralUtilities.get_temp_folder(), str(uuid.uuid4()))
        try:
            self.git_clone(temp_folder, repository_folder, include_submodules=False)
            # the local clone already checks out the source's current branch on the tagged commit; the explicit checkout only guarantees gitversion sees the correct branch-name (and thus the correct increment-rule)
            self.run_program_argsasarray("git", ["checkout", branch_name], temp_folder, throw_exception_if_exitcode_is_not_zero=True)
            self.run_program("git","-c user.name=\"noname\" -c user.email=\"noname@example.com\" commit -m empty --quiet --allow-empty", temp_folder)
            result = self.get_version_from_gitversion(temp_folder, "MajorMinorPatch")
            self.__next_gitversion_cache[cache_key] = result
            self.__write_next_version_to_disk_cache(repository_folder, commit_id, branch_name, result)
            return result
        finally:
            GeneralUtilities.ensure_directory_does_not_exist(temp_folder)

    @GeneralUtilities.check_arguments
    def get_scriptcollection_repository_cache_folder(self, repository_folder: str) -> str:
        return os.path.join(repository_folder, ".ScriptCollection", "Cache")

    @GeneralUtilities.check_arguments
    def ensure_scriptcollection_gitignore_is_setup(self, repository_folder: str) -> None:
        """Ensures that "<repository>/.ScriptCollection/.gitignore" exists and contains the expected entries."""
        scriptcollection_folder = os.path.join(repository_folder, ".ScriptCollection")
        GeneralUtilities.ensure_directory_exists(scriptcollection_folder)
        gitignore_file = os.path.join(scriptcollection_folder, ".gitignore")
        lines = ["/Cache/"]
        GeneralUtilities.write_lines_to_file(gitignore_file, lines)

    @GeneralUtilities.check_arguments
    def __get_next_version_disk_cache_file(self, repository_folder: str) -> str:
        return os.path.join(self.get_scriptcollection_repository_cache_folder(repository_folder), "GitVersionNextVersion.txt")

    @GeneralUtilities.check_arguments
    def __read_next_version_from_disk_cache(self, repository_folder: str, commit_id: str, branch_name: str) -> str:
        # returns None if there is no cached entry for the given commit and branch. the entries use a tab as separator because git-ref-names can not contain tabs (or any other control-character), so the branch-name can never collide with the separator.
        cache_file = self.__get_next_version_disk_cache_file(repository_folder)
        GeneralUtilities.ensure_directory_exists(os.path.dirname(cache_file))
        GeneralUtilities.ensure_file_exists(cache_file)
        for line in GeneralUtilities.read_nonempty_lines_from_file(cache_file):
            parts = line.split("\t")
            if len(parts) == 3 and parts[0] == commit_id and parts[1] == branch_name:
                return parts[2]
        return None

    @GeneralUtilities.check_arguments
    def __write_next_version_to_disk_cache(self, repository_folder: str, commit_id: str, branch_name: str, version_to_cache: str) -> None:
        # the cache-file lives below ".ScriptCollection/Cache"; ensure the .gitignore is set up first so writing the cache never introduces uncommitted changes.
        self.ensure_scriptcollection_gitignore_is_setup(repository_folder)
        cache_file = self.__get_next_version_disk_cache_file(repository_folder)
        GeneralUtilities.ensure_directory_exists(os.path.dirname(cache_file))
        lines = []
        if os.path.isfile(cache_file):
            for line in GeneralUtilities.read_nonempty_lines_from_file(cache_file):
                parts = line.split("\t")
                if not (len(parts) == 3 and parts[0] == commit_id and parts[1] == branch_name):
                    lines.append(line)
        lines.append(f"{commit_id}\t{branch_name}\t{version_to_cache}")
        GeneralUtilities.write_lines_to_file(cache_file, lines)

    @GeneralUtilities.check_arguments
    def check_python_ast(self, path: str) -> list[tuple[str, int, int, str]]:
        """
        Parses python-source-files with the ast-module to detect syntax-errors without executing them.
        'path' can be a single file (which is checked regardless of its file-extension) or a folder (in which case
        all "*.py"-files below it are checked recursively). Returns one (file, line, column, message)-tuple for every
        file that could not be parsed; an empty list means all checked files are syntactically valid. Raises a
        ValueError if 'path' neither exists as file nor as folder.
        """
        files_to_check: list[str] = []
        if os.path.isfile(path):
            files_to_check.append(path)
        elif os.path.isdir(path):
            for root, _, files in os.walk(path):
                for file in files:
                    if file.endswith(".py"):
                        files_to_check.append(os.path.join(root, file))
        else:
            raise ValueError(f"Path '{path}' does not exist as file or folder.")
        result: list[tuple[str, int, int, str]] = []
        for file in sorted(files_to_check):
            try:
                with open(file, "r", encoding="utf-8") as file_handle:
                    source = file_handle.read()
                ast.parse(source, filename=file)
            except SyntaxError as syntax_error:
                result.append((file, syntax_error.lineno or 0, syntax_error.offset or 0, syntax_error.msg or "Syntax-error"))
            except UnicodeDecodeError as decode_error:
                result.append((file, 0, 0, f"File could not be decoded as utf-8: {decode_error}"))
        return result

    @GeneralUtilities.check_arguments
    def get_real_git_folder(self,repository_folder:str) -> str:
        git_folder = os.path.join(repository_folder, ".git")
        if os.path.isfile(git_folder):
            with open(git_folder, "r", encoding="utf-8") as f:
                line = f.readline().strip()
            prefix = "gitdir:"
            if not line.startswith(prefix):
                raise ValueError(f"Invalid .git file: '{git_folder}'")
            git_dir = line[len(prefix):].strip()
            if not os.path.isabs(git_dir):
                git_dir = os.path.normpath(os.path.join(repository_folder, git_dir))
            if not os.path.isdir(git_dir):
                raise ValueError(f"Resolved git directory '{git_dir}' does not exist.")
            return git_dir
        elif os.path.isdir(git_folder):
            return git_folder
        else:
            raise ValueError(f"Folder '{repository_folder}' is not a git-repository (no .git-folder found).")

    @staticmethod
    @GeneralUtilities.check_arguments
    def is_patch_version(version_string: str) -> bool:
        return not version_string.endswith(".0")

    @GeneralUtilities.check_arguments
    def get_version_from_gitversion(self, folder: str, variable: str) -> str:
        git_folder:str=self.get_real_git_folder(folder)
        cache_folder:str=os.path.join(git_folder,"gitversion_cache")
        GeneralUtilities.ensure_directory_does_not_exist(cache_folder)
        # /nofetch and /nonormalize: avoid network calls / branch normalization (no auth, no DNS, deterministic in containers and offline).
        # called twice as workaround for issue 1877 in gitversion ( https://github.com/GitTools/GitVersion/issues/1877 )
        # timeoutInSeconds: gitversion finishes within seconds on a normal repository; enforce a timeout so a hanging gitversion-process (observed in some build-containers) aborts the build instead of waiting forever.
        gitversion_timeout_in_seconds: int = 300
        result = self.run_program_argsasarray("gitversion", ["/nofetch", "/nonormalize", "/showVariable", variable], folder, timeoutInSeconds=gitversion_timeout_in_seconds)
        result = self.run_program_argsasarray("gitversion", ["/nofetch", "/nonormalize", "/showVariable", variable], folder, timeoutInSeconds=gitversion_timeout_in_seconds)
        result = GeneralUtilities.strip_new_line_character(result[1])
        return result

    @GeneralUtilities.check_arguments
    def generate_certificate_authority(self, folder: str, name: str, subj_c: str, subj_st: str, subj_l: str, subj_o: str, subj_ou: str, days_until_expire: int = None, password: str = None) -> None:
        if days_until_expire is None:
            days_until_expire = 1825
        if password is None:
            password = GeneralUtilities.generate_password()
        GeneralUtilities.ensure_directory_exists(folder)
        self.run_program_argsasarray("openssl", ['req', '-new', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:prime256v1', '-days', str(days_until_expire), '-nodes', '-x509', '-subj', f'/C={subj_c}/ST={subj_st}/L={subj_l}/O={subj_o}/CN={name}/OU={subj_ou}', '-passout', f'pass:{password}', '-keyout', f'{name}.key', '-out', f'{name}.crt'], folder)

    @GeneralUtilities.check_arguments
    def generate_certificate(self, folder: str,  domain: str, filename: str, subj_c: str, subj_st: str, subj_l: str, subj_o: str, subj_ou: str, days_until_expire: int = None, password: str = None) -> None:
        if days_until_expire is None:
            days_until_expire = 397
        if password is None:
            password = GeneralUtilities.generate_password()
        rsa_key_length = 4096
        self.run_program_argsasarray("openssl", ['genrsa', '-out', f'{filename}.key', f'{rsa_key_length}'], folder)
        self.run_program_argsasarray("openssl", ['req', '-new', '-subj', f'/C={subj_c}/ST={subj_st}/L={subj_l}/O={subj_o}/CN={domain}/OU={subj_ou}', '-x509', '-key', f'{filename}.key', '-out', f'{filename}.unsigned.crt', '-days', f'{days_until_expire}'], folder)
        self.run_program_argsasarray("openssl", ['pkcs12', '-export', '-out', f'{filename}.selfsigned.pfx', '-password', f'pass:{password}', '-inkey', f'{filename}.key', '-in', f'{filename}.unsigned.crt'], folder)
        GeneralUtilities.write_text_to_file(os.path.join(folder, f"{filename}.password"), password)
        GeneralUtilities.write_text_to_file(os.path.join(folder, f"{filename}.san.conf"), f"""[ req ]
default_bits        = {rsa_key_length}
distinguished_name  = req_distinguished_name
req_extensions      = v3_req
default_md          = sha256
dirstring_type      = nombstr
prompt              = no

[ req_distinguished_name ]
countryName         = {subj_c}
stateOrProvinceName = {subj_st}
localityName        = {subj_l}
organizationName    = {subj_o}
organizationUnit    = {subj_ou}
commonName          = {domain}

[v3_req]
subjectAltName      = @subject_alt_name

[ subject_alt_name ]
DNS                 = {domain}
""")

    @GeneralUtilities.check_arguments
    def generate_certificate_sign_request(self, folder: str, domain: str, filename: str, subj_c: str, subj_st: str, subj_l: str, subj_o: str, subj_ou: str) -> None:
        self.run_program_argsasarray("openssl", ['req', '-new', '-subj', f'/C={subj_c}/ST={subj_st}/L={subj_l}/O={subj_o}/CN={domain}/OU={subj_ou}', '-key', f'{filename}.key', f'-out', f'{filename}.csr', f'-config', f'{filename}.san.conf'], folder)

    @GeneralUtilities.check_arguments
    def sign_certificate(self, folder: str, ca_folder: str, ca_name: str, domain: str, filename: str, days_until_expire: int = None) -> None:
        if days_until_expire is None:
            days_until_expire = 397
        ca = os.path.join(ca_folder, ca_name)
        password_file = os.path.join(folder, f"{filename}.password")
        password = GeneralUtilities.read_text_from_file(password_file)
        self.run_program_argsasarray("openssl", ['x509', '-req', '-in', f'{filename}.csr', '-CA', f'{ca}.crt', '-CAkey', f'{ca}.key', '-CAcreateserial', '-CAserial', f'{ca}.srl', '-out', f'{filename}.crt', '-days', str(days_until_expire),  '-sha256', '-extensions', 'v3_req', '-extfile', f'{filename}.san.conf'], folder)
        self.run_program_argsasarray("openssl", ['pkcs12', '-export', '-out', f'{filename}.pfx', f'-inkey', f'{filename}.key', '-in', f'{filename}.crt', '-password', f'pass:{password}'], folder)

    @GeneralUtilities.check_arguments
    def update_dependencies_of_python_in_requirementstxt_file(self, file: str, ignored_dependencies: list[str]):
        # TODO consider ignored_dependencies
        lines = GeneralUtilities.read_lines_from_file(file)
        new_lines = []
        for line in lines:
            if GeneralUtilities.string_has_content(line):
                new_lines.append(self.__get_updated_line_for_python_requirements(line.strip()))
        GeneralUtilities.write_lines_to_file(file, new_lines)

    @GeneralUtilities.check_arguments
    def __get_updated_line_for_python_requirements(self, line: str) -> str:
        if "==" in line or "<" in line:
            return line
        elif ">" in line:
            try:
                # line is something like "cyclonedx-bom>=2.0.2" and the function must return with the updated version
                # (something like "cyclonedx-bom>=2.11.0" for example)
                package = line.split(">")[0]
                operator = ">=" if ">=" in line else ">"
                headers = {'Cache-Control': 'no-cache'}
                response = requests.get(f'https://pypi.org/pypi/{package}/json', timeout=5, headers=headers)
                latest_version = response.json()['info']['version']
                # TODO update only minor- and patch-version
                # TODO print info if there is a new major-version
                return package+operator+latest_version
            except:
                return line
        else:
            raise ValueError(f'Unexpected line in requirements-file: "{line}"')

    @GeneralUtilities.check_arguments
    def update_dependencies_of_python_in_setupcfg_file(self, setup_cfg_file: str, ignored_dependencies: list[str]):
        # TODO consider ignored_dependencies
        lines = GeneralUtilities.read_lines_from_file(setup_cfg_file)
        new_lines = []
        requirement_parsing_mode = False
        for line in lines:
            new_line = line
            if (requirement_parsing_mode):
                if ("<" in line or "=" in line or ">" in line):
                    updated_line = f"    {self.__get_updated_line_for_python_requirements(line.strip())}"
                    new_line = updated_line
                else:
                    requirement_parsing_mode = False
            else:
                if line.startswith("install_requires ="):
                    requirement_parsing_mode = True
            new_lines.append(new_line)
        GeneralUtilities.write_lines_to_file(setup_cfg_file, new_lines)

    @GeneralUtilities.check_arguments
    def update_dependencies_of_dotnet_project(self, csproj_file: str,  ignored_dependencies: list[str]):
        folder = os.path.dirname(csproj_file)
        csproj_filename = os.path.basename(csproj_file)
        self.log.log(f"Check for updates in {csproj_filename}", LogLevel.Information)
        result = self.run_program_with_retry("dotnet", f"list {csproj_filename} package --outdated", folder, print_errors_as_information=True)
        for line in result[1].replace("\r", GeneralUtilities.empty_string).split("\n"):
            # Relevant output-lines are something like "    > NJsonSchema             10.7.0        10.7.0      10.9.0"
            if ">" in line:
                package_name = line.replace(">", GeneralUtilities.empty_string).strip().split(" ")[0]
                if not (package_name in ignored_dependencies):
                    self.log.log(f"Update package {package_name}...", LogLevel.Debug)
                    time.sleep(1.1)  # attempt to prevent rate-limit
                    self.run_program_with_retry("dotnet", f"add {csproj_filename} package {package_name}", folder, print_errors_as_information=True)

    @GeneralUtilities.check_arguments
    def create_deb_package(self, toolname: str, binary_folder: str, control_file_content: str, deb_output_folder: str, permission_of_executable_file_as_octet_triple: int) -> None:

        # prepare
        GeneralUtilities.ensure_directory_exists(deb_output_folder)
        temp_folder = os.path.join(GeneralUtilities.get_temp_folder(), str(uuid.uuid4()))
        GeneralUtilities.ensure_directory_exists(temp_folder)
        bin_folder = binary_folder
        tool_content_folder_name = toolname+"Content"

        # create folder
        GeneralUtilities.ensure_directory_exists(temp_folder)
        control_content_folder_name = "controlcontent"
        packagecontent_control_folder = os.path.join(temp_folder, control_content_folder_name)
        GeneralUtilities.ensure_directory_exists(packagecontent_control_folder)
        data_content_folder_name = "datacontent"
        packagecontent_data_folder = os.path.join(temp_folder, data_content_folder_name)
        GeneralUtilities.ensure_directory_exists(packagecontent_data_folder)
        entireresult_content_folder_name = "entireresultcontent"
        packagecontent_entireresult_folder = os.path.join(temp_folder, entireresult_content_folder_name)
        GeneralUtilities.ensure_directory_exists(packagecontent_entireresult_folder)

        # create "debian-binary"-file
        debianbinary_file = os.path.join(packagecontent_entireresult_folder, "debian-binary")
        GeneralUtilities.ensure_file_exists(debianbinary_file)
        GeneralUtilities.write_text_to_file(debianbinary_file, "2.0\n")

        # create control-content

        #  conffiles
        conffiles_file = os.path.join(packagecontent_control_folder, "conffiles")
        GeneralUtilities.ensure_file_exists(conffiles_file)

        #  postinst-script
        postinst_file = os.path.join(packagecontent_control_folder, "postinst")
        GeneralUtilities.ensure_file_exists(postinst_file)
        exe_file = f"/usr/bin/{tool_content_folder_name}/{toolname}"
        link_file = f"/usr/bin/{toolname.lower()}"
        permission = str(permission_of_executable_file_as_octet_triple)
        GeneralUtilities.write_text_to_file(postinst_file, f"""#!/bin/sh
ln -s {exe_file} {link_file}
chmod {permission} {exe_file}
chmod {permission} {link_file}
""")

        #  control
        control_file = os.path.join(packagecontent_control_folder, "control")
        GeneralUtilities.ensure_file_exists(control_file)
        GeneralUtilities.write_text_to_file(control_file, control_file_content)

        #  md5sums
        md5sums_file = os.path.join(packagecontent_control_folder, "md5sums")
        GeneralUtilities.ensure_file_exists(md5sums_file)

        # create data-content

        #  copy binaries
        usr_bin_folder = os.path.join(packagecontent_data_folder, "usr/bin")
        GeneralUtilities.ensure_directory_exists(usr_bin_folder)
        usr_bin_content_folder = os.path.join(usr_bin_folder, tool_content_folder_name)
        GeneralUtilities.copy_content_of_folder(bin_folder, usr_bin_content_folder)

        # create debfile
        deb_filename = f"{toolname}.deb"
        self.run_program_argsasarray("tar", ["czf", f"../{entireresult_content_folder_name}/control.tar.gz", "*"], packagecontent_control_folder)
        self.run_program_argsasarray("tar", ["czf", f"../{entireresult_content_folder_name}/data.tar.gz", "*"], packagecontent_data_folder)
        self.run_program_argsasarray("ar", ["r", deb_filename, "debian-binary", "control.tar.gz", "data.tar.gz"], packagecontent_entireresult_folder)
        result_file = os.path.join(packagecontent_entireresult_folder, deb_filename)
        shutil.copy(result_file, os.path.join(deb_output_folder, deb_filename))

        # cleanup
        GeneralUtilities.ensure_directory_does_not_exist(temp_folder)

    @GeneralUtilities.check_arguments
    def update_year_in_copyright_tags(self, file: str) -> None:
        current_year = str(GeneralUtilities.get_now().year)
        lines = GeneralUtilities.read_lines_from_file(file)
        lines_result = []
        for line in lines:
            if match := re.search("(.*<[Cc]opyright>.*)\\d\\d\\d\\d(.*<\\/[Cc]opyright>.*)", line):
                part1 = match.group(1)
                part2 = match.group(2)
                adapted = part1+current_year+part2
            else:
                adapted = line
            lines_result.append(adapted)
        GeneralUtilities.write_lines_to_file(file, lines_result)

    @GeneralUtilities.check_arguments
    def update_year_in_first_line_of_file(self, file: str) -> None:
        current_year = str(GeneralUtilities.get_now().year)
        lines = GeneralUtilities.read_lines_from_file(file)
        lines[0] = re.sub("\\d\\d\\d\\d", current_year, lines[0])
        GeneralUtilities.write_lines_to_file(file, lines)

    @GeneralUtilities.check_arguments
    def get_external_ip_address(self) -> str:
        information = self.get_externalnetworkinformation_as_json_string()
        parsed = json.loads(information)
        return parsed["IPAddress"]

    @GeneralUtilities.check_arguments
    def get_country_of_external_ip_address(self) -> str:
        information = self.get_externalnetworkinformation_as_json_string()
        parsed = json.loads(information)
        return parsed["Country"]

    @GeneralUtilities.check_arguments
    def get_externalnetworkinformation_as_json_string(self,clientinformation_link:str='https://clientinformation.anion327.de') -> str:
        headers = {'Cache-Control': 'no-cache'}
        response = requests.get(clientinformation_link,  timeout=5, headers=headers)
        network_information_as_json_string = GeneralUtilities.bytes_to_string(response.content)
        return network_information_as_json_string

    @GeneralUtilities.check_arguments
    def change_file_extensions(self, folder: str, from_extension: str, to_extension: str, recursive: bool, ignore_case: bool) -> None:
        extension_to_compare: str = None
        if ignore_case:
            extension_to_compare = from_extension.lower()
        else:
            extension_to_compare = from_extension
        for file in GeneralUtilities.get_direct_files_of_folder(folder):
            if (ignore_case and file.lower().endswith(f".{extension_to_compare}") or not ignore_case and file.endswith(f".{extension_to_compare}")):
                p = Path(file)
                p.rename(p.with_suffix('.'+to_extension))
        if recursive:
            for subfolder in GeneralUtilities.get_direct_folders_of_folder(folder):
                self.change_file_extensions(subfolder, from_extension, to_extension, recursive, ignore_case)

    @GeneralUtilities.check_arguments
    def __add_chapter(self, main_reference_file, reference_content_folder, number: int, chaptertitle: str, content: str = None):
        if content is None:
            content = "TXDX add content here"
        filename = str(number).zfill(2)+"_"+chaptertitle.replace(' ', '-')
        file = f"{reference_content_folder}/{filename}.md"
        full_title = f"{number}. {chaptertitle}"

        GeneralUtilities.append_line_to_file(main_reference_file, f"- [{full_title}](./{filename}.md)")

        GeneralUtilities.ensure_file_exists(file)
        GeneralUtilities.write_text_to_file(file, f"""# {full_title}

{content}
""".replace("XDX", "ODO"))

    @GeneralUtilities.check_arguments
    def generate_arc42_reference_template(self, repository: str, productname: str = None, subfolder: str = None):
        productname: str = None
        if productname is None:
            productname = os.path.basename(repository)
        if subfolder is None:
            subfolder = "Other/Reference"
        reference_root_folder = f"{repository}/{subfolder}"
        reference_content_folder = reference_root_folder + "/Technical"
        if os.path.isdir(reference_root_folder):
            raise ValueError(f"The folder '{reference_root_folder}' does already exist.")
        GeneralUtilities.ensure_directory_exists(reference_root_folder)
        GeneralUtilities.ensure_directory_exists(reference_content_folder)
        main_reference_file = f"{reference_root_folder}/Reference.md"
        GeneralUtilities.ensure_file_exists(main_reference_file)
        GeneralUtilities.write_text_to_file(main_reference_file, f"""# {productname}

TXDX add minimal service-description here.

## Technical documentation

""".replace("XDX", "ODO"))
        self.__add_chapter(main_reference_file, reference_content_folder, 1, 'Introduction and Goals', """## Overview

TXDX

## Quality goals

TXDX

## Stakeholder

| Name | How to contact | Reason |
| ---- | -------------- | ------ |""")
        self.__add_chapter(main_reference_file, reference_content_folder, 2, 'Constraints', """## Technical constraints

| Constraint-identifier | Constraint | Reason |
| --------------------- | ---------- | ------ |

## Organizational constraints

| Constraint-identifier | Constraint | Reason |
| --------------------- | ---------- | ------ |""")
        self.__add_chapter(main_reference_file, reference_content_folder, 3, 'Context and Scope', """## Context

TXDX

## Scope

TXDX""")
        self.__add_chapter(main_reference_file, reference_content_folder, 4, 'Solution Strategy', """TXDX""")
        self.__add_chapter(main_reference_file, reference_content_folder, 5, 'Building Block View', """TXDX""")
        self.__add_chapter(main_reference_file, reference_content_folder, 6, 'Runtime View', """TXDX""")
        self.__add_chapter(main_reference_file, reference_content_folder, 7, 'Deployment View', """## Infrastructure-overview

TXDX

## Infrastructure-requirements

TXDX

## Deployment-proecsses

TXDX""")
        self.__add_chapter(main_reference_file, reference_content_folder, 8, 'Crosscutting Concepts', """TXDX""")
        self.__add_chapter(main_reference_file, reference_content_folder, 9, 'Architectural Decisions', """## Decision-board

| Decision-identifier | Date | Decision | Reason and notes |
| ------------------- | ---- | -------- | ---------------- |""")  # empty because there are no decsions yet
        self.__add_chapter(main_reference_file, reference_content_folder, 10, 'Quality Requirements', """TXDX""")
        self.__add_chapter(main_reference_file, reference_content_folder, 11, 'Risks and Technical Debt', """## Risks

Currently there are no known risks.

## Technical debts

Currently there are no technical depts.""")
        self.__add_chapter(main_reference_file, reference_content_folder, 12, 'Glossary', """## Terms

| Term | Meaning |
| ---- | ------- |

## Abbreviations

| Abbreviation | Meaning |
| ------------ | ------- |""")

        GeneralUtilities.append_to_file(main_reference_file, """

## Responsibilities

| Responsibility  | Name and contact-information |
| --------------- | ---------------------------- |
| Pdocut-owner    | TXDX                         |
| Product-manager | TXDX                         |
| Support         | TXDX                         |

## License & Pricing

TXDX

## External resources

- [Repository](TXDX)
- [Productive-System](TXDX)
- [QualityCheck-system](TXDX)
""".replace("XDX", "ODO"))

    @GeneralUtilities.check_arguments
    def run_with_timeout(self, method, timeout_in_seconds: float) -> bool:
        # Returns true if the method was terminated due to a timeout
        # Returns false if the method terminates in the given time
        p = multiprocessing.Process(target=method)
        p.start()
        p.join(timeout_in_seconds)
        if p.is_alive():
            p.kill()
            p.join()
            return True
        else:
            return False

    @GeneralUtilities.check_arguments
    def ensure_local_docker_network_exists(self, network_name: str) -> None:
        if not self.local_docker_network_exists(network_name):
            self.create_local_docker_network(network_name)

    @GeneralUtilities.check_arguments
    def ensure_local_docker_network_does_not_exist(self, network_name: str) -> None:
        if self.local_docker_network_exists(network_name):
            self.remove_local_docker_network(network_name)

    @GeneralUtilities.check_arguments
    def local_docker_network_exists(self, network_name: str) -> bool:
        return network_name in self.get_all_local_existing_docker_networks()

    @GeneralUtilities.check_arguments
    def get_all_local_existing_docker_networks(self) -> list[str]:
        program_call_result = self.run_program("docker", "network list")
        std_out = program_call_result[1]
        std_out_lines = std_out.split("\n")[1:]
        result: list[str] = []
        for std_out_line in std_out_lines:
            normalized_line = ';'.join(std_out_line.split())
            splitted = normalized_line.split(";")
            result.append(splitted[1])
        return result

    @GeneralUtilities.check_arguments
    def remove_local_docker_network(self, network_name: str) -> None:
        self.run_program("docker", f"network remove {network_name}")

    @GeneralUtilities.check_arguments
    def create_local_docker_network(self, network_name: str) -> None:
        self.run_program("docker", f"network create {network_name}")

    @GeneralUtilities.check_arguments
    def format_xml_file(self, file: str,add_xml_declaration:bool=True) -> None:
        encoding = "utf-8"
        element = ET.XML(GeneralUtilities.read_text_from_file(file, encoding))
        def trim_texts(elem: ET.Element):
            if elem.text:
                elem.text = elem.text.strip()
            if elem.tail:
                elem.tail = elem.tail.strip()
            for child in elem:
                trim_texts(child)
        trim_texts(element)
        ET.indent(element)
        content = ET.tostring(element, xml_declaration=add_xml_declaration, encoding="unicode")
        GeneralUtilities.write_text_to_file(file, content.rstrip("\n") + "\n", encoding)
        self.normalize_line_endings(file)

    @GeneralUtilities.check_arguments
    def format_html_file(self, file: str, add_html_declaration: bool = False) -> None:
        encoding = "utf-8"
        content = GeneralUtilities.read_text_from_file(file, encoding)
        content=self.format_html_content(content, add_html_declaration)
        GeneralUtilities.write_text_to_file(file, content, encoding)
        self.normalize_line_endings(file)

    @GeneralUtilities.check_arguments
    def normalize_line_endings(self, file: str) -> None:
        # Normalizes all physical line-endings of the given file to LF (replaces CRLF and lone CR by LF).
        # Operates on the raw bytes so no character-encoding is assumed and only the line-ending-bytes are
        # touched; the file is only rewritten when its content actually changes.
        content = GeneralUtilities.read_binary_from_file(file)
        normalized_content = content.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        if normalized_content != content:
            GeneralUtilities.write_binary_to_file(file, normalized_content)

    @GeneralUtilities.check_arguments
    def remove_trailing_linebreak(self, file: str) -> None:
        content = GeneralUtilities.read_binary_from_file(file)
        if content.endswith(b"\r\n"):
            GeneralUtilities.write_binary_to_file(file, content[:-2])
        elif content.endswith(b"\n") or content.endswith(b"\r"):
            GeneralUtilities.write_binary_to_file(file, content[:-1])

    @GeneralUtilities.check_arguments
    def format_html_content(self, content: str, add_html_declaration: bool = False) -> str:

        VOID_ELEMENTS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
                         "link", "meta", "param", "source", "track", "wbr"}

        class _Node:
            __slots__ = ("tag", "attrs", "children", "text", "is_void", "raw")
            def __init__(self, tag=None, attrs=(), text=None, is_void=False, raw=None):
                self.tag = tag
                self.attrs = list(attrs)
                self.children = []
                self.text = text
                self.is_void = is_void
                self.raw = raw

        class _Builder(HTMLParser):
            def __init__(self):
                super().__init__(convert_charrefs=False)
                self.root = _Node()
                self.stack = [self.root]

            def _top(self):
                return self.stack[-1]

            def handle_starttag(self, tag, attrs):
                raw = self.get_starttag_text()
                raw_lower = raw.lower()
                original_attrs = []
                pos = 1 + len(tag)
                for lc_name, value in attrs:
                    idx = raw_lower.index(lc_name, pos)
                    original_attrs.append((raw[idx:idx + len(lc_name)], value))
                    pos = idx + len(lc_name)
                node = _Node(tag=tag, attrs=original_attrs, is_void=tag.lower() in VOID_ELEMENTS)
                self._top().children.append(node)
                if not node.is_void:
                    self.stack.append(node)

            def handle_endtag(self, tag):
                if len(self.stack) > 1 and self.stack[-1].tag == tag:
                    self.stack.pop()

            def handle_data(self, data):
                t = " ".join(data.split())
                if t:
                    self._top().children.append(_Node(text=t))

            def handle_entityref(self, name):
                self._top().children.append(_Node(text=f"&{name};"))

            def handle_charref(self, name):
                self._top().children.append(_Node(text=f"&#{name};"))

            def handle_comment(self, data):
                self._top().children.append(_Node(raw=f"<!--{data}-->"))

            def handle_decl(self, decl):
                self._top().children.append(_Node(raw=f"<!{decl}>"))

            def handle_pi(self, data):
                self._top().children.append(_Node(raw=f"<?{data}>"))

        _angular_exprs: list[str] = []

        def _protect_angular(m: re.Match) -> str:
            idx = len(_angular_exprs)
            _angular_exprs.append(m.group(0))
            return f"__ANGEXPR{idx}__"

        protected = re.sub(r'\{\{[\s\S]*?\}\}', _protect_angular, content)
        builder = _Builder()
        builder.feed(protected)
        ind = "  "

        def _serialize(node: _Node, depth: int) -> list:
            prefix = ind * depth
            if node.raw is not None:
                return [prefix + node.raw]
            if node.text is not None:
                return [node.text]
            if node.tag is None:
                out = []
                for c in node.children:
                    out.extend(_serialize(c, depth))
                return out
            attr_str = "".join(f" {n}" if v is None else f' {n}="{v}"' for n, v in node.attrs)
            if node.is_void:
                return [f"{prefix}<{node.tag}{attr_str}>"]
            has_elem_children = any(c.tag is not None for c in node.children)
            if not has_elem_children:
                inner = "".join(c.text or "" for c in node.children)
                return [f"{prefix}<{node.tag}{attr_str}>{inner}</{node.tag}>"]
            lines = [f"{prefix}<{node.tag}{attr_str}>"]
            for c in node.children:
                child_lines = _serialize(c, depth + 1)
                if c.text is not None:
                    lines.append(ind * (depth + 1) + child_lines[0])
                else:
                    lines.extend(child_lines)
            lines.append(f"{prefix}</{node.tag}>")
            return lines

        result = "\n".join(line for line in _serialize(builder.root, 0) if line.strip())
        for i, expr in enumerate(_angular_exprs):
            result = result.replace(f"__ANGEXPR{i}__", expr)
        if add_html_declaration and not result.lstrip().startswith("<!DOCTYPE"):
            result = "<!DOCTYPE html>\n" + result
        return result

    @GeneralUtilities.check_arguments
    def get_pip_index_url_arguments_from_local_cache(self)->list[str]:
        arguments=[]
        pip_folder=GeneralUtilities.normalize_path(self.get_global_cache_folder()+"/Pip")
        if os.path.isdir(pip_folder):
            main_index_file=GeneralUtilities.normalize_path(os.path.join(pip_folder, "MainIndex.txt"))
            if os.path.isfile(main_index_file):
                lines=GeneralUtilities.read_nonempty_lines_from_file(main_index_file)
                url=[line for line in lines if line.startswith("IndexURL: ")][0].split(":", 1)[1].strip()
                arguments.append("--index-url")
                arguments.append(url)
            extra_index_folder=GeneralUtilities.normalize_path(os.path.join(pip_folder, "ExtraIndexURLs"))
            if os.path.isdir(extra_index_folder):
                index_files=GeneralUtilities.get_direct_files_of_folder(extra_index_folder)
                if len(index_files) > 0:
                    for indexurl_file in index_files:
                        lines=GeneralUtilities.read_nonempty_lines_from_file(indexurl_file)
                        url=[line for line in lines if line.startswith("IndexURL: ")][0].split(":", 1)[1].strip()
                        arguments.append("--extra-index-url")
                        arguments.append(url)
        return arguments

    @GeneralUtilities.check_arguments
    def install_requirementstxt_file(self, requirements_txt_file: str):
        folder: str = os.path.dirname(requirements_txt_file)
        filename: str = os.path.basename(requirements_txt_file)
        arguments= ["install", "-r", filename]
        for argument in self.get_pip_index_url_arguments_from_local_cache():
            arguments.append(argument)
        self.run_program_argsasarray("pip", arguments, folder,print_live_output=self.log.loglevel==LogLevel.Debug)

    @GeneralUtilities.check_arguments
    def ocr_analysis_of_folder_using_local_docker_image(self, folder: str, extensions: list[str], languages: list[str],base_folder_for_entry: str,ignore_pattern:list[str] ) -> list[str]:  # Returns a list of changed files due to ocr-analysis.
        #TODO start docker server
        serviceaddress:str=None#TODO
        self.ocr_analysis_of_folder(folder, serviceaddress, extensions, languages, base_folder_for_entry,ignore_pattern)
        #TODO stop docker server

    @GeneralUtilities.check_arguments
    def ocr_analysis_of_folder(self, folder: str, serviceaddress: str, extensions: list[str], languages: list[str],base_folder_for_entry: str,ignore_pattern:list[str] ) -> list[str]:  # Returns a list of changed files due to ocr-analysis.
        supported_extensions = ['png', 'jpg', 'jpeg', 'tiff', 'bmp', 'gif', 'pdf', 'docx', 'doc', 'xlsx', 'xls', 'pptx', 'ppt']
        changes_files: list[str] = []
        if base_folder_for_entry is None:
            base_folder_for_entry=folder
        if extensions is None:
            extensions = supported_extensions
        for file in GeneralUtilities.get_direct_files_of_folder(folder):
            if GeneralUtilities.is_ignored_by_glob_pattern(os.path.dirname(file),file,ignore_pattern):
                continue
            file_lower = file.lower()
            for extension in extensions:
                if file_lower.endswith("."+extension):
                    if self.ocr_analysis_of_file(file, serviceaddress, languages,base_folder_for_entry):
                        changes_files.append(file)
                    break
        for subfolder in GeneralUtilities.get_direct_folders_of_folder(folder):
            if GeneralUtilities.is_ignored_by_glob_pattern(os.path.dirname(subfolder),subfolder,ignore_pattern):
                continue
            for file in self.ocr_analysis_of_folder(subfolder, serviceaddress, extensions, languages,base_folder_for_entry+"/"+os.path.basename(subfolder), ignore_pattern):
                changes_files.append(file)
        return changes_files


    @GeneralUtilities.check_arguments
    def __it_supported_extension(self, file: str, supported_extensions: list[str]) -> bool:
        file_lower = file.lower()
        for extension in supported_extensions:
            if file_lower.endswith("."+extension):
                return True
        return False
    
    @GeneralUtilities.check_arguments
    def ocr_analysis_of_file(self, file: str, serviceaddress: str, languages: list[str], readable_folder_entry:str ) -> bool:  # Returns true if the ocr-file was generated or updated. Returns false if the existing ocr-file was not changed.
        supported_extensions = ['png', 'jpg', 'jpeg', 'tiff', 'bmp', 'webp', 'gif', 'pdf', 'rtf', 'docx', 'doc', 'odt', 'xlsx', 'xls', 'ods', 'pptx', 'ppt', 'odp']
        if not self.__it_supported_extension(file, supported_extensions):
            raise ValueError(f"File '{file}' is not supported due to unsupported extension. Supported extensions are: {', '.join(supported_extensions)}")
        target_file = file+".ocr.txt"
        hash_of_current_file: str = GeneralUtilities.get_sha256_of_file(file)
        try:
            if os.path.isfile(target_file):
                lines = GeneralUtilities.read_lines_from_file(target_file)
                previous_hash_of_current_file: str = lines[1].split(":")[1].strip()
                if hash_of_current_file == previous_hash_of_current_file:
                    return False
        except:
            pass
        GeneralUtilities.write_message_to_stdout(f"Starting OCR-analysis of file \"{file}\"...")
        ocr_content = self.get_ocr_content_of_file(file, serviceaddress, languages)
        GeneralUtilities.ensure_file_exists(target_file)
        if readable_folder_entry is None:
            readable_folder_entry="."
        readable_folder_entry=readable_folder_entry.replace("\\", "/")
        GeneralUtilities.write_text_to_file(target_file, f"""Name of file: \"{readable_folder_entry}/{os.path.basename(file)}\""
Hash of file: {hash_of_current_file}
OCR-content:
{ocr_content}""")
        return True

    @GeneralUtilities.check_arguments
    def get_ocr_content_of_file(self, file: str, serviceaddress: str, languages: list[str]) -> str:
        result: str = None
        extension = Path(file).suffix[1:]
        mime_types = {
            "pdf": "application/pdf",
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "txt": "text/plain",
            "json": "application/json",
            "doc": "application/msword",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "xls": "application/vnd.ms-excel",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }
        if serviceaddress is None:
            server_url_file:str= GeneralUtilities.normalize_path(f"{str(Path.home())}/.ScriptCollection/OCR/ServiceURL.txt")
            if os.path.isfile(server_url_file):
                for line in GeneralUtilities.read_nonempty_lines_from_file(server_url_file):
                    if not line.startswith("#"):
                        serviceaddress = line.strip()
                        break
        GeneralUtilities.assert_not_null(serviceaddress, "ocr-service-address must not be null.")
        mime_type = mime_types.get(extension.lower(), "application/octet-stream")
        service_url: str = f"{serviceaddress}/API/v1/SimpleOCR/GetOCRContent?mimeType={mime_type}"
        for language in languages:
            service_url = service_url + f"&languages={language}"
        headers = {'Cache-Control': 'no-cache'}
        with open(file, "rb") as f:
            files_to_analyse = {
                "fileContent": (os.path.basename(file), f, mime_type)
            }
            r = requests.put(service_url, timeout=3600, headers=headers, files=files_to_analyse,verify=True)
            if r.status_code != 200:
                if r.status_code == 400:
                    return f"Could not calculate ocr-content for file \"{file}\". File may be broken."
                else:
                    raise ValueError(f"Retrieving ocr-content for file \"{file}\" resulted in HTTP-response-code {r.status_code}.")

            result = GeneralUtilities.bytes_to_string(r.content)
        return result

    @GeneralUtilities.check_arguments
    def ocr_analysis_of_repository(self, folder: str, serviceaddress: str, extensions: list[str], languages: list[str]) -> None:
        self.assert_is_git_repository(folder)
        self.ocr_analysis_of_folder(folder, serviceaddress, extensions, languages,".",[".git"])

    @GeneralUtilities.check_arguments
    def update_timestamp_in_file(self, target_file: str) -> None:
        lines = GeneralUtilities.read_lines_from_file(target_file)
        new_lines = []
        prefix: str = "# last update: "
        for line in lines:
            if line.startswith(prefix):
                new_lines.append(prefix+GeneralUtilities.datetime_to_string_for_readable_entry(GeneralUtilities.get_now(),False))
            else:
                new_lines.append(line)
        GeneralUtilities.write_lines_to_file(target_file, new_lines)

    @GeneralUtilities.check_arguments
    def do_and_log_task(self, name_of_task: str, task,log_end_of_Task:bool=True)->int:
        try:
            self.log.log(f"Start action \"{name_of_task}\".", LogLevel.Information)
            result = task()
            if result is None:
                result = 0
            return result
        except Exception as e:
            self.log.log_exception(f"Error while running action \"{name_of_task}\".", e, LogLevel.Error)
            return 1
        finally:
            if log_end_of_Task:
                self.log.log(f"Finished action \"{name_of_task}\".", LogLevel.Information)


    default_excluded_patterns_for_loc: list[str] = ["**.txt", "**.md", "**.svg", "**.xlf", "**.vscode", "**/Resources/**", "**/Reference/**", ".gitignore", ".gitattributes", "Other/Metrics/**"]

    @GeneralUtilities.check_arguments
    def get_lines_of_code_with_default_excluded_patterns(self, repository: str) -> int:
        return self.get_lines_of_code(repository, self.default_excluded_patterns_for_loc)

    @GeneralUtilities.check_arguments
    def get_lines_of_code(self, repository: str, excluded_pattern: list[str]) -> int:
        self.assert_is_git_repository(repository)
        result: int = 0
        self.log.log(f"Calculate lines of code in repository '{repository}' with excluded patterns: {', '.join(excluded_pattern)}",LogLevel.Debug)
        git_response = self.run_program("git", "ls-files", repository)
        files: list[str] = GeneralUtilities.string_to_lines(git_response[1])
        for file in files:
            if os.path.isfile(os.path.join(repository, file)):
                if self.__is_excluded_by_glob_pattern(file, excluded_pattern):
                    self.log.log(f"File '{file}' is ignored because it matches an excluded pattern.",LogLevel.Diagnostic)
                else:
                    full_file: str = os.path.join(repository, file)
                    if GeneralUtilities.is_binary_file(full_file):
                        self.log.log(f"File '{file}' is ignored because it is a binary-file.",LogLevel.Diagnostic)
                    else:
                        self.log.log(f"Count lines of file '{file}'.",LogLevel.Diagnostic)
                        length = len(GeneralUtilities.read_nonempty_lines_from_file(full_file))
                        result = result+length
            else:
                self.log.log(f"File '{file}' is ignored because it does not exist.",LogLevel.Diagnostic)
        return result

    @GeneralUtilities.check_arguments
    def __is_excluded_by_glob_pattern(self, file: str, excluded_patterns: list[str]) -> bool:
        for pattern in excluded_patterns:
            if fnmatch.fnmatch(file, pattern):
                return True
        return False
    
    @GeneralUtilities.check_arguments
    def create_zip_archive(self, folder:str,zip_file:str) -> None:
        GeneralUtilities.assert_folder_exists(folder)
        GeneralUtilities.assert_file_does_not_exist(zip_file)
        folder = os.path.abspath(folder)
        with zipfile.ZipFile(zip_file, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(folder):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, start=folder)
                    zipf.write(file_path, arcname)

    @GeneralUtilities.check_arguments
    def start_local_test_service(self, file: str):
        example_folder = os.path.dirname(file)
        docker_compose_file = os.path.join(example_folder, "docker-compose.yml")
        for service in self.get_services_from_yaml_file(docker_compose_file):
            self.kill_docker_container(service)
        example_name = os.path.basename(example_folder)
        title = f"Test{example_name}"
        in_build_container = self.is_running_in_build_container()
        generated_ports_override_file = GeneralUtilities.empty_string
        argument = "compose"
        if not in_build_container:
            # Locally the test-process runs directly on the host (not inside the docker-network), so the container-ports (declared as "expose" in the
            # compose-file) have to be published to the host. To avoid a committed override-file this publish-mapping is generated on the fly into a
            # temporary file. In the build-container nothing is published at all (see below) to avoid host-port-conflicts.
            generated_ports_override_file = self.__generate_localhost_ports_override_file(docker_compose_file)
            if generated_ports_override_file != GeneralUtilities.empty_string:
                argument = argument+f" -f docker-compose.yml -f {generated_ports_override_file}"
        argument = argument+f" -p {title.lower()}"
        if os.path.isfile(os.path.join(example_folder,"Parameters.env")):
            argument=argument+" --env-file Parameters.env"
        argument=argument+" up --detach"
        if in_build_container:
            # In a DooD-setup the test-service-containers are siblings on the docker-daemon and resolve their bind-mount-sources against the DAEMON's
            # filesystem, not against this build-container's filesystem. Clearing the source-folders from within this build-container (as the *Start.py-
            # scripts do) therefore does not reset what the containers actually mount. Reset them daemon-side first so that e.g. a database starts on a
            # clean data-directory instead of stale content (which could otherwise keep an outdated pg_hba.conf and reject the build-container's connection).
            self.__reset_compose_bind_mounted_volumes_daemon_side(docker_compose_file, example_folder, title.lower())
        try:
            self.run_program("docker", argument, example_folder, title=title,print_live_output=True)
        finally:
            if generated_ports_override_file != GeneralUtilities.empty_string:
                GeneralUtilities.ensure_file_does_not_exist(generated_ports_override_file)
        if in_build_container:
            # Inside the build-container the docker-socket points at a daemon on which the test-service-containers are created as SIBLING-containers
            # attached to the (external) compose-network. The build-container itself is not attached to that network, so without the following step it
            # could neither route to the container-IPs nor use the docker-DNS (which results in connection-timeouts even though the container-name can
            # be resolved via /etc/hosts). Therefore the build-container is attached to every (external) network the compose-file uses. No port is
            # published to the host, so concurrent pipelines on the same host do not conflict on host-ports.
            self.__connect_build_container_to_compose_networks(docker_compose_file)
            # In addition the container-names are mapped to their current container-IPs in the /etc/hosts of this build-container so that the
            # container-names can be used in the connection-strings even if the docker-DNS is not consulted. The managed block is rewritten on each
            # start because the containers get a new IP every time.
            self.__register_test_service_containers_in_etc_hosts(docker_compose_file)

    @GeneralUtilities.check_arguments
    def __reset_compose_bind_mounted_volumes_daemon_side(self, docker_compose_file: str, example_folder: str, project_name: str) -> None:
        # Empties the bind-mounted directories of all compose-services on the DAEMON's filesystem, i.e. exactly where the (sibling-)containers will mount
        # them. In a DooD-setup a bind-mount-source like "./Volumes/..." is resolved by the docker-daemon and not inside this build-container, so deleting
        # the folder from within this build-container does not reset what e.g. a database-container mounts (which would otherwise start on stale data, like
        # an outdated pg_hba.conf). The directories are emptied via a throwaway-container of the service's own image (compose resolves the image and mounts
        # the volumes exactly like for the real container); only the directory-content is removed, not the mount-root itself. Failures are tolerated because
        # a not-yet existing source-directory simply needs no clearing.
        env_file_arguments: list[str] = []
        if os.path.isfile(os.path.join(example_folder, "Parameters.env")):
            env_file_arguments = ["--env-file", "Parameters.env"]
        with open(docker_compose_file, encoding="utf-8") as stream:
            loaded = yaml.safe_load(stream)
        services = loaded.get("services", dict())
        for service_name, service_definition in services.items():
            service_definition = service_definition or dict()
            for volume in service_definition.get("volumes", list()):
                source = None
                target = None
                if isinstance(volume, str):
                    volume_parts = volume.split(":")
                    if 2 <= len(volume_parts):
                        source = volume_parts[0]
                        target = volume_parts[1]
                elif isinstance(volume, dict):
                    if volume.get("type", "bind") == "bind":
                        source = volume.get("source")
                        target = volume.get("target")
                if not GeneralUtilities.string_has_content(source) or not GeneralUtilities.string_has_content(target):
                    continue
                # Named volumes (a source without a path-indicator) are managed by docker itself and must not be cleared this way.
                if not (source.startswith(".") or source.startswith("/") or source.startswith("~")):
                    continue
                # Empty the directory-content using only a POSIX-shell (no dependency on "find"/"-delete", which busybox-based images may not provide). The
                # three globs cover normal entries, dotfiles and double-dot-prefixed entries (but never "." or ".."); the trailing "; true" keeps the
                # exitcode at 0 even when a glob does not expand (already-empty directory). This works for any service-image that ships a shell (which all
                # real stateful images do); images without a shell (distroless/scratch) do not have a resettable bind-mounted data-directory here anyway.
                clear_command = f"rm -rf \"{target}\"/..?* \"{target}\"/.[!.]* \"{target}\"/* 2>/dev/null; true"
                self.run_program_argsasarray("docker", ["compose", "-p", project_name] + env_file_arguments + ["run", "--rm", "--no-deps", "--entrypoint", "sh", service_name, "-c", clear_command], example_folder, throw_exception_if_exitcode_is_not_zero=False)

    @GeneralUtilities.check_arguments
    def __generate_localhost_ports_override_file(self, docker_compose_file: str) -> str:
        with open(docker_compose_file, encoding="utf-8") as stream:
            loaded = yaml.safe_load(stream)
        services = loaded.get("services", dict())
        override_services = dict()
        for service_name, service_definition in services.items():
            exposed_ports = service_definition.get("expose", list())
            if 0 < len(exposed_ports):
                # Each exposed container-port is published to the same port on the host (e.g. "5432" -> "5432:5432").
                override_services[service_name] = {"ports": [f"{exposed_port}:{exposed_port}" for exposed_port in exposed_ports]}
        if 0 == len(override_services):
            return GeneralUtilities.empty_string
        override_file = os.path.join(GeneralUtilities.get_temp_folder(), f"docker-compose.localhost.{str(uuid.uuid4())}.yml")
        with open(override_file, "w", encoding="utf-8") as stream:
            yaml.safe_dump({"services": override_services}, stream)
        return override_file

    @GeneralUtilities.check_arguments
    def __get_own_container_id(self) -> str:
        # Determines the id of the container this process currently runs in. The hostname usually equals the short container-id, but a runner can override
        # the hostname, so the id is derived from the mountinfo-/cgroup-entries instead. Docker bind-mounts files like /etc/hostname, /etc/hosts and
        # /etc/resolv.conf from /var/lib/docker/containers/<full-id>/..., so the OWN full container-id appears in a "docker/containers/<id>"-path-segment.
        # A plain 64-hex-search is NOT sufficient because mountinfo can also contain other 64-hex-ids (most notably anonymous-volume-ids under
        # /var/lib/docker/volumes/<id>/_data, but also layer-ids) which are not container-ids and would cause a "No such container"-error when used for
        # "docker network connect". Therefore container-id-specific patterns are collected first and (where the docker-daemon is reachable) each candidate
        # is verified to actually be a known container; only then a broader 64-hex-search and finally the hostname are used as fallbacks.
        specific_container_id_patterns = [
            re.compile(r"docker/containers/([0-9a-f]{64})"),  # own id via the bind-mounted /etc/*-files (most reliable)
            re.compile(r"docker[-/]([0-9a-f]{64})"),           # cgroup-style: /docker/<id> (cgroup v1) or docker-<id>.scope (systemd-cgroup)
            re.compile(r"kubepods[^\n]*?([0-9a-f]{64})"),      # kubernetes-pods
        ]
        broad_container_id_pattern = re.compile(r"([0-9a-f]{64})")
        specific_candidate_ids: list[str] = []
        broad_candidate_ids: list[str] = []
        for proc_file in ["/proc/self/mountinfo", "/proc/self/cgroup"]:
            if not os.path.isfile(proc_file):
                continue
            try:
                content = GeneralUtilities.read_text_from_file(proc_file)
            except Exception:
                continue
            for pattern in specific_container_id_patterns:
                for match in pattern.finditer(content):
                    if match.group(1) not in specific_candidate_ids:
                        specific_candidate_ids.append(match.group(1))
            for match in broad_container_id_pattern.finditer(content):
                if match.group(1) not in broad_candidate_ids:
                    broad_candidate_ids.append(match.group(1))
        # Prefer a specific candidate that the docker-daemon actually knows (this reliably filters out volume-/layer-ids); fall back to the first specific
        # candidate if the daemon is not reachable here at all.
        for candidate_id in specific_candidate_ids:
            inspect_result = self.run_program_argsasarray("docker", ["inspect", "-f", "{{.Id}}", candidate_id], throw_exception_if_exitcode_is_not_zero=False)
            if inspect_result[0] == 0:
                return candidate_id
        if 0 < len(specific_candidate_ids):
            return specific_candidate_ids[0]
        for candidate_id in broad_candidate_ids:
            inspect_result = self.run_program_argsasarray("docker", ["inspect", "-f", "{{.Id}}", candidate_id], throw_exception_if_exitcode_is_not_zero=False)
            if inspect_result[0] == 0:
                return candidate_id
        if 0 < len(broad_candidate_ids):
            return broad_candidate_ids[0]
        if os.path.isfile("/etc/hostname"):
            return GeneralUtilities.read_text_from_file_without_linebreak("/etc/hostname").strip()
        return GeneralUtilities.empty_string

    @GeneralUtilities.check_arguments
    def __connect_build_container_to_compose_networks(self, docker_compose_file: str) -> None:
        # Attaches THIS build-container to every (external) network used by the compose-file so that the test-service-containers (which are
        # sibling-containers on the same docker-daemon) become routable and resolvable. The docker-socket is shared with the daemon, but the
        # network-namespace of the build-container is not, so without attaching there is no network-path to the container-IPs.
        own_container_id = self.__get_own_container_id()
        if not GeneralUtilities.string_has_content(own_container_id):
            return
        with open(docker_compose_file, encoding="utf-8") as stream:
            loaded = yaml.safe_load(stream)
        networks = loaded.get("networks", dict())
        for network_key, network_definition in networks.items():
            network_definition = network_definition or dict()
            network_name = network_definition.get("name", network_key)
            inspect_result = self.run_program_argsasarray("docker", ["network", "inspect", "-f", "{{range $id, $c := .Containers}}{{$id}}\n{{end}}", network_name], throw_exception_if_exitcode_is_not_zero=False)
            if inspect_result[0] != 0:
                continue  # The network does not exist (yet); nothing to attach to.
            # The keys of .Containers are full container-ids; the hostname (own_container_id) is the corresponding short-id (a prefix of it).
            connected_container_ids = [line.strip() for line in inspect_result[1].splitlines() if GeneralUtilities.string_has_content(line)]
            already_connected = any(connected_container_id.startswith(own_container_id) for connected_container_id in connected_container_ids)
            if not already_connected:
                # Attaching this build-container to the compose-network is REQUIRED for the test-process to reach the test-service-containers. If it fails,
                # the tests would otherwise resolve the container-name (via /etc/hosts) but have no network-route to the container-IP and only fail later
                # with a misleading connection-timeout. Therefore the attach must fail loudly here with the actual docker-error (e.g. "No such container"
                # or "network not found") instead of being swallowed.
                self.run_program_argsasarray("docker", ["network", "connect", network_name, own_container_id], throw_exception_if_exitcode_is_not_zero=True)

    @GeneralUtilities.check_arguments
    def __disconnect_build_container_from_compose_networks(self, docker_compose_file: str) -> None:
        # Detaches THIS build-container again from every (external) network used by the compose-file. This is the inverse of
        # __connect_build_container_to_compose_networks and is run before "compose down" so the network can be removed without leaving a stale/null
        # network-reference on the build-container (which would otherwise break the GitHub-runner "Stop containers"-post-step). Failures are ignored on
        # purpose: the network might already be gone, or the build-container might never have been attached (e.g. the attach failed or did not run).
        own_container_id = self.__get_own_container_id()
        if not GeneralUtilities.string_has_content(own_container_id):
            return
        if not os.path.isfile(docker_compose_file):
            return
        with open(docker_compose_file, encoding="utf-8") as stream:
            loaded = yaml.safe_load(stream)
        networks = loaded.get("networks", dict())
        for network_key, network_definition in networks.items():
            network_definition = network_definition or dict()
            network_name = network_definition.get("name", network_key)
            self.run_program_argsasarray("docker", ["network", "disconnect", "-f", network_name, own_container_id], throw_exception_if_exitcode_is_not_zero=False)

    @GeneralUtilities.check_arguments
    def __register_test_service_containers_in_etc_hosts(self, docker_compose_file: str) -> None:
        # Maps the container-names of the test-services to their current container-IPs in the /etc/hosts of THIS build-container (neither the runner-host
        # nor the test-service-containers are touched). The managed block is rewritten on each start because the containers get a new IP every time.
        hosts_file = "/etc/hosts"
        if not os.path.isfile(hosts_file):
            return
        with open(docker_compose_file, encoding="utf-8") as stream:
            loaded = yaml.safe_load(stream)
        services = loaded.get("services", dict())
        entries: list[str] = []
        for service_name, service_definition in services.items():
            container_name = service_definition.get("container_name", service_name)
            inspect_result = self.run_program_argsasarray("docker", ["inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}", container_name], throw_exception_if_exitcode_is_not_zero=False)
            if inspect_result[0] != 0:
                continue
            ip_addresses = [ip_address for ip_address in inspect_result[1].split() if GeneralUtilities.string_has_content(ip_address)]
            if 0 < len(ip_addresses):
                entries.append(f"{ip_addresses[0]}\t{container_name}")
        start_marker = "# >>> scriptcollection-test-service-hosts (managed automatically; do not edit)"
        end_marker = "# <<< scriptcollection-test-service-hosts"
        with open(hosts_file, "r", encoding="utf-8") as stream:
            content = stream.read()
        # Remove a previously written block first so stale IPs of already-recreated containers do not shadow the current ones.
        content = re.sub(re.escape(start_marker)+".*?"+re.escape(end_marker)+r"\n?", GeneralUtilities.empty_string, content, flags=re.DOTALL)
        content = content.rstrip("\n")+"\n"
        if 0 < len(entries):
            content = content+start_marker+"\n"+"\n".join(entries)+"\n"+end_marker+"\n"
        with open(hosts_file, "w", encoding="utf-8") as stream:
            stream.write(content)

    @GeneralUtilities.check_arguments
    def stop_local_test_service(self, file: str):
        example_folder = os.path.dirname(file)
        example_name = os.path.basename(example_folder)
        title = f"Test{example_name}"
        if self.is_running_in_build_container():
            # Inverse of __connect_build_container_to_compose_networks (see start_local_test_service): detach THIS build-container from the compose-networks
            # BEFORE "compose down" removes them. Otherwise "compose down" removes a network this build-container is still attached to, which leaves a
            # stale/null network-reference on the build-container. The GitHub-runner adds an automatic post-job "Stop containers"-step (present whenever a
            # job uses "container:") that enumerates the build-container's networks to disconnect them; that stale entry then makes it fail with
            # "Value cannot be null. (Parameter 'network')". Disconnecting here first leaves the build-container attached only to the runner-managed
            # job-network, so the cleanup finds a consistent state.
            self.__disconnect_build_container_from_compose_networks(os.path.join(example_folder, "docker-compose.yml"))
        self.run_program("docker", f"compose -p {title.lower()} down", example_folder, title=title,print_live_output=True)

    @GeneralUtilities.check_arguments
    def generate_chart_diagram(self,source_file:str,target_file:str):
        workingfolder=os.path.dirname(source_file)
        argument=f"\"{source_file}\" \"{target_file}\""
        loglevelMap = {
            LogLevel.Error: "error",
            LogLevel.Warning: "warn",
            LogLevel.Information: "info",
            LogLevel.Debug: "debug",
        }
        if self.log.loglevel==LogLevel.Debug:
            argument=f"-l {loglevelMap[self.log.loglevel]} {argument}"
        self.run_with_epew("vl2svg",argument,workingfolder,encode_argument_in_base64=True)
        #this uses vega-light. to use vega "vg2svg" should be used instead.

    @GeneralUtilities.check_arguments
    def inspect_container(self, container_name: str) :
        program_result = self.run_program(
            "docker",
            f"inspect {container_name}",
            throw_exception_if_exitcode_is_not_zero=True
        )
        stdout=program_result[1]

        data = json.loads(stdout)
        GeneralUtilities.assert_condition(len(data)==1,f"Unexpected array-length of docker-inspect-output for container \"{container_name}\".")
        return data[0]

    @GeneralUtilities.check_arguments
    def container_is_exists(self,container_name:str)->bool:
        program_result = self.run_program(
            "docker",
            f"inspect {container_name}",
            throw_exception_if_exitcode_is_not_zero=False
        )
        return program_result[0]==0

    @GeneralUtilities.check_arguments
    def container_is_running(self,container_name:str)->bool:
        data = self.inspect_container( container_name)
        if data is None:
            return False

        return data["State"]["Status"] == "running"

    @GeneralUtilities.check_arguments
    def container_is_healthy(self,container_name:str)->bool:
        data = self.inspect_container( container_name)
        if data is None:
            return False

        state = data["State"]
        health = state.get("Health")

        if health is None:
            return False  # kein HEALTHCHECK definiert

        return health["Status"] == "healthy"

    @GeneralUtilities.check_arguments
    def get_output_of_container(self,container_name:str)->str:
    
        program_result= self.run_program_argsasarray(
            "docker",
            ["logs",container_name],
            throw_exception_if_exitcode_is_not_zero=False
        )
        exit_code=program_result[0]
        stdout=program_result[1]
        stderr=program_result[2]
        if exit_code != 0:
            return ""

        return stdout+"\n"+stderr

    @GeneralUtilities.check_arguments
    def container_is_running_and_healthy(self,container_name:str)->bool:
        if not self.container_is_exists(container_name):
            return False
        if not self.container_is_running(container_name):
            return False
        if not self.container_is_healthy(container_name):
            return False
        return True

    def reclaim_space_from_docker(self,remove_containers:bool,remove_volumes:bool,remove_images:bool, amount_of_attempts: int = 5):
        self.log.log("Reclaim disk space from docker...",LogLevel.Debug)
        if remove_containers:
            self.run_program_with_retry("docker","container prune -f",amount_of_attempts=amount_of_attempts)
        if remove_volumes:
            self.run_program_with_retry("docker","volume prune -f",amount_of_attempts=amount_of_attempts)
        if remove_images:
            self.run_program_with_retry("docker","image prune -a -f",amount_of_attempts=amount_of_attempts)
        self.run_program_with_retry("docker","builder prune -a -f",amount_of_attempts=amount_of_attempts)
        self.run_program_with_retry("docker","buildx prune -a -f",amount_of_attempts=amount_of_attempts,throw_exception_if_exitcode_is_not_zero=False) # buildx prune is not available on every machine.
        self.run_program_with_retry("docker","system df",print_live_output=self.log.loglevel==LogLevel.Debug,amount_of_attempts=amount_of_attempts)

    @GeneralUtilities.check_arguments
    def get_docker_networks(self)->list[str]:
        program_result=self.run_program("docker","network list")
        result=[]
        lines=program_result[1].split("\n")[1:]
        for line in lines:
            splitted=[item for item in line.split(' ') if GeneralUtilities.string_has_content(item)]
            result.append(splitted[1].replace("\n","").replace("\r","").strip())
        return result

    @GeneralUtilities.check_arguments
    def ensure_docker_network_is_available(self,network_name:str):
        if not (network_name  in self.get_docker_networks()):
            self.run_program("docker",f"network create {network_name}")

    @GeneralUtilities.check_arguments
    def ensure_docker_network_is_not_available(self,network_name:str):
        if network_name  in self.get_docker_networks():
            self.run_program("docker",f"network rm {network_name}")

    @GeneralUtilities.check_arguments
    def get_external_docker_networks_from_compose_file(self, compose_file: str) -> list[str]:
        with open(compose_file, encoding="utf-8") as stream:
            loaded = yaml.safe_load(stream)
        networks = loaded.get("networks", dict())
        result = []
        for network_key, network_definition in networks.items():
            network_definition = network_definition or dict()
            if network_definition.get("external", False):
                network_name = network_definition.get("name", network_key)
                result.append(network_name)
        return result

    @GeneralUtilities.check_arguments
    def show_external_docker_networks_from_compose_file(self, compose_file: str) -> None:
        for network_name in self.get_external_docker_networks_from_compose_file(compose_file):
            GeneralUtilities.write_message_to_stdout(network_name)

    @GeneralUtilities.check_arguments
    def ensure_external_docker_networks_exist_from_compose_file(self, compose_file: str) -> None:
        for network_name in self.get_external_docker_networks_from_compose_file(compose_file):
            self.ensure_docker_network_is_available(network_name)

    @GeneralUtilities.check_arguments
    def get_available_cultures_for_angular_app(self,angular_json_file:str)->list[str]:
        languages = ["en"]
        with open(angular_json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        for project in data.get("projects", {}).values():
            i18n = project.get("i18n", {})
            locales = i18n.get("locales", {})
            languages.extend(locales.keys())

        languages=list(languages)
        return languages

    @GeneralUtilities.check_arguments
    def parse_tasks_from_codeworkspace_file(self,code_workspace_file:str)->list[VSCodeWorkspaceShellTask]:
        result=[]
        jsoncontent = json.loads(GeneralUtilities.read_text_from_file(code_workspace_file))
        tasks = jsoncontent["tasks"]["tasks"]
        for task in tasks:
            if task["type"] == "shell":
                label: str = task["label"]
                name: str = GeneralUtilities.to_pascal_case(label)
                command:str= task["command"]
                work_dir:str = None

                if "options" in task:
                    options = task["options"]
                    if "cwd" in options:
                        work_dir = options["cwd"]
                        work_dir = work_dir.replace("${workspaceFolder}", ".")

                command_with_args = command
                if "args" in task:
                    args = task["args"]
                    if len(args) > 1:
                        command_with_args = f"{command_with_args} {' '.join(args)}"

                description: str =None
                if "description" in task:
                    description =  f'{label} ({task["description"]})'
                else:
                    description =  label


                alias_list:list[str]=[]
                name_lower=name.lower()
                if name!=name.lower():
                    alias_list.append(name_lower)

                if "aliases" in task:
                    aliases = task["aliases"]
                    for alias in aliases:
                        alias_list.append(alias)

                allow_custom_arguments:bool=False
                if "allowcustomarguments" in task:
                    allow_custom_arguments = task["allowcustomarguments"]

                result.append(VSCodeWorkspaceShellTask(name, description, work_dir, command_with_args, alias_list, allow_custom_arguments))
        return result

    @GeneralUtilities.check_arguments
    def parse_mongodbconnection_from_codeworkspace_file(self,code_workspace_file:str)->list[VSCodeWorkspaceMongoDBConnection]:
        result=[]
        jsoncontent = json.loads(GeneralUtilities.read_text_from_file(code_workspace_file))
        settings=jsoncontent["settings"]
        if "mdb.presetConnections" in settings:
            connections = settings["mdb.presetConnections"]
            for connection in connections:
                result.append(VSCodeWorkspaceMongoDBConnection(connection["name"],connection["connectionString"]))
        return result

    @GeneralUtilities.check_arguments
    def parse_sqlconnection_from_codeworkspace_file(self,code_workspace_file:str)->list[VSCodeWorkspaceMariaDBConnection]:
        result=[]
        jsoncontent = json.loads(GeneralUtilities.read_text_from_file(code_workspace_file))
        settings=jsoncontent["settings"]
        if "sqltools.connections" in settings:
            connections = settings["sqltools.connections"]
            for connection in connections:
                result.append(VSCodeWorkspaceMariaDBConnection(connection["name"],connection["server"],connection["port"],connection["database"],connection["username"],connection["password"]))
        return result

    @GeneralUtilities.check_arguments
    def is_xliff2_file(self,file: str) -> bool:
        tree = ET.parse(file)
        root = tree.getroot()

        tag = root.tag  # "{urn:oasis:names:tc:xliff:document:2.0}xliff"

        if tag.startswith("{"):
            namespace, localname = tag[1:].split("}", 1)
        else:
            namespace = None
            localname = tag

        if localname != "xliff":
            return False

        if namespace != "urn:oasis:names:tc:xliff:document:2.0":
            return False

        if root.get("version") != "2.0":
            return False

        return True

    @GeneralUtilities.check_arguments
    def __sync_xlf2_files(self,base_file:ET.ElementTree, language_files:dict [
        str,#filepath
        ET.ElementTree#parsed file
        ]):
        """This function assumes that all files are valid xliff2 files and that the base file is the reference for syncing.
        This function adds new entries from the base file to the language files if they do not already exist using the value from base_file.
        This function removes entries from the language files if they do not exist in the base file anymore.
        In the end the updated language files are written to the disk. The base file is not changed."""
        #The file which was parsed looks like:
        #<?xml version="1.0" encoding="UTF-8" ?>
        #<xliff version="2.0" xmlns="urn:oasis:names:tc:xliff:document:2.0" srcLang="en">
        #  <file id="ngi18n" original="ng.template">
        #    <unit id="logingreeting">
        #      <notes>
        #        <note category="location">src/app/modules/home-page/login-form/login-form.component.html:2,4</note>
        #      </notes>
        #      <segment>
        #        <source>Welcome back, please login</source>
        #      </segment>
        #    </unit>
        #    <unit id="username">
        #      <notes>
        #        <note category="location">src/app/modules/home-page/login-form/login-form.component.html:5,6</note>
        #      </notes>
        #      <segment>
        #        <source>Username</source>
        #      </segment>
        #    </unit>
        #    <unit id="password">
        #      <notes>
        #        <note category="location">src/app/modules/home-page/login-form/login-form.component.html:12,13</note>
        #      </notes>
        #      <segment>
        #        <source>Password</source>
        #      </segment>
        #    </unit>
        #  </file>
        #</xliff>

        NS = "urn:oasis:names:tc:xliff:document:2.0"
        NSMAP = {"x": NS}
        base_root = base_file.getroot()
        base_file_element = base_root.find("x:file", namespaces=NSMAP)
        if base_file_element is None:
            raise ValueError("Invalid XLIFF base file: <file> element not found")

        # Collect base units
        base_units = {
            unit.get("id"): unit
            for unit in base_file_element.findall("x:unit", namespaces=NSMAP)
        }
        base_ids = set(base_units.keys())
        for filepath, lang_tree in language_files.items():
            lang_root = lang_tree.getroot()
            lang_file_element = lang_root.find("x:file", namespaces=NSMAP)
            if lang_file_element is None:
                raise ValueError(f"{filepath}: <file> element not found")

            # Collect language units
            lang_units = {
                unit.get("id"): unit
                for unit in lang_file_element.findall("x:unit", namespaces=NSMAP)
            }
            lang_ids = set(lang_units.keys())

            # Remove obsolete units
            obsolete_ids = lang_ids - base_ids
            for unit_id in obsolete_ids:
                lang_file_element.remove(lang_units[unit_id])

            # Add missing units
            missing_ids = base_ids - lang_ids
            for unit_id in missing_ids:
                new_unit = copy.deepcopy(base_units[unit_id])
                lang_file_element.append(new_unit)

            # Reorder units to match base order
            current_units = {
                unit.get("id"): unit
                for unit in lang_file_element.findall("x:unit", namespaces=NSMAP)
            }
            for unit in list(lang_file_element.findall("x:unit", namespaces=NSMAP)):
                lang_file_element.remove(unit)
            for unit_id in base_units.keys():
                if unit_id in current_units:
                    lang_file_element.append(current_units[unit_id])

            #TODO if a translation-unit has the "new"-attribute: set its value from the fallback-language. (if the culture contains a "-": e. g. take value from "de" as fallback-value for "de-AT"; or else: take value from base_file as fallback-value)

            # Write file back to disk
            ET.register_namespace("", NS)  # Ensure default namespace is declared without prefix
            Path(filepath).write_bytes(
                ET.tostring(
                    lang_tree.getroot(),
                    xml_declaration=True,
                    encoding="UTF-8"
                )
            )
            ScriptCollectionCore().format_xml_file(filepath)

    @GeneralUtilities.check_arguments
    def sync_xlf2_files(self,prefix:str, languages:list[str], folder:str):
        #languages=["de", "fr"] for example. the default-language (usually english) must not be included.
        base_file=os.path.join(folder, f"{prefix}.xlf")
        base_file_xml:ET.ElementTree=ET.parse(base_file)
        GeneralUtilities.assert_condition(self.is_xliff2_file(base_file), f"The base file '{base_file}' is not a valid XLIFF 2.0 file.")
        GeneralUtilities.assert_file_exists(base_file)
        if len(languages)==0:
            raise ValueError("No files provided for syncing.")
        if len(languages)==1:
            return
        language_files_list=[os.path.join(folder, f"{prefix}.{language}.xlf") for language in languages]
        language_files_with_content:dict[str,ET.ElementTree]=dict()
        for language_file in language_files_list:
            GeneralUtilities.assert_file_exists(language_file)
            GeneralUtilities.assert_condition(self.is_xliff2_file(language_file), f"The base file '{base_file}' is not a valid XLIFF 2.0 file.")
            language_files_with_content[language_file]=ET.parse(language_file)

        #sync existing files
        self.__sync_xlf2_files(base_file_xml, language_files_with_content)
            

    @GeneralUtilities.check_arguments
    def translate_xlf_files_in_folder(self, folder: str, base_language: str, libre_translate_api_server: str):
        """Translates all .xlf files directly in the given folder (non-recursive)."""
        pattern = re.compile(r'^.+\.[a-z]{2,3}\.xlf$')
        for filename in os.listdir(folder):
            if not pattern.match(filename):
                continue
            file_path = os.path.join(folder, filename)
            self.translate_xlf_file(file_path, base_language, libre_translate_api_server)

    @GeneralUtilities.check_arguments
    def translate_xlf_file(self, file: str, base_language: str, libre_translate_api_server: str):
        """
        Translates all segments with state='initial' in a XLIFF 2.0 file.
        The target language is extracted from the filename (e.g. 'messages.es.xlf' -> 'es').
        """
        ns_uri = "urn:oasis:names:tc:xliff:document:2.0"
        ns = {"xliff": ns_uri}

        filename = os.path.basename(file)
        parts = filename.split(".")
        if len(parts) < 3:
            raise ValueError(f"Cannot extract language from filename: {filename}")
        target_language = parts[-2]

        tree = ET.parse(file)
        root = tree.getroot()

        for segment in root.findall(".//xliff:segment", ns):
            if segment.get("state", "initial") != "initial":
                continue
            source_el = segment.find("xliff:source", ns)
            if source_el is None or not source_el.text:
                continue

            translated_text = self.translate(source_el.text, base_language, target_language, libre_translate_api_server)

            target_el = segment.find("xliff:target", ns)
            if target_el is None:
                target_el = ET.SubElement(segment, f"{{{ns_uri}}}target")

            target_el.text = translated_text
            segment.set("state", "translated")

        ET.register_namespace("", ns_uri)
        xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        with open(file, "wb") as f:
            f.write(xml_bytes)
        self.format_xml_file(file)

    @GeneralUtilities.check_arguments
    def translate(self, content: str, source_language: str, target_language: str, libre_translate_api_server: str) -> str:
        """Translates text using the LibreTranslate API."""
        url = f"{libre_translate_api_server.rstrip('/')}/translate"
        if "-" in source_language:
            source_language=source_language.split("-")[0]
        if "-" in target_language:
            target_language=target_language.split("-")[0]
        payload = {
            "q": content,
            "source": source_language,
            "target": target_language,
            "format": "text"
        }
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()["translatedText"]

    @GeneralUtilities.check_arguments
    def detect_language(self, content: str, libre_translate_api_server: str) -> str:
        """Detects the language of the given text using the LibreTranslate API."""
        url = f"{libre_translate_api_server.rstrip('/')}/detect"
        payload = {"q": content}
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        results = response.json()
        if not results:
            raise ValueError("Language detection returned no results.")
        return results[0]["language"]

    @GeneralUtilities.check_arguments
    def get_all_files_in_git_repository(self,repository_folder:str,ignore_ignored_files:bool=True,include_submodules: bool = True) -> list[str]:
        """Returns a list of all files in a git-repository."""
        cmd = ["ls-files", "--cached"]
        if ignore_ignored_files:
            cmd.append("--exclude-standard")
        if include_submodules:
            cmd.append("--recurse-submodules")
        output=self.run_program_argsasarray("git", cmd,repository_folder)
        files = [ GeneralUtilities.normalize_path("./" + line) for line in output[1].splitlines()if line.strip() ]
        return files

    @GeneralUtilities.check_arguments
    def write_file_list_for_repository(self,repository_folder:str,target_file:str="./FileList.txt",ignore_ignored_files:bool=True,include_submodules: bool = True) -> None:
        if not os.path.isabs(target_file):
            target_file=GeneralUtilities.resolve_relative_path(target_file,repository_folder)
        target_file=GeneralUtilities.normalize_path(target_file)
        files=[path.replace("\\","/") for path in self.get_all_files_in_git_repository(repository_folder,ignore_ignored_files,include_submodules)]
        GeneralUtilities.ensure_file_exists(target_file)
        GeneralUtilities.write_lines_to_file(target_file, files)

    @GeneralUtilities.check_arguments
    def get_all_commits_in_git_repository(self,repository_folder:str,include_all_heads:bool=False) -> list[str]:
        """Returns a textual visualization of all commits in a git-repository."""
        #do 'git log --reverse --all --pretty=format:"%ci | %H | %cn <%ce> | %d | %s"'
        args = ["log", "--reverse", "--pretty=format:%ci | %H | %cn <%ce> | %D | %s"]
        if include_all_heads:
            args.append("--all")
        result=self.run_program_argsasarray("git", args, repository_folder, throw_exception_if_exitcode_is_not_zero=True)
        output= result[1]
        result=output.splitlines()
        return result

    @GeneralUtilities.check_arguments
    def write_commit_list_for_repository(self,repository_folder:str,target_file:str,include_all_heads:bool=False) -> None:
        if os.path.isabs(target_file):
            target_file=GeneralUtilities.resolve_relative_path(target_file,repository_folder)
        target_file=GeneralUtilities.normalize_path(target_file)
        commits=self.get_all_commits_in_git_repository(repository_folder, include_all_heads)
        GeneralUtilities.ensure_file_exists(target_file)
        GeneralUtilities.write_lines_to_file(target_file, commits)

    @GeneralUtilities.check_arguments
    def is_runnning_in_container(self) ->bool:
        """this function is based on a convention and does not do a real check."""
        return os.environ.get("ISRUNNINGINCONTAINER") == "true"
    
    @GeneralUtilities.check_arguments
    def is_running_in_build_container(self) ->bool:
        """this function is based on a convention and does not do a real check."""
        return os.environ.get("ISRUNNINGINBUILDCONTAINER") == "true"
