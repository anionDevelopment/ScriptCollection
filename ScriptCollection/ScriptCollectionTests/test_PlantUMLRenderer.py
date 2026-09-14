import os
import tempfile
import unittest
from ..ScriptCollection.GeneralUtilities import GeneralUtilities
from ..ScriptCollection.TFCPS.PlantUMLRenderer import PlantUMLRenderer, PlantUMLContainerCall


class PlantUMLRendererTests(unittest.TestCase):

    def test_get_output_filename_uses_the_title_behind_startuml(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_folder:
            # arrange
            plantuml_file = os.path.join(temporary_folder, "Source.plantuml")
            GeneralUtilities.write_lines_to_file(plantuml_file, ["@startuml CodeUnits-Overview", "[A]", "@enduml"])

            # act
            actual_result = PlantUMLRenderer.get_output_filename_for_plantuml_filename(plantuml_file)

            # assert
            self.assertEqual("CodeUnits-Overview.svg", actual_result)

    def test_get_output_filename_falls_back_to_the_filename_when_no_title_is_given(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_folder:
            # arrange
            plantuml_file = os.path.join(temporary_folder, "Source.plantuml")
            GeneralUtilities.write_lines_to_file(plantuml_file, ["@startuml", "[A]", "@enduml"])

            # act
            actual_result = PlantUMLRenderer.get_output_filename_for_plantuml_filename(plantuml_file)

            # assert
            self.assertEqual("Source.svg", actual_result)

    def test_container_call_on_a_host_bindmounts_the_folder_with_the_diagrams(self) -> None:
        # act
        actual_result: PlantUMLContainerCall = PlantUMLRenderer.get_container_call_configuration("/repository/Other/Reference", None)

        # assert
        self.assertEqual(["-v", "/repository/Other/Reference:/data"], actual_result.mount_arguments)
        self.assertEqual("/data", actual_result.work_folder)

    def test_container_call_in_a_container_shares_the_own_volumes_and_keeps_the_path(self) -> None:
        # arrange
        # This is the path as it exists inside the build-container: the repository is mounted there, so a
        # sibling-container which shares these volumes sees it under exactly this path. A bind-mount of it would be
        # resolved by the daemon of the host, where it does not exist.
        diagrams_files_folder = "/Workspace/Project/Repository/Other/Reference"

        # act
        actual_result: PlantUMLContainerCall = PlantUMLRenderer.get_container_call_configuration(diagrams_files_folder, "0123456789abcdef")

        # assert
        self.assertEqual(["--volumes-from", "0123456789abcdef"], actual_result.mount_arguments)
        self.assertEqual(diagrams_files_folder, actual_result.work_folder)

    def test_container_call_in_a_container_writes_a_windowspath_in_the_linuxnotation(self) -> None:
        # act
        actual_result: PlantUMLContainerCall = PlantUMLRenderer.get_container_call_configuration(r"\Workspace\Project\Repository", "0123456789abcdef")

        # assert
        self.assertEqual("/Workspace/Project/Repository", actual_result.work_folder)

    def test_the_rendering_container_runs_as_the_own_user_except_on_windows(self) -> None:
        # act
        actual_result = PlantUMLRenderer.get_user_arguments()

        # assert
        # The image runs as an own unprivileged user, which can not write the generated svg into a folder of the
        # machine when the ownership does not match. On windows there is no such ownership.
        if GeneralUtilities.current_system_is_windows():
            self.assertEqual([], actual_result)
        else:
            self.assertEqual("--user", actual_result[0])
            self.assertEqual(f"{os.getuid()}:{os.getgid()}", actual_result[1])  # pylint: disable=no-member

    def test_the_image_is_declared_under_a_name_of_its_own(self) -> None:
        # act
        actual_result = PlantUMLRenderer.get_image_name()

        # assert
        # Everything the rendering needs (plantuml, java, Graphviz and the fonts) is part of this image, so the whole
        # result of a rendering is pinned by the tag which the repository declares for this name.
        self.assertEqual("PlantUML", actual_result)
