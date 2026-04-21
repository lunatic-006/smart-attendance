import cv2
import numpy as np
import base64

try:
    import face_recognition
    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False


class FaceEngine:
    def __init__(self, tolerance=0.5):
        self.tolerance = tolerance  # lower is stricter. default face_recognition is 0.6
        # Load cascade classifier once, not on every call
        self._face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

    def decode_base64_image(self, base64_string: str) -> np.ndarray:
        """Decodes base64 string to OpenCV BGR image."""
        try:
            if ',' in base64_string:
                base64_string = base64_string.split(',')[1]

            img_data = base64.b64decode(base64_string)
            nparr = np.frombuffer(img_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img is None:
                raise ValueError("Failed to decode image. The image data may be corrupted or in an unsupported format.")

            return img
        except Exception as e:
            raise ValueError(f"Image decoding error: {str(e)}")

    def _validate_face_opencv(self, img: np.ndarray) -> tuple:
        """
        Validate a single face is present using OpenCV Haar cascade.
        Returns the face bounding box (x, y, w, h).
        """
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = self._face_cascade.detectMultiScale(gray, 1.3, 5)

        if len(faces) == 0:
            raise ValueError("No face detected in the image. Cannot proceed without a face.")
        if len(faces) > 1:
            raise ValueError(f"Multiple faces detected ({len(faces)}). Please ensure only one person is in the frame.")

        (x, y, w, h) = faces[0]
        img_h, img_w = img.shape[:2]
        face_ratio = (w * h) / (img_w * img_h)

        if face_ratio < 0.05:
            raise ValueError(f"Face too small in frame ({face_ratio*100:.1f}% of frame). Move closer to camera.")

        return faces[0]

    def get_face_embedding(self, base64_image: str) -> list[float]:
        """
        Detects face and returns the 128-dimensional embedding.
        Throws ValueError if no face or >1 face is found.
        Decodes the image ONCE and performs face detection ONCE.
        """
        img = self.decode_base64_image(base64_image)

        if FACE_RECOGNITION_AVAILABLE:
            # Use face_recognition library (more accurate than Haar cascade)
            rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            try:
                face_locations = face_recognition.face_locations(rgb_img)
            except Exception as e:
                raise ValueError(f"Face detection error: {str(e)}")

            if len(face_locations) == 0:
                raise ValueError("No face detected in the image.")
            if len(face_locations) > 1:
                raise ValueError("Multiple faces detected. Please ensure only one person is in the frame.")

            # Validate face size
            top, right, bottom, left = face_locations[0]
            face_w = right - left
            face_h = bottom - top
            img_h, img_w = img.shape[:2]
            face_ratio = (face_w * face_h) / (img_w * img_h)

            if face_ratio < 0.05:
                raise ValueError(f"Face too small in frame ({face_ratio*100:.1f}% of frame). Move closer to camera.")

            try:
                encodings = face_recognition.face_encodings(rgb_img, face_locations)
                if not encodings:
                    raise ValueError("Could not extract face encoding.")
                return encodings[0].tolist()
            except ValueError:
                raise
            except Exception as e:
                raise ValueError(f"Face encoding error: {str(e)}")
        else:
            # Fallback: OpenCV Haar cascade + histogram embedding
            self._validate_face_opencv(img)

            try:
                # Resize to standard size for consistent embeddings
                img_resized = cv2.resize(img, (128, 128))
                gray_resized = cv2.cvtColor(img_resized, cv2.COLOR_BGR2GRAY)
                edges = cv2.Canny(gray_resized, 100, 200)

                # Create 128D embedding from edge histogram
                hist = cv2.calcHist([edges], [0], None, [128], [0, 256])
                hist = cv2.normalize(hist, hist).flatten()

                return list(hist)[:128]
            except Exception as e:
                # Final fallback: hash-based embedding
                import hashlib
                img_data = cv2.resize(img, (16, 16))
                pixels = img_data.flatten().tobytes()

                hash_obj = hashlib.sha256(pixels)
                hash_bytes = hash_obj.digest()  # 32 bytes

                embedding = [float(hash_bytes[i % 32]) / 255.0 for i in range(128)]
                return embedding

    def check_liveness(self, base64_image: str) -> bool:
        """
        Basic liveness detection heuristic: ensures face size is reasonable
        and not a small cropped printout relative to the frame.
        """
        img = self.decode_base64_image(base64_image)

        try:
            self._validate_face_opencv(img)
            return True
        except ValueError:
            return False

    def compare_faces(self, known_encoding: list[float], unknown_encoding: list[float]) -> bool:
        """Compare two face encodings to see if they match."""
        known_np = np.array(known_encoding)
        unknown_np = np.array(unknown_encoding)

        if FACE_RECOGNITION_AVAILABLE:
            results = face_recognition.compare_faces([known_np], unknown_np, tolerance=self.tolerance)
            return results[0]
        else:
            # Fallback: Euclidean distance comparison
            distance = np.linalg.norm(known_np - unknown_np)
            return distance < 0.6
