from packaging.version import Version
from ...GeneralUtilities import VersionEcholon
from ..AbstractImageHandler import AbstractImageHandler

class ImageHandlerGitlabCE(AbstractImageHandler):
    """Recognizes the tags of GitLab ce (for example "18.5.1-ce.0"), so that they are not handled by a generic handler: an update of
    GitLab must respect the required upgrade-stops, which is not implemented yet."""

    def can_handle(self,image_name:str,tag:str)->bool:
        return "gitlab" in image_name.lower() and tag.endswith("-ce.0")

    def tag_has_same_format(self,image_name:str,tag:str,reference_tag:str)->bool:
        raise NotImplementedError(f"Updating the tag of image \"{image_name}\" (GitLab ce) is not implemented yet.")

    def tag_to_version(self,image_name:str,tag:str)->Version:
        raise NotImplementedError(f"Updating the tag of image \"{image_name}\" (GitLab ce) is not implemented yet.")

    def get_default_echolon_for_update(self,image_name:str)->VersionEcholon:
        return VersionEcholon.CustomAlgorithm
