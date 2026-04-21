"""
Real-time face recognition module for continuous stream processing.
Optimized for low-latency, high-throughput face recognition.

Features:
- Frame buffering and async processing
- Confidence thresholding
- Face tracking across frames
- Performance monitoring
"""

import asyncio
import time
import numpy as np
import json
from collections import deque
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class FaceDetection:
    """Single face detection result."""
    face_id: str
    embedding: List[float]
    confidence: float
    bbox: Dict
    timestamp: float
    matched_user_id: Optional[str] = None
    match_confidence: float = 0.0


class FrameBuffer:
    """Efficiently buffer video frames for async processing."""
    
    def __init__(self, max_size: int = 30):
        self.buffer = deque(maxlen=max_size)
        self.timestamps = deque(maxlen=max_size)
        self.processing_lock = asyncio.Lock()
    
    async def add_frame(self, frame_data: str, timestamp: float):
        """Add frame to buffer."""
        self.buffer.append(frame_data)
        self.timestamps.append(timestamp)
    
    async def get_frame(self) -> Tuple[Optional[str], Optional[float]]:
        """Get oldest frame from buffer."""
        async with self.processing_lock:
            if len(self.buffer) > 0:
                frame = self.buffer.popleft()
                ts = self.timestamps.popleft()
                return frame, ts
        return None, None
    
    def size(self) -> int:
        return len(self.buffer)
    
    def clear(self):
        self.buffer.clear()
        self.timestamps.clear()


class FaceTracker:
    """Track faces across consecutive frames for continuity."""
    
    def __init__(self, max_history: int = 5, confidence_threshold: float = 0.5):
        self.face_history: Dict[str, deque] = {}
        self.max_history = max_history
        self.confidence_threshold = confidence_threshold
    
    def update(self, face_id: str, detection: FaceDetection):
        """Update face tracking history."""
        if face_id not in self.face_history:
            self.face_history[face_id] = deque(maxlen=self.max_history)
        
        self.face_history[face_id].append(detection)
    
    def get_stable_match(self, face_id: str) -> Optional[Tuple[str, float]]:
        """
        Get stable match only if face has been consistently matched for several frames.
        Returns (matched_user_id, avg_confidence) or None if not stable.
        """
        if face_id not in self.face_history or len(self.face_history[face_id]) < 2:
            return None
        
        history = list(self.face_history[face_id])
        
        # Check if all recent detections match the same user
        matched_users = [d.matched_user_id for d in history if d.matched_user_id]
        confidences = [d.match_confidence for d in history if d.matched_user_id]
        
        if not matched_users:
            return None
        
        # All matches should be for the same user
        if len(set(matched_users)) != 1:
            return None
        
        # Average confidence should be above threshold
        avg_confidence = np.mean(confidences) if confidences else 0.0
        
        if avg_confidence >= self.confidence_threshold:
            return matched_users[0], avg_confidence
        
        return None
    
    def cleanup_old(self, max_age_seconds: float = 30):
        """Remove old face tracking entries."""
        current_time = time.time()
        to_remove = []
        
        for face_id, history in self.face_history.items():
            if len(history) > 0:
                last_detection = history[-1]
                if current_time - last_detection.timestamp > max_age_seconds:
                    to_remove.append(face_id)
        
        for face_id in to_remove:
            del self.face_history[face_id]


