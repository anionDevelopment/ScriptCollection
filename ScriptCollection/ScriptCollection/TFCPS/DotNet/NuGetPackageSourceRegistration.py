import re
from ...GeneralUtilities import GeneralUtilities
from ...ScriptCollectionCore import ScriptCollectionCore
from ...SCLog import LogLevel
from ..PackageSource import PackageSource
from ..TFCPS_Tools_General import TFCPS_Tools_General


class NuGetPackageSourceRegistration:
    """Registers the NuGet-sources which are declared for the current machine (see TFCPS_Tools_General.get_declared_package_sources). It is
    used by every DotNet-codeunit-build and by the command-line-tool 'scregisterpackagesources' (which the agent-sandbox of scrais runs before
    the agent starts), so a source is registered on the same way everywhere."""

    #the output of the dotnet-cli is localized. The language is set explicitly because the output of "dotnet nuget list source" gets parsed, which would otherwise only work on machines which are configured to use english.
    __dotnet_cli_environment_variables: dict = {"DOTNET_CLI_UI_LANGUAGE": "en-US"}
    __sc: ScriptCollectionCore = None
    __tfcps_tools_general: TFCPS_Tools_General = None

    def __init__(self, sc: ScriptCollectionCore, tfcps_tools_general: TFCPS_Tools_General):
        self.__sc = sc
        self.__tfcps_tools_general = tfcps_tools_general

    @GeneralUtilities.check_arguments
    def register_declared_package_sources(self, folder: str) -> None:
        """Ensures that every NuGet-source which is declared for this machine is registered with its current credentials, so a codeunit can
        also use dependencies which are not available on nuget.org. The dotnet-cli is run in the given folder.
        A source which is already registered under the declared name is removed and registered again, so an outdated registration (for
        example one which points to another url) can not let the registration fail. Sources which are not declared are not touched at
        all: the registration is stored in the NuGet-configuration of the current user, which - when the build runs directly on the
        host - is the configuration the user also uses for their own work and which must not be destroyed by a build."""
        package_sources: list[PackageSource] = self.__tfcps_tools_general.get_declared_package_sources("CSharp")
        if len(package_sources) == 0:
            return
        for package_source in package_sources:
            registered_sources: dict[str, str] = self.__get_registered_nuget_sources(folder)
            name_of_source_with_same_name: str = None
            name_of_source_with_same_url: str = None
            for registered_name, registered_url in registered_sources.items():
                if registered_name.lower() == package_source.name.lower():
                    name_of_source_with_same_name = registered_name
                elif self.__nuget_sources_are_equal(registered_url, package_source.url):
                    #the same feed can already be registered under another name (which is the usual case on a machine on which the user
                    #configured the feed manually). Such a source is updated instead of being added a second time, because a second
                    #registration of the same url would let every restore query the feed twice.
                    name_of_source_with_same_url = registered_name
            if name_of_source_with_same_name is not None:
                self.__remove_nuget_source(folder, name_of_source_with_same_name)
            if name_of_source_with_same_url is None:
                arguments = ["nuget", "add", "source", package_source.url, "--name", package_source.name]
            else:
                #the credentials are set again even when the source already exists, because a token can have been rotated since it was registered.
                arguments = ["nuget", "update", "source", name_of_source_with_same_url, "--source", package_source.url]
            if package_source.has_credentials():
                arguments = arguments+["--username", package_source.username, "--password", package_source.password]
                if not GeneralUtilities.current_system_is_windows():
                    #without this the password can not be encrypted, which lets the command fail on the operating-systems which do not support the encryption.
                    arguments.append("--store-password-in-clear-text")
            arguments_for_log = list(arguments)
            if package_source.has_credentials():
                arguments_for_log[arguments_for_log.index("--password")+1] = "***"#the password must not be written to the build-log
            self.__sc.log.log(f"Add NuGet-source \"{package_source.name}\" ({package_source.url})..." if name_of_source_with_same_url is None else f"Update the already registered NuGet-source \"{name_of_source_with_same_url}\" ({package_source.url})...", LogLevel.Debug)
            self.__sc.run_program_argsasarray("dotnet", arguments, folder, arguments_for_log=arguments_for_log, print_live_output=False, env_vars=self.__dotnet_cli_environment_variables)

    @GeneralUtilities.check_arguments
    def __remove_nuget_source(self, folder: str, name: str) -> None:
        """Removes the registration of the NuGet-source with the given name, so it can be registered again with its currently declared url and credentials."""
        self.__sc.log.log(f"Remove the outdated registration of the NuGet-source \"{name}\"...", LogLevel.Debug)
        self.__sc.run_program_argsasarray("dotnet", ["nuget", "remove", "source", name], folder, print_live_output=False, env_vars=self.__dotnet_cli_environment_variables)

    @GeneralUtilities.check_arguments
    def __get_registered_nuget_sources(self, folder: str) -> dict[str, str]:
        """Returns the NuGet-sources which are registered for the given folder as a mapping of their name to their url. The sources are
        read from the output of "dotnet nuget list source", which prints the name (with its state) and the url of a source in two
        consecutive lines."""
        result: dict[str, str] = {}
        list_result = self.__sc.run_program_argsasarray("dotnet", ["nuget", "list", "source"], folder, throw_exception_if_exitcode_is_not_zero=False, print_live_output=False, env_vars=self.__dotnet_cli_environment_variables)
        name_pattern = re.compile(r"^\s*\d+\.\s+(.+?)\s+\[[^\[\]]+\]\s*$")
        current_name: str = None
        for line in list_result[1].splitlines():
            match = name_pattern.match(line)
            if match is not None:
                current_name = match.group(1).strip()
            elif current_name is not None and GeneralUtilities.string_has_content(line):
                result[current_name] = line.strip()
                current_name = None
        return result

    @GeneralUtilities.check_arguments
    def __nuget_sources_are_equal(self, url: str, other_url: str) -> bool:
        """Compares two urls of package-sources. A trailing slash and the case are ignored because they do not address a different feed."""
        return url.strip().rstrip("/").lower() == other_url.strip().rstrip("/").lower()
