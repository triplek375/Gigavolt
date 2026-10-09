# Gigavolt

## Schema ERD
![Schema](schema.png)

## Creating instances
1. Give instance name, select no of instances and Ubuntu
2. Use VPC key and security group
3. Use the init_script.sh in user-data.log
4. After creating rename the instances
5. systemctl stop mariadb (all nodes)
6. sudo galera_new_cluster (nodeA)
7. systemctl start mariadb (node A, B and then C)

## Stopping instances safely


## Starting instances safely


## Remote SSH
1. Download .pem
2. Permissions: User(Read-Only), Groups(None), Others(None)
3. Connect: ssh -i /home/kaushal/Downloads/labsuser.pem ubuntu@public_ip
4. Validate: bash /opt/scripts/val_script.sh
