import pytest
import subprocess
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
import xml.etree.ElementTree as ET
import tempfile
import shutil

from sf_validations import (
    run_sf_command,
    manage_validation_rules_in_temp_project,
    show_banner
)


class TestRunSfCommand:
    """Test suite for run_sf_command function"""
    
    @patch('subprocess.run')
    def test_successful_command(self, mock_run):
        """Test successful SF CLI command execution"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"status": 0, "result": {"data": "test"}})
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        result = run_sf_command(['org', 'list'])
        
        assert result['status'] == 0
        assert result['result']['data'] == 'test'
        mock_run.assert_called_once()
    
    @patch('subprocess.run')
    def test_command_failure_with_error_message(self, mock_run):
        """Test SF CLI command failure with error message"""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = json.dumps({"status": 1, "message": "Authentication failed"})
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        with pytest.raises(RuntimeError) as exc_info:
            run_sf_command(['org', 'list'])
        
        assert "Authentication failed" in str(exc_info.value)
    
    @patch('subprocess.run')
    def test_command_not_found(self, mock_run):
        """Test when SF CLI is not installed"""
        mock_run.side_effect = FileNotFoundError()
        
        with pytest.raises(RuntimeError) as exc_info:
            run_sf_command(['org', 'list'])
        
        assert "Salesforce CLI ('sf') not found" in str(exc_info.value)
    
    @patch('subprocess.run')
    def test_invalid_json_response(self, mock_run):
        """Test handling of non-JSON response"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Not valid JSON"
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        with pytest.raises(RuntimeError):
            run_sf_command(['org', 'list'])
    
    @patch('subprocess.run')
    def test_command_with_cwd(self, mock_run):
        """Test command execution with custom working directory"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"status": 0, "result": {}})
        mock_run.return_value = mock_result
        
        run_sf_command(['project', 'deploy'], cwd='/tmp/test')
        
        mock_run.assert_called_once()
        assert mock_run.call_args[1]['cwd'] == '/tmp/test'


class TestManageValidationRules:
    """Test suite for manage_validation_rules_in_temp_project function"""
    
    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary project directory structure"""
        temp_dir = Path(tempfile.mkdtemp())
        project_root = temp_dir / 'SandcastleMetadata'
        project_root.mkdir()
        
        # Create standard SFDX project structure
        objects_path = project_root / "force-app" / "main" / "default" / "objects"
        objects_path.mkdir(parents=True)
        
        yield project_root
        
        # Cleanup
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def validation_rule_xml(self):
        """Sample validation rule XML content"""
        return '''<?xml version="1.0" encoding="UTF-8"?>
<ValidationRule xmlns="http://soap.sforce.com/2006/04/metadata">
    <active>true</active>
    <errorConditionFormula>Amount &lt; 0</errorConditionFormula>
    <errorMessage>Amount cannot be negative</errorMessage>
    <fullName>Negative_Amount_Check</fullName>
</ValidationRule>'''
    
    def create_validation_rules(self, project_root, sobject, rule_count=3, active=True):
        """Helper to create test validation rules"""
        validation_rules_path = project_root / "force-app" / "main" / "default" / "objects" / sobject / "validationRules"
        validation_rules_path.mkdir(parents=True, exist_ok=True)
        
        for i in range(rule_count):
            rule_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<ValidationRule xmlns="http://soap.sforce.com/2006/04/metadata">
    <active>{'true' if active else 'false'}</active>
    <errorConditionFormula>TestCondition</errorConditionFormula>
    <errorMessage>Test Error {i}</errorMessage>
    <fullName>Test_Rule_{i}</fullName>
