#!/bin/bash

if [ "$EUID" -ne 0 ]
  then echo "This script is expected to be executed with elevated privileges."
  exit
fi

#TODO check if docker is available

#remove unused docker-container
#docker volume prune --force

#remove unused images
#docker rmi $(docker images --filter "dangling=true" -q --no-trunc) # TODO issue: this line is not idempotent
