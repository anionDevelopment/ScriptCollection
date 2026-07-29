from ..GeneralUtilities import GeneralUtilities
from .TFCPS_CodeUnit_BuildCodeUnit import TFCPS_CodeUnit_BuildCodeUnit


class TFCPS_BuildCodeUnitsHook:
    """Allows to run additional actions at defined moments of the build of the codeunits of a repository.

    This is an internal extension-point of ScriptCollection: it exists so a workflow which has to do something between the regular
    build-steps (for example the dependency-update) can use the regular build-process instead of reimplementing a reduced variant of it.
    Reimplementing it is what makes such a workflow miss preparation-steps like the required environment-variables, the custom
    pre-codeunit-build-script or the package-sources which are needed to resolve the dependencies of a codeunit.

    The extension-point for the user of ScriptCollection are the custom scripts in the configuration-folder (see
    TFCPS_Tools_General.get_custom_script_file), not this class.

    All operations have an empty default-implementation, so an implementation only has to define the moments it is interested in."""

    @GeneralUtilities.check_arguments
    def run_after_preparation(self, repository: str) -> None:
        """Is called after the build was prepared (environment-variables, custom pre-codeunit-build-script and prepare-script of the
        repository) and before the first codeunit is built."""

    @GeneralUtilities.check_arguments
    def run_after_codeunit_was_built(self, codeunit_build: TFCPS_CodeUnit_BuildCodeUnit) -> None:
        """Is called after a codeunit was built. The codeunit-build is passed so an implementation can build the codeunit again, for
        example when it changed the codeunit and wants to verify that it is still buildable."""
