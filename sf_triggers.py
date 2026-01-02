#!/usr/bin/env python3
"""
Salesforce Apex Trigger Manager
Disables all Apex triggers in a Salesforce org and can restore them later.

Author: Ken Brill
Version: 1.0.0
License: MIT License
"""

import os
import sys
import json
import argparse
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

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
        if value and config.get(key) != value:            # Don't save production orgs as defaults
            if 'org' in key:
                try:
                    sf_cli = SalesforceCLI(value)
                    if not sf_cli.is_sandbox():
                        console.print(f"[dim]Skipping save of production org '{value}' to config[/dim]")
                        continue
                except Exception:
                    pass            config[key] = value
            changed = True
    if changed:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)

def check_triggers(target_org: str):
    """
    Query apex triggers and display active/inactive counts.
    """
    try:
        sf_cli = SalesforceCLI(target_org=target_org)
        if not sf_cli.is_sandbox():
            console.print(f"[bold red]✗ SAFETY CHECK FAILED[/bold red]")
            console.print(f"[red]The target org '{target_org}' is a PRODUCTION environment.[/red]")
            console.print(f"[yellow]Trigger operations are only allowed on sandbox environments.[/yellow]")
            raise RuntimeError(f"Cannot check triggers on production org '{target_org}'")
    except RuntimeError as e:
        if "SAFETY CHECK FAILED" in str(e) or "production org" in str(e):
            raise
        console.print(f"[yellow]⚠ Warning: Could not verify sandbox status: {e}[/yellow]")
        console.print(f"[yellow]Proceeding with caution...[/yellow]")
    
    console.print(f"\n[bold cyan]🔍 Checking Apex Triggers[/bold cyan]")
    console.print(f"[dim]Target Org: {target_org}[/dim]")
    
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task(f"[cyan]Querying apex triggers...", total=None)
            
            # Query for deployable triggers only (exclude managed package triggers)
            query = "SELECT Id, Name, Status, NamespacePrefix FROM ApexTrigger"
            query_result = sf_cli._execute_sf_command(['data', 'query', '--query', query, '--use-tooling-api'])
            
            progress.update(task, completed=True)
        
        records = query_result.get('result', {}).get('records', [])
        
        # Filter out managed package triggers (those with a NamespacePrefix)
        deployable_triggers = [r for r in records if not r.get('NamespacePrefix')]
        managed_triggers = [r for r in records if r.get('NamespacePrefix')]
        
        active_count = sum(1 for record in deployable_triggers if record.get('Status') == 'Active')
        inactive_count = sum(1 for record in deployable_triggers if record.get('Status') == 'Inactive')
        managed_active = sum(1 for record in managed_triggers if record.get('Status') == 'Active')
        
        console.print(f"\n[bold cyan]Apex Triggers Summary[/bold cyan]")
        table = Table(show_header=False, box=box.SIMPLE)
        table.add_row("Active (Deployable)", f"[green]{active_count}[/green]")
        table.add_row("Inactive (Deployable)", f"[dim]{inactive_count}[/dim]")
        table.add_row("Total (Deployable)", f"[cyan]{len(deployable_triggers)}[/cyan]")
        if managed_triggers:
            table.add_row("[dim]Managed Package Triggers[/dim]", f"[yellow]{len(managed_triggers)}[/yellow]")
            table.add_row("[dim]  - Active[/dim]", f"[dim]{managed_active}[/dim]")
        console.print(table)
        
    except RuntimeError as e:
        console.print(f"[bold red]✗ Error: {e}[/bold red]")
        raise
    except Exception as e:
        console.print(f"[bold red]✗ Unexpected error: {e}[/bold red]")
        raise

def show_banner():
    """Display the application banner."""
    title = Text()
    title.append("Apex Trigger Manager\n", style="bold cyan")
    title.append(f"Version {VERSION}\n", style="dim")
    title.append(f"Author: {AUTHOR}\n", style="green")
    title.append(f"Support: {REPO}", style="blue underline")
    
    console.print(Panel(title, box=box.DOUBLE, border_style="cyan", padding=(1, 2)))

