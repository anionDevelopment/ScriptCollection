import os
import unittest
from unittest.mock import patch
from ..ScriptCollection.ScriptCollectionCore import ScriptCollectionCore
from ..ScriptCollection.TFCPS.DotNet.NuGetPackageSourceRegistration import NuGetPackageSourceRegistration
from ..ScriptCollection.TFCPS.TFCPS_Tools_General import TFCPS_Tools_General


class RecordedDotNetCalls:
    """Replaces the dotnet-cli: "dotnet nuget list source" returns the given registered sources, every call is recorded."""
    registered_sources: dict[str, str] = None
    calls: list[list[str]] = None
    logged_calls: list[list[str]] = None

    def __init__(self, registered_sources: dict[str, str]):
        self.registered_sources = registered_sources
        self.calls = []
        self.logged_calls = []

    def run_program(self, program: str, arguments: list[str], *_, **keyword_arguments) -> tuple[int, str, str, int]:
        assert program == "dotnet"
        self.calls.append(arguments)
        self.logged_calls.append(keyword_arguments.get("arguments_for_log", arguments))
        if arguments == ["nuget", "list", "source"]:
            output = "Registered Sources:\n" + "".join(f"  {index+1}.  {name} [Enabled]\n      {url}\n" for index, (name, url) in enumerate(self.registered_sources.items()))
            return (0, output, "", 0)
        return (0, "", "", 0)

    def get_modifying_calls(self) -> list[list[str]]:
        return [call for call in self.calls if call != ["nuget", "list", "source"]]


def register(registered_sources: dict[str, str], declarations: dict[str, str]) -> RecordedDotNetCalls:
    recorded = RecordedDotNetCalls(registered_sources)
    sc = ScriptCollectionCore()
    #cleared so that package-sources which are declared in the real environment do not leak into the test.
    with patch.dict(os.environ, declarations, clear=True), patch.object(sc, "run_program_argsasarray", side_effect=recorded.run_program):
        NuGetPackageSourceRegistration(sc, TFCPS_Tools_General(sc)).register_declared_package_sources("MyFolder")
    return recorded


class NuGetPackageSourceRegistrationTests(unittest.TestCase):

    def test_nothing_declared_changes_nothing(self) -> None:
        # act
        recorded = register({"nuget.org": "https://api.nuget.org/v3/index.json"}, {})

        # assert
        self.assertEqual([], recorded.calls)

    def test_a_declared_source_is_added_with_its_credentials(self) -> None:
        # act
        recorded = register({"nuget.org": "https://api.nuget.org/v3/index.json"}, {"Dependency_CSharp_MyFeed_URL": "https://example.com/nuget/index.json", "Dependency_CSharp_MyFeed_Username": "MyUser", "Dependency_CSharp_MyFeed_Password": "MyPassword"})

        # assert
        modifying_call = recorded.get_modifying_calls()[0]
        self.assertEqual(1, len(recorded.get_modifying_calls()))
        self.assertEqual(["nuget", "add", "source", "https://example.com/nuget/index.json", "--name", "myfeed", "--username", "MyUser", "--password", "MyPassword"], modifying_call[0:10])
        #the password must not be written to the build-log.
        self.assertNotIn("MyPassword", recorded.logged_calls[-1])

    def test_a_source_with_the_same_url_under_another_name_is_updated(self) -> None:
        # act
        recorded = register({"MyManuallyConfiguredFeed": "https://example.com/nuget/index.json/"}, {"Dependency_CSharp_MyFeed_URL": "https://EXAMPLE.com/nuget/index.json"})

        # assert
        #a second registration of the same feed would let every restore query the feed twice.
        self.assertEqual([["nuget", "update", "source", "MyManuallyConfiguredFeed", "--source", "https://EXAMPLE.com/nuget/index.json"]], recorded.get_modifying_calls())

    def test_a_source_with_the_same_name_is_registered_again(self) -> None:
        # act
        recorded = register({"myfeed": "https://example.com/old/index.json"}, {"Dependency_CSharp_MyFeed_URL": "https://example.com/new/index.json"})

        # assert
        self.assertEqual([["nuget", "remove", "source", "myfeed"], ["nuget", "add", "source", "https://example.com/new/index.json", "--name", "myfeed"]], recorded.get_modifying_calls())
