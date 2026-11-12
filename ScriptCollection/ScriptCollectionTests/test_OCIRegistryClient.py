import unittest
import requests
from ..ScriptCollection.OCIImages.OCIRegistryClient import OCIRegistryClient
from ..ScriptCollection.ScriptCollectionCore import ScriptCollectionCore
from ..ScriptCollection.SCLog import LogLevel


class FakeResponse(requests.Response):
    """A response which is created by the testcase instead of being received from a server."""

    def __init__(self, status_code: int, json_content: dict, headers: dict[str, str] = None, next_url: str = None):
        super().__init__()
        self.status_code = status_code
        self.__json_content = json_content
        self.headers.update(headers or {})
        self.__links = {} if next_url is None else {"next": {"url": next_url}}

    @property
    def links(self) -> dict:
        return self.__links

    def json(self, **kwargs) -> dict:
        return self.__json_content


def create_registry_client(responses: dict[str, FakeResponse], credentials: list[tuple[str, str, str]]) -> tuple[OCIRegistryClient, list[tuple[str, str]]]:
    """Returns an OCIRegistryClient whose requests are answered by the given responses (key: url) instead of a server, because a
    testcase must not communicate with a server. A request to a url which already has an "Authorization"-header is answered by the
    response with the key "<url> (authorized)" if available.
    Returns the client and the list of the sent requests (as url and authorization-header)."""
    sc = ScriptCollectionCore()
    sc.log.loglevel = LogLevel.Quiet
    setattr(sc, "get_docker_registry_credentials_from_environment_variables", lambda: credentials)
    result = OCIRegistryClient(sc)
    sent_requests: list[tuple[str, str]] = []

    def send_get_request(url: str, authorization_header: str) -> FakeResponse:
        sent_requests.append((url, authorization_header))
        if authorization_header is not None and f"{url} (authorized)" in responses:
            return responses[f"{url} (authorized)"]
        return responses[url]
    setattr(result, "send_get_request", send_get_request)
    return (result, sent_requests)


class OCIRegistryClientTests(unittest.TestCase):

    def test_registry_address_is_split_like_docker_does_it(self) -> None:
        # arrange
        registry_client = create_registry_client({}, [])[0]

        # act & assert
        self.assertEqual(("docker.io", "library/debian"), registry_client.split_registry_address("docker.io/library/debian"))
        self.assertEqual(("docker.io", "library/debian"), registry_client.split_registry_address("docker.io/debian"))
        self.assertEqual(("docker.io", "library/debian"), registry_client.split_registry_address("debian"))
        self.assertEqual(("docker.io", "aniondev/scbuilder"), registry_client.split_registry_address("aniondev/scbuilder"))
        self.assertEqual(("ghcr.io", "betterleaks/betterleaks"), registry_client.split_registry_address("ghcr.io/betterleaks/betterleaks"))
        self.assertEqual(("myregistry.example.com:5000", "debian"), registry_client.split_registry_address("myregistry.example.com:5000/debian"))
        self.assertEqual(("localhost", "debian"), registry_client.split_registry_address("localhost/debian"))

    def test_anonymous_bearer_token_is_requested_and_all_pages_are_read(self) -> None:
        # arrange
        first_page_url = "https://ghcr.io/v2/betterleaks/betterleaks/tags/list?n=1000"
        second_page_url = "https://ghcr.io/v2/betterleaks/betterleaks/tags/list?last=v1.4.1&n=1000"
        token_url = "https://ghcr.io/token?service=ghcr.io&scope=repository%3Abetterleaks%2Fbetterleaks%3Apull"
        responses = {
            first_page_url: FakeResponse(401, {}, {"WWW-Authenticate": 'Bearer realm="https://ghcr.io/token",service="ghcr.io",scope="repository:betterleaks/betterleaks:pull"'}),
            f"{first_page_url} (authorized)": FakeResponse(200, {"tags": ["v1.4.0", "v1.4.1"]}, next_url="/v2/betterleaks/betterleaks/tags/list?last=v1.4.1&n=1000"),
            token_url: FakeResponse(200, {"token": "abc"}),
            second_page_url: FakeResponse(200, {"tags": ["v1.5.0"]}),
        }
        registry_client, sent_requests = create_registry_client(responses, [])

        # act
        actual_result = registry_client.get_tags("ghcr.io/betterleaks/betterleaks")

        # assert
        self.assertEqual(["v1.4.0", "v1.4.1", "v1.5.0"], actual_result)
        self.assertEqual([(first_page_url, None), (token_url, None), (first_page_url, "Bearer abc"), (second_page_url, "Bearer abc")], sent_requests)

    def test_docker_hub_is_accessed_using_its_api_host(self) -> None:
        # arrange
        url = "https://registry-1.docker.io/v2/library/debian/tags/list?n=1000"
        registry_client, sent_requests = create_registry_client({url: FakeResponse(200, {"tags": ["13.4-slim"]})}, [])

        # act
        actual_result = registry_client.get_tags("docker.io/library/debian")

        # assert
        self.assertEqual(["13.4-slim"], actual_result)
        self.assertEqual([(url, None)], sent_requests)

    def test_defined_credentials_are_used_for_basic_authentication(self) -> None:
        # arrange
        url = "https://myregistry.example.com/v2/debian/tags/list?n=1000"
        responses = {
            url: FakeResponse(401, {}, {"WWW-Authenticate": 'Basic realm="Registry"'}),
            f"{url} (authorized)": FakeResponse(200, {"tags": ["13.4-slim"]}),
        }
        registry_client, sent_requests = create_registry_client(responses, [("myregistry.example.com", "user", "password")])

        # act
        actual_result = registry_client.get_tags("myregistry.example.com/debian")

        # assert
        self.assertEqual(["13.4-slim"], actual_result)
        self.assertEqual((url, "Basic dXNlcjpwYXNzd29yZA=="), sent_requests[1])

    def test_basic_authentication_without_defined_credentials_fails(self) -> None:
        # arrange
        url = "https://myregistry.example.com/v2/debian/tags/list?n=1000"
        registry_client = create_registry_client({url: FakeResponse(401, {}, {"WWW-Authenticate": 'Basic realm="Registry"'})}, [])[0]

        # act & assert
        with self.assertRaises(Exception):
            registry_client.get_tags("myregistry.example.com/debian")
