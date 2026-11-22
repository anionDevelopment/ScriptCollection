import re
from abc import abstractmethod
from packaging.version import Version
from ..GeneralUtilities import GeneralUtilities
from .AbstractImageHandler import AbstractImageHandler

class AbstractTagPatternImageHandler(AbstractImageHandler):
    """Base for image-handlers whose tags consist of an optional prefix, a numeric version and an optional suffix, for example
    "13.4-slim" (prefix "", version "13.4", suffix "-slim") or "v1.62.1-noble" (prefix "v", version "1.62.1", suffix "-noble").
    Two tags have the same format if they have the same prefix, the same suffix and the same amount of version-parts. The suffix
    must start with "-", "_" or "+" so that it can be separated from the version unambiguously."""

    __tag_pattern=re.compile(r"^(?P<prefix>v?)(?P<version>\d+(?:\.\d+)*)(?P<suffix>(?:[-_+].*)?)$")

    @abstractmethod
    def _protected_accepts_tag_parts(self,image_name:str,prefix:str,suffix:str)->bool:
        """Returns whether this handler is responsible for tags with the given prefix and suffix of the given image."""
        raise NotImplementedError()#because it is abstract

    def can_handle(self,image_name:str,tag:str)->bool:
        tag_parts=self.__split_tag(tag)
        if tag_parts is None:
            return False
        return self._protected_accepts_tag_parts(image_name,tag_parts[0],tag_parts[2])

    def tag_has_same_format(self,image_name:str,tag:str,reference_tag:str)->bool:
        tag_parts=self.__split_tag(tag)
        reference_tag_parts=self.__split_tag(reference_tag)
        if tag_parts is None or reference_tag_parts is None:
            return False
        same_prefix=tag_parts[0]==reference_tag_parts[0]
        same_amount_of_version_parts=len(tag_parts[1].split("."))==len(reference_tag_parts[1].split("."))
        same_suffix=tag_parts[2]==reference_tag_parts[2]
        return same_prefix and same_amount_of_version_parts and same_suffix

    def tag_to_version(self,image_name:str,tag:str)->Version:
        tag_parts=self.__split_tag(tag)
        GeneralUtilities.assert_condition(tag_parts is not None,f"Tag \"{tag}\" of image \"{image_name}\" does not have the format <prefix><version><suffix>.")
        return Version(tag_parts[1])

    def __split_tag(self,tag:str)->tuple[str,str,str]:
        """Returns (prefix, version, suffix) of the tag or None if the tag does not have the format <prefix><version><suffix>."""
        match=AbstractTagPatternImageHandler.__tag_pattern.match(tag)
        if match is None:
            return None
        return (match.group("prefix"),match.group("version"),match.group("suffix"))
