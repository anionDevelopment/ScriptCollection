from ScriptCollection.TFCPS.Python.TFCPS_CodeUnitSpecific_Python import TFCPS_CodeUnitSpecific_Python_Functions,TFCPS_CodeUnitSpecific_Python_CLI

def build():

    tf:TFCPS_CodeUnitSpecific_Python_Functions=TFCPS_CodeUnitSpecific_Python_CLI.parse(__file__)
    tf.build()


if __name__ == "__main__":
    build()