class TriggerManager:
    def __init__(self, target_org: str, api_version: str = "58.0"):
        self.target_org = target_org
        self.api_version = api_version
        # Set working directory to ~/Sandcastle/apextriggers
        self.working_dir = Path.home() / "Sandcastle" / "apextriggers"
        self.manifest_dir = self.working_dir / "manifest"
        self.triggers_dir = self.working_dir / "force-app" / "main" / "default" / "triggers"
        self.state_file = self.working_dir / "trigger_state.json"
        self.package_xml = self.manifest_dir / "triggersPackage.xml"
        self.sf_cli = SalesforceCLI(target_org)
        
    def print(self, message: str, style: str = None):
        """Print with Rich markup."""
        console.print(message, style=style)
    
    def verify_sandbox(self) -> bool:
        """Verify that the target org is a sandbox."""
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("Verifying org is a sandbox", total=None)
                is_sandbox = self.sf_cli.is_sandbox()
                progress.update(task, completed=True)
            
            if not is_sandbox:
                raise RuntimeError(
                    f"Target org '{self.target_org}' is NOT a sandbox. "
                    "This script can only be run against sandbox orgs for safety."
                )
            
            self.print("[green]✓ Verified: Target org is a sandbox[/green]")
            return True
        except RuntimeError:
            raise  # Re-raise RuntimeError as-is
        except Exception as e:
            raise RuntimeError(f"Error verifying sandbox status: {e}") from e
            
    def setup_directories(self):
        """Create necessary directories if they don't exist."""
        self.working_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_dir.mkdir(exist_ok=True)
        self.triggers_dir.mkdir(parents=True, exist_ok=True)
        
        # Create sfdx-project.json if it doesn't exist
        sfdx_project_file = self.working_dir / "sfdx-project.json"
        if not sfdx_project_file.exists():
            sfdx_project = {
                "packageDirectories": [
                    {
                        "path": "force-app",
                        "default": True
                    }
                ],
                "name": "apex-trigger-manager",
                "namespace": "",
                "sfdcLoginUrl": "https://login.salesforce.com",
                "sourceApiVersion": self.api_version
            }
            with open(sfdx_project_file, 'w') as f:
                json.dump(sfdx_project, f, indent=2)
        
        # Create .forceignore if it doesn't exist
        forceignore_file = self.working_dir / ".forceignore"
        if not forceignore_file.exists():
            forceignore_content = """# List files or directories below to ignore them when running force:source:push, force:source:pull, and force:source:status
# More information: https://developer.salesforce.com/docs/atlas.en-us.sfdx_dev.meta/sfdx_dev/sfdx_dev_exclude_source.htm

**/*.dup
.sfdx
.vscode
"""
            with open(forceignore_file, 'w') as f:
                f.write(forceignore_content)
        
    def create_package_xml(self):
        """Create package.xml to retrieve all triggers."""
        package_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>*</members>
        <name>ApexTrigger</name>
    </types>
    <version>{self.api_version}</version>
