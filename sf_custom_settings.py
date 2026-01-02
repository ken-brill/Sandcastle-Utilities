#!/usr/bin/env python3
"""
Salesforce Custom Setting Manager
Manages checkbox fields in ESB Events Controller custom setting.

Author: Ken Brill
Version: 1.0.0
License: MIT License
"""

import os
import sys
import json
import argparse
import time
import select
import subprocess
import threading
from pathlib import Path
from typing import Dict, List
from datetime import datetime

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

# Notification support
SYSTEM = sys.platform  # 'darwin' for macOS, 'linux' for Linux, 'win32' for Windows

# Windows-specific imports
if SYSTEM == 'win32':
    import ctypes

# Import the Salesforce CLI wrapper
try:
    from cli.salesforce_cli import SalesforceCLI
except ImportError as e:
    raise RuntimeError(
        "Required module 'cli.salesforce_cli' not found. "
        "Make sure the cli/salesforce_cli.py file exists in your project."
    ) from e

console = Console()

VERSION = "1.0.0"
AUTHOR = "Ken Brill"
REPO = "https://github.com/ken-brill/Sandcastle-Utilities"
CONFIG_FILE = Path.home() / "Sandcastle" / "config.json"
STATE_FILE = Path.home() / "Sandcastle" / "custom_setting_state.json"

# Custom Setting API Name
CUSTOM_SETTING_NAME = "ESB_Events_Controller__c"

def wait_with_interrupt(seconds: int) -> bool:
    """
    Wait for specified seconds, checking for keyboard input.
    Returns True if a key was pressed, False if timeout occurred.
    """
    try:
        # Try using select for Unix/Linux/macOS
        if select.select([sys.stdin], [], [], seconds)[0]:
            # A key was pressed
            sys.stdin.read(1)
            return True
        return False
    except Exception:
        # Fallback for Windows or if select fails
        # Just do a regular sleep
        time.sleep(seconds)
        return False

