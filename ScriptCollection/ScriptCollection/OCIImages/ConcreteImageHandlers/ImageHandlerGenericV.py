from ...GeneralUtilities import VersionEcholon
from ..AbstractTagPatternImageHandler import AbstractTagPatternImageHandler

class ImageHandlerGenericV(AbstractTagPatternImageHandler):
    """Handles tags which consist of the prefix "v", a numeric version and an optional suffix, for example "v1.41.2" or "v1.62.1-noble"."""

    def _protected_accepts_tag_parts(self,image_name:str,prefix:str,suffix:str)->bool:
        return prefix=="v"

    def get_default_echolon_for_update(self,image_name:str)->VersionEcholon:
        return VersionEcholon.LatestVersion
