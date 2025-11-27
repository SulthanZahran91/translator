"""Token counting utilities for translation chunking.

Uses tiktoken with cl100k_base encoding for accurate token counting
compatible with OpenAI-style models.
"""

import tiktoken

from backend.core.config import get_settings


class Tokenizer:
    """Token counter using tiktoken."""
    
    def __init__(self, encoding_name: str = "cl100k_base") -> None:
        """Initialize tokenizer.
        
        Args:
            encoding_name: The tiktoken encoding to use. Default is cl100k_base
                          which is used by GPT-4 and compatible models.
        """
        self._encoding = tiktoken.get_encoding(encoding_name)
        self._settings = get_settings()
    
    def count_tokens(self, text: str) -> int:
        """Count the number of tokens in text.
        
        Args:
            text: The text to count tokens for
            
        Returns:
            Number of tokens
        """
        if not text:
            return 0
        return len(self._encoding.encode(text))
    
    def encode(self, text: str) -> list[int]:
        """Encode text to token IDs.
        
        Args:
            text: The text to encode
            
        Returns:
            List of token IDs
        """
        return self._encoding.encode(text)
    
    def decode(self, tokens: list[int]) -> str:
        """Decode token IDs back to text.
        
        Args:
            tokens: List of token IDs
            
        Returns:
            Decoded text
        """
        return self._encoding.decode(tokens)
    
    def truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        """Truncate text to fit within token limit.
        
        Args:
            text: The text to truncate
            max_tokens: Maximum number of tokens
            
        Returns:
            Truncated text
        """
        tokens = self.encode(text)
        if len(tokens) <= max_tokens:
            return text
        return self.decode(tokens[:max_tokens])
    
    def split_by_tokens(self, text: str, max_tokens: int) -> list[str]:
        """Split text into chunks of roughly max_tokens each.
        
        This is a simple token-based split that doesn't consider
        sentence boundaries. For smarter splitting, use the Chunker class.
        
        Args:
            text: The text to split
            max_tokens: Maximum tokens per chunk
            
        Returns:
            List of text chunks
        """
        tokens = self.encode(text)
        chunks: list[str] = []
        
        for i in range(0, len(tokens), max_tokens):
            chunk_tokens = tokens[i:i + max_tokens]
            chunks.append(self.decode(chunk_tokens))
        
        return chunks
    
    @property
    def max_tokens_per_unit(self) -> int:
        """Get maximum tokens per translation unit from settings."""
        return self._settings.max_tokens_per_unit
    
    @property
    def glossary_token_budget(self) -> int:
        """Get glossary token budget from settings."""
        return self._settings.glossary_token_budget
    
    @property
    def context_tail_tokens(self) -> int:
        """Get context tail tokens from settings."""
        return self._settings.context_tail_tokens


# Singleton instance
_tokenizer: Tokenizer | None = None


def get_tokenizer() -> Tokenizer:
    """Get the tokenizer singleton."""
    global _tokenizer
    if _tokenizer is None:
        _tokenizer = Tokenizer()
    return _tokenizer


def count_tokens(text: str) -> int:
    """Convenience function to count tokens in text."""
    return get_tokenizer().count_tokens(text)

