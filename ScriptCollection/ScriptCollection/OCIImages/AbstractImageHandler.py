from abc import ABC, abstractmethod
from packaging.version import Version
from ..GeneralUtilities import GeneralUtilities, VersionEcholon

class AbstractImageHandler(ABC):
    
    @abstractmethod
    def can_handle(self,image_name:str)->bool:
        raise NotImplementedError()#because it is abstract
    
    def _protected_get_credentials_for_registry(self,registry_address:str,username_str:str)->tuple[str,str]:
        """return (username, password) for basic auth.
        Data will be taken from "~/.ScriptCollection/GlobalCache/RegistryCredentials.csv" if available.
        If no credentials are available then None will be returned for the missing values."""
        raise NotImplementedError()
    
    def _protected_get_tags_from_images_from_custom_registry(self,registry_address:str)->list[str]:
        raise NotImplementedError()
    
    def _protected_get_tags_from_images_from_docker_hub(self,registry_address:str,tag_filter:str)->list[str]:
        GeneralUtilities.assert_condition(registry_address.startswith("docker.io/",f"Image \"{registry_address}\" is not from docker-hub."))
        raise NotImplementedError()
    
    @abstractmethod
    def get_available_tags_of_image(self,image_name:str,registry_address:str)->list[str]:
        raise NotImplementedError()#because it is abstract

    @abstractmethod
    def tag_to_version(self,image_name:str,tag:str)->Version:
        raise NotImplementedError()#because it is abstract

    @abstractmethod
    def version_to_tag(self,image_name:str,version:Version)->str:
        raise NotImplementedError()#because it is abstract

    @abstractmethod
    def get_default_echolon_for_update(self,image_name:str)->VersionEcholon:
        raise NotImplementedError()#because it is abstract