</Package>'''
        
        with open(self.package_xml, 'w') as f:
            f.write(package_content)
        
    def run_sf_command(self, command: List[str], description: str = None) -> bool:
        """Execute Salesforce CLI command with progress indicator."""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task(description or "Running command", total=None)
            try:
                result = subprocess.run(
                    command,
                    check=True,
                    capture_output=True,
                    text=True,
                    cwd=str(self.working_dir)
                )
                progress.update(task, completed=True)
                return True
            except subprocess.CalledProcessError as e:
                progress.stop()
                self.print(f"\n[red]✗ Error: {e.stderr.strip()}[/red]")
                return False
            
    def retrieve_triggers(self) -> bool:
        """Retrieve all triggers from Salesforce org."""
        command = [
            "sf", "project", "retrieve", "start",
            "-x", "manifest/triggersPackage.xml",
            "--target-org", self.target_org,
            "--ignore-conflicts"
        ]
        return self.run_sf_command(command, f"Retrieving triggers from '{self.target_org}'")
        
    def get_trigger_metadata_files(self) -> List[Path]:
        """Get all trigger metadata files."""
        if not self.triggers_dir.exists():
            return []
        return list(self.triggers_dir.glob("*.trigger-meta.xml"))
        
    def read_trigger_status(self, meta_file: Path) -> str:
        """Read the current status of a trigger."""
        try:
            tree = ET.parse(meta_file)
            root = tree.getroot()
            # Handle namespace
            ns = {'ns': 'http://soap.sforce.com/2006/04/metadata'}
            status_elem = root.find('ns:status', ns)
            if status_elem is None:
                status_elem = root.find('status')
            return status_elem.text if status_elem is not None else "Unknown"
        except Exception as e:
            return "Unknown"
            
    def update_trigger_status(self, meta_file: Path, new_status: str) -> bool:
        """Update the status of a trigger in its metadata file."""
        try:
            tree = ET.parse(meta_file)
            root = tree.getroot()
            
            # Handle namespace
            ns = {'ns': 'http://soap.sforce.com/2006/04/metadata'}
            status_elem = root.find('ns:status', ns)
            if status_elem is None:
                status_elem = root.find('status')
                
            if status_elem is not None:
                status_elem.text = new_status
                tree.write(meta_file, encoding='utf-8', xml_declaration=True)
                return True
            return False
        except Exception as e:
            return False
            
    def disable_triggers(self) -> Dict[str, str]:
        """Disable all triggers and track which ones were changed."""
        changed_triggers = {}
        meta_files = self.get_trigger_metadata_files()
        
        if not meta_files:
            self.print("[yellow]⚠ No trigger metadata files found[/yellow]")
            return changed_triggers
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task = progress.add_task("Processing triggers", total=len(meta_files))
            
            for meta_file in meta_files:
                trigger_name = meta_file.stem.replace('.trigger-meta', '')
                original_status = self.read_trigger_status(meta_file)
                
                if original_status == "Active":
                    if self.update_trigger_status(meta_file, "Inactive"):
                        changed_triggers[trigger_name] = original_status
                
                progress.advance(task)
                
        return changed_triggers
        
    def enable_triggers(self, state: Dict[str, str]):
        """Re-enable triggers that were previously disabled."""
        meta_files = self.get_trigger_metadata_files()
        restored_count = 0
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task = progress.add_task("Restoring triggers", total=len(state))
            
            for meta_file in meta_files:
                trigger_name = meta_file.stem.replace('.trigger-meta', '')
                
                if trigger_name in state:
                    original_status = state[trigger_name]
                    if self.update_trigger_status(meta_file, original_status):
                        restored_count += 1
                    progress.advance(task)
                    
    def deploy_triggers(self) -> bool:
        """Deploy modified triggers back to Salesforce org."""
        command = [
            "sf", "project", "deploy", "start",
            "-x", "manifest/triggersPackage.xml",
            "--target-org", self.target_org
        ]
        return self.run_sf_command(command, f"Deploying triggers to '{self.target_org}'")
        
    def save_state(self, state: Dict[str, str], force: bool = False):
        """Save the state of changed triggers."""
        if self.state_file.exists() and not force:
            self.print("\n[yellow]⚠ State file already exists - preserving it[/yellow]")
            self.print("  Use --reset to overwrite")
            return
            
        with open(self.state_file, 'w') as f:
            json.dump(state, f, indent=2)
        
    def load_state(self) -> Dict[str, str]:
        """Load the previously saved state."""
        if not self.state_file.exists():
            return {}
            
        with open(self.state_file, 'r') as f:
            return json.load(f)
    
    def cleanup_triggers(self):
        """Remove all downloaded trigger files."""
        import shutil
        if self.triggers_dir.exists():
            shutil.rmtree(self.triggers_dir)
            self.triggers_dir.mkdir(parents=True)
            self.print("[green]✓ Cleaned up trigger files[/green]")
            
    def show_summary(self, changed_triggers: Dict[str, str], mode: str):
        """Show summary of changes."""
        if mode == "disable":
            table = Table(title="Disabled Triggers", show_header=True, header_style="bold magenta")
            table.add_column("Trigger Name", style="cyan")
            table.add_column("Previous Status", style="green")
            
            for trigger, status in changed_triggers.items():
                table.add_row(trigger, status)
            
            console.print(table)
            console.print(f"\n[green]✓ Disabled {len(changed_triggers)} trigger(s)[/green]")
        else:
            console.print(f"\n[green]✓ Restored {len(changed_triggers)} trigger(s)[/green]")

def main():
    show_banner()
    
    config = load_config()
    saved_target_org = config.get("target_org")
    target_org_help = f"Salesforce org alias (default: {saved_target_org})" if saved_target_org else "Salesforce org alias (required on first run)"
    
    parser = argparse.ArgumentParser(
        description="Manage Apex Trigger activation in Salesforce"
    )
    parser.add_argument(
        "--target-org",
        default=None,
        help=target_org_help
    )
    parser.add_argument(
        "--disable",
        action="store_true",
        help="Disable all active triggers (default behavior)"
    )
    parser.add_argument(
        "--enable",
        action="store_true",
        help="Re-enable previously disabled triggers"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset: clean up all files and allow fresh disable operation"
    )
    parser.add_argument(
        "--api-version",
        default="58.0",
        help="Salesforce API version (default: 58.0)"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check and display active/inactive trigger counts"
    )
    
    args = parser.parse_args()
    target_org = args.target_org or saved_target_org

    if not target_org:
        console.print("[red]✗ Provide --target-org at least once to establish a default[/red]")
        sys.exit(1)

    if args.target_org:
        persist_config({"target_org": args.target_org})

    manager = TriggerManager(target_org, args.api_version)
    
    # Handle check mode
    if args.check:
        try:
            check_triggers(target_org)
            console.print()
            sys.exit(0)
        except Exception:
            sys.exit(1)
    
    console.print(f"\n[cyan]Mode: [yellow]{'RESTORE' if args.enable else 'DISABLE'}[/yellow][/cyan] | Org: [magenta]{target_org}[/magenta]\n")
    
    manager.setup_directories()
    
    # Verify sandbox before any operations
    try:
        manager.verify_sandbox()
    except RuntimeError as e:
        console.print(f"\n[red]✗ {e}[/red]")
        sys.exit(1)
    
    if args.enable:
        # Restore triggers
        state = manager.load_state()
        
        if not state:
            manager.print("[red]✗ No triggers to restore[/red]")
            sys.exit(1)
        
        manager.print(f"\nFound [cyan]{len(state)}[/cyan] trigger(s) to restore")
        
        # Retrieve current state
        manager.create_package_xml()
        if not manager.retrieve_triggers():
            sys.exit(1)
            
        # Enable triggers
        manager.enable_triggers(state)
        
        # Deploy
        if manager.deploy_triggers():
            manager.show_summary(state, "restore")
            manager.state_file.unlink()
            manager.print("[dim]State file cleaned up[/dim]")
            # Auto-cleanup trigger files after successful restore
            manager.cleanup_triggers()
        else:
            manager.print("[red]✗ Failed to deploy[/red]")
            sys.exit(1)
    else:
        # Disable triggers
        
        # Handle reset - clean up everything first
        if args.reset:
            if manager.state_file.exists():
                manager.state_file.unlink()
                manager.print("[yellow]Removed existing state file[/yellow]")
            manager.cleanup_triggers()
        
        # Check if state file exists and --reset not used
        if manager.state_file.exists() and not args.reset:
            manager.print("\n[yellow]⚠ State file already exists[/yellow]")
            manager.print("  Use --enable to restore or --reset to start fresh")
            sys.exit(1)
        
        manager.create_package_xml()
        
        # Retrieve triggers
        if not manager.retrieve_triggers():
            sys.exit(1)
            
        # Disable triggers and track changes
        changed = manager.disable_triggers()
        
        if not changed:
            manager.print("[yellow]⚠ No active triggers found[/yellow]")
            sys.exit(0)
        
        # Save state
        manager.save_state(changed, force=args.reset)
        
        # Show what will be disabled
        manager.show_summary(changed, "disable")
        
        # Deploy changes
        if manager.deploy_triggers():
            manager.print("\n[green]✓ Successfully disabled all active triggers![/green]")
        else:
            manager.print("[red]✗ Failed to deploy[/red]")
            sys.exit(1)

if __name__ == "__main__":
    main()