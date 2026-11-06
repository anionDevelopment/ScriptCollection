import os
import re
from ..GeneralUtilities import GeneralUtilities
from ..ScriptCollectionCore import ScriptCollectionCore
from .TFCPS_Tools_General import TFCPS_Tools_General


class ContainerMount:
    """A file or folder of the host which is made available in a container."""
    source: str = None
    target: str = None
    read_only: bool = None

    def __init__(self, source: str, target: str, read_only: bool):
        self.source = source
        self.target = target
        self.read_only = read_only


class ContainerBuildEnvironment:
    """The build-environment which a container gets from the host on which it is started: the mounts, the environment-variables and the
    host-preparation-hook. It is the one place which defines it, so that every container which builds a repository (the build-container of
    'scbuildcodeunits -c' and the agent-sandbox of 'scrais') gets the same one. How the mounts are applied (bind-mount or copy) is decided by
    the caller, because that depends on where the caller itself runs. See the article "Configuration-folder" of the reference for what is
    mounted and why."""

    __sc: ScriptCollectionCore = None
    __tfcps_tools_general: TFCPS_Tools_General = None
    __repository: str = None

    def __init__(self, sc: ScriptCollectionCore, tfcps_tools_general: TFCPS_Tools_General, repository: str):
        self.__sc = sc
        self.__tfcps_tools_general = tfcps_tools_general
        self.__repository = repository

    @GeneralUtilities.check_arguments
    def run_host_preparation_hook(self, build_arguments: list[str]) -> None:
        """Runs the optional user-specific script which prepares this host for a container-start (for example to log in to the registry the
        image is pulled from). It has to run before get_environment_variables, so it can also create the files their values are read from."""
        self.__tfcps_tools_general.run_custom_script_if_available(self.__tfcps_tools_general.get_custom_script_file("CustomPreCodeUnitBuildScriptForContainer.py"), build_arguments)

    @GeneralUtilities.check_arguments
    def get_mounts(self) -> list[ContainerMount]:
        """Returns the files and folders of this host which a container gets. A part which does not exist on this host is not returned."""
        result: list[ContainerMount] = []

        #the optional user-specific scripts which prepare the container itself. the whole folder (not only the pre-codeunit-build-hook
        #itself) is mounted, so the hook can start a sibling script placed next to it (for example to keep the hook independent of a
        #package it only installs, while the actual preparation-logic which needs that package lives in the sibling script; see
        #TFCPS_Tools_General.get_custom_scripts_folder_for_container). The mount is writable (not read-only) because the scripts in that
        #folder also use it as their own download-cache-folder. A build inside the container runs the hook (see
        #TFCPS_CodeUnit_BuildCodeUnits.__run_custom_pre_codeunit_build_script).
        custom_scripts_folder: str = self.__tfcps_tools_general.get_custom_scripts_folder_for_container()
        if os.path.isdir(custom_scripts_folder):
            result.append(ContainerMount(custom_scripts_folder, self.__tfcps_tools_general.get_folder_of_custom_scripts_in_container(), False))

        #the machine-wide image-registries-file of this host, so the container takes the images from the same custom registries as this
        #host. Without it the container would find no mapping at all - the configuration-folder inside the container belongs to the
        #container-user and is empty - and would therefore fall back to the upstream-registries defined in the repository, which are
        #rate-limited. It is read-only because a build never changes the file.
        oci_image_manager = self.__tfcps_tools_general.oci_image_manager
        image_registries_file: str = oci_image_manager.get_image_registries_file_in_configuration_folder()
        if os.path.isfile(image_registries_file):
            result.append(ContainerMount(image_registries_file, oci_image_manager.get_image_registries_file_in_container(), True))

        #the 'TFCPS'-folder of the configuration-folder of this host, so the container resolves the required environment-variables of the
        #product (see TFCPS_Tools_General.get_required_environment_variables) and the OCI-registry-credentials (see
        #ScriptCollectionCore.get_docker_registry_credentials_from_environment_variables) exactly like this host does - including a registry
        #which is not publicly readable. The whole folder is mounted and not only EnvironmentVariables.csv in it, because a value of that file
        #can point to a secret-file next to it ('file'-kind with a relative path, which is the recommended form) and such a value is resolved
        #relative to the file itself. Only this folder (and not the whole configuration-folder) is mounted, so nothing else of it is exposed.
        #It is read-only because a build never changes it.
        tfcps_configuration_folder: str = self.__sc.get_tfcps_configuration_folder()
        if os.path.isdir(tfcps_configuration_folder):
            result.append(ContainerMount(tfcps_configuration_folder, self.__sc.get_tfcps_configuration_folder_in_container(), True))

        #the files of the root-CA-certificates which this host declares via TrustedRootCA_<name>_Path. They are installed into the
        #trust-store of the container by the entrypoint of the SCBuilder-image (see __get_trusted_root_cas).
        file_cas, _ = self.__get_trusted_root_cas()
        for ca_name, host_path in file_cas.items():
            result.append(ContainerMount(host_path, f"/Workspace/RootCAs/{ca_name}.crt", True))
        return result

    @GeneralUtilities.check_arguments
    def get_environment_variables(self) -> dict[str, str]:
        """Returns the environment-variables (name and value) which a container gets: the ones which are declared as required in
        <repository>/.ScriptCollection/ProductInformation.xml (including the ones which are declared for this machine, see
        TFCPS_Tools_General.get_required_environment_variable_names) and the TrustedRootCA_<name>_ContentBase64-variables. The values are
        typically secrets: a caller must give them to docker through the environment of the docker-client and pass only their names as
        arguments, because arguments are written to the log and are visible in the process-list of this host."""
        result: dict[str, str] = self.__tfcps_tools_general.get_required_environment_variables(self.__repository)
        _, inline_cas = self.__get_trusted_root_cas()
        result.update(inline_cas)
        return result

    @GeneralUtilities.check_arguments
    def __get_trusted_root_cas(self) -> tuple[dict[str, str], dict[str, str]]:
        """Resolves the TrustedRootCA_<name>_Path and TrustedRootCA_<name>_ContentBase64 environment-variables of this host. Returns
        (file_cas, inline_cas):
        - file_cas: <name> -> host-path of the certificate for each _Path-variable.
        - inline_cas: variable-name -> value for each _ContentBase64-variable.
        Candidate-names are collected from two sources (identical to the OCI-registry-credentials, see
        ScriptCollectionCore.__get_defined_oci_registry_names): the machine-wide environment-variables-configuration-file and the
        environment of the current process. The value is then resolved through ScriptCollectionCore.resolve_environment_variable, so a
        CSV-entry takes precedence over an environment-variable of the same name - consistent with every other environment-variable
        this script-collection resolves. If a name is declared in the file but its value can not be determined there (for example a
        'file'-entry pointing to a missing file), the resolver falls back to the environment and fails only if neither source yields a
        value. The actual trust-store update happens in SCBuilder's EntryPoint.sh, which scans /Workspace/RootCAs and the
        TrustedRootCA_*-environment-variables and runs update-ca-certificates once before any build-step. The <name>-part becomes the
        filename inside /usr/local/share/ca-certificates/ and must therefore be unique across the two env-var-forms; a duplicate is
        rejected here with a clear error, before the container is started."""
        path_pattern = re.compile(r"^TrustedRootCA_(.+)_Path$", re.IGNORECASE)
        content_b64_pattern = re.compile(r"^TrustedRootCA_(.+)_ContentBase64$", re.IGNORECASE)
        #collect every candidate-variable-name from both sources before any value is resolved; this way a secret-value is read only for
        #a name that is actually declared and the discovery is identical to the OCI-registry-credential-discovery. The configuration-
        #file is scanned before the environment and a name found in both is kept with the casing of the file: on Windows, os.environ
        #normalizes a variable-name to uppercase as soon as it is set, so without this preference the same declaration in both places
        #would be treated as two different names and resolution would silently pick the environment-value instead of the file-value.
        candidate_names: dict[str, str] = {}#lower-case variable-name -> canonical variable-name (file-casing preferred)
        configuration_file = self.__sc.get_environment_variables_configuration_file()
        if os.path.isfile(configuration_file):
            for entry in GeneralUtilities.read_csv_file(configuration_file, True):
                if 0 == len(entry):
                    continue
                env_name = entry[0]
                if path_pattern.match(env_name) is not None or content_b64_pattern.match(env_name) is not None:
                    candidate_names.setdefault(env_name.lower(), env_name)
        for env_name in os.environ.keys():
            if path_pattern.match(env_name) is not None or content_b64_pattern.match(env_name) is not None:
                candidate_names.setdefault(env_name.lower(), env_name)
        seen_names: dict[str, str] = {}#lower-case <name>-part -> originating variable-name, used only to produce an informative error on duplicate <name>.
        file_cas: dict[str, str] = {}
        inline_cas: dict[str, str] = {}
        #sorted so the log-output (and therefore the order of the mounts and environment-variables) stays deterministic across runs.
        for env_name in sorted(candidate_names.values(), key=str.lower):
            env_value = self.__sc.resolve_environment_variable(env_name, f"the TrustedRootCA-mechanism (declared via \"{env_name}\")")
            if not GeneralUtilities.string_has_content(env_value):
                continue
            path_match = path_pattern.match(env_name)
            if path_match is not None:
                ca_name = path_match.group(1)
                self.__check_trusted_root_ca_name_is_unique(seen_names, ca_name, env_name)
                host_path = env_value.strip()
                if not os.path.isfile(host_path):
                    raise ValueError(f"Environment-variable \"{env_name}\" points to a file which does not exist on this host: \"{host_path}\".")
                with open(host_path, "r", encoding="utf-8", errors="replace") as pem_file:
                    head = pem_file.read(64)
                if "-----BEGIN CERTIFICATE-----" not in head:
                    raise ValueError(f"Environment-variable \"{env_name}\" (\"{host_path}\") does not look like a PEM-encoded certificate (missing \"-----BEGIN CERTIFICATE-----\"-header).")
                file_cas[ca_name] = host_path
                continue
            content_b64_match = content_b64_pattern.match(env_name)
            if content_b64_match is not None:
                ca_name = content_b64_match.group(1)
                self.__check_trusted_root_ca_name_is_unique(seen_names, ca_name, env_name)
                inline_cas[env_name] = env_value
                continue
        return file_cas, inline_cas

    @GeneralUtilities.check_arguments
    def __check_trusted_root_ca_name_is_unique(self, seen_names: dict[str, str], ca_name: str, env_name: str) -> None:
        key = ca_name.lower()
        if key in seen_names:
            raise ValueError(f"Multiple TrustedRootCA-definitions for name \"{ca_name}\" found (\"{seen_names[key]}\" and \"{env_name}\"). The <name>-part becomes the filename in the trust-store and must therefore be unique across _Path and _ContentBase64.")
        seen_names[key] = env_name