class RealtimeRecognitionEngine:
    """
    Main engine for real-time face recognition with optimizations.
    """
    
    def __init__(self, face_engine, db, frame_skip: int = 1, confidence_threshold: float = 0.5):
        """
        Initialize real-time engine.
        
        Args:
            face_engine: FaceEngine instance (standard or advanced)
            db: Database connection factory
            frame_skip: Process every Nth frame (default 1 = all frames)
            confidence_threshold: Minimum confidence for stable matches
        """
        self.face_engine = face_engine
        self.db = db
        self.frame_skip = frame_skip
        self.frame_counter = 0
        
        # Buffers and queues
        self.frame_buffer = FrameBuffer(max_size=30)
        self.face_tracker = FaceTracker(confidence_threshold=confidence_threshold)
        
        # Performance monitoring
        self.performance_stats = {
            "frames_processed": 0,
            "frames_skipped": 0,
            "avg_processing_time": 0.0,
            "processing_times": deque(maxlen=100),
            "faces_detected": 0,
            "matches_found": 0,
            "false_positives": 0
        }
        
        # Embedding cache (user_id -> embedding)
        self.embedding_cache = {}
        self.cache_ttl = 300  # 5 minutes
        self.cache_timestamps = {}
    
    def skip_frame(self) -> bool:
        """Check if current frame should be skipped."""
        self.frame_counter += 1
        if self.frame_counter % self.frame_skip == 0:
            return False
        self.performance_stats["frames_skipped"] += 1
        return True
    
    async def add_frame(self, base64_image: str) -> Dict:
        """
        Add frame to processing queue.
        Returns status immediately without waiting.
        """
        timestamp = time.time()
        
        # Add to buffer for async processing
        await self.frame_buffer.add_frame(base64_image, timestamp)
        
        return {
            "status": "queued",
            "buffer_size": self.frame_buffer.size(),
            "timestamp": timestamp
        }
    
    async def process_frame(self) -> Optional[Dict]:
        """
        Process single frame from buffer asynchronously.
        Returns detection result or None if buffer empty.
        """
        frame_data, timestamp = await self.frame_buffer.get_frame()
        
        if frame_data is None:
            return None
        
        start_time = time.time()
        
        try:
            # Detect faces in frame
            if hasattr(self.face_engine, 'detect_faces'):
                # Advanced pipeline
                detections = self.face_engine.detect_faces(frame_data)
            else:
                # Standard pipeline fallback
                detections = [{"confidence": 1.0}]  # Simplified for standard
            
            if not detections:
                return {
                    "status": "no_faces",
                    "timestamp": timestamp,
                    "processing_time": time.time() - start_time
                }
            
            results = []
            for i, detection in enumerate(detections):
                face_id = f"face_{i}_{int(timestamp * 1000)}"
                
                try:
                    # Extract embedding
                    if hasattr(self.face_engine, 'get_face_embedding'):
                        if hasattr(self.face_engine, 'get_model_info'):
                            # Advanced pipeline
                            result = self.face_engine.get_face_embedding(frame_data)
                            embedding = result["embedding"]
                            confidence = result["confidence"]
                        else:
                            # Standard pipeline
                            embedding = self.face_engine.get_face_embedding(frame_data)
                            confidence = 0.9
                    else:
                        continue
                    
                    face_det = FaceDetection(
                        face_id=face_id,
                        embedding=embedding,
                        confidence=confidence,
                        bbox=detection.get("bbox", {}),
                        timestamp=timestamp
                    )
                    
                    # Update tracker
                    self.face_tracker.update(face_id, face_det)
                    
                    results.append({
                        "face_id": face_id,
                        "confidence": confidence,
                        "bbox": detection.get("bbox", {}),
                        "timestamp": timestamp
                    })
                    
                    self.performance_stats["faces_detected"] += 1
                
                except Exception as e:
                    print(f"Error processing face {i}: {str(e)}")
            
            # Update performance stats
            processing_time = time.time() - start_time
            self.performance_stats["processing_times"].append(processing_time)
            self.performance_stats["avg_processing_time"] = np.mean(
                list(self.performance_stats["processing_times"])
            )
            self.performance_stats["frames_processed"] += 1
            
            return {
                "status": "success",
                "detections": results,
                "detection_count": len(results),
                "processing_time": processing_time,
                "timestamp": timestamp
            }
        
        except Exception as e:
            print(f"Error in process_frame: {str(e)}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": timestamp
            }
    
    def match_face_to_user(self, embedding: List[float], student_id: str) -> Optional[Dict]:
        """
        Match extracted embedding to student enrollment.
        """
        try:
            # Get stored embedding from cache or DB
            stored_embedding = self._get_stored_embedding(student_id)
            if stored_embedding is None:
                return None
            
            # Compare embeddings
            if hasattr(self.face_engine, 'compare_faces_cosine'):
                # Advanced pipeline
                result = self.face_engine.compare_faces_cosine(stored_embedding, embedding)
                return {
                    "match": result["match"],
                    "similarity": result["cosine_similarity"],
                    "confidence": result["confidence"],
                    "distance": result["distance"]
                }
            else:
                # Standard pipeline
                match = self.face_engine.compare_faces(stored_embedding, embedding)
                return {
                    "match": match,
                    "confidence": 100.0 if match else 0.0
                }
        
        except Exception as e:
            print(f"Error in match_face_to_user: {str(e)}")
            return None
    
    def _get_stored_embedding(self, student_id: str) -> Optional[List[float]]:
        """Get stored embedding from cache with TTL."""
        current_time = time.time()
        
        # Check cache validity
        if student_id in self.embedding_cache:
            if current_time - self.cache_timestamps[student_id] < self.cache_ttl:
                return self.embedding_cache[student_id]
            else:
                # Expired, remove from cache
                del self.embedding_cache[student_id]
                del self.cache_timestamps[student_id]
        
        # Fetch from DB
        try:
            db = self.db()
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
            print(f"Error fetching embedding from DB: {str(e)}")
        
        return None
    
    def get_performance_stats(self) -> Dict:
        """Get performance monitoring statistics."""
        return {
            "frames_processed": self.performance_stats["frames_processed"],
            "frames_skipped": self.performance_stats["frames_skipped"],
            "avg_processing_time_ms": self.performance_stats["avg_processing_time"] * 1000,
            "faces_detected": self.performance_stats["faces_detected"],
            "matches_found": self.performance_stats["matches_found"],
            "tracking_entries": len(self.face_tracker.face_history)
        }
    
    def clear_cache(self):
        """Clear embedding cache."""
        self.embedding_cache.clear()
        self.cache_timestamps.clear()
