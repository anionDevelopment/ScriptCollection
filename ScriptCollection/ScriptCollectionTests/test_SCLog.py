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
            content="\n".join(lines)
            assert "Exception: test-message; Exception-details: test-exception; Traceback: Traceback (most recent call last):" == lines[0]
            #the frame-headers (file, line-number, function-name) are asserted because they are taken directly from the code-object of each frame and are therefore always deterministic.
            #the corresponding source-code-snippets (for example "self.__test_function()") are intentionally not asserted: printing them is a best-effort feature of the traceback-module
            #which re-reads the source-file from disk via linecache when the traceback is formatted, and that re-read is not guaranteed to succeed in every environment (for example when
            #the sourcecode-file is accessed through a mounted filesystem inside a build-container), which made this test flaky.
            outer_frame_marker="ScriptCollectionTests"+os.sep+"test_SCLog.py\", line 23, in test_log_exception"
            inner_frame_marker="test_SCLog.py\", line 14, in __test_function"
            assert outer_frame_marker in content
            assert inner_frame_marker in content
            assert content.index(outer_frame_marker) < content.index(inner_frame_marker)
            non_empty_lines=[line for line in lines if GeneralUtilities.string_has_content(line)]
            assert "ValueError: test-exception" == non_empty_lines[-1]

            #cleanup
        finally:
            GeneralUtilities.ensure_file_does_not_exist(log_file)
