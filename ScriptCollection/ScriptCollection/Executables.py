import base64
import os
import re
import subprocess
import fnmatch
import argparse
import time
import traceback
import shutil
import keyboard
from .ScriptCollectionCore import ScriptCollectionCore
from .GeneralUtilities import GeneralUtilities, VersionEcholon
from .SCLog import LogLevel, SCLog
from .TFCPS.TFCPS_CodeUnit_BuildCodeUnits import TFCPS_CodeUnit_BuildCodeUnits
from .TFCPS.TFCPS_Tools_General import TFCPS_Tools_General
from .OCIImages.OCIImageManager import OCIImageManager

def FilenameObfuscator() -> int:
    parser = argparse.ArgumentParser(description=''''Obfuscates the names of all files in the given folder.
Caution: This script can cause harm if you pass a wrong inputfolder-argument.''')

    parser.add_argument('--printtableheadline', type=GeneralUtilities.string_to_boolean, const=True, default=True, nargs='?', help='Prints column-titles in the name-mapping-csv-file')
    parser.add_argument('--namemappingfile', default="NameMapping.csv", help='Specifies the file where the name-mapping will be written to')
    parser.add_argument('--extensions', default="exe,py,sh",
                        help='Comma-separated list of file-extensions of files where this tool should be applied. Use "*" to obfuscate all')
    parser.add_argument('--inputfolder', help='Specifies the foldere where the files are stored whose names should be obfuscated', required=True)

    args = parser.parse_args()
    ScriptCollectionCore().SCFilenameObfuscator(args.inputfolder, args.printtableheadline, args.namemappingfile, args.extensions)
    return 0


def CreateISOFileWithObfuscatedFiles() -> int:
    parser = argparse.ArgumentParser(description='''Creates an iso file with the files in the given folder and changes their names and hash-values.
This script does not process subfolders transitively.''')

    parser.add_argument('--inputfolder', help='Specifies the foldere where the files are stored which should be added to the iso-file', required=True)
    parser.add_argument('--outputfile', default="files.iso", help='Specifies the output-iso-file and its location')
    parser.add_argument('--printtableheadline', default=False, action='store_true', help='Prints column-titles in the name-mapping-csv-file')
    parser.add_argument('--createnoisofile', default=False, action='store_true', help="Create no iso file")
    parser.add_argument('--extensions', default="exe,py,sh", help='Comma-separated list of file-extensions of files where this tool should be applied. Use "*" to obfuscate all')
    args = parser.parse_args()

    ScriptCollectionCore().SCCreateISOFileWithObfuscatedFiles(args.inputfolder, args.outputfile, args.printtableheadline, not args.createnoisofile, args.extensions)
    return 0


def ChangeHashOfProgram() -> int:
    parser = argparse.ArgumentParser(description='Changes the hash-value of arbitrary files by appending data at the end of the file.')
    parser.add_argument('--inputfile', help='Specifies the script/executable-file whose hash-value should be changed', required=True)
    args = parser.parse_args()
    ScriptCollectionCore().SCChangeHashOfProgram(args.inputfile)
    return 0


def CalculateBitcoinBlockHash() -> int:
    parser = argparse.ArgumentParser(description='Calculates the Hash of the header of a bitcoin-block.')
    parser.add_argument('--version', help='Block-version', required=True)
    parser.add_argument('--previousblockhash', help='Hash-value of the previous block', required=True)
    parser.add_argument('--transactionsmerkleroot', help='Hashvalue of the merkle-root of the transactions which are contained in the block', required=True)
    parser.add_argument('--timestamp', help='Timestamp of the block', required=True)
    parser.add_argument('--target', help='difficulty', required=True)
    parser.add_argument('--nonce', help='Arbitrary 32-bit-integer-value', required=True)
    args = parser.parse_args()

    args = parser.parse_args()
    GeneralUtilities.write_message_to_stdout(ScriptCollectionCore().SCCalculateBitcoinBlockHash(args.version, args.previousblockhash,                                                                                                args.transactionsmerkleroot, args.timestamp, args.target, args.nonce))
    return 0


def Show2FAAsQRCode():

    parser = argparse.ArgumentParser(description="""Always when you use 2-factor-authentication you have the problem:
Where to backup the secret-key so that it is easy to re-setup them when you have a new phone?
Using this script is a solution. Always when you setup a 2fa you copy and store the secret in a csv-file.
It should be obviously that this csv-file must be stored encrypted!
Now if you want to move your 2fa-codes to a new phone you simply call "SCShow2FAAsQRCode 2FA.csv"
Then the qr-codes will be displayed in the console and you can scan them on your new phone.
This script does not saving the any data anywhere.

The structure of the csv-file can be viewd here:
Displayname;Website;Email-address;Secret;Period;
Amazon;Amazon.de;myemailaddress@example.com;QWERTY;30;
Google;Google.de;myemailaddress@example.com;ASDFGH;30;

Hints:
-Since the first line of the csv-file contains headlines the first line will always be ignored
-30 is the commonly used value for the period""")
    parser.add_argument('csvfile', help='File where the 2fa-codes are stored')
    args = parser.parse_args()
    ScriptCollectionCore().SCShow2FAAsQRCode(args.csvfile)
    return 0


def SearchInFiles() -> int:
    parser = argparse.ArgumentParser(description='''Searchs for the given searchstrings in the content of all files in the given folder.
This program prints all files where the given searchstring was found to the console''')

    parser.add_argument('folder', help='Folder for search')
    parser.add_argument('searchstring', help='string to look for')

    args = parser.parse_args()
    ScriptCollectionCore().SCSearchInFiles(args.folder, args.searchstring)
    return 0


def ReplaceSubstringsInFilenames() -> int:
    parser = argparse.ArgumentParser(description='Replaces certain substrings in filenames. This program requires "pip install Send2Trash" in certain cases.')

    parser.add_argument('folder', help='Folder where the files are stored which should be renamed')
    parser.add_argument('substringInFilename', help='String to be replaced')
    parser.add_argument('newSubstringInFilename', help='new string value for filename')
    parser.add_argument('conflictResolveMode', help='''Set a method how to handle cases where a file with the new filename already exits and
    the files have not the same content. Possible values are: ignore, preservenewest, merge''')

    args = parser.parse_args()

    ScriptCollectionCore().SCReplaceSubstringsInFilenames(args.folder, args.substringInFilename, args.newSubstringInFilename, args.conflictResolveMode)
    return 0


def GenerateSnkFiles() -> int:
    parser = argparse.ArgumentParser(description='Generate multiple .snk-files')
    parser.add_argument('outputfolder', help='Folder where the files are stored which should be hashed')
    parser.add_argument('--keysize', default='4096')
    parser.add_argument('--amountofkeys', default='10')

    args = parser.parse_args()
    ScriptCollectionCore().SCGenerateSnkFiles(args.outputfolder, args.keysize, args.amountofkeys)
    return 0


def OrganizeLinesInFile() -> int:
    parser = argparse.ArgumentParser(description='Processes the lines of a file with the given commands')

    parser.add_argument('file', help='File which should be transformed')
    parser.add_argument('--encoding', default="utf-8", help='Encoding for the file which should be transformed')
    parser.add_argument("--sort", help="Sort lines", action='store_true')
    parser.add_argument("--remove_duplicated_lines", help="Remove duplicate lines", action='store_true')
    parser.add_argument("--ignore_first_line", help="Ignores the first line in the file", action='store_true')
    parser.add_argument("--remove_empty_lines", help="Removes lines which are empty or contains only whitespaces", action='store_true')
    parser.add_argument('--ignored_start_character', default="", help='Characters which should not be considered at the begin of a line')

    args = parser.parse_args()
    ScriptCollectionCore().sc_organize_lines_in_file(args.file, args.encoding, args.sort, args.remove_duplicated_lines, args.ignore_first_line, args.remove_empty_lines, list(args.ignored_start_character))