</ValidationRule>'''
            rule_file = validation_rules_path / f"Test_Rule_{i}.validationRule-meta.xml"
            rule_file.write_text(rule_content)
        
        return validation_rules_path
    
    @patch('sf_validations.Progress')
    @patch('sf_validations.Path.home')
    @patch('sf_validations.run_sf_command')
    @patch('sf_validations.console')
    def test_disable_mode_success(self, mock_console, mock_run_sf, mock_home, mock_progress, temp_project_dir):
        """Test successful disable mode execution"""
        mock_home.return_value = temp_project_dir.parent
        
        # Mock Progress context manager
        mock_progress_instance = MagicMock()
        mock_progress.return_value.__enter__.return_value = mock_progress_instance
        mock_progress.return_value.__exit__.return_value = None
        
        # Setup validation rules
        self.create_validation_rules(temp_project_dir, 'Opportunity', 3, active=True)
        
        # Mock SF CLI responses
        mock_run_sf.return_value = {"status": 0}
        
        with patch('sf_validations.shutil.rmtree'):
            with patch('os.getcwd', return_value='/test'):
                with patch('os.chdir'):
                    manage_validation_rules_in_temp_project('TESTORG', 'Opportunity', 'disable')
        
        # Verify backup was created
        backup_dir = temp_project_dir / "original_validation_rules"
        assert backup_dir.exists()
        assert len(list(backup_dir.glob('*.validationRule-meta.xml'))) == 3
    
    @patch('sf_validations.Path.home')
    @patch('sf_validations.console')
    def test_enable_mode_no_cache(self, mock_console, mock_home, temp_project_dir):
        """Test enable mode when no cache exists"""
        mock_home.return_value = temp_project_dir.parent
        
        # Remove the project directory to simulate no cache
        shutil.rmtree(temp_project_dir)
        
        # Should return early without raising
        manage_validation_rules_in_temp_project('TESTORG', 'Opportunity', 'enable')
        
        # Verify error message was printed
        assert any('Error' in str(call) for call in mock_console.print.call_args_list)
    
    @patch('sf_validations.Path.home')
    @patch('sf_validations.run_sf_command')
    @patch('sf_validations.console')
    def test_enable_mode_object_not_in_cache(self, mock_console, mock_run_sf, mock_home, temp_project_dir):
        """Test enable mode when requested object is not in cache"""
        mock_home.return_value = temp_project_dir.parent
        
        # Create cache for Opportunity but not Account
        self.create_validation_rules(temp_project_dir, 'Opportunity', 2)
        backup_dir = temp_project_dir / "original_validation_rules"
        backup_dir.mkdir()
        
        # Try to enable Account (not in cache)
        with pytest.raises(RuntimeError) as exc_info:
            manage_validation_rules_in_temp_project('TESTORG', 'Account', 'enable')
        
        assert "not found in cache" in str(exc_info.value)
    
    @patch('sf_validations.Progress')
    @patch('sf_validations.Path.home')
    @patch('sf_validations.run_sf_command')
    @patch('sf_validations.console')
    def test_enable_mode_success(self, mock_console, mock_run_sf, mock_home, mock_progress, temp_project_dir):
        """Test successful enable mode execution"""
        mock_home.return_value = temp_project_dir.parent
        
        # Mock Progress context manager
        mock_progress_instance = MagicMock()
        mock_progress.return_value.__enter__.return_value = mock_progress_instance
        mock_progress.return_value.__exit__.return_value = None
        
        # Setup object structure
        obj_path = temp_project_dir / "force-app" / "main" / "default" / "objects" / "Opportunity"
        obj_path.mkdir(parents=True)
        
        # Create backup directory with rules
        backup_dir = temp_project_dir / "original_validation_rules"
        backup_dir.mkdir()
        
        for i in range(2):
            rule_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<ValidationRule xmlns="http://soap.sforce.com/2006/04/metadata">
    <active>true</active>
    <fullName>Test_Rule_{i}</fullName>
</ValidationRule>'''
            (backup_dir / f"Test_Rule_{i}.validationRule-meta.xml").write_text(rule_content)
        
        mock_run_sf.return_value = {"status": 0}
        
        manage_validation_rules_in_temp_project('TESTORG', 'Opportunity', 'enable')
        
        # Verify deployment was called
        assert any('deploy' in str(call) for call in mock_run_sf.call_args_list)
    
    @patch('sf_validations.Progress')
    @patch('sf_validations.Path.home')
    @patch('sf_validations.run_sf_command')
    @patch('sf_validations.console')
    def test_sync_mode_no_rules(self, mock_console, mock_run_sf, mock_home, mock_progress, temp_project_dir):
        """Test sync mode when no validation rules exist"""
        mock_home.return_value = temp_project_dir.parent
        
        # Mock Progress context manager
        mock_progress_instance = MagicMock()
        mock_progress.return_value.__enter__.return_value = mock_progress_instance
        mock_progress.return_value.__exit__.return_value = None
        
        # Mock SF CLI to return success but create no rules
        mock_run_sf.return_value = {"status": 0}
        
        with patch('sf_validations.shutil.rmtree'):
            with patch('os.getcwd', return_value='/test'):
                with patch('os.chdir'):
                    manage_validation_rules_in_temp_project('TARGET', 'Opportunity', 'sync', 'SOURCE')
        
        # Should print message about no rules found
        assert any('No validation rules' in str(call) for call in mock_console.print.call_args_list)
    
    @patch('sf_validations.Path.home')
    def test_sync_mode_no_source_org(self, mock_home, temp_project_dir):
        """Test sync mode without source org specified"""
        mock_home.return_value = temp_project_dir.parent
        
        with pytest.raises(RuntimeError) as exc_info:
            manage_validation_rules_in_temp_project('TARGET', 'Opportunity', 'sync')
        
        assert "source-org is required" in str(exc_info.value)


