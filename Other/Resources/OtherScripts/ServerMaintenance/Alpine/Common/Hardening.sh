#! /bin/bash
# This script is intended to be run as user with root privileges.

#Arguments:
applicationstokeep="$2" #semicolon-separated list
additionalFolderToRemove="$3" #semicolon-separated list

cd /

# TODO:
# - deinstall/disable sudo, wget, ls, ping, git, find, chown, chmod, etc. and all other applications which are not listed in $applicationstokeep
# - generally disable root-login
# - shrink rights of all users as much as possible
# - prevent writing files using something like "echo x > y"
# - prevent executing files as much as possible
# etc.
