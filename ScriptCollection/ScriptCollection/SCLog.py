import traceback
from enum import Enum
from datetime import datetime
from .GeneralUtilities import GeneralUtilities


class LogLevel(Enum):
    Quiet = 0
    Error = 1
    Warning = 2
    Information = 3
    Debug = 4
    Diagnostic = 5

    def __int__(self):
        return self.value


class SCLog:
    loglevel: LogLevel = None  #minimum loglevel
    log_file: str = None
    add_overhead_to_console: bool = None
    add_overhead_to_logfile: bool = None
    print_as_color: bool = None
    add_milliseconds_to_logfile_entry: bool = None

    def __init__(self, log_file: str = None, loglevel: LogLevel = None, print_as_color: bool = True):
        self.log_file = log_file
        if loglevel is None:
            self.loglevel = LogLevel.Information
        else:
            self.loglevel = loglevel
        self.add_overhead_to_console = False
        self.add_overhead_to_logfile = False
        self.add_milliseconds_to_logfile_entry = False
        self.print_as_color = print_as_color

    @GeneralUtilities.check_arguments
    def log_exception(self, message: str, ex: Exception,loglevel:LogLevel = LogLevel.Error):
        self.log(f"Exception: {message}; Exception-details: {str(ex)}; Traceback: {traceback.format_exc()}", loglevel)

    @GeneralUtilities.check_arguments
    def log(self, message: str, loglevel: LogLevel = None):
        for line in GeneralUtilities.string_to_lines(message, True, False):
            self.__log_line(line, loglevel)

    @GeneralUtilities.check_arguments
    def __log_line(self, message: str, loglevel: LogLevel = None):

        print_to_console: bool = True
        print_to_logfile: bool = self.log_file is not None

        if loglevel is None:
            loglevel = LogLevel.Information

        if int(self.loglevel)<int(loglevel):
            return

        part1: str = GeneralUtilities.empty_string
        part2: str = GeneralUtilities.empty_string
        part3: str = "] "
        part4: str = message

        if loglevel == LogLevel.Warning and not message.startswith("Warning: "):
            part4 = f"Warning: {message}"
        if loglevel == LogLevel.Debug and not message.startswith("Debug: "):
            part4 = f"Debug: {message}"
        if loglevel == LogLevel.Diagnostic and not message.startswith("Diagnostic: "):
            part4 = f"Diagnostic: {message}"

        moment: datetime = datetime.now(datetime.now().astimezone().tzinfo)

        part1 = f"[{GeneralUtilities.datetime_to_string_for_logfile_entry(moment, self.add_milliseconds_to_logfile_entry)}] ["
        if loglevel == LogLevel.Information:
            part2 = f"Information"
        elif loglevel == LogLevel.Error:
            part2 = f"Error"
        elif loglevel == LogLevel.Warning:
            part2 = f"Warning"
        elif loglevel == LogLevel.Debug:
            part2 = f"Debug"
        elif loglevel == LogLevel.Diagnostic:
            part2 = f"Diagnostic"
        else:
            raise ValueError("Unknown loglevel.")

        if print_to_console:
            print_to_std_out: bool = loglevel in (LogLevel.Debug, LogLevel.Information)
            if self.add_overhead_to_console:
                GeneralUtilities.print_text(part1, print_to_std_out)
                if loglevel == LogLevel.Information:
                    GeneralUtilities.print_text_in_green(part2, print_to_std_out, self.print_as_color)
                elif loglevel == LogLevel.Error:
                    GeneralUtilities.print_text_in_red(part2, print_to_std_out, self.print_as_color)
                elif loglevel == LogLevel.Warning:
                    GeneralUtilities.print_text_in_yellow(part2, print_to_std_out, self.print_as_color)
                elif loglevel == LogLevel.Debug:
                    GeneralUtilities.print_text_in_cyan(part2, print_to_std_out, self.print_as_color)
                elif loglevel == LogLevel.Diagnostic:
                    GeneralUtilities.print_text_in_cyan(part2, print_to_std_out, self.print_as_color)
                else:
                    raise ValueError("Unknown loglevel.")
                GeneralUtilities.print_text(part3+part4+"\n", print_to_std_out)
            else:
                GeneralUtilities.print_text(part4+"\n", print_to_std_out)

        if print_to_logfile:
            GeneralUtilities.ensure_file_exists(self.log_file)
            if self.add_overhead_to_logfile:
                GeneralUtilities.append_line_to_file(self.log_file, part1+part2+part3+part4)
            else:
                GeneralUtilities.append_line_to_file(self.log_file, part4)
