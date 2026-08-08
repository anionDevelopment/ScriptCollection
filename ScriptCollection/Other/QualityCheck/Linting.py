import sys
from ScriptCollection.TFCPS.Python.TFCPS_CodeUnitSpecific_Python import TFCPS_CodeUnitSpecific_Python_Functions,TFCPS_CodeUnitSpecific_Python_CLI


def linting():
    tf:TFCPS_CodeUnitSpecific_Python_Functions=TFCPS_CodeUnitSpecific_Python_CLI.parse(__file__)
    tf.linting()


if __name__ == "__main__":
    linting()
