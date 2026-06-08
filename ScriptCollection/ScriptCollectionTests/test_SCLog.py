import os
import tempfile
import unittest
import uuid
from ..ScriptCollection.GeneralUtilities import GeneralUtilities
from ..ScriptCollection.SCLog import SCLog


class SCLogTests(unittest.TestCase):


    @GeneralUtilities.check_arguments
    def __test_function(self):
        raise ValueError("test-exception")
    
    @GeneralUtilities.check_arguments
    def test_log_exception(self) -> None:
        # arrange
        log_file:str = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()) + ".log")
        GeneralUtilities.ensure_file_exists(log_file)
        log = SCLog(log_file)
        try:
            self.__test_function()
        except Exception as e:
            
            # act
            log.log_exception("test-message",e)

            # assert
            lines=GeneralUtilities.read_lines_from_file(log_file)
            assert "Exception: test-message; Exception-details: test-exception; Traceback: Traceback (most recent call last):" == lines[0]
            assert "ScriptCollectionTests"+os.sep+"test_SCLog.py\", line 23, in test_log_exception" in lines[1]
            assert "self.__test_function()" in lines[2]
            assert "test_SCLog.py\", line 14, in __test_function" in lines[6] 
            assert "raise ValueError(\"test-exception\")" in lines[7] 
            assert "ValueError: test-exception" == lines[8] 

            #cleanup
        finally:
            GeneralUtilities.ensure_file_does_not_exist(log_file)
