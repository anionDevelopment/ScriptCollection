import sys
from ScriptCollection.TFCPS.Python.TFCPS_CodeUnitSpecific_Python import TFCPS_CodeUnitSpecific_Python_Functions,TFCPS_CodeUnitSpecific_Python_CLI


def run_testcases():
    tf:TFCPS_CodeUnitSpecific_Python_Functions=TFCPS_CodeUnitSpecific_Python_CLI.parse(__file__)
    tf.run_testcases()


if __name__ == "__main__":
    run_testcases()
