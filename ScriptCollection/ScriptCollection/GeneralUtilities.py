import re
import os
from os import listdir
from os.path import isfile, join, isdir
import platform
import json
import inspect
import ctypes
import hashlib
import subprocess
import shutil
import time
import urllib
import stat
import fnmatch
import secrets
import string as strin
import sys
from importlib import resources
from enum import Enum
import traceback
import warnings
import functools
from pathlib import Path
from datetime import datetime, timedelta, date, timezone
import typing
from packaging.version import Version
import psutil
from defusedxml.minidom import parse
from OpenSSL import crypto

class VersionEcholon(Enum):
    LatestPatch = 0
    LatestPatchOrLatestMinor = 1
    LatestPatchOrLatestMinorOrNextMajor = 2
    LatestVersion = 3
    CustomAlgorithm = 4
    NoUpdate = 5

class Platform(Enum):
    Windows_AMD64 = 0
    Linux_AMD64 = 1
    Linux_ARM64 = 2
    MacOS_ARM64 = 3


class Dependency:
    dependencyname:str = None
    current_version:str = None

    def __init__(self,dependencyname:str,current_version:str):
        self.dependencyname=dependencyname
        self.current_version=current_version

class GeneralUtilities:

    empty_string: str = ""

    @staticmethod
    def get_modest_dark_url() -> str:
        return "https://aniondev.github.io/CDN/ScriptCollectionDesigns/ModestDark/Style.css"

    @staticmethod
    def is_generic(t: typing.Type):
        return hasattr(t, "__origin__")

    @staticmethod
    def is_debugger_attached():
        return sys.gettrace() is not None

    @staticmethod
    def check_arguments(function):
        def __check_function(*args, **named_args):
            parameters: list = inspect.getfullargspec(function)[0].copy()
            arguments: list = list(tuple(args)).copy()
            if "self" in parameters:
                parameters.remove("self")
                arguments.pop(0)
            for index, argument in enumerate(arguments):
                if argument is not None:  # Check type of None is not possible. None is always a valid argument-value
                    if parameters[index] in function.__annotations__:  # Check if a type-hint for parameter exist. If not, no parameter-type available for argument-type-check
                        # Check type of arguments if the type is a generic type seems to be impossible.
                        if not GeneralUtilities.is_generic(function.__annotations__[parameters[index]]):
                            if not isinstance(argument, function.__annotations__[parameters[index]]):
                                raise TypeError(f"Argument with index {index} for function {function.__name__} ('{str(argument)}') is not of type {function.__annotations__[parameters[index]]} but has type "+str(type(argument)))
            for index, named_argument in enumerate(named_args):
                if named_args[named_argument] is not None:
                    if parameters[index] in function.__annotations__:
                        if not GeneralUtilities.is_generic(function.__annotations__.get(named_argument)):
                            if not isinstance(named_args[named_argument], function.__annotations__.get(named_argument)):
                                raise TypeError(f"Argument with name {named_argument} for function {function.__name__} ('{str(named_args[named_argument])}') is not of type {function.__annotations__.get(named_argument)}")
            return function(*args, **named_args)
        __check_function.__doc__ = function.__doc__
        return __check_function

    @staticmethod
    def deprecated(reason: str=None):
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                msg = f"Function {func.__name__}() is deprecated."
                if GeneralUtilities.string_has_content(reason):
                    msg += f" {reason}"
                warnings.warn(
                    msg,
                    category=DeprecationWarning,
                    stacklevel=2
                )
                return func(*args, **kwargs)
            return wrapper
        return decorator

    @staticmethod
    @check_arguments
    def args_array_surround_with_quotes_if_required(arguments: list[str]) -> list[str]:
        result = []
        for argument in arguments:
            if " " in argument and not (argument.startswith('"') and argument.endswith('"')):
                result.append(f'"{argument}"')
            else:
                result.append(argument)
        return result

    @staticmethod
    @check_arguments
    def string_to_lines(string: str, add_empty_lines: bool = True, adapt_lines: bool = True) -> list[str]:
        result : list[str] = list[str]()
        lines : list[str] = list[str]()
        if (string is not None):
            if ("\n" in string):
                lines = string.split("\n")
            else:
                lines.append(string)
        for rawline in lines:
            if adapt_lines:
                line = rawline.replace("\r", "").strip()
            else:
                line = rawline
            if GeneralUtilities.string_is_none_or_whitespace(line):
                if add_empty_lines:
                    result.append(line)
            else:
                result.append(line)
        return result

    @staticmethod
    @check_arguments
    def string_to_datetime(value: str) -> datetime:
        """expects a value in the format 2022-10-06T19:26:01"""
        if "." in value:
            value = value.split(".")[0]
        return datetime.strptime(value,"%Y-%m-%dT%H:%M:%S") 

    @staticmethod
    @check_arguments
    def datetime_to_string(value: datetime) -> str:
        """returns a value in the format 2022-10-06T19:26:01"""
        return value.strftime("%Y-%m-%dT%H:%M:%S")

    @staticmethod
    @check_arguments
    def string_to_date(value: str) -> date:
        """expects a value in the format 2022-10-06"""
        splitted = value.split("-")
        return date(int(splitted[0]), int(splitted[1]), int(splitted[2])) 
    
    @staticmethod
    @check_arguments
    def date_to_string(value: date) -> str:
        """returns a value in the format 2022-10-06"""
        return value.strftime("%Y-%m-%d") 

    @staticmethod
    @check_arguments
    def copy_content_of_folder(source_directory: str, target_directory: str, overwrite_existing_files=False, ignored_glob_patterms: list[str] = None) -> None:
        GeneralUtilities.__copy_or_move_content_of_folder(source_directory, target_directory, overwrite_existing_files, False, ignored_glob_patterms)

    @staticmethod
    @check_arguments
    def move_content_of_folder(source_directory: str, target_directory: str, overwrite_existing_files=False, ignored_glob_patterms: list[str] = None) -> None:
        GeneralUtilities.__copy_or_move_content_of_folder(source_directory, target_directory, overwrite_existing_files, True, ignored_glob_patterms)

    @staticmethod
    @check_arguments
    def merge_dependency_lists(versions:list[list[Dependency]]) -> dict[str,set[str]]:
        result:dict[str,set[str]]=dict[str,set[str]]()
        for dlist in versions:
            for ditem in dlist:
                if not ditem.dependencyname in result:
                    result[ditem.dependencyname]=set[str]()
                result[ditem.dependencyname].add(ditem.current_version)
        return result
    
    @staticmethod
    @check_arguments
    def choose_version(available_versions:list[str],current_version:str,echolon:VersionEcholon) -> str:
        match echolon:
            case VersionEcholon.LatestPatch:
                return GeneralUtilities.get_latest_version(GeneralUtilities.filter_versions_by_prefix(available_versions,f"{GeneralUtilities.get_major_part_of_version(current_version)}.{GeneralUtilities.get_minor_part_of_version(current_version)}."))
            case VersionEcholon.LatestPatchOrLatestMinor:
                return GeneralUtilities.get_latest_version(GeneralUtilities.filter_versions_by_prefix(available_versions,f"{GeneralUtilities.get_major_part_of_version(current_version)}."))
            case VersionEcholon.LatestPatchOrLatestMinorOrNextMajor:
                raise  ValueError("not implemented")#TODO
            case VersionEcholon.LatestVersion:
                return GeneralUtilities.get_latest_version(available_versions)
            case VersionEcholon.NoUpdate:
                return current_version
            case _:
                raise  ValueError("Unknown echolon-value: "+str(echolon))
    
    @staticmethod
    @check_arguments
    def get_latest_version(versions:list[str]) -> str:
        GeneralUtilities.assert_condition(0<len(versions),"Version-list can not be empty.")
        latest = max(versions, key=Version)
        return latest
    
    @staticmethod
    @check_arguments
    def filter_versions_by_prefix(versions:list[str],prefix:str) -> list[str]:
        return [v for v in versions if v.startswith(prefix)]
    
    @staticmethod
    @check_arguments
    def get_major_part_of_version(version:str) -> int:
        return GeneralUtilities.get_version_parts(version)[0]
    
    @staticmethod
    @check_arguments
    def get_minor_part_of_version(version:str) -> int:
        return GeneralUtilities.get_version_parts(version)[1]
    
    @staticmethod
    @check_arguments
    def get_patch_part_of_version(version:str) -> int:
        return GeneralUtilities.get_version_parts(version)[2]
    
    @staticmethod
    @check_arguments
    def get_version_parts(version:str) -> tuple[int,int,int]:
        match = re.match(r"^(\d+).(\d+).(\d+)$", version)
        GeneralUtilities.assert_condition(match is not None,f"string \"{version}\" is not a valid version.")
        return (int(match.group(1)),int(match.group(2)),int(match.group(3)))
    
    @staticmethod
    @check_arguments
    def is_ignored_by_glob_pattern(source_directory:str,path:str, ignored_glob_patterms: list[str]) -> bool:
        source_directory=GeneralUtilities.normalize_path(source_directory)
        path=GeneralUtilities.normalize_path(path)
        GeneralUtilities.assert_condition(path.startswith(source_directory), f"Path '{path}' is not located in source directory '{source_directory}'.")
        if ignored_glob_patterms is None:
            return False
        relative_path = os.path.relpath(path, source_directory)
        for pattern in ignored_glob_patterms:
            if fnmatch.filter([relative_path], pattern):
                return True
        return False

    @staticmethod
    @check_arguments
    def safe_copy(src:str, dst:str):
        shutil.copy2(src, dst)
        src_size = os.path.getsize(src)
        dst_size = os.path.getsize(dst)
        if src_size != dst_size:
            raise IOError(f"Copy failed: size mismatch {src} ({src_size}) != {dst} ({dst_size})")

    @staticmethod
    @check_arguments
    def __copy_or_move_content_of_folder(source_directory: str, target_directory: str, overwrite_existing_files:bool, remove_source: bool,ignored_glob_patterms: list[str] = None) -> None:
        srcDirFull = GeneralUtilities.resolve_relative_path_from_current_working_directory(source_directory)
        dstDirFull = GeneralUtilities.resolve_relative_path_from_current_working_directory(target_directory)
        if (os.path.isdir(source_directory)):
            GeneralUtilities.ensure_directory_exists(target_directory)
            for file in GeneralUtilities.get_direct_files_of_folder(srcDirFull):
                filename = os.path.basename(file)
                if not GeneralUtilities.is_ignored_by_glob_pattern(source_directory,file, ignored_glob_patterms):
                    targetfile = os.path.join(dstDirFull, filename)
                    if (os.path.isfile(targetfile)):
                        if overwrite_existing_files:
                            GeneralUtilities.ensure_file_does_not_exist(targetfile)
                        else:
                            raise ValueError(f"Targetfile '{targetfile}' does already exist.")
                    GeneralUtilities.safe_copy(file, targetfile)
                    if remove_source:
                        GeneralUtilities.ensure_file_does_not_exist(file)#remove file to save storage
            for sub_folder in GeneralUtilities.get_direct_folders_of_folder(srcDirFull):
                if not GeneralUtilities.is_ignored_by_glob_pattern(source_directory,sub_folder, ignored_glob_patterms):
                    foldername = os.path.basename(sub_folder)
                    sub_target = os.path.join(dstDirFull, foldername)
                    GeneralUtilities.__copy_or_move_content_of_folder(sub_folder, sub_target, overwrite_existing_files, remove_source,ignored_glob_patterms)
                    if remove_source:
                        GeneralUtilities.ensure_directory_does_not_exist(sub_folder)
        else:
            raise ValueError(f"Folder '{source_directory}' does not exist")

    @staticmethod
    @check_arguments
    def replace_regex_each_line_of_file(file: str, replace_from_regex: str, replace_to_regex: str, encoding="utf-8", verbose: bool = False) -> None:
        if verbose:
            GeneralUtilities.write_message_to_stdout(f"Replace '{replace_from_regex}' to '{replace_to_regex}' in '{file}'")
        lines=GeneralUtilities.read_lines_from_file(file,encoding)
        replaced_lines = []
        for line in lines:
            replaced_line = re.sub(replace_from_regex, replace_to_regex, line)
            replaced_lines.append(replaced_line)
        GeneralUtilities.write_lines_to_file(file,replaced_lines,encoding)

    @staticmethod
    @check_arguments
    def replace_regex_in_file(file: str, replace_from_regex: str, replace_to_regex: str, encoding="utf-8") -> None:
        with open(file, encoding=encoding, mode="r") as f:
            content = f.read()
            content = re.sub(replace_from_regex, replace_to_regex, content)
        with open(file, encoding=encoding, mode="w") as f:
            f.write(content)

    @staticmethod
    @check_arguments
    def replace_xmltag_in_file(file: str, tag: str, new_value: str, encoding="utf-8") -> None:
        GeneralUtilities.assert_condition(tag.isalnum(tag), f"Invalid tag: \"{tag}\"")
        GeneralUtilities.replace_regex_in_file(file, f"<{tag}>.*</{tag}>", f"<{tag}>{new_value}</{tag}>", encoding)

    @staticmethod
    @check_arguments
    def update_version_in_csproj_file(file: str, target_version: str) -> None:
        GeneralUtilities.replace_xmltag_in_file(file, "Version", target_version)
        GeneralUtilities.replace_xmltag_in_file(file, "AssemblyVersion", target_version + ".0")
        GeneralUtilities.replace_xmltag_in_file(file, "FileVersion", target_version + ".0")

    @staticmethod
    @check_arguments
    def replace_underscores_in_text(text: str, replacements: dict) -> str:
        changed = True
        while changed:
            changed = False
            for key, value in replacements.items():
                previousValue = text
                text = text.replace(f"__{key}__", value)
                if (not text == previousValue):
                    changed = True
        return text

    @staticmethod
    @check_arguments
    def replace_underscores_in_file(file: str, replacements: dict, encoding: str = "utf-8"):
        text = GeneralUtilities.read_text_from_file(file, encoding)
        text = GeneralUtilities.replace_underscores_in_text(text, replacements)
        GeneralUtilities.write_text_to_file(file, text, encoding)

    @staticmethod
    @check_arguments
    def print_text(text: str, print_to_stdout: bool = True):
        stream: object = sys.stdout if print_to_stdout else sys.stderr
        GeneralUtilities.__print_text_to_console(text, stream)

    @staticmethod
    @check_arguments
    def print_text_in_green(text: str, print_to_stdout: bool = True, print_as_color: bool = True):
        GeneralUtilities.print_text_in_color(text, 32, print_to_stdout, print_as_color)

    @staticmethod
    @check_arguments
    def print_text_in_yellow(text: str, print_to_stdout: bool = True, print_as_color: bool = True):
        GeneralUtilities.print_text_in_color(text, 33, print_to_stdout, print_as_color)

    @staticmethod
    @check_arguments
    def print_text_in_red(text: str, print_to_stdout: bool = True, print_as_color: bool = True):
        GeneralUtilities.print_text_in_color(text, 31, print_to_stdout, print_as_color)

    @staticmethod
    @check_arguments
    def print_text_in_cyan(text: str, print_to_stdout: bool = True, print_as_color: bool = True):
        GeneralUtilities.print_text_in_color(text, 36, print_to_stdout, print_as_color)

    @staticmethod
    @check_arguments
    def print_text_in_color(text: str, colorcode: int, print_to_stdout: bool = True, print_as_color: bool = True):
        stream: object = sys.stdout if print_to_stdout else sys.stderr
        if print_as_color:
            text = f"\033[{colorcode}m{text}\033[0m"
        GeneralUtilities.__print_text_to_console(text, stream)

    @staticmethod
    @check_arguments
    def __print_text_to_console(text: str, stream: object):
        stream.write(text)
        stream.flush()

    @staticmethod
    @check_arguments
    def reconfigure_standard_input_and_outputs():
        sys.stdin.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
        sys.stdout.reconfigure(encoding='utf-8')

    @staticmethod
    @check_arguments
    def write_message_to_stdout_advanced(message: str, add_empty_lines: bool = True, adapt_lines: bool = True, append_linebreak: bool = True):
        new_line_character: str = "\n" if append_linebreak else GeneralUtilities.empty_string
        for line in GeneralUtilities.string_to_lines(message, add_empty_lines, adapt_lines):
            sys.stdout.write(GeneralUtilities.str_none_safe(line)+new_line_character)
            sys.stdout.flush()

    @staticmethod
    @check_arguments
    def write_message_to_stdout(message: str):
        GeneralUtilities.write_message_to_stdout_advanced(message, True, True, True)

    @staticmethod
    @check_arguments
    def write_message_to_stderr_advanced(message: str, add_empty_lines: bool = True, adapt_lines: bool = True, append_linebreak: bool = True):
        new_line_character: str = "\n" if append_linebreak else GeneralUtilities.empty_string
        for line in GeneralUtilities.string_to_lines(message, add_empty_lines, adapt_lines):
            sys.stderr.write(GeneralUtilities.str_none_safe(line)+new_line_character)
            sys.stderr.flush()

    @staticmethod
    @check_arguments
    def write_message_to_stderr(message: str):
        GeneralUtilities.write_message_to_stderr_advanced(message, True, True, True)

    @staticmethod
    @check_arguments
    def get_advanced_errormessage_for_os_error(os_error: OSError) -> str:
        if GeneralUtilities.string_has_content(os_error.filename2):
            secondpath = f" {os_error.filename2}"
        else:
            secondpath = GeneralUtilities.empty_string
        return f"Related path(s): {os_error.filename}{secondpath}"

    @staticmethod
    @check_arguments
    def write_exception_to_stderr(exception: Exception, extra_message: str = None):
        GeneralUtilities.write_exception_to_stderr_with_traceback(exception, None, extra_message)

    @staticmethod
    @check_arguments
    def write_exception_to_stderr_with_traceback(exception: Exception, current_traceback=None, extra_message: str = None):
        GeneralUtilities.write_message_to_stderr(GeneralUtilities.exception_to_str(exception,current_traceback,extra_message))

    @staticmethod
    @check_arguments
    def exception_to_str(exception: Exception, current_traceback=None, extra_message: str = None)->str:
        result=""
        result=result+"Exception("
        result=result+"\n  Type: " + str(type(exception))
        result=result+"\n  Message: " + str(exception)
        if extra_message is not None:
            result=result+"\n  Extra-message: " + str(extra_message)
        if isinstance(exception, OSError):
            result=result+"\n  "+GeneralUtilities.get_advanced_errormessage_for_os_error(exception)
        if current_traceback is not None:
            result=result+"\n  Traceback:\n" +str(current_traceback.format_exc())
        result=result+"\n)"
        return result

    @staticmethod
    @check_arguments
    def string_has_content(string: str) -> bool:
        if string is None:
            return False
        else:
            return len(string.strip()) > 0

    @staticmethod
    @check_arguments
    def datetime_to_string_for_logfile_name(datetime_object: datetime, add_milliseconds: bool ) -> str:
        """returns a string like '2025-08-21T15-30-00+02-00' or '2025-08-21T15-30-00.123+02-00' depending on the value of add_milliseconds"""
        return GeneralUtilities.datetime_to_string_base(datetime_object, add_milliseconds, "T", "-", False)

    @staticmethod
    @check_arguments
    def datetime_to_string_for_logfile_entry(datetime_object: datetime, add_milliseconds: bool ) -> str:
        """returns a string like '2025-08-21T15:30:00+02:00' or '2025-08-21T15:30:00.123+02:00' depending on the value of add_milliseconds"""
        return GeneralUtilities.datetime_to_string_base(datetime_object, add_milliseconds, "T", ":", False)

    @staticmethod
    @check_arguments
    def datetime_to_string_for_readable_entry(datetime_object: datetime, add_milliseconds: bool ) -> str:
        """returns a string like '2025-08-21 15-30-00 +02:00' or '2025-08-21 15:30:00.123 +02:00' depending on the value of add_milliseconds"""
        return GeneralUtilities.datetime_to_string_base(datetime_object, add_milliseconds, " ", ":", True)
        
    @staticmethod
    @check_arguments
    def datetime_to_string_base(datetime_object: datetime, add_milliseconds: bool ,mid_separator:str,time_separator:str,add_whitespace_before_timezone:bool) -> str:
        dt:datetime=None
        if datetime_object.tzinfo is None:
            dt = datetime_object.replace(tzinfo=timezone.utc)  # assume UTC when no timezone is given
        else:
            dt = datetime_object
        pattern = "%Y-%m-%d"+mid_separator+"%H"+time_separator+"%M"+time_separator+"%S"
        if add_milliseconds:
            pattern = pattern+".%f"
        if add_whitespace_before_timezone:
            pattern = pattern+" "
        pattern = pattern+"%z"

        result = dt.strftime(pattern)
        result = result[:-2] + time_separator + result[-2:]
        return result
    
    @staticmethod
    @check_arguments
    def string_has_nonwhitespace_content(string: str) -> bool:
        if string is None:
            return False
        else:
            return len(string.strip()) > 0

    @staticmethod
    @check_arguments
    def string_is_none_or_empty(argument: str) -> bool:
        if argument is None:
            return True
        type_of_argument = type(argument)
        if type_of_argument == str:
            return argument == GeneralUtilities.empty_string
        else:
            raise ValueError(f"expected string-variable in argument of string_is_none_or_empty but the type was '{str(type_of_argument)}'")

    @staticmethod
    @check_arguments
    def string_is_none_or_whitespace(string: str) -> bool:
        if GeneralUtilities.string_is_none_or_empty(string):
            return True
        else:
            return string.strip() == GeneralUtilities.empty_string

    @staticmethod
    @check_arguments
    def strip_new_line_character(value: str) -> str:
        while not GeneralUtilities.__strip_new_line_character_helper_value_is_ok(value):
            value = GeneralUtilities.__strip_new_line_character_helper_normalize_value(value)
        return value

    @staticmethod
    @check_arguments
    def __strip_new_line_character_helper_value_is_ok(value: str) -> bool:
        if value.startswith("\r") or value.endswith("\r"):
            return False
        if value.startswith("\n") or value.endswith("\n"):
            return False
        return True

    @staticmethod
    @check_arguments
    def __strip_new_line_character_helper_normalize_value(value: str) -> str:
        return value.strip('\n').strip('\r')

    @staticmethod
    @check_arguments
    def file_ends_with_newline(file: str) -> bool:
        file=GeneralUtilities.normalize_path(file)
        with open(file, "rb") as file_object:
            return GeneralUtilities.ends_with_newline_character(file_object.read())

    @staticmethod
    @check_arguments
    def ends_with_newline_character(content: bytes) -> bool:
        result = content.endswith(GeneralUtilities.string_to_bytes("\n"))
        return result

    @staticmethod
    @check_arguments
    def file_ends_with_content(file: str) -> bool:
        content = GeneralUtilities.read_binary_from_file(file)
        if len(content) == 0:
            return False
        else:
            if GeneralUtilities.ends_with_newline_character(content):
                return False
            else:
                return True

    @staticmethod
    @check_arguments
    def get_new_line_character_for_textfile_if_required(file: str) -> bool:
        if GeneralUtilities.file_ends_with_content(file):
            return "\n"
        else:
            return GeneralUtilities.empty_string

    @staticmethod
    @check_arguments
    def append_line_to_file(file: str, line: str, encoding: str = "utf-8") -> None:
        file=GeneralUtilities.normalize_path(file)
        GeneralUtilities.append_lines_to_file(file, [line], encoding)

    @staticmethod
    @check_arguments
    def append_lines_to_file(file: str, lines: list[str], encoding: str = "utf-8") -> None:
        file=GeneralUtilities.normalize_path(file)
        if len(lines) == 0:
            return
        is_first_line = True
        for line in lines:
            insert_linebreak: bool = None
            if is_first_line:
                insert_linebreak = GeneralUtilities.file_ends_with_content(file)
            else:
                insert_linebreak = True
            line_to_write: str = None
            if insert_linebreak:
                line_to_write = "\n"+line
            else:
                line_to_write = line
            with open(file, "r+b") as fileObject:
                fileObject.seek(0, os.SEEK_END)
                fileObject.write(GeneralUtilities.string_to_bytes(line_to_write, encoding))
            is_first_line = False

    @staticmethod
    @check_arguments
    def append_to_file(file: str, content: str, encoding: str = "utf-8") -> None:
        file=GeneralUtilities.normalize_path(file)
        GeneralUtilities.assert_condition(not "\n" in content, "Appending multiple lines is not allowed. Use append_lines_to_file instead.")
        with open(file, "a", encoding=encoding) as fileObject:
            fileObject.write(content)

    @staticmethod
    @check_arguments
    def ensure_directory_exists(path: str) -> None:
        path=GeneralUtilities.normalize_path(path)
        if not os.path.isdir(path):
            os.makedirs(path)

    @staticmethod
    @check_arguments
    def ensure_file_exists(path: str) -> None:
        path=GeneralUtilities.normalize_path(path)
        if (not os.path.isfile(path)):
            with open(path, "a+", encoding="utf-8"):
                pass

    @staticmethod
    @check_arguments
    def __remove_readonly(func, path, _):
        os.chmod(path, stat.S_IWRITE)
        func(path)

    @staticmethod
    @check_arguments
    def __rmtree(directory: str) -> None:
        shutil.rmtree(directory, onerror=GeneralUtilities.__remove_readonly)  # pylint: disable=deprecated-argument

    @staticmethod
    @check_arguments
    def ensure_directory_does_not_exist(path: str) -> None:
        if (os.path.isdir(path)):
            for root, dirs, files in os.walk(path, topdown=False):
                for name in files:
                    filename = os.path.join(root, name)
                    os.chmod(filename, stat.S_IWUSR)
                    os.remove(filename)
                for name in dirs:
                    GeneralUtilities.__rmtree(os.path.join(root, name))
            GeneralUtilities.__rmtree(path)

    @staticmethod
    @check_arguments
    def ensure_folder_exists_and_is_empty(path: str) -> None:
        GeneralUtilities.ensure_directory_exists(path)
        for filename in os.listdir(path):
            file_path = os.path.join(path, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)
            if os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)

    @staticmethod
    @check_arguments
    def ensure_file_does_not_exist(path: str) -> None:
        if (os.path.isfile(path)):
            os.remove(path)

    @staticmethod
    @check_arguments
    def ensure_path_does_not_exist(path: str) -> None:
        if (os.path.isfile(path)):
            GeneralUtilities.ensure_file_does_not_exist(path)
        if (os.path.isdir(path)):
            GeneralUtilities.ensure_directory_does_not_exist(path)

    @staticmethod
    @check_arguments
    def format_xml_file(filepath: str) -> None:
        GeneralUtilities.format_xml_file_with_encoding(filepath, "utf-8")

    @staticmethod
    @check_arguments
    def format_xml_file_with_encoding(filepath: str, encoding: str) -> None:
        with open(filepath, 'r', encoding=encoding) as file:
            text = file.read()
        text = parse(text).toprettyxml()
        with open(filepath, 'w', encoding=encoding) as file:
            file.write(text)

    @staticmethod
    @check_arguments
    def get_clusters_and_sectors_of_disk(diskpath: str) -> None:
        GeneralUtilities.assert_condition(GeneralUtilities.current_system_is_windows(), "get_clusters_and_sectors_of_disk(diskpath) is only available on windows.")
        sectorsPerCluster = ctypes.c_ulonglong(0)
        bytesPerSector = ctypes.c_ulonglong(0)
        rootPathName = ctypes.c_wchar_p(diskpath)
        ctypes.windll.kernel32.GetDiskFreeSpaceW(rootPathName, ctypes.pointer(sectorsPerCluster), ctypes.pointer(bytesPerSector), None, None)
        return (sectorsPerCluster.value, bytesPerSector.value)

    @staticmethod
    @check_arguments
    def ensure_path_is_not_quoted(path: str) -> str:
        if (path.startswith("\"") and path.endswith("\"")) or (path.startswith("'") and path.endswith("'")):
            path = path[1:]
            path = path[:-1]
            return path
        else:
            return path

    @staticmethod
    @check_arguments
    def get_missing_files(folderA: str, folderB: str) -> list:
        folderA_length = len(folderA)
        result = []
        for fileA in GeneralUtilities.absolute_file_paths(folderA):
            file = fileA[folderA_length:]
            fileB = folderB + file
            if not os.path.isfile(fileB):
                result.append(fileB)
        return result

    @staticmethod
    @check_arguments
    def to_pascal_case(s: str) -> str:
        return ''.join(current.lower() if prev.isalnum() else current.upper() for prev, current in zip(' ' + s, s) if current.isalnum())

    @staticmethod
    @check_arguments
    def to_snake_case(s: str) -> str:
        return '_'.join(t.lower() for t in re.split(r'[^a-zA-Z0-9]+', s) if t)

    @staticmethod
    @check_arguments
    def to_camel_case(s: str) -> str:
        words = [t.lower() for t in re.split(r'[^a-zA-Z0-9]+', s) if t]
        return words[0] + ''.join(w.capitalize() for w in words[1:]) if words else ''

    @staticmethod
    @check_arguments
    def to_kebab_case(s: str) -> str:
        return '-'.join(t.lower() for t in re.split(r'[^a-zA-Z0-9]+', s) if t)

    @staticmethod
    @check_arguments
    def find_between(s: str, start: str, end: str) -> str:
        return s.split(start)[1].split(end)[0]

    @staticmethod
    @check_arguments
    def write_lines_to_file(file: str, lines: list, encoding="utf-8") -> None:
        lines = [GeneralUtilities.strip_new_line_character(line) for line in lines]
        content = "\n".join(lines)
        GeneralUtilities.write_text_to_file(file, content, encoding)

    @staticmethod
    @check_arguments
    def write_text_to_file(file: str, content: str, encoding="utf-8") -> None:
        GeneralUtilities.write_binary_to_file(file, bytes(bytearray(content, encoding)))

    @staticmethod
    @check_arguments
    def write_binary_to_file(file: str, content: bytes) -> None:
        with open(file, "wb") as file_object:
            file_object.write(content)

    @staticmethod
    def is_binary_file(path: str):
        content = GeneralUtilities.read_binary_from_file(path)
        binary_content_indicators = [b'\x00', b'\x01', b'\x02', b'\x03', b'\x04', b'\x05', b'\x06', b'\x07', b'\x08', b'\x0E', b'\x1F']
        for binary_content_indicator in binary_content_indicators:
            if binary_content_indicator in content:
                return True
        return False

    @staticmethod
    @check_arguments
    def read_lines_from_file(file: str, encoding="utf-8") -> list[str]:
        content = GeneralUtilities.read_text_from_file(file, encoding)
        if len(content) == 0:
            return []
        else:
            return [GeneralUtilities.strip_new_line_character(line) for line in content.split('\n')]

    @staticmethod
    @check_arguments
    def read_nonempty_lines_from_file(file: str, encoding="utf-8") -> list[str]:
        return [line for line in GeneralUtilities.read_lines_from_file(file, encoding) if GeneralUtilities.string_has_content(line)]

    @staticmethod
    @check_arguments
    def read_text_from_file(file: str, encoding="utf-8") -> str:
        GeneralUtilities.assert_file_exists(file)
        return GeneralUtilities.bytes_to_string(GeneralUtilities.read_binary_from_file(file), encoding)

    @staticmethod
    @check_arguments
    def read_text_from_file_without_linebreak(file: str, encoding="utf-8") -> str:
        return GeneralUtilities.read_text_from_file(file,encoding).replace("\n","").replace("\r","")

    @staticmethod
    @check_arguments
    def read_binary_from_file(file: str) -> bytes:
        file=GeneralUtilities.normalize_path(file)
        with open(file, "rb") as file_object:
            return file_object.read()

    @staticmethod
    @check_arguments
    def timedelta_to_simple_string(delta: timedelta) -> str:
        return (datetime(1970, 1, 1, 0, 0, 0) + delta).strftime('%H:%M:%S')

    @staticmethod
    @check_arguments
    def resolve_relative_path_from_current_working_directory(path: str) -> str:
        return GeneralUtilities.resolve_relative_path(path, os.getcwd())

    @staticmethod
    @check_arguments
    def resolve_relative_path(path: str, base_path: str):
        if (os.path.isabs(path)):
            return path
        else:
            return str(Path(os.path.join(base_path, path)).resolve())

    @staticmethod
    @check_arguments
    def get_metadata_for_file_for_clone_folder_structure(file: str) -> str:
        size = os.path.getsize(file)
        last_modified_timestamp = os.path.getmtime(file)
        hash_value = GeneralUtilities.get_sha256_of_file(file)
        last_access_timestamp = os.path.getatime(file)
        return f'{{"size":"{size}","sha256":"{hash_value}","mtime":"{last_modified_timestamp}","atime":"{last_access_timestamp}"}}'

    @staticmethod
    @check_arguments
    def clone_folder_structure(source: str, target: str, copy_only_metadata: bool):
        source = GeneralUtilities.resolve_relative_path(source, os.getcwd())
        target = GeneralUtilities.resolve_relative_path(target, os.getcwd())
        length_of_source = len(source)
        for source_file in GeneralUtilities.absolute_file_paths(source):
            target_file = target+source_file[length_of_source:]
            GeneralUtilities.ensure_directory_exists(os.path.dirname(target_file))
            if copy_only_metadata:
                with open(target_file, 'w', encoding='utf8') as f:
                    f.write(GeneralUtilities.get_metadata_for_file_for_clone_folder_structure(source_file))
            else:
                shutil.copyfile(source_file, target_file)

    @staticmethod
    @check_arguments
    def current_user_has_elevated_privileges() -> bool:
        try:
            return os.getuid() == 0
        except AttributeError:
            return ctypes.windll.shell32.IsUserAnAdmin() == 1

    @staticmethod
    @check_arguments
    def ensure_elevated_privileges() -> None:
        if (not GeneralUtilities.current_user_has_elevated_privileges()):
            raise ValueError("Not enough privileges.")

    @staticmethod
    @check_arguments
    def rename_names_of_all_files_and_folders(folder: str, replace_from: str, replace_to: str, replace_only_full_match=False):
        for file in GeneralUtilities.get_direct_files_of_folder(folder):
            GeneralUtilities.replace_in_filename(file, replace_from, replace_to, replace_only_full_match)
        for sub_folder in GeneralUtilities.get_direct_folders_of_folder(folder):
            GeneralUtilities.rename_names_of_all_files_and_folders(sub_folder, replace_from, replace_to, replace_only_full_match)
        GeneralUtilities.replace_in_foldername(folder, replace_from, replace_to, replace_only_full_match)

    @staticmethod
    @check_arguments
    def get_direct_files_of_folder(folder: str) -> list[str]:
        result = [os.path.join(folder, f) for f in listdir(folder) if isfile(join(folder, f))]
        result = sorted(result, key=str.casefold)
        return result

    @staticmethod
    @check_arguments
    def get_direct_folders_of_folder(folder: str) -> list[str]:
        result = [os.path.join(folder, f) for f in listdir(folder) if isdir(join(folder, f))]
        result = sorted(result, key=str.casefold)
        return result

    @staticmethod
    @check_arguments
    def get_all_files_of_folder(folder: str) -> list[str]:
        result = list()
        result.extend(GeneralUtilities.get_direct_files_of_folder(folder))
        for subfolder in GeneralUtilities.get_direct_folders_of_folder(folder):
            result.extend(GeneralUtilities.get_all_files_of_folder(subfolder))
        result = sorted(result, key=str.casefold)
        return result

    @staticmethod
    @check_arguments
    def get_all_folders_of_folder(folder: str) -> list[str]:
        result = list()
        subfolders = GeneralUtilities.get_direct_folders_of_folder(folder)
        result.extend(subfolders)
        for subfolder in subfolders:
            result.extend(GeneralUtilities.get_all_folders_of_folder(subfolder))
        result = sorted(result, key=str.casefold)
        return result

    @staticmethod
    @check_arguments
    def get_all_objects_of_folder(folder: str) -> list[str]:
        return sorted(GeneralUtilities.get_all_files_of_folder(folder) + GeneralUtilities.get_all_folders_of_folder(folder), key=str.casefold)

    @staticmethod
    @check_arguments
    def replace_in_filename(file: str, replace_from: str, replace_to: str, replace_only_full_match=False):
        filename = Path(file).name
        if (GeneralUtilities.__should_get_replaced(filename, replace_from, replace_only_full_match)):
            folder_of_file = os.path.dirname(file)
            os.rename(file, os.path.join(folder_of_file, filename.replace(replace_from, replace_to)))

    @staticmethod
    @check_arguments
    def replace_in_foldername(folder: str, replace_from: str, replace_to: str, replace_only_full_match=False):
        foldername = Path(folder).name
        if (GeneralUtilities.__should_get_replaced(foldername, replace_from, replace_only_full_match)):
            folder_of_folder = os.path.dirname(folder)
            os.rename(folder, os.path.join(folder_of_folder, foldername.replace(replace_from, replace_to)))

    @staticmethod
    @check_arguments
    def __should_get_replaced(input_text, search_text, replace_only_full_match) -> bool:
        if replace_only_full_match:
            return input_text == search_text
        else:
            return search_text in input_text

    @staticmethod
    @check_arguments
    def str_none_safe(variable) -> str:
        if variable is None:
            return ''
        else:
            return str(variable)

    @staticmethod
    @check_arguments
    def arguments_to_array(arguments_as_string: str) -> list[str]:
        if arguments_as_string is None:
            return []
        if GeneralUtilities.string_has_content(arguments_as_string):
            return arguments_as_string.split(" ")  # TODO this function should get improved to allow whitespaces in quote-substrings
        else:
            return []

    @staticmethod
    @check_arguments
    def arguments_to_array_for_log(arguments_as_string: str) -> list[str]:
        if arguments_as_string is None:
            return None
        return GeneralUtilities.arguments_to_array(arguments_as_string)

    @staticmethod
    @check_arguments
    def get_sha256_of_file(file: str) -> str:
        sha256 = hashlib.sha256()
        with open(file, "rb") as fileObject:
            for chunk in iter(lambda: fileObject.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    @staticmethod
    @check_arguments
    def remove_duplicates(input_list) -> list:
        result = []
        for item in input_list:
            if not item in result:
                result.append(item)
        return result

    @staticmethod
    @check_arguments
    def print_stacktrace() -> None:
        for line in traceback.format_stack():
            GeneralUtilities.write_message_to_stderr(line.strip())

    @staticmethod
    @check_arguments
    def string_to_boolean(value: str) -> bool:
        value = value.strip().lower()
        if value in ('yes', 'y', 'true', 't', '1'):
            return True
        elif value in ('no', 'n', 'false', 'f', '0'):
            return False
        else:
            raise ValueError(f"Can not convert '{value}' to a boolean value")

    @staticmethod
    @check_arguments
    def file_is_empty(file: str) -> bool:
        return os.stat(file).st_size == 0

    @staticmethod
    @check_arguments
    def folder_is_empty(folder: str) -> bool:
        return len(GeneralUtilities.get_direct_files_of_folder(folder)) == 0 and len(GeneralUtilities.get_direct_folders_of_folder(folder)) == 0

    @staticmethod
    @check_arguments
    def get_time_based_logfile_by_folder(folder: str, name: str = "Log") -> str:
        return os.path.join(GeneralUtilities.resolve_relative_path_from_current_working_directory(folder), f"{GeneralUtilities.get_time_based_logfilename(name)}.log")

    @staticmethod
    @check_arguments
    def get_now() -> datetime:
        return datetime.now().astimezone().replace(microsecond=0)

    @staticmethod
    @check_arguments
    def get_time_based_logfilename(name: str = "Log") -> str:
        d = GeneralUtilities.get_now()
        return f"{name}_{GeneralUtilities.datetime_to_string_for_logfile_name(d,False)}"

    @staticmethod
    @check_arguments
    def bytes_to_string(payload: bytes, encoding: str = 'utf-8') -> str:
        return payload.decode(encoding, errors="ignore")

    @staticmethod
    @check_arguments
    def string_to_bytes(payload: str, encoding: str = 'utf-8') -> bytes:
        return payload.encode(encoding, errors="ignore")

    @staticmethod
    @check_arguments
    def contains_line(lines, regex: str) -> bool:
        for line in lines:
            if (re.match(regex, line)):
                return True
        return False

    @staticmethod
    @check_arguments
    def read_csv_file(file: str, ignore_first_line: bool = False, treat_number_sign_at_begin_of_line_as_comment: bool = True, trim_values: bool = True, encoding="utf-8", ignore_empty_lines: bool = True, separator_character: str = ";", values_are_surrounded_by_quotes: bool = False) -> list[list[str]]:
        lines = GeneralUtilities.read_lines_from_file(file, encoding)

        if ignore_first_line:
            lines = lines[1:]
        result = list()
        line: str = None
        for line_loopvariable in lines:
            use_line = True
            line = line_loopvariable

            if trim_values:
                line = line.strip()
            if ignore_empty_lines:
                if not GeneralUtilities.string_has_content(line):
                    use_line = False

            if treat_number_sign_at_begin_of_line_as_comment:
                if line.startswith("#"):
                    use_line = False

            if use_line:
                if separator_character in line:
                    raw_values_of_line = GeneralUtilities.to_list(line, separator_character)
                else:
                    raw_values_of_line = [line]
                if trim_values:
                    raw_values_of_line = [value.strip() for value in raw_values_of_line]
                values_of_line = []
                for raw_value_of_line in raw_values_of_line:
                    value_of_line = raw_value_of_line
                    if values_are_surrounded_by_quotes:
                        value_of_line = value_of_line[1:]
                        value_of_line = value_of_line[:-1]
                        value_of_line = value_of_line.replace('""', '"')
                    values_of_line.append(value_of_line)
                result.extend([values_of_line])
        return result

    @staticmethod
    @check_arguments
    def epew_is_available() -> bool:
        return GeneralUtilities.tool_is_available("epew")

    @staticmethod
    @check_arguments
    def tool_is_available(toolname: str) -> bool:
        try:
            return shutil.which(toolname) is not None
        except:
            return False

    @staticmethod
    @check_arguments
    @deprecated
    def absolute_file_paths(directory: str) -> list[str]:
        return GeneralUtilities.get_all_files_of_folder(directory)

    @staticmethod
    @check_arguments
    def to_list(list_as_string: str, separator: str = ",") -> list[str]:
        result = list()
        if list_as_string is not None:
            list_as_string = list_as_string.strip()
            if list_as_string == GeneralUtilities.empty_string:
                pass
            elif separator in list_as_string:
                for item in list_as_string.split(separator):
                    result.append(item.strip())
            else:
                result.append(list_as_string)
        return result

    @staticmethod
    @check_arguments
    def get_next_square_number(number: int) -> int:
        GeneralUtilities.assert_condition(number >= 0, "get_next_square_number is only applicable for nonnegative numbers")
        if number == 0:
            return 1
        root = 0
        square = 0
        while square < number:
            root = root+1
            square = root*root
        return root*root

    @staticmethod
    @check_arguments
    def generate_password(length: int = 16, alphabet: str = None) -> None:
        if alphabet is None:
            alphabet = strin.ascii_letters + strin.digits+"_"
        return GeneralUtilities.empty_string.join(secrets.choice(alphabet) for i in range(length))

    @staticmethod
    @check_arguments
    def assert_condition(condition: bool, information: str = None) -> None:
        """Throws an exception if the condition is false."""
        if (not condition):
            if information is None:
                information = "Internal assertion error."
            raise ValueError("Condition failed. "+information)

    @staticmethod
    def current_system_is_windows():
        return platform.system() == 'Windows'

    @staticmethod
    def current_system_is_linux():
        return platform.system() == 'Linux'

    @staticmethod
    def current_system_is_macos():
        return platform.system() == 'Darwin'

    @staticmethod
    @check_arguments
    def get_line():
        return "--------------------------"

    @staticmethod
    def get_longline():
        return GeneralUtilities.get_line() + GeneralUtilities.get_line()

    @staticmethod
    @check_arguments
    def get_icon_check_empty(positive: bool) -> str:
        if positive:
            return "✅"
        else:
            return GeneralUtilities.empty_string

    @staticmethod
    @check_arguments
    def get_icon_check_cross(positive: bool) -> str:
        if positive:
            return "✅"
        else:
            return "❌"

    @staticmethod
    @check_arguments
    def get_certificate_expiry_date(certificate_file: str) -> datetime:
        with open(certificate_file, encoding="utf-8") as certificate_file_content:
            cert = crypto.load_certificate(crypto.FILETYPE_PEM, certificate_file_content.read())
            date_as_bytes = cert.get_notAfter()
            date_as_string = date_as_bytes.decode("utf-8")
            result = datetime.strptime(date_as_string, '%Y%m%d%H%M%SZ')
            return result

    @staticmethod
    @check_arguments
    def certificate_is_expired(certificate_file: str) -> bool:
        return GeneralUtilities.get_certificate_expiry_date(certificate_file) < GeneralUtilities.get_now()

    @staticmethod
    @check_arguments
    def internet_connection_is_available() -> bool:
        """Returns True as soon as any of a small set of well-known public hosts can be reached.
        Returns False only when none of the hosts answered (= no internet connectivity)."""
        hosts: list[str] = [
            "https://www.google.com",
            "https://www.wikipedia.org",
            "https://www.github.com",
            "https://www.cloudflare.com",
        ]
        for host in hosts:
            try:
                with urllib.request.urlopen(host, timeout=10):
                    return True
            except Exception:
                continue
        return False

    @staticmethod
    @check_arguments
    def replace_variable_in_string(input_string: str, variable_name: str, variable_value: str) -> str:
        GeneralUtilities.assert_condition(not "__" in variable_name, f"'{variable_name}' is an invalid variable name because it contains '__' which is treated as control-sequence.")
        return input_string.replace(f"__[{variable_name}]__", variable_value)
    
    @staticmethod
    @check_arguments
    def replace_variable(prefix:str, variable_name:str, suffix:str, value:str, content: str) -> str:
        GeneralUtilities.assert_condition(not "__" in variable_name, f"'{variable_name}' is an invalid variable name because it contains '__' which is treated as control-sequence.")
        pattern = re.escape(GeneralUtilities.str_none_safe( prefix)) + r"\s*" +"__"+ re.escape(variable_name) + "__"+r"\s*" + re.escape(GeneralUtilities.str_none_safe( suffix))
        result:str= re.sub(pattern, value, content)
        GeneralUtilities.assert_condition(not f"__{variable_name}__" in result, f"Variable '{variable_name}' was not replaced in the content. This is likely caused by an error in the content or the variable name.")
        return result

    @staticmethod
    @check_arguments
    def input(prompt: str, print_result: bool) -> str:  # This function is a workaround for usescases like python scripts which calls input(...) using epew because then the prompt is not printed by the built-in-input-function.
        GeneralUtilities.write_message_to_stdout(prompt)
        result: str = input()
        if print_result:
            GeneralUtilities.write_message_to_stdout(f"Result: {result}")
        return result

    @staticmethod
    @check_arguments
    def run_program_simple(program: str, arguments: list[str], cwd: str = None) -> tuple[int, str, str]:
        if cwd is None:
            cwd = os.getcwd()
        cmd = [program]+arguments
        with subprocess.Popen(cmd, cwd=cwd, stderr=subprocess.PIPE, stdout=subprocess.PIPE) as process:
            stdout, stderr = process.communicate()
            exit_code = process.wait()
            return (exit_code, stdout, stderr)

    @staticmethod
    @check_arguments
    def assert_file_exists(file: str,message=None) -> None:
        if message is None:
            message=f"File '{file}' does not exist."
        GeneralUtilities.assert_condition(os.path.isfile(file), message)

    @staticmethod
    @check_arguments
    def assert_file_does_not_exist(file: str,message=None) -> None:
        if message is None:
            message=f"File '{file}' exists."
        GeneralUtilities.assert_condition(not os.path.isfile(file), message)

    @staticmethod
    @check_arguments
    def assert_folder_exists(folder: str,message=None) -> None:
        if message is None:
            message=f"Folder '{folder}' does not exist."
        GeneralUtilities.assert_condition(os.path.isdir(folder),message )

    @staticmethod
    @check_arguments
    def assert_folder_does_not_exist(folder: str,message=None) -> None:
        if message is None:
            message= f"Folder '{folder}' exists."
        GeneralUtilities.assert_condition(not os.path.isdir(folder), f"Folder '{folder}' exists.")

    @staticmethod
    @check_arguments
    def assert_not_null(obj,message:str=None) -> str:
        if message is None:
            message="Variable is not set"
        GeneralUtilities.assert_condition(obj is not None, message)

    @staticmethod
    @check_arguments
    def retry_action(action, amount_of_attempts: int, action_name: str = None,delay_in_seconds:int=2) -> None:
        amount_of_fails = 0
        last_exception:Exception=None
        GeneralUtilities.assert_condition(0<amount_of_attempts,"amount_of_attempts must be greater than 0.")
        while amount_of_fails<amount_of_attempts:
            try:
                result = action()
                return result
            except Exception as e:
                time.sleep(delay_in_seconds)
                amount_of_fails = amount_of_fails+1
                last_exception=e
        GeneralUtilities.assert_not_null(last_exception)
        message = "Action"
        if action_name is not None:
            message = f"{message} \"{action_name}\""
        message = f"{message} failed {amount_of_attempts} time(s)."
        GeneralUtilities.write_message_to_stderr(message)
        raise last_exception


    @staticmethod
    @check_arguments
    def normalize_path(path)->str:
        path=str(path)
        if GeneralUtilities.current_system_is_windows():
            path=path.replace("/","\\")
        else:
            path=path.replace("\\","/")
        return path
    
    @staticmethod
    @check_arguments
    def int_to_string(number: int, leading_zeroplaces: int, trailing_zeroplaces: int) -> str:
        return GeneralUtilities.float_to_string(float(number), leading_zeroplaces, trailing_zeroplaces)

    @staticmethod
    @check_arguments
    def float_to_string(number: float, leading_zeroplaces: int, trailing_zeroplaces: int) -> str:
        plain_str = str(number)
        GeneralUtilities.assert_condition("." in plain_str)
        splitted: list[str] = plain_str.split(".")
        return splitted[0].zfill(leading_zeroplaces)+"."+splitted[1].ljust(trailing_zeroplaces, '0')

    @staticmethod
    @check_arguments
    def process_is_running_by_name(process_name: str) -> bool:
        processes: list[psutil.Process] = list(psutil.process_iter())
        for p in processes:
            if p.name() == process_name:
                return True
        return False

    @staticmethod
    @check_arguments
    def process_is_running_by_id(process_id: int) -> bool:
        processes: list[psutil.Process] = list(psutil.process_iter())
        for p in processes:
            if p.pid == process_id:
                return True
        return False

    @staticmethod
    @check_arguments
    def kill_process(process_id: int, include_child_processes: bool) -> bool:
        if GeneralUtilities. process_is_running_by_id(process_id):
            GeneralUtilities.write_message_to_stdout(f"Process with id {process_id} is running. Terminating it...")
            process = psutil.Process(process_id)
            if include_child_processes:
                for child in process.children(recursive=True):
                    if GeneralUtilities.process_is_running_by_id(child.pid):
                        child.kill()
            if GeneralUtilities.process_is_running_by_id(process_id):
                process.kill()
        else:
            GeneralUtilities.write_message_to_stdout(f"Process with id {process_id} is not running anymore.")

    @staticmethod
    @check_arguments
    def get_only_item_from_list(list_with_one_element:list):
        GeneralUtilities.assert_condition(len(list_with_one_element)==1,f"List does not contain exactly one item. It contains {len(list_with_one_element)} items.")
        return list_with_one_element[0]
    
    @staticmethod
    @check_arguments
    def trim_newlines(s: str) -> str:
        return s.strip("\n")
    
    @staticmethod
    @check_arguments
    def log_merger(folder:str):
        """For each log file in this folder this function looks for log-rotation-files and merges them together again into one file."""
        all_files=GeneralUtilities.get_direct_files_of_folder(folder)
        for log_file in all_files:
            if "AutoRename" in log_file:
                continue
            filename=os.path.basename(log_file)
            filename_without_extension=Path(log_file).stem
            if not ".archive." in filename:

                #merge with rotated logs
                if filename.endswith(".log") and not ".archive." in filename:
                    rotated_log_files=sorted([f for f in all_files if os.path.basename(f).startswith(filename_without_extension+".archive.")], key=GeneralUtilities._internal_extract_log_file_number)
                    result=GeneralUtilities.empty_string
                    if 0<len(rotated_log_files):
                        for rotated_log_file in rotated_log_files:
                            result+="\n"+GeneralUtilities.read_text_from_file(rotated_log_file)
                        result+="\n"+GeneralUtilities.read_text_from_file(log_file)
                        GeneralUtilities.write_text_to_file(log_file, result)
                        for rotated_log_file in rotated_log_files:
                            GeneralUtilities.ensure_file_does_not_exist(rotated_log_file)
                
                #normalize
                logs=GeneralUtilities.read_text_from_file(log_file)
                logs=logs.replace("\r\n", "\n")
                logs=logs.replace("\r", GeneralUtilities.empty_string)
                logs=re.sub(r"\n+", "\n", logs)
                logs=GeneralUtilities.trim_newlines(logs)
                GeneralUtilities.write_text_to_file(log_file, logs)

    @staticmethod
    @check_arguments
    def _internal_extract_log_file_number(filename: str) -> int:
        m = re.search(r"\.archive\.(\d+)\.log$", filename)
        if m:
            return int(m.group(1))
        else:
            raise ValueError(f"Filename '{filename}' does not match the expected pattern for rotated log files.")

    @staticmethod
    @check_arguments
    def _internal_load_resource(relative_path: str) -> bytes:
        res = resources.files("ScriptCollection.Resources")
        for part in relative_path.split("/"):
            res = res.joinpath(part)
        result= res.read_bytes()
        return result

    @staticmethod
    @check_arguments
    def escape_json_string_value(str_value: str) -> str:
        """For input 'a"b\\c' this function returns 'a\\"b\\\\c'. This function does not add surrounding quotes. It only escapes the characters inside the string."""
        json_escaped = json.dumps(str_value)
        return json_escaped[1:-1] 
    
    @staticmethod
    @check_arguments
    def escape_json_property_value(str_value: str) -> str:
        # remove all characters not in [a-zA-Z0-9_]
        sanitized = re.sub(r'[^a-zA-Z0-9_]', '', str_value)

        # check if result starts with [a-zA-Z_]
        if not sanitized or len(sanitized) == 0 or not re.match(r'[a-zA-Z_]', sanitized[0]):
            raise ValueError(f"Invalid JSON property name after sanitizing: '{sanitized}'. Value must start with [a-zA-Z_].")

        return sanitized

    @staticmethod
    @check_arguments
    def escape_yaml_string_value(str_value: str) -> str:
        """For input 'a"b\\c' this function returns 'a\\"b\\\\c'. This function does not add surrounding quotes. It only escapes the characters inside the string."""
        result= GeneralUtilities.escape_json_string_value(str_value)
        #do other adaptions here if desired/required
        return result

    @staticmethod
    @check_arguments
    def escape_yaml_property_value(str_value: str) -> str:
        result= GeneralUtilities.escape_json_property_value(str_value)
        #do other adaptions here if desired/required
        return result
    
        
    @staticmethod
    @check_arguments
    def get_current_platform() -> Platform:
        system = platform.system().lower()
        machine = platform.machine().lower()

        if system == "windows" and machine in ("x86_64", "amd64"):
            return Platform.Windows_AMD64
        elif system == "linux" and machine in ("x86_64", "amd64"):
            return Platform.Linux_AMD64
        elif system == "linux" and machine in ("arm64", "aarch64"):
            return Platform.Linux_ARM64
        elif system == "darwin" and machine in ("x86_64", "amd64"):
            return Platform.MacOS_ARM64
        else:
            raise ValueError(f"Unsupported platform: {system}/{machine}")

    @staticmethod
    @check_arguments
    def current_system_is_x64():
        arch = platform.machine().lower()
        return arch in ("x86_64", "amd64")

    @staticmethod
    @check_arguments
    def current_system_is_arm64():
        arch = platform.machine().lower()
        return arch in ("arm", "aarch64")
    
    @staticmethod
    @check_arguments
    def platform_to_short_str(platform_value: Platform) -> str:
        mapping = {
            Platform.Windows_AMD64: "win-x64",
            Platform.Linux_AMD64:   "linux-x64",
            Platform.Linux_ARM64:   "linux-arm64",
            Platform.MacOS_ARM64:   "osx-arm64",
        }
        return mapping[platform_value]
    
    @staticmethod
    @check_arguments
    def platform_from_short_str(platform_str: str) -> Platform:
        mapping = {
            "win-x64": Platform.Windows_AMD64,
            "linux-x64":   Platform.Linux_AMD64,
            "linux-arm64": Platform.Linux_ARM64,
            "osx-arm64":   Platform.MacOS_ARM64,
        }
        if platform_str not in mapping:
            raise ValueError(f"Unsupported platform string: {platform_str}")
        return mapping[platform_str]
    
    @staticmethod
    @check_arguments
    def platform_to_dash_str(platform_value: Platform) -> str:
        mapping = {
            Platform.Windows_AMD64: "Windows-x64",
            Platform.Linux_AMD64:   "Linux-x64",
            Platform.Linux_ARM64:   "Linux-arm64",
            Platform.MacOS_ARM64:   "MacOS-arm64",
        }
        return mapping[platform_value]

    @staticmethod
    @check_arguments
    def platform_from_dash_str(platform_str: str) -> Platform:
        mapping = {
            "Windows-x64": Platform.Windows_AMD64,
            "Linux-x64":   Platform.Linux_AMD64,
            "Linux-arm64": Platform.Linux_ARM64,
            "MacOS-arm64":   Platform.MacOS_ARM64,
        }
        if platform_str not in mapping:
            raise ValueError(f"Unsupported platform string: {platform_str}")
        return mapping[platform_str]

    @staticmethod
    @check_arguments
    def platform_to_docker_platform_str(platform_value: Platform) -> str:
        mapping = {
            Platform.Windows_AMD64: "windows/amd64",
            Platform.Linux_AMD64:   "linux/amd64",
            Platform.Linux_ARM64:   "linux/arm64",
            Platform.MacOS_ARM64:   "linux/arm64",  # macOS → linux container
        }
        return mapping[platform_value]

    @staticmethod
    @check_arguments
    def platform_to_dotnet_runtime_identifier(platform_value: Platform) -> str:
        mapping = {
            Platform.Windows_AMD64: "win-x64",
            Platform.Linux_AMD64:   "linux-x64",
            Platform.Linux_ARM64:   "linux-arm64",
            Platform.MacOS_ARM64:   "osx-arm64",
        }
        return mapping[platform_value]

    @staticmethod
    @check_arguments
    def platform_to_go_runtime_identifier(platform_value: Platform) -> str:
        mapping = {
            Platform.Linux_AMD64:   "amd64",
            Platform.Linux_ARM64:   "arm64",
        }
        return mapping[platform_value]

    @staticmethod
    @check_arguments
    def get_all_platforms() -> list[Platform]:
        return [
            Platform.Windows_AMD64,
            Platform.Linux_AMD64,
            Platform.Linux_ARM64,
            Platform.MacOS_ARM64,
        ]

    @staticmethod
    @check_arguments
    def get_scriptcollection_configuration_folder() -> str:
        result = os.path.join(str(Path.home()), ".ScriptCollection")
        result = GeneralUtilities.normalize_path(result)
        GeneralUtilities.ensure_directory_exists(result)
        return result

    @staticmethod
    @check_arguments
    def get_python_executable() -> str:
        configured_file = os.path.join(GeneralUtilities.get_scriptcollection_configuration_folder(), "PythonExecutable.txt")
        if os.path.isfile(configured_file):
            result = GeneralUtilities.read_text_from_file(configured_file).strip()
            GeneralUtilities.assert_condition(os.path.isfile(result), f"Python executable does not exist: '{result}'")
        elif GeneralUtilities.string_has_content(sys.executable):
            result = sys.executable
        else:
            result = "python"
        return result

    @staticmethod
    @check_arguments
    def get_docker_executable() -> str:
        configured_file = os.path.join(GeneralUtilities.get_scriptcollection_configuration_folder(), "DockerExecutable.txt")
        if os.path.isfile(configured_file):
            result = GeneralUtilities.read_text_from_file(configured_file).strip()
            GeneralUtilities.assert_condition(os.path.isfile(result), f"Docker executable does not exist: '{result}'")
        elif GeneralUtilities.string_has_content(sys.executable):
            result = sys.executable
        else:
            result = "docker"
        return result
