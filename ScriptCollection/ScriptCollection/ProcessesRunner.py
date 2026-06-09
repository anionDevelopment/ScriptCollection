import psutil
from .GeneralUtilities import GeneralUtilities
from .ScriptCollectionCore import ScriptCollectionCore

# runs multiple processes in parallel and terminate all if at least one is terminated


class ProcessStartInformation:
    workingdirectory: str = None
    program: str = None
    arguments: str = None

    def __init__(self, workingdirectory: str, program: str, arguments: str):
        self.workingdirectory = workingdirectory
        self.program = program
        self.arguments = arguments


class ProcessesRunner:
    sc: ScriptCollectionCore = None
    processes: list[ProcessStartInformation] = None

    def __init__(self, processes: list[ProcessStartInformation]):
        self.sc = ScriptCollectionCore()
        self.processes = processes

    @GeneralUtilities.check_arguments
    def run(self):
        pids: list[int] = list[int]()
        for processstartinfo in self.processes:
            pids.append(self.sc.run_program_async(processstartinfo.program, processstartinfo.argumentss, processstartinfo.workingdirectory))
        enabled = True
        while enabled:
            for pid in pids:
                if not psutil.pid_exists(pid):
                    enabled = False
        # one program terminate so exit and terminate all now
        processes = psutil.process_iter()
        for pid in pids:
            if psutil.pid_exists(pid):
                for proc in processes:
                    if proc.pid == pid:
                        proc.kill()
