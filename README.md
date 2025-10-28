# FortiGate-login-with-SSH-and-collect-CLI-command-outputs

## Purpose
FortiGate CLI output Collector python script - to assist with automated output collection for troubleshooting

CAUTION : 
* Create a separate dedicated account(username/password) for read-only purpose to use with this script, so that the script is enabled to collect read only outputs and not make any inadvertant changes to Fortigate configs.
* Review the script, test it in a lab device before it is used in production, this is not an official Fortinet script, just a hobby project to illustrate the use case.

Usage example:
  python3 fg_cli_collect.py --host 192.168.1.99 --username admin-read --commands cli-commands.txt --output output-file.txt

If you omit --password, you will be prompted securely.
Note: "admin-read" is just an example account created in FortiGate GUI specifically with read only permissions.

## Usage Example

1. Install dependency:
```bash
pip install paramiko
```
2. Prepare cli-commands.txt:
Here is an example of a couple of CLI command outputs to collect, the CLI commands should be one per line.
```bash
get system status
get system performance status
execute tac report
```
3. Run:
```bash
python3 fg_cli_collect.py --host 192.168.1.99 --username admin-read --commands cli-commands.txt --output output-file.txt
```
You’ll be prompted for the password if not passed with --password.

Optional:
use "verbose" argument for debugging
```bash
python3 fg_cli_collect.py --host 192.168.1.99 --username fortinet --commands cli-commands.txt --output output-file.txt --verbose
```
### Example outputs:
```bash
C:\Downloads>python3 fg_cli_collect.py --host 192.168.1.99 --username fortinet --commands cli-commands.txt --output output-file.txt --verbose
Password for fortinet@192.168.1.99:

[14:25:48] Loaded 2 commands from cli-commands.txt
[14:25:48] Connecting to 10.9.11.26:22 as fortinet ...
[14:25:49] Received chunk (19 bytes): ...Fortigate-VM #
[14:25:49] Prompt detected.
[14:25:49] Running command: get sys status
\nFortigate-VM #  warm rebootytes): ...2025
[14:25:52] No new data for 3.0s → assuming end of command.
[14:25:56] No new data for 3.0s → assuming end of command.
[14:25:56] Finished 'get sys status', collected 1032 chars.
[14:25:56] Running command: get sys ha status
\nFortigate-VM #  0nk (288 bytes): ...
[14:25:59] No new data for 3.0s → assuming end of command.
[14:26:02] No new data for 3.0s → assuming end of command.
[14:26:02] Finished 'get sys ha status', collected 288 chars.
[14:26:02] ✅ Output saved to output-file.txt

C:\Downloads>
```

