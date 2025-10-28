#!/usr/bin/env python3
"""
fg_cli_collect.py

Usage example:
  python3 fg_cli_collect.py --host 192.168.1.99 --username admin --commands cli-commands.txt --output output-file.txt

If you omit --password, you will be prompted securely.

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

# ---------- Global defaults ----------
RECV_BUFFER = 65536          # bytes to read per recv
COMMAND_DELAY = 0.2          # seconds between sending a command and reading
MORE_PROMPT_PATTERNS = [     # known FortiGate pager prompts
    b'--More--',
    b'--More-- ',
    b'More ',
    b'Press any key to continue',
]


# ---------- Helper functions ----------
def read_until_prompt(chan, prompt_regex, timeout):
    """
    Reads data from the SSH channel until we detect the FortiGate prompt
    or a timeout occurs.
    Returns the entire bytes buffer.
    """
    buffer = b''
    chan.settimeout(timeout)
    start = time.time()
    while True:
        try:
            if chan.recv_ready():
                data = chan.recv(RECV_BUFFER)
                if not data:
                    break
                buffer += data
                # If prompt detected -> stop
                if re.search(prompt_regex, buffer.decode(errors='ignore')):
                    break
            else:
                time.sleep(0.05)
                if (time.time() - start) > timeout:
                    break
        except Exception:
            break
    return buffer


def detect_more_prompt(data_bytes):
    """Return True if '--More--' or similar pager prompt detected."""
    if not data_bytes:
        return False
    for pattern in MORE_PROMPT_PATTERNS:
        if pattern in data_bytes:
            return True
    return False


def sanitize_prompt_line(line):
    """
    Construct a regex pattern to detect the FortiGate CLI prompt.
    Typical prompts: 'hostname #', 'hostname >', 'hostname (config) #'
    """
    escaped = re.escape(line.strip())
    if not escaped:
        return r'[>#]\s*$'
    return escaped + r'[\s\S]{0,30}[#>]\s*$'


# ---------- Main logic ----------
def main():
    parser = argparse.ArgumentParser(description='Run CLI commands on a FortiGate and collect outputs.')
    parser.add_argument('--host', required=True, help='FortiGate hostname or IP')
    parser.add_argument('--port', type=int, default=22, help='SSH port (default: 22)')
    parser.add_argument('--username', '-u', required=True, help='SSH username')
    parser.add_argument('--password', '-p', help='SSH password (omit to prompt securely)')
    parser.add_argument('--commands', '-c', default='cli-commands.txt', help='File with CLI commands')
    parser.add_argument('--output', '-o', default='output-file.txt', help='File to save outputs')
    parser.add_argument('--timeout', type=float, default=2.0, help='Read timeout in seconds (default: 2.0)')
    args = parser.parse_args()

    # Local variable instead of global
    read_timeout = args.timeout

    host = args.host
    port = args.port
    username = args.username
    password = args.password if args.password else getpass.getpass(f'Password for {username}@{host}: ')
    commands_file = args.commands
    output_file = args.output

    # Read CLI commands from file
    try:
        with open(commands_file, 'r', encoding='utf-8') as f:
            commands = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
    except FileNotFoundError:
        print(f'[ERROR] Commands file not found: {commands_file}', file=sys.stderr)
        sys.exit(1)

    if not commands:
        print('[ERROR] No commands found in file.', file=sys.stderr)
        sys.exit(1)

    # Create SSH client
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    print(f'Connecting to {host}:{port} as {username} ...')
    try:
        ssh.connect(
            hostname=host,
            port=port,
            username=username,
            password=password,
            look_for_keys=False,
            allow_agent=False,
            timeout=10
        )
    except Exception as e:
        print(f'[ERROR] SSH connection failed: {e}', file=sys.stderr)
        sys.exit(1)

    chan = ssh.invoke_shell()
    chan.settimeout(read_timeout)
    time.sleep(0.5)

    # Capture the initial banner/prompt
    initial = read_until_prompt(chan, r'[>#]\s*$', timeout=3.0)
    initial_decoded = initial.decode(errors='ignore')

    # Try to guess the prompt
    prompt_line = ''
    for l in reversed(initial_decoded.splitlines()):
        if l.strip():
            prompt_line = l.strip()
            break
    prompt_regex = sanitize_prompt_line(prompt_line)

    # Collect outputs
    outputs = []
    outputs.append(f'-- Session start: {time.strftime("%Y-%m-%d %H:%M:%S")} --\n')
    outputs.append(f'Connected to {host} as {username}\n\n')

    if initial_decoded.strip():
        outputs.append('--- Initial Banner ---\n')
        outputs.append(initial_decoded + '\n')
        outputs.append('--- End Banner ---\n\n')

    # Execute each command
    for cmd in commands:
        print(f'Running: {cmd}')
        outputs.append(f'\n=== Command: {cmd} ===\n')

        chan.send(cmd + '\n')
        time.sleep(COMMAND_DELAY)

        collected = b''
        overall_start = time.time()
        max_command_time = 120.0  # safety timeout per command

        while True:
            chunk = read_until_prompt(chan, prompt_regex, timeout=read_timeout)
            if chunk:
                collected += chunk

            # Handle pager
            if detect_more_prompt(collected):
                chan.send(' ')
                time.sleep(0.2)
                continue

            # Detect prompt (command done)
            try:
                if re.search(prompt_regex, collected.decode(errors='ignore')):
                    break
            except Exception:
                pass

            # Timeout guard
            if (time.time() - overall_start) > max_command_time:
                collected += b'\n[ERROR] Command timed out.\n'
                break

            time.sleep(0.1)

        text = collected.decode('utf-8', errors='replace')
        outputs.append(text)
        outputs.append(f'\n=== End of Command: {cmd} ===\n')

    outputs.append(f'\n-- Session end: {time.strftime("%Y-%m-%d %H:%M:%S")} --\n')

    # Close connections
    try:
        chan.close()
        ssh.close()
    except Exception:
        pass

    # Write output file
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(''.join(outputs))
        print(f'\n✅ All done. Results saved to: {output_file}')
    except Exception as e:
        print(f'[ERROR] Failed to write output file: {e}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
