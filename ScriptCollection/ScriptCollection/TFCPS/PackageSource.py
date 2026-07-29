from ..GeneralUtilities import GeneralUtilities


class PackageSource:
    """A source from which packages of a dependency of a codeunit are downloaded (for example a NuGet-feed).
    A package-source is not part of a repository: which sources a machine may use and which credentials it uses for them is
    machine-specific information. It is therefore transported via environment-variables (see
    TFCPS_Tools_General.get_declared_package_sources), whose values are typically defined in the user-specific
    configuration-file of the required environment-variables."""

    name: str = None
    url: str = None
    username: str = None
    password: str = None

    def __init__(self, name: str, url: str, username: str, password: str):
        GeneralUtilities.assert_condition(GeneralUtilities.string_has_content(name), "A package-source must have a name.")
        GeneralUtilities.assert_condition(GeneralUtilities.string_has_content(url), f"The package-source '{name}' must have an url.")
        self.name = name
        self.url = url
        self.username = username
        self.password = password

    @GeneralUtilities.check_arguments
    def has_credentials(self) -> bool:
        return GeneralUtilities.string_has_content(self.username) and GeneralUtilities.string_has_content(self.password)
