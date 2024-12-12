import groq
import asyncio
import logging
from typing import Dict, Any, Optional
from functools import lru_cache
from datetime import datetime, timedelta
import json
import aiohttp
import backoff
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class AnalysisResult:
    """Structure for analysis results"""
    summary: str
    recommendations: list[str]
    risk_level: str
    confidence: float
    timestamp: datetime

class PromptTemplates:
    """Manages prompt templates for different analysis types"""
    
    @staticmethod
    def code_analysis() -> str:
        return """Analyze the following code and provide:
1. A brief summary
2. Potential issues or risks
3. Best practices recommendations
4. Performance considerations

Code:
{code}
"""

    @staticmethod
    def pr_analysis() -> str:
        return """Review this Pull Request and provide:
1. Overview of changes
2. Impact analysis
3. Security considerations
4. Implementation quality
5. Recommendations

Pull Request:
{pr_content}
"""

    @staticmethod
    def documentation_generation() -> str:
        return """Generate comprehensive documentation for the following code:
1. Function/class purpose
2. Parameters description
3. Return value details
4. Usage examples
5. Important notes

Code:
{code}
"""

class GroqClient:
    def __init__(
        self,
        api_key: str,
        model_name: str = "mixtral-8x7b-32768",
        cache_ttl: int = 3600,  # 1 hour cache TTL
        max_retries: int = 3
    ):
        self.client = groq.Groq(api_key=api_key)
        self.model_name = model_name
        self.cache_ttl = cache_ttl
        self.max_retries = max_retries
        self.templates = PromptTemplates()
        
        # Initialize cache
        self._response_cache: Dict[str, Dict[str, Any]] = {}

    def _generate_cache_key(self, content: str, analysis_type: str) -> str:
        """Generate a unique cache key."""
        content_hash = hash(content)
        return f"{analysis_type}:{content_hash}"

    def _is_cached_valid(self, cache_entry: Dict[str, Any]) -> bool:
        """Check if a cache entry is still valid."""
        if not cache_entry:
            return False
        
        cached_time = cache_entry.get('timestamp')
        if not cached_time:
            return False
            
        age = datetime.now() - cached_time
        return age.seconds < self.cache_ttl

    async def _get_cached_response(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get a cached response if valid."""
        cache_entry = self._response_cache.get(cache_key)
        if cache_entry and self._is_cached_valid(cache_entry):
            logger.debug(f"Cache hit for key: {cache_key}")
            return cache_entry['response']
        return None

    def _cache_response(self, cache_key: str, response: Dict[str, Any]):
        """Cache a response."""
        self._response_cache[cache_key] = {
            'response': response,
            'timestamp': datetime.now()
        }

    @backoff.on_exception(
        backoff.expo,
        (aiohttp.ClientError, groq.error.APIError),
        max_tries=3
    )
    async def _make_groq_request(self, prompt: str) -> Dict[str, Any]:
        """Make a request to Groq API with exponential backoff retry."""
        try:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2000
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error making Groq request: {str(e)}")
            raise

    async def analyze_code(self, code: str) -> Dict[str, Any]:
        """Analyze code and provide insights."""
        cache_key = self._generate_cache_key(code, 'code_analysis')
        
        # Check cache
        cached = await self._get_cached_response(cache_key)
        if cached:
            return cached
        
        # Prepare prompt
        prompt = self.templates.code_analysis().format(code=code)
        
        try:
            # Get response from Groq
            response = await self._make_groq_request(prompt)
            
            # Parse and structure the response
            analysis = {
                'summary': '',
                'issues': [],
                'recommendations': [],
                'performance': []
            }
            
            # Process the response into structured format
            # (Implementation depends on the actual response format)
            # This is a simplified example
            analysis = json.loads(response)
            
            # Cache the result
            self._cache_response(cache_key, analysis)
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing code: {str(e)}")
            raise

    async def analyze_pr(self, pr_content: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze a pull request."""
        cache_key = self._generate_cache_key(
            json.dumps(pr_content),
            'pr_analysis'
        )
        
        # Check cache
        cached = await self._get_cached_response(cache_key)
        if cached:
            return cached
        
        # Prepare prompt
        prompt = self.templates.pr_analysis().format(pr_content=json.dumps(pr_content))
        
        try:
            # Get response from Groq
            response = await self._make_groq_request(prompt)
            
            # Parse and structure the response
            analysis = {
                'summary': '',
                'impact': '',
                'security': [],
                'quality': '',
                'recommendations': []
            }
            
            # Process the response into structured format
            analysis = json.loads(response)
            
            # Cache the result
            self._cache_response(cache_key, analysis)
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing PR: {str(e)}")
            raise

    async def generate_documentation(self, code: str) -> Dict[str, Any]:
        """Generate documentation for code."""
        cache_key = self._generate_cache_key(code, 'documentation')
        
        # Check cache
        cached = await self._get_cached_response(cache_key)
        if cached:
            return cached
        
        # Prepare prompt
        prompt = self.templates.documentation_generation().format(code=code)
        
        try:
            # Get response from Groq
            response = await self._make_groq_request(prompt)
            
            # Parse and structure the response
            documentation = {
                'description': '',
                'parameters': [],
                'returns': '',
                'examples': [],
                'notes': []
            }
            
            # Process the response into structured format
            documentation = json.loads(response)
            
            # Cache the result
            self._cache_response(cache_key, documentation)
            
            return documentation
            
        except Exception as e:
            logger.error(f"Error generating documentation: {str(e)}")
            raise

    def clear_cache(self):
        """Clear the response cache."""
        self._response_cache.clear()
        logger.info("Cache cleared")

# Example usage
if __name__ == "__main__":
    async def main():
        client = GroqClient(api_key="your-api-key")
        
        code = """
        def factorial(n):
            if n == 0:
                return 1
            return n * factorial(n-1)
        """
        
        try:
            analysis = await client.analyze_code(code)
            print("Code Analysis:", json.dumps(analysis, indent=2))
            
            docs = await client.generate_documentation(code)
            print("Documentation:", json.dumps(docs, indent=2))
            
        except Exception as e:
            print(f"Error: {e}")

    asyncio.run(main())