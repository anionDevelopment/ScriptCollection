# Contributing

Thank you for your interest in contributing to this product!
We welcome contributions from everyone.

Contributions are accepted as pull-request.
Before you submit a pull-request, please read these guidelines carefully.

## Contributor License Agreement (CLA)

All contributions to this product must be made under the terms of the Contributor License Agreement.

By submitting a contribution (including code, documentation, or any other materials), you agree that:

- You have read and understood the CLA.
- You have the right to grant the license described in the CLA.
- Your contribution does not violate the rights of any third party.

The CLA is located in [`ContributorLicenseAgreement.txt`](ContributorLicenseAgreement.txt).

Contributions submitted without a signed CLA may be rejected or removed.
This is required for legal reasons because otherwise a product is not maintainable anymore if the copyright of the product is divided among several actors.

## How to Contribute

### Technical considerations

1. Fork the repository and create a branch for your feature or bugfix.
2. Make your changes following the coding guidelines and ensure the project is buildable without generating any changes in the repository.
3. Submit a pull request to the main-branch with a clear description of your changes.
4. Ensure you have accepted the CLA before your pull request can be merged.

### Development guidelines

#### Structure

When adding new features, do not alter the existing project architecture.
New code must follow the same style, structure, and patterns already established in the codebase.
Look at existing features as the reference implementation and build analogously.
If there is a file called HowToBuild.md for the code you changed then you must ensure that when your work is finished the project is buildable using the instruction in HowToBuild.md without generating any changes in the repository.

#### Documentation

There must be doc-comments for all functions you write except helper-scripts. The access-modifier does not matter for this rule.

#### Tests

There must be unit-tests for every nontrivial new or changed function-behavior.

---

Thank you for helping make this product better!
