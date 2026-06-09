import unittest
from pathlib import Path
from ..ScriptCollection.UnassignedVariablesCheck import UnassignedVariablesCheck


class CodestyleTests(unittest.TestCase):

    def test_no_bare_annotations(self) -> None:
        UnassignedVariablesCheck.assert_no_unassigned_variables_in_codeunit(str(Path(__file__).resolve().parent.parent))
