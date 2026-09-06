import os
import platform
import posixpath
import shutil
import re
import socket
import uuid
import xml.etree.ElementTree as ET
import zipfile

import yaml

from ...ArbTranslationsOrganizer import ArbTranslationsOrganizer
from ...GeneralUtilities import GeneralUtilities
from ...SCLog import  LogLevel
from ...ScriptCollectionCore import ScriptCollectionCore
from ..TFCPS_CodeUnitSpecific_Base import TFCPS_CodeUnitSpecific_Base,TFCPS_CodeUnitSpecific_Base_CLI
from ..TFCPS_RemoteBuild import TFCPS_RemoteBuild, RunnerOperatingSystem

class TFCPS_CodeUnitSpecific_Flutter_Functions(TFCPS_CodeUnitSpecific_Base):

    # The names under which a package-registry (for example pub.dev) expects the readme, the license and the
    # changelog inside a package.
    __name_of_readme_in_package: str = "README.md"
    __name_of_license_in_package: str = "LICENSE"
    __name_of_changelog_in_package: str = "CHANGELOG.md"

    # The name a changelog-file of a repository has, see "Other/Resources/Changelog".
    __changelog_file_name_pattern = re.compile(r"^v(?P<version>\d+\.\d+\.\d+)\.md$")

    # The linebreak which is used inside a generated file of the package. It is not the linebreak of the
    # operating-system, because the content of such a file has to look the same regardless of where it was built.
    __linebreak: str = "\n"

    # The artifacts which contain a copy of the sourcecode and therefore a copy of the package. Which of them
    # really exist depends on the targets which were built (see build()).
    __artifacts_which_contain_the_sourcecode: list[str] = ["SourceCode", "BuildResult_SourceCode"]

    # The address github hosts a repository under and the address it delivers the raw files of a repository under.
    __github_address_prefix: str = "https://github.com/"
    __github_raw_address_prefix: str = "https://raw.githubusercontent.com/"

    # The schema the generated bill-of-materials is written in.
    __cyclonedx_namespace: str = "http://cyclonedx.org/schema/bom/1.6"

    def __init__(self,current_file:str,verbosity:LogLevel,targetenvironmenttype:str,use_cache:bool,is_pre_merge:bool):
        super().__init__(current_file, verbosity,targetenvironmenttype,use_cache,is_pre_merge)


    @GeneralUtilities.check_arguments
    def build(self,package_name:str,targets:list[str],add_readme_of_codeunit_to_package:bool=False,add_license_of_repository_to_package:bool=False,add_changelog_of_repository_to_package:bool=False,branch_of_published_state:str="main") -> None:
        """Builds the codeunit for the given targets.

        'add_readme_of_codeunit_to_package', 'add_license_of_repository_to_package' and
        'add_changelog_of_repository_to_package' put the readme of the codeunit ("<codeunit>/ReadMe.md"), the
        license of the repository ("License.txt") respectively the changelog of the repository
        ("Other/Resources/Changelog") into the copies of the package which the sourcecode-artifacts contain. Set
        them for a codeunit whose package is published to a package-registry like pub.dev, which shows the readme
        and the changelog of a package on the page of the package and expects the license to be part of the
        package.
        'branch_of_published_state' is the branch whose state the published package refers to. It is used to make
        the links of that readme absolute."""
        codeunit_folder = self.get_codeunit_folder()
        codeunit_name = os.path.basename(codeunit_folder)
        src_folder: str = None
        if package_name is None:
            src_folder = codeunit_folder
        else:
            src_folder = GeneralUtilities.resolve_relative_path(package_name, codeunit_folder) # TODO replace packagename
        artifacts_folder = os.path.join(codeunit_folder, "Other", "Artifacts")
        
        target_names: dict[str, str] = {
            "web": "WebApplication",
            "windows": "Windows",
            "linux": "Linux",
            "macos": "MacOS",
            "ios": "IOS",
            "android": "Android",
        }
        for target in targets:
            self._protected_sc.log.log(f"Build flutter-codeunit {codeunit_name} for target {target_names[target]}...")
            if target == "web":
                self._protected_sc.run_with_epew("flutter", "build web", src_folder)
                web_relase_folder = os.path.join(src_folder, "build/web")
                web_folder = os.path.join(artifacts_folder, "BuildResult_WebApplication")
                GeneralUtilities.ensure_directory_does_not_exist(web_folder)
                GeneralUtilities.ensure_directory_exists(web_folder)
                GeneralUtilities.copy_content_of_folder(web_relase_folder, web_folder)
            elif target == "windows":
                # Windows-builds prefer a Windows-task-runner - even when building on a Windows-client - so that all builds
                # are produced uniformly in the same defined environment. See the remote-build-article in the reference. If
                # no runner is configured, fall back to building locally (only possible when already running on Windows)
                # instead of failing, so a development machine without a configured runner is not blocked.
                if platform.system() == "Windows" and not TFCPS_RemoteBuild(self._protected_sc).has_any_runner_configured():
                    self._protected_sc.log.log("No remote-build-runner is configured; building the windows-target locally "
                                                "instead. This build is not guaranteed to be produced in the same uniform "
                                                "environment as a runner-built one.", LogLevel.Warning)
                    self._protected_sc.run_with_epew("flutter", "build windows", src_folder)
                else:
                    self.run_program_on_remote_runner(RunnerOperatingSystem.Windows, "flutter", ["build", "windows"], src_folder)
                windows_release_folder = os.path.join(src_folder, "build/windows/x64/runner/Release")
                windows_folder = os.path.join(artifacts_folder, "BuildResult_Windows")
                GeneralUtilities.ensure_directory_does_not_exist(windows_folder)
                GeneralUtilities.ensure_directory_exists(windows_folder)
                GeneralUtilities.copy_content_of_folder(windows_release_folder, windows_folder)
            elif target == "linux":
                # Linux-desktop-builds run in a sibling-container of the "SCBuilder"-image (defined in
                # ".ScriptCollection/OCIImages/ImageDefinition.csv" of the repository, like every other image the
                # build uses), which has the Linux-desktop-toolchain (clang/cmake/ninja/libgtk-3-dev) this target
                # needs. Unlike windows/ios/appbundle this is not a permanently-running remote-task-runner: SCBuilder
                # is started fresh, just for this one build-step, and removed again afterwards.
                self.__build_linux_in_container(codeunit_folder, src_folder)
                linux_release_folder = os.path.join(src_folder, "build/linux/x64/release/bundle")
                linux_folder = os.path.join(artifacts_folder, "BuildResult_Linux")
                GeneralUtilities.ensure_directory_does_not_exist(linux_folder)
                GeneralUtilities.ensure_directory_exists(linux_folder)
                GeneralUtilities.copy_content_of_folder(linux_release_folder, linux_folder)
            elif target == "macos":
                # macOS-desktop-builds must run on macOS and therefore always run on the macOS-task-runner (uniform
                # builds), analogous to how ios-builds always run on the iOS-task-runner. See SCTaskRunnerMacOS and
                # the remote-build-article in the reference.
                self.run_program_on_remote_runner(RunnerOperatingSystem.MacOS, "flutter", ["build", "macos"], src_folder)
                macos_release_folder = os.path.join(src_folder, "build/macos/Build/Products/Release")
                macos_folder = os.path.join(artifacts_folder, "BuildResult_MacOS")
                GeneralUtilities.ensure_directory_does_not_exist(macos_folder)
                GeneralUtilities.ensure_directory_exists(macos_folder)
                GeneralUtilities.copy_content_of_folder(macos_release_folder, macos_folder)
            elif target == "ios":
                # iOS-builds must run on macOS and therefore always run on the dedicated iOS-task-runner (uniform
                # builds). See SCTaskRunnerIOS and the remote-build-article in the reference.
                self.run_program_on_remote_runner(RunnerOperatingSystem.IOS, "flutter", ["build", "ios"], src_folder)
                ios_release_folder = os.path.join(src_folder, "build/ios/iphoneos")
                ios_folder = os.path.join(artifacts_folder, "BuildResult_IOS")
                GeneralUtilities.ensure_directory_does_not_exist(ios_folder)
                GeneralUtilities.ensure_directory_exists(ios_folder)
                GeneralUtilities.copy_content_of_folder(ios_release_folder, ios_folder)
            elif target == "android":
                # Android-app-builds always run on an Android-task-runner (see SCTaskRunnerAndroid and the
                # remote-build-article in the reference), analogous to how ios-builds always run on a macOS-task-runner:
                # the Android-SDK/NDK-toolchain no longer lives in SCBuilder itself, it moved into SCTaskRunnerAndroid.
                self.run_program_on_remote_runner(RunnerOperatingSystem.Android, "flutter", ["build", "appbundle"], src_folder)
                enabled=False
                if enabled:#TODO move to external because this is not platform indepent
                    aab_folder = os.path.join(artifacts_folder, "BuildResult_AAB")
                    GeneralUtilities.ensure_directory_does_not_exist(aab_folder)
                    GeneralUtilities.ensure_directory_exists(aab_folder)
                    aab_relase_folder = os.path.join(src_folder, "build/app/outputs/bundle/release")
                    aab_file_original = self._protected_sc.find_file_by_extension(aab_relase_folder, "aab")
                    aab_file = os.path.join(aab_folder, f"{codeunit_name}.aab")
                    shutil.copyfile(aab_file_original, aab_file)
                    
                    bundletool = self.tfcps_Tools_General.ensure_androidappbundletool_is_available(None,self.use_cache())
                    apk_folder = os.path.join(artifacts_folder, "BuildResult_APK")
                    GeneralUtilities.ensure_directory_does_not_exist(apk_folder)
                    GeneralUtilities.ensure_directory_exists(apk_folder)
                    apks_file = f"{apk_folder}/{codeunit_name}.apks"
                    self._protected_sc.run_program("java", f"-jar {bundletool} build-apks --bundle={aab_file} --output={apks_file} --mode=universal", aab_relase_folder)
                    with zipfile.ZipFile(apks_file, "r") as zip_ref:
                        zip_ref.extract("universal.apk", apk_folder)
                    GeneralUtilities.ensure_file_does_not_exist(apks_file)
                    os.rename(f"{apk_folder}/universal.apk", f"{apk_folder}/{codeunit_name}.apk")
            else:
                raise ValueError(f"Not supported target: {target}")
        self.__generate_bom_for_flutter_package(package_name)
        self.copy_source_files_to_output_directory()
        if len(targets) == 0:
            # A pure Dart/Flutter library codeunit (no platform target) has no compiled artifact of its own, but
            # TFCPS_CodeUnit_BuildCodeUnit.build_codeunit() requires a 'BuildResult_.+'-matching artifact for every
            # codeunit. Publish a copy of the SourceCode-artifact under a BuildResult_-name to satisfy that generic
            # check instead of weakening it for every codeunit type. The SourceCode-artifact folder itself keeps its
            # name unchanged because the DependentCodeUnits-convention (see the reference) already relies on it.
            source_code_folder = os.path.join(artifacts_folder, "SourceCode")
            build_result_source_code_folder = os.path.join(artifacts_folder, "BuildResult_SourceCode")
            GeneralUtilities.ensure_directory_does_not_exist(build_result_source_code_folder)
            GeneralUtilities.ensure_directory_exists(build_result_source_code_folder)
            GeneralUtilities.copy_content_of_folder(source_code_folder, build_result_source_code_folder)
        if add_readme_of_codeunit_to_package or add_license_of_repository_to_package or add_changelog_of_repository_to_package:
            self.__add_package_registry_files_to_artifacts(artifacts_folder, package_name, add_readme_of_codeunit_to_package, add_license_of_repository_to_package, add_changelog_of_repository_to_package, branch_of_published_state)

    @GeneralUtilities.check_arguments
    def __generate_bom_for_flutter_package(self, package_name: str) -> None:
        """Generates the bill-of-materials of the codeunit from the "pubspec.lock" of its package.

        The lockfile is the only place which states the exact version of every package the codeunit really uses,
        direct as well as transitive ones, which is exactly what a bill-of-materials has to contain. It is
        generated from that file instead of by an external tool, because pub has no equivalent of "cyclonedx-npm"
        or "cyclonedx-gomod" which could be demanded from every machine which builds a flutter-codeunit."""
        package_folder: str = self.get_codeunit_folder() if package_name is None else GeneralUtilities.resolve_relative_path(package_name, self.get_codeunit_folder())
        lockfile: str = os.path.join(package_folder, "pubspec.lock")
        if not os.path.isfile(lockfile):
            # A library does not commit its lockfile (see https://dart.dev/guides/libraries/private-files), so on
            # a fresh clone the file only exists after the dependencies were resolved once.
            self._protected_sc.run_with_epew("flutter", "pub get", package_folder)
        GeneralUtilities.assert_file_exists(lockfile, f"The lockfile \"{lockfile}\" does not exist, so the bill-of-materials of the codeunit can not be generated.")
        codeunit_version: str = self.tfcps_Tools_General.get_version_of_codeunit(self.get_codeunit_file())
        bom_folder: str = os.path.join(self.get_artifacts_folder(), "BOM")
        GeneralUtilities.ensure_directory_exists(bom_folder)
        bom_file: str = os.path.join(bom_folder, f"{self.get_codeunit_name()}.{codeunit_version}.bom.xml")
        GeneralUtilities.write_text_to_file(bom_file, TFCPS_CodeUnitSpecific_Flutter_Functions.__get_bom_content(lockfile, self.get_codeunit_name(), codeunit_version))
        self._protected_sc.format_xml_file(bom_file)

    @staticmethod
    @GeneralUtilities.check_arguments
    def __get_bom_content(lockfile: str, codeunit_name: str, codeunit_version: str) -> str:
        """Returns the bill-of-materials of the packages of [lockfile] as a CycloneDX-document."""
        lockfile_content = yaml.safe_load(GeneralUtilities.read_text_from_file(lockfile))
        # A lockfile which has no packages at all has an empty "packages"-block, which yaml reads as None and not
        # as an empty dictionary, so both cases have to be handled here.
        packages: dict = (lockfile_content.get("packages") if lockfile_content is not None else None) or dict()
        bom = ET.Element("bom", {"xmlns": TFCPS_CodeUnitSpecific_Flutter_Functions.__cyclonedx_namespace, "version": "1", "serialNumber": f"urn:uuid:{uuid.uuid4()}"})
        metadata = ET.SubElement(bom, "metadata")
        ET.SubElement(metadata, "timestamp").text = GeneralUtilities.datetime_to_string(GeneralUtilities.get_now())
        tool = ET.SubElement(ET.SubElement(ET.SubElement(metadata, "tools"), "components"), "component", {"type": "application"})
        ET.SubElement(tool, "name").text = "ScriptCollection"
        ET.SubElement(tool, "version").text = ScriptCollectionCore.get_scriptcollection_version()
        subject = ET.SubElement(metadata, "component", {"type": "library", "bom-ref": f"pkg:pub/{codeunit_name}@{codeunit_version}"})
        ET.SubElement(subject, "name").text = codeunit_name
        ET.SubElement(subject, "version").text = codeunit_version
        components = ET.SubElement(bom, "components")
        # The packages are sorted by their name, so that two builds of the same state result in the same document
        # instead of in one whose entries are ordered differently for no reason.
        for package_name in sorted(packages.keys()):
            TFCPS_CodeUnitSpecific_Flutter_Functions.__add_bom_component(components, package_name, packages[package_name])
        return ET.tostring(bom, encoding="unicode")

    @staticmethod
    @GeneralUtilities.check_arguments
    def __add_bom_component(components: ET.Element, package_name: str, package: dict) -> None:
        """Adds the package [package_name] of a "pubspec.lock" to the components of a bill-of-materials."""
        package_version: str = str(package.get("version", GeneralUtilities.empty_string))
        description: dict = package.get("description", dict())
        description = description if isinstance(description, dict) else dict()
        source: str = package.get("source", GeneralUtilities.empty_string)
        # A package-url identifies a package worldwide, so it is only set for a package which really is available
        # under that identity: a package which comes from a local path or from the sdk is not.
        is_published_package: bool = source == "hosted"
        component = ET.SubElement(components, "component", {"type": "library", "bom-ref": f"pkg:pub/{package_name}@{package_version}" if is_published_package else f"{source}:{package_name}"})
        ET.SubElement(component, "name").text = package_name
        ET.SubElement(component, "version").text = package_version
        # "dependency" states whether the package is used directly by the codeunit or only by one of its
        # dependencies, which is the information a reader of the bill-of-materials needs to know who to ask for an
        # update of it.
        ET.SubElement(component, "description").text = f"Package from the source \"{source}\" ({package.get('dependency', 'unknown dependency-kind')})."
        checksum: str = description.get("sha256", None) if is_published_package else None
        if checksum is not None:
            hashes = ET.SubElement(component, "hashes")
            ET.SubElement(hashes, "hash", {"alg": "SHA-256"}).text = checksum
        if is_published_package:
            ET.SubElement(component, "purl").text = f"pkg:pub/{package_name}@{package_version}"
            registry_address: str = description.get("url", None)
            if registry_address is not None:
                external_references = ET.SubElement(component, "externalReferences")
                ET.SubElement(ET.SubElement(external_references, "reference", {"type": "distribution"}), "url").text = f"{registry_address.rstrip('/')}/packages/{package_name}/versions/{package_version}"

    @GeneralUtilities.check_arguments
    def __add_package_registry_files_to_artifacts(self, artifacts_folder: str, package_name: str, add_readme: bool, add_license: bool, add_changelog: bool, branch_of_published_state: str) -> None:
        """Puts the readme of the codeunit as well as the license and the changelog of the repository into the
        copies of the package which the sourcecode-artifacts contain.

        Doing it here means that the codeunit keeps one single readme and the repository one single license and one
        single changelog, instead of a second copy inside the package which would have to be maintained in parallel
        and would drift apart from the original.

        The readme is taken from the codeunit and not from the repository, because a repository can contain
        several codeunits and therefore several packages, each of which needs its own description."""
        readme_content: str = None
        if add_readme:
            readme_file: str = os.path.join(self.get_codeunit_folder(), "ReadMe.md")
            GeneralUtilities.assert_file_exists(readme_file, f"The readme of the codeunit (\"{readme_file}\") does not exist, but it should be added to the package.")
            readme_content = self.__get_readme_with_absolute_links(GeneralUtilities.read_text_from_file(readme_file), branch_of_published_state)
        license_file: str = os.path.join(self.get_repository_folder(), "License.txt")
        if add_license:
            GeneralUtilities.assert_file_exists(license_file, f"The license of the repository (\"{license_file}\") does not exist, but it should be added to the package.")
        changelog_content: str = None
        if add_changelog:
            changelog_content = self.__get_changelog_of_repository()
        for artifact_name in self.__artifacts_which_contain_the_sourcecode:
            artifact_folder: str = os.path.join(artifacts_folder, artifact_name)
            if not os.path.isdir(artifact_folder):
                continue
            # A codeunit without a package-name is its own package, so the sourcecode-artifact itself is the
            # package-folder in that case.
            package_folder: str = artifact_folder if package_name is None else os.path.join(artifact_folder, package_name)
            GeneralUtilities.assert_folder_exists(package_folder)
            if add_readme:
                GeneralUtilities.write_text_to_file(os.path.join(package_folder, self.__name_of_readme_in_package), readme_content)
            if add_license:
                shutil.copyfile(license_file, os.path.join(package_folder, self.__name_of_license_in_package))
            if add_changelog:
                GeneralUtilities.write_text_to_file(os.path.join(package_folder, self.__name_of_changelog_in_package), changelog_content)

    @GeneralUtilities.check_arguments
    def __get_changelog_of_repository(self) -> str:
        """Returns the changelog of the repository ("Other/Resources/Changelog") in the format a package expects
        for its changelog-file: one section per version, newest version first.

        The whole history is rendered and not only the version which is currently built, because a
        package-registry shows this file as the changelog of the package, where a reader expects to see what
        changed in every released version."""
        changelog_folder: str = os.path.join(self.get_repository_folder(), "Other", "Resources", "Changelog")
        GeneralUtilities.assert_folder_exists(changelog_folder, f"The changelog-folder of the repository (\"{changelog_folder}\") does not exist, but the changelog should be added to the package.")
        versions: list[tuple[tuple[int, ...], str]] = []
        for file_name in os.listdir(changelog_folder):
            match = self.__changelog_file_name_pattern.match(file_name)
            if match is not None:
                version: str = match.group("version")
                # The version is sorted by its numbers and not as a text, because "0.10.0" is newer than "0.9.0"
                # while it is smaller as a text.
                versions.append((tuple(int(part) for part in version.split(".")), version))
        if len(versions) == 0:
            raise ValueError(f"The changelog-folder of the repository (\"{changelog_folder}\") does not contain any changelog-file, but the changelog should be added to the package.")
        sections: list[str] = []
        for _, version in sorted(versions, reverse=True):
            content: str = GeneralUtilities.read_text_from_file(os.path.join(changelog_folder, f"v{version}.md"))
            sections.append(f"## {version}{self.__linebreak}{self.__linebreak}{self.__get_entries_of_changelog_file(content)}")
        return self.__linebreak.join(sections)

    @staticmethod
    @GeneralUtilities.check_arguments
    def __get_entries_of_changelog_file(content: str) -> str:
        """Returns the entries of one changelog-file of the repository, without the headlines it begins with.

        Those headlines ("# Release notes", "## Changes") describe the file itself, while in the changelog of the
        package the version is the headline of the section. Only the headlines at the beginning of the file are
        removed, so a headline which belongs to the content of an entry is kept."""
        lines: list[str] = content.splitlines()
        index: int = 0
        while index < len(lines) and (lines[index].startswith("#") or len(lines[index].strip()) == 0):
            index = index+1
        return TFCPS_CodeUnitSpecific_Flutter_Functions.__linebreak.join(lines[index:]).strip()+TFCPS_CodeUnitSpecific_Flutter_Functions.__linebreak

    @GeneralUtilities.check_arguments
    def __get_readme_with_absolute_links(self, readme_content: str, branch_of_published_state: str) -> str:
        """Returns the given readme with every link which points into the repository replaced by an absolute one.

        A package-registry does not show the readme in the context of the repository, so a relative link (for
        example the one of a screenshot) can not be resolved there and the image would stay invisible. The address
        of the repository is taken from the product-information-file, so that a rename of the repository does not
        have to be repeated in every codeunit."""
        remote_address: str = self.get_remote_address()
        if not remote_address.startswith(self.__github_address_prefix):
            # Only the address under which github delivers the raw files of a repository is known here. A
            # repository which is hosted somewhere else keeps its relative links instead of getting links which
            # point to an address which does not exist.
            return readme_content
        # Example: "https://github.com/anionDev/MatCultureSelector" becomes
        # "https://raw.githubusercontent.com/anionDev/MatCultureSelector/main".
        address_of_raw_files: str = f"{remote_address.replace(self.__github_address_prefix, self.__github_raw_address_prefix)}/{branch_of_published_state}"
        codeunit_name: str = self.get_codeunit_name()

        def make_link_absolute(match) -> str:
            # The link is relative to the folder of the codeunit, because that is where the readme lies. The
            # resulting path is normalized because a link which leaves the codeunit-folder ("../Other/...") would
            # otherwise result in an address which contains ".." and which no webserver resolves.
            path_in_repository: str = posixpath.normpath(f"{codeunit_name}/{match.group('target')}")
            return f"]({address_of_raw_files}/{path_in_repository})"

        # Matched is the target of a markdown-link which is neither absolute ("https://...", "//..."), nor an
        # anchor ("#...") nor root-relative ("/..."), so exactly the links which point into the repository.
        return re.sub(r"\]\((?P<target>(?![a-zA-Z][a-zA-Z0-9+.-]*:|//|#|/)[^)]+)\)", make_link_absolute, readme_content)

    @GeneralUtilities.check_arguments
    def linting(self,package_name:str=None) -> None:
        """Runs the linting of the codeunit.

        'package_name' is the name of the folder which contains the package of the codeunit. If it is not given
        then the package-folders are searched, so a codeunit which is its own package as well as one which
        contains the package in a subfolder are both linted without having to state which of the two it is."""
        codeunit_folder = self.get_codeunit_folder()
        self._protected_sc.normalize_invisible_characters_of_files_in_folder(codeunit_folder, ["java","dart", "kt", "html"])
        package_folders: list[str] = [os.path.join(codeunit_folder, package_name)] if package_name is not None else self.__get_package_folders()
        for package_folder in package_folders:
            # The dependencies of every package which is analyzed have to be resolved first. "flutter analyze"
            # does resolve them by itself, but only when it has to resolve anything at all: if the package itself
            # is already resolved (which it is after the testcases ran) then a package below it (for example the
            # "example"-application of a library) stays unresolved, and every symbol of every dependency of that
            # package is then reported as undefined - which looks like hundreds of real errors but is only a
            # missing "pub get".
            for folder_to_resolve in TFCPS_CodeUnitSpecific_Flutter_Functions.__get_folders_with_a_package(package_folder):
                self._protected_sc.run_with_epew("flutter", "pub get", folder_to_resolve, print_live_output=self.get_verbosity() == LogLevel.Debug)
            # "flutter analyze" is what runs the rules of the "analysis_options.yaml" of the package (usually
            # "package:flutter_lints"). It analyzes the package and everything below it, and it exits with a
            # non-zero exit-code as soon as it found an issue, which is what makes the linting fail.
            self._protected_sc.run_with_epew("flutter", "analyze", package_folder, print_live_output=self.get_verbosity() == LogLevel.Debug)

    @staticmethod
    @GeneralUtilities.check_arguments
    def __get_folders_with_a_package(folder: str) -> list[str]:
        """Returns [folder] and every folder below it which contains a "pubspec.yaml", so every folder whose
        dependencies have to be resolved before the folder can be analyzed.

        Generated and downloaded content is skipped: it contains the packages of the pub-cache and the output of
        previous builds, which are not part of the codeunit and must not be resolved as if they were."""
        folders_which_do_not_belong_to_the_sourcecode: set[str] = {".dart_tool", ".git", "build", "Artifacts"}
        result: list[str] = []
        for current_folder, subfolders, files in os.walk(folder):
            subfolders[:] = sorted(subfolder for subfolder in subfolders if subfolder not in folders_which_do_not_belong_to_the_sourcecode)
            if "pubspec.yaml" in files:
                result.append(current_folder)
        return result

    @GeneralUtilities.check_arguments
    def __get_package_folders(self) -> list[str]:
        """Returns the folders of the codeunit which contain a package, so the folders which contain a
        'pubspec.yaml'.

        Only the codeunit-folder itself and its direct subfolders are considered: a package which lies deeper (for
        example the 'example'-application of a package) belongs to the package above it and is processed together
        with it, not as a package of its own."""
        codeunit_folder: str = self.get_codeunit_folder()
        if os.path.isfile(os.path.join(codeunit_folder, "pubspec.yaml")):
            return [codeunit_folder]
        result: list[str] = []
        for entry in sorted(os.listdir(codeunit_folder)):
            folder: str = os.path.join(codeunit_folder, entry)
            if os.path.isdir(folder) and os.path.isfile(os.path.join(folder, "pubspec.yaml")):
                result.append(folder)
        GeneralUtilities.assert_condition(0 < len(result), f"The codeunit \"{self.get_codeunit_name()}\" does not contain a package: neither \"{codeunit_folder}\" nor one of its direct subfolders contains a \"pubspec.yaml\".")
        return result

    def organize_translations(self,arb_folder:str,languages:list[str])->None:
        self.tfcps_Tools_General.write_languages_as_resource(self.get_codeunit_folder(),languages)
        GeneralUtilities.assert_condition("en" in languages, "The languages-list must contain \"en\" (the default-language), even though \"en\" itself is never translated.")
        translated_languages = [language for language in languages if language != "en"]
        absolute_arb_folder=os.path.join(self.get_codeunit_folder(),arb_folder)#original flutter arb files
        xlf_folder=os.path.join(self.get_codeunit_folder(),"Other","Resources","Translations")#here should xlf files be stored like in E:\Data\Projects\ConSurv\ConSurvFrontend\Other\Resources\Translations: messages.xlf (with english texts), and messages.de.xlf, messages.fr.xlf, etc with the translations
        statistics=ArbTranslationsOrganizer().organize_translations(self._protected_sc,absolute_arb_folder,xlf_folder,translated_languages)
        target_file=os.path.join(xlf_folder,"TranslationState.json")
        self._protected_sc.generate_translation_state_diagram(statistics,target_file)

    @GeneralUtilities.check_arguments
    def translate_safe(self, base_language: str = "en", throw_if_no_credentials: bool = False) -> None:
        """Translates every not-yet-translated segment of Other/Resources/Translations/messages.<language>.xlf via
        LibreTranslate, if a translation-service is configured. The translation-service can be configured by creating
        a file at ~/.ScriptCollection/TranslationServiceProperties.txt with the content
        "LibreTranslateAPI=your_api_server_url" (matching TFCPS_CodeUnitSpecific_NodeJS_Functions.translate_safe)."""
        translationservice_file = os.path.join(self._protected_sc.get_global_cache_folder(), "TranslationServiceProperties.txt")
        api_server: str | None = None
        if os.path.isfile(translationservice_file):
            for line in GeneralUtilities.read_nonempty_lines_from_file(translationservice_file):
                if line.startswith("LibreTranslateAPI="):
                    api_server = line.replace("LibreTranslateAPI=", "").strip()
        if api_server is None:
            if throw_if_no_credentials:
                raise ValueError(
                    "No translation-service configured. Please create a file at "
                    "~/.ScriptCollection/TranslationServiceProperties.txt with the content "
                    "'LibreTranslateAPI=your_api_server_url' to enable automatic translation of xlf-files."
                )
        else:
            xlf_folder = os.path.join(self.get_codeunit_folder(), "Other", "Resources", "Translations")
            self._protected_sc.translate_xlf_files_in_folder(xlf_folder, base_language, api_server)

    @GeneralUtilities.check_arguments
    def do_common_tasks(self,current_codeunit_version:str,package_name:str )-> None:
        self.do_common_tasks_base(current_codeunit_version)
        self.__rewrite_vendored_pubspec_path_dependencies(self.get_codeunit_folder())
        # Removes any stale "build"/".dart_tool"-state before every build. Without this a leftover incremental-
        # compiler-cache from a previous, different run can make "flutter build <target>" (see build()) fail with
        # confusing "isn't defined"-errors for a file that is otherwise completely valid - reproduced and fixed for
        # MetisGameManager, where a stale cache broke settings_page.dart's compilation until "flutter clean" was run
        # by hand. This only deletes git-ignored files ("build", ".dart_tool", "ephemeral", see flutter's own
        # "clean" command), so it stays consistent with the pipeline's general idempotency-guarantee.
        package_folder = os.path.join(self.get_codeunit_folder(), package_name)
        self._protected_sc.run_with_epew("flutter", "clean", package_folder)
        # The codeunit-version is the single source of truth for the version of a flutter/dart-codeunit, so the
        # version of its package (which pub itself never derives from anything else) has to be kept in sync with it.
        repository_folder = self.get_repository_folder()
        version = current_codeunit_version if current_codeunit_version is not None else self.tfcps_Tools_General.get_version_of_project(repository_folder)
        pubspec_file = os.path.join(package_folder, "pubspec.yaml")
        content = GeneralUtilities.read_text_from_file(pubspec_file)
        content = re.sub(r"(?m)^version:.*$", f"version: {version}", content, count=1)
        GeneralUtilities.write_text_to_file(pubspec_file, content)

    @staticmethod
    def __rewrite_vendored_pubspec_path_dependencies(codeunit_folder: str) -> None:
        """copy_artifacts_from_dependent_code_units (see TFCPS_Tools_General, called by do_common_tasks_base right
        before this) vendors every declared dependent-codeunit's Other/Artifacts-folder into
        Other/Resources/DependentCodeUnits/<dependency>/ as flat siblings. A vendored Dart/Flutter package can
        itself declare a further, transitive dependent-codeunit as a "path"-dependency - but that path is only
        valid inside the dependency's own repository-layout (for example
        "../Other/Resources/DependentCodeUnits/AthenaBase/SourceCode/athena_base", correct only relative to
        AthenaGameChess's own folder-structure). Other/Resources/DependentCodeUnits is gitignored in every codeunit,
        so it is never part of a "SourceCode"-artifact (see copy_source_files_to_output_directory, which packages
        only "git ls-files"-tracked files) - meaning this path can never resolve at its new, vendored location, no
        matter which repository-layout the declaring codeunit itself uses.

        Since the common-project-structure's own dependentcodeunits-declaration convention already requires the
        *current* codeunit to directly declare (and therefore vendor, as a flat sibling right here) any codeunit it
        transitively needs, the fix is to rewrite such a dangling "path"-dependency to point at that sibling
        instead - never leaving a codeunit which combines more than one level of dependent-codeunits (for example a
        Flutter-app depending on a library which itself depends on a shared base-library) with two different,
        conflicting "path"-sources for the same package, which "dart pub get"/"flutter pub get" rejects outright.
        """
        dependent_codeunits_folder = os.path.join(codeunit_folder, "Other", "Resources", "DependentCodeUnits")
        if not os.path.isdir(dependent_codeunits_folder):
            return
        # Map every vendored package's own name (from its own pubspec.yaml) to the folder it was vendored into, so
        # a dangling "path"-dependency elsewhere can be redirected to the correct, flat sibling. Also keep every
        # vendored package-folder found (not deduplicated by name): both the "SourceCode"- and the
        # "BuildResult_SourceCode"-copy of the same package (see build(), which publishes the latter as a copy of
        # the former only to satisfy a generic artifact-naming check) need their own "path"-dependencies rewritten,
        # even though only the "SourceCode"-copy is ever actually resolved by "pub get".
        package_name_to_folder: dict[str, str] = {}
        all_package_folders: list[str] = []
        for dependency_name in sorted(os.listdir(dependent_codeunits_folder)):
            dependency_folder = os.path.join(dependent_codeunits_folder, dependency_name)
            if not os.path.isdir(dependency_folder):
                continue
            for flavor in ("SourceCode", "BuildResult_SourceCode"):
                flavor_folder = os.path.join(dependency_folder, flavor)
                if not os.path.isdir(flavor_folder):
                    continue
                for package_name in sorted(os.listdir(flavor_folder)):
                    package_folder = os.path.join(flavor_folder, package_name)
                    if os.path.isfile(os.path.join(package_folder, "pubspec.yaml")):
                        package_name_to_folder.setdefault(package_name, package_folder)
                        all_package_folders.append(package_folder)
        if len(package_name_to_folder) == 0:
            return
        for package_folder in all_package_folders:
            pubspec_file = os.path.join(package_folder, "pubspec.yaml")
            content = GeneralUtilities.read_text_from_file(pubspec_file)

            def replace_path_dependency(match: "re.Match[str]", current_package_folder: str = package_folder) -> str:
                dependency_name = match.group(2)
                target_folder = package_name_to_folder.get(dependency_name)
                if target_folder is None or os.path.normpath(target_folder) == os.path.normpath(current_package_folder):
                    return match.group(0)
                relative_path = os.path.relpath(target_folder, current_package_folder).replace(os.sep, "/")
                return f"{match.group(1)}{dependency_name}:\n{match.group(3)}path: {relative_path}"

            new_content = re.sub(r"(?m)^( {2})(\S+):\n( {4})path:\s*.+$", replace_path_dependency, content)
            if new_content != content:
                GeneralUtilities.write_text_to_file(pubspec_file, new_content)

    @GeneralUtilities.check_arguments
    def generate_reference(self) -> None:
        self.generate_reference_using_docfx()

    
    @GeneralUtilities.check_arguments
    def run_testcases(self,package_name:str) -> None:
        codeunit_folder = self.get_codeunit_folder()
        repository_folder = GeneralUtilities.resolve_relative_path("..", codeunit_folder)
        codeunit_name = os.path.basename(codeunit_folder)
        src_folder = GeneralUtilities.resolve_relative_path(package_name, codeunit_folder)
        
        self._protected_sc.run_with_epew("flutter", "test --coverage", src_folder)
        test_coverage_folder_relative = "Other/Artifacts/TestCoverage"
        test_coverage_folder = GeneralUtilities.resolve_relative_path(test_coverage_folder_relative, codeunit_folder)
        GeneralUtilities.ensure_directory_exists(test_coverage_folder)
        coverage_file_relative = f"{test_coverage_folder_relative}/TestCoverage.xml"
        coverage_file = GeneralUtilities.resolve_relative_path(coverage_file_relative, codeunit_folder)
        self._protected_sc.run_with_epew("lcov_cobertura", f"coverage/lcov.info --base-dir . --excludes test --output ../{coverage_file_relative} --demangle", src_folder)

        # format correctly
        content = GeneralUtilities.read_text_from_file(coverage_file)
        content = re.sub('<![^<]+>', '', content)
        content = re.sub('\\\\', '/', content)
        content = self.__rewrite_flutter_coverage_package_names(content, codeunit_name)
        content = re.sub('\\ filename=\\"lib/', f' filename="{package_name}/lib/', content)
        GeneralUtilities.write_text_to_file(coverage_file, content)
        self.tfcps_Tools_General.merge_packages(coverage_file, codeunit_name)
        self.tfcps_Tools_General.calculate_entire_line_rate(coverage_file)
        self.run_testcases_common_post_task(repository_folder, codeunit_name, True, self.get_target_environment_type())

    @GeneralUtilities.check_arguments
    def __build_linux_in_container(self, codeunit_folder: str, src_folder: str) -> None:
        """Runs "flutter build linux" inside a sibling-container of the "SCBuilder"-image (see the "linux"-branch of
        build() for why). If this process itself already runs inside a container (e.g. a "scbuildcodeunits -c"-run),
        the sibling-container is given access to the same volumes via "--volumes-from" instead of a bind-mount: a
        bind-mount of a path of this container would be resolved by the docker-daemon of the host, where that path
        does not exist or points to unrelated data (same reasoning as TFCPS_VisualRegressionTests)."""
        repository_folder = self.get_repository_folder()
        image = self.tfcps_Tools_General.oci_image_manager.get_registry_address_for_image_with_default_tag(repository_folder, "SCBuilder")
        image_address, image_tag = ScriptCollectionCore.split_image_address_and_tag(image)
        self._protected_sc.docker_pull(image_address, image_tag)
        working_directory_relative = os.path.relpath(src_folder, codeunit_folder).replace("\\", "/").strip("/")
        if self.__is_running_in_container():
            mount_arguments = ["--volumes-from", self.__get_own_container_id()]
            codeunit_folder_in_container = codeunit_folder.replace("\\", "/")
        else:
            codeunit_folder_in_container = "/codeunit"
            mount_arguments = ["-v", f"{codeunit_folder}:{codeunit_folder_in_container}"]
        working_folder = codeunit_folder_in_container if working_directory_relative in ("", ".") else f"{codeunit_folder_in_container}/{working_directory_relative}"
        # ".dart_tool" is hidden behind its own volume instead of being part of the bind-mount/volumes-from above:
        # ".dart_tool/package_config.json" records absolute paths into the pub-cache and the Flutter-SDK, which are
        # only valid on whatever host produced them. Reusing a ".dart_tool" a plain (non-containerized) run already
        # generated on the Windows/macOS host here would silently break resolution of every package (including
        # "package:flutter" itself) inside the Linux container, and vice versa - this was reproduced for
        # MetisGameManager, where a Windows-generated ".dart_tool" made the containerized "flutter build linux" fail
        # with seemingly unrelated "isn't defined"-errors across the whole codebase. This volume is reused by later
        # runs, so only the first one has to download the packages again (mirrors
        # VisualRegressionContainer.run_visual_regression_tests's own dart_tool_volume_name).
        dart_tool_volume_name = f"{os.path.basename(codeunit_folder).lower()}-build-linux-dart-tool"
        volume_arguments = ["-v", f"{dart_tool_volume_name}:{working_folder}/.dart_tool"]
        command = "flutter pub get && flutter build linux"
        arguments = ["run", "--rm"]+mount_arguments+volume_arguments+["-w", working_folder, image, "/bin/sh", "-c", command]
        self._protected_sc.run_program_argsasarray("docker", arguments, print_live_output=True)

    @GeneralUtilities.check_arguments
    def __is_running_in_container(self) -> bool:
        # The filesystem-marker is checked in addition to the convention-based environment-variable because a wrong
        # result here does not only change a message but makes the sibling-container access the wrong folder.
        return os.path.exists("/.dockerenv") or self._protected_sc.is_runnning_in_container()

    @GeneralUtilities.check_arguments
    def __get_own_container_id(self) -> str:
        # Determines the id of the container this process runs in, so that its volumes can be shared with the
        # SCBuilder-sibling-container via "docker run --volumes-from" (see TFCPS_VisualRegressionTests, which uses
        # the identical approach for the same reason).
        try:
            with open("/proc/self/mountinfo", "r", encoding="utf-8") as file_handle:
                match = re.search(r"/containers/([0-9a-f]{64})/", file_handle.read())
                if match is not None:
                    return match.group(1)
        except OSError:
            pass
        try:
            with open("/proc/self/cgroup", "r", encoding="utf-8") as file_handle:
                match = re.search(r"[0-9a-f]{64}", file_handle.read())
                if match is not None:
                    return match.group(0)
        except OSError:
            pass
        return socket.gethostname()

    @staticmethod
    def __rewrite_flutter_coverage_package_names(cobertura_xml_content:str,codeunit_name:str) -> str:
        """lcov_cobertura names a package after its source-subfolder relative to "lib" (for example "lib" itself
        for a file directly in "lib", "lib.chess" for a file in "lib/chess"), which has nothing to do with the
        codeunit-name. TFCPS_Tools_General.merge_packages expects every package of this coverage-file to equal the
        codeunit-name or to be dotted below it, so every "lib"-prefix is rewritten to the codeunit-name here
        instead: "lib" becomes "<codeunit-name>", "lib.chess" becomes "<codeunit-name>.chess". Without this,
        merge_packages either keeps nothing (a Flutter-codeunit's packages never actually match the codeunit-name)
        or - once the codeunit's lib-folder has only that single, unprefixed "lib"-package - crashes outright,
        because merge_packages is not the only caller which expects every package to have a name."""
        return re.sub(r' name="lib(\.[^"]*)?"', lambda match: f' name="{codeunit_name}{match.group(1) or ""}"', cobertura_xml_content)
    
    
    def get_dependencies(self)->dict[str,set[str]]:
        return dict[str,set[str]]()#TODO
    
    @GeneralUtilities.check_arguments
    def get_available_versions(self,dependencyname:str)->list[str]:
        return []#TODO
    
    def set_dependency_version(self,name:str,new_version:str)->None:
        raise ValueError(f"Operation is not implemented.")
    
class TFCPS_CodeUnitSpecific_Flutter_CLI:

    @staticmethod
    @GeneralUtilities.check_arguments
    def parse(file:str)->TFCPS_CodeUnitSpecific_Flutter_Functions:
        parser=TFCPS_CodeUnitSpecific_Base_CLI.get_base_parser()
        #add custom parameter if desired
        args=parser.parse_args()
        result:TFCPS_CodeUnitSpecific_Flutter_Functions=TFCPS_CodeUnitSpecific_Flutter_Functions(file,LogLevel(int(args.verbosity)),args.targetenvironmenttype,not args.nocache,args.ispremerge)
        return result
