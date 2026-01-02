# Salesforce Metadata Management Utilities

This repository provides Python scripts to streamline the management of Salesforce metadata, specifically Apex Triggers and Validation Rules. These tools help developers and administrators safely control activation statuses and synchronize configurations across different Salesforce environments.

---

## Tools Included

-   `sf_validations.py`: Manages the activation state and synchronization of Salesforce Validation Rules.
📺 **Video Tutorial**: [Watch the demo on YouTube](https://www.youtube.com/watch?v=S2K8MAhCABI)

-   `sf_triggers.py`: Manages the activation state of Salesforce Apex Triggers.

-   `sf_custom_settings.py`: Automates the management of Custom Setting checkbox fields with interactive reminders and cross-platform notifications. Example implementation for feature toggle automation.



---

## Key Features

### For Validation Rules (`sf_validations.py`)

-   ✅ **Disable Mode**: Temporarily deactivate validation rules in a sandbox for data migration or mass updates.
-   ✅ **Enable Mode**: Re-activate validation rules from cached backups.
-   ✅ **Sync Mode**: Copy validation rules from one sandbox to another, ensuring consistency.
-   ✅ **Check Mode**: Query and display active/inactive validation rule counts without making changes.
-   ✅ **Multi-Object Support**: Process validation rules for multiple SObjects in a single run.
-   ✅ **Smart Caching**: Automatically manages cached validation rules for efficient re-enabling.

### For Apex Triggers (`sf_triggers.py`)

-   ✅ **Disable Mode**: Temporarily deactivate all Apex Triggers in a sandbox.
-   ✅ **Enable Mode**: Re-activate previously disabled Apex Triggers from a stored state.
-   ✅ **Reset Option**: Clean up all temporary files and stored states for a fresh start.
-   ✅ **Managed Package Filtering**: Distinguishes between deployable and managed package triggers.

### For Custom Settings (`sf_custom_settings.py`)

-   ✅ **Check All Mode**: Enable all checkbox fields with interactive reminders.
-   ✅ **Uncheck All Mode**: Disable all checkbox fields and save original state.

-   ✅ **Status Mode**: Query and display checkbox status without making changes.
-   ✅ **Cross-Platform Alerts**: Voice alerts + dialog boxes on macOS and Windows.
-   ✅ **Interactive Reminders**: 30-second beeps with 60-second voice/dialog notifications.
-   ✅ **Production Support**: Works on both sandbox and production orgs (with confirmation).
-   ✅ **State Persistence**: Automatic backup and restoration of checkbox states.

### Common Features

-   ✅ **Safety Checks**: Prevents operations on production orgs to safeguard your environment.
-   ✅ **Salesforce CLI Integration**: Leverages `sf` CLI for robust metadata operations.
-   ✅ **Rich Terminal UI**: Provides clear progress tracking and status updates using `rich`.

---

## Requirements

-   **Salesforce CLI (sf)**: Must be installed and in your system's PATH.
    -   Install instructions: [Salesforce CLI Setup Guide](https://developer.salesforce.com/docs/atlas.en-us.sfdx_setup.meta/sfdx_setup/sfdx_setup_install_cli.htm)
-   **Python 3.8+**
-   **Python Dependencies**:
    ```bash
    pip install rich
    ```

---

## Installation

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/ken-brill/Sandcastle-Utilities.git
    cd Sandcastle/validation_test
    ```

2.  **Install Python dependencies**:
    ```bash
    pip install rich
    ```

3.  **Authenticate with Salesforce**:
    Before using either script, ensure you are authenticated with your target (and source, for sync) Salesforce orgs using the Salesforce CLI.
    ```bash
    sf org login web --alias MYSANDBOX
    ```

---

## Usage

### 1. Salesforce Validation Rule Manager (`sf_validations.py`)

This script helps you manage validation rules with different modes: `disable`, `enable`, and `sync`.

#### Basic Syntax

```bash
python3 sf_validations.py -m <mode> -t <target-org> [-o <objects>] [-s <source-org>]
```

#### Arguments

| Argument       | Short | Default     | Description                                                                  |
| :------------- | :---- | :---------- | :--------------------------------------------------------------------------- |
| `--mode`       | `-m`  | `disable`   | Operation mode: `disable`, `enable`, `sync`, or `check`.                     |
| `--target-org` | `-t`  | (Saved)     | Alias of the target Salesforce org. Required on first run.                   |
| `--object`     | `-o`  | `Opportunity` | SObject name(s), comma-separated for multiple. Omit for `enable` mode to process all cached objects. |
| `--source-org` | `-s`  | (Saved)     | Alias of the source org for `sync` mode. Required on first sync operation.   |

#### Modes

##### a. Disable Mode (Default)
Deactivates validation rules for specified (or default `Opportunity`) objects in the target org. Backs up original rules.

```bash
# Disable rules for Opportunity and Account in MYSANDBOX
python3 sf_validations.py -m disable -t MYSANDBOX -o Opportunity,Account
```

##### b. Enable Mode
Re-activates validation rules from previously created backups. Can auto-detect and enable rules for all cached objects.

```bash
# Enable rules for a specific object (Opportunity)
python3 sf_validations.py -m enable -t MYSANDBOX -o Opportunity

# Enable rules for all objects with cached backups in MYSANDBOX
python3 sf_validations.py -m enable -t MYSANDBOX
```

##### c. Sync Mode
Copies validation rules from a source org to a target org for specified objects.

```bash
# Sync Account and Contact validation rules from dev-sandbox to qa-sandbox
python3 sf_validations.py -m sync -t qa-sandbox -s dev-sandbox -o Account,Contact
```

##### d. Check Mode
Queries and displays the count of active and inactive validation rules without making any modifications.

```bash
# Check validation rule status for Opportunity in MYSANDBOX
python3 sf_validations.py -m check -t MYSANDBOX -o Opportunity

# Check validation rule status for Account (uses default or saved target org)
python3 sf_validations.py -m check -o Account
```

---

### 2. Salesforce Apex Trigger Manager (`sf_triggers.py`)

This script allows you to disable and re-enable all Apex triggers in a sandbox environment.

#### Basic Syntax

```bash
python3 sf_triggers.py --target-org <alias> [--disable | --enable | --reset] [--api-version <version>]
```

#### Arguments

| Argument        | Short | Default     | Description                                                                  |
| :-------------- | :---- | :---------- | :--------------------------------------------------------------------------- |
| `--target-org`  |       | (Saved)     | Alias of the target Salesforce org. Required on first run.                   |
| `--disable`     |       | (Default)   | Deactivates all active Apex triggers in the target org.                      |
| `--enable`      |       |             | Re-activates previously disabled Apex triggers from the stored state file.   |
| `--reset`       |       |             | Cleans up all temporary files and trigger state, allowing a fresh `--disable` operation. |
| `--api-version` |       | `58.0`      | Salesforce API version to use for metadata operations.                       |

#### Modes

##### a. Disable Mode (Default)
Disables all active Apex triggers in the specified target org and saves their original state.

```bash
# Disable all triggers in MYSANDBOX
python3 sf_triggers.py --target-org MYSANDBOX --disable
```

##### b. Enable Mode
Re-enables triggers that were previously disabled using this script, restoring them to their original active/inactive state.

```bash
# Re-enable triggers in MYSANDBOX
python3 sf_triggers.py --target-org MYSANDBOX --enable
```

##### c. Reset Option
Use this to clear any existing trigger state files and temporary metadata, forcing a clean start. Useful if state becomes corrupted or you want to discard previous changes.

```bash
# Reset trigger state and then disable triggers
python3 sf_triggers.py --target-org MYSANDBOX --reset --disable
```

##### d. Check Mode
Queries the target org to display the current count of active and inactive Apex triggers. This mode performs no modifications and is useful for auditing trigger status before making changes.

```bash
# Check trigger status in MYSANDBOX
python3 sf_triggers.py --target-org MYSANDBOX --check
```

**Output Example:**
```
Apex Trigger Status for MYSANDBOX
┏━━━━━━━━━━━━━┳━━━━━━┓
┃ Status      ┃ Count ┃
┡━━━━━━━━━━━━━╇━━━━━━┩
│ Active      │  12   │
│ Inactive    │   3   │
│ Total       │  15   │
└─────────────┴─────┘
```

---

## 3. Salesforce Custom Setting Manager (`sf_custom_settings.py`)

This script demonstrates how to automate the management of Custom Setting checkbox fields in Salesforce. It provides a complete example of managing mutable hierarchical custom settings, with interactive reminders and multi-platform notifications.

**Use Case**: This example manages the `ESB_Events_Controller__c` custom setting, which controls feature toggles for event processing. The script can be adapted to manage any custom setting with boolean fields in your Salesforce instance.

#### Features

- ✅ **Check All Mode**: Enable all checkbox fields and enter an interactive reminder loop
- ✅ **Uncheck All Mode**: Disable all checkbox fields and save the original state
- ✅ **Restore Mode**: Restore all checkbox fields to their previously saved state
- ✅ **Status Mode**: Query and display current checkbox status without making changes
- ✅ **Cross-Platform Alerts**: Multi-modal notifications with voice alerts + dialog boxes on macOS and Windows
- ✅ **Interactive Reminder Loop**: Every 30 seconds with 60-second voice/dialog alerts
- ✅ **Production Org Support**: Works with both sandbox and production (with user confirmation)
- ✅ **State Persistence**: Automatically saves original state for restoration

#### Basic Syntax

```bash
./sf_custom_settings.py --target-org SANDBOX_ALIAS --check-all
./sf_custom_settings.py --target-org SANDBOX_ALIAS --uncheck-all
./sf_custom_settings.py --target-org SANDBOX_ALIAS --status
```

#### Arguments

| Argument           | Description                                                        |
| :----------------- | :----------------------------------------------------------------- |
| `--target-org`     | Alias of the target Salesforce org. Saved on first run.           |
| `--check-all`      | Enable all checkbox fields and enter annoying reminder loop.      |
| `--uncheck-all`    | Disable all checkbox fields and save original state.              |
| `--status`         | Display current checkbox status without making changes.           |
| `--dialog-timeout` | Dialog box auto-dismiss timeout in seconds (default: 10, saved).  |
| `--test-dialog`    | Test desktop notifications (debug only).                          |

#### Modes

##### Status Mode
Query current checkbox status and display in a formatted table:

```bash
./sf_custom_settings.py --status
```

Output:
```
Custom Setting Status: ESB_Events_Controller__c

┌──────────────────────────────┬────────────────┐
│ Field Name                   │ Status         │
├──────────────────────────────┼────────────────┤
│ Event_Processing__c          │ ✓ Checked      │
│ Error_Logging__c             │ ☐ Unchecked    │
│ Analytics_Enabled__c         │ ✓ Checked      │
└──────────────────────────────┴────────────────┘

Checked      3
Unchecked    1
Total        4
```

##### Check All Mode
Enable all checkbox fields and enter the reminder loop:

```bash
./sf_custom_settings.py --check-all
```

What happens:
1. Displays current checkbox status
2. Enters interactive reminder loop
3. Every 30 seconds: Terminal bell + red warning panel
4. Every 60 seconds: Voice alert + dialog box popup
5. Press any key to exit loop and uncheck boxes

The annoying alerts include:
- **macOS**: Native dialog boxes + Samantha voice alert via `say` command
- **Windows**: Native MessageBox + PowerShell text-to-speech
- **All Platforms**: Terminal beeps + Rich red warning panels

##### Uncheck All Mode
Disable all checkbox fields and save the original state:

```bash
./sf_custom_settings.py --uncheck-all
```

This saves the original state to `~/Sandcastle/custom_setting_state.json` so you can restore it later.
This saves the original state to `~/Sandcastle/custom_setting_state.json` so you can restore it manually if needed.
#### Example Workflow

```bash
# 1. Check current status
./sf_custom_settings.py --status

# 2. Configure dialog timeout (saved for future runs)
./sf_custom_settings.py --dialog-timeout 15 --check-all

# 3. Enable all checkboxes with reminder loop
./sf_custom_settings.py --check-all

# ... after testing, manually update checkboxes ...

# 4. Verify status after manual changes
./sf_custom_settings.py --status

# 5. Test your notification settings
./sf_custom_settings.py --test-dialog
```

#### Cross-Platform Notifications

The script uses native platform APIs for maximum compatibility:

**macOS**:
- Dialog boxes via `osascript` AppleScript
- Voice alerts via `say` command (Samantha voice)
- System sounds via `afplay`

**Windows**:
- Native MessageBox via `ctypes.windll.user32.MessageBoxW`
- Voice alerts via PowerShell's `System.Speech.Synthesis.SpeechSynthesizer`
- Terminal beeps via standard output

**All Platforms**:
- Terminal beeps (ASCII bell character)
- Rich library red warning panels
- Interactive keyboard prompts

#### How to Adapt for Your Custom Settings

This script is designed as an example. To use it with your own custom settings:

1. **Update the Custom Setting API Name**:
   ```python
   CUSTOM_SETTING_NAME = "Your_Custom_Setting__c"
   ```

2. **Run the script**:
   ```bash
   ./sf_custom_settings.py --target-org YOUR_ORG --status
   ```

3. The script automatically discovers all boolean fields and manages them.

#### State Files

- **State Storage**: `~/Sandcastle/custom_setting_state.json`
  - Saved when you run `--uncheck-all`
  - Contains the original state of all checkboxes before they were unchecked
  - Organization-specific (includes target org name)
  - Can be manually inspected to see previous values if needed

#### Production Org Support

The script now allows operations on production orgs:

```bash
./sf_custom_settings.py --target-org PRODUCTION --check-all
```

When targeting a production org:
- ⚠️ **Bold red warning** is displayed
- You must confirm with `y` to proceed (or `n` to cancel)
- **Production orgs will NOT be saved as default** in config.json
- This ensures you don't accidentally use production as your default

---

## Safety Features

All three scripts include robust safety mechanisms:
-   **Production Org Protection**: Operations are strictly blocked on production Salesforce environments to prevent unintended consequences.
-   **Sandbox Requirement**: Both tools verify that the target org is a sandbox before proceeding with any metadata modifications.

---

## Configuration File

All three scripts use a shared configuration file to persist your preferences and defaults across runs.

### Configuration File Location
**`~/.Sandcastle/config.json`**

This file is created automatically on the first run of any script. Location: Your home directory (`~`) under the `.Sandcastle` folder.

### Stored Configuration

The config file stores the following information:

| Setting         | Script(s)              | Purpose                                                  |
| :-------------- | :--------------------- | :------------------------------------------------------- |
| `target_org`    | All 3 scripts          | Default Salesforce org alias for target operations      |
| `source_org`    | sf_validations.py      | Default source org for sync operations                  |
| `dialog_timeout`| sf_custom_settings.py  | Dialog box auto-dismiss timeout in seconds (default: 10)|

### Important Notes

- **Production Orgs**: Production org aliases are **never saved** to the config file, even if you successfully run a script against production. This is intentional—only sandbox orgs become saved defaults.
- **Sandbox Defaults**: Only sandbox org aliases are persisted to `config.json` to prevent accidental use of production as a default.
- **Manual Editing**: You can manually edit `config.json` if needed. Format:
  ```json
  {
    "target_org": "my-sandbox",
    "source_org": "source-sandbox",
    "dialog_timeout": "15"
  }
  ```

### Clearing Configuration

To reset all saved defaults:
```bash
rm ~/.Sandcastle/config.json
```

You'll need to provide `--target-org` (and `--source-org` for validations sync) on the next run.

---

## Cache and State Management

### Validation Rules (`sf_validations.py`)

-   **Cache Location**: `~/Sandcastle/MetadataCache/`
    -   Contains a temporary SFDX project structure (`force-app/main/default/objects/`) for retrieved validation rules.
    -   `original_validation_rules/` directory stores backups of validation rule `.xml` files before they are disabled.
-   **Clearing Cache**: To remove all cached validation rule data:
    ```bash
    rm -rf ~/Sandcastle/MetadataCache
    ```

### Apex Triggers (`sf_triggers.py`)

-   **Working Directory**: `~/Sandcastle/apextriggers/`
    -   Contains a temporary SFDX project structure (`force-app/main/default/triggers/`) for retrieved triggers.
    -   `trigger_state.json` stores the original activation status of triggers that were disabled by the script, allowing for precise re-enabling.
-   **Clearing State**: The `--reset` flag handles cleanup of the state file and temporary trigger metadata. To manually remove all trigger-related files:
    ```bash
    rm -rf ~/Sandcastle/apextriggers
    ```

---

## Troubleshooting

### Common Issues for Both Tools

-   **"Salesforce CLI ('sf') not found"**: Ensure Salesforce CLI is installed and configured in your system's PATH.
-   **"Cannot perform X operation on production org"**: This is an intentional safety feature. Both tools are designed to operate exclusively on sandbox environments.
-   **"Operation cancelled by user"**: You can interrupt an ongoing operation with `Ctrl+C`.

### Specific to Validation Rules (`sf_validations.py`)

-   **"SandcastleMetadata directory not found" / "No cached objects found"**: Run the script in `--mode=disable` for the desired object(s) first to create the necessary backups and cache.
-   **"Object 'X' not found in cached data"**: If enabling a specific object, ensure it was previously disabled (and thus cached).
-   **"1 conflicts detected" during deployment**: The script attempts to handle conflicts with `--ignore-conflicts`. If issues persist, manual review may be needed.

### Specific to Apex Triggers (`sf_triggers.py`)

-   **"State file already exists"**: If running `--disable` when a `trigger_state.json` already exists, use `--enable` to restore or `--reset --disable` to start fresh.
-   **"No triggers to restore"**: If running `--enable` and no `trigger_state.json` is found, it means no triggers were previously disabled by the script or the state file was removed.

---

## How It Works

### Validation Rules (`sf_validations.py`)

-   **Disable Workflow**: Generates a temporary SFDX project, retrieves specified `CustomObject` metadata, copies `.validationRule-meta.xml` files to a backup, modifies the active flag to `false` in retrieved files, and deploys changes to the target org.
-   **Enable Workflow**: Restores `.validationRule-meta.xml` files from the backup into the temporary project, and deploys them to the target org with `--ignore-conflicts` to resolve potential deployment issues.
-   **Sync Workflow**: Retrieves `CustomObject` metadata from the source org, cleans up all non-validation rule files, and then deploys the retrieved validation rules to the target org.

### Apex Triggers (`sf_triggers.py`)

-   **Disable Workflow**: Creates a temporary SFDX project structure, retrieves all `ApexTrigger` metadata, parses each `.trigger-meta.xml` file, changes the `status` from `Active` to `Inactive`, and deploys the modified triggers back to the org. The original `Active` state is saved to `trigger_state.json`.
-   **Enable Workflow**: Retrieves the current trigger metadata, uses `trigger_state.json` to identify which triggers were previously active, updates their `status` to `Active` in the local metadata, and deploys these changes.
-   **Directory Management**: Creates a `~/Sandcastle/apextriggers` directory to manage the temporary SFDX project, manifest files, and the state file.

---

## File Structure

```
validation_test/
├── sf_triggers.py             # Apex Trigger management script
├── sf_validations.py          # Validation Rule management script
├── sf_custom_settings.py      # Custom Setting checkbox management script
├── disable_opportunity_apextriggers.py  # Utility script
├── disable_opportunity_validations.py   # Utility script
├── test_sf_validations.py     # Unit tests for sf_validations.py
├── pytest.ini                 # Pytest configuration
├── README.md                  # This file
├── TEST_README.md             # Testing documentation
└── cli/
    ├── salesforce_cli.py      # Salesforce CLI wrapper
    └── logs/
        └── queries.csv        # Query logging
```

---

## Future Enhancements

-   **Flow Manager**: Working on a dedicated script to enable or disable Salesforce Flows.

---

## Contributing

Found a bug or have a feature request? Please open an issue on GitHub:
[https://github.com/ken-brill/Sandcastle-Utilities/issues](https://github.com/ken-brill/Sandcastle-Utilities/issues)

---

## License

MIT License - See `LICENSE` file for details

---

## Disclaimer

**Use at your own risk.** These tools modify Salesforce metadata. Always:
-   Test in a sandbox environment first.
-   Maintain backups of your metadata (especially validation rules and Apex triggers).
-   Understand the changes being made.
-   Review cached backups or state files before re-enabling.

The author is not responsible for data loss or unexpected behavior.

---

## Support

For issues, questions, or contributions:
-   **GitHub:** [https://github.com/ken-brill/Sandcastle-Utilities](https://github.com/ken-brill/Sandcastle-Utilities)
-   **Author:** Ken Brill

---

## Changelog

### v1.0.0 (January 1, 2026)
-   Initial release of combined Salesforce Metadata Management Utilities.
-   Includes `sf_validations.py` for Validation Rule management (disable, enable, sync).
-   Includes `sf_triggers.py` for Apex Trigger management (disable, enable).
-   Comprehensive safety checks for production orgs.
-   Detailed usage, examples, and troubleshooting.