def CreateHashOfAllFiles() -> int:
    parser = argparse.ArgumentParser(description='Calculates the SHA-256-value of all files in the given folder and stores the hash-value in a file next to the hashed file.')
    parser.add_argument('folder', help='Folder where the files are stored which should be hashed')
    args = parser.parse_args()
    ScriptCollectionCore().SCCreateHashOfAllFiles(args.folder)
    return 0


def CreateSimpleMergeWithoutRelease() -> int:
    parser = argparse.ArgumentParser(description='TODO')
    parser.add_argument('repository',  help='TODO')
    parser.add_argument('sourcebranch', default="stable", help='TODO')
    parser.add_argument('targetbranch', default="master",  help='TODO')
    parser.add_argument('remotename', default=None, help='TODO')
    parser.add_argument('--remove-sourcebranch', dest='removesourcebranch', action='store_true', help='TODO')
    parser.add_argument('--no-remove-sourcebranch', dest='removesourcebranch', action='store_false', help='TODO')
    parser.set_defaults(removesourcebranch=False)
    args = parser.parse_args()
    ScriptCollectionCore().SCCreateSimpleMergeWithoutRelease(args.repository, args.sourcebranch, args.targetbranch, args.remotename, args.removesourcebranch)
    return 0


def CreateEmptyFileWithSpecificSize() -> int:
    parser = argparse.ArgumentParser(description='Creates a file with a specific size')
    parser.add_argument('name', help='Specifies the name of the created file')
    parser.add_argument('size', help='Specifies the size of the created file')
    args = parser.parse_args()
    return ScriptCollectionCore().SCCreateEmptyFileWithSpecificSize(args.name, args.size)


def ShowMissingFiles() -> int:
    parser = argparse.ArgumentParser(description='Shows all files which are in folderA but not in folder B. This program does not do any content-comparisons.')
    parser.add_argument('folderA')
    parser.add_argument('folderB')
    args = parser.parse_args()
    ScriptCollectionCore().show_missing_files(args.folderA, args.folderB)
    return 0


def ExtractPDFPages() -> int:
    parser = argparse.ArgumentParser(description='Extract pages from PDF-file')
    parser.add_argument('file', help='Input file')
    parser.add_argument('frompage', help='First page')
    parser.add_argument('topage', help='Last page')
    parser.add_argument('outputfile', help='File for the resulting PDF-document')
    args = parser.parse_args()
    ScriptCollectionCore().extract_pdf_pages(args.file, int(args.frompage), int(args.topage), args.outputfile)
    return 0


def MergePDFs() -> int:
    parser = argparse.ArgumentParser(description='Merges PDF-files')
    parser.add_argument('files', help='Comma-separated filenames')
    parser.add_argument('outputfile', help='File for the resulting PDF-document')
    args = parser.parse_args()
    ScriptCollectionCore().merge_pdf_files(args.files.split(','), args.outputfile)
    return 0




def KeyboardDiagnosis() -> None:
    """Caution: This function does usually never terminate"""
    keyboard.hook(__keyhook)
    while True:
        time.sleep(10)


def __keyhook(self, event) -> None:
    GeneralUtilities.write_message_to_stdout(str(event.name)+" "+event.event_type)


def GenerateThumbnail() -> int:
    parser = argparse.ArgumentParser(description='Generate thumpnails for video-files')
    parser.add_argument('file', help='Input-videofile for thumbnail-generation')
    parser.add_argument('framerate', help='', default="16")
    args = parser.parse_args()
    try:
        ScriptCollectionCore().generate_thumbnail(args.file, args.framerate)
        return 0
    except Exception as exception:
        GeneralUtilities.write_exception_to_stderr_with_traceback(exception, traceback)
        return 1


def ObfuscateFilesFolder() -> int:
    parser = argparse.ArgumentParser(description='''Changes the hash-value of the files in the given folder and renames them to obfuscated names.
This script does not process subfolders transitively.
Caution: This script can cause harm if you pass a wrong inputfolder-argument.''')

    parser.add_argument('--printtableheadline', type=GeneralUtilities.string_to_boolean, const=True,  default=True, nargs='?', help='Prints column-titles in the name-mapping-csv-file')
    parser.add_argument('--namemappingfile', default="NameMapping.csv", help='Specifies the file where the name-mapping will be written to')
    parser.add_argument('--extensions', default="exe,py,sh", help='Comma-separated list of file-extensions of files where this tool should be applied. Use "*" to obfuscate all')
    parser.add_argument('--inputfolder', help='Specifies the folder where the files are stored whose names should be obfuscated', required=True)

    args = parser.parse_args()
    ScriptCollectionCore().SCObfuscateFilesFolder(args.inputfolder, args.printtableheadline, args.namemappingfile, args.extensions)
    return 0


def HealthCheck() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', required=True)
    args = parser.parse_args()
    return ScriptCollectionCore().SCHealthcheck(args.file)


def BuildCodeUnits() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument('-r','--repositoryfolder', required=False, default=".")
    verbosity_values = ", ".join(f"{lvl.value}={lvl.name}" for lvl in LogLevel)
    parser.add_argument('-v', '--verbosity', required=False, default=3, help=f"Sets the loglevel. Possible values: {verbosity_values}")
    parser.add_argument('-e','--targetenvironment', required=False, default="QualityCheck")
    parser.add_argument('-a','--additionalargumentsfile', required=False, default=None)
    parser.add_argument("-c",'--nocache', required=False, default=False, action='store_true')
    parser.add_argument('-p','--ispremerge', required=False, default=False, action='store_true')
    parser.add_argument('-u','--assertnonewchanges', required=False, default=False, action='store_true')

    args = parser.parse_args()
    
    verbosity=LogLevel(int(args.verbosity))

    repo:str=GeneralUtilities.resolve_relative_path(args.repositoryfolder,os.getcwd())

    t:TFCPS_CodeUnit_BuildCodeUnits=TFCPS_CodeUnit_BuildCodeUnits(repo,verbosity,args.targetenvironment,args.additionalargumentsfile,not args.nocache,args.ispremerge,args.assertnonewchanges) 
    t.build_codeunits()
    return 0


def BuildCodeUnitsC() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('-r','--repositoryfolder', required=False, default=".")
    verbosity_values = ", ".join(f"{lvl.value}={lvl.name}" for lvl in LogLevel)
    parser.add_argument('-v', '--verbosity', required=False, default=3, help=f"Sets the loglevel. Possible values: {verbosity_values}")
    parser.add_argument('--targetenvironment', required=False, default="QualityCheck")
    parser.add_argument('--additionalargumentsfile', required=False, default=None)
    parser.add_argument("-c",'--nocache', required=False, default=False, action='store_true')
    parser.add_argument('-p','--ispremerge', required=False, default=False, action='store_true')
    parser.add_argument('--image', required=False, default="scbuilder:latest")
    parser.add_argument('-u','--assertnonewchanges', required=False, default=False, action='store_true')
    args = parser.parse_args()
    GeneralUtilities.reconfigure_standard_input_and_outputs()
    repo:str=GeneralUtilities.resolve_relative_path(args.repositoryfolder,os.getcwd())
    verbosity=LogLevel(int(args.verbosity))
    t:TFCPS_CodeUnit_BuildCodeUnits=TFCPS_CodeUnit_BuildCodeUnits(repo,verbosity,args.targetenvironment,args.additionalargumentsfile,not args.nocache,args.ispremerge,args.assertnonewchanges) 
    t.build_codeunits_in_container()
    return 0