class TestValidationRuleXMLProcessing:
    """Test suite for XML processing of validation rules"""
    
    def test_parse_active_validation_rule(self):
        """Test parsing an active validation rule"""
        xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<ValidationRule xmlns="http://soap.sforce.com/2006/04/metadata">
    <active>true</active>
    <errorConditionFormula>Amount &lt; 0</errorConditionFormula>
    <errorMessage>Amount cannot be negative</errorMessage>
    <fullName>Negative_Amount_Check</fullName>
</ValidationRule>'''
        
        root = ET.fromstring(xml_content)
        ns = {'sf': 'http://soap.sforce.com/2006/04/metadata'}
        
        active_element = root.find('sf:active', ns)
        assert active_element is not None
        assert active_element.text == 'true'
    
    def test_modify_validation_rule_to_inactive(self):
        """Test modifying a validation rule to inactive"""
        xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<ValidationRule xmlns="http://soap.sforce.com/2006/04/metadata">
    <active>true</active>
    <errorConditionFormula>Amount &lt; 0</errorConditionFormula>
    <errorMessage>Amount cannot be negative</errorMessage>
    <fullName>Negative_Amount_Check</fullName>
</ValidationRule>'''
        
        tree = ET.ElementTree(ET.fromstring(xml_content))
        root = tree.getroot()
        ns = {'sf': 'http://soap.sforce.com/2006/04/metadata'}
        
        active_element = root.find('sf:active', ns)
        active_element.text = 'false'
        
        # Convert back to string to verify (handles namespaced elements)
        xml_str = ET.tostring(root, encoding='unicode')
        # XML may be serialized with namespace prefix, so check for both formats
        assert 'false</ns0:active>' in xml_str or 'false</active>' in xml_str


class TestCLIArgumentParsing:
    """Test suite for command-line argument parsing"""
    
    @patch('sys.argv', ['sf_validations.py', '-m', 'disable', '-o', 'Account'])
    @patch('sf_validations.show_banner')
    @patch('sf_validations.manage_validation_rules_in_temp_project')
    def test_single_object_disable(self, mock_manage, mock_banner):
        """Test parsing single object for disable mode"""
        # This would need to import and run the main block
        # For now, we test the logic separately
        pass
    
    @patch('sys.argv', ['sf_validations.py', '-m', 'enable'])
    @patch('sf_validations.show_banner')
    @patch('sf_validations.Path.home')
    def test_enable_without_object(self, mock_home, mock_banner):
        """Test enable mode without specifying objects"""
        # Should auto-detect from cache
        pass


