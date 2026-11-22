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
| `scinitencryptedcontainerinrepo` | Creates the container-file as encrypted empty container. Fails if the container-file already exists.                                                                                                                                         |
| `scdecryptinrepo`                | Decrypts the container-file into the target-folder. Fails if the target-folder is not empty. In a git-repository the target-folder is added to `.gitignore` before anything is decrypted into it, if it is not git-ignored yet.               |
| `scencryptinrepo`                | Encrypts the content of the target-folder into the container-file and deletes the content of the target-folder afterwards. If the content did not change, the container-file remains unchanged, so git does not show a change for it.       |

`scdecryptinrepo` and `scencryptinrepo` are reverse-functions of each other.

All 3 commands have the same arguments:

| Argument           | Required | Description                                                                                                                                         |
| ------------------ | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `-f`, `--folder`   | no       | Folder which contains the definition-file (usually the root-folder of the repository). Relative paths are resolved against the current working-directory. Default: `.` |
| `-n`, `--name`     | yes      | Name of the container as defined in the definition-file.                                                                                            |
| `-p`, `--password` | yes      | Password of the container.                                                                                                                          |

## Definition-file

The containers are defined in `<folder>/.ScriptCollection/EncryptedFolders.csv`.
The first line is the header. The columns are separated by semicolon:

| Column   | Description                                                                                                       |
| -------- | ----------------------------------------------------------------------------------------------------------------- |
| `Name`   | Name of the container. Used for the `--name`-argument. Must be unique in the file.                               |
| `File`   | Relative path of the container-file. Must be located in a subfolder of `<folder>` and not inside of `Target`.  |
| `Target` | Relative path of the target-folder. Must be a subfolder of `<folder>`.                                           |

Example:

```csv
Name;File;Target
ServerCredentials;Other/Resources/SensitiveData/ServerCredentials.bin;Other/Resources/SensitiveData/ServerCredentials
```

Lines starting with `#` are treated as comments.

## Usage

### Create a new container

1. Add the container to `.ScriptCollection/EncryptedFolders.csv`.
2. Create the encrypted empty container:

   ```cmd
   scinitencryptedcontainerinrepo -n ServerCredentials -p MyPassword
   ```

3. Commit the definition-file and the container-file.

### Change the content of a container

1. Decrypt the container:

   ```cmd
   scdecryptinrepo -n ServerCredentials -p MyPassword
   ```

   The target-folder now contains the decrypted files and folders. In a git-repository it is git-ignored.
2. Add, change or remove files and folders in the target-folder.
3. Encrypt the container again:

   ```cmd
   scencryptinrepo -n ServerCredentials -p MyPassword
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
- Links (symbolic links, hardlinks, junctions) in the target-folder are not supported. `scencryptinrepo` fails if it finds one.
- File-attributes and timestamps of the files are not stored in the container. Empty folders are stored.

## Security

- Encryption: AES-256-GCM. The key is derived from the password using scrypt with a random salt. Every write of a container-file uses a new salt and a new nonce.
- The container-file is authenticated, so manipulations of the container-file are detected while decrypting.
- The password is passed as commandline-argument, so it can be visible in the history of the shell and in the process-list of the operating-system. Consider this when using the commands on shared systems.
- The target-folder contains the sensitive data unencrypted while it is decrypted. Run `scencryptinrepo` as soon as you do not need the decrypted data anymore.
- Use a strong password. The security of the container-file in the repository depends completely on the password.
