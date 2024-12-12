# Description: Generate documentation for Python code using OpenAI's GPT-3.
from typing import Dict, List, Optional
import logging
from dataclasses import dataclass
from datetime import datetime
import asyncio

from .groq_client import GroqClient

logger = logging.getLogger(__name__)

@dataclass
class DocumentationConfig:
    include_examples: bool = True
    include_types: bool = True
    include_parameters: bool = True
    include_returns: bool = True
    include_errors: bool = True
    include_usage: bool = True
    format: str = "markdown"

class DocGenerationError(Exception):
    """Base exception for documentation generation."""
    pass

class DocumentationGenerator:
    def __init__(self, groq_client: GroqClient):
        self.groq_client = groq_client
        self.default_config = DocumentationConfig()

    async def generate_function_docs(
        self,
        code: str,
        config: Optional[DocumentationConfig] = None
    ) -> str:
        """Generate documentation for a Python function."""
        config = config or self.default_config
        
        try:
            prompt = self._create_function_doc_prompt(code, config)
            response = await self.groq_client.generate_documentation(prompt)
            return self._format_documentation(response, config.format)
        
        except Exception as e:
            logger.error(f"Error generating function documentation: {str(e)}")
            raise DocGenerationError(f"Failed to generate function documentation: {str(e)}")

    async def generate_class_docs(
        self,
        code: str,
        config: Optional[DocumentationConfig] = None
    ) -> str:
        """Generate documentation for a Python class."""
        config = config or self.default_config
        
        try:
            prompt = self._create_class_doc_prompt(code, config)
            response = await self.groq_client.generate_documentation(prompt)
            return self._format_documentation(response, config.format)
        
        except Exception as e:
            logger.error(f"Error generating class documentation: {str(e)}")
            raise DocGenerationError(f"Failed to generate class documentation: {str(e)}")

    async def generate_module_docs(
        self,
        code: str,
        config: Optional[DocumentationConfig] = None
    ) -> str:
        """Generate documentation for a Python module."""
        config = config or self.default_config
        
        try:
            prompt = self._create_module_doc_prompt(code, config)
            response = await self.groq_client.generate_documentation(prompt)
            return self._format_documentation(response, config.format)
        
        except Exception as e:
            logger.error(f"Error generating module documentation: {str(e)}")
            raise DocGenerationError(f"Failed to generate module documentation: {str(e)}")

    def _create_function_doc_prompt(self, code: str, config: DocumentationConfig) -> str:
        """Create prompt for function documentation."""
        prompt_parts = [
            "Generate comprehensive Python function documentation with the following requirements:",
            "1. Clear description of functionality",
            "2. Proper formatting and structure"
        ]

        if config.include_parameters:
            prompt_parts.append("3. Parameter descriptions with types")
        
        if config.include_returns:
            prompt_parts.append("4. Return value details")
        
        if config.include_examples:
            prompt_parts.append("5. Usage examples")
        
        if config.include_errors:
            prompt_parts.append("6. Possible exceptions")

        prompt_parts.extend([
            "\nFunction code:",
            code,
            "\nPlease provide detailed documentation following these requirements."
        ])

        return "\n".join(prompt_parts)

    def _create_class_doc_prompt(self, code: str, config: DocumentationConfig) -> str:
        """Create prompt for class documentation."""
        prompt_parts = [
            "Generate comprehensive Python class documentation with the following requirements:",
            "1. Class purpose and overview",
            "2. Proper formatting and structure",
            "3. Method descriptions"
        ]

        if config.include_parameters:
            prompt_parts.append("4. Constructor parameters")
        
        if config.include_types:
            prompt_parts.append("5. Attribute types")
        
        if config.include_examples:
            prompt_parts.append("6. Usage examples")
        
        if config.include_errors:
            prompt_parts.append("7. Possible exceptions")

        prompt_parts.extend([
            "\nClass code:",
            code,
            "\nPlease provide detailed documentation following these requirements."
        ])

        return "\n".join(prompt_parts)

    def _create_module_doc_prompt(self, code: str, config: DocumentationConfig) -> str:
        """Create prompt for module documentation."""
        prompt_parts = [
            "Generate comprehensive Python module documentation with the following requirements:",
            "1. Module purpose and overview",
            "2. Proper formatting and structure",
            "3. Class and function listings"
        ]

        if config.include_examples:
            prompt_parts.append("4. Usage examples")
        
        if config.include_types:
            prompt_parts.append("5. Type information")
        
        if config.include_errors:
            prompt_parts.append("6. Common errors and solutions")

        prompt_parts.extend([
            "\nModule code:",
            code,
            "\nPlease provide detailed documentation following these requirements."
        ])

        return "\n".join(prompt_parts)

    def _format_documentation(self, doc_text: str, format_type: str) -> str:
        """Format the documentation according to specified format."""
        if format_type == "markdown":
            return self._format_markdown(doc_text)
        elif format_type == "rst":
            return self._format_rst(doc_text)
        else:
            return doc_text

    def _format_markdown(self, doc_text: str) -> str:
        """Format documentation as Markdown."""
        # Add any markdown-specific formatting
        return doc_text

    def _format_rst(self, doc_text: str) -> str:
        """Format documentation as ReStructuredText."""
        # Add any RST-specific formatting
        return doc_text

    async def generate_project_docs(
        self,
        files: Dict[str, str],
        config: Optional[DocumentationConfig] = None
    ) -> Dict[str, str]:
        """Generate documentation for multiple files in a project."""
        config = config or self.default_config
        documentation = {}
        
        try:
            for filename, code in files.items():
                if filename.endswith('.py'):
                    if 'class' in code.lower():
                        doc = await self.generate_class_docs(code, config)
                    else:
                        doc = await self.generate_module_docs(code, config)
                    documentation[filename] = doc
            
            return documentation
            
        except Exception as e:
            logger.error(f"Error generating project documentation: {str(e)}")
            raise DocGenerationError(f"Failed to generate project documentation: {str(e)}")

    async def update_existing_docs(
        self,
        code: str,
        existing_docs: str,
        config: Optional[DocumentationConfig] = None
    ) -> str:
        """Update existing documentation based on code changes."""
        config = config or self.default_config
        
        try:
            prompt = f"""
            Update the following documentation based on the current code.
            Keep the existing structure and style, but update content as needed.
            
            Existing documentation:
            {existing_docs}
            
            Current code:
            {code}
            
            Please provide updated documentation following the existing format.
            """
            
            response = await self.groq_client.generate_documentation(prompt)
            return self._format_documentation(response, config.format)
            
        except Exception as e:
            logger.error(f"Error updating documentation: {str(e)}")
            raise DocGenerationError(f"Failed to update documentation: {str(e)}")

# Example usage
if __name__ == "__main__":
    async def main():
        from .groq_client import GroqClient
        
        # Initialize clients
        groq_client = GroqClient(api_key="your-key")
        doc_generator = DocumentationGenerator(groq_client)
        
        # Example code to document
        example_code = """
        def calculate_total(items: List[Dict]) -> float:
            '''Calculate total value of items.'''
            total = 0.0
            for item in items:
                total += item.get('price', 0) * item.get('quantity', 0)
            return total
        """
        
        try:
            # Generate documentation
            docs = await doc_generator.generate_function_docs(
                example_code,
                DocumentationConfig(include_examples=True)
            )
            print("Generated Documentation:")
            print(docs)
            
        except DocGenerationError as e:
            print(f"Error: {str(e)}")

    asyncio.run(main())
