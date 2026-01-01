#!/usr/bin/env python3
import subprocess
import xml.etree.ElementTree as ET
import shutil
from pathlib import Path
import os
import argparse
import json
import sys
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich import box
from rich.text import Text

# Import SalesforceCLI for sandbox verification
sys.path.insert(0, str(Path(__file__).parent))
from cli.salesforce_cli import SalesforceCLI

console = Console()

VERSION = "1.0.0"
AUTHOR = "Ken Brill"
REPO = "https://github.com/ken-brill/Sandcastle-Utilities"
CONFIG_FILE = Path.home() / "Sandcastle" / "config.json"

def load_config() -> dict:
    """Load persisted defaults for org aliases."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def persist_config(updates: dict):
    """Persist provided org aliases as the new defaults."""
    config = load_config()
    changed = False
    for key, value in updates.items():
        if value and config.get(key) != value:
            config[key] = value
            changed = True
    if changed:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)

def show_banner():
    """Display the application banner."""
    title = Text()
    title.append("Salesforce Validation Rule Manager\n", style="bold cyan")
    title.append(f"Version {VERSION}\n", style="dim")
    title.append(f"Author: {AUTHOR}\n", style="green")
    title.append(f"Support: {REPO}", style="blue underline")
    
    console.print(Panel(title, box=box.DOUBLE, border_style="cyan", padding=(1, 2)))

def run_sf_command(command_args, cwd=None):
    """Executes a Salesforce CLI command and returns its JSON output."""
    full_command = ['sf'] + command_args + ['--json']
    try:
        result = subprocess.run(
            full_command,
            capture_output=True,
            text=True,
            check=False,
            cwd=cwd
        )
        
        json_output = {}
        if result.stdout:
            try:
                json_output = json.loads(result.stdout)
            except json.JSONDecodeError:
                console.print(f"[yellow]⚠ Warning: SF CLI output was not valid JSON[/yellow]")

        if result.returncode != 0 or json_output.get('status') != 0:
            error_message = json_output.get('message', f'Unknown error. STDERR: {result.stderr}')
            raise RuntimeError(f"SF CLI command failed: {error_message}")
        
        return json_output
    except FileNotFoundError:
        raise RuntimeError("Salesforce CLI ('sf') not found. Please ensure it is installed and in your PATH.")
    except Exception as e:
        raise RuntimeError(f"An unexpected error occurred: {e}")

def manage_validation_rules_in_temp_project(target_org, sobject_name, mode, source_org=None):
    """
    Disable, enable, or sync validation rules for a specific sObject using a temporary SFDX project.
    """
    # Verify target org is a sandbox before proceeding
    try:
        sf_cli = SalesforceCLI(target_org=target_org)
        if not sf_cli.is_sandbox():
            console.print(f"[bold red]✗ SAFETY CHECK FAILED[/bold red]")
            console.print(f"[red]The target org '{target_org}' is a PRODUCTION environment.[/red]")
            console.print(f"[yellow]Validation rule operations are only allowed on sandbox environments.[/yellow]")
            raise RuntimeError(f"Cannot perform {mode} operation on production org '{target_org}'")
        console.print(f"[dim]✓ Verified: '{target_org}' is a sandbox[/dim]")
    except RuntimeError as e:
        if "SAFETY CHECK FAILED" in str(e) or "production org" in str(e):
            raise
        # If we can't verify (e.g., connection issue), warn but don't block
        console.print(f"[yellow]⚠ Warning: Could not verify sandbox status: {e}[/yellow]")
        console.print(f"[yellow]Proceeding with caution...[/yellow]")
    
    temp_sfdx_project_dir = Path.home() / 'Sandcastle' / 'MetadataCache'
    
    # Create title based on mode
    mode_title = {
        'disable': f'🔒 Disabling Validation Rules',
        'enable': f'✅ Enabling Validation Rules', 
        'sync': f'🔄 Syncing Validation Rules'
    }
    
    console.print(f"\n[bold cyan]{mode_title.get(mode, mode.capitalize())}[/bold cyan]")
    console.print(f"[dim]Object: {sobject_name} | Target Org: {target_org}[/dim]")
    if mode == 'sync':
        console.print(f"[dim]Source Org: {source_org}[/dim]")

    try:
        project_root = temp_sfdx_project_dir
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            
            # Handle enable mode
            if mode == 'enable':
                if not project_root.exists():
                    console.print("[red]✗ Error: SandcastleMetadata directory not found[/red]")
                    console.print("[yellow]Run with --mode=disable first to create backups[/yellow]")
                    return
                
            # Handle sync mode    
            elif mode == 'sync':
                if not source_org:
                    raise RuntimeError("--source-org is required for sync mode")
                
                task = progress.add_task("[cyan]Setting up project...", total=100)
                
                if project_root.exists():
                    shutil.rmtree(project_root)
                progress.update(task, advance=20)
                
                original_cwd = os.getcwd()
                os.chdir(Path.home())
                try:
                    run_sf_command(['project', 'generate', '--name', 'SandcastleMetadata'])
                finally:
                    os.chdir(original_cwd)
                progress.update(task, advance=30)
                
                if not project_root.exists():
                    raise RuntimeError(f"SFDX project not created at {project_root}")
                
                progress.update(task, description=f"[cyan]Retrieving from {source_org}...", advance=20)
                retrieve_command = [
                    'project', 'retrieve', 'start',
                    '--metadata', f'CustomObject:{sobject_name}',
                    '--target-org', source_org,
                    '--wait', '20'
                ]
                run_sf_command(retrieve_command, cwd=str(project_root))
                progress.update(task, advance=30)
                
                validation_rules_path = project_root / "force-app" / "main" / "default" / "objects" / sobject_name / "validationRules"
                if not validation_rules_path.exists() or not list(validation_rules_path.glob('*.validationRule-meta.xml')):
                    console.print(f"[yellow]ℹ No validation rules found in {source_org}[/yellow]")
                    return
                
                # Clean up non-validation-rule files
                objects_path = project_root / "force-app" / "main" / "default" / "objects" / sobject_name
                fields_path = objects_path / "fields"
                if fields_path.exists():
                    shutil.rmtree(fields_path)
                
                for item in objects_path.iterdir():
                    if item.name != "validationRules":
                        if item.is_file():
                            item.unlink()
                        elif item.is_dir():
                            shutil.rmtree(item)
                
                progress.update(task, completed=100)
                
            # Handle disable mode
            else:
                task = progress.add_task("[cyan]Setting up project...", total=100)
                
                if project_root.exists():
                    shutil.rmtree(project_root)
                progress.update(task, advance=20)
                
                original_cwd = os.getcwd()
                os.chdir(Path.home())
                try:
                    run_sf_command(['project', 'generate', '--name', 'SandcastleMetadata'])
                finally:
                    os.chdir(original_cwd)
                progress.update(task, advance=30)
                
                if not project_root.exists():
                    raise RuntimeError(f"SFDX project not created at {project_root}")
                
                progress.update(task, description=f"[cyan]Retrieving from {target_org}...", advance=20)
                retrieve_command = [
                    'project', 'retrieve', 'start',
                    '--metadata', f'CustomObject:{sobject_name}',
                    '--target-org', target_org,
                    '--wait', '20'
                ]
                run_sf_command(retrieve_command, cwd=str(project_root))
                progress.update(task, advance=30, completed=100)

        validation_rules_path = project_root / "force-app" / "main" / "default" / "objects" / sobject_name / "validationRules"
        
        if mode == 'disable' and not validation_rules_path.exists():
            console.print(f"[yellow]ℹ No validation rules found in {target_org}[/yellow]")
            return

        # Process based on mode
        if mode == 'disable':
            original_rules_dir = project_root / "original_validation_rules"
            original_rules_dir.mkdir(exist_ok=True)
            
            rule_files = list(validation_rules_path.glob('*.validationRule-meta.xml'))
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console
            ) as progress:
                task = progress.add_task("[cyan]Processing validation rules...", total=len(rule_files))
                
                modified_count = 0
                skipped_count = 0
                
                for rule_file in rule_files:
                    # Backup
                    shutil.copy(rule_file, original_rules_dir)
                    
                    # Parse and modify
                    tree = ET.parse(rule_file)
                    root = tree.getroot()
                    ns = {'sf': 'http://soap.sforce.com/2006/04/metadata'}
                    ET.register_namespace('', 'http://soap.sforce.com/2006/04/metadata')
                    
                    active_element = root.find('sf:active', ns)
                    if active_element is None:
                        active_element = root.find('active')
                    
                    if active_element is not None and active_element.text == 'true':
                        active_element.text = 'false'
                        tree.write(rule_file, encoding='utf-8', xml_declaration=True)
                        modified_count += 1
                    else:
                        skipped_count += 1
                    
                    progress.update(task, advance=1)
            
            # Show summary
            table = Table(show_header=False, box=box.SIMPLE)
            table.add_row("Modified", f"[green]{modified_count}[/green]")
            table.add_row("Already inactive", f"[dim]{skipped_count}[/dim]")
            console.print(table)
            
            if modified_count > 0:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console
                ) as progress:
                    task = progress.add_task(f"[cyan]Deploying to {target_org}...", total=None)
                    deploy_command = [
                        'project', 'deploy', 'start',
                        '--source-dir', 'force-app',
                        '--target-org', target_org,
                        '--wait', '20'
                    ]
                    run_sf_command(deploy_command, cwd=str(project_root))
                    progress.update(task, completed=True)
                
                console.print(f"[bold green]✓ Successfully disabled {modified_count} validation rule(s)[/bold green]")
            else:
                console.print("[dim]ℹ All validation rules already inactive[/dim]")

        elif mode == 'enable':
            # Check if this specific object exists in the cached project structure
            cached_object_path = project_root / "force-app" / "main" / "default" / "objects" / sobject_name
            if not cached_object_path.exists():
                console.print(f"[red]✗ Error: Object '{sobject_name}' not found in cached data[/red]")
                console.print("[yellow]Run with --mode=disable for this object first to create backups[/yellow]")
                raise RuntimeError(f"Object '{sobject_name}' not found in cache")
            
            original_rules_dir = project_root / "original_validation_rules"
            if not original_rules_dir.exists() or not any(original_rules_dir.iterdir()):
                console.print("[red]✗ Error: No backup found[/red]")
                console.print("[yellow]Run with --mode=disable first to create backups[/yellow]")
                return

            # Get validation rules from the backup for this specific object
            rule_files = list(original_rules_dir.glob('*.validationRule-meta.xml'))
            
            if not rule_files:
                console.print(f"[yellow]⚠ No validation rules found in backup for {sobject_name}[/yellow]")
                return
            
            # Ensure the validation rules directory exists
            validation_rules_path.mkdir(parents=True, exist_ok=True)
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console
            ) as progress:
                task = progress.add_task("[cyan]Restoring validation rules...", total=len(rule_files))
                
                for rule_file in rule_files:
                    dest_file = validation_rules_path / rule_file.name
                    shutil.copy(rule_file, dest_file)
                    progress.update(task, advance=1)
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task(f"[cyan]Deploying to {target_org}...", total=None)
                deploy_command = [
                    'project', 'deploy', 'start',
                    '--source-dir', 'force-app',
                    '--target-org', target_org,
                    '--ignore-conflicts',
                    '--wait', '20'
                ]
                run_sf_command(deploy_command, cwd=str(project_root))
                progress.update(task, completed=True)
            
            console.print(f"[bold green]✓ Successfully re-enabled {len(rule_files)} validation rule(s)[/bold green]")

        elif mode == 'sync':
            rule_files = list(validation_rules_path.glob('*.validationRule-meta.xml'))
            rule_count = len(rule_files)
            
            console.print(f"\n[cyan]Found {rule_count} validation rule(s) to sync[/cyan]")
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task(f"[cyan]Deploying to {target_org}...", total=None)
                deploy_command = [
                    'project', 'deploy', 'start',
                    '--source-dir', str(validation_rules_path),
                    '--target-org', target_org,
                    '--ignore-conflicts',
                    '--wait', '20'
                ]
                run_sf_command(deploy_command, cwd=str(project_root))
                progress.update(task, completed=True)
            
            console.print(f"[bold green]✓ Successfully synced {rule_count} validation rule(s)[/bold green]")
            console.print(f"[dim]   {source_org} → {target_org}[/dim]")

    except RuntimeError as e:
        console.print(f"[bold red]✗ Error: {e}[/bold red]")
        raise
    except Exception as e:
        console.print(f"[bold red]✗ Unexpected error: {e}[/bold red]")
        raise

if __name__ == "__main__":
    show_banner()
    
    config = load_config()
    saved_target_org = config.get("target_org")
    saved_source_org = config.get("source_org")
    
    target_org_help = f'Target Salesforce org alias (default: {saved_target_org})' if saved_target_org else 'Target Salesforce org alias (required on first run)'
    source_org_help = f'Source Salesforce org alias for sync mode (default: {saved_source_org})' if saved_source_org else 'Source Salesforce org alias for sync mode (required on first sync)'
    
    parser = argparse.ArgumentParser(
        description="Manage Salesforce Validation Rules",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('-t', '--target-org', default=None, 
                        help=target_org_help)
    parser.add_argument('-s', '--source-org', default=None, 
                        help=source_org_help)
    parser.add_argument('-o', '--object', default=None, 
                        help='SObject name(s) - comma-separated for multiple. For enable mode, omit to enable all cached objects (default: Opportunity for disable/sync modes)')
    parser.add_argument('-m', '--mode', choices=['disable', 'enable', 'sync'], 
                        default='disable', 
                        help='Mode: disable, enable, or sync (default: disable)')
    args = parser.parse_args()

    target_org = args.target_org or saved_target_org
    source_org = args.source_org or saved_source_org

    if not target_org:
        console.print("[red]✗ Provide --target-org at least once to establish a default[/red]")
        exit(1)

    if args.mode == 'sync' and not source_org:
        console.print("[red]✗ Provide --source-org for sync mode (value will be saved as default)[/red]")
        exit(1)

    persist_config({"target_org": args.target_org, "source_org": args.source_org})

    # Handle enable mode - discover objects from cache if not specified
    if args.mode == 'enable' and args.object is None:
        temp_sfdx_project_dir = Path.home() / 'Sandcastle' / 'MetadataCache'
        objects_path = temp_sfdx_project_dir / "force-app" / "main" / "default" / "objects"
        
        if not objects_path.exists():
            console.print("[red]✗ Error: No cached objects found in SandcastleMetadata[/red]")
            console.print("[yellow]Run with --mode=disable first to create backups[/yellow]")
            exit(1)
        
        # Discover all objects with backed-up validation rules
        cached_objects = []
        for obj_dir in objects_path.iterdir():
            if obj_dir.is_dir():
                original_rules_dir = temp_sfdx_project_dir / "original_validation_rules"
                if original_rules_dir.exists():
                    # Check if this object has any validation rules in backup
                    obj_rules = list(original_rules_dir.glob(f'*.validationRule-meta.xml'))
                    if obj_rules:
                        cached_objects.append(obj_dir.name)
        
        if not cached_objects:
            console.print("[red]✗ Error: No backed-up validation rules found[/red]")
            console.print("[yellow]Run with --mode=disable first to create backups[/yellow]")
            exit(1)
        
        objects = cached_objects
        console.print(f"[cyan]ℹ Auto-detected cached objects: {', '.join(objects)}[/cyan]")
    
    # For enable mode with specified objects, validate they exist in cache
    elif args.mode == 'enable' and args.object is not None:
        temp_sfdx_project_dir = Path.home() / 'Sandcastle' / 'MetadataCache'
        original_rules_dir = temp_sfdx_project_dir / "original_validation_rules"
        
        if not original_rules_dir.exists():
            console.print("[red]✗ Error: No cached validation rules found[/red]")
            console.print("[yellow]Run with --mode=disable first to create backups[/yellow]")
            exit(1)
        
        objects = [obj.strip() for obj in args.object.split(',')]
        
        # Note: We'll validate per-object in the loop below since backups are stored by rule name, not object
    
    # For other modes, require object specification or use default
    else:
        if args.object is None:
            objects = ['Opportunity']  # Default for disable/sync modes
        else:
            objects = [obj.strip() for obj in args.object.split(',')]
    
    console.print(f"\n[bold]Processing {len(objects)} object(s): [cyan]{', '.join(objects)}[/cyan][/bold]\n")

    try:
        for idx, sobject in enumerate(objects, 1):
            if len(objects) > 1:
                console.print(f"\n[bold yellow]━━━ Object {idx}/{len(objects)}: {sobject} ━━━[/bold yellow]")
            
            if args.mode == 'sync':
                manage_validation_rules_in_temp_project(target_org, sobject, "sync", source_org)
            elif args.mode == 'disable':
                manage_validation_rules_in_temp_project(target_org, sobject, "disable")
            elif args.mode == 'enable':
                manage_validation_rules_in_temp_project(target_org, sobject, "enable")
            
        console.print("\n[bold green]Done![/bold green] 🎉\n")
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user[/yellow]")
    except Exception:
        console.print("\n[bold red]Operation failed[/bold red]")
        raise