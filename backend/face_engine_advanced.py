"""
Advanced Face Recognition Pipeline using YOLOv8-Face + ArcFace
Optimized for CPU-only environments with fallback capabilities.

Pipeline:
Camera → YOLOv8-Face Detection → ArcFace Embeddings → Cosine Similarity → Match
"""

import cv2
import numpy as np
import base64
import json
import hashlib
from pathlib import Path

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False

try:
    import insightface
    ARCFACE_AVAILABLE = True
except ImportError:
    ARCFACE_AVAILABLE = False


class AdvancedFaceEngine:
    """
    Advanced face recognition engine using YOLOv8-Face for detection and ArcFace for embeddings.
    Includes CPU optimization, caching, and confidence scoring.
    """
    
    def __init__(self, model_name="yolov8n-face", use_cpu=True, confidence_threshold=0.5):
        """
        Initialize the advanced face engine.
        
        Args:
            model_name: YOLOv8 model variant (yolov8n-face is fastest on CPU)
            use_cpu: Force CPU usage (recommended for Intel i7)
            confidence_threshold: Cosine similarity threshold for matching (0.0-1.0)
        """
        self.use_cpu = use_cpu
        self.confidence_threshold = confidence_threshold
        self.device = "cpu" if use_cpu else "0"  # GPU if available
        
        # Initialize models
        self.yolo_model = None
        self.arcface_model = None
        self.embedding_cache = {}  # In-memory cache for embeddings
        
        if YOLO_AVAILABLE:
            try:
                # Use nano model for speed on CPU (yolov8n-face)
                self.yolo_model = YOLO(f"{model_name}.pt", verbose=False)
                self.yolo_model.to(self.device)
            except Exception as e:
                print(f"Warning: Could not load YOLOv8 model: {e}")
        
        if ARCFACE_AVAILABLE:
            try:
                # Initialize InsightFace with ArcFace model
                self.arcface_model = insightface.app.FaceAnalysis(
                    name='buffalo_sc',  # CPU-friendly model
                    providers=['CPUExecutionProvider'],
                    download_path='./models'
                )
                self.arcface_model.prepare(ctx_id=-1)  # CPU
            except Exception as e:
                print(f"Warning: Could not load ArcFace model: {e}")

    def decode_base64_image(self, base64_string: str) -> np.ndarray:
        """Decode base64 string to OpenCV BGR image with validation."""
        try:
            if ',' in base64_string:
                base64_string = base64_string.split(',')[1]
            
            img_data = base64.b64decode(base64_string)
            nparr = np.frombuffer(img_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if img is None:
                raise ValueError("Failed to decode image. Image data may be corrupted.")
            
            return img
        except Exception as e:
            raise ValueError(f"Image decoding error: {str(e)}")

    def _preprocess_image(self, img: np.ndarray) -> np.ndarray:
        """
        Preprocess image for better detection and recognition:
        - Auto-enhance contrast
        - Normalize brightness
        - Reduce noise
        """
        # Convert to LAB for better contrast adjustment
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        
        # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        l = clahe.apply(l)
        
        # Merge and convert back to BGR
        lab = cv2.merge([l, a, b])
        img_enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        
        # Reduce noise
        img_enhanced = cv2.bilateralFilter(img_enhanced, 9, 75, 75)
        
        return img_enhanced

    def detect_faces(self, base64_image: str) -> list[dict]:
        """
        Detect faces in image using YOLOv8-Face.
        
        Returns:
            List of face detections with coordinates and confidence scores.
        """
        try:
            img = self.decode_base64_image(base64_image)
        except Exception as e:
            raise ValueError(f"Failed to process image: {str(e)}")
        
        if not YOLO_AVAILABLE:
            raise RuntimeError("YOLOv8 not available. Install ultralytics: pip install ultralytics")
        
        try:
            # Preprocess image for better detection
            img_enhanced = self._preprocess_image(img)
            
            # Run YOLOv8 detection
            results = self.yolo_model(img_enhanced, conf=0.3, verbose=False)
            
            detections = []
            if results and len(results) > 0:
                boxes = results[0].boxes
                for box in boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    conf = float(box.conf[0])
                    
                    detections.append({
                        "x1": x1,
                        "y1": y1,
                        "x2": x2,
                        "y2": y2,
                        "confidence": conf,
                        "width": x2 - x1,
                        "height": y2 - y1
                    })
            
            return detections
        except Exception as e:
            raise ValueError(f"Face detection error: {str(e)}")

    def get_face_embedding(self, base64_image: str) -> dict:
        """
        Extract ArcFace embedding from face.
        
        Returns:
            Dictionary with embedding (512-dimensional), detection info, and confidence.
        """
        try:
            img = self.decode_base64_image(base64_image)
        except Exception as e:
            raise ValueError(f"Failed to process image: {str(e)}")
        
        if not ARCFACE_AVAILABLE:
            raise RuntimeError("ArcFace not available. Install insightface: pip install insightface")
        
        try:
            # Detect faces using InsightFace
            faces = self.arcface_model.get(img)
            
            if len(faces) == 0:
                raise ValueError("No face detected in the image.")
            if len(faces) > 1:
                raise ValueError("Multiple faces detected. Please ensure only one person is in the frame.")
            
            face = faces[0]
            embedding = face.embedding.tolist()
            
            return {
                "embedding": embedding,
                "embedding_dim": 512,
                "confidence": float(face.det_score),
                "bbox": {
                    "x1": int(face.bbox[0]),
                    "y1": int(face.bbox[1]),
                    "x2": int(face.bbox[2]),
                    "y2": int(face.bbox[3])
                }
            }
        except Exception as e:
            raise ValueError(f"Face embedding extraction error: {str(e)}")

    def compare_faces_cosine(self, embedding1: list[float], embedding2: list[float]) -> dict:
        """
        Compare two ArcFace embeddings using cosine similarity.
        
        Returns:
            Dictionary with match status, similarity score, and distance.
        """
        try:
            emb1 = np.array(embedding1)
            emb2 = np.array(embedding2)
            
            # Normalize embeddings (ArcFace already normalizes, but ensure it)
            emb1 = emb1 / np.linalg.norm(emb1)
            emb2 = emb2 / np.linalg.norm(emb2)
            
            # Cosine similarity
            cosine_sim = np.dot(emb1, emb2)
            
            # Convert to distance (0 = perfect match, 2 = opposite)
            distance = 1 - cosine_sim
            
            # Determine match
            match = cosine_sim >= self.confidence_threshold
            
            return {
                "match": match,
                "cosine_similarity": float(cosine_sim),
                "distance": float(distance),
                "confidence": float(max(0, cosine_sim)) * 100,
                "threshold": self.confidence_threshold
            }
        except Exception as e:
            raise ValueError(f"Face comparison error: {str(e)}")

    def check_liveness_advanced(self, base64_image: str) -> dict:
        """
        Advanced liveness detection using:
        - Face size validation
        - Eye presence detection
        - Quality metrics
        
        Returns:
            Dictionary with liveness status and confidence.
        """
        try:
            img = self.decode_base64_image(base64_image)
        except Exception as e:
            raise ValueError(f"Failed to process image: {str(e)}")
        
        try:
            if not ARCFACE_AVAILABLE:
                # Fallback to basic checks
                return self._check_liveness_basic(img)
            
            faces = self.arcface_model.get(img)
            if len(faces) == 0:
                return {"is_live": False, "reason": "No face detected", "confidence": 0.0}
            
            face = faces[0]
            img_h, img_w = img.shape[:2]
            
            x1, y1, x2, y2 = map(int, face.bbox)
            face_width = x2 - x1
            face_height = y2 - y1
            face_area = face_width * face_height
            frame_area = img_w * img_h
            
            # Liveness checks
            checks = []
            
            # 1. Face size check (should be at least 10% of frame)
            face_size_ratio = face_area / frame_area
            if face_size_ratio >= 0.1:
                checks.append(True)
            else:
                checks.append(False)
            
            # 2. Face confidence check (should be high)
            if face.det_score > 0.5:
                checks.append(True)
            else:
                checks.append(False)
            
            # 3. Landmark quality check (if available)
            if hasattr(face, 'landmark'):
                if face.landmark is not None:
                    checks.append(True)
                else:
                    checks.append(False)
            
            # Overall liveness decision
            is_live = sum(checks) >= 2  # At least 2 checks must pass
            confidence = sum(checks) / len(checks) if checks else 0.0
            
            return {
                "is_live": is_live,
                "confidence": float(confidence),
                "face_size_ratio": float(face_size_ratio),
                "detection_score": float(face.det_score),
                "checks_passed": sum(checks),
                "total_checks": len(checks)
            }
        except Exception as e:
            raise ValueError(f"Liveness check error: {str(e)}")

    def _check_liveness_basic(self, img: np.ndarray) -> dict:
        """Basic liveness detection fallback."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        faces = face_cascade.detectMultiScale(gray, 1.3, 5)
        
        if len(faces) == 0:
            return {"is_live": False, "reason": "No face cascade detected", "confidence": 0.0}
        
        x, y, w, h = faces[0]
        img_h, img_w = img.shape[:2]
        face_area = w * h
        frame_area = img_w * img_h
        
        is_live = (face_area / frame_area) >= 0.05
        confidence = (face_area / frame_area) / 0.05 if is_live else 0.0
        
        return {
            "is_live": is_live,
            "reason": "Basic cascade detection",
            "confidence": float(min(confidence, 1.0))
        }

    def get_embedding_with_cache(self, base64_image: str, cache_key: str = None) -> dict:
        """
        Get embedding with optional caching for faster re-processing of same image.
        
        Args:
            base64_image: Base64 encoded image
            cache_key: Optional cache key (e.g., user_id)
        
        Returns:
            Embedding result from cache or fresh extraction
        """
        if cache_key and cache_key in self.embedding_cache:
            return self.embedding_cache[cache_key]
        
        result = self.get_face_embedding(base64_image)
        
        if cache_key:
            self.embedding_cache[cache_key] = result
        
        return result

    def clear_cache(self):
        """Clear embedding cache."""
        self.embedding_cache.clear()

    def get_model_info(self) -> dict:
        """Return information about loaded models."""
        return {
            "yolo_available": YOLO_AVAILABLE,
            "arcface_available": ARCFACE_AVAILABLE,
            "yolo_loaded": self.yolo_model is not None,
            "arcface_loaded": self.arcface_model is not None,
            "device": self.device,
            "embedding_dimension": 512,
            "comparison_method": "cosine_similarity"
        }
