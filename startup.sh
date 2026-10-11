#!/bin/bash

# =======================================================================
# Startup Script for Manual Bootstrapping of MariaDB Galera Cluster
# Using grastate.dat file to find safe bootstrap node
# Usage : bash /opt/scripts/startup.sh
# =======================================================================

GRASTATE_FILE="/var/lib/mysql/grastate.dat"
SAFE_TO_BOOTSTRAP=$(grep 'safe_to_bootstrap:' "$GRASTATE_FILE" | awk '{print $2}')

if [ "$SAFE_TO_BOOTSTRAP" -eq 1 ]; then
    echo "==================================================================="
    echo "Status: safe_to_bootstrap is 1."
    echo "Action: Bootstrapping the Galera cluster from this node..."
    echo "==================================================================="
    
    sudo galera_new_cluster
else
    echo "==================================================================="
    echo "Status: safe_to_bootstrap is 0. (not safe node)"
    echo "==================================================================="
fi

systemctl status mariadb --no-pager