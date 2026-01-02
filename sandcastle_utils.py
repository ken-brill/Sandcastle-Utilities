#!/usr/bin/env python3
"""
Sandcastle Utilities
Shared utility functions for Sandcastle Salesforce tools.

Author: Ken Brill
Version: 1.0.0
License: MIT License
"""

import json
from pathlib import Path
from typing import Dict
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich import box

# Import SalesforceCLI for sandbox verification
try:
    from cli.salesforce_cli import SalesforceCLI
except ImportError:
    # Allow import to succeed even if CLI module not available
    SalesforceCLI = None

console = Console()

# Common constants
VERSION = "1.0.0"
AUTHOR = "Ken Brill"
REPO = "https://github.com/ken-brill/Sandcastle-Utilities"
CONFIG_FILE = Path.home() / "Sandcastle" / "config.json"


def load_config() -> Dict[str, str]:
    """
    Load persisted defaults for org aliases and other configuration.
    
    Returns:
        Dict containing configuration keys and values, or empty dict if file doesn't exist.
    """
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def persist_config(updates: Dict[str, str], skip_production_orgs: bool = True):
    """
    Persist provided configuration values as the new defaults.
    
    Args:
        updates: Dictionary of configuration keys and values to save
        skip_production_orgs: If True, production orgs won't be saved (default: True)
    """
    config = load_config()
    changed = False
    
    for key, value in updates.items():
        if value and config.get(key) != value:
            # Skip saving production orgs if requested
            if skip_production_orgs and 'org' in key and SalesforceCLI is not None:
                try:
                    sf_cli = SalesforceCLI(value)
                    if not sf_cli.is_sandbox():
                        console.print(f"[dim]Skipping save of production org '{value}' to config[/dim]")
                        continue
                except Exception:
                    # If we can't verify, proceed with caution
                    pass
            
            config[key] = value
            changed = True
    
    if changed:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)


def show_banner(tool_name: str, custom_version: str = None):
    """
    Display an application banner with consistent styling.
    
    Args:
        tool_name: Name of the tool to display in the banner
        custom_version: Optional custom version string (defaults to VERSION constant)
    """
    title = Text()
    title.append(f"{tool_name}\n", style="bold cyan")
    title.append(f"Version {custom_version or VERSION}\n", style="dim")
    title.append(f"Author: {AUTHOR}\n", style="green")
    title.append(f"Support: {REPO}", style="blue underline")
    
    console.print(Panel(title, box=box.DOUBLE, border_style="cyan", padding=(1, 2)))


def get_config_value(key: str, default=None):
    """
    Get a single configuration value by key.
    
    Args:
        key: Configuration key to retrieve
        default: Default value if key doesn't exist
        
    Returns:
        Configuration value or default
    """
    config = load_config()
    return config.get(key, default)


def update_config_value(key: str, value, skip_production_orgs: bool = True):
    """
    Update a single configuration value.
    
    Args:
        key: Configuration key to update
        value: New value to set
        skip_production_orgs: If True, production orgs won't be saved (default: True)
    """
    persist_config({key: value}, skip_production_orgs=skip_production_orgs)
