import os
from pathlib import Path
from ..GeneralUtilities import GeneralUtilities
from ..ScriptCollectionCore import ScriptCollectionCore
from ..OCIImages.OCIImageManager import OCIImageManager


class PlantUMLContainerCall:
    """Describes how the container which renders a diagram has to be started: which mount-arguments it gets and under
    which path the folder with the diagram-sources is visible inside it. Which of the two possible shapes is used is
    decided by PlantUMLRenderer.get_container_call_configuration."""

    mount_arguments: list[str] = None
    work_folder: str = None

    def __init__(self, mount_arguments: list[str], work_folder: str):
        self.mount_arguments = mount_arguments
        self.work_folder = work_folder


class PlantUMLRenderer:
    """Renders '*.plantuml'-files into svg-files.

    The rendering always happens inside a short-lived, disposable container which runs the image the repository
    declares as 'PlantUML' in '<repository>/.ScriptCollection/OCIImages/ImageDefinition.csv'. Nothing of the rendering
    comes from the executing machine: plantuml itself, the java-runtime, Graphviz (which plantuml needs to lay out
    component- and class-diagrams) and the fonts are all part of that image, so the pinned image-tag alone determines
    what a diagram looks like.

    That is what makes the generated svg byte-identical on every machine. It is required because plantuml computes the
    whole svg-geometry from the font-metrics of the jvm: Windows- and Linux-builds of a jdk use the same FreeType-based
    rasterizer and round identically, but a macOS-build uses Apple's CoreText and rounds the vertical metrics slightly
    differently, which shifts positions in the resulting svg. Rendering with one pinned linux-image everywhere avoids
    that, so a regenerated diagram does not show up as a spurious change. When the image-tag is bumped, the committed
    diagram-svgs have to be regenerated and re-committed once."""

    # Name under which the image used for the rendering has to be declared by every repository.
    __image_name: str = "PlantUML"
    # Font all diagrams are rendered with. It is passed on the commandline (and not written into every single
    # diagram-source) so that a hand-written diagram is rendered with the same font as a generated one. Pinning it
    # keeps the diagrams independent of which font plantuml's default 'sans-serif' happens to resolve to.
    __diagram_font_name: str = "DejaVu Sans"
    # Folder inside the rendering-container to which the folder with the diagram-sources is mounted when the rendering
    # runs on a host. This is the working-directory the image itself declares.
    __container_work_folder: str = "/data"

    __sc: ScriptCollectionCore = None
    __oci_image_manager: OCIImageManager = None
    __repository_folder: str = None

    def __init__(self, sc: ScriptCollectionCore, oci_image_manager: OCIImageManager, repository_folder: str):
        self.__sc = sc
        self.__oci_image_manager = oci_image_manager
        self.__repository_folder = repository_folder

    @staticmethod
    @GeneralUtilities.check_arguments
    def get_diagram_font_name() -> str:
        """Returns the font all diagrams are rendered with. Generated diagram-sources state it as 'skinparam
        defaultFontName' themselves so their committed content already says which font they belong to."""
        return PlantUMLRenderer.__diagram_font_name

    @staticmethod
    @GeneralUtilities.check_arguments
    def get_image_name() -> str:
        """Returns the name under which the image used for the rendering has to be declared in
        '<repository>/.ScriptCollection/OCIImages/ImageDefinition.csv'."""
        return PlantUMLRenderer.__image_name

    @staticmethod
    @GeneralUtilities.check_arguments
    def get_output_filename_for_plantuml_filename(plantuml_file: str) -> str:
        """Returns the name of the svg-file plantuml writes for the given diagram-source. Plantuml derives it from the
        title given behind '@startuml' and falls back to the name of the source-file when there is none."""
        for line in GeneralUtilities.read_lines_from_file(plantuml_file):
            prefix = "@startuml "
            if line.startswith(prefix):
                title = line[len(prefix):]
                return title+".svg"
        return Path(plantuml_file).stem+".svg"

    @GeneralUtilities.check_arguments
    def render_folder(self, diagrams_files_folder: str) -> None:
        """Renders every '*.plantuml'-file which is located somewhere below the given folder into a svg-file next to it."""
        plantuml_files: list[str] = [file for file in GeneralUtilities.get_all_files_of_folder(diagrams_files_folder) if file.endswith(".plantuml")]
        if len(plantuml_files) == 0:
            return
        docker_image: str = self.__oci_image_manager.get_registry_address_for_image_with_default_tag(self.__repository_folder, PlantUMLRenderer.__image_name)
        self.__assert_docker_daemon_is_reachable()
        image_address, image_tag = ScriptCollectionCore.split_image_address_and_tag(docker_image)
        # Pull explicitly (once for all diagrams) instead of letting the first "docker run" download the image
        # implicitly, because docker writes the progress of an implicit download to std-err, which would be logged as
        # an error although nothing failed.
        self.__sc.docker_pull(image_address, image_tag)
        # Inside a build-container the forwarded docker-socket belongs to the daemon of the host, so the container
        # started here is a sibling-container and not a child. See get_container_call_configuration.
        own_container_id: str = self.__sc.get_own_container_id() if self.__sc.is_runnning_in_container() else None
        for plantuml_file in plantuml_files:
            folder: str = os.path.dirname(plantuml_file)
            container_call: PlantUMLContainerCall = PlantUMLRenderer.get_container_call_configuration(folder, own_container_id)
            self.__run_plantuml_in_container(container_call, docker_image, os.path.basename(plantuml_file))
            result_file: str = os.path.join(folder, PlantUMLRenderer.get_output_filename_for_plantuml_filename(plantuml_file))
            GeneralUtilities.assert_file_exists(result_file)
            self.__sc.format_xml_file(result_file)

    @staticmethod
    @GeneralUtilities.check_arguments
    def get_container_call_configuration(diagrams_files_folder: str, own_container_id: str) -> PlantUMLContainerCall:
        """Returns how the rendering-container has to be started for the given folder. There are two cases:

        - This process runs directly on a host: the docker-daemon resolves a bind-mount on the same filesystem this
          process sees, so the folder with the diagram-sources is bind-mounted into the container. 'own_container_id'
          is None in this case.
        - This process itself runs in a container whose docker-socket is forwarded to the daemon of the host (for
          example the build-container): a bind-mount would then be resolved by that daemon, where the paths of this
          process do not exist. Docker silently creates an empty directory for a missing bind-mount-source, so the
          rendering would run in an empty working-directory and would not find any diagram. The volumes of this
          container are therefore shared with the sibling-container instead, which makes the repository visible there
          under exactly the path this process uses.

        The same rendering-command is used in both cases; only the mount-arguments and the working-directory differ."""
        if own_container_id is None:
            return PlantUMLContainerCall(["-v", f"{diagrams_files_folder}:{PlantUMLRenderer.__container_work_folder}"], PlantUMLRenderer.__container_work_folder)
        return PlantUMLContainerCall(["--volumes-from", own_container_id], PlantUMLRenderer.__to_container_path(diagrams_files_folder))

    @staticmethod
    @GeneralUtilities.check_arguments
    def get_user_arguments() -> list[str]:
        """Returns the arguments which make the rendering-container write the generated svg as the user this process
        runs as. The image runs as an own unprivileged user by default, which can not write into a folder of the
        machine when the ownership does not match - the generated svg has to belong to the user who runs the build.
        On windows there is no such ownership, so nothing is passed there."""
        if GeneralUtilities.current_system_is_windows():
            return []
        # "getuid"/"getgid" do not exist on windows, which is why they are only reached below that check; pylint
        # analyses this file on windows as well and does not see that.
        return ["--user", f"{os.getuid()}:{os.getgid()}"]  # pylint: disable=no-member

    @GeneralUtilities.check_arguments
    def __run_plantuml_in_container(self, container_call: PlantUMLContainerCall, docker_image: str, plantuml_filename: str) -> None:
        # The image declares "java -jar <plantuml.jar>" as its entrypoint, so only the arguments of plantuml itself are
        # passed here.
        plantuml_arguments: list[str] = ["-tsvg", f"-SdefaultFontName={PlantUMLRenderer.__diagram_font_name}", plantuml_filename]
        docker_arguments: list[str] = ["run", "--rm"]+container_call.mount_arguments+PlantUMLRenderer.get_user_arguments()+["-w", container_call.work_folder, docker_image]+plantuml_arguments
        self.__sc.run_program_argsasarray("docker", docker_arguments)

    @GeneralUtilities.check_arguments
    def __assert_docker_daemon_is_reachable(self) -> None:
        # The rendering runs via "docker run", so an unreachable daemon makes it fail with an error which looks like a
        # rendering-problem. "docker version --format {{.Server.Version}}" queries the daemon itself and exits
        # non-zero exactly when it can not be reached, which distinguishes the infrastructure-problem from a real
        # rendering-error.
        daemon_check = self.__sc.run_program_argsasarray("docker", ["version", "--format", "{{.Server.Version}}"], throw_exception_if_exitcode_is_not_zero=False, print_live_output=False)
        if daemon_check[0] != 0:
            raise ValueError(f"The plantuml-diagrams can not be rendered because the docker-daemon is not reachable (exit-code {daemon_check[0]}: {daemon_check[2].strip()}). The rendering runs plantuml via 'docker run', which requires a running docker-daemon (inside a build-container its socket must be forwarded to the daemon of the host). This is an infrastructure-problem, not a problem of a diagram.")

    @staticmethod
    @GeneralUtilities.check_arguments
    def __to_container_path(path: str) -> str:
        # A path which is used inside the container has to be written in the linux-notation. This only has an effect
        # when this function is called with a path of a windows-host, which happens in the tests.
        return path.replace("\\", "/").rstrip("/")
