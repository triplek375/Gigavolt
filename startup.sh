#!/bin/bash

# =======================================================================
# Startup Script for Manual Bootstrapping of MariaDB Galera Cluster
# Using grastate.dat file for safe to bootstrap and wsrep_recovery for seq no
# If safe_to_bootstrap is 1, bootstrap the cluster
# If safe_to_bootstrap is 0 and seqno is -1, recover the seq no
# Else, the mariadb will have to be manually started on the node.
# Usage : bash /opt/scripts/startup.sh
# =======================================================================

GRASTATE_FILE="/var/lib/mysql/grastate.dat"

if [ ! -f "$GRASTATE_FILE" ]; then
    echo "==================================================================="
    echo "Status: grastate.dat is missing."
    echo "==================================================================="
    SAFE_TO_BOOTSTRAP="0"
    SEQNO="-1"
    echo "==================================================================="
    echo "Action: SAFE_TO_BOOTSTRAP=0 and SEQNO=-1."
    echo "==================================================================="
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

elif [ "$SAFE_TO_BOOTSTRAP" -eq 0 ] && [ "$SEQNO" == "-1" ]; then
    echo "==================================================================="
    echo "Status: safe_to_bootstrap is 0 and seqno is -1 (Crash detected)."
    echo "==================================================================="
    
    sudo mysqld --wsrep-recover 2> /tmp/wsrep_recovery.log
    RECOVERED_SEQNO=$(grep "Recovered position:" /tmp/wsrep_recovery.log | tail -1 | awk -F':' '{print $NF}' | tr -d ' ')
    
    echo "True sequence number from InnoDB logs : ${RECOVERED_SEQNO}"
    echo "Note: Ensure this is the highest sequence number across all nodes before proceeding."
    
    read -p "Do you want to force this as the safe node? (Y/n): " FORCE_CHOICE
    
    if [[ "$FORCE_CHOICE" =~ ^[Yy]$ ]]; then
        sudo sed -i 's/safe_to_bootstrap: 0/safe_to_bootstrap: 1/' "$GRASTATE_FILE"
        sudo galera_new_cluster
        echo "==================================================================="
        echo "Galera cluster bootstrapping successful!"
        echo "==================================================================="
    else
        echo "==================================================================="
        echo "Action: Manually start the mariadb service on this node."
        echo "==================================================================="
    fi

    systemctl status mariadb --no-pager

else
    echo "==================================================================="
    echo "Status: safe_to_bootstrap is 0. (not safe node)"
    echo "==================================================================="

    systemctl status mariadb --no-pager

    echo "==================================================================="
    echo "Action: Manually start the mariadb service on this node."
    echo "==================================================================="
fi