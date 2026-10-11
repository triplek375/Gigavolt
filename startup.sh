#!/bin/bash

# =======================================================================
# Startup Script for Manual Bootstrapping of MariaDB Galera Cluster
# Using grastate.dat file for safe to bootstrap and seq no
# If grastate.dat is missing, create a new cluster
# If safe_to_bootstrap is 1, bootstrap the cluster
# If safe_to_bootstrap is 0 and seqno is not -1, manually start mariadb using seqno
# If safe_to_bootstrap is 0 and seqno is -1, create a new cluster
# Else, grastate.dat file is corrupt and a new cluster must be created
# Usage : bash /opt/scripts/startup.sh
# =======================================================================

GRASTATE_FILE="/var/lib/mysql/grastate.dat"

if [ ! -f "$GRASTATE_FILE" ]; then
    echo "==================================================================="
    echo "Status: grastate.dat is missing. (Crash Detected)"
    echo "==================================================================="
    echo "==================================================================="
    echo "Action: Manually create a new cluster"
    echo "==================================================================="
    exit 0
else
    SAFE_TO_BOOTSTRAP=$(grep 'safe_to_bootstrap:' "$GRASTATE_FILE" | awk '{print $2}')
    SEQNO=$(grep 'seqno:' "$GRASTATE_FILE" | awk '{print $2}')
fi

if [ "$SAFE_TO_BOOTSTRAP" -eq 1 ]; then
    echo "==================================================================="
    echo "Status: safe_to_bootstrap is 1."
    echo "==================================================================="
    
    sudo galera_new_cluster

    systemctl status mariadb --no-pager

    echo "==================================================================="
    echo "Galera cluster bootstrapping successful!"
    echo "==================================================================="

elif [ "$SAFE_TO_BOOTSTRAP" -eq 0 ] && [ "$SEQNO" != "-1" ]; then
    echo "==================================================================="
    echo "Status: safe_to_bootstrap is 0 and seqno is $SEQNO."
    echo "==================================================================="

    echo "==================================================================="
    echo "Action: Manually start mariadb by checking sequence number"
    echo "==================================================================="

elif [ "$SAFE_TO_BOOTSTRAP" -eq 0 ] && [ "$SEQNO" == "-1" ]; then
    echo "==================================================================="
    echo "Status: safe_to_bootstrap is 0 and seqno is -1 (Crash detected)."
    echo "==================================================================="
    
    echo "==================================================================="
    echo "Action: Manually create a new cluster"
    echo "==================================================================="
else
    else
    echo "==================================================================="
    echo "Status: Corrupt file"
    echo "==================================================================="

    cat "$GRASTATE_FILE"
    
    echo "==================================================================="
    echo "Action: Manually create a new cluster"
    echo "==================================================================="
fi