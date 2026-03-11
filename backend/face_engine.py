import face_recognition
import cv2
import numpy as np
import base64

class FaceEngine:
    def __init__(self, tolerance=0.5):
        self.tolerance = tolerance # lower is stricter. default face_recognition is 0.6

    def decode_base64_image(self, base64_string: str) -> np.ndarray:
        """Decodes base64 string to OpenCV BGR image"""
        if ',' in base64_string:
            base64_string = base64_string.split(',')[1]
        
        img_data = base64.b64decode(base64_string)
        nparr = np.frombuffer(img_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return img

    def get_face_embedding(self, base64_image: str) -> list[float]:
        """
        Detects face and returns the 128-dimensional embedding.
        Throws ValueError if no face or >1 face is found.
        """
        img = self.decode_base64_image(base64_image)
        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        
        face_locations = face_recognition.face_locations(rgb_img)
        
        if len(face_locations) == 0:
            raise ValueError("No face detected in the image.")
        if len(face_locations) > 1:
            raise ValueError("Multiple faces detected. Please ensure only one person is in the frame.")
            
        encodings = face_recognition.face_encodings(rgb_img, face_locations)
        return encodings[0].tolist()

    def check_liveness(self, base64_image: str) -> bool:
        """
        Basic liveness detection. In a full production system, this would track multiple frames 
        (e.g., Eye Aspect Ratio for blink detection) or use a deep learning anti-spoofing model.
        For this MVP, we perform a placeholder heuristic: ensures face size is reasonable 
        and not a small cropped printout relative to the frame.
        """
        img = self.decode_base64_image(base64_image)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        faces = face_cascade.detectMultiScale(gray, 1.3, 5)
        
        if len(faces) == 0:
            return False
            
        (x, y, w, h) = faces[0]
        img_h, img_w = img.shape[:2]
        
        # Heuristic: face should occupy at least 5% of the frame area to prevent small photo spoofing from a distance
        face_area = w * h
        frame_area = img_w * img_h
        
        if face_area / frame_area < 0.05:
            return False
            
        return True

    def compare_faces(self, known_encoding: list[float], unknown_encoding: list[float]) -> bool:
        """Compare two face encodings to see if they match."""
        known_np = np.array(known_encoding)
        unknown_np = np.array(unknown_encoding)
        
        # returns array of booleans, we just take the single element
        results = face_recognition.compare_faces([known_np], unknown_np, tolerance=self.tolerance)
        return results[0]
