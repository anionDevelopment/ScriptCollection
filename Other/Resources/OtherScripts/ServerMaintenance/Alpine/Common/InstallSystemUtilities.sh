#! /bin/bash
# This script is intended to be executed as user with elevated privileges.

pushd $(dirname $0)

apk add gnupg sudo wget curl tree procps git bmon iftop gdb nano

popd
