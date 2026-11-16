import os
import yaml
from packaging.version import Version
from ..GeneralUtilities import GeneralUtilities
from ..ScriptCollectionCore import ScriptCollectionCore
from ..GeneralUtilities import VersionEcholon
from ..SCLog import LogLevel
from .AbstractImageHandler import AbstractImageHandler
from .OCIRegistryClient import OCIRegistryClient
from .ConcreteImageHandlers.ImageHandlerDebian import ImageHandlerDebian
from .ConcreteImageHandlers.ImageHandlerDebianSlim import ImageHandlerDebianSlim
from .ConcreteImageHandlers.ImageHandlerGeneric import ImageHandlerGeneric
from .ConcreteImageHandlers.ImageHandlerGenericV import ImageHandlerGenericV
from .ConcreteImageHandlers.ImageHandlerGitlabCE import ImageHandlerGitlabCE
from .ConcreteImageHandlers.ImageHandlerGitlabEE import ImageHandlerGitlabEE

class OCIImageManager:

    __sc:ScriptCollectionCore=None
    image_handler:list[AbstractImageHandler] = None
    registry_client:OCIRegistryClient = None
    #image-names for which it was already logged that the fallback-registry is used. The lookup happens for every image of
    #the repository and often several times per build, so without this the same hint would flood the log.
    __images_with_reported_fallback_registry:set[str] = None
    #availability of an image-address with tag in its registry. The address of an image is resolved several times per build and
    #the check costs a request to the registry, so its result is remembered for the runtime of this process.
    __availability_of_image:dict[str,bool] = None

    def __init__(self,sc:ScriptCollectionCore):
        if sc is None:
            sc=ScriptCollectionCore()
        self.__sc=sc
        self.__images_with_reported_fallback_registry=set()
        self.__availability_of_image=dict()
        self.registry_client=OCIRegistryClient(self.__sc)
        #the order matters: the first handler which can handle a tag is used, so the specific handlers have to be listed before the generic ones.
        self.image_handler=[
            ImageHandlerGitlabCE(),
            ImageHandlerGitlabEE(),
            ImageHandlerDebianSlim(),
            ImageHandlerDebian(),
            ImageHandlerGenericV(),
            ImageHandlerGeneric(),
        ]

    @GeneralUtilities.check_arguments
    def get_image_handler(self,image_name:str,tag:str)->AbstractImageHandler:
        for image_handler in self.image_handler:
            if image_handler.can_handle(image_name,tag):
                return image_handler
        raise ValueError(f"No image-handler available for tag \"{tag}\" of image \"{image_name}\".")

    @GeneralUtilities.check_arguments
    def get_repository_image_definition_file(self,repository:str)->str:
        self.__sc.assert_is_git_repository(repository)
        return os.path.join(repository,".ScriptCollection","OCIImages","ImageDefinition.csv")
    
    @GeneralUtilities.check_arguments
    def get_image_registries_file_in_container(self)->str:
        """Returns the file inside a build-container to which the host mounts its image-registries-file (see
        TFCPS_CodeUnit_BuildCodeUnits.__run_scriptcollection_executable_in_container). It is an own path (and not the
        configuration-folder of the container-user) because the home-folder inside the container depends on the user the
        image runs as, while this path is defined by the mount and is therefore identical for both sides."""
        return "/Workspace/ScriptCollectionConfiguration/OCIImages/ImageRegistries.csv"

    @GeneralUtilities.check_arguments
    def get_image_registries_file_in_configuration_folder(self)->str:
        """Returns the image-registries-file in the configuration-folder of the current user, and creates it if it does not exist yet.
        This is the file of the machine on which a command was started, so it is also the file which is mounted into a build-container
        (in contrast to get_global_docker_image_registries_file, which inside a container resolves to that mount instead)."""
        folder=os.path.join(self.__sc.get_global_cache_folder(),"OCIImages")
        GeneralUtilities.ensure_directory_exists(folder)
        result=os.path.join(folder,"ImageRegistries.csv")
        if not os.path.isfile(result):
            GeneralUtilities.ensure_file_exists(result)
            GeneralUtilities.write_lines_to_file(result,["ImageName;RegistryAddress"])
        return result

    @GeneralUtilities.check_arguments
    def get_global_docker_image_registries_file(self)->str:
        """Returns the machine-wide file which maps an image-name to the custom registry-address the image should be taken from.
        The file which the host mounted into a build-container has precedence over the file in the configuration-folder of the
        current user: in a container that configuration-folder belongs to the container-user and therefore never contains the
        configuration of the machine on which the build was started."""
        mounted_file=self.get_image_registries_file_in_container()
        if os.path.isfile(mounted_file):
            return mounted_file
        return self.get_image_registries_file_in_configuration_folder()
    
    @GeneralUtilities.check_arguments
    def get_used_images_in_repository(self,repository:str)->list[str]:
        result:list[str]=[]
        repository_image_definition_file=self.get_repository_image_definition_file(repository)
        for line in [f.split(";") for f in GeneralUtilities.read_nonempty_lines_from_file(repository_image_definition_file)[1:]]:
            result.append(line[0])
        return result

    @GeneralUtilities.check_arguments
    def custom_registry_is_defined(self,image_name:str)->bool:
        global_docker_image_registries_file=self.get_global_docker_image_registries_file()
        for line in  GeneralUtilities.read_nonempty_lines_from_file(global_docker_image_registries_file)[1:]:
            line_parts=line.split(";")
            if image_name==line_parts[0]:
                GeneralUtilities.assert_condition(GeneralUtilities.string_has_content(line_parts[1]),f"No registry defined for image {image_name}.")
                return True
        return False

    @GeneralUtilities.check_arguments
    def get_tag_for_image(self,repository:str,image_name:str)->str:
        repository_image_definition_file=self.get_repository_image_definition_file(repository)
        for line in [f.split(";") for f in GeneralUtilities.read_nonempty_lines_from_file(repository_image_definition_file)[1:]]:
            if image_name==line[0]:
                return line[2]
        raise ValueError(f"No tag defined for image \"{image_name}\".")

    @GeneralUtilities.check_arguments
    def get_custom_registry_address_for_image(self,image_name:str)->str:
        """Returns the registry-address which is defined for the image in the machine-wide image-registries-file, always without tag.
        Use custom_registry_is_defined to check whether such an address is defined for the image at all."""
        global_docker_image_registries_file=self.get_global_docker_image_registries_file()
        for line in [f.split(";") for f in GeneralUtilities.read_nonempty_lines_from_file(global_docker_image_registries_file)[1:]]:
            if image_name==line[0]:
                return line[1]
        raise ValueError(f"No custom registry is defined for image \"{image_name}\" in \"{global_docker_image_registries_file}\".")

    @GeneralUtilities.check_arguments
    def get_fallback_registry_address_for_image(self,repository:str,image_name:str)->str:
        """Returns the upstream-registry-address which the repository defines for the image, always without tag."""
        repository_image_definition_file=self.get_repository_image_definition_file(repository)
        for line in [f.split(";") for f in GeneralUtilities.read_nonempty_lines_from_file(repository_image_definition_file)[1:]]:
            if image_name==line[0]:
                return line[1]
        raise ValueError(f"No registry defined for image \"{image_name}\" in \"{repository_image_definition_file}\".")

    @GeneralUtilities.check_arguments
    def get_registry_address_for_image(self,repository:str,image_name:str)->str:
        """Returns the registry-address the image has to be taken from, always without tag.
        Example: if image_name==Debian this function returns something like "myregistry.example.com/debian".
        This is the custom registry-address which is defined for this machine if the image is really available there, and the
        upstream-registry-address which the repository defines otherwise."""
        fallback_registry_address=self.get_fallback_registry_address_for_image(repository,image_name)
        if self.custom_registry_is_defined(image_name):
            custom_registry_address=self.get_custom_registry_address_for_image(image_name)
            if self.__custom_registry_provides_image(custom_registry_address,self.get_tag_for_image(repository,image_name)):
                return custom_registry_address
            self.__report_usage_of_fallback_registry(image_name,fallback_registry_address,f"the image is not available in the custom registry \"{custom_registry_address}\"")
        else:
            self.__report_usage_of_fallback_registry(image_name,fallback_registry_address,f"no custom registry is defined for the image in \"{self.get_global_docker_image_registries_file()}\"")
        return fallback_registry_address

    @GeneralUtilities.check_arguments
    def __custom_registry_provides_image(self,custom_registry_address:str,tag:str)->bool:
        """Returns whether the image can be used with this tag from the custom registry-address, which is the case when it is already
        available in the local image-store of the docker-daemon or when the custom registry provides it.
        The local image-store is checked first because an image which is already available there is not downloaded at all (see
        ScriptCollectionCore.docker_pull), so asking the registry would only cost a request - and would make a build which does not need
        any download depend on a reachable registry.
        A custom registry is typically not publicly readable, so the login to the registries which are defined for this machine is done
        before the registry is asked; without it the answer would be that the image is not available although it only is not readable
        without credentials. A failed login does not break the build: the login can fail because the registry is not reachable, because
        the credentials are missing or wrong, or because the docker-daemon is not available at all, and in each of these cases the image
        can not be taken from the custom registry. The login-failure is therefore treated like an image which is not available in the
        custom registry, so that a warning is logged and the fallback-registry is used (see get_registry_address_for_image) instead of
        aborting the build."""
        image_with_tag=f"{custom_registry_address}:{tag}"
        if image_with_tag not in self.__availability_of_image:
            if self.__sc.local_docker_image_exists(custom_registry_address,tag):
                self.__availability_of_image[image_with_tag]=True
            else:
                try:
                    self.__sc.login_to_defined_docker_registries()
                except Exception as exception:
                    self.__sc.log.log(f"The login to the defined docker-registries failed, so the image \"{image_with_tag}\" is treated as not available in the custom registry \"{custom_registry_address}\" and the fallback-registry is used instead. Reason: {exception}",LogLevel.Warning)
                    self.__availability_of_image[image_with_tag]=False
                    return self.__availability_of_image[image_with_tag]
                self.__availability_of_image[image_with_tag]=self.__sc.image_is_available_in_registry(custom_registry_address,tag)
        return self.__availability_of_image[image_with_tag]

    @GeneralUtilities.check_arguments
    def __report_usage_of_fallback_registry(self,image_name:str,fallback_registry_address:str,reason:str)->None:
        """Logs that the image is taken from the upstream-registry which the repository defines, together with the reason why the custom
        registry is not used. The fallback exists so that a freshly cloned product is buildable without further setup and so that a custom
        registry which does not provide the image does not break a build, but an upstream-registry is typically rate-limited, so using it
        is worth a hint."""
        if image_name in self.__images_with_reported_fallback_registry:
            return
        self.__images_with_reported_fallback_registry.add(image_name)
        self.__sc.log.log(f"The fallback-registry \"{fallback_registry_address}\" is used for image \"{image_name}\" because {reason}.",LogLevel.Warning)

    @GeneralUtilities.check_arguments
    def get_registry_address_for_image_with_default_tag(self,repository:str,image_name:str)->str:
        return f"{self.get_registry_address_for_image(repository,image_name)}:{self.get_tag_for_image(repository,image_name)}"

    @GeneralUtilities.check_arguments
    def update_default_tag_for_images_in_image_definitions_file(self,repository:str,search_in_custom_registry_only_if_available:bool)->None:
        """Updates the default-tag of every image in the image-definition-file of the repository to the latest available tag with the same format.
        If search_in_custom_registry_only_if_available is True then only the custom registry which is defined for an image on this machine is
        asked for newer tags, so that only tags are chosen which are available there; an image without custom registry keeps its tag then."""
        file=self.get_repository_image_definition_file(repository)
        GeneralUtilities.assert_file_exists(file)
        lines=GeneralUtilities.read_nonempty_lines_from_file(file)
        new_lines:list[str]=[]
        #file looks like:
        #ImageName;UpstreamRegistryAddress;DefaultTag
        #Debian;docker.io/library/debian;13.4-slim
        for line in lines:
            if line.startswith("ImageName;"): #header line
                new_lines.append(line)
                continue
            line_parts=line.split(";")
            image_name=line_parts[0]
            registry_address=line_parts[1]
            default_tag=line_parts[2]
            tag=default_tag
            addresses_to_check=self.__get_registry_addresses_to_search_for_newer_tags(image_name,registry_address,search_in_custom_registry_only_if_available)
            if len(addresses_to_check)==0:
                self.__sc.log.log(f"The tag of image \"{image_name}\" is not updated because no custom registry is defined for it in \"{self.get_global_docker_image_registries_file()}\".",LogLevel.Warning)
            else:
                try:
                    tag=self.get_latest_tag_of_image(image_name,addresses_to_check,default_tag,VersionEcholon.LatestVersion)
                except Exception as e:
                    self.__sc.log.log(f"Could not determine the latest tag of image \"{image_name}\" using the registries {', '.join(addresses_to_check)}. Reason: {type(e).__name__}: {str(e)}",LogLevel.Warning)
            if tag!=default_tag:
                self.__sc.log.log(f"Update tag of image \"{image_name}\" from \"{default_tag}\" to \"{tag}\".",LogLevel.Information)
            new_lines.append(f"{image_name};{registry_address};{tag}")
        GeneralUtilities.write_lines_to_file(file,new_lines)

    @GeneralUtilities.check_arguments
    def __get_registry_addresses_to_search_for_newer_tags(self,image_name:str,upstream_registry_address:str,search_in_custom_registry_only_if_available:bool)->list[str]:
        result:list[str]=[]
        if self.custom_registry_is_defined(image_name):
            #the custom registry-address is used directly (and not get_registry_address_for_image) because this function does not
            #pull an image but asks the registry which tags it has, so it does not matter whether that registry currently provides
            #the image with the tag which is defined at the moment.
            result.append(self.get_custom_registry_address_for_image(image_name))
        if not search_in_custom_registry_only_if_available:
            result.append(upstream_registry_address)
        return result

    @GeneralUtilities.check_arguments
    def get_latest_tag_of_image(self,image_name:str,registry_addresses:list[str],current_tag:str,echolon:VersionEcholon)->str:
        """Returns the tag the image should be updated to according to the echolon, considering the tags of all given registry-addresses
        (always without tag, for example "docker.io/library/debian").
        Only tags with the same format as the current tag are candidates (see AbstractImageHandler.tag_has_same_format). The current tag is
        always a candidate, so the result is never a downgrade."""
        image_handler=self.get_image_handler(image_name,current_tag)
        if echolon==VersionEcholon.NoUpdate:
            return current_tag
        candidate_tags:list[str]=[current_tag]
        for registry_address in registry_addresses:
            for tag in self.registry_client.get_tags(registry_address):
                if tag not in candidate_tags and image_handler.tag_has_same_format(image_name,tag,current_tag):
                    candidate_tags.append(tag)
        if echolon==VersionEcholon.CustomAlgorithm:
            return image_handler.get_latest_tag_custom(image_name,current_tag,candidate_tags)
        tags_by_version:dict[Version,str]={}
        for tag in candidate_tags:
            #setdefault, because different tags can represent the same version (like "13.4" and "13.04"); then the first one (the current tag if affected) is used.
            tags_by_version.setdefault(image_handler.tag_to_version(image_name,tag),tag)
        current_version=image_handler.tag_to_version(image_name,current_tag)
        return tags_by_version[self.choose_version(set(tags_by_version.keys()),current_version,echolon)]

    @GeneralUtilities.check_arguments
    def choose_version(self,available_versions:set[Version],current_version:Version,echolon:VersionEcholon)->Version:
        """Returns the version out of the available versions which should be used according to the echolon.
        available_versions must contain current_version. The echolons NoUpdate and CustomAlgorithm are not handled here because they do
        not choose out of the available versions."""
        GeneralUtilities.assert_condition(current_version in available_versions,f"The available versions do not contain the current version {current_version}.")
        result:Version=None
        match echolon:
            case VersionEcholon.LatestPatch:#caution: this never updates the minor or major version
                #take the latest available patch-version for the current minor-version of the image.
                result=self.__get_latest_patch(available_versions,current_version.major,current_version.minor)
            case VersionEcholon.LatestPatchOrLatestMinor:#caution: this never updates the major version
                #take the latest available patch-version for the current minor-version of the image if there is a newer patch version available.
                #otherwise take the latest available patch-version of the next available minor-version within the current major-version.
                result=self.__get_latest_patch_or_next_minor(available_versions,current_version)
            case VersionEcholon.LatestPatchOrLatestMinorOrNextMajor:#usual case for images which have complex migrations sometimes, like GitLab or NextCloud
                #like LatestPatchOrLatestMinor, but if there is neither a newer patch nor a newer minor-version available within the current major-version
                #then take the latest available patch-version of the lowest minor-version of the next available major-version.
                result=self.__get_latest_patch_or_next_minor(available_versions,current_version)
                if result==current_version:
                    next_major=self.__get_next_higher_value({v.major for v in available_versions},current_version.major)
                    if next_major is not None:
                        lowest_minor=min({v.minor for v in available_versions if v.major==next_major})
                        result=self.__get_latest_patch(available_versions,next_major,lowest_minor)
            case VersionEcholon.LatestVersion:#usual case for most images
                #take the latest available version of the image.
                result=max(available_versions)
            case _:
                raise ValueError(f"Echolon \"{echolon.name}\" does not choose a version out of the available versions.")
        return result

    @GeneralUtilities.check_arguments
    def __get_latest_patch(self,available_versions:set[Version],major:int,minor:int)->Version:
        """Returns the latest available patch-version for the given major- and minor-version or None if no such version is available."""
        matching_versions={v for v in available_versions if v.major==major and v.minor==minor}
        if len(matching_versions)==0:
            return None
        return max(matching_versions)

    @GeneralUtilities.check_arguments
    def __get_latest_patch_or_next_minor(self,available_versions:set[Version],current_version:Version)->Version:
        latest_patch=self.__get_latest_patch(available_versions,current_version.major,current_version.minor)
        if latest_patch is not None and latest_patch>current_version:
            return latest_patch
        next_minor=self.__get_next_higher_value({v.minor for v in available_versions if v.major==current_version.major},current_version.minor)
        if next_minor is not None:
            return self.__get_latest_patch(available_versions,current_version.major,next_minor)
        return current_version

    @GeneralUtilities.check_arguments
    def __get_next_higher_value(self,values:set[int],current_value:int)->int:
        """Returns the smallest value in values which is greater than current_value or None if no such value exists."""
        higher_values={v for v in values if v>current_value}
        if len(higher_values)==0:
            return None
        return min(higher_values)

    @GeneralUtilities.check_arguments
    def get_images_used_in_docker_compose_file(self,docker_compose_file:str)->dict[str,tuple[str,str,str]]:#returns dict[service_name,[image_name,image_address,current_tag]]
        GeneralUtilities.assert_file_exists(docker_compose_file)
        result: dict[str, tuple[str, str, str]] = {}
        with open(docker_compose_file, "r", encoding="utf-8") as f:
            compose_data = yaml.safe_load(f)
        services = (compose_data or {}).get("services", {}) or {}
        for service_name, service_definition in services.items():
            if not isinstance(service_definition, dict):
                continue
            image_value = service_definition.get("image")
            if not isinstance(image_value, str) or not image_value:
                continue
            last_colon = image_value.rfind(":")
            last_slash = image_value.rfind("/")
            if last_colon == -1 or last_colon < last_slash:
                image_address = image_value
                current_tag = "latest"
            else:
                image_address = image_value[:last_colon]
                current_tag = image_value[last_colon + 1:]
            image_name = image_address.rsplit("/", 1)[-1]
            result[service_name] = (image_name, image_address, current_tag)
        return result

    @GeneralUtilities.check_arguments
    def update_image_in_docker_compose_file(self,docker_compose_file:str,default_echolon:VersionEcholon=None,per_image_echolons:dict[str,VersionEcholon]=None,verbose:bool=False)->None:
        if per_image_echolons is None:
            per_image_echolons = {}
        if verbose:
            self.__sc.log.log(f"Checking images in docker-compose-file \"{docker_compose_file}\" for updates.",LogLevel.Information)
        for service,service_information in self.get_images_used_in_docker_compose_file(docker_compose_file).items():
            image_name=service_information[0]
            image_address=service_information[1]
            current_tag=service_information[2]
            image_handler=self.get_image_handler(image_name,current_tag)
            effective_echolon=per_image_echolons.get(image_name,default_echolon)
            if effective_echolon is None:
                effective_echolon=image_handler.get_default_echolon_for_update(image_name)
            if verbose:
                self.__sc.log.log(f"Service \"{service}\": checking image \"{image_address}:{current_tag}\" using echolon \"{effective_echolon.name}\".",LogLevel.Information)
            new_tag=self.get_latest_tag_of_image(image_name,[image_address],current_tag,effective_echolon)
            if new_tag != current_tag:
                new_image_reference = f"{image_address}:{new_tag}"
                if verbose:
                    self.__sc.log.log(f"Service \"{service}\": updating image \"{image_address}\" from tag \"{current_tag}\" to tag \"{new_tag}\".",LogLevel.Information)
                with open(docker_compose_file, "r", encoding="utf-8") as f:
                    compose_data = yaml.safe_load(f)
                compose_data["services"][service]["image"] = new_image_reference
                with open(docker_compose_file, "w", encoding="utf-8") as f:
                    yaml.safe_dump(compose_data, f, default_flow_style=False, sort_keys=False)
            else:
                if verbose:
                    self.__sc.log.log(f"Service \"{service}\": image \"{image_address}\" is already up-to-date at tag \"{current_tag}\".",LogLevel.Information)
