import base64
import re
from urllib.parse import urlencode
import requests
from ..GeneralUtilities import GeneralUtilities
from ..ScriptCollectionCore import ScriptCollectionCore


class OCIRegistryClient:
    """Reads information about images from OCI-registries using the OCI-distribution-api (see
    https://github.com/opencontainers/distribution-spec/blob/main/spec.md ), which is implemented by docker-hub, ghcr.io,
    quay.io, mcr.microsoft.com and by a custom deployed docker-registry as well. So there is one implementation for all registries
    and no registry-specific api is used."""

    __sc: ScriptCollectionCore = None
    __docker_hub_address: str = "docker.io"
    __docker_hub_api_host: str = "registry-1.docker.io"
    __page_size: int = 1000
    __timeout_in_seconds: int = 30

    def __init__(self, sc: ScriptCollectionCore):
        self.__sc = sc

    @GeneralUtilities.check_arguments
    def split_registry_address(self, registry_address: str) -> tuple[str, str]:
        """Splits an image-address without tag into the host of the registry and the repository inside the registry, following the
        rules of docker: the first segment is a host if it contains a "." or a ":" or if it is "localhost", otherwise the image is
        located on docker-hub. On docker-hub an image without namespace belongs to the namespace "library".
        Examples: "docker.io/debian" -> ("docker.io", "library/debian"), "aniondev/scbuilder" -> ("docker.io", "aniondev/scbuilder"),
        "myregistry.example.com:5000/debian" -> ("myregistry.example.com:5000", "debian")."""
        segments = registry_address.split("/")
        first_segment = segments[0]
        if len(segments) > 1 and ("." in first_segment or ":" in first_segment or first_segment == "localhost"):
            host = first_segment
            repository = "/".join(segments[1:])
        else:
            host = OCIRegistryClient.__docker_hub_address
            repository = registry_address
        if host == OCIRegistryClient.__docker_hub_address and "/" not in repository:
            repository = f"library/{repository}"
        return (host, repository)

    @GeneralUtilities.check_arguments
    def get_tags(self, registry_address: str) -> list[str]:
        """Returns all tags of the image which is located at the given image-address (without tag), for example
        "docker.io/library/debian" or "ghcr.io/betterleaks/betterleaks".
        If credentials for the registry are defined on this machine (see
        ScriptCollectionCore.get_docker_registry_credentials_from_environment_variables) then they are used, otherwise the registry is
        accessed anonymously."""
        host, repository = self.split_registry_address(registry_address)
        api_host = OCIRegistryClient.__docker_hub_api_host if host == OCIRegistryClient.__docker_hub_address else host
        credentials = self.__get_credentials(host)
        result: list[str] = []
        url = f"https://{api_host}/v2/{repository}/tags/list?n={OCIRegistryClient.__page_size}"
        authorization_header: str = None
        while url is not None:
            response = self.send_get_request(url, authorization_header)
            if response.status_code == 401 and authorization_header is None:
                authorization_header = self.__get_authorization_header(response.headers.get("WWW-Authenticate"), credentials)
                response = self.send_get_request(url, authorization_header)
            response.raise_for_status()
            result.extend(response.json().get("tags") or [])
            url = self.__get_url_of_next_page(api_host, response)
        return result

    @GeneralUtilities.check_arguments
    def send_get_request(self, url: str, authorization_header: str) -> requests.Response:
        """Sends a get-request. This is the only function of this class which communicates with a server."""
        headers = {}
        if authorization_header is not None:
            headers["Authorization"] = authorization_header
        return requests.get(url, headers=headers, timeout=OCIRegistryClient.__timeout_in_seconds)

    @GeneralUtilities.check_arguments
    def __get_credentials(self, host: str) -> tuple[str, str]:
        """Returns (username, password) of the registry with the given host or None if no credentials are defined for it."""
        for address, username, password in self.__sc.get_docker_registry_credentials_from_environment_variables():
            if address.rstrip("/") == host:
                return (username, password)
        return None

    @GeneralUtilities.check_arguments
    def __get_authorization_header(self, authentication_challenge: str, credentials: tuple[str, str]) -> str:
        """Returns the value of the authorization-header which answers the given challenge (the WWW-Authenticate-header of a 401-response)."""
        GeneralUtilities.assert_condition(GeneralUtilities.string_has_content(authentication_challenge), "The registry requires authentication but does not tell how.")
        scheme = authentication_challenge.split(" ", 1)[0].lower()
        if scheme == "basic":
            GeneralUtilities.assert_condition(credentials is not None, "The registry requires basic-authentication but no credentials are defined for it.")
            return self.__get_basic_authorization_header(credentials)
        GeneralUtilities.assert_condition(scheme == "bearer", f"Unsupported authentication-scheme in challenge \"{authentication_challenge}\".")
        parameters = dict(re.findall(r'(\w+)="([^"]*)"', authentication_challenge))
        GeneralUtilities.assert_condition("realm" in parameters, f"No realm defined in challenge \"{authentication_challenge}\".")
        token_parameters = {key: value for key, value in parameters.items() if key in ("service", "scope")}
        token_url = f"{parameters['realm']}?{urlencode(token_parameters)}"
        token_authorization_header = None if credentials is None else self.__get_basic_authorization_header(credentials)
        response = self.send_get_request(token_url, token_authorization_header)
        response.raise_for_status()
        token_data = response.json()
        token = token_data.get("token") or token_data.get("access_token")
        GeneralUtilities.assert_condition(GeneralUtilities.string_has_content(token), f"The token-service \"{parameters['realm']}\" did not return a token.")
        return f"Bearer {token}"

    @GeneralUtilities.check_arguments
    def __get_basic_authorization_header(self, credentials: tuple[str, str]) -> str:
        encoded_credentials = base64.b64encode(f"{credentials[0]}:{credentials[1]}".encode("utf-8")).decode("ascii")
        return f"Basic {encoded_credentials}"

    @GeneralUtilities.check_arguments
    def __get_url_of_next_page(self, api_host: str, response: requests.Response) -> str:
        """Returns the url of the next page of a paginated tag-list or None if the response contains the last page."""
        next_link = response.links.get("next")
        if next_link is None:
            return None
        next_url: str = next_link["url"]
        if next_url.startswith("/"):
            next_url = f"https://{api_host}{next_url}"
        return next_url
