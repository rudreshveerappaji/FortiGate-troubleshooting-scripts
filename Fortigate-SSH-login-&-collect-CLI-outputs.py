#!/usr/bin/env python3
"""
fg_cli_collect.py

Usage:
  python3 fg_cli_collect.py --host 1.2.3.4 --username admin --commands cli-commands.txt --output output-file.txt
  (If --password is omitted you'll be prompted securely.)

What it does:
  - Connects to a FortiGate via SSH using paramiko.
  - Reads commands from `cli-commands.txt` (one CLI command per line).
  - Executes each command on the remote FortiGate CLI (interactive shell).
  - Collects the output for each command and writes all results into `output-file.txt`.
  - Attempts to handle paginated output (e.g. `--More--`) by sending a space when the pager prompt is detected.
  - Has fairly robust read loops and timeouts to avoid hanging indefinitely.

Dependencies:
  pip install paramiko
"""

import argparse
import getpass
import time
import re
import sys

import paramiko

# ---------- Configuration Defaults ----------
RECV_BUFFER = 65536          # bytes to read per recv
READ_TIMEOUT = 2.0           # seconds to wait for more data in normal read loop
COMMAND_DELAY = 0.2          # small pause after sending a command (seconds)
MORE_PROMPT_PATTERNS = [     # patterns that indicate the device is waiting for pager input
    b'--More--',
    b'--More-- ',
    b'More ',
    b'Press any key to continue',
]


# ---------- Helper functions ----------
def read_until_prompt(chan, prompt_regex, timeout=READ_TIMEOUT):
    """
    Read from an interactive SSH channel until the prompt_regex is seen (or timeout).
    Handles incremental reads and returns the entire buffer (bytes).
    """
    buffer = b''
    chan.settimeout(timeout)
    start = time.time()
    while True:
        try:
            if chan.recv_ready():
                data = chan.recv(RECV_BUFFER)
                if not data:
                    # remote closed or no data
                    break
                buffer += data
                # if we detect pager, caller may need to send continuation (we still keep reading)
                if re.search(prompt_regex, buffer.decode(errors='ignore')):
                    break
            else:
                # Nothing ready right now: small sleep then check elapsed time
                time.sleep(0.05)
                # break if we've been idle past the provided timeout (this ensures we don't hang)
                if (time.time() - start) > timeout:
                    break
        except Exception:
            # In case of socket timeout or other issues, break loop
            break
    return buffer


def detect_more_prompt(data_bytes):
    """
    Return True if any known '--More--' pager prompt appears in the bytes data.
    """
    if not data_bytes:
        return False
    for p in MORE_PROMPT_PATTERNS:
        if p in data_bytes:
            return True
    return False


def sanitize_prompt_line(line):
    """
    A simple helper to construct a regex that matches a typical FortiGate prompt.
    FortiGate prompts often look like: "hostname #", "hostname (config) #", "hostname >"
    We'll create a regex that looks for the hostname followed by space(s) and [#>].
    """
    # Escape regex characters in the line
    escaped = re.escape(line.strip())
    # If there's no visible prompt candidate, fallback to a generic prompt regex.
    if not escaped:
        return r'[>#]\s*$'
    # Build flexible regex: hostname (maybe with parentheses / words) then whitespace and prompt char
    # Example: my-fg600c #   or my-fg600c (global) #
    return escaped + r'[\s\S]{0,30}[#>]\s*$'  # allow up to 30 arbitrary chars between name and prompt char