def UpdateDependencies() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('-r','--repositoryfolder', required=False, default=".")
    verbosity_values = ", ".join(f"{lvl.value}={lvl.name}" for lvl in LogLevel)
    parser.add_argument('-v', '--verbosity', required=False, default=3, help=f"Sets the loglevel. Possible values: {verbosity_values}")
    parser.add_argument('--targetenvironment', required=False, default="QualityCheck")
    parser.add_argument('--additionalargumentsfile', required=False, default=None)
    parser.add_argument("-c",'--nocache', required=False, default=False, action='store_true')
    args = parser.parse_args()
    verbosity=LogLevel(int(args.verbosity))
    repo:str=GeneralUtilities.resolve_relative_path(args.repositoryfolder,os.getcwd())
    t:TFCPS_CodeUnit_BuildCodeUnits=TFCPS_CodeUnit_BuildCodeUnits(repo,verbosity,args.targetenvironment,args.additionalargumentsfile,not args.nocache,False,False) 
    t.update_dependencies()
    return 0


def GenerateCertificateAuthority() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--name', required=True)
    parser.add_argument('--subj_c', required=True)
    parser.add_argument('--subj_st', required=True)
    parser.add_argument('--subj_l', required=True)
    parser.add_argument('--subj_o', required=True)
    parser.add_argument('--subj_ou', required=True)
    parser.add_argument('--days_until_expire', required=False, default=None, type=int)
    parser.add_argument('--password', required=False, default=None)
    args = parser.parse_args()
    ScriptCollectionCore().generate_certificate_authority(os.getcwd(), args.name, args.subj_c, args.subj_st, args.subj_l, args.subj_o, args.subj_ou, args.days_until_expire, args.password)
    return 0


def GenerateCertificate() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--filename', required=True)
    parser.add_argument('--domain', required=True)
    parser.add_argument('--subj_c', required=True)
    parser.add_argument('--subj_st', required=True)
    parser.add_argument('--subj_l', required=True)
    parser.add_argument('--subj_o', required=True)
    parser.add_argument('--subj_ou', required=True)
    parser.add_argument('--days_until_expire', required=False, default=None, type=int)
    parser.add_argument('--password', required=False, default=None)
    args = parser.parse_args()
    ScriptCollectionCore().generate_certificate(os.getcwd(), args.domain, args.filename, args.subj_c, args.subj_st, args.subj_l, args.subj_o, args.subj_ou, args.days_until_expire, args.password)
    return 0


def GenerateCertificateSignRequest() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--filename', required=True)
    parser.add_argument('--domain', required=True)
    parser.add_argument('--subj_c', required=True)
    parser.add_argument('--subj_st', required=True)
    parser.add_argument('--subj_l', required=True)
    parser.add_argument('--subj_o', required=True)
    parser.add_argument('--subj_ou', required=True)
    args = parser.parse_args()
    ScriptCollectionCore().generate_certificate_sign_request(os.getcwd(), args.domain, args.filename, args.subj_c, args.subj_st, args.subj_l, args.subj_o, args.sub_ou)
    return 0


def SignCertificate() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--cafolder', required=True)
    parser.add_argument('--caname', required=True)
    parser.add_argument('--targetcertificate', required=True)
    parser.add_argument('--filename', required=True)
    parser.add_argument('--days_until_expire', required=False, default=None, type=int)
    args = parser.parse_args()
    ScriptCollectionCore().sign_certificate(os.getcwd(), args.cafolder, args.caname, args.targetcertificate, args.filename, args.args.days_until_expire)
    return 0


def ChangeFileExtensions() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--folder', required=True)
    parser.add_argument('-s', '--source_extension', required=True)
    parser.add_argument('-t', '--target_extension', required=True)
    parser.add_argument('-r', '--recursive', required=False, default=False, type=GeneralUtilities.string_to_boolean)
    parser.add_argument('-i', '--ignore_case', required=False, default=True, type=GeneralUtilities.string_to_boolean)
    args = parser.parse_args()
    ScriptCollectionCore().change_file_extensions(args.folder, args.source_extension, args.target_extension, args.recursive, args.ignore_case)
    return 0


def GenerateARC42ReferenceTemplate() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--folder', required=False)
    parser.add_argument('-p', '--productname', required=False)
    parser.add_argument('-s', '--subfolder', required=False)
    args = parser.parse_args()

    folder = args.folder
    if folder is None:
        folder = os.getcwd()
    ScriptCollectionCore().generate_arc42_reference_template(folder, args.productname, args.subfolder)
    return 0


def CreateChangelogEntry() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--repositorypath', required=False, default=".")
    parser.add_argument('-m', '--message', required=False, default=None)
    parser.add_argument('-c', '--commit', action='store_true', required=False, default=False)
    parser.add_argument('-f', '--force', action='store_true', required=False, default=False)
    args = parser.parse_args()

    folder: str = None
    if os.path.isabs(args.repositorypath):
        folder = args.repositorypath
    else:
        folder = GeneralUtilities.resolve_relative_path(args.repositorypath, os.getcwd())
    t=TFCPS_Tools_General(ScriptCollectionCore())
    t.create_changelog_entry(folder, args.message, args.commit, args.force)
    return 0


def FileExists() -> int:
    parser = argparse.ArgumentParser(description="This function returns 0 if the given file exists. Otherwise this function returns 2. If an error occurrs the exitcode is 1.")
    parser.add_argument('-p', '--path', required=True)
    args = parser.parse_args()
    if os.path.isfile(args.path):
        return 0
    else:
        return 2


def FolderExists() -> int:
    parser = argparse.ArgumentParser(description="This function returns 0 if the given folder exists. Otherwise this function returns 2. If an error occurrs the exitcode is 1.")
    parser.add_argument('-p', '--path', required=True)
    args = parser.parse_args()
    if os.path.isdir(args.path):
        return 0
    else:
        return 2


def PrintFileContent() -> int:
    parser = argparse.ArgumentParser(description="This function prints the content of a file. With --excludedfolder you can forbid reading files inside certain folders even though reading is allowed in general.")
    parser.add_argument('-p', '--path', required=True)
    parser.add_argument('-e', '--encoding', required=False, default="utf-8")
    parser.add_argument('-b', '--basefolder', required=False, default=".", help="Base-folder the excludedfolder-entries are relative to. Defaults to the current working-directory.")
    parser.add_argument('-x', '--excludedfolder', action='append', default=[], help="A folder (relative to basefolder) whose files must not be read. Can be specified multiple times. Example: --excludedfolder .git --excludedfolder .claude --excludedfolder Other/Secrets")
    parser.add_argument('-f', '--fromline', required=False, default=None, type=int, help="1-based line-number to start printing from (inclusive). Defaults to the first line.")
    parser.add_argument('-t', '--toline', required=False, default=None, type=int, help="1-based line-number to stop printing at (inclusive). Defaults to the last line.")
    args = parser.parse_args()
    file = args.path
    encoding = args.encoding
    sc = ScriptCollectionCore()
    if not sc.path_is_allowed_within_base_folder(file, args.basefolder, args.excludedfolder):
        GeneralUtilities.write_message_to_stderr(f"Reading '{file}' is not allowed because it is not located inside the base-folder or it is located inside an excluded folder.")
        return 1
    GeneralUtilities.write_message_to_stdout(sc.get_file_content(file, encoding, args.fromline, args.toline))
    return 0


