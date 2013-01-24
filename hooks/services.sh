#!/bin/bash


# Definition of available services in landscape, and mapping to the 
# variable in /etc/default/landcape
unset DEFAULT_VAR
declare -A DEFAULT_VAR
DEFAULT_VAR=(
    [appserver]="RUN_APPSERVER"
    [msgserver]="RUN_MSGSERVER"
    [pingserver]="RUN_PINGSERVER"
    [combo-loader]="RUN_COMBO_LOADER"
    [async-frontend]="RUN_ASYNC_FRONTEND"
    [apiserver]="RUN_APISERVER"
    [package-upload]="RUN_PACKAGEUPLOADSERVER"
    [jobhandler]="RUN_JOBHANDLER"
    [package-search]="RUN_PACKAGESEARCH"
)
