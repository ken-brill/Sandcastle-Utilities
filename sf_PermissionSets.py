#!/usr/bin/env python3
"""
Salesforce Permission Set Report Generator
Retrieves all permission sets and exports their permissions to CSV.

Author: Ken Brill
Version: 1.0.0
License: MIT License
"""

import os
import sys
import json
import csv
import argparse
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List
from collections import defaultdict

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

# Import shared utilities
from sandcastle_utils import (
    load_config,
    persist_config,
    show_banner,
    verify_sandbox_org,
    CONFIG_FILE,
    VERSION,
    AUTHOR,
    REPO
)

console = Console()

class PermissionSetAnalyzer:
    def __init__(self, source_org: str):
        self.source_org = source_org
        self.sf_cli = SalesforceCLI(source_org)
        self.metadata_dir = None
        self.permissions_data = defaultdict(list)
        self.profile_data = defaultdict(list)
    
    def retrieve_metadata(self):
        """Retrieve permission sets and profiles metadata from org"""
        console.print(f"\n[bold cyan]🔥 Retrieving Permission Sets & Profiles[/bold cyan]")
        console.print(f"[dim]Source Org: {self.source_org}[/dim]")
        
        sandcastle_dir = Path.home() / "Sandcastle"
        sandcastle_dir.mkdir(parents=True, exist_ok=True)
        
        project_dir = sandcastle_dir / "PermissionSetsProject"
        
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console
            ) as progress:
                if not project_dir.exists():
                    task = progress.add_task("[cyan]Creating SFDX project...", total=None)
                    
                    original_cwd = os.getcwd()
                    os.chdir(sandcastle_dir)
                    try:
                        result = subprocess.run(
                            ['sf', 'project', 'generate', '--name', 'PermissionSetsProject'],
                            capture_output=True,
                            text=True,
                            check=True
                        )
                    finally:
                        os.chdir(original_cwd)
                    
                    progress.update(task, completed=True)
                
                task = progress.add_task("[cyan]Retrieving permission sets & profiles...", total=None)
                
                cmd = [
                    'project', 'retrieve', 'start',
                    '-m', 'PermissionSet',
                    '-m', 'Profile',
                    '--wait', '20'
                ]
                
                original_cwd = os.getcwd()
                os.chdir(project_dir)
                try:
                    result = self.sf_cli._execute_sf_command(cmd)
                finally:
                    os.chdir(original_cwd)
                
                progress.update(task, completed=True)
            
            self.metadata_dir = project_dir / "force-app" / "main" / "default"
            
            console.print(f"[green]✓[/green] Permission sets & profiles retrieved to [cyan]{self.metadata_dir}[/cyan]")
            return True
            
        except Exception as e:
            console.print(f"[bold red]✗ Error retrieving permission sets: {e}[/bold red]")
            raise
    
    def parse_permission_set_xml(self, file_path: Path) -> List[Dict]:
        """Parse a single permission set XML file"""
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            
            ns = {'sf': 'http://soap.sforce.com/2006/04/metadata'}
            
            permissions = []
            
            # Object Permissions
            for obj_perm in root.findall('.//sf:objectPermissions', ns):
                obj_name = obj_perm.find('sf:object', ns)
                obj_name = obj_name.text if obj_name is not None else 'N/A'
                
                perms = {
                    'Type': 'Object',
                    'Name': obj_name,
                    'Create': obj_perm.find('sf:allowCreate', ns).text if obj_perm.find('sf:allowCreate', ns) is not None else 'false',
                    'Read': obj_perm.find('sf:allowRead', ns).text if obj_perm.find('sf:allowRead', ns) is not None else 'false',
                    'Edit': obj_perm.find('sf:allowEdit', ns).text if obj_perm.find('sf:allowEdit', ns) is not None else 'false',
                    'Delete': obj_perm.find('sf:allowDelete', ns).text if obj_perm.find('sf:allowDelete', ns) is not None else 'false',
                }
                permissions.append(perms)
            
            # Field Permissions
            for field_perm in root.findall('.//sf:fieldPermissions', ns):
                field = field_perm.find('sf:field', ns)
                field = field.text if field is not None else 'N/A'
                
                perms = {
                    'Type': 'Field',
                    'Name': field,
                    'Read': field_perm.find('sf:readable', ns).text if field_perm.find('sf:readable', ns) is not None else 'false',
                    'Edit': field_perm.find('sf:editable', ns).text if field_perm.find('sf:editable', ns) is not None else 'false',
                }
                permissions.append(perms)
            
            # Custom Permissions
            for cust_perm in root.findall('.//sf:customPermissions', ns):
                name = cust_perm.find('sf:name', ns)
                name = name.text if name is not None else 'N/A'
                enabled = cust_perm.find('sf:enabled', ns)
                enabled = enabled.text if enabled is not None else 'false'
                
                perms = {
                    'Type': 'Custom Permission',
                    'Name': name,
                    'Enabled': enabled,
                }
                permissions.append(perms)
            
            # Apex Class Access
            for apex in root.findall('.//sf:classAccesses', ns):
                apex_class = apex.find('sf:apexClass', ns)
                apex_class = apex_class.text if apex_class is not None else 'N/A'
                enabled = apex.find('sf:enabled', ns)
                enabled = enabled.text if enabled is not None else 'false'
                
                perms = {
                    'Type': 'Apex Class',
                    'Name': apex_class,
                    'Enabled': enabled,
                }
                permissions.append(perms)
            
            # Visualforce Page Access
            for vf_page in root.findall('.//sf:pageAccesses', ns):
                page = vf_page.find('sf:apexPage', ns)
                page = page.text if page is not None else 'N/A'
                enabled = vf_page.find('sf:enabled', ns)
                enabled = enabled.text if enabled is not None else 'false'
                
                perms = {
                    'Type': 'Visualforce Page',
                    'Name': page,
                    'Enabled': enabled,
                }
                permissions.append(perms)
            
            return permissions
        
        except Exception as e:
            console.print(f"[yellow]⚠ Warning: Error parsing {file_path.name}: {e}[/yellow]")
            return []
    
    def parse_profile_xml(self, file_path: Path) -> List[Dict]:
        """Parse a single profile XML file"""
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            
            ns = {'sf': 'http://soap.sforce.com/2006/04/metadata'}
            
            permissions = []
            
            # Object Permissions
            for obj_perm in root.findall('.//sf:objectPermissions', ns):
                obj_name = obj_perm.find('sf:object', ns)
                obj_name = obj_name.text if obj_name is not None else 'N/A'
                
                perms = {
                    'Type': 'Object',
                    'Name': obj_name,
                    'Create': obj_perm.find('sf:allowCreate', ns).text if obj_perm.find('sf:allowCreate', ns) is not None else 'false',
                    'Read': obj_perm.find('sf:allowRead', ns).text if obj_perm.find('sf:allowRead', ns) is not None else 'false',
                    'Edit': obj_perm.find('sf:allowEdit', ns).text if obj_perm.find('sf:allowEdit', ns) is not None else 'false',
                    'Delete': obj_perm.find('sf:allowDelete', ns).text if obj_perm.find('sf:allowDelete', ns) is not None else 'false',
                }
                permissions.append(perms)
            
            # Field Permissions
            for field_perm in root.findall('.//sf:fieldPermissions', ns):
                field = field_perm.find('sf:field', ns)
                field = field.text if field is not None else 'N/A'
                
                perms = {
                    'Type': 'Field',
                    'Name': field,
                    'Read': field_perm.find('sf:readable', ns).text if field_perm.find('sf:readable', ns) is not None else 'false',
                    'Edit': field_perm.find('sf:editable', ns).text if field_perm.find('sf:editable', ns) is not None else 'false',
                }
                permissions.append(perms)
            
            # User Permissions (unique to profiles)
            for user_perm in root.findall('.//sf:userPermissions', ns):
                name = user_perm.find('sf:name', ns)
                name = name.text if name is not None else 'N/A'
                enabled = user_perm.find('sf:enabled', ns)
                enabled = enabled.text if enabled is not None else 'false'
                
                perms = {
                    'Type': 'User Permission',
                    'Name': name,
                    'Enabled': enabled,
                }
                permissions.append(perms)
            
            # Custom Permissions
            for cust_perm in root.findall('.//sf:customPermissions', ns):
                name = cust_perm.find('sf:name', ns)
                name = name.text if name is not None else 'N/A'
                enabled = cust_perm.find('sf:enabled', ns)
                enabled = enabled.text if enabled is not None else 'false'
                
                perms = {
                    'Type': 'Custom Permission',
                    'Name': name,
                    'Enabled': enabled,
                }
                permissions.append(perms)
            
            # Apex Class Access
            for apex in root.findall('.//sf:classAccesses', ns):
                apex_class = apex.find('sf:apexClass', ns)
                apex_class = apex_class.text if apex_class is not None else 'N/A'
                enabled = apex.find('sf:enabled', ns)
                enabled = enabled.text if enabled is not None else 'false'
                
                perms = {
                    'Type': 'Apex Class',
                    'Name': apex_class,
                    'Enabled': enabled,
                }
                permissions.append(perms)
            
            # Visualforce Page Access
            for vf_page in root.findall('.//sf:pageAccesses', ns):
                page = vf_page.find('sf:apexPage', ns)
                page = page.text if page is not None else 'N/A'
                enabled = vf_page.find('sf:enabled', ns)
                enabled = enabled.text if enabled is not None else 'false'
                
                perms = {
                    'Type': 'Visualforce Page',
                    'Name': page,
                    'Enabled': enabled,
                }
                permissions.append(perms)
            
            return permissions
        
        except Exception as e:
            console.print(f"[yellow]⚠ Warning: Error parsing {file_path.name}: {e}[/yellow]")
            return []
    
    def process_metadata(self):
        """Find and process all permission set and profile XML files"""
        console.print(f"\n[bold cyan]🔍 Processing Permission Sets & Profiles[/bold cyan]")
        
        perm_set_dir = self.metadata_dir / "permissionsets"
        profile_dir = self.metadata_dir / "profiles"
        
        perm_set_files = list(perm_set_dir.glob("*.permissionset-meta.xml")) if perm_set_dir.exists() else []
        profile_files = list(profile_dir.glob("*.profile-meta.xml")) if profile_dir.exists() else []
        
        total_files = len(perm_set_files) + len(profile_files)
        
        if total_files == 0:
            console.print(f"[yellow]⚠ No permission sets or profiles found[/yellow]")
            return
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task = progress.add_task(f"[cyan]Processing metadata files...", total=total_files)
            
            for xml_file in perm_set_files:
                perm_set_name = xml_file.stem.replace(".permissionset-meta", "")
                permissions = self.parse_permission_set_xml(xml_file)
                self.permissions_data[perm_set_name] = permissions
                progress.update(task, advance=1)
            
            for xml_file in profile_files:
                profile_name = xml_file.stem.replace(".profile-meta", "")
                permissions = self.parse_profile_xml(xml_file)
                self.profile_data[profile_name] = permissions
                progress.update(task, advance=1)
        
        console.print(f"[green]✓[/green] Processed [cyan]{len(self.permissions_data)}[/cyan] permission sets and [cyan]{len(self.profile_data)}[/cyan] profiles")
    
    def export_to_csv(self, output_file: Path):
        """Export permissions data to CSV"""
        console.print(f"\n[bold cyan]📊 Exporting Report[/bold cyan]")
        console.print(f"[dim]Output File: {output_file}[/dim]")
        
        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['Type', 'Name', 'Permission Type', 'Object/Field', 'Create', 'Read', 'Edit', 'Delete', 'Enabled', 'Readable', 'Editable']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames, restval='')
                
                writer.writeheader()
                
                for perm_set_name, permissions in sorted(self.permissions_data.items()):
                    if not permissions:
                        writer.writerow({'Type': 'Permission Set', 'Name': perm_set_name})
                    else:
                        for perm in permissions:
                            row = {'Type': 'Permission Set', 'Name': perm_set_name, 'Permission Type': perm.get('Type'), 'Object/Field': perm.get('Name')}
                            row.update({k: v for k, v in perm.items() if k not in ['Type', 'Name']})
                            writer.writerow(row)
                
                for profile_name, permissions in sorted(self.profile_data.items()):
                    if not permissions:
                        writer.writerow({'Type': 'Profile', 'Name': profile_name})
                    else:
                        for perm in permissions:
                            row = {'Type': 'Profile', 'Name': profile_name, 'Permission Type': perm.get('Type'), 'Object/Field': perm.get('Name')}
                            row.update({k: v for k, v in perm.items() if k not in ['Type', 'Name']})
                            writer.writerow(row)
            
            console.print(f"[green]✓[/green] Report successfully created: [cyan]{output_file}[/cyan]")
            
            self.print_summary()
        
        except Exception as e:
            console.print(f"[bold red]✗ Error writing CSV: {e}[/bold red]")
            raise
    
    def print_summary(self):
        """Print summary statistics"""
        total_sets = len(self.permissions_data)
        total_profiles = len(self.profile_data)
        total_set_perms = sum(len(perms) for perms in self.permissions_data.values())
        total_profile_perms = sum(len(perms) for perms in self.profile_data.values())
        
        console.print(f"\n[bold cyan]📊 Summary[/bold cyan]")
        
        table = Table(show_header=False, box=box.SIMPLE)
        table.add_row("Permission Sets", f"[cyan]{total_sets}[/cyan]")
        table.add_row("Profiles", f"[cyan]{total_profiles}[/cyan]")
        table.add_row("Total Permissions (Sets)", f"[cyan]{total_set_perms}[/cyan]")
        table.add_row("Total Permissions (Profiles)", f"[cyan]{total_profile_perms}[/cyan]")
        console.print(table)
    
    def run(self, output_file: Path):
        """Execute full workflow"""
        self.retrieve_metadata()
        self.process_metadata()
        self.export_to_csv(output_file)