def CreateFile() -> int:
    parser = argparse.ArgumentParser(description="This function creates an empty file.")
    parser.add_argument('-p', '--path', required=True)
    parser.add_argument('-e', '--errorwhenexists', action='store_true', required=False, default=False)
    parser.add_argument('-c', '--createnecessaryfolder', action='store_true', required=False, default=False)
    args = parser.parse_args()
    sc = ScriptCollectionCore()
    sc.create_file(args.path, args.errorwhenexists, args.createnecessaryfolder)
    return 0


def CreateFolder() -> int:
    parser = argparse.ArgumentParser(description="This function creates an empty folder.")
    parser.add_argument('-p', '--path', required=True)
    parser.add_argument('-e', '--errorwhenexists', action='store_true', required=False, default=False)
    parser.add_argument('-c', '--createnecessaryfolder', action='store_true', required=False, default=False)
    args = parser.parse_args()
    sc = ScriptCollectionCore()
    sc.create_folder(args.path, args.errorwhenexists, args.createnecessaryfolder)
    return 0


def CreateSkill() -> int:
    parser = argparse.ArgumentParser(description="Creates a skill ('skills/<name>/' with a lightweight 'skill.json' and a lazy-loaded 'detail.md'). The skill is created in the given repository-folder, or - if none is given - in the current working-directory when that is a git-repository, otherwise in the user's ScriptCollection-configuration-folder.")
    parser.add_argument('-n', '--name', required=True, help='Name of the skill.')
    parser.add_argument('-d', '--description', required=True, help='Description of the skill.')
    parser.add_argument('-r', '--repositoryfolder', required=False, default=None, help='Repository-folder to create the skill in. Defaults to the current git-repository or the user-folder.')
    parser.add_argument('-t', '--tags', required=False, default=None, help='Comma-separated list of tags.')
    parser.add_argument('-p', '--priority', required=False, default=None, help='Priority of the skill (e.g. "high", "medium", "low").')
    parser.add_argument('-g', '--triggers', required=False, default=None, help='Comma-separated list of triggers.')
    args = parser.parse_args()
    tags = [tag.strip() for tag in args.tags.split(",") if tag.strip() != GeneralUtilities.empty_string] if args.tags is not None else []
    triggers = [trigger.strip() for trigger in args.triggers.split(",") if trigger.strip() != GeneralUtilities.empty_string] if args.triggers is not None else []
    skill_folder = ScriptCollectionCore().create_skill(args.name, args.description, args.repositoryfolder, tags, args.priority, triggers)
    GeneralUtilities.write_message_to_stdout(skill_folder)
    return 0


def AppendLineToFile() -> int:
    parser = argparse.ArgumentParser(description="Appends a line to a file. By default a leading newline is inserted before the line and a trailing newline after it (POSIX-line-ended files).")
    parser.add_argument('-p', '--path', required=True)
    parser.add_argument('-l', '--line', required=True, help='Line content to append (without trailing newline).')
    parser.add_argument('-e', '--encoding', default="utf-8")
    parser.add_argument('--skip-leading-newline-if-file-already-ends-with-newline', action='store_true', default=False, help='If the file already ends with a newline character, do not insert another leading newline (avoids an empty line).')
    parser.add_argument('--no-trailing-newline', action='store_true', default=False, help='Do not append a trailing newline character after the line.')
    args = parser.parse_args()
    if not os.path.isfile(args.path):
        GeneralUtilities.write_message_to_stderr(f"File '{args.path}' does not exist.")
        return 1
    existing = GeneralUtilities.read_text_from_file(args.path, args.encoding)
    if not existing:
        prefix = ""
    elif existing.endswith("\n") and args.skip_leading_newline_if_file_already_ends_with_newline:
        prefix = ""
    else:
        prefix = "\n"
    suffix = "" if args.no_trailing_newline else "\n"
    GeneralUtilities.write_text_to_file(args.path, existing + prefix + args.line + suffix, args.encoding)
    return 0


def RegexReplaceInFile() -> int:
    parser = argparse.ArgumentParser(description="Performs a regex-based replacement in a file and writes the result back. Supports backreferences (e.g. \\1) in the replacement string.")
    parser.add_argument('-p', '--path', required=True)
    parser.add_argument('-r', '--pattern', required=True, help='Regular expression to match.')
    parser.add_argument('-w', '--replacement', required=True, help='Replacement string (supports backreferences such as \\1).')
    parser.add_argument('-e', '--encoding', default="utf-8")
    parser.add_argument('-i', '--case-insensitive', action='store_true', default=False)
    parser.add_argument('-m', '--multiline', action='store_true', default=False, help='Enable re.MULTILINE (^ and $ match at line boundaries).')
    parser.add_argument('-d', '--dotall', action='store_true', default=False, help='Enable re.DOTALL (. matches newlines).')
    args = parser.parse_args()
    if not os.path.isfile(args.path):
        GeneralUtilities.write_message_to_stderr(f"File '{args.path}' does not exist.")
        return 1
    flags = 0
    if args.case_insensitive:
        flags |= re.IGNORECASE
    if args.multiline:
        flags |= re.MULTILINE
    if args.dotall:
        flags |= re.DOTALL
    content = GeneralUtilities.read_text_from_file(args.path, args.encoding)
    new_content = re.sub(args.pattern, args.replacement, content, flags=flags)
    GeneralUtilities.write_text_to_file(args.path, new_content, args.encoding)
    return 0


def NormalizeLineEndings() -> int:
    parser = argparse.ArgumentParser(description="Normalizes all physical line-endings of a file to LF (replaces CRLF and lone CR by LF).")
    parser.add_argument('-p', '--path', required=True)
    args = parser.parse_args()
    if not os.path.isfile(args.path):
        GeneralUtilities.write_message_to_stderr(f"File '{args.path}' does not exist.")
        return 1
    ScriptCollectionCore().normalize_line_endings(args.path)
    return 0


def PrintFileSize() -> int:
    parser = argparse.ArgumentParser(description="This function prints the size of a file")
    parser.add_argument('-p', '--path', required=True)
    args = parser.parse_args()
    file = args.path
    if os.path.isfile(file):
        size = os.path.getsize(file)
        GeneralUtilities.write_message_to_stdout(str(size))
        return 0
    else:
        GeneralUtilities.write_exception_to_stderr(f"File '{file}' does not exist.")
        return 1


def FileContainsContent() -> int:
    parser = argparse.ArgumentParser(description="Returns exit-code 0 if the file contains the given content, 2 if not. 1 on error (e.g. file does not exist).")
    parser.add_argument('-p', '--path', required=True)
    parser.add_argument('-c', '--content', required=True, help='Substring (or regex if --regex is set) to search for.')
    parser.add_argument('-r', '--regex', action='store_true', default=False, help='Treat --content as a regular expression.')
    parser.add_argument('-i', '--case-insensitive', action='store_true', default=False, help='Match case-insensitively.')
    parser.add_argument('-e', '--encoding', default="utf-8")
    args = parser.parse_args()
    if not os.path.isfile(args.path):
        GeneralUtilities.write_message_to_stderr(f"File '{args.path}' does not exist.")
        return 1
    sc = ScriptCollectionCore()
    found = sc.file_contains_content(args.path, args.content, args.regex, not args.case_insensitive, args.encoding)
    return 0 if found else 2


