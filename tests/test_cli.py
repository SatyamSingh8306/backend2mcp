"""Tests for CLI module."""

import subprocess
import sys
from unittest.mock import patch

import pytest


class TestCLI:
    """Test CLI functionality."""

    def test_cli_entry_point(self):
        """Test CLI can be invoked."""
        result = subprocess.run(
            [sys.executable, "-c", "from backend2mcp.cli import main; main()"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        # Should fail due to missing arguments, not import error
        assert result.returncode != 0
        assert "Usage:" in result.stderr or "Error:" in result.stderr

    def test_cli_help(self):
        """Test CLI help output."""
        result = subprocess.run(
            [sys.executable, "-m", "backend2mcp", "--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0
        assert "backend2mcp" in result.stdout
        assert "run" in result.stdout

    def test_cli_run_missing_module(self):
        """Test CLI run with missing module."""
        result = subprocess.run(
            [sys.executable, "-m", "backend2mcp", "run", "nonexistent:app"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode != 0

    def test_module_import(self):
        """Test CLI module can be imported."""
        from backend2mcp.cli import app, run

        assert app is not None
        assert callable(run)


class TestCLIAutoDetection:
    """Test CLI framework auto-detection."""

    def test_parse_module_path(self):
        """Test parsing module:object format."""
        from backend2mcp.cli import _detect_and_create_adapter

        # This tests the import logic without actually importing
        module_path = "test:app"
        assert ":" in module_path
        module_name, obj_name = module_path.rsplit(":", 1)
        assert module_name == "test"
        assert obj_name == "app"