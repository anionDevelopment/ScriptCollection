import os
from urllib import request
import time
import ssl
from datetime import timedelta,datetime
from ...GeneralUtilities import GeneralUtilities, Platform
from ...SCLog import  LogLevel
from ..TFCPS_CodeUnitSpecific_Base import TFCPS_CodeUnitSpecific_Base,TFCPS_CodeUnitSpecific_Base_CLI


class TFCPS_CodeUnitSpecific_Docker_Functions(TFCPS_CodeUnitSpecific_Base):

    def __init__(self,current_file:str,verbosity:LogLevel,targetenvironmenttype:str,use_cache:bool,is_pre_merge:bool):
        super().__init__(current_file, verbosity,targetenvironmenttype,use_cache,is_pre_merge)

    @GeneralUtilities.check_arguments
    def build(self,platforms:list[Platform],custom_arguments:dict[str,str]) -> None:
        codeunitname: str =self.get_codeunit_name()
        codeunit_folder =self.get_codeunit_folder()
        codeunitname_lower = codeunitname.lower()
        codeunit_file =self.get_codeunit_file()
        codeunitversion = self.tfcps_Tools_General.get_version_of_codeunit(codeunit_file)
        if custom_arguments is None:
            custom_arguments=dict[str,str]()
        artifacts_folder = GeneralUtilities.resolve_relative_path("Other/Artifacts", codeunit_folder)
        app_artifacts_folder = os.path.join(artifacts_folder, "BuildResult_OCIImage")
        GeneralUtilities.ensure_folder_exists_and_is_empty(app_artifacts_folder)
        for platform in platforms:
            #builder must be created once before with "docker buildx create --use"
            args = ["buildx","build", "--platform",GeneralUtilities.platform_to_docker_platform_str(platform), "--pull", "--force-rm", "--progress=plain", "--build-arg", f"TargetEnvironmentType={self.get_target_environment_type()}", "--build-arg", f"CodeUnitName={codeunitname}", "--build-arg", f"CodeUnitVersion={codeunitversion}", "--build-arg", f"CodeUnitOwnerName={self.tfcps_Tools_General.get_codeunit_owner_name(self.get_codeunit_file())}", "--build-arg", f"CodeUnitOwnerEMailAddress={self.tfcps_Tools_General.get_codeunit_owner_emailaddress(self.get_codeunit_file())}", "--build-arg", f"Platform={GeneralUtilities.platform_to_dash_str(platform)}", "--build-arg", f"DotNetRuntime={GeneralUtilities.platform_to_dotnet_runtime_identifier(platform)}", "--build-arg", f"PlatformForGoVersion={GeneralUtilities.platform_to_go_runtime_identifier(platform)}"]
            for custom_argument_key, custom_argument_value in custom_arguments.items():
                args.append("--build-arg")
                args.append(f"{custom_argument_key}={custom_argument_value}")
            pip_args=self._protected_sc.get_pip_index_url_arguments_from_local_cache()
            if len(pip_args)>0:
                args.append("--build-arg")
                args.append(f"PipIndexUrlArguments={' '.join(pip_args)}")
            args = args+["--tag", f"{codeunitname_lower}:latest", "--tag", f"{codeunitname_lower}:{codeunitversion}", "--file", f"{codeunitname}/Dockerfile"]
            if not self.use_cache():
                args.append("--no-cache")
            target_file=os.path.join(app_artifacts_folder,f"{codeunitname}_v{codeunitversion}_{GeneralUtilities.platform_to_dash_str(platform)}.tar")
            args.append("--output")
            args.append(f"type=docker,dest={target_file}")
            args.append(".")
            time.sleep(5)
            self._protected_sc.run_program_argsasarray_with_retry("docker", args, codeunit_folder, print_errors_as_information=True,print_live_output=self.get_verbosity()==LogLevel.Debug,amount_of_attempts=3,delay_in_seconds=5)
            time.sleep(2)
            self._protected_sc.run_program_argsasarray("docker", ["load", "-i", target_file], codeunit_folder, print_errors_as_information=True,print_live_output=self.get_verbosity()==LogLevel.Debug)

        self.__generate_sbom_for_docker_image()
        self.copy_source_files_to_output_directory()


    @GeneralUtilities.check_arguments
    def __generate_sbom_for_docker_image(self) -> None:
        codeunitname=self.get_codeunit_name()
        codeunit_folder =self.get_codeunit_folder()
        artifacts_folder = GeneralUtilities.resolve_relative_path("Other/Artifacts", codeunit_folder)
        codeunitname_lower = codeunitname.lower()
        sbom_folder = os.path.join(artifacts_folder, "BOM")
        codeunitversion = self.tfcps_Tools_General.get_version_of_codeunit(self.get_codeunit_file())
        GeneralUtilities.ensure_directory_exists(sbom_folder)
        sbom_file = os.path.join(sbom_folder, f"{codeunitname}.{codeunitversion}.sbom.xml")
        # Let syft write the SBOM to stdout and capture it instead of retrieving it via a
        # bind-mount: in CI the docker daemon does not share this job's filesystem (mounted
        # socket / DinD), so a "-v ./BOM:/BOM" mount would write the file onto the daemon host
        # rather than into this job's BOM folder. stdout flows back through the docker client,
        # so it works regardless of where the daemon runs. format_xml_file re-parses and
        # rewrites the document, so the resulting file is byte-stable.
        syft_result = self._protected_sc.run_program_argsasarray("docker", ["run","--rm","-v","/var/run/docker.sock:/var/run/docker.sock",self.tfcps_Tools_General.oci_image_manager.get_registry_address_for_image_with_default_tag(self.get_repository_folder(),"Syft"),f"{codeunitname_lower}:{codeunitversion}","-o","cyclonedx-xml"], artifacts_folder, print_errors_as_information=True)
        GeneralUtilities.write_text_to_file(sbom_file, syft_result[1])
        self._protected_sc.format_xml_file(sbom_file)
 
    @GeneralUtilities.check_arguments
    def linting(self) -> None:
        pass#TODO

    @GeneralUtilities.check_arguments
    def do_common_tasks(self,current_codeunit_version:str )-> None:
        codeunitname =self.get_codeunit_name()
        codeunit_folder = self.get_codeunit_folder()
        codeunit_version = current_codeunit_version
        self._protected_sc.replace_version_in_dockerfile_file(GeneralUtilities.resolve_relative_path(f"./{codeunitname}/Dockerfile", codeunit_folder), codeunit_version)
        self.do_common_tasks_base(current_codeunit_version)
        self.tfcps_Tools_General.standardized_tasks_update_version_in_docker_examples_if_available(codeunit_folder,codeunit_version)
 
    @GeneralUtilities.check_arguments
    def generate_reference(self) -> None:
        self.generate_reference_using_docfx()
    
    @GeneralUtilities.check_arguments
    def run_testcases(self) -> None:
        pass#TODO
    
    @GeneralUtilities.check_arguments
    def get_dependencies(self)->dict[str,set[str]]:
        return dict[str,set[str]]()#TODO
    
    @GeneralUtilities.check_arguments
    def get_available_versions(self,dependencyname:str)->list[str]:
        return []#TODO

    @GeneralUtilities.check_arguments
    def set_dependency_version(self,name:str,new_version:str)->None:
        raise ValueError(f"Operation is not implemented.")

    @GeneralUtilities.check_arguments
    @GeneralUtilities.deprecated("Use image_is_working_via_network instead, which tests the image over a user-defined docker-network without publishing a host-port.")
    def image_is_working(self,timeout:timedelta,environment_variables:dict[str,str],test_port:int,http_test_route:str,use_https_for_test:bool)->tuple[bool,str]:
        if timeout is None:
            timeout=timedelta(seconds=120)
        if environment_variables is None:
            environment_variables={}
        current_platform = GeneralUtilities.get_current_platform()
        platform_for_test:Platform=None
        if current_platform == Platform.Windows_AMD64:
            platform_for_test=Platform.Linux_AMD64
        elif current_platform == Platform.Linux_AMD64:
            platform_for_test=Platform.Linux_AMD64
        elif current_platform == Platform.Linux_ARM64:
            platform_for_test=Platform.Linux_ARM64
        elif current_platform == Platform.MacOS_ARM64:
            platform_for_test=Platform.Linux_ARM64
        else:
            raise ValueError(f"Current platform {current_platform} is not supported for testing.")
        oci_image_artifacts_folder :str= GeneralUtilities.resolve_relative_path("Other/Artifacts/BuildResult_OCIImage", self.get_codeunit_folder())
        container_name:str=f"{self.get_codeunit_name()}finaltest".lower()
        self.tfcps_Tools_General.ensure_containers_are_not_running([container_name])
        self.tfcps_Tools_General.load_docker_image(oci_image_artifacts_folder,platform_for_test)
        codeunit_file:str=os.path.join(self.get_codeunit_folder(),f"{self.get_codeunit_name()}.codeunit.xml")
        image=f"{self.get_codeunit_name()}:{self.tfcps_Tools_General.get_version_of_codeunit(codeunit_file)}".lower()
        argument=f"run -d --name {container_name}"
        if test_port is not None:
            argument=f"{argument} -p {test_port}:{test_port}"
        for k,v in environment_variables.items():
            argument=f"{argument} -e {k}={v}"#TODO switch to argument-array to also allow values with white-space
        argument=f"{argument} {image}"
        GeneralUtilities.assert_condition(http_test_route is None or http_test_route.startswith("/"),"If a test-route is given then it must start with \"/\".")
        try:
            last_exception:Exception=None
            self._protected_sc.run_program("docker",argument)
            start:datetime=GeneralUtilities.get_now()
            end:datetime=start+timeout
            while GeneralUtilities.get_now()<end:
                time.sleep(1)
                try:
                    if not self._protected_sc.container_is_running_and_healthy(container_name):
                        raise ValueError("Container is not running and healthy.")
                    if http_test_route is not None:
                        url="http"
                        if use_https_for_test:
                            url=url+"s"
                        url=url+"://localhost"
                        if test_port is not None:
                            url=url+":"+str(test_port)
                        url=url+http_test_route
                        ctx = ssl.create_default_context()
                        ctx.check_hostname = False
                        ctx.verify_mode = ssl.CERT_NONE
                        with request.urlopen(url, context=ctx) as response:
                            status = response.status
                            if status < 200 or 300 <= status:
                                raise ValueError(f"Test-call \"GET {url}\" had response-statuscode {status}.")
                    return (True,None)
                except Exception as e:
                    last_exception=e
            container_output:str=None
            if not self._protected_sc.container_is_exists(container_name):
                return (False,f"Container \"{container_name}\" does not exist.")
            try:
                container_output="\nContainer-output:\n"+self._protected_sc.get_output_of_container(container_name)
            except Exception:
                container_output="\n(Container-output not retrievable.)"
            exception_message=f"\nContainer was started with \"docker {argument}\"."
            if last_exception is not None:
                exception_message=exception_message+"\nLast exception: "+GeneralUtilities.exception_to_str(last_exception)
            if not self._protected_sc.container_is_running(container_name):
                return (False,f"Container \"{container_name}\" is not running.{exception_message}{container_output}")
            if not self._protected_sc.container_is_healthy(container_name):
                return (False,f"Container \"{container_name}\" is not healthy.{exception_message}{container_output}")
            return (False,f"Container \"{container_name}\" is not working properly.{exception_message}{container_output}")
        finally:
            self.tfcps_Tools_General.ensure_containers_are_not_running([container_name])

    @GeneralUtilities.check_arguments
    @GeneralUtilities.deprecated("Use verify_image_is_working_via_network instead, which tests the image over a user-defined docker-network without publishing a host-port.")
    def verify_image_is_working(self,timeout:timedelta,environment_variables:dict[str,str],test_port:int,http_test_route:str,use_https_for_test:bool):
        check_result:tuple[bool,str]= self.image_is_working(timeout,environment_variables,test_port,http_test_route,use_https_for_test)
        if not check_result[0]:
            raise ValueError("Image not working: "+check_result[1])

    @GeneralUtilities.check_arguments
    def image_is_working_via_network(self,timeout:timedelta,environment_variables:dict[str,str],container_port:int,http_test_route:str,use_https_for_test:bool,network_name:str)->tuple[bool,str]:
        """Tests the built image without publishing a host-port: the container is attached to a
        user-defined docker-network and the http-test is executed from a sibling-container on the
        same network (addressing the container under test by its name). This avoids opening a port
        on the docker-host - which, when the daemon is the host-daemon (mounted socket), would be a
        real port on the host. The http-test is executed from a dedicated minimal curl-image that is
        resolved via the image-manager (registered as "Curl"), so it is pulled from the configured
        registry (no rate-limit) and does not require the image under test to provide curl.
        container_port is the port the application listens on inside the container."""
        if timeout is None:
            timeout=timedelta(seconds=120)
        if environment_variables is None:
            environment_variables={}
        current_platform = GeneralUtilities.get_current_platform()
        platform_for_test:Platform=None
        if current_platform == Platform.Windows_AMD64:
            platform_for_test=Platform.Linux_AMD64
        elif current_platform == Platform.Linux_AMD64:
            platform_for_test=Platform.Linux_AMD64
        elif current_platform == Platform.Linux_ARM64:
            platform_for_test=Platform.Linux_ARM64
        elif current_platform == Platform.MacOS_ARM64:
            platform_for_test=Platform.Linux_ARM64
        else:
            raise ValueError(f"Current platform {current_platform} is not supported for testing.")
        oci_image_artifacts_folder :str= GeneralUtilities.resolve_relative_path("Other/Artifacts/BuildResult_OCIImage", self.get_codeunit_folder())
        container_name:str=f"{self.get_codeunit_name()}finaltest".lower()
        GeneralUtilities.assert_condition(http_test_route is None or http_test_route.startswith("/"),"If a test-route is given then it must start with \"/\".")
        self.tfcps_Tools_General.ensure_containers_are_not_running([container_name])
        self.tfcps_Tools_General.load_docker_image(oci_image_artifacts_folder,platform_for_test)
        codeunit_file:str=os.path.join(self.get_codeunit_folder(),f"{self.get_codeunit_name()}.codeunit.xml")
        image=f"{self.get_codeunit_name()}:{self.tfcps_Tools_General.get_version_of_codeunit(codeunit_file)}".lower()
        self._protected_sc.ensure_local_docker_network_exists(network_name)
        argument=f"run -d --name {container_name} --network {network_name}"
        for k,v in environment_variables.items():
            argument=f"{argument} -e {k}={v}"#TODO switch to argument-array to also allow values with white-space
        argument=f"{argument} {image}"
        curl_image:str=None
        if http_test_route is not None:
            # Use a dedicated minimal curl-image to run the http-test from a sibling-container,
            # so it does not depend on the image under test providing curl. It is resolved via
            # the image-manager (like Syft), so it is pulled from the configured registry and
            # does not hit registry-rate-limits.
            curl_image=self.tfcps_Tools_General.oci_image_manager.get_registry_address_for_image_with_default_tag(self.get_repository_folder(),"Curl")
        try:
            last_exception:Exception=None
            self._protected_sc.run_program("docker",argument)
            start:datetime=GeneralUtilities.get_now()
            end:datetime=start+timeout
            while GeneralUtilities.get_now()<end:
                time.sleep(1)
                try:
                    if not self._protected_sc.container_is_running_and_healthy(container_name):
                        raise ValueError("Container is not running and healthy.")
                    if http_test_route is not None:
                        scheme="https" if use_https_for_test else "http"
                        url=f"{scheme}://{container_name}:{container_port}{http_test_route}"
                        curl_arguments="--fail --silent --show-error --max-time 30"
                        if use_https_for_test:
                            curl_arguments=curl_arguments+" --insecure"
                        self._protected_sc.run_program("docker",f"run --rm --network {network_name} --entrypoint curl {curl_image} {curl_arguments} {url}")
                    return (True,None)
                except Exception as e:
                    last_exception=e
            container_output:str=None
            if not self._protected_sc.container_is_exists(container_name):
                return (False,f"Container \"{container_name}\" does not exist.")
            try:
                container_output="\nContainer-output:\n"+self._protected_sc.get_output_of_container(container_name)
            except Exception:
                container_output="\n(Container-output not retrievable.)"
            exception_message=f"\nContainer was started with \"docker {argument}\"."
            if last_exception is not None:
                exception_message=exception_message+"\nLast exception: "+GeneralUtilities.exception_to_str(last_exception)
            if not self._protected_sc.container_is_running(container_name):
                return (False,f"Container \"{container_name}\" is not running.{exception_message}{container_output}")
            if not self._protected_sc.container_is_healthy(container_name):
                return (False,f"Container \"{container_name}\" is not healthy.{exception_message}{container_output}")
            return (False,f"Container \"{container_name}\" is not working properly.{exception_message}{container_output}")
        finally:
            self.tfcps_Tools_General.ensure_containers_are_not_running([container_name])

    @GeneralUtilities.check_arguments
    def verify_image_is_working_via_network(self,timeout:timedelta,environment_variables:dict[str,str],container_port:int,http_test_route:str,use_https_for_test:bool,network_name:str):
        check_result:tuple[bool,str]= self.image_is_working_via_network(timeout,environment_variables,container_port,http_test_route,use_https_for_test,network_name)
        if not check_result[0]:
            raise ValueError("Image not working: "+check_result[1])

class TFCPS_CodeUnitSpecific_Docker_CLI:

    @staticmethod
    @GeneralUtilities.check_arguments
    def parse(file:str)->TFCPS_CodeUnitSpecific_Docker_Functions:
        parser=TFCPS_CodeUnitSpecific_Base_CLI.get_base_parser()
        #add custom parameter if desired
        args=parser.parse_args()
        result:TFCPS_CodeUnitSpecific_Docker_Functions=TFCPS_CodeUnitSpecific_Docker_Functions(file,LogLevel(int(args.verbosity)),args.targetenvironmenttype,not args.nocache,args.ispremerge)
        return result
