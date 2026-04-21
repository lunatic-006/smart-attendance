"""
Pipeline configuration and selection.
Choose between standard (MTCNN + FaceNet) or advanced (YOLOv8 + ArcFace) pipelines.
"""

import os
from enum import Enum


class PipelineType(Enum):
    """Available face recognition pipelines."""
    STANDARD = "standard"  # MTCNN + FaceNet (fast, good for CPU)
    ADVANCED = "advanced"  # YOLOv8 + ArcFace (accurate, slower on CPU)


class PipelineConfig:
    """Configuration for face recognition pipeline."""
    
    # Set via environment variable or directly
    PIPELINE = os.getenv("FACE_PIPELINE", "standard").lower()
    
    # YOLOv8 model selection (for advanced pipeline)
    # Options: yolov8n-face (fastest), yolov8s-face, yolov8m-face, yolov8l-face, yolov8x-face
    YOLO_MODEL = os.getenv("YOLO_MODEL", "yolov8n-face")
    
    # Force CPU usage (for low-resource environments)
    FORCE_CPU = os.getenv("FORCE_CPU", "true").lower() == "true"
    
    # Confidence thresholds
    # REDUCED to secure level - face detection validation now enforced
    STANDARD_TOLERANCE = float(os.getenv("STANDARD_TOLERANCE", "0.65"))
    ADVANCED_CONFIDENCE = float(os.getenv("ADVANCED_CONFIDENCE", "0.6"))
    
    # Liveness detection (disabled by default - face detection validation + tolerance 0.65 provides sufficient security)
    # To enable: set ENABLE_LIVENESS=true in environment or modify this default to "true"
    ENABLE_LIVENESS = os.getenv("ENABLE_LIVENESS", "false").lower() == "true"
    LIVENESS_TYPE = os.getenv("LIVENESS_TYPE", "basic")  # "basic" or "advanced"
    
    @staticmethod
    def is_standard() -> bool:
        """Check if using standard pipeline."""
        return PipelineConfig.PIPELINE == "standard"
    
    @staticmethod
    def is_advanced() -> bool:
        """Check if using advanced pipeline."""
        return PipelineConfig.PIPELINE == "advanced"
    
    @staticmethod
    def get_pipeline_info() -> dict:
        """Get current pipeline configuration."""
        return {
            "pipeline": PipelineConfig.PIPELINE,
            "yolo_model": PipelineConfig.YOLO_MODEL,
            "force_cpu": PipelineConfig.FORCE_CPU,
            "standard_tolerance": PipelineConfig.STANDARD_TOLERANCE,
            "advanced_confidence": PipelineConfig.ADVANCED_CONFIDENCE,
            "liveness_enabled": PipelineConfig.ENABLE_LIVENESS,
            "liveness_type": PipelineConfig.LIVENESS_TYPE,
        }


def get_face_engine():
    """
    Factory function to get appropriate face engine based on configuration.
    
    Returns:
        FaceEngine or AdvancedFaceEngine instance
    """
    if PipelineConfig.is_advanced():
        from .face_engine_advanced import AdvancedFaceEngine
        print("Using advanced pipeline: YOLOv8 + ArcFace")
        return AdvancedFaceEngine(
            model_name=PipelineConfig.YOLO_MODEL,
            use_cpu=PipelineConfig.FORCE_CPU,
            confidence_threshold=PipelineConfig.ADVANCED_CONFIDENCE
        )
    else:
        from .face_engine import FaceEngine
        print("Using standard pipeline: MTCNN + FaceNet")
        return FaceEngine(tolerance=PipelineConfig.STANDARD_TOLERANCE)
