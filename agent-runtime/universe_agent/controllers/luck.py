import random
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

class LuckController:
    """
    Implements MacroLuckPolicy (story/opportunity layer).
    macroLuckRate ∈ [0.01, 0.10]
    """
    def __init__(self, luck_rate: float = 0.05, seed: Optional[int] = None):
        if seed is not None:
            random.seed(seed)
        self.luck_rate = max(0.01, min(0.10, luck_rate))


    def apply_luck(self, event_name: str) -> bool:
        """
        Determines if luck is applied to an event.
        Returns True if luck is triggered.
        """
        is_lucky = random.random() < self.luck_rate
        if is_lucky:
            logger.info(f"[LUCK] Macro luck triggered for event: {event_name}")
        return is_lucky

    def bias_selection(self, options: list, event_name: str) -> Any:
        """
        Biases selection of options if luck is triggered.
        """
        if not options:
            return None
            
        if self.apply_luck(event_name):
            # Pick best/most positive outcome if lucky
            # For MVP, we just shuffle bias
            return options[-1] # Usually positive outcomes are added last
            
        return random.choice(options)
