# Gigavolt

## Schema ERD
![Schema](schema.png)

## Remote SSH
1. Download .pem
2. Permissions 
    User = Read-Only
    Groups = None
    Others = None
3. Terminal
    ssh -i /home/kaushal/Downloads/labsuser.pem ubuntu@public_ip
    bash /opt/scripts/val_script.txt