def main():
    show_banner("Permission Set & Profile Report Generator")
    
    config = load_config()
    saved_source_org = config.get("source_org")
    
    source_org_help = f"Source Salesforce org alias (default: {saved_source_org})" if saved_source_org else "Source Salesforce org alias (required on first run)"
    
    parser = argparse.ArgumentParser(
        description="Generate a CSV report of all permission sets and profiles with their permissions from a Salesforce org.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
  ./sf_PermissionSets.py --source-org KBRILL
  ./sf_PermissionSets.py --source-org KBRILL --output custom_report.csv
  ./sf_PermissionSets.py  # Uses saved default org
        """
    )
    
    parser.add_argument(
        "--source-org",
        help=source_org_help,
        default=saved_source_org
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output CSV file path (default: permission_sets_report.csv)",
        default="permission_sets_report.csv"
    )
    
    args = parser.parse_args()
    
    source_org = args.source_org
    if not source_org:
        console.print("[bold red]✗ Error: --source-org is required[/bold red]")
        console.print("[yellow]Run with --source-org <alias> to specify the source org[/yellow]")
        sys.exit(1)
    
    output_file = Path(args.output)
    
    try:
        console.print(f"[dim]Source org: {source_org}[/dim]")
        
        persist_config({"source_org": source_org})
        
        analyzer = PermissionSetAnalyzer(source_org)
        analyzer.run(output_file)
        
        console.print(f"\n[bold green]✓ Permission set & profile report complete![/bold green]")
        
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠ Operation cancelled by user[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[bold red]✗ Error: {e}[/bold red]")
        sys.exit(1)


if __name__ == "__main__":
    main()