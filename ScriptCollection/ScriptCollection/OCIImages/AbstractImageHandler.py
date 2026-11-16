from abc import ABC, abstractmethod
from packaging.version import Version
from ..GeneralUtilities import VersionEcholon

class AbstractImageHandler(ABC):
    """An image-handler knows the format of the tags of certain images: which tags of a registry are candidates for an update of a
    given tag and which version a tag represents. The tags themselves are read from the registry by the OCIRegistryClient."""

    @abstractmethod
    def can_handle(self,image_name:str,tag:str)->bool:
        """Returns whether this handler knows the format of the given tag of the given image."""
        raise NotImplementedError()#because it is abstract

    @abstractmethod
    def tag_has_same_format(self,image_name:str,tag:str,reference_tag:str)->bool:
        """Returns whether the given tag has the same format as the reference-tag, which means it is a candidate for an update of the
        reference-tag. Example: for the reference-tag "13.4-slim" the tag "13.5-slim" has the same format but "13.5" and "13-slim" do not."""
        raise NotImplementedError()#because it is abstract

    @abstractmethod
    def tag_to_version(self,image_name:str,tag:str)->Version:
        raise NotImplementedError()#because it is abstract

    @abstractmethod
    def get_default_echolon_for_update(self,image_name:str)->VersionEcholon:
        raise NotImplementedError()#because it is abstract

    def get_latest_tag_custom(self,image_name:str,current_tag:str,candidate_tags:list[str])->str:
        """Determines the tag the image should be updated to using an image-specific custom algorithm.
        candidate_tags contains the current tag and all available tags which have the same format as the current tag.
        This is used when the echolon VersionEcholon.CustomAlgorithm is selected.
        Image-handlers which want to support a custom algorithm must override this method."""
        raise ValueError(f"Image-handler \"{type(self).__name__}\" does not define a custom algorithm for determining the latest version of image \"{image_name}\".")
