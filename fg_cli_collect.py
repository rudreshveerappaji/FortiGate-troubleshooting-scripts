#!/usr/bin/env python3
"""
fg_cli_collect.py
FortiGate CLI output Collector - to assist with automated output collection for troubleshooting

CAUTION : 
* Create separate credentials for read-only purpose so that the script is enabled ot collect read only outputs and not make any inadvertant changes to Fortigate configs.
* Review the script, test it in lab before it is used in production, this is not an official Fortinet script, only a hobby project.

Usage example:
  python3 fg_cli_collect.py --host 192.168.1.99 --username admin-read --commands cli-commands.txt --output output-file.txt

If you omit --password, you will be prompted securely.
Note: "admin-read" is just an example account created in FortiGate GUI specifically with read only permissions.

Description:
  - Connects to a FortiGate firewall using SSH (via Paramiko).
  - Reads CLI commands from cli-commands.txt (one per line).
  - Executes each command and captures the output.
  - Handles paginated output (e.g. '--More--') automatically.
  - Saves all command outputs into output-file.txt.

Dependencies:
  pip install paramiko

"""

import argparse
import getpass
import time
import re
import sys
import paramiko
from datetime import datetime

RECV_BUFFER = 65536
COMMAND_DELAY = 0.2
MORE_PROMPT_PATTERNS = [b'--More--', b'More', b'Press any key']
MAX_COMMAND_TIME = 90.0
CONNECTION_TIMEOUT = 10
DEFAULT_READ_TIMEOUT = 2.0


def log(msg, verbose=True):
    if verbose:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def detect_more_prompt(data_bytes):
    if not data_bytes:
        return False
    for pattern in MORE_PROMPT_PATTERNS:
        if pattern in data_bytes:
            return True
    return False


def sanitize_prompt_line(line):
    """
    Creates a relaxed regex for the FortiGate prompt.
    - Tolerates optional trailing text/spaces
    - Works with or without (config) contexts
    """
    escaped = re.escape(line.strip())
    if not escaped:
        return r'[>#]\s*$'
    # match up to 40 extra printable chars after hostname before # or >
    return escaped + r'[\s\S]{0,40}?[#>]\s*$'


def read_until_prompt(chan, prompt_regex, timeout, max_wait, idle_exit_after, verbose=False):
    """
    Read data until:
      - Prompt regex detected, OR
      - idle_exit_after seconds pass with no new data, OR
      - max_wait exceeded.
    """
    buffer = b''
    start_time = time.time()
    last_data_time = time.time()
    chan.settimeout(timeout)

    while True:
        try:
            if chan.recv_ready():
                data = chan.recv(RECV_BUFFER)
                if not data:
                    break
                buffer += data
                last_data_time = time.time()
                if verbose:
                    snippet = data.decode(errors='ignore')[-60:].replace('\n', '\\n')
                    log(f"Received chunk ({len(data)} bytes): ...{snippet}")
                if re.search(prompt_regex, buffer.decode(errors='ignore')):
                    log("Prompt detected.", verbose)
                    break
            else:
                time.sleep(0.05)

            # Idle timeout
            if (time.time() - last_data_time) > idle_exit_after:
                log(f"No new data for {idle_exit_after}s → assuming end of command.", verbose)
                break
            if (time.time() - start_time) > max_wait:
                log(f"Max wait {max_wait}s exceeded.", verbose)
                break
        except Exception as e:
            log(f"Exception during read: {e}", verbose)
            break
    return buffer