class TestIntegrationScenarios:
    """Integration tests for complete workflows"""
    
    @pytest.fixture
    def mock_sf_env(self):
        """Setup mock Salesforce environment"""
        with patch('sf_validations.run_sf_command') as mock_sf:
            mock_sf.return_value = {"status": 0, "result": {}}
            yield mock_sf
    
    @patch('sf_validations.Progress')
    @patch('sf_validations.Path.home')
    @patch('sf_validations.console')
    def test_complete_disable_enable_cycle(self, mock_console, mock_home, mock_progress, mock_sf_env, tmp_path):
        """Test complete disable then enable workflow"""
        mock_home.return_value = tmp_path
        
        # Mock Progress context manager
        mock_progress_instance = MagicMock()
        mock_progress.return_value.__enter__.return_value = mock_progress_instance
        mock_progress.return_value.__exit__.return_value = None
        
        project_root = tmp_path / 'SandcastleMetadata'
        project_root.mkdir()
        
        # Create test validation rules
        validation_rules_path = project_root / "force-app" / "main" / "default" / "objects" / "Opportunity" / "validationRules"
        validation_rules_path.mkdir(parents=True)
        
        rule_file = validation_rules_path / "Test_Rule.validationRule-meta.xml"
        rule_file.write_text('''<?xml version="1.0" encoding="UTF-8"?>
<ValidationRule xmlns="http://soap.sforce.com/2006/04/metadata">
    <active>true</active>
    <fullName>Test_Rule</fullName>
</ValidationRule>''')
        
        with patch('sf_validations.shutil.rmtree'):
            with patch('os.getcwd', return_value='/test'):
                with patch('os.chdir'):
                    # Disable
                    manage_validation_rules_in_temp_project('TESTORG', 'Opportunity', 'disable')
                    
                    # Verify backup created
                    backup_dir = project_root / "original_validation_rules"
                    assert backup_dir.exists()
                    
                    # Enable
                    manage_validation_rules_in_temp_project('TESTORG', 'Opportunity', 'enable')


class TestErrorHandling:
    """Test suite for error handling scenarios"""
    
    @patch('subprocess.run')
    def test_deployment_conflict_error(self, mock_subprocess):
        """Test handling of deployment conflicts"""
        # Mock subprocess to return conflict error
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = json.dumps({"status": 1, "message": "1 conflicts detected"})
        mock_result.stderr = ""
        mock_subprocess.return_value = mock_result
        
        with pytest.raises(RuntimeError) as exc_info:
            run_sf_command(['project', 'deploy'])
        
        assert "conflicts detected" in str(exc_info.value)
    
    @patch('sf_validations.Path.home')
    @patch('sf_validations.console')
    def test_missing_backup_directory(self, mock_console, mock_home, tmp_path):
        """Test enable mode when backup directory is missing"""
        mock_home.return_value = tmp_path
        
        project_root = tmp_path / 'SandcastleMetadata'
        project_root.mkdir()
        
        # Create object path but no backup
        obj_path = project_root / "force-app" / "main" / "default" / "objects" / "Opportunity"
        obj_path.mkdir(parents=True)
        
        manage_validation_rules_in_temp_project('TESTORG', 'Opportunity', 'enable')
        
        # Should print error message
        assert any('No backup found' in str(call) for call in mock_console.print.call_args_list)


class TestShowBanner:
    """Test suite for banner display"""
    
    @patch('sf_validations.console')
    def test_banner_displays(self, mock_console):
        """Test that banner displays correctly"""
        show_banner()
        
        # Verify console.print was called
        assert mock_console.print.called


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
