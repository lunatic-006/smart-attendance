/**
 * Browser-based Face Recognition — Smart Attendance System
 * Uses face-api.js (TensorFlow.js) for client-side face detection and recognition.
 * Replaces the Python backend face_engine.py / face_engine_advanced.py
 */

const FACE_API_MODEL_URL = 'https://cdn.jsdelivr.net/npm/@vladmandic/face-api/model/';
const FACE_MATCH_THRESHOLD = 0.55; // Lower = stricter (Euclidean distance)

let faceModelsLoaded = false;

// ==================== Model Loading ====================
async function loadFaceModels() {
    if (faceModelsLoaded) return;

    console.log('🔄 Loading face recognition models...');
    try {
        await Promise.all([
            faceapi.nets.tinyFaceDetector.loadFromUri(FACE_API_MODEL_URL),
            faceapi.nets.faceLandmark68TinyNet.loadFromUri(FACE_API_MODEL_URL),
            faceapi.nets.faceRecognitionNet.loadFromUri(FACE_API_MODEL_URL),
        ]);
        faceModelsLoaded = true;
        console.log('✅ Face recognition models loaded successfully');
    } catch (err) {
        console.error('❌ Failed to load face models:', err);
        throw new Error('Failed to load face recognition models. Check your internet connection.');
    }
}

// ==================== Image Helpers ====================
/**
 * Create an HTMLImageElement from a base64 data URL.
 */
function loadImageFromDataUrl(dataUrl) {
    return new Promise((resolve, reject) => {
        const img = new Image();
        img.crossOrigin = 'anonymous';
        img.onload = () => resolve(img);
        img.onerror = () => reject(new Error('Failed to load image from data URL'));
        img.src = dataUrl;
    });
}

// ==================== Face Descriptor Extraction ====================
/**
 * Extract a 128-dimensional face descriptor from a base64 image.
 * @param {string} base64DataUrl - The base64-encoded image (data:image/jpeg;base64,...)
 * @returns {Promise<number[]>} - 128-dim face descriptor as a regular array
 * @throws {Error} if no face detected
 */
async function getFaceDescriptorFromBase64(base64DataUrl) {
    if (!faceModelsLoaded) await loadFaceModels();

    const img = await loadImageFromDataUrl(base64DataUrl);

    const detection = await faceapi
        .detectSingleFace(img, new faceapi.TinyFaceDetectorOptions({ inputSize: 416, scoreThreshold: 0.5 }))
        .withFaceLandmarks(true) // true = use tiny landmarks model
        .withFaceDescriptor();

    if (!detection) {
        throw new Error('No face detected in the image. Please ensure your face is clearly visible.');
    }

    // Convert Float32Array to regular array for JSON serialization
    return Array.from(detection.descriptor);
}

/**
 * Extract face descriptors from multiple images and average them.
 * Used during registration with 3 angles (front, left, right).
 * @param {string[]} base64Images - Array of base64 data URLs
 * @returns {Promise<number[]>} - Averaged 128-dim face descriptor
 */
async function getAverageFaceDescriptor(base64Images) {
    if (!faceModelsLoaded) await loadFaceModels();

    const descriptors = [];
    const errors = [];

    for (let i = 0; i < base64Images.length; i++) {
        try {
            const desc = await getFaceDescriptorFromBase64(base64Images[i]);
            descriptors.push(desc);
        } catch (err) {
            errors.push(`Image ${i + 1}: ${err.message}`);
        }
    }

    if (descriptors.length === 0) {
        throw new Error(`No face detected in any images. ${errors.join(' | ')}`);
    }

    // Average all descriptors
    const dim = descriptors[0].length;
    const avg = new Array(dim).fill(0);
    for (const desc of descriptors) {
        for (let j = 0; j < dim; j++) {
            avg[j] += desc[j];
        }
    }
    for (let j = 0; j < dim; j++) {
        avg[j] /= descriptors.length;
    }

    console.log(`✅ Averaged ${descriptors.length} face descriptors (${errors.length} failed)`);
    return avg;
}

// ==================== Face Comparison ====================
/**
 * Compare two face descriptors using Euclidean distance.
 * @param {number[]} stored - The stored face descriptor (from registration)
 * @param {number[]} captured - The captured face descriptor (from webcam)
 * @param {number} [threshold] - Distance threshold (lower = stricter)
 * @returns {{ match: boolean, distance: number, confidence: number }}
 */
function compareFaceDescriptors(stored, captured, threshold = FACE_MATCH_THRESHOLD) {
    if (!stored || !captured || stored.length !== captured.length) {
        return { match: false, distance: Infinity, confidence: 0 };
    }

    // Euclidean distance
    let sumSq = 0;
    for (let i = 0; i < stored.length; i++) {
        const diff = stored[i] - captured[i];
        sumSq += diff * diff;
    }
    const distance = Math.sqrt(sumSq);

    // Convert distance to confidence percentage (0-100)
    // Distance of 0 = 100% confidence, distance of 1.0+ = 0%
    const confidence = Math.max(0, Math.min(100, (1 - distance) * 100));
    const match = distance < threshold;

    return { match, distance: parseFloat(distance.toFixed(4)), confidence: parseFloat(confidence.toFixed(1)) };
}

/**
 * Full verification pipeline: extract descriptor from webcam and compare with stored.
 * @param {string} capturedBase64 - Webcam capture as base64 data URL
 * @param {number[]} storedDescriptor - Stored face descriptor from registration
 * @returns {Promise<{ match: boolean, distance: number, confidence: number }>}
 */
async function verifyFace(capturedBase64, storedDescriptor) {
    const capturedDescriptor = await getFaceDescriptorFromBase64(capturedBase64);
    return compareFaceDescriptors(storedDescriptor, capturedDescriptor);
}

console.log('🧠 Face recognition module loaded');
