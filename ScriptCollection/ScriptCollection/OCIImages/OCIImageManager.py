import os
import yaml
from packaging.version import Version
from ..GeneralUtilities import GeneralUtilities
from ..ScriptCollectionCore import ScriptCollectionCore
from ..GeneralUtilities import VersionEcholon
from ..SCLog import LogLevel
from .AbstractImageHandler import AbstractImageHandler
from .ConcreteImageHandlers.ImageHandlerDebian import ImageHandlerDebian
from .ConcreteImageHandlers.ImageHandlerDebianSlim import ImageHandlerDebianSlim
from .ConcreteImageHandlers.ImageHandlerGeneric import ImageHandlerGeneric
from .ConcreteImageHandlers.ImageHandlerGenericV import ImageHandlerGenericV
from .ConcreteImageHandlers.ImageHandlerGitlabCE import ImageHandlerGitlabCE
from .ConcreteImageHandlers.ImageHandlerGitlabEE import ImageHandlerGitlabEE

class OCIImageManager:

    __sc:ScriptCollectionCore=None
    image_handler:list[AbstractImageHandler]

    def __init__(self,sc:ScriptCollectionCore):
        if sc is None:
            sc=ScriptCollectionCore()
        self.__sc=sc
        self.image_handler=[
            ImageHandlerDebian(),
            ImageHandlerDebianSlim(),
            ImageHandlerGeneric(),
            ImageHandlerGenericV(),
            ImageHandlerGitlabCE(),
            ImageHandlerGitlabEE(),
        ]

    @GeneralUtilities.check_arguments
    def get_image_handler(self,image_name:str)->AbstractImageHandler:
        for image_handler in self.image_handler: 
            if image_handler.can_handle(image_name):
                return image_handler
        raise ValueError(f"No image-handler available for image \"{image_name}\".")

    @GeneralUtilities.check_arguments
    def get_repository_image_definition_file(self,repository:str)->str:
        self.__sc.assert_is_git_repository(repository)
        return os.path.join(repository,".ScriptCollection","OCIImages","ImageDefinition.csv")
    
    @GeneralUtilities.check_arguments
    def get_global_docker_image_registries_file(self)->str:
        folder=os.path.join(self.__sc.get_global_cache_folder(),"OCIImages")
        GeneralUtilities.ensure_directory_exists(folder)
        result=os.path.join(folder,"ImageRegistries.csv")
        if not os.path.isfile(result):
            GeneralUtilities.ensure_file_exists(result)
            GeneralUtilities.write_lines_to_file(result,["ImageName;RegistryAddress"])
        return result
    
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
            splitted_line=line.split(";")
            if image_name==splitted_line[0]:
                GeneralUtilities.assert_condition(GeneralUtilities.string_has_content(splitted_line[1]),f"No registry defined for image {image_name}.")
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
    def get_registry_address_for_image(self,repository:str,image_name:str)->str:
        """Example: if image_name==Debian this function returns something like "myregistry.example.com/debian", always without tag."""
        if self.custom_registry_is_defined(image_name):
            #return image from custom registry-address
            global_docker_image_registries_file=self.get_global_docker_image_registries_file()
            for line in [f.split(";") for f in GeneralUtilities.read_nonempty_lines_from_file(global_docker_image_registries_file)[1:]]:
                if image_name==line[0]:
                    return line[1]
        else:
            #return fallback-registry-address
            repository_image_definition_file=self.get_repository_image_definition_file(repository)
            for line in [f.split(";") for f in GeneralUtilities.read_nonempty_lines_from_file(repository_image_definition_file)[1:]]:
                if image_name==line[0]:
                    return line[1]
        raise ValueError(f"No registry defined for image \"{image_name}\".")

    @GeneralUtilities.check_arguments
    def get_registry_address_for_image_with_default_tag(self,repository:str,image_name:str)->str:
        return f"{self.get_registry_address_for_image(repository,image_name)}:{self.get_tag_for_image(repository,image_name)}"

    @GeneralUtilities.check_arguments
    def update_default_tag_for_images_in_image_definitions_file(self,repository:str,search_in_custom_registry_only_if_available:bool)->None:
        file=f"{repository}/.ScriptCollection/OCIImages/ImageDefinition.csv"
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
            splitted_line=line.split(";")
            image_name=splitted_line[0]
            registry_address=splitted_line[1]
            default_tag=splitted_line[2]
            tag=default_tag
            try:
                addresses_to_check=[]
                if self.custom_registry_is_defined(image_name):
                    addresses_to_check.append(self.get_registry_address_for_image(repository,image_name))
                else:
                    if search_in_custom_registry_only_if_available:
                        raise ValueError(f"No custom registry defined for image {image_name}.")
                if not search_in_custom_registry_only_if_available:
                    addresses_to_check.append(registry_address)
                newest_versions:set[Version]={default_tag}
                current_version=Version(default_tag)
                for address in addresses_to_check:
                    newest_versions_for_address=self.get_available_versions_of_image_which_are_newer(image_name,address,current_version,VersionEcholon.LatestVersion)
                    if newest_versions_for_address is not None:
                        newest_versions.update(newest_versions_for_address)
                GeneralUtilities.assert_condition(len(newest_versions)>0,f"Could not find any version for image {image_name} in registry {registry_address}.")
                newest_version=max(newest_versions)
                tag=self.version_to_tag(image_name,newest_version)
            except Exception as e:
                self.__sc.log.log(f"Could not get tag for image {image_name} from registry {registry_address}. Reason: {str(e)}",LogLevel.Warning)
            new_lines.append(f"{image_name};{registry_address};{tag}")
        GeneralUtilities.write_lines_to_file(file,new_lines)

    @GeneralUtilities.check_arguments
    def get_available_versions_of_image_which_are_newer(self,image_name:str,registry_address:str,current_version:Version,echolon: VersionEcholon)->Version:
        #image_handler=self.get_image_handler(image_name)
        result= None #TODO calculate result using get_available_tags_of_image.
        #TODO if echolon is not none, then use echolon instead of the default echolon of the image-handler.
        #TODO return the versions sorted.
        #TODO if result is empty: return None
        return result
    
    @GeneralUtilities.check_arguments
    def get_available_tags_of_image(self,image_name:str,registry_address:str)->list[str]:
        """registry_address must have one of theese formats: "myregistry.example.com/debian" or "docker.io/debian" or "docker.io/myuser/debian".
        returns something like ["13.2-slim", "13.2", "13.3-slim", "13.3"]."""
        return self.get_image_handler(image_name).get_available_tags_of_image(image_name,registry_address)

    @GeneralUtilities.check_arguments
    def tag_to_version(self,image_name:str,tag:str)->Version:
        """registry_address must have one of theese formats: "myregistry.example.com/debian" or "docker.io/debian" or "docker.io/myuser/debian"."""
        return self.get_image_handler(image_name).tag_to_version(image_name, tag)

    @GeneralUtilities.check_arguments
    def version_to_tag(self,image_name:str,version:Version)->str:
        """registry_address must have one of theese formats: "myregistry.example.com/debian" or "docker.io/debian" or "docker.io/myuser/debian".
        returns something like "13.3-slim".
        If there are multiple tags available for a certain version then the image-handler decides which one will be returned."""
        return self.get_image_handler(image_name).version_to_tag(image_name,version)

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
    def update_image_in_docker_compose_file(self,docker_compose_file:str,default_echolon:VersionEcholon=None,per_image_echolons:dict[str,VersionEcholon]=None)->None:
        if per_image_echolons is None:
            per_image_echolons = {}
        for service,service_information in self.get_images_used_in_docker_compose_file(docker_compose_file).items():
            image_name=service_information[0]
            image_address=service_information[1]
            current_tag=service_information[2]
            image_handler=self.get_image_handler(image_name)
            effective_echolon=per_image_echolons.get(image_name,default_echolon)
            if effective_echolon is None:
                effective_echolon=image_handler.get_default_echolon_for_update()
            new_versions_for_address=self.get_available_versions_of_image_which_are_newer(image_name,image_address,self.tag_to_version(image_name,current_tag),effective_echolon)
            new_tag=self.version_to_tag(image_name,new_versions_for_address)
            if new_tag is not None and new_tag != current_tag:
                new_image_reference = f"{image_address}:{new_tag}"
                with open(docker_compose_file, "r", encoding="utf-8") as f:
                    compose_data = yaml.safe_load(f)
                compose_data["services"][service]["image"] = new_image_reference
                with open(docker_compose_file, "w", encoding="utf-8") as f:
                    yaml.safe_dump(compose_data, f, default_flow_style=False, sort_keys=False)
