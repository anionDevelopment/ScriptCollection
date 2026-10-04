#! /bin/bash
# This script is intended to be executed as user with elevated privileges.

pushd $(dirname $0)

./AptUpgrade.sh
apt-get -y install curl fail2ban ca-certificates wget gpg htop iputils-ping jq libxslt-dev lsof ntfs-3g ntp net-tools python3-pip tcpdump tree unattended-upgrades hdparm lm-sensors mdadm smartmontools ifupdown gdisk rsync util-linux apt-file psmisc zip

popd