# ---------- Main logic ----------
def main():
    parser = argparse.ArgumentParser(description='Run CLI commands on a FortiGate and collect outputs.')
    parser.add_argument('--host', required=True, help='FortiGate hostname or IP')
    parser.add_argument('--port', type=int, default=22, help='SSH port (default: 22)')
    parser.add_argument('--username', '-u', required=True, help='SSH username')
    parser.add_argument('--password', '-p', help='SSH password (omit to be prompted securely)')
    parser.add_argument('--commands', '-c', default='cli-commands.txt', help='File with CLI commands, one per line')
    parser.add_argument('--output', '-o', default='output-file.txt', help='File to write combined outputs to')
    parser.add_argument('--timeout', type=float, default=READ_TIMEOUT, help='Read timeout in seconds (default: 2.0)')
    args = parser.parse_args()

    host = args.host
    port = args.port
    username = args.username
    password = args.password if args.password is not None else getpass.getpass(f'Password for {username}@{host}: ')
    commands_file = args.commands
    output_file = args.output

    # Update constant-ish runtime values
    global READ_TIMEOUT
    READ_TIMEOUT = args.timeout

    # Read CLI commands to run
    try:
        with open(commands_file, 'r', encoding='utf-8') as f:
            commands = [line.rstrip('\n') for line in f if line.strip() and not line.strip().startswith('#')]
            # ignore blank lines and lines starting with '#' (comments)
    except FileNotFoundError:
        print(f'Commands file not found: {commands_file}', file=sys.stderr)
        sys.exit(2)

    if not commands:
        print('No commands to run (commands file empty or only comments).', file=sys.stderr)
        sys.exit(2)

    # Create SSH client
    ssh = paramiko.SSHClient()
    # Automatically add host keys from unknown servers (like ssh -o StrictHostKeyChecking=no).
    # For production security consider using known_hosts instead.
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        print(f'Connecting to {host}:{port} as {username} ...')
        ssh.connect(hostname=host, port=port, username=username, password=password, look_for_keys=False, allow_agent=False, timeout=10)
    except Exception as e:
        print(f'Failed to connect/login: {e}', file=sys.stderr)
        sys.exit(2)

    # Open an interactive shell so we can handle prompts and pagers
    chan = ssh.invoke_shell()
    chan.settimeout(READ_TIMEOUT)

    # Give the remote a moment to present the prompt
    time.sleep(0.5)

    # Read initial banner and prompt
    initial = b''
    # Read a bit to capture the prompt line. We'll use a longer initial read timeout.
    try:
        initial = read_until_prompt(chan, r'[#>]\s*$', timeout=3.0)
    except Exception:
        pass

    initial_decoded = initial.decode(errors='ignore')
    # Heuristic: find last non-empty line as the prompt line sample
    prompt_line = ''
    for l in reversed(initial_decoded.splitlines()):
        if l.strip():
            prompt_line = l.strip()
            break

    if prompt_line:
        prompt_regex = sanitize_prompt_line(prompt_line)
    else:
        # As a fallback, use generic prompt regex: prompt ends with # or >
        prompt_regex = r'[>#]\s*$'

    # We'll accumulate outputs into a list, then write at the end
    outputs = []
    outputs.append(f'-- Session start: {time.strftime("%Y-%m-%d %H:%M:%S")} --\n')
    outputs.append(f'Connected to {host} as {username}\n\n')
    # Also store initial banner for context
    if initial_decoded.strip():
        outputs.append('--- Initial banner/prompt ---\n')
        outputs.append(initial_decoded + '\n')
        outputs.append('--- End initial banner ---\n\n')

    # Optional: disable terminal line wrapping if FortiGate supports it. We'll not send commands blindly.
    # Execute each command sequentially
    for cmd in commands:
        outputs.append(f'\n=== Command: {cmd} ===\n')
        # Send command
        chan.send(cmd + '\n')
        time.sleep(COMMAND_DELAY)

        # We will iterate: read chunk, if a pager prompt detected send ' ' (space) to continue and keep reading,
        # otherwise stop when we detect the device prompt (using prompt_regex) or when we hit a safe timeout.
        collected = b''
        overall_start = time.time()
        # We'll allow up to a maximum overall time per command to avoid infinite loops
        max_command_time = 120.0  # seconds per command; adjust if you expect very long outputs

        while True:
            # Read available output (short timeout)
            chunk = b''
            try:
                # Non-blocking read: keep reading until no more data appears for READ_TIMEOUT
                chunk = read_until_prompt(chan, prompt_regex, timeout=READ_TIMEOUT)
            except Exception:
                # read_until_prompt handles timeouts internally; ignore exceptions
                chunk = b''

            if chunk:
                collected += chunk

            # If pager prompt detected, send space and continue reading
            if detect_more_prompt(collected):
                try:
                    # send single space to continue the pager
                    chan.send(' ')
                except Exception:
                    pass
                # small sleep to let the device send the next chunk
                time.sleep(0.15)
                # continue loop to read more
                continue

            # If prompt regex appears in collected data, we assume command finished
            try:
                if re.search(prompt_regex, collected.decode(errors='ignore')):
                    break
            except Exception:
                # decoding issue, break to avoid infinite loop
                pass

            # Timeout guard for this command
            if (time.time() - overall_start) > max_command_time:
                collected += b'\n[ERROR] command timed out after %.0f seconds\n' % max_command_time
                break

            # small sleep before next check
            time.sleep(0.1)

        # Decoded and append to outputs
        try:
            text = collected.decode('utf-8', errors='replace')
        except Exception:
            text = collected.decode('utf-8', errors='replace')
        outputs.append(text)
        outputs.append('\n=== End of command: %s ===\n' % cmd)

    outputs.append('\n-- Session end: %s --\n' % time.strftime('%Y-%m-%d %H:%M:%S'))

    # Clean up and close SSH
    try:
        chan.close()
    except Exception:
        pass
    try:
        ssh.close()
    except Exception:
        pass

    # Write everything to the output file
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(''.join(outputs))
    except Exception as e:
        print(f'Failed to write output file: {e}', file=sys.stderr)
        sys.exit(2)

    print(f'All done. Output written to: {output_file}')


if __name__ == '__main__':
    main()