def RemoveFile() -> int:
    parser = argparse.ArgumentParser(description="This function removes a file.")
    parser.add_argument('-p', '--path', required=True)
    parser.add_argument('-e', '--errorwhennotexists', action='store_true', required=False, default=False)
    args = parser.parse_args()
    file = args.path
    errorwhennotexists = args.errorwhennotexists
    if os.path.isfile(file):
        GeneralUtilities.ensure_file_does_not_exist(file)
    else:
        if errorwhennotexists:
            GeneralUtilities.write_exception_to_stderr(f"File '{file}' does not exist.")
            return 1
    return 0


def RemoveFolder() -> int:
    parser = argparse.ArgumentParser(description="This function removes a folder.")
    parser.add_argument('-p', '--path', required=True)
    parser.add_argument('-e', '--errorwhennotexists', action='store_true', required=False, default=False)
    args = parser.parse_args()
    folder = args.path
    errorwhennotexists = args.errorwhennotexists
    if os.path.isdir(folder):
        GeneralUtilities.ensure_directory_does_not_exist(folder)
    else:
        if errorwhennotexists:
            GeneralUtilities.write_exception_to_stderr(f"Folder '{folder}' does not exist.")
            return 1
    return 0


def Rename() -> int:
    parser = argparse.ArgumentParser(description="This function renames a file or folder.")
    parser.add_argument('-s', '--source', required=True)
    parser.add_argument('-t', '--target', required=True)
    args = parser.parse_args()
    os.rename(args.source, args.target)
    return 0


def Copy() -> int:
    parser = argparse.ArgumentParser(description="This function copies a file or folder.")
    parser.add_argument('-s', '--source', required=True)
    parser.add_argument('-t', '--target', required=True)
    args = parser.parse_args()

    if os.path.isfile(args.target) or os.path.isdir(args.target):
        raise ValueError(f"Can not copy to '{args.target}' because the target already exists.")

    source = args.source
    if not os.path.isabs(source):
        source = GeneralUtilities.resolve_relative_path(source, os.getcwd())
    target = args.target
    if not os.path.isabs(target):
        target = GeneralUtilities.resolve_relative_path(target, os.getcwd())

    if os.path.isfile(source):
        shutil.copyfile(source, target)
    elif os.path.isdir(source):
        GeneralUtilities.ensure_directory_exists(target)
        GeneralUtilities.copy_content_of_folder(source, target)
    else:
        raise ValueError(f"'{source}' can not be copied because the path does not exist.")
    return 0

def GetSize() -> int:
    parser = argparse.ArgumentParser(description="This function prints the size of a file.")
    parser.add_argument('-p', '--path', required=True)
    args = parser.parse_args()

    path = GeneralUtilities.resolve_relative_path(args.path, os.getcwd())

    if not os.path.isfile(path):
        raise ValueError(f"File '{path}' does not exist.")

    GeneralUtilities.write_message_to_stdout(str(os.path.getsize(path)))
    return 0

def PrintOSName() -> int:
    if GeneralUtilities.current_system_is_windows():
        GeneralUtilities.write_message_to_stdout("Windows")
    elif GeneralUtilities.current_system_is_linux():
        GeneralUtilities.write_message_to_stdout("Linux")
    # TODO consider Mac, Unix, etc. too
    else:
        GeneralUtilities.write_message_to_stderr("Unknown OS.")
        return 1
    return 0


def PrintCurrecntWorkingDirectory() -> int:
    GeneralUtilities.write_message_to_stdout(os.getcwd())
    return 0


def ListFolderContent() -> int:
    parser = argparse.ArgumentParser(description="This function lists folder-content.")
    parser.add_argument('-p', '--path', required=True)
    parser.add_argument('-f', '--excludefiles', action='store_true', required=False, default=False)
    parser.add_argument('-d', '--excludedirectories', action='store_true', required=False, default=False)
    parser.add_argument('-n', '--printonlynamewithoutpath', action='store_true', required=False, default=False)
    parser.add_argument('-t', '--transitive', action='store_true', required=False, default=False, help='Recurse into subfolders.')
    filter_group = parser.add_mutually_exclusive_group()
    filter_group.add_argument('--extension', help='Comma-separated list of file extensions (without dot) to include, e.g. "py,md".')
    filter_group.add_argument('--glob', help='Glob pattern matched against entry basename, e.g. "*.py" or "test_*".')
    filter_group.add_argument('--regex', help='Regex pattern matched against entry basename.')
    args = parser.parse_args()
    folder = args.path
    if not os.path.isabs(folder):
        folder = GeneralUtilities.resolve_relative_path(folder, os.getcwd())
    if not os.path.isdir(folder):
        GeneralUtilities.write_message_to_stderr(f"Folder '{folder}' does not exist.")
        return 1
    if args.excludefiles and args.excludedirectories:
        GeneralUtilities.write_message_to_stderr("Nothing to list: both files and folders are excluded.")
        return 1
    extensions: set[str] = None
    if args.extension is not None:
        extensions = {e.strip().lower().lstrip(".") for e in args.extension.split(",") if e.strip()}

    def matches_filter(entry_path: str) -> bool:
        basename = os.path.basename(entry_path)
        if extensions is not None:
            ext = os.path.splitext(basename)[1].lstrip(".").lower()
            return ext in extensions
        if args.glob is not None:
            return fnmatch.fnmatch(basename, args.glob)
        if args.regex is not None:
            return re.search(args.regex, basename) is not None
        return True

    entries: list[str] = []
    if args.transitive:
        for current_root, subfolders, files in os.walk(folder):
            if not args.excludedirectories:
                for subfolder in subfolders:
                    entries.append(os.path.join(current_root, subfolder))
            if not args.excludefiles:
                for file in files:
                    entries.append(os.path.join(current_root, file))
    else:
        if not args.excludefiles:
            entries = entries + GeneralUtilities.get_direct_files_of_folder(folder)
        if not args.excludedirectories:
            entries = entries + GeneralUtilities.get_direct_folders_of_folder(folder)

    for entry in entries:
        if not matches_filter(entry):
            continue
        content_to_print = os.path.basename(entry) if args.printonlynamewithoutpath else entry
        GeneralUtilities.write_message_to_stdout(content_to_print)
    return 0