def main():
    parser = argparse.ArgumentParser(description='Run CLI commands on FortiGate.')
    parser.add_argument('--host', required=True)
    parser.add_argument('--port', type=int, default=22)
    parser.add_argument('--username', '-u', required=True)
    parser.add_argument('--password', '-p')
    parser.add_argument('--commands', '-c', default='cli-commands.txt')
    parser.add_argument('--output', '-o', default='output-file.txt')
    parser.add_argument('--timeout', type=float, default=DEFAULT_READ_TIMEOUT)
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args()

    verbose = args.verbose
    read_timeout = args.timeout
    host, port, username = args.host, args.port, args.username
    password = args.password or getpass.getpass(f'Password for {username}@{host}: ')
    commands_file, output_file = args.commands, args.output

    # --- Load commands ---
    try:
        with open(commands_file, 'r', encoding='utf-8') as f:
            commands = [l.strip() for l in f if l.strip() and not l.startswith('#')]
    except FileNotFoundError:
        log(f"[ERROR] Commands file not found: {commands_file}")
        sys.exit(1)
    if not commands:
        log("[ERROR] No commands found.")
        sys.exit(1)
    log(f"Loaded {len(commands)} commands from {commands_file}", verbose)

    # --- Connect ---
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    log(f"Connecting to {host}:{port} as {username} ...", verbose)
    try:
        ssh.connect(
            hostname=host, port=port,
            username=username, password=password,
            look_for_keys=False, allow_agent=False,
            timeout=CONNECTION_TIMEOUT
        )
    except Exception as e:
        log(f"[ERROR] SSH connect failed: {e}")
        sys.exit(1)

    chan = ssh.invoke_shell()
    chan.settimeout(read_timeout)
    time.sleep(0.5)

    # --- Detect prompt ---
    initial = read_until_prompt(chan, r'[>#]\s*$', timeout=3.0, max_wait=5.0, idle_exit_after=3.0, verbose=verbose)
    decoded_init = initial.decode(errors='ignore')
    prompt_line = ''
    for l in reversed(decoded_init.splitlines()):
        if l.strip():
            prompt_line = l.strip()
            break
    prompt_regex = sanitize_prompt_line(prompt_line)
    log(f"Detected prompt pattern: {prompt_regex}", verbose)

    outputs = []
    outputs.append(f'-- Session start: {datetime.now()} --\n')
    outputs.append(f'Connected to {host} as {username}\n\n')
    if decoded_init.strip():
        outputs.append('--- Initial Banner ---\n')
        outputs.append(decoded_init + '\n')
        outputs.append('--- End Banner ---\n\n')

    # --- Run commands ---
    for cmd in commands:
        log(f"Running command: {cmd}", verbose)
        outputs.append(f'\n=== Command: {cmd} ===\n')

        try:
            chan.send(cmd + '\n')
        except Exception as e:
            log(f"[ERROR] Failed to send '{cmd}': {e}")
            outputs.append(f"[ERROR] Failed to send {cmd}\n")
            continue

        time.sleep(COMMAND_DELAY)
        collected = b''
        start_time = time.time()

        while True:
            chunk = read_until_prompt(
                chan, prompt_regex,
                timeout=read_timeout, max_wait=15.0,
                idle_exit_after=3.0, verbose=verbose
            )
            if chunk:
                collected += chunk
            if detect_more_prompt(collected):
                log("Pager detected → sending space.", verbose)
                chan.send(' ')
                time.sleep(0.2)
                continue
            # If no chunk for long enough or timeout reached
            if (time.time() - start_time) > MAX_COMMAND_TIME:
                log(f"[WARN] Command '{cmd}' timed out after {MAX_COMMAND_TIME}s", verbose)
                collected += b'\n[WARN] Command timed out.\n'
                break
            # Break if we saw prompt or if read_until_prompt exited due to idle
            if not chunk:
                break

        text = collected.decode('utf-8', errors='replace')
        outputs.append(text)
        outputs.append(f'\n=== End of Command: {cmd} ===\n')
        log(f"Finished '{cmd}', collected {len(text)} chars.", verbose)

    outputs.append(f'\n-- Session end: {datetime.now()} --\n')

    # --- Cleanup ---
    try:
        chan.close()
        ssh.close()
    except Exception:
        pass

    # --- Save output ---
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(''.join(outputs))
        log(f"✅ Output saved to {output_file}")
    except Exception as e:
        log(f"[ERROR] Failed to write output: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

