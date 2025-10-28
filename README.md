# FortiGate-login-with-SSH-and-collect-CLI-command-outputs


## Usage Example

1. Install dependency:

pip install paramiko

2. Prepare cli-commands.txt:

get system status
get system performance status

3. Run:

python3 fg_cli_collect.py --host 192.168.1.99 --username admin --commands cli-commands.txt --output output-file.txt

You’ll be prompted for the password if not passed with --password.

Optional:
use "verbose" argument for debugging
python3 fg_cli_collect.py --host 10.9.11.26 --username fortinet --commands cli-commands.txt --output output-file.txt --verbose

### Example outputs:

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

