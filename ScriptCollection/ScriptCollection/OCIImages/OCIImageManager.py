import os
from unittest import result
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

    def get_image_handler(self,image_name:str)->AbstractImageHandler:
        for image_handler in self.image_handler: 
            if image_handler.can_handle(image_name):
                return image_handler
        raise ValueError(f"No image-handler available for image \"{image_name}\".")

    def get_repository_image_definition_file(self,repository:str)->str:
        self.__sc.assert_is_git_repository(repository)
        sc_folder_in_repo=os.path.join(repository,".ScriptCollection","OCIImages")
        GeneralUtilities.ensure_directory_exists(sc_folder_in_repo)
        image_definition_file=os.path.join(sc_folder_in_repo,"ImageDefinition.csv")
        if not os.path.isfile(image_definition_file):
            GeneralUtilities.ensure_file_exists(image_definition_file)
            GeneralUtilities.write_text_to_file(image_definition_file,"ImageName;UpstreamRegistryAddress;DefaultTag")
        return image_definition_file
    
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

    def custom_registry_is_defined(self,image_name:str)->bool:
        global_docker_image_registries_file=self.get_global_docker_image_registries_file()
        for line in  GeneralUtilities.read_nonempty_lines_from_file(global_docker_image_registries_file)[1:]:
            splitted_line=line.split(";")
            if image_name==splitted_line[0]:
                GeneralUtilities.assert_condition(GeneralUtilities.string_has_content(splitted_line[1]),f"No registry defined for image {image_name}.")
                return True
        return False

    def get_tag_for_image(self,repository:str,image_name:str,strict_mode:bool)->str:
        repository_image_definition_file=self.get_repository_image_definition_file(repository)
        for line in [f.split(";") for f in GeneralUtilities.read_nonempty_lines_from_file(repository_image_definition_file)[1:]]:
            if image_name==line[0]:
                return line[2]
        raise ValueError(f"No tag defined for image \"{image_name}\".")

    def get_registry_address_for_image(self,repository:str,image_name:str)->str:
        """if image_name==Debian this function returns something like "myregistry.example.com/debian", always without tag."""
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

    def get_registry_address_for_image_with_default_tag(self,repository:str,image_name:str,strict_mode:bool=True)->str:
        return f"{self.get_registry_address_for_image(repository,image_name)}:{self.get_tag_for_image(repository,image_name,strict_mode)}"

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
                newest_versions:set[Version]=[default_tag]
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

    def get_available_versions_of_image_which_are_newer(self,image_name:str,registry_address:str,current_version:Version,echolon: VersionEcholon)->Version:
        image_handler=self.get_image_handler(image_name)
        result= None #TODO calculate result using get_available_tags_of_image.
        #TODO if echolon is not none, then use echolon instead of the default echolon of the image-handler.
        #TODO return the versions sorted.
        #TODO if result is empty: return None
        return result
    
    def get_available_tags_of_image(self,image_name:str,registry_address:str)->list[str]:
        """registry_address must have one of theese formats: "myregistry.example.com/debian" or "docker.io/debian" or "docker.io/myuser/debian".
        returns something like ["13.2-slim", "13.2", "13.3-slim", "13.3"]."""
        return self.get_image_handler(image_name).get_available_tags_of_image(image_name,registry_address)

    def tag_to_version(self,image_name:str,tag:str)->Version:
        """registry_address must have one of theese formats: "myregistry.example.com/debian" or "docker.io/debian" or "docker.io/myuser/debian"."""
        return self.get_image_handler(image_name).tag_to_version(image_name, tag)

    def version_to_tag(self,image_name:str,version:Version)->str:
        """registry_address must have one of theese formats: "myregistry.example.com/debian" or "docker.io/debian" or "docker.io/myuser/debian".
        returns something like "13.3-slim".
        If there are multiple tags available for a certain version then the image-handler decides which one will be returned."""
        return self.get_image_handler(image_name).version_to_tag(image_name,version)

    def get_images_used_in_docker_compose_file(self,docker_compose_file:str)->dict[str,tuple[str,str,str]]:#returns dict[service_name,[image_name,image_address,current_tag]]
        GeneralUtilities.assert_file_exists(docker_compose_file)
        return {}#TODO implement function

    def update_image_in_docker_compose_file(self,docker_compose_file:str)->None:
        for service,service_information in self.get_images_used_in_docker_compose_file(docker_compose_file).items():
            image_name=service_information[0]
            image_address=service_information[1]
            current_tag=service_information[2]
            image_handler=self.get_image_handler(image_name)
            new_versions_for_address=self.get_available_versions_of_image_which_are_newer(image_name,image_address,self.tag_to_version(image_name,current_tag),image_handler.get_default_echolon_for_update())
            new_tag=self.version_to_tag(image_name,new_versions_for_address)
            #TODO update tag for service in docker-compose-file to new_tag
        
