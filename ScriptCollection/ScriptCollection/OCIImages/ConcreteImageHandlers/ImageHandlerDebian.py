from ...GeneralUtilities import VersionEcholon
from ..AbstractTagPatternImageHandler import AbstractTagPatternImageHandler

class ImageHandlerDebian(AbstractTagPatternImageHandler):
    """Handles the tags of debian without variant, for example "13.4"."""

    def _protected_accepts_tag_parts(self,image_name:str,prefix:str,suffix:str)->bool:
        return image_name.lower()=="debian" and prefix=="" and suffix==""

    def get_default_echolon_for_update(self,image_name:str)->VersionEcholon:
        return VersionEcholon.LatestPatch
