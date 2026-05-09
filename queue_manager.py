"""
Queue Manager Module
Manages pending questions waiting for AI processing.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import json


@dataclass
class PendingQuestion:
    """Represents a question pending AI response"""
    question_number: int
    question_text: str
    question_type: str
    options: List[Dict[str, str]]
    quiz_link: str
    timestamp: str
    attempt_count: int = 0
    max_retries: int = 3
    ai_response: Optional[str] = None
    
    def to_dict(self):
        return asdict(self)


class QueueManager:
    """Manage pending questions queue"""
    
    def __init__(self, max_queue_size: int = 1000):
        self.queue: List[PendingQuestion] = []
        self.processed: List[PendingQuestion] = []
        self.failed: List[PendingQuestion] = []
        self.max_queue_size = max_queue_size
        
    def add_question(self, question_number: int, question_text: str, 
                     question_type: str, options: List[Dict[str, str]], 
                     quiz_link: str) -> bool:
        """Add question to pending queue"""
        if len(self.queue) >= self.max_queue_size:
            print(f"Queue full: {len(self.queue)} questions")
            return False
        
        pq = PendingQuestion(
            question_number=question_number,
            question_text=question_text,
            question_type=question_type,
            options=options,
            quiz_link=quiz_link,
            timestamp=datetime.now().isoformat()
        )
        
        self.queue.append(pq)
        return True
    
    def get_next_question(self) -> Optional[PendingQuestion]:
        """Get next question from queue"""
        if self.queue:
            return self.queue[0]
        return None
    
    def mark_processed(self, question_number: int, ai_response: str) -> bool:
        """Move question to processed after AI response"""
        for i, pq in enumerate(self.queue):
            if pq.question_number == question_number:
                pq.ai_response = ai_response
                self.processed.append(self.queue.pop(i))
                return True
        return False
    
    def mark_failed(self, question_number: int) -> bool:
        """Move question to failed after max retries"""
        for i, pq in enumerate(self.queue):
            if pq.question_number == question_number:
                self.failed.append(self.queue.pop(i))
                return True
        return False
    
    def retry_question(self, question_number: int) -> bool:
        """Retry a failed question"""
        for pq in self.queue:
            if pq.question_number == question_number:
                pq.attempt_count += 1
                return pq.attempt_count < pq.max_retries
        return False
    
    def get_queue_size(self) -> int:
        return len(self.queue)
    
    def get_processed_count(self) -> int:
        return len(self.processed)
    
    def get_failed_count(self) -> int:
        return len(self.failed)
    
    def export_queue(self, filepath: str) -> bool:
        """Export queue state to JSON"""
        try:
            state = {
                'pending': [pq.to_dict() for pq in self.queue],
                'processed': [pq.to_dict() for pq in self.processed],
                'failed': [pq.to_dict() for pq in self.failed],
                'timestamp': datetime.now().isoformat()
            }
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error exporting queue: {e}")
            return False
    
    def clear(self):
        """Clear all queues"""
        self.queue.clear()
        self.processed.clear()
        self.failed.clear()