def play_annoying_alert():
    """Play an annoying alert sound."""
    # Terminal bell (works everywhere)
    for _ in range(3):
        sys.stdout.write('\a')
        sys.stdout.flush()
        time.sleep(0.2)
    
    # Try to play system sound on macOS
    try:
        subprocess.Popen(
            ['afplay', '/System/Library/Sounds/Alarm.aiff'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except (FileNotFoundError, OSError):
        # Sound file not available, just use the bell
        pass

def show_warning_loop():
    """Show the annoying warning that appears in the loop."""
    warning_text = Text()
    warning_text.append("⚠️  CUSTOM SETTING CHECKBOXES ARE CHECKED ⚠️\n", style="bold red")
    warning_text.append("Uncheck them as soon as possible!\n", style="bold yellow")
    warning_text.append("Run: ", style="dim")
    warning_text.append("./sf_custom_settings.py --uncheck-all\n\n", style="bold cyan")
    warning_text.append("Or press ANY KEY to dismiss this alert and get the option to uncheck", style="dim italic")
    
    console.print(Panel(warning_text, border_style="red", box=box.DOUBLE, padding=(1, 2)))

def show_dialog_box():
    """Show a cross-platform dialog box using native platform APIs."""
    def _show():
        try:
            if SYSTEM == 'darwin':  # macOS
                # Use osascript for native macOS dialog
                dialog_script = '''
                display dialog "⚠️  CHECKBOXES ARE CHECKED!\\n\\nCustom Setting checkboxes are still enabled.\\nUncheck them immediately!\\n\\nRun: ./sf_custom_settings.py --uncheck-all" with title "ESB Events Controller Warning" buttons {"I'll uncheck them now"} default button 1 with icon caution giving up after 10
                '''
                subprocess.run(
                    ['osascript', '-e', dialog_script],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False
                )
            
            elif SYSTEM == 'win32':  # Windows
                # Use ctypes for native Windows MessageBox (no dependencies!)
                MB_OK = 0x0
                MB_ICONWARNING = 0x30
                MB_TOPMOST = 0x40000
                
                title = "ESB Events Controller Warning"
                message = (
                    "⚠️  CHECKBOXES ARE CHECKED!\n\n"
                    "Custom Setting checkboxes are still enabled.\n"
                    "Uncheck them immediately!\n\n"
                    "Run: ./sf_custom_settings.py --uncheck-all"
                )
                
                ctypes.windll.user32.MessageBoxW(
                    0,
                    message,
                    title,
                    MB_OK | MB_ICONWARNING | MB_TOPMOST
                )
        
        except Exception:
            # Dialog not available, skip silently
            pass
    
    # Run in a separate thread so it doesn't block
    thread = threading.Thread(target=_show, daemon=True)
    thread.start()
    # Give the dialog a moment to appear
    time.sleep(0.5)

def send_voice_alert():
    """Send a voice alert using platform-specific text-to-speech."""
    try:
        if SYSTEM == 'darwin':  # macOS
            subprocess.Popen(
                ['say', '-v', 'Samantha', 'Warning! Custom Setting checkboxes are checked!'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        elif SYSTEM == 'win32':  # Windows
            # Use PowerShell's speech synthesizer
            ps_command = '''
            Add-Type -AssemblyName System.Speech;
            $speak = New-Object System.Speech.Synthesis.SpeechSynthesizer;
            $speak.Speak("Warning! Custom Setting checkboxes are checked!")
            '''
            subprocess.Popen(
                ['powershell', '-Command', ps_command],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
    except (FileNotFoundError, OSError):
        # Voice not available, skip silently
        pass

def send_desktop_notification():
    """Send a desktop notification reminder with voice alert and dialog box."""
    try:
        # Voice alert (platform-specific)
        send_voice_alert()
        
        # Dialog box (native platform APIs - no dependencies!)
        show_dialog_box()
        
        console.print("[dim]🔊 Sent voice alert + dialog box[/dim]")
    
    except Exception as e:
        console.print(f"[dim]⚠️  Could not send notification: {e}[/dim]")

def load_config() -> Dict[str, str]:
    """Load persisted defaults for org aliases."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def persist_config(updates: Dict[str, str]):
    """Persist provided org aliases as the new defaults."""
    config = load_config()
    changed = False
    for key, value in updates.items():
        if value and config.get(key) != value:
            # Don't save production orgs as defaults
            if 'org' in key:
                try:
                    sf_cli = SalesforceCLI(value)
                    if not sf_cli.is_sandbox():
                        console.print(f"[dim]Skipping save of production org '{value}' to config[/dim]")
                        continue
                except Exception:
                    pass
            config[key] = value
            changed = True
    if changed:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)

def show_banner():
    """Display the application banner."""
    title = Text()
    title.append("Custom Setting Manager\n", style="bold cyan")
    title.append(f"Version {VERSION}\n", style="dim")
    title.append(f"Author: {AUTHOR}\n", style="green")
    title.append(f"Support: {REPO}", style="blue underline")
    
    console.print(Panel(title, box=box.DOUBLE, border_style="cyan", padding=(1, 2)))

class CustomSettingManager:
    def __init__(self, target_org: str):
        self.target_org = target_org
        self.sf_cli = SalesforceCLI(target_org)
        
    def verify_sandbox(self) -> bool:
        """Verify sandbox status and prompt for production confirmation if needed."""
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("Verifying org type", total=None)
                is_sandbox = self.sf_cli.is_sandbox()
                progress.update(task, completed=True)
            
            if not is_sandbox:
                # Production org detected - require user confirmation
                console.print("\n[bold red]⚠️  WARNING: THIS IS A PRODUCTION ORG ⚠️[/bold red]")
                console.print("[yellow]You are about to run this script against a PRODUCTION organization![/yellow]\n")
                console.print("[dim]This will enable/disable custom setting checkboxes in your LIVE environment.[/dim]\n")
                
                # Require explicit confirmation
                response = console.input(
                    "[bold red]Proceed with production org? (y/n): [/bold red]"
                ).strip().lower()
                
                if response not in ['y', 'yes']:
                    console.print("[yellow]Operation cancelled.[/yellow]\n")
                    sys.exit(0)
                
                console.print("[yellow]Proceeding with PRODUCTION org...[/yellow]\n")
            else:
                console.print("[green]✓ Verified: Target org is a sandbox[/green]")
            
            return True
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Error verifying org status: {e}") from e
    
    def get_checkbox_fields(self) -> List[str]:
        """Get all checkbox fields from the custom setting."""
        console.print(f"\n[cyan]Describing {CUSTOM_SETTING_NAME}...[/cyan]")
        
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("Getting field information", total=None)
                
                # Use sobject describe to get field information
                result = self.sf_cli._execute_sf_command([
                    'sobject', 'describe',
                    '--sobject', CUSTOM_SETTING_NAME
                ])
                
                progress.update(task, completed=True)
            
            fields = result.get('result', {}).get('fields', [])
            
            # Filter for checkbox fields only
            checkbox_fields = [
                field['name'] 
                for field in fields 
                if field.get('type') == 'boolean' and field.get('updateable', True)
            ]
            
            if not checkbox_fields:
                raise RuntimeError(f"No updateable checkbox fields found in {CUSTOM_SETTING_NAME}")
            
            console.print(f"[green]✓ Found {len(checkbox_fields)} checkbox field(s)[/green]")
            return checkbox_fields
            
        except Exception as e:
            raise RuntimeError(f"Error describing custom setting: {e}") from e
    
    def get_custom_setting_record(self) -> Dict:
        """Get the custom setting record."""
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("Querying custom setting", total=None)
                
                query = f"SELECT Id FROM {CUSTOM_SETTING_NAME} LIMIT 1"
                result = self.sf_cli._execute_sf_command([
                    'data', 'query',
                    '--query', query
                ])
                
                progress.update(task, completed=True)
            
            records = result.get('result', {}).get('records', [])
            
            if not records:
                raise RuntimeError(
                    f"No record found in {CUSTOM_SETTING_NAME}. "
                    "Please create a record first in your org."
                )
            
            return records[0]
            
        except Exception as e:
            raise RuntimeError(f"Error querying custom setting: {e}") from e
    
    def check_status(self, checkbox_fields: List[str]) -> Dict[str, bool]:
        """Check current status of all checkbox fields."""
        console.print(f"\n[cyan]Checking current checkbox status...[/cyan]")
        
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("Querying checkbox values", total=None)
                
                fields_str = ", ".join(['Id'] + checkbox_fields)
                query = f"SELECT {fields_str} FROM {CUSTOM_SETTING_NAME} LIMIT 1"
                
                result = self.sf_cli._execute_sf_command([
                    'data', 'query',
                    '--query', query
                ])
                
                progress.update(task, completed=True)
            
            records = result.get('result', {}).get('records', [])
            
            if not records:
                raise RuntimeError(f"No record found in {CUSTOM_SETTING_NAME}")
            
            record = records[0]
            
            # Build status dictionary
            status = {}
            for field in checkbox_fields:
                status[field] = record.get(field, False)
            
            return status
            
        except Exception as e:
            raise RuntimeError(f"Error checking status: {e}") from e
    
    def display_status(self, status: Dict[str, bool]):
        """Display the current checkbox status."""
        console.print(f"\n[bold cyan]Custom Setting Status: {CUSTOM_SETTING_NAME}[/bold cyan]")
        
        checked_count = sum(1 for v in status.values() if v)
        unchecked_count = len(status) - checked_count
        
        table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE)
        table.add_column("Field Name", style="cyan")
        table.add_column("Status", justify="center")
        
        for field, is_checked in sorted(status.items()):
            status_str = "[green]✓ Checked[/green]" if is_checked else "[dim]☐ Unchecked[/dim]"
            table.add_row(field, status_str)
        
        console.print(table)
        
        summary = Table(show_header=False, box=box.SIMPLE)
        summary.add_row("Checked", f"[green]{checked_count}[/green]")
        summary.add_row("Unchecked", f"[dim]{unchecked_count}[/dim]")
        summary.add_row("Total", f"[cyan]{len(status)}[/cyan]")
        console.print(summary)
    
    def update_checkboxes(self, checkbox_fields: List[str], check_all: bool) -> Dict[str, bool]:
        """Update all checkbox fields to checked or unchecked."""
        # First get current status
        current_status = self.check_status(checkbox_fields)
        
        # Get the record ID
        record = self.get_custom_setting_record()
        record_id = record['Id']
        
        # Build update data
        update_data = {field: check_all for field in checkbox_fields}
        
        console.print(f"\n[cyan]{'Checking' if check_all else 'Unchecking'} all checkboxes...[/cyan]")
        
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("Updating custom setting", total=None)
                
                # Build the update command with key=value pairs
                values_str = " ".join([f"{k}={str(v).lower()}" for k, v in update_data.items()])
                
                self.sf_cli._execute_sf_command([
                    'data', 'update', 'record',
                    '--sobject', CUSTOM_SETTING_NAME,
                    '--record-id', record_id,
                    '--values', values_str
                ])
                
                progress.update(task, completed=True)
            
            console.print(f"[green]✓ Successfully {'checked' if check_all else 'unchecked'} {len(checkbox_fields)} checkbox field(s)[/green]")
            
            return current_status
            
        except Exception as e:
            raise RuntimeError(f"Error updating custom setting: {e}") from e
    
    def save_state(self, state: Dict[str, bool]):
        """Save the original state of checkboxes."""
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, 'w') as f:
            json.dump({
                'org': self.target_org,
                'custom_setting': CUSTOM_SETTING_NAME,
                'checkboxes': state
            }, f, indent=2)
        console.print(f"[dim]Saved original state to {STATE_FILE}[/dim]")
    
    def load_state(self) -> Dict[str, bool]:
        """Load the previously saved state."""
        if not STATE_FILE.exists():
            raise RuntimeError("No saved state found. Run with --uncheck-all first.")
        
        with open(STATE_FILE, 'r') as f:
            data = json.load(f)
        
        if data.get('org') != self.target_org:
            raise RuntimeError(
                f"State file is for org '{data.get('org')}' but you're targeting '{self.target_org}'"
            )
        
        return data.get('checkboxes', {})
    
    def restore_state(self, checkbox_fields: List[str]):
        """Restore checkboxes to their original state."""
        console.print(f"\n[cyan]Restoring original state...[/cyan]")
        
        # Load saved state
        saved_state = self.load_state()
        
        # Get record ID
        record = self.get_custom_setting_record()
        record_id = record['Id']
        
        # Build update data from saved state
        update_data = {field: saved_state.get(field, False) for field in checkbox_fields}
        
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("Restoring checkboxes", total=None)
                
                # Build the update command with key=value pairs
                values_str = " ".join([f"{k}={str(v).lower()}" for k, v in update_data.items()])
                
                self.sf_cli._execute_sf_command([
                    'data', 'update', 'record',
                    '--sobject', CUSTOM_SETTING_NAME,
                    '--record-id', record_id,
                    '--values', values_str
                ])
                
                progress.update(task, completed=True)
            
            console.print(f"[green]✓ Successfully restored {len(checkbox_fields)} checkbox field(s) to original state[/green]")
            
            # Clean up state file
            STATE_FILE.unlink()
            console.print(f"[dim]Removed state file[/dim]")
            
        except Exception as e:
            raise RuntimeError(f"Error restoring state: {e}") from e

def main():
    show_banner()
    
    config = load_config()
    saved_target_org = config.get("target_org")
    target_org_help = f"Salesforce org alias (default: {saved_target_org})" if saved_target_org else "Salesforce org alias (required on first run)"
    
    parser = argparse.ArgumentParser(
        description=f"Manage checkbox fields in {CUSTOM_SETTING_NAME} custom setting"
    )
    parser.add_argument(
        "--target-org",
        default=None,
        help=target_org_help
    )
    parser.add_argument(
        "--check-all",
        action="store_true",
        help="Check all checkbox fields and enter annoying reminder loop"
    )
    parser.add_argument(
        "--uncheck-all",
        action="store_true",
        help="Uncheck all checkbox fields and save original state"
    )
    parser.add_argument(
        "--restore",
        action="store_true",
        help="Restore checkboxes to their original state"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Display current checkbox status without making changes"
    )
    parser.add_argument(
        "--test-dialog",
        action="store_true",
        help="Test desktop notification (debug only)"
    )
    
    args = parser.parse_args()
    
    # Handle test-dialog
    if args.test_dialog:
        console.print("\n[cyan]Testing desktop notification...[/cyan]\n")
        send_desktop_notification()
        console.print("\n[green]Test complete! (waiting for dialog to display...)[/green]\n")
        # Wait for dialog to finish (10 second auto-dismiss + buffer)
        time.sleep(12)
        sys.exit(0)
    target_org = args.target_org or saved_target_org

    if not target_org:
        console.print("[red]✗ Provide --target-org at least once to establish a default[/red]")
        sys.exit(1)

    if args.target_org:
        persist_config({"target_org": args.target_org})
    
    # Validate mode selection (exclude test-dialog from count)
    mode_count = sum([args.check_all, args.uncheck_all, args.restore, args.status])
    if mode_count == 0:
        console.print("[red]✗ Please specify a mode: --check-all, --uncheck-all, --restore, or --status[/red]")
        sys.exit(1)
    elif mode_count > 1:
        console.print("[red]✗ Please specify only one mode at a time[/red]")
        sys.exit(1)
    
    manager = CustomSettingManager(target_org)
    
    console.print(f"\n[cyan]Target Org: [magenta]{target_org}[/magenta][/cyan]")
    console.print(f"[cyan]Custom Setting: [yellow]{CUSTOM_SETTING_NAME}[/yellow][/cyan]\n")
    
    # Verify sandbox before any operations
    try:
        manager.verify_sandbox()
    except RuntimeError as e:
        console.print(f"\n[red]✗ {e}[/red]")
        sys.exit(1)
    
    try:
        # Get checkbox fields
        checkbox_fields = manager.get_checkbox_fields()
        
        if args.status:
            # Just display status
            status = manager.check_status(checkbox_fields)
            manager.display_status(status)
            
        elif args.check_all:
            # Check all boxes
            original_state = manager.update_checkboxes(checkbox_fields, True)
            manager.save_state(original_state)
            
            # Show new status
            new_status = manager.check_status(checkbox_fields)
            manager.display_status(new_status)
            
            # Enter the annoying reminder loop
            console.print("\n[bold yellow]⚠️  Entering reminder loop - Press any key to exit loop[/bold yellow]\n")
            time.sleep(2)
            
            loop_count = 0
            notification_countdown = 0
            
            while True:
                # Wait 30 seconds, return True if key pressed
                key_pressed = wait_with_interrupt(30)
                notification_countdown += 30
                loop_count += 1
                
                # Send notification every 60 seconds
                if notification_countdown >= 60:
                    send_desktop_notification()
                    notification_countdown = 0
                
                if key_pressed:
                    # User pressed a key
                    console.clear()
                    console.print("\n[bold green]You pressed a key![/bold green]\n")
                    
                    # Ask if they want to uncheck
                    response = console.input("[bold cyan]Do you want to UNCHECK all the boxes now? (yes/no): [/bold cyan]").strip().lower()
                    
                    if response in ['yes', 'y']:
                        console.print("\n[green]Unchecking all boxes...[/green]")
                        manager.update_checkboxes(checkbox_fields, False)
                        manager.save_state(original_state)  # Update saved state
                        
                        # Show restored status
                        new_status = manager.check_status(checkbox_fields)
                        manager.display_status(new_status)
                        
                        console.print("\n[green]✓ Successfully unchecked and exiting reminder loop![/green]\n")
                        break
                    else:
                        console.print("\n[yellow]Returning to reminder loop...[/yellow]\n")
                        time.sleep(1)
                else:
                    # Timeout - show annoying alert
                    play_annoying_alert()
                    console.clear()
                    show_warning_loop()
                    console.print(f"\n[dim]Reminder #{loop_count}[/dim]\n")
            
        elif args.uncheck_all:
            # Uncheck all boxes
            original_state = manager.update_checkboxes(checkbox_fields, False)
            manager.save_state(original_state)
            
            # Show new status
            new_status = manager.check_status(checkbox_fields)
            manager.display_status(new_status)
            
        elif args.restore:
            # Restore original state
            manager.restore_state(checkbox_fields)
            
            # Show restored status
            restored_status = manager.check_status(checkbox_fields)
            manager.display_status(restored_status)
        
        console.print()
        
    except RuntimeError as e:
        console.print(f"\n[red]✗ Error: {e}[/red]")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print(f"\n[yellow]Interrupted by user[/yellow]\n")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[red]✗ Unexpected error: {e}[/red]")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        sys.exit(1)

if __name__ == "__main__":
    main()
