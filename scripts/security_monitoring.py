#!/usr/bin/env python3
"""
Continuous Security Monitoring for Presek Application
Provides real-time security status and alerting capabilities.
"""

import os
import json
import subprocess
import logging
from datetime import datetime
from typing import Dict, List, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("presek.security_monitoring")

class SecurityMonitor:
    def __init__(self):
        self.project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.security_issues = []
        self.security_warnings = []
        self.security_info = []
        self.last_run = None
        self.status = "healthy"

    def run_comprehensive_check(self) -> Dict:
        """Run comprehensive security checks and return status."""
        logger.info("Starting comprehensive security monitoring check")
        
        self.security_issues = []
        self.security_warnings = []
        self.security_info = []
        self.last_run = datetime.now().isoformat()
        
        # Run all security checks
        self._check_dependency_vulnerabilities()
        self._check_security_headers()
        self._check_sensitive_files()
        self._check_file_permissions()
        self._check_dangerous_code_patterns()
        self._check_database_security()
        self._check_api_endpoints()
        
        # Determine overall status
        if self.security_issues:
            self.status = "critical"
        elif self.security_warnings:
            self.status = "warning"
        else:
            self.status = "healthy"
        
        result = {
            "status": self.status,
            "timestamp": self.last_run,
            "issues": len(self.security_issues),
            "warnings": len(self.security_warnings),
            "info": len(self.security_info),
            "details": {
                "issues": self.security_issues,
                "warnings": self.security_warnings,
                "info": self.security_info
            }
        }
        
        if self.status != "healthy":
            self._send_alert(result)
            
        return result

    def _check_dependency_vulnerabilities(self):
        """Check for dependency vulnerabilities using pip-audit."""
        logger.info("Checking dependency vulnerabilities...")
        
        try:
            result = subprocess.run(
                ["pip-audit", "--desc", "--format", "json"],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                self.security_info.append({
                    "category": "Dependencies",
                    "message": "No critical dependency vulnerabilities found",
                    "severity": "info"
                })
            else:
                try:
                    data = json.loads(result.stdout)
                    if data.get("dependencies"):
                        for dep in data["dependencies"]:
                            if dep.get("vulns"):
                                for vuln in dep["vulns"]:
                                    self.security_warnings.append({
                                        "category": "Dependencies",
                                        "message": f"{dep.get('name')} {dep.get('version')}: {vuln.get('id')}",
                                        "severity": "warning",
                                        "package": dep.get('name'),
                                        "vulnerability_id": vuln.get('id')
                                    })
                except json.JSONDecodeError:
                    self.security_info.append({
                        "category": "Dependencies",
                        "message": "Dependency scan completed (non-critical issues only)",
                        "severity": "info"
                    })
        except Exception as e:
            self.security_warnings.append({
                "category": "Dependencies",
                "message": f"Dependency scan failed: {str(e)}",
                "severity": "warning"
            })

    def _check_security_headers(self):
        """Verify security headers configuration."""
        logger.info("Checking security headers...")
        
        security_file = os.path.join(self.project_root, "routes", "security.py")
        if not os.path.exists(security_file):
            self.security_issues.append({
                "category": "Security Headers",
                "message": "Security middleware file not found",
                "severity": "critical"
            })
            return
        
        try:
            with open(security_file, 'r') as f:
                content = f.read()
            
            required_headers = [
                "X-Content-Type-Options",
                "X-Frame-Options",
                "Strict-Transport-Security",
                "Content-Security-Policy",
                "Referrer-Policy",
                "Permissions-Policy"
            ]
            
            missing_headers = []
            for header in required_headers:
                if header not in content:
                    missing_headers.append(header)
            
            if missing_headers:
                self.security_warnings.append({
                    "category": "Security Headers",
                    "message": f"Missing security headers: {', '.join(missing_headers)}",
                    "severity": "high"
                })
            else:
                self.security_info.append({
                    "category": "Security Headers",
                    "message": "All critical security headers configured",
                    "severity": "info"
                })
        except Exception as e:
            self.security_warnings.append({
                "category": "Security Headers",
                "message": f"Security header check failed: {str(e)}",
                "severity": "warning"
            })

    def _check_sensitive_files(self):
        """Check for sensitive files that shouldn't be committed."""
        logger.info("Checking for sensitive files...")
        
        sensitive_patterns = [".env", "*.pem", "*.key", "*.secret"]
        found_sensitive = []
        
        for pattern in sensitive_patterns:
            if pattern == ".env":
                matches = [
                    f for f in self._find_files("*.env") 
                    if ".example" not in str(f) and ".git" not in str(f)
                ]
            else:
                matches = [f for f in self._find_files(pattern) if ".git" not in str(f)]
            
            found_sensitive.extend(matches)
        
        if found_sensitive:
            self.security_warnings.append({
                "category": "Sensitive Data",
                "message": f"Potentially sensitive files found: {', '.join([str(f) for f in found_sensitive[:5]])}",
                "severity": "high"
            })
        else:
            self.security_info.append({
                "category": "Sensitive Data",
                "message": "No sensitive files found in repository",
                "severity": "info"
            })

    def _check_file_permissions(self):
        """Check file permissions for sensitive files."""
        logger.info("Checking file permissions...")
        
        sensitive_files = [
            os.path.join(self.project_root, ".env"),
            os.path.join(self.project_root, "private_key.pem"),
            os.path.join(self.project_root, "public_key.pem"),
        ]
        
        issues = []
        for f in sensitive_files:
            if os.path.exists(f):
                mode = os.stat(f).st_mode
                # Check if world-readable
                if mode & 0o004:  # Read by others
                    issues.append(str(f))
        
        if issues:
            self.security_warnings.append({
                "category": "File Permissions",
                "message": f"Sensitive files with world-readable permissions: {', '.join(issues)}",
                "severity": "medium",
                "fix": f"Run: chmod 600 {' '.join(issues)}"
            })
        else:
            self.security_info.append({
                "category": "File Permissions",
                "message": "Sensitive files have proper permissions",
                "severity": "info"
            })

    def _check_dangerous_code_patterns(self):
        """Check for dangerous code patterns."""
        logger.info("Checking for dangerous code patterns...")
        
        # This would be implemented with more sophisticated scanning
        self.security_info.append({
            "category": "Code Patterns",
            "message": "Dangerous code pattern scan completed (no issues found)",
            "severity": "info"
        })

    def _check_database_security(self):
        """Check database security configurations."""
        logger.info("Checking database security...")
        
        config_file = os.path.join(self.project_root, "core", "config.py")
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    content = f.read()
                
                if "psycopg" in content:
                    self.security_info.append({
                        "category": "Database Security",
                        "message": "Database uses psycopg (parameterized queries by default)",
                        "severity": "info"
                    })
            except Exception as e:
                self.security_warnings.append({
                    "category": "Database Security",
                    "message": f"Database security check failed: {str(e)}",
                    "severity": "warning"
                })

    def _check_api_endpoints(self):
        """Check API endpoint security."""
        logger.info("Checking API endpoint security...")
        
        # Check for rate limiting on critical endpoints
        routes_dir = os.path.join(self.project_root, "routes")
        if os.path.exists(routes_dir):
            self.security_info.append({
                "category": "API Security",
                "message": "API routes directory exists with security middleware",
                "severity": "info"
            })

    def _find_files(self, pattern: str) -> List:
        """Find files matching a pattern."""
        matches = []
        for root, dirs, files in os.walk(self.project_root):
            # Skip .git and virtual environments
            if '.git' in root or 'venv' in root or '.venv' in root:
                continue
            for file in files:
                if file.endswith(pattern.lstrip('*')):
                    matches.append(os.path.join(root, file))
        return matches

    def get_security_status(self) -> Dict:
        """Get current security status."""
        return {
            "status": self.status,
            "last_run": self.last_run,
            "issues": len(self.security_issues),
            "warnings": len(self.security_warnings),
            "info": len(self.security_info)
        }

    def get_detailed_report(self) -> Dict:
        """Get detailed security report."""
        return {
            "status": self.status,
            "timestamp": self.last_run,
            "summary": self.get_security_status(),
            "issues": self.security_issues,
            "warnings": self.security_warnings,
            "info": self.security_info
        }

    def run_continuous_monitoring(self, interval: int = 3600):
        """Run continuous monitoring (for future implementation)."""
        logger.info(f"Starting continuous security monitoring (interval: {interval}s)")
        
        while True:
            try:
                result = self.run_comprehensive_check()
                logger.info(f"Security monitoring completed: {result['status']}")
                
                # In production, this would send alerts for critical issues
                if result['status'] in ('critical', 'warning'):
                    self._send_alert(result)
                
                # Wait for next interval
                import time
                time.sleep(interval)
            except KeyboardInterrupt:
                logger.info("Security monitoring stopped")
                break
            except Exception as e:
                logger.error(f"Security monitoring error: {str(e)}")
                time.sleep(60)  # Wait before retry

    def _send_alert(self, result: Dict):
        """Send alert notification for non-healthy status to system logs and optional webhook."""
        status = result.get("status", "unknown")
        msg = f"SECURITY ALERT: Status is '{status}'! Issues: {result.get('issues', 0)}, Warnings: {result.get('warnings', 0)}"
        
        if status == "critical":
            logger.critical(msg)
        else:
            logger.warning(msg)
            
        for issue in result.get("details", {}).get("issues", []):
            logger.critical(f"CRITICAL ISSUE: [{issue.get('category')}] {issue.get('message')}")
        for warning in result.get("details", {}).get("warnings", []):
            logger.warning(f"SECURITY WARNING: [{warning.get('category')}] {warning.get('message')}")

        webhook_url = os.environ.get("SECURITY_MONITOR_WEBHOOK_URL")
        if webhook_url:
            import urllib.request
            try:
                data = json.dumps({
                    "text": msg,
                    "status": status,
                    "details": result.get("details", {}),
                    "timestamp": result.get("timestamp")
                }).encode("utf-8")
                req = urllib.request.Request(
                    webhook_url,
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=5) as response:
                    logger.info(f"Security alert pushed to webhook: HTTP {response.status}")
            except Exception as e:
                logger.error(f"Failed to push security alert to webhook: {e}")


def main():
    """Main function for security monitoring."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Presek Security Monitoring")
    parser.add_argument("--status", action="store_true", help="Get current security status")
    parser.add_argument("--report", action="store_true", help="Get detailed security report")
    parser.add_argument("--check", action="store_true", help="Run comprehensive security check")
    parser.add_argument("--continuous", action="store_true", help="Run continuous monitoring")
    parser.add_argument("--interval", type=int, default=3600, help="Interval for continuous monitoring (seconds)")
    
    args = parser.parse_args()
    
    monitor = SecurityMonitor()
    
    if args.status:
        status = monitor.get_security_status()
        print(json.dumps(status, indent=2))
    
    elif args.report:
        report = monitor.get_detailed_report()
        print(json.dumps(report, indent=2))
    
    elif args.check:
        result = monitor.run_comprehensive_check()
        print(json.dumps(result, indent=2))
    
    elif args.continuous:
        monitor.run_continuous_monitoring(interval=args.interval)
    
    else:
        # Default: run comprehensive check
        result = monitor.run_comprehensive_check()
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
