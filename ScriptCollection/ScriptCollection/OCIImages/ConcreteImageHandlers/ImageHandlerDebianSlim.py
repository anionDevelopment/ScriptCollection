from ...GeneralUtilities import VersionEcholon
from ..AbstractTagPatternImageHandler import AbstractTagPatternImageHandler

class ImageHandlerDebianSlim(AbstractTagPatternImageHandler):
    """Handles the tags of the slim-variant of debian, for example "13.4-slim"."""

    def _protected_accepts_tag_parts(self,image_name:str,prefix:str,suffix:str)->bool:
        return image_name.lower()=="debian" and prefix=="" and suffix=="-slim"

    def get_default_echolon_for_update(self,image_name:str)->VersionEcholon:
        return VersionEcholon.LatestPatch
