# Encrypted containers in a repository

## Overview

Encrypted containers allow committing sensitive data (for example credentials, certificates or configuration-files with secrets) to a git-repository without ever having them unencrypted in a committable state.

An encrypted container consists of:

- a container-file (committed): contains all files and folders of the target-folder in encrypted form.
- a target-folder (git-ignored): contains the decrypted files and folders while working with them.

The sensitive data are always either encrypted (in the container-file) or git-ignored (in the target-folder).

ScriptCollection provides 3 commands for this:

| Command                          | What it does                                                                                                                                                                                                                                 |
| -------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `scinitencryptedcontainerinrepo` | Creates a new container: creates the container-file as encrypted empty container and adds the line `<Name>;<Target>` to the definition-file (which is created if it does not exist). Fails if the name is already defined or if the container-file already exists. |
| `scdecryptinrepo`                | Decrypts the container-file into the target-folder. Fails if the target-folder is not empty. In a git-repository the target-folder is added to `.gitignore` before anything is decrypted into it, if it is not git-ignored yet.               |
| `scencryptinrepo`                | Encrypts the content of the target-folder into the container-file and deletes the content of the target-folder afterwards. If the content did not change, the container-file remains unchanged, so git does not show a change for it.       |

`scdecryptinrepo` and `scencryptinrepo` are reverse-functions of each other.

Arguments:

| Argument           | Required | Description                                                                                                                                         |
| ------------------ | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `-f`, `--folder`   | no       | Folder which contains the definition-file (usually the root-folder of the repository). Relative paths are resolved against the current working-directory. Default: `.` |
| `-n`, `--name`     | yes      | Name of the container as defined in the definition-file.                                                                                            |
| `-p`, `--password` | one of `-p` and `-i` | Password of the container.                                                                                                              |
| `-i`, `--interactive` | one of `-p` and `-i` | Requests the password interactively (without echo). `scinitencryptedcontainerinrepo` requests it twice and fails if the inputs are not equal. |
| `-t`, `--target`   | yes, only for `scinitencryptedcontainerinrepo` | Target-folder of the new container, relative to `--folder`. Is written to the column `Target` of the definition-file.          |

## Definition-file

The containers are defined in `<folder>/.ScriptCollection/EncryptedFolders.csv`.
The first line is the header. The columns are separated by semicolon:

| Column   | Description                                                                                                                                                                  |
| -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Name`   | Name of the container. Used for the `--name`-argument and as file-name of the container-file. Must be unique in the file and must only contain letters, digits, `-`, `_` and `.`. |
| `Target` | Relative path of the target-folder. Must be a subfolder of `<folder>`. Must not contain and must not be located inside of `.ScriptCollection/SensitiveDataContainer`.        |

Example:

```csv
Name;Target
ServerCredentials;Other/Resources/SensitiveData/ServerCredentials
```

Lines starting with `#` are treated as comments.

## Container-files

The location of the container-files can not be configured. The container-file of a container is always stored as `<folder>/.ScriptCollection/SensitiveDataContainer/<Name>.bin`.
For the example above this is `.ScriptCollection/SensitiveDataContainer/ServerCredentials.bin`.

## Usage

### Create a new container

1. Create the container:

   ```cmd
   scinitencryptedcontainerinrepo -n ServerCredentials -t Other/Resources/SensitiveData/ServerCredentials -i
   ```

   This adds the line `ServerCredentials;Other/Resources/SensitiveData/ServerCredentials` to `.ScriptCollection/EncryptedFolders.csv` (the file is created if it does not exist) and creates the encrypted empty container-file `.ScriptCollection/SensitiveDataContainer/ServerCredentials.bin`.
2. Commit the definition-file and the container-file.

### Change the content of a container

1. Decrypt the container:

   ```cmd
   scdecryptinrepo -n ServerCredentials -i
   ```

   The target-folder now contains the decrypted files and folders. In a git-repository it is git-ignored.
2. Add, change or remove files and folders in the target-folder.
3. Encrypt the container again:

   ```cmd
   scencryptinrepo -n ServerCredentials -i
   ```

   The container-file is updated and the content of the target-folder is deleted. The target-folder itself remains as empty folder.
4. Commit the changed container-file.

### Only read the content of a container

Decrypt the container, read the files and run `scencryptinrepo` afterwards. Since the content did not change, the container-file remains unchanged and the content of the target-folder is deleted.

### Change the password of a container

`scencryptinrepo` refuses to overwrite a container-file which can not be decrypted with the given password. This prevents that a typo in the password makes the content inaccessible. To change the password:

1. Decrypt the container with the old password using `scdecryptinrepo`.
2. Delete the container-file.
3. Encrypt the container with the new password using `scencryptinrepo`.

## Behavior in detail

- `scdecryptinrepo` fails if the target-folder already contains files or folders, so that existing (possibly changed and not yet encrypted) data are never overwritten.
- `scdecryptinrepo` fails if the container-file does not exist. Use `scinitencryptedcontainerinrepo` to create it.
- `scdecryptinrepo` with a wrong password fails without creating the target-folder.
- `scencryptinrepo` verifies the written container-file (decrypting it again and comparing it with the content of the target-folder) before it deletes the content of the target-folder.
- `scencryptinrepo` fails if the target-folder does not exist.
- Links (symbolic links, hard links, junctions) in the target-folder are not supported. `scencryptinrepo` fails if it finds one.
- File-attributes and timestamps of the files are not stored in the container. Empty folders are stored.

## Security

- Encryption: AES-256-GCM. The key is derived from the password using scrypt with a random salt. Every write of a container-file uses a new salt and a new nonce.
- The container-file is authenticated, so manipulations of the container-file are detected while decrypting.
- A password passed with `--password` can be visible in the history of the shell and in the process-list of the operating-system. Use `--interactive` to avoid this.
- The target-folder contains the sensitive data unencrypted while it is decrypted. Run `scencryptinrepo` as soon as you do not need the decrypted data anymore.
- Use a strong password. The security of the container-file in the repository depends completely on the password.
