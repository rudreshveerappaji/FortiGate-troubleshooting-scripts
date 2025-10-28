# FortiGate-login-with-SSH-and-collect-CLI-command-outputs


### Usage Example

1. Install dependency:

pip install paramiko

2. Prepare cli-commands.txt:

get system status
get system performance status

3. Run:

python3 fg_cli_collect.py --host 192.168.1.99 --username admin --commands cli-commands.txt --output output-file.txt

You’ll be prompted for the password if not passed with --password.
