from ...GeneralUtilities import VersionEcholon
from ..AbstractTagPatternImageHandler import AbstractTagPatternImageHandler

class ImageHandlerGeneric(AbstractTagPatternImageHandler):
    """Handles tags which consist of a numeric version and an optional suffix, for example "12.2.2", "1.2026.8" or "7.2-26.04_edge"."""

    def _protected_accepts_tag_parts(self,image_name:str,prefix:str,suffix:str)->bool:
        return prefix==""

    def get_default_echolon_for_update(self,image_name:str)->VersionEcholon:
        return VersionEcholon.LatestVersion
