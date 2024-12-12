import ast
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum
import re
from datetime import datetime

logger = logging.getLogger(__name__)

class SecurityLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class BestPracticeLevel(Enum):
    SUGGESTION = "suggestion"
    RECOMMENDED = "recommended"
    REQUIRED = "required"

@dataclass
class SecurityIssue:
    description: str
    level: SecurityLevel
    line_number: int
    code_snippet: str
    recommendation: str

@dataclass
class BestPracticeIssue:
    description: str
    level: BestPracticeLevel
    line_number: int
    current_practice: str
    recommended_practice: str

@dataclass
class PerformanceIssue:
    description: str
    impact: str
    line_number: int
    suggestion: str
    estimated_improvement: str

@dataclass
class DocumentationIssue:
    description: str
    missing_elements: List[str]
    line_number: int
    suggestion: str

@dataclass
class AnalysisReport:
    timestamp: datetime
    code_hash: str
    security_score: float
    best_practices_score: float
    performance_score: float
    documentation_score: float
    overall_score: float
    security_issues: List[SecurityIssue]
    best_practice_issues: List[BestPracticeIssue]
    performance_issues: List[PerformanceIssue]
    documentation_issues: List[DocumentationIssue]
    summary: str
    recommendations: List[str]

class CodeAnalyzer:
    def __init__(self):
        self.security_patterns = {
            'sql_injection': r'execute\s*\(\s*["\'].*?\%.*?["\']\s*\)',
            'command_injection': r'os\.system\(|subprocess\.call\(',
            'unsafe_deserialization': r'pickle\.loads|yaml\.load\(',
            'hardcoded_secrets': r'password\s*=\s*["\'][^"\']+["\']|api_key\s*=\s*["\'][^"\']+["\']'
        }

        self.best_practice_patterns = {
            'naming_convention': {
                'function': r'^[a-z_][a-z0-9_]*$',
                'class': r'^[A-Z][a-zA-Z0-9]*$',
                'constant': r'^[A-Z_][A-Z0-9_]*$'
            },
            'max_line_length': 80,
            'max_function_length': 50
        }

    async def analyze_code(self, code: str) -> AnalysisReport:
        """Analyze code and generate a comprehensive report."""
        try:
            # Parse the code
            tree = ast.parse(code)
            
            # Perform various analyses
            security_issues = await self._analyze_security(code, tree)
            best_practice_issues = await self._analyze_best_practices(code, tree)
            performance_issues = await self._analyze_performance(code, tree)
            documentation_issues = await self._analyze_documentation(code, tree)
            
            # Calculate scores
            security_score = self._calculate_security_score(security_issues)
            best_practices_score = self._calculate_best_practices_score(best_practice_issues)
            performance_score = self._calculate_performance_score(performance_issues)
            documentation_score = self._calculate_documentation_score(documentation_issues)
            
            # Calculate overall score
            overall_score = (security_score * 0.4 +
                           best_practices_score * 0.3 +
                           performance_score * 0.2 +
                           documentation_score * 0.1)
            
            # Generate report
            report = AnalysisReport(
                timestamp=datetime.now(),
                code_hash=hash(code),
                security_score=security_score,
                best_practices_score=best_practices_score,
                performance_score=performance_score,
                documentation_score=documentation_score,
                overall_score=overall_score,
                security_issues=security_issues,
                best_practice_issues=best_practice_issues,
                performance_issues=performance_issues,
                documentation_issues=documentation_issues,
                summary=self._generate_summary(
                    security_issues,
                    best_practice_issues,
                    performance_issues,
                    documentation_issues
                ),
                recommendations=self._generate_recommendations(
                    security_issues,
                    best_practice_issues,
                    performance_issues,
                    documentation_issues
                )
            )
            
            return report
            
        except Exception as e:
            logger.error(f"Error analyzing code: {str(e)}")
            raise

    async def _analyze_security(self, code: str, tree: ast.AST) -> List[SecurityIssue]:
        """Analyze code for security issues."""
        issues = []
        
        # Check for known security patterns
        for line_num, line in enumerate(code.split('\n'), 1):
            for pattern_name, pattern in self.security_patterns.items():
                if re.search(pattern, line):
                    issues.append(SecurityIssue(
                        description=f"Potential {pattern_name} vulnerability detected",
                        level=SecurityLevel.HIGH,
                        line_number=line_num,
                        code_snippet=line.strip(),
                        recommendation=self._get_security_recommendation(pattern_name)
                    ))
        
        # Analyze AST for security issues
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Check for dangerous function calls
                if isinstance(node.func, ast.Name):
                    if node.func.id in ['eval', 'exec']:
                        issues.append(SecurityIssue(
                            description="Use of dangerous function detected",
                            level=SecurityLevel.CRITICAL,
                            line_number=node.lineno,
                            code_snippet=f"{node.func.id}(...)",
                            recommendation="Avoid using eval/exec as they can execute arbitrary code"
                        ))
        
        return issues

    async def _analyze_best_practices(self, code: str, tree: ast.AST) -> List[BestPracticeIssue]:
        """Analyze code for best practice violations."""
        issues = []
        
        # Check naming conventions
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if not re.match(self.best_practice_patterns['naming_convention']['function'], node.name):
                    issues.append(BestPracticeIssue(
                        description="Function naming convention violation",
                        level=BestPracticeLevel.RECOMMENDED,
                        line_number=node.lineno,
                        current_practice=node.name,
                        recommended_practice="Use snake_case for function names"
                    ))
            
            elif isinstance(node, ast.ClassDef):
                if not re.match(self.best_practice_patterns['naming_convention']['class'], node.name):
                    issues.append(BestPracticeIssue(
                        description="Class naming convention violation",
                        level=BestPracticeLevel.RECOMMENDED,
                        line_number=node.lineno,
                        current_practice=node.name,
                        recommended_practice="Use PascalCase for class names"
                    ))
        
        # Check line lengths
        for line_num, line in enumerate(code.split('\n'), 1):
            if len(line) > self.best_practice_patterns['max_line_length']:
                issues.append(BestPracticeIssue(
                    description="Line too long",
                    level=BestPracticeLevel.SUGGESTION,
                    line_number=line_num,
                    current_practice=f"Line length: {len(line)}",
                    recommended_practice=f"Keep lines under {self.best_practice_patterns['max_line_length']} characters"
                ))
        
        return issues

    async def _analyze_performance(self, code: str, tree: ast.AST) -> List[PerformanceIssue]:
        """Analyze code for performance issues."""
        issues = []
        
        for node in ast.walk(tree):
            # Check for nested loops
            if isinstance(node, ast.For):
                for child in ast.walk(node):
                    if isinstance(child, ast.For):
                        issues.append(PerformanceIssue(
                            description="Nested loop detected",
                            impact="O(n²) time complexity",
                            line_number=node.lineno,
                            suggestion="Consider using more efficient data structures or algorithms",
                            estimated_improvement="Could be O(n) with proper optimization"
                        ))
            
            # Check for multiple list/dict comprehensions
            if isinstance(node, ast.ListComp) or isinstance(node, ast.DictComp):
                if len(node.generators) > 1:
                    issues.append(PerformanceIssue(
                        description="Complex comprehension detected",
                        impact="Reduced readability and potential performance impact",
                        line_number=node.lineno,
                        suggestion="Consider breaking down into multiple steps",
                        estimated_improvement="Better readability and maintainability"
                    ))
        
        return issues

    async def _analyze_documentation(self, code: str, tree: ast.AST) -> List[DocumentationIssue]:
        """Analyze code for documentation issues."""
        issues = []
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                missing_elements = []
                
                # Check for docstring
                if ast.get_docstring(node) is None:
                    missing_elements.append("docstring")
                
                # Check function parameter documentation
                if isinstance(node, ast.FunctionDef):
                    if node.args.args and not ast.get_docstring(node):
                        missing_elements.append("parameter documentation")
                
                if missing_elements:
                    issues.append(DocumentationIssue(
                        description=f"Missing documentation in {node.name}",
                        missing_elements=missing_elements,
                        line_number=node.lineno,
                        suggestion="Add comprehensive documentation"
                    ))
        
        return issues

    def _calculate_security_score(self, issues: List[SecurityIssue]) -> float:
        """Calculate security score based on issues."""
        if not issues:
            return 100.0
            
        weights = {
            SecurityLevel.LOW: 0.2,
            SecurityLevel.MEDIUM: 0.4,
            SecurityLevel.HIGH: 0.6,
            SecurityLevel.CRITICAL: 1.0
        }
        
        total_weight = sum(weights[issue.level] for issue in issues)
        return max(0, 100 - (total_weight * 20))

    def _calculate_best_practices_score(self, issues: List[BestPracticeIssue]) -> float:
        """Calculate best practices score."""
        if not issues:
            return 100.0
            
        weights = {
            BestPracticeLevel.SUGGESTION: 0.2,
            BestPracticeLevel.RECOMMENDED: 0.5,
            BestPracticeLevel.REQUIRED: 1.0
        }
        
        total_weight = sum(weights[issue.level] for issue in issues)
        return max(0, 100 - (total_weight * 10))

    def _calculate_performance_score(self, issues: List[PerformanceIssue]) -> float:
        """Calculate performance score."""
        if not issues:
            return 100.0
        return max(0, 100 - (len(issues) * 15))

    def _calculate_documentation_score(self, issues: List[DocumentationIssue]) -> float:
        """Calculate documentation score."""
        if not issues:
            return 100.0
        return max(0, 100 - (len(issues) * 10))

    def _get_security_recommendation(self, issue_type: str) -> str:
        """Get security recommendation for specific issue type."""
        recommendations = {
            'sql_injection': "Use parameterized queries or ORM",
            'command_injection': "Use subprocess.run with shell=False",
            'unsafe_deserialization': "Use safe alternatives like json.loads",
            'hardcoded_secrets': "Use environment variables or secure secret management"
        }
        return recommendations.get(issue_type, "Review and fix security issue")

    def _generate_summary(self, security_issues, best_practice_issues,
                         performance_issues, documentation_issues) -> str:
        """Generate analysis summary."""
        total_issues = (len(security_issues) + len(best_practice_issues) +
                       len(performance_issues) + len(documentation_issues))
        
        return (
            f"Found {total_issues} issues:\n"
            f"- Security: {len(security_issues)} issues\n"
            f"- Best Practices: {len(best_practice_issues)} issues\n"
            f"- Performance: {len(performance_issues)} issues\n"
            f"- Documentation: {len(documentation_issues)} issues"
        )

    def _generate_recommendations(self, security_issues, best_practice_issues,
                                performance_issues, documentation_issues) -> List[str]:
        """Generate prioritized recommendations."""
        recommendations = []
        
        # Add critical security issues first
        for issue in security_issues:
            if issue.level == SecurityLevel.CRITICAL:
                recommendations.append(f"CRITICAL: {issue.recommendation}")
        
        # Add other high-priority issues
        for issue in security_issues:
            if issue.level == SecurityLevel.HIGH:
                recommendations.append(f"HIGH: {issue.recommendation}")
        
        # Add important best practices
        for issue in best_practice_issues:
            if issue.level == BestPracticeLevel.REQUIRED:
                recommendations.append(f"REQUIRED: {issue.recommended_practice}")
        
        return recommendations

# Example usage
if __name__ == "__main__":
    async def main():
        analyzer = CodeAnalyzer()
        
        test_code = """
def calculate_total(items):
    total = 0
    for item in items:
        for price in item.prices:  # Nested loop
            total += price
    return total
        """
        
        try:
            report = await analyzer.analyze_code(test_code)
            print(f"Analysis Report:\n{report.summary}\n")
            print(f"Overall Score: {report.overall_score:.2f}")
            print("\nRecommendations:")
            for rec in report.recommendations:
                print(f"- {rec}")
                
        except Exception as e:
            print(f"Error: {e}")

    import asyncio
    asyncio.run(main())