def ForEach() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Iterates the entries of a folder and runs a command for each one. The placeholder '{path}' "
            "in the command template is replaced with the entry's absolute path before execution. "
            "By default only direct child entries are processed; with --transitive the whole subtree is walked. "
            "By default only files are processed; use --include-folders to also process folders.\n"
            "\n"
            "Example: scforeach -f . -c \"git -C \\\"{path}\\\" status -s\" --include-folders --skip-files"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('-f', '--folder', required=True, help='Folder whose entries should be iterated.')
    parser.add_argument('-c', '--command', required=True, help='Command template. Use "{path}" as placeholder for the entry path.')
    parser.add_argument('-t', '--transitive', action='store_true', default=False, help='Recurse into subfolders.')
    parser.add_argument('--include-folders', action='store_true', default=False, help='Also process folder entries (default: only files).')
    parser.add_argument('--skip-files', action='store_true', default=False, help='Skip file entries (useful in combination with --include-folders).')
    parser.add_argument('--continue-on-error', action='store_true', default=False, help='Continue with the next entry even if a command returns a non-zero exit-code.')
    args = parser.parse_args()
    if not os.path.isdir(args.folder):
        GeneralUtilities.write_message_to_stderr(f"Folder '{args.folder}' does not exist.")
        return 1
    process_files = not args.skip_files
    process_folders = args.include_folders
    if not process_files and not process_folders:
        GeneralUtilities.write_message_to_stderr("Nothing to do: both files and folders are excluded.")
        return 1
    entries: list[str] = []
    if args.transitive:
        for current_root, subfolders, files in os.walk(args.folder):
            if process_folders:
                for subfolder in subfolders:
                    entries.append(os.path.join(current_root, subfolder))
            if process_files:
                for file in files:
                    entries.append(os.path.join(current_root, file))
    else:
        for entry_name in os.listdir(args.folder):
            entry_path = os.path.join(args.folder, entry_name)
            if os.path.isfile(entry_path) and process_files:
                entries.append(entry_path)
            elif os.path.isdir(entry_path) and process_folders:
                entries.append(entry_path)
    aggregate_exit_code = 0
    for entry_path in entries:
        absolute_entry_path = os.path.abspath(entry_path)
        rendered_command = args.command.replace("{path}", absolute_entry_path)
        completed = subprocess.run(rendered_command, shell=True, capture_output=True, text=True, check=False)
        if completed.stdout:
            GeneralUtilities.write_message_to_stdout(completed.stdout.rstrip("\n"))
        if completed.stderr:
            GeneralUtilities.write_message_to_stderr(completed.stderr.rstrip("\n"))
        if completed.returncode != 0:
            aggregate_exit_code = completed.returncode
            if not args.continue_on_error:
                return aggregate_exit_code
    return aggregate_exit_code


def NpmI() -> int:
    parser = argparse.ArgumentParser(description="Does \"npm clean install\".")
    parser.add_argument('-d', '--directory', required=False, default=".")
    parser.add_argument('-f', '--force', action='store_true', required=False, default=False)
    parser.add_argument('-v', '--verbose', action='store_true', required=False, default=False)
    parser.add_argument('-c', '--nocache', action='store_true', required=False, default=False)
    args = parser.parse_args()
    if os.path.isabs(args.directory):
        folder = args.directory
    else: 
        folder = GeneralUtilities.resolve_relative_path(args.directory, os.getcwd())
    t = TFCPS_Tools_General(ScriptCollectionCore())
    t.do_npm_install(folder, args.force,not args.nocache)
    return 0


def CurrentUserHasElevatedPrivileges() -> int:
    parser = argparse.ArgumentParser(description="Returns 1 if the current user has elevated privileges. Otherwise this function returns 0.")
    parser.parse_args()
    if GeneralUtilities.current_user_has_elevated_privileges():
        return 1
    else:
        return 0


def Espoc() -> int:
    parser = argparse.ArgumentParser(description="Espoc (appreviation for 'exit started programs on close') is a tool to ensure the started processes of your program will also get terminated when the execution of your program is finished.")
    parser.add_argument('-p', '--processid', required=True)
    parser.add_argument('-f', '--file', required=True, help='Specifies the file where the process-ids of the started processes are stored (line by line). This file will be deleted when all started processes are terminated.')
    parser.add_argument('-l', '--logfile', required=False,default=None)
    args = parser.parse_args()
    process_id = int(args.processid)
    process_list_file: str = args.file
    log:SCLog=None
    if args.logfile is None:
        log=SCLog()
    else:
        log=SCLog(args.logfile)
        log.add_overhead_to_logfile=True
    log.log(f"Start Espoc for process id {process_id} and process list file '{process_list_file}'.")
    try:
        if not os.path.isabs(process_list_file):
            process_list_file = GeneralUtilities.resolve_relative_path(process_list_file, os.getcwd())
        GeneralUtilities.assert_condition(GeneralUtilities.process_is_running_by_id(process_id), f"Process with id {process_id} is not running.")
        while GeneralUtilities.process_is_running_by_id(process_id):
            time.sleep(1)
        log.log(f"Process with id {process_id} is not running anymore. Start terminating remaining processes.")
        if os.path.exists(process_list_file):
            for line in GeneralUtilities.read_nonempty_lines_from_file(process_list_file):
                current_process_id = int(line.strip())
                try:
                    log.log(f"Terminate process {current_process_id}...")
                    GeneralUtilities.kill_process(current_process_id, True)
                except Exception as exception:
                    log.log_exception(f"Error while terminating process with id {current_process_id}.",exception)
            log.log("All started processes terminated.")
            GeneralUtilities.ensure_file_does_not_exist(process_list_file)
        else:
            log.log(f"File '{process_list_file}' does not exist. No processes to terminate.")
        return 0
    except Exception as exception:
        log.log_exception("Fatal error in Espoc.", exception)
        return 1


def ConvertGitRepositoryToBareRepository() -> int:
    parser = argparse.ArgumentParser(description="Converts a local git-repository to a bare repository.")
    parser.add_argument('-f', '--folder', required=True, help='Git-repository-folder which should be converted.')
    args = parser.parse_args()
    sc = ScriptCollectionCore()
    sc.convert_git_repository_to_bare_repository(args.folder)
    return 0


def OCRAnalysisOfFolder() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--serviceaddress', required=False, default=None)
    parser.add_argument('-e', '--extensions', required=False, default="pdf,docx,jpg,png,xlsx")
    parser.add_argument('-l', '--languages', required=False, default="eng")
    parser.add_argument('-f', '--folder', required=False, default=None)
    args = parser.parse_args()
    sc = ScriptCollectionCore()
    if args.folder is None:
        args.folder = os.getcwd()
    languages=args.languages.split(",")
    extensions=args.extensions.split(",")
    sc.ocr_analysis_of_folder(args.folder, args.serviceaddress, extensions, languages,args.folder,[])
    return 0


def OCRAnalysisOfFile() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--serviceaddress', required=False, default=None)
    parser.add_argument('-l', '--languages', required=False, default="eng")
    parser.add_argument('-f', '--file', required=True)
    args = parser.parse_args()
    sc = ScriptCollectionCore()
    languages=args.languages.split(",")
    sc.ocr_analysis_of_file(args.file, args.serviceaddress, languages,".")
    return 0


def OCRAnalysisOfRepository() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--serviceaddress', required=False, default=None)
    parser.add_argument('-e', '--extensions', required=False, default="pdf,docx,jpg,png,xlsx")
    parser.add_argument('-l', '--languages', required=False, default="eng")
    parser.add_argument('-f', '--folder', required=False, default=None)
    args = parser.parse_args()
    sc = ScriptCollectionCore()
    if args.folder is None:
        args.folder = os.getcwd()
    languages=args.languages.split(",")
    extensions=args.extensions.split(",")
    sc.ocr_analysis_of_repository(args.folder, args.serviceaddress, extensions, languages)
    return 0


