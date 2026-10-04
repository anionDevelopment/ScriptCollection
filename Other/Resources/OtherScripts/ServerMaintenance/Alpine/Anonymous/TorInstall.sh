#! /bin/bash
# This script is intended to be executed on an alpine-system as root-user.
# After execution usually the following paths will be used by default:
# /etc/tor (configuration)
# /var/log/tor (logs)

pushd $(dirname $0)

# preparation:
../Common/InstallSystemUtilities.sh

apk add tor

popd
