import os
from pathlib import Path
from datetime import datetime, timedelta
import traceback
from shutil import copyfile
import argparse
from .GeneralUtilities import GeneralUtilities
from .ScriptCollectionCore import ScriptCollectionCore
from .SCLog import LogLevel


class CertificateUpdater:
    maximal_age_of_certificates_in_days: int = None
    __domains: list[str] = None
    __email: str = None
    __current_folder: str = None
    __last_update_timestamp_file: str = None
    __repository_folder: str = None
    __letsencrypt_folder: str = None
    __letsencrypt_live_folder: str = None
    __letsencrypt_archive_folder: str = None
    __log_folder: str = None
    __sc: ScriptCollectionCore = None
    __arguments: ScriptCollectionCore = None
    __certbot_image_address_with_tag:str=None

    def __init__(self, domains: list[str], email: str, current_file: str, arguments: list[str],certbot_image_address_with_tag:str=None):
        self.__sc = ScriptCollectionCore()
        self.maximal_age_of_certificates_in_days = 15
        self.__domains = domains
        self.__email = email
        self.__current_folder = current_file
        self.__arguments = arguments
        self.__last_update_timestamp_file = GeneralUtilities.resolve_relative_path("./LastCertificateUpdate.csv", self.__current_folder)
        self.__repository_folder = GeneralUtilities.resolve_relative_path("../..", self.__current_folder)
        self.__sc.assert_is_git_repository(self.__repository_folder)
        self.__letsencrypt_folder = f"{ self.__repository_folder}/Configuration/Volumes/letsencrypt"
        self.__letsencrypt_live_folder = os.path.join(self.__letsencrypt_folder, "live")
        self.__letsencrypt_archive_folder = os.path.join(self.__letsencrypt_folder, "archive")
        self.__log_folder = GeneralUtilities.resolve_relative_path("Logs/Overhead", self.__repository_folder)
        if certbot_image_address_with_tag is None:
            certbot_image_address_with_tag="docker.io/certbot/certbot:latest"
        self.__certbot_image_address_with_tag=certbot_image_address_with_tag

    @GeneralUtilities.check_arguments
    def __get_latest_index_by_domain(self, domain: str) -> int:
        result = self.__get_latest_index_by_filelist(GeneralUtilities.get_all_files_of_folder(os.path.join(self.__letsencrypt_archive_folder, domain)))
        GeneralUtilities.write_message_to_stdout(f"Debug: Latest found existing number for domain {domain}: {result}")
        return result

    @GeneralUtilities.check_arguments
    def __get_latest_index_by_filelist(self, filenames: list[str]) -> int:
        filenames = [Path(os.path.basename(file)).stem for file in filenames]
        filenames = [file for file in filenames if file.startswith("privkey")]
        numbers = [int(file[len("privkey"):]) for file in filenames]
        result = max(numbers)
        return result

    @GeneralUtilities.check_arguments
    def __replace_symlink_by_file(self, domain: str, filename: str, index: int) -> None:
        # ".../live/example.com/cert.pem" is a symlink but should replaced by a copy of ".../archive/example.com/cert.42pem"
        archive_file = os.path.join(self.__letsencrypt_archive_folder, domain, filename+str(index)+".pem")
        live_folder = os.path.join(self.__letsencrypt_live_folder, domain)
        live_filename = filename+".pem"
        live_file = os.path.join(live_folder, live_filename)
        self.__sc.run_program("rm", live_filename, live_folder, throw_exception_if_exitcode_is_not_zero=True)
        copyfile(archive_file, live_file)

    @GeneralUtilities.check_arguments
    def __replace_file_by_symlink(self, domain: str, filename: str, index: int) -> None:
        # new ".../live/example.com/cert.pem" is a file but should replaced by a symlink which points to ".../archive/example.com/cert42.pem"
        live_folder = os.path.join(self.__letsencrypt_live_folder, domain)
        live_filename = filename+".pem"
        self.__sc.run_program("rm", live_filename, live_folder, throw_exception_if_exitcode_is_not_zero=True)
        self.__sc.run_program("ln", f"-s ../../archive/{domain}/{filename+str(index)}.pem {live_filename}", live_folder, throw_exception_if_exitcode_is_not_zero=True)

    @GeneralUtilities.check_arguments
    def __replace_symlinks_by_files(self, domain):
        index = self.__get_latest_index_by_domain(domain)
        self.__replace_symlink_by_file(domain, "cert", index)
        self.__replace_symlink_by_file(domain, "chain", index)
        self.__replace_symlink_by_file(domain, "fullchain", index)
        self.__replace_symlink_by_file(domain, "privkey", index)

    @GeneralUtilities.check_arguments
    def __replace_files_by_symlinks(self, domain):
        index = self.__get_latest_index_by_domain(domain)
        self.__replace_file_by_symlink(domain, "cert", index)
        self.__replace_file_by_symlink(domain, "chain", index)
        self.__replace_file_by_symlink(domain, "fullchain", index)
        self.__replace_file_by_symlink(domain, "privkey", index)

    @GeneralUtilities.check_arguments
    def __update_certificates(self) -> None:
        self.__sc.git_commit(self.__repository_folder, "Saved current changes")
        error_occurred = False
        for domain in self.__domains:
            certbot_container_name = "certificate_updater"
            try:
                GeneralUtilities.write_message_to_stdout(GeneralUtilities.get_line())
                GeneralUtilities.write_message_to_stdout(f"Process domain {domain}")
                self.__sc.run_program("docker", f"container rm {certbot_container_name}", self.__current_folder, throw_exception_if_exitcode_is_not_zero=False)
                certificate_for_domain_already_exists = os.path.isfile(f"{self.__letsencrypt_folder}/renewal/{domain}.conf")
                if certificate_for_domain_already_exists:
                    GeneralUtilities.write_message_to_stdout(f"Update certificate for domain {domain}")
                    self.__replace_files_by_symlinks(domain)
                else:
                    GeneralUtilities.write_message_to_stdout(f"Create certificate for domain {domain}")
                dockerargument = f"run --rm --name {certbot_container_name} --volume {self.__letsencrypt_folder}:/etc/letsencrypt"
                dockerargument = dockerargument + f" --volume {self.__log_folder}:/var/log/letsencrypt -p 80:80 "+self.__certbot_image_address_with_tag
                certbotargument = f"--standalone --email {self.__email} --agree-tos --force-renewal --rsa-key-size 4096 --non-interactive --no-eff-email --domain {domain} certonly"
                if self.__sc.log.loglevel==LogLevel.Debug:
                    certbotargument=certbotargument+" -v"
                if (certificate_for_domain_already_exists):
                    self.__sc.run_program("docker", f"{dockerargument} --no-random-sleep-on-renew {certbotargument}", self.__current_folder)
                    self.__replace_symlinks_by_files(domain)
                    GeneralUtilities.write_message_to_stdout(f"Certificates updated for {domain}.")
                else:
                    self.__sc.run_program("docker", f"{dockerargument} --cert-name {domain} {certbotargument}", self.__current_folder)
            except Exception as exception:
                error_occurred = True
                GeneralUtilities.write_exception_to_stderr_with_traceback(exception, traceback, "Error while updating certificate")
        self.__sc.git_commit(self.__repository_folder, "Executed certificate-update-process")
        GeneralUtilities.write_message_to_stdout("Finished certificate-update-process")
        if error_occurred:
            raise ValueError("Certificates for at least one domain could not be added/updated.")

    @GeneralUtilities.check_arguments
    def __get_last_certificate_update_date(self) -> datetime:
        if os.path.exists(self.__last_update_timestamp_file):
            filecontent = GeneralUtilities.read_text_from_file(self.__last_update_timestamp_file)
            return GeneralUtilities.string_to_datetime(filecontent.replace("\r", GeneralUtilities.empty_string).replace("\n", GeneralUtilities.empty_string))
        else:
            return datetime(year=1970, month=1, day=1)

    @GeneralUtilities.check_arguments
    def __set_last_certificate_update_date(self, moment: datetime) -> datetime:
        GeneralUtilities.ensure_file_exists(self.__last_update_timestamp_file)
        GeneralUtilities.write_text_to_file(self.__last_update_timestamp_file, GeneralUtilities.datetime_to_string(moment))

    @GeneralUtilities.check_arguments
    def update_certificates_if_required(self) -> None:
        now = datetime.now()
        parser = argparse.ArgumentParser(description="Updated lets-encrypt-certificates")
        parser.add_argument('-f', '--force', action='store_true', required=False, default=False)
        parser.add_argument('-v', '--verbose', action='store_true', required=False, default=False)
        args = parser.parse_args(self.__arguments)
        if args.verbose:
            self.__sc.log.loglevel = LogLevel.Debug
        if (self.__get_last_certificate_update_date()+timedelta(days=self.maximal_age_of_certificates_in_days)) < now or args.force:
            GeneralUtilities.write_message_to_stdout(f"Update certificates...")
            self.__update_certificates()
            self.__set_last_certificate_update_date(now)
        else:
            GeneralUtilities.write_message_to_stdout(f"Certificates are already up to date.")