def UpdateImagesInDockerComposeFile() -> int:
    echolon_values = ", ".join(f"{e.value}={e.name}" for e in VersionEcholon)
    parser = argparse.ArgumentParser(
        description=(
            "This function updates images in a Docker Compose file.\n"
            "\n"
            "Example (default LatestPatch for everything, but override per image):\n"
            "  scupdateimagesindockercomposefile -f docker-compose.yml -e 0 "
            "-i Debian=3 -i PostgreSQL=1 -i Syft=5\n"
            "  -> Debian uses LatestVersion (3), PostgreSQL uses LatestPatchOrLatestMinor (1),\n"
            "     Syft is not updated (5=NoUpdate), all others use the default LatestPatch (0)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('-f', '--file', required=False, default="./docker-compose.yml")
    parser.add_argument('-e', '--echolon', type=int, required=False, default=None, help=f"Default version-echolon applied to all images that have no specific override. Possible values: {echolon_values}. If not set, the image-handler default is used.")
    parser.add_argument('-i', '--image-echolon', action='append', default=[], help="Per-image echolon override in the format 'imagename=echolon' (e.g. 'Debian=3'). Can be specified multiple times.")
    args = parser.parse_args()
    sc = ScriptCollectionCore()
    file = GeneralUtilities.resolve_relative_path(args.file, os.getcwd())
    default_echolon: VersionEcholon = VersionEcholon(args.echolon) if args.echolon is not None else None
    per_image_echolons: dict[str, VersionEcholon] = {}
    for item in args.image_echolon:
        if "=" not in item:
            raise ValueError(f"Invalid value for --image-echolon: '{item}'. Expected format: 'imagename=echolon'.")
        name_part, echolon_part = item.split("=", 1)
        per_image_echolons[name_part.strip()] = VersionEcholon(int(echolon_part.strip()))
    oci = OCIImageManager(sc)
    oci.update_image_in_docker_compose_file(file, default_echolon, per_image_echolons)
    return 0


def SetFileContent() -> int:
    parser = argparse.ArgumentParser(description="This function writes content into a file.")
    parser.add_argument('-p', '--path', required=True)
    parser.add_argument('-b', '--argumentisinbase64', action='store_true', required=False, default=False)
    parser.add_argument('-c', '--content', required=True)
    parser.add_argument('-e', '--encoding', required=False, default="utf-8")
    args = parser.parse_args()
    sc = ScriptCollectionCore()
    content = args.content
    if args.argumentisinbase64:
        base64_string: str = args.content
        base64_bytes = base64_string.encode('utf-8')
        original_bytes = base64.b64decode(base64_bytes)
        content = original_bytes.decode('utf-8')
    sc.set_file_content(args.path, content, args.encoding)
    return 0


def GenerateTaskfileFromWorkspacefile() -> int:
    parser = argparse.ArgumentParser(description="Generates a Taskfile.yml file from a .code-workspace file.")
    parser.add_argument('-f', '--repositoryfolder', required=True, help='Repository folder containing the .code-workspace file.')
    parser.add_argument('--appendcliargs', action='store_true', default=False, help='Append "{{.CLI_ARGS}}" to each generated task command so extra CLI-args can be forwarded.')
    args = parser.parse_args()
    repository_folder = args.repositoryfolder
    if not os.path.isabs(repository_folder):
        repository_folder = GeneralUtilities.resolve_relative_path(repository_folder, os.getcwd())
    if not os.path.isdir(repository_folder):
        GeneralUtilities.write_message_to_stderr(f"Folder '{repository_folder}' does not exist.")
        return 1
    sc = ScriptCollectionCore()
    TFCPS_Tools_General(sc).generate_tasksfile_from_workspace_file(repository_folder, args.appendcliargs)
    return 0


def UpdateTimestampInFile() -> int:
    parser = argparse.ArgumentParser(description="Update the timestamp in a comment in a file")
    parser.add_argument('-f', '--file', required=True)
    args = parser.parse_args()
    sc = ScriptCollectionCore()
    sc.update_timestamp_in_file(args.file)
    return 0


def LOC() -> int:
    sc = ScriptCollectionCore()
    default_patterns: list[str] = sc.default_excluded_patterns_for_loc
    default_patterns_joined = ",".join(default_patterns)
    parser = argparse.ArgumentParser(description=f"Counts the lines of code in a git-repository. Default patterns are: {default_patterns_joined}")
    parser.add_argument('-r', '--repository', required=True)
    parser.add_argument('-e', '--excluded_pattern', nargs='+')
    parser.add_argument('-d', '--do_not_add_default_pattern', action='store_true', default=False)
    parser.add_argument('-v', '--verbose', action='store_true', default=False)
    args = parser.parse_args()
    
    folder: str = None
    if os.path.isabs(args.repository):
        folder = args.repository
    else:
        folder = GeneralUtilities.resolve_relative_path(args.repository, os.getcwd())
    excluded_patterns: list[str] = []

    if not args.do_not_add_default_pattern:
        excluded_patterns = excluded_patterns + sc.default_excluded_patterns_for_loc
    if args.excluded_pattern is not None:
        excluded_patterns = excluded_patterns + args.excluded_pattern

    if args.verbose:
        sc.log.loglevel=LogLevel.Debug
    else:
        sc.log.loglevel=LogLevel.Information

    GeneralUtilities.write_message_to_stdout(str(sc.get_lines_of_code(folder, excluded_patterns)))
    return 0

def CreateRelease()->int:
    sc = ScriptCollectionCore()
    parser = argparse.ArgumentParser(description="Creates a release in a git-repository which uses the anion-build-platform.")
    parser.add_argument('-b', '--buildrepository', required=False, default=".")
    verbosity_values = ", ".join(f"{lvl.value}={lvl.name}" for lvl in LogLevel)
    parser.add_argument('-v', '--verbosity', required=False, default=3, help=f"Sets the loglevel. Possible values: {verbosity_values}")
    parser.add_argument('-s', '--sourcebranch', required=False, default="other/next-release")
    parser.add_argument('-u', '--updatedependencies', required=False, action='store_true', default=False)
    parser.add_argument('-l', '--lazymode', required=False, action='store_true', default=False)
    args = parser.parse_args()

    build_repo_folder: str = None
    if os.path.isabs(args.buildrepository):
        build_repo_folder = args.buildrepository
    else:
        build_repo_folder = GeneralUtilities.resolve_relative_path(args.buildrepository, os.getcwd())

    verbosity=int(args.verbosity)
    sc.log.loglevel=LogLevel(verbosity)

    scripts_folder:str=os.path.join(build_repo_folder,"Scripts","CreateRelease")
    arguments=f"CreateRelease.py --buildrepositoriesfolder {build_repo_folder} --verbosity {verbosity} --sourcebranch {args.sourcebranch}"
    if args.updatedependencies:
        arguments=arguments+" --updatedependencies"
    if args.lazymode:
        arguments=arguments+" --lazymode"
    sc.run_program(GeneralUtilities.get_python_executable(), arguments, scripts_folder,print_live_output=True)

    return 0

def CleanToolsCache()->int:
    sc=ScriptCollectionCore()
    GeneralUtilities.ensure_folder_exists_and_is_empty(sc.get_global_cache_folder())
    return 0


def DownloadCachableTools()->int:
    parser = argparse.ArgumentParser(description="Downloads all tools that are stored in the global ScriptCollection-cache (for example CycloneDX-CLI, PlantUML, MediaMTX, TruffleHog, OpenAPIGenerator and AndroidAppBundleTool). Running this - for example in a build-image - lets repeated pipeline-runs avoid rate-limits and run faster because the tools are already present.")
    parser.add_argument('-v', '--verbose', action='store_true', required=False, default=False, help="Enables verbose (debug) output.")
    parser.add_argument('-e', '--enforceupdate', action='store_true', required=False, default=False, help="Re-download the tools even if they are already present in the cache.")
    #TODO for each tool which will be installed allow to specify a specific version number
    args = parser.parse_args()
    sc: ScriptCollectionCore = ScriptCollectionCore()
    TFCPS_Tools_General(sc).download_all_cachable_tools(args.enforceupdate, args.verbose)
    return 0


def EnsureDockerNetworkIsAvailable()->int:
    sc = ScriptCollectionCore()
    parser = argparse.ArgumentParser()
    parser.add_argument('-n', '--networkname', required=True)
    args = parser.parse_args()

    sc:ScriptCollectionCore=ScriptCollectionCore()
    sc.ensure_docker_network_is_available(args.networkname)
    return 0


def ReclaimSpaceFromDocker()->int:
    sc = ScriptCollectionCore()
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--removecontainers', action='store_true', default=False)
    parser.add_argument('-v', '--removevolumes', action='store_true', default=False)
    parser.add_argument('-i', '--removeimages', action='store_true', default=False)
    verbosity_values = ", ".join(f"{lvl.value}={lvl.name}" for lvl in LogLevel)
    parser.add_argument('-v', '--verbosity', required=False, default=3, help=f"Sets the loglevel. Possible values: {verbosity_values}")
    args = parser.parse_args()
    sc:ScriptCollectionCore=ScriptCollectionCore()
    verbosity=int(args.verbosity)
    sc.log.loglevel=LogLevel(verbosity)
    sc.reclaim_space_from_docker(args.removecontainers,args.removevolumes,args.removeimages)
    return 0


def AddImageToCustomRegistry()->int:
    sc = ScriptCollectionCore()
    parser = argparse.ArgumentParser()
    parser.add_argument('-r', '--remotehub', required=True)
    parser.add_argument('-i', '--imagenameonremotehub', required=True)
    parser.add_argument('-o', '--ownregistryaddress', required=True)
    parser.add_argument('-l', '--imagenameonownregistry', required=True)
    parser.add_argument('-t', '--tag', required=False,default="latest")
    parser.add_argument('-u', '--username', required=False,default=None)
    parser.add_argument('-p', '--password', required=False,default=None)
    verbosity_values = ", ".join(f"{lvl.value}={lvl.name}" for lvl in LogLevel)
    parser.add_argument('-v', '--verbosity', required=False, default=3, help=f"Sets the loglevel. Possible values: {verbosity_values}")
    parser.add_argument('-r', '--removeimagelocally', action='store_true', default=False)
    args = parser.parse_args()
    sc:ScriptCollectionCore=ScriptCollectionCore()
    verbosity=int(args.verbosity)
    sc.log.loglevel=LogLevel(verbosity)
    sc.add_image_to_custom_docker_image_registry(args.remotehub,args.imagenameonremotehub,args.ownregistryaddress,args.imagenameonownregistry,args.tag,args.username,args.password)
    return 0

def SearchForSecrets() -> int:
    parser = argparse.ArgumentParser(description="Scans the given repository for secrets using Betterleaks. Fails if unignored findings are present.")
    parser.add_argument('-r', '--repository', required=False, default=None, help="Path to the repository. Defaults to the current working directory.")
    verbosity_values = ", ".join(f"{lvl.value}={lvl.name}" for lvl in LogLevel)
    parser.add_argument('-v', '--verbosity', required=False, default=3, help=f"Sets the loglevel. Possible values: {verbosity_values}")
    args = parser.parse_args()
    repository = GeneralUtilities.resolve_relative_path(args.repository, os.getcwd()) if args.repository is not None else os.getcwd()
    t: TFCPS_CodeUnit_BuildCodeUnits = TFCPS_CodeUnit_BuildCodeUnits(repository, LogLevel(int(args.verbosity)), "QualityCheck", None, True, False, False)
    t.search_for_secrets()
    return 0


def PrepareBuildPipelineForGitlab() -> int:
    parser = argparse.ArgumentParser(description="Prepares the build-pipeline-configuration for GitLab.")
    verbosity_values = ", ".join(f"{lvl.value}={lvl.name}" for lvl in LogLevel)
    parser.add_argument('-v', '--verbosity', required=False, default=3, help=f"Sets the loglevel. Possible values: {verbosity_values}")
    args = parser.parse_args()
    sc: ScriptCollectionCore = ScriptCollectionCore()
    sc.log.loglevel = LogLevel(int(args.verbosity))
    GeneralUtilities.assert_condition(sc.is_running_in_build_container(), "This function should only be run in the build container.")
    sc.run_program("update-ca-certificates")
    sc.run_program_argsasarray("sh",["-c","docker buildx create --name ci-builder --driver docker-container --use 2>/dev/null || docker buildx use ci-builder"])
    sc.run_program("docker","buildx inspect --bootstrap")
    return 0


def ShowVersion() -> int:
    GeneralUtilities.write_message_to_stdout(ScriptCollectionCore.get_scriptcollection_version())
    return 0


def ShowProjectVersion() -> int:
    parser = argparse.ArgumentParser(description="Prints the semver-version of a project as calculated by gitversion.")
    parser.add_argument('-r', '--repository', required=False, default=None, help="Path to the repository. Defaults to the current working directory.")
    args = parser.parse_args()
    repository = GeneralUtilities.resolve_relative_path(args.repository, os.getcwd()) if args.repository is not None else os.getcwd()
    sc: ScriptCollectionCore = ScriptCollectionCore()
    GeneralUtilities.write_message_to_stdout(sc.get_semver_version_from_gitversion(repository))
    return 0


def RunCommandInFolder() -> int:
    parser = argparse.ArgumentParser(description="Runs a command in a folder if (and only if) the folder is located inside the allowed folder.")
    parser.add_argument('-b', '--basefolder', required=True, help="Folder in which the command is  executed in.")
    parser.add_argument('-c', '--command', required=True, help="Command which should be executed.")
    parser.add_argument('-a', '--arguments', required=False, default="", help="Arguments which should be passed to the command.")
    parser.add_argument('-e', '--excludedfolder', action='append', default=[], help="A folder (relative to basefolder) which is not allowed even if it lies inside basefolder. Can be specified multiple times. Example: --excludedfolder .git --excludedfolder .claude --excludedfolder Other/Secrets")
    parser.add_argument('-f', '--actualfolder', required=True, help="Folder-argument.")
    args = parser.parse_args()
    sc = ScriptCollectionCore()
    return sc.run_command_in_folder(args.basefolder, args.command, args.arguments, args.actualfolder, args.excludedfolder)


def RemoveTrailingLinebreak() -> int:
    parser = argparse.ArgumentParser(description="Removes the trailing linebreak from a file. If the last character is not a linebreak, the file is not modified.")
    parser.add_argument('-p', '--path', required=True, help="Path to the file.")
    args = parser.parse_args()
    if not os.path.isfile(args.path):
        GeneralUtilities.write_message_to_stderr(f"File '{args.path}' does not exist.")
        return 1
    ScriptCollectionCore().remove_trailing_linebreak(args.path)
    return 0


def SyncXlfFiles()->int:
    parser = argparse.ArgumentParser(description="This function syncs the content of xlf-files in a folder. This is useful to keep the content of xlf-files in sync which are used for translations in software projects.")
    parser.add_argument('-p', '--prefix',  required=True, help="File prefix. Example: 'message' when the files are named 'message.xlf', 'message.fr.xlf', etc.")
    parser.add_argument('-l', '--languages',  required=True, help="Comma-separated list of languages. Example: 'en,fr,de'")
    parser.add_argument('-f', '--folder',  required=False)
    args = parser.parse_args()
    sc:ScriptCollectionCore=ScriptCollectionCore()
    languages=str(args.languages).split(",")
    folder=GeneralUtilities.resolve_relative_path(args.folder, os.getcwd())
    sc.sync_xlf2_files(args.prefix, languages, folder)
    return 0
