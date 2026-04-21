"""
Single-Person Real-Time Face Recognition Engine
Optimized for one person in frame at a time.
Includes student queue management for sequential processing.

Perfect for:
- Classroom attendance booth (one student at a time)
- Queue-based entry systems
- Single-camera deployment
"""

import asyncio
import time
import numpy as np
import json
from collections import deque
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class StudentStatus:
    """Track status of a student in queue."""
    student_id: str
    name: str
    timestamp: float
    status: str  # "waiting", "capturing", "matched", "failed", "timeout"
    confidence: float = 0.0
    attempts: int = 0
    match_time: Optional[float] = None


class SinglePersonRealtimeEngine:
    """
    Real-time face recognition optimized for single-person capture.
    """
    
    def __init__(self, face_engine, db_factory, confidence_threshold: float = 0.5):
        """
        Initialize single-person engine.
        
        Args:
            face_engine: FaceEngine instance
            db_factory: Function to get DB connection
            confidence_threshold: Minimum confidence for match (0.0-1.0)
        """
        self.face_engine = face_engine
        self.db_factory = db_factory
        self.confidence_threshold = confidence_threshold
        
        # Single-person state
        self.current_student_id: Optional[str] = None
        self.current_session_key: Optional[str] = None
        self.is_capturing = False
        
        # Frame buffer for current person
        self.frame_buffer = deque(maxlen=15)  # Keep last 15 frames for analysis
        self.frame_timestamps = deque(maxlen=15)
        
        # Tracking across frames
        self.face_detections = deque(maxlen=30)  # Track detections for confidence
        self.match_history = deque(maxlen=10)    # Track matched predictions
        
        # Performance monitoring
        self.stats = {
            "frames_captured": 0,
            "faces_detected": 0,
            "stable_matches": 0,
            "confidence_scores": deque(maxlen=100),
            "processing_times": deque(maxlen=100),
            "current_confidence": 0.0,
            "capture_duration": 0.0,
            "capture_start_time": None
        }
        
        # Embedding cache
        self.embedding_cache = {}
        self.cache_ttl = 300  # 5 minutes
        self.cache_timestamps = {}
        
        # Student queue for batch processing
        self.queue = deque()
        self.processed_students = {}
    
    def set_current_student(self, student_id: str, session_key: str) -> Dict:
        """Set the target student for current capture session."""
        self.current_student_id = student_id
        self.current_session_key = session_key
        self.is_capturing = False
        
        # Clear buffers
        self.frame_buffer.clear()
        self.frame_timestamps.clear()
        self.face_detections.clear()
        self.match_history.clear()
        
        # Reset stats for new capture
        self.stats["capture_start_time"] = time.time()
        self.stats["capture_duration"] = 0.0
        self.stats["current_confidence"] = 0.0
        self.stats["frames_captured"] = 0
        
        return {
            "status": "ready",
            "student_id": student_id,
            "message": "Ready to capture. Look at camera."
        }
    
    async def add_frame(self, base64_image: str) -> Dict:
        """
        Add single frame from camera.
        """
        if not self.current_student_id:
            return {"status": "error", "message": "No student set"}
        
        timestamp = time.time()
        self.frame_buffer.append(base64_image)
        self.frame_timestamps.append(timestamp)
        self.stats["frames_captured"] += 1
        self.stats["capture_duration"] = timestamp - (self.stats["capture_start_time"] or timestamp)
        
        return {
            "status": "queued",
            "frames_buffered": len(self.frame_buffer),
            "capture_duration_ms": self.stats["capture_duration"] * 1000
        }
    
    async def process_single_face(self) -> Dict:
        """
        Process current buffered frame(s) for single person detection.
        
        Returns comprehensive detection result.
        """
        if len(self.frame_buffer) == 0:
            return {
                "status": "no_frames",
                "message": "No frames in buffer"
            }
        
        start_time = time.time()
        
        try:
            # Process most recent frame
            latest_frame = list(self.frame_buffer)[-1]
            
            # 1. Face Detection
            detected = False
            if hasattr(self.face_engine, 'detect_faces'):
                detections = self.face_engine.detect_faces(latest_frame)
                detected = len(detections) > 0
            else:
                detected = self.face_engine.check_liveness(latest_frame)
            
            if not detected:
                self.stats["faces_detected"] = 0
                return {
                    "status": "face_not_detected",
                    "message": "No face in frame. Please look at camera.",
                    "processing_time_ms": (time.time() - start_time) * 1000,
                    "frames_checked": len(self.frame_buffer)
                }
            
            self.stats["faces_detected"] += 1
            
            # 2. Extract Embedding
            try:
                if hasattr(self.face_engine, 'get_model_info'):
                    result = self.face_engine.get_face_embedding(latest_frame)
                    embedding = result["embedding"]
                else:
                    embedding = self.face_engine.get_face_embedding(latest_frame)
            except Exception as e:
                return {
                    "status": "embedding_error",
                    "message": f"Could not extract face features: {str(e)}",
                    "processing_time_ms": (time.time() - start_time) * 1000
                }
            
            # 3. Get stored embedding for this student
            stored_embedding = self._get_stored_embedding(self.current_student_id)
            if not stored_embedding:
                return {
                    "status": "student_not_registered",
                    "message": f"Student {self.current_student_id} not registered"
                }
            
            # 4. Compare embeddings
            try:
                if hasattr(self.face_engine, 'compare_faces_cosine'):
                    comparison = self.face_engine.compare_faces_cosine(stored_embedding, embedding)
                    is_match = comparison["match"]
                    confidence = comparison["confidence"] / 100.0  # Normalize to 0-1
                else:
                    is_match = self.face_engine.compare_faces(stored_embedding, embedding)
                    confidence = 1.0 if is_match else 0.0
            except Exception as e:
                return {
                    "status": "comparison_error",
                    "message": f"Comparison error: {str(e)}"
                }
            
            # Track this match attempt
            current_timestamp = time.time()
            self.match_history.append({
                "timestamp": current_timestamp,
                "confidence": confidence,
                "is_match": is_match
            })
            
            self.stats["confidence_scores"].append(confidence)
            self.stats["current_confidence"] = confidence
            
            # 5. Evaluate multi-frame consistency
            stable_match = self._evaluate_match_stability()
            
            if stable_match:
                self.stats["stable_matches"] += 1
                processing_time = time.time() - start_time
                self.stats["processing_times"].append(processing_time)
                
                return {
                    "status": "match_confirmed",
                    "student_id": self.current_student_id,
                    "confidence": confidence * 100,  # Back to 0-100
                    "stable": True,
                    "frames_analyzed": len(self.match_history),
                    "processing_time_ms": processing_time * 1000,
                    "message": "Face recognized! Attendance marked."
                }
            else:
                processing_time = time.time() - start_time
                self.stats["processing_times"].append(processing_time)
                
                return {
                    "status": "processing",
                    "confidence": confidence * 100,
                    "stable": False,
                    "frames_needed": max(0, 5 - len(self.match_history)),
                    "processing_time_ms": processing_time * 1000,
                    "message": f"Face detected. Confidence: {confidence*100:.1f}%. Please hold still..."
                }
        
        except Exception as e:
            return {
                "status": "error",
                "message": f"Processing error: {str(e)}",
                "processing_time_ms": (time.time() - start_time) * 1000
            }
    
    def _evaluate_match_stability(self) -> bool:
        """
        Evaluate if match is stable across multiple frames.
        
        Returns True if:
        - At least 3 consecutive positive matches
        - Average confidence > threshold
        """
        if len(self.match_history) < 3:
            return False
        
        recent_matches = list(self.match_history)[-5:]  # Last 5 attempts
        
        # Check if majority are matches
        match_count = sum(1 for m in recent_matches if m["is_match"])
        if match_count < 3:
            return False
        
        # Check average confidence
        avg_confidence = np.mean([m["confidence"] for m in recent_matches])
        
        return avg_confidence >= self.confidence_threshold
    
    def _get_stored_embedding(self, student_id: str) -> Optional[List[float]]:
        """Get stored embedding from cache or DB."""
        current_time = time.time()
        
        # Check cache
        if student_id in self.embedding_cache:
            if current_time - self.cache_timestamps[student_id] < self.cache_ttl:
                return self.embedding_cache[student_id]
            else:
                del self.embedding_cache[student_id]
                del self.cache_timestamps[student_id]
        
        # Fetch from DB
        try:
            db = self.db_factory()
            cursor = db.cursor()
            cursor.execute("SELECT face_encoding FROM students WHERE id=?", (student_id,))
            row = cursor.fetchone()
            db.close()
            
            if row and row["face_encoding"]:
                embedding = json.loads(row["face_encoding"])
                self.embedding_cache[student_id] = embedding
                self.cache_timestamps[student_id] = current_time
                return embedding
        except Exception as e:
            print(f"Error fetching embedding: {str(e)}")
        
        return None
    
    def add_to_queue(self, students: List[Dict]) -> Dict:
        """
        Add students to processing queue.
        
        Args:
            students: List of {"student_id": "...", "name": "..."}
        
        Returns:
            Queue status
        """
        for student in students:
            status = StudentStatus(
                student_id=student["student_id"],
                name=student.get("name", "Unknown"),
                timestamp=time.time(),
                status="waiting"
            )
            self.queue.append(status)
        
        return {
            "status": "queue_updated",
            "queue_length": len(self.queue),
            "next_student": self._peek_next_student() if self.queue else None
        }
    
    def _peek_next_student(self) -> Optional[Dict]:
        """Peek at next student in queue without removing."""
        if self.queue:
            s = self.queue[0]
            return {
                "student_id": s.student_id,
                "name": s.name
            }
        return None
    
    def get_next_student(self) -> Optional[Dict]:
        """Pop next student from queue and set as current."""
        if self.queue:
            student_status = self.queue.popleft()
            student_status.status = "capturing"
            student_status.timestamp = time.time()
            
            self.set_current_student(
                student_status.student_id,
                f"queue_{student_status.student_id}"
            )
            
            return {
                "student_id": student_status.student_id,
                "name": student_status.name,
                "queue_remaining": len(self.queue)
            }
        return None
    
    def finish_queue(self) -> Dict:
        """Get summary of processed students."""
        return {
            "total_processed": len(self.processed_students),
            "successful": sum(1 for s in self.processed_students.values() if s["status"] == "matched"),
            "failed": sum(1 for s in self.processed_students.values() if s["status"] == "failed"),
            "processed_students": list(self.processed_students.values())
        }
    
    def get_stats(self) -> Dict:
        """Get comprehensive statistics."""
        avg_confidence = np.mean(list(self.stats["confidence_scores"])) if self.stats["confidence_scores"] else 0.0
        avg_processing = np.mean(list(self.stats["processing_times"])) if self.stats["processing_times"] else 0.0
        
        return {
            "frames_captured": self.stats["frames_captured"],
            "faces_detected": self.stats["faces_detected"],
            "stable_matches": self.stats["stable_matches"],
            "current_confidence": self.stats["current_confidence"] * 100,
            "avg_confidence": avg_confidence * 100,
            "avg_processing_time_ms": avg_processing * 1000,
            "capture_duration_ms": self.stats["capture_duration"] * 1000,
            "buffer_size": len(self.frame_buffer),
            "queue_length": len(self.queue)
        }
    
    def clear_cache(self):
        """Clear embedding cache."""
        self.embedding_cache.clear()
        self.cache_timestamps.clear